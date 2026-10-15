"""Render Kubernetes YAML for Podman and install it as a Quadlet service.

./deploy prepare   Dev: write build/install.yaml (+ build/files/*.tar).

Files are listed in config.yaml under SECRET_FILES and VOLUME_FILES (id -> files).
./deploy install   Prod (service user): render, podman load, install Quadlet, restart.
"""

import base64
import json
import os
import pwd
import re
import secrets
import shutil
import ssl
import string
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import yaml

HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
MANIFESTS = ROOT / "manifests"
CONFIG = ROOT / "config.yaml"  # Standalone manifest fixtures only.

QUADLET_TEMPLATE = ROOT / "quadlet" / "myproduct.kube"
QUADLET_DIR = HOME / ".config/containers/systemd"
QUADLET_TARGET = QUADLET_DIR / "myproduct.kube"
QUADLET_YAML = QUADLET_DIR / "myproduct.yaml"  # Yaml=myproduct.yaml in .kube
SERVICE = "myproduct.service"

SECRET_FILES = "SECRET_FILES"
VOLUME_FILES = "VOLUME_FILES"
GENERATED_SECRETS = "GENERATED_SECRETS"

# Tar archives for VOLUME_FILES. Podman imports them into the volumes on every
# start, so they must stay in the service user's home directory.
FILES_DIR = HOME / "files"
IMPORT_SOURCE = "volume.podman.io/import-source"

ID = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
SECRET_KEY = re.compile(r"^[-._a-zA-Z0-9]+$")
# Podman rejects secrets over 512,000 bytes (the whole Secret document).
MAX_SECRET_SIZE = 500000

PH = re.compile(r"^@@([A-Z0-9_]+)@@$")
MAX_PORT = 65535


COMPONENTS = ("platform", "identity", "app1", "app2", "help")
DEPENDENCIES = {
    "platform": (),
    "identity": ("platform",),
    "app1": ("platform", "identity"),
    "app2": ("platform", "identity"),
    "help": ("platform",),
}
VERSION_FILES = {"platform": "PLATFORM_VERSION", "identity": "IDENTITY_VERSION"}


class DeployError(Exception):
    """Error shown as a single ERROR line without a traceback."""


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


def load_yaml(path):
    """Read one YAML document safely and reject duplicate keys."""
    with path.open(encoding="utf-8") as f:
        # A SafeLoader subclass rejects duplicates without allowing object construction.
        return yaml.load(f, Loader=UniqueKeyLoader)


def load_yaml_all(path):
    """Read all YAML documents safely and reject duplicate keys."""
    with path.open(encoding="utf-8") as f:
        return list(yaml.load_all(f, Loader=UniqueKeyLoader))


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
        raise DeployError(f"{path} must contain KEY: value pairs")

    return config


def validate_config(config, path):
    """Validate the complete config; individual merge layers may be incomplete."""
    for key, value in config.items():
        if not isinstance(key, str):
            raise DeployError(f"All keys in {path} must be strings")

        if key in (SECRET_FILES, VOLUME_FILES, GENERATED_SECRETS):
            continue  # File groups and generated paths validate their own structures.

        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise DeployError(
                f"{key} in {path} must be a string or an integer, "
                f"got type {type(value).__name__}. Put text in quotes."
            )

    port = config.get("HTTPS_PORT")
    if not isinstance(port, int) or not 1 <= port <= MAX_PORT:
        raise DeployError(
            f"HTTPS_PORT in {path} must be an integer 1-{MAX_PORT} without quotes"
        )

    for key in ("DB_HOST", "DB_PORT", "DB_USER", "DB_NAME"):
        if key in config:
            value = config[key]
            if not isinstance(value, str) or not value or "\x00" in value:
                raise DeployError(f"{key} in {path} must be non-empty text")
    if "DB_PORT" in config:
        port = config["DB_PORT"]
        if not re.fullmatch(r"[0-9]{1,5}", port) or not 1 <= int(port) <= MAX_PORT:
            raise DeployError(
                f"DB_PORT in {path} must be text containing an integer 1-{MAX_PORT}"
            )

    return config


def load_config(path):
    """Production loads only the authoritative materialized file."""
    return validate_config(config_layer(path), path)


def merge_config(*paths, overrides=None):
    """Merge mappings at the top level, in order, then validate the result."""
    config = {}
    for path in paths:
        config.update(config_layer(path))
    config.update(overrides or {})
    return validate_config(config, paths[-1])


def component_defaults(component, overrides=None, dev=False):
    """Build complete config from common, component and explicit local overrides."""
    paths = [
        ROOT / "config/common.defaults.yaml",
        ROOT / "components" / component / "config.defaults.yaml",
    ]
    local = ROOT / "config/dev.yaml"
    if dev and (local.exists() or local.is_symlink()):
        paths.append(local)
    config = merge_config(*paths, overrides=overrides)
    materialized = (BUILD / "dev" if dev else HOME) / component / "config.yaml"
    validate_component_config(config, component, materialized)
    return config


def validate_component_config(config, component, path, check_placeholders=True):
    """Require shared values and every whole-value manifest placeholder before writes."""
    required = {"PUBLIC_ORIGIN", "HTTPS_PORT"}

    def collect(value):
        if isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, str):
            match = PH.fullmatch(value)
            if match:
                required.add(match[1])

    if check_placeholders:
        for manifest in sorted(
            (ROOT / "components" / component / "manifests").glob("*.yaml")
        ):
            collect(load_yaml_all(manifest))
    # PUBLIC_HOSTNAME is derived from the validated origin for platform rendering.
    if component == "platform":
        required.discard("PUBLIC_HOSTNAME")
    for key in sorted(required):
        if key not in config:
            raise DeployError(
                f"Missing {key} in {path}; add it explicitly before installation"
            )
    public_origin(config["PUBLIC_ORIGIN"], path)
    check_component_config_names(config, component, path)
    generated_secret_paths(config, path.parent)
    for group in (SECRET_FILES, VOLUME_FILES):
        mapping = config.get(group, {})
        if not isinstance(mapping, dict):
            raise DeployError(f"{group} in {path} must be a map")
        for name, entries in mapping.items():
            if (
                not isinstance(name, str)
                or not ID.fullmatch(name)
                or not isinstance(entries, list)
                or not entries
                or any(not isinstance(entry, str) or not entry for entry in entries)
            ):
                raise DeployError(f"{group} in {path} must be id: [list of paths]")


