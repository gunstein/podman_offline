"""Render component declarations and config into what is installed.

Rendering is the whole path from declarations to installable output: config
validation, effective (validated) manifests, secret generation and file
delivery, and finally the YAML and import archives (materialize). Validation is
its first stage, so nothing is generated from declarations that do not check.
"""

import base64
import os
import re
import secrets
import stat
import string
import tarfile
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from . import common, environment, mounts, templates
from .output import log


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate keys instead of keeping the last value."""

    def construct_mapping(self, node, deep=False):
        """Build a YAML mapping and reject duplicate keys with their line number."""
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


# Build-time image variables (backlog 63): config/images.yaml, used only in the
# image field of containers and initContainers, plus the built-in
# COMPONENT_VERSION. Bundles ship the resolved, literal references.
IMAGE_VARIABLES = "config/images.yaml"
IMAGE_NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")
# Names that already mean something else: reserved or derived config names.
IMAGE_RESERVED = (
    "COMPONENT_VERSION",
    "PUBLIC_HOSTNAME",
    "CLIENT_ID",
    "CLIENT_BASE_PATH",
    common.SECRET_FILES,
    common.VOLUME_FILES,
    common.SECRET_TEMPLATES,
    common.ENVIRONMENT,
    common.MOUNTS,
)


def image_variables(root):
    """The variables of root/config/images.yaml; {} without the file.

    A release has no such file: its manifests hold literal references.
    """
    path = root / IMAGE_VARIABLES
    if not path.is_file():
        return {}
    data = load_yaml(path)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise common.DeployError(f"{path} must map NAME: value")
    for name, value in data.items():
        if not isinstance(name, str) or not IMAGE_NAME.fullmatch(name):
            raise common.DeployError(
                f"{path}: {name!r} is not a variable name; use A-Z, 0-9 and _"
            )
        if name in IMAGE_RESERVED:
            raise common.DeployError(f"{path}: {name} is a reserved name; rename it")
        if isinstance(value, str):
            # Build time (backlog 86): the building process's variables.
            value = data[name] = templates.setting_text(value, f"{path}: {name}")
        if not isinstance(value, str) or not value:
            raise common.DeployError(
                f"{path}: {name} must be a nonempty text value; quote numbers "
                "such as '17.11'"
            )
    return data


def load_manifest(path):
    """A component manifest with its image fields resolved (backlog 63).

    Every reader of component manifests uses this before anything else reads
    them, so pull, build, dev, validate and the bundle see the same images.
    The manifest's place, <root>/components/<id>/manifests/, gives the
    component's VERSION and config.defaults.yaml and the root's
    config/images.yaml.
    """
    component = path.parent.parent
    variables = image_variables(component.parent.parent)
    return resolve_images(load_yaml_all(path), variables, component, path)


def resolve_images(documents, variables, component, path):
    """Replace @@NAME@@ and @@$NAME@@ in each container image; refuse image variables elsewhere."""
    defaults = component / "config.defaults.yaml"
    settings = load_yaml(defaults) if defaults.is_file() else None
    for name in sorted(set(variables) & set(settings or {})):
        raise common.DeployError(
            f"{name} is both an image variable ({IMAGE_VARIABLES}) and a setting in "
            f"{defaults}; rename one"
        )
    # Tolerant of malformed documents: their shape is reported by the usual
    # checks (pod_specs) as validate findings.
    pods = [
        doc.get("spec")
        for doc in documents
        if isinstance(doc, dict) and doc.get("kind") == "Pod"
    ]
    for spec in pods:
        groups = (
            [spec.get(group) for group in ("containers", "initContainers")]
            if isinstance(spec, dict)
            else []
        )
        for container in [
            c for group in groups if isinstance(group, list) for c in group
        ]:
            image = container.get("image") if isinstance(container, dict) else None
            if not isinstance(image, str) or "@@" not in image:
                continue
            where = f"{path}: container {container.get('name')!r}"

            def value(group, field, where=where):
                if group is not None:
                    raise common.DeployError(
                        f"{where}: an image may not use a secret placeholder"
                    )
                if field.startswith("$"):
                    # Build time (backlog 86): the building process's variable.
                    return templates.environment_value(field[1:], where)
                if field == "COMPONENT_VERSION":
                    return component_version(component, where)
                if field not in variables:
                    raise common.DeployError(
                        f"{where}: image uses @@{field}@@, which is not in "
                        f"{IMAGE_VARIABLES}; add it there or fix the name"
                    )
                if "@@" in variables[field]:
                    raise common.DeployError(
                        f"{where}: @@{field}@@ gives no valid reference "
                        f"after {IMAGE_VARIABLES}; check its values"
                    )
                return variables[field]

            # One pass, as every template (templates.substitute): @@@@ is a
            # literal @@, which the reference check below then refuses.
            resolved = templates.substitute(image, value, where)
            if "@@" in resolved or any(c.isspace() for c in resolved):
                raise common.DeployError(
                    f"{where}: image {resolved!r} is not a valid reference after "
                    f"{IMAGE_VARIABLES}; check its values"
                )
            if "://" in resolved:
                raise common.DeployError(
                    f"{where}: image {resolved!r} has a URL scheme; give only the "
                    f"registry host and path in {IMAGE_VARIABLES}"
                )
            container["image"] = resolved
    for name in sorted(set(variables) & placeholders_outside_images(documents)):
        raise common.DeployError(
            f"{path}: @@{name}@@ is an image variable ({IMAGE_VARIABLES}); use it "
            "only in a container image"
        )
    return documents


def component_version(component, where):
    path = component / "VERSION"
    if not path.is_file():
        raise common.DeployError(
            f"{where}: @@COMPONENT_VERSION@@ needs the component's VERSION file"
        )
    return path.read_text(encoding="utf-8").strip()


def placeholders_outside_images(value, key=None):
    """Every @@NAME@@ name in the documents except in image fields."""
    found = set()
    if isinstance(value, dict):
        for item_key, item in value.items():
            if item_key != "image":
                found |= placeholders_outside_images(item, item_key)
    elif isinstance(value, list):
        for item in value:
            found |= placeholders_outside_images(item)
    elif isinstance(value, str):
        found = {match[1] for match in templates.placeholders(value)}
    return found


def load_yaml(path):
    """Read one YAML document safely and reject duplicate keys."""
    try:
        with path.open(encoding="utf-8") as f:
            # A SafeLoader subclass rejects duplicates without allowing object construction.
            return yaml.load(f, Loader=UniqueKeyLoader)
    except UnicodeDecodeError:
        raise common.DeployError(f"{path} is not valid UTF-8") from None


def load_yaml_all(path):
    """Read all YAML documents safely and reject duplicate keys."""
    try:
        with path.open(encoding="utf-8") as f:
            return list(yaml.load_all(f, Loader=UniqueKeyLoader))
    except UnicodeDecodeError:
        raise common.DeployError(f"{path} is not valid UTF-8") from None


def config_layer(path):
    """Read one mapping, rejecting duplicate keys without exposing YAML values."""
    try:
        config = load_yaml(path)
    except (yaml.YAMLError, TypeError) as error:
        mark = getattr(error, "problem_mark", None)
        location = f" at line {mark.line + 1}" if mark is not None else ""
        problem = getattr(error, "problem", "") or ""
        detail = problem if problem.startswith("duplicate key ") else "invalid YAML"
        raise yaml.YAMLError(f"{path}{location}: {detail}") from None

    if not isinstance(config, dict):
        raise common.DeployError(f"{path} must contain KEY: value pairs")

    return config


def validate_config(config, path):
    """Validate the complete config; individual merge layers may be incomplete."""
    for key, value in config.items():
        if not isinstance(key, str):
            raise common.DeployError(f"All keys in {path} must be strings")

        if key in (common.ENVIRONMENT, common.MOUNTS):
            raise common.DeployError(
                f"{path}: {key} belongs only in the release's "
                "components/<id>/config.defaults.yaml; remove it here"
            )

        if key == common.OVERRIDES:
            raise common.DeployError(
                f"{path}: overrides is reserved for config/dev.yaml and a build "
                "environment file config/<environment>.yaml; remove it here"
            )

        if key == common.SECRET_TEMPLATES:
            raise common.DeployError(
                f"{path}: SECRET_TEMPLATES is not supported; write the secret as "
                "@@secret:<id>/<key>@@ in ENVIRONMENT or in a MOUNTS file"
            )

        if key in (common.SECRET_FILES, common.VOLUME_FILES):
            continue  # File groups and generated paths validate their own structures.

        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise common.DeployError(
                f"{key} in {path} must be a string or an integer, "
                f"got type {type(value).__name__}. Put text in quotes."
            )

    port = config.get("HTTPS_PORT")
    if "HTTPS_PORT" in config and (
        isinstance(port, bool)
        or not isinstance(port, int)
        or not 1 <= port <= common.MAX_PORT
    ):
        raise common.DeployError(
            f"HTTPS_PORT in {path} must be an integer 1-{common.MAX_PORT} without quotes"
        )

    for key in ("DB_HOST", "DB_PORT", "DB_USER", "DB_NAME"):
        # A value with @@$NAME@@ is checked once resolved (resolve_settings).
        if key in config and not has_environment_reference(config[key]):
            value = config[key]
            if not isinstance(value, str) or not value or "\x00" in value:
                raise common.DeployError(f"{key} in {path} must be non-empty text")
    if "DB_PORT" in config and not has_environment_reference(config["DB_PORT"]):
        port = config["DB_PORT"]
        if (
            not re.fullmatch(r"[0-9]{1,5}", port)
            or not 1 <= int(port) <= common.MAX_PORT
        ):
            raise common.DeployError(
                f"DB_PORT in {path} must be text containing an integer 1-{common.MAX_PORT}"
            )

    return config


def has_environment_reference(value):
    return isinstance(value, str) and "@@$" in value


def resolve_settings(config, path):
    """The settings with @@$NAME@@ resolved and @@@@ made @@, then validated.

    Deploy time (backlog 86): call once, after the layers are merged, so only
    the effective value of a setting is resolved, and before anything uses
    the values (PUBLIC_HOSTNAME, credentials, rendering). Its output is final
    text: never pass a resolved value through it again (component_defaults'
    resolved). SECRET_FILES and VOLUME_FILES are declarations, not settings,
    and keep their text.
    """
    result = dict(config)
    for key, value in config.items():
        if key not in (common.SECRET_FILES, common.VOLUME_FILES) and isinstance(
            value, str
        ):
            result[key] = templates.setting_text(value, f"{key} in {path}")
    return validate_config(result, path)


def load_config(path):
    """Production loads only the authoritative materialized file."""
    return validate_config(config_layer(path), path)


def merge_config(*paths, overrides=None):
    """Merge mappings at the top level, in order, then validate the result.

    ENVIRONMENT and MOUNTS belong to the release (deployment/environment.py,
    deployment/mounts.py), so they are left out of the merged config and never
    reach the operator's config.yaml.
    """
    config = {}
    for path in paths:
        layer = config_layer(path)
        if (
            path.name == "config.defaults.yaml"
            and path.parent.parent.name == "components"
        ):
            layer.pop(common.ENVIRONMENT, None)
            layer.pop(common.MOUNTS, None)
        config.update(layer)
    config.update(overrides or {})
    return validate_config(config, paths[-1] if paths else "config")


def merged_defaults(component, overrides=None, dev=False):
    """The component defaults and, in dev, config/dev.yaml, merged; not resolved.

    Each layer file is optional; a component without settings needs none.
    config/dev.yaml is the developer's local, untracked override (dev_layer).
    init-config writes this, so @@$NAME@@ references stay references.
    """
    defaults = common.ROOT / "components" / component / "config.defaults.yaml"
    local = common.ROOT / "config/dev.yaml"
    paths = [path for path in (defaults,) if path.exists() or path.is_symlink()]
    config = merge_config(*paths)
    if dev and (local.exists() or local.is_symlink()):
        config = dev_layer(config, local, component)
    config.update(overrides or {})
    return validate_config(config, local if dev else defaults)


def component_defaults(component, overrides=None, dev=False, resolved=None):
    """merged_defaults with its references resolved (resolve_settings), validated.

    resolved holds settings that are already final text (the gateway's
    public settings): they are added after the resolution, never resolved
    again, so an escaped @@ in them stays literal.
    """
    source = (
        common.ROOT / "config/dev.yaml"
        if dev
        else common.ROOT / "components" / component / "config.defaults.yaml"
    )
    config = resolve_settings(merged_defaults(component, overrides, dev), source)
    config.update(resolved or {})
    materialized = (
        (common.BUILD / "dev" if dev else common.STATE) / component / "config.yaml"
    )
    validate_component_config(config, component, materialized)
    return config


def dev_layer(config, path, component):
    """Apply config/dev.yaml to one component's config.

    A setting replaces the whole value for every component. A SECRET_FILES or
    VOLUME_FILES ID replaces only that ID's source list, in the component whose
    ID it starts with; the ID must already be declared there. The reserved
    overrides block is no setting: deploy.dev_settings reads it
    (environment.read_dev_overrides), and it never reaches a config.yaml.
    """
    layer = config_layer(path)
    result = dict(config)
    for key, value in layer.items():
        if key == common.OVERRIDES:
            continue
        if key not in (common.SECRET_FILES, common.VOLUME_FILES):
            result[key] = value
            continue
        if not isinstance(value, dict):
            raise common.DeployError(f"{path}: {key} must be a map of IDs")
        group = dict(result.get(key) or {})
        for name, sources in value.items():
            if not str(name).startswith(component + "-"):
                continue  # Another component's ID (dev_file_ids checks the owner).
            if name not in group:
                raise common.DeployError(
                    f"{path}: {key}.{name} is not declared in "
                    f"components/{component}/config.defaults.yaml; dev.yaml can only "
                    "replace the sources of a declared ID"
                )
            group[name] = sources
        result[key] = group
    return result


def dev_file_ids(path, components):
    """Every SECRET_FILES/VOLUME_FILES ID in config/dev.yaml belongs to a component."""
    if not (path.exists() or path.is_symlink()):
        return
    layer = config_layer(path)
    for key in (common.SECRET_FILES, common.VOLUME_FILES):
        for name in layer.get(key) or {}:
            if not any(str(name).startswith(item + "-") for item in components):
                raise common.DeployError(
                    f"{path}: {key}.{name} does not start with a component ID "
                    "from bundles.yaml"
                )


def validate_component_config(config, component, path):
    """Validate whole-value and ConfigMap inline inputs before initialization writes.

    Shared public settings are required by the component's declared contract
    (catalog.operator_config), not here.
    """
    required = set()
    configmaps = []

    def collect(value):
        if isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, str):
            match = common.PH.fullmatch(value)
            if match:
                required.add(match[1])

    for manifest in sorted(
        (common.ROOT / "components" / component / "manifests").glob("*.yaml")
    ):
        documents = load_manifest(manifest)
        collect(documents)
        configmaps.extend(
            doc
            for doc in documents
            if isinstance(doc, dict) and doc.get("kind") == "ConfigMap"
        )
    for name in environment.CLIENT_SETTINGS:
        if name in config:
            raise common.DeployError(
                f"{name} in {path} is derived from client.yaml; remove it"
            )
    # PUBLIC_HOSTNAME is always derived from PUBLIC_ORIGIN, so it cannot disagree.
    if "PUBLIC_HOSTNAME" in config:
        raise common.DeployError(
            f"PUBLIC_HOSTNAME in {path} is derived from PUBLIC_ORIGIN; remove it"
        )
    if "PUBLIC_HOSTNAME" in required:
        required.discard("PUBLIC_HOSTNAME")
        required.add("PUBLIC_ORIGIN")
    for key in sorted(required):
        if key not in config:
            raise common.DeployError(
                f"Missing {key} in {path}; add it explicitly before installation"
            )
    if "PUBLIC_ORIGIN" in config:
        public_origin(config["PUBLIC_ORIGIN"], path)
    check_component_config_names(config, component, path)
    generated_secret_paths(config, path.parent)
    check_component_file_sources(config, component)
    check_templates(config, path, component)
    if configmaps:
        effective = with_derived(config, path)
        for document in configmaps:
            check_kinds([document], path)
            configmap_data(document, replace(document, effective), effective)


def check_templates(config, path, component=None):
    """Validate the ENVIRONMENT/MOUNTS recipes without reading credentials.

    effective_documents runs it on the effective config, before any write.
    """
    templates.validate(
        with_derived(config, path), secret_keys(config, path, [], component)
    )


def with_derived(config, path):
    """Copy config with PUBLIC_HOSTNAME derived from PUBLIC_ORIGIN.

    PUBLIC_HOSTNAME cannot be stored in config: a second authoritative value
    could disagree with PUBLIC_ORIGIN. validate_component_config rejects it.
    """
    effective = dict(config)
    if "PUBLIC_ORIGIN" in config:
        effective["PUBLIC_HOSTNAME"] = public_origin(
            config["PUBLIC_ORIGIN"], path
        ).hostname
    return effective


def with_client_settings(config, component):
    """Copy config with CLIENT_ID and CLIENT_BASE_PATH from client.yaml, if any.

    client.yaml is the one place for the OIDC client ID and base path; the app
    receives them through ENVIRONMENT lines such as APP_ID: '@@CLIENT_ID@@'.
    registrations.client_descriptor validates the file itself.
    """
    path = common.ROOT / "components" / component / "client.yaml"
    data = load_yaml(path) if path.is_file() else None
    if not isinstance(data, dict):
        return config
    effective = dict(config)
    for name, key in environment.CLIENT_SETTINGS.items():
        if isinstance(data.get(key), str):
            effective[name] = data[key]
    return effective


def public_origin(value, path):
    """Validate an HTTPS origin without exposing its supplied value in errors."""
    message = f"PUBLIC_ORIGIN in {path} must be an HTTPS origin without credentials, path or query"
    if not isinstance(value, str):
        raise common.DeployError(message)
    try:
        address = urlsplit(value.rstrip("/"))
        hostname = address.hostname
    except ValueError:
        raise common.DeployError(message) from None
    if (
        address.scheme != "https"
        or not hostname
        or address.path
        or address.query
        or address.fragment
        or address.username is not None
        or address.password is not None
    ):
        raise common.DeployError(message)
    return address


def file_group_sources(config, group):
    """Validate one delivery map without reading or generating its source files."""
    mapping = config.get(group, {})
    if not isinstance(mapping, dict):
        raise common.DeployError(f"{group} must be id: [list of file sources]")
    for name, sources in mapping.items():
        if not isinstance(name, str) or not common.ID.fullmatch(name):
            raise common.DeployError(
                f"Invalid id in {group}; use lowercase letters, digits and -"
            )
        where = f"{group}.{name}"
        if not isinstance(sources, list) or not sources:
            raise common.DeployError(f"{where} must be a nonempty list of file sources")
        for source in sources:
            if not isinstance(source, dict) or set(source) - {
                "path",
                "component_file",
                "generate",
            }:
                raise common.DeployError(
                    f"{where}: each source must contain exactly one of path or component_file, and optional generate for path"
                )
            if ("path" in source) == ("component_file" in source):
                raise common.DeployError(
                    f"{where}: use exactly one of path or component_file"
                )
            kind = "component_file" if "component_file" in source else "path"
            if kind == "component_file" and "generate" in source:
                raise common.DeployError(f"{where}: component_file cannot use generate")
            path = source[kind]
            if not isinstance(path, str) or not path or "\x00" in path:
                raise common.DeployError(f"{where}: {kind} must be nonempty text")
            names = source.get("generate", [])
            if not isinstance(names, list) or any(
                not isinstance(value, str) or "\x00" in value for value in names
            ):
                raise common.DeployError(
                    f"{where}: generate must be a list of relative file paths"
                )
    return mapping


def generated_secret_paths(config, base_dir):
    """Resolve generation declared on delivery sources; never read or create files."""
    base = base_dir.resolve()
    paths = []
    seen = set()
    for group in (common.SECRET_FILES, common.VOLUME_FILES):
        for name, sources in file_group_sources(config, group).items():
            for source in sources:
                for filename in source.get("generate", []):
                    directory, relative = Path(source["path"]), Path(filename)
                    if (
                        directory.is_absolute()
                        or source["path"].startswith("~")
                        or ".." in directory.parts
                        or relative.is_absolute()
                        or ".." in relative.parts
                        or not relative.name
                    ):
                        raise common.DeployError(
                            f"{group}.{name}: generated paths must stay under the config directory"
                        )
                    path = (base / directory / relative).resolve()
                    try:
                        path.relative_to(base)
                    except ValueError:
                        raise common.DeployError(
                            f"{group}.{name}: generated path resolves outside the config directory"
                        ) from None
                    # A Secret holds files by name only; refuse before generating.
                    if group == common.SECRET_FILES and (
                        len(relative.parts) != 1
                        or not common.SECRET_KEY.fullmatch(relative.name)
                    ):
                        raise common.DeployError(
                            f"{group}.{name}: generated file {filename!r} must be one "
                            "file name of letters, digits, . - and _"
                        )
                    if path in seen:
                        raise common.DeployError(
                            f"{group}.{name}: duplicate generated file declaration"
                        )
                    source_path = base / directory
                    if source_path.exists() and not source_path.is_dir():
                        raise common.DeployError(
                            f"{group}.{name}: a generate source must be a directory"
                        )
                    seen.add(path)
                    paths.append(path)
    return paths


def generate_secrets(config, base_dir):
    """Create missing private secret files once, within the config directory."""
    for path in generated_secret_paths(config, base_dir):
        if path.exists():
            if not path.is_file() or path.stat().st_size == 0:
                raise common.DeployError(
                    f"Generated secret file {path} is empty or not a regular file"
                )
            continue
        missing, parent = [], path.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        for directory in reversed(missing):
            directory.mkdir(mode=0o700, exist_ok=True)
        path.parent.chmod(0o700)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if not path.is_file() or path.stat().st_size == 0:
                raise common.DeployError(
                    f"Generated secret file {path} is empty or not a regular file"
                ) from None
            continue
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            stream.write(
                "".join(
                    secrets.choice(string.ascii_letters + string.digits)
                    for _ in range(32)
                )
            )
        log.info(f"[OK] Generated secret file {path}")


def replace(value, config):
    """Replace whole placeholders recursively and keep the config value's type."""
    if isinstance(value, dict):
        return {key: replace(item, config) for key, item in value.items()}

    if isinstance(value, list):
        return [replace(item, config) for item in value]

    if isinstance(value, str):
        match = common.PH.fullmatch(value)
        if match:
            key = match.group(1)
            if key not in config:
                raise common.DeployError(f"Missing {key} in config.yaml")
            # An inserted value is never template text, so it cannot carry an
            # escape: @@ in it is refused, as in every other place (backlog 87).
            if isinstance(config[key], str) and "@@" in config[key]:
                raise common.DeployError(
                    f"The value of {key} contains @@; a value is not template text"
                )
            return config[key]
        # A whole "@@$NAME@@" value: the process environment's text (backlog 86).
        if value.startswith("@@$") and value.endswith("@@") and value.count("@@") == 2:
            where = "a manifest value"
            return templates.environment_value(
                templates.environment_name(value[2:-2], where), where
            )
        # Text without placeholders: its @@@@ escapes become @@, once (backlog
        # 87). Text with an embedded placeholder is left for ConfigMap data
        # (configmap_data) or refused by check_unresolved.
        if not templates.malformed(value) and not templates.placeholders(value):
            return templates.substitute(value, None, "a manifest value")

    return value


