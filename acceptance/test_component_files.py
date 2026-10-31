"""Public seed assertions and the SQL failure/retry harness, with Podman stubbed."""

import contextlib
import copy
import io
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import database_test
import test_database_init
from test_components import guest_code


class SeedContentTests(unittest.TestCase):
    def test_expected_rows_for_dev_prod_and_changed_release(self):
        check = guest_code("SEED_CONTENT")["check_rows"]
        for mode, value, rows in (
            ("dev", "release-v1", "reference|release-v1\n"),
            ("prod", "release-v1", "reference|release-v1\n"),
            ("prod", "release-v2", "reference|release-v2\n"),
        ):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                check(rows, mode, value)
            self.assertIn("reference|" + value, output.getvalue())

    def test_missing_reference_old_upgrade_value_prod_dev_sample_and_duplicates_fail(
        self,
    ):
        check = guest_code("SEED_CONTENT")["check_rows"]
        for rows in (
            "",
            "reference|release-v1\n",
            "dev-sample|dev-only\nreference|release-v2\n",
            "reference|release-v2\nreference|release-v2\n",
            "reference|private-row-value\n",
        ):
            with self.subTest(rows=rows), self.assertRaises(RuntimeError) as failure:
                check(rows, "prod", "release-v2")
            self.assertNotIn("private-row-value", str(failure.exception))


class ReportLoginTests(unittest.TestCase):
    """MOUNTS demo: the login made by the rendered seed SQL file (backlog 77)."""

    MOUNTED = (0, "/seed\n/seed-secret/020-report-role.sql\n", "")
    ROLE = (0, "1\n", "")

    def check(self, results, before=(MOUNTED, ROLE)):
        """Run check_report_login with stubbed Podman results; return the logins."""
        login = guest_code("SEED_CONTENT")["check_report_login"]
        results = list(before) + list(results)
        calls = []

        def run(arguments, **kwargs):
            calls.append((arguments, kwargs.get("input")))
            returncode, stdout, stderr = results[len(calls) - 1]
            return types.SimpleNamespace(
                returncode=returncode, stdout=stdout, stderr=stderr
            )

        with tempfile.TemporaryDirectory() as directory:
            password = Path(directory) / "password"
            password.write_text("GeneratedReportPassword\n")
            with (
                mock.patch.object(subprocess, "run", side_effect=run),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                login("app1", password, "release-v1")
        return calls[len(before) :], output.getvalue()

    def test_right_password_logs_in_and_wrong_password_is_rejected(self):
        calls, output = self.check([(0, "release-v1\n", ""), (2, "", "auth failed")])
        self.assertEqual(
            [value for _, value in calls],
            ["GeneratedReportPassword", "wrong-GeneratedReportPassword"],
        )
        for arguments, _ in calls:
            self.assertEqual(arguments[:4], ["podman", "exec", "-i", "app1-postgres-db"])
            self.assertIn("-U todo_report", arguments[-1])
            # The password goes on stdin, never in argv.
            self.assertNotIn("GeneratedReportPassword", " ".join(arguments))
        self.assertIn("MOUNTS SQL file created todo_report", output)

    def test_each_failure_names_its_cause_without_values(self):
        ok, refused = (0, "release-v1\n", ""), (2, "", "")
        for before, results, cause in (
            ((self.MOUNTED, self.ROLE), [refused, refused], "generated password was refused"),
            ((self.MOUNTED, self.ROLE), [ok, ok], "wrong password was accepted"),
            ((self.MOUNTED, self.ROLE), [(0, "stale\n", ""), refused], "unexpected query result"),
            (
                (self.MOUNTED, self.ROLE),
                [(0, "release-v1\n", "GeneratedReportPassword"), refused],
                "output contains the password",
            ),
            (((0, "/seed\n", ""),), [], "has no /seed-secret/020-report-role.sql mount"),
            ((self.MOUNTED, (0, "0\n", "")), [], "role todo_report does not exist"),
        ):
            with self.subTest(cause=cause), self.assertRaises(RuntimeError) as failure:
                self.check(results, before)
            self.assertIn(cause, str(failure.exception))
            self.assertNotIn("GeneratedReportPassword", str(failure.exception))


class SeedRetryHarnessTests(unittest.TestCase):
    def client(self):
        # Reuse the declaration fixture, without inheriting its test methods.
        fixture = test_database_init.DatabaseInitHarnessTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture.base, copy.deepcopy(fixture.client)

    def run_probe(
        self,
        first_exit="1",
        consumer="",
        repaired_exit="0",
        rows="reference=release-v1\n",
    ):
        base, client = self.client()
        commands = []
        attempts = [first_exit, repaired_exit, "0"]

        def podman(arguments):
            commands.append(arguments)
            if arguments[0] == "wait":
                result = (
                    attempts.pop(0) if arguments[-1].endswith("seed-database") else "0"
                )
            elif arguments[0] == "ps":
                result = consumer
            elif arguments[0] == "exec":
                result = rows
            else:
                result = ""
            return types.SimpleNamespace(stdout=result)

        output = io.StringIO()
        with (
            mock.patch.object(database_test, "podman", side_effect=podman),
            mock.patch.object(
                subprocess, "run", return_value=types.SimpleNamespace(returncode=0)
            ),
            contextlib.redirect_stdout(output),
        ):
            database_test.seed_retry_check(base, "disposable-network", client)
        return commands, output.getvalue()

    def test_failure_repair_and_replay_use_real_init_and_cleanup_volume(self):
        commands, output = self.run_probe()
        self.assertEqual(
            sum(command[:2] == ["kube", "down"] for command in commands), 3
        )
        self.assertEqual(commands[-1][0:2], ["volume", "rm"])
        self.assertIn("repaired import and replay retained Todo data", output)

    def test_false_init_success_started_consumer_and_failed_retry_are_rejected(self):
        for arguments in (
            {"first_exit": "0"},
            {"consumer": "Exited (0)\n"},
            {"repaired_exit": "1"},
            {"first_exit": ""},
            # A failed file's earlier statement was committed instead of rolled back.
            {"rows": "partial=x\nreference=release-v1\n"},
            {"rows": "\n"},
        ):
            with self.subTest(arguments=arguments), self.assertRaises(RuntimeError):
                self.run_probe(**arguments)
