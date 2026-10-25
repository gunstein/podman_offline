#!/usr/bin/env python3
"""Complete fail-stop WP0 controller. Import and --list never access the lab."""

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import contracts as contract
from contracts import (
    ACCOUNT,
    APPROVED_FINGERPRINT,
    LOCK_TIMEOUT,
    POSITIVE,
    TRUST_TIMEOUT,
    require,
)
from pve import Proxmox, env_file

spec = importlib.util.spec_from_file_location(
    "wp0_existing_harness", HERE.parent / "acceptance.py"
)
assert spec and spec.loader
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)
import host_setup

SSH = [
    "ssh",
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "ConnectTimeout=8",
]
SCP = ["scp", "-q", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes"]


class ProdAPI:
    """Only VM-scoped reads, tracked task reads and the four authorized mutations."""

    def __init__(self, client, vmid):
        require(bool(re.fullmatch(r"[1-9][0-9]*", vmid)), "Invalid PROD VMID")
        self.client = client
        self.base = "/nodes/{node}/qemu/" + vmid
        self.vmid = vmid
        self.tasks = set()
        self.snapshots = {"clean-agent"}

    def request(self, method, path) -> Any:
        suffix = path.removeprefix(self.base)
        reads = {"/config", "/status/current", "/snapshot"}
        reads |= {"/snapshot/" + name + "/config" for name in self.snapshots}
        task_read = method == "GET" and path in self.tasks
        normal_read = (
            method == "GET" and path.startswith(self.base + "/") and suffix in reads
        )
        mutation = (
            method == "POST"
            and path.startswith(self.base + "/")
            and suffix
            in {
                "/status/stop",
                "/status/shutdown",
                "/status/start",
                "/snapshot/clean-agent/rollback",
            }
        )
        require(
            task_read or normal_read or mutation,
            "Proxmox operation outside the PROD allowlist",
        )
        result = self.client.request(method, path)
        if method == "GET" and suffix == "/snapshot":
            names = {row["name"] for row in result if row["name"] != "current"}
            require(
                all(re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in names),
                "Invalid snapshot name",
            )
            self.snapshots = names
        if mutation:
            require(
                isinstance(result, str)
                and result.startswith("UPID:")
                and result.split(":")[6] == self.vmid,
                "Task does not belong to PROD",
            )
            endpoint = (
                "/nodes/{node}/tasks/" + urllib.parse.quote(result, safe="") + "/status"
            )
            self.tasks.add(endpoint)
        return result

    def task(self, suffix):
        task = self.request("POST", self.base + suffix)
        endpoint = (
            "/nodes/{node}/tasks/" + urllib.parse.quote(task, safe="") + "/status"
        )
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            status = self.request("GET", endpoint)
            if status["status"] == "stopped":
                require(
                    status.get("exitstatus") == "OK",
                    "Proxmox task failed: " + str(status.get("exitstatus", "unknown")),
                )
                return True
            time.sleep(2)
        raise RuntimeError("Proxmox task timed out")

    def preflight(self):
        config = self.request("GET", self.base + "/config")
        status = self.request("GET", self.base + "/status/current")
        snapshots = self.request("GET", self.base + "/snapshot")
        configurations = {
            row["name"]: self.request(
                "GET", self.base + "/snapshot/" + row["name"] + "/config"
            )
            for row in snapshots
            if row["name"] != "current"
        }
        return contract.snapshot_preflight(config, status, snapshots, configurations)


def key_inventory(home):
    return {
        str(path.relative_to(home)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in home.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


class Evidence:
    """PASS requires an explicit True predicate; reports survive failures and partial setup."""

    def __init__(self, folder, cases):
        self.folder = folder
        folder.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.records = []
        self.meta = {
            "cases": cases,
            "complete_matrix_selected": cases == contract.matrix(),
            "trust_timeout_seconds": TRUST_TIMEOUT,
            "lock_timeout_seconds": LOCK_TIMEOUT,
            "automation_adaptations": [
                "dnf -y",
                "SSH input directory replaces mounted medium",
                "scripted paper output checks",
            ],
            "evidence_class": "real lab only when --execute is explicitly authorized",
        }
        self.success = False
        self.current = ""
        self.redactions = []

    def scrub(self, text):
        for value in self.redactions:
            text = text.replace(value, "[REDACTED]")
        return text

    def save(self):
        (self.folder / "metadata.json").write_text(
            self.scrub(json.dumps(self.meta, indent=2)) + "\n"
        )
        (self.folder / "record.jsonl").write_text(
            self.scrub("".join(json.dumps(row) + "\n" for row in self.records))
        )
        passed = (
            self.success
            and bool(self.records)
            and all(row["result"] == "PASS" for row in self.records)
        )
        required_steps = {
            "controller-source",
            "controller-config",
            "snapshot-preflight",
            "build-fixtures",
        }
        required_steps |= {
            group + "-" + profile + "-" + step
            for group, profile in self.meta["cases"]
            for step in (
                "rollback",
                "baseline",
                "profile",
                "isolation",
                "transfer",
                "probe",
                "audit",
            )
        }
        recorded_steps = [row["step"] for row in self.records]
        passed = (
            passed
            and required_steps <= set(recorded_steps)
            and len(recorded_steps) == len(set(recorded_steps))
        )
        passed = passed and self.meta.get("original_signing_home_unchanged") is True
        (self.folder / "REPORT.md").write_text(
            "# WP0 investigation\n\n"
            + (
                (
                    "WP0 MATRIX PASS"
                    if self.meta["complete_matrix_selected"]
                    else "SELECTED CASES PASS"
                )
                if passed
                else "NOT CLEAN"
            )
            + "\n\n"
            + "| Step | Result | Reason |\n| --- | --- | --- |\n"
            + "".join(
                "| {step} | {result} | {reason} |\n".format(**row)
                for row in self.records
            )
            + "\nOnly selected, completed case groups are covered. Unreached cases are NOT TESTED.\n"
        )
        return passed

    def step(self, name, action):
        print("START " + name, flush=True)
        self.current = name
        row = {
            "step": name,
            "result": "FAIL",
            "reason": "",
            "started": datetime.datetime.now(datetime.UTC).isoformat(),
        }
        try:
            require(action() is True, "Step returned without its predicate")
            row["result"] = "PASS"
        except BaseException as error:
            row["reason"] = self.scrub(type(error).__name__ + ": " + str(error))
            raise
        finally:
            self.records.append(row)
            self.save()
            print(row["result"] + " " + name, flush=True)

    def json(self, name, value):
        (self.folder / (name + ".json")).write_text(
            self.scrub(json.dumps(value, indent=2)) + "\n"
        )


def expected_predicates(group):
    if group in ("C1", "D"):
        return {
            "signature-" + name
            for name in (
                "product",
                "unsigned",
                "foreign",
                "tampered-header",
                "tampered-payload",
                "product-subkey",
                "foreign-subkey",
            )
        } | ({"repository-download"} if group == "D" else set())
    if group == "C2":
        return {
            "stop-two-primary.asc",
            "stop-foreign.asc",
            "leftover-setup",
            "leftover-replaced",
        }
    if group == "R5":
        return {"diagnosis", "newer-stop", "unchanged"}
    if group.startswith("R"):
        return {
            "diagnosis",
            "repair-version",
            "repair-integrity",
            "repair-trust",
            "repair-execution",
        } | ({"duplicate-cleanup", "release-retained"} if group == "R3" else set())
    return {
        "A": {"prototype-trust"},
        "B": {"prototype-trust", "root-stdin", "account-python"},
        "E": {"trust-visible", "first-execution"},
        "F": {
            "plain-dnf-release",
            "plain-rpm-release",
            "plain-dnf-tools",
            "record-package",
            "record-boot",
            "record-dead",
            "record-reused",
            "not-ancestor",
            "manager-running",
            "manager-independent",
            "authorized-one",
        },
        "G": {
            "bounded-runtime",
            "inherited-accepted",
            "forged-refused",
            "check-exit-lock-held",
            "admin-exit-lock-held",
            "preun-and-dnf-complete",
            "lock-released",
        },
        "H": {
            "bypass-upgrade",
            "mismatch-admin",
            "mismatch-runtime",
            "missing-admin",
            "missing-runtime",
        },
    }[group]


def check_probe(group, value):
    require(value.get("ok") is True, "Missing probe completion predicate")
    require(
        set(value.get("predicates", [])) == expected_predicates(group),
        "Probe did not establish every required predicate",
    )
    require(
        len(value["predicates"]) == len(set(value["predicates"])),
        "Duplicate probe predicate",
    )
    if group == "C2":
        require(
            len(value.get("observations", [])) == 1
            and value["observations"][0]["kind"] == "two-primary-rpm-import-NOT-A-GATE",
            "Missing separate import observation",
        )
    return True


def recorded_policy():
    text = (HERE / "results/policy-P1.txt").read_text()
    rules = text.split("=== Effective rules ===\n", 1)[1].split(
        "=== fapolicyd.conf ===\n", 1
    )[0]
    return {
        "rules": rules,
        "plugin_package": next(
            line
            for line in text.splitlines()
            if line.startswith("rpm-plugin-fapolicyd-")
        ),
        "languages": [line for line in rules.splitlines() if line.startswith("-> ")],
        "config": text.split("=== fapolicyd.conf ===\n", 1)[1].split(
            "=== RPM filters ===\n", 1
        )[0],
        "filter": text.split("=== RPM filters ===\n", 1)[1]
        .split("=== RPM plugin configuration ===\n", 1)[0]
        .rstrip(),
        "plugin": text.split("=== RPM plugin configuration ===\n", 1)[1].strip(),
    }


class Investigation:
    def __init__(self, evidence):
        self.evidence = evidence
        self.prod_ready = False
        self.cfg = {}
        self.redactions = evidence.redactions
        self.counter = 0
        self.audit_start = None
        self.case = ""

    def execute_command(self, args, script=None, timeout=1200):
        self.counter += 1
        evidence = {"argv": list(map(str, args)), "exit": None}
        try:
            result = subprocess.run(
                list(map(str, args)),
                input=script,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
            evidence.update(
                exit=result.returncode, stdout=result.stdout, stderr=result.stderr
            )
        except subprocess.TimeoutExpired as error:

            def text(value):
                return (
                    value.decode(errors="replace")
                    if isinstance(value, bytes)
                    else (value or "")
                )

            evidence.update(
                timed_out=True, stdout=text(error.stdout), stderr=text(error.stderr)
            )
            raise RuntimeError(
                "Controller command timed out; see command evidence"
            ) from None
        except OSError as error:
            evidence.update(error=type(error).__name__)
            raise RuntimeError("Controller command could not start") from None
        finally:
            self.evidence.json(f"command-{self.counter:04d}", evidence)
        require(result.returncode == 0, "Command failed; see command evidence")
        return result.stdout

    def connect(self, config):
        self.cfg = env_file(config)
        harness.validate(self.cfg)
        require(
            self.cfg["PROD_SNAPSHOT"] == "clean-agent",
            "Only clean-agent rollback is allowed",
        )
        client = Proxmox(self.cfg["PVE_ENV"])
        self.api = ProdAPI(client, self.cfg["PROD_VMID"])
        self.host = self.cfg["SSH_USER"] + "@" + self.cfg["PROD_IP"]
        self.redactions += [self.host, client.config["PVE_TOKEN_SECRET"]]
        return True

    def remote(self, action, arguments=None):
        # Every expected value, including the pinned fingerprint, travels in the
        # independently supplied SSH program, never in the candidate directory.
        source = 'import sys, types, json, os\nos.environ["LC_ALL"] = "C"\n'
        for name in ("contracts", "operations", "mechanisms", "guest"):
            source += f"m = types.ModuleType({name!r}); sys.modules[{name!r}] = m\n"
            source += (
                "exec(compile("
                + repr((HERE / (name + ".py")).read_text())
                + ", "
                + repr(name)
                + ', "exec"), m.__dict__)\n'
            )
        source += (
            "print(json.dumps(m.entry("
            + repr(action)
            + ", "
            + repr(arguments or {})
            + ")))\n"
        )
        output = self.execute_command(
            SSH + [self.host, "sudo -n python3 -I -B -"], source
        )
        data = json.loads(output)
        self.evidence.json(self.case + "-" + action + "-" + str(self.counter), data)
        require(data["success"] is True, data.get("error", "Guest action failed"))
        return data["value"]

    def reset(self):
        self.audit_start = None
        self.api.preflight()
        self.prod_ready = False
        self.audit_start = None
        status = self.api.request("GET", self.api.base + "/status/current")
        if status["status"] != "stopped":
            self.api.task("/status/stop")
        self.api.task("/snapshot/clean-agent/rollback")
        self.api.task("/status/start")
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            result = subprocess.run(
                SSH + [self.host, "true"], capture_output=True, check=False, timeout=15
            )
            if result.returncode == 0:
                self.prod_ready = True
                return True
            time.sleep(2)
        raise RuntimeError("PROD SSH did not become ready")

    def baseline(self):
        facts = self.remote("baseline")
        self.evidence.json(self.case + "-baseline", facts)
        contract.check_baseline(facts)
        contract.check_profile(facts["policy"], recorded_policy(), "P1")
        self.baseline_policy = facts["policy"]
        return True

    def profile(self, selected):
        observed = self.remote("p2" if selected == "P2" else "profile")
        self.evidence.json(self.case + "-policy", observed)
        return contract.check_profile(observed, self.baseline_policy, selected)

    def isolate(self):
        # Reuse only the existing harness's isolate action, never its VM runner.
        args = [
            "isolate",
            "wp0",
            self.cfg["LAB_CIDR"],
            self.cfg["PROD_IP"],
            self.cfg["PROD_HOST"],
            self.cfg["HTTPS_PORT"],
            "WP0",
            "PROD",
            str(int(time.time())),
            "",
            "",
            "platform",
            "myproduct",
        ]
        source = (
            "set -- "
            + " ".join(map(shlex.quote, args))
            + "\n"
            + (HERE.parent / "remote.sh").read_text()
        )
        output = self.execute_command(SSH + [self.host, "bash -se"], source)
        require(
            all(
                token in output
                for token in (
                    "PASS: registry blocked",
                    "PASS: public DNS lookup failed",
                    "PASS: public pull failed",
                )
            ),
            "Missing isolation predicates",
        )
        return True

    def transfer(self, fixtures):
        # Check independently before copying anything. No product-fingerprint
        # file is generated, accepted or sent with this directory.
        require(
            not (fixtures / "product-fingerprint").exists(),
            "Expected fingerprint must not be a delivery file",
        )
        with tempfile.TemporaryDirectory(prefix="wp0-public-key-") as home:
            for name in ("RPM-GPG-KEY-myproduct", "product-subkey.asc"):
                output = self.execute_command(
                    [
                        "gpg",
                        "--homedir",
                        home,
                        "--batch",
                        "--with-colons",
                        "--show-keys",
                        fixtures / name,
                    ]
                )
                contract.authorize_key(output, APPROVED_FINGERPRINT)
        self.execute_command(SSH + [self.host, "install -d -m 0700 /var/tmp/wp0-input"])
        self.execute_command(
            SCP + ["-r", str(fixtures) + "/."] + [self.host + ":/var/tmp/wp0-input/"]
        )
        return True

    def account(self, private):
        key = private / "operator-key"
        self.execute_command(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key])
        provisioned = self.remote(
            "provision", {"public": key.with_suffix(".pub").read_text().strip()}
        )
        require(provisioned.get("ok") is True, "Missing account provisioning predicate")
        self.operator = SSH + [
            "-o",
            "IdentitiesOnly=yes",
            "-i",
            str(key),
            ACCOUNT + "@" + self.cfg["PROD_IP"],
        ]
        self.redactions.append(ACCOUNT + "@" + self.cfg["PROD_IP"])
        return True

    def runtime(self, source):
        return self.execute_command(self.operator + ["bash -se"], source)

    def prototype(self, credentials):
        result = self.remote("install-prototype", {"port": self.cfg["HTTPS_PORT"]})
        check_probe("A", result)
        values = {
            "product": "myproduct",
            "runtime": ACCOUNT,
            "gateway": "platform",
            "gateway_version": "0.4.12",
            "login_component": "identity",
            "login_version": "0.4.12",
            "port": self.cfg["HTTPS_PORT"],
            "public_origin": "https://"
            + self.cfg["PROD_HOST"]
            + ":"
            + self.cfg["HTTPS_PORT"],
            "bind_ip": self.cfg["PROD_IP"],
            "credentials": "/var/tmp/wp0-credentials",
            "credential_format": "pem",
            "discovery_path": "/identity/.well-known/openid-configuration",
        }
        self.runtime(
            'test "$(id -un)" = '
            + ACCOUNT
            + '\ntest "$XDG_RUNTIME_DIR" = /run/user/$(id -u)\nsystemctl --user is-system-running\n'
        )
        for step in ("init-layout", "gateway-config"):
            self.runtime(host_setup.script(step, values))
        names = {
            "web.crt": "platform/credentials/web/web.crt",
            "web.key": "platform/credentials/web/web.key",
            "ca.crt": "PKI/private/ca.crt",
            "identity.crt": "identity/credentials/identity/identity.crt",
            "identity.key": "identity/credentials/identity/identity.key",
            "alice-password": "identity/credentials/users/alice-password",
            "bob-password": "identity/credentials/users/bob-password",
        }
        for name, relative in names.items():
            self.execute_command(
                SCP
                + [
                    "-o",
                    "IdentitiesOnly=yes",
                    "-i",
                    self.operator[self.operator.index("-i") + 1],
                    credentials / relative,
                    ACCOUNT
                    + "@"
                    + self.cfg["PROD_IP"]
                    + ":"
                    + values["credentials"]
                    + "/"
                    + name,
                ]
            )
        for step in (
            "gateway-credentials",
            "gateway-install",
            "gateway-check",
            "identity-config",
            "identity-install",
            "identity-check",
        ):
            output = self.runtime(host_setup.script(step, values))
            expected = {"gateway-check": "204", "identity-check": "200"}.get(step)
            if expected:
                require(output.strip() == expected, "Prototype HTTPS check failed")
        # Require actual healthy containers and complete installed status; never
        # infer health just from an active systemd service or a successful CLI exit.
        code = (
            "python3 -B - <<'HEALTH'\n"
            + (HERE / "contracts.py").read_text()
            + """
import json, subprocess
status = subprocess.run(['bash','/var/lib/myproduct/releases/myproduct-platform-0.4.12/deploy.sh','status','--json'], capture_output=True, text=True, check=True)
data = json.loads(status.stdout)
for unit in ('myproduct-platform','myproduct-identity'):
    subprocess.run(['systemctl','--user','is-active',unit], check=True, stdout=subprocess.DEVNULL)
result = subprocess.run(['podman','ps','--all','--format','json'], capture_output=True, text=True, check=True)
details = []
for container in json.loads(result.stdout):
    details.append(json.loads(subprocess.run(['podman','inspect',container['Id']], capture_output=True,text=True,check=True).stdout)[0])
runtime_health(data, details)
print(json.dumps({'status': data, 'containers': [{'name': row['Name'], 'state': row['State']['Status'], 'health': row['State']['Health']['Status']} for row in details if not row['IsInfra'] and not row['IsService']]}))
print('WP0 three containers healthy and installed status complete')
HEALTH
"""
        )
        output = self.runtime(code)
        require(
            "WP0 three containers healthy and installed status complete" in output,
            "Missing final runtime health predicate",
        )
        return True

    def probe(self, group, private, credentials):
        self.account(private)
        self.audit_start = self.execute_command(
            SSH + [self.host, contract.AUDIT_START_COMMAND]
        ).strip()
        if group == "A":
            return self.prototype(credentials)
        if group in ("F", "G", "H"):
            require(
                self.runtime(
                    'test "$(id -un)" = ' + ACCOUNT + '\nprintf "WP0 runtime SSH\\n"\n'
                ).strip()
                == "WP0 runtime SSH",
                "Runtime SSH login predicate failed",
            )
        result = self.remote(group, {"port": self.cfg["HTTPS_PORT"]})
        if group == "E":
            require(
                result.get("ok") is True
                and result.get("predicates") == ["trust-visible"],
                "Missing pre-execution trust predicate",
            )
            require(
                self.runtime("wp0-selfcheck\n").strip() == "WP0 trusted module",
                "First runtime execution failed",
            )
            result["predicates"].append("first-execution")
            self.evidence.json(self.case + "-execution-verdict", result)
        return check_probe(group, result)

    def collect_audit(self, group):
        require(
            self.prod_ready and self.audit_start is not None,
            "Probe audit start unavailable",
        )
        result = self.remote("audit", {"start": self.audit_start})
        self.evidence.json(self.case + "-audit", result)
        # None of these probes intentionally execute an untrusted release or
        # relax fapolicyd. Scriptlet/CLI refusals are expected errors, not an
        # authorization to accept arbitrary policy denials in negative runs.
        require(
            result["no_events"] is True, "Unexpected FANOTIFY/AVC event in " + group
        )
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run")
    parser.add_argument("--case", choices=("all", *contract.GROUPS), default="all")
    parser.add_argument("--profile", choices=("all", "P1", "P2"), default="all")
    parser.add_argument("--list", action="store_true")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Explicit authorization for a separately reviewed lab run",
    )
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
    cases = contract.matrix(args.case, args.profile)
    if args.list:
        for group, profile in cases:
            print(group, profile, "positive" if group in POSITIVE else "negative")
        return 0
    if (
        not args.execute
        or not args.run
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run)
    ):
        parser.error("A reviewed lab run requires --execute and a fresh valid --run ID")
    os.umask(0o077)
    evidence = Evidence(
        Path.home() / "podman-offline-acceptance-runs" / args.run, cases
    )
    run = Investigation(evidence)
    before = None
    key_home = Path.home() / ".podman-offline-rpm-gnupg"
    try:
        evidence.meta["revision"] = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()

        def source_state():
            clean = subprocess.check_output(
                ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
            ).strip()
            branch = subprocess.check_output(
                ["git", "-C", str(ROOT), "branch", "--show-current"], text=True
            ).strip()
            require(
                not clean and branch == "feature/69-wp0",
                "Use a clean committed feature/69-wp0 checkout",
            )
            return True

        evidence.step("controller-source", source_state)
        evidence.step("controller-config", lambda: run.connect(args.config))
        evidence.step("snapshot-preflight", run.api.preflight)
        with tempfile.TemporaryDirectory(prefix="wp0-", dir="/tmp") as temporary:
            scratch = Path(temporary)
            before = key_inventory(key_home)

            def build():
                run.execute_command(["bash", HERE / "build.sh", scratch, args.bundles])
                require(
                    (
                        scratch / "fixtures" / "myproduct-tools-2.0-1.noarch.rpm"
                    ).is_file(),
                    "Missing delivered tools fixture",
                )
                return True

            evidence.step("build-fixtures", build)
            credentials = scratch / "credentials"
            for component in ("platform", "identity"):
                run.execute_command(
                    [
                        "bash",
                        ROOT / "dev/generate-certificates.sh",
                        "--root",
                        credentials,
                        component,
                        run.cfg["PROD_HOST"],
                    ]
                )
            for path in credentials.glob("identity/credentials/users/*-password"):
                run.redactions.append(path.read_text().strip())
            for group, profile in cases:
                run.case = group + "-" + profile
                evidence.meta["current_case"] = run.case
                private = scratch / run.case
                private.mkdir(mode=0o700)
                for label, action in (
                    ("rollback", run.reset),
                    ("baseline", run.baseline),
                    ("profile", lambda p=profile: run.profile(p)),
                    ("isolation", run.isolate),
                    ("transfer", lambda: run.transfer(scratch / "fixtures")),
                    ("probe", lambda g=group, p=private: run.probe(g, p, credentials)),
                ):
                    evidence.step(run.case + "-" + label, action)
                evidence.step(run.case + "-audit", lambda g=group: run.collect_audit(g))
            evidence.success = True
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 - evidence must survive every failed action
        reason = type(error).__name__ + ": " + str(error)
        for private_value in run.redactions:
            reason = reason.replace(private_value, "[REDACTED]")
        evidence.meta["stop"] = reason
        if run.prod_ready and run.audit_start:
            try:
                evidence.step(
                    run.case + "-failure-audit",
                    lambda: run.collect_audit("failed probe"),
                )
            except Exception as audit_error:  # noqa: BLE001 - retain the original failure
                evidence.meta["audit_failure"] = type(audit_error).__name__
    finally:
        if before is not None:
            try:
                unchanged = before == key_inventory(key_home)
                evidence.meta["original_signing_home_unchanged"] = unchanged
                if not unchanged:
                    evidence.success = False
            except OSError as error:
                evidence.success = False
                evidence.meta["signing_home_verification_error"] = type(error).__name__
        passed = evidence.save()
        print(
            (
                (
                    "WP0 MATRIX PASS: "
                    if evidence.meta["complete_matrix_selected"]
                    else "SELECTED CASES PASS: "
                )
                if passed
                else "NOT CLEAN: "
            )
            + str(evidence.folder / "REPORT.md")
        )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