def write_private(path, text):
    """Write the file with mode 0600 from the first byte."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)  # in case the file existed with another mode
        f.write(text)


def resolve_path(value, base_dir):
    """Resolve a relative path from the config directory; ~ is allowed."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else base_dir / path


def resolve_file_source(entry, base_dir=None, component=None, root=None):
    """Resolve one validated source in its config or selected component context.

    Shipped inputs are public immutable release content. Inspect names/types only;
    never follow a link, read file bytes or create a generation target here.
    """
    if "component_file" not in entry:
        return resolve_path(entry["path"], base_dir)
    if not isinstance(component, str) or not common.ID.fullmatch(component):
        raise common.DeployError(
            "component_file requires an explicit component context"
        )
    value = entry["component_file"]
    relative = Path(value)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not relative.parts
        or value.startswith("~")
    ):
        raise common.DeployError(
            "component_file must be a relative path below this component's files/"
        )
    path = common.component_file(component, relative, root)
    check_component_file_tree(path)
    return path


def check_component_file_tree(path):
    """Check the full selected tree before tar's dereference or any generation."""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        raise common.DeployError(f"Missing component_file source: {path}") from None
    if stat.S_ISDIR(mode):
        for item in sorted(path.iterdir()):
            check_component_file_tree(item)
    elif not stat.S_ISREG(mode):
        raise common.DeployError(
            f"{path}: a component's files/ may hold only regular files and "
            "directories, without symlinks"
        )


