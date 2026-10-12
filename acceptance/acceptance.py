#!/usr/bin/env python3
"""One immutable run, ordered steps, first failure stops. Controller: stdlib only."""

import argparse
import datetime
import hashlib
import ipaddress
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pve import Proxmox, env_file

ROOT = Path(__file__).resolve().parent.parent
RUNS = Path.home() / "podman-offline-acceptance-runs"
SSH = [
    "ssh",
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "ConnectTimeout=8",
]
SCP = [
    "scp",
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "ConnectTimeout=8",
]


def stamp():
    return datetime.datetime.now(datetime.UTC).isoformat()


def validate(config):
    for role in ("DEV", "PROD"):
        ipaddress.IPv4Address(config[role + "_IP"])
        if not re.fullmatch(r"[1-9][0-9]*", config[role + "_VMID"]):
            raise ValueError("Invalid VM ID")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", config[role + "_SNAPSHOT"]):
            raise ValueError("Invalid snapshot name")
    network = ipaddress.IPv4Network(config["LAB_CIDR"])
    if network.prefixlen < 24:
        raise ValueError("LAB_CIDR must be /24 or narrower")
    if any(
        ipaddress.IPv4Address(config[r + "_IP"]) not in network for r in ("DEV", "PROD")
    ):
        raise ValueError("Both VMs must belong to LAB_CIDR")
    if (
        config["DEV_VMID"] == config["PROD_VMID"]
        or config["DEV_IP"] == config["PROD_IP"]
    ):
        raise ValueError("Two distinct VMs required")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", config["SSH_USER"]):
        raise ValueError("Invalid SSH user")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", config["PROD_HOST"]):
        raise ValueError("Invalid application hostname")
    if not 1024 <= int(config["HTTPS_PORT"]) <= 65535:
        raise ValueError("HTTPS_PORT must be 1024..65535")


