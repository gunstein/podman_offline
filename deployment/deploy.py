"""Component preparation and the rootless install/uninstall lifecycle.

Registrations and the pending-operation record live in registrations.py.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from . import (
    catalog,
    common,
    environment,
    health,
    layout,
    mounts,
    registrations,
    templates,
)
from . import render as rendering
from .output import log


def setting_values(component, settings):
    """Typed values for init-config --set: only the release's own scalar settings.

    A value takes the type of the release default (a number stays a number);
    a file group, ENVIRONMENT or MOUNTS cannot be set this way.
    """
    defaults = catalog.release_defaults(component)
    values = {}
    for key, text in settings.items():
        default = defaults.get(key)
        if key not in defaults or isinstance(default, (dict, list)) or default is None:
            raise common.DeployError(
                f"--set {key}: not a setting of {component}; settings: "
                + ", ".join(
                    sorted(
                        name
                        for name, value in defaults.items()
                        if not isinstance(value, (dict, list)) and value is not None
                    )
                )
            )
        if isinstance(default, bool) or not isinstance(default, int):
            values[key] = text
        elif text.isdigit():
            values[key] = int(text)
        else:
            raise common.DeployError(f"--set {key}: expected a number")
    return values


def init_config(component, settings=None, environment_name=None):
    """Exclusively materialize one bundled config; never create private input files.

    settings (KEY: text, from --set) are written into the new config with the
    defaults, in one atomic step: the file appears complete or not at all, so
    the runtime command asks again after an interruption (backlog 69,
    decision 9). An existing config is never changed. environment_name
    (backlog 85) validates the release's declarations with that target
    environment's overrides; nothing of it is written to config.yaml.
    """
    production_environment()
    descriptor = bundle_descriptor()
    env_overrides = target_environment(environment_name, component)
    if component != descriptor["name"]:
        raise common.DeployError(
            f"Component {component} is not included in this bundle"
        )
    registrations.check_pending("init-config", component, descriptor["product"])
    check_dependencies_installed(descriptor)
    target = common.STATE / component / "config.yaml"
    for path in [target] + list(target.parents):
        if path.is_symlink():
            raise common.DeployError(f"Refuse symlinked config path: {path}")
    if target.exists():
        if settings:
            raise common.DeployError(
                f"{target} exists; --set only applies to a new config, edit it instead"
            )
        log.info(
            f"[OK] Existing config retained unchanged: {target}; install validates it"
        )
        return
    values = setting_values(component, settings or {})
    # The gateway's public settings complete the defaults for validation only;
    # they stay in the gateway's config.yaml, which install reads again.
    public = catalog.gateway_settings(descriptor["public_from"])
    config = rendering.component_defaults(component, overrides={**values, **public})
    # The release's own declarations (ENVIRONMENT, MOUNTS, manifests) are
    # checked as validate does, before the file exists; credentials may follow.
    descriptor = catalog.environment_descriptor(
        descriptor, env_overrides, catalog.load_installed_metadata(common.STATE)
    )
    validate_component(
        rendering.effective_config(config, target, component, env_overrides),
        target,
        common.ROOT / "components" / component / "manifests",
        component,
        catalog.imported_volumes(descriptor),
        catalog.imported_secrets(descriptor),
        env_overrides,
    )
    config = {key: value for key, value in config.items() if key not in public}
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.parent.chmod(0o700)
    # Written beside the target, then linked: link fails if the config exists,
    # and a reader never sees a partly written file.
    partial = target.with_name(target.name + ".partial")
    if partial.is_symlink() or partial.exists():
        partial.unlink()
    fd = os.open(str(partial), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        yaml.safe_dump(config, stream, sort_keys=False)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(str(partial), str(target))
    finally:
        partial.unlink()
    log.info(f"[OK] Initialized {target}")


def check_api_secret_lines(descriptor, installed):
    """Identity's API secret lines decide where each installed API's value goes.

    The installed Identity's api_secrets is the only mapping. A new Identity
    release may move a line to another <n> (owner_secrets rebuilds the Secret
    by API name), but it may not drop an installed API.
    """
    name = descriptor["name"]
    apis = sorted(
        other
        for other, entry in installed.items()
        if other != name and entry["apis"] == name
    )
    dropped = [api for api in apis if api not in descriptor["api_secrets"]]
    if dropped:
        raise common.DeployError(
            f"This {name} release has no API secret line for installed "
            f"{', '.join(dropped)}; uninstall {dropped[0]} first, or keep its "
            f"ApiResources__<n>__ApiSecrets__0__Value line in {name}'s ENVIRONMENT"
        )


POSTGRES_DATA = "/var/lib/postgresql/data"


def database_preflight(config, config_path, documents):
    """Guard PostgreSQL password creation using the volume that will be installed.

    documents is effective_documents() output: placeholders are replaced, so
    Podman is asked about the configured volume name. Runs after validation and
    before generation, never inside the generic secret generator. A missing
    password with an existing volume is refused: the volume keeps the old one.
    """
    for claim, password in database_bindings(config, config_path, documents):
        if password.exists() or password.is_symlink():
            check_database_password(password)
            continue
        check_database_volume_absent(claim, password)
        check_password_provided(config, config_path, password)


def database_bindings(config, config_path, documents):
    """Return (data claim, password file) for every database container; no host query.

    Unsupported PostgreSQL layouts are refused here, from declarations only.
    """
    bindings = []
    for pod, spec in rendering.pod_specs(documents):
        for group, container in rendering.containers(spec):
            binding = postgres_binding(
                pod,
                spec,
                group,
                container,
                environment_entries(container, documents, config),
            )
            if binding is None:
                continue
            claim, secret_name, key = binding
            password = database_password_path(config, config_path, secret_name, key)
            bindings.append((claim, password))
    return bindings


def check_password_provided(config, config_path, password):
    """A missing database password must be one that generate creates."""
    if password.resolve() not in rendering.generated_secret_paths(
        config, config_path.parent
    ):
        raise common.DeployError(
            f"Missing database password file {password}; declare generate on its {common.SECRET_FILES} source in {config_path}"
        )


def environment_entries(container, documents, config):
    """The variables a container gets through envFrom, as env entries.

    From a ConfigMap in the effective documents (ENVIRONMENT's public values,
    already substituted) with their values; from an ENVIRONMENT Secret recipe
    by name only, never its value. The database check reads them like the
    manifest's env, so POSTGRES_PASSWORD_FILE may be declared in either place.
    """
    maps = {
        (doc.get("metadata") or {}).get("name"): doc.get("data") or {}
        for doc in documents
        if isinstance(doc, dict) and doc.get("kind") == "ConfigMap"
    }
    recipes = config.get(common.SECRET_TEMPLATES) or {}
    entries = []
    for source in container.get("envFrom", []):
        if not isinstance(source, dict):
            continue
        name = (source.get("configMapRef") or {}).get("name")
        if name in maps:
            entries += [
                {"name": key, "value": value} for key, value in maps[name].items()
            ]
        name = (source.get("secretRef") or {}).get("name")
        if name in recipes:
            entries += [
                {"name": key, "valueFrom": {"secret": name}} for key in recipes[name]
            ]
    return entries


def postgres_binding(pod, spec, group, container, environment=()):
    """Return (data claim, password Secret, Secret key) or None for a non-database container.

    A container is a database container when it sets any POSTGRES_PASSWORD*
    variable, in its manifest env or through environment (environment_entries),
    or mounts the PostgreSQL data directory. Only the POSTGRES_PASSWORD_FILE
    layout with a public path, a mounted Secret and a PVC at the data directory
    is supported; anything else (another password form, a path from a Secret,
    no password setting) is refused so a lost password can never be replaced
    silently (item 7).
    """
    where = f"container {container.get('name', '<unnamed>')!r} ({group}) of Pod {pod.get('metadata', {}).get('name')!r}"
    env = [entry for entry in container.get("env", []) if isinstance(entry, dict)]
    env += list(environment)
    names = sorted(
        entry["name"]
        for entry in env
        if isinstance(entry.get("name"), str)
        and entry["name"].startswith("POSTGRES_PASSWORD")
    )
    data_mounted = any(
        isinstance(mount, dict) and mount.get("mountPath") == POSTGRES_DATA
        for mount in container.get("volumeMounts", [])
    )
    if not names and not data_mounted:
        return None
    if names != ["POSTGRES_PASSWORD_FILE"]:
        raise common.DeployError(
            f"Unsupported PostgreSQL password setting {', '.join(names) or '(none)'} "
            f"in {where}; use only POSTGRES_PASSWORD_FILE with a mounted Secret"
        )
    entry = next(entry for entry in env if entry["name"] == "POSTGRES_PASSWORD_FILE")
    reference = entry.get("value")
    if (
        "valueFrom" in entry
        or not isinstance(reference, str)
        or not Path(reference).is_absolute()
    ):
        raise common.DeployError(f"Invalid POSTGRES_PASSWORD_FILE in {where}")
    password_file = Path(reference)
    mounts = [m for m in container.get("volumeMounts", []) if isinstance(m, dict)]
    data_volume = next(
        (m.get("name") for m in mounts if m.get("mountPath") == POSTGRES_DATA), None
    )
    # The password file is either inside a Secret mounted as its directory
    # (the file name is items[].path), or mounted alone at its own path, as
    # MOUNTS does (subPath names items[].path). Exactly one of the two.
    directory = [m for m in mounts if m.get("mountPath") == str(password_file.parent)]
    single = [m for m in mounts if m.get("mountPath") == str(password_file)]
    secret_volume = item_path = None
    if single:
        secret_volume, item_path = single[0].get("name"), single[0].get("subPath")
    elif directory:
        secret_volume, item_path = directory[0].get("name"), password_file.name
    if (
        len(directory) + len(single) != 1
        or not data_volume
        or not secret_volume
        or not isinstance(item_path, str)
    ):
        raise common.DeployError(
            f"Unsupported PostgreSQL password/data mounts in {where}: mount the "
            f"password Secret either as the directory {password_file.parent} or "
            f"as the single file {password_file} with subPath (MOUNTS does this), "
            f"and a PersistentVolumeClaim at {POSTGRES_DATA}"
        )
    volumes = {
        volume.get("name"): volume
        for volume in spec.get("volumes", [])
        if isinstance(volume, dict)
    }
    try:
        secret = volumes[secret_volume]["secret"]
        claim = volumes[data_volume]["persistentVolumeClaim"]["claimName"]
        keys = [
            item["key"] for item in secret.get("items", []) if item["path"] == item_path
        ]
        if len(keys) != 1 or not isinstance(claim, str):
            raise KeyError("password key")
        return claim, secret["secretName"], keys[0]
    except (KeyError, TypeError, AttributeError):
        raise common.DeployError(
            f"Unsupported PostgreSQL Secret/PVC binding in {where}"
        ) from None


def database_password_path(config, config_path, secret_name, key):
    """Return the one config file that delivers the password key of the Secret."""
    entries = rendering.file_group_sources(config, common.SECRET_FILES).get(
        secret_name, []
    )
    candidates = []
    for entry in entries:
        if "component_file" in entry:
            raise common.DeployError(
                f"{config_path}: database passwords cannot use component_file; provide external/generated credentials"
            )
        source = rendering.resolve_file_source(entry, config_path.parent)
        directory = "generate" in entry or source.is_dir()
        candidates.append(
            source if source.name == key and not directory else source / key
        )
    if len(candidates) != 1:
        raise common.DeployError(
            f"{config_path}: {common.SECRET_FILES}.{secret_name} must identify one password file"
        )
    return candidates[0]


def check_database_password(password):
    """An existing password must be a nonempty single-line regular file."""
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


def check_database_volume_absent(claim, password):
    """Only Podman's documented "absent" answer (exit 1) allows a new password."""
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


