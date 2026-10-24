"""Read installed markers/metadata and pending work, then query user unit states."""

import json
import subprocess

from . import catalog, common, deploy, registrations

# Never echo arbitrary command output (e.g. a bus error) as a unit state.
UNIT_STATES = {
    "active",
    "reloading",
    "inactive",
    "failed",
    "activating",
    "deactivating",
    "maintenance",
    "refreshing",
    "unknown",
}


def unit_state(unit):
    """A failed/missing unit or unavailable user manager is a finding, not a crash."""
    try:
        result = subprocess.run(  # noqa: UP022 - Python 3.6
            ["systemctl", "--user", "is-active", unit],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,  # noqa: UP021 - Python 3.6
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return "unavailable"
    state = result.stdout.strip()
    if state not in UNIT_STATES or (state == "active" and result.returncode != 0):
        return "unavailable"
    return state


def marker_version(name):
    """Reject symlinked/nonregular markers and validate the completed version."""
    marker = common.STATE / "installed" / name
    if marker.is_symlink() or (marker.exists() and not marker.is_file()):
        raise common.DeployError(f"Invalid installed marker {marker}")
    try:
        version = catalog.installed_version(common.STATE, name)
        if version is not None:
            catalog.version_number(version)
    except (OSError, UnicodeError, common.DeployError):
        raise common.DeployError(f"Invalid installed marker {marker}") from None
    return version


def collect():
    """Use this bundle only to select the product/code, never its incoming version."""
    if not (common.ROOT / "bundle.yaml").is_file():
        raise common.DeployError("Run status from an unpacked component bundle")
    deploy.service_user()  # Read-only identity/bootstrap/layout; no manager query.
    product = catalog.product_name(common.ROOT)
    descriptors = catalog.load_installed_metadata(common.STATE)
    deploy.check_same_product(product, descriptors)
    catalog.installed_components(common.STATE, descriptors)
    pending = registrations.load_pending()
    if pending is not None and pending["product"] != product:
        raise common.DeployError("Pending operation belongs to another product")
    if pending is not None:
        pending = {key: pending[key] for key in ("operation", "component", "owners")}
    components = []
    for name in catalog.dependency_order(descriptors):
        version = marker_version(name)
        recorded = descriptors[name]["version"]
        components.append(
            {
                "name": name,
                "version": version,
                "recorded_version": recorded,
                "unit": catalog.unit_name(name) + ".service",
                "complete": version is not None and version == recorded,
            }
        )
    # Validate all state files before the first host query.
    for component in components:
        component["state"] = unit_state(component["unit"])
    return {"product": product, "components": components, "pending": pending}


def status(json_output=False):
    """Print one snapshot. Empty, incomplete, pending or non-active means exit 1."""
    report = collect()
    if json_output:
        print(json.dumps(report, sort_keys=True))
    else:
        print("COMPONENT VERSION UNIT STATE INSTALLATION")
        for component in report["components"]:
            detail = (
                "installed"
                if component["complete"]
                else ("incomplete (recorded " + component["recorded_version"] + ")")
            )
            print(
                f"{component['name']} {component['version'] or '-'} "
                f"{component['unit']} {component['state']} {detail}"
            )
        if not report["components"]:
            print("No installed components.")
        print("Product: " + report["product"])
        pending = report["pending"]
        if pending is None:
            print("Pending: none")
        else:
            owners = ", ".join(pending["owners"]) or "none"
            print(
                f"Pending: {pending['operation']} {pending['component']}; owners: {owners}"
            )
    successful = (
        bool(report["components"])
        and report["pending"] is None
        and all(
            component["complete"] and component["state"] == "active"
            for component in report["components"]
        )
    )
    return 0 if successful else 1
