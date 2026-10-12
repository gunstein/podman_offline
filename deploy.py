"""Render Kubernetes YAML for Podman and install it as a Quadlet service.

./deploy prepare   Dev: write build/install.yaml (+ build/files/*.tar).

Filer angis i config.yaml under SECRET_FILES og VOLUME_FILES (id -> filer).
./deploy install   Prod (tjenestebruker): render, podman load, install Quadlet, restart.
"""

import base64
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
MANIFESTS = ROOT / "manifests"
CONFIG = ROOT / "config.yaml"

QUADLET_TEMPLATE = ROOT / "quadlet" / "myproduct.kube"
QUADLET_DIR = Path.home() / ".config/containers/systemd"
QUADLET_TARGET = QUADLET_DIR / "myproduct.kube"
QUADLET_YAML = QUADLET_DIR / "myproduct.yaml"  # Yaml=myproduct.yaml i .kube
SERVICE = "myproduct.service"

# Filer fra config.yaml (se config.example.yaml):
#   SECRET_FILES: id -> filer som blir én Secret per id (én nøkkel per fil)
#   VOLUME_FILES: id -> filer som lastes inn i ett Podman-volum per id
SECRET_FILES = "SECRET_FILES"
VOLUME_FILES = "VOLUME_FILES"

# Tar-arkiver for VOLUME_FILES. Podman importerer dem i volumene ved hver
# oppstart, så de må ligge fast i tjenestebrukerens hjemmekatalog.
FILES_DIR = Path.home() / "files"
IMPORT_SOURCE = "volume.podman.io/import-source"

ID = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
SECRET_KEY = re.compile(r"^[-._a-zA-Z0-9]+$")
# Podman avviser secrets over 512 000 byte (hele Secret-dokumentet).
MAX_SECRET_SIZE = 500000

PH = re.compile(r"^@@([A-Z0-9_]+)@@$")
MAX_PORT = 65535


class DeployError(Exception):
    """Feil som vises som én ERROR-linje uten traceback."""


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader som avviser dupliserte nøkler i stedet for å ta siste verdi."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplikat nøkkel {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_yaml(path):
    with path.open(encoding="utf-8") as f:
        # UniqueKeyLoader arver SafeLoader, så dette er like trygt som safe_load.
        return yaml.load(f, Loader=UniqueKeyLoader)


def load_yaml_all(path):
    with path.open(encoding="utf-8") as f:
        return list(yaml.load_all(f, Loader=UniqueKeyLoader))


def load_config(path):
    config = load_yaml(path)

    if not isinstance(config, dict):
        raise DeployError(f"{path} må inneholde KEY: verdi-par")

    for key, value in config.items():
        if not isinstance(key, str):
            raise DeployError("Alle nøkler i config.yaml må være tekst")

        if key in (SECRET_FILES, VOLUME_FILES):
            continue  # valideres i load_file_group()

        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise DeployError(
                f"{key} i config.yaml må være tekst eller heltall, "
                f"fikk {value!r}. Sett tekst i anførselstegn."
            )

    port = config.get("HTTPS_PORT")
    if not isinstance(port, int) or not 1 <= port <= MAX_PORT:
        raise DeployError(
            f"HTTPS_PORT i config.yaml må være et heltall 1-{MAX_PORT} "
            f"uten anførselstegn, fikk {port!r}"
        )

    return config


def replace(value, config):
    if isinstance(value, dict):
        return {key: replace(item, config) for key, item in value.items()}

    if isinstance(value, list):
        return [replace(item, config) for item in value]

    if isinstance(value, str):
        match = PH.fullmatch(value)
        if match:
            key = match.group(1)
            if key not in config:
                raise DeployError(f"Mangler {key} i config.yaml")
            return config[key]

    return value