def check_component_file_sources(config, component):
    """Validate portable declarations before writes, including standalone callers."""
    for group in (common.SECRET_FILES, common.VOLUME_FILES):
        selected = {}
        for name, entries in file_group_sources(config, group).items():
            portable = [entry for entry in entries if "component_file" in entry]
            if portable:
                selected[name] = portable
        # Reuse delivery's key/type/duplicate checks, inspecting no file bytes.
        load_file_group({group: selected}, group, component=component)


def load_file_group(config, group, base_dir=None, component=None):
    """Read file groups and expand directory paths one level, relative to the config."""
    spec = file_group_sources(config, group)
    groups = {}
    for group_id, entries in spec.items():
        where = f"{group}.{group_id}"
        items = []

        for path in (
            resolve_file_source(entry, base_dir, component) for entry in entries
        ):
            if not path.exists():
                raise common.DeployError(f"Missing {path} ({where})")
            items += sorted(path.iterdir()) if path.is_dir() else [path]

        names = [item.name for item in items]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise common.DeployError(
                f"{where} has several files with the same name: {duplicates}"
            )

        if group == common.SECRET_FILES:
            for item in items:
                if not item.is_file():
                    raise common.DeployError(
                        f"{where}: {item} is a directory. Secrets can only "
                        "contain files; use VOLUME_FILES for directory trees"
                    )
                if not common.SECRET_KEY.fullmatch(item.name):
                    raise common.DeployError(
                        f"{where}: the file name {item.name!r} may only contain "
                        "letters, digits, . - and _"
                    )

        groups[group_id] = items

    return groups


