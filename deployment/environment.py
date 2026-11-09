"""ENVIRONMENT in config.defaults.yaml: each container's environment (backlog 77).

ENVIRONMENT maps a container name to its variables. It ships with the release
and is read only from the release's components/<id>/config.defaults.yaml;
init-config never copies it to the operator's config.yaml
(render.merge_config), so a new release always brings its own environment.

Every value is the text written in the file; YAML does not turn it into a
number or a boolean. A line without a secret reference becomes data of the
generated ConfigMap <component>-<container>-env; a line with one becomes a key
of the generated Secret <component>-<container>-env-secret, composed by an
internal SECRET_TEMPLATES recipe (deployment/templates.py). The platform adds envFrom for both to the
container.

The recipes exist only in the transient effective config (with_recipes, from
render.effective_config) that validation and materialization both use; they
are never written to the operator's config.yaml. The ConfigMaps and envFrom
entries are added to the effective documents (apply, from
render.effective_documents) before the existing link and secret checks, so
those checks run unchanged.

A component uses only its own secrets: Secret IDs start with the component ID
(render.check_component_names). The one exception is Identity's
ApiResources__<n>__ApiSecrets__0__Value line, which names an API component's
secret; the platform delivers that value in <identity>-apis (registrations).

Overrides (backlog 84): a build environment file config/<environment>.yaml,
or the overrides block of config/dev.yaml, adds or replaces single variables
of named containers (read_overrides). read() merges them into the common
declarations; every reader (catalog derivation, recipes, ConfigMaps, the
validate summary) receives the same Overrides value, or None for the common
declarations alone. A bundle carries the merged result in its own
config.defaults.yaml (bundle.compiled_defaults), so production reads no
override file and always passes None.
"""

import collections
import re

import yaml

from . import common, templates

KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\Z")
# The one Identity variable that receives another component's secret (Duende).
API_SECRET_KEY = re.compile(r"ApiResources__(0|[1-9][0-9]*)__ApiSecrets__0__Value\Z")
# Its value: exactly one secret reference, @@secret:<id>/<key>@@.
WHOLE_SECRET = re.compile(r"@@secret:([a-z0-9-]+/[-._a-zA-Z0-9]+)@@\Z")

# Settings derived from client.yaml (render.with_client_settings).
CLIENT_SETTINGS = {"CLIENT_ID": "id", "CLIENT_BASE_PATH": "base_path"}
# One ENVIRONMENT line that names another component's secret; source names
# the file it comes from, for error messages.
ForeignLine = collections.namedtuple(
    "ForeignLine", "container key value secrets source"
)
# The selected overrides: path is the file shown in messages (relative to the
# checkout), components maps component -> container -> variable -> text.
Overrides = collections.namedtuple("Overrides", "path components")
# config/dev.yaml and config/images.yaml have other meanings.
RESERVED_ENVIRONMENTS = ("dev", "images")
# Plain YAML scalars that mean null; quoted text such as 'null' is text.
NULL = re.compile(r"(~|null|Null|NULL|)\Z")


class TextLoader(yaml.BaseLoader):
    """Reads every value as the written text and rejects duplicate keys."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


class OverrideLoader(TextLoader):
    """TextLoader that returns None for a plain null, so overrides can refuse it.

    TextLoader reads `KEY:` and `KEY: null` as text ("" and "null"); an
    override must not turn a forgotten value into text, and there is no
    deletion syntax.
    """

    def construct_scalar(self, node):  # pyright: ignore[reportIncompatibleMethodOverride]
        if node.style is None and NULL.fullmatch(node.value):
            return None
        return super().construct_scalar(node)


def defaults_path(component):
    return common.ROOT / "components" / component / "config.defaults.yaml"


def configmap_name(component, container):
    return f"{component}-{container}-env"


def secret_name(component, container):
    return f"{component}-{container}-env-secret"


def owner_secret_name(component):
    """The Secret the platform renders for Identity's API secret lines."""
    return f"{component}-apis"


