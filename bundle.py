"""Build the offline bundles: dist/<product>-<component>-<version>-offline.tar.gz (+ .sha256).

<product> is bundles.yaml's product name. With --environment <name>, the
overrides of config/<name>.yaml are compiled into each bundle's
config.defaults.yaml (backlog 84) and the output goes to dist/<name>/.
"""

import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml

from deployment import arguments, catalog, common, environment, output, templates
from deployment import render as rendering

# A child of the deployment logger: same handlers, streams and convention.
log = logging.getLogger("deployment.bundle")

ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "build" / "bundle"
DIST = ROOT / "dist"
# OpenPGP key (ID or fingerprint) that signs each archive (<archive>.asc). The
# target verifies it with gpgv before unpacking; see README, "Signed bundles".
SIGNING_KEY = "BUNDLE_SIGNING_KEY"


class BundleError(Exception):
    """Error shown as a single ERROR line without a traceback."""


# Operator documents shipped in every component bundle (backlog 64).
RELEASE_DOCS = ("docs/PRODUCTION-INSTALL.md", "docs/PFX-CREDENTIALS.md")


def run(*args):
    """Show and run a command; stop on a failing status."""
    log.debug("+ " + " ".join(map(str, args)))
    subprocess.run(list(map(str, args)), check=True)


def sha256(path):
    """Compute a file's SHA256 without reading the whole file into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def owner_root(info):
    """Set the tar member's owner to root without changing the file mode."""
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    return info


def resolved_manifests(paths):
    """{path: documents} with image variables resolved (render.load_manifest).

    The component is the directory above manifests/ (components/<id>/manifests).
    """
    result = {}
    try:
        for path in paths:
            documents = rendering.load_manifest(path)
            rendering.pod_specs(documents, str(path))  # Kinds, named by file.
            result[path] = documents
    except common.DeployError as error:
        raise BundleError(str(error)) from None
    return result


def manifest_images(manifests=None, names=None):
    """Find images in the given manifests, the named components or the catalog.

    Directories under components/ that the catalog does not list are never
    read, nor components a build environment leaves out (names, backlog 85).
    Image variables are resolved, so pull, build and bundle see the same names.
    """
    documents = []
    if manifests:
        paths = sorted(manifests.glob("*.yaml"))
    else:
        try:
            names = list(catalog.source_descriptors(ROOT)) if names is None else names
        except common.DeployError as error:
            raise BundleError(str(error)) from None
        paths = [
            path
            for name in names
            for path in sorted(
                (ROOT / "components" / name / "manifests").glob("*.yaml")
            )
        ]
    for path_documents in resolved_manifests(paths).values():
        documents.extend(path_documents)
    try:
        return rendering.find_images(documents)
    except common.DeployError as error:
        raise BundleError(str(error)) from None