def init_config(component):
    """Exclusively materialize one bundled config; never create private input files."""
    production_environment()
    reject_legacy_layout()
    if component == "core":
        raise DeployError("core was renamed to platform; use init-config platform")
    if component not in bundle_components():
        raise DeployError(f"Component {component} is not included in this bundle")
    if component != "platform":
        component_dependencies(component)
    target = HOME / component / "config.yaml"
    for path in [target] + list(target.parents):
        if path.is_symlink():
            raise DeployError(f"Refuse symlinked config path: {path}")
    if target.exists():
        reject_legacy_layout(volumes=True)
        print(
            f"[OK] Existing config retained unchanged: {target}; install validates it"
        )
        return
    overrides = {}
    platform_path = component_paths("platform")[0]
    if (
        component != "platform"
        and (HOME / "installed/platform").exists()
        and not platform_path.exists()
    ):
        raise DeployError(
            f"Missing {platform_path}; restore installed platform config before initializing {component}"
        )
    if component != "platform" and platform_path.exists():
        platform = load_config(platform_path)
        validate_component_config(
            platform,
            "platform",
            platform_path,
            check_placeholders=not (HOME / "installed/platform").is_file(),
        )
        overrides = {key: platform[key] for key in ("PUBLIC_ORIGIN", "HTTPS_PORT")}
    config = component_defaults(component, overrides=overrides)
    reject_legacy_layout(volumes=True)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.parent.chmod(0o700)
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        yaml.safe_dump(config, stream, sort_keys=False)
    print(
        f"[OK] Initialized {target}; edit config and prepare credentials before install"
    )


def public_origin(value, path):
    """Validate an HTTPS origin without exposing its supplied value in errors."""
    message = f"PUBLIC_ORIGIN in {path} must be an HTTPS origin without credentials, path or query"
    if not isinstance(value, str):
        raise DeployError(message)
    try:
        address = urlsplit(value.rstrip("/"))
        hostname = address.hostname
    except ValueError:
        raise DeployError(message) from None
    if (
        address.scheme != "https"
        or not hostname
        or address.path
        or address.query
        or address.fragment
        or address.username is not None
        or address.password is not None
    ):
        raise DeployError(message)
    return address


def generated_secret_paths(config, base_dir):
    """Resolve declared secret paths without generating or reading their contents."""
    entries = config.get(GENERATED_SECRETS, [])
    if not isinstance(entries, list) or not all(
        isinstance(entry, str) for entry in entries
    ):
        raise DeployError(f"{GENERATED_SECRETS} must be a list of relative file paths")
    base = base_dir.resolve()
    paths = []
    for entry in entries:
        relative = Path(entry)
        if relative.is_absolute() or ".." in relative.parts or not relative.name:
            raise DeployError(
                f"{GENERATED_SECRETS}: {entry!r} must stay under the config directory"
            )
        path = (base / relative).resolve()
        try:
            path.relative_to(base)
        except ValueError:
            raise DeployError(
                f"{GENERATED_SECRETS}: {entry!r} resolves outside the config directory"
            ) from None
        paths.append(path)
    return paths


def database_preflight(config, config_path, manifests):
    """Guard PostgreSQL password creation using its manifest's actual named volume.

    This lifecycle check runs before rendering/generation, never inside the
    general secret generator. Existing volumes are conservatively retained.
    """
    for manifest in sorted(manifests.glob("*.yaml")):
        for doc in load_yaml_all(manifest):
            if not doc or doc.get("kind") != "Pod":
                continue
            spec = doc.get("spec", {})
            volumes = {v["name"]: v for v in spec.get("volumes", [])}
            for container in spec.get("containers", []):
                env = {e["name"]: e.get("value") for e in container.get("env", [])}
                if "POSTGRES_PASSWORD_FILE" not in env:
                    continue
                reference = env["POSTGRES_PASSWORD_FILE"]
                if not isinstance(reference, str) or not Path(reference).is_absolute():
                    raise DeployError(f"Invalid POSTGRES_PASSWORD_FILE in {manifest}")
                password_file = Path(reference)
                mounts = container.get("volumeMounts", [])
                secret_mount = next(
                    (m for m in mounts if m["mountPath"] == str(password_file.parent)),
                    None,
                )
                data_mount = next(
                    (m for m in mounts if m["mountPath"] == "/var/lib/postgresql/data"),
                    None,
                )
                if not secret_mount or not data_mount:
                    raise DeployError(
                        f"Unsupported PostgreSQL password/data mounts in {manifest}"
                    )
                try:
                    secret = volumes[secret_mount["name"]]["secret"]
                    claim = volumes[data_mount["name"]]["persistentVolumeClaim"][
                        "claimName"
                    ]
                    keys = [
                        item["key"]
                        for item in secret.get("items", [])
                        if item["path"] == password_file.name
                    ]
                    if len(keys) != 1:
                        raise KeyError("password key")
                    key = keys[0]
                except (KeyError, TypeError):
                    raise DeployError(
                        f"Unsupported PostgreSQL Secret/PVC binding in {manifest}"
                    ) from None
                entries = config.get(SECRET_FILES, {}).get(secret["secretName"], [])
                candidates = []
                for entry in entries:
                    source = resolve_path(entry, config_path.parent)
                    candidates.append(source if source.name == key else source / key)
                if len(candidates) != 1:
                    raise DeployError(
                        f"{config_path}: {SECRET_FILES}.{secret['secretName']} must identify one password file"
                    )
                password = candidates[0]
                if password.exists() or password.is_symlink():
                    if not password.is_file():
                        raise DeployError(
                            f"Invalid database password file {password}; restore from backup"
                        )
                    try:
                        content = password.read_bytes().decode("utf-8").rstrip("\n")
                    except (OSError, UnicodeError):
                        raise DeployError(
                            f"Invalid database password file {password}; restore from backup"
                        ) from None
                    if not content or any(c in content for c in ("\x00", "\n", "\r")):
                        raise DeployError(
                            f"Empty or invalid database password file {password}; restore from backup"
                        )
                    continue
                try:
                    result = subprocess.run(  # noqa: UP022 - Python 3.6
                        ["podman", "volume", "exists", claim],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                    )
                except OSError:
                    raise DeployError(
                        f"Cannot check database volume {claim}; no password generated"
                    ) from None
                if result.returncode == 0:
                    raise DeployError(
                        f"Missing database password file {password} with existing volume {claim}; "
                        "restore the password from backup or use a separate recovery procedure; no password generated"
                    )
                if result.returncode != 1:
                    raise DeployError(
                        f"Cannot check database volume {claim}; no password generated"
                    )
                if password.resolve() not in generated_secret_paths(
                    config, config_path.parent
                ):
                    raise DeployError(
                        f"Missing database password file {password}; add its path to {GENERATED_SECRETS} in {config_path}"
                    )


