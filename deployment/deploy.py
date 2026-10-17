"""Component preparation, registrations and rootless install/uninstall lifecycle."""

import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
from pathlib import Path

import yaml

from . import catalog, common
from . import render as rendering


def init_config(component):
    """Exclusively materialize one bundled config; never create private input files."""
    production_environment()
    descriptor = bundle_descriptor()
    if component != descriptor["name"]:
        raise common.DeployError(
            f"Component {component} is not included in this bundle"
        )
    check_pending("init-config", component)
    check_dependencies_installed(descriptor)
    target = common.HOME / component / "config.yaml"
    for path in [target] + list(target.parents):
        if path.is_symlink():
            raise common.DeployError(f"Refuse symlinked config path: {path}")
    if target.exists():
        print(
            f"[OK] Existing config retained unchanged: {target}; install validates it"
        )
        return
    overrides = {}
    source = descriptor["public_from"]
    if source is not None:
        # The dependency is installed (checked above), so its config must exist.
        source_path = component_paths(source)[0]
        if not source_path.exists():
            raise common.DeployError(
                f"Missing {source_path}; restore installed {source} config before initializing {component}"
            )
        overrides = public_settings(rendering.load_config(source_path), source_path)
    config = rendering.component_defaults(component, overrides=overrides)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.parent.chmod(0o700)
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        yaml.safe_dump(config, stream, sort_keys=False)
    print(
        f"[OK] Initialized {target}; edit config and prepare credentials before install"
    )


PUBLIC_KEYS = ("PUBLIC_ORIGIN", "HTTPS_PORT")


def public_settings(config, path):
    """Return the validated shared public origin and port of one config."""
    for key in PUBLIC_KEYS:
        if key not in config:
            raise common.DeployError(
                f"Missing {key} in {path}; add it explicitly before installation"
            )
    rendering.public_origin(config["PUBLIC_ORIGIN"], path)
    return {key: config[key] for key in PUBLIC_KEYS}


def check_public_settings(descriptor, config, path):
    """A component declaring public_from must use that dependency's origin and port."""
    source = descriptor["public_from"]
    if source is None:
        return
    source_path = component_paths(source)[0]
    expected = public_settings(rendering.load_config(source_path), source_path)
    actual = public_settings(config, path)
    for key in PUBLIC_KEYS:
        if actual[key] != expected[key]:
            raise common.DeployError(f"{key} in {path} must match {source_path}")