def check_dev_shared_settings(component, gateway):
    """Refuse a component's own public settings; they are read from the gateway."""
    path = common.ROOT / "components" / component / "config.defaults.yaml"
    if path.exists() or path.is_symlink():
        local = rendering.config_layer(path)
        for key in catalog.PUBLIC_KEYS:
            if key in local:
                raise common.DeployError(
                    f"{path}: {key} is read from {gateway}'s config; "
                    f"set it there, not in {component}"
                )


def dev_settings():
    """Compile the source catalog and merge dev config for each component.

    Both are in dependency order, so a public_from source is merged before the
    components that take its PUBLIC_ORIGIN and HTTPS_PORT, as init-config does
    in production. Returns (descriptors, settings, env_overrides): the last is
    config/dev.yaml's overrides block (environment.Overrides or None), read
    once and used for the catalog here and for every component's
    ENVIRONMENT by the caller. Nothing is written here.
    """
    local = common.ROOT / "config/dev.yaml"
    env_overrides = environment.read_dev_overrides(local)
    known = catalog.source_descriptors(common.ROOT, env_overrides)
    rendering.dev_file_ids(local, known)
    settings = {}
    for component, descriptor in known.items():
        source = descriptor["public_from"]
        if source:
            check_dev_shared_settings(component, source)
        overrides = (
            catalog.public_settings(
                settings[source], common.BUILD / "dev" / source / "config.yaml"
            )
            if source
            else None
        )
        settings[component] = rendering.component_defaults(
            component, overrides=overrides, dev=True
        )
    return known, settings, env_overrides


