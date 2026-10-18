"""Component preparation and the rootless install/uninstall lifecycle.

Registrations and the pending-operation record live in registrations.py.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from . import catalog, common, health, registrations
from . import render as rendering


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
        source_path = catalog.component_paths(source)[0]
        if not source_path.exists():
            raise common.DeployError(
                f"Missing {source_path}; restore installed {source} config before initializing {component}"
            )
        owner = catalog.load_installed_metadata(common.HOME)[source]
        overrides = public_settings(
            rendering.load_config(source_path), source_path, shared_keys(owner)
        )
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


# Always shared with public_from dependents, with extra validation. Other names
# are shared only when the owner lists them in shares (bundles.yaml). Reserved
# names: docs/COMPONENTS.md, "Reserved configuration names".
PUBLIC_KEYS = ("PUBLIC_ORIGIN", "HTTPS_PORT")


def shared_keys(owner):
    """The config names an owner's public_from dependents take from it."""
    return PUBLIC_KEYS + tuple(key for key in owner["shares"] if key not in PUBLIC_KEYS)


def public_settings(config, path, keys=PUBLIC_KEYS):
    """Return the validated shared settings of one config (origin, port, shares)."""
    for key in keys:
        if key not in config:
            raise common.DeployError(
                f"Missing {key} in {path}; add it explicitly before installation"
            )
    rendering.public_origin(config["PUBLIC_ORIGIN"], path)
    return {key: config[key] for key in keys}


def check_public_settings(descriptor, config, path, known):
    """A component declaring public_from must use that dependency's shared settings.

    known holds the owner's descriptor (installed metadata, or this bundle).
    Errors name the setting, both files and the owner, never the values.
    """
    source = descriptor["public_from"]
    if source is None:
        return
    keys = shared_keys(known[source])
    source_path = catalog.component_paths(source)[0]
    expected = public_settings(rendering.load_config(source_path), source_path, keys)
    actual = public_settings(config, path, keys)
    for key in keys:
        if actual[key] != expected[key]:
            raise common.DeployError(
                f"{key} in {path} must match {source_path} ({source} shares it)"
            )


def check_own_shares(descriptor, config, path):
    """An owner's own config must define every name it shares."""
    for key in descriptor["shares"]:
        if key not in config:
            raise common.DeployError(
                f"Missing {key} in {path}; {descriptor['name']} shares it "
                "(shares in bundles.yaml)"
            )


def check_kept_shares(descriptor, installed):
    """An owner upgrade must keep every name its installed dependents take from it."""
    name = descriptor["name"]
    if name not in installed:
        return
    dropped = set(installed[name]["shares"]) - set(descriptor["shares"])
    dependents = sorted(
        other for other, entry in installed.items() if entry["public_from"] == name
    )
    if dropped and dependents:
        raise common.DeployError(
            f"{name} no longer shares {', '.join(sorted(dropped))}, which installed "
            f"{', '.join(dependents)} take from it (public_from); keep it in "
            f"{name}'s shares until they no longer use it"
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
        source = rendering.resolve_path(entry["path"], config_path.parent)
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
                settings[source],
                common.BUILD / "dev" / source / "config.yaml",
                shared_keys(known[source]),
            )
            if source
            else None
        )
        settings[component] = rendering.component_defaults(
            component, overrides=overrides, dev=True
        )
    return known, settings


def validate_component(config, config_path, manifests, component=None, imported=()):
    """Validate one component's manifests from declarations; no writes or host commands.

    Kinds, names, placeholders, pull policy, mounts and links (effective
    documents) and the supported PostgreSQL layout. Returns the effective
    documents. Every lifecycle path and ./deploy validate start with this; a
    new declaration check belongs here or in install_checks, so that the
    command and the lifecycle cannot disagree.
    """
    documents = rendering.effective_documents(
        config, config_path, manifests, component, imported
    )
    database_bindings(config, config_path, documents)
    registrations.check_client_identity(manifests.parent, documents)
    return documents


def check_manifests(config, config_path, manifests, component=None, imported=()):
    """Validate the component, then check database volumes; no writes.

    Every path (install, prepare, standalone) runs this before generating any
    secret: declarations are validated first, so a broken manifest never
    reaches a host command, and the preflight is the first host command.
    """
    documents = validate_component(config, config_path, manifests, component, imported)
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
            known[component]["accepts"].values(),
        )
        checked[component] = config, documents
    return checked


