"""Compile bundle descriptors for test fixtures from the shipped demo catalog.

Tests that model the demo product use the real bundles.yaml, so the test graph
cannot drift from the shipped one. Tests of other products write their own
catalog instead.
"""

import json
import re
import shutil
from pathlib import Path

import yaml
from deployment import catalog

REPO = Path(__file__).resolve().parents[2]
DEMO = catalog.load_catalog(REPO)
# The catalog's Identity, which every compiled descriptor names (backlog 85).
IDENTITY = catalog.catalog_document(REPO)[1].get("identity")
DEMO_COMPONENTS = tuple(DEMO)
COMPATIBLE = {"min": "1.0.0", "before": "2.0.0"}


# The demo gateway's public settings, which every other component reads from
# platform's config.yaml.
def operator_config(config):
    """A non-gateway component's config.yaml as init-config writes it."""
    return {key: value for key, value in config.items() if key not in DEMO_PUBLIC}


DEMO_PUBLIC = catalog.public_settings(
    yaml.safe_load((REPO / "components/platform/config.defaults.yaml").read_text()),
    REPO / "components/platform/config.defaults.yaml",
)


def demo_descriptor(root, name, requirement=None, version=None):
    """Compile one demo component like bundle.py, reading the fixture's files.

    The version comes from the fixture's version file. A fixture without
    route.conf or client.yaml models a release that declares no such
    registration, so that role is left out.
    """
    entry = DEMO[name]
    directory = root / "components" / name
    descriptor = {
        "name": name,
        "product": "myproduct",
        "version": version or (directory / "VERSION").read_text().strip(),
        "identity": IDENTITY,
        "requires": {
            dependency: dict(requirement or COMPATIBLE)
            for dependency in entry["requires"]
        },
        "public_from": entry["public_from"],
        "routes": entry["routes"],
        "clients": entry["clients"],
        "apis": entry["apis"],
        "accepts": dict(entry["accepts"]),
        "api_secrets": dict(entry["api_secrets"]),
    }
    for role, filename in catalog.ROLE_FILES.items():
        if not (directory / filename).is_file():
            descriptor[role] = None
    return descriptor


def copy_image_variables(root):
    """Copy the demo's config/images.yaml, which its manifests' image fields use."""
    (root / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / "config/images.yaml", root / "config/images.yaml")


def write_descriptor(root, name, requirement=None, **changes):
    """Write the unpacked bundle's bundle.yaml for one demo component."""
    descriptor = demo_descriptor(root, name, requirement)
    descriptor.update(changes)
    path = root / "bundle.yaml"
    path.write_text(yaml.safe_dump(descriptor, sort_keys=False), encoding="utf-8")
    return descriptor


def mark_installed(root, home, name, version, requirement=None):
    """Record a completed demo install: metadata first, then the version marker."""
    descriptor = demo_descriptor(root, name, requirement, version)
    for path, text in (
        (catalog.metadata_path(home, name), json.dumps(descriptor, sort_keys=True)),
        (home / "installed" / name, version + "\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return descriptor


def demo_secret_keys(component):
    """Secret name -> the keys the demo component's pods select.

    From the manifests (volumes[].secret.items[].key) and from MOUNTS secret
    files ('@@secret:<id>/<key>@@' in config.defaults.yaml).
    """
    keys = {}
    directory = REPO / "components" / component
    for path in sorted((directory / "manifests").glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            for volume in ((doc or {}).get("spec") or {}).get("volumes", []):
                secret = volume.get("secret") or {}
                for item in secret.get("items") or []:
                    keys.setdefault(secret["secretName"], set()).add(item["key"])
    path = directory / "config.defaults.yaml"
    defaults = (yaml.safe_load(path.read_text()) if path.is_file() else None) or {}
    for mounts in (defaults.get("MOUNTS") or {}).values():
        for source in mounts.values():
            match = re.fullmatch(r"@@secret:([a-z0-9-]+)/([-._a-zA-Z0-9]+)@@", source)
            if match:
                keys.setdefault(match[1], set()).add(match[2])
    return keys


def write_secret_fixtures(base, config, component, data=b"dummy"):
    """Write one file per selected key into each Secret's first source directory.

    Generated keys are left to generation. Synthetic bytes only; tests that need
    a real certificate overwrite that file afterwards.
    """
    keys = demo_secret_keys(component)
    for name, sources in config.get("SECRET_FILES", {}).items():
        source = sources[0]
        target = Path(base) / source["path"]
        target.mkdir(parents=True, exist_ok=True)
        for key in sorted(keys.get(name, ())):
            if key not in source.get("generate", []):
                (target / key).write_bytes(data)