def database_preflight(config, config_path, manifests):
    """Guard PostgreSQL password creation using its manifest's actual named volume.

    This lifecycle check runs before rendering/generation, never inside the
    general secret generator. Existing volumes are conservatively retained.
    """
    for manifest in sorted(manifests.glob("*.yaml")):
        for doc in rendering.load_yaml_all(manifest):
            if not doc or doc.get("kind") != "Pod":
                continue
            spec = doc.get("spec", {})
            volumes = {v["name"]: v for v in spec.get("volumes", [])}
            for container in spec.get("containers", []):
                env = {e["name"]: e.get("value") for e in container.get("env", [])}
                if "POSTGRES_PASSWORD_FILE" not in env:
                    continue
                reference = env["POSTGRES_PASSWORD_FILE"]
                if not isinstance(reference, str) or not Path(reference).is_absolute():
                    raise common.DeployError(
                        f"Invalid POSTGRES_PASSWORD_FILE in {manifest}"
                    )
                password_file = Path(reference)
                mounts = container.get("volumeMounts", [])
                secret_mount = next(
                    (m for m in mounts if m["mountPath"] == str(password_file.parent)),
                    None,
                )
                data_mount = next(
                    (m for m in mounts if m["mountPath"] == "/var/lib/postgresql/data"),
                    None,
                )
                if not secret_mount or not data_mount:
                    raise common.DeployError(
                        f"Unsupported PostgreSQL password/data mounts in {manifest}"
                    )
                try:
                    secret = volumes[secret_mount["name"]]["secret"]
                    claim = volumes[data_mount["name"]]["persistentVolumeClaim"][
                        "claimName"
                    ]
                    keys = [
                        item["key"]
                        for item in secret.get("items", [])
                        if item["path"] == password_file.name
                    ]
                    if len(keys) != 1:
                        raise KeyError("password key")
                    key = keys[0]
                except (KeyError, TypeError):
                    raise common.DeployError(
                        f"Unsupported PostgreSQL Secret/PVC binding in {manifest}"
                    ) from None
                entries = rendering.file_group_sources(config, common.SECRET_FILES).get(
                    secret["secretName"], []
                )
                candidates = []
                for entry in entries:
                    source = rendering.resolve_path(entry["path"], config_path.parent)
                    directory = "generate" in entry or source.is_dir()
                    candidates.append(
                        source if source.name == key and not directory else source / key
                    )
                if len(candidates) != 1:
                    raise common.DeployError(
                        f"{config_path}: {common.SECRET_FILES}.{secret['secretName']} must identify one password file"
                    )
                password = candidates[0]
                if password.exists() or password.is_symlink():
                    if not password.is_file():
                        raise common.DeployError(
                            f"Invalid database password file {password}; restore from backup"
                        )
                    try:
                        content = password.read_bytes().decode("utf-8").rstrip("\n")
                    except (OSError, UnicodeError):
                        raise common.DeployError(
                            f"Invalid database password file {password}; restore from backup"
                        ) from None
                    if not content or any(c in content for c in ("\x00", "\n", "\r")):
                        raise common.DeployError(
                            f"Empty or invalid database password file {password}; restore from backup"
                        )
                    continue
                try:
                    result = subprocess.run(  # noqa: UP022 - Python 3.6
                        ["podman", "volume", "exists", claim],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                    )
                except OSError:
                    raise common.DeployError(
                        f"Cannot check database volume {claim}; no password generated"
                    ) from None
                if result.returncode == 0:
                    raise common.DeployError(
                        f"Missing database password file {password} with existing volume {claim}; "
                        "restore the password from backup or use a separate recovery procedure; no password generated"
                    )
                if result.returncode != 1:
                    raise common.DeployError(
                        f"Cannot check database volume {claim}; no password generated"
                    )
                if password.resolve() not in rendering.generated_secret_paths(
                    config, config_path.parent
                ):
                    raise common.DeployError(
                        f"Missing database password file {password}; declare generate on its {common.SECRET_FILES} source in {config_path}"
                    )


def dev_settings():
    """Compile the source catalog and merge dev config for each component.

    Both are in dependency order, so a public_from source is merged before the
    components that take its PUBLIC_ORIGIN and HTTPS_PORT, as init-config does
    in production. Nothing is written here.
    """
    known = catalog.source_descriptors(common.ROOT)
    settings = {}
    for component, descriptor in known.items():
        source = descriptor["public_from"]
        overrides = (
            public_settings(
                settings[source], common.BUILD / "dev" / source / "config.yaml"
            )
            if source
            else None
        )
        settings[component] = rendering.component_defaults(
            component, overrides=overrides, dev=True
        )
    return known, settings


def dev_database_preflight(settings):
    """Check the dev database volumes of every catalog component before any writes."""
    for component, config in settings.items():
        database_preflight(
            config,
            common.BUILD / "dev" / component / "config.yaml",
            common.ROOT / "components" / component / "manifests",
        )


def prepare_components():
    """Render the catalog components with private dev state and their registrations."""
    state = common.BUILD / "dev"
    known, settings_by_component = dev_settings()
    dev_database_preflight(settings_by_component)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    for component, settings in settings_by_component.items():
        target = state / component / "config.yaml"
        rendering.write_private(target, yaml.safe_dump(settings, sort_keys=False))
    # Dev registrations come only from the current catalog. Removing older copies
    # keeps a service removed from bundles.yaml out of the proxy and Identity.
    for name in catalog.ROLE_FILES:
        if (state / name).is_symlink():
            raise common.DeployError(
                f"Refuse symlinked dev registrations: {state / name}"
            )
        shutil.rmtree(str(state / name), ignore_errors=True)
    with tempfile.TemporaryDirectory(prefix="myproduct-prepare-") as directory:
        imports, updates = registration_stage(
            list(known), Path(directory), known, home=state
        )
        documents = []
        for component in known:
            text = rendering.materialize_and_render(
                state / component / "files",
                config_path=state / component / "config.yaml",
                manifests=common.ROOT / "components" / component / "manifests",
                component=component,
                extra_volumes=component_imports(component, imports, known),
            )
            documents.extend(yaml.safe_load_all(text))
        rendering.check_links(documents, {})
        write_registrations(updates, home=state)
        rendering.write_private(
            common.BUILD / "install.yaml",
            yaml.safe_dump_all(documents, sort_keys=False),
        )
    print(f"[OK] {common.BUILD / 'install.yaml'}")