def check_file_sources(config, path, imported=(), component=None):
    """Check that declared file sources exist with the right type; read no contents.

    A source with generate may still be missing: generation creates it. Imported
    registration volumes replace a same-named VOLUME_FILES entry and are skipped.
    Only names and types are inspected, so this is safe for private files.
    """
    imported = set(imported)
    for group in (common.SECRET_FILES, common.VOLUME_FILES):
        present = {}
        for group_id, entries in file_group_sources(config, group).items():
            if group == common.VOLUME_FILES and group_id in imported:
                continue
            kept = [
                entry
                for entry in entries
                if "generate" not in entry
                or resolve_file_source(entry, path.parent, component).exists()
            ]
            if kept:
                present[group_id] = kept
        load_file_group({group: present}, group, path.parent, component)


def secret_keys(config, path, documents, component=None):
    """Return the keys each Secret provides, decided from declarations only.

    SECRET_FILES keys are the file names of its sources (a directory's entries
    or the file itself) plus generate names; an inline Secret's keys are its
    data and stringData keys. A Secret whose source is still missing (and not
    generated) maps to None: its keys are unknown, and the missing source is
    reported by check_file_sources. No file contents are read.
    """
    keys = {}
    for name, entries in file_group_sources(config, common.SECRET_FILES).items():
        found = set()
        for entry in entries:
            source = resolve_file_source(entry, path.parent, component)
            found.update(entry.get("generate", []))
            if source.is_dir():
                found.update(item.name for item in source.iterdir())
            elif source.exists():
                found.add(source.name)
            elif "generate" not in entry:
                found = None
                break
        keys[name] = found
    for doc in documents:
        if isinstance(doc, dict) and doc.get("kind") == "Secret":
            name = (doc.get("metadata") or {}).get("name")
            data = {}
            for field in ("data", "stringData"):
                if isinstance(doc.get(field), dict):
                    data.update(doc[field])
            keys[name] = {str(key) for key in data}
    keys.update(
        {name: set(values) for name, values in templates.declarations(config).items()}
    )
    return keys