def write_private(path, text):
    """Skriv filen med mode 0600 fra første byte."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)  # i tilfelle filen fantes med annen mode
        f.write(text)


def resolve_path(value):
    """Relativ sti regnes fra prosjekt-/bundle-roten. ~ er tillatt."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def load_file_group(config, group):
    """Les SECRET_FILES eller VOLUME_FILES: {id: [fil eller katalog, ...]}.

    Returner {id: [Path, ...]} med det som skal ligge på toppnivå:
    en fil er seg selv, en katalog bidrar med innholdet sitt.
    """
    spec = config.get(group) or {}

    if not isinstance(spec, dict):
        raise DeployError(f"{group} i config.yaml må være id: [liste med filer]")

    groups = {}

    for group_id, entries in spec.items():
        where = f"{group}.{group_id}"

        if not isinstance(group_id, str) or not ID.fullmatch(group_id):
            raise DeployError(
                f"Ugyldig id {group_id!r} i {group}. Bruk små bokstaver, tall og -"
            )

        if (
            not isinstance(entries, list)
            or not entries
            or not all(isinstance(entry, str) for entry in entries)
        ):
            raise DeployError(f"{where} må være en liste med filstier")

        items = []

        for path in (resolve_path(entry) for entry in entries):
            if not path.exists():
                raise DeployError(f"Mangler {path} ({where})")
            items += sorted(path.iterdir()) if path.is_dir() else [path]

        names = [item.name for item in items]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise DeployError(f"{where} har flere filer med samme navn: {duplicates}")

        if group == SECRET_FILES:
            for item in items:
                if not item.is_file():
                    raise DeployError(
                        f"{where}: {item} er en katalog. Secrets kan bare "
                        "inneholde filer; bruk VOLUME_FILES for katalogtrær"
                    )
                if not SECRET_KEY.fullmatch(item.name):
                    raise DeployError(
                        f"{where}: filnavnet {item.name!r} kan bare inneholde "
                        "bokstaver, tall, . - og _"
                    )

        groups[group_id] = items

    return groups


def secret_documents(secrets):
    """Én Secret per SECRET_FILES-id. Hver fil blir én fil i containeren."""
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
                f"{SECRET_FILES}.{secret_id} er for stor for en Podman-secret "
                f"(maks ca. {MAX_SECRET_SIZE * 3 // 4} byte filinnhold). "
                "Bruk VOLUME_FILES for store filer"
            )

        docs.append(doc)

    return docs


def normalize(info):
    """Like rettigheter uansett hvordan filene ser ut på maskinen de kom fra."""
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mode = 0o755 if info.isdir() or info.mode & 0o111 else 0o644
    return info


def archive_path(files_dir, volume_id):
    return files_dir / f"{volume_id}.tar"


def write_file_archives(volumes, files_dir):
    """Lag ett tar-arkiv per VOLUME_FILES-id."""
    if not volumes:
        return

    files_dir.mkdir(parents=True, exist_ok=True)
    files_dir.chmod(0o700)

    for volume_id, items in volumes.items():
        archive = archive_path(files_dir, volume_id)
        fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)

        with os.fdopen(fd, "wb") as raw:
            os.fchmod(raw.fileno(), 0o600)
            # dereference=True: en symlink lagres som filen den peker på.
            with tarfile.open(fileobj=raw, mode="w", dereference=True) as tar:
                for item in items:
                    tar.add(str(item), arcname=item.name, filter=normalize)


def volume_claims(volumes, files_dir):
    """Én PVC per VOLUME_FILES-id. Podman lager volumet og pakker ut arkivet."""
    return [
        {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": volume_id,
                "annotations": {IMPORT_SOURCE: str(archive_path(files_dir, volume_id))},
            },
            # Podman bruker ikke spec, men Kubernetes krever feltene.
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "1Gi"}},
            },
        }
        for volume_id in volumes
    ]


def references(value, found):
    """Finn alle Secret- og PVC-navn manifestene bruker."""
    if isinstance(value, dict):
        secret = value.get("secret")
        if isinstance(secret, dict) and "secretName" in secret:
            found.add(("Secret", secret["secretName"]))

        claim = value.get("persistentVolumeClaim")
        if isinstance(claim, dict) and "claimName" in claim:
            found.add(("PersistentVolumeClaim", claim["claimName"]))

        for key in ("secretKeyRef", "secretRef"):
            ref = value.get(key)
            if isinstance(ref, dict) and "name" in ref:
                found.add(("Secret", ref["name"]))

        for item in value.values():
            references(item, found)

    elif isinstance(value, list):
        for item in value:
            references(item, found)

    return found


def check_links(docs, from_config):
    """Sjekk at config-id-er og manifest-referanser passer sammen.

    from_config: {(kind, navn): "SECRET_FILES.id" / "VOLUME_FILES.id"}
    """
    defined = [
        (doc.get("kind"), (doc.get("metadata") or {}).get("name"))
        for doc in docs
        if isinstance(doc, dict)
        and doc.get("kind") in ("Secret", "PersistentVolumeClaim", "ConfigMap")
    ]

    names = [name for _, name in defined]
    for name in sorted({n for n in names if names.count(n) > 1}, key=str):
        raise DeployError(
            f"Navnet {name!r} er definert flere ganger som Secret/PVC/ConfigMap. "
            "Podman lager ett volum per navn, så navnene må være unike på tvers av typene"
        )

    defined = {(kind, name) for kind, name in defined if kind != "ConfigMap"}
    used = references(docs, set())

    for kind, name in sorted(used - set(defined)):
        group = SECRET_FILES if kind == "Secret" else VOLUME_FILES
        raise DeployError(
            f"Et manifest bruker {kind} {name!r}, men den finnes ikke. "
            f"Legg den til under {group} i config.yaml eller i et manifest"
        )

    for key, where in sorted(from_config.items()):
        if key not in used:
            raise DeployError(
                f"{where} i config.yaml brukes ikke av noe manifest. "
                "Sjekk at id-en er lik secretName/claimName i manifestet"
            )


