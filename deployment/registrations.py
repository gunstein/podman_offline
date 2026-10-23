"""Public route and client registrations, and the pending-operation record.

Install and uninstall use these; they do not depend on either. Staging
builds the registrations in a temporary directory, the pending record
(pending-operation.json) lists owners that still have to restart, and only
then are registrations written or deleted in the service user's home.
"""

import json
import os
import re
import shutil
import ssl
import tempfile
from pathlib import Path

from . import catalog, common
from . import render as rendering


def registration_stage(components, directory, known, home=None, configs=None):
    """Stage existing and proposed public routes and clients without changing live state.

    known maps component IDs to descriptors: installed metadata plus the incoming
    bundle in production, the source catalog in dev. Each existing registration
    must belong to a known component; the role owners come from accepts.

    For the selected components the release files are authoritative: their
    installed registrations are never copied, and a role the release no longer
    declares is returned in removals. Absence for any other component never
    means removal. Returns (imports, updates, removals).

    configs (dev) maps each component to its config before it is written; dev
    registrations then come only from the catalog, so existing ones are ignored.
    """
    home = home or common.STATE
    owners = catalog.role_owners(known, "registration owners")
    for name in catalog.ROLE_FILES:
        source = home / name
        if source.is_symlink():
            raise common.DeployError(
                f"Refuse symlinked shared registration directory: {source}"
            )
        (directory / name).mkdir()
        if configs is not None or not source.exists():
            continue
        for path in sorted(source.iterdir()):
            if path.is_symlink():
                raise common.DeployError(
                    f"Refuse symlinked public registration: {path}"
                )
            if name == "routes":
                owner = path.name[: -len(".conf")] if path.suffix == ".conf" else ""
                if not path.is_file() or owner not in known:
                    raise common.DeployError(
                        f"Unexpected public route registration: {path}"
                    )
                if owner not in components:
                    shutil.copy2(path, directory / name / path.name)
                continue
            if not path.is_dir() or path.name not in known:
                raise common.DeployError(
                    f"Unexpected public client registration: {path}"
                )
            if path.name in components:
                continue  # The release decides, even after a partial prior write.
            target = directory / name / path.name
            target.mkdir()
            for filename in ("client.json", "client.crt"):
                public = path / filename
                if public.is_symlink():
                    raise common.DeployError(
                        f"Refuse symlinked public client file: {public}"
                    )
                shutil.copy2(public, target / filename)
    updates, removals = {}, set()
    for component in components:
        for role, relative in (
            ("routes", "routes/" + component + ".conf"),
            ("clients", "clients/" + component),
        ):
            if known[component][role] is None and (
                (home / relative).exists() or (home / relative).is_symlink()
            ):
                removals.add(relative)
        source = common.ROOT / "components" / component
        declared = {
            role: source / filename
            for role, filename in catalog.ROLE_FILES.items()
            if known[component][role] is not None
        }
        for role, filename in catalog.ROLE_FILES.items():
            if (role in declared) != (source / filename).is_file():
                raise common.DeployError(
                    f"{source / filename} must exist exactly when {component} declares {role}"
                )
        if not declared:
            continue
        config_path = catalog.state_paths(component, home)[0]
        if configs is None:
            config = rendering.load_config(config_path)
        else:
            config = configs[component]
        if "routes" in declared:
            updates["routes/" + component + ".conf"] = declared["routes"].read_bytes()
        if "clients" in declared:
            updates.update(
                client_registration(component, declared["clients"], config, config_path)
            )
    for relative, data in updates.items():
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    routes = directory / "routes/installed.conf"
    routes.write_text(
        "\n".join(
            path.read_text()
            for path in sorted((directory / "routes").glob("*.conf"))
            if path != routes
        ),
        encoding="utf-8",
    )
    client_dirs = sorted(
        path for path in (directory / "clients").iterdir() if path.is_dir()
    )
    client_ids = [registered_client_id(path / "client.json") for path in client_dirs]
    duplicates = sorted({value for value in client_ids if client_ids.count(value) > 1})
    if duplicates:
        raise common.DeployError(
            "OIDC client IDs must be unique across components: " + ", ".join(duplicates)
        )
    index = directory / "clients/installed.json"
    index.write_text(
        json.dumps([path.name + "/client.json" for path in client_dirs]),
        encoding="utf-8",
    )
    # Imports overwrite files without deleting old entries; only these current indexes are read.
    imports = {}
    if owners["routes"]:
        imports[known[owners["routes"]]["accepts"]["routes"]] = [routes]
    if owners["clients"]:
        imports[known[owners["clients"]]["accepts"]["clients"]] = client_dirs + [index]
    return imports, updates, removals