def check_secret_keys(config, path, documents, component=None):
    """Every Secret key a pod selects must exist; Podman would fail at start.

    Checks volumes[].secret.items[].key and env[].valueFrom.secretKeyRef.key
    against secret_keys(); references marked optional are skipped.
    """
    keys = secret_keys(config, path, documents, component)

    def check(name, key, where):
        available = keys.get(name)
        if available is None or key in available:
            return
        raise common.DeployError(
            f"{path}: {where} uses key {key!r} of Secret {name!r}, which provides "
            f"only {', '.join(sorted(available)) or 'no keys'}"
        )

    for pod, spec in pod_specs(documents):
        pod_name = (pod.get("metadata") or {}).get("name")
        for volume in spec.get("volumes", []):
            secret = volume.get("secret") if isinstance(volume, dict) else None
            if not isinstance(secret, dict) or secret.get("optional"):
                continue
            for item in secret.get("items") or []:
                if isinstance(item, dict) and "key" in item:
                    check(
                        secret.get("secretName"),
                        str(item["key"]),
                        f"Pod {pod_name!r} volume {volume.get('name')!r}",
                    )
        for _, container in containers(spec):
            for entry in container.get("env", []):
                source = (
                    (entry.get("valueFrom") or {}) if isinstance(entry, dict) else {}
                )
                ref = source.get("secretKeyRef")
                if isinstance(ref, dict) and "key" in ref and not ref.get("optional"):
                    check(
                        ref.get("name"),
                        str(ref["key"]),
                        f"Pod {pod_name!r} container {container.get('name')!r} "
                        f"env {entry.get('name')!r}",
                    )


def secret_documents(secrets):
    """Build base64-encoded Secrets within Podman's size limit."""
    docs = []

    for secret_id, items in secrets.items():
        doc = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": secret_id},
            "type": "Opaque",
            "data": {
                item.name: base64.b64encode(item.read_bytes()).decode("ascii")
                for item in items
            },
        }

        if len(yaml.safe_dump(doc)) > common.MAX_SECRET_SIZE:
            raise common.DeployError(
                f"{common.SECRET_FILES}.{secret_id} is too large for a Podman secret "
                f"(max about {common.MAX_SECRET_SIZE * 3 // 4} bytes of file content). "
                "Use VOLUME_FILES for large files"
            )

        docs.append(doc)

    return docs


