"""Run one real deploy invocation in a fresh interpreter with only host transport stubbed."""

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path


def main():
    parameters = json.loads(sys.stdin.read())
    root = Path(parameters["root"])
    namespace = runpy.run_path(parameters["source"])
    state = namespace["install"].__globals__
    state.update(
        ROOT=root,
        HOME=root / "home",
        BUILD=root / "build",
        QUADLET_DIR=root / "home/.config/containers/systemd",
        QUADLET_TEMPLATE=root / "quadlet/myproduct.kube",
        production_environment=lambda: None,
        legacy_volume_exists=lambda name: False,
    )
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
    archives = state["write_file_archives"]

    def write_archives(groups, directory):
        record_event(["archives", str(directory)])
        if directory.parent.name == parameters.get("archive_failure"):
            raise OSError("Injected import failure")
        return archives(groups, directory)

    state["write_file_archives"] = write_archives
    private = state["write_private"]

    def write_private(path, text):
        if str(path.relative_to(root / "home")) == parameters.get("write_failure"):
            raise OSError("Injected registration failure")
        return private(path, text)

    state["write_private"] = write_private
    clear = state["clear_pending"]

    def clear_pending():
        if parameters.get("clear_failure"):
            raise OSError("Injected completion cleanup failure")
        return clear()

    state["clear_pending"] = clear_pending
    try:
        if parameters["action"] == "install":
            state["install"]()
        elif parameters["action"] == "init-config":
            state["init_config"](state["bundle_components"]()[0])
        else:
            state["uninstall"](delete_data=parameters.get("delete_data", False))
    except (state["DeployError"], OSError, subprocess.CalledProcessError) as error:
        record_event(["error", type(error).__name__, str(error)])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
