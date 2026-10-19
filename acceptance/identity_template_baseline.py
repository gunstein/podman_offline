#!/usr/bin/env python3
"""Prepare only the disposable Identity lab baseline before a template upgrade.

The --identity-only scenario builds this genuine old in-app implementation,
committed locally so the clean-checkout bundle check still applies; the upgrade
builder checks out the tested revision to build the new one.
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
    # A local commit in the disposable clone keeps every later build on a clean tree.
    for command in (
        ["add", "--"] + list(FILES),
        [
            "-c",
            "user.name=acceptance",
            "-c",
            "user.email=lab@invalid",
            "commit",
            "-q",
            "-m",
            "Acceptance-only Identity baseline " + VERSION,
        ],
    ):
        if subprocess.run(["git", "-C", str(source)] + command, check=False).returncode:
            raise RuntimeError("Could not commit the pinned Identity baseline")
    print("PASS: prepared and committed pinned in-app Identity baseline " + VERSION)


if __name__ == "__main__":
    prepare(Path.cwd())