def normalize(info):
    """Normalize ownership, modes and timestamps for stable import checksums."""
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    info.mode = 0o755 if info.isdir() or info.mode & 0o111 else 0o644
    return info


def archive_path(files_dir, volume_id):
    """Return the import archive path for a volume id."""
    return files_dir / f"{volume_id}.tar"


def write_file_archives(volumes, files_dir):
    """Write one tar archive per VOLUME_FILES id."""
    if not volumes:
        return

    files_dir.mkdir(parents=True, exist_ok=True)
    files_dir.chmod(0o700)

    for volume_id, items in volumes.items():
        archive = archive_path(files_dir, volume_id)
        fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)

        with os.fdopen(fd, "wb") as raw:
            os.fchmod(raw.fileno(), 0o600)
            # The offline archive must contain link targets, not links to the build machine.
            with tarfile.open(fileobj=raw, mode="w", dereference=True) as tar:
                for item in items:
                    tar.add(str(item), arcname=item.name, filter=normalize)


def volume_claims(volumes, files_dir):
    """Build PVCs that let Podman import each VOLUME_FILES archive."""
    return [
        {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": volume_id,
                "annotations": {
                    common.IMPORT_SOURCE: str(archive_path(files_dir, volume_id))
                },
            },
            # Podman ignores spec, but Kubernetes requires the fields.
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "1Gi"}},
            },
        }
        for volume_id in volumes
    ]


def references(value, found):
    """Find Secret, PVC and ConfigMap references used by the manifests."""
    if isinstance(value, dict):
        secret = value.get("secret")
        if isinstance(secret, dict) and "secretName" in secret:
            found.add(("Secret", secret["secretName"]))

        claim = value.get("persistentVolumeClaim")
        if isinstance(claim, dict) and "claimName" in claim:
            found.add(("PersistentVolumeClaim", claim["claimName"]))

        config_map = value.get("configMap")
        if isinstance(config_map, dict) and "name" in config_map:
            found.add(("ConfigMap", config_map["name"]))

        for key in ("secretKeyRef", "secretRef", "configMapRef", "configMapKeyRef"):
            ref = value.get(key)
            if isinstance(ref, dict) and "name" in ref:
                kind = "ConfigMap" if key.startswith("configMap") else "Secret"
                found.add((kind, ref["name"]))

        for item in value.values():
            references(item, found)

    elif isinstance(value, list):
        for item in value:
            references(item, found)

    return found


def check_links(docs, from_config, sources=None, recipe_references=()):
    """Validate unique volume names and links between config and manifests."""
    defined = [
        (doc.get("kind"), (doc.get("metadata") or {}).get("name"))
        for doc in docs
        if isinstance(doc, dict)
        and doc.get("kind") in ("Secret", "PersistentVolumeClaim", "ConfigMap")
    ]

    names = [name for _, name in defined]
    for name in sorted({n for n in names if names.count(n) > 1}, key=str):
        raise common.DeployError(
            f"The name {name!r} is defined more than once as Secret/PVC/ConfigMap. "
            "Podman creates one volume per name, so names must be unique across kinds"
        )

    defined = set(defined)
    used = references(docs, set()) | set(recipe_references)

    for kind, name in sorted(used - set(defined)):
        source = ""
        if sources:
            for doc, path in zip(docs, sources):
                if path and (kind, name) in references(doc, set()):
                    source = f"{path}: "
                    break
        if kind == "ConfigMap":
            hint = "Define it in a manifest"
        else:
            group = common.SECRET_FILES if kind == "Secret" else common.VOLUME_FILES
            hint = f"Add it under {group} in config.yaml or in a manifest"
        raise common.DeployError(
            f"{source}A manifest uses {kind} {name!r}, but it does not exist. {hint}"
        )

    for key, where in sorted(from_config.items()):
        if key not in used:
            raise common.DeployError(
                f"{where} is not used by any manifest, ENVIRONMENT or MOUNTS file. "
                "Check that the id matches secretName/claimName in a manifest or "
                "@@secret:<id>/<key>@@ in ENVIRONMENT, a MOUNTS file or a MOUNTS source"
            )


SUPPORTED_KINDS = ("Pod", "ConfigMap", "PersistentVolumeClaim", "Secret")


def check_kinds(documents, source):
    """Accept only the resource kinds every lifecycle step understands.

    Rendering, preflight, image discovery, name checks and uninstall all read
    Pods through pod_specs(). A Deployment or List would pass some of those
    steps and bypass others, so it is refused before any side effect.
    """
    for doc in documents:
        if doc is None:
            continue  # An empty YAML document, e.g. after a leading ---.
        kind = doc.get("kind") if isinstance(doc, dict) else None
        if not isinstance(kind, str) or kind not in SUPPORTED_KINDS:
            raise common.DeployError(
                f"{source}: unsupported resource kind {kind!r}; "
                "supported: " + ", ".join(SUPPORTED_KINDS)
            )
        if not isinstance(doc.get("metadata", {}), dict):
            raise common.DeployError(f"{source}: {kind} metadata must be a map")


# Container-only fields commonly misplaced beside containers/initContainers.
# Pod fields such as securityContext and restartPolicy deliberately stay allowed.
CONTAINER_ONLY_FIELDS = (
    "env",
    "envFrom",
    "command",
    "args",
    "image",
    "imagePullPolicy",
    "volumeMounts",
    "volumeDevices",
    "ports",
    "workingDir",
    "livenessProbe",
    "readinessProbe",
    "startupProbe",
    "lifecycle",
    "stdin",
    "stdinOnce",
    "tty",
    "terminationMessagePath",
    "terminationMessagePolicy",
)


