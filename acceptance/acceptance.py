#!/usr/bin/env python3
"""One immutable run, ordered steps, first failure stops. Controller: stdlib only."""

import argparse
import datetime
import gzip
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

import host_setup as operator_flow
from pve import Proxmox, env_file

ROOT = Path(__file__).resolve().parent.parent
RUNS = Path.home() / "podman-offline-acceptance-runs"
# Identity's persistent config, changed only by the explicit template addition.
IDENTITY_CONFIG_CHANGE = ("identity/config.yaml",)
# product: in bundles.yaml; acceptance/renamed_product.py declares RENAMED_PRODUCT.
DEMO_PRODUCT = "myproduct"
RENAMED_PRODUCT = "shop"


def bundle_versions(listing, product=DEMO_PRODUCT):
    """Map each component to its built version, in the order bundle.py listed them.

    Each line of dist/current-bundles.txt is <product>-<id>-<version>-offline.tar.gz.
    """
    archive = re.compile(
        re.escape(product)
        + r"-([a-z0-9]+(?:-[a-z0-9]+)*)-([0-9]+\.[0-9]+\.[0-9]+)-offline\.tar\.gz"
    )
    versions = {}
    for line in listing.splitlines():
        match = archive.fullmatch(line.strip())
        if match:
            versions[match.group(1)] = match.group(2)
    if not versions:
        raise RuntimeError("No bundles listed in dist/current-bundles.txt")
    return versions


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
    """Return the current UTC time in ISO format for the logs."""
    return datetime.datetime.now(datetime.UTC).isoformat()