def prepare_components():
    """Render the catalog components with private dev state and their registrations."""
    state = common.BUILD / "dev"
    known, settings_by_component = dev_settings()
    checked = check_dev_components(known, settings_by_component)
    for name in catalog.ROLE_FILES:
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
            home=state,
            configs=settings_by_component,
        )
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        for component, settings in settings_by_component.items():
            target = state / component / "config.yaml"
            rendering.write_private(target, yaml.safe_dump(settings, sort_keys=False))
        # Dev registrations come only from the current catalog. Removing older
        # copies keeps a service removed from bundles.yaml out of the proxy and
        # Identity.
        for name in catalog.ROLE_FILES:
            shutil.rmtree(str(state / name), ignore_errors=True)
        documents, archives = [], []
        for component, (config, component_documents) in checked.items():
            files = state / component / "files"
            text, volumes = rendering.materialize(
                config,
                state / component / "config.yaml",
                component_documents,
                files,
                registrations.component_imports(component, imports, known),
            )
            documents.extend(yaml.safe_load_all(text))
            archives.append((volumes, files))
        rendering.check_links(documents, {})
        for volumes, files in archives:
            rendering.write_file_archives(volumes, files)
        registrations.write_registrations(updates, home=state)
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
    if not common.CONFIG.exists():
        raise common.DeployError(f"Missing {common.CONFIG}")
    config = rendering.load_config(common.CONFIG)
    documents = check_manifests(config, common.CONFIG, common.MANIFESTS)
    files = common.BUILD / "files"
    text, volumes = rendering.materialize(config, common.CONFIG, documents, files)
    rendering.write_file_archives(volumes, files)
    rendering.write_private(output, text)
    print(f"[OK] {output}")


def run(*args):
    """Show and run a command; stop on a failing status."""
    print("+", " ".join(map(str, args)))
    subprocess.run(list(map(str, args)), check=True)


def service_user():
    """Refuse root and a HOME that is not the service user's; reads only."""
    if os.geteuid() == 0:
        raise common.DeployError("Run install as the service user, not as root")

    configured_home = os.environ.get("HOME")
    if configured_home is not None and Path(configured_home) != common.HOME:
        raise common.DeployError(
            f"HOME={configured_home!r} differs from the home directory {common.HOME} in "
            "the user database. Run install with the service user's HOME"
        )


