"""Build the offline bundle: dist/myproduct-<version>-offline.tar.gz (+ .sha256)."""

import hashlib
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml

import deploy

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
    """Find images in the selected manifests or all source components."""
    documents = []
    paths = (
        sorted(manifests.glob("*.yaml"))
        if manifests
        else sorted((ROOT / "components").glob("*/manifests/*.yaml"))
    )
    if manifests is None and not paths:
        paths = sorted((ROOT / "manifests").glob("*.yaml"))
    for path in paths:
        documents.extend(deploy.load_yaml_all(path))
    try:
        return deploy.find_images(documents)
    except deploy.DeployError as error:
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
    sources = []
    # Standalone manifest fixtures keep explicit root-level config; products do not.
    if not (ROOT / "components").is_dir():
        sources.extend(
            [(ROOT / "config.yaml", ROOT), (ROOT / "config.defaults.yaml", ROOT)]
        )
    for directory in config_dirs or [ROOT]:
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
                config = deploy.config_layer(path)
                secrets.update(deploy.generated_secret_paths(config, base))
            except (deploy.DeployError, yaml.YAMLError):
                raise BundleError(
                    f"Cannot validate generated secret paths in {path}"
                ) from None

    def guard(directory, names):
        """Fail before copying a secret file or a directory containing one."""
        for name in names:
            path = (Path(directory) / name).resolve()
            for secret in secrets:
                if path == secret or path in secret.parents:
                    raise BundleError(
                        f"Cannot bundle generated secret via {Path(directory) / name}"
                    )
        return [
            name
            for name in names
            if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
        ]

    return guard


def build_release(version, bundle_name=None, components=None):
    """Package one selected bundle or a standalone manifest fixture."""
    name = (
        f"myproduct-{bundle_name}-{version}" if bundle_name else f"myproduct-{version}"
    )
    target = STAGE / name

    directories = [ROOT / "components" / component for component in (components or [])]
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
    guard = generated_secret_guard([ROOT] + sorted((ROOT / "components").glob("*")))
    guard(
        ROOT,
        [
            "deploy",
            "deploy.py",
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

    for filename in [
        "deploy",
        "deploy.py",
        "VERSION",
        "README.md",
    ] + (["config.defaults.yaml"] if not components else ["CORE_VERSION"]):
        shutil.copy2(ROOT / filename, target / filename)

    for component, directory in zip(components or [], directories):
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
    if components:
        (target / "config").mkdir()
        guard(ROOT / "config", ["common.defaults.yaml"])
        shutil.copy2(
            ROOT / "config/common.defaults.yaml", target / "config/common.defaults.yaml"
        )
        (target / "bundle.yaml").write_text(
            yaml.safe_dump({"name": bundle_name, "components": components}),
            encoding="utf-8",
        )
    for dirname in (
        ["scripts", "quadlet"] if components else ["manifests", "scripts", "quadlet"]
    ):
        shutil.copytree(ROOT / dirname, target / dirname, ignore=guard)

    # Optional files/ ships product files for SECRET_FILES and VOLUME_FILES.
    if (ROOT / "files").is_dir():
        shutil.copytree(ROOT / "files", target / "files", ignore=guard)

    if not components:
        (target / "generated-certificates").mkdir(mode=0o700)
        (target / "generated-certificates").chmod(0o700)
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

    with tarfile.open(archive, "w:gz") as tar:
        tar.add(target, arcname=name, filter=owner_root)

    (DIST / f"{archive.name}.sha256").write_text(
        f"{sha256(archive)}  {archive.name}\n",
        encoding="utf-8",
    )

    print(f"[OK] {archive}")


def build():
    """Build every defined component bundle, or one standalone manifest fixture."""
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    definitions = (
        deploy.load_yaml(ROOT / "bundles.yaml")
        if (ROOT / "bundles.yaml").exists()
        else {None: None}
    )
    if not isinstance(definitions, dict) or not definitions:
        raise BundleError("bundles.yaml must define at least one bundle")
    for name, components in definitions.items():
        if name is not None and (
            name not in ("app1", "app2", "help")
            or components != (["help"] if name == "help" else ["core", name])
        ):
            raise BundleError("Invalid bundle component definition")
    manifest_images()
    guard = generated_secret_guard([ROOT] + sorted((ROOT / "components").glob("*")))
    guard(ROOT, ["files", "manifests", "scripts", "quadlet"])
    shutil.rmtree(STAGE, ignore_errors=True)
    for name, components in definitions.items():
        build_release(version, name, components)


def main():
    """Build the bundle and return an exit code without traceback for expected errors."""
    try:
        build()
    except (
        OSError,
        BundleError,
        yaml.YAMLError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