def pod_specs(documents, source="manifests"):
    """Check supported resource/Pod shapes and return each (document, spec)."""
    documents = list(documents)  # Callers may pass a one-shot YAML generator.
    check_kinds(documents, source)
    specs = []
    for doc in documents:
        if doc is not None and doc["kind"] == "Pod":
            spec = doc.get("spec", {})
            if not isinstance(spec, dict):
                raise common.DeployError(f"{source}: Pod spec must be a map")
            for field in CONTAINER_ONLY_FIELDS:
                if field in spec:
                    raise common.DeployError(
                        f"{source}: spec.{field} is not allowed here; place {field} "
                        "under spec.containers[] or spec.initContainers[]"
                    )
            if "hostAliases" in spec:
                # Keep public-origin resolution authoritative in the network DNS.
                raise common.DeployError(
                    f"{source}: spec.hostAliases is not supported: containers "
                    "reach the public origin through the proxy's host name in the "
                    "product network"
                )
            check_lists(spec, ("volumes",), f"{source}: Pod spec")
            specs.append((doc, spec))
    return specs


def containers(spec):
    """Return (group, container) for regular and init containers of one pod spec."""
    found = []
    for group in ("containers", "initContainers"):
        entries = spec.get(group, [])
        if not isinstance(entries, list):
            raise common.DeployError(f"{group} must be a list")
        for container in entries:
            if not isinstance(container, dict):
                raise common.DeployError(f"{group} entries must be maps")
            check_lists(
                container,
                ("env", "envFrom", "volumeMounts"),
                f"container {container.get('name', '<unnamed>')!r} ({group})",
            )
            found.append((group, container))
    return found


def check_lists(item, keys, where):
    """Fields every step iterates over must be lists of maps when present."""
    for key in keys:
        value = item.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
            raise common.DeployError(f"{where}: {key} must be a list of maps")


def check_pod_specs(documents, source="manifests"):
    """Validate offline pull policy and mounts within each pod specification."""
    for _, spec in pod_specs(documents, source):
        volumes = {
            volume.get("name")
            for volume in spec.get("volumes", [])
            if isinstance(volume, dict)
        }
        for group, container in containers(spec):
            name = container.get("name", "<unnamed>")
            if container.get("imagePullPolicy") != "Never":
                raise common.DeployError(
                    f"Container {name!r} ({group}) must use imagePullPolicy: Never"
                )
            for mount in container.get("volumeMounts", []):
                if not isinstance(mount, dict) or mount.get("name") not in volumes:
                    raise common.DeployError(
                        f"Container {name!r} ({group}) mounts an undefined volume: {mount.get('name') if isinstance(mount, dict) else mount!r}"
                    )


def check_component_names(documents, component, source):
    """Reject unsupported kinds and unprefixed resources before any writes."""
    check_kinds(documents, source)
    for doc in documents:
        if doc is None:
            continue
        name = (doc.get("metadata") or {}).get("name")
        if (
            not isinstance(name, str)
            or not name.startswith(component + "-")
            or not common.ID.fullmatch(name)
        ):
            raise common.DeployError(
                f"{source}: {doc['kind']} name must start with {component}- and be a valid resource name"
            )


def check_component_config_names(config, component, path):
    """Validate every configured Secret/PVC prefix without generating any files."""
    for group, kind in (
        (common.SECRET_FILES, "Secret"),
        (common.VOLUME_FILES, "PersistentVolumeClaim"),
    ):
        mapping = config.get(group, {})
        if not isinstance(mapping, dict):
            raise common.DeployError(f"{group} in {path} must be a map")
        check_component_names(
            [{"kind": kind, "metadata": {"name": name}} for name in mapping],
            component,
            path,
        )


def check_imported_mounted(documents, imported, path):
    """Each received registration volume must be mounted, not only declared.

    check_links proves a Pod volume references the PVC; a volume that no
    container mounts would pass that check while the registrations never
    reach the application.
    """
    for name in sorted(imported):
        mounted = False
        for _, spec in pod_specs(documents):
            volumes = {
                volume.get("name")
                for volume in spec.get("volumes", [])
                if (volume.get("persistentVolumeClaim") or {}).get("claimName") == name
            }
            mounted = mounted or any(
                mount.get("name") in volumes
                for _, container in containers(spec)
                for mount in container.get("volumeMounts", [])
            )
        if not mounted:
            raise common.DeployError(
                f"{path}: this component receives registrations in volume {name}; "
                "mount it with volumeMounts in a container of the Pod that declares it"
            )


def effective_config(config, path, component, env_overrides=None):
    """Validate a component's config; add PUBLIC_HOSTNAME and ENVIRONMENT/MOUNTS recipes; no writes.

    The result is transient: validation and materialization use it, nobody
    writes it to config.yaml. env_overrides (environment.Overrides: dev's
    overrides block, or the target environment file of --environment; None
    without either) must be the same value effective_documents receives.
    """
    validate_component_config(config, component, path)
    derived = with_client_settings(with_derived(config, path), component)
    with_environment = environment.with_recipes(derived, component, env_overrides)
    return mounts.with_recipes(with_environment, component)


def declared_volume_names(config, path, imported):
    """Return the Secret and PVC names that config and registration imports provide."""
    try:
        secrets = sorted(
            set(file_group_sources(config, common.SECRET_FILES))
            | set(templates.declarations(config))
        )
        volumes = file_group_sources(config, common.VOLUME_FILES)
    except common.DeployError as error:
        raise common.DeployError(f"{path}: {error}") from None
    return secrets, sorted(set(volumes) | set(imported))


def configmap_data(original, rendered, config):
    """Compose only original ConfigMap data strings; retain whole-value behavior.

    Looking at the original prevents treating a config value inserted by replace()
    as another recipe. Other manifest fields keep replace()'s existing semantics.
    """
    data = rendered.get("data") or {}
    if not isinstance(data, dict):
        raise common.DeployError("ConfigMap.data must be a map")
    original_data = original.get("data")
    result = {}
    for key, value in data.items():
        text = original_data.get(key) if isinstance(original_data, dict) else None
        if isinstance(text, str) and not common.PH.fullmatch(text):
            where = (
                f"ConfigMap {rendered.get('metadata', {}).get('name')} data key {key}"
            )
            value = templates.config_text(text, config, where)
        result[str(key)] = str(value)
    return result


def named_containers(documents):
    """Map each container name (regular or init) to its (pod spec, container) pairs."""
    found = {}
    for _, spec in pod_specs(documents):
        for _, container in containers(spec):
            found.setdefault(container.get("name"), []).append((spec, container))
    return found


