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


def read(component):
    """Return {container: {key: value}} from the component's env/ files; no secrets read."""
    from . import render as rendering  # render imports this module.

    folder = directory(component)
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


def is_secret_line(value, where):
    return isinstance(value, str) and any(
        group is not None for _, group, _ in templates.tokens(value, where)
    )


def with_recipes(config, component):
    """Return config plus one synthetic recipe per container with secret lines."""
    files = read(component)
    if not files:
        return config
    recipes = dict(config.get(common.SECRET_TEMPLATES) or {})
    for container, values in files.items():
        where = f"components/{component}/env/{container}.yaml"
        secret = {
            key: value
            for key, value in values.items()
            if is_secret_line(value, f"{where}: {key}")
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
    result = dict(config)
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
        public = {}
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
        if len(public) < len(values):
            env_from.append(
                {"secretRef": {"name": secret_name(component, container_name)}}
            )
    return documents, sources


def summary(component, config):
    """One validate line per env/ file, with names and counts, never values."""
    lines = []
    recipes = config.get(common.SECRET_TEMPLATES) or {}
    for container, values in read(component).items():
        name = secret_name(component, container)
        secret = recipes.get(name, {})
        parts = []
        if len(values) > len(secret):
            parts.append(
                f"{len(values) - len(secret)} settings "
                f"(ConfigMap {configmap_name(component, container)})"
            )
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
