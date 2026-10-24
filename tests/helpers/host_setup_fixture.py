"""Synthetic signed releases for host setup, without demo component assumptions."""

import hashlib
import importlib.util
import io
import tarfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def release_module():
    spec = importlib.util.spec_from_file_location(
        "host_release", ROOT / "scripts/release.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archive(directory, component="worker", version="1.0.0", host=True):
    name = "cedar-" + component + "-" + version
    files = {
        "VERSION": (version + "\n").encode(),
        "bundle.yaml": yaml.safe_dump(
            {"product": "cedar", "name": component, "version": version}
        ).encode(),
        "deployment/common.py": b"# independent external-image component\n",
    }
    if host:
        files["scripts/prepare-host.sh"] = b"#!/bin/bash\nexit 0\n"
    files["checksums.sha256"] = "".join(
        hashlib.sha256(data).hexdigest() + "  " + key + "\n"
        for key, data in sorted(files.items())
    ).encode()
    path = directory / (name + "-offline.tar.gz")
    directories = {name}
    for key in files:
        directories.update(str(p) for p in (Path(name) / key).parents if str(p) != ".")
    with tarfile.open(str(path), "w:gz") as output:
        for key in sorted(directories, key=lambda v: (v.count("/"), v)):
            entry = tarfile.TarInfo(key)
            entry.type = tarfile.DIRTYPE
            entry.mode = 0o755
            output.addfile(entry)
        for key, data in files.items():
            entry = tarfile.TarInfo(name + "/" + key)
            entry.mode = 0o644
            entry.size = len(data)
            output.addfile(entry, io.BytesIO(data))
    return path