def registered_client_id(path):
    """Read the OIDC client ID of one staged public registration."""
    try:
        client_id = json.loads(path.read_text(encoding="utf-8")).get("Id")
    except (OSError, ValueError, AttributeError):
        client_id = None
    if not isinstance(client_id, str) or not client_id:
        raise common.DeployError(
            f"Invalid public client registration: {path.parent.name}"
        )
    return client_id


CLIENT_PATH = re.compile(r"^(/[a-z0-9][a-z0-9-]*)+$")


CLIENT_KEYS = {"id", "base_path", "scopes", "certificate"}
VARIABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def client_descriptor(path):
    """Read and check client.yaml: id, base_path, scopes, certificate, environment.

    environment is optional: {id: <variable>, base_path: <variable>} names the
    container variables that carry these values (the demo: APP_ID, BASE_PATH),
    so check_client_identity can compare them.
    """
    metadata = rendering.load_yaml(path)
    environment = (
        metadata.get("environment", {}) if isinstance(metadata, dict) else None
    )
    if (
        not isinstance(metadata, dict)
        or not CLIENT_KEYS <= set(metadata) <= CLIENT_KEYS | {"environment"}
        or not isinstance(metadata["id"], str)
        or not common.ID.fullmatch(metadata["id"])
        or not isinstance(metadata["base_path"], str)
        or not CLIENT_PATH.fullmatch(metadata["base_path"])
        or metadata["scopes"] != ["openid", "profile", metadata["id"]]
        or not isinstance(metadata["certificate"], str)
        or Path(metadata["certificate"]).is_absolute()
        or ".." in Path(metadata["certificate"]).parts
        or not isinstance(environment, dict)
        or not set(environment) <= {"id", "base_path"}
        or not all(
            isinstance(name, str) and VARIABLE.fullmatch(name)
            for name in environment.values()
        )
    ):
        raise common.DeployError(
            f"Invalid public client descriptor: {path}; expected id, "
            "base_path (/path), scopes [openid, profile, <id>], a relative certificate "
            "and optionally environment: {id: <VARIABLE>, base_path: <VARIABLE>}"
        )
    return metadata


def check_client_identity(directory, documents):
    """The client ID and base_path in client.yaml must match the app and its route.

    A mismatch otherwise shows only as an OIDC failure at login. route.conf, if
    present, must have a location for base_path. With environment declared,
    some container must set each named variable, and every container that sets
    it must use the client.yaml value. documents are the effective manifests.
    """
    path = directory / "client.yaml"
    if not path.is_file():
        return
    metadata = client_descriptor(path)
    base_path = metadata["base_path"]
    route = directory / "route.conf"
    if route.is_file() and not re.search(
        r"\blocation\s+(=\s*)?" + re.escape(base_path) + r"[/\s{]",
        route.read_text(encoding="utf-8"),
    ):
        raise common.DeployError(
            f"{route} has no location for base_path {base_path} from {path}"
        )
    for key, variable in sorted(metadata.get("environment", {}).items()):
        values = sorted(
            {
                str(entry.get("value"))
                for _, spec in rendering.pod_specs(documents)
                for _, container in rendering.containers(spec)
                for entry in container.get("env", [])
                if isinstance(entry, dict) and entry.get("name") == variable
            }
        )
        if values != [metadata[key]]:
            raise common.DeployError(
                f"{path}: {key} is {metadata[key]!r}, but the manifests set "
                f"{variable} to {', '.join(map(repr, values)) or 'nothing'}"
            )