def secret_ids(value):
    """The SECRET_FILES IDs a value references with @@secret:<id>/<key>@@."""
    ids = []
    for match in templates.TOKEN.finditer(value):
        reference = templates.SECRET_REF.fullmatch(match[1])
        if reference:
            ids.append(reference[1])
    return ids


def foreign_secrets(component, value):
    """Secret IDs in value that belong to another component."""
    return [name for name in secret_ids(value) if not name.startswith(component + "-")]


def read(component, env_overrides=None):
    """Return {container: {key: text}}: ENVIRONMENT plus the selected overrides.

    No secrets are read. env_overrides is an Overrides value or None.
    """
    return merge(read_defaults(defaults_path(component)), component, env_overrides)


def merge(environments, component, env_overrides):
    """Add or replace single variables; every other variable stays as declared.

    A name that differs from a declared one only in case is refused: .NET
    reads both as the same key, and there is no rule for which one wins.
    """
    overrides = (env_overrides.components if env_overrides else {}).get(component)
    if not overrides:
        return environments
    result = {container: dict(values) for container, values in environments.items()}
    for container, values in overrides.items():
        target = result.setdefault(container, {})
        for key, value in values.items():
            for declared in target:
                if declared != key and declared.lower() == key.lower():
                    raise common.DeployError(
                        f"{env_overrides.path}: overrides.{component}.ENVIRONMENT."
                        f"{container}: {key} and {declared} "
                        f"(components/{component}/config.defaults.yaml) differ only "
                        "in case; use the declared spelling to replace it"
                    )
            target[key] = value
    return result


def where(component, container, env_overrides, key=None):
    """The file and place a container's (or one variable's) declaration comes from."""
    overrides = (env_overrides.components if env_overrides else {}).get(component, {})
    common_place = (
        f"components/{component}/config.defaults.yaml: ENVIRONMENT.{container}"
    )
    override_place = (
        f"{env_overrides.path}: overrides.{component}.ENVIRONMENT.{container}"
        if container in overrides
        else None
    )
    if key is not None:
        return (
            override_place
            if override_place and key in overrides[container]
            else common_place
        )
    if override_place and container in read_defaults(defaults_path(component)):
        return f"{common_place} with {override_place}"
    return override_place or common_place


def environment_file(root, name):
    """config/<name>.yaml of a build environment; the name is checked first."""
    # The product name's rule: name becomes config/<name>.yaml and dist/<name>/.
    if not common.PRODUCT.fullmatch(name):
        raise common.DeployError(
            f"--environment {name!r}: use lowercase letters, digits and inner "
            "hyphens, a letter first and at most 32 characters, for example prod1"
        )
    if name in RESERVED_ENVIRONMENTS:
        raise common.DeployError(
            f"--environment {name}: config/{name}.yaml has another meaning; "
            "choose another name"
        )
    path = root / "config" / (name + ".yaml")
    if path.is_symlink() or not path.is_file():
        raise common.DeployError(
            f"--environment {name}: missing file config/{name}.yaml"
        )
    return path


def read_environment_file(root, name):
    """The Overrides of config/<name>.yaml; its only top-level key is overrides."""
    path = environment_file(root, name)
    shown = f"config/{name}.yaml"
    document = load(path, OverrideLoader)
    if document is None:
        document = {}
    if not isinstance(document, dict):
        raise common.DeployError(f"{shown} must contain overrides:")
    for key in document:
        if key == "components":
            raise common.DeployError(
                f"{shown}: components: (an environment's component set, backlog "
                "85) is not implemented yet; remove it and build the whole catalog"
            )
        if key != common.OVERRIDES:
            raise common.DeployError(
                f"{shown}: {key!r} is not allowed; an environment file holds only "
                "overrides: <component>: ENVIRONMENT: <container>: <variables>"
            )
    return read_overrides(document.get(common.OVERRIDES, {}), shown)