def validate_component(
    config,
    config_path,
    manifests,
    component=None,
    imported=(),
    imported_secrets=(),
    env_overrides=None,
):
    """Validate one component's manifests from declarations; no writes or host commands.

    Quadlet templates, kinds, names, placeholders, pull policy, mounts and links
    (effective documents) and the supported PostgreSQL layout. Returns the effective
    documents. Every lifecycle path and ./deploy.sh validate start with this; a
    new declaration check belongs here or in install_checks, so that the
    command and the lifecycle cannot disagree.
    """
    check_quadlet_templates(component)
    documents = rendering.effective_documents(
        config,
        config_path,
        manifests,
        component,
        imported,
        imported_secrets,
        env_overrides,
    )
    database_bindings(config, config_path, documents)
    registrations.check_client_route(manifests.parent)
    return documents


def check_manifests(
    config,
    config_path,
    manifests,
    component=None,
    imported=(),
    imported_secrets=(),
    env_overrides=None,
):
    """Validate the component, then check database volumes; no writes.

    Every path (install, prepare) runs this before generating any
    secret: declarations are validated before any Podman command. Production
    install has already checked the user-manager environment at this point.
    env_overrides (environment.Overrides) is dev's overrides block, or the
    target environment file of --environment (backlog 85); None without
    either. Bundles are environment-neutral, so production passes the
    file's overrides here, as dev passes its block.
    """
    documents = validate_component(
        config,
        config_path,
        manifests,
        component,
        imported,
        imported_secrets,
        env_overrides,
    )
    database_preflight(config, config_path, documents)
    return documents


def check_selected_keys(config, config_path, documents, component=None):
    """Every Secret key a pod selects must be one its sources provide; no file is read.

    Run by validate and by prepare and install before their first write, once
    every credential must be delivered; not by init-config or the dev
    preflight of dev/demo-credentials.sh, which run before credentials exist.
    A MOUNTS secret file is checked first, so its error names the MOUNTS line.
    """
    if component:
        mounts.check_keys(
            component, rendering.secret_keys(config, config_path, documents, component)
        )
    rendering.check_secret_keys(config, config_path, documents, component)


def image_archive():
    """Return the bundle's image archive; checked before any secret is generated."""
    archive = common.ROOT / "images/images.tar"
    if not archive.is_file():
        raise common.DeployError(f"Missing image archive {archive}")
    return archive


def check_dev_components(known, settings, env_overrides):
    """Validate and check every catalog component before any dev write.

    Returns component -> (effective config, effective documents) for rendering.
    """
    checked = {}
    for component, component_settings in settings.items():
        path = common.BUILD / "dev" / component / "config.yaml"
        config = rendering.effective_config(
            component_settings, path, component, env_overrides
        )
        documents = check_manifests(
            config,
            path,
            common.ROOT / "components" / component / "manifests",
            component,
            catalog.imported_volumes(known[component]),
            catalog.imported_secrets(known[component]),
            env_overrides,
        )
        checked[component] = config, documents
    return checked


def prepare_components():
    """Render the catalog components with private dev state and their registrations."""
    state = common.BUILD / "dev"
    known, settings_by_component, env_overrides = dev_settings()
    checked = check_dev_components(known, settings_by_component, env_overrides)
    for component, (config, documents) in checked.items():
        check_selected_keys(
            config, state / component / "config.yaml", documents, component
        )
    for name in catalog.ROLES:
        if (state / name).is_symlink():
            raise common.DeployError(
                f"Refuse symlinked dev registrations: {state / name}"
            )
    with tempfile.TemporaryDirectory(
        prefix=catalog.product_name(common.ROOT) + "-prepare-"
    ) as directory:
        # Validate every registration before the first dev write.
        imports, updates, _ = registrations.registration_stage(
            list(known),
            Path(directory),
            known,
            state=state,
            configs=settings_by_component,
        )
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        for component, settings in settings_by_component.items():
            target = state / component / "config.yaml"
            rendering.write_private(target, yaml.safe_dump(settings, sort_keys=False))
        # Dev registrations come only from the current catalog. Removing older
        # copies keeps a service removed from bundles.yaml out of the proxy and
        # Identity.
        for name in catalog.ROLES:
            shutil.rmtree(str(state / name), ignore_errors=True)
        # Owners render before the APIs they serve, so API secrets come first.
        updates.update(
            registrations.api_updates(
                list(known),
                known,
                imports,
                {
                    component: (config, state / component / "config.yaml")
                    for component, (config, _) in checked.items()
                },
            )
        )
        documents, archives = [], []
        for component, (config, component_documents) in checked.items():
            files = state / component / "files"
            text, volumes = rendering.materialize(
                config,
                state / component / "config.yaml",
                component_documents,
                files,
                registrations.component_imports(component, imports, known),
                component=component,
                extra_secrets=registrations.owner_secrets(component, imports, known),
            )
            documents.extend(yaml.safe_load_all(text))
            archives.append((volumes, files))
        rendering.check_links(documents, {})
        for volumes, files in archives:
            rendering.write_file_archives(volumes, files)
        registrations.write_registrations(updates, state=state)
        rendering.write_private(
            common.BUILD / "install.yaml",
            yaml.safe_dump_all(documents, sort_keys=False),
        )
    log.info(f"[OK] {common.BUILD / 'install.yaml'}")