class Run:
    def __init__(self, run_id, config):
        self.id = run_id
        self.config_file = config
        self.folder = RUNS / run_id
        self.folder.mkdir(parents=True, mode=0o700, exist_ok=False)
        (self.folder / "logs").mkdir(mode=0o700)
        self.meta = {}
        self.log = None
        self.private = None
        self.dev_private = None
        self.redactions = []
        self.finished = False
        self.revision = ""
        self.cfg = {}
        self.started_epoch = str(int(time.time()))
        self.prod_ready = False

    def write(self, text):
        for value in self.redactions:
            text = text.replace(value, "[REDACTED]")
        if self.log:
            self.log.write(text)
            self.log.flush()

    def command(self, args, script=None, timeout=3600):
        self.write("$ " + " ".join(shlex.quote(str(a)) for a in args) + "\n")
        if script:
            self.write("# stdin script:\n" + script + "\n")
        try:
            result = subprocess.run(
                list(map(str, args)),
                check=False,
                input=script,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as error:
            output = error.stdout or b""
            self.write(
                output.decode(errors="replace") if isinstance(output, bytes) else output
            )
            raise RuntimeError("Command timed out") from None
        self.write(result.stdout + f"\nexit={result.returncode}\n")
        if result.returncode:
            raise RuntimeError(f"Command exited {result.returncode}")
        if re.search(r"(?m)^Error:|^FAIL:", result.stdout):
            raise RuntimeError("Command reported an error despite exit 0")
        return result.stdout

    def host(self, role):
        return self.cfg["SSH_USER"] + "@" + self.cfg[role + "_IP"]

    def ssh(self, role, script, timeout=3600):
        return self.command(SSH + [self.host(role), "bash -se"], script, timeout)

    def guest(self, role, action):
        args = [
            action,
            self.id,
            self.cfg["LAB_CIDR"],
            self.cfg["PROD_IP"],
            self.cfg["PROD_HOST"],
            self.cfg["HTTPS_PORT"],
            self.revision,
            role,
            self.started_epoch,
        ]
        script = (ROOT / "acceptance/remote.sh").read_text()
        prefix = "set -- " + " ".join(map(shlex.quote, args)) + "\n"
        return self.ssh(role, prefix + script)

    def step(self, name, action):
        print("START " + name, flush=True)
        started = stamp()
        clock = time.monotonic()
        result, exit_code = "PASS", 0
        error = None
        with (self.folder / "logs" / (name + ".log")).open("x") as log:
            self.log = log
            self.write(f"start={started}\nstep={name}\n")
            try:
                action()
            except (Exception, KeyboardInterrupt) as failure:  # noqa: BLE001 - record every failed step
                result, exit_code = "FAIL", 1
                error = failure
                self.write("FAIL: " + str(failure) + "\n")
            seconds = round(time.monotonic() - clock, 3)
            self.write(f"end={stamp()}\nexit={exit_code}\nseconds={seconds}\n")
            self.log = None
        record = {
            "step": name,
            "start": started,
            "seconds": seconds,
            "result": result,
            "exit": exit_code,
            "log": "logs/" + name + ".log",
        }
        with (self.folder / "record.jsonl").open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        print(f"{result} {name} ({seconds:.1f}s)", flush=True)
        if error is not None:
            raise RuntimeError("STOP at " + name) from None

    def readiness(self):
        self.cfg = env_file(self.config_file)
        validate(self.cfg)
        for program in ("git", "ssh", "scp"):
            if not shutil.which(program):
                raise RuntimeError("Missing controller tool: " + program)
        self.revision = self.command(["git", "-C", ROOT, "rev-parse", "HEAD"]).strip()
        clean = not self.command(["git", "-C", ROOT, "status", "--porcelain"]).strip()
        self.meta.update(
            revision=self.revision,
            clean=clean,
            version=(ROOT / "VERSION").read_text().strip(),
            dev=self.cfg["DEV_IP"],
            prod=self.cfg["PROD_IP"],
            start_epoch=self.started_epoch,
            dev_snapshot=self.cfg["DEV_SNAPSHOT"],
            prod_snapshot=self.cfg["PROD_SNAPSHOT"],
        )
        if not clean:
            raise RuntimeError(
                "Checkout is dirty; commit the test harness before running"
            )
        runtime = Path(os.environ["XDG_RUNTIME_DIR"])
        if (
            not runtime.is_dir()
            or runtime.stat().st_uid != os.getuid()
            or runtime.stat().st_mode & 0o077
        ):
            raise RuntimeError("XDG_RUNTIME_DIR must be an owned private directory")
        self.pve = Proxmox(self.cfg["PVE_ENV"])
        self.redactions.append(self.pve.config["PVE_TOKEN_SECRET"])
        managed = self.pve.request("GET", "/cluster/ha/resources")
        if any(
            row.get("sid")
            in ("vm:" + self.cfg["DEV_VMID"], "vm:" + self.cfg["PROD_VMID"])
            for row in managed
        ):
            raise RuntimeError("Lab VM is managed by Proxmox HA")
        for role in ("DEV", "PROD"):
            endpoint = "/nodes/{node}/qemu/" + self.cfg[role + "_VMID"]
            config = self.pve.request("GET", endpoint + "/config")
            if any(
                "link_down=1" in v for k, v in config.items() if k.startswith("net")
            ):
                raise RuntimeError("Proxmox NIC is disconnected: " + role)
            if self.pve.request("GET", endpoint + "/firewall/options").get("enable", 0):
                raise RuntimeError(
                    "VM Proxmox firewall enabled; prepare the lab baseline first"
                )
            names = [s["name"] for s in self.pve.request("GET", endpoint + "/snapshot")]
            if self.cfg[role + "_SNAPSHOT"] not in names:
                raise RuntimeError("Missing snapshot for " + role)
            self.write(
                "{}: VM {} snapshots={}\n".format(role, self.cfg[role + "_VMID"], names)
            )
            self.meta[role.lower() + "_readiness_profile"] = self.guest(
                role, "readiness"
            )
        self.private = Path(
            tempfile.mkdtemp(prefix="podman-offline-", dir=str(runtime))
        )

    def wait_ssh(self, role, old_boot=None):
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            args = SSH + [self.host(role), "cat /proc/sys/kernel/random/boot_id"]
            self.write("$ " + " ".join(map(shlex.quote, args)) + "\n")
            result = subprocess.run(
                args,
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.write(result.stdout + result.stderr + f"exit={result.returncode}\n")
            boot = result.stdout.strip()
            if result.returncode == 0 and boot and boot != old_boot:
                return boot
            time.sleep(3)
        raise RuntimeError("SSH/new boot did not become ready: " + role)

    def reset(self, role):
        endpoint = "/nodes/{node}/qemu/" + self.cfg[role + "_VMID"]
        status = self.pve.request("GET", endpoint + "/status/current")["status"]
        if status != "stopped":
            self.write("Proxmox POST " + endpoint + "/status/stop\n")
            self.pve.task(endpoint + "/status/stop")
        rollback = endpoint + "/snapshot/" + self.cfg[role + "_SNAPSHOT"] + "/rollback"
        self.write("Proxmox POST " + rollback + "\n")
        self.pve.task(rollback)
        self.write("Proxmox POST " + endpoint + "/status/start\n")
        self.pve.task(endpoint + "/status/start")
        self.meta[role.lower() + "_boot_before"] = self.wait_ssh(role)
        if role == "PROD":
            self.prod_ready = True
        self.meta[role.lower() + "_facts"] = self.guest(role, "clean")

    def source(self):
        source = self.folder / "source.bundle"
        self.command(["git", "-C", ROOT, "bundle", "create", source, "HEAD"])
        base = "podman-offline-acceptance/" + self.id
        self.ssh("DEV", "mkdir -p " + shlex.quote(base))
        self.command(SCP + [source, self.host("DEV") + ":" + base + "/source.bundle"])
        self.guest("DEV", "clone")

    def transfer(self):
        base = "podman-offline-acceptance/" + self.id
        archive = "myproduct-" + self.meta["version"] + "-offline.tar.gz"
        self.ssh("PROD", "mkdir -p " + shlex.quote(base))
        for suffix in ("", ".sha256"):
            local = self.folder / (archive + suffix)
            self.command(
                SCP
                + [
                    self.host("DEV") + ":" + base + "/src/dist/" + archive + suffix,
                    local,
                ]
            )
            self.command(
                SCP + [local, self.host("PROD") + ":" + base + "/" + archive + suffix]
            )
        with (self.folder / archive).open("rb") as stream:
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        self.meta["bundle_sha256"] = digest.hexdigest()
        self.write("bundle_sha256=" + digest.hexdigest() + "\n")
        self.guest("PROD", "unpack")

    def credentials(self):
        assert self.private is not None
        output = self.ssh("DEV", 'printf "%s" "${XDG_RUNTIME_DIR:?}"')
        runtime = output.splitlines()[-1]
        if not re.fullmatch(r"/run/user/[0-9]+", runtime):
            raise RuntimeError("Unexpected VM runtime path")
        self.dev_private = runtime + "/podman-offline-" + self.id
        self.ssh("DEV", "mkdir -m 700 " + shlex.quote(self.dev_private))
        base = "/var/lib/myproduct/releases/myproduct-" + self.meta["version"] + "/"
        files = {
            "ca.crt": "PKI/private/ca.crt",
            "alice-password": "generated-certificates/users/alice-password",
            "bob-password": "generated-certificates/users/bob-password",
        }
        for name, relative in files.items():
            local = self.private / name
            # Secret bytes go straight to a private file, never through command logs.
            args = SSH + [
                self.host("PROD"),
                "sudo -n -H -u myproduct cat " + shlex.quote(base + relative),
            ]
            self.write("$ " + shlex.join(args) + " > [private runtime file]\n")
            with local.open("xb") as stream:
                result = subprocess.run(
                    args, check=False, stdout=stream, stderr=subprocess.PIPE, timeout=30
                )
            self.write(f"secret transfer exit={result.returncode}\n")
            if result.returncode:
                raise RuntimeError("Unable to read product credentials")
            local.chmod(0o600)
            if name.endswith("-password"):
                self.redactions.append(local.read_text().strip())
            self.command(
                SCP + [local, self.host("DEV") + ":" + self.dev_private + "/" + name]
            )

    def cleanup(self):
        try:
            if self.dev_private:
                self.guest("DEV", "cleanup")
        finally:
            if self.private:
                shutil.rmtree(str(self.private))
                self.write("Controller runtime secrets removed\n")

    def finalize(self):
        # Read-only audit evidence is required even after a failed prod step.
        if self.prod_ready:
            try:
                self.step("10-prod-audit", lambda: self.guest("PROD", "audit"))
            except Exception as error:  # noqa: BLE001 - preserve original failure and still clean up
                print(str(error), file=sys.stderr)
        try:
            self.step("10-cleanup", self.cleanup)
        except Exception as error:  # noqa: BLE001 - cleanup failure must affect verdict
            print(str(error), file=sys.stderr)

    def reboot(self):
        old = self.guest("PROD", "boot").splitlines()[-1]
        self.meta["prod_boot_before_reboot"] = old
        self.guest("PROD", "reboot")
        self.meta["prod_boot_after_reboot"] = self.wait_ssh("PROD", old)

    def execute(self):
        self.step("00-readiness", self.readiness)
        for role in ("DEV", "PROD"):
            self.step("01-reset-" + role.lower(), lambda r=role: self.reset(r))
        self.step("02-isolate-prod", lambda: self.guest("PROD", "isolate"))
        self.step("03-source", self.source)
        actions = [
            "unit",
            "build-images",
            "dev-up",
            "venv",
            "dev-e2e",
            "examples-setup",
        ]
        actions += [
            "example-" + name
            for name in (
                "basic",
                "secrets",
                "volumes",
                "init-containers",
                "manifest-defined",
                "failures",
            )
        ]
        actions += ["dev-down"]
        for action in actions:
            self.step("03-" + action, lambda a=action: self.guest("DEV", a))
        self.step("04-bundle", lambda: self.guest("DEV", "bundle"))
        self.step("05-transfer", self.transfer)
        self.step("06-install", lambda: self.guest("PROD", "install"))
        self.step("07-check", lambda: self.guest("PROD", "check"))
        self.step("08-credentials", self.credentials)
        self.step("08-e2e", lambda: self.guest("DEV", "prod-e2e"))
        self.step("08-markers", lambda: self.guest("DEV", "markers-create"))
        self.step("09-stop", lambda: self.guest("PROD", "stop"))
        for action in ("start", "restart", "kill"):
            self.step("09-" + action, lambda a=action: self.guest("PROD", a))
            self.step(
                "09-markers-" + action, lambda: self.guest("DEV", "markers-check")
            )
        self.step("09-reboot", self.reboot)
        self.step("09-offline-after-reboot", lambda: self.guest("PROD", "offline"))
        self.step("09-check-after-reboot", lambda: self.guest("PROD", "check"))
        self.step("09-e2e-after-reboot", lambda: self.guest("DEV", "prod-e2e"))
        self.step("09-markers-after-reboot", lambda: self.guest("DEV", "markers-check"))
        self.finished = True

    def report(self):
        records = [
            json.loads(line)
            for line in (self.folder / "record.jsonl").read_text().splitlines()
        ]
        verdict = (
            "CLEAN PASS"
            if self.finished and all(r["result"] == "PASS" for r in records)
            else "NOT CLEAN"
        )
        fence = chr(96) * 3
        lines = [
            "# Acceptance " + self.id,
            "",
            "**" + verdict + "**",
            "",
            "Metadata recorded by the runner:",
            fence + "json",
            json.dumps(self.meta, indent=2),
            fence,
            "",
            "| Step | Result | Seconds | Log |",
            "| --- | --- | ---: | --- |",
        ]
        for record in records:
            lines.append(
                "| {step} | {result} | {seconds} | [{log}]({log}) |".format(**record)
            )
        lines += [
            "",
            "A failed step stops execution. Later steps were NOT TESTED.",
            "Only read-only prod audit collection and secret cleanup may run after failure. No retries or repairs.",
            "",
        ]
        report = "\n".join(lines)
        (self.folder / "REPORT.md").write_text(report)
        evidence = [report, "\n# Evidence excerpts (full output in linked logs)\n"]
        for record in records:
            path = self.folder / record["log"]
            data = path.read_bytes()
            evidence += [
                "\n## " + record["step"],
                "Log SHA256: " + hashlib.sha256(data).hexdigest(),
                fence + "text",
                data.decode()
                if record["step"] == "10-prod-audit"
                else "\n".join(data.decode().splitlines()[-65:]),
                fence,
            ]
        (self.folder / "EVIDENCE.md").write_text("\n".join(evidence) + "\n")
        print(verdict + ": " + str(self.folder / "EVIDENCE.md"), flush=True)
        return verdict == "CLEAN PASS"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument(
        "--config", default="~/.config/podman-offline-acceptance/lab.env"
    )
    parser.add_argument("action", choices=["run"])
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run):
        parser.error("Invalid run ID")
    os.umask(0o077)
    run = Run(args.run, args.config)
    try:
        run.execute()
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 - always produce evidence
        print(str(error), file=sys.stderr)
    finally:
        run.finalize()
    return 0 if run.report() else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        raise SystemExit(1)