def read_dev_overrides(path):
    """The Overrides of config/dev.yaml's reserved overrides block, or None."""
    if not (path.exists() or path.is_symlink()):
        return None
    document = load(path, OverrideLoader)
    if not isinstance(document, dict) or common.OVERRIDES not in document:
        return None
    return read_overrides(document[common.OVERRIDES], "config/dev.yaml")


def read_overrides(block, shown):
    """Check one overrides block and return Overrides; empty mappings have no effect.

    shown is the file name used in messages. Component IDs are checked
    against the catalog in catalog.load_catalog, containers against the
    manifests where the declarations are used (check_container).
    """
    check_mapping(block, shown, common.OVERRIDES, "each component to ENVIRONMENT")
    components = {}
    for component, entry in block.items():
        place = f"{common.OVERRIDES}.{component}"
        check_name(component, shown, common.OVERRIDES, "component ID")
        check_mapping(entry, shown, place, "ENVIRONMENT to its containers")
        unknown = sorted(str(key) for key in entry if key != common.ENVIRONMENT)
        if unknown:
            raise common.DeployError(
                f"{shown}: {place}: {', '.join(unknown)} cannot be overridden; an "
                "environment changes only ENVIRONMENT variables"
            )
        place += "." + common.ENVIRONMENT
        containers = entry.get(common.ENVIRONMENT, {})
        check_mapping(containers, shown, place, "each container to its variables")
        result = {}
        for container, values in containers.items():
            check_name(container, shown, place, "container name")
            here = f"{place}.{container}"
            if not isinstance(values, dict):
                raise common.DeployError(
                    f"{shown}: {here} must hold NAME: 'value' lines"
                )
            for key, value in values.items():
                if value is None:
                    raise common.DeployError(
                        f"{shown}: {here}: {key} has no value (YAML null); write "
                        f"{key}: '' for an empty value. There is no deletion: a "
                        "variable only some environments need belongs in their files"
                    )
            if values:
                result[container] = check_values(values, f"{shown}: {here}")
        if result:
            components[component] = result
    return Overrides(shown, components)


def check_mapping(value, shown, place, what):
    """An overrides level must be a mapping; null (an empty assignment) is refused."""
    if value is None:
        raise common.DeployError(
            f"{shown}: {place} is empty (YAML null); write {{}} or remove it"
        )
    if not isinstance(value, dict):
        raise common.DeployError(f"{shown}: {place} must map {what}")


def check_name(value, shown, place, what):
    """A component ID or container name in an overrides block."""
    if not isinstance(value, str) or not common.ID.fullmatch(value):
        raise common.DeployError(f"{shown}: {place}: {value!r} is not a {what}")


def load(path, loader=TextLoader):
    """The whole config.defaults.yaml with every value as written text."""
    try:
        with path.open(encoding="utf-8") as stream:
            return yaml.load(stream, Loader=loader)
    except UnicodeDecodeError:
        raise common.DeployError(f"{path} is not valid UTF-8") from None
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        line = f" at line {mark.line + 1}" if mark is not None else ""
        problem = getattr(error, "problem", "") or ""
        detail = problem if problem.startswith("duplicate key ") else "invalid YAML"
        raise common.DeployError(
            f"{path}{line}: {detail}; write NAME: 'value' and quote values "
            "that start with @@"
        ) from None


def read_defaults(path):
    """read() for an explicit config.defaults.yaml (the catalog may read another root)."""
    if not path.is_file():
        return {}
    document = load(path)
    if not isinstance(document, dict) or common.ENVIRONMENT not in document:
        return {}
    containers = document[common.ENVIRONMENT]
    where = f"{path}: {common.ENVIRONMENT}"
    if not isinstance(containers, dict) or not containers:
        raise common.DeployError(
            f"{where} must map each container name to its variables"
        )
    result = {}
    for container, values in containers.items():
        if not common.ID.fullmatch(container):
            raise common.DeployError(f"{where}: {container!r} is not a container name")
        result[container] = check_values(values, f"{where}.{container}")
    return result