def render(files_dir=None, write_archives=True):
    """Returner ferdig install-YAML som tekst.

    Skriver bare tar-arkivene for VOLUME_FILES (til files_dir, standard
    build/files), og først når alt annet er validert. Med write_archives=False
    valideres og rendres YAML uten å skrive arkiver.
    """
    if not CONFIG.exists():
        raise DeployError(f"Mangler {CONFIG}")

    files_dir = files_dir or BUILD / "files"
    config = load_config(CONFIG)
    secrets = load_file_group(config, SECRET_FILES)
    volumes = load_file_group(config, VOLUME_FILES)

    docs: list = secret_documents(secrets) + volume_claims(volumes, files_dir)

    for path in sorted(MANIFESTS.glob("*.yaml")):
        docs += [
            replace(document, config)
            for document in load_yaml_all(path)
            if document is not None
        ]

    for doc in docs:
        if isinstance(doc, dict) and doc.get("kind") == "ConfigMap":
            data = doc.get("data") or {}
            if not isinstance(data, dict):
                raise DeployError("ConfigMap.data må være et map")
            doc["data"] = {str(key): str(value) for key, value in data.items()}

    from_config = {("Secret", i): f"{SECRET_FILES}.{i}" for i in secrets}
    from_config.update(
        {("PersistentVolumeClaim", i): f"{VOLUME_FILES}.{i}" for i in volumes}
    )
    check_links(docs, from_config)

    text = yaml.safe_dump_all(docs, sort_keys=False)

    # Base64 inneholder aldri '@', så Secret-data gir ikke falske treff.
    if "@@" in text:
        raise DeployError(
            'Uerstattet @@...@@ i manifestene. Kun hele verdier som "@@NAVN@@" støttes.'
        )

    if write_archives:
        write_file_archives(volumes, files_dir)
    return text


def prepare():
    output = BUILD / "install.yaml"
    write_private(output, render())
    print(f"[OK] {output}")


def run(*args):
    print("+", " ".join(map(str, args)))
    subprocess.run(list(map(str, args)), check=True)


def find_images(documents):
    """Finn unike, fullt kvalifiserte images i pod-spesifikasjoner."""
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
                        if not isinstance(image, str) or not image.strip():
                            raise DeployError("Container må ha et image-navn som tekst")
                        if "@@" in image:
                            raise DeployError(
                                f"Image {image}: placeholders støttes ikke"
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
                                f"Image {image} må være fullt kvalifisert"
                            )
                        images.add(image)
                pending.append(child)
    if not images:
        raise DeployError("Ingen images funnet i manifestene")
    return sorted(images)


def install():
    if os.geteuid() == 0:
        raise DeployError("Kjør install som tjenestebrukeren, ikke som root")

    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.geteuid()}")
    if not runtime.is_dir():
        raise DeployError(
            f"Mangler runtime-katalog {runtime}. Aktiver linger for tjenestebrukeren "
            "med loginctl enable-linger og kontroller at brukerinstansen kjører"
        )
    os.environ["XDG_RUNTIME_DIR"] = str(runtime)

    text = render(FILES_DIR, write_archives=False)
    archive = ROOT / "images" / "images.tar"
    if not archive.is_file():
        raise DeployError(f"Mangler image-arkivet {archive}")
    run("podman", "load", "-i", archive)
    for image in find_images(yaml.safe_load_all(text)):
        try:
            run("podman", "image", "exists", image)
        except subprocess.CalledProcessError as error:
            raise DeployError(
                f"Image {image} er ikke tilgjengelig etter podman load "
                f"(podman image exists ga exit {error.returncode})"
            ) from None

    render(FILES_DIR)  # Skriv importarkivene først etter vellykket image-sjekk.

    # YAML og Quadlet ligger fast i tjenestebrukerens hjem, også etter reboot.
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

    print(f"[OK] {SERVICE} kjører. Sjekk at containerne over er 'Up'.")


def main():
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
                f"Feilsøk: journalctl --user -u {SERVICE} og "
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