def client_registration(component, path, config, config_path):
    """Build one public OIDC client registration from client.yaml.

    Protocol of the existing apps and Identity: the app requests its client ID
    as a scope, so scopes are exactly [openid, profile, <id>], and the redirect
    URI is PUBLIC_ORIGIN + base_path + /auth/callback. The client ID and
    base_path must match the app's settings (check_client_identity compares
    them when client.yaml names the variables); they may differ from the
    component ID. Only public certificates are accepted.
    """
    metadata = client_descriptor(path)
    certificate = rendering.resolve_path(metadata["certificate"], config_path.parent)
    try:
        certificate_bytes = certificate.read_bytes()
    except OSError:
        raise common.DeployError(
            f"Missing public client certificate {certificate} (certificate in {path})"
        ) from None
    try:
        ssl.PEM_cert_to_DER_cert(certificate_bytes.decode("ascii"))
    except (ValueError, UnicodeError):
        raise common.DeployError(
            f"Expected a public PEM certificate in {certificate}"
        ) from None
    rendering.public_origin(config.get("PUBLIC_ORIGIN"), config_path)
    origin = config["PUBLIC_ORIGIN"].rstrip("/")
    prefix = "clients/" + component + "/"
    return {
        prefix + "client.crt": certificate_bytes,
        prefix + "client.json": json.dumps(
            {
                "Id": metadata["id"],
                "RedirectUris": [origin + metadata["base_path"] + "/auth/callback"],
                "Scopes": metadata["scopes"],
                "Certificate": "client.crt",
            },
            sort_keys=True,
        ).encode("utf-8"),
    }


def write_registrations(updates, home=None, removals=()):
    """Write changed public registrations privately and delete removed ones.

    Unchanged files are kept. Callers record owner work first (save_pending),
    because a deleted registration no longer shows that its owner must restart.
    """
    home = home or common.STATE
    if any(
        (home / relative).is_symlink() for relative in list(updates) + list(removals)
    ):
        raise common.DeployError("Refuse symlinked public registration output")
    for relative, data in updates.items():
        target = home / relative
        if target.is_file() and target.read_bytes() == data:
            continue
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.parent.chmod(0o700)
        rendering.write_private(target, data.decode("utf-8"))
    for relative in sorted(removals):
        target = home / relative
        if target.is_dir():
            for child in target.iterdir():
                if child.is_symlink() or not child.is_file():
                    raise common.DeployError(
                        f"Refuse unexpected public registration file: {child}"
                    )
            shutil.rmtree(str(target))
        elif target.exists():
            target.unlink()


def component_imports(component, imports, known):
    """Return the registration archives this component accepts, if any."""
    selected = {
        volume: imports[volume]
        for volume in known[component]["accepts"].values()
        if volume in imports
    }
    return selected or None


def registration_changes(updates, owners, home=None, removals=()):
    """Compare before writing so unfinished owners can be recorded first.

    Returns the owners that must rebuild their imports and restart. A removed
    registration whose role no known component accepts has no owner to
    restart; recording None would make the pending record unreadable.
    """
    changed = {owners[relative.split("/", 1)[0]] for relative in removals}
    for relative, data in updates.items():
        target = (home or common.STATE) / relative
        if target.is_symlink():
            raise common.DeployError("Refuse symlinked public registration output")
        if not target.is_file() or target.read_bytes() != data:
            changed.add(owners[relative.split("/", 1)[0]])
    return changed - {None}


def apply_registration_updates(component, product, updates, removals, owners):
    """Record unfinished owners durably before writing or deleting registrations."""
    pending = check_pending("install", component, product)
    changed = registration_changes(updates, owners, removals=removals) | set(
        pending["owners"] if pending else []
    )
    if changed:
        pending = {
            "operation": "install",
            "component": component,
            "product": product,
            "owners": sorted(changed),
        }
        save_pending(pending)
    write_registrations(updates, removals=removals)
    return changed, pending


