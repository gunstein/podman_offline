"""Trust observation gates: no LMDB mutation, lab access or relaxed predicates."""

import contextlib
import importlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent / "rpm_wp0"))
op = importlib.import_module("operations")


def result(output):
    return subprocess.CompletedProcess([], 0, output, "")


class TrustRefreshTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(op, "TRUST_CURSOR", "before"))
        self.stack.enter_context(mock.patch.object(op, "TRUST_SERVICE", "42"))
        self.stack.enter_context(mock.patch.object(op, "TRANSCRIPT", []))

    def test_capture_precedes_both_dnf_entry_points(self):
        calls = []
        with (
            mock.patch.object(
                op, "capture_trust_cursor", side_effect=lambda: calls.append("cursor")
            ),
            mock.patch.object(
                op, "command", side_effect=lambda args, **kw: calls.append(args[0])
            ),
            mock.patch.object(
                op,
                "paper_command",
                side_effect=lambda *a, **kw: calls.append("paper-dnf"),
            ),
        ):
            op.dnf("install", "fixture.rpm")
            self.assertEqual(calls, ["cursor", "dnf"])
            calls.clear()
            op.paper_install("reinstall")
            self.assertEqual(calls, ["rpm", "cursor", "paper-dnf"])

    def test_capture_rejects_failed_daemon_or_missing_cursor(self):
        for output in (
            "ActiveState=failed\nMainPID=0\n",
            "ActiveState=active\nMainPID=0\n",
        ):
            with (
                mock.patch.object(op, "command", return_value=result(output)),
                self.assertRaises(RuntimeError),
            ):
                op.capture_trust_cursor()
            self.assertIsNone(op.TRUST_CURSOR)
        with (
            mock.patch.object(op, "service_identity", return_value="42"),
            mock.patch.object(op, "command", return_value=result("")),
            self.assertRaisesRegex(RuntimeError, "cursor"),
        ):
            op.capture_trust_cursor()

    def test_only_last_completed_refresh_after_cursor_opens_gate(self):
        for messages, expected in (
            ([], None),
            (["Updating trust database"], None),
            (["Updated", "Updating trust database"], None),
            (["Updating trust database", "Updated"], "1"),
        ):
            records = [
                json.dumps({"__CURSOR": str(i), "MESSAGE": m})
                for i, m in enumerate(messages)
            ]
            with mock.patch.object(
                op, "command", return_value=result("\n".join(records))
            ) as command:
                self.assertEqual(op.completed_refresh(3), expected)
                self.assertIn("--after-cursor=before", command.call_args.args[0])
                self.assertEqual(command.call_args.kwargs["timeout"], 3)

    def test_no_dump_before_refresh_and_stable_refresh_passes(self):
        inv = {"/x": (1, "hash")}
        generations = iter([None, "complete", "complete"])
        with (
            mock.patch.object(op, "trust_inventory", return_value=inv),
            mock.patch.object(op, "service_identity", return_value="42"),
            mock.patch.object(
                op, "completed_refresh", side_effect=lambda timeout: next(generations)
            ),
            mock.patch.object(
                op, "command", return_value=result("rpmdb /x 1 hash\n")
            ) as command,
        ):
            self.assertTrue(op.wait_trust(["fixture"]))
        command.assert_called_once()
        self.assertEqual(command.call_args.args[0], ["fapolicyd-cli", "--dump-db"])

    def test_refresh_overlap_and_untrusted_source_never_pass(self):
        for before, after, output in (
            ("a", "b", "rpmdb /x 1 hash"),
            ("a", None, "rpmdb /x 1 hash"),
            ("a", "a", "src_unknown /x 1 hash"),
            ("a", "a", "rpmdb /x 1 hash\nfiledb /x 1 hash"),
        ):

            def one_poll(poll, timeout):
                self.assertEqual(timeout, 30)
                self.assertFalse(poll(timeout))
                raise RuntimeError("test stop")

            with (
                mock.patch.object(
                    op, "trust_inventory", return_value={"/x": (1, "hash")}
                ),
                mock.patch.object(op, "service_identity", return_value="42"),
                mock.patch.object(op, "completed_refresh", side_effect=[before, after]),
                mock.patch.object(op, "command", return_value=result(output)),
                mock.patch.object(op, "bounded_poll", side_effect=one_poll),
                self.assertRaisesRegex(RuntimeError, "test stop"),
            ):
                op.wait_trust(["fixture"])

    def test_daemon_exit_or_restart_prevents_pass(self):
        for status in (RuntimeError("fapolicyd is not active"), "43"):
            with (
                mock.patch.object(
                    op, "trust_inventory", return_value={"/x": (1, "hash")}
                ),
                mock.patch.object(op, "service_identity", side_effect=["42", status]),
                mock.patch.object(op, "completed_refresh", return_value="done"),
                mock.patch.object(
                    op, "command", return_value=result("rpmdb /x 1 hash")
                ),
                self.assertRaises(RuntimeError),
            ):
                op.wait_trust(["fixture"])

    def test_observations_share_deadline_and_cli_error_is_not_retried(self):
        with (
            mock.patch.object(op, "trust_inventory", return_value={"/x": (1, "hash")}),
            mock.patch.object(op, "service_identity", return_value="42"),
            mock.patch.object(op.time, "monotonic", side_effect=[0, 0, 31]),
            mock.patch.object(op, "completed_refresh") as refresh,
            self.assertRaisesRegex(RuntimeError, "deadline"),
        ):
            op.wait_trust(["fixture"])
        refresh.assert_not_called()
        with (
            mock.patch.object(op, "trust_inventory", return_value={"/x": (1, "hash")}),
            mock.patch.object(op, "service_identity", return_value="42"),
            mock.patch.object(op, "completed_refresh", return_value="done"),
            mock.patch.object(
                op, "command", side_effect=RuntimeError("CLI failed")
            ) as command,
            self.assertRaisesRegex(RuntimeError, "CLI failed"),
        ):
            op.wait_trust(["fixture"])
        command.assert_called_once()


if __name__ == "__main__":
    unittest.main()
