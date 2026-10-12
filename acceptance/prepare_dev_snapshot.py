#!/usr/bin/env python3
"""Create clean-dev from clean-agent on DEV only; preserve the source snapshot."""

import argparse
import datetime
import ipaddress
import json
import re
import shlex
import subprocess
import time

from pve import Proxmox, env_file

SSH = [
    "ssh",
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "ConnectTimeout=8",
]


def ssh(host, script):
    print("$ ssh " + host + " bash -se\n" + script, flush=True)
    subprocess.run(SSH + [host, "bash -se"], input=script, text=True, check=True)


def wait_ssh(host):
    for _ in range(80):
        result = subprocess.run(
            SSH + [host, "true"],
            check=False,
            timeout=15,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return
        time.sleep(3)
    raise RuntimeError("DEV SSH did not become ready")


def prepare(config, client):
    if not re.fullmatch(r"[1-9][0-9]*", config["DEV_VMID"]):
        raise ValueError("Invalid DEV VM ID")
    if config["DEV_VMID"] == config["PROD_VMID"]:
        raise ValueError("DEV and PROD must be different VMs")
    ipaddress.IPv4Address(config["DEV_IP"])
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", config["SSH_USER"]):
        raise ValueError("Invalid SSH user")
    base = "/nodes/{node}/qemu/" + config["DEV_VMID"]
    source = base + "/snapshot/clean-agent"
    before = client.request("GET", source + "/config")
    before.pop(
        "digest", None
    )  # Digest may cover the whole VM config, not just this snapshot.
    names = [row["name"] for row in client.request("GET", base + "/snapshot")]
    if "clean-dev" in names:
        raise RuntimeError("clean-dev already exists; refusing to replace it")
    if any(
        row.get("sid") == "vm:" + config["DEV_VMID"]
        for row in client.request("GET", "/cluster/ha/resources")
    ):
        raise RuntimeError("DEV is managed by HA")
    print(
        "Source snapshot configuration:",
        json.dumps(
            {
                key: before[key]
                for key in ("name", "snaptime", "description")
                if key in before
            },
            sort_keys=True,
        ),
        flush=True,
    )

    def task(path, form=None):
        print("Proxmox POST " + path + " " + json.dumps(form or {}), flush=True)
        client.task(path, form)

    if client.request("GET", base + "/status/current")["status"] != "stopped":
        task(base + "/status/stop")
    task(source + "/rollback")
    task(base + "/status/start")
    host = config["SSH_USER"] + "@" + config["DEV_IP"]
    wait_ssh(host)
    checks = """test "$(getenforce)" = Enforcing
sudo -n systemctl is-active firewalld
sudo -n systemctl is-enabled firewalld
"""
    ssh(
        host,
        checks
        + """sudo -n systemctl is-active fapolicyd
sudo -n systemctl is-enabled fapolicyd
sudo -n systemctl disable --now fapolicyd
"""
        + checks
        + """test "$(systemctl show fapolicyd -p ActiveState --value)" = inactive
test "$(systemctl show fapolicyd -p UnitFileState --value)" = disabled
echo 'PASS: only fapolicyd stopped/disabled; SELinux Enforcing, firewalld enabled/active'
""",
    )
    task(base + "/status/shutdown")
    task(
        base + "/snapshot",
        {
            "snapname": "clean-dev",
            "description": "Derived from clean-agent; only fapolicyd stopped and disabled. SELinux enforcing and firewalld unchanged.",
        },
    )
    after = client.request("GET", source + "/config")
    after.pop("digest", None)
    if before != after:
        raise RuntimeError("Source snapshot metadata changed unexpectedly")
    task(base + "/status/start")
    wait_ssh(host)
    ssh(
        host,
        checks
        + """test "$(systemctl show fapolicyd -p ActiveState --value)" = inactive
test "$(systemctl show fapolicyd -p UnitFileState --value)" = disabled
echo 'PASS: clean-dev booted with the required profile'
""",
    )
    print(
        "PASS: clean-dev created; clean-agent unchanged; PROD was not touched",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="~/.config/podman-offline-acceptance/lab.env"
    )
    parser.add_argument(
        "--create",
        action="store_true",
        required=True,
        help="Authorize destructive rollback of DEV to clean-agent",
    )
    args = parser.parse_args()
    print("Started:", datetime.datetime.now(datetime.UTC).isoformat(), flush=True)
    print("Config file:", shlex.quote(args.config), flush=True)
    config = env_file(args.config)
    prepare(config, Proxmox(config["PVE_ENV"]))


if __name__ == "__main__":
    main()
