"""Render Kubernetes YAML for Podman and install it as a Quadlet service.

./deploy prepare   Dev: write build/install.yaml (+ build/files/*.tar).

Files are listed in config.yaml under SECRET_FILES and VOLUME_FILES (id -> files).
./deploy install   Prod (service user): render, podman load, install Quadlet, restart.
"""

import base64
import os
import pwd
import re
import secrets
import string
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml

HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
MANIFESTS = ROOT / "manifests"
CONFIG = ROOT / "config.yaml"

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


def load_config(path):
    """Read config and validate key types, value types and the HTTPS port."""
    try:
        config = load_yaml(path)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = f" at line {mark.line + 1}" if mark is not None else ""
        problem = getattr(error, "problem", "") or ""
        detail = problem if problem.startswith("duplicate key ") else "invalid YAML"
        raise yaml.YAMLError(f"{path}{location}: {detail}") from None

    if not isinstance(config, dict):
        raise DeployError(f"{path} must contain KEY: value pairs")

    for key, value in config.items():
        if not isinstance(key, str):
            raise DeployError("All keys in config.yaml must be strings")

        if key in (SECRET_FILES, VOLUME_FILES, GENERATED_SECRETS):
            continue  # File groups and generated paths validate their own structures.

        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise DeployError(
                f"{key} in config.yaml must be a string or an integer, "
                f"got type {type(value).__name__}. Put text in quotes."
            )

    port = config.get("HTTPS_PORT")
    if not isinstance(port, int) or not 1 <= port <= MAX_PORT:
        raise DeployError(
            f"HTTPS_PORT in config.yaml must be an integer 1-{MAX_PORT} without quotes"
        )

    return config


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
    """Normalize tar ownership to root and file modes to 0644 or 0755."""
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
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
        for group, kind in (
            (SECRET_FILES, "Secret"),
            (VOLUME_FILES, "PersistentVolumeClaim"),
        ):
            mapping = config.get(group, {})
            if not isinstance(mapping, dict):
                raise DeployError(f"{group} in {config_path} must be a map")
            check_component_names(
                [{"kind": kind, "metadata": {"name": name}} for name in mapping],
                component,
                config_path,
            )
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
            raise DeployError(f"{path}: {error}") from None
        docs += rendered
        sources.extend([path] * len(rendered))

    from_config = {("Secret", i): f"{SECRET_FILES}.{i}" for i in secrets}
    from_config.update(
        {("PersistentVolumeClaim", i): f"{VOLUME_FILES}.{i}" for i in volumes}
    )
    check_links(docs, from_config, sources)

    text = yaml.safe_dump_all(docs, sort_keys=False)

    # Base64 never contains '@', so Secret data cannot give false matches.
    if "@@" in text:
        raise DeployError(
            'Unreplaced @@...@@ in the manifests. Only whole values like "@@NAME@@" are supported.'
        )

    if write_archives:
        write_file_archives(volumes, files_dir)
    return text


def prepare():
    """Write validated dev YAML and import archives without running Podman."""
    output = BUILD / "install.yaml"
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
    """Read a release's fixed component selection and reject an invalid descriptor."""
    descriptor = load_yaml(ROOT / "bundle.yaml")
    if not isinstance(descriptor, dict) or set(descriptor) != {"name", "components"}:
        raise DeployError("Invalid bundle.yaml")
    name = descriptor["name"]
    expected = ["help"] if name == "help" else ["core", name]
    if name not in ("app1", "app2", "help") or descriptor["components"] != expected:
        raise DeployError("Invalid bundle component selection")
    return expected


def version_number(value):
    """Parse a three-part numeric version for deterministic core comparisons."""
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise DeployError(
            "Versions must contain three numeric parts: major.minor.patch"
        )
    return tuple(int(part) for part in value.split("."))