def prepare():
    """Write validated dev YAML and import archives without running Podman."""
    if not (common.ROOT / "components").is_dir():
        raise common.DeployError(
            "Run prepare from the source checkout; it has components/ and bundles.yaml"
        )
    if (common.ROOT / "bundle.yaml").exists():
        raise common.DeployError(
            "Run prepare from the source checkout; production bundles use persistent config with install"
        )
    prepare_components()


def run(*args):
    """Show and run a command; stop on a failing status."""
    log.debug("+ " + " ".join(map(str, args)))
    subprocess.run(list(map(str, args)), check=True)


def service_identity():
    """Check the account, then select the production paths; reads only.

    Refuses root, a HOME that is not the account's registered home and the
    source checkout. Shared with the explicit init-layout command.
    """
    if os.geteuid() == 0:
        raise common.DeployError("Run install as the service user, not as root")

    configured_home = os.environ.get("HOME")
    if configured_home is not None and Path(configured_home) != common.HOME:
        raise common.DeployError(
            f"HOME={configured_home!r} differs from the home directory {common.HOME} in "
            "the user database. Run install with the service user's HOME"
        )
    if (common.ROOT / "components").is_dir() and not (
        common.ROOT / "bundle.yaml"
    ).is_file():
        # Source dev never reads production bootstrap settings.
        raise common.DeployError(
            "Run production commands from an unpacked component bundle, not the "
            "source checkout"
        )


def service_user():
    """Validate identity, then read the private bootstrap and select paths."""
    service_identity()
    return layout.select(catalog.product_name(common.ROOT))


def init_layout():
    """Create only the runtime account's bootstrap; no systemd or credential reads."""
    service_identity()
    descriptor = bundle_descriptor()
    layout.initialize(descriptor["product"])


def production_environment():
    """Validate the service user, paths and runtime before rendering or commands.

    The user manager check (systemctl --user show-environment) is a read-only
    host query; it confirms services use the same storage as this process.
    """
    root = service_user()
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
    layout.check_user_manager(root)


def bundle_descriptor():
    """Read this unpacked bundle's own validated component descriptor."""
    return catalog.load_bundle_descriptor(common.ROOT)


def check_dependencies_installed(descriptor):
    """Every declared dependency must be installed in a compatible version."""
    for dependency, requirement in descriptor["requires"].items():
        version = catalog.installed_version(common.STATE, dependency)
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
    for name in catalog.dependents(installed, common.STATE, component):
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


def check_not_downgrade(descriptor):
    """Every install renders the component again; only a downgrade is refused."""
    component = descriptor["name"]
    installed = catalog.installed_version(common.STATE, component)
    if installed is None:
        return
    if catalog.version_number(descriptor["version"]) < catalog.version_number(
        installed
    ):
        # The harness parses "<Component> downgrade refused" (acceptance/remote.sh).
        raise common.DeployError(
            f"{component.title()} downgrade refused: requested "
            f"{descriptor['version']}, installed {installed}"
        )


def quadlet_text(suffix, product, name):
    """Render internal names and the release's hosts-policy path; no config values."""
    path = common.QUADLET_TEMPLATE.with_suffix(suffix)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError:
        raise common.DeployError(f"{path}: Quadlet template must be UTF-8") from None
    obsolete = re.search(r"(?<!\$)\{(?:name|product)\}", text)
    if obsolete:
        raise common.DeployError(f"{path}: obsolete Quadlet marker {obsolete[0]}")
    values = {"PRODUCT_NAME": product, "UNIT_NAME": name}

    def resolve(group, field):
        if group is not None:
            raise common.DeployError(
                f"{path}: Secret placeholders are forbidden in Quadlet"
            )
        if field == "PODMAN_HOSTS_CONFIG":
            policy = path.parent / "containers-hosts.conf"
            if policy.is_symlink() or not policy.is_file():
                raise common.DeployError(f"{policy}: missing regular hosts-policy file")
            # Environment= is quoted in the template. Escape its literal path,
            # including systemd specifiers; it follows a relocated bundle.
            value = str(policy.resolve())
            if any(ord(char) < 32 for char in value):
                raise common.DeployError(
                    "Control character in Quadlet hosts-policy path"
                )
            return value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
        if field not in values:
            raise common.DeployError(
                f"{path}: unknown Quadlet token @@{field}@@; "
                "allowed: @@UNIT_NAME@@, @@PRODUCT_NAME@@, @@PODMAN_HOSTS_CONFIG@@"
            )
        return values[field]

    return templates.substitute(text, resolve, str(path))


def check_quadlet_templates(component):
    """Validate both release templates without config, credentials or host queries."""
    product = catalog.product_name(common.ROOT)
    name = catalog.unit_name(component)
    return {
        suffix: quadlet_text(suffix, product, name) for suffix in (".kube", ".network")
    }


