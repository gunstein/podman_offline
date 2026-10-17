"""Read and validate the component model; no lifecycle actions.

One schema describes a component everywhere:

- Source: ``bundles.yaml`` lists every component of the product (the catalog).
  ``source_descriptors`` compiles each entry with its version and dependency
  ranges.
- Bundle: ``bundle.yaml`` holds the single compiled descriptor of that bundle.
- Target: ``metadata/<id>.json`` keeps the installed descriptor, so dependents
  and registration owners stay known without the source checkout.

A descriptor is a plain dict with exactly the keys in ``DESCRIPTOR_KEYS``.
"""

import json
import re
from pathlib import Path

from . import common
from . import render as rendering

# Directories and files the target home uses for shared state. A component with
# one of these IDs would share a path with that state, so the IDs are reserved.
RESERVED_IDS = ("installed", "metadata", "routes", "clients", "files")

# Registration roles. A component that declares a role registers the matching
# file with the component that accepts that role.
ROLE_FILES = {"routes": "route.conf", "clients": "client.yaml"}

UPGRADES = ("always", "newer-only")
CATALOG_KEYS = (
    "requires",
    "version_file",
    "upgrade",
    "public_from",
    "routes",
    "clients",
    "accepts",
)
DESCRIPTOR_KEYS = (
    "name",
    "version",
    "requires",
    "upgrade",
    "public_from",
    "routes",
    "clients",
    "accepts",
)


def check_id(value, where):
    """Accept lowercase letters, digits and inner hyphens; never rewrite a name.

    Component IDs become resource prefixes, Podman volume and unit names and
    directory names, so `my-identity` is valid and `my_identity` is not.
    """
    if not isinstance(value, str) or not common.ID.fullmatch(value):
        raise common.DeployError(
            f"{where}: invalid component ID {value!r}; use lowercase letters, "
            "digits and inner hyphens, for example my-identity (not my_identity)"
        )
    if value in RESERVED_IDS:
        raise common.DeployError(
            f"{where}: component ID {value!r} is reserved for shared state"
        )


def version_number(value):
    """Parse a three-part numeric version for deterministic comparisons."""
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise common.DeployError(
            "Versions must contain three numeric parts: major.minor.patch"
        )
    return tuple(int(part) for part in value.split("."))


def compatible_range(version):
    """Declare a compatible major series, or minor series while the dependency is 0.x."""
    major, minor, _ = version_number(version)
    upper = f"{major + 1}.0.0" if major else f"0.{minor + 1}.0"
    return {"min": version, "before": upper}


def check_range(requirement):
    """Require an explicit nonempty inclusive-minimum/exclusive-upper range."""
    if not isinstance(requirement, dict) or set(requirement) != {"min", "before"}:
        raise common.DeployError("Invalid dependency version requirement")
    if version_number(requirement["min"]) >= version_number(requirement["before"]):
        raise common.DeployError("Empty dependency version requirement")


def load_catalog(root):
    """Read bundles.yaml and validate the graph before any file or host action."""
    path = root / "bundles.yaml"
    if not path.is_file():
        raise common.DeployError(f"Missing component catalog {path}")
    data = rendering.config_layer(path)  # Rejects duplicate keys with their line.
    if set(data) != {"components"}:
        raise common.DeployError(f"{path} must contain only a components: map")
    entries = data["components"]
    if not isinstance(entries, dict) or not entries:
        raise common.DeployError(f"{path}: components must be a nonempty map")
    catalog = {}
    for name, entry in entries.items():
        where = f"{path}: components.{name}"
        check_id(name, where)
        if entry is None:
            entry = {}
        if not isinstance(entry, dict) or set(entry) - set(CATALOG_KEYS):
            raise common.DeployError(
                f"{where}: allowed fields are {', '.join(CATALOG_KEYS)}"
            )
        catalog[name] = {
            "requires": entry.get("requires", []),
            "version_file": entry.get("version_file", "VERSION"),
            "upgrade": entry.get("upgrade", "always"),
            "public_from": entry.get("public_from"),
            "routes": entry.get("routes"),
            "clients": entry.get("clients"),
            "accepts": entry.get("accepts", {}),
        }
        requires = catalog[name]["requires"]
        if not isinstance(requires, list) or len(set(map(str, requires))) != len(
            requires
        ):
            raise common.DeployError(f"{where}.requires must be a list without repeats")
        for dependency in requires:
            check_id(dependency, f"{where}.requires")
            if dependency == name:
                raise common.DeployError(f"{where}.requires must not name itself")
        check_roles(name, catalog[name], where)
    for name, entry in catalog.items():
        for dependency in entry["requires"]:
            if dependency not in catalog:
                raise common.DeployError(
                    f"{path}: components.{name}.requires names {dependency}, "
                    "which is not in the catalog"
                )
    check_owners(catalog, str(path))
    dependency_order(catalog)  # Reject cycles before anything else uses the graph.
    return catalog