def prepare():
    """Write validated dev YAML and import archives without running Podman."""
    if (common.ROOT / "components").is_dir():
        if (common.ROOT / "bundle.yaml").exists():
            raise common.DeployError(
                "Run prepare from the source checkout; production bundles use persistent config with install"
            )
        prepare_components()
        return
    prepare_standalone()


def prepare_standalone():
    """Render the explicit root-config fixture used by standalone examples/tests."""
    output = common.BUILD / "install.yaml"
    if common.CONFIG.is_file():
        database_preflight(
            rendering.load_config(common.CONFIG), common.CONFIG, common.MANIFESTS
        )
    rendering.write_private(output, rendering.materialize_and_render())
    print(f"[OK] {output}")


def run(*args):
    """Show and run a command; stop on a failing status."""
    print("+", " ".join(map(str, args)))
    subprocess.run(list(map(str, args)), check=True)


def production_environment():
    """Validate the service user and set its runtime before rendering or commands."""
    if os.geteuid() == 0:
        raise common.DeployError("Run install as the service user, not as root")

    configured_home = os.environ.get("HOME")
    if configured_home is not None and Path(configured_home) != common.HOME:
        raise common.DeployError(
            f"HOME={configured_home!r} differs from the home directory {common.HOME} in "
            "the user database. Run install with the service user's HOME"
        )

    runtime = Path(f"/run/user/{os.geteuid()}")
    configured_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if configured_runtime is not None and configured_runtime != str(runtime):
        raise common.DeployError(
            f"XDG_RUNTIME_DIR={configured_runtime!r} differs from the expected {runtime} "
            "for the service user"
        )
    if not runtime.is_dir():
        raise common.DeployError(
            f"Missing runtime directory {runtime}. Enable linger for the service user "
            "with loginctl enable-linger and check that the user instance is running"
        )
    os.environ["XDG_RUNTIME_DIR"] = str(runtime)


def install_standalone():
    """Install a standalone rootless manifest fixture using the persistent config."""
    production_environment()
    config_path = common.HOME / "config.yaml"
    if config_path.is_file():
        database_preflight(
            rendering.load_config(config_path), config_path, common.MANIFESTS
        )
    text = rendering.materialize_and_render(
        common.FILES_DIR, write_archives=False, config_path=config_path
    )
    archive = common.ROOT / "images" / "images.tar"
    if not archive.is_file():
        raise common.DeployError(f"Missing image archive {archive}")
    run("podman", "load", "-i", archive)
    for image in rendering.find_images(yaml.safe_load_all(text)):
        try:
            run("podman", "image", "exists", image)
        except subprocess.CalledProcessError as error:
            raise common.DeployError(
                f"Image {image} is not available after podman load "
                f"(podman image exists returned exit {error.returncode})"
            ) from None

    # Old YAML must not import new files after a failed image check.
    rendering.materialize_and_render(common.FILES_DIR, config_path=config_path)

    common.QUADLET_DIR.mkdir(parents=True, exist_ok=True)
    rendering.write_private(common.QUADLET_YAML, text)
    for suffix in (".kube", ".network"):
        target = common.QUADLET_TARGET.with_suffix(suffix)
        target.write_text(
            common.QUADLET_TEMPLATE.with_suffix(suffix).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        target.chmod(0o644)

    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "restart", common.SERVICE)
    run("systemctl", "--user", "is-active", "--quiet", common.SERVICE)
    run("podman", "ps", "--all", "--pod")

    print(
        f"[OK] {common.SERVICE} is running. Check that the containers above are 'Up'."
    )


