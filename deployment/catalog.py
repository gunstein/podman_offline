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

# Directories and files the target state directory uses for shared state. A component with
# one of these IDs would share a path with that state, so the IDs are reserved.
RESERVED_IDS = ("installed", "metadata", "routes", "clients", "apis", "files")

# Registration roles. A component that declares a role registers the matching
# file with the component that accepts that role. routes and clients arrive in
# an imported volume; apis in a Secret the owner names in accepts.
ROLE_FILES = {"routes": "route.conf", "clients": "client.yaml", "apis": "api.yaml"}
# The role whose accepts value names a Secret instead of a volume.
SECRET_ROLES = ("apis",)

UPGRADES = ("always", "newer-only")
# Config names a component may share with its public_from dependents, beside
# PUBLIC_ORIGIN and HTTPS_PORT (always shared). The placeholder name rule; the
# names below have built-in meaning and cannot be shared. See
# docs/COMPONENTS.md, "Reserved configuration names".
SETTING = re.compile(r"^[A-Z0-9_]+$")
UNSHAREABLE = ("PUBLIC_HOSTNAME", "SECRET_FILES", "VOLUME_FILES", "SECRET_TEMPLATES")
CATALOG_KEYS = (
    "requires",
    "upgrade",
    "public_from",
    "shares",
    "routes",
    "clients",
    "apis",
    "accepts",
)
DESCRIPTOR_KEYS = (
    "name",
    "product",
    "version",
    "requires",
    "upgrade",
    "public_from",
    "shares",
    "routes",
    "clients",
    "apis",
    "accepts",
)
# Descriptor fields added after the first product-named releases, with the
# value an older descriptor without them means.
LATER_KEYS = {"shares": [], "apis": None}


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


