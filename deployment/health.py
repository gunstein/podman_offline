"""Wait until an installed unit's containers are running and healthy.

systemctl is-active only says that kube play started the pod; a container can
still crash or fail its health check. Install, upgrade and owner restarts wait
here before they count as done. Only container names and states are read from
podman inspect; nothing else is printed.
"""

import json
import subprocess
import time

from . import common
from . import render as rendering

# The acceptance harness uses the same limit; the demo apps need about 15 s.
TIMEOUT = 150
INTERVAL = 2


def expected_containers(path):
    """The app containers of an installed YAML; kube play names them <pod>-<name>."""
    documents = rendering.load_yaml_all(path)
    return sorted(
        str((pod.get("metadata") or {}).get("name")) + "-" + str(container.get("name"))
        for pod, spec in rendering.pod_specs(documents, path)
        for container in spec.get("containers", [])
    )


def container_state(name):
    """Return (status, health) of one container, or None while it does not exist.

    health is '' for a container without a health check.
    """
    result = subprocess.run(  # noqa: UP022 - Python 3.6
        ["podman", "container", "inspect", "--format", "json", name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,  # noqa: UP021 - Python 3.6
        check=False,
    )
    if result.returncode:
        return None
    try:
        state = json.loads(result.stdout)[0]["State"]
        status = state["Status"]
        health = (state.get("Health") or {}).get("Status") or ""
    except (ValueError, LookupError, TypeError, AttributeError):
        raise common.DeployError(
            f"Unreadable podman inspect state for {name}"
        ) from None
    return str(status), str(health)


def wait_healthy(unit, path):
    """Wait until every app container in path runs and is healthy (if checked).

    unit names the systemd service for the error hint. An unhealthy container
    fails at once; anything else not yet ready is retried until TIMEOUT.
    """
    names = expected_containers(path)
    deadline = time.monotonic() + TIMEOUT
    while True:
        waiting = {}
        for name in names:
            state = container_state(name)
            if state and state[1] == "unhealthy":
                raise common.DeployError(
                    f"Container {name} is unhealthy. Troubleshoot: journalctl --user "
                    f"-u {unit} and podman logs {name}"
                )
            if (
                state is None
                or state[0] != "running"
                or state[1] not in ("healthy", "")
            ):
                waiting[name] = state
        if not waiting:
            print(f"[OK] {unit}: {len(names)} containers running and healthy")
            return
        if time.monotonic() >= deadline:
            details = ", ".join(
                f"{name} ({'/'.join(filter(None, state)) if state else 'missing'})"
                for name, state in sorted(waiting.items())
            )
            raise common.DeployError(
                f"{unit} is active, but after {TIMEOUT}s these containers are not "
                f"running and healthy: {details}. Troubleshoot: journalctl --user "
                f"-u {unit} and podman logs <container>"
            )
        time.sleep(INTERVAL)