def bundle_descriptor():
    """Read this unpacked bundle's own validated component descriptor."""
    return catalog.load_bundle_descriptor(common.ROOT)


def check_dependencies_installed(descriptor):
    """Every declared dependency must be installed in a compatible version."""
    for dependency, requirement in descriptor["requires"].items():
        version = catalog.installed_version(common.HOME, dependency)
        if version is None:
            raise common.DeployError(
                "Install the separate "
                + dependency
                + " bundle before installing "
                + descriptor["name"]
            )
        check_version_requirement(dependency, version, requirement, descriptor["name"])


def check_dependents(descriptor, installed):
    """Installed dependents keep their recorded requirement on this component."""
    component = descriptor["name"]
    for name in catalog.dependents(installed, common.HOME, component):
        check_version_requirement(
            component,
            descriptor["version"],
            installed[name]["requires"][component],
            name,
        )


def check_version_requirement(component, version, requirement, dependent):
    """Use the existing inclusive-minimum/exclusive-upper numeric contract."""
    catalog.check_range(requirement)
    if (
        not catalog.version_number(requirement["min"])
        <= catalog.version_number(version)
        < catalog.version_number(requirement["before"])
    ):
        raise common.DeployError(
            component.title() + " version does not satisfy dependency for " + dependent
        )


def install_needed(descriptor):
    """Decide whether this install renders and restarts the component.

    upgrade: always reinstalls every time. upgrade: newer-only installs a missing
    or newer version, keeps an equal one and refuses a downgrade.
    """
    if descriptor["upgrade"] == "always":
        return True
    component = descriptor["name"]
    installed = catalog.installed_version(common.HOME, component)
    if installed is None:
        return True
    requested = catalog.version_number(descriptor["version"])
    if requested < catalog.version_number(installed):
        raise common.DeployError(
            component.title()
            + " downgrade refused: requested "
            + descriptor["version"]
            + ", installed "
            + installed
        )
    return requested > catalog.version_number(installed)


def component_paths(component, home=None):
    """Return one component's persistent config, archives and Quadlet paths."""
    base = (home or common.HOME).resolve()
    state = base / component
    paths = [
        state,
        state / "files",
        state / "config.yaml",
        base / "installed" / component,
        base / "metadata",
        catalog.metadata_path(base, component),
    ]
    paths.extend((state / "files").glob("*.tar"))
    if home is None:
        paths.extend(
            [
                common.QUADLET_DIR / ("myproduct-" + component + suffix)
                for suffix in (".yaml", ".kube")
            ]
        )
    if any(path.is_symlink() for path in paths):
        raise common.DeployError(
            f"Refuse symlinked component state or output paths for {component}"
        )
    return (
        state / "config.yaml",
        state / "files",
        common.QUADLET_DIR / ("myproduct-" + component + ".yaml"),
        common.QUADLET_DIR / ("myproduct-" + component + ".kube"),
    )


def registration_stage(components, directory, known, home=None):
    """Stage existing and proposed public routes and clients without changing live state.

    known maps component IDs to descriptors: installed metadata plus the incoming
    bundle in production, the source catalog in dev. Each existing registration
    must belong to a known component; the role owners come from accepts.
    """
    home = home or common.HOME
    owners = catalog.role_owners(known, "registration owners")
    for name in catalog.ROLE_FILES:
        source = home / name
        if source.is_symlink():
            raise common.DeployError(
                f"Refuse symlinked shared registration directory: {source}"
            )
        (directory / name).mkdir()
        if not source.exists():
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
                shutil.copy2(path, directory / name / path.name)
                continue
            if not path.is_dir() or path.name not in known:
                raise common.DeployError(
                    f"Unexpected public client registration: {path}"
                )
            if path.name in components and known[path.name]["clients"]:
                continue  # Rebuild the incoming client even after a partial prior write.
            target = directory / name / path.name
            target.mkdir()
            for filename in ("client.json", "client.crt"):
                public = path / filename
                if public.is_symlink():
                    raise common.DeployError(
                        f"Refuse symlinked public client file: {public}"
                    )
                shutil.copy2(public, target / filename)
    updates = {}
    for component in components:
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
        config_path = component_paths(component, home)[0]
        config = rendering.load_config(config_path)
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
    return imports, updates


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