def check_roles(name, entry, where):
    """Validate one component's roles; shared by catalog and descriptors."""
    if entry["upgrade"] not in UPGRADES:
        raise common.DeployError(
            f"{where}.upgrade must be one of {', '.join(UPGRADES)}"
        )
    requires = entry["requires"]
    for key in ("public_from", "routes", "clients"):
        value = entry[key]
        if value is None:
            continue
        check_id(value, f"{where}.{key}")
        if value not in requires:
            raise common.DeployError(
                f"{where}.{key}: {value} must also be listed in requires"
            )
    if entry["clients"] is not None and entry["public_from"] is None:
        raise common.DeployError(
            f"{where}: clients needs public_from for the redirect URI origin"
        )
    accepts = entry["accepts"]
    if not isinstance(accepts, dict) or set(accepts) - set(ROLE_FILES):
        raise common.DeployError(
            f"{where}.accepts must map routes and/or clients to a volume ID"
        )
    for role, volume in accepts.items():
        if (
            not isinstance(volume, str)
            or not common.ID.fullmatch(volume)
            or not volume.startswith(name + "-")
        ):
            raise common.DeployError(
                f"{where}.accepts.{role} must be a volume ID starting with {name}-"
            )
    if len(set(accepts.values())) != len(accepts):
        raise common.DeployError(f"{where}.accepts needs a separate volume per role")


def check_owners(descriptors, where):
    """Each role has at most one accepting component, which must accept it."""
    role_owners(descriptors, where)
    for name, entry in descriptors.items():
        for role in ROLE_FILES:
            owner = entry[role]
            if owner is None or owner not in descriptors:
                continue
            if role not in descriptors[owner]["accepts"]:
                raise common.DeployError(
                    f"{where}: {name} registers {role} with {owner}, "
                    f"but {owner} does not accept {role}"
                )


def role_owners(descriptors, where):
    """Return {role: owner or None}; two owners of one role are ambiguous."""
    owners = {}
    for role in ROLE_FILES:
        accepting = [
            name for name, entry in descriptors.items() if role in entry["accepts"]
        ]
        if len(accepting) > 1:
            raise common.DeployError(
                f"{where}: {' and '.join(sorted(accepting))} both accept {role}"
            )
        owners[role] = accepting[0] if accepting else None
    return owners


def dependency_order(descriptors, names=None):
    """Order names so dependencies come first; unrelated names keep their order."""
    names = list(descriptors if names is None else names)
    ordered, visiting = [], []

    def visit(name):
        if name in ordered or name not in descriptors:
            return
        if name in visiting:
            cycle = visiting[visiting.index(name) :] + [name]
            raise common.DeployError("Dependency cycle: " + " -> ".join(cycle))
        visiting.append(name)
        for dependency in descriptors[name]["requires"]:
            visit(dependency)
        visiting.pop()
        ordered.append(name)

    for name in descriptors:
        visit(name)
    return [name for name in ordered if name in names]