def check_same_product(product, installed):
    """One service user runs one product; refuse another before any write."""
    others = sorted({descriptor["product"] for descriptor in installed.values()})
    if others and others != [product]:
        raise common.DeployError(
            "This service user already runs product "
            + ", ".join(others)
            + "; this bundle belongs to "
            + product
            + ". Install each product under its own service user"
        )


def check_shared_network():
    """Validate the shared network before creating secrets or loading images."""
    product = catalog.product_name(common.ROOT)
    network = common.QUADLET_DIR / (product + ".network")
    network_text = quadlet_text(".network", product, product)
    if network.exists() and network.read_text(encoding="utf-8") != network_text:
        raise common.DeployError(
            f"Existing shared network differs from the bundle: {network}"
        )
    return network, network_text


def materialize_component_manifests(checked, imports, known):
    """Render the validated components; missing secrets may be created here.

    Returns component -> (install YAML, import volumes); nothing else is written.
    """
    rendered = {}
    for component, (config, documents) in checked.items():
        config_path, files, _, _ = catalog.component_paths(component)
        rendered[component] = rendering.materialize(
            config,
            config_path,
            documents,
            files,
            registrations.component_imports(component, imports, known),
            component=component,
            extra_secrets=registrations.owner_secrets(component, imports, known),
        )
    return rendered


def load_and_verify_images(archive, rendered):
    """Load this bundle and verify every required image before persistent service changes."""
    run("podman", "load", "-i", archive)
    documents = [
        doc for text, _ in rendered.values() for doc in yaml.safe_load_all(text)
    ]
    for image in rendering.find_images(documents):
        try:
            run("podman", "image", "exists", image)
        except subprocess.CalledProcessError as error:
            raise common.DeployError(
                f"Image {image} is unavailable after load (exit {error.returncode})"
            ) from None


def write_component_units_and_imports(rendered, network, network_text):
    """Write selected imports/YAML/Quadlets, retaining the existing shared network."""
    common.QUADLET_DIR.mkdir(parents=True, exist_ok=True)
    if not network.exists():
        network.write_text(network_text, encoding="utf-8")
        network.chmod(0o644)
    for component, (text, volumes) in rendered.items():
        _, files, output, quadlet = catalog.component_paths(component)
        rendering.write_file_archives(volumes, files)
        rendering.write_private(output, text)
        quadlet.write_text(
            quadlet_text(".kube", catalog.product_name(common.ROOT), output.stem),
            encoding="utf-8",
        )
        quadlet.chmod(0o644)


def write_changed_owner_imports(components, changed, imports, known):
    """Rebuild imports for registration owners outside the selected component."""
    for owner in sorted(changed):
        if owner not in components:
            rendering.write_file_archives(
                registrations.component_imports(owner, imports, known) or {},
                catalog.component_paths(owner)[1],
            )
            replace_owner_secrets(owner, imports, known)


def replace_owner_secrets(owner, imports, known):
    """Rewrite the registration Secret in an installed owner's YAML.

    The owner is not rendered again: only its accepted Secret (accepts.apis)
    is replaced, or added if it is missing; restarting the unit runs kube play
    with the new value. The new YAML is published atomically
    (write_install_record), so an interruption leaves the old file and the
    pending record repeats this step.
    """
    secrets = registrations.owner_secrets(owner, imports, known)
    if not secrets:
        return
    output = catalog.component_paths(owner)[2]
    name = secrets[0]["metadata"]["name"]
    try:
        documents = [doc for doc in rendering.load_yaml_all(output) if doc is not None]
        rendering.check_component_names(documents, owner, output)
    except (OSError, yaml.YAMLError, common.DeployError):
        raise common.DeployError(
            f"Cannot read the installed YAML of {owner} ({output}) to update its "
            f"registration Secret {name}. Restore that file from backup, then run "
            "./deploy.sh install from this bundle again to finish the pending install"
        ) from None
    positions = [
        position
        for position, doc in enumerate(documents)
        if doc["kind"] == "Secret" and doc["metadata"]["name"] == name
    ]
    if len(positions) > 1:
        raise common.DeployError(f"{output} defines Secret {name} more than once")
    if positions:
        documents[positions[0]] = secrets[0]
    else:
        documents.insert(0, secrets[0])
    write_install_record(output, yaml.safe_dump_all(documents, sort_keys=False))


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
        restart_service(component)
        if pending and component in pending["owners"]:
            registrations.acknowledge_owner(pending, component)


def restart_service(component):
    """Restart one component's unit and require it active with healthy containers."""
    service = catalog.unit_name(component) + ".service"
    run("systemctl", "--user", "restart", service)
    run("systemctl", "--user", "is-active", "--quiet", service)
    health.wait_healthy(service, catalog.component_paths(component)[2])


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
        catalog.metadata_path(common.STATE, descriptor["name"]),
        json.dumps(descriptor, sort_keys=True) + "\n",
    )


def environment_effect(descriptor, env_overrides, known):
    """What an install applies from the environment, beyond the release itself.

    The environment file's entry for this component ({} without one), and
    for an API the secret line of the installed Identity that names it
    (api_secrets: index and "<secret id>/<key>"), whose value this
    component's install delivers to Identity. known holds the installed
    descriptors (and this one).
    """
    name, identity = descriptor["name"], descriptor["identity"]
    owner = known.get(identity) if identity not in (None, name) else None
    return {
        "overrides": (env_overrides.components.get(name) or {})
        if env_overrides is not None
        else {},
        "api_secret": owner["api_secrets"].get(name) if owner else None,
    }


