"""ENVIRONMENT in config.defaults.yaml: each container's environment (backlog 77).

ENVIRONMENT maps a container name to its variables. It ships with the release
and is read only from the release's components/<id>/config.defaults.yaml;
init-config never copies it to the operator's config.yaml
(render.merge_config), so a new release always brings its own environment.

Every value is the text written in the file; YAML does not turn it into a
number or a boolean. A line without a secret reference becomes data of the
generated ConfigMap <component>-<container>-env; a line with one becomes a key
of the generated Secret <component>-<container>-env-secret, composed by an
ordinary SECRET_TEMPLATES recipe. The platform adds envFrom for both to the
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
# The platform reads these from a container's manifest env, never from envFrom:
# the PostgreSQL layout check (deploy.postgres_binding).
DATABASE_PREFIX = "POSTGRES_PASSWORD"

# One ENVIRONMENT line that names another component's secret.
ForeignLine = collections.namedtuple("ForeignLine", "container key value secrets")


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


def read(component):
    """Return {container: {key: text}} from the component's ENVIRONMENT; no secrets read."""
    return read_defaults(defaults_path(component))


def read_defaults(path):
    """read() for an explicit config.defaults.yaml (the catalog may read another root)."""
    if (path.parent / "env").exists():
        raise common.DeployError(
            f"{path.parent / 'env'} is no longer read: move each env/<container>.yaml "
            f"under ENVIRONMENT: <container>: in {path}, then remove env/"
        )
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as stream:
            document = yaml.load(stream, Loader=TextLoader)
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
                raise common.DeployError(
                    f"{where}: {key}: unknown placeholder {match[0]}; use "
                    "@@NAME@@ for a setting or @@secret:<id>/<key>@@ for a secret"
                )
        if key.startswith(DATABASE_PREFIX):
            raise common.DeployError(
                f"{where}: {key} is checked by the platform's database layout "
                "check; keep it in the manifest's env"
            )
    return values


def foreign_lines(directory):
    """[ForeignLine] for the ENVIRONMENT lines that name another component's secret."""
    component = directory.name
    return [
        ForeignLine(container, key, value, foreign_secrets(component, value))
        for container, values in read_defaults(
            directory / "config.defaults.yaml"
        ).items()
        for key, value in values.items()
        if foreign_secrets(component, value)
    ]


def is_secret_line(value):
    return bool(secret_ids(value))


def with_recipes(config, component):
    """Return config plus one recipe per ENVIRONMENT container with secret lines.

    A line naming another component's secret (Identity's API secret line) gets
    no recipe: the platform renders <identity>-apis for it.
    """
    environments = read(component)
    if not environments:
        return config
    declared = sorted(config.get(common.SECRET_FILES) or {})
    recipes = dict(config.get(common.SECRET_TEMPLATES) or {})
    for container, values in environments.items():
        where = f"components/{component}/config.defaults.yaml: ENVIRONMENT.{container}"
        secret = {}
        for key, value in values.items():
            if not is_secret_line(value) or foreign_secrets(component, value):
                continue
            for name in secret_ids(value):
                if name not in declared:
                    raise common.DeployError(
                        f"{where}: {key}: SECRET_FILES has no {name}; declared: "
                        + (", ".join(declared) or "none")
                    )
            secret[key] = value
        if not secret:
            continue
        name = secret_name(component, container)
        if name in recipes:
            raise common.DeployError(
                f"SECRET_TEMPLATES.{name} is the Secret {where} generates; "
                "rename the recipe"
            )
        recipes[name] = secret
    result = dict(config)
    result[common.SECRET_TEMPLATES] = recipes
    return result


def apply(documents, sources, config, component, containers, client_variables=()):
    """Add the generated ConfigMaps and envFrom entries to the effective documents.

    config is the effective config (with derived settings and recipes);
    containers maps each container name to the matching container dicts.
    Returns the new documents and sources lists.
    """
    environments = read(component)
    if not environments:
        return documents, sources
    documents, sources = list(documents), list(sources)
    for container_name, values in environments.items():
        where = (
            f"components/{component}/config.defaults.yaml: ENVIRONMENT.{container_name}"
        )
        matches = containers.get(container_name, [])
        if len(matches) != 1:
            raise common.DeployError(
                f"{where}: the component must have exactly one container named "
                f"{container_name}; it has {len(matches)}"
            )
        container = matches[0]
        if container.get("envFrom"):
            raise common.DeployError(
                f"{where}: container {container_name} also has envFrom; use "
                "ENVIRONMENT or the container's hand-written envFrom, not both"
            )
        manifest_names = {
            str(entry.get("name")).lower(): entry.get("name")
            for entry in container.get("env", [])
        }
        public, receives = {}, False
        for key, value in values.items():
            if key.lower() in manifest_names:
                raise common.DeployError(
                    f"{where}: {key} is also set in the manifest's env "
                    f"({manifest_names[key.lower()]}); keep it in one place"
                )
            if key in client_variables:
                raise common.DeployError(
                    f"{where}: {key} is compared with client.yaml; keep it in "
                    "the manifest's env"
                )
            if foreign_secrets(component, value):
                if not API_SECRET_KEY.fullmatch(key):
                    raise common.DeployError(
                        f"{where}: {key} names another component's secret; only "
                        "identity's ApiResources__<n>__ApiSecrets__0__Value may"
                    )
                receives = True  # The value arrives in <identity>-apis.
                continue
            if is_secret_line(value):
                continue
            text = templates.config_text(value, config, f"{where}: {key}")
            templates.check_text(text, f"{where}: {key}", "config")
            public[key] = text
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


def summary(component, config):
    """One validate line per container in ENVIRONMENT, with names and counts, never values."""
    lines = []
    recipes = config.get(common.SECRET_TEMPLATES) or {}
    for container, values in read(component).items():
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
