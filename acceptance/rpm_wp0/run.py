#!/usr/bin/env python3
"""WP0 investigation controller: PROD only, private artifacts, first failure stops."""

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pve import Proxmox, env_file

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "wp0_harness", HERE.parent / "acceptance.py"
)
assert spec is not None and spec.loader is not None
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def key_inventory(home):
    """Read regular key files only; never connect to the original GnuPG agent."""
    return {
        str(path.relative_to(home)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in home.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


class Investigation(harness.Run):
    """Reuse logging and network isolation without Run.execute/readiness (both VMs)."""

    def __init__(self, run_id, config):
        super().__init__(run_id, config)
        self.cfg = env_file(config)
        harness.validate(self.cfg)
        if self.cfg["PROD_SNAPSHOT"] != "clean-agent":
            raise RuntimeError("PROD_SNAPSHOT must be clean-agent")
        self.pve = Proxmox(self.cfg["PVE_ENV"])
        self.endpoint = "/nodes/{node}/qemu/" + self.cfg["PROD_VMID"]
        vm = self.pve.request("GET", self.endpoint + "/config")
        if vm.get("name") != "todo-standby":
            raise RuntimeError("Only todo-standby is authorized")
        if any(
            row.get("sid") == "vm:" + self.cfg["PROD_VMID"]
            for row in self.pve.request("GET", "/cluster/ha/resources")
        ):
            raise RuntimeError("PROD is managed by HA")
        self.redactions += [self.pve.config["PVE_TOKEN_SECRET"]]
        # Do not log account/address connection strings from reused Run.command.
        self.redactions += [self.host("PROD")]
        self.revision = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
        self.meta.update(revision=self.revision, started=stamp(), order=["C/P1"])
        self.source_snapshot = self.snapshot_config()

    def snapshot_config(self):
        data = self.pve.request("GET", self.endpoint + "/snapshot/clean-agent/config")
        data.pop("digest", None)
        return data

    def root_file(self, name, timeout=600):
        # A pipe transports the probe source without registering it as file trust.
        # SSH runs this root shell directly; no product file is executed here.
        return self.command(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "ConnectTimeout=8",
                self.host("PROD"),
                "sudo -n bash -se",
            ],
            (HERE / name).read_text(),
            timeout=timeout,
        )

    def rollback(self, snapshot):
        if snapshot not in ("clean-agent", "clean-strict"):
            raise ValueError("Unauthorized snapshot")
        if (
            self.pve.request("GET", self.endpoint + "/status/current")["status"]
            != "stopped"
        ):
            self.pve.task(self.endpoint + "/status/stop")
        self.pve.task(self.endpoint + "/snapshot/" + snapshot + "/rollback")
        self.pve.task(self.endpoint + "/status/start")
        self.wait_ssh("PROD")
        self.prod_ready = True

    def policy(self, profile):
        evidence = self.root_file("policy.sh")
        (self.folder / ("policy-" + profile + ".txt")).write_text(evidence)
        expected = ("rpmdb,file", "none") if profile == "P1" else ("rpmdb", "sha256")
        for key, value in zip(("trust", "integrity"), expected):
            if not re.search(
                r"(?m)^" + key + r"\s*=\s*" + re.escape(value) + r"\s*$", evidence
            ):
                raise RuntimeError("Unexpected " + profile + " setting: " + key)

    def strict_snapshot(self):
        names = [
            row["name"] for row in self.pve.request("GET", self.endpoint + "/snapshot")
        ]
        if "clean-strict" in names:
            self.rollback("clean-strict")
            self.policy("P2")
            return
        self.rollback("clean-agent")
        self.policy("P1")
        self.root_file("strict.sh")
        self.policy("P2")
        self.pve.task(self.endpoint + "/status/shutdown")
        self.pve.task(
            self.endpoint + "/snapshot",
            {
                "snapname": "clean-strict",
                "description": "WP0 P2 from clean-agent: rpmdb only, sha256, rules 1/2/12 removed; no product files.",
            },
        )
        if self.snapshot_config() != self.source_snapshot:
            raise RuntimeError("clean-agent snapshot metadata changed")

    def transfer(self, fixtures):
        self.ssh("PROD", "mkdir -m 0700 /var/tmp/wp0-input")
        self.command(
            ["scp", "-q", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes"]
            + sorted(map(str, fixtures.iterdir()))
            + [self.host("PROD") + ":/var/tmp/wp0-input/"],
            timeout=600,
        )

    def audit(self):
        self.root_file("audit.sh")


def stamp():
    return datetime.datetime.now(datetime.UTC).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument(
        "--config", default="~/.config/podman-offline-acceptance/lab.env"
    )
    parser.add_argument(
        "--bundles",
        type=Path,
        default=Path.home()
        / "podman-offline-acceptance-runs/host65-20261024-144821-app1",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run):
        parser.error("Invalid run ID")
    os.umask(0o077)
    run = Investigation(args.run, args.config)
    key_home = Path.home() / ".podman-offline-rpm-gnupg"
    before = key_inventory(key_home)
    try:
        with tempfile.TemporaryDirectory(prefix="wp0-", dir="/tmp") as scratch:
            work = Path(scratch)
            run.step(
                "00-build",
                lambda: run.command(
                    ["bash", HERE / "build.sh", work, args.bundles], timeout=1200
                ),
            )
            run.step("01-strict-snapshot", run.strict_snapshot)
            run.step("02-reset-P1", lambda: run.rollback("clean-agent"))
            run.step("03-policy-P1", lambda: run.policy("P1"))
            run.step("04-isolate-P1", lambda: run.guest("PROD", "isolate"))
            run.step("05-transfer-P1", lambda: run.transfer(work / "fixtures"))
            run.step("C-P1", lambda: run.root_file("bootstrap.sh"))
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 - stop and preserve evidence
        print(str(error), file=sys.stderr)
    finally:
        if run.prod_ready:
            run.step("99-audit", run.audit)
        if before != key_inventory(key_home):
            raise RuntimeError("Original signing home changed")
        (run.folder / "metadata.json").write_text(json.dumps(run.meta, indent=2) + "\n")
        run.report()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
