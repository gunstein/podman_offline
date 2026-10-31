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

from . import catalog, common, health, layout, registrations, templates
from . import render as rendering
from .output import log


def init_config(component):
    """Exclusively materialize one bundled config; never create private input files."""
    production_environment()
    descriptor = bundle_descriptor()
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
        log.info(
            f"[OK] Existing config retained unchanged: {target}; install validates it"
        )
        return
    # The gateway's public settings complete the defaults for validation only;
    # they stay in the gateway's config.yaml, which install reads again.
    public = catalog.gateway_settings(descriptor["public_from"])
    config = rendering.component_defaults(component, overrides=public)
    config = {key: value for key, value in config.items() if key not in public}
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.parent.chmod(0o700)
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        yaml.safe_dump(config, stream, sort_keys=False)
    log.info(
        f"[OK] Initialized {target}; edit config and prepare credentials before install"
    )


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
            binding = postgres_binding(pod, spec, group, container)
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


def postgres_binding(pod, spec, group, container):
    """Return (data claim, password Secret, Secret key) or None for a non-database container.

    A container is a database container when it sets any POSTGRES_PASSWORD*
    variable or mounts the PostgreSQL data directory. Only the
    POSTGRES_PASSWORD_FILE layout with a mounted Secret and a PVC at the data
    directory is supported; anything else (another password form, envFrom, no
    password setting) is refused so a lost password can never be replaced
    silently (item 7).
    """
    where = f"container {container.get('name', '<unnamed>')!r} ({group}) of Pod {pod.get('metadata', {}).get('name')!r}"
    env = [entry for entry in container.get("env", []) if isinstance(entry, dict)]
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
    mounts = {
        mount.get("mountPath"): mount.get("name")
        for mount in container.get("volumeMounts", [])
        if isinstance(mount, dict)
    }
    secret_volume = mounts.get(str(password_file.parent))
    data_volume = mounts.get(POSTGRES_DATA)
    if not secret_volume or not data_volume:
        raise common.DeployError(
            f"Unsupported PostgreSQL password/data mounts in {where}"
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
            item["key"]
            for item in secret.get("items", [])
            if item["path"] == password_file.name
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
    for name in ("config.defaults.yaml", "config.dev.yaml"):
        path = common.ROOT / "components" / component / name
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
    in production. Nothing is written here.
    """
    known = catalog.source_descriptors(common.ROOT)
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
    return known, settings


def validate_component(
    config, config_path, manifests, component=None, imported=(), imported_secrets=()
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
        config, config_path, manifests, component, imported, imported_secrets
    )
    database_bindings(config, config_path, documents)
    registrations.check_client_identity(manifests.parent, documents)
    return documents


def check_manifests(
    config, config_path, manifests, component=None, imported=(), imported_secrets=()
):
    """Validate the component, then check database volumes; no writes.

    Every path (install, prepare, standalone) runs this before generating any
    secret: declarations are validated before any Podman command. Production
    install has already checked the user-manager environment at this point.
    """
    documents = validate_component(
        config, config_path, manifests, component, imported, imported_secrets
    )
    database_preflight(config, config_path, documents)
    return documents


def image_archive():
    """Return the bundle's image archive; checked before any secret is generated."""
    archive = common.ROOT / "images/images.tar"
    if not archive.is_file():
        raise common.DeployError(f"Missing image archive {archive}")
    return archive


def check_dev_components(known, settings):
    """Validate and check every catalog component before any dev write.

    Returns component -> (effective config, effective documents) for rendering.
    """
    checked = {}
    for component, component_settings in settings.items():
        path = common.BUILD / "dev" / component / "config.yaml"
        config = rendering.effective_config(component_settings, path, component)
        documents = check_manifests(
            config,
            path,
            common.ROOT / "components" / component / "manifests",
            component,
            catalog.imported_volumes(known[component]),
            catalog.imported_secrets(known[component]),
        )
        checked[component] = config, documents
    return checked


def prepare_components():
    """Render the catalog components with private dev state and their registrations."""
    state = common.BUILD / "dev"
    known, settings_by_component = dev_settings()
    checked = check_dev_components(known, settings_by_component)
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
    if not common.CONFIG.exists():
        raise common.DeployError(f"Missing {common.CONFIG}")
    config = rendering.load_config(common.CONFIG)
    documents = check_manifests(config, common.CONFIG, common.MANIFESTS)
    files = common.BUILD / "files"
    text, volumes = rendering.materialize(config, common.CONFIG, documents, files)
    rendering.write_file_archives(volumes, files)
    rendering.write_private(output, text)
    log.info(f"[OK] {output}")


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


def install_standalone():
    """Install a release without components/: one manifests/ folder, one service.

    install() calls this for a release that has neither bundle.yaml nor
    components/, such as a fixture under examples/ (examples/VM-CHECKLIST.md).
    It reads config.yaml in the state directory (common.STATE) and the
    release's manifests/ and images/images.tar, in this order:

    1. service_user() selects installation paths, check_quadlet_templates()
       validates both templates, then production_environment() checks runtime
       and the user manager. STATE/config.yaml must exist.
    2. check_manifests(): kinds, placeholders, pull policy, mounts and links
       of the effective manifests, then the database preflight; images.tar
       must exist and every container needs a fully qualified image.
    3. rendering.materialize(): may generate allowed missing secrets and
       renders the YAML once; no other files are written yet.
    4. podman load of images.tar, then podman image exists for every image.
    5. Only then the import archives in files/, so a failed image check never
       leaves new imports beside the old YAML.
    6. The Quadlet .yaml, .kube and .network, then daemon-reload, restart and
       is-active for the single service, and podman ps.

    It uses no catalog, metadata, registrations, pending record or markers.
    It raises DeployError for a missing config, invalid manifests, a database
    preflight finding, a missing images.tar or an image the archive did not
    provide; a failing systemctl or podman command raises CalledProcessError.
    """
    service_user()
    quadlets = check_quadlet_templates()
    production_environment()
    config_path = common.STATE / "config.yaml"
    if not config_path.exists():
        raise common.DeployError(f"Missing {config_path}")
    config = rendering.load_config(config_path)
    documents = check_manifests(config, config_path, common.MANIFESTS)
    archive = image_archive()
    rendering.find_images(documents)
    text, volumes = rendering.materialize(
        config, config_path, documents, common.FILES_DIR
    )
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
    rendering.write_file_archives(volumes, common.FILES_DIR)

    common.QUADLET_DIR.mkdir(parents=True, exist_ok=True)
    rendering.write_private(common.QUADLET_YAML, text)
    for suffix in (".kube", ".network"):
        target = common.QUADLET_TARGET.with_suffix(suffix)
        target.write_text(
            quadlets[suffix],
            encoding="utf-8",
        )
        target.chmod(0o644)

    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "restart", common.SERVICE)
    run("systemctl", "--user", "is-active", "--quiet", common.SERVICE)
    health.wait_healthy(common.SERVICE, common.QUADLET_YAML)
    run("podman", "ps", "--all", "--pod")

    log.info(
        f"[OK] {common.SERVICE} is running. Check that the containers above are 'Up'."
    )


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