def check_values(values, where):
    """Check one container's variables: names, one-line text and placeholders."""
    if not values or not isinstance(values, dict):
        raise common.DeployError(f"{where} must hold NAME: 'value' lines")
    seen = {}
    for key, value in values.items():
        if ":" in key:
            raise common.DeployError(
                f"{where}: {key!r} is not a variable name; use __ instead of :"
            )
        if not KEY.fullmatch(key):
            raise common.DeployError(
                f"{where}: {key!r} is not a variable name (letters, digits, "
                "_, -, ., not starting with a digit)"
            )
        # .NET reads configuration keys case-insensitively.
        if key.lower() in seen:
            raise common.DeployError(
                f"{where}: {seen[key.lower()]} and {key} differ only in case"
            )
        seen[key.lower()] = key
        if not isinstance(value, str):
            raise common.DeployError(
                f"{where}: {key} must be one line of text, not a list or map"
            )
        for match in templates.TOKEN.finditer(value):
            if not (
                templates.CONFIG_NAME.fullmatch(match[1])
                or templates.SECRET_REF.fullmatch(match[1])
            ):
                # Never repeat the text: a value pasted by mistake stays private.
                raise common.DeployError(
                    f"{where}: {key}: unknown or nested placeholder; use "
                    "@@NAME@@ for a setting or @@secret:<id>/<key>@@ for a secret"
                )
    return values


def foreign_lines(directory, env_overrides=None):
    """[ForeignLine] for the ENVIRONMENT lines that name another component's secret.

    The lines are the merged declarations, so an override of Identity's API
    secret lines reaches the catalog's api_secrets as well as the rendering.
    """
    component = directory.name
    environments = merge(
        read_defaults(directory / "config.defaults.yaml"), component, env_overrides
    )
    return [
        ForeignLine(
            container,
            key,
            value,
            foreign_secrets(component, value),
            where(component, container, env_overrides, key),
        )
        for container, values in environments.items()
        for key, value in values.items()
        if foreign_secrets(component, value)
    ]


def is_secret_line(value):
    return bool(secret_ids(value))


def with_recipes(config, component, env_overrides=None):
    """Return config plus one recipe per ENVIRONMENT container with secret lines.

    A line naming another component's secret (Identity's API secret line) gets
    no recipe: the platform renders <identity>-apis for it. Recipes are built
    from the merged declarations every time, so an override that turns a
    secret line into a public one (or back) leaves no stale recipe.
    """
    environments = read(component, env_overrides)
    if not environments:
        return config
    declared = sorted(config.get(common.SECRET_FILES) or {})
    recipes = dict(config.get(common.SECRET_TEMPLATES) or {})
    for container, values in environments.items():
        secret = {}
        for key, value in values.items():
            if not is_secret_line(value) or foreign_secrets(component, value):
                continue
            for name in secret_ids(value):
                if name not in declared:
                    raise common.DeployError(
                        f"{where(component, container, env_overrides, key)}: "
                        f"{key}: SECRET_FILES has no {name}; declared: "
                        + (", ".join(declared) or "none")
                    )
            secret[key] = value
        if not secret:
            continue
        recipes[secret_name(component, container)] = secret
    result = dict(config)
    result[common.SECRET_TEMPLATES] = recipes
    return result


def public_text(value, config, where):
    """Fill in @@NAME@@ settings; like a secret line, only inserted values are checked.

    The text around them is written by the release author and may contain
    anything, such as the ; of a connection string.
    """

    def resolve(group, field):
        inserted = templates.config_value(config, field, where)
        templates.check_text(inserted, where, field)
        return inserted

    return templates.substitute(value, resolve, where)