def check_product(value, where):
    """Accept a product name: it prefixes units, the network and archives."""
    if not isinstance(value, str) or not common.PRODUCT.fullmatch(value):
        raise common.DeployError(
            f"{where}: invalid product name {value!r}; use lowercase letters, "
            "digits and inner hyphens, a letter first and at most 32 characters, "
            "for example my-shop"
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


def catalog_document(root):
    """Read bundles.yaml and check its top level: product and components."""
    path = root / "bundles.yaml"
    if not path.is_file():
        raise common.DeployError(f"Missing component catalog {path}")
    data = rendering.config_layer(path)  # Rejects duplicate keys with their line.
    if set(data) != {"product", "components"}:
        raise common.DeployError(
            f"{path} must contain exactly product: <name> and a components: map"
        )
    check_product(data["product"], f"{path}: product")
    return path, data


def product_name(root):
    """Return the product name of the release or checkout at root.

    A bundle reads its compiled bundle.yaml, the source checkout reads
    bundles.yaml, and a standalone manifest fixture uses
    common.STANDALONE_PRODUCT.
    """
    if (root / "bundle.yaml").is_file():
        return load_bundle_descriptor(root)["product"]
    if (root / "bundles.yaml").is_file():
        return catalog_document(root)[1]["product"]
    return common.STANDALONE_PRODUCT


def load_catalog(root):
    """Read bundles.yaml and validate the graph before any file or host action."""
    path, data = catalog_document(root)
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
            "upgrade": entry.get("upgrade", "always"),
            "public_from": entry.get("public_from"),
            "shares": entry.get("shares", []),
            "routes": entry.get("routes"),
            "clients": entry.get("clients"),
            "apis": entry.get("apis"),
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
        check_entry(name, catalog[name], where)
    for name, entry in catalog.items():
        for dependency in entry["requires"]:
            if dependency not in catalog:
                raise common.DeployError(
                    f"{path}: components.{name}.requires names {dependency}, "
                    "which is not in the catalog"
                )
    check_id_prefixes(catalog, str(path))
    check_owners(catalog, str(path))
    dependency_order(catalog)  # Reject cycles before anything else uses the graph.
    return catalog


def check_entry(name, entry, where):
    """Validate the fields a catalog entry and a compiled descriptor share."""
    if entry["upgrade"] not in UPGRADES:
        raise common.DeployError(
            f"{where}.upgrade must be one of {', '.join(UPGRADES)}"
        )
    requires = entry["requires"]
    for key in ("public_from",) + tuple(ROLE_FILES):
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
    shares = entry["shares"]
    if not isinstance(shares, list) or len(set(map(str, shares))) != len(shares):
        raise common.DeployError(f"{where}.shares must be a list without repeats")
    for setting in shares:
        if not isinstance(setting, str) or not SETTING.fullmatch(setting):
            raise common.DeployError(
                f"{where}.shares: {setting!r} is not a config name (A-Z, 0-9, _)"
            )
        if setting in UNSHAREABLE:
            raise common.DeployError(
                f"{where}.shares: {setting} is reserved and cannot be shared"
            )
    accepts = entry["accepts"]
    if not isinstance(accepts, dict) or set(accepts) - set(ROLE_FILES):
        raise common.DeployError(
            f"{where}.accepts must map routes, clients and/or apis to a resource "
            "name (a volume ID; a Secret name for apis)"
        )
    for role, volume in accepts.items():
        if (
            not isinstance(volume, str)
            or not common.ID.fullmatch(volume)
            or not volume.startswith(name + "-")
        ):
            kind = "Secret name" if role in SECRET_ROLES else "volume ID"
            raise common.DeployError(
                f"{where}.accepts.{role} must be a {kind} starting with {name}-"
            )
    if len(set(accepts.values())) != len(accepts):
        raise common.DeployError(f"{where}.accepts needs a separate resource per role")


def check_id_prefixes(names, where):
    """Refuse an ID that is another ID plus "-": resource names would collide.

    Every resource of a component starts with "<id>-", so with orders and
    orders-data the name orders-data-db would belong to both, and deleting the
    data of one could delete the other's volume.
    """
    for name in sorted(names):
        for other in sorted(names):
            if other != name and other.startswith(name + "-"):
                raise common.DeployError(
                    f"{where}: component {other} starts with {name}-, so their "
                    "resource names can collide; rename one of them"
                )


def check_owners(descriptors, where):
    """Each role has at most one accepting component, which must accept it."""
    role_owners(descriptors, where)
    for name, entry in descriptors.items():
        for role in ROLE_FILES:
            owner = entry[role]
            # An owner outside this set is a missing dependency, reported by the
            # catalog's requires check or by install's dependency check.
            if owner is None or owner not in descriptors:
                continue
            if role not in descriptors[owner]["accepts"]:
                raise common.DeployError(
                    f"{where}: {name} registers {role} with {owner}, "
                    f"but {owner} does not accept {role}"
                )


def imported_volumes(descriptor):
    """The registration volumes a component accepts (routes, clients)."""
    return [
        name for role, name in descriptor["accepts"].items() if role not in SECRET_ROLES
    ]


def imported_secrets(descriptor):
    """The registration Secrets a component accepts (apis)."""
    return [
        name for role, name in descriptor["accepts"].items() if role in SECRET_ROLES
    ]


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
    product = catalog_document(root)[1]["product"]
    versions = {}
    for name, entry in catalog.items():
        directory = component_directory(root, name)
        version_path = confined_file(
            root, "components/" + name + "/VERSION", "Component version"
        )
        try:
            versions[name] = version_path.read_text(encoding="utf-8").strip()
            version_number(versions[name])
        except (UnicodeError, common.DeployError):
            raise common.DeployError(
                f"{version_path} must hold one major.minor.patch version"
            ) from None
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
            "product": product,
            "version": versions[name],
            "requires": {
                dependency: compatible_range(versions[dependency])
                for dependency in entry["requires"]
            },
            "upgrade": entry["upgrade"],
            "public_from": entry["public_from"],
            "shares": list(entry["shares"]),
            "routes": entry["routes"],
            "clients": entry["clients"],
            "apis": entry["apis"],
            "accepts": dict(entry["accepts"]),
        }
    return descriptors


