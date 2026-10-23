"""./deploy validate: report findings without writing anything (backlog 23).

The command reuses the lifecycle's checks so the two cannot disagree:
deploy.validate_component (manifests and PostgreSQL layout), deploy.install_checks
and deploy.install_preconditions (bundle), and registrations.registration_stage in a
temporary directory. The only checks that run here earlier than in the
lifecycle are marked "lifecycle:" below with the place install or prepare
does the same. Credentials are never read; config, metadata, public
registrations and certificates are.
"""

import tempfile
from pathlib import Path

import yaml

from . import catalog, common, deploy, registrations
from . import render as rendering

ERRORS = (common.DeployError, OSError, yaml.YAMLError)


def validate():
    """Report every component's first finding; exit non-zero when there is one.

    The source checkout validates every catalog component with its dev config,
    an unpacked bundle its own component against the persistent config and the
    installed set, and a standalone fixture its manifests against config.yaml.
    Staging uses a temporary directory that is removed. No secret generation,
    rendered output, archives, Podman, systemd or network.
    """
    if (common.ROOT / "bundle.yaml").exists():
        names, findings = validate_bundle()
    elif (common.ROOT / "components").is_dir():
        names, findings = validate_catalog()
    else:
        names, findings = validate_standalone()
    if findings:
        raise common.DeployError(
            f"{len(findings)} validation finding(s); nothing was written:\n"
            + "\n".join(f"  {scope}: {message}" for scope, message in findings)
        )
    print(
        "[OK] validated "
        + ", ".join(names)
        + "; nothing written, no Podman or systemd commands"
    )


def validate_catalog():
    """Validate every catalog component with its dev config, as prepare would.

    A placeholder missing from a component's config stops the whole run while
    dev config is assembled (deploy.dev_settings), exactly as prepare does.
    """
    state = common.BUILD / "dev"
    known, settings = deploy.dev_settings()
    findings = []
    for component, component_settings in settings.items():
        path = state / component / "config.yaml"
        imported = known[component]["accepts"].values()
        try:
            config = rendering.effective_config(component_settings, path, component)
            documents = deploy.validate_component(
                config,
                path,
                common.ROOT / "components" / component / "manifests",
                component,
                imported,
            )
            check_images(documents)
            check_sources(config, path, documents, imported, component)
        except ERRORS as error:
            findings.append((component, str(error)))
    try:
        with tempfile.TemporaryDirectory(
            prefix=catalog.product_name(common.ROOT) + "-validate-"
        ) as directory:
            registrations.registration_stage(
                list(known), Path(directory), known, state=state, configs=settings
            )
    except ERRORS as error:
        findings.append(("registrations", str(error)))
    return list(known), findings


def validate_bundle():
    """Validate this bundle's component as install would, without the volume query.

    Needs the service user (not root, its own HOME) and its bootstrap file
    with a prepared installation root (layout.select), but no runtime
    directory or user manager, so it also works before linger is enabled.
    """
    deploy.service_user()
    descriptor, known, config, config_path, render = deploy.install_checks()
    name = descriptor["name"]
    findings = []
    try:
        with tempfile.TemporaryDirectory(
            prefix=catalog.product_name(common.ROOT) + "-validate-"
        ) as directory:
            registrations.registration_stage([name], Path(directory), known)
    except ERRORS as error:
        findings.append(("registrations", str(error)))
    imported = descriptor["accepts"].values()
    try:
        checked = {}
        if render:
            effective = rendering.effective_config(config, config_path, name)
            documents = deploy.validate_component(
                effective,
                config_path,
                common.ROOT / "components" / name / "manifests",
                name,
                imported,
            )
            checked[name] = (effective, documents)
        deploy.install_preconditions(name, checked)
        for effective, documents in checked.values():
            check_sources(effective, config_path, documents, imported, name)
    except ERRORS as error:
        findings.append((name, str(error)))
    return [name], findings


def validate_standalone():
    """Validate the standalone fixture's manifests against config.yaml, as prepare."""
    if not common.CONFIG.exists():
        raise common.DeployError(f"Missing {common.CONFIG}")
    findings = []
    try:
        config = rendering.load_config(common.CONFIG)
        documents = deploy.validate_component(config, common.CONFIG, common.MANIFESTS)
        check_images(documents)
        check_sources(config, common.CONFIG, documents)
    except ERRORS as error:
        findings.append(("manifests", str(error)))
    return ["manifests"], findings


def check_images(documents):
    """Fully qualified images; lifecycle: build-bundle.sh and install_preconditions."""
    if any(True for _ in rendering.pod_specs(documents)):
        rendering.find_images(documents)


def check_sources(config, config_path, documents, imported=(), component=None):
    """Declared files and the database password; reads no file contents.

    lifecycle: materialize (check_secret_keys, then load_file_group after
    generation), and
    database_preflight, which first asks Podman whether the volume exists.
    Without that query a missing password can mean either case, so the
    message names both remedies.
    """
    # The password first: its message is more specific than a missing source.
    for _, password in deploy.database_bindings(config, config_path, documents):
        if not (password.exists() or password.is_symlink()):
            try:
                deploy.check_password_provided(config, config_path, password)
            except common.DeployError as error:
                raise common.DeployError(
                    f"{error}, or restore the password from backup if its "
                    "database volume already exists"
                ) from None
    # Same order as materialize: selected Secret keys, then the sources.
    rendering.check_secret_keys(config, config_path, documents, component)
    rendering.check_file_sources(config, config_path, imported, component)
