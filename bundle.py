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


def manifest_images():
    """Find sorted manifest images and turn image errors into BundleError."""
    documents = []
    for path in sorted((ROOT / "manifests").glob("*.yaml")):
        documents.extend(deploy.load_yaml_all(path))
    try:
        return deploy.find_images(documents)
    except deploy.DeployError as error:
        raise BundleError(str(error)) from None


def build():
    """Build a checksummed offline bundle from manifests and local Podman images."""
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    name = f"myproduct-{version}"
    target = STAGE / name

    images = manifest_images()

    shutil.rmtree(STAGE, ignore_errors=True)
    target.mkdir(parents=True)

    for filename in [
        "deploy",
        "deploy.py",
        "VERSION",
        "README.md",
        "config.example.yaml",
    ]:
        shutil.copy2(ROOT / filename, target / filename)

    for dirname in ["manifests", "scripts", "quadlet"]:
        shutil.copytree(ROOT / dirname, target / dirname)

    # Optional files/ ships product files for SECRET_FILES and VOLUME_FILES.
    if (ROOT / "files").is_dir():
        shutil.copytree(ROOT / "files", target / "files")

    (target / "generated-certificates").mkdir(mode=0o700)
    (target / "generated-certificates").chmod(0o700)  # uavhengig av umask
    (target / "build").mkdir()

    (target / "deploy").chmod(0o755)
    for script in (target / "scripts").glob("*.sh"):
        script.chmod(0o755)

    image_dir = target / "images"
    image_dir.mkdir()
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