def confined_file(root, relative, where):
    """Resolve a declared release file without leaving the release directory."""
    if (
        not isinstance(relative, str)
        or not relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise common.DeployError(f"{where} must be a relative path inside {root}")
    path = root / relative
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise common.DeployError(f"{where} resolves outside {root}") from None
    if not path.is_file():
        raise common.DeployError(f"{where}: missing file {path}")
    return path


def component_directory(root, name):
    """Return a selected component's directory; it must exist and contain manifests."""
    directory = root / "components" / name
    if directory.is_symlink() or not directory.is_dir():
        raise common.DeployError(
            f"Missing component directory {directory} for catalog entry {name}"
        )
    manifests = directory / "manifests"
    if manifests.is_symlink() or not sorted(manifests.glob("*.yaml")):
        raise common.DeployError(
            f"{manifests} must contain at least one *.yaml manifest"
        )
    return directory


def source_descriptors(root):
    """Compile every catalog entry into a descriptor, checking its source files."""
    catalog = load_catalog(root)
    versions = {}
    for name, entry in catalog.items():
        version_path = confined_file(
            root, entry["version_file"], f"components.{name}.version_file"
        )
        try:
            versions[name] = version_path.read_text(encoding="utf-8").strip()
            version_number(versions[name])
        except (UnicodeError, common.DeployError):
            raise common.DeployError(
                f"{version_path} (components.{name}.version_file) must hold "
                "one major.minor.patch version"
            ) from None
        directory = component_directory(root, name)
        for role, filename in ROLE_FILES.items():
            declared = entry[role] is not None
            present = (directory / filename).is_file()
            if declared != present:
                raise common.DeployError(
                    f"components.{name}: {directory / filename} "
                    + (
                        f"is missing for {role}: {entry[role]}"
                        if declared
                        else f"exists, so declare {role}: <owner> in bundles.yaml"
                    )
                )
    descriptors = {}
    for name in dependency_order(catalog):
        entry = catalog[name]
        descriptors[name] = {
            "name": name,
            "version": versions[name],
            "requires": {
                dependency: compatible_range(versions[dependency])
                for dependency in entry["requires"]
            },
            "upgrade": entry["upgrade"],
            "public_from": entry["public_from"],
            "routes": entry["routes"],
            "clients": entry["clients"],
            "accepts": dict(entry["accepts"]),
        }
    return descriptors


def check_descriptor(data, where):
    """Validate one compiled descriptor read from bundle.yaml or installed metadata."""
    if not isinstance(data, dict) or set(data) != set(DESCRIPTOR_KEYS):
        raise common.DeployError(
            f"{where}: expected exactly the fields {', '.join(DESCRIPTOR_KEYS)}"
        )
    check_id(data["name"], f"{where}: name")
    version_number(data["version"])
    requires = data["requires"]
    if not isinstance(requires, dict):
        raise common.DeployError(f"{where}: requires must be a map")
    for dependency, requirement in requires.items():
        check_id(dependency, f"{where}: requires")
        if dependency == data["name"]:
            raise common.DeployError(f"{where}: requires must not name itself")
        check_range(requirement)
    check_roles(data["name"], data, where)
    return data


def load_bundle_descriptor(root):
    """Read the unpacked bundle's own compiled descriptor."""
    path = root / "bundle.yaml"
    return check_descriptor(rendering.load_yaml(path), str(path))


def metadata_path(home, name):
    """Installed public metadata, kept until the component is uninstalled."""
    return home / "metadata" / (name + ".json")


def installed_version(home, name):
    """Return the completed install's version, or None while not installed."""
    marker = home / "installed" / name
    return marker.read_text().strip() if marker.is_file() else None


def load_installed_metadata(home):
    """Read every installed descriptor strictly; temporary files start with a dot.

    A descriptor is written before its completion marker, so this includes
    a component whose install has not finished; installed_version tells them apart.
    """
    directory = home / "metadata"
    if directory.is_symlink():
        raise common.DeployError(f"Refuse symlinked installed metadata: {directory}")
    descriptors = {}
    if not directory.exists():
        return descriptors
    for path in sorted(directory.iterdir()):
        if path.name.startswith("."):
            continue
        name = path.name[: -len(".json")] if path.name.endswith(".json") else ""
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError("regular file required")
            check_id(name, str(path))
            descriptor = check_descriptor(json.loads(path.read_text()), str(path))
            if descriptor["name"] != name:
                raise ValueError("name")
        except (OSError, ValueError, common.DeployError):
            raise common.DeployError(f"Invalid installed metadata {path}") from None
        descriptors[name] = descriptor
    return descriptors


def installed_components(home, descriptors):
    """Names with a completion marker; each must have installed metadata."""
    directory = home / "installed"
    if directory.is_symlink():
        raise common.DeployError(f"Refuse symlinked installed markers: {directory}")
    if not directory.exists():
        return []
    names = []
    for marker in sorted(directory.iterdir()):
        if marker.name.startswith("."):
            continue  # An interrupted atomic write leaves only a temporary file.
        check_id(marker.name, str(marker))
        if marker.name not in descriptors:
            raise common.DeployError(
                f"Missing installed metadata {metadata_path(home, marker.name)} for {marker}"
            )
        names.append(marker.name)
    return names


def dependents(descriptors, home, name):
    """Completed installs whose recorded requirements name this component."""
    return [
        other
        for other in installed_components(home, descriptors)
        if name in descriptors[other]["requires"]
    ]