def validate(config):
    """Validate the lab VMs, addresses, subnet, names and HTTPS port."""
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
    """Perform one immutable acceptance run with logs and stop at the first failure."""

    def __init__(self, run_id, config, first_app="app1"):
        """Create a new, private run folder and initialize the run state."""
        self.id = run_id
        self.first_app = first_app
        self.help_only = False
        self.identity_only = False
        self.platform_help_only = False
        self.renamed_product = False
        self.status_retry = False
        self.host_setup = False
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
        self.persistent_before = None
        self.warnings = set()

    def write(self, text):
        """Write to the step log after masking known secrets."""
        for value in self.redactions:
            text = text.replace(value, "[REDACTED]")
        if self.log:
            self.log.write(text)
            self.log.flush()

    def log_streams(self, stdout, stderr, log_stdout=True):
        """Log separate streams and name warnings without showing private hash values."""
        stdout, stderr = stdout or "", stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        for line in stderr.splitlines():
            if re.match(r"^(?:\*\* )?WARNING|^Warning:", line):
                for value in self.redactions:
                    line = line.replace(value, "[REDACTED]")
                self.warnings.add("stderr warning: " + line)
        self.write(
            "[stdout]\n" + (stdout if log_stdout else "[private hash data omitted]\n")
        )
        self.write("\n[stderr]\n" + stderr + "\n")

    def command(self, args, script=None, timeout=3600, log_stdout=True):
        """Log separate streams, reject a failing status and return only stdout."""
        self.write("$ " + " ".join(shlex.quote(str(a)) for a in args) + "\n")
        if script:
            self.write("# stdin script:\n" + script + "\n")
        try:
            result = subprocess.run(
                list(map(str, args)),
                check=False,
                input=script,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as error:
            self.log_streams(error.stdout, error.stderr, log_stdout)
            raise RuntimeError("Command timed out") from None
        self.log_streams(result.stdout, result.stderr, log_stdout)
        self.write(f"exit={result.returncode}\n")
        if result.returncode:
            raise RuntimeError(f"Command exited {result.returncode}")
        if any(
            re.search(r"(?m)^Error:|^FAIL:", stream or "")
            for stream in (result.stdout, result.stderr)
        ):
            raise RuntimeError("Command reported an error despite exit 0")
        return result.stdout or ""

    def host(self, role):
        """Return the SSH user and address for the chosen VM role."""
        return self.cfg["SSH_USER"] + "@" + self.cfg[role + "_IP"]

    def ssh(self, role, script, timeout=3600, log_stdout=True):
        """Run a script over SSH and collect its output in the step log."""
        return self.command(
            SSH + [self.host(role), "bash -se"], script, timeout, log_stdout
        )

    @property
    def product(self):
        """The product name under test: the service user, units and archives."""
        return RENAMED_PRODUCT if self.renamed_product else DEMO_PRODUCT

    def guest(
        self, role, action, version="", log_stdout=True, old_version="", bundle="app1"
    ):
        """Run a fixed VM step over SSH with this run's parameters."""
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
            version,
            old_version,
            bundle,
            self.product,
        ]
        script = (ROOT / "acceptance/remote.sh").read_text()
        safety = (
            (ROOT / "acceptance/release_safety_test.py")
            .read_text()
            .replace(
                'HELPER_SOURCE = ""  # RELEASE_HELPER_SOURCE',
                "HELPER_SOURCE = " + repr((ROOT / "scripts/release.py").read_text()),
            )
        )
        script = script.replace(
            "# RELEASE_SAFETY_BODY", "printf '%s\\n' " + shlex.quote(safety)
        )
        script = script.replace(
            "# RELEASE_HELPER_BODY",
            "printf '%s\\n' " + shlex.quote((ROOT / "scripts/release.py").read_text()),
        )
        script = script.replace(
            "# STATUS_RETRY_BODY",
            "printf '%s\\n' "
            + shlex.quote((ROOT / "acceptance/status_retry_test.py").read_text()),
        )
        prefix = "set -- " + " ".join(map(shlex.quote, args)) + "\n"
        return self.ssh(role, prefix + script, log_stdout=log_stdout)

    def step(self, name, action):
        """Run one step once, log the outcome and stop at the first failure."""
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
        """Check a clean checkout, lab access and profiles before the VMs change."""
        self.cfg = env_file(self.config_file)
        validate(self.cfg)
        programs = ("git", "ssh", "scp") + (("ssh-keygen",) if self.host_setup else ())
        for program in programs:
            if not shutil.which(program):
                raise RuntimeError("Missing controller tool: " + program)
        self.revision = self.command(["git", "-C", ROOT, "rev-parse", "HEAD"]).strip()
        clean = not self.command(["git", "-C", ROOT, "status", "--porcelain"]).strip()
        self.meta.update(
            revision=self.revision,
            clean=clean,
            version=(ROOT / "components/app1/VERSION").read_text().strip(),
            platform_version=(ROOT / "components/platform/VERSION").read_text().strip(),
            identity_version=(ROOT / "components/identity/VERSION").read_text().strip(),
            first_app=self.first_app,
            status_retry=self.status_retry,
            host_setup=self.host_setup,
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
        """Wait for SSH and, if given, a boot ID that differs from the previous one."""
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
            self.log_streams(result.stdout, result.stderr)
            self.write(f"exit={result.returncode}\n")
            if result.returncode == 0:
                boot = self.boot_id(result.stdout)
                if boot != old_boot:
                    return boot
            time.sleep(3)
        raise RuntimeError("SSH/new boot did not become ready: " + role)

    def reset(self, role):
        """Roll a VM back to its snapshot and record the clean state after boot."""
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
        """Send a Git bundle of the chosen HEAD to the dev VM and clone it there."""
        source = self.folder / "source.bundle"
        self.command(["git", "-C", ROOT, "bundle", "create", source, "HEAD"])
        base = "podman-offline-acceptance/" + self.id
        self.ssh("DEV", "mkdir -p " + shlex.quote(base))
        self.command(SCP + [source, self.host("DEV") + ":" + base + "/source.bundle"])
        self.guest("DEV", "clone")

    def transfer(self, version=None, bundle="app1", tree="src", publish=True):
        """Transfer the chosen product bundle through the controller and record SHA256."""
        base = "podman-offline-acceptance/" + self.id
        version = version or self.meta["bundles_built"][bundle]
        archive = self.product + "-" + bundle + "-" + version + "-offline.tar.gz"
        self.ssh("PROD", "mkdir -p " + shlex.quote(base))
        # Demo provisioning is not in product bundles (backlog 25, F10).
        self.command(
            SCP
            + [
                str(ROOT / "dev/generate-certificates.sh"),
                self.host("PROD") + ":" + base + "/generate-certificates.sh",
            ]
        )
        # Compressed: PROD's fapolicyd denies every process opening an untrusted
        # Python file (%languages), including scp overwriting it. remote.sh
        # pipes the decompressed probe to python3 instead of opening a .py file.
        probe = self.folder / "prepare_host_test.py.gz"
        probe.write_bytes(
            gzip.compress(
                (ROOT / "acceptance/prepare_host_test.py").read_bytes(), mtime=0
            )
        )
        self.command(
            SCP + [probe, self.host("PROD") + ":" + base + "/prepare_host_test.py.gz"]
        )
        # The archive, its checksum and its signature, then the lab build's
        # public key: PROD trusts only that key (backlog 38).
        for source, name in [
            (base + "/" + tree + "/dist/" + archive + suffix, archive + suffix)
            for suffix in ("", ".sha256", ".asc")
        ] + [(base + "/bundle-signing.gpg", "bundle-signing.gpg")]:
            local = self.folder / name
            self.command(SCP + [self.host("DEV") + ":" + source, local])
            self.command(SCP + [local, self.host("PROD") + ":" + base + "/" + name])
        with (self.folder / archive).open("rb") as stream:
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        self.meta.setdefault("bundles", {})[bundle + "-" + version] = digest.hexdigest()
        self.write("bundle_sha256=" + digest.hexdigest() + "\n")
        if publish:
            self.guest("PROD", "publish-release", version, bundle=bundle)

    def record_bundles(self, action):
        """Read the components and versions the last build produced on DEV."""
        self.meta["bundles_built"] = bundle_versions(
            self.guest("DEV", action), self.product
        )
        self.write("bundles_built=" + json.dumps(self.meta["bundles_built"]) + "\n")

    def transfer_bundles(self):
        """Transfer only the bundles selected for this fresh-install scenario."""
        bundles = (
            ("platform", "identity", "app1", "help")
            if self.help_only
            else ("platform", "identity", "app1", "app2", "help")
        )
        if self.platform_help_only:
            bundles = ("platform", "help")
        for bundle in bundles:
            self.transfer(bundle=bundle)

    def boot_id(self, output):
        """Validate a boot ID from stdout without accepting warnings or empty output."""
        boot = output.strip()
        if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot):
            raise RuntimeError("Invalid or empty boot-ID on stdout")
        return boot

    def registry_transfer(self):
        """Transfer the small registry fixture bundle through the controller with its checksum."""
        base = "podman-offline-acceptance/" + self.id
        folder = self.folder / "registry"
        folder.mkdir(mode=0o700)
        self.ssh("PROD", "mkdir -p " + shlex.quote(base + "/registry"))
        archive = "myproduct-0.0.0-offline.tar.gz"  # Standalone fixture name.
        for suffix in ("", ".sha256"):
            local = folder / (archive + suffix)
            self.command(
                SCP
                + [
                    self.host("DEV")
                    + ":"
                    + base
                    + "/registry-fixture/dist/"
                    + archive
                    + suffix,
                    local,
                ]
            )
            self.command(
                SCP
                + [
                    local,
                    self.host("PROD") + ":" + base + "/registry/" + archive + suffix,
                ]
            )
        self.meta["registry_bundle_sha256"] = hashlib.sha256(
            (folder / archive).read_bytes()
        ).hexdigest()

    def persistent_state(self, phase, allowed_changes=()):
        """Compare private hash values and log only file names and same/changed.

        allowed_changes names files an earlier, separately verified step may
        change on purpose; every other file and the CA must stay identical.
        A passing check moves those allowed files into the baseline, so a later
        upgrade accepts the verified state but still detects new changes.
        """
        try:
            state = json.loads(self.guest("PROD", "persistent-state", log_stdout=False))
        except (ValueError, TypeError):
            raise RuntimeError(
                "Invalid or empty persistent-state JSON on stdout"
            ) from None
        if (
            not isinstance(state, dict)
            or set(state) != {"ca_der_sha256", "files_sha256"}
            or not isinstance(state["files_sha256"], dict)
            or not state["files_sha256"]
            or any(
                not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in [state["ca_der_sha256"]]
                + list(state["files_sha256"].values())
            )
            or any(
                not isinstance(name, str)
                or "\n" in name
                or name.startswith("/")
                or ".." in Path(name).parts
                for name in state["files_sha256"]
            )
        ):
            raise RuntimeError("Invalid persistent-state schema on stdout")
        if phase == "before":
            self.persistent_before = state
        if self.persistent_before is None:
            raise RuntimeError("Missing persistent-state baseline")
        before = self.persistent_before
        comparisons = {}
        for name in sorted(set(before["files_sha256"]) | set(state["files_sha256"])):
            same = before["files_sha256"].get(name) == state["files_sha256"].get(name)
            if name == "PKI/private/ca.crt":
                same = same and before["ca_der_sha256"] == state["ca_der_sha256"]
            comparisons[name] = "same" if same else "changed"
            self.write(name + ": " + comparisons[name] + "\n")
        self.meta["persistent_" + phase] = comparisons
        unexpected = [
            name
            for name, result in comparisons.items()
            if result == "changed" and name not in allowed_changes
        ]
        if before["ca_der_sha256"] != state["ca_der_sha256"]:
            unexpected.append("CA certificate")
        if phase == "after" and unexpected:
            raise RuntimeError(
                "Persistent config, certificates or CA changed during upgrade"
            )
        for name in allowed_changes:
            if name in state["files_sha256"]:
                before["files_sha256"][name] = state["files_sha256"][name]
            else:
                before["files_sha256"].pop(name, None)

    def upgrade(self):
        """Build and install a new version, and check persistent state and e2e."""
        version = self.meta["version"]
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            raise RuntimeError("Upgrade test requires a three-part numeric VERSION")
        parts = version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = ".".join(parts)
        self.meta["upgrade_version"] = new_version
        self.step("10-siblings-before", lambda: self.guest("PROD", "siblings-before"))
        self.step(
            "10-build-upgrade", lambda: self.guest("DEV", "upgrade-bundle", new_version)
        )
        self.step("10-transfer-upgrade", lambda: self.transfer(new_version))
        self.step(
            "10-install-upgrade",
            lambda: self.guest("PROD", "upgrade", old_version=version),
        )
        self.step("10-siblings-after", lambda: self.guest("PROD", "siblings-after"))
        self.step("10-check-upgrade", lambda: self.guest("PROD", "check"))
        # Public seed bytes intentionally change; config and credentials may not.
        self.step(
            "10-persistent-after",
            lambda: self.persistent_state(
                "after", allowed_changes=("app1/files/app1-seed.tar",)
            ),
        )
        self.step("10-e2e-upgrade", lambda: self.guest("DEV", "prod-e2e"))
        self.step("10-markers-upgrade", lambda: self.guest("DEV", "markers-check"))
        self.step(
            "10-retire-app",
            lambda: self.guest("PROD", "app-retire", new_version, old_version=version),
        )

    def upgrade_platform(self):
        """Verify a newer shared platform and reject an older platform before persistent changes."""
        parts = self.meta["platform_version"].split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        version = ".".join(parts)
        self.meta["platform_upgrade_release"] = version
        self.step(
            "10-platform-siblings-before",
            lambda: self.guest("PROD", "platform-siblings-before", bundle="platform"),
        )
        self.step(
            "10-platform-before",
            lambda: self.guest("PROD", "platform-before", bundle="platform"),
        )
        self.step(
            "10-platform-build",
            lambda: self.guest(
                "DEV", "platform-upgrade-bundle", version, bundle="platform"
            ),
        )
        self.step(
            "10-platform-transfer", lambda: self.transfer(version, bundle="platform")
        )
        self.step(
            "10-platform-install",
            lambda: self.guest("PROD", "platform-upgrade", version, bundle="platform"),
        )
        self.step(
            "10-platform-after",
            lambda: self.guest("PROD", "platform-after", version, bundle="platform"),
        )
        self.step(
            "10-platform-siblings-after",
            lambda: self.guest("PROD", "platform-siblings-after", bundle="platform"),
        )
        self.step("10-platform-persistent", lambda: self.persistent_state("after"))
        self.step("10-platform-e2e", lambda: self.guest("DEV", "prod-e2e"))
        self.step("10-platform-markers", lambda: self.guest("DEV", "markers-check"))
        self.step(
            "10-platform-downgrade",
            lambda: self.guest(
                "PROD",
                "platform-downgrade",
                version,
                old_version=self.meta["platform_version"],
                bundle="platform",
            ),
        )
        self.step(
            "10-platform-e2e-after-refusal", lambda: self.guest("DEV", "prod-e2e")
        )
        self.step(
            "10-platform-retire",
            lambda: self.guest(
                "PROD",
                "platform-retire",
                version,
                old_version=self.meta["platform_version"],
                bundle="platform",
            ),
        )
        self.step(
            "10-platform-final-siblings",
            lambda: self.guest("PROD", "platform-siblings-after", bundle="platform"),
        )

    def upgrade_identity(self):
        """Transfer only a rebuilt Identity image/bundle; verify runtime, data and siblings."""
        parts = self.meta["identity_version"].split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        version = ".".join(parts)
        self.meta["identity_upgrade_release"] = version
        self.step(
            "10-identity-siblings-before",
            lambda: self.guest("PROD", "identity-siblings-before", bundle="identity"),
        )
        self.step(
            "10-identity-before",
            lambda: self.guest("PROD", "identity-before", bundle="identity"),
        )
        self.step(
            "10-identity-build",
            lambda: self.guest(
                "DEV", "identity-upgrade-bundle", version, bundle="identity"
            ),
        )
        self.step(
            "10-identity-transfer", lambda: self.transfer(version, bundle="identity")
        )
        self.step(
            "10-identity-install",
            lambda: self.guest("PROD", "identity-upgrade", version, bundle="identity"),
        )
        self.step(
            "10-identity-image-data",
            lambda: self.guest("PROD", "identity-after", version, bundle="identity"),
        )
        self.step(
            "10-identity-siblings-after",
            lambda: self.guest("PROD", "identity-siblings-after", bundle="identity"),
        )
        # The explicit SECRET_TEMPLATES addition in identity-upgrade may change only
        # Identity's config; identity-after verified the result on PROD.
        self.step(
            "10-identity-persistent",
            lambda: self.persistent_state("after", IDENTITY_CONFIG_CHANGE),
        )
        self.step("10-identity-e2e", lambda: self.guest("DEV", "prod-e2e"))
        self.step("10-identity-markers", lambda: self.guest("DEV", "markers-check"))
        self.step("10-identity-database", lambda: self.guest("PROD", "database-auth"))
        self.step(
            "10-identity-retire",
            lambda: self.guest(
                "PROD",
                "identity-retire",
                version,
                old_version=self.meta["identity_version"],
                bundle="identity",
            ),
        )
        self.step(
            "10-identity-final-siblings",
            lambda: self.guest("PROD", "identity-siblings-after", bundle="identity"),
        )

    def upgrade_help(self):
        """Transfer only a new help image/content release; unchanged route forbids platform restart."""
        version = self.meta["version"]
        parts = version.split(".")
        parts[-1] = str(int(parts[-1]) + 2)
        new_version = ".".join(parts)
        self.meta["help_upgrade_version"] = new_version
        self.step(
            "10-help-before",
            lambda: self.guest("PROD", "help-siblings-before", bundle="help"),
        )
        self.step(
            "10-help-build",
            lambda: self.guest(
                "DEV", "help-upgrade-bundle", new_version, bundle="help"
            ),
        )
        self.step("10-help-transfer", lambda: self.transfer(new_version, bundle="help"))
        self.step(
            "10-help-install",
            lambda: self.guest("PROD", "help-upgrade", new_version, bundle="help"),
        )
        self.step(
            "10-help-content",
            lambda: self.guest("PROD", "help-content", new_version, bundle="help"),
        )
        self.step(
            "10-help-after",
            lambda: self.guest("PROD", "help-siblings-after", bundle="help"),
        )
        self.step("10-help-persistent", lambda: self.persistent_state("after"))
        e2e = "app1-e2e" if self.help_only else "prod-e2e"
        markers = "app1-markers-check" if self.help_only else "markers-check"
        self.step("10-help-e2e", lambda: self.guest("DEV", e2e))
        self.step("10-help-markers", lambda: self.guest("DEV", markers))
        self.step(
            "10-help-retire",
            lambda: self.guest(
                "PROD", "help-retire", new_version, old_version=version, bundle="help"
            ),
        )
        self.step(
            "10-help-retired-siblings",
            lambda: self.guest("PROD", "help-siblings-after", bundle="help"),
        )

    def credentials(self, component="identity", directory="credentials"):
        """Move the CA and demo passwords through private runtime files without logging content."""
        assert self.private is not None
        output = self.ssh("DEV", 'printf "%s" "${XDG_RUNTIME_DIR:?}"')
        runtime = output.strip()
        if not re.fullmatch(r"/run/user/[0-9]+", runtime):
            raise RuntimeError("Unexpected VM runtime path")
        self.dev_private = runtime + "/podman-offline-" + self.id
        self.ssh("DEV", "mkdir -m 700 " + shlex.quote(self.dev_private))
        # Mirrors remote.sh: the runtime account is not named after the product.
        base = "/var/lib/" + self.product + "/state/"
        files = {
            "ca.crt": "PKI/private/ca.crt",
            "alice-password": component + "/" + directory + "/users/alice-password",
            "bob-password": component + "/" + directory + "/users/bob-password",
        }
        for name, relative in files.items():
            local = self.private / name
            # Secret bytes go straight to a private file, never through command logs.
            args = SSH + [
                self.host("PROD"),
                "sudo -n -H -u "
                + self.product[:27]
                + "-ops cat "
                + shlex.quote(base + relative),
            ]
            self.write("$ " + shlex.join(args) + " > [private runtime file]\n")
            with local.open("xb") as stream:
                result = subprocess.run(
                    args, check=False, stdout=stream, stderr=subprocess.PIPE, timeout=30
                )
            self.log_streams("", result.stderr)
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
        """Delete transferred runtime secrets, even when the remote cleanup fails."""
        try:
            if self.host_setup:
                operator_flow.cleanup(self)
            if self.dev_private:
                self.guest("DEV", "cleanup")
        finally:
            if self.private:
                shutil.rmtree(str(self.private))
                self.write("Controller runtime secrets removed\n")

    def finalize(self):
        # Read-only audit evidence is required even after a failed prod step.
        """Collect read-only prod audit and clean up secrets, also after the first failure."""
        if self.prod_ready:
            try:
                action = "audit-check" if self.finished else "audit"
                self.step("11-prod-audit", lambda: self.guest("PROD", action))
            except Exception as error:  # noqa: BLE001 - preserve original failure and still clean up
                print(str(error), file=sys.stderr)
        try:
            self.step("11-cleanup", self.cleanup)
        except Exception as error:  # noqa: BLE001 - cleanup failure must affect verdict
            print(str(error), file=sys.stderr)

    def reboot(self):
        """Schedule a prod reboot and record that SSH returns with a new boot ID."""
        old = self.boot_id(self.guest("PROD", "boot"))
        self.meta["prod_boot_before_reboot"] = old
        self.guest("PROD", "reboot")
        self.meta["prod_boot_after_reboot"] = self.wait_ssh("PROD", old)

    def execute(self):
        """Run the whole acceptance flow in a fixed order without repeating failed steps."""
        self.step("00-readiness", self.readiness)
        for role in ("DEV", "PROD"):
            self.step("01-reset-" + role.lower(), lambda r=role: self.reset(r))
        self.step("02-isolate-prod", lambda: self.guest("PROD", "isolate"))
        self.step("03-source", self.source)
        self.step("03-host-path-safety", lambda: self.guest("DEV", "host-path-safety"))
        if self.host_setup:
            operator_flow.execute(self)
            return
        if self.renamed_product:
            self.execute_renamed()
            return
        if self.identity_only:
            self.step("03-unit", lambda: self.guest("DEV", "unit"))
            self.step(
                "03-identity-template-baseline",
                lambda: self.guest("DEV", "identity-template-baseline"),
            )
            self.meta["identity_version"] = "0.4.11"
            self.meta["identity_template_baseline"] = (
                "932c7f3a647a84fb5388144bc822f895cc40d959"
            )
        actions = [
            "unit",
            "build-images",
            "pull-images",
            "database-runtime",
            "dev-up",
            "venv",
            "dev-e2e",
            "registry-test",
            "examples-setup",
        ]
        if self.identity_only:
            actions.remove("unit")
        actions += [
            "example-" + name
            for name in (
                "basic",
                "secrets",
                "generated-secrets",
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
        self.step("04-bundle-list", lambda: self.record_bundles("bundle-list"))
        self.step("05-transfer", self.transfer_bundles)
        self.step("05-registry-transfer", self.registry_transfer)
        self.step(
            "06-prepare-host", lambda: self.guest("PROD", "prepare-host", bundle="help")
        )
        self.step(
            "06-help-alone", lambda: self.guest("PROD", "help-alone", bundle="help")
        )
        order = [self.first_app, "app2" if self.first_app == "app1" else "app1", "help"]
        if self.help_only:
            order = ["app1", "help"]
        if self.platform_help_only:
            order = ["help"]
        else:
            order.insert(0, "identity")
        order.insert(0, "platform")
        for bundle in order:
            self.step(
                "06-install-" + bundle,
                lambda b=bundle: self.guest("PROD", "install", bundle=b),
            )
            self.step("06-healthy-" + bundle, lambda: self.guest("PROD", "health"))
        self.step(
            "07-host-path-safety",
            lambda: self.guest("PROD", "host-path-safety", bundle="help"),
        )
        self.step(
            "07-release-safety",
            lambda: self.guest("PROD", "release-safety", bundle="platform"),
        )
        self.step("07-healthy-host-repeat", lambda: self.guest("PROD", "health"))
        if self.status_retry:
            self.step(
                "07-status-retry",
                lambda: self.guest("PROD", "status-retry", bundle="app1"),
            )
        if self.platform_help_only:
            self.step(
                "07-proxy-help-without-identity",
                lambda: self.guest("PROD", "help-without-identity", bundle="help"),
            )
            self.finished = True
            return
        self.step("07-registry-offline", lambda: self.guest("PROD", "registry-offline"))
        self.step("07-check", lambda: self.guest("PROD", "check"))
        self.step("07-database-auth", lambda: self.guest("PROD", "database-auth"))
        self.step("07-persistent-before", lambda: self.persistent_state("before"))
        self.step("08-credentials", self.credentials)
        if self.help_only:
            self.step("08-app1-e2e", lambda: self.guest("DEV", "app1-e2e"))
            self.step(
                "08-app1-markers", lambda: self.guest("DEV", "app1-markers-create")
            )
            self.upgrade_help()
            self.finished = True
            return
        self.step("08-e2e", lambda: self.guest("DEV", "prod-e2e"))
        self.step("08-shared-login", lambda: self.guest("DEV", "shared-login"))
        self.step("08-markers", lambda: self.guest("DEV", "markers-create"))
        if self.identity_only:
            self.upgrade_identity()
            self.finished = True
            return
        self.step("09-stop", lambda: self.guest("PROD", "stop"))
        for action in ("start", "restart", "crash", "hang"):
            self.step("09-" + action, lambda a=action: self.guest("PROD", a))
            if action in ("crash", "hang"):
                self.step(
                    "09-launch-audit-" + action,
                    lambda: self.guest("PROD", "launch-audit-check"),
                )
            self.step(
                "09-markers-" + action, lambda: self.guest("DEV", "markers-check")
            )
        self.step("09-reboot", self.reboot)
        self.step(
            "09-wait-boot-service", lambda: self.guest("PROD", "wait-boot-service")
        )
        self.step("09-offline-after-reboot", lambda: self.guest("PROD", "offline"))
        self.step("09-check-after-reboot", lambda: self.guest("PROD", "check"))
        self.step("09-e2e-after-reboot", lambda: self.guest("DEV", "prod-e2e"))
        self.step("09-database-auth", lambda: self.guest("PROD", "database-auth"))
        self.step("09-markers-after-reboot", lambda: self.guest("DEV", "markers-check"))
        self.step("09-home-unchanged", lambda: self.guest("PROD", "home-unchanged"))
        self.upgrade_help()
        self.upgrade()
        self.upgrade_platform()
        self.upgrade_identity()
        self.step("10-database-auth", lambda: self.guest("PROD", "database-auth"))
        self.step("10-uninstall-app1", lambda: self.guest("PROD", "uninstall"))
        self.step("10-check-uninstall", lambda: self.guest("PROD", "check"))
        self.step("10-e2e-uninstall", lambda: self.guest("DEV", "survivor-e2e"))
        self.step("10-markers-uninstall", lambda: self.guest("DEV", "survivor-markers"))
        self.step("10-home-unchanged", lambda: self.guest("PROD", "home-unchanged"))
        self.finished = True

    def execute_renamed(self):
        """Run the renamed product from generated declarations through dev and offline prod."""
        for action in ("build-images", "pull-images", "renamed-generate"):
            self.step("03-" + action, lambda a=action: self.guest("DEV", a))
        for action in ("renamed-dev-up", "venv", "renamed-dev-e2e", "renamed-dev-down"):
            self.step("03-" + action, lambda a=action: self.guest("DEV", a))
        self.step("04-renamed-bundle", lambda: self.guest("DEV", "renamed-bundle"))
        # Recorded before manual leaves the source: prod installs every built bundle.
        self.step(
            "04-renamed-bundle-list",
            lambda: self.record_bundles("renamed-bundle-list"),
        )
        # Remove manual from the source product; prod still installs its retained bundle.
        self.step(
            "04-renamed-remove-manual",
            lambda: self.guest("DEV", "renamed-remove-manual"),
        )
        order = list(self.meta["bundles_built"])
        for name in order:
            self.step(
                "05-transfer-" + name,
                lambda n=name: self.transfer(bundle=n, tree="renamed"),
            )
        self.step(
            "06-prepare-host",
            lambda: self.guest("PROD", "prepare-host", bundle="gateway"),
        )
        # The target never has the source checkout or the renamed tree.
        for name in order:
            self.step(
                "06-install-" + name,
                lambda n=name: self.guest("PROD", "install", bundle=n),
            )
            self.step("06-healthy-" + name, lambda: self.guest("PROD", "health"))
        self.step(
            "07-host-path-safety",
            lambda: self.guest("PROD", "host-path-safety", bundle="gateway"),
        )
        self.step(
            "07-release-safety",
            lambda: self.guest("PROD", "release-safety", bundle="gateway"),
        )
        self.step("07-healthy-host-repeat", lambda: self.guest("PROD", "health"))
        self.step("07-init-check", lambda: self.guest("PROD", "renamed-init-check"))
        if self.status_retry:
            self.step(
                "07-status-retry",
                lambda: self.guest("PROD", "status-retry", bundle="orders"),
            )
        self.step("08-credentials", lambda: self.credentials("login-service"))
        self.step("08-e2e", lambda: self.guest("DEV", "renamed-e2e"))
        self.step("08-markers", lambda: self.guest("DEV", "renamed-markers-create"))
        self.step("09-restart", lambda: self.guest("PROD", "restart"))
        self.step(
            "09-markers-restart", lambda: self.guest("DEV", "renamed-markers-check")
        )
        self.step(
            "09-redeploy-orders",
            lambda: self.guest("PROD", "install", bundle="orders"),
        )
        self.step("09-healthy-redeploy", lambda: self.guest("PROD", "health"))
        self.step(
            "09-markers-redeploy", lambda: self.guest("DEV", "renamed-markers-check")
        )
        # A newer inventory release without route and client removes both (item 21).
        self.step(
            "10-inventory-drop-registrations",
            self.inventory_without_registrations,
        )
        self.step(
            "10-transfer-inventory-without-registrations",
            lambda: self.transfer(
                version=self.meta["inventory_without_registrations"],
                bundle="inventory",
                tree="renamed",
            ),
        )
        self.step(
            "10-install-inventory-without-registrations",
            lambda: self.guest("PROD", "install", bundle="inventory"),
        )
        self.step(
            "10-healthy-without-registrations", lambda: self.guest("PROD", "health")
        )
        self.step(
            "10-registrations-removed",
            lambda: self.guest(
                "PROD", "renamed-registrations-removed", bundle="inventory"
            ),
        )
        self.step(
            "10-survivor-after-removal", lambda: self.guest("DEV", "renamed-survivor")
        )
        self.step(
            "10-uninstall-inventory",
            lambda: self.guest("PROD", "renamed-uninstall", bundle="inventory"),
        )
        self.step("10-survivor", lambda: self.guest("DEV", "renamed-survivor"))
        self.step(
            "10-uninstall-manual-from-retained-bundle",
            lambda: self.guest("PROD", "renamed-uninstall", bundle="manual"),
        )
        self.step(
            "10-survivor-after-manual", lambda: self.guest("DEV", "renamed-survivor")
        )
        self.step("10-home-unchanged", lambda: self.guest("PROD", "home-unchanged"))
        self.finished = True

    def inventory_without_registrations(self):
        """Build a newer inventory without route and client on DEV; record its version."""
        versions = bundle_versions(
            self.guest("DEV", "renamed-inventory-drop"), self.product
        )
        version = versions["inventory"]
        if version == self.meta["bundles_built"]["inventory"]:
            raise RuntimeError(
                "The inventory release without registrations is not newer"
            )
        self.meta["inventory_without_registrations"] = version
        self.write("inventory_without_registrations=" + version + "\n")

    def report(self):
        """Generate report and evidence; only a complete, error-free run gives CLEAN PASS."""
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
            "Warnings: " + ("; ".join(sorted(self.warnings)) or "none recorded"),
            "",
            "Persistent files: only names and same/changed are recorded; hashes remain in memory.",
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
            "Only read-only prod launch diagnostics, audit collection and secret cleanup may run after a failed step. No automatic step retries or repairs.",
            "The opt-in status-retry probe performs its controlled retry and config restoration inside that step.",
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
                if record["step"] == "11-prod-audit"
                or record["step"].startswith("09-launch-audit-")
                else "\n".join(data.decode().splitlines()[-65:]),
                fence,
            ]
        (self.folder / "EVIDENCE.md").write_text("\n".join(evidence) + "\n")
        print(verdict + ": " + str(self.folder / "EVIDENCE.md"), flush=True)
        return verdict == "CLEAN PASS"


def main():
    """Start a new run ID and produce report and cleanup even on failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument(
        "--config", default="~/.config/podman-offline-acceptance/lab.env"
    )
    parser.add_argument("--first-app", choices=["app1", "app2"], default="app1")
    parser.add_argument(
        "--help-only",
        action="store_true",
        help="Install app1/platform then help and upgrade only help",
    )
    parser.add_argument(
        "--identity-only",
        action="store_true",
        help="Install all components and verify only the independent Identity upgrade",
    )
    parser.add_argument(
        "--platform-help-only",
        action="store_true",
        help="Verify platform/help without Identity or apps",
    )
    parser.add_argument(
        "--renamed-product",
        action="store_true",
        help="Generate the renamed product from the demo and run its dev and offline lifecycle",
    )
    parser.add_argument("action", choices=["run"])
    parser.add_argument(
        "--status-retry",
        action="store_true",
        help="Inject a same-version install failure and verify status/retry on disposable PROD",
    )
    parser.add_argument(
        "--host-setup",
        action="store_true",
        help="Run the focused manual-matched item 65 setup/SSH scenario",
    )
    args = parser.parse_args()
    if args.host_setup and (args.status_retry or args.identity_only or args.help_only):
        parser.error(
            "--host-setup is a separate focused scenario; choose normal, renamed or platform-only"
        )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run):
        parser.error("Invalid run ID")
    if (
        sum(
            (
                args.help_only,
                args.identity_only,
                args.platform_help_only,
                args.renamed_product,
            )
        )
        > 1
    ):
        parser.error("Choose only one focused scenario")
    os.umask(0o077)
    if args.status_retry and args.platform_help_only:
        parser.error("--status-retry requires app1 or the renamed orders component")
    run = Run(args.run, args.config, args.first_app)
    run.help_only = args.help_only
    run.identity_only = args.identity_only
    run.platform_help_only = args.platform_help_only
    run.renamed_product = args.renamed_product
    run.status_retry = args.status_retry
    run.host_setup = args.host_setup
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
