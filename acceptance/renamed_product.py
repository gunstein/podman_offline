"""Derive a renamed product from the shipped demo using declarations only.

The renamed product reuses the demo's application images and code. Only YAML,
route/client descriptors and runtime settings change, which is what a product
owner would edit, including the product name `shop` in bundles.yaml:

    python3 acceptance/renamed_product.py generate SOURCE TARGET
    python3 acceptance/renamed_product.py credentials ROOT HOSTNAME [COMPONENT...]

`generate` copies the files Git tracks in SOURCE (so no local dev config,
credentials or build output) and replaces components/ and bundles.yaml. The
renamed product models the fixed acceptance matrix, so demo components outside
NAMES (app3, backlog 71) are left out. `credentials` runs the demo provisioning script for the matching
demo component and moves the result to the renamed component's directory.

Public URL paths are application settings, not component IDs: orders serves
/orders, inventory serves /stock with OIDC client ID `inventory`, and orders
uses client ID `orders-web`. Identity keeps its /identity path and the manual
keeps /help because those paths are compiled into their applications.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

NAMES = {
    "platform": "gateway",
    "identity": "login-service",
    "app1": "orders",
    "app2": "inventory",
    "help": "manual",
}
# The product name: service user, units, network and archive names on the target.
PRODUCT = "shop"
PATHS = {"/app1": "/orders", "/app2": "/stock"}
# A product-owned setting the gateway shares (backlog 26); its public_from
# dependents inherit it at init-config and must keep the same value.
SHARED = {"SHOP_NAME": "Renamed shop"}
CLIENT_IDS = {"app1": "orders-web", "app2": "inventory"}


def rename(value):
    """Rename a component ID or a resource name that carries a component prefix."""
    for old, new in NAMES.items():
        if value == old:
            return new
        if value.startswith(old + "-"):
            return new + value[len(old) :]
    return value


def rename_references(value):
    """Rename resource names in a manifest; image names stay unchanged."""
    if isinstance(value, list):
        return [rename_references(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == "image":
            result[key] = item
        elif key == "metadata" and isinstance(item, dict) and "name" in item:
            result[key] = dict(item, name=rename(item["name"]))
        elif key in ("claimName", "secretName") and isinstance(item, str):
            result[key] = rename(item)
        elif (
            key in ("configMap", "configMapRef", "secretRef", "secretKeyRef")
            and isinstance(item, dict)
            and "name" in item
        ):
            result[key] = dict(rename_references(item), name=rename(item["name"]))
        else:
            result[key] = rename_references(item)
    return result


def rename_environment(document, component):
    """Point the app at its own client ID and base path, and its database host."""
    for spec in (document.get("spec") or {},):
        for group in ("containers", "initContainers"):
            for container in spec.get(group, []):
                for variable in container.get("env", []):
                    if variable.get("name") == "APP_ID" and component in CLIENT_IDS:
                        variable["value"] = CLIENT_IDS[component]
                    elif variable.get("name") == "BASE_PATH":
                        variable["value"] = PATHS.get(
                            variable["value"], variable["value"]
                        )
    return document


def rename_route(text):
    """Rename upstream hosts, nginx variables and the mapped public paths."""
    for old, new in NAMES.items():
        text = re.sub(r"\$" + old + "_", "$" + new.replace("-", "_") + "_", text)
        text = re.sub(
            r"(?<![\w$/.-])" + old + r"-(?=[a-z0-9-]*:[0-9])", new + "-", text
        )
    for old, new in PATHS.items():
        text = re.sub(r"(?<![\w-])" + re.escape(old) + r"(?![\w-])", new, text)
    return text


def rename_defaults(config):
    """Rename prefixed file-source IDs and the database host."""
    result = dict(config)
    for group in ("SECRET_FILES", "VOLUME_FILES", "SECRET_TEMPLATES"):
        if group in result:
            result[group] = {rename(key): value for key, value in result[group].items()}
    if "SECRET_TEMPLATES" in result:
        result["SECRET_TEMPLATES"] = {
            name: {
                key: re.sub(
                    r"@@secret:([^/]+)/",
                    lambda match: "@@secret:" + rename(match[1]) + "/",
                    text,
                )
                for key, text in values.items()
            }
            for name, values in result["SECRET_TEMPLATES"].items()
        }
    if "DB_HOST" in result:
        result["DB_HOST"] = rename(result["DB_HOST"])
    return result


def rename_client(descriptor, component):
    client_id = CLIENT_IDS[component]
    return dict(
        descriptor,
        id=client_id,
        base_path=PATHS[descriptor["base_path"]],
        scopes=["openid", "profile", client_id],
    )


def rename_catalog(data):
    entries = {}
    for name, entry in data["components"].items():
        entry = dict(entry or {})
        if "requires" in entry:
            entry["requires"] = [rename(value) for value in entry["requires"]]
        for key in ("public_from", "routes", "clients", "apis"):
            if key in entry:
                entry[key] = rename(entry[key])
        if "accepts" in entry:
            entry["accepts"] = {
                role: rename(volume) for role, volume in entry["accepts"].items()
            }
        if rename(name) == "gateway":
            entry["shares"] = sorted(SHARED)
        entries[rename(name)] = entry
    return {"product": PRODUCT, "components": entries}


def dump(path, data, multiple=False):
    with path.open("w", encoding="utf-8") as stream:
        if multiple:
            yaml.safe_dump_all(data, stream, sort_keys=False)
        else:
            yaml.safe_dump(data, stream, sort_keys=False)


def copy_tracked_files(source, target):
    """Copy only files Git tracks, never local config, credentials or build output."""
    listing = subprocess.run(
        ["git", "-C", str(source), "ls-files", "-z"],
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.decode("utf-8")
    for relative in filter(None, listing.split("\0")):
        origin = source / relative
        if not origin.is_file():
            continue  # Deleted in the working tree but not yet committed.
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(origin), str(destination))


def generate(source, target):
    """Write the renamed checkout; the target must not exist yet."""
    if target.exists():
        raise SystemExit(f"FAIL: {target} already exists")
    copy_tracked_files(source, target)
    shutil.rmtree(str(target / "components"))
    with (source / "bundles.yaml").open(encoding="utf-8") as stream:
        catalog = yaml.safe_load(stream)
    catalog["components"] = {
        name: entry for name, entry in catalog["components"].items() if name in NAMES
    }
    dump(target / "bundles.yaml", rename_catalog(catalog))
    for old in catalog["components"]:
        new = rename(old)
        origin, destination = source / "components" / old, target / "components" / new
        (destination / "manifests").mkdir(parents=True)
        shutil.copy2(str(origin / "VERSION"), str(destination / "VERSION"))
        if (origin / "files").exists():
            shutil.copytree(str(origin / "files"), str(destination / "files"))
        for manifest in sorted((origin / "manifests").glob("*.yaml")):
            with manifest.open(encoding="utf-8") as stream:
                documents = [
                    rename_environment(rename_references(document), old)
                    for document in yaml.safe_load_all(stream)
                    if document is not None
                ]
            dump(destination / "manifests" / manifest.name, documents, multiple=True)
        defaults = origin / "config.defaults.yaml"
        if defaults.exists():
            with defaults.open(encoding="utf-8") as stream:
                values = rename_defaults(yaml.safe_load(stream))
            if new == "gateway":
                values.update(SHARED)
            dump(destination / defaults.name, values)
        dev_config = origin / "config.dev.yaml"
        if dev_config.exists():
            with dev_config.open(encoding="utf-8") as stream:
                dump(
                    destination / dev_config.name,
                    rename_defaults(yaml.safe_load(stream)),
                )
        if (origin / "route.conf").exists():
            (destination / "route.conf").write_text(
                rename_route((origin / "route.conf").read_text(encoding="utf-8")),
                encoding="utf-8",
            )
        if (origin / "client.yaml").exists():
            with (origin / "client.yaml").open(encoding="utf-8") as stream:
                dump(
                    destination / "client.yaml",
                    rename_client(yaml.safe_load(stream), old),
                )
    print(f"PASS: renamed product written to {target}")


def credentials(root, hostname, components):
    """Provision demo credentials, then move them to the renamed directories.

    Existing renamed credentials are moved back first, so the demo script keeps
    them byte-for-byte instead of generating new keys.
    """
    script = Path(__file__).resolve().parent.parent / "dev/generate-certificates.sh"
    old_names = {new: old for old, new in NAMES.items()}
    for component in components or list(old_names):
        old = old_names[component]
        renamed, demo = root / component / "credentials", root / old / "credentials"
        if demo.exists():
            raise SystemExit(f"FAIL: unexpected demo credential directory {demo}")
        if renamed.exists():
            demo.parent.mkdir(mode=0o700, exist_ok=True)
            renamed.rename(demo)
        subprocess.run(
            ["bash", str(script), "--root", str(root), old, hostname], check=True
        )
        renamed.parent.mkdir(mode=0o700, exist_ok=True)
        demo.rename(renamed)
        demo.parent.rmdir()
    print("PASS: demo credentials provisioned for the renamed components")


def main(arguments):
    if len(arguments) == 3 and arguments[0] == "generate":
        generate(Path(arguments[1]).resolve(), Path(arguments[2]).resolve())
    elif len(arguments) >= 3 and arguments[0] == "credentials":
        credentials(Path(arguments[1]).resolve(), arguments[2], arguments[3:])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