def core_upgrade_needed(version):
    """Install missing/newer core, retain an equal core and reject downgrades."""
    requested = version_number(version)
    marker = HOME / "installed/core"
    if not marker.is_file():
        return True
    installed = version_number(marker.read_text().strip())
    if requested < installed:
        raise DeployError(
            f"Core downgrade refused: requested {version}, installed {marker.read_text().strip()}"
        )
    return requested > installed


def component_paths(component):
    """Return one component's persistent config, archives and Quadlet paths."""
    state = HOME / component
    return (
        state / "config.yaml",
        state / "files",
        QUADLET_DIR / ("myproduct-" + component + ".yaml"),
        QUADLET_DIR / ("myproduct-" + component + ".kube"),
    )


def install_components():
    """Validate the selected components and images before writing scoped services."""
    production_environment()
    components = bundle_components()
    version_number((ROOT / "VERSION").read_text().strip())
    source_components = list(components)
    if "core" in components and not core_upgrade_needed(
        (ROOT / "CORE_VERSION").read_text().strip()
    ):
        components.remove("core")
    for component in source_components:
        for path in sorted(
            (ROOT / "components" / component / "manifests").glob("*.yaml")
        ):
            check_component_names(load_yaml_all(path), component, path)
    if components == ["help"] and not (HOME / "installed/core").is_file():
        raise DeployError("Install an app bundle with core before installing help")
    network = QUADLET_DIR / "myproduct.network"
    network_text = QUADLET_TEMPLATE.with_suffix(".network").read_text(encoding="utf-8")
    if network.exists() and network.read_text(encoding="utf-8") != network_text:
        raise DeployError(f"Existing shared network differs from the bundle: {network}")
    rendered = {}
    for component in components:
        config, files, _, _ = component_paths(component)
        rendered[component] = render(
            files,
            write_archives=False,
            config_path=config,
            manifests=ROOT / "components" / component / "manifests",
            component=component,
        )
    archive = ROOT / "images/images.tar"
    if not archive.is_file():
        raise DeployError(f"Missing image archive {archive}")
    run("podman", "load", "-i", archive)
    documents = [doc for text in rendered.values() for doc in yaml.safe_load_all(text)]
    for image in find_images(documents):
        try:
            run("podman", "image", "exists", image)
        except subprocess.CalledProcessError as error:
            raise DeployError(
                f"Image {image} is unavailable after load (exit {error.returncode})"
            ) from None
    QUADLET_DIR.mkdir(parents=True, exist_ok=True)
    if not network.exists():
        network.write_text(network_text, encoding="utf-8")
        network.chmod(0o644)
    for component in components:
        config, files, output, quadlet = component_paths(component)
        render(
            files,
            config_path=config,
            manifests=ROOT / "components" / component / "manifests",
            component=component,
        )
        write_private(output, rendered[component])
        quadlet.write_text(
            QUADLET_TEMPLATE.read_text(encoding="utf-8").replace(
                "Yaml=myproduct.yaml", "Yaml=" + output.name
            ),
            encoding="utf-8",
        )
        quadlet.chmod(0o644)
    run("systemctl", "--user", "daemon-reload")
    for component in components:
        service = "myproduct-" + component + ".service"
        run("systemctl", "--user", "restart", service)
        run("systemctl", "--user", "is-active", "--quiet", service)
        version = (
            (ROOT / ("CORE_VERSION" if component == "core" else "VERSION"))
            .read_text()
            .strip()
        )
        write_private(HOME / "installed" / component, version + "\n")
    run("podman", "ps", "--all", "--pod")


def install():
    """Install the selected component bundle or a standalone manifest fixture."""
    if (ROOT / "bundle.yaml").exists():
        install_components()
    else:
        install_legacy()


def main():
    """Run the chosen deploy command and return an exit code for expected errors."""
    commands = {"prepare": prepare, "install": install}
    args = sys.argv[1:]

    if len(args) != 1 or args[0] not in commands:
        print("Usage: ./deploy prepare|install")
        return 2

    try:
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