def pending_path():
    """Keep retry metadata outside releases; never traverse a symlinked state path."""
    path = common.STATE / "pending-operation.json"
    if any(parent.is_symlink() for parent in [path] + list(path.parents)):
        raise common.DeployError("Refuse symlinked pending-operation state")
    return path


def load_pending():
    """Accept only the small, component-scoped install/uninstall retry record.

    The record names its product: when the last component's metadata is
    already gone, it is the only place that still says whose work this is.
    """
    path = pending_path()
    if not path.exists():
        return None
    try:
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise ValueError("private regular file required")
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise TypeError("record required")
        operation = state.get("operation")
        keys = {"operation", "component", "product", "owners"}
        if operation == "uninstall":
            keys.update(("delete_data", "volumes", "stopped"))
        elif operation != "install":
            raise ValueError("operation")
        component = state.get("component")
        if (
            set(state) != keys
            or not isinstance(component, str)
            or not common.ID.fullmatch(component)
            or not isinstance(state["product"], str)
            or not common.PRODUCT.fullmatch(state["product"])
        ):
            raise ValueError("component/fields")
        owners = state["owners"]
        # Owners are checked against the descriptors when the operation resumes.
        if (
            not isinstance(owners, list)
            or any(
                not isinstance(owner, str) or not common.ID.fullmatch(owner)
                for owner in owners
            )
            or len(set(owners)) != len(owners)
            or component in owners
        ):
            raise ValueError("owners")
        if operation == "uninstall":
            volumes = state["volumes"]
            if (
                type(state["delete_data"]) is not bool
                or type(state["stopped"]) is not bool
                or not isinstance(volumes, list)
                or any(
                    not isinstance(name, str)
                    or not common.ID.fullmatch(name)
                    or not name.startswith(component + "-")
                    for name in volumes
                )
                or len(set(volumes)) != len(volumes)
            ):
                raise ValueError("uninstall fields")
        elif not owners:
            raise ValueError("empty install work")
    except (OSError, ValueError, TypeError, UnicodeError):
        raise common.DeployError(
            "Invalid pending-operation state; no changes made"
        ) from None
    return state


def check_pending(operation, component, product, delete_data=False):
    """Reject conflicting lifecycle commands; resume only the recorded operation.

    product is the bundle's product; another product's bundle never resumes or
    clears the record, even with the same component ID.
    """
    state = load_pending()
    if state is None:
        return None
    if state["product"] != product:
        raise common.DeployError(
            "Pending "
            + state["operation"]
            + " of "
            + state["component"]
            + " belongs to product "
            + state["product"]
            + "; this bundle belongs to "
            + product
            + ". Finish it with that product's bundle"
        )
    if state["operation"] != operation or state["component"] != component:
        flag = " --delete-data" if state.get("delete_data") else ""
        raise common.DeployError(
            "Pending "
            + state["operation"]
            + " for "
            + state["component"]
            + "; finish with that component's bundle: ./deploy "
            + state["operation"]
            + flag
        )
    if operation == "uninstall" and state["delete_data"] != delete_data:
        raise common.DeployError(
            "Pending uninstall requires the same --delete-data choice"
        )
    return state


def sync_pending_directory():
    """Make journal replacement/removal durable before proceeding to side effects."""
    descriptor = os.open(str(common.STATE), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def save_pending(state):
    """Atomically replace private metadata; an interrupted write retains the old record."""
    path = pending_path()
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=str(common.STATE))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(path))
        sync_pending_directory()
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def clear_pending():
    """Remove only the successfully completed current operation's record."""
    pending_path().unlink()
    sync_pending_directory()


def acknowledge_owner(state, owner, clear_when_done=False):
    """Record that one owner's restart finished, so a retry skips only that owner.

    An install record is finished once no owner is left; an uninstall record
    still has its own final steps, so it is cleared by uninstall itself.
    """
    state["owners"].remove(owner)
    if state["owners"] or not clear_when_done:
        save_pending(state)
    else:
        clear_pending()
