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

from . import common
from . import render as rendering


def init_config(component):
    """Exclusively materialize one bundled config; never create private input files."""
    production_environment()
    if component not in bundle_components():
        raise common.DeployError(
            f"Component {component} is not included in this bundle"
        )
    check_pending("init-config", component)
    if component != "platform":
        component_dependencies(component)
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
    platform_path = component_paths("platform")[0]
    if (
        component != "platform"
        and (common.HOME / "installed/platform").exists()
        and not platform_path.exists()
    ):
        raise common.DeployError(
            f"Missing {platform_path}; restore installed platform config before initializing {component}"
        )
    if component != "platform" and platform_path.exists():
        platform = rendering.load_config(platform_path)
        rendering.validate_component_config(
            platform,
            "platform",
            platform_path,
            check_placeholders=not (common.HOME / "installed/platform").is_file(),
        )
        overrides = {key: platform[key] for key in ("PUBLIC_ORIGIN", "HTTPS_PORT")}
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
                entries = config.get(common.SECRET_FILES, {}).get(
                    secret["secretName"], []
                )
                candidates = []
                for entry in entries:
                    source = rendering.resolve_path(entry, config_path.parent)
                    candidates.append(source if source.name == key else source / key)
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
                        f"Missing database password file {password}; add its path to {common.GENERATED_SECRETS} in {config_path}"
                    )