def check_container(component, container_name, values, containers, env_overrides):
    """The checks of one container's variables that need no config; returns it.

    The container must exist exactly once (regular or init container), have
    no hand-written envFrom, and not set the same variable in its manifest
    env. Only Identity's API secret line may name another component's secret.
    apply runs this on the rendered manifests; bundle.check_declarations on
    the manifests as written, before a build writes anything.
    """
    place = where(component, container_name, env_overrides)
    matches = containers.get(container_name, [])
    if len(matches) != 1:
        raise common.DeployError(
            f"{place}: the component must have exactly one container named "
            f"{container_name}; it has {len(matches)}"
        )
    _, container = matches[0]
    if container.get("envFrom"):
        raise common.DeployError(
            f"{place}: container {container_name} also has envFrom; use "
            "ENVIRONMENT or the container's hand-written envFrom, not both"
        )
    manifest_names = {
        str(entry.get("name")).lower(): entry.get("name")
        for entry in container.get("env", [])
    }
    for key, value in values.items():
        here = where(component, container_name, env_overrides, key)
        if key.lower() in manifest_names:
            raise common.DeployError(
                f"{here}: {key} is also set in the manifest's env "
                f"({manifest_names[key.lower()]}); keep it in one place"
            )
        if foreign_secrets(component, value) and not API_SECRET_KEY.fullmatch(key):
            raise common.DeployError(
                f"{here}: {key} names another component's secret; only "
                "identity's ApiResources__<n>__ApiSecrets__0__Value may"
            )
    return container


def apply(documents, sources, config, component, containers, env_overrides=None):
    """Add the generated ConfigMaps and envFrom entries to the effective documents.

    config is the effective config (with derived settings and recipes, from
    with_recipes with the same env_overrides); containers maps each container
    name to its (pod spec, container) pairs. Returns the new documents and
    sources lists.
    """
    environments = read(component, env_overrides)
    if not environments:
        return documents, sources
    documents, sources = list(documents), list(sources)
    for container_name, values in environments.items():
        container = check_container(
            component, container_name, values, containers, env_overrides
        )
        public, receives = {}, False
        for key, value in values.items():
            here = where(component, container_name, env_overrides, key)
            if foreign_secrets(component, value):
                receives = True  # The value arrives in <identity>-apis.
                continue
            if is_secret_line(value):
                continue
            for name in CLIENT_SETTINGS:
                if f"@@{name}@@" in value and name not in config:
                    raise common.DeployError(
                        f"{here}: {key}: @@{name}@@ comes from client.yaml, which "
                        f"components/{component} does not have"
                    )
            public[key] = public_text(value, config, f"{here}: {key}")
        env_from = container.setdefault("envFrom", [])
        if public:
            name = configmap_name(component, container_name)
            documents.append(
                {
                    "apiVersion": "v1",
                    "kind": "ConfigMap",
                    "metadata": {"name": name},
                    "data": public,
                }
            )
            sources.append(defaults_path(component))
            env_from.append({"configMapRef": {"name": name}})
        if secret_name(component, container_name) in (
            config.get(common.SECRET_TEMPLATES) or {}
        ):
            env_from.append(
                {"secretRef": {"name": secret_name(component, container_name)}}
            )
        if receives:
            env_from.append({"secretRef": {"name": owner_secret_name(component)}})
    return documents, sources


def summary(component, config, env_overrides=None):
    """One validate line per container in ENVIRONMENT, with names and counts, never values."""
    lines = []
    recipes = config.get(common.SECRET_TEMPLATES) or {}
    for container, values in read(component, env_overrides).items():
        name = secret_name(component, container)
        secret = recipes.get(name, {})
        received = [v for v in values.values() if foreign_secrets(component, v)]
        parts = []
        settings = len(values) - len(secret) - len(received)
        if settings:
            parts.append(
                f"{settings} settings "
                f"(ConfigMap {configmap_name(component, container)})"
            )
        if secret:
            used = sorted(
                {group for text in secret.values() for group in secret_ids(text)}
            )
            parts.append(f"{len(secret)} secret (Secret {name}: {', '.join(used)})")
        if received:
            parts.append(
                f"{len(received)} API secrets (Secret {owner_secret_name(component)}, "
                "each only while its API is installed)"
            )
        lines.append(f"{component}/{container}: ENVIRONMENT -> " + ", ".join(parts))
    return lines
