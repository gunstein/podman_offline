"""env/<container>.yaml: one container's environment in one flat file (backlog 77).

A line without a secret reference becomes data of the generated ConfigMap
<component>-<container>-env; a line with one becomes a key of the generated
Secret <component>-<container>-env-secret, composed by an ordinary
SECRET_TEMPLATES recipe. The platform adds envFrom for both to the container.

The recipes exist only in the transient effective config (with_recipes, from
render.effective_config) that validation and materialization both use; they
are never written to the operator's config.yaml. The ConfigMaps and envFrom
entries are added to the effective documents (apply, from
render.effective_documents) before the existing link and secret checks, so
those checks run unchanged.
"""

import re

from . import common, templates

KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\Z")
API_SECRET = re.compile(r"@@api-secret:([^@]*)@@")
# The generated value an API shares with Identity (backlog 77, section 5).
API_SOURCE_PATH = "credentials/api-secret"
# The platform reads these from a container's manifest env, never from envFrom:
# the PostgreSQL layout check (deploy.postgres_binding) and the client.yaml
# identity check (registrations.check_client_identity).
DATABASE_PREFIX = "POSTGRES_PASSWORD"


def directory(component):
    return common.ROOT / "components" / component / "env"


def configmap_name(component, container):
    return f"{component}-{container}-env"


def secret_name(component, container):
    return f"{component}-{container}-env-secret"


def api_source(component):
    """The internal SECRET_FILES ID of an API's own generated secret."""
    return f"{component}-api-secret"


def api_secret_lines(folder):
    """[(container, key, value, [referenced IDs])] for @@api-secret: lines in folder/env."""
    return [
        (container, key, value, API_SECRET.findall(value))
        for container, values in read_folder(folder / "env").items()
        for key, value in values.items()
        if isinstance(value, str) and "@@api-secret:" in value
    ]


def read(component):
    """Return {container: {key: value}} from the component's env/ files; no secrets read."""
    return read_folder(directory(component))


