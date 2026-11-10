"""Build app1's changed public SQL in an isolated checkout, retaining source state."""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def build_upgrade(source, version, revision, product):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise RuntimeError("Invalid seed upgrade version")
    with tempfile.TemporaryDirectory(prefix="seed-upgrade-") as directory:
        release = Path(directory) / "release"
        subprocess.run(
            ["git", "clone", "--local", "--no-hardlinks", str(source), str(release)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(release), "checkout", "-q", "--detach", revision],
            check=True,
        )
        (release / "components/app1/VERSION").write_text(version + "\n")
        sql = release / "components/app1/files/sql/010-reference.sql"
        text = sql.read_text()
        if text.count("'release-v1'") != 1:
            raise RuntimeError("Expected exactly one reference release marker")
        sql.write_text(text.replace("'release-v1'", "'release-v2'"))
        changed = (
            subprocess.check_output(["git", "-C", str(release), "diff", "--name-only"])
            .decode()
            .splitlines()
        )
        if sorted(changed) != [
            "components/app1/VERSION",
            "components/app1/files/sql/010-reference.sql",
        ]:
            raise RuntimeError(
                "Seed upgrade must change exactly app1 VERSION and reference SQL"
            )
        subprocess.run(
            ["bash", "./build-bundle.sh", "app1"], cwd=str(release), check=True
        )
        name = product + "-app1-" + version + "-offline.tar.gz"
        (source / "dist").mkdir(exist_ok=True)
        for suffix in ("", ".sha256", ".asc"):
            artifact = release / "dist" / (name + suffix)
            if suffix != ".asc" or artifact.exists():
                shutil.copy2(str(artifact), str(source / "dist" / artifact.name))
        images = source / "build/bundle" / (product + "-app1-" + version) / "images"
        images.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            str(
                release
                / "build/bundle"
                / (product + "-app1-" + version)
                / "images/images.txt"
            ),
            str(images / "images.txt"),
        )
    print("PASS: isolated app1 SQL upgrade; source checkout unchanged")


if __name__ == "__main__":
    build_upgrade(Path(sys.argv[1]).resolve(), *sys.argv[2:])