def write_installed_marker(descriptor, effect, environment_name=None):
    """Publish the completed version before acknowledging the install attempt.

    effect (environment_effect) and the environment's name (None without
    one) are recorded just before it (catalog.environment_record_path). An
    earlier uninstall record goes with it: the component is installed again.
    """
    write_install_record(
        catalog.environment_record_path(common.STATE, descriptor["name"]),
        json.dumps(dict(effect, environment=environment_name), sort_keys=True) + "\n",
    )
    write_install_record(
        common.STATE / "installed" / descriptor["name"], descriptor["version"] + "\n"
    )
    record = catalog.uninstalled_path(common.STATE, descriptor["name"])
    if record.is_file():
        record.unlink()


def install_preconditions(checked):
    """Install's checks after the manifests and before generation; read-only.

    The shared network matches the bundle, the image archive exists and every
    image of the rendered component is fully qualified. ./deploy.sh validate
    runs this too.
    """
    network, network_text = check_shared_network()
    archive = image_archive()
    rendering.find_images([doc for _, docs in checked.values() for doc in docs])
    return network, network_text, archive


def install_component_plan(
    descriptor,
    checked,
    known,
    imports,
    updates,
    removals,
    env_overrides=None,
    environment_name=None,
):
    """Apply a staged install in the established validation/write/restart order."""
    name = descriptor["name"]
    components = list(checked)
    owners = catalog.role_owners(known, "registration owners")
    network, network_text, archive = install_preconditions(checked)
    rendered = materialize_component_manifests(checked, imports, known)
    updates = dict(updates)
    updates.update(
        registrations.api_updates(
            [name],
            known,
            imports,
            {
                component: (config, catalog.component_paths(component)[0])
                for component, (config, _) in checked.items()
            },
        )
    )
    load_and_verify_images(archive, rendered)
    registrations.begin_install(name, descriptor["product"], descriptor["version"])
    write_installed_metadata(descriptor)
    changed, pending = registrations.apply_registration_updates(
        name, descriptor["product"], descriptor["version"], updates, removals, owners
    )
    write_component_units_and_imports(rendered, network, network_text)
    write_changed_owner_imports(components, changed, imports, known)
    restart_component_services(components, changed, pending, known)
    write_installed_marker(
        descriptor,
        environment_effect(descriptor, env_overrides, known),
        environment_name,
    )
    registrations.clear_pending()
    run("podman", "ps", "--all", "--pod")


def install_checks(env_overrides=None):
    """Decide everything install needs before staging; no writes, no host commands.

    The bundle descriptor in the target environment (environment_descriptor;
    the bundle's own without one), the installed set with this descriptor (ID
    prefixes, role owners, pending owner work), dependency and dependent
    ranges, and the persistent config with the gateway's public settings.
    Returns (descriptor, known, config, config_path). ./deploy.sh validate
    runs this too.
    """
    installed = catalog.load_installed_metadata(common.STATE)
    descriptor = catalog.environment_descriptor(
        bundle_descriptor(), env_overrides, installed
    )
    name = descriptor["name"]
    check_quadlet_templates(name)
    pending = registrations.check_pending("install", name, descriptor["product"])
    check_same_product(descriptor["product"], installed)
    known = dict(installed)
    known[name] = descriptor
    catalog.check_id_prefixes(known, "installed components and this bundle")
    # An Identity release without an installed API's line is refused first,
    # with the uninstall it needs (the owner check would only say "does not
    # accept apis").
    check_api_secret_lines(descriptor, installed)
    # An incoming descriptor must not take over a role another component serves.
    catalog.check_owners(known, "installed components and this bundle")
    # Unfinished owner work stays valid even if this release drops the role,
    # as long as the owner still serves that role among the known components.
    owners = catalog.role_owners(known, "installed components and this bundle")
    unknown = set(pending["owners"] if pending else []) - set(owners.values())
    if unknown:
        raise common.DeployError(
            "Pending owner work for "
            + ", ".join(sorted(unknown))
            + ", which no installed component serves; no changes made"
        )
    check_dependencies_installed(descriptor)
    check_dependents(descriptor, installed)
    config_path = catalog.component_paths(name)[0]
    if not config_path.is_file():
        raise common.DeployError(
            f"Missing {config_path}; run ./deploy.sh init-config {name} first"
        )
    config, from_release = catalog.operator_config(descriptor, config_path)
    if from_release:
        log.info(
            f"[OK] {name}: from the release defaults (not in {config_path}): "
            + ", ".join(from_release)
        )
    check_not_downgrade(descriptor)
    rendering.validate_component_config(config, name, config_path)
    return descriptor, known, config, config_path


def install_components(environment_name=None):
    """Validate the bundle, installed state and config before writing anything.

    Order: service_user selects paths, an install without an environment is
    refused for a component its environment changed
    (check_installed_without_environment), the target environment file is
    read (target_environment), install_checks validates declarations (including
    both Quadlet templates), production_environment checks runtime and the
    user manager, then temporary registration staging, manifests and
    database preflight, and install_component_plan.
    """
    # Pure declaration checks precede even the user-manager host query.
    service_user()
    product, name = bundle_descriptor()["product"], bundle_descriptor()["name"]
    if environment_name is None:
        check_installed_without_environment(product, name)
    env_overrides = target_environment(environment_name, name)
    descriptor, known, config, config_path = install_checks(env_overrides)
    production_environment()
    name = descriptor["name"]
    with tempfile.TemporaryDirectory(
        prefix=descriptor["product"] + "-install-", dir=os.environ["XDG_RUNTIME_DIR"]
    ) as directory:
        # Staging only reads and validates registrations; it writes nothing
        # outside the temporary directory and precedes workload host commands.
        imports, updates, removals = registrations.registration_stage(
            [name], Path(directory), known
        )
        effective = rendering.effective_config(config, config_path, name, env_overrides)
        checked = {
            name: (
                effective,
                check_manifests(
                    effective,
                    config_path,
                    common.ROOT / "components" / name / "manifests",
                    name,
                    catalog.imported_volumes(descriptor),
                    catalog.imported_secrets(descriptor),
                    env_overrides,
                ),
            )
        }
        check_selected_keys(effective, config_path, checked[name][1], name)
        install_component_plan(
            descriptor,
            checked,
            known,
            imports,
            updates,
            removals,
            env_overrides,
            environment_name,
        )