def check_unresolved(value):
    """Refuse a placeholder replace() cannot fill, read from the source text.

    The source is checked, not the output: escaped @@@@ is a literal @@ in
    the output and must stay allowed there. A placeholder works as a whole
    value ("@@NAME@@", "@@$NAME@@") and, embedded, only in ConfigMap data,
    which configmap_data composes (and checks) itself.
    """
    if isinstance(value, dict):
        configmap = value.get("kind") == "ConfigMap"
        for key, item in value.items():
            if not (configmap and key == "data"):
                check_unresolved(item)
    elif isinstance(value, list):
        for item in value:
            check_unresolved(item)
    elif isinstance(value, str):
        whole = common.PH.fullmatch(value) or (
            value.startswith("@@$") and value.endswith("@@") and value.count("@@") == 2
        )
        if not whole and (templates.malformed(value) or templates.placeholders(value)):
            raise common.DeployError(
                'Unreplaced @@...@@. Only whole values like "@@NAME@@" are '
                "supported; write @@@@ for a literal @@."
            )


def effective_documents(
    config,
    path,
    manifests,
    component=None,
    imported=(),
    imported_secrets=(),
    env_overrides=None,
):
    """Return the manifests as they will be installed, fully validated, without writes.

    Everything that can be decided from declarations is checked here, before
    any secret is generated: kinds, placeholders, resource names (after
    substitution), pull policies, mounts, duplicates and the links between
    manifests, config, imported registration volumes and registration Secrets
    (by name). A registration Secret (accepts.apis) is rendered by the platform,
    so config must not declare the same name. env_overrides: as for
    effective_config.
    """
    # Standalone prepare/install/validate load_config directly, without going
    # through effective_config; do not rely on prior component config validation.
    check_component_file_sources(config, component)
    check_templates(config, path, component)
    documents, sources = [], []
    for manifest in sorted(manifests.glob("*.yaml")):
        original = load_manifest(manifest)
        check_kinds(original, manifest)
        original = [document for document in original if document is not None]
        try:
            rendered = [replace(document, config) for document in original]
            check_pod_specs(rendered, str(manifest))
            for before, doc in zip(original, rendered):
                if isinstance(doc, dict) and doc["kind"] == "ConfigMap":
                    doc["data"] = configmap_data(before, doc, config)
            check_unresolved(original)
        except common.DeployError as error:
            raise common.DeployError(f"{manifest} (config {path}): {error}") from None
        if component:
            check_component_names(rendered, component, manifest)
        documents += rendered
        sources += [manifest] * len(rendered)
    if component:
        documents, sources = environment.apply(
            documents,
            sources,
            config,
            component,
            named_containers(documents),
            env_overrides,
        )
        mounts.apply(documents, component, named_containers(documents))

    imported = set(imported)
    secrets, volumes = declared_volume_names(config, path, imported)
    for name in sorted(imported_secrets):
        if name in secrets or name in volumes:
            raise common.DeployError(
                f"{path}: {name} is the registration Secret this component accepts "
                "(accepts in bundles.yaml); the platform renders it, so do not "
                "declare it in config"
            )
    declared = [
        {"kind": "Secret", "metadata": {"name": i}}
        for i in secrets + sorted(imported_secrets)
    ] + [{"kind": "PersistentVolumeClaim", "metadata": {"name": i}} for i in volumes]
    from_config = {
        ("Secret", i): f"{common.SECRET_FILES}.{i} in config.yaml" for i in secrets
    }
    from_config.update(
        {
            ("Secret", i): f"Registration Secret {i} (accepts in bundles.yaml)"
            for i in imported_secrets
        }
    )
    from_config.update(
        {
            ("PersistentVolumeClaim", i): (
                f"Imported volume {i} (accepts in bundles.yaml)"
                if i in imported
                else f"{common.VOLUME_FILES}.{i} in config.yaml"
            )
            for i in volumes
        }
    )
    try:
        check_links(
            declared + documents,
            from_config,
            [None] * len(declared) + sources,
            templates.references(config),
        )
    except common.DeployError as error:
        raise common.DeployError(f"{path}: {error}") from None
    check_imported_mounted(documents, imported, path)
    return documents


def materialize(
    config,
    path,
    documents,
    files_dir,
    extra_volumes=None,
    component=None,
    extra_secrets=(),
):
    """Create allowed missing secrets and return the install YAML and import volumes.

    Call only with effective_documents() output and after the database preflight.
    Checks that need the files themselves (missing, empty or oversized sources)
    necessarily run here, after generation. Secret keys the pods select are
    checked first, from file names and generate declarations. extra_secrets
    are the registration Secret documents the component accepts.
    """
    check_component_file_sources(config, component)
    check_secret_keys(config, path, documents, component)
    generate_secrets(config, path.parent)
    secrets = load_file_group(config, common.SECRET_FILES, path.parent, component)
    # Imported registration volumes replace a same-named VOLUME_FILES entry.
    volume_config = dict(config)
    volume_config[common.VOLUME_FILES] = {
        key: entries
        for key, entries in config.get(common.VOLUME_FILES, {}).items()
        if key not in (extra_volumes or {})
    }
    volumes = load_file_group(
        volume_config, common.VOLUME_FILES, path.parent, component
    )
    volumes.update(extra_volumes or {})
    file_secrets = secret_documents(secrets)
    docs = (
        file_secrets
        + templates.documents(config, file_secrets)
        + list(extra_secrets)
        + volume_claims(volumes, files_dir)
        + documents
    )
    return yaml.safe_dump_all(docs, sort_keys=False), volumes


def find_images(documents):
    """Find unique, fully qualified images in pod specs."""
    images = set()
    for _, spec in pod_specs(documents):
        for key, container in containers(spec):
            image = container.get("image")
            container_name = container.get("name", "<unnamed>")
            where = f"container {container_name!r} ({key})"
            if not isinstance(image, str) or not image.strip():
                raise common.DeployError(
                    f"Container must have an image name as a string: {where}"
                )
            if "@@" in image:
                raise common.DeployError(
                    f"Image {image}: placeholders are not supported in {where}"
                )
            registry, separator, name = image.partition("/")
            if (
                not separator
                or not name
                or not ("." in registry or ":" in registry or registry == "localhost")
            ):
                raise common.DeployError(
                    f"Image {image} must be fully qualified in {where}"
                )
            images.add(image)
    if not images:
        raise common.DeployError("No images found in the manifests")
    return sorted(images)