def client_registration(component, path, config, config_path):
    """Build one public OIDC client registration from client.yaml.

    Protocol of the existing apps and Identity: the app requests its client ID
    as a scope, so scopes are exactly [openid, profile, <id>], and the redirect
    URI is PUBLIC_ORIGIN + base_path + /auth/callback. The client ID and
    base_path must match the app's APP_ID and BASE_PATH settings; they may
    differ from the component ID. Only public certificates are accepted.
    """
    metadata = rendering.load_yaml(path)
    if (
        not isinstance(metadata, dict)
        or set(metadata) != {"id", "base_path", "scopes", "certificate"}
        or not isinstance(metadata["id"], str)
        or not common.ID.fullmatch(metadata["id"])
        or not isinstance(metadata["base_path"], str)
        or not CLIENT_PATH.fullmatch(metadata["base_path"])
        or metadata["scopes"] != ["openid", "profile", metadata["id"]]
        or not isinstance(metadata["certificate"], str)
        or Path(metadata["certificate"]).is_absolute()
        or ".." in Path(metadata["certificate"]).parts
    ):
        raise common.DeployError(
            f"Invalid public client descriptor: {path}; expected id, "
            "base_path (/path), scopes [openid, profile, <id>] and a relative certificate"
        )
    certificate = rendering.resolve_path(metadata["certificate"], config_path.parent)
    certificate_bytes = certificate.read_bytes()
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


def write_registrations(updates, home=None):
    """Write changed public registrations privately; unchanged files are kept."""
    if any(((home or common.HOME) / relative).is_symlink() for relative in updates):
        raise common.DeployError("Refuse symlinked public registration output")
    for relative, data in updates.items():
        target = (home or common.HOME) / relative
        if target.is_file() and target.read_bytes() == data:
            continue
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.parent.chmod(0o700)
        rendering.write_private(target, data.decode("utf-8"))


def component_imports(component, imports, known):
    """Return the registration archives this component accepts, if any."""
    selected = {
        volume: imports[volume]
        for volume in known[component]["accepts"].values()
        if volume in imports
    }
    return selected or None


def pending_path():
    """Keep retry metadata outside releases; never traverse a symlinked state path."""
    path = common.HOME / "pending-operation.json"
    if any(parent.is_symlink() for parent in [path] + list(path.parents)):
        raise common.DeployError("Refuse symlinked pending-operation state")
    return path


