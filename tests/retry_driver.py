"""Run one real deploy invocation in a fresh interpreter with only host transport stubbed."""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    parameters = json.loads(sys.stdin.read())
    root = Path(parameters["root"])
    sys.path.insert(0, str(Path(parameters["source"]).parent.parent))
    lifecycle = importlib.import_module("deployment.deploy")
    common = importlib.import_module("deployment.common")
    rendering = importlib.import_module("deployment.render")
    state = vars(lifecycle)
    # deploy.py calls these through the registrations module, so patch them there.
    registration_state = vars(importlib.import_module("deployment.registrations"))
    # An unpacked release may live outside the persistent home it installs into.
    home = Path(parameters.get("home", str(root / "home")))
    vars(common).update(
        ROOT=root,
        HOME=home,
        BUILD=root / "build",
        QUADLET_DIR=home / ".config/containers/systemd",
        QUADLET_TEMPLATE=root / "quadlet/template.kube",
    )
    state.update(production_environment=lambda: None)
    os.environ["XDG_RUNTIME_DIR"] = str(root)
    events = []
    record = Path(parameters["record"])
    volumes = root / "host-volumes.json"

    def record_event(event):
        events.append(event)
        record.write_text(json.dumps({"pid": os.getpid(), "events": events}))

    def command(arguments, check=False, **kwargs):
        args = list(map(str, arguments))
        record_event(args)
        if args == parameters.get("interrupt"):
            os._exit(99)
        status = 0
        if args == parameters.get("failure"):
            status = 125
        elif args[:3] == ["podman", "volume", "exists"]:
            if parameters.get("volume_check_error") == args[-1]:
                status = 125
            else:
                names = json.loads(volumes.read_text()) if volumes.exists() else []
                status = 0 if args[-1] in names else 1
        elif args[:3] == ["podman", "volume", "rm"]:
            names = json.loads(volumes.read_text())
            names.remove(args[-1])
            volumes.write_text(json.dumps(names))
        if check and status:
            raise subprocess.CalledProcessError(status, args)
        return subprocess.CompletedProcess(args, status)

    subprocess.run = command

    # Containers are healthy at once; the health wait itself has its own tests.
    def container_state(name):
        # Containers of the component named by "unhealthy" fail their check.
        if name.startswith(parameters.get("unhealthy", "\0") + "-"):
            return ("running", "unhealthy")
        return ("running", "healthy")

    vars(importlib.import_module("deployment.health"))["container_state"] = (
        container_state
    )
    archives = rendering.write_file_archives

    def write_archives(groups, directory):
        record_event(["archives", str(directory)])
        if directory.parent.name == parameters.get("archive_failure"):
            raise OSError("Injected import failure")
        return archives(groups, directory)

    vars(rendering)["write_file_archives"] = write_archives
    private = rendering.write_private

    def write_private(path, text):
        if str(path.relative_to(home)) == parameters.get("write_failure"):
            raise OSError("Injected registration failure")
        return private(path, text)

    vars(rendering)["write_private"] = write_private
    replace = os.replace

    def replace_record(source, destination):
        relative = str(Path(destination).relative_to(home))
        if relative == parameters.get("record_failure"):
            raise OSError("Injected install record failure")
        if relative == parameters.get("record_interrupt"):
            # Simulate a process dying with an incompletely written temporary file.
            Path(source).write_text("partial")
            os._exit(99)
        return replace(source, destination)

    os.replace = replace_record
    clear = registration_state["clear_pending"]

    def clear_pending():
        if parameters.get("clear_failure"):
            raise OSError("Injected completion cleanup failure")
        return clear()

    registration_state["clear_pending"] = clear_pending
    registrations = registration_state["write_registrations"]

    def write_registrations(updates, home=None, removals=()):
        # Die after deleting only the first removal, as a crash mid-removal would.
        if parameters.get("removal_interrupt") and removals:
            registrations(updates, home, sorted(removals)[:1])
            os._exit(99)
        return registrations(updates, home, removals)

    registration_state["write_registrations"] = write_registrations
    try:
        if parameters["action"] == "install":
            state["install"]()
        elif parameters["action"] == "init-config":
            state["init_config"](state["bundle_descriptor"]()["name"])
        else:
            state["uninstall"](delete_data=parameters.get("delete_data", False))
    except (common.DeployError, OSError, subprocess.CalledProcessError) as error:
        record_event(["error", type(error).__name__, str(error)])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