def check_descriptor(data, where):
    """Validate one compiled descriptor read from bundle.yaml or installed metadata.

    shares and apis came after the first product-named releases; a descriptor
    without them shares nothing and registers no API (LATER_KEYS). Every other
    field is required.
    """
    if isinstance(data, dict) and set(LATER_KEYS) - set(data):
        data = dict(data)
        for key, value in LATER_KEYS.items():
            data.setdefault(key, value)
    if not isinstance(data, dict) or set(data) != set(DESCRIPTOR_KEYS):
        raise common.DeployError(
            f"{where}: expected exactly the fields {', '.join(DESCRIPTOR_KEYS)}"
        )
    check_id(data["name"], f"{where}: name")
    check_product(data["product"], f"{where}: product")
    version_number(data["version"])
    requires = data["requires"]
    if not isinstance(requires, dict):
        raise common.DeployError(f"{where}: requires must be a map")
    for dependency, requirement in requires.items():
        check_id(dependency, f"{where}: requires")
        if dependency == data["name"]:
            raise common.DeployError(f"{where}: requires must not name itself")
        check_range(requirement)
    check_entry(data["name"], data, where)
    return data


def load_bundle_descriptor(root):
    """Read the unpacked bundle's own compiled descriptor."""
    path = root / "bundle.yaml"
    return check_descriptor(rendering.load_yaml(path), str(path))


def metadata_path(state, name):
    """Installed public metadata, kept until the component is uninstalled."""
    return state / "metadata" / (name + ".json")


def unit_name(component):
    """Name of the component's Quadlet files and service: <product>-<component>."""
    return product_name(common.ROOT) + "-" + component


def state_paths(component, state=None):
    """Return one component's config and archive paths in a state directory.

    state names another state directory than common.STATE (build/dev in source
    dev). Refuses symlinked state paths.
    """
    base = (state or common.STATE).resolve()
    folder = base / component
    paths = [
        folder,
        folder / "files",
        folder / "config.yaml",
        base / "installed" / component,
        base / "metadata",
        metadata_path(base, component),
    ]
    paths.extend((folder / "files").glob("*.tar"))
    if any(path.is_symlink() for path in paths):
        raise common.DeployError(
            f"Refuse symlinked component state or output paths for {component}"
        )
    return folder / "config.yaml", folder / "files"


def component_paths(component):
    """Return one installed component's config, archives and Quadlet paths."""
    config, files = state_paths(component)
    unit = unit_name(component)
    output = common.QUADLET_DIR / (unit + ".yaml")
    quadlet = common.QUADLET_DIR / (unit + ".kube")
    if output.is_symlink() or quadlet.is_symlink():
        raise common.DeployError(
            f"Refuse symlinked component state or output paths for {component}"
        )
    return config, files, output, quadlet


def installed_version(state, name):
    """Return the completed install's version, or None while not installed."""
    marker = state / "installed" / name
    return marker.read_text().strip() if marker.is_file() else None


class PreProductMetadata(Exception):
    """Installed metadata from before product names; there is no migration."""


def load_installed_metadata(state):
    """Read every installed descriptor strictly; temporary files start with a dot.

    A descriptor is written before its completion marker, so this includes
    a component whose install has not finished. installed_version gives its
    last completed version; pending work also distinguishes failed reinstalls.
    """
    directory = state / "metadata"
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
            data = json.loads(path.read_text())
            if isinstance(data, dict) and set(data) == set(DESCRIPTOR_KEYS) - {
                "product"
            } - set(LATER_KEYS):
                raise PreProductMetadata()
            descriptor = check_descriptor(data, str(path))
            if descriptor["name"] != name:
                raise ValueError("name")
        except PreProductMetadata:
            raise common.DeployError(
                f"{path} was written by a release before product names "
                "(0.4.10 or older), and there is no migration. Remove that installation "
                "with its own releases, or install on a new service user "
                "(README: Product name)"
            ) from None
        except (OSError, ValueError, common.DeployError):
            raise common.DeployError(f"Invalid installed metadata {path}") from None
        descriptors[name] = descriptor
    return descriptors


def installed_components(state, descriptors):
    """Names with a completion marker; each must have installed metadata."""
    directory = state / "installed"
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
                f"Missing installed metadata {metadata_path(state, marker.name)} for {marker}"
            )
        names.append(marker.name)
    return names


def dependents(descriptors, state, name):
    """Completed installs whose recorded requirements name this component."""
    return [
        other
        for other in installed_components(state, descriptors)
        if name in descriptors[other]["requires"]
    ]