def load_pending():
    """Accept only the small, component-scoped install/uninstall retry record."""
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
        keys = {"operation", "component", "owners"}
        if operation == "uninstall":
            keys.update(("delete_data", "volumes", "stopped"))
        elif operation != "install":
            raise ValueError("operation")
        component = state.get("component")
        if (
            set(state) != keys
            or not isinstance(component, str)
            or not common.ID.fullmatch(component)
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


def check_pending(operation, component, delete_data=False):
    """Reject conflicting lifecycle commands; resume only the recorded operation."""
    state = load_pending()
    if state is None:
        return None
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
    descriptor = os.open(str(common.HOME), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def save_pending(state):
    """Atomically replace private metadata; an interrupted write retains the old record."""
    path = pending_path()
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=str(common.HOME))
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


def registration_changes(updates, owners, home=None):
    """Compare before writing so unfinished owners can be recorded first."""
    changed = set()
    for relative, data in updates.items():
        target = (home or common.HOME) / relative
        if target.is_symlink():
            raise common.DeployError("Refuse symlinked public registration output")
        if not target.is_file() or target.read_bytes() != data:
            changed.add(owners[relative.split("/", 1)[0]])
    return changed


def check_shared_network():
    """Validate the shared network before creating secrets or loading images."""
    network = common.QUADLET_DIR / "myproduct.network"
    network_text = common.QUADLET_TEMPLATE.with_suffix(".network").read_text(
        encoding="utf-8"
    )
    if network.exists() and network.read_text(encoding="utf-8") != network_text:
        raise common.DeployError(
            f"Existing shared network differs from the bundle: {network}"
        )
    return network, network_text


def materialize_component_manifests(components, imports, known):
    """Validate and render selected components; missing secrets may be created here."""
    rendered = {}
    for component in components:
        config, files, _, _ = component_paths(component)
        rendered[component] = rendering.materialize_and_render(
            files,
            write_archives=False,
            config_path=config,
            manifests=common.ROOT / "components" / component / "manifests",
            component=component,
            extra_volumes=component_imports(component, imports, known),
        )
    return rendered


def load_and_verify_images(components, source_components, rendered):
    """Load this bundle and verify every required image before persistent service changes."""
    archive = common.ROOT / "images/images.tar"
    if not archive.is_file():
        raise common.DeployError(f"Missing image archive {archive}")
    run("podman", "load", "-i", archive)
    documents = [doc for text in rendered.values() for doc in yaml.safe_load_all(text)]
    for component in source_components:
        if component not in components:
            for path in sorted(
                (common.ROOT / "components" / component / "manifests").glob("*.yaml")
            ):
                documents.extend(rendering.load_yaml_all(path))
    for image in rendering.find_images(documents):
        try:
            run("podman", "image", "exists", image)
        except subprocess.CalledProcessError as error:
            raise common.DeployError(
                f"Image {image} is unavailable after load (exit {error.returncode})"
            ) from None


def apply_registration_updates(component, updates, owners):
    """Record unfinished owners durably before writing their public registrations."""
    pending = check_pending("install", component)
    changed = registration_changes(updates, owners) | set(
        pending["owners"] if pending else []
    )
    if changed:
        pending = {
            "operation": "install",
            "component": component,
            "owners": sorted(changed),
        }
        save_pending(pending)
    write_registrations(updates)
    return changed, pending


def write_component_units_and_imports(
    components, imports, rendered, network, network_text, known
):
    """Write selected imports/YAML/Quadlets, retaining the existing shared network."""
    common.QUADLET_DIR.mkdir(parents=True, exist_ok=True)
    if not network.exists():
        network.write_text(network_text, encoding="utf-8")
        network.chmod(0o644)
    for component in components:
        config, files, output, quadlet = component_paths(component)
        rendering.materialize_and_render(
            files,
            config_path=config,
            manifests=common.ROOT / "components" / component / "manifests",
            component=component,
            extra_volumes=component_imports(component, imports, known),
        )
        rendering.write_private(output, rendered[component])
        quadlet.write_text(
            common.QUADLET_TEMPLATE.read_text(encoding="utf-8").replace(
                "Yaml=myproduct.yaml", "Yaml=" + output.name
            ),
            encoding="utf-8",
        )
        quadlet.chmod(0o644)


def write_changed_owner_imports(components, changed, imports, known):
    """Rebuild imports for registration owners outside the selected component."""
    for owner in sorted(changed):
        if owner not in components:
            rendering.write_file_archives(
                component_imports(owner, imports, known) or {},
                component_paths(owner)[1],
            )


def restart_order(known, names):
    """Dependents first: an owner restarts after the components it serves.

    The gateway thus publishes a new route only once the service behind it and
    its client registration are back.
    """
    return list(reversed(catalog.dependency_order(known, names)))


def restart_component_services(components, changed, pending, known):
    """Restart the selected component and changed owners in restart_order.

    Each owner is acknowledged in the pending record only after its restart
    and active check succeed, so a retry repeats exactly the unfinished owners.
    """
    run("systemctl", "--user", "daemon-reload")
    for component in restart_order(known, set(components) | changed):
        service = "myproduct-" + component + ".service"
        run("systemctl", "--user", "restart", service)
        run("systemctl", "--user", "is-active", "--quiet", service)
        if pending and component in pending["owners"]:
            pending["owners"].remove(component)
            if pending["owners"]:
                save_pending(pending)
            else:
                clear_pending()
                pending = None


def write_install_record(path, text):
    """Atomically publish a private record, retaining the old file on write failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".install-", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(path))
        directory = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_installed_metadata(descriptor):
    """Record public metadata before registrations name this component.

    Registration staging accepts only known components, and a retry or another
    bundle may need this descriptor before the completion marker exists.
    """
    write_install_record(
        catalog.metadata_path(common.HOME, descriptor["name"]),
        json.dumps(descriptor, sort_keys=True) + "\n",
    )


def write_installed_marker(descriptor):
    """Publish the version last; it confirms the install completed."""
    write_install_record(
        common.HOME / "installed" / descriptor["name"], descriptor["version"] + "\n"
    )


def install_component_plan(descriptor, components, known, imports, updates):
    """Apply a staged install in the established validation/write/restart order."""
    name = descriptor["name"]
    owners = catalog.role_owners(known, "registration owners")
    network, network_text = check_shared_network()
    rendered = materialize_component_manifests(components, imports, known)
    load_and_verify_images(components, [name], rendered)
    write_installed_metadata(descriptor)
    changed, pending = apply_registration_updates(name, updates, owners)
    write_component_units_and_imports(
        components, imports, rendered, network, network_text, known
    )
    write_changed_owner_imports(components, changed, imports, known)
    restart_component_services(components, changed, pending, known)
    write_installed_marker(descriptor)
    run("podman", "ps", "--all", "--pod")


def install_components():
    """Validate the bundle, installed state and config before writing anything.

    Order: descriptors and dependencies, then config and database preflight,
    then staging in a temporary directory, then install_component_plan.
    """
    production_environment()
    descriptor = bundle_descriptor()
    name = descriptor["name"]
    pending = check_pending("install", name)
    installed = catalog.load_installed_metadata(common.HOME)
    known = dict(installed)
    known[name] = descriptor
    # An incoming descriptor must not take over a role another component serves.
    catalog.check_owners(known, "installed components and this bundle")
    if pending and not set(pending["owners"]) <= {
        descriptor["routes"],
        descriptor["clients"],
    }:
        raise common.DeployError("Invalid pending-operation state; no changes made")
    check_dependencies_installed(descriptor)
    check_dependents(descriptor, installed)
    components = [name] if install_needed(descriptor) else []
    for path in sorted(
        (common.ROOT / "components" / name / "manifests").glob("*.yaml")
    ):
        rendering.check_component_names(rendering.load_yaml_all(path), name, path)
    config_path = component_paths(name)[0]
    config = rendering.load_config(config_path)
    rendering.validate_component_config(
        config, name, config_path, check_placeholders=bool(components)
    )
    check_public_settings(descriptor, config, config_path)
    for component in components:
        database_preflight(
            config, config_path, common.ROOT / "components" / component / "manifests"
        )
    with tempfile.TemporaryDirectory(
        prefix="myproduct-install-", dir=os.environ["XDG_RUNTIME_DIR"]
    ) as directory:
        imports, updates = registration_stage([name], Path(directory), known)
        install_component_plan(descriptor, components, known, imports, updates)


def install():
    """Install the selected component bundle or a standalone manifest fixture."""
    if (common.ROOT / "bundle.yaml").exists():
        install_components()
    elif (common.ROOT / "components").is_dir():
        raise common.DeployError(
            "Run install from an unpacked component bundle, not the source checkout"
        )
    else:
        install_standalone()


def uninstall(component=None, delete_data=False):
    """Resume one scoped uninstall from validated metadata, even after removing its YAML."""
    production_environment()
    own = bundle_descriptor()["name"]
    component = component or own
    if component != own:
        raise common.DeployError("This bundle can only uninstall its own component")
    state = check_pending("uninstall", component, delete_data)
    marker = common.HOME / "installed" / component
    if state is None and not marker.is_file():
        raise common.DeployError(f"Component {component} is not installed")
    installed = catalog.load_installed_metadata(common.HOME)
    dependents = catalog.dependents(installed, common.HOME, component)
    if dependents:
        raise common.DeployError(
            component.title() + " is still required by: " + ", ".join(dependents)
        )
    _, _, output, quadlet = component_paths(component)
    route = common.HOME / "routes" / (component + ".conf")
    client = common.HOME / "clients" / component
    for path in (
        output,
        quadlet,
        route,
        client,
        marker,
        catalog.metadata_path(common.HOME, component),
    ):
        if any(parent.is_symlink() for parent in [path] + list(path.parents)):
            raise common.DeployError("Refuse symlinked uninstall state or output paths")
    if state is None:
        documents = rendering.load_yaml_all(output)
        rendering.check_component_names(documents, component, output)
        volumes = sorted(
            {
                doc["metadata"]["name"]
                for doc in documents
                if isinstance(doc, dict)
                and doc.get("kind") in ("Secret", "PersistentVolumeClaim")
            }
        )
        config_maps = {
            doc["metadata"]["name"]
            for doc in documents
            if isinstance(doc, dict) and doc.get("kind") == "ConfigMap"
        }
        for doc in documents:
            if not isinstance(doc, dict) or doc.get("kind") != "Pod":
                continue
            for volume in doc.get("spec", {}).get("volumes", []):
                if "configMap" not in volume:
                    continue
                source = volume["configMap"]
                if (
                    not isinstance(source, dict)
                    or not isinstance(source.get("name"), str)
                    or source["name"] not in config_maps
                ):
                    raise common.DeployError("Invalid mounted ConfigMap for uninstall")
                if source["name"] not in volumes:
                    volumes.append(source["name"])
        volumes.sort()
        if any(
            not common.ID.fullmatch(name) or not name.startswith(component + "-")
            for name in volumes
        ):
            raise common.DeployError("Invalid component volume name for uninstall")
        # Validate every public input before saving the plan or stopping/deleting anything.
        with tempfile.TemporaryDirectory(
            prefix="myproduct-remove-", dir=os.environ["XDG_RUNTIME_DIR"]
        ) as directory:
            registration_stage([], Path(directory), installed)
        role_owners = catalog.role_owners(installed, "installed components")
        owners = set()
        if route.is_file():
            owners.add(role_owners["routes"])
        if client.exists():
            owners.add(role_owners["clients"])
        state = {
            "operation": "uninstall",
            "component": component,
            "delete_data": delete_data,
            "volumes": volumes,
            "stopped": False,
            "owners": sorted(
                owner
                for owner in owners
                if owner not in (None, component)
                and catalog.installed_version(common.HOME, owner)
            ),
        }
        save_pending(state)
    if not state["stopped"]:
        run("systemctl", "--user", "stop", "myproduct-" + component + ".service")
        state["stopped"] = True
        save_pending(state)
    for path in (output, quadlet, route):
        if path.exists():
            path.unlink()
    if client.exists():
        shutil.rmtree(client)
    run("systemctl", "--user", "daemon-reload")
    if state["owners"]:
        with tempfile.TemporaryDirectory(
            prefix="myproduct-remove-", dir=os.environ["XDG_RUNTIME_DIR"]
        ) as directory:
            imports, _ = registration_stage([], Path(directory), installed)
            for owner in list(state["owners"]):
                component_paths(owner)
                if owner not in installed or not catalog.installed_version(
                    common.HOME, owner
                ):
                    raise common.DeployError(
                        "Pending registration owner is not installed: " + owner
                    )
            for owner in restart_order(installed, state["owners"]):
                rendering.write_file_archives(
                    component_imports(owner, imports, installed) or {},
                    component_paths(owner)[1],
                )
                service = "myproduct-" + owner + ".service"
                run("systemctl", "--user", "restart", service)
                run("systemctl", "--user", "is-active", "--quiet", service)
                state["owners"].remove(owner)
                save_pending(state)
    if delete_data:
        for name in state["volumes"]:
            result = subprocess.run(  # noqa: UP022 - Python 3.6
                ["podman", "volume", "exists", name],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if result.returncode == 0:
                run("podman", "volume", "rm", name)
            elif result.returncode != 1:
                raise common.DeployError(f"Cannot check volume {name} before deletion")
        if (common.HOME / component).exists():
            shutil.rmtree(common.HOME / component)
    # Marker first: metadata without a marker is an unfinished install, never the reverse.
    for path in (marker, catalog.metadata_path(common.HOME, component)):
        if path.exists():
            path.unlink()
    clear_pending()
    print(
        f"[OK] Uninstalled {component}; shared network retained; data {'deleted' if delete_data else 'preserved'}"
    )
