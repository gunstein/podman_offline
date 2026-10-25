"""WP0 local gates: no lab config, Proxmox, VM, signing home or root access."""

import copy
import fcntl
import importlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent / "rpm_wp0"
sys.path.insert(0, str(HERE))
c = importlib.import_module("contracts")
guest = importlib.import_module("guest")
m = importlib.import_module("mechanisms")
op = importlib.import_module("operations")

spec = importlib.util.spec_from_file_location("wp0_controller", HERE / "run.py")
assert spec and spec.loader
wp0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wp0)


def key(fingerprint=c.APPROVED_FINGERPRINT):
    return "pub::::::::::\nfpr:::::::::" + fingerprint + ":\n"


class Clock:
    def __init__(self):
        self.value = 0.0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class PredicateTests(unittest.TestCase):
    def test_signature_rejects_unsigned_bad_exit_extra_lines_and_warning(self):
        self.assertTrue(c.signature_ok(0, "x.rpm: digests signatures OK\n"))
        for status, text in (
            (0, "x.rpm: digests OK"),
            (1, "x.rpm: digests signatures OK"),
            (0, "x.rpm: digests SIGNATURES NOT OK"),
            (0, "x.rpm: digests signatures OK\nwarning"),
            (0, "x.rpm: digests signatures OK\ny.rpm: digests signatures OK"),
        ):
            with self.subTest(status=status, text=text):
                self.assertFalse(c.signature_ok(status, text))

    def test_subkey_fingerprint_does_not_replace_primary(self):
        text = key() + "sub::::::::::\nfpr:::::::::" + "A" * 40 + ":\n"
        self.assertTrue(c.authorize_key(text))
        for text in (key("A" * 40), key() + key("B" * 40), "", "pub::::::::::\n"):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                c.authorize_key(text)

    def test_trust_poll_passes_and_times_out_at_30_seconds(self):
        self.assertEqual(c.TRUST_TIMEOUT, 30)
        clock = Clock()
        self.assertTrue(
            c.bounded_poll(
                lambda remaining: clock.value > 0.2,
                c.TRUST_TIMEOUT,
                clock.now,
                clock.sleep,
            )
        )
        clock = Clock()
        with self.assertRaisesRegex(RuntimeError, "Timed out"):
            c.bounded_poll(
                lambda remaining: False, c.TRUST_TIMEOUT, clock.now, clock.sleep
            )
        self.assertAlmostEqual(clock.value, 30)

    def test_late_trust_is_not_accepted(self):
        clock = Clock()

        def slow(remaining):
            self.assertEqual(remaining, 30)
            clock.sleep(31)
            return True

        with self.assertRaisesRegex(RuntimeError, "deadline"):
            c.bounded_poll(slow, c.TRUST_TIMEOUT, clock.now, clock.sleep)

    def test_lock_wait_times_out_at_5_seconds(self):
        self.assertEqual(c.LOCK_TIMEOUT, 5)
        clock = Clock()
        with (
            mock.patch.object(m.fcntl, "flock", side_effect=BlockingIOError),
            self.assertRaisesRegex(RuntimeError, "operation lock busy"),
        ):
            m.acquire(123, c.LOCK_TIMEOUT, clock.now, clock.sleep)
        self.assertAlmostEqual(clock.value, 5)

    def test_repair_decision_comes_from_rpmdb_state(self):
        for versions, expected in (
            ([], "install"),
            (["1.0"], "install"),
            (["2.0"], "reinstall"),
            (["1.0", "2.0"], "deduplicate"),
            (["3.0"], "stop-newer"),
        ):
            self.assertEqual(c.repair_decision(versions), expected)
        with self.assertRaises(RuntimeError):
            c.repair_decision(["1.0", "1.0"])

    def test_matrix_covers_every_case_with_no_combined_positive_negative_run(self):
        matrix = c.matrix()
        self.assertEqual(len(matrix), 24)
        self.assertEqual(len(matrix), len(set(matrix)))
        self.assertEqual({g for g, _ in matrix}, set(c.GROUPS))
        self.assertEqual(c.matrix("B"), [("B", "P2")])
        for group, profile in matrix:
            self.assertEqual(c.matrix(group, profile), [(group, profile)])
        with self.assertRaises(RuntimeError):
            c.matrix("G", "P2")

    def test_trust_requires_exact_digest_size_and_source(self):
        inventory = {"/usr/libexec/cedar/code.py": (20, "a" * 64)}
        line = "rpmdb /usr/libexec/cedar/code.py 20 " + "a" * 64
        self.assertTrue(op.trust_matches(line, inventory))
        for output in (
            "",
            line.replace("rpmdb", "file"),
            line.replace(" 20 ", " 21 "),
            line[:-1] + "b",
            line + "\nfile /var/lib/myproduct/releases/any/file.py 1 " + "b" * 64,
        ):
            self.assertFalse(op.trust_matches(output, inventory))


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.baseline = wp0.recorded_policy()

    def test_p1_exact_and_p2_derivation(self):
        self.assertTrue(c.check_profile(self.baseline, self.baseline, "P1"))
        sources = {"base.rules": "\n".join(c.P1_RULES) + "\n"}
        changed, config = c.derive_p2_sources(sources, self.baseline["config"])
        self.assertEqual(
            tuple(changed["base.rules"].splitlines()),
            tuple(r for r in c.P1_RULES if r not in c.REMOVED_RULES),
        )
        p2 = dict(
            self.baseline,
            rules="\n".join(
                str(i) + ". " + rule
                for i, rule in enumerate(changed["base.rules"].splitlines(), 1)
            ),
            config=config,
        )
        self.assertTrue(c.check_profile(p2, self.baseline, "P2"))
        with self.assertRaises(RuntimeError):
            c.check_profile(p2, self.baseline, "P1")

    def test_unrelated_changes_are_rejected(self):
        for field, value in (
            (
                "config",
                self.baseline["config"].replace(
                    "subj_cache_size = 4099", "subj_cache_size = 16381"
                ),
            ),
            ("rules", self.baseline["rules"] + "\n15. allow perm=any all : all"),
            ("filter", "changed"),
            ("plugin", "missing"),
            ("languages", []),
        ):
            observed = dict(self.baseline, **{field: value})
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                c.check_profile(observed, self.baseline, "P1")

    def test_ambiguous_source_policy_rejected_before_writes(self):
        for sources in (
            {"one": "\n".join(c.P1_RULES[:-3])},
            {"one": "\n".join(c.P1_RULES), "two": c.P1_RULES[0]},
        ):
            original = dict(sources)
            with self.assertRaises(RuntimeError):
                c.derive_p2_sources(sources, self.baseline["config"])
            self.assertEqual(sources, original)

    def test_baseline_refuses_state_and_inactive_security(self):
        facts = {
            "os": "Oracle Linux Server release 9.8\n",
            "selinux": "Enforcing\n",
            "services": ["active", "active"],
            "artifacts": [],
            "packages": [],
            "keys": [],
        }
        self.assertTrue(c.check_baseline(facts))
        for field, value in (
            ("os", "OL8"),
            ("selinux", "Permissive"),
            ("services", ["active", "inactive"]),
            ("artifacts", ["/root/pkg"]),
            ("packages", ["cedar"]),
            ("keys", ["probe-key"]),
        ):
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                c.check_baseline(dict(facts, **{field: value}))


class ProxmoxBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.raw = mock.Mock()
        self.api = wp0.ProdAPI(self.raw, "108")
        self.config = {
            "scsi0": "local-zfs:vm-108-disk-0,size=32G",
            "scsi1": "local-zfs:vm-108-disk-1,size=8G",
            "parent": "clean-agent",
        }
        self.status = {"status": "running", "ha": {"managed": 0}}
        self.snapshots = [
            {"name": "old", "snaptime": 1},
            {"name": "clean-agent", "snaptime": 2, "parent": "old"},
            {"name": "current"},
        ]
        self.configurations = {"old": self.config, "clean-agent": self.config}

    def test_snapshot_preflight_all_disks_and_ha(self):
        self.assertTrue(
            c.snapshot_preflight(
                self.config, self.status, self.snapshots, self.configurations
            )
        )
        for status in ({"ha": {"managed": 1}}, {}):
            with self.assertRaises(RuntimeError):
                c.snapshot_preflight(
                    self.config, status, self.snapshots, self.configurations
                )
        later = self.snapshots + [{"name": "strict", "snaptime": 3}]
        configs = dict(
            self.configurations,
            strict={"scsi0": "different:disk", "scsi1": self.config["scsi1"]},
        )
        with self.assertRaisesRegex(RuntimeError, "newest"):
            c.snapshot_preflight(self.config, self.status, later, configs)
        incomplete = dict(
            self.configurations, **{"clean-agent": {"scsi0": self.config["scsi0"]}}
        )
        with self.assertRaisesRegex(RuntimeError, "every current"):
            c.snapshot_preflight(self.config, self.status, self.snapshots, incomplete)

    def test_missing_anchor_and_unsnapshotable_disk_stop(self):
        with self.assertRaises(RuntimeError):
            c.snapshot_preflight(self.config, self.status, [], {})
        with self.assertRaises(RuntimeError):
            c.disks({"scsi0": "local-zfs:x,snapshot=0"})
        with self.assertRaises(RuntimeError):
            c.snapshot_preflight(
                dict(self.config, parent="strict"),
                self.status,
                self.snapshots,
                self.configurations,
            )

    def test_allowlist_denies_all_snapshot_mutations_and_other_vms(self):
        for method, path in (
            ("POST", self.api.base + "/snapshot"),
            ("DELETE", self.api.base + "/snapshot/clean-agent"),
            ("PUT", self.api.base + "/snapshot/clean-agent/config"),
            ("POST", self.api.base + "/snapshot/strict/rollback"),
            ("GET", "/nodes/{node}/qemu/109/config"),
            ("POST", "/nodes/{node}/qemu/109/status/start"),
            ("GET", "/cluster/ha/resources"),
            ("GET", "/nodes/{node}/tasks/unknown/status"),
        ):
            with (
                self.subTest(method=method, path=path),
                self.assertRaises(RuntimeError),
            ):
                self.api.request(method, path)
        self.raw.request.assert_not_called()

    def test_only_tasks_issued_for_prod_can_be_polled(self):
        task = "UPID:node:0001:0002:0003:qmstop:108:root@pam:"
        self.raw.request.return_value = task
        self.assertEqual(self.api.request("POST", self.api.base + "/status/stop"), task)
        path = next(iter(self.api.tasks))
        self.raw.request.return_value = {"status": "stopped", "exitstatus": "OK"}
        self.assertEqual(self.api.request("GET", path)["exitstatus"], "OK")
        self.raw.request.return_value = task.replace(":108:", ":109:")
        with self.assertRaises(RuntimeError):
            self.api.request("POST", self.api.base + "/status/start")

    def test_reset_preflight_before_mutation_and_clears_ready(self):
        run = wp0.Investigation(mock.Mock())
        run.api = mock.Mock()
        run.api.base = "/nodes/{node}/qemu/108"
        run.prod_ready = True
        run.api.preflight.side_effect = RuntimeError("newer snapshot")
        with self.assertRaises(RuntimeError):
            run.reset()
        run.api.task.assert_not_called()
        run.api.preflight.side_effect = None
        run.api.request.return_value = {"status": "running"}

        def stop(suffix):
            self.assertFalse(run.prod_ready)
            raise RuntimeError("stop failed")

        run.api.task.side_effect = stop
        with self.assertRaises(RuntimeError):
            run.reset()
        self.assertFalse(run.prod_ready)


class BootstrapTests(unittest.TestCase):
    def test_invalid_key_stops_before_import_or_database_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "db"
            for colons in (key() + key("A" * 40), key("A" * 40)):
                with (
                    mock.patch.object(op, "key_text", return_value=colons),
                    mock.patch.object(op, "command") as command,
                ):
                    with self.assertRaisesRegex(RuntimeError, "STOP:"):
                        op.import_product(Path("bad.asc"), database)
                    command.assert_not_called()
                    self.assertFalse(database.exists())

    def test_bootstrap_stops_without_install_and_verifies_private_copy(self):
        with (
            mock.patch.object(
                op, "verify_paper_delivery", return_value=False
            ) as verify,
            mock.patch.object(op, "paper_install") as install,
            self.assertRaisesRegex(RuntimeError, "signature"),
        ):
            op.bootstrap()
        verify.assert_called_once_with("RPM-GPG-KEY-myproduct", op.DELIVERED)
        install.assert_not_called()

    def test_validated_key_precedes_import_and_database_creation(self):
        calls = []
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(
                op, "key_text", side_effect=lambda path: calls.append("key") or key()
            ),
            mock.patch.object(
                op, "command", side_effect=lambda args: calls.append(args)
            ),
        ):
            op.import_product(Path("product.asc"), Path(directory) / "fresh-db")
        self.assertEqual(calls[0], "key")
        self.assertEqual(calls[1][0], "rpmkeys")
        self.assertIn("--import", calls[1])

    def test_fingerprint_cannot_be_overridden_by_delivery(self):
        run = wp0.Investigation(mock.Mock())
        run.execute_command = mock.Mock()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "product-fingerprint").write_text("A" * 40)
            with self.assertRaisesRegex(RuntimeError, "delivery file"):
                run.transfer(root)
            run.execute_command.assert_not_called()
        self.assertEqual(
            c.APPROVED_FINGERPRINT, "425584C83A44FFC9F7E5E1A4E2021B0CC1DD70E3"
        )
        self.assertNotIn("product-fingerprint", (HERE / "fixtures.py").read_text())

    def test_c2_checks_actual_stop_and_postconditions(self):
        guest.PREDICATES.clear()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Simulate a broken bootstrap accepting a two-key file: the C2 gate
            # must fail, even though the fixture itself has two primary keys.
            with (
                mock.patch.object(op, "PKG", root),
                mock.patch.object(op, "global_keys", return_value=["os-key"]),
                mock.patch.object(op, "versions", return_value=[]),
                mock.patch.object(op, "bootstrap", return_value=True),
                self.assertRaisesRegex(RuntimeError, "stop-two-primary"),
            ):
                guest.stop_rules()
        self.assertEqual(guest.PREDICATES, [])


