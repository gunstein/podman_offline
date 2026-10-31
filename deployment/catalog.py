"""Read and validate the component model; no lifecycle actions.

One schema describes a component everywhere:

- Source: ``bundles.yaml`` lists every component of the product (the catalog)
  and names the gateway and Identity. ``derive_entries`` turns it and the
  components' registration files into normalized entries; ``source_descriptors``
  compiles each entry with its version and dependency ranges.
- Bundle: ``bundle.yaml`` holds the single compiled descriptor of that bundle.
- Target: ``metadata/<id>.json`` keeps the installed descriptor, so dependents
  and registration owners stay known without the source checkout.

A descriptor is a plain dict with exactly the keys in ``DESCRIPTOR_KEYS``.
"""

import json
import re
from pathlib import Path

from . import common, environment
from . import render as rendering

# Directories and files the target state directory uses for shared state. A component with
# one of these IDs would share a path with that state, so the IDs are reserved.
RESERVED_IDS = ("installed", "metadata", "routes", "clients", "apis", "files")

# Registration roles. routes and clients come from a file in the component
# and arrive at their owner in an imported volume; an API secret is the API's
# own declared secret that Identity's ENVIRONMENT names, and arrives in a Secret
# the platform renders for the owner (registrations.owner_secrets).
ROLES = ("routes", "clients", "apis")
ROLE_FILES = {"routes": "route.conf", "clients": "client.yaml"}
# The role whose accepts value names a Secret instead of a volume.
SECRET_ROLES = ("apis",)