def generate_secrets(config, base_dir):
    """Create missing private secret files once, within the config directory."""
    for path in generated_secret_paths(config, base_dir):
        if path.exists():
            if not path.is_file() or path.stat().st_size == 0:
                raise DeployError(
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
                raise DeployError(
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
        print(f"[OK] Generated secret file {path}")


def replace(value, config):
    """Replace whole placeholders recursively and keep the config value's type."""
    if isinstance(value, dict):
        return {key: replace(item, config) for key, item in value.items()}

    if isinstance(value, list):
        return [replace(item, config) for item in value]

    if isinstance(value, str):
        match = PH.fullmatch(value)
        if match:
            key = match.group(1)
            if key not in config:
                raise DeployError(f"Missing {key} in config.yaml")
            return config[key]

    return value


def write_private(path, text):
    """Write the file with mode 0600 from the first byte."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)  # in case the file existed with another mode
        f.write(text)


def resolve_path(value, base_dir=None):
    """Resolve a relative path from the config directory; ~ is allowed."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base_dir or CONFIG.parent) / path


def load_file_group(config, group, base_dir=None):
    """Read file groups and expand directory paths one level, relative to the config."""
    spec = config.get(group, {})

    if not isinstance(spec, dict):
        raise DeployError(f"{group} in config.yaml must be id: [list of files]")

    groups = {}

    for group_id, entries in spec.items():
        where = f"{group}.{group_id}"

        if not isinstance(group_id, str) or not ID.fullmatch(group_id):
            raise DeployError(
                f"Invalid id {group_id!r} in {group}. Use lowercase letters, digits and -"
            )

        if (
            not isinstance(entries, list)
            or not entries
            or not all(isinstance(entry, str) for entry in entries)
        ):
            raise DeployError(f"{where} must be a list of file paths")

        items = []

        for path in (resolve_path(entry, base_dir) for entry in entries):
            if not path.exists():
                raise DeployError(f"Missing {path} ({where})")
            items += sorted(path.iterdir()) if path.is_dir() else [path]

        names = [item.name for item in items]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise DeployError(
                f"{where} has several files with the same name: {duplicates}"
            )

        if group == SECRET_FILES:
            for item in items:
                if not item.is_file():
                    raise DeployError(
                        f"{where}: {item} is a directory. Secrets can only "
                        "contain files; use VOLUME_FILES for directory trees"
                    )
                if not SECRET_KEY.fullmatch(item.name):
                    raise DeployError(
                        f"{where}: the file name {item.name!r} may only contain "
                        "letters, digits, . - and _"
                    )

        groups[group_id] = items

    return groups


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

        if len(yaml.safe_dump(doc)) > MAX_SECRET_SIZE:
            raise DeployError(
                f"{SECRET_FILES}.{secret_id} is too large for a Podman secret "
                f"(max about {MAX_SECRET_SIZE * 3 // 4} bytes of file content). "
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
                "annotations": {IMPORT_SOURCE: str(archive_path(files_dir, volume_id))},
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


def check_links(docs, from_config, sources=None):
    """Validate unique volume names and links between config and manifests."""
    defined = [
        (doc.get("kind"), (doc.get("metadata") or {}).get("name"))
        for doc in docs
        if isinstance(doc, dict)
        and doc.get("kind") in ("Secret", "PersistentVolumeClaim", "ConfigMap")
    ]

    names = [name for _, name in defined]
    for name in sorted({n for n in names if names.count(n) > 1}, key=str):
        raise DeployError(
            f"The name {name!r} is defined more than once as Secret/PVC/ConfigMap. "
            "Podman creates one volume per name, so names must be unique across kinds"
        )

    defined = set(defined)
    used = references(docs, set())

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
            group = SECRET_FILES if kind == "Secret" else VOLUME_FILES
            hint = f"Add it under {group} in config.yaml or in a manifest"
        raise DeployError(
            f"{source}A manifest uses {kind} {name!r}, but it does not exist. {hint}"
        )

    for key, where in sorted(from_config.items()):
        if key not in used:
            raise DeployError(
                f"{where} in config.yaml is not used by any manifest. "
                "Check that the id matches secretName/claimName in the manifest"
            )


def check_pod_spec(value):
    """Validate offline pull policy and mounts within each pod specification."""
    if isinstance(value, dict):
        spec = value.get("spec")
        if not isinstance(spec, dict):
            spec = {}
        volumes = {
            volume.get("name")
            for volume in spec.get("volumes", [])
            if isinstance(volume, dict)
        }
        for group in ("containers", "initContainers"):
            for container in spec.get(group, []):
                if not isinstance(container, dict):
                    raise DeployError(f"{group} entries must be maps")
                name = container.get("name", "<unnamed>")
                if container.get("imagePullPolicy") != "Never":
                    raise DeployError(
                        f"Container {name!r} ({group}) must use imagePullPolicy: Never"
                    )
                for mount in container.get("volumeMounts", []):
                    if not isinstance(mount, dict) or mount.get("name") not in volumes:
                        raise DeployError(
                            f"Container {name!r} ({group}) mounts an undefined volume: {mount.get('name') if isinstance(mount, dict) else mount!r}"
                        )
        for child in value.values():
            check_pod_spec(child)
    elif isinstance(value, list):
        for child in value:
            check_pod_spec(child)


def check_component_names(documents, component, source):
    """Reject unprefixed component resources before generating or writing files."""
    for doc in documents:
        if not isinstance(doc, dict) or doc.get("kind") not in (
            "Pod",
            "Secret",
            "PersistentVolumeClaim",
            "ConfigMap",
        ):
            continue
        name = (doc.get("metadata") or {}).get("name")
        if (
            not isinstance(name, str)
            or not name.startswith(component + "-")
            or not ID.fullmatch(name)
        ):
            raise DeployError(
                f"{source}: {doc['kind']} name must start with {component}- and be a valid resource name"
            )


def check_component_config_names(config, component, path):
    """Validate every configured Secret/PVC prefix without generating any files."""
    for group, kind in (
        (SECRET_FILES, "Secret"),
        (VOLUME_FILES, "PersistentVolumeClaim"),
    ):
        mapping = config.get(group, {})
        if not isinstance(mapping, dict):
            raise DeployError(f"{group} in {path} must be a map")
        check_component_names(
            [{"kind": kind, "metadata": {"name": name}} for name in mapping],
            component,
            path,
        )


def render(
    files_dir=None,
    write_archives=True,
    config_path=None,
    manifests=None,
    component=None,
    extra_volumes=None,
):
    """Render validated YAML and write import archives if write_archives is set."""
    config_path = config_path or CONFIG
    if not config_path.exists():
        raise DeployError(f"Missing {config_path}")

    files_dir = files_dir or BUILD / "files"
    config = load_config(config_path)
    manifests = manifests or MANIFESTS
    if component:
        for path in sorted(manifests.glob("*.yaml")):
            check_component_names(load_yaml_all(path), component, path)
        check_component_config_names(config, component, config_path)
    if component == "platform" and "PUBLIC_ORIGIN" in config:
        config["PUBLIC_HOSTNAME"] = public_origin(
            config["PUBLIC_ORIGIN"], config_path
        ).hostname
    if component:
        validate_component_config(config, component, config_path)
    generate_secrets(config, config_path.parent)
    secrets = load_file_group(config, SECRET_FILES, config_path.parent)
    volume_config = dict(config)
    mapping = config.get(VOLUME_FILES, {})
    if not isinstance(mapping, dict):
        raise DeployError(f"{VOLUME_FILES} in {config_path} must be a map")
    volume_config[VOLUME_FILES] = {
        key: entries
        for key, entries in mapping.items()
        if key not in (extra_volumes or {})
    }
    volumes = load_file_group(volume_config, VOLUME_FILES, config_path.parent)
    volumes.update(extra_volumes or {})

    docs: list = secret_documents(secrets) + volume_claims(volumes, files_dir)
    sources: list = [None] * len(docs)

    for path in sorted(manifests.glob("*.yaml")):
        try:
            rendered = [
                replace(document, config)
                for document in load_yaml_all(path)
                if document is not None
            ]
            for doc in rendered:
                check_pod_spec(doc)
                if isinstance(doc, dict) and doc.get("kind") == "ConfigMap":
                    data = doc.get("data") or {}
                    if not isinstance(data, dict):
                        raise DeployError("ConfigMap.data must be a map")
                    doc["data"] = {str(key): str(value) for key, value in data.items()}
            if "@@" in yaml.safe_dump_all(rendered, sort_keys=False):
                raise DeployError(
                    'Unreplaced @@...@@. Only whole values like "@@NAME@@" are supported.'
                )
        except DeployError as error:
            raise DeployError(f"{path} (config {config_path}): {error}") from None
        docs += rendered
        sources.extend([path] * len(rendered))

    from_config = {("Secret", i): f"{SECRET_FILES}.{i}" for i in secrets}
    from_config.update(
        {("PersistentVolumeClaim", i): f"{VOLUME_FILES}.{i}" for i in volumes}
    )
    try:
        check_links(docs, from_config, sources)
    except DeployError as error:
        raise DeployError(f"{config_path}: {error}") from None

    text = yaml.safe_dump_all(docs, sort_keys=False)

    # Base64 never contains '@', so Secret data cannot give false matches.
    if "@@" in text:
        raise DeployError(
            'Unreplaced @@...@@ in the manifests. Only whole values like "@@NAME@@" are supported.'
        )

    if write_archives:
        write_file_archives(volumes, files_dir)
    return text


def prepare_components():
    """Render all source components with private dev state and shared imported registrations."""
    state = BUILD / "dev"
    reject_legacy_layout(home=state)
    settings_by_component = {
        component: component_defaults(component, dev=True) for component in COMPONENTS
    }
    for component, settings in settings_by_component.items():
        database_preflight(
            settings,
            state / component / "config.yaml",
            ROOT / "components" / component / "manifests",
        )
    reject_legacy_layout(home=state, volumes=True)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    for component in COMPONENTS:
        target = state / component / "config.yaml"
        settings = settings_by_component[component]
        write_private(target, yaml.safe_dump(settings, sort_keys=False))
    with tempfile.TemporaryDirectory(prefix="myproduct-prepare-") as directory:
        imports, updates = registration_stage(
            ["identity", "app1", "app2", "help"], Path(directory), home=state
        )
        documents = []
        for component in COMPONENTS:
            text = render(
                state / component / "files",
                config_path=state / component / "config.yaml",
                manifests=ROOT / "components" / component / "manifests",
                component=component,
                extra_volumes=component_imports(
                    component, imports, settings_by_component[component]
                ),
            )
            documents.extend(yaml.safe_load_all(text))
        check_links(documents, {})
        write_registrations(updates, home=state)
        write_private(
            BUILD / "install.yaml", yaml.safe_dump_all(documents, sort_keys=False)
        )
    print(f"[OK] {BUILD / 'install.yaml'}")


def prepare():
    """Write validated dev YAML and import archives without running Podman."""
    if (ROOT / "components").is_dir():
        if (ROOT / "bundle.yaml").exists():
            raise DeployError(
                "Run prepare from the source checkout; production bundles use persistent config with install"
            )
        prepare_components()
        return
    output = BUILD / "install.yaml"
    if CONFIG.is_file():
        database_preflight(load_config(CONFIG), CONFIG, MANIFESTS)
    write_private(output, render())
    print(f"[OK] {output}")


def run(*args):
    """Show and run a command; stop on a failing status."""
    print("+", " ".join(map(str, args)))
    subprocess.run(list(map(str, args)), check=True)


def find_images(documents):
    """Find unique, fully qualified images in pod specs."""
    images = set()
    pending = list(documents)
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            for key, child in value.items():
                if key in ("containers", "initContainers") and isinstance(child, list):
                    for container in child:
                        image = (
                            container.get("image")
                            if isinstance(container, dict)
                            else None
                        )
                        container_name = (
                            container.get("name", "<unnamed>")
                            if isinstance(container, dict)
                            else "<unnamed>"
                        )
                        where = f"container {container_name!r} ({key})"
                        if not isinstance(image, str) or not image.strip():
                            raise DeployError(
                                f"Container must have an image name as a string: {where}"
                            )
                        if "@@" in image:
                            raise DeployError(
                                f"Image {image}: placeholders are not supported in {where}"
                            )
                        registry, separator, name = image.partition("/")
                        if (
                            not separator
                            or not name
                            or not (
                                "." in registry
                                or ":" in registry
                                or registry == "localhost"
                            )
                        ):
                            raise DeployError(
                                f"Image {image} must be fully qualified in {where}"
                            )
                        images.add(image)
                pending.append(child)
    if not images:
        raise DeployError("No images found in the manifests")
    return sorted(images)


def production_environment():
    """Validate the service user and set its runtime before rendering or commands."""
    if os.geteuid() == 0:
        raise DeployError("Run install as the service user, not as root")

    configured_home = os.environ.get("HOME")
    if configured_home is not None and Path(configured_home) != HOME:
        raise DeployError(
            f"HOME={configured_home!r} differs from the home directory {HOME} in "
            "the user database. Run install with the service user's HOME"
        )

    runtime = Path(f"/run/user/{os.geteuid()}")
    configured_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if configured_runtime is not None and configured_runtime != str(runtime):
        raise DeployError(
            f"XDG_RUNTIME_DIR={configured_runtime!r} differs from the expected {runtime} "
            "for the service user"
        )
    if not runtime.is_dir():
        raise DeployError(
            f"Missing runtime directory {runtime}. Enable linger for the service user "
            "with loginctl enable-linger and check that the user instance is running"
        )
    os.environ["XDG_RUNTIME_DIR"] = str(runtime)


def install_legacy():
    """Install a standalone rootless manifest fixture using the persistent config."""
    production_environment()
    config_path = HOME / "config.yaml"
    if config_path.is_file():
        database_preflight(load_config(config_path), config_path, MANIFESTS)
    text = render(FILES_DIR, write_archives=False, config_path=config_path)
    archive = ROOT / "images" / "images.tar"
    if not archive.is_file():
        raise DeployError(f"Missing image archive {archive}")
    run("podman", "load", "-i", archive)
    for image in find_images(yaml.safe_load_all(text)):
        try:
            run("podman", "image", "exists", image)
        except subprocess.CalledProcessError as error:
            raise DeployError(
                f"Image {image} is not available after podman load "
                f"(podman image exists returned exit {error.returncode})"
            ) from None

    # Old YAML must not import new files after a failed image check.
    render(FILES_DIR, config_path=config_path)

    QUADLET_DIR.mkdir(parents=True, exist_ok=True)
    write_private(QUADLET_YAML, text)
    for suffix in (".kube", ".network"):
        target = QUADLET_TARGET.with_suffix(suffix)
        target.write_text(
            QUADLET_TEMPLATE.with_suffix(suffix).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        target.chmod(0o644)

    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "restart", SERVICE)
    run("systemctl", "--user", "is-active", "--quiet", SERVICE)
    run("podman", "ps", "--all", "--pod")

    print(f"[OK] {SERVICE} is running. Check that the containers above are 'Up'.")


def bundle_components():
    """Accept only one component per offline bundle, with explicit dependencies."""
    descriptor = load_yaml(ROOT / "bundle.yaml")
    if not isinstance(descriptor, dict) or set(descriptor) != {
        "name",
        "components",
        "requires",
    }:
        raise DeployError(
            "Invalid bundle.yaml; use a separate platform/identity/app/help bundle"
        )
    name = descriptor["name"]
    if name not in COMPONENTS or descriptor["components"] != [name]:
        raise DeployError(
            "Invalid bundle component selection; platform must be separate"
        )
    requires = descriptor["requires"]
    if not isinstance(requires, dict) or set(requires) != set(DEPENDENCIES[name]):
        raise DeployError("Invalid bundle dependencies")
    for requirement in requires.values():
        validate_platform_requirement(requirement)
    return [name]


def platform_requirement(version):
    """Declare a compatible major series, or minor series while platform is 0.x."""
    major, minor, _ = version_number(version)
    upper = f"{major + 1}.0.0" if major else f"0.{minor + 1}.0"
    return {"min": version, "before": upper}


def validate_platform_requirement(requirement):
    """Require an explicit nonempty inclusive-minimum/exclusive-upper range."""
    if not isinstance(requirement, dict) or set(requirement) != {"min", "before"}:
        raise DeployError("Invalid platform version requirement")
    if not all(isinstance(value, str) for value in requirement.values()):
        raise DeployError("Invalid platform version requirement")
    if version_number(requirement["min"]) >= version_number(requirement["before"]):
        raise DeployError("Empty platform version requirement")


def component_dependencies(component):
    """Validate fixed component dependencies and installed dependents before writes."""
    requires = load_yaml(ROOT / "bundle.yaml")["requires"]
    for dependency, requirement in requires.items():
        marker = HOME / "installed" / dependency
        if not marker.is_file():
            raise DeployError(
                "Install the separate "
                + dependency
                + " bundle before installing "
                + component
            )
        check_version_requirement(
            dependency, marker.read_text().strip(), requirement, component
        )
    requested = (ROOT / VERSION_FILES.get(component, "VERSION")).read_text().strip()
    for name in COMPONENTS:
        if (
            name == component
            or component not in DEPENDENCIES[name]
            or not (HOME / "installed" / name).is_file()
        ):
            continue
        path = HOME / "dependencies" / (name + ".json")
        try:
            installed = json.loads(path.read_text())
            if not isinstance(installed, dict) or set(installed) != set(
                DEPENDENCIES[name]
            ):
                raise ValueError("dependency keys")
            for requirement in installed.values():
                validate_platform_requirement(requirement)
        except (OSError, ValueError, KeyError, TypeError, DeployError):
            raise DeployError(
                "Missing or invalid installed " + component + " requirement for " + name
            ) from None
        check_version_requirement(component, requested, installed[component], name)


def check_version_requirement(component, version, requirement, dependent):
    """Use the existing inclusive-minimum/exclusive-upper numeric contract."""
    validate_platform_requirement(requirement)
    if (
        not version_number(requirement["min"])
        <= version_number(version)
        < version_number(requirement["before"])
    ):
        raise DeployError(
            component.title() + " version does not satisfy dependency for " + dependent
        )


def reject_legacy_layout(home=None, volumes=False):
    """Refuse known core state; never migrate, delete or infer absence after an error."""
    home = HOME if home is None else home
    paths = [
        home / "core",
        home / "installed/core",
        home / ".config/containers/systemd/myproduct-core.yaml",
        home / ".config/containers/systemd/myproduct-core.kube",
        home / ".config/systemd/user/myproduct-core.service",
    ]
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        paths.extend(
            Path(runtime) / "systemd" / directory / "myproduct-core.service"
            for directory in ("generator", "generator.early", "generator.late")
        )
    for path in paths:
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        raise DeployError(
            "Legacy core layout detected; use its previous release. A separate migration procedure or an explicitly fresh installation is required; mixed core/platform state is refused"
        )
    reject_combined_platform(home)
    if not volumes:
        return
    for name in (
        "core-identity-data",
        "core-identity-protection",
        "core-routes",
        "core-clients",
        "platform-identity-data",
        "platform-identity-protection",
        "platform-clients",
    ):
        if legacy_volume_exists(name):
            raise DeployError(
                "Legacy core volume/combined platform volume detected: "
                + name
                + "; use the previous release or a separate migration procedure; no automatic migration"
            )


def reject_combined_platform(home):
    """Proxy-only platform is valid; reject concrete signs of its former Identity ownership."""
    old = [
        home / "platform/generated-certificates" / name
        for name in ("identity", "identity-db", "app", "users")
    ]
    old.append(home / "platform/files/platform-clients.tar")
    for path in old:
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        raise DeployError(
            "Combined platform/Identity layout detected; use its previous release or a separate migration procedure; mixed layouts are refused"
        )
    marker = home / "installed/platform"
    if marker.is_file() and version_number(marker.read_text().strip()) < (0, 4, 0):
        raise DeployError(
            "Combined platform/Identity version detected; a separate migration procedure is required"
        )
    for path in (
        home / "platform/config.yaml",
        home / ".config/containers/systemd/myproduct-platform.yaml",
    ):
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise DeployError(
                "Cannot check combined platform/Identity layout; no changes made"
            ) from None
        if re.search(
            r"platform-(?:identity|api-secrets|database-password|demo-users|clients)|generated-certificates/(?:identity-db|identity/|app/|users/)",
            text,
        ):
            raise DeployError(
                "Combined platform/Identity config or service detected; a separate migration procedure is required"
            )


def legacy_volume_exists(name):
    """Distinguish an absent legacy volume from an unavailable volume store."""
    try:
        result = subprocess.run(  # noqa: UP022 - Python 3.6
            ["podman", "volume", "exists", name],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise DeployError("Cannot check legacy core volumes; no changes made") from None
    if result.returncode not in (0, 1):
        raise DeployError(
            "Cannot check legacy core volume " + name + "; no changes made"
        )
    return result.returncode == 0


def version_number(value):
    """Parse a three-part numeric version for deterministic platform comparisons."""
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise DeployError(
            "Versions must contain three numeric parts: major.minor.patch"
        )
    return tuple(int(part) for part in value.split("."))


def platform_upgrade_needed(version):
    """Retain the existing platform comparison entry point."""
    return shared_upgrade_needed("platform", version)


def shared_upgrade_needed(component, version):
    """Install missing/newer shared components; retain equals and refuse downgrades."""
    requested = version_number(version)
    marker = HOME / "installed" / component
    if not marker.is_file():
        return True
    installed = version_number(marker.read_text().strip())
    if requested < installed:
        raise DeployError(
            component.title()
            + " downgrade refused: requested "
            + version
            + ", installed "
            + marker.read_text().strip()
        )
    return requested > installed


def component_paths(component, home=None):
    """Return one component's persistent config, archives and Quadlet paths."""
    base = (home or HOME).resolve()
    state = base / component
    paths = [
        state,
        state / "files",
        state / "config.yaml",
        base / "installed" / component,
        base / "dependencies",
        base / "dependencies" / (component + ".json"),
    ]
    paths.extend((state / "files").glob("*.tar"))
    if home is None:
        paths.extend(
            [
                QUADLET_DIR / ("myproduct-" + component + suffix)
                for suffix in (".yaml", ".kube")
            ]
        )
    if any(path.is_symlink() for path in paths):
        raise DeployError(
            f"Refuse symlinked component state or output paths for {component}"
        )
    return (
        state / "config.yaml",
        state / "files",
        QUADLET_DIR / ("myproduct-" + component + ".yaml"),
        QUADLET_DIR / ("myproduct-" + component + ".kube"),
    )


def registration_stage(components, directory, home=None):
    """Stage existing and proposed public routes and clients without changing live state."""
    home = home or HOME
    for name in ("routes", "clients"):
        source = home / name
        if source.is_symlink():
            raise DeployError(
                f"Refuse symlinked shared registration directory: {source}"
            )
        (directory / name).mkdir()
        if not source.exists():
            continue
        for path in sorted(source.iterdir()):
            if path.is_symlink():
                raise DeployError(f"Refuse symlinked public registration: {path}")
            if name == "routes":
                if path.suffix == ".conf":
                    shutil.copy2(path, directory / name / path.name)
            elif path.is_dir() and path.name in ("app1", "app2"):
                target = directory / name / path.name
                target.mkdir()
                for filename in ("client.json", "client.crt"):
                    public = path / filename
                    if public.is_symlink():
                        raise DeployError(
                            f"Refuse symlinked public client file: {public}"
                        )
                    shutil.copy2(public, target / filename)
            else:
                raise DeployError(f"Unexpected public client registration: {path}")
    updates = {}
    for component in components:
        source = ROOT / "components" / component
        route = source / "route.conf"
        client = source / "client.yaml"
        if not route.is_file() and not client.is_file():
            continue
        config = load_config(component_paths(component, home)[0])
        platform = load_config(component_paths("platform", home)[0])
        if any(
            config.get(key) != platform.get(key)
            for key in ("PUBLIC_ORIGIN", "HTTPS_PORT")
        ):
            raise DeployError(
                f"{component} PUBLIC_ORIGIN and HTTPS_PORT must match the persistent platform config"
            )
        if route.is_file():
            updates["routes/" + component + ".conf"] = route.read_bytes()
        if client.is_file():
            metadata = load_yaml(client)
            if (
                not isinstance(metadata, dict)
                or set(metadata) != {"id", "base_path", "scopes", "certificate"}
                or metadata["id"] != component
                or metadata["base_path"] != "/" + component
                or metadata["scopes"] != ["openid", "profile", component]
                or not isinstance(metadata["certificate"], str)
                or Path(metadata["certificate"]).is_absolute()
                or ".." in Path(metadata["certificate"]).parts
            ):
                raise DeployError(f"Invalid public client descriptor: {client}")
            certificate = resolve_path(
                metadata["certificate"], component_paths(component, home)[0].parent
            )
            certificate_bytes = certificate.read_bytes()
            try:
                ssl.PEM_cert_to_DER_cert(certificate_bytes.decode("ascii"))
            except (ValueError, UnicodeError):
                raise DeployError(
                    f"Expected a public PEM certificate in {certificate}"
                ) from None
            public_origin(
                config.get("PUBLIC_ORIGIN"), component_paths(component, home)[0]
            )
            origin = config["PUBLIC_ORIGIN"].rstrip("/")
            prefix = "clients/" + component + "/"
            updates[prefix + "client.crt"] = certificate_bytes
            updates[prefix + "client.json"] = json.dumps(
                {
                    "Id": component,
                    "RedirectUris": [origin + metadata["base_path"] + "/auth/callback"],
                    "Scopes": metadata["scopes"],
                    "Certificate": "client.crt",
                },
                sort_keys=True,
            ).encode("utf-8")
    for relative, data in updates.items():
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    routes = directory / "routes/installed.conf"
    routes.write_text(
        "\n".join(
            path.read_text()
            for path in sorted((directory / "routes").glob("*.conf"))
            if path != routes
        ),
        encoding="utf-8",
    )
    client_dirs = sorted(
        path for path in (directory / "clients").iterdir() if path.is_dir()
    )
    index = directory / "clients/installed.json"
    index.write_text(
        json.dumps([path.name + "/client.json" for path in client_dirs]),
        encoding="utf-8",
    )
    # Imports overwrite files without deleting old entries; only these current indexes are read.
    imports = {"platform-routes": [routes], "identity-clients": client_dirs + [index]}
    return imports, updates


def write_registrations(updates, home=None):
    """Write changed public registrations privately and report which registration owners must restart."""
    changed = set()
    if any(((home or HOME) / relative).is_symlink() for relative in updates):
        raise DeployError("Refuse symlinked public registration output")
    for relative, data in updates.items():
        target = (home or HOME) / relative
        if target.is_file() and target.read_bytes() == data:
            continue
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.parent.chmod(0o700)
        write_private(target, data.decode("utf-8"))
        changed.add("platform" if relative.startswith("routes/") else "identity")
    return changed


def component_imports(component, imports, config=None):
    """Route and client archives have separate owners; never cross their PVC namespaces."""
    selected = {
        key: value for key, value in imports.items() if key.startswith(component + "-")
    }
    if config is not None:
        selected = {
            key: value
            for key, value in selected.items()
            if key in config.get(VOLUME_FILES, {})
        }
    return selected or None


def install_component_plan(components, source_components, imports, updates):
    """Apply a preflighted plan after validating images, changing only selected components."""
    network = QUADLET_DIR / "myproduct.network"
    network_text = QUADLET_TEMPLATE.with_suffix(".network").read_text(encoding="utf-8")
    if network.exists() and network.read_text(encoding="utf-8") != network_text:
        raise DeployError(f"Existing shared network differs from the bundle: {network}")
    rendered = {}
    for component in components:
        config, files, _, _ = component_paths(component)
        extra = component_imports(component, imports, load_config(config))
        rendered[component] = render(
            files,
            write_archives=False,
            config_path=config,
            manifests=ROOT / "components" / component / "manifests",
            component=component,
            extra_volumes=extra,
        )
    archive = ROOT / "images/images.tar"
    if not archive.is_file():
        raise DeployError(f"Missing image archive {archive}")
    run("podman", "load", "-i", archive)
    documents = [doc for text in rendered.values() for doc in yaml.safe_load_all(text)]
    for component in source_components:
        if component not in components:
            for path in sorted(
                (ROOT / "components" / component / "manifests").glob("*.yaml")
            ):
                documents.extend(load_yaml_all(path))
    for image in find_images(documents):
        try:
            run("podman", "image", "exists", image)
        except subprocess.CalledProcessError as error:
            raise DeployError(
                f"Image {image} is unavailable after load (exit {error.returncode})"
            ) from None
    changed = write_registrations(updates)
    QUADLET_DIR.mkdir(parents=True, exist_ok=True)
    if not network.exists():
        network.write_text(network_text, encoding="utf-8")
        network.chmod(0o644)
    for component in components:
        config, files, output, quadlet = component_paths(component)
        extra = component_imports(component, imports, load_config(config))
        render(
            files,
            config_path=config,
            manifests=ROOT / "components" / component / "manifests",
            component=component,
            extra_volumes=extra,
        )
        write_private(output, rendered[component])
        quadlet.write_text(
            QUADLET_TEMPLATE.read_text(encoding="utf-8").replace(
                "Yaml=myproduct.yaml", "Yaml=" + output.name
            ),
            encoding="utf-8",
        )
        quadlet.chmod(0o644)
    for owner in ("identity", "platform"):
        if owner in changed and owner not in components:
            write_file_archives(
                component_imports(owner, imports) or {}, component_paths(owner)[1]
            )
    run("systemctl", "--user", "daemon-reload")
    services = [component for component in components if component not in VERSION_FILES]
    services.extend(
        owner
        for owner in ("identity", "platform")
        if owner in components or owner in changed
    )
    for component in services:
        service = "myproduct-" + component + ".service"
        run("systemctl", "--user", "restart", service)
        run("systemctl", "--user", "is-active", "--quiet", service)
    for component in components:
        version = (ROOT / VERSION_FILES.get(component, "VERSION")).read_text().strip()
        write_private(HOME / "installed" / component, version + "\n")
        write_private(
            HOME / "dependencies" / (component + ".json"),
            json.dumps(load_yaml(ROOT / "bundle.yaml")["requires"], sort_keys=True),
        )
    run("podman", "ps", "--all", "--pod")


def install_components():
    """Validate the selected components and images before writing scoped services."""
    production_environment()
    reject_legacy_layout()
    components = bundle_components()
    component_dependencies(components[0])
    version_number((ROOT / "VERSION").read_text().strip())
    source_components = list(components)
    for component in tuple(components):
        if component in VERSION_FILES and not shared_upgrade_needed(
            component, (ROOT / VERSION_FILES[component]).read_text().strip()
        ):
            components.remove(component)
    for component in source_components:
        for path in sorted(
            (ROOT / "components" / component / "manifests").glob("*.yaml")
        ):
            check_component_names(load_yaml_all(path), component, path)
        config_path = component_paths(component)[0]
        validate_component_config(
            load_config(config_path),
            component,
            config_path,
            check_placeholders=component in components,
        )
    platform_path = component_paths("platform")[0]
    platform = load_config(platform_path)
    validate_component_config(
        platform, "platform", platform_path, check_placeholders="platform" in components
    )
    for component in source_components:
        if component == "platform":
            continue
        path = component_paths(component)[0]
        config = load_config(path)
        for key in ("PUBLIC_ORIGIN", "HTTPS_PORT"):
            if config[key] != platform[key]:
                raise DeployError(f"{key} in {path} must match {platform_path}")
    reject_legacy_layout(volumes=True)
    for component in components:
        config_path = component_paths(component)[0]
        database_preflight(
            load_config(config_path),
            config_path,
            ROOT / "components" / component / "manifests",
        )
    with tempfile.TemporaryDirectory(
        prefix="myproduct-install-", dir=os.environ["XDG_RUNTIME_DIR"]
    ) as directory:
        imports, updates = registration_stage(source_components, Path(directory))
        install_component_plan(components, source_components, imports, updates)


def install():
    """Install the selected component bundle or a standalone manifest fixture."""
    if (ROOT / "bundle.yaml").exists():
        install_components()
    elif (ROOT / "components").is_dir():
        raise DeployError(
            "Run install from an unpacked platform/identity/app/help bundle, not the source checkout"
        )
    else:
        install_legacy()


def uninstall(component=None, delete_data=False):
    """Remove one scoped service and registration, preserving data unless explicitly requested."""
    production_environment()
    reject_legacy_layout()
    selected = bundle_components()
    own = selected[0]
    component = component or own
    if component != own:
        raise DeployError("This bundle can only uninstall its own component")
    marker = HOME / "installed" / component
    if not marker.is_file():
        raise DeployError(f"Component {component} is not installed")
    dependents = [
        name
        for name in COMPONENTS
        if component in DEPENDENCIES[name] and (HOME / "installed" / name).is_file()
    ]
    if dependents:
        raise DeployError(
            component.title() + " is still required by: " + ", ".join(dependents)
        )
    reject_legacy_layout(volumes=True)
    _, _, output, quadlet = component_paths(component)
    documents = load_yaml_all(output)
    check_component_names(documents, component, output)
    volumes = [
        doc["metadata"]["name"]
        for doc in documents
        if isinstance(doc, dict)
        and doc.get("kind") in ("Secret", "PersistentVolumeClaim")
    ]
    run("systemctl", "--user", "stop", "myproduct-" + component + ".service")
    for path in (output, quadlet):
        path.unlink()
    changed = set()
    route = HOME / "routes" / (component + ".conf")
    if route.is_file():
        route.unlink()
        changed.add("platform")
    client = HOME / "clients" / component
    if client.exists():
        changed.add("identity")
        if client.is_symlink():
            raise DeployError("Refuse symlinked client registration")
        shutil.rmtree(client)
    marker.unlink()
    dependency = HOME / "dependencies" / (component + ".json")
    if dependency.exists():
        dependency.unlink()
    if changed:
        with tempfile.TemporaryDirectory(
            prefix="myproduct-remove-", dir=os.environ["XDG_RUNTIME_DIR"]
        ) as directory:
            imports, _ = registration_stage([], Path(directory))
            for owner in ("identity", "platform"):
                if (
                    owner in changed
                    and owner != component
                    and (HOME / "installed" / owner).is_file()
                ):
                    write_file_archives(
                        component_imports(owner, imports) or {},
                        component_paths(owner)[1],
                    )
                    run(
                        "systemctl",
                        "--user",
                        "restart",
                        "myproduct-" + owner + ".service",
                    )
                    run(
                        "systemctl",
                        "--user",
                        "is-active",
                        "--quiet",
                        "myproduct-" + owner + ".service",
                    )
    run("systemctl", "--user", "daemon-reload")
    if delete_data:
        for name in volumes:
            result = subprocess.run(  # noqa: UP022 - Python 3.6
                ["podman", "volume", "exists", name],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if result.returncode == 0:
                run("podman", "volume", "rm", name)
            elif result.returncode != 1:
                raise DeployError(f"Cannot check volume {name} before deletion")
        shutil.rmtree(HOME / component)
    print(
        f"[OK] Uninstalled {component}; shared network retained; data {'deleted' if delete_data else 'preserved'}"
    )


def main():
    """Run the chosen deploy command and return an exit code for expected errors."""
    commands = {
        "prepare": prepare,
        "install": install,
        "uninstall": uninstall,
        "init-config": init_config,
    }
    args = sys.argv[1:]
    if "core" in args:
        print(
            "ERROR: core was renamed to platform; use the separate platform bundle",
            file=sys.stderr,
        )
        return 2
    removing = bool(args and args[0] == "uninstall")
    valid_remove = removing and args[1:] in (
        [],
        ["platform"],
        ["--delete-data"],
        ["platform", "--delete-data"],
    )
    initializing = bool(args and args[0] == "init-config" and len(args) == 2)
    if (
        not args
        or args[0] not in commands
        or (
            not valid_remove
            and not initializing
            and (len(args) != 1 or args[0] == "init-config")
        )
    ):
        print(
            "Usage: ./deploy prepare|install|uninstall [platform] [--delete-data] | init-config <component>"
        )
        return 2

    try:
        if initializing:
            init_config(args[1])
        elif removing:
            uninstall(
                "platform" if "platform" in args[1:] else None,
                "--delete-data" in args[1:],
            )
        else:
            commands[args[0]]()
    except subprocess.CalledProcessError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        if args[0] == "install":
            print(
                f"Troubleshoot: journalctl --user -u {SERVICE} and "
                "/usr/lib/systemd/user-generators/podman-user-generator --dryrun",
                file=sys.stderr,
            )
        return 1
    except (OSError, DeployError, yaml.YAMLError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
