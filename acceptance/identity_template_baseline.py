#!/usr/bin/env python3
"""Prepare only the disposable Identity lab baseline before a template upgrade.

The --identity-only scenario builds this genuine old in-app implementation,
then the ordinary upgrade builder clones current HEAD to test the new one.
Never run this against an operator's working checkout.
"""

import subprocess
from pathlib import Path

BASELINE = "932c7f3a647a84fb5388144bc822f895cc40d959"
VERSION = "0.4.11"
FILES = (
    "IDENTITY_VERSION",
    "components/identity/config.defaults.yaml",
    "components/identity/manifests/50-identity.yaml",
    "apps/identity/Program.cs",
    "apps/identity/DatabaseEnvironment.cs",
    "apps/identity/Containerfile",
)


def prepare(source):
    """Read pinned files from local git; no network or dependency on an old tree."""
    contents = {}
    for name in FILES:
        result = subprocess.run(
            ["git", "-C", str(source), "show", BASELINE + ":" + name],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("Pinned Identity baseline is unavailable in local git")
        contents[name] = result.stdout
    for name, content in contents.items():
        (source / name).write_bytes(content)
    print("PASS: prepared pinned in-app Identity baseline " + VERSION)


if __name__ == "__main__":
    prepare(Path.cwd())