# Every component except the gateway reads these from the gateway's
# config.yaml at install and validate; its own config.yaml does not hold them.
PUBLIC_KEYS = ("PUBLIC_ORIGIN", "HTTPS_PORT")
# bundles.yaml lists component IDs only; a normalized entry is derived from
# the gateway/identity names and the component files (derive_entries).
# Normalized fields, as the rest of the code and compiled descriptors use them.
ENTRY_KEYS = (
    "requires",
    "public_from",
    "routes",
    "clients",
    "apis",
    "accepts",
    "api_secrets",
)
# api_secrets is Identity's {API component: {"index": <n> in
# ApiResources__<n>__ApiSecrets__0__Value, "secret": "<SECRET_FILES ID>/<key>"}}.
DESCRIPTOR_KEYS = (
    "name",
    "product",
    "version",
    "requires",
    "public_from",
    "routes",
    "clients",
    "apis",
    "accepts",
    "api_secrets",
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
    """Read bundles.yaml and check its top level.

    product and components are required; gateway and identity are optional.
    """
    path = root / "bundles.yaml"
    if not path.is_file():
        raise common.DeployError(f"Missing component catalog {path}")
    data = rendering.config_layer(path)  # Rejects duplicate keys with their line.
    if not {"product", "components"} <= set(data) or set(data) - {
        "product",
        "components",
        "gateway",
        "identity",
    }:
        raise common.DeployError(
            f"{path} must contain product: <name> and a components: list, "
            "optionally gateway: <id> and identity: <id>"
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
    if not isinstance(entries, list) or not entries:
        raise common.DeployError(
            f"{path}: components must be a nonempty list of component IDs, for "
            "example components: [platform, identity, app1]"
        )
    for name in entries:
        check_id(name, f"{path}: components")
    if len(set(entries)) != len(entries):
        raise common.DeployError(f"{path}: components lists an ID twice")
    files = {name: registration_files(root / "components" / name) for name in entries}
    catalog = derive_entries(path, data, files)
    for name, entry in catalog.items():
        check_entry(name, entry, f"{path}: components.{name}")
    check_id_prefixes(catalog, str(path))
    check_owners(catalog, str(path))
    dependency_order(catalog)  # Reject cycles before anything else uses the graph.
    return catalog


def registration_files(directory):
    """Which registration files a source component has, and its foreign secret lines.

    Reads only file existence and ENVIRONMENT; never manifests or settings.
    """
    return {
        "route": (directory / ROLE_FILES["routes"]).is_file(),
        "client": (directory / ROLE_FILES["clients"]).is_file(),
        "foreign": environment.foreign_lines(directory),
    }


def api_secret_mapping(identity, files):
    """Check every ENVIRONMENT line that names another component's secret.

    Return Identity's {API: {"index": <n>, "secret": "<id>/<key>"}}. Secret IDs
    start with their component's ID, so the API is the listed component whose
    ID begins the secret ID. Only Identity may name another component's secret,
    as the whole value of ApiResources__<n>__ApiSecrets__0__Value, one line per
    API, each <n> once, all in one container.
    """
    mapping, containers = {}, set()
    for name, found in files.items():
        for line in found["foreign"]:
            where = (
                f"components/{name}/config.defaults.yaml: "
                f"ENVIRONMENT.{line.container}.{line.key}"
            )
            if name != identity:
                hint = (
                    "only identity's ApiResources__<n>__ApiSecrets__0__Value lines may"
                    if identity
                    else "set identity: <id> in bundles.yaml if this is your Identity"
                )
                raise common.DeployError(
                    f"{where}: {', '.join(line.secrets)} is another component's "
                    f"secret; {name} may use only its own (IDs starting with "
                    f"{name}-); {hint}"
                )
            match = environment.API_SECRET_KEY.fullmatch(line.key)
            whole = environment.WHOLE_SECRET.fullmatch(line.value)
            if not match or not whole:
                raise common.DeployError(
                    f"{where}: identity receives another component's secret only as "
                    "the whole value of ApiResources__<n>__ApiSecrets__0__Value, "
                    "for example '@@secret:orders-api-secret/value@@'"
                )
            secret = whole[1]  # "<id>/<key>"
            owners = [
                other
                for other in files
                if other != identity and secret.startswith(other + "-")
            ]
            if not owners:
                raise common.DeployError(
                    f"{where}: no listed component owns {line.secrets[0]}; a secret ID "
                    "starts with the ID of the component that declares it"
                )
            api, index = owners[0], int(match[1])
            if api in mapping or index in [e["index"] for e in mapping.values()]:
                raise common.DeployError(
                    f"{where}: each API needs exactly one line and its own <n>"
                )
            mapping[api] = {"index": index, "secret": secret}
            containers.add(line.container)
    if len(containers) > 1:
        raise common.DeployError(
            f"components/{identity}: API secret lines must all be in one container"
        )
    return mapping


def derive_entries(path, document, files):
    """Turn the catalog and each component's registration files into normalized entries.

    Pure: no reads, writes or host commands. files maps each component to
    registration_files(). The rules (docs/COMPONENT-SMALL-VARIANT.md, 2.3):

    - The gateway receives routes in <gateway>-routes. Every other component
      takes the gateway's public settings and requires it; a component with
      route.conf registers it with the gateway.
    - Identity receives clients in <identity>-clients and API secrets in
      <identity>-apis, each only when some component uses it, so an Identity
      without that role needs no unused volume or Secret.
    - Dependencies come only from these rules: the gateway, then Identity.
    """
    components = document["components"]
    roles = {}
    for key in ("gateway", "identity"):
        value = document.get(key)
        if value is not None and value not in components:
            raise common.DeployError(
                f"{path}: {key}: {value!r} must be one of the listed components"
            )
        roles[key] = value
    gateway, identity = roles["gateway"], roles["identity"]
    uses_clients = any(found["client"] for found in files.values())
    mapping = api_secret_mapping(identity, files)
    entries = {}
    for name in components:
        found = files[name]
        directory = f"components/{name}"
        entry = {
            "requires": [],
            "public_from": None,
            "routes": None,
            "clients": None,
            "apis": None,
            "accepts": {},
            "api_secrets": {},
        }
        if found["route"]:
            if gateway is None:
                raise common.DeployError(
                    f"{directory}/route.conf needs a gateway: add gateway: <id> "
                    f"to {path}"
                )
            if name == gateway:
                raise common.DeployError(
                    f"{directory}/route.conf: the gateway serves routes itself; "
                    "remove the file"
                )
            entry["routes"] = gateway
        if found["client"]:
            if identity is None:
                raise common.DeployError(
                    f"{directory}/client.yaml needs identity: <id> in {path}"
                )
            if gateway is None or name == gateway:
                raise common.DeployError(
                    f"{directory}/client.yaml needs the gateway's public origin for "
                    "its redirect URI: set gateway: <id>, and keep clients off "
                    "the gateway itself"
                )
            if name == identity:
                raise common.DeployError(
                    f"{directory}/client.yaml: identity does not register a "
                    "client with itself; remove the file"
                )
            entry["clients"] = identity
        if name in mapping:
            entry["apis"] = identity
        if name == gateway:
            entry["accepts"]["routes"] = name + "-routes"
        elif gateway is not None:
            entry["public_from"] = gateway
        if name == identity:
            if uses_clients:
                entry["accepts"]["clients"] = name + "-clients"
            if mapping:
                entry["accepts"]["apis"] = environment.owner_secret_name(name)
                entry["api_secrets"] = mapping
        derived = [entry["public_from"], entry["clients"], entry["apis"]]
        entry["requires"] = [
            dependency
            for dependency in (gateway, identity)
            if dependency is not None and dependency in derived
        ]
        entries[name] = entry
    return entries


def derived_lines(entries):
    """One line per component saying what derive_entries decided, without values."""
    lines = []
    for name, entry in entries.items():
        parts = []
        received = [
            f"{role} in {resource}"
            for role, resource in sorted(entry["accepts"].items())
        ]
        if received:
            parts.append("receives " + ", ".join(received))
        if entry["public_from"]:
            # Routes always go to the gateway, which is also public_from.
            what = (
                "public settings and routes" if entry["routes"] else "public settings"
            )
            parts.append(f"{what} from {entry['public_from']}")
        if entry["clients"]:
            parts.append(f"client.yaml -> {entry['clients']}")
        if entry["apis"]:
            parts.append(f"API secret -> {entry['apis']}")
        if entry["requires"]:
            parts.append("requires " + ", ".join(entry["requires"]))
        lines.append(f"{name}: " + ("; ".join(parts) or "no links"))
    return lines


def check_entry(name, entry, where):
    """Validate the fields a catalog entry and a compiled descriptor share."""
    requires = entry["requires"]
    for key in ("public_from",) + ROLES:
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
    if not isinstance(accepts, dict) or set(accepts) - set(ROLES):
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
    mapping = entry["api_secrets"]
    if not isinstance(mapping, dict) or (mapping and "apis" not in accepts):
        raise common.DeployError(
            f"{where}.api_secrets is allowed only on the component that accepts apis"
        )
    indexes = []
    for api, line in mapping.items():
        check_id(api, f"{where}.api_secrets")
        if (
            not isinstance(line, dict)
            or set(line) != {"index", "secret"}
            or type(line["index"]) is not int
            or line["index"] < 0
            or not environment.WHOLE_SECRET.fullmatch(f"@@secret:{line['secret']}@@")
            or not line["secret"].startswith(api + "-")
        ):
            raise common.DeployError(
                f"{where}.api_secrets.{api} must hold index (0 or more) and secret "
                f"(<{api}-... SECRET_FILES ID>/<key>)"
            )
        indexes.append(line["index"])
    if len(set(indexes)) != len(indexes):
        raise common.DeployError(f"{where}.api_secrets needs a separate index per API")


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
        for role in ROLES:
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
    for role in ROLES:
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
        component_directory(root, name)
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
            "public_from": entry["public_from"],
            "routes": entry["routes"],
            "clients": entry["clients"],
            "apis": entry["apis"],
            "accepts": dict(entry["accepts"]),
            "api_secrets": {
                api: dict(line) for api, line in entry["api_secrets"].items()
            },
        }
    return descriptors


def check_descriptor(data, where):
    """Validate one compiled descriptor read from bundle.yaml or installed metadata."""
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


def public_settings(config, path):
    """The validated PUBLIC_ORIGIN and HTTPS_PORT of a gateway's config."""
    for key in PUBLIC_KEYS:
        if key not in config:
            raise common.DeployError(
                f"Missing {key} in {path}; add it explicitly before installation"
            )
    rendering.public_origin(config["PUBLIC_ORIGIN"], path)
    return {key: config[key] for key in PUBLIC_KEYS}


def gateway_settings(gateway, state=None):
    """Read the installed gateway's public settings; {} without a gateway."""
    if gateway is None:
        return {}
    path = state_paths(gateway, state)[0]
    if not path.is_file():
        raise common.DeployError(
            f"Missing {path}; restore the installed {gateway} config first"
        )
    return public_settings(rendering.load_config(path), path)


# Maps whose IDs are completed one by one from the release defaults.
FILE_GROUPS = (common.SECRET_FILES, common.VOLUME_FILES, common.SECRET_TEMPLATES)


def release_defaults(component):
    """The release's config.defaults.yaml for a component (without ENVIRONMENT)."""
    path = common.ROOT / "components" / component / "config.defaults.yaml"
    return rendering.merge_config(path) if path.exists() or path.is_symlink() else {}


def operator_config(descriptor, path, state=None):
    """Return (config, names taken from the release) for an installed component.

    The operator's config.yaml wins. A setting it does not have, or a
    SECRET_FILES/VOLUME_FILES/SECRET_TEMPLATES ID it does not list, comes from
    the release's config.defaults.yaml, so a new release can add one without
    an operator edit; nothing is written. PUBLIC_ORIGIN and HTTPS_PORT come
    from the gateway's config.yaml; another component's config.yaml may not
    set them. No writes.
    """
    config = rendering.load_config(path)
    gateway = descriptor["public_from"]
    if gateway is not None:
        for key in PUBLIC_KEYS:
            if key in config:
                raise common.DeployError(
                    f"{key} in {path} is read from {gateway}'s config.yaml; "
                    "remove it here"
                )
    defaults = release_defaults(descriptor["name"])
    added = []
    for key, value in defaults.items():
        if gateway is not None and key in PUBLIC_KEYS:
            continue
        if key not in config:
            config[key] = value
            added.append(key)
        elif key in FILE_GROUPS and isinstance(config[key], dict):
            for name, entry in value.items():
                if name not in config[key]:
                    config[key] = dict(config[key], **{name: entry})
                    added.append(f"{key}.{name}")
    config.update(gateway_settings(gateway, state))
    return config, added


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
            descriptor = check_descriptor(json.loads(path.read_text()), str(path))
            if descriptor["name"] != name:
                raise ValueError("name")
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
