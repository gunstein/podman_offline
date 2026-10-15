# ruff: noqa: UP021, UP022 - host/test code retains Python 3.6 APIs
"""Private historical-upgrade observations and explicit operator config additions.

Sent over stdin by upgrade_020.py; never logs password bytes or private hashes.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

HOME = Path.home()
SNAPSHOT = HOME / ".upgrade-020.json"
COMPONENTS = ("core", "app1", "app2")


def command(args):
    """Keep inspect/trust output private, including on failure."""
    result = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError("Upgrade observation command failed (details withheld)")
    return result.stdout


def observe():
    """Capture immutable credentials, configs, import archives, volumes and service identity."""
    files = {}
    for component in COMPONENTS:
        paths = [HOME / component / "config.yaml"]
        for directory in ("generated-certificates", "files"):
            paths.extend(
                path
                for path in (HOME / component / directory).rglob("*")
                if path.is_file()
            )
        route = HOME / "routes" / (component + ".conf")
        if route.is_file():
            paths.append(route)
        paths.extend(
            path for path in (HOME / "clients" / component).rglob("*") if path.is_file()
        )
        for suffix in ("yaml", "kube"):
            paths.append(
                HOME
                / ".config/containers/systemd"
                / ("myproduct-" + component + "." + suffix)
            )
        files[component] = {
            str(path.relative_to(HOME)): {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "mode": path.stat().st_mode & 0o777,
            }
            for path in paths
        }
    passwords = ["core/generated-certificates/identity-db/password"] + [
        name + "/generated-certificates/database/password" for name in ("app1", "app2")
    ]
    if any(name not in files[name.split("/")[0]] for name in passwords):
        raise RuntimeError("Missing legacy database password evidence")
    volumes = {}
    for name in ("core-identity-data", "app1-data", "app2-data"):
        rows = json.loads(command(["podman", "volume", "inspect", name]))
        if not isinstance(rows, list) or len(rows) != 1:
            raise RuntimeError("Incomplete database volume observation")
        row = rows[0]
        volumes[name] = {key: row[key] for key in ("Name", "Mountpoint", "CreatedAt")}
    services = {}
    for component in COMPONENTS:
        properties = command(
            [
                "systemctl",
                "--user",
                "show",
                "myproduct-" + component + ".service",
                "--property=ActiveState,InvocationID,ExecMainStartTimestampMonotonic",
            ]
        ).strip()
        values = dict(line.split("=", 1) for line in properties.splitlines())
        if (
            values.get("ActiveState") != "active"
            or not values.get("InvocationID")
            or not values.get("ExecMainStartTimestampMonotonic", "").isdigit()
            or int(values["ExecMainStartTimestampMonotonic"]) <= 0
        ):
            raise RuntimeError("Invalid service observation")
        services[component] = properties
    containers = {}
    names = ["core-identity-postgres-db", "core-identity-app", "core-proxy-nginx"]
    names += [
        component + suffix
        for component in ("app1", "app2")
        for suffix in ("-postgres-db", "-todo-backend", "-todo-frontend")
    ]
    rows = json.loads(command(["podman", "inspect", "--format", "json"] + names))
    if not isinstance(rows, list) or len(rows) != len(names):
        raise RuntimeError("Incomplete container observation")
    for row in rows:
        name, state = row["Name"], row["State"]
        if (
            name not in names
            or name in containers
            or state["Status"] != "running"
            or state["Health"]["Status"] != "healthy"
            or type(state["Pid"]) is not int
            or state["Pid"] <= 1
            or not state["StartedAt"]
            or not row["Id"]
        ):
            raise RuntimeError("Invalid container observation")
        containers[name] = {
            "Id": row["Id"],
            "Pid": state["Pid"],
            "StartedAt": state["StartedAt"],
            "RestartCount": row["RestartCount"],
        }
    return {
        "containers": containers,
        "files": files,
        "volumes": volumes,
        "services": services,
        "versions": {
            name: (HOME / "installed" / name).read_text().strip() for name in COMPONENTS
        },
    }


def save(state):
    """Keep the comparison evidence private on the service-user host."""
    temporary = SNAPSHOT.with_suffix(".pending")
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(state, stream)
    temporary.replace(SNAPSHOT)


def migrate(component):
    """Apply exactly README's manual fields/list addition without changing identities."""
    path = HOME / component / "config.yaml"
    config = yaml.safe_load(path.read_text())
    expected = {
        "DB_HOST": "core-identity-postgres"
        if component == "core"
        else component + "-postgres",
        "DB_PORT": "5432",
        "DB_USER": "identity" if component == "core" else "todo",
        "DB_NAME": "identity" if component == "core" else "todo",
    }
    if any(key in config for key in expected):
        raise RuntimeError("Legacy config already contains database parameters")
    config.update(expected)
    relative = (
        "generated-certificates/"
        + ("identity-db" if component == "core" else "database")
        + "/password"
    )
    if relative in config["GENERATED_SECRETS"]:
        raise RuntimeError("Legacy password already declared")
    config["GENERATED_SECRETS"].append(relative)
    with path.open("w") as stream:
        yaml.safe_dump(config, stream)