def production_environment():
    """Validate the service user and set its runtime before rendering or commands."""
    service_user()
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
    """Install a release without components/: one manifests/ folder, one service.

    install() calls this for a release that has neither bundle.yaml nor
    components/, such as a fixture under examples/ (examples/VM-CHECKLIST.md).
    It reads the service user's ~/config.yaml (not ~/.config/...) and the
    release's manifests/ and images/images.tar, in this order:

    1. production_environment() (service user, HOME, runtime directory), then
       ~/config.yaml must exist.
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
    production_environment()
    config_path = common.HOME / "config.yaml"
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
            quadlet_text(suffix, common.STANDALONE_PRODUCT, common.STANDALONE_PRODUCT),
            encoding="utf-8",
        )
        target.chmod(0o644)

    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "restart", common.SERVICE)
    run("systemctl", "--user", "is-active", "--quiet", common.SERVICE)
    health.wait_healthy(common.SERVICE, common.QUADLET_YAML)
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


def quadlet_text(suffix, product, name):
    """Fill quadlet/template.kube or template.network for one unit.

    {product} becomes the product name (the shared network), {name} the unit's
    file name without suffix: <product>-<component>, or the product itself.
    """
    text = common.QUADLET_TEMPLATE.with_suffix(suffix).read_text(encoding="utf-8")
    return text.replace("{product}", product).replace("{name}", name)


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
            registrations.acknowledge_owner(pending, component, clear_when_done=True)
            if not pending["owners"]:
                pending = None


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
        catalog.metadata_path(common.HOME, descriptor["name"]),
        json.dumps(descriptor, sort_keys=True) + "\n",
    )


def write_installed_marker(descriptor):
    """Publish the version last; it confirms the install completed."""
    write_install_record(
        common.HOME / "installed" / descriptor["name"], descriptor["version"] + "\n"
    )


def install_preconditions(name, checked):
    """Install's checks after the manifests and before generation; read-only.

    The shared network matches the bundle, the image archive exists and every
    image install will verify is fully qualified: the rendered component's, or
    the component's own manifests when it is not rendered. ./deploy validate
    runs this too.
    """
    network, network_text = check_shared_network()
    archive = image_archive()
    documents = [doc for _, docs in checked.values() for doc in docs]
    if name not in checked:
        for path in sorted(
            (common.ROOT / "components" / name / "manifests").glob("*.yaml")
        ):
            documents.extend(rendering.load_yaml_all(path))
    rendering.find_images(documents)
    return network, network_text, archive


def install_component_plan(descriptor, checked, known, imports, updates, removals):
    """Apply a staged install in the established validation/write/restart order."""
    name = descriptor["name"]
    components = list(checked)
    owners = catalog.role_owners(known, "registration owners")
    network, network_text, archive = install_preconditions(name, checked)
    rendered = materialize_component_manifests(checked, imports, known)
    load_and_verify_images(archive, components, [name], rendered)
    write_installed_metadata(descriptor)
    changed, pending = registrations.apply_registration_updates(
        name, descriptor["product"], updates, removals, owners
    )
    write_component_units_and_imports(rendered, network, network_text)
    write_changed_owner_imports(components, changed, imports, known)
    restart_component_services(components, changed, pending, known)
    write_installed_marker(descriptor)
    run("podman", "ps", "--all", "--pod")


def install_checks():
    """Decide everything install needs before staging; no writes, no host commands.

    The bundle descriptor, the installed set with this descriptor (ID prefixes,
    role owners, pending owner work), dependency and dependent ranges, and the
    persistent config with its public_from settings. Returns (descriptor,
    known, config, config_path, render); render is False when only
    registrations and owners are refreshed. ./deploy validate runs this too.
    """
    descriptor = bundle_descriptor()
    name = descriptor["name"]
    pending = registrations.check_pending("install", name, descriptor["product"])
    installed = catalog.load_installed_metadata(common.HOME)
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
    check_kept_shares(descriptor, installed)
    config_path = catalog.component_paths(name)[0]
    if not config_path.is_file():
        raise common.DeployError(
            f"Missing {config_path}; run ./deploy init-config {name} first"
        )
    config = rendering.load_config(config_path)
    render = install_needed(descriptor)
    rendering.validate_component_config(
        config, name, config_path, check_placeholders=render
    )
    check_own_shares(descriptor, config, config_path)
    check_public_settings(descriptor, config, config_path, known)
    return descriptor, known, config, config_path, render


def install_components():
    """Validate the bundle, installed state and config before writing anything.

    Order: install_checks, then staging in a temporary directory, then
    manifests and database preflight, then install_component_plan.
    """
    production_environment()
    descriptor, known, config, config_path, render = install_checks()
    name = descriptor["name"]
    with tempfile.TemporaryDirectory(
        prefix=descriptor["product"] + "-install-", dir=os.environ["XDG_RUNTIME_DIR"]
    ) as directory:
        # Staging only reads and validates registrations; it writes nothing
        # outside the temporary directory and runs before any host command.
        imports, updates, removals = registrations.registration_stage(
            [name], Path(directory), known
        )
        checked = {}
        if render:
            effective = rendering.effective_config(config, config_path, name)
            checked[name] = (
                effective,
                check_manifests(
                    effective,
                    config_path,
                    common.ROOT / "components" / name / "manifests",
                    name,
                    descriptor["accepts"].values(),
                ),
            )
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
    route = common.HOME / "routes" / (component + ".conf")
    client = common.HOME / "clients" / component
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
            and catalog.installed_version(common.HOME, owner)
        ),
    }


def uninstall(component=None, delete_data=False):
    """Resume one scoped uninstall from validated metadata, even after removing its YAML."""
    production_environment()
    descriptor = bundle_descriptor()
    own = descriptor["name"]
    component = component or own
    if component != own:
        raise common.DeployError("This bundle can only uninstall its own component")
    state = registrations.check_pending(
        "uninstall", component, descriptor["product"], delete_data
    )
    marker = common.HOME / "installed" / component
    if state is None and not marker.is_file():
        if catalog.metadata_path(common.HOME, component).is_file():
            # Metadata is written before the units and the marker last, so this
            # is a first install that stopped. Finishing it is the one recovery.
            raise common.DeployError(
                f"Component {component} has an unfinished first install "
                f"(metadata without installed/{component}). Run ./deploy install "
                "from its bundle again to finish it, then uninstall; if that "
                "install keeps failing, fix the cause it reports first"
            )
        raise common.DeployError(f"Component {component} is not installed")
    installed = catalog.load_installed_metadata(common.HOME)
    check_same_product(descriptor["product"], installed)
    dependents = catalog.dependents(installed, common.HOME, component)
    if dependents:
        raise common.DeployError(
            component.title() + " is still required by: " + ", ".join(dependents)
        )
    _, _, output, quadlet = catalog.component_paths(component)
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
        state = uninstall_plan(component, delete_data, installed, descriptor["product"])
        registrations.save_pending(state)
    if not state["stopped"]:
        run("systemctl", "--user", "stop", catalog.unit_name(component) + ".service")
        state["stopped"] = True
        registrations.save_pending(state)
    for path in (output, quadlet, route):
        if path.exists():
            path.unlink()
    if client.exists():
        shutil.rmtree(client)
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
                    common.HOME, owner
                ):
                    raise common.DeployError(
                        "Pending registration owner is not installed: " + owner
                    )
            for owner in restart_order(installed, state["owners"]):
                rendering.write_file_archives(
                    registrations.component_imports(owner, imports, installed) or {},
                    catalog.component_paths(owner)[1],
                )
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
        if (common.HOME / component).exists():
            shutil.rmtree(common.HOME / component)
    # Marker first: metadata without a marker is an unfinished install, never the reverse.
    for path in (marker, catalog.metadata_path(common.HOME, component)):
        if path.exists():
            path.unlink()
    registrations.clear_pending()
    print(
        f"[OK] Uninstalled {component}; shared network retained; data {'deleted' if delete_data else 'preserved'}"
    )
