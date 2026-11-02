"""MOUNTS in config.defaults.yaml: files mounted into containers (backlogs 77, 80).

MOUNTS maps a container name to its files, each a path in the container and
one of two kinds of source:

    MOUNTS:
      migrate:
        /sql/10-roles.sql: sql/10-roles.sql                      # 1. component file
        /run/secrets/ca.crt: '@@secret:shop-trust-chain/ca.crt@@'  # 2. secret file

1. A component file is a template under components/<id>/files/. @@NAME@@ (a
   setting) and @@secret:<id>/<key>@@ (the component's own SECRET_FILES) are
   filled in at install, as in ENVIRONMENT. The rendered files of one container
   go into the generated Secret <component>-<container>-files, because they may
   hold a password: an internal SECRET_TEMPLATES recipe that exists only in the
   transient effective config (with_recipes).
2. A secret file is exactly one whole reference to a key of one of the
   component's own SECRET_FILES. Nothing is rendered: the existing Secret is
   mounted itself, so the bytes arrive unchanged (a PFX or a trailing newline
   too).

secret_reference() tells the two apart. For both, the platform adds a volume
to the container's Pod and mounts each file read-only at its path (apply),
before the usual link and key checks. Like ENVIRONMENT, MOUNTS ships with the
release and is never copied to the operator's config.yaml (render.merge_config).
"""

import posixpath

from . import common, environment, templates

# One part of a container path, and a file name: letters, digits and -._ only.
SAFE_PATH = common.SECRET_KEY


def secret_name(component, container):
    return f"{component}-{container}-files"


def volume_name(container):
    return f"{container}-files"


def secret_volume_name(secret_id):
    """The Pod volume of a SECRET_FILES Secret mounted through MOUNTS."""
    return f"{secret_id}-mount"


def secret_reference(source):
    """(secret ID, key) when source is exactly @@secret:<id>/<key>@@, else None.

    None means a component file under files/ (read_defaults checks it).
    """
    if not (
        isinstance(source, str) and source.startswith("@@") and source.endswith("@@")
    ):
        return None
    match = templates.SECRET_REF.fullmatch(source[2:-2])
    return (match[1], match[2]) if match else None


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
            reference = secret_reference(source)
            if (
                not target.startswith("/")
                or posixpath.normpath(target) != target
                or target == "/"
                or not all(SAFE_PATH.fullmatch(part) for part in target[1:].split("/"))
            ):
                raise common.DeployError(
                    f"{here}: {target!r} is not an absolute path in the container"
                )
            if reference:
                if not reference[0].startswith(component + "-"):
                    raise common.DeployError(
                        f"{here}.{target}: {reference[0]} is another component's "
                        f"secret; mount only {component}'s own SECRET_FILES"
                    )
                continue
            if isinstance(source, str) and "@@" in source:
                raise common.DeployError(
                    f"{here}.{target}: a secret file is exactly one whole reference "
                    f"'@@secret:<secret-id>/<key>@@' to {component}'s own SECRET_FILES; "
                    "anything else is a file under "
                    f"components/{component}/files/"
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
            file = common.component_file(component, source, path.parents[2])
            if not file.is_file():
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
    path = common.component_file(component, source)
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
            reference = secret_reference(source)
            if reference:
                # A secret file is mounted from its own Secret by apply();
                # it is never read or rendered here.
                if reference[0] not in declared:
                    raise common.DeployError(
                        f"{where}: SECRET_FILES has no {reference[0]}; declared: "
                        + (", ".join(declared) or "none")
                        + ". Declare it in SECRET_FILES or fix the ID"
                    )
                continue
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
        if recipe:
            recipes[secret_name(component, container)] = recipe
    result = dict(config)
    result[common.SECRET_TEMPLATES] = recipes
    return result


def apply(documents, component, pods):
    """Add each MOUNTS container's volumes and read-only file mounts in place.

    pods maps each container name to the matching (pod spec, container) pairs.
    Component files come from the container's generated Secret; a secret file
    comes from its own SECRET_FILES Secret, one volume per Secret and Pod,
    shared by the containers of that Pod that mount it.
    """
    added = {}  # (id of the Pod spec, volume name) -> volume this function added
    for container_name, mounts in read(component).items():
        where = f"components/{component}/config.defaults.yaml: MOUNTS.{container_name}"
        matches = pods.get(container_name, [])
        if len(matches) != 1:
            raise common.DeployError(
                f"{where}: the component must have exactly one container named "
                f"{container_name}; it has {len(matches)}"
            )
        spec, container = matches[0]
        used = {item.get("mountPath") for item in container.get("volumeMounts", [])}
        for target in mounts:
            if target in used:
                raise common.DeployError(
                    f"{where}: {target} is also a volumeMount in the manifest; "
                    "remove one of them"
                )
        files = {
            target: source
            for target, source in mounts.items()
            if secret_reference(source) is None
        }
        if files:
            add_component_files(
                spec, container, component, container_name, files, where
            )
        for target, source in mounts.items():
            reference = secret_reference(source)
            if reference is None:
                continue
            secret_id, key = reference
            name = secret_volume_name(secret_id)
            volume = added.get((id(spec), name))
            if volume is None:
                if any(item.get("name") == name for item in spec.get("volumes", [])):
                    raise common.DeployError(
                        f"{where}: the Pod already has a volume named {name}; rename it"
                    )
                volume = {
                    "name": name,
                    "secret": {"secretName": secret_id, "items": []},
                }
                spec.setdefault("volumes", []).append(volume)
                added[(id(spec), name)] = volume
            items = volume["secret"]["items"]
            if {"key": key, "path": key} not in items:
                items.append({"key": key, "path": key})
            container.setdefault("volumeMounts", []).append(
                {"name": name, "mountPath": target, "subPath": key, "readOnly": True}
            )
    return documents


def add_component_files(spec, container, component, container_name, files, where):
    """Mount a container's rendered component files from its generated Secret."""
    volume = volume_name(container_name)
    if any(item.get("name") == volume for item in spec.get("volumes", [])):
        raise common.DeployError(
            f"{where}: the Pod already has a volume named {volume}; rename it"
        )
    keys = []
    for target, source in files.items():
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


def summary(component, config):
    """One validate line per MOUNTS container: paths and secret IDs, never values."""
    lines = []
    for container, mounts in read(component).items():
        name = secret_name(component, container)
        texts = (config.get(common.SECRET_TEMPLATES) or {}).get(name, {}).values()
        used = sorted(
            {group for text in texts for group in environment.secret_ids(text)}
        )
        references = [secret_reference(source) for source in mounts.values()]
        parts = []
        if None in references:  # at least one component file
            parts.append(f"Secret {name}" + (f": {', '.join(used)}" if used else ""))
        direct = sorted({reference[0] for reference in references if reference})
        if direct:
            parts.append("unchanged from Secret " + ", ".join(direct))
        lines.append(
            f"{component}/{container}: MOUNTS -> {', '.join(mounts)} ({'; '.join(parts)})"
        )
    return lines