class MechanismTests(unittest.TestCase):
    def test_inherited_lock_accepts_shared_description_and_refuses_unlocked_forgery(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock"
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                with self.assertRaisesRegex(RuntimeError, "did not inherit"):
                    m.inherited(fd, path)
                fcntl.flock(fd, fcntl.LOCK_EX)
                duplicate = os.dup(fd)
                try:
                    self.assertTrue(m.inherited(duplicate, path))
                finally:
                    os.close(duplicate)
                other = Path(directory) / "other"
                other.write_text("")
                with self.assertRaisesRegex(RuntimeError, "forged"):
                    m.inherited(fd, other)
            finally:
                os.close(fd)

    def test_scm_rights_retains_lock_after_sender_closes(self):
        import array

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock"
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            left, right = socket.socketpair()
            received = None
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                left.sendmsg(
                    [b'{"state":"uninitialized","allowed":true}'],
                    [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))],
                )
                received = m.receive_lock(right)
                os.close(fd)
                fd = None
                self.assertTrue(m.inherited(received, path))
            finally:
                if fd is not None:
                    os.close(fd)
                if received is not None:
                    os.close(received)
                left.close()
                right.close()

    def test_guard_rejects_each_invalid_record(self):
        record = {
            "package": "cedar-base-1-1",
            "pid": 23,
            "start": "100",
            "boot": "boot",
            "nonce": "a" * 64,
        }
        process = lambda pid: ("100", True)
        self.assertTrue(
            m.guard_record(record, record["package"], [23], "boot", process)
        )
        for change in (
            {"package": "other"},
            {"boot": "other"},
            {"start": "0"},
            {"nonce": ""},
        ):
            with self.assertRaises(RuntimeError):
                m.guard_record(
                    dict(record, **change), record["package"], [23], "boot", process
                )
        with self.assertRaisesRegex(RuntimeError, "ancestor"):
            m.guard_record(record, record["package"], [], "boot", process)
        with self.assertRaisesRegex(RuntimeError, "not wp0-admin"):
            m.guard_record(
                record, record["package"], [23], "boot", lambda pid: ("100", False)
            )

        def dead(pid):
            raise FileNotFoundError

        with self.assertRaisesRegex(RuntimeError, "dead"):
            m.guard_record(record, record["package"], [23], "boot", dead)

    def test_identity_mismatch_prevents_any_release_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            records = Path(directory)
            path = records / "cedar-base.json"
            path.write_text('{"header":"old"}')
            with (
                mock.patch.object(m, "IDENTITIES", records),
                mock.patch.object(
                    m, "package_identity", return_value={"header": "changed"}
                ),
                mock.patch.object(m, "command") as command,
            ):
                # Test process owns the fixture record; owner 0 is enforced by
                # the real entry point, separately from this identity predicate.
                with (
                    mock.patch.object(
                        Path,
                        "stat",
                        return_value=type(
                            "S", (), {"st_uid": 0, "st_mode": 0o100644}
                        )(),
                    ),
                    self.assertRaisesRegex(RuntimeError, "mismatching identity"),
                ):
                    m.verify_identity("cedar-base")
                command.assert_not_called()


class ReportingTests(unittest.TestCase):
    def test_no_pass_without_explicit_predicate_and_report_after_any_failure(self):
        for value in (None, False, 1, {}, []):
            with tempfile.TemporaryDirectory() as directory:
                evidence = wp0.Evidence(Path(directory) / "run", [("C1", "P1")])
                with self.assertRaises(RuntimeError):
                    evidence.step("missing", lambda v=value: v)
                self.assertEqual(evidence.records[0]["result"], "FAIL")
                self.assertIn("NOT CLEAN", (evidence.folder / "REPORT.md").read_text())
                self.assertTrue((evidence.folder / "metadata.json").is_file())

    def test_audit_failure_does_not_erase_original_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = wp0.Evidence(Path(directory) / "run", [("A", "P1")])
            for label in ("original-probe", "audit"):
                with self.assertRaises(RuntimeError):
                    evidence.step(label, lambda: c.require(False, "injected failure"))
            records = [
                json.loads(line)
                for line in (evidence.folder / "record.jsonl").read_text().splitlines()
            ]
            self.assertEqual(
                [row["step"] for row in records], ["original-probe", "audit"]
            )
            self.assertEqual([row["result"] for row in records], ["FAIL", "FAIL"])

    def test_probe_completion_requires_every_named_predicate(self):
        for group in c.GROUPS:
            required = wp0.expected_predicates(group)
            self.assertTrue(required)
            value = {"ok": True, "predicates": list(required)}
            if group == "C2":
                value["observations"] = [{"kind": "two-primary-rpm-import-NOT-A-GATE"}]
            self.assertTrue(wp0.check_probe(group, value))
            value["predicates"].pop()
            with self.assertRaises(RuntimeError):
                wp0.check_probe(group, value)

    def test_import_and_listing_never_read_lab_configuration(self):
        with (
            mock.patch.object(
                wp0, "env_file", side_effect=AssertionError("lab access")
            ),
            mock.patch.object(sys, "argv", ["run.py", "--list"]),
        ):
            self.assertEqual(wp0.main(), 0)


