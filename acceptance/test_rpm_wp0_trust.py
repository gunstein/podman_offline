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
            (["Updated"], None),
            (["Updated", "Updated"], None),
            (["Updated", op.REFRESH_START, "Updated"], "2"),
            (["Updating trust database", "Updated", "Updated"], None),
            (["Updating trust database"], None),
            (["Updated", "Updating trust database"], None),
            (["Updating trust database", "Updated"], None),
            ([op.REFRESH_START, "Updating trust database", "Updated"], "2"),
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

    def test_cursor_waits_for_old_refresh_before_allowing_dnf(self):
        rows = [
            [{"__CURSOR": "old-start", "MESSAGE": "Updating trust database"}],
            [
                {"__CURSOR": "old-start", "MESSAGE": "Updating trust database"},
                {"__CURSOR": "old-done", "MESSAGE": "Updated"},
            ],
        ]
        calls = []

        def journal(args, timeout):
            self.assertIn("_PID=42", args)
            self.assertIsNone(op.TRUST_CURSOR)
            calls.append("journal")
            return rows.pop(0)

        with (
            mock.patch.object(op, "service_identity", return_value="42"),
            mock.patch.object(op, "journal_records", side_effect=journal),
            mock.patch.object(
                op, "command", side_effect=lambda *a, **kw: calls.append("dnf")
            ),
        ):
            op.dnf("reinstall", "same-bytes.rpm")
        self.assertEqual(calls, ["journal", "journal", "dnf"])
        self.assertEqual(op.TRUST_CURSOR, "old-done")
        with mock.patch.object(
            op,
            "journal_records",
            return_value=[{"__CURSOR": "stale-done", "MESSAGE": "Updated"}],
        ):
            self.assertIsNone(op.completed_refresh(1))

    def test_pre_transaction_timeout_never_calls_dnf_or_publishes_cursor(self):
        def expire(poll, timeout):
            self.assertEqual(timeout, 30)
            self.assertFalse(poll(timeout))
            raise RuntimeError("Timed out")

        with (
            mock.patch.object(op, "bounded_poll", side_effect=expire),
            mock.patch.object(op, "service_identity", return_value="42"),
            mock.patch.object(
                op,
                "journal_records",
                return_value=[
                    {"__CURSOR": "start", "MESSAGE": "Updating trust database"}
                ],
            ),
            mock.patch.object(op, "command") as command,
            self.assertRaisesRegex(RuntimeError, "Timed out"),
        ):
            op.dnf("reinstall", "same-bytes.rpm")
        command.assert_not_called()
        self.assertIsNone(op.TRUST_CURSOR)
        self.assertIsNone(op.TRUST_SERVICE)

    def test_initial_ready_is_idle_but_restart_before_cursor_is_refused(self):
        for identities, passes in ((["42", "42"], True), (["42", "43"], False)):
            with (
                mock.patch.object(op, "service_identity", side_effect=identities),
                mock.patch.object(
                    op,
                    "journal_records",
                    return_value=[
                        {
                            "__CURSOR": "ready",
                            "MESSAGE": "Starting to listen for events",
                        }
                    ],
                ),
            ):
                if passes:
                    op.capture_trust_cursor()
                    self.assertEqual(op.TRUST_CURSOR, "ready")
                else:
                    with self.assertRaisesRegex(RuntimeError, "restarted"):
                        op.capture_trust_cursor()
                    self.assertIsNone(op.TRUST_CURSOR)

    def test_timeout_transcript_keeps_partial_bytes_and_original_exception(self):
        for argv in (["fapolicyd-cli", "--dump-db"], op.JOURNAL):
            for output in (b"partial\xff", "partial", None):
                error = subprocess.TimeoutExpired(
                    argv, 0.5, output=output, stderr=b"diagnostic"
                )
                with (
                    mock.patch.object(op.subprocess, "run", side_effect=error),
                    self.assertRaises(subprocess.TimeoutExpired) as caught,
                ):
                    op.command(argv, timeout=0.5)
                self.assertIs(caught.exception, error)
                row = op.TRANSCRIPT[-1]
                self.assertTrue(row["timed_out"])
                self.assertEqual(row["timeout_seconds"], 0.5)
                self.assertIsNone(row["exit"])
                self.assertEqual(row["stderr"], "diagnostic")
                self.assertEqual(
                    row["stdout"],
                    ""
                    if output is None
                    else output.decode("utf-8", errors="replace")
                    if isinstance(output, bytes)
                    else output,
                )

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