def pull_images(images):
    """Pull registry images afresh; localhost/ names must already exist locally."""
    for image in sorted(set(images)):
        registry = image.split("/", 1)[0]
        if registry == "localhost":
            continue
        args = ["podman", "pull", "--policy=always", image]
        log.debug("+ " + " ".join(args))
        try:
            # Registry errors may contain authentication details; report only the image and hint.
            subprocess.run(  # noqa: UP022 - Python 3.6 lacks capture_output
                args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError:
            raise BundleError(
                f"Cannot pull image {image!r}; check podman login {registry} and the registry CA certificate"
            ) from None


def generated_secret_guard(config_dirs=None):
    """Reject copies of declared local secrets, including symlink aliases."""
    secrets = set()
    directories = list(config_dirs or [ROOT])
    credential_roots = {(ROOT / "credentials").resolve()}
    for directory in directories:
        if directory != ROOT:
            credential_roots.add((directory / "credentials").resolve())
            credential_roots.add(
                (ROOT / "build/dev" / directory.name / "credentials").resolve()
            )
    sources = []
    for directory in directories:
        if directory == ROOT:
            continue
        base = ROOT / "build/dev" / directory.name
        sources.append((directory / "config.defaults.yaml", base, directory.name))
        # A local complete config is private state, not a configuration layer.
        sources.append((directory / "config.yaml", directory, directory.name))
        sources.append((base / "config.yaml", base, directory.name))
        sources.append((ROOT / "config/dev.yaml", base, directory.name))
    for path, base, component in sources:
        if path.exists():
            try:
                config = rendering.config_layer(path)
                secrets.update(rendering.generated_secret_paths(config, base))
                for group in (common.SECRET_FILES, common.VOLUME_FILES):
                    for entries in rendering.file_group_sources(config, group).values():
                        for entry in entries:
                            if "component_file" in entry:
                                # Explicit public release content may be delivered as a
                                # Secret. Ordinary private declarations still protect
                                # that same file, even when an alias names it.
                                rendering.resolve_file_source(
                                    entry, base, component, ROOT
                                )
                            elif group == common.SECRET_FILES:
                                secrets.add(
                                    rendering.resolve_file_source(entry, base).resolve()
                                )
            except (common.DeployError, yaml.YAMLError):
                raise BundleError(
                    f"Cannot validate generated secret paths in {path}"
                ) from None

    def guard(directory, names):
        """Fail before copying a secret file or a directory containing one."""
        for name in names:
            path = (Path(directory) / name).resolve()
            for private in credential_roots:
                if (
                    path == private
                    or private in path.parents
                    or path in private.parents
                ):
                    raise BundleError(
                        f"Cannot bundle credentials via {Path(directory) / name}"
                    )
            for secret in secrets:
                if path == secret or path in secret.parents or secret in path.parents:
                    raise BundleError(
                        f"Cannot bundle generated secret via {Path(directory) / name}"
                    )
        return [
            name
            for name in names
            if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
        ]

    return guard


def guarded_directories():
    """Directories whose private files must never enter any archive.

    A product guards every catalog component, not only the bundled one, also
    those a build environment leaves out: only their IDs are needed here.
    """
    names = catalog.catalog_components(ROOT)[2]
    return [ROOT] + [ROOT / "components" / name for name in names]


def output_directories(environment_name):
    """Staging and output of one build; each environment has its own.

    build/bundle and dist/ without an environment, build/bundle-<name> and
    dist/<name>/ with one: the same component version can have different
    bytes in two environments, and one build never removes another's files.
    """
    if environment_name is None:
        return STAGE, DIST
    return STAGE.with_name(f"{STAGE.name}-{environment_name}"), DIST / environment_name


def check_declarations(component, env_overrides):
    """Check an overridden component's merged ENVIRONMENT before any output.

    Only what the declarations decide without the operator's settings:
    variable names and placeholder syntax, the merge, SECRET_FILES
    declarations and generated Secret names, @@CLIENT_ID@@ without
    client.yaml, and the containers: each must exist once, without
    hand-written envFrom or the same variable in its env. A container name
    written as a @@NAME@@ setting is known only at install, so while the
    component has one, the container checks of non-empty entries are left to
    install, which renders the compiled ENVIRONMENT; an empty entry for a
    container without common ENVIRONMENT is not compiled, so it must name
    exactly one container written literally. Setting
    values, credentials and the PostgreSQL guard are checked by validate and
    install (deploy.validate_component).
    """
    directory = ROOT / "components" / component
    defaults_file = directory / "config.defaults.yaml"
    defaults = rendering.merge_config(defaults_file) if defaults_file.exists() else {}
    templates.declarations(environment.with_recipes(defaults, component, env_overrides))
    client = rendering.with_client_settings({}, component)
    manifests = resolved_manifests(sorted((directory / "manifests").glob("*.yaml")))
    containers = rendering.named_containers(
        [doc for documents in manifests.values() for doc in documents]
    )
    names_known = not any("@@" in str(name) for name in containers)
    merged = environment.read(component, env_overrides)
    for container in environment.overridden_containers(component, env_overrides):
        # An empty entry absent from the merged ENVIRONMENT is not compiled
        # into the bundle, so install never sees it: check it here or refuse.
        if names_known or (container not in merged and container in containers):
            environment.check_exists(component, container, containers, env_overrides)
        elif container not in merged:
            raise BundleError(
                f"{env_overrides.path}: overrides.{component}.ENVIRONMENT."
                f"{container}: an empty entry for a container the build cannot "
                "find (a container name is a @@NAME@@ setting) changes nothing "
                "and cannot be checked later; remove it"
            )
    for container, values in merged.items():
        environment.check_client_settings(
            component, container, values, client, env_overrides
        )
        if names_known:
            environment.check_container(
                component, container, values, containers, env_overrides
            )


def compiled_defaults(path, component, env_overrides):
    """config.defaults.yaml with the selected overrides merged into ENVIRONMENT.

    Settings keep their YAML types, read as merge_config reads them;
    ENVIRONMENT and MOUNTS keep their written text (environment.TextLoader).
    safe_dump quotes every text that YAML would read as another type, and
    allow_unicode=False writes every non-ASCII character as an escape, so
    nothing is lost (a literal U+0085 would otherwise read back as a line
    break). The bundle reads exactly the merged text. Comments are not kept;
    build_release writes this file only when the environment changes the
    component's ENVIRONMENT.
    """
    typed = rendering.config_layer(path) if path.exists() else {}
    text = (environment.load(path) or {}) if path.exists() else {}
    compiled = {
        key: text[key] if key == common.MOUNTS else value
        for key, value in typed.items()
    }
    compiled[common.ENVIRONMENT] = environment.read(component, env_overrides)
    return yaml.safe_dump(compiled, sort_keys=False, allow_unicode=False)


def build_release(version, descriptor, env_overrides=None, stage=None, dist=None):
    """Package one compiled component descriptor into dist (default dist/)."""
    stage = stage or STAGE
    dist = dist or DIST
    component = str(descriptor["name"])
    name = f"{descriptor['product']}-{component}-{version}"
    target = stage / name

    directory = ROOT / "components" / component
    # One resolution for the image list and the shipped manifests.
    manifests = resolved_manifests(sorted((directory / "manifests").glob("*.yaml")))
    try:
        images = rendering.find_images(
            [doc for documents in manifests.values() for doc in documents]
        )
    except common.DeployError as error:
        raise BundleError(str(error)) from None
    guard = generated_secret_guard(guarded_directories())
    guard(ROOT, ["deploy.sh", "deployment", "README.md", "scripts", "quadlet"])

    target.mkdir(parents=True)
    for filename in ("deploy.sh", "README.md"):
        shutil.copy2(ROOT / filename, target / filename)
    shutil.copytree(ROOT / "deployment", target / "deployment", ignore=guard)
    # Informational copy of the descriptor's version for operators.
    (target / "VERSION").write_text(version + "\n", encoding="utf-8")

    destination = target / "components" / component
    destination.mkdir(parents=True)
    guard(directory, ["manifests"])
    (destination / "manifests").mkdir()
    for path, documents in manifests.items():
        # Literal images only; config/images.yaml is not shipped.
        (destination / "manifests" / path.name).write_text(
            yaml.safe_dump_all(
                [doc for doc in documents if doc is not None], sort_keys=False
            ),
            encoding="utf-8",
        )
    for entry in (
        "config.defaults.yaml",
        "route.conf",
        "client.yaml",
        "files",
    ):
        source = directory / entry
        if not source.exists():
            continue
        guard(directory, [entry])
        if entry == "files":
            # Release files are copied, not followed: no links, no special files.
            try:
                rendering.check_component_file_tree(source)
            except common.DeployError as error:
                raise BundleError(str(error)) from None
        if source.is_dir():
            shutil.copytree(source, destination / entry, ignore=guard)
        else:
            shutil.copy2(source, destination / entry)
    if environment.read(component, env_overrides) != environment.read(component):
        # The bundle carries its environment: production reads only this file.
        (destination / "config.defaults.yaml").write_text(
            compiled_defaults(
                directory / "config.defaults.yaml", component, env_overrides
            ),
            encoding="utf-8",
        )
    # The operator guide and the documents it links travel with every release
    # (backlog 64); the guide links nothing else except README.md.
    for document in RELEASE_DOCS:
        if (ROOT / document).is_file():
            (target / "docs").mkdir(exist_ok=True)
            shutil.copy2(ROOT / document, target / document)
    # The compiled descriptor lets the target work without bundles.yaml.
    (target / "bundle.yaml").write_text(
        yaml.safe_dump(descriptor, sort_keys=False), encoding="utf-8"
    )
    for dirname in ("scripts", "quadlet"):
        shutil.copytree(ROOT / dirname, target / dirname, ignore=guard)

    (target / "deploy.sh").chmod(0o755)
    for script in (target / "scripts").glob("*.sh"):
        script.chmod(0o755)

    image_dir = target / "images"
    image_dir.mkdir()
    pull_images(images)
    run("podman", "save", "-m", "-o", image_dir / "images.tar", *images)
    (image_dir / "images.txt").write_text("\n".join(images) + "\n", encoding="utf-8")

    checksums = [
        f"{sha256(path)}  {path.relative_to(target)}"
        for path in sorted(target.rglob("*"))
        if path.is_file() and path.name != "checksums.sha256"
    ]
    (target / "checksums.sha256").write_text(
        "\n".join(checksums) + "\n",
        encoding="utf-8",
    )

    dist.mkdir(parents=True, exist_ok=True)
    archive = dist / f"{name}-offline.tar.gz"

    # gzip level 6 compresses about three times faster than tarfile's default
    # 9, for archives under 1 % larger (measured on 3 GB of binaries).
    with tarfile.open(archive, "w:gz", compresslevel=6) as tar:
        tar.add(target, arcname=name, filter=owner_root)

    (dist / f"{archive.name}.sha256").write_text(
        f"{sha256(archive)}  {archive.name}\n",
        encoding="utf-8",
    )
    sign(archive)

    log.info(f"[OK] {archive}")
    return archive


def sign(archive):
    """Write a detached OpenPGP signature beside the archive, or say it is unsigned.

    The checksum only detects corruption; whoever can replace the archive can
    replace it too. The signature, checked with the organisation's public key on
    the target, shows who built it. An old signature is removed first, so a
    rebuilt archive is never left beside a signature of an earlier one.
    """
    signature = archive.with_name(archive.name + ".asc")
    if signature.exists():
        signature.unlink()
    key = os.environ.get(SIGNING_KEY, "").strip()
    if not key:
        log.warning(
            f"WARNING: {archive.name} is unsigned; set {SIGNING_KEY} to sign bundles"
        )
        return None
    run(
        "gpg",
        "--batch",
        "--yes",
        "--local-user",
        key,
        "--armor",
        "--output",
        signature,
        "--detach-sign",
        archive,
    )
    return signature


def build(selected=(), environment_name=None):
    """Build one bundle per catalog component.

    selected names catalog components to build; the whole catalog is still
    validated. A partial build leaves current-bundles.txt unchanged,
    because that list names the complete current product. environment_name
    selects config/<name>.yaml: its components: is the product (the others
    get no bundle and their manifests are not read), its overrides are part of
    every derived descriptor and bundled config.defaults.yaml, and the output
    goes to dist/<name>/ (output_directories). The source files are never
    changed.
    """
    if not (ROOT / "bundles.yaml").exists():
        raise BundleError(f"Missing {ROOT / 'bundles.yaml'}")
    env_overrides = (
        environment.read_environment_file(ROOT, environment_name)
        if environment_name is not None
        else None
    )
    stage, dist = output_directories(environment_name)
    # Validate the whole catalog, its declarations and its selected images
    # before any output.
    descriptors = catalog.source_descriptors(ROOT, env_overrides)
    unknown = sorted(set(selected) - set(descriptors))
    if unknown and env_overrides and env_overrides.selected is not None:
        raise BundleError(
            ", ".join(unknown) + f" is not in {env_overrides.path} components:; "
            "build it with an environment that includes it"
        )
    if unknown:
        raise BundleError(
            "Unknown component " + ", ".join(unknown) + "; see bundles.yaml"
        )
    # Only overridden components: the common declarations keep their checks
    # at validate and install, as without an environment.
    for name in sorted(env_overrides.components if env_overrides else {}):
        check_declarations(name, env_overrides)
    manifest_images(names=list(descriptors))
    guard = generated_secret_guard(guarded_directories())
    guard(ROOT, ["scripts", "quadlet"])
    shutil.rmtree(stage, ignore_errors=True)
    current = [
        build_release(descriptor["version"], descriptor, env_overrides, stage, dist)
        for name, descriptor in descriptors.items()
        if not selected or name in selected
    ]
    if selected:
        return
    # dist/ also keeps earlier archives, for example of a removed component that
    # is still installed somewhere; this list names only the current product.
    (dist / "current-bundles.txt").write_text(
        "".join(path.name + "\n" for path in current), encoding="utf-8"
    )


def parser():
    """./build-bundle.sh [--environment <name>] [<component> ...] [--verbose]."""
    result = arguments.Parser(
        prog="./build-bundle.sh",
        usage="./build-bundle.sh [--environment <name>] [<component> ...] [--verbose]",
        description=(
            "Build offline bundles; without components, every catalog component, "
            "or every component of the --environment"
        ),
        allow_abbrev=False,
    )
    result.add_argument(
        "--environment",
        metavar="<name>",
        help="compile the ENVIRONMENT overrides of config/<name>.yaml into the "
        "bundles and write them to dist/<name>/",
    )
    result.add_argument(
        "--verbose",
        action=arguments.Once,
        default=False,
        help="also show each host command",
    )
    result.add_argument("components", nargs="*", metavar="<component>")
    return result


def main(command_line=None):
    """Build the bundle and return an exit code without traceback for expected errors.

    command_line is the argument list (default: sys.argv[1:]): optional
    --environment <name>, component names and --verbose. Usage errors exit 2
    and --help 0.
    """
    try:
        args = arguments.parse(
            parser(),
            sys.argv[1:] if command_line is None else command_line,
            flags=("--environment",),
        )
    except arguments.UsageError as error:
        return error.code
    output.configure(verbose=args.verbose)
    try:
        build(args.components, args.environment)
    except (
        OSError,
        BundleError,
        common.DeployError,
        yaml.YAMLError,
        subprocess.CalledProcessError,
    ) as error:
        log.error(f"ERROR: {error}")
        return 1
    log.info("PASS: ./build-bundle.sh completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