class FlowTests(unittest.TestCase):
    def test_remote_program_has_independent_pin_and_no_import_side_effects(self):
        run = wp0.Investigation(mock.Mock())
        run.host = "placeholder"
        captured = []

        def capture(args, script):
            captured.append(script)
            return '{"success": true, "value": {"captured": true}}'

        run.execute_command = capture
        self.assertEqual(run.remote("not-an-action"), {"captured": True})
        self.assertIn(c.APPROVED_FINGERPRINT, captured[0])
        # Execute the exact generated program with an unknown action locally.
        # Its only action must be a JSON failure, without an OS/lab command.
        result = subprocess.run(
            [sys.executable, "-B", "-"],
            input=captured[0],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertFalse(data["success"])
        self.assertEqual(data["commands"], [])

    def test_timeout_evidence_and_report_are_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = wp0.Evidence(Path(directory) / "run", [("E", "P1")])
            run = wp0.Investigation(evidence)
            run.redactions.append("private-fixture-value")
            timeout = subprocess.TimeoutExpired(
                ["safe-command"],
                1,
                output=b"private-fixture-value",
                stderr=b"partial error",
            )
            with (
                mock.patch.object(wp0.subprocess, "run", side_effect=timeout),
                self.assertRaisesRegex(RuntimeError, "timed out"),
            ):
                evidence.step("timeout", lambda: run.execute_command(["safe-command"]))
            command = json.loads((evidence.folder / "command-0001.json").read_text())
            self.assertTrue(command["timed_out"])
            self.assertEqual(command["stdout"], "[REDACTED]")
            self.assertIn("NOT CLEAN", (evidence.folder / "REPORT.md").read_text())

    def test_e_uses_first_runtime_ssh_execution_after_trust(self):
        run = wp0.Investigation(mock.Mock())
        run.host = "placeholder"
        run.cfg = {"HTTPS_PORT": "8443"}
        order = []
        run.account = lambda private: order.append("account") or True
        run.execute_command = lambda args: "10/25/2026 12:00:00"
        run.remote = lambda group, arguments: (
            order.append("trust") or {"ok": True, "predicates": ["trust-visible"]}
        )
        run.runtime = lambda code: (
            order.append("first-execution") or "WP0 trusted module"
        )
        self.assertTrue(run.probe("E", Path("unused"), Path("unused")))
        self.assertEqual(order, ["account", "trust", "first-execution"])
        run.remote = lambda *args: {"ok": True, "predicates": []}
        run.runtime = mock.Mock()
        with self.assertRaises(RuntimeError):
            run.probe("E", Path("unused"), Path("unused"))
        run.runtime.assert_not_called()

    def test_e_guest_returns_trust_only_and_controller_executes_first(self):
        guest.PREDICATES.clear()
        with (
            mock.patch.object(op, "install_verified", return_value=True) as install,
            mock.patch.object(op, "wait_trust", return_value=True) as trust,
            mock.patch.object(op, "command") as command,
        ):
            result = guest.main("E", {})
        install.assert_called_once_with([op.DELIVERED])
        trust.assert_called_once_with([op.TOOLS])
        command.assert_not_called()
        self.assertEqual(result["predicates"], ["trust-visible"])
        run = wp0.Investigation(mock.Mock())
        run.host = "placeholder"
        run.cfg = {"HTTPS_PORT": "8443"}
        run.account = mock.Mock(return_value=True)
        run.execute_command = mock.Mock(return_value="10/25/2026 12:00:00")
        run.remote = mock.Mock(return_value=result)
        run.runtime = mock.Mock(return_value="WP0 trusted module")
        self.assertTrue(run.probe("E", Path("unused"), Path("unused")))
        run.runtime.assert_called_once_with("wp0-selfcheck\n")

    def test_full_matrix_order_and_first_failure_stop_without_lab(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory:
                events = []
                fake = mock.Mock()
                fake.prod_ready = False
                fake.audit_start = None
                fake.redactions = []
                fake.cfg = {"PROD_HOST": "fixture.invalid"}
                fake.api.preflight.return_value = True
                fake.connect.return_value = True
                for method in (
                    "reset",
                    "baseline",
                    "profile",
                    "isolate",
                    "transfer",
                    "collect_audit",
                ):
                    getattr(fake, method).side_effect = (
                        lambda *args, method=method, events=events: (
                            events.append(method) or True
                        )
                    )

                def probe(group, *args, events=events, fail=fail):
                    events.append("probe-" + group)
                    return not (fail and group == "C1")

                fake.probe.side_effect = probe

                def command(args):
                    if str(args[1]).endswith("build.sh"):
                        fixtures = Path(args[2]) / "fixtures"
                        fixtures.mkdir()
                        (fixtures / op.DELIVERED).write_bytes(b"fixture")
                    return ""

                fake.execute_command.side_effect = command
                argv = ["run.py", "--run", "local-wiring", "--execute"]
                with (
                    mock.patch.object(wp0, "Investigation", return_value=fake),
                    mock.patch.object(wp0.Path, "home", return_value=Path(directory)),
                    mock.patch.object(wp0, "key_inventory", return_value={}),
                    mock.patch.object(
                        wp0.subprocess,
                        "check_output",
                        side_effect=lambda args, **kwargs: (
                            "feature/69-wp0"
                            if "branch" in args
                            else ("" if "status" in args else "fixture-commit")
                        ),
                    ),
                    mock.patch.object(sys, "argv", argv),
                ):
                    result = wp0.main()
                expected = []
                for group, profile in c.matrix():
                    expected.extend(
                        [
                            "reset",
                            "baseline",
                            "profile",
                            "isolate",
                            "transfer",
                            "probe-" + group,
                        ]
                    )
                    if fail and group == "C1":
                        break
                    expected.append("collect_audit")
                self.assertEqual(events, expected)
                self.assertEqual(result, 1 if fail else 0)
                report = (
                    Path(directory)
                    / "podman-offline-acceptance-runs/local-wiring/REPORT.md"
                )
                self.assertIn(
                    "NOT CLEAN" if fail else "\nWP0 MATRIX PASS\n", report.read_text()
                )

    def test_repair_missing_files_and_missing_registration_have_different_repairs(self):
        from types import SimpleNamespace

        for state, action in (
            ("R1", "reinstall"),
            ("R2", "install"),
            ("R4", "install"),
        ):
            with self.subTest(state=state):
                guest.PREDICATES.clear()
                installed = ["2.0"] if state != "R4" else ["1.0"]
                calls = []

                def command(args, calls=calls, installed=installed, **kwargs):
                    calls.append(list(args))
                    if "--justdb" in args:
                        installed.clear()
                    if "-V" in args:
                        return SimpleNamespace(
                            returncode=1,
                            stdout="missing wp0-selfcheck\nmissing probe_module.py",
                            stderr="",
                        )
                    return SimpleNamespace(
                        returncode=0, stdout="WP0 trusted module", stderr=""
                    )

                def install(actual, expected=action, installed=installed):
                    self.assertEqual(actual, expected)
                    installed[:] = ["2.0"]

                with (
                    mock.patch.object(op, "install_verified", return_value=True),
                    mock.patch.object(op, "command", side_effect=command),
                    mock.patch.object(
                        op,
                        "versions",
                        side_effect=lambda installed=installed: list(installed),
                    ),
                    mock.patch.object(op, "verify_paper_delivery", return_value=True),
                    mock.patch.object(op, "paper_install", side_effect=install),
                    mock.patch.object(op, "rpm_clean", return_value=True),
                    mock.patch.object(op, "wait_trust", return_value=True),
                    mock.patch.object(Path, "unlink"),
                    mock.patch.object(Path, "is_file", return_value=True),
                ):
                    self.assertTrue(guest.repair(state))
                self.assertEqual(set(guest.PREDICATES), wp0.expected_predicates(state))
                if state == "R2":
                    self.assertIn(
                        ["rpm", "-e", "--justdb", "--noscripts", op.TOOLS], calls
                    )
                else:
                    self.assertFalse(any("--justdb" in call for call in calls))

    def test_release_spec_owns_only_its_leaf_directory_and_payload(self):
        fixtures = importlib.import_module("fixtures")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            top, output = root / "build", root / "out"
            top.mkdir()
            output.mkdir()
            binary = top / "RPMS/noarch"
            binary.mkdir(parents=True)

            def rpmbuild(args):
                self.assertEqual(args[0], "rpmbuild")
                name = Path(args[-1]).stem.removesuffix("-1.0")
                (binary / (name + "-1.0-1.noarch.rpm")).write_bytes(b"stub RPM")
                return ""

            with (
                mock.patch.object(fixtures, "TOP", top),
                mock.patch.object(fixtures, "OUT", output),
                mock.patch.object(fixtures, "run", side_effect=rpmbuild),
                mock.patch.object(fixtures, "sign"),
            ):
                for name in ("wp0-release-base", "wp0-release-sibling"):
                    leaf = "/var/lib/wp0-probe/releases/" + name
                    files = {leaf + "/version": (b"1.0\n", 0o644)}
                    fixtures.build(name, "1.0", files, ":", owned_directories=(leaf,))
                    spec = (top / (name + "-1.0.spec")).read_text()
                    manifest = spec.split("%defattr(-,root,root,-)\n", 1)[1]
                    self.assertEqual(
                        set(manifest.splitlines()), {"%dir " + leaf, leaf + "/version"}
                    )
                    staged = top / (name + "-1.0") / leaf.lstrip("/")
                    self.assertTrue(staged.is_dir())
                    self.assertEqual((staged / "version").read_bytes(), b"1.0\n")

    def test_fixture_layout_versions_and_generated_shell_syntax(self):
        # Verify the fixture generator and its actual shell payloads without
        # rpm-build, GnuPG, network or access to the real signing home.
        import struct

        fixtures = importlib.import_module("fixtures")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out"
            output.mkdir()
            built = []
            fake_rpm = (
                bytes(104)
                + struct.pack(">II", 0, 0)
                + bytes(8)
                + struct.pack(">II", 0, 100)
                + bytes(200)
            )

            def build(name, version, payload, guard, *args, owned_directories=()):
                if name.startswith("wp0-release-"):
                    self.assertEqual(
                        owned_directories, ("/var/lib/wp0-probe/releases/" + name,)
                    )
                    self.assertEqual(
                        args,
                        (
                            "Requires: myproduct-tools\nRequires(preun): myproduct-tools",
                        ),
                    )
                else:
                    self.assertEqual(owned_directories, ())
                built.append((name, version, payload, guard))
                (output / (name + "-" + version + "-1.noarch.rpm")).write_bytes(
                    fake_rpm
                )

            def command(args):
                if "--list-keys" in args:
                    primary = (
                        c.APPROVED_FINGERPRINT
                        if args[-1] == c.APPROVED_FINGERPRINT
                        else "A" * 40
                    )
                    return (
                        key(primary) + "sub::::::::::\nfpr:::::::::" + "B" * 40 + ":\n"
                    )
                return "public fixture"

            with (
                mock.patch.object(fixtures, "OUT", output),
                mock.patch.object(fixtures, "SUPPORT", HERE),
                mock.patch.object(fixtures, "TOP", root / "build"),
                mock.patch.object(fixtures, "run", side_effect=command),
                mock.patch.object(fixtures, "build", side_effect=build),
                mock.patch.dict(os.environ),
            ):
                fixtures.main()
            self.assertEqual(len(built), 7)
            self.assertFalse((output / "product-fingerprint").exists())
            for name, version, payload, guard in built:
                scripts = [guard.encode()] + [
                    data
                    for data, mode in payload.values()
                    if data.startswith(b"#!/bin/bash")
                ]
                for source in scripts:
                    result = subprocess.run(
                        ["bash", "-n"], input=source, capture_output=True, check=False
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)


class AdditionalContractTests(unittest.TestCase):
    def test_health_rejects_active_unit_with_missing_unhealthy_or_incomplete_runtime(
        self,
    ):
        status = {
            "product": "myproduct",
            "pending": None,
            "components": [
                {"name": name, "version": "0.4.12", "complete": True, "state": "active"}
                for name in ("platform", "identity")
            ],
        }
        container = {
            "IsInfra": False,
            "IsService": False,
            "State": {
                "Running": True,
                "Status": "running",
                "Health": {"Status": "healthy"},
            },
        }
        rows = [copy.deepcopy(container) for _ in range(3)]
        self.assertTrue(
            c.runtime_health(status, rows + [dict(container, IsInfra=True)])
        )
        with self.assertRaises(RuntimeError):
            c.runtime_health(status, rows[:2])
        broken = copy.deepcopy(rows)
        broken[0]["State"]["Health"]["Status"] = "unhealthy"
        with self.assertRaises(RuntimeError):
            c.runtime_health(status, broken)
        incomplete = copy.deepcopy(status)
        incomplete["components"][0]["complete"] = False
        with self.assertRaises(RuntimeError):
            c.runtime_health(incomplete, rows)
        with self.assertRaises(RuntimeError):
            c.runtime_health(dict(status, pending={"component": "platform"}), rows)

    def test_late_lock_acquisition_is_not_accepted(self):
        clock = Clock()

        def slow(fd, flags):
            clock.sleep(6)

        with (
            mock.patch.object(m.fcntl, "flock", side_effect=slow),
            self.assertRaisesRegex(RuntimeError, "deadline"),
        ):
            m.acquire(123, c.LOCK_TIMEOUT, clock.now, clock.sleep)

    def test_rpm_query_uses_rpm_newline_and_tab_escapes(self):
        from types import SimpleNamespace

        def command(args, **kwargs):
            query = args[args.index("--qf") + 1]
            # Model rpm's query formatting, including its own escape decoding.
            self.assertNotIn(chr(92) * 2, query)
            text = query.replace("%{VERSION}", "2.0").replace(chr(92) + "n", "\n")
            return SimpleNamespace(stdout=text, stderr="", returncode=0)

        with mock.patch.object(op, "command", side_effect=command):
            self.assertEqual(op.versions(), ["2.0"])
        calls = []

        def inventory(args, **kwargs):
            query = args[args.index("--qf") + 1]
            self.assertNotIn(chr(92) * 2, query)
            calls.append(query)
            text = "/usr/libexec/worker.py\t7\t" + "a" * 64 + "\t33188\n"
            return SimpleNamespace(stdout=text, stderr="", returncode=0)

        with mock.patch.object(op, "command", side_effect=inventory):
            self.assertEqual(
                op.trust_inventory(["cedar-tools"]),
                {"/usr/libexec/worker.py": (7, "a" * 64)},
            )
        self.assertIn(chr(92) + "t", calls[0])

    def test_secret_error_is_scrubbed_in_all_evidence_files(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = wp0.Evidence(Path(directory) / "run", [("C1", "P1")])
            evidence.redactions.append("private-value")

            def fail():
                raise RuntimeError("private-value")

            with self.assertRaises(RuntimeError):
                evidence.step("failure", fail)
            evidence.json("extra", {"data": "private-value"})
            for path in evidence.folder.iterdir():
                self.assertNotIn("private-value", path.read_text())

    def test_key_inventory_excludes_agent_sockets_and_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "key").write_bytes(b"private fixture, never printed")
            (root / "link").symlink_to(root / "key")
            channel = socket.socket(socket.AF_UNIX)
            try:
                channel.bind(str(root / "agent"))
                before = wp0.key_inventory(root)
                self.assertEqual(set(before), {"key"})
                (root / "key").write_bytes(b"changed fixture")
                self.assertNotEqual(before, wp0.key_inventory(root))
            finally:
                channel.close()


class FinalFlowRegressions(unittest.TestCase):
    def test_historical_filter_whitespace_and_unknown_rule_output(self):
        baseline = wp0.recorded_policy()
        observed = dict(
            baseline,
            filter=baseline["filter"].replace("# Drop any xz", "# Drop any xz "),
        )
        self.assertTrue(c.check_profile(observed, baseline, "P1"))
        with self.assertRaisesRegex(RuntimeError, "rule output"):
            c.check_profile(
                dict(
                    baseline, rules=baseline["rules"] + "\nERROR: unrecognized policy"
                ),
                baseline,
                "P1",
            )
        with self.assertRaises(RuntimeError):
            c.check_profile(
                dict(baseline, plugin_package="other-version"), baseline, "P1"
            )

    def test_duplicate_repair_rechecks_state_before_reinstall_and_keeps_release(self):
        from types import SimpleNamespace

        guest.PREDICATES.clear()
        installed = ["1.0"]
        events = []

        def command(args, **kwargs):
            if "--replacefiles" in args:
                events.append("register-delivered")
                installed.append("2.0")
            return SimpleNamespace(returncode=0, stdout="WP0 trusted module", stderr="")

        def dnf(*args):
            self.assertEqual(args, ("remove", "--duplicates"))
            # Tie the expectation to the paper command, rather than reproducing
            # an implementation-specific package restriction in the fixture.
            plan = (HERE.parents[1] / "docs/RPM-DELIVERY-PLAN.md").read_text()
            self.assertIn("`dnf ... " + " ".join(args) + "`", plan)
            events.append("deduplicate")
            installed[:] = ["2.0"]

        def install(action):
            self.assertEqual(action, "reinstall")
            events.append("reinstall")

        with (
            mock.patch.object(op, "install_verified", return_value=True),
            mock.patch.object(op, "fresh_directory"),
            mock.patch.object(
                op, "copy_candidate", return_value=Path("/root/pkg/fixture.rpm")
            ),
            mock.patch.object(op, "import_product"),
            mock.patch.object(op, "verify", return_value=True),
            mock.patch.object(op, "command", side_effect=command),
            mock.patch.object(op, "dnf", side_effect=dnf),
            mock.patch.object(
                op,
                "versions",
                side_effect=lambda package=None: (
                    ["1.0"] if package == "wp0-release-sibling" else list(installed)
                ),
            ),
            mock.patch.object(
                op,
                "verify_paper_delivery",
                side_effect=lambda: events.append("paper-verify") or True,
            ),
            mock.patch.object(op, "paper_install", side_effect=install),
            mock.patch.object(op, "rpm_clean", return_value=True),
            mock.patch.object(op, "wait_trust", return_value=True),
            mock.patch.object(m, "record_identity"),
            mock.patch.object(Path, "mkdir"),
        ):
            self.assertTrue(guest.repair("R3"))
        self.assertEqual(
            events, ["register-delivered", "paper-verify", "deduplicate", "reinstall"]
        )
        self.assertEqual(set(guest.PREDICATES), wp0.expected_predicates("R3"))

    def test_newer_tools_stop_never_installs_and_detects_changed_state(self):
        for changed in (False, True):
            with (
                self.subTest(changed=changed),
                tempfile.TemporaryDirectory() as directory,
            ):
                guest.PREDICATES.clear()
                path = Path(directory) / "module.py"
                path.write_bytes(b"private-independent-fixture")
                identities = [
                    {"header": "newer"},
                    {"header": "changed" if changed else "newer"},
                ]
                with (
                    mock.patch.object(op, "install_verified", return_value=True),
                    mock.patch.object(op, "versions", return_value=["3.0"]),
                    mock.patch.object(m, "package_identity", side_effect=identities),
                    mock.patch.object(Path, "glob", return_value=[path]),
                    mock.patch.object(op, "rpm_clean", return_value=True),
                    mock.patch.object(
                        op, "verify_paper_delivery", return_value=True
                    ) as verify,
                    mock.patch.object(op, "paper_install") as install,
                ):
                    if changed:
                        with self.assertRaisesRegex(RuntimeError, "unchanged"):
                            guest.repair("R5")
                    else:
                        self.assertTrue(guest.repair("R5"))
                        self.assertEqual(
                            set(guest.PREDICATES), wp0.expected_predicates("R5")
                        )
                    verify.assert_called_once_with()
                    install.assert_not_called()

    def test_a_uses_manual_flow_and_nonoptional_final_health_predicate(self):
        import ast

        run = wp0.Investigation(mock.Mock())
        run.cfg = {
            "HTTPS_PORT": "8443",
            "PROD_HOST": "fixture.invalid",
            "PROD_IP": "192.0.2.10",
        }
        run.operator = ["ssh", "-i", "/unused/key", "operator@placeholder"]
        run.remote = lambda *args: {"ok": True, "predicates": ["prototype-trust"]}
        run.execute_command = lambda *args: ""
        calls = []

        def runtime(code):
            calls.append(code)
            if code in ("gateway-check", "identity-check"):
                return "204" if code == "gateway-check" else "200"
            if code.startswith("python3 -B - <<'HEALTH'"):
                source = code.split("\n", 1)[1].rsplit("HEALTH", 1)[0]
                tree = ast.parse(source, feature_version=(3, 9))
                self.assertFalse(
                    any(isinstance(node, ast.Assert) for node in ast.walk(tree))
                )
                return "WP0 three containers healthy and installed status complete"
            return ""

        run.runtime = runtime
        with mock.patch.object(
            wp0.host_setup, "script", side_effect=lambda step, values: step
        ):
            self.assertTrue(run.prototype(Path("/unused/credentials")))
        self.assertEqual(
            calls[1:-1],
            [
                "init-layout",
                "gateway-config",
                "gateway-credentials",
                "gateway-install",
                "gateway-check",
                "identity-config",
                "identity-install",
                "identity-check",
            ],
        )


class EvidenceBoundaryRegressions(unittest.TestCase):
    def test_missing_or_malformed_audit_never_counts_as_clean(self):
        from types import SimpleNamespace

        with mock.patch.object(
            op,
            "command",
            return_value=SimpleNamespace(
                returncode=1, stdout="", stderr="<no matches>"
            ),
        ):
            self.assertTrue(guest.audit("10/25/26 12:00:00")["no_events"])
        for code, output in (
            (1, "read failed"),
            (1, "read failed\n<no matches>"),
            (0, ""),
            (0, "malformed event"),
        ):
            with (
                mock.patch.object(
                    op,
                    "command",
                    return_value=SimpleNamespace(
                        returncode=code, stdout=output, stderr=""
                    ),
                ),
                self.assertRaises(RuntimeError),
            ):
                guest.audit("10/25/26 12:00:00")
        with mock.patch.object(
            op,
            "command",
            return_value=SimpleNamespace(
                returncode=0, stdout="type=AVC msg=fixture", stderr=""
            ),
        ):
            self.assertFalse(guest.audit("10/25/26 12:00:00")["no_events"])

    def test_global_key_inventory_compares_public_bytes_not_key_ids(self):
        from types import SimpleNamespace

        first = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nfirst-public-fixture\n-----END PGP PUBLIC KEY BLOCK-----"
        second = first.replace("first-public-fixture", "different-public-fixture")
        with mock.patch.object(
            op,
            "command",
            side_effect=[SimpleNamespace(stdout=first), SimpleNamespace(stdout=second)],
        ):
            self.assertNotEqual(op.global_keys(), op.global_keys())
        with (
            mock.patch.object(
                op,
                "command",
                return_value=SimpleNamespace(stdout="unreadable certificate"),
            ),
            self.assertRaises(RuntimeError),
        ):
            op.global_keys()


class CompletionRegressions(unittest.TestCase):
    def test_package_query_error_is_not_a_missing_package(self):
        from types import SimpleNamespace

        with mock.patch.object(
            op,
            "command",
            return_value=SimpleNamespace(
                returncode=1,
                stdout="package myproduct-tools is not installed\n",
                stderr="",
            ),
        ):
            self.assertEqual(op.versions(), [])
        for stdout, stderr in (
            ("", "rpmdb damaged"),
            ("package myproduct-tools is not installed", "database warning"),
        ):
            with (
                mock.patch.object(
                    op,
                    "command",
                    return_value=SimpleNamespace(
                        returncode=1, stdout=stdout, stderr=stderr
                    ),
                ),
                self.assertRaises(RuntimeError),
            ):
                op.versions()

    def test_foreign_imported_fixture_must_really_verify_globally(self):
        from types import SimpleNamespace

        guest.PREDICATES.clear()
        with (
            mock.patch.object(op, "key_text", return_value=key("A" * 40)),
            mock.patch.object(
                op,
                "command",
                side_effect=[
                    SimpleNamespace(returncode=0),
                    SimpleNamespace(
                        returncode=1, stdout="SIGNATURES NOT OK", stderr=""
                    ),
                ],
            ),
            mock.patch.object(op, "import_product") as imported,
            self.assertRaisesRegex(RuntimeError, "globally imported"),
        ):
            guest.signature_matrix()
        imported.assert_not_called()
        self.assertEqual(guest.PREDICATES, [])

    def test_completion_flag_cannot_hide_missing_case_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = wp0.Evidence(Path(directory) / "run", [("E", "P1")])
            evidence.success = True
            evidence.meta["original_signing_home_unchanged"] = True
            evidence.step("controller-source", lambda: True)
            self.assertFalse(evidence.save())
            self.assertIn("NOT CLEAN", (evidence.folder / "REPORT.md").read_text())
            for step in (
                "controller-config",
                "snapshot-preflight",
                "build-fixtures",
                "E-P1-rollback",
                "E-P1-baseline",
                "E-P1-profile",
                "E-P1-isolation",
                "E-P1-transfer",
                "E-P1-probe",
                "E-P1-audit",
            ):
                evidence.step(step, lambda: True)
            self.assertTrue(evidence.save())
            report = (evidence.folder / "REPORT.md").read_text()
            self.assertIn("SELECTED CASES PASS", report)
            self.assertNotIn("WP0 MATRIX PASS", report)


class IndependentReviewRegressions(unittest.TestCase):
    def test_c1_uses_paper_gate_for_each_signature_fixture(self):
        from types import SimpleNamespace

        guest.PREDICATES.clear()
        with (
            mock.patch.object(op, "key_text", return_value=key("A" * 40)),
            mock.patch.object(
                op,
                "command",
                return_value=SimpleNamespace(
                    returncode=0, stdout="foreign.rpm: digests signatures OK", stderr=""
                ),
            ),
            mock.patch.object(
                op,
                "verify_paper_delivery",
                side_effect=[True, False, False, False, False, True, False],
            ) as paper,
            mock.patch.object(op, "verify") as tools_gate,
        ):
            self.assertTrue(guest.signature_matrix())
        self.assertEqual(
            paper.call_args_list,
            [
                mock.call("RPM-GPG-KEY-myproduct", op.DELIVERED),
                mock.call("RPM-GPG-KEY-myproduct", "unsigned.rpm"),
                mock.call("RPM-GPG-KEY-myproduct", "foreign.rpm"),
                mock.call("RPM-GPG-KEY-myproduct", "tampered-header.rpm"),
                mock.call("RPM-GPG-KEY-myproduct", "tampered-payload.rpm"),
                mock.call("product-subkey.asc", "product-subkey.rpm"),
                mock.call("RPM-GPG-KEY-myproduct", "foreign-subkey.rpm"),
            ],
        )
        tools_gate.assert_not_called()
        self.assertEqual(set(guest.PREDICATES), wp0.expected_predicates("C1"))

    def test_audit_date_round_trips_through_c_locale_libc_parser(self):
        import ctypes
        import locale

        start = subprocess.check_output(
            ["bash", "-c", c.AUDIT_START_COMMAND], text=True
        ).strip()
        previous = locale.setlocale(locale.LC_TIME)
        try:
            locale.setlocale(locale.LC_TIME, "C")
            libc = ctypes.CDLL(None)
            libc.strptime.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p]
            libc.strptime.restype = ctypes.c_char_p
            # Oversized, aligned storage for struct tm; no clock or host changes.
            storage = (ctypes.c_long * 32)()
            self.assertEqual(
                libc.strptime(start.encode(), b"%x %X", ctypes.byref(storage)), b""
            )
        finally:
            locale.setlocale(locale.LC_TIME, previous)
        self.assertEqual(c.audit_start_fields(start), start.split())
        with (
            mock.patch.object(op, "command") as command,
            self.assertRaisesRegex(RuntimeError, "C-locale"),
        ):
            guest.audit("10/25/2026 12:00:00")
        command.assert_not_called()

    def test_paper_commands_use_real_shell_globs_and_stop_before_import(self):
        from contextlib import nullcontext

        for case in (
            "valid",
            "wrong",
            "two-primary",
            "three-packages",
            "bad-signature",
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                medium, scratch, executables = (
                    root / "medium",
                    root / "pkg",
                    root / "bin",
                )
                for path in (medium, scratch, executables):
                    path.mkdir()
                (scratch / "obsolete.rpm").write_text("foreign fixture")
                (medium / "RPM-GPG-KEY-myproduct").write_text("public fixture")
                (medium / op.DELIVERED).write_text("assigned candidate")
                if case == "three-packages":
                    for version in ("1.0", "3.0"):
                        (medium / f"myproduct-tools-{version}-1.noarch.rpm").write_text(
                            "setup fixture"
                        )
                fingerprint = "A" * 40 if case == "wrong" else c.APPROVED_FINGERPRINT
                displayed = "pub   rsa2048 2026-10-25 [SC]\n      " + fingerprint + "\n"
                if case == "two-primary":
                    displayed += (
                        "pub   rsa2048 2026-10-25 [SC]\n      " + "A" * 40 + "\n"
                    )
                key_output = root / "key-output"
                key_output.write_text(displayed)
                log = root / "calls"
                prefix = '#!/bin/bash\nprintf "%s %s\\n" "${0##*/}" "$*" >> "$WP0_TEST_LOG"\n'
                bodies = {
                    "gpg": 'cat "$WP0_TEST_KEY_OUTPUT"\n',
                    "rpmkeys": """if [[ "$*" == *--import* ]]; then
mkdir -p "$2"
exit 0
fi
if [[ "$WP0_TEST_CASE" == bad-signature ]]; then
echo 'signature NOT OK'
exit 1
fi
for arg in "$@"; do
case "$arg" in
myproduct-tools-*.rpm) printf '%s: digests signatures OK\\n' "$arg";;
esac
done
""",
                    "rpm": "exit 0\n",
                    "dnf": "exit 0\n",
                    "systemctl": "printf 'ActiveState=active\\nMainPID=42\\n'\n",
                    "journalctl": 'echo \'{"__CURSOR":"before","MESSAGE":"Starting to listen for events"}\'\n',
                }
                for name, body in bodies.items():
                    path = executables / name
                    path.write_text(prefix + body)
                    path.chmod(0o755)
                with (
                    mock.patch.dict(
                        os.environ,
                        {
                            "PATH": str(executables) + os.pathsep + os.environ["PATH"],
                            "WP0_TEST_LOG": str(log),
                            "WP0_TEST_KEY_OUTPUT": str(key_output),
                            "WP0_TEST_CASE": case,
                        },
                    ),
                    mock.patch.object(op, "PKG", scratch),
                    mock.patch.object(
                        op,
                        "paper_delivery",
                        side_effect=lambda *_, medium=medium: nullcontext(medium),
                    ),
                    mock.patch.object(op, "TRANSCRIPT", []),
                ):
                    if case == "valid":
                        self.assertTrue(op.bootstrap())
                    else:
                        with self.assertRaisesRegex(RuntimeError, "STOP:"):
                            op.bootstrap()
                calls = log.read_text()
                self.assertIn("gpg --show-keys RPM-GPG-KEY-myproduct", calls)
                self.assertFalse((scratch / "obsolete.rpm").exists())
                self.assertEqual(scratch.stat().st_mode & 0o777, 0o700)
                if case in ("wrong", "two-primary"):
                    self.assertFalse((scratch / "db").exists())
                    self.assertNotIn("rpmkeys ", calls)
                else:
                    self.assertTrue((scratch / "db").is_dir())
                if case == "valid":
                    self.assertIn("rpm --import RPM-GPG-KEY-myproduct", calls)
                    self.assertIn(
                        "dnf --disablerepo=* --setopt=localpkg_gpgcheck=1 -y install ./"
                        + op.DELIVERED,
                        calls,
                    )
                else:
                    self.assertNotIn("\nrpm --import", calls)
                    self.assertNotIn("\ndnf ", calls)
                if case == "three-packages":
                    self.assertEqual(
                        len(list(scratch.glob("myproduct-tools-*.rpm"))), 3
                    )
                    self.assertIn("myproduct-tools-1.0-1.noarch.rpm", calls)
                    self.assertIn("myproduct-tools-3.0-1.noarch.rpm", calls)

    def test_paper_delivery_selects_one_candidate_without_changing_bytes(self):
        def copy(name, destination):
            target = destination / name
            target.write_bytes(name.encode())
            return target

        with mock.patch.object(op, "copy_candidate", side_effect=copy):
            with op.paper_delivery(
                "product-subkey.asc", "product-subkey.rpm"
            ) as delivery:
                self.assertEqual(
                    {p.name for p in delivery.iterdir()},
                    {"RPM-GPG-KEY-myproduct", op.DELIVERED},
                )
                self.assertEqual(
                    (delivery / op.DELIVERED).read_bytes(), b"product-subkey.rpm"
                )
                self.assertEqual(
                    (delivery / "RPM-GPG-KEY-myproduct").read_bytes(),
                    b"product-subkey.asc",
                )
            self.assertFalse(delivery.exists())

    def test_paper_display_requires_one_primary_and_its_full_fingerprint(self):
        displayed = (
            "pub   rsa2048\n    " + c.APPROVED_FINGERPRINT + "\nuid WP0\nsub rsa2048\n"
        )
        self.assertTrue(c.authorize_paper_key(displayed))
        for invalid in (
            displayed + displayed,
            displayed.replace(c.APPROVED_FINGERPRINT, "A" * 40),
            "pub rsa2048\n",
            "sub rsa2048\n" + c.APPROVED_FINGERPRINT,
        ):
            with self.assertRaises(RuntimeError):
                c.authorize_paper_key(invalid)

    def test_account_python_requires_descendants_and_lock_not_root_chown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("state", "config", "storage"):
                (root / name).mkdir()
            self.assertFalse(guest.account_python_prepared(root, os.getuid()))
            for name in (
                "config/cni/net.d",
                "config/containers/systemd",
                "storage/containers/storage",
            ):
                (root / name).mkdir(parents=True)
            self.assertFalse(guest.account_python_prepared(root, os.getuid()))
            (root / "config/cni/net.d/cni.lock").touch()
            self.assertTrue(guest.account_python_prepared(root, os.getuid()))
            self.assertFalse(guest.account_python_prepared(root, os.getuid() + 1))

    def test_build_mounts_only_disposable_copies_for_selinux_relabel(self):
        source = (HERE / "build.sh").read_text()
        self.assertIn('cp -a "$here" "$work/support"', source)
        self.assertNotIn('-v "$here"', source)
        self.assertNotIn('-v "$here/', source)
        self.assertIn('-v "$work/support":/support:ro,Z', source)


class LabFailureRegressions(unittest.TestCase):
    def test_health_program_selects_installed_layout_and_records_failure_inventory(
        self,
    ):
        import contextlib
        import io
        import types

        for fault in (None, "unhealthy", "empty"):
            with self.subTest(fault=fault):
                run = wp0.Investigation(mock.Mock())
                run.cfg = {
                    "HTTPS_PORT": "8443",
                    "PROD_HOST": "fixture.invalid",
                    "PROD_IP": "192.0.2.10",
                }
                run.operator = ["ssh", "-i", "/unused/key", "operator@placeholder"]
                run.remote = lambda *_: {"ok": True, "predicates": ["prototype-trust"]}
                run.execute_command = mock.Mock(return_value="")
                status = {
                    "product": "myproduct",
                    "pending": None,
                    "components": [
                        {
                            "name": name,
                            "version": "0.4.12",
                            "complete": True,
                            "state": "active",
                        }
                        for name in ("platform", "identity")
                    ],
                    "not_public": "PRIVATE_SENTINEL",
                }
                containers = [
                    {
                        "Name": name,
                        "IsInfra": False,
                        "IsService": False,
                        "State": {
                            "Running": True,
                            "Status": "running",
                            "Health": {"Status": "healthy"},
                        },
                        "Config": {"Env": ["PRIVATE_SENTINEL"]},
                    }
                    for name in (
                        "platform-proxy-nginx",
                        "identity-postgres-db",
                        "identity-server-app",
                    )
                ]
                if fault == "unhealthy":
                    containers[0]["State"]["Health"]["Status"] = "unhealthy"
                if fault == "empty":
                    containers = []
                order = []
                observed = io.StringIO()
                deployment = types.ModuleType("deployment")

                def select(product, order=order):
                    self.assertEqual(product, "myproduct")
                    order.append("select")
                    os.environ.update(
                        XDG_CONFIG_HOME="/var/lib/myproduct/config",
                        XDG_DATA_HOME="/var/lib/myproduct/storage",
                    )
                    return Path("/var/lib/myproduct")

                def manager(root, order=order):
                    self.assertEqual(root, Path("/var/lib/myproduct"))
                    order.append("manager")

                deployment.__dict__["layout"] = types.SimpleNamespace(
                    select=select, check_user_manager=manager
                )

                def command(
                    args, order=order, status=status, containers=containers, **kwargs
                ):
                    if args[0] == "bash":
                        self.assertNotIn("XDG_DATA_HOME", os.environ)
                        return types.SimpleNamespace(stdout=json.dumps(status))
                    if args[0] == "systemctl":
                        return types.SimpleNamespace(stdout="active")
                    self.assertEqual(
                        os.environ["XDG_CONFIG_HOME"], "/var/lib/myproduct/config"
                    )
                    self.assertEqual(
                        os.environ["XDG_DATA_HOME"], "/var/lib/myproduct/storage"
                    )
                    if args[1] == "ps":
                        order.append("podman")
                        return types.SimpleNamespace(
                            stdout=json.dumps(
                                [{"Id": str(i)} for i in range(len(containers))]
                            )
                        )
                    self.assertEqual(args[1], "inspect")
                    return types.SimpleNamespace(
                        stdout=json.dumps([containers[int(args[2])]])
                    )

                def runtime(source, observed=observed):
                    if source in ("gateway-check", "identity-check"):
                        return "204" if source == "gateway-check" else "200"
                    if not source.startswith("python3 -B - <<'HEALTH'"):
                        return ""
                    program = source.split("\n", 1)[1].rsplit("HEALTH", 1)[0]
                    with contextlib.redirect_stdout(observed):
                        exec(compile(program, "actual-WP0-health-program", "exec"), {})  # noqa: S102 - execute the actual trusted payload with mocked host boundaries
                    return observed.getvalue()

                run.runtime = runtime
                with (
                    mock.patch.object(
                        wp0.host_setup, "script", side_effect=lambda step, _: step
                    ),
                    mock.patch.dict(sys.modules, {"deployment": deployment}),
                    mock.patch.object(sys, "path", list(sys.path)),
                    mock.patch.dict(
                        os.environ, {"PATH": os.environ["PATH"]}, clear=True
                    ),
                    mock.patch.object(subprocess, "run", side_effect=command),
                ):
                    if fault is None:
                        self.assertTrue(run.prototype(Path("/unused/credentials")))
                    else:
                        with self.assertRaises(RuntimeError):
                            run.prototype(Path("/unused/credentials"))
                self.assertEqual(order, ["select", "manager", "podman"])
                output = observed.getvalue()
                projection = json.loads(output.splitlines()[0])
                self.assertEqual(projection["application_count"], len(containers))
                self.assertNotIn("PRIVATE_SENTINEL", output)
                self.assertNotIn("Config", output)
                self.assertEqual(
                    "WP0 three containers healthy" in output, fault is None
                )

    def test_audit_explicitly_reads_logs_and_keeps_no_match_diagnostic(self):
        from types import SimpleNamespace

        with mock.patch.object(
            op,
            "command",
            return_value=SimpleNamespace(
                returncode=1, stdout="", stderr="<no matches>\n"
            ),
        ) as command:
            self.assertTrue(guest.audit("10/25/26 13:46:48")["no_events"])
        command.assert_called_once_with(
            [
                "ausearch",
                "--input-logs",
                "-m",
                "FANOTIFY,AVC",
                "-ts",
                "10/25/26",
                "13:46:48",
            ],
            allowed=(0, 1),
            stdin=subprocess.DEVNULL,
        )
        # Raw mode's empty status-1 result must still never turn into a PASS.
        with (
            mock.patch.object(
                op,
                "command",
                return_value=SimpleNamespace(returncode=1, stdout="", stderr=""),
            ),
            self.assertRaisesRegex(RuntimeError, "ambiguous"),
        ):
            guest.audit("10/25/26 13:46:48")

    def test_runtime_projection_excludes_pending_contents_and_infrastructure_health(
        self,
    ):
        projection = c.runtime_projection(
            {
                "product": "myproduct",
                "pending": {"private": "PRIVATE_SENTINEL"},
                "components": [],
            },
            [
                {
                    "Name": "infra",
                    "IsInfra": True,
                    "IsService": False,
                    "State": {"Running": True, "Status": "running"},
                    "Config": {"Env": ["PRIVATE_SENTINEL"]},
                }
            ],
        )
        self.assertTrue(projection["status"]["pending_present"])
        self.assertEqual(projection["application_count"], 0)
        self.assertIsNone(projection["containers"][0]["health"])
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(projection))


if __name__ == "__main__":
    unittest.main()