def prepare_components():
    """Render all source components with private dev state and shared imported registrations."""
    state = common.BUILD / "dev"
    settings_by_component = {
        component: rendering.component_defaults(component, dev=True)
        for component in common.COMPONENTS
    }
    for component, settings in settings_by_component.items():
        database_preflight(
            settings,
            state / component / "config.yaml",
            common.ROOT / "components" / component / "manifests",
        )
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    for component in common.COMPONENTS:
        target = state / component / "config.yaml"
        settings = settings_by_component[component]
        rendering.write_private(target, yaml.safe_dump(settings, sort_keys=False))
    with tempfile.TemporaryDirectory(prefix="myproduct-prepare-") as directory:
        imports, updates = registration_stage(
            ["identity", "app1", "app2", "help"], Path(directory), home=state
        )
        documents = []
        for component in common.COMPONENTS:
            text = rendering.materialize_and_render(
                state / component / "files",
                config_path=state / component / "config.yaml",
                manifests=common.ROOT / "components" / component / "manifests",
                component=component,
                extra_volumes=component_imports(
                    component, imports, settings_by_component[component]
                ),
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


def bundle_components():
    """Accept only one component per offline bundle, with explicit dependencies."""
    descriptor = rendering.load_yaml(common.ROOT / "bundle.yaml")
    if not isinstance(descriptor, dict) or set(descriptor) != {
        "name",
        "components",
        "requires",
    }:
        raise common.DeployError(
            "Invalid bundle.yaml; use a separate platform/identity/app/help bundle"
        )
    name = descriptor["name"]
    if name not in common.COMPONENTS or descriptor["components"] != [name]:
        raise common.DeployError(
            "Invalid bundle component selection; platform must be separate"
        )
    requires = descriptor["requires"]
    if not isinstance(requires, dict) or set(requires) != set(
        common.DEPENDENCIES[name]
    ):
        raise common.DeployError("Invalid bundle dependencies")
    for requirement in requires.values():
        validate_platform_requirement(requirement)
    return [name]


def platform_requirement(version):
    """Declare a compatible major series, or minor series while platform is 0.x."""
    major, minor, _ = version_number(version)
    upper = f"{major + 1}.0.0" if major else f"0.{minor + 1}.0"
    return {"min": version, "before": upper}


def validate_platform_requirement(requirement):
    """Require an explicit nonempty inclusive-minimum/exclusive-upper range."""
    if not isinstance(requirement, dict) or set(requirement) != {"min", "before"}:
        raise common.DeployError("Invalid platform version requirement")
    if not all(isinstance(value, str) for value in requirement.values()):
        raise common.DeployError("Invalid platform version requirement")
    if version_number(requirement["min"]) >= version_number(requirement["before"]):
        raise common.DeployError("Empty platform version requirement")


def component_dependencies(component):
    """Validate fixed component dependencies and installed dependents before writes."""
    check_pending("install", component)
    requires = rendering.load_yaml(common.ROOT / "bundle.yaml")["requires"]
    for dependency, requirement in requires.items():
        marker = common.HOME / "installed" / dependency
        if not marker.is_file():
            raise common.DeployError(
                "Install the separate "
                + dependency
                + " bundle before installing "
                + component
            )
        check_version_requirement(
            dependency, marker.read_text().strip(), requirement, component
        )
    requested = (
        (common.ROOT / common.VERSION_FILES.get(component, "VERSION"))
        .read_text()
        .strip()
    )
    for name in common.COMPONENTS:
        if (
            name == component
            or component not in common.DEPENDENCIES[name]
            or not (common.HOME / "installed" / name).is_file()
        ):
            continue
        path = common.HOME / "dependencies" / (name + ".json")
        try:
            installed = json.loads(path.read_text())
            if not isinstance(installed, dict) or set(installed) != set(
                common.DEPENDENCIES[name]
            ):
                raise ValueError("dependency keys")
            for requirement in installed.values():
                validate_platform_requirement(requirement)
        except (OSError, ValueError, KeyError, TypeError, common.DeployError):
            raise common.DeployError(
                "Missing or invalid installed " + component + " requirement for " + name
            ) from None
        check_version_requirement(component, requested, installed[component], name)


def check_version_requirement(component, version, requirement, dependent):
    """Use the existing inclusive-minimum/exclusive-upper numeric contract."""
    validate_platform_requirement(requirement)
    if (
        not version_number(requirement["min"])
        <= version_number(version)
        < version_number(requirement["before"])
    ):
        raise common.DeployError(
            component.title() + " version does not satisfy dependency for " + dependent
        )


def version_number(value):
    """Parse a three-part numeric version for deterministic platform comparisons."""
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise common.DeployError(
            "Versions must contain three numeric parts: major.minor.patch"
        )
    return tuple(int(part) for part in value.split("."))


def platform_upgrade_needed(version):
    """Retain the existing platform comparison entry point."""
    return shared_upgrade_needed("platform", version)


def shared_upgrade_needed(component, version):
    """Install missing/newer shared components; retain equals and refuse downgrades."""
    requested = version_number(version)
    marker = common.HOME / "installed" / component
    if not marker.is_file():
        return True
    installed = version_number(marker.read_text().strip())
    if requested < installed:
        raise common.DeployError(
            component.title()
            + " downgrade refused: requested "
            + version
            + ", installed "
            + marker.read_text().strip()
        )
    return requested > installed


def component_paths(component, home=None):
    """Return one component's persistent config, archives and Quadlet paths."""
    base = (home or common.HOME).resolve()
    state = base / component
    paths = [
        state,
        state / "files",
        state / "config.yaml",
        base / "installed" / component,
        base / "dependencies",
        base / "dependencies" / (component + ".json"),
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


def registration_stage(components, directory, home=None):
    """Stage existing and proposed public routes and clients without changing live state."""
    home = home or common.HOME
    for name in ("routes", "clients"):
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
                if path.suffix == ".conf":
                    shutil.copy2(path, directory / name / path.name)
            elif path.is_dir() and path.name in ("app1", "app2"):
                if (
                    path.name in components
                    and (
                        common.ROOT / "components" / path.name / "client.yaml"
                    ).is_file()
                ):
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
            else:
                raise common.DeployError(
                    f"Unexpected public client registration: {path}"
                )
    updates = {}
    for component in components:
        source = common.ROOT / "components" / component
        route = source / "route.conf"
        client = source / "client.yaml"
        if not route.is_file() and not client.is_file():
            continue
        config = rendering.load_config(component_paths(component, home)[0])
        platform = rendering.load_config(component_paths("platform", home)[0])
        if any(
            config.get(key) != platform.get(key)
            for key in ("PUBLIC_ORIGIN", "HTTPS_PORT")
        ):
            raise common.DeployError(
                f"{component} PUBLIC_ORIGIN and HTTPS_PORT must match the persistent platform config"
            )
        if route.is_file():
            updates["routes/" + component + ".conf"] = route.read_bytes()
        if client.is_file():
            metadata = rendering.load_yaml(client)
            if (
                not isinstance(metadata, dict)
                or set(metadata) != {"id", "base_path", "scopes", "certificate"}
                or metadata["id"] != component
                or metadata["base_path"] != "/" + component
                or metadata["scopes"] != ["openid", "profile", component]
                or not isinstance(metadata["certificate"], str)
                or Path(metadata["certificate"]).is_absolute()
                or ".." in Path(metadata["certificate"]).parts
            ):
                raise common.DeployError(f"Invalid public client descriptor: {client}")
            certificate = rendering.resolve_path(
                metadata["certificate"], component_paths(component, home)[0].parent
            )
            certificate_bytes = certificate.read_bytes()
            try:
                ssl.PEM_cert_to_DER_cert(certificate_bytes.decode("ascii"))
            except (ValueError, UnicodeError):
                raise common.DeployError(
                    f"Expected a public PEM certificate in {certificate}"
                ) from None
            rendering.public_origin(
                config.get("PUBLIC_ORIGIN"), component_paths(component, home)[0]
            )
            origin = config["PUBLIC_ORIGIN"].rstrip("/")
            prefix = "clients/" + component + "/"
            updates[prefix + "client.crt"] = certificate_bytes
            updates[prefix + "client.json"] = json.dumps(
                {
                    "Id": component,
                    "RedirectUris": [origin + metadata["base_path"] + "/auth/callback"],
                    "Scopes": metadata["scopes"],
                    "Certificate": "client.crt",
                },
                sort_keys=True,
            ).encode("utf-8")
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
    index = directory / "clients/installed.json"
    index.write_text(
        json.dumps([path.name + "/client.json" for path in client_dirs]),
        encoding="utf-8",
    )
    # Imports overwrite files without deleting old entries; only these current indexes are read.
    imports = {"platform-routes": [routes], "identity-clients": client_dirs + [index]}
    return imports, updates


def write_registrations(updates, home=None):
    """Write changed public registrations privately and report which registration owners must restart."""
    changed = set()
    if any(((home or common.HOME) / relative).is_symlink() for relative in updates):
        raise common.DeployError("Refuse symlinked public registration output")
    for relative, data in updates.items():
        target = (home or common.HOME) / relative
        if target.is_file() and target.read_bytes() == data:
            continue
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.parent.chmod(0o700)
        rendering.write_private(target, data.decode("utf-8"))
        changed.add("platform" if relative.startswith("routes/") else "identity")
    return changed


def component_imports(component, imports, config=None):
    """Route and client archives have separate owners; never cross their PVC namespaces."""
    selected = {
        key: value for key, value in imports.items() if key.startswith(component + "-")
    }
    if config is not None:
        selected = {
            key: value
            for key, value in selected.items()
            if key in config.get(common.VOLUME_FILES, {})
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
            or component not in common.COMPONENTS
        ):
            raise ValueError("component/fields")
        owners = state["owners"]
        allowed = set(common.DEPENDENCIES[component])
        if (
            not isinstance(owners, list)
            or any(not isinstance(owner, str) for owner in owners)
            or len(set(owners)) != len(owners)
            or not set(owners) <= allowed
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


def registration_changes(updates, home=None):
    """Compare before writing so unfinished owners can be recorded first."""
    changed = set()
    for relative, data in updates.items():
        target = (home or common.HOME) / relative
        if target.is_symlink():
            raise common.DeployError("Refuse symlinked public registration output")
        if not target.is_file() or target.read_bytes() != data:
            changed.add("platform" if relative.startswith("routes/") else "identity")
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


def materialize_component_manifests(components, imports):
    """Validate and render selected components; missing secrets may be created here."""
    rendered = {}
    for component in components:
        config, files, _, _ = component_paths(component)
        extra = component_imports(component, imports, rendering.load_config(config))
        rendered[component] = rendering.materialize_and_render(
            files,
            write_archives=False,
            config_path=config,
            manifests=common.ROOT / "components" / component / "manifests",
            component=component,
            extra_volumes=extra,
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


def apply_registration_updates(component, updates):
    """Record unfinished owners durably before writing their public registrations."""
    pending = check_pending("install", component)
    changed = registration_changes(updates) | set(pending["owners"] if pending else [])
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
    components, imports, rendered, network, network_text
):
    """Write selected imports/YAML/Quadlets, retaining the existing shared network."""
    common.QUADLET_DIR.mkdir(parents=True, exist_ok=True)
    if not network.exists():
        network.write_text(network_text, encoding="utf-8")
        network.chmod(0o644)
    for component in components:
        config, files, output, quadlet = component_paths(component)
        extra = component_imports(component, imports, rendering.load_config(config))
        rendering.materialize_and_render(
            files,
            config_path=config,
            manifests=common.ROOT / "components" / component / "manifests",
            component=component,
            extra_volumes=extra,
        )
        rendering.write_private(output, rendered[component])
        quadlet.write_text(
            common.QUADLET_TEMPLATE.read_text(encoding="utf-8").replace(
                "Yaml=myproduct.yaml", "Yaml=" + output.name
            ),
            encoding="utf-8",
        )
        quadlet.chmod(0o644)


def write_changed_owner_imports(components, changed, imports):
    """Rebuild imports for shared owners outside the selected component."""
    for owner in ("identity", "platform"):
        if owner in changed and owner not in components:
            rendering.write_file_archives(
                component_imports(owner, imports) or {}, component_paths(owner)[1]
            )


def restart_component_services(components, changed, pending):
    """Restart only required services and acknowledge each completed pending owner."""
    run("systemctl", "--user", "daemon-reload")
    services = [
        component for component in components if component not in common.VERSION_FILES
    ]
    services.extend(
        owner
        for owner in ("identity", "platform")
        if owner in components or owner in changed
    )
    for component in services:
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


def write_installed_markers(components):
    """Persist contracts first; publish the version last as completion confirmation."""
    for component in components:
        version = (
            (common.ROOT / common.VERSION_FILES.get(component, "VERSION"))
            .read_text()
            .strip()
        )
        write_install_record(
            common.HOME / "dependencies" / (component + ".json"),
            json.dumps(
                rendering.load_yaml(common.ROOT / "bundle.yaml")["requires"],
                sort_keys=True,
            ),
        )
        write_install_record(common.HOME / "installed" / component, version + "\n")


def install_component_plan(components, source_components, imports, updates):
    """Apply a staged install in the established validation/write/restart order."""
    network, network_text = check_shared_network()
    rendered = materialize_component_manifests(components, imports)
    load_and_verify_images(components, source_components, rendered)
    changed, pending = apply_registration_updates(source_components[0], updates)
    write_component_units_and_imports(
        components, imports, rendered, network, network_text
    )
    write_changed_owner_imports(components, changed, imports)
    restart_component_services(components, changed, pending)
    write_installed_markers(components)
    run("podman", "ps", "--all", "--pod")


def install_components():
    """Validate the selected components and images before writing scoped services."""
    production_environment()
    components = bundle_components()
    component_dependencies(components[0])
    version_number((common.ROOT / "VERSION").read_text().strip())
    source_components = list(components)
    for component in tuple(components):
        if component in common.VERSION_FILES and not shared_upgrade_needed(
            component,
            (common.ROOT / common.VERSION_FILES[component]).read_text().strip(),
        ):
            components.remove(component)
    for component in source_components:
        for path in sorted(
            (common.ROOT / "components" / component / "manifests").glob("*.yaml")
        ):
            rendering.check_component_names(
                rendering.load_yaml_all(path), component, path
            )
        config_path = component_paths(component)[0]
        rendering.validate_component_config(
            rendering.load_config(config_path),
            component,
            config_path,
            check_placeholders=component in components,
        )
    platform_path = component_paths("platform")[0]
    platform = rendering.load_config(platform_path)
    rendering.validate_component_config(
        platform, "platform", platform_path, check_placeholders="platform" in components
    )
    for component in source_components:
        if component == "platform":
            continue
        path = component_paths(component)[0]
        config = rendering.load_config(path)
        for key in ("PUBLIC_ORIGIN", "HTTPS_PORT"):
            if config[key] != platform[key]:
                raise common.DeployError(f"{key} in {path} must match {platform_path}")
    for component in components:
        config_path = component_paths(component)[0]
        database_preflight(
            rendering.load_config(config_path),
            config_path,
            common.ROOT / "components" / component / "manifests",
        )
    with tempfile.TemporaryDirectory(
        prefix="myproduct-install-", dir=os.environ["XDG_RUNTIME_DIR"]
    ) as directory:
        imports, updates = registration_stage(source_components, Path(directory))
        install_component_plan(components, source_components, imports, updates)


def install():
    """Install the selected component bundle or a standalone manifest fixture."""
    if (common.ROOT / "bundle.yaml").exists():
        install_components()
    elif (common.ROOT / "components").is_dir():
        raise common.DeployError(
            "Run install from an unpacked platform/identity/app/help bundle, not the source checkout"
        )
    else:
        install_standalone()


def uninstall(component=None, delete_data=False):
    """Resume one scoped uninstall from validated metadata, even after removing its YAML."""
    production_environment()
    own = bundle_components()[0]
    component = component or own
    if component != own:
        raise common.DeployError("This bundle can only uninstall its own component")
    state = check_pending("uninstall", component, delete_data)
    marker = common.HOME / "installed" / component
    if state is None and not marker.is_file():
        raise common.DeployError(f"Component {component} is not installed")
    dependents = [
        name
        for name in common.COMPONENTS
        if component in common.DEPENDENCIES[name]
        and (common.HOME / "installed" / name).is_file()
    ]
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
        common.HOME / "dependencies" / (component + ".json"),
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
        if any(
            not common.ID.fullmatch(name) or not name.startswith(component + "-")
            for name in volumes
        ):
            raise common.DeployError("Invalid component volume name for uninstall")
        # Validate every public input before saving the plan or stopping/deleting anything.
        with tempfile.TemporaryDirectory(
            prefix="myproduct-remove-", dir=os.environ["XDG_RUNTIME_DIR"]
        ) as directory:
            registration_stage([], Path(directory))
        owners = set()
        if route.is_file():
            owners.add("platform")
        if client.exists():
            owners.add("identity")
        state = {
            "operation": "uninstall",
            "component": component,
            "delete_data": delete_data,
            "volumes": volumes,
            "stopped": False,
            "owners": sorted(
                owner
                for owner in owners
                if owner != component and (common.HOME / "installed" / owner).is_file()
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
            imports, _ = registration_stage([], Path(directory))
            for owner in ("identity", "platform"):
                if owner not in state["owners"]:
                    continue
                component_paths(owner)
                if not (common.HOME / "installed" / owner).is_file():
                    raise common.DeployError(
                        "Pending registration owner is not installed: " + owner
                    )
                rendering.write_file_archives(
                    component_imports(owner, imports) or {}, component_paths(owner)[1]
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
    for path in (marker, common.HOME / "dependencies" / (component + ".json")):
        if path.exists():
            path.unlink()
    clear_pending()
    print(
        f"[OK] Uninstalled {component}; shared network retained; data {'deleted' if delete_data else 'preserved'}"
    )