def check_quadlet_templates(component=None):
    """Validate both release templates without config, credentials or host queries."""
    product = catalog.product_name(common.ROOT)
    name = catalog.unit_name(component) if component is not None else product
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


def load_and_verify_images(archive, components, source_components, rendered):
    """Load this bundle and verify every required image before persistent service changes."""
    run("podman", "load", "-i", archive)
    documents = [
        doc for text, _ in rendered.values() for doc in yaml.safe_load_all(text)
    ]
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


def write_installed_marker(descriptor):
    """Publish the completed version before acknowledging the install attempt."""
    write_install_record(
        common.STATE / "installed" / descriptor["name"], descriptor["version"] + "\n"
    )


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


def install_component_plan(descriptor, checked, known, imports, updates, removals):
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
    load_and_verify_images(archive, components, [name], rendered)
    registrations.begin_install(name, descriptor["product"], descriptor["version"])
    write_installed_metadata(descriptor)
    changed, pending = registrations.apply_registration_updates(
        name, descriptor["product"], descriptor["version"], updates, removals, owners
    )
    write_component_units_and_imports(rendered, network, network_text)
    write_changed_owner_imports(components, changed, imports, known)
    restart_component_services(components, changed, pending, known)
    write_installed_marker(descriptor)
    registrations.clear_pending()
    run("podman", "ps", "--all", "--pod")


def install_checks():
    """Decide everything install needs before staging; no writes, no host commands.

    The bundle descriptor, the installed set with this descriptor (ID prefixes,
    role owners, pending owner work), dependency and dependent ranges, and the
    persistent config with the gateway's public settings. Returns (descriptor,
    known, config, config_path). ./deploy.sh validate runs this too.
    """
    descriptor = bundle_descriptor()
    name = descriptor["name"]
    check_quadlet_templates(name)
    pending = registrations.check_pending("install", name, descriptor["product"])
    installed = catalog.load_installed_metadata(common.STATE)
    check_same_product(descriptor["product"], installed)
    known = dict(installed)
    known[name] = descriptor
    catalog.check_id_prefixes(known, "installed components and this bundle")
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
    check_api_secret_lines(descriptor, installed)
    rendering.validate_component_config(config, name, config_path)
    return descriptor, known, config, config_path


def install_components():
    """Validate the bundle, installed state and config before writing anything.

    Order: service_user selects paths, install_checks validates declarations
    (including both Quadlet templates), production_environment checks runtime
    and the user manager, then temporary registration staging, manifests and
    database preflight, and install_component_plan.
    """
    # Pure declaration checks precede even the user-manager host query.
    service_user()
    descriptor, known, config, config_path = install_checks()
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
        effective = rendering.effective_config(config, config_path, name)
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
                ),
            )
        }
        install_component_plan(descriptor, checked, known, imports, updates, removals)


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
    # Marker first: metadata without a marker is an unfinished install, never the reverse.
    for path in (marker, catalog.metadata_path(common.STATE, component)):
        if path.exists():
            path.unlink()
    registrations.clear_pending()
    log.info(
        f"[OK] Uninstalled {component}; shared network retained; data {'deleted' if delete_data else 'preserved'}"
    )
    return removed