def main(action, version):
    """Verify both staged upgrades without repairing or rotating database state."""
    if action.startswith("trust-"):
        # fapolicyd's database is read through the privileged remote action below;
        # service-user checks here prove markers/sibling service remain unchanged.
        state = json.loads(SNAPSHOT.read_text())
        current = observe()
        if current != state["expected"]:
            raise RuntimeError("State changed during trust retirement")
    elif action == "baseline":
        if SNAPSHOT.exists():
            raise RuntimeError("Historical snapshot already exists")
        current = observe()
        if set(current["versions"].values()) != {"0.2.0"}:
            raise RuntimeError("Baseline is not an installed 0.2.0 release")
        save({"old": current, "expected": current})
    elif action.startswith("migrate-"):
        state = json.loads(SNAPSHOT.read_text())
        if observe() != state["expected"]:
            raise RuntimeError("State drift before manual migration")
        selected = ("core", "app1") if action == "migrate-app1" else ("app2",)
        for component in selected:
            migrate(component)
        current = observe()
        # Only the selected persistent configs may change in this operator step.
        expected = state["expected"]
        for component in selected:
            name = component + "/config.yaml"
            expected["files"][component][name] = current["files"][component][name]
        if current != expected:
            raise RuntimeError("Manual migration changed unrelated state")
        state["expected"] = current
        save(state)
    elif action in ("check-app1", "check-app2"):
        state = json.loads(SNAPSHOT.read_text())
        current, expected = observe(), state["expected"]
        if current["volumes"] != state["old"]["volumes"]:
            raise RuntimeError("Database volume identity changed")
        selected = ("core", "app1") if action == "check-app1" else ("app2",)
        for component in COMPONENTS:
            if component not in selected:
                for name, identity in expected["containers"].items():
                    if (
                        name.startswith(component + "-")
                        and current["containers"].get(name) != identity
                    ):
                        raise RuntimeError("Untouched sibling container changed")
                for key in ("files", "versions", "services"):
                    if current[key][component] != expected[key][component]:
                        raise RuntimeError("Untouched sibling changed")
                continue
            if current["versions"][component] != version:
                raise RuntimeError("Upgrade version marker missing")

            # Rendering/imports may change, but every credential and the manually
            # edited config must remain byte-for-byte, with no additions/removals.
            def protected_files(snapshot, component=component):
                return {
                    name: value
                    for name, value in snapshot["files"][component].items()
                    if "/generated-certificates/" in name
                    or name.endswith("/config.yaml")
                }

            if protected_files(current) != protected_files(expected):
                raise RuntimeError("Credentials or persistent config changed")
        state["expected"] = current
        save(state)
    else:
        raise RuntimeError("Unknown historical upgrade action")
    print("PASS: historical upgrade " + action)


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception:  # noqa: BLE001 - withhold private observation details
        raise SystemExit(
            "FAIL: historical upgrade state check (details withheld)"
        ) from None