def install(environment_name=None):
    """Install the component of this unpacked bundle, in a target environment or not."""
    if not (common.ROOT / "bundle.yaml").exists():
        raise common.DeployError(
            "Run install from an unpacked component bundle, not the source checkout"
        )
    install_components(environment_name)


def target_environment(environment_name, component):
    """The Overrides of state/<environment>.yaml, or None without an environment.

    Read again by every command that needs it, so install, validate,
    init-config and a retry all use the file as it is now; nothing about the
    selection is remembered (backlog 85). The component must be listed.
    """
    if environment_name is None:
        return None
    env_overrides = environment.read_environment_file(common.STATE, environment_name)
    if component not in env_overrides.selected:
        raise common.DeployError(
            f"{env_overrides.path}: {component} is not in components:; add it there "
            f"to deploy it in this environment"
        )
    return env_overrides


def recorded_environment(name):
    """The environment of name's last install, when that install applied anything from it.

    Read from the record write_installed_marker wrote; None without one, or
    when the environment gave the component no overrides and no API secret
    line (then an install without it changes nothing it applied).
    """
    record = catalog.environment_record_path(common.STATE, name)
    if record.is_symlink():
        raise common.DeployError(f"Refuse symlinked environment record {record}")
    if not record.is_file():
        return None
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
        environment_name = data["environment"]
        applied = data["overrides"] or data["api_secret"]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        raise common.DeployError(f"Invalid environment record {record}") from None
    return environment_name if environment_name and applied else None


def check_installed_without_environment(product, name):
    """Product owner, 2026-11-10 (backlog 85): an environment is not dropped silently.

    An install without --environment of a component whose last install got
    overrides or an API secret line from an environment would remove them
    (an API would lose its registration with Identity). Refused before any
    change, naming the command to use.
    """
    environment_name = recorded_environment(name)
    if environment_name:
        raise common.DeployError(
            f"{name} was installed with --environment {environment_name}, which "
            "gave it overrides or an API secret line; an install without it would "
            f"remove them. Run {product} --environment {environment_name} (or "
            f"./deploy.sh install --environment {environment_name}); nothing was "
            "changed"
        )


def environment_applied(descriptor, env_overrides, installed):
    """Whether the completed install of this release has this environment's effect.

    The same version, the same descriptor in the environment (its API roles)
    and the same recorded environment_effect (its overrides, and the secret
    line Identity uses for it); anything else needs an install.
    """
    name = descriptor["name"]
    record = catalog.environment_record_path(common.STATE, name)
    if (
        catalog.installed_version(common.STATE, name) != descriptor["version"]
        or installed.get(name) != descriptor
        or record.is_symlink()
        or not record.is_file()
    ):
        return False
    try:
        applied = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return False
    if not isinstance(applied, dict):
        return False
    applied.pop("environment", None)  # Another file with the same effect is applied.
    current = environment_effect(descriptor, env_overrides, installed)
    return applied == json.loads(json.dumps(current))


def check_environment(environment_name, json_output=False):
    """deploy.sh check-environment <name>: this release in the environment; no writes.

    What the declarations decide without config or credentials, so the
    runtime command can check every selected release before it changes
    anything: the file (environment.read_environment_file), the merged
    ENVIRONMENT (names, placeholder syntax, SECRET_FILES declarations and
    generated Secret names, client settings, the containers of the
    manifests), the descriptor in the environment (environment_descriptor:
    Identity's API secret lines against the listed components, no other
    component naming a foreign secret, every dependency listed, also
    Identity for an API the installed Identity registers), and for any other
    component the declaration of a secret Identity's overrides name. A
    container name written as a @@NAME@@ setting is known only with
    settings; its checks are left to install. Install repeats all of this
    with the operator's config (install_checks, effective_documents).

    Needs no bootstrap file and no config. With --json it prints
    {"applied": ..., "component": ...}: whether the completed install already
    has this environment's effect (environment_applied), so the runtime
    command can leave it as it is.
    """
    service_identity()
    descriptor = bundle_descriptor()
    # No bootstrap needed: the runtime command checks before init-layout.
    layout.select_state(descriptor["product"])
    name = descriptor["name"]
    env_overrides = target_environment(environment_name, name)
    if env_overrides is None:
        raise common.DeployError("check-environment needs an environment name")
    directory = common.ROOT / "components" / name
    defaults = catalog.release_defaults(name)
    templates.declarations(environment.with_recipes(defaults, name, env_overrides))
    client = rendering.with_client_settings({}, name)
    documents = [
        document
        for path in sorted((directory / "manifests").glob("*.yaml"))
        for document in rendering.load_manifest(path)
    ]
    containers = rendering.named_containers(documents)
    literal = not any("@@" in str(container) for container in containers)
    merged = environment.read(name, env_overrides)
    for container in environment.overridden_containers(name, env_overrides):
        if literal or (container not in merged and container not in containers):
            environment.check_exists(name, container, containers, env_overrides)
    for container, values in merged.items():
        environment.check_client_settings(
            name, container, values, client, env_overrides
        )
        if literal:
            environment.check_container(
                name, container, values, containers, env_overrides
            )
    identity = descriptor["identity"]
    installed = catalog.load_installed_metadata(common.STATE)
    # The API roles, the dependencies in the environment and the rule that
    # only Identity names another component's secret.
    effective = catalog.environment_descriptor(descriptor, env_overrides, installed)
    if name != identity and identity is not None:
        declared = defaults.get(common.SECRET_FILES) or {}
        for values in (env_overrides.components.get(identity) or {}).values():
            for value in values.values():
                for secret in environment.secret_ids(value):
                    if secret.startswith(name + "-") and secret not in declared:
                        raise common.DeployError(
                            f"{env_overrides.path}: overrides.{identity} names "
                            f"{secret}, which {name} does not declare in SECRET_FILES"
                        )
    if json_output:
        applied = environment_applied(effective, env_overrides, installed)
        print(json.dumps({"applied": applied, "component": name}, sort_keys=True))
    else:
        log.info(f"[OK] {name} fits environment {environment_name}")


