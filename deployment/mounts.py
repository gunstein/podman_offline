"""MOUNTS in config.defaults.yaml: release files mounted into containers (backlog 77).

MOUNTS maps a container name to the files it gets:

    MOUNTS:
      migrate:
        /sql/10-roles.sql: sql/10-roles.sql   # path in the container: file under files/

The file is a template under components/<id>/files/. @@NAME@@ (a setting) and
@@secret:<id>/<key>@@ (the component's own SECRET_FILES) are filled in at
install, as in ENVIRONMENT. Like ENVIRONMENT, MOUNTS ships with the release and
is never copied to the operator's config.yaml (render.merge_config).

The rendered files of one container go into the generated Secret
<component>-<container>-files, because they may hold a password. The platform
adds a volume to the container's Pod and mounts each file read-only at its path.
As with ENVIRONMENT, the Secret is an internal SECRET_TEMPLATES recipe that
exists only in the transient effective config (with_recipes), and the volume is
added to the effective documents (apply) before the usual link checks.
"""

import posixpath

from . import common, environment, templates

# One part of a container path, and a file name: letters, digits and -._ only.
SAFE_PATH = common.SECRET_KEY


def secret_name(component, container):
    return f"{component}-{container}-files"


def volume_name(container):
    return f"{container}-files"


def read(component):
    """Return {container: {container path: file under files/}}; nothing rendered."""
    return read_defaults(environment.defaults_path(component), component)


def read_defaults(path, component):
    if not path.is_file():
        return {}
    document = environment.load(path)
    if not isinstance(document, dict) or common.MOUNTS not in document:
        return {}
    containers = document[common.MOUNTS]
    where = f"{path}: {common.MOUNTS}"
    if not isinstance(containers, dict) or not containers:
        raise common.DeployError(f"{where} must map each container name to its files")
    files = path.parent / "files"
    result = {}
    for container, mounts in containers.items():
        here = f"{where}.{container}"
        if not common.ID.fullmatch(container):
            raise common.DeployError(f"{where}: {container!r} is not a container name")
        if not isinstance(mounts, dict) or not mounts:
            raise common.DeployError(
                f"{here} must hold /path/in/container: file/under/files lines"
            )
        names = {}
        for target, source in mounts.items():
            if (
                not target.startswith("/")
                or posixpath.normpath(target) != target
                or target == "/"
                or not all(SAFE_PATH.fullmatch(part) for part in target[1:].split("/"))
            ):
                raise common.DeployError(
                    f"{here}: {target!r} is not an absolute path in the container"
                )
            if (
                not isinstance(source, str)
                or source.startswith("/")
                or posixpath.normpath(source) != source
                or source.split("/")[0] == ".."
            ):
                raise common.DeployError(
                    f"{here}.{target}: write a file under "
                    f"components/{component}/files/, for example sql/10-roles.sql"
                )
            file = files / source
            if file.is_symlink() or not file.is_file():
                raise common.DeployError(
                    f"{here}.{target}: components/{component}/files/{source} "
                    "is missing or not a regular file"
                )
            key = posixpath.basename(source)
            if not SAFE_PATH.fullmatch(key):
                raise common.DeployError(
                    f"{here}.{target}: name the file with letters, digits and -._ only"
                )
            if key in names and names[key] != source:
                raise common.DeployError(
                    f"{here}: {names[key]} and {source} have the same file name; "
                    "rename one"
                )
            names[key] = source
        result[container] = dict(mounts)
    return result


def file_text(component, source, where):
    path = environment.defaults_path(component).parent / "files" / source
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise common.DeployError(f"{where}: {path} is not UTF-8 text") from None


def with_recipes(config, component):
    """Return config plus one recipe per MOUNTS container; no secret is read."""
    containers = read(component)
    if not containers:
        return config
    declared = sorted(config.get(common.SECRET_FILES) or {})
    recipes = dict(config.get(common.SECRET_TEMPLATES) or {})
    for container, mounts in containers.items():
        recipe = {}
        for target, source in mounts.items():
            where = (
                f"components/{component}/config.defaults.yaml: "
                f"MOUNTS.{container}.{target}"
            )
            text = file_text(component, source, where)
            for match, group, field in templates.tokens(text, f"{where}: {source}"):
                if group is None:
                    if field not in config:
                        raise common.DeployError(
                            f"{where}: {source} uses {match[0]}, which is not a "
                            "setting of this component"
                        )
                elif not group.startswith(component + "-"):
                    raise common.DeployError(
                        f"{where}: {source} uses {group}, another component's "
                        f"secret; use only {component}'s own"
                    )
                elif group not in declared:
                    raise common.DeployError(
                        f"{where}: {source}: SECRET_FILES has no {group}; declared: "
                        + (", ".join(declared) or "none")
                    )
            recipe[posixpath.basename(source)] = text
        recipes[secret_name(component, container)] = recipe
    result = dict(config)
    result[common.SECRET_TEMPLATES] = recipes
    return result


def apply(documents, component, pods):
    """Add each MOUNTS container's volume and read-only file mounts in place.

    pods maps each container name to the matching (pod spec, container) pairs.
    """
    for container_name, mounts in read(component).items():
        where = f"components/{component}/config.defaults.yaml: MOUNTS.{container_name}"
        matches = pods.get(container_name, [])
        if len(matches) != 1:
            raise common.DeployError(
                f"{where}: the component must have exactly one container named "
                f"{container_name}; it has {len(matches)}"
            )
        spec, container = matches[0]
        volume = volume_name(container_name)
        if any(item.get("name") == volume for item in spec.get("volumes", [])):
            raise common.DeployError(
                f"{where}: the Pod already has a volume named {volume}; rename it"
            )
        used = {item.get("mountPath") for item in container.get("volumeMounts", [])}
        keys = []
        for target, source in mounts.items():
            if target in used:
                raise common.DeployError(
                    f"{where}: {target} is also a volumeMount in the manifest"
                )
            key = posixpath.basename(source)
            if key not in keys:
                keys.append(key)
            container.setdefault("volumeMounts", []).append(
                {"name": volume, "mountPath": target, "subPath": key, "readOnly": True}
            )
        spec.setdefault("volumes", []).append(
            {
                "name": volume,
                "secret": {
                    "secretName": secret_name(component, container_name),
                    "items": [{"key": key, "path": key} for key in keys],
                },
            }
        )
    return documents


def summary(component, config):
    """One validate line per MOUNTS container: paths and secret IDs, never values."""
    lines = []
    for container, mounts in read(component).items():
        name = secret_name(component, container)
        texts = (config.get(common.SECRET_TEMPLATES) or {}).get(name, {}).values()
        used = sorted(
            {group for text in texts for group in environment.secret_ids(text)}
        )
        lines.append(
            f"{component}/{container}: MOUNTS -> {', '.join(mounts)} "
            f"(Secret {name}" + (f": {', '.join(used)})" if used else ")")
        )
    return lines
