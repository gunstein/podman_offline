"""Build the offline bundles: dist/<product>-<component>-<version>-offline.tar.gz (+ .sha256).

<product> is bundles.yaml's product name; a standalone manifest fixture builds
dist/myproduct-<version>-offline.tar.gz (common.STANDALONE_PRODUCT).
"""

import hashlib
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml

from deployment import catalog, common
from deployment import render as rendering

ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "build" / "bundle"
DIST = ROOT / "dist"


class BundleError(Exception):
    """Error shown as a single ERROR line without a traceback."""


def run(*args):
    """Show and run a command; stop on a failing status."""
    print("+", " ".join(map(str, args)))
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


def manifest_images(manifests=None):
    """Find images in the given manifests, or in every catalog component.

    Without bundles.yaml the standalone manifests/ fixture is used. Directories
    under components/ that the catalog does not list are never read.
    """
    documents = []
    if manifests:
        paths = sorted(manifests.glob("*.yaml"))
    elif (ROOT / "bundles.yaml").exists():
        try:
            names = catalog.source_descriptors(ROOT)
        except common.DeployError as error:
            raise BundleError(str(error)) from None
        paths = [
            path
            for name in names
            for path in sorted(
                (ROOT / "components" / name / "manifests").glob("*.yaml")
            )
        ]
    else:
        paths = sorted((ROOT / "manifests").glob("*.yaml"))
    try:
        for path in paths:
            path_documents = rendering.load_yaml_all(path)
            rendering.check_kinds(path_documents, path)
            documents.extend(path_documents)
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
        print("+", " ".join(args))
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
    # Standalone manifest fixtures keep explicit root-level config; products do not.
    if not (ROOT / "components").is_dir():
        sources.extend(
            [(ROOT / "config.yaml", ROOT), (ROOT / "config.defaults.yaml", ROOT)]
        )
    for directory in directories:
        if directory == ROOT:
            continue
        base = ROOT / "build/dev" / directory.name
        sources.append((directory / "config.defaults.yaml", base))
        # A local complete config is private state, not a configuration layer.
        sources.append((directory / "config.yaml", directory))
        sources.append((base / "config.yaml", base))
        sources.append((ROOT / "config/common.defaults.yaml", base))
        sources.append((ROOT / "config/dev.yaml", base))
    for path, base in sources:
        if path.exists():
            try:
                config = rendering.config_layer(path)
                secrets.update(rendering.generated_secret_paths(config, base))
                for entries in rendering.file_group_sources(
                    config, common.SECRET_FILES
                ).values():
                    secrets.update(
                        rendering.resolve_path(entry["path"], base).resolve()
                        for entry in entries
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

    A product guards every catalog component, not only the bundled one; a
    standalone fixture guards any component directory that happens to exist.
    """
    if (ROOT / "bundles.yaml").exists():
        names = list(catalog.load_catalog(ROOT))
        return [ROOT] + [ROOT / "components" / name for name in names]
    return [ROOT] + sorted((ROOT / "components").glob("*"))


def build_release(version, descriptor=None):
    """Package one compiled component descriptor or a standalone manifest fixture."""
    components = [str(descriptor["name"])] if descriptor else []
    name = (
        f"{descriptor['product']}-{components[0]}-{version}"
        if descriptor
        else f"{common.STANDALONE_PRODUCT}-{version}"
    )
    target = STAGE / name

    directories = [ROOT / "components" / component for component in components]
    images = (
        sorted(
            {
                image
                for directory in directories
                for image in manifest_images(directory / "manifests")
            }
        )
        if directories
        else manifest_images()
    )
    guard = generated_secret_guard(guarded_directories())
    guard(
        ROOT,
        [
            "deploy",
            "deployment",
            "VERSION",
            "README.md",
            "config.defaults.yaml",
            "manifests",
            "scripts",
            "quadlet",
            "files",
        ],
    )

    target.mkdir(parents=True)

    for filename in ["deploy", "README.md"] + (
        ["VERSION", "config.defaults.yaml"] if not components else []
    ):
        shutil.copy2(ROOT / filename, target / filename)

    shutil.copytree(ROOT / "deployment", target / "deployment", ignore=guard)

    if components:
        # Informational copy of the descriptor's version for operators.
        (target / "VERSION").write_text(version + "\n", encoding="utf-8")

    for component, directory in zip(components, directories):
        (target / "components").mkdir(exist_ok=True)
        destination = target / "components" / component
        destination.mkdir()
        for entry in (
            "manifests",
            "config.defaults.yaml",
            "route.conf",
            "client.yaml",
            "files",
        ):
            source = directory / entry
            if not source.exists():
                continue
            guard(directory, [entry])
            if source.is_dir():
                shutil.copytree(source, destination / entry, ignore=guard)
            else:
                shutil.copy2(source, destination / entry)
    if components and (ROOT / "config/common.defaults.yaml").exists():
        (target / "config").mkdir()
        guard(ROOT / "config", ["common.defaults.yaml"])
        shutil.copy2(
            ROOT / "config/common.defaults.yaml", target / "config/common.defaults.yaml"
        )
    if components:
        # The compiled descriptor lets the target work without bundles.yaml.
        (target / "bundle.yaml").write_text(
            yaml.safe_dump(descriptor, sort_keys=False), encoding="utf-8"
        )
    for dirname in (
        ["scripts", "quadlet"] if components else ["manifests", "scripts", "quadlet"]
    ):
        shutil.copytree(ROOT / dirname, target / dirname, ignore=guard)

    # Optional files/ ships product files for SECRET_FILES and VOLUME_FILES.
    if (ROOT / "files").is_dir():
        shutil.copytree(ROOT / "files", target / "files", ignore=guard)

    if not components:
        (target / "credentials").mkdir(mode=0o700)
        (target / "credentials").chmod(0o700)
        (target / "build").mkdir()

    (target / "deploy").chmod(0o755)
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

    DIST.mkdir(exist_ok=True)
    archive = DIST / f"{name}-offline.tar.gz"

    # gzip level 6 compresses about three times faster than tarfile's default
    # 9, for archives under 1 % larger (measured on 3 GB of binaries).
    with tarfile.open(archive, "w:gz", compresslevel=6) as tar:
        tar.add(target, arcname=name, filter=owner_root)

    (DIST / f"{archive.name}.sha256").write_text(
        f"{sha256(archive)}  {archive.name}\n",
        encoding="utf-8",
    )

    print(f"[OK] {archive}")
    return archive


def build(selected=()):
    """Build one bundle per catalog component, or one standalone manifest fixture.

    selected names catalog components to build; the whole catalog is still
    validated. A partial build leaves dist/current-bundles.txt unchanged,
    because that list names the complete current product.
    """
    if not (ROOT / "bundles.yaml").exists():
        if selected:
            raise BundleError("Component names need a catalog (bundles.yaml)")
        manifest_images()
        guard = generated_secret_guard(guarded_directories())
        guard(ROOT, ["files", "manifests", "scripts", "quadlet"])
        shutil.rmtree(STAGE, ignore_errors=True)
        build_release((ROOT / "VERSION").read_text(encoding="utf-8").strip())
        return
    # Validate the whole catalog and its selected images before any output.
    descriptors = catalog.source_descriptors(ROOT)
    unknown = sorted(set(selected) - set(descriptors))
    if unknown:
        raise BundleError(
            "Unknown component " + ", ".join(unknown) + "; see bundles.yaml"
        )
    manifest_images()
    guard = generated_secret_guard(guarded_directories())
    guard(ROOT, ["files", "manifests", "scripts", "quadlet"])
    shutil.rmtree(STAGE, ignore_errors=True)
    current = [
        build_release(descriptor["version"], descriptor)
        for name, descriptor in descriptors.items()
        if not selected or name in selected
    ]
    if selected:
        return
    # dist/ also keeps earlier archives, for example of a removed component that
    # is still installed somewhere; this list names only the current product.
    (DIST / "current-bundles.txt").write_text(
        "".join(path.name + "\n" for path in current), encoding="utf-8"
    )


def main(arguments=None):
    """Build the bundle and return an exit code without traceback for expected errors.

    arguments are optional component names (default: the command line).
    """
    try:
        build(sys.argv[1:] if arguments is None else arguments)
    except (
        OSError,
        BundleError,
        common.DeployError,
        yaml.YAMLError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