def read_folder(folder):
    """read() for an explicit env/ folder (the catalog may read another root)."""
    from . import render as rendering  # render imports this module.

    if not folder.exists() and not folder.is_symlink():
        return {}
    if folder.is_symlink() or not folder.is_dir():
        raise common.DeployError(f"{folder} must be a directory")
    files = {}
    for path in sorted(folder.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix != ".yaml":
            raise common.DeployError(f"{path}: env/ holds only <container>.yaml files")
        values = rendering.config_layer(path)  # Duplicate keys are refused here.
        if not values:
            raise common.DeployError(f"{path} is empty; remove it or add settings")
        seen = {}
        for key, value in values.items():
            if not isinstance(key, str) or ":" in key:
                raise common.DeployError(
                    f"{path}: {key!r} is not a variable name; use __ instead of :"
                )
            if not KEY.fullmatch(key):
                raise common.DeployError(
                    f"{path}: {key!r} is not a variable name (letters, digits, "
                    "_, -, ., not starting with a digit)"
                )
            # .NET reads configuration keys case-insensitively.
            if key.lower() in seen:
                raise common.DeployError(
                    f"{path}: {seen[key.lower()]} and {key} differ only in case"
                )
            seen[key.lower()] = key
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise common.DeployError(
                    f"{path}: {key} must be text or an integer; quote it"
                )
            if key.startswith(DATABASE_PREFIX):
                raise common.DeployError(
                    f"{path}: {key} is checked by the platform's database layout "
                    "check; keep it in the manifest's env"
                )
        files[path.stem] = values
    return files


def receives_api_secret(value, component):
    """Identity's line for another component's API secret (the platform injects it)."""
    return isinstance(value, str) and any(
        api != component for api in API_SECRET.findall(value)
    )


def own_api_secret(value, component):
    """An API's own placeholder as the long reference to its generated source."""
    if not isinstance(value, str):
        return value
    return value.replace(
        f"@@api-secret:{component}@@", f"@@secret:{api_source(component)}/value@@"
    )


def is_secret_line(value, where):
    return isinstance(value, str) and any(
        group is not None for _, group, _ in templates.tokens(value, where)
    )


def with_recipes(config, component):
    """Return config plus one synthetic recipe per container with secret lines.

    An API also gets its generated source SECRET_FILES.<component>-api-secret
    at credentials/api-secret/value. Identity's lines for other components'
    API secrets get no recipe: the platform renders <identity>-apis.
    """
    files = read(component)
    if not files:
        return config
    result = dict(config)
    values_used = [value for values in files.values() for value in values.values()]
    if any(
        isinstance(value, str) and f"@@api-secret:{component}@@" in value
        for value in values_used
    ):
        sources = dict(config.get(common.SECRET_FILES) or {})
        for name, entries in sources.items():
            paths = [entry.get("path") for entry in entries if isinstance(entry, dict)]
            if name == api_source(component) or API_SOURCE_PATH in paths:
                raise common.DeployError(
                    f"{common.SECRET_FILES}.{name}: {API_SOURCE_PATH} is the API "
                    f"secret the platform generates for @@api-secret:{component}@@ "
                    f"(internal ID {api_source(component)}); remove or rename it"
                )
        sources[api_source(component)] = [
            {"path": API_SOURCE_PATH, "generate": ["value"]}
        ]
        result[common.SECRET_FILES] = sources
    recipes = dict(config.get(common.SECRET_TEMPLATES) or {})
    for container, values in files.items():
        where = f"components/{component}/env/{container}.yaml"
        secret = {
            key: own_api_secret(value, component)
            for key, value in values.items()
            if not receives_api_secret(value, component)
            and is_secret_line(own_api_secret(value, component), f"{where}: {key}")
        }
        if not secret:
            continue
        name = secret_name(component, container)
        if name in recipes:
            raise common.DeployError(
                f"SECRET_TEMPLATES.{name} is the Secret {where} generates; "
                "rename the recipe"
            )
        recipes[name] = secret
    result[common.SECRET_TEMPLATES] = recipes
    return result


def apply(documents, sources, config, component, path, client_variables=()):
    """Add the generated ConfigMaps and envFrom entries to the effective documents.

    config is the effective config (with derived settings and recipes).
    Returns the new documents and sources lists.
    """
    from . import render as rendering

    files = read(component)
    if not files:
        return documents, sources
    found = {}
    for _, spec in rendering.pod_specs(documents):
        for _, container in rendering.containers(spec):
            found.setdefault(container.get("name"), []).append(container)
    documents, sources = list(documents), list(sources)
    for container_name, values in files.items():
        where = f"components/{component}/env/{container_name}.yaml"
        matches = found.get(container_name, [])
        if len(matches) != 1:
            raise common.DeployError(
                f"{where}: the component must have exactly one container named "
                f"{container_name}; it has {len(matches)}"
            )
        container = matches[0]
        if container.get("envFrom"):
            raise common.DeployError(
                f"{where}: container {container_name} also has envFrom; use "
                f"env/{container_name}.yaml or keep the container's hand-written "
                "envFrom, not both"
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
            if receives_api_secret(value, component):
                receives = True  # The value arrives in <identity>-apis.
                continue
            value = own_api_secret(value, component)
            if is_secret_line(value, f"{where}: {key}"):
                continue
            text = templates.config_text(str(value), config, f"{where}: {key}")
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
            sources.append(directory(component) / (container_name + ".yaml"))
            env_from.append({"configMapRef": {"name": name}})
        if secret_name(component, container_name) in (
            config.get(common.SECRET_TEMPLATES) or {}
        ):
            env_from.append(
                {"secretRef": {"name": secret_name(component, container_name)}}
            )
        if receives:
            # The registration Secret the platform renders (accepts.apis).
            env_from.append({"secretRef": {"name": component + "-apis"}})
    return documents, sources


def summary(component, config):
    """One validate line per env/ file, with names and counts, never values."""
    lines = []
    recipes = config.get(common.SECRET_TEMPLATES) or {}
    for container, values in read(component).items():
        name = secret_name(component, container)
        secret = recipes.get(name, {})
        received = [v for v in values.values() if receives_api_secret(v, component)]
        parts = []
        settings = len(values) - len(secret) - len(received)
        if settings:
            parts.append(
                f"{settings} settings "
                f"(ConfigMap {configmap_name(component, container)})"
            )
        if received:
            parts.append(f"{len(received)} API secrets (Secret {component}-apis)")
        if secret:
            used = sorted(
                {
                    group
                    for key, text in secret.items()
                    for _, group, _ in templates.tokens(text, key)
                    if group is not None
                }
            )
            parts.append(f"{len(secret)} secret (Secret {name}: {', '.join(used)})")
        lines.append(
            f"{component}/{container}: env/{container}.yaml -> " + ", ".join(parts)
        )
    return lines