def uninstall_plan(component, delete_data, installed, product):
    """Validate installed state and return the uninstall record; changes nothing.

    The volumes come from the installed YAML (Secrets, PVCs and mounted
    ConfigMaps, all prefixed with the component ID); the owners are those
    whose registration of this component must be rebuilt after removal.
    """
    _, _, output, _ = catalog.component_paths(component)
    route = common.STATE / "routes" / (component + ".conf")
    client = common.STATE / "clients" / component
    api = common.STATE / "apis" / component
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
    for _, spec in rendering.pod_specs(documents, output):
        for volume in spec.get("volumes", []):
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
        prefix=catalog.product_name(common.ROOT) + "-remove-",
        dir=os.environ["XDG_RUNTIME_DIR"],
    ) as directory:
        registrations.registration_stage([], Path(directory), installed)
    role_owners = catalog.role_owners(installed, "installed components")
    owners = set()
    if route.is_file():
        owners.add(role_owners["routes"])
    if client.exists():
        owners.add(role_owners["clients"])
    if api.exists():
        owners.add(role_owners["apis"])
    return {
        "operation": "uninstall",
        "component": component,
        "product": product,
        "delete_data": delete_data,
        "volumes": volumes,
        "stopped": False,
        "owners": sorted(
            owner
            for owner in owners
            if owner not in (None, component)
            and catalog.installed_version(common.STATE, owner)
        ),
    }


def uninstall(component=None, delete_data=False):
    """Resume one scoped uninstall from validated metadata, even after removing its YAML.

    Returns the installed version that was removed, which can differ from this
    bundle's version (the journal records both).
    """
    production_environment()
    descriptor = bundle_descriptor()
    own = descriptor["name"]
    component = component or own
    if component != own:
        raise common.DeployError("This bundle can only uninstall its own component")
    state = registrations.check_pending(
        "uninstall", component, descriptor["product"], delete_data
    )
    marker = common.STATE / "installed" / component
    if state is None and not marker.is_file():
        if catalog.metadata_path(common.STATE, component).is_file():
            # Metadata is written before the units and the marker last, so this
            # is a first install that stopped. Finishing it is the one recovery.
            raise common.DeployError(
                f"Component {component} has an unfinished first install "
                f"(metadata without installed/{component}). Run ./deploy.sh install "
                "from its bundle again to finish it, then uninstall; if that "
                "install keeps failing, fix the cause it reports first"
            )
        raise common.DeployError(f"Component {component} is not installed")
    installed = catalog.load_installed_metadata(common.STATE)
    check_same_product(descriptor["product"], installed)
    dependents = catalog.dependents(installed, common.STATE, component)
    if dependents:
        raise common.DeployError(
            component.title() + " is still required by: " + ", ".join(dependents)
        )
    _, _, output, quadlet = catalog.component_paths(component)
    route = common.STATE / "routes" / (component + ".conf")
    client = common.STATE / "clients" / component
    api = common.STATE / "apis" / component
    for path in (
        output,
        quadlet,
        route,
        client,
        api,
        marker,
        catalog.metadata_path(common.STATE, component),
        catalog.environment_record_path(common.STATE, component),
        catalog.uninstalled_path(common.STATE, component),
    ):
        if any(parent.is_symlink() for parent in [path] + list(path.parents)):
            raise common.DeployError("Refuse symlinked uninstall state or output paths")
    if state is None:
        state = uninstall_plan(component, delete_data, installed, descriptor["product"])
        registrations.save_pending(state)
    if not state["stopped"]:
        run("systemctl", "--user", "stop", catalog.unit_name(component) + ".service")
        state["stopped"] = True
        registrations.save_pending(state)
    for path in (output, quadlet, route):
        if path.exists():
            path.unlink()
    for directory in (client, api):
        if directory.exists():
            shutil.rmtree(directory)
    run("systemctl", "--user", "daemon-reload")
    if state["owners"]:
        with tempfile.TemporaryDirectory(
            prefix=catalog.product_name(common.ROOT) + "-remove-",
            dir=os.environ["XDG_RUNTIME_DIR"],
        ) as directory:
            imports, _, _ = registrations.registration_stage(
                [], Path(directory), installed
            )
            for owner in list(state["owners"]):
                catalog.component_paths(owner)
                if owner not in installed or not catalog.installed_version(
                    common.STATE, owner
                ):
                    raise common.DeployError(
                        "Pending registration owner is not installed: " + owner
                    )
            for owner in restart_order(installed, state["owners"]):
                rendering.write_file_archives(
                    registrations.component_imports(owner, imports, installed) or {},
                    catalog.component_paths(owner)[1],
                )
                replace_owner_secrets(owner, imports, installed)
                restart_service(owner)
                registrations.acknowledge_owner(state, owner)
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
        if (common.STATE / component).exists():
            shutil.rmtree(common.STATE / component)
    removed = catalog.installed_version(common.STATE, component)
    # Before the marker goes: the runtime command must not install the
    # component again (backlog 85). A retry finds the pending record; once
    # the marker is gone it keeps the record written with the version.
    record = catalog.uninstalled_path(common.STATE, component)
    if removed is not None or not record.is_file():
        write_install_record(record, (removed or "") + "\n")
    # Marker first: metadata without a marker is an unfinished install, never the reverse.
    for path in (
        marker,
        catalog.metadata_path(common.STATE, component),
        catalog.environment_record_path(common.STATE, component),
    ):
        if path.exists():
            path.unlink()
    registrations.clear_pending()
    log.info(
        f"[OK] Uninstalled {component}; shared network retained; data {'deleted' if delete_data else 'preserved'}"
    )
    return removed
