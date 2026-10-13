"""Safety/stop rules tested without SSH, Proxmox, root or network."""

import contextlib
import importlib.util
import io
import json
import os
import re
import shlex
import stat
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from pve import env_file

spec = importlib.util.spec_from_file_location(
    "runner", Path(__file__).with_name("acceptance.py")
)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def shell_code(source, function=None, heredoc=None, action=None):
    """Get named shell code or a heredoc without depending on comments or indentation."""
    if heredoc:
        match = re.search(r"<<-?['\"]?" + re.escape(heredoc) + r"['\"]?\s*\n", source)
        if not match:
            raise ValueError("Missing heredoc: " + heredoc)
        end = re.search(
            r"^" + re.escape(heredoc) + r"\s*$", source[match.end() :], re.MULTILINE
        )
        if not end:
            raise ValueError("Unterminated heredoc: " + heredoc)
        return source[match.end() : match.end() + end.start()]
    pattern = (
        r"^" + re.escape(function) + r"\(\)\s*\{"
        if function
        else r"^" + re.escape(action or "") + r"\)\s*$"
    )
    match = re.search(pattern, source, re.MULTILINE)
    if not match:
        raise ValueError("Missing shell code: " + str(function or action))
    lines = source[match.start() :].splitlines(keepends=True)
    tag, result = None, []
    for line in lines:
        result.append(line)
        if tag:
            if line.strip() == tag:
                tag = None
            continue
        marker = re.search(r"<<-?['\"]?(\w+)['\"]?", line)
        if marker:
            tag = marker.group(1)
        elif (function and re.match(r"^}\s*$", line)) or (
            action and line.strip() == ";;"
        ):
            return "".join(result) if function else "".join(result[1:-1])
    raise ValueError("Uavsluttet shellkode: " + str(function or action))


class HarnessTests(unittest.TestCase):
    """Test the run's stop rules, secrets and life cycle without lab access."""

    def setUp(self):
        """Create an isolated run folder and hide the tests' console output."""
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(mock.patch.object(runner, "RUNS", self.root))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.harness = runner.Run("test", "not-used")

    def test_existing_run_cannot_be_reused(self):
        """Confirm that an existing run ID is never overwritten."""
        with self.assertRaises(FileExistsError):
            runner.Run("test", "not-used")

    def test_failed_command_is_recorded_and_not_clean(self):
        """Confirm that the command's failing status is logged and gives NOT CLEAN."""
        with self.assertRaises(RuntimeError):
            self.harness.step(
                "01",
                lambda: self.harness.command(["python3", "-c", "raise SystemExit(7)"]),
            )
        self.assertFalse(self.harness.report())
        row = json.loads((self.harness.folder / "record.jsonl").read_text())
        self.assertEqual(row["result"], "FAIL")
        self.assertIn("exit=7", (self.harness.folder / row["log"]).read_text())
        self.assertIn("NOT CLEAN", (self.harness.folder / "EVIDENCE.md").read_text())

    def test_partial_pass_is_not_clean(self):
        """Confirm that an incomplete run cannot get CLEAN PASS."""
        self.harness.step("00", lambda: None)
        self.assertFalse(self.harness.report())

    def test_duplicate_step_cannot_be_reexecuted(self):
        """Confirm that a step that already ran is not executed again."""
        action = mock.Mock()
        self.harness.step("00", action)
        with self.assertRaises(FileExistsError):
            self.harness.step("00", action)
        action.assert_called_once()

    def test_no_steps_after_first_failure(self):
        """Confirm that a readiness failure stops further VM operations."""
        self.harness.readiness = mock.Mock(side_effect=RuntimeError("readiness"))
        self.harness.reset = mock.Mock()
        with self.assertRaises(RuntimeError):
            self.harness.execute()
        self.harness.reset.assert_not_called()

    def test_token_and_password_are_redacted_from_logs(self):
        """Confirm that known tokens and passwords are masked in logs and evidence."""
        self.harness.redactions = ["synthetic-token", "synthetic-password"]
        self.harness.step(
            "00", lambda: self.harness.write("synthetic-token synthetic-password")
        )
        self.harness.report()
        for path in self.harness.folder.rglob("*"):
            if path.is_file():
                self.assertNotIn("synthetic-token", path.read_text())
                self.assertNotIn("synthetic-password", path.read_text())

    def test_podman_zero_exit_error_is_a_failure(self):
        """Confirm that a Podman error with exit 0 still stops the run."""
        process = mock.patch.object(
            runner.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                [], 0, "Error: network cleanup failed"
            ),
        )
        with process, self.assertRaises(RuntimeError):
            self.harness.step(
                "00", lambda: self.harness.command(["podman", "kube", "down"])
            )
        self.assertFalse(self.harness.report())

    def test_expected_example_validation_error_is_not_false_failure(self):
        """Confirm that expected negative examples do not give false test failures."""
        process = mock.patch.object(
            runner.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                [], 0, "ERROR: expected config failure\nPASS: failures"
            ),
        )
        with process:
            self.harness.step(
                "00", lambda: self.harness.command(["examples/run.sh", "failures"])
            )

    def test_configuration_permissions_and_duplicate_keys(self):
        """Confirm private config permissions and rejection of duplicate keys."""
        path = self.root / "lab.env"
        path.write_text("KEY=one\n")
        path.chmod(0o644)
        with self.assertRaises(RuntimeError):
            env_file(path)
        path.chmod(0o600)
        self.assertEqual(env_file(path), {"KEY": "one"})
        path.write_text("KEY=one\nKEY=two\n")
        with self.assertRaises(RuntimeError):
            env_file(path)

    def test_cleanup_local_secrets_even_if_remote_cleanup_fails(self):
        """Confirm local secret cleanup even when the SSH cleanup fails."""
        self.harness.private = self.root / "secret"
        self.harness.private.mkdir()
        self.harness.dev_private = "/run/user/1000/test"
        self.harness.guest = mock.Mock(side_effect=RuntimeError("SSH failed"))
        with self.assertRaises(RuntimeError):
            self.harness.cleanup()
        self.assertFalse(self.harness.private.exists())

    def test_cleanup_failure_prevents_clean_pass(self):
        """Confirm that a cleanup failure prevents CLEAN PASS."""
        self.harness.finished = True
        with self.assertRaises(RuntimeError):
            self.harness.step(
                "11-cleanup", lambda: (_ for _ in ()).throw(RuntimeError("cleanup"))
            )
        self.assertFalse(self.harness.report())

    def test_prod_audit_is_collected_after_failure_and_preserved_in_full(self):
        """Confirm full audit collection and preservation also after a failed step."""
        self.harness.prod_ready = True
        with self.assertRaises(RuntimeError):
            self.harness.step("05", lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        self.harness.guest = mock.Mock(
            side_effect=lambda *args: self.harness.write(
                "\n".join("audit-event-" + str(i) for i in range(100))
            )
        )
        self.harness.finalize()
        self.harness.guest.assert_called_once_with("PROD", "audit")
        self.assertFalse(self.harness.report())
        evidence = (self.harness.folder / "EVIDENCE.md").read_text()
        self.assertIn("audit-event-0", evidence)
        self.assertIn("audit-event-99", evidence)

    def test_failed_audit_still_cleans_secrets_and_prevents_clean_pass(self):
        """Confirm cleanup and NOT CLEAN when the audit cannot be collected."""
        self.harness.finished = True
        self.harness.prod_ready = True
        self.harness.guest = mock.Mock(side_effect=RuntimeError("audit unavailable"))
        self.harness.cleanup = mock.Mock()
        self.harness.finalize()
        self.harness.cleanup.assert_called_once()
        self.assertFalse(self.harness.report())

    def test_completed_run_with_final_audit_denials_is_not_clean(self):
        """Let denials after the last e2e fail an otherwise complete run."""
        self.harness.finished = True
        self.harness.prod_ready = True
        self.harness.cleanup = mock.Mock()

        def audit(role, action):
            """Simulate audit events and reject them only in check mode."""
            self.harness.write("type=AVC denied\n")
            if action == "audit-check":
                raise RuntimeError("FANOTIFY/AVC events recorded")

        self.harness.guest = mock.Mock(side_effect=audit)
        self.harness.finalize()
        self.harness.guest.assert_called_once_with("PROD", "audit-check")
        self.assertFalse(self.harness.report())
        self.assertIn(
            "type=AVC denied", (self.harness.folder / "EVIDENCE.md").read_text()
        )
        self.harness.cleanup.assert_called_once()

    def test_unknown_stderr_warning_is_named_and_redacted_in_report(self):
        """Record unknown warnings too, without exposing known secrets."""
        self.harness.redactions.append("synthetic-secret")
        self.harness.step(
            "warning",
            lambda: self.harness.log_streams(
                "", "Warning: synthetic-secret uses an old key\n"
            ),
        )
        self.harness.report()
        report = (self.harness.folder / "REPORT.md").read_text()
        self.assertIn("stderr warning: Warning: [REDACTED] uses an old key", report)
        self.assertNotIn("synthetic-secret", report)

    def boot_service_fixture(self, states):
        """Run the real wait loop with a stubbed systemctl and no delay."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        function = shell_code(remote, function="wait_boot_service")
        state_file, calls = self.root / "boot-states", self.root / "boot-calls"
        state_file.write_text("\n".join(states) + "\n")
        calls.write_text("")
        stubs = r"""
# Get the next systemd state and log every command.
user_service() {
    echo "$*" >> "$calls"
    if [[ $1 == status ]]; then echo 'service diagnostics'; return 3; fi
    value=$(head -1 "$state_file")
    if [[ $(wc -l < "$state_file") -gt 1 ]]; then tail -n +2 "$state_file" > "$state_file.next"; mv "$state_file.next" "$state_file"; fi
    echo "$value"
    [[ $value == active ]] && return 0
    return 3
}
# Avoid real waiting in the test.
sleep() { :; }
"""
        script = (
            "set -eu\nstate_file="
            + shlex.quote(str(state_file))
            + "\ncalls="
            + shlex.quote(str(calls))
            + "\n"
            + stubs
            + function
            + "\nwait_boot_service\n"
        )
        result = subprocess.run(
            ["bash", "-se"], input=script, capture_output=True, text=True, check=False
        )
        commands = calls.read_text().splitlines()
        self.assertTrue(all(c.startswith(("is-active ", "status ")) for c in commands))
        return result, commands

    def test_boot_service_waits_until_active_without_starting(self):
        """Accept activation that ends active without start or restart calls."""
        result, commands = self.boot_service_fixture(
            ["activating", "activating", "active"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(commands, ["is-active myproduct.service"] * 3)

    def test_boot_service_failed_stops_immediately_with_status(self):
        """Stop as soon as systemd reports failed and include status diagnostics."""
        result, commands = self.boot_service_fixture(["failed", "active"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            commands,
            ["is-active myproduct.service", "status --no-pager myproduct.service"],
        )
        self.assertIn("service diagnostics", result.stdout)

    def test_boot_service_timeout_fails_without_starting(self):
        """Reject a service that never becomes active within the wait limit."""
        result, commands = self.boot_service_fixture(["activating"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(commands.count("is-active myproduct.service"), 120)
        self.assertIn("within 240s", result.stdout)

    def test_audit_uses_separate_streams_and_locale_date(self):
        """Confirm the date format, separate audit streams and strict error handling."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        code = shell_code(remote, heredoc="AUDIT")
        self.assertIn(
            'LC_ALL=C date -d "$run_started"',
            remote.replace("@$run_started", "$run_started"),
        )
        cases = (
            (1, "", "<no matches>\n", "check", True),
            (0, "type=AVC denied\n", "warning\n", "check", False),
            (0, "type=FANOTIFY resp=deny\n", "", "check", False),
            (0, "type=AVC denied\n", "warning\n", "collect", True),
            (1, "", "Invalid start date\n", "check", False),
            (1, "<no matches>\n", "", "check", False),
            (0, "", "", "collect", False),
        )
        for status, stdout, stderr, mode, success in cases:
            with self.subTest(status=status, mode=mode, stdout=stdout):
                out, err = io.StringIO(), io.StringIO()
                result = subprocess.CompletedProcess([], status, stdout, stderr)
                with (
                    mock.patch.object(
                        subprocess, "run", return_value=result
                    ) as command,
                    mock.patch("sys.argv", ["audit", "10/12/26", "18:18:52", mode]),
                    contextlib.redirect_stdout(out),
                    contextlib.redirect_stderr(err),
                ):
                    if success:
                        exec(code, {"__name__": "audit_test"})  # noqa: S102 - test the repository-owned audit heredoc
                    else:
                        with self.assertRaises(SystemExit):
                            exec(code, {"__name__": "audit_test"})  # noqa: S102 - test the repository-owned audit heredoc
                self.assertEqual(out.getvalue().startswith(stdout), True)
                self.assertEqual(err.getvalue(), stderr)
                self.assertEqual(command.call_args.kwargs["stderr"], subprocess.PIPE)
                self.assertIn("FANOTIFY,AVC,USER_AVC", command.call_args.args[0])
                self.assertEqual(
                    command.call_args.args[0][-3:], ["10/12/26", "18:18:52", "-i"]
                )

    def state_fixture(self, digest="a"):
        """Build synthetic hash data without secrets for 24 persistent files."""
        names = (
            "config.yaml",
            "PKI/private/ca.crt",
            "PKI/private/ca.key",
            "PKI/private/ca.srl",
            "PKI/private/identity.csr",
            "PKI/private/identity.ext",
            "PKI/private/todo-client.csr",
            "PKI/private/todo-client.ext",
            "PKI/private/web.csr",
            "PKI/private/web.ext",
            "files/todo-signing.tar",
            "generated-certificates/client/todo-client.crt",
            "generated-certificates/identity-db/password",
            "generated-certificates/identity/identity.crt",
            "generated-certificates/identity/identity.key",
            "generated-certificates/todo-db/password",
            "generated-certificates/todo/ca.crt",
            "generated-certificates/todo/session-key",
            "generated-certificates/todo/todo-client.crt",
            "generated-certificates/todo/todo-client.key",
            "generated-certificates/users/alice-password",
            "generated-certificates/users/bob-password",
            "generated-certificates/web/web.crt",
            "generated-certificates/web/web.key",
        )
        return {
            "ca_der_sha256": digest * 64,
            "files_sha256": dict.fromkeys(names, digest * 64),
        }

    def test_json_stdout_with_ssh_warning_passes_without_hash_disclosure(self):
        """Confirm valid JSON with an SSH warning and only file status in the evidence."""
        state = self.state_fixture()
        warning = "** WARNING: connection is not using a post-quantum key exchange algorithm.\n"
        self.harness.guest = lambda *args, **kwargs: self.harness.command(
            ["ssh"], log_stdout=kwargs["log_stdout"]
        )
        result = subprocess.CompletedProcess([], 0, json.dumps(state), warning)
        with mock.patch.object(
            runner.subprocess, "run", return_value=result
        ) as command:
            self.harness.step("before", lambda: self.harness.persistent_state("before"))
            self.harness.step("after", lambda: self.harness.persistent_state("after"))
        self.assertTrue(command.call_args.kwargs["capture_output"])
        self.harness.report()
        for name in ("logs/before.log", "logs/after.log", "REPORT.md", "EVIDENCE.md"):
            data = (self.harness.folder / name).read_text()
            self.assertNotIn("a" * 64, data)
            self.assertIn("post-quantum key exchange", data)
            for filename in state["files_sha256"]:
                self.assertIn(
                    filename + (": same" if name.startswith("logs/") else ""), data
                )

    def test_invalid_or_empty_json_and_nonzero_valid_json_fail(self):
        """Reject invalid stdout and a failing status even when the JSON is valid."""
        for status, output in (
            (0, ""),
            (0, "not json"),
            (0, "{}"),
            (7, json.dumps(self.state_fixture())),
        ):
            with self.subTest(status=status, output=output):
                self.harness.guest = lambda *args, **kwargs: self.harness.command(
                    ["ssh"], log_stdout=False
                )
                result = subprocess.CompletedProcess(
                    [], status, output, "SSH warning\n"
                )
                log = io.StringIO()
                self.harness.log = log
                with (
                    mock.patch.object(runner.subprocess, "run", return_value=result),
                    self.assertRaises(RuntimeError),
                ):
                    self.harness.persistent_state("before")
                self.assertIn("[stderr]\nSSH warning", log.getvalue())
                self.harness.log = None

    def test_zero_exit_error_on_stderr_is_still_failure(self):
        """Keep the Podman error check also when errors go to stderr."""
        result = subprocess.CompletedProcess([], 0, "", "Error: failure\n")
        with (
            mock.patch.object(runner.subprocess, "run", return_value=result),
            self.assertRaises(RuntimeError),
        ):
            self.harness.command(["podman"])

    def isolation_script(
        self,
        status,
        diagnostic="Error: dial tcp: lookup registry-1.docker.io: no such host",
    ):
        """Build the isolation step with local stubs for network, sudo and tools."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        function = shell_code(remote, function="offline")
        stubs = """
# Simulate sudo and Podman with the chosen pull status, without privileges.
sudo() {
    if [[ $* == '-n podman pull '* ]]; then
        echo 'pull stdout'
        echo "$diagnostic" >&2
        return "$pull_status"
    fi
}
# Simulate a blocked HTTPS connection without network.
curl() { echo 'curl: DNS blocked' >&2; return 6; }
# Simulate the DNS probe without any lookup.
python3() { echo 'PASS: public DNS lookup failed'; }
# Run the stubbed command without a real timeout.
timeout() { shift; "$@"; }
echo '** WARNING: connection is not using a post-quantum key exchange algorithm.' >&2
"""
        return (
            "set -euo pipefail\npull_status="
            + str(status)
            + "\ndiagnostic="
            + shlex.quote(diagnostic)
            + "\n"
            + stubs
            + function
            + "\noffline\n"
        )

    def test_isolation_expected_pull_failures_preserve_separate_stderr(self):
        """Accept blocked pull probes and keep the SSH warning and diagnostics on stderr."""
        for status in (125, 124):
            with self.subTest(status=status):
                name = "isolation-" + str(status)
                self.harness.step(
                    name,
                    lambda code=status: self.harness.command(
                        ["bash", "-se"], self.isolation_script(code)
                    ),
                )
                log = (self.harness.folder / ("logs/" + name + ".log")).read_text()
                stdout, stderr = log.rsplit("[stdout]\n", 1)[1].split("[stderr]\n", 1)
                self.assertIn(
                    "PASS: public pull failed (exit " + str(status) + ")", stdout
                )
                self.assertNotIn("Error: dial tcp", stdout)
                self.assertIn("pull stdout", stdout)
                self.assertNotIn("pull stdout", stderr)
                self.assertIn(
                    "pull-probe: Error: dial tcp: lookup registry-1.docker.io: no such host",
                    stderr,
                )
                self.assertIn(
                    "** WARNING: connection is not using a post-quantum", stderr
                )

    def test_isolation_permission_failure_is_not_network_evidence(self):
        """Reject Podman exit 125 when the error is about permissions rather than network."""
        with self.assertRaisesRegex(RuntimeError, "Command exited 1"):
            self.harness.command(
                ["bash", "-se"],
                self.isolation_script(125, "Error: storage: permission denied"),
            )

    def test_isolation_successful_pull_is_failure(self):
        """Reject the isolation step when a public image can be pulled."""
        with self.assertRaisesRegex(RuntimeError, "Command exited 1"):
            self.harness.command(["bash", "-se"], self.isolation_script(0))

    def test_isolation_unexpected_pull_status_is_failure(self):
        """Reject unexpected pull statuses even when stderr has the probe prefix."""
        for status in (1, 126, 127):
            with (
                self.subTest(status=status),
                self.assertRaisesRegex(RuntimeError, "Command exited 1"),
            ):
                self.harness.command(["bash", "-se"], self.isolation_script(status))

    def test_empty_resource_stdout_does_not_hide_failed_command(self):
        """Reject a failing resource command before an empty stdout can be accepted."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        block = re.sub(
            r"^\s*facts\s*$", "", shell_code(remote, action="clean"), flags=re.MULTILINE
        )
        stubs = "podman() { echo 'resource warning' >&2; return 7; }\n"
        result = subprocess.run(
            ["bash", "-eu", "-c", stubs + block],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, "")
        self.assertIn("resource warning", result.stderr)

    def test_boot_id_rejects_empty_or_mixed_stdout(self):
        """Accept only one valid boot ID from stdout."""
        boot = "12345678-1234-1234-1234-123456789abc"
        self.assertEqual(self.harness.boot_id(boot + "\n"), boot)
        for output in ("", "warning\n" + boot):
            with self.assertRaises(RuntimeError):
                self.harness.boot_id(output)

    def trust_helper(self):
        """Get the wait function shared by the VM procedure and README."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        return shell_code(remote, function="wait_trust")

    def run_trust_wait(self, outputs, exit_code=0):
        """Run the read-only trust wait against sequential database fixtures without delay."""
        fixtures = self.root / "trust-fixtures"
        fixtures.mkdir(exist_ok=True)
        for index, output in enumerate(outputs, 1):
            (fixtures / str(index)).write_text(output)
        counter = fixtures / "counter"
        counter.write_text("0")
        script = r"""
# Read the next database fixture and keep warnings on stderr.
sudo() {
    printf 'Warning: fixture warning\n' >&2
    count=$(cat "$fixtures/counter")
    count=$((count + 1))
    printf '%s' "$count" > "$fixtures/counter"
    if [[ $count -gt $last ]]; then count=$last; fi
    cat "$fixtures/$count"
    return "$fixture_status"
}
# Avoid real waiting or external commands in the regression test.
sleep() { :; }
# Run the stubbed read with the same arguments as the production call.
timeout() { shift; "$@"; }
wait_trust /new/deploy.py /old/deploy.py
"""
        prefix = "set -eu\nfixtures=" + shlex.quote(str(fixtures))
        prefix += (
            "\nlast=" + str(len(outputs)) + "\nfixture_status=" + str(exit_code) + "\n"
        )
        result = subprocess.run(
            ["bash", "-se"],
            input=prefix + self.trust_helper() + script,
            capture_output=True,
            text=True,
            check=False,
        )
        return result, int(counter.read_text())

    def test_trust_wait_accepts_delayed_update_without_mutations(self):
        """Wait for the new entry and the removed old one without writing hash values."""
        digest = "a" * 64
        new = "file /new/deploy.py 123 " + digest + "\n"
        old = "file /old/deploy.py 123 " + digest + "\n"
        result, calls = self.run_trust_wait([old, old + new, new])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, 3)
        self.assertIn("Warning: fixture warning", result.stderr)
        self.assertNotIn(digest, result.stdout + result.stderr)
        self.assertNotIn("--update", self.trust_helper())
        self.assertNotIn("--file", self.trust_helper())

    def test_trust_wait_preserves_paths_with_spaces(self):
        """Accept real RPM paths with spaces and compare the whole release path."""
        digest = "d" * 64
        rows = [
            "rpmdb /usr/lib/python3.9/site-packages/setuptools/command/launcher manifest.xml 123 "
            + digest,
            "rpmdb /usr/lib/python3.9/site-packages/setuptools/script (dev).tmpl 123 "
            + digest,
            "file /new/deploy.py backup 123 " + digest,
        ]
        pending = "\n".join(rows) + "\n"
        result, calls = self.run_trust_wait(
            [pending, pending + "file /new/deploy.py 123 " + digest + "\n"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, 2)
        self.assertNotIn(digest, result.stdout + result.stderr)

    def test_trust_wait_times_out_with_stale_database(self):
        """Reject a stale database after the limit even if the reads succeed."""
        result, calls = self.run_trust_wait(
            ["file /old/deploy.py 123 " + "b" * 64 + "\n"]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, 30)
        self.assertIn("30 checks", result.stderr)

    def test_trust_wait_rejects_failed_empty_or_invalid_read(self):
        """Stop at once on command errors or unusable stdout, also with warnings."""
        valid = "file /new/deploy.py 123 " + "c" * 64 + "\n"
        for output, status in ((valid, 1), ("", 0), ("invalid\n", 0)):
            with self.subTest(output=output[:10], status=status):
                result, calls = self.run_trust_wait([output], status)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, 1)
                self.assertIn("Warning: fixture warning", result.stderr)

    def test_readme_uses_same_trust_wait_as_remote(self):
        """Confirm that the documented function performs the same read-only check."""
        readme = (
            Path(__file__).resolve().parent.parent.joinpath("README.md").read_text()
        )
        self.assertIn(self.trust_helper().strip(), readme)

    def trust_procedure(self, source, install_status=0, health_status=0):
        """Run the README or VM procedure with stubbed trust and install calls."""
        if source == "remote":
            remote = Path(__file__).with_name("remote.sh").read_text()
            code = shell_code(remote, action="upgrade")
        else:
            readme = (
                Path(__file__).resolve().parent.parent.joinpath("README.md").read_text()
            )
            blocks = re.findall(r"```sh\n(.*?)```", readme, re.DOTALL)
            code = "\n".join(
                block
                for block in blocks
                if "--file delete" in block and "deploy.py install" in block
            )
        (self.root / "version").write_text("0.1.1\n")
        (self.root / "myproduct-0.1.1-offline.tar.gz").touch()
        calls = self.root / "trust-calls"
        calls.write_text("")
        stubs = r"""
# Record trust actions and simulate install failures.
sudo() {
    case "$*" in
        *'--file add'*) echo add >> "$calls";;
        *'--file delete'*) echo delete >> "$calls";;
        *'--update'*) echo update >> "$calls";;
        *'deploy.py install'*) echo install >> "$calls"; return "$install_status";;
        *'--dump-db'*) printf "file %s 123 %064d\n" "$product/deploy.py" 0;;
        *'systemctl --user'*) healthy;;
    esac
}
# Run only stubbed commands under timeout in the test.
timeout() { shift; "$@"; }
# Simulate a passing checksum without reading a real archive.
sha256sum() { :; }
# Simulate the health check after install.
healthy() { echo health >> "$calls"; return "$health_status"; }
"""
        prefix = (
            "set -eu\nbase="
            + shlex.quote(str(self.root))
            + "\nproduct=/var/lib/myproduct/releases/myproduct-0.1.1\nrelease=$product\nbundle=app1\nold_version=0.1.0\nas_product() { :; }\ncalls="
            + shlex.quote(str(calls))
            + "\ninstall_status="
            + str(install_status)
            + "\nhealth_status="
            + str(health_status)
            + "\n"
        )
        result = subprocess.run(
            ["bash", "-se"],
            input=prefix + stubs + self.trust_helper() + code,
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result, calls.read_text().splitlines()

    def test_upgrade_trust_removed_only_after_install_and_health(self):
        """Confirm the same safe trust order in README and the VM procedure."""
        for source in ("remote", "README"):
            with self.subTest(source=source):
                result, calls = self.trust_procedure(source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    calls, ["add", "update", "install", "health", "delete", "update"]
                )

    def test_failed_upgrade_keeps_old_trust(self):
        """Keep the old trust when install or the health check fails."""
        for source in ("remote", "README"):
            for install, health in ((1, 0), (0, 1)):
                with self.subTest(source=source, install=install, health=health):
                    result, calls = self.trust_procedure(source, install, health)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("delete", calls)

    def test_upgrade_preserves_credentials_and_orders_checks(self):
        """Confirm the upgrade order and reuse of the original passwords."""
        self.harness.meta["version"] = "0.1.0"
        self.harness.persistent_before = self.state_fixture()
        self.harness.guest = mock.Mock(return_value=json.dumps(self.state_fixture()))
        self.harness.transfer = mock.Mock()
        self.harness.credentials = mock.Mock()
        self.harness.upgrade()
        self.harness.credentials.assert_not_called()
        self.harness.transfer.assert_called_once_with("0.1.1")
        self.assertEqual(
            self.harness.guest.call_args_list,
            [
                mock.call("DEV", "upgrade-bundle", "0.1.1"),
                mock.call("PROD", "upgrade", old_version="0.1.0"),
                mock.call("PROD", "check"),
                mock.call("PROD", "persistent-state", log_stdout=False),
                mock.call("DEV", "prod-e2e"),
                mock.call("DEV", "markers-check"),
            ],
        )

    def test_upgrade_hash_change_stops_before_e2e(self):
        """Confirm a stop before e2e when the upgrade changes persistent state."""
        self.harness.meta["version"] = "0.1.0"
        self.harness.persistent_before = self.state_fixture()
        self.harness.guest = mock.Mock(return_value=json.dumps(self.state_fixture("b")))
        self.harness.transfer = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "10-persistent-after"):
            self.harness.upgrade()
        self.assertNotIn(
            mock.call("DEV", "prod-e2e"), self.harness.guest.call_args_list
        )
        self.assertFalse(self.harness.report())

    def test_failed_upgrade_install_stops_before_other_checks(self):
        """Confirm that a failed upgrade stops later checks."""
        self.harness.meta["version"] = "0.1.0"
        self.harness.transfer = mock.Mock()
        self.harness.guest = mock.Mock(
            side_effect=["built", RuntimeError("install failed")]
        )
        with self.assertRaisesRegex(RuntimeError, "10-install-upgrade"):
            self.harness.upgrade()
        self.assertEqual(self.harness.guest.call_count, 2)
        self.assertFalse(self.harness.finished)

    def test_full_run_rechecks_after_reboot_and_upgrade(self):
        """Confirm that prod checks are repeated after reboot and upgrade."""
        self.harness.meta["version"] = "0.1.0"
        self.harness.readiness = mock.Mock()
        self.harness.reset = mock.Mock()
        self.harness.source = mock.Mock()
        self.harness.transfer = mock.Mock()
        self.harness.registry_transfer = mock.Mock()
        self.harness.credentials = mock.Mock()
        self.harness.reboot = mock.Mock()
        self.harness.guest = mock.Mock(return_value=json.dumps(self.state_fixture()))
        self.harness.execute()
        self.harness.reboot.assert_called_once()
        self.assertTrue(self.harness.finished)
        records = [
            json.loads(line)["step"]
            for line in (self.harness.folder / "record.jsonl").read_text().splitlines()
        ]
        expected = [
            "09-crash",
            "09-launch-audit-crash",
            "09-markers-crash",
            "09-hang",
            "09-launch-audit-hang",
            "09-markers-hang",
            "09-reboot",
            "09-wait-boot-service",
            "09-offline-after-reboot",
            "09-check-after-reboot",
            "09-e2e-after-reboot",
            "09-markers-after-reboot",
            "10-build-upgrade",
            "10-transfer-upgrade",
            "10-install-upgrade",
            "10-check-upgrade",
            "10-persistent-after",
            "10-e2e-upgrade",
            "10-markers-upgrade",
        ]
        self.assertEqual(records[records.index("09-crash") :], expected)
        for step in (
            "03-build-images",
            "03-pull-images",
            "03-registry-test",
            "05-registry-transfer",
            "07-registry-offline",
        ):
            self.assertIn(step, records)
        self.assertLess(
            records.index("03-registry-test"), records.index("03-examples-setup")
        )
        self.assertLess(
            records.index("06-install"), records.index("07-registry-offline")
        )
        self.assertLess(records.index("07-registry-offline"), records.index("07-check"))
        self.assertEqual(
            self.harness.guest.call_args_list.count(mock.call("PROD", "check")), 3
        )

    def test_registry_transfer_moves_archive_and_checksum_without_credentials(self):
        """Keep the registry fixture transfer separate from the product version and credentials."""
        self.harness.cfg = {
            "SSH_USER": "lab",
            "DEV_IP": "192.0.2.1",
            "PROD_IP": "192.0.2.2",
        }
        self.harness.ssh = mock.Mock()

        def copy(arguments):
            """Simulate scp downloads to the requested controller artifact path."""
            if isinstance(arguments[-1], Path):
                arguments[-1].write_bytes(b"public fixture bundle")

        self.harness.command = mock.Mock(side_effect=copy)
        self.harness.registry_transfer()
        self.assertEqual(self.harness.command.call_count, 4)
        self.assertIn("registry_bundle_sha256", self.harness.meta)
        self.assertNotIn("version", self.harness.meta)
        self.assertEqual(
            (self.harness.folder / "registry").stat().st_mode & 0o777, 0o700
        )

    def test_registry_offline_probe_checks_exact_name_and_never_pulls(self):
        """Require offline load/name validation and a temporary run with pull=never."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        block = shell_code(remote, action="registry-offline")
        self.assertIn("as_product podman load -i /dev/stdin", block)
        self.assertIn('as_product podman image exists "$image"', block)
        self.assertIn('podman run --rm --pull=never --network=none "$image"', block)
        self.assertIn("audit_events check", block)
        self.assertNotIn("podman pull", block)

    def test_launcher_denial_stops_before_markers_hang_or_reboot(self):
        """Stop immediately at the first pre-reboot launcher audit failure."""
        self.harness.meta["version"] = "0.1.0"
        for name in (
            "readiness",
            "reset",
            "source",
            "transfer",
            "registry_transfer",
            "credentials",
            "reboot",
        ):
            setattr(self.harness, name, mock.Mock())

        def guest(role, action, **kwargs):
            """Fail only the audit immediately after the successful crash check."""
            if action == "launch-audit-check":
                raise RuntimeError("FANOTIFY denial")
            return json.dumps(self.state_fixture())

        self.harness.guest = mock.Mock(side_effect=guest)
        with self.assertRaisesRegex(RuntimeError, "09-launch-audit-crash"):
            self.harness.execute()
        self.harness.reboot.assert_not_called()
        self.assertNotIn(mock.call("PROD", "hang"), self.harness.guest.call_args_list)
        self.assertFalse(self.harness.report())

    def test_persistent_snapshot_hashes_config_pki_and_files_without_content(self):
        """Confirm file hash coverage without printing secret file content."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        code = shell_code(remote, heredoc="HASHES")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = b"synthetic-secret-that-must-not-be-printed"
            for name in self.state_fixture()["files_sha256"]:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(private)
            (root / "PKI/private/ca.crt").write_text(
                "-----BEGIN CERTIFICATE-----\nAQID\n-----END CERTIFICATE-----\n"
            )
            result = subprocess.run(
                ["python3", "-c", code],
                env=dict(os.environ, HOME=temporary),
                check=True,
                capture_output=True,
                text=True,
            )
            state = json.loads(result.stdout)
            self.assertEqual(len(state["files_sha256"]), 24)
            self.assertIn("files/todo-signing.tar", state["files_sha256"])
            self.assertNotIn(private.decode(), result.stdout)

    def test_credentials_stream_to_private_files_without_logging_content(self):
        """Confirm direct transfer of passwords to private files without logging content."""
        self.harness.private = self.root / "private"
        self.harness.private.mkdir(mode=0o700)
        self.harness.meta["version"] = "0.1.0"
        self.harness.cfg = {
            "SSH_USER": "operator",
            "PROD_IP": "192.0.2.2",
            "DEV_IP": "192.0.2.1",
        }
        self.harness.ssh = mock.Mock(side_effect=["/run/user/1000", ""])
        self.harness.command = mock.Mock()

        def transfer(args, stdout, **kwargs):
            """Simulate the SSH transfer and check that it uses private file output."""
            self.assertIn(
                "sudo -n -H -u myproduct cat /var/lib/myproduct/",
                args[-1],
            )
            stdout.write(b"synthetic-private-content")
            return subprocess.CompletedProcess(
                args, 0, stderr=b"SSH transfer warning\n"
            )

        with mock.patch.object(runner.subprocess, "run", side_effect=transfer):
            self.harness.step("credentials", self.harness.credentials)
        self.assertNotIn(
            "synthetic-private-content",
            (self.harness.folder / "logs/credentials.log").read_text(),
        )
        self.assertIn(
            "[stderr]\nSSH transfer warning",
            (self.harness.folder / "logs/credentials.log").read_text(),
        )
        self.assertEqual(
            (self.harness.private / "alice-password").read_bytes(),
            b"synthetic-private-content",
        )

    def test_product_commands_enter_service_home_and_set_runtime(self):
        """Confirm the service user's cwd, HOME and runtime when run through sudo."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        function = shell_code(remote, function="as_product")
        home = self.root / "service home"
        home.mkdir(mode=0o700)
        operator = self.root / "operator-private"
        operator.mkdir(mode=0o700)
        probe = "import json,os,sys; print(json.dumps([os.getcwd(), os.environ['HOME'], os.environ['XDG_RUNTIME_DIR'], sys.argv[1:]]))"
        # Simulate sudo changing identity/HOME while retaining the caller's cwd.
        stub = 'sudo() { shift 4; "$@"; }\n'
        script = (
            stub
            + function
            + "as_product python3 -c "
            + runner.shlex.quote(probe)
            + " 'argument with spaces'"
        )
        result = subprocess.run(
            ["bash", "-eu", "-c", script],
            cwd=operator,
            env=dict(
                os.environ, HOME=str(home), XDG_RUNTIME_DIR="/wrong/operator/runtime"
            ),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [
                str(home),
                str(home),
                "/run/user/" + str(os.getuid()),
                ["argument with spaces"],
            ],
        )

    def test_missing_service_home_stops_before_command(self):
        """Confirm that a missing service home stops the command."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        function = shell_code(remote, function="as_product")
        script = (
            'sudo() { shift 4; "$@"; }\n' + function + "as_product echo SHOULD_NOT_RUN"
        )
        result = subprocess.run(
            ["bash", "-eu", "-c", script],
            cwd=self.root,
            env=dict(os.environ, HOME=str(self.root / "missing-home")),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("SHOULD_NOT_RUN", result.stdout)

    def test_documented_install_enters_release_from_operator_directory(self):
        """Confirm that the README command switches from the operator's cwd to the release."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        command = next(
            line.strip()
            for line in remote.splitlines()
            if "exec python3 deploy.py install" in line
        )
        readme = (Path(__file__).resolve().parent.parent / "README.md").read_text()
        self.assertIn(
            command.replace("sudo -n ", "sudo ").replace('"$product"', '"$release"'),
            readme,
        )
        release = self.root / "service home/releases/myproduct-test"
        release.mkdir(parents=True)
        (release / "deploy.py").write_text(
            "import os,sys; print(os.getcwd()); print(sys.argv[1])\n"
        )
        operator = self.root / "operator-private"
        operator.mkdir(mode=0o700)
        script = 'sudo() { shift 4; "$@"; }\nproduct=$1\n' + command
        result = subprocess.run(
            ["bash", "-eu", "-c", script, "bash", str(release)],
            cwd=operator,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [str(release), "install"])

    def test_guest_security_profile_checks(self):
        """Confirm acceptance and rejection of the VM roles' security profiles."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        function = shell_code(remote, function="profile")
        stubs = """
getenforce() { echo "$selinux_value"; }
systemctl() {
    if [[ $2 == fapolicyd ]]; then
        if [[ $4 == ActiveState ]]; then echo "$policy_value"; else echo "$enabled_value"; fi
    else echo "$firewall_value"; fi
}
"""
        for role, policy, enabled, selinux, firewall, expected in (
            ("DEV", "inactive", "disabled", "Enforcing", "active", 0),
            ("DEV", "active", "enabled", "Enforcing", "active", 1),
            ("DEV", "inactive", "enabled", "Enforcing", "active", 1),
            ("PROD", "active", "enabled", "Enforcing", "active", 0),
            ("PROD", "inactive", "disabled", "Enforcing", "active", 1),
            ("PROD", "active", "enabled", "Permissive", "active", 1),
            ("DEV", "inactive", "disabled", "Enforcing", "inactive", 1),
        ):
            with self.subTest(
                role=role, policy=policy, selinux=selinux, firewall=firewall
            ):
                settings = (
                    f"role={role}; policy_value={policy}; enabled_value={enabled}; "
                    f"selinux_value={selinux}; firewall_value={firewall}\n"
                )
                result = subprocess.run(
                    ["bash", "-e", "-c", settings + stubs + function + "profile"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.returncode, expected, result.stdout + result.stderr
                )


class HealthTests(unittest.TestCase):
    """Test manifest-driven health and a strict inventory check without Podman."""

    def setUp(self):
        """Load the health check and replace only process calls and the clock."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        self.namespace: dict = {"__name__": "fixture"}
        exec(  # noqa: S102 - repository-owned heredoc under test
            compile(shell_code(remote, heredoc="HEALTHY"), "HEALTHY", "exec"),
            self.namespace,
        )
        self.now = 0
        self.namespace["time"] = types.SimpleNamespace(
            monotonic=lambda: self.now, sleep=self.advance
        )

    def advance(self, seconds):
        """Advance the test clock without real waiting."""
        self.now += seconds

    def row(self, name="pod-app", health="healthy"):
        """Build an inspect fixture with a private field that must never be logged."""
        return {
            "Name": name,
            "IsInfra": False,
            "IsService": False,
            "State": {"Status": "running", "Health": {"Status": health}},
            "Config": {"Env": ["PRIVATE=DO_NOT_LOG"]},
        }

    def run_health(self, rows, exit_code=0):
        """Run the wait loop with stubbed inventory, stdout and stderr."""
        self.namespace["expected_containers"] = lambda path: ({"pod-app"}, set())

        def run(arguments, **kwargs):
            """Return only controlled inspect data or container IDs."""
            output = json.dumps(rows) if "inspect" in arguments else "id\n"
            return subprocess.CompletedProcess(
                arguments, exit_code, output, "Warning: fixture\n"
            )

        output, errors = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(subprocess, "run", side_effect=run),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(errors),
        ):
            self.namespace["main"]()
        return output.getvalue(), errors.getvalue()

    def test_healthy_and_warning_pass_without_private_output(self):
        """Accept a correct inventory with healthy and log stderr separately."""
        output, errors = self.run_health([self.row()])
        self.assertIn("health=healthy", output)
        self.assertIn("Warning: fixture", errors)
        self.assertNotIn("DO_NOT_LOG", output + errors)

    def test_missing_extra_duplicate_and_unhealthy_fail(self):
        """Reject a wrong inventory and unhealthy at once."""
        for rows in (
            [],
            [self.row("other")],
            [self.row(), self.row("other")],
            [self.row(), self.row()],
            [self.row(health="unhealthy")],
        ):
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                self.run_health(rows)

    def test_starting_times_out(self):
        """Reject a persistent starting status after 150 seconds."""
        with self.assertRaisesRegex(RuntimeError, "150s"):
            self.run_health([self.row(health="starting")])
        self.assertEqual(self.now, 150)

    def test_command_and_parse_errors_fail_immediately(self):
        """Reject a failing status and invalid inspect fields without retry."""
        with self.assertRaises(RuntimeError):
            self.run_health([self.row()], exit_code=7)
        with self.assertRaises(KeyError):
            self.run_health([{}])
        self.assertEqual(self.now, 0)

    def test_expected_names_follow_manifest_including_new_app(self):
        """Read names from the real manifests and include a new app automatically."""
        repo = Path(__file__).resolve().parent.parent
        text = "\n---\n".join(
            path.read_text()
            for path in sorted((repo / "components").glob("*/manifests/*.yaml"))
        )
        text += "\n---\nkind: Pod\nmetadata: {name: extra}\nspec:\n  containers: [{name: app}]\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "installed.yaml"
            path.write_text(text)
            names, init = self.namespace["expected_containers"](path)
        self.assertEqual(len(names), 11)
        self.assertIn("extra-app", names)
        self.assertFalse(init)


class LauncherDiagnosticsTests(unittest.TestCase):
    """Test read-only launcher evidence with separate streams and safe projections."""

    def setUp(self):
        """Load the diagnostic heredoc without executing its main entry point."""
        self.remote = Path(__file__).with_name("remote.sh").read_text()
        self.namespace = {}
        self.namespace["__name__"] = "launcher_test"
        exec(shell_code(self.remote, heredoc="LAUNCH_DIAGNOSTICS"), self.namespace)  # noqa: S102 - test the repository-owned diagnostic heredoc
        self.unit = "a" * 64 + "-123.service"

    def properties(self, arguments=""):
        """Provide the exact systemd property set with controlled ExecStart content."""
        values = {key: "" for key in self.namespace["PROPERTIES"]}
        values.update(
            LoadState="loaded",
            ActiveState="active",
            SubState="exited",
            Result="success",
            MainPID="0",
            ExecMainPID="8805",
            ExecMainCode="1",
            ExecMainStatus="0",
            ExecStart=arguments,
        )
        return "\n".join(key + "=" + value for key, value in values.items())

    def test_journal_projection_preserves_exec_failure_without_secret_messages(self):
        """Keep failure, PID and unit identifiers without arbitrary message content."""
        rows = [
            {"MESSAGE": "private-secret-value", "_PID": "1"},
            {
                "MESSAGE": "Failed at step EXEC spawning /usr/bin/podman: Operation not permitted private-secret-value",
                "USER_UNIT": self.unit,
                "_PID": "8805",
                "__REALTIME_TIMESTAMP": "123456",
            },
        ]
        events, units = self.namespace["journal_events"](
            "\n".join(map(json.dumps, rows))
        )
        self.assertEqual(units, {self.unit})
        self.assertEqual(events[0]["_PID"], "8805")
        self.assertIn("Operation not permitted", json.dumps(events))
        self.assertNotIn("private-secret-value", json.dumps(events))

    def test_invalid_journal_json_fails_without_echoing_data(self):
        """Reject malformed or missing journal fields without displaying raw output."""
        for output in ("private-secret-value", "[]", '{"MESSAGE": 3}'):
            with (
                self.subTest(output=output),
                self.assertRaisesRegex(RuntimeError, "Invalid journal"),
            ):
                self.namespace["journal_events"](output)

    def test_unit_properties_log_only_the_expected_healthcheck_arguments(self):
        """Show the canonical healthcheck command and withhold unexpected arguments."""
        expected = "/usr/bin/podman healthcheck run " + "a" * 64
        safe = "{ path=/usr/bin/podman ; argv[]=" + expected + " ; ignore_errors=no ; }"
        result = self.namespace["unit_state"](self.unit, self.properties(safe))
        self.assertEqual(result["ExecStart"], expected)
        unsafe = safe.replace(
            " ; ignore_errors", " --password private-secret-value ; ignore_errors"
        )
        result = self.namespace["unit_state"](self.unit, self.properties(unsafe))
        self.assertIn("withheld", result["ExecStart"])
        self.assertNotIn("private-secret-value", json.dumps(result))

    def test_missing_properties_fail_without_logging_raw_data(self):
        """Reject incomplete systemd output rather than treating it as evidence."""
        with self.assertRaisesRegex(RuntimeError, "Missing systemd properties"):
            self.namespace["unit_state"](self.unit, "Result=success")

    def removed_properties(self):
        """Return the actual property shape of run-19's removed transient service."""
        return (
            "MainPID=0\nResult=success\nExecMainPID=0\nExecMainCode=0\n"
            "ExecMainStatus=0\nLoadState=not-found\nActiveState=inactive\nSubState=dead"
        )

    def test_removed_transient_unit_has_unavailable_execution_evidence(self):
        """Accept run-19's absent ExecStart without presenting default values as success."""
        result = self.namespace["unit_state"](self.unit, self.removed_properties())
        self.assertEqual(
            result,
            {
                "unit": self.unit,
                "LoadState": "not-found",
                "evidence": "unavailable: transient unit removed",
            },
        )
        self.assertNotIn("Result", result)
        self.assertNotIn("ExecMainStatus", result)
        self.assertNotIn("ExecStart", result)

    def test_loaded_unit_missing_execstart_still_fails(self):
        """Require ExecStart for a loaded service despite the historical-unit exception."""
        output = self.removed_properties().replace(
            "LoadState=not-found", "LoadState=loaded"
        )
        with self.assertRaisesRegex(RuntimeError, "Missing systemd properties"):
            self.namespace["unit_state"](self.unit, output)

    def test_removed_unit_missing_another_required_property_still_fails(self):
        """Keep strict validation of the remaining fields on removed transient services."""
        output = self.removed_properties().replace("ExecMainPID=0\n", "")
        with self.assertRaisesRegex(RuntimeError, "Missing systemd properties"):
            self.namespace["unit_state"](self.unit, output)

    def test_historical_cleanup_does_not_prevent_current_launcher_collection(self):
        """Collect current ExecStart after recording unavailable historical launcher state."""
        current = "b" * 64 + "-456.service"
        expected = "/usr/bin/podman healthcheck run " + "b" * 64
        properties = (
            "{ path=/usr/bin/podman ; argv[]=" + expected + " ; ignore_errors=no ; }"
        )
        event = json.dumps({"MESSAGE": self.unit + ": Failed with result 'exit-code'"})
        self.namespace["command"] = mock.Mock(
            side_effect=[
                "0 boot-id\n",
                event,
                current + " loaded active exited\n",
                self.removed_properties(),
                self.properties(properties),
            ]
        )
        out = io.StringIO()
        with (
            mock.patch("pwd.getpwnam", return_value=types.SimpleNamespace(pw_uid=995)),
            mock.patch("sys.argv", ["diagnostics", "123"]),
            mock.patch.object(Path, "read_text", return_value="boot-id"),
            contextlib.redirect_stdout(out),
        ):
            self.namespace["main"]()
        self.assertIn(
            '"evidence": "unavailable: transient unit removed"', out.getvalue()
        )
        self.assertIn(expected, out.getvalue())
        self.assertIn("PASS: read-only launcher diagnostics collected", out.getvalue())

    def test_command_failure_keeps_stderr_and_never_logs_raw_stdout(self):
        """Fail on a nonzero status even with valid-looking stdout and retain stderr."""
        out, err = io.StringIO(), io.StringIO()
        result = subprocess.CompletedProcess(
            [], 1, "private-secret-value", "diagnostic warning\n"
        )
        with (
            mock.patch.object(subprocess, "run", return_value=result),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            self.assertRaisesRegex(RuntimeError, "exit 1"),
        ):
            self.namespace["command"](["journalctl"])
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "diagnostic warning\n")

    def test_main_collects_journal_and_read_only_state_before_audit(self):
        """Collect safe launcher fields with no state-changing commands or environments."""
        event = json.dumps(
            {
                "MESSAGE": self.unit
                + ": Main process exited, code=exited, status=203/EXEC",
                "_PID": "8805",
            }
        )
        command = mock.Mock(
            side_effect=[
                "0 boot-id\n",
                event,
                self.unit + " loaded active exited\n",
                self.properties(),
            ]
        )
        self.namespace["command"] = command
        out = io.StringIO()
        with (
            mock.patch("pwd.getpwnam", return_value=types.SimpleNamespace(pw_uid=995)),
            mock.patch("sys.argv", ["diagnostics", "123"]),
            mock.patch.object(Path, "read_text", return_value="boot-id"),
            contextlib.redirect_stdout(out),
        ):
            self.namespace["main"]()
        self.assertIn("203/EXEC", out.getvalue())
        self.assertIn('"ExecMainPID": "8805"', out.getvalue())
        calls = [call.args[0] for call in command.call_args_list]
        self.assertIn("@123", calls[1])
        self.assertIn("_UID=995", calls[1])
        self.assertNotIn("_COMM=systemd", calls[1])
        self.assertEqual(calls[2][4], "list-units")
        self.assertEqual(calls[3][4], "show")
        self.assertNotIn("Environment", " ".join(calls[3]))

    def test_missing_service_user_skips_launcher_commands(self):
        """Allow read-only final audit collection when installation never created the user."""
        self.namespace["command"] = mock.Mock()
        with (
            mock.patch("pwd.getpwnam", side_effect=KeyError),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.namespace["main"]()
        self.namespace["command"].assert_not_called()

    def test_audit_still_runs_after_diagnostic_failure(self):
        """Preserve audit evidence and a failing result even when launch diagnostics fail."""
        block = shell_code(self.remote, action="audit|audit-check|launch-audit-check")
        script = (
            "set -euo pipefail\nrun_started=123\naction=launch-audit-check\n"
            "health_launch_diagnostics() { echo diagnostic-failed; return 7; }\n"
            "sudo() { return 0; }\n"
            "audit_events() { echo audit-mode=$1; }\n" + block
        )
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, check=False
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("audit-mode=check", result.stdout)


class DeliveredSecretTests(unittest.TestCase):
    """Compare generated bytes to the delivered environment without disclosing either."""

    def namespace(self, path):
        """Load the named secret check with a temporary source file."""
        source = Path(__file__).with_name("remote.sh").read_text()
        namespace: dict = {"__name__": "fixture"}
        exec(  # noqa: S102 - repository-owned heredoc
            compile(shell_code(source, heredoc="API_SECRET"), "API_SECRET", "exec"),
            namespace,
        )
        namespace["SECRET_FILE"] = path
        return namespace

    def test_delivered_bytes_must_match_not_just_length(self):
        """Reject a different 32-byte value and never log values or diagnostic output."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_bytes(b"a" * 32)
            namespace = self.namespace(path)
            for value, status in ((b"b" * 32, 0), (b"a" * 32, 125), (b"a" * 32, 0)):
                output, errors = io.StringIO(), io.StringIO()
                result = subprocess.CompletedProcess(
                    [], status, value, b"private-diagnostic"
                )
                with (
                    mock.patch.object(subprocess, "run", return_value=result),
                    contextlib.redirect_stdout(output),
                    contextlib.redirect_stderr(errors),
                ):
                    if status or value != path.read_bytes():
                        with self.assertRaises(RuntimeError):
                            namespace["main"]()
                    else:
                        namespace["main"]()
                        self.assertIn("PASS:", output.getvalue())
                for private in ("a" * 32, "b" * 32, "private-diagnostic"):
                    self.assertNotIn(private, output.getvalue() + errors.getvalue())


class HangTests(unittest.TestCase):
    """Test SIGSTOP and a health-driven restart with stubbed Podman and signals."""

    def setUp(self):
        """Load the hang check and use a virtual 300-second clock."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        self.namespace: dict = {"__name__": "fixture"}
        exec(  # noqa: S102 - repository-owned heredoc under test
            compile(shell_code(remote, heredoc="HANG"), "HANG", "exec"), self.namespace
        )
        self.now, self.calls = 0, []
        self.namespace["time"] = types.SimpleNamespace(
            monotonic=lambda: self.now, sleep=self.advance
        )

    def advance(self, seconds):
        """Advance the test clock without real waiting."""
        self.now += seconds

    def state(
        self,
        pid=1200,
        count=0,
        started="before",
        stopped=False,
        health="healthy",
        running=True,
    ):
        """Build a limited inspect fixture with controllable restart and health fields."""
        return {
            "RestartCount": count,
            "State": {
                "Pid": pid,
                "Running": running,
                "StartedAt": started,
                "StoppedByUser": stopped,
                "Health": {"Status": health},
            },
            "Config": {"Env": ["PRIVATE=DO_NOT_LOG"]},
        }

    def run_hang(self, after, top="HPID\n1200\n1201\n", phases=None):
        """Run the hang test with controlled states without freezing host processes."""
        pending = (
            [self.state()]
            + (phases if phases is not None else [self.state(health="unhealthy")])
            + [after]
        )

        def run(arguments, **kwargs):
            """Return top/inspect and record SIGSTOP without sending a signal."""
            self.calls.append(arguments)
            if "inspect" in arguments:
                row = pending.pop(0) if len(pending) > 1 else pending[0]
                output = json.dumps([row])
            elif "top" in arguments:
                output = top
            else:
                self.assertEqual(arguments[:4], ["sudo", "-n", "kill", "-STOP"])
                output = ""
            return subprocess.CompletedProcess(arguments, 0, output, "")

        output = io.StringIO()
        with (
            mock.patch.object(subprocess, "run", side_effect=run),
            contextlib.redirect_stdout(output),
        ):
            self.namespace["main"]()
        return output.getvalue()

    def test_valid_restart_passes_and_stops_every_process_once(self):
        """Require an observed unhealthy, a new process and healthy after one restart."""
        output = self.run_hang(self.state(pid=1300, count=1, started="after"))
        self.assertIn("PASS: unhealthy", output)
        self.assertNotIn("DO_NOT_LOG", output)
        signals = [call for call in self.calls if "-STOP" in call]
        self.assertEqual(
            signals,
            [
                ["sudo", "-n", "kill", "-STOP", "1200"],
                ["sudo", "-n", "kill", "-STOP", "1201"],
            ],
        )
        self.assertFalse(any("pause" in call or "-CONT" in call for call in self.calls))

    def test_health_stop_flag_clears_after_one_restart(self):
        """Allow the observed temporary stop flag only on the original unhealthy process."""
        phases = [
            self.state(health="unhealthy", stopped=True, running=False),
            self.state(pid=0, health="unhealthy", stopped=True, running=False),
            self.state(pid=1300, count=1, started="after", health="starting"),
        ]
        output = self.run_hang(
            self.state(pid=1300, count=1, started="after"), phases=phases
        )
        self.assertIn('"StoppedByUser": true', output)
        self.assertIn("PASS: unhealthy", output)

    def test_stop_flag_outside_original_unhealthy_stop_fails(self):
        """Reject a user-stop flag outside the original unhealthy stop phase."""
        phases = [
            self.state(stopped=True, running=False),
            self.state(health="unhealthy", stopped=True),
            self.state(pid=1300, health="unhealthy", stopped=True, running=False),
            self.state(
                started="other", health="unhealthy", stopped=True, running=False
            ),
            self.state(
                pid=1300, count=1, started="after", health="starting", stopped=True
            ),
        ]
        for phase in phases:
            with (
                self.subTest(phase=phase),
                self.assertRaisesRegex(RuntimeError, "StoppedByUser"),
            ):
                self.run_hang(
                    self.state(pid=1300, count=1, started="after"), phases=[phase]
                )

    def test_original_unhealthy_stop_without_restart_times_out(self):
        """Fail on timeout when the allowed stop phase never becomes a restart."""
        with self.assertRaisesRegex(RuntimeError, "300s"):
            self.run_hang(self.state(health="unhealthy", stopped=True, running=False))
        self.assertEqual(self.now, 300)

    def test_unchanged_count_or_pid_times_out(self):
        """Reject a restart without an increased count or a changed PID."""
        for after in (
            self.state(pid=1300, started="after"),
            self.state(count=1, started="after"),
        ):
            with (
                self.subTest(after=after),
                self.assertRaisesRegex(RuntimeError, "300s"),
            ):
                self.now = 0
                self.run_hang(after)
            self.assertEqual(self.now, 300)

    def test_multiple_restarts_and_user_stop_fail(self):
        """Reject several restarts and StoppedByUser even with healthy."""
        for after in (
            self.state(pid=1300, count=2, started="after"),
            self.state(pid=1300, count=1, started="after", stopped=True),
        ):
            with self.subTest(after=after), self.assertRaises(RuntimeError):
                self.run_hang(after)

    def test_invalid_top_fails_before_signal(self):
        """Reject empty or dangerous host PIDs before SIGSTOP."""
        for top in (
            "",
            "HPID\n1\n",
            "HPID\nbad\n",
            "HPID\n1201\n",
            "HPID\n1200\n1200\n",
        ):
            with self.subTest(top=top), self.assertRaises(RuntimeError):
                self.calls = []
                self.run_hang(self.state(), top)
            self.assertFalse(any("-STOP" in call for call in self.calls))

    def test_missing_stopped_by_user_is_not_assumed_false(self):
        """Reject an inspect projection without its explicit user-stop flag."""
        row = self.state()
        del row["State"]["StoppedByUser"]
        self.namespace["command"] = lambda arguments, row=row: json.dumps([row])
        with self.assertRaisesRegex(RuntimeError, "Invalid or empty"):
            self.namespace["inspect_container"]()

    def test_hang_action_checks_health_and_proxy_after_restart(self):
        """Require the health check and HTTPS readiness before the marker check."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        block = shell_code(remote, action="hang")
        self.assertIn("HANG\n    healthy\n    wait_backend\n", block)
        self.assertNotIn("podman kill", block)


class CrashTests(unittest.TestCase):
    """Test an unexpected process crash with stubbed inspect, signal and clock."""

    def setUp(self):
        """Load the crash step's Python code without running commands on the host."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        code = shell_code(remote, heredoc="CRASH")
        self.namespace: dict = {"__name__": "fixture"}
        exec(compile(code, "remote.sh:CRASH", "exec"), self.namespace)  # noqa: S102 - repository-owned heredoc under test
        self.now = 0
        self.namespace["time"] = types.SimpleNamespace(
            monotonic=lambda: self.now, sleep=self.advance
        )
        self.calls = []
        self.output = io.StringIO()

    def advance(self, seconds):
        """Advance the test clock without real waiting."""
        self.now += seconds

    def state(
        self,
        pid: object = 1200,
        count=0,
        started="2026-10-12 21:00:00 +0200 CEST",
        stopped=False,
    ):
        """Build inspect JSON with a start time containing spaces and a private control field."""
        return {
            "State": {
                "Pid": pid,
                "Running": True,
                "StartedAt": started,
                "StoppedByUser": stopped,
            },
            "RestartCount": count,
            "Config": {"Env": ["PRIVATE=DO_NOT_LOG"]},
        }

    def run_crash(self, states, inspect_exit=0):
        """Run the whole crash check with controlled inspect answers and signal status."""
        pending = list(states)

        def run(arguments, **kwargs):
            """Return the next inspect answer and record the signal without sending it."""
            self.calls.append(arguments)
            if "inspect" in arguments:
                row = pending.pop(0) if len(pending) > 1 else pending[0]
                output = row if isinstance(row, str) else json.dumps([row])
                return subprocess.CompletedProcess(arguments, inspect_exit, output, "")
            self.assertEqual(arguments[:4], ["sudo", "-n", "kill", "-KILL"])
            return subprocess.CompletedProcess(arguments, 0, "", "")

        with (
            mock.patch.object(subprocess, "run", side_effect=run),
            contextlib.redirect_stdout(self.output),
        ):
            self.namespace["main"]()

    def test_missing_stopped_by_user_is_not_assumed_false(self):
        """Reject missing, null or string flags instead of accepting incomplete state."""
        for value in (None, "false", "missing"):
            row = self.state()
            if value == "missing":
                del row["State"]["StoppedByUser"]
            else:
                row["State"]["StoppedByUser"] = value
            self.namespace["command"] = lambda arguments, row=row: json.dumps([row])
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(RuntimeError, "Invalid or empty"),
            ):
                self.namespace["inspect_container"]()

    def test_inspect_projects_false_stop_flag_explicitly(self):
        """Emit StoppedByUser even when native inspect JSON omits its false value."""
        for tag in ("CRASH", "HANG"):
            source = shell_code(
                Path(__file__).with_name("remote.sh").read_text(), heredoc=tag
            )
            self.assertIn("{{.State.StoppedByUser}}", source)
            self.assertNotIn('state.get("StoppedByUser", False)', source)

    def test_valid_restart_passes_without_podman_kill_or_private_output(self):
        """Require a new PID, start time and count after exactly one host SIGKILL."""
        before = self.state()
        after = self.state(pid=1300, count=1, started="2026-10-12 21:00:02 +0200 CEST")
        self.run_crash([before, after])
        self.assertEqual(
            sum(call[:4] == ["sudo", "-n", "kill", "-KILL"] for call in self.calls), 1
        )
        self.assertIn(["sudo", "-n", "kill", "-KILL", "1200"], self.calls)
        self.assertFalse(
            any("podman" in call and "kill" in call for call in self.calls)
        )
        self.assertIn("PASS: one automatic restart", self.output.getvalue())
        self.assertNotIn("DO_NOT_LOG", self.output.getvalue())
        self.assertIn("2026-10-12 21:00:02 +0200 CEST", self.output.getvalue())

    def test_invalid_or_empty_pid_fails_before_signal(self):
        """Reject a missing, empty, negative or dangerous PID before the signal is sent."""
        for pid in (None, "", 0, 1, -1, "1200", True):
            with self.subTest(pid=pid), self.assertRaisesRegex(RuntimeError, "Invalid"):
                self.run_crash([self.state(pid=pid)])
        self.assertFalse(any("-KILL" in call for call in self.calls))

    def test_empty_json_or_failed_inspect_prevents_signal(self):
        """Reject empty JSON and a failing status even if stdout otherwise has valid JSON."""
        for data, status in (("", 0), (self.state(), 7)):
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                self.run_crash([data], inspect_exit=status)
        self.assertFalse(any("-KILL" in call for call in self.calls))

    def test_unchanged_restart_count_times_out(self):
        """Reject a new process without an increased Podman restart count after 60 seconds."""
        with self.assertRaisesRegex(RuntimeError, "within 60s"):
            self.run_crash([self.state(), self.state(pid=1300, started="later")])
        self.assertEqual(self.now, 60)

    def test_same_pid_times_out(self):
        """Reject an increased count when the container's PID is not new."""
        with self.assertRaisesRegex(RuntimeError, "within 60s"):
            self.run_crash([self.state(), self.state(count=1, started="later")])
        self.assertEqual(self.now, 60)

    def test_same_start_time_times_out(self):
        """Reject a new PID and count when the start time has not changed."""
        with self.assertRaisesRegex(RuntimeError, "within 60s"):
            self.run_crash([self.state(), self.state(pid=1300, count=1)])
        self.assertEqual(self.now, 60)

    def test_stopped_by_user_fails(self):
        """Reject a user stop even if PID, start time and count look new."""
        with self.assertRaisesRegex(RuntimeError, "StoppedByUser"):
            self.run_crash(
                [
                    self.state(),
                    self.state(pid=1300, count=1, started="later", stopped=True),
                ]
            )

    def test_multiple_restarts_fail(self):
        """Reject an unstable restart with a count above baseline plus one."""
        with self.assertRaisesRegex(RuntimeError, "more than once"):
            self.run_crash(
                [self.state(), self.state(pid=1300, count=2, started="later")]
            )

    def test_crash_checks_containers_then_https_health(self):
        """Check that a successful restart is followed by container and proxy health."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        block = shell_code(remote, action="crash")
        self.assertNotIn("podman kill", block)
        self.assertIn("CRASH\n    healthy\n    wait_backend\n", block)
        function = shell_code(remote, function="wait_backend")
        script = """set -eu
state=/var/lib/myproduct
prod_host=myproduct-proxy
prod_ip=192.0.2.2
port=8443
# Simulate an HTTP answer that becomes ready on the second attempt.
as_product() { if [[ -f $ready ]]; then printf 200; else touch "$ready"; printf 503; fi; }
# Avoid real waiting in the test.
sleep() { :; }
"""
        with tempfile.TemporaryDirectory() as temporary:
            script = (
                "ready="
                + shlex.quote(temporary + "/ready")
                + "\n"
                + script
                + function
                + "\nwait_backend\n"
            )
            result = subprocess.run(
                ["bash", "-se"],
                input=script,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HTTP=503", result.stdout)
        self.assertIn("HTTP=200", result.stdout)
        self.assertIn('"https://$prod_host:$port/api/health"', function)
        self.assertIn('--cacert "$state/PKI/private/ca.crt"', function)


class SelinuxTests(unittest.TestCase):
    """Test policy lookups and narrow classification with run-6 fixtures."""

    def setUp(self):
        """Load the heredoc check with a synthetic policy and real run-6 lines."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        self.code = shell_code(remote, heredoc="LABELS")
        self.policy = types.SimpleNamespace(
            matchpathcon=mock.Mock(side_effect=self.matchpathcon)
        )
        self.namespace: dict = {"__name__": "fixture"}
        with mock.patch.dict("sys.modules", {"selinux": self.policy}):
            exec(compile(self.code, "remote.sh:LABELS", "exec"), self.namespace)  # noqa: S102 - trusted repo heredoc under test
        self.storage = self.namespace["STORAGE"]
        self.upper_layers = set()
        self.filesystem = types.SimpleNamespace(
            lstat=mock.Mock(
                return_value=types.SimpleNamespace(st_mode=stat.S_IFREG | 0o600)
            ),
            getxattr=mock.Mock(),
            walk=os.walk,
        )
        self.namespace["os"] = self.filesystem
        self.lines = (
            Path(__file__)
            .with_name("fixtures")
            .joinpath("run-6-restorecon.log")
            .read_text()
            .splitlines()
        )
        self.upper_layers = set(
            re.findall(r"/overlay/([0-9a-f]{64})/diff", "\n".join(self.lines))
        )

    def matchpathcon(self, path, mode):
        """Return synthetic policy types for the storage's known path profiles."""
        probes = {
            str(self.storage / "overlay-layers"),
            str(self.storage / "volumes/x/_data/y"),
        }
        if mode == 0:
            self.assertIn(path, probes)
        else:
            self.assertIn(
                mode,
                (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK, stat.S_IFSOCK, stat.S_IFIFO),
            )
        if "/volumes/" in path:
            kind = "container_file_t"
        elif (
            any("/" + name in path for name in ("overlay-layers", "overlay-images"))
            or path.endswith("/overlay")
            or "/overlay/" in path
        ):
            kind = "container_ro_file_t"
        else:
            kind = "container_var_lib_t"
        return 0, "system_u:object_r:" + kind + ":s0"

    def test_restorecon_stderr_is_logged_and_fails(self):
        """Reject restorecon diagnostics at exit 0 and keep them on stderr."""
        output, errors = io.StringIO(), io.StringIO()
        result = subprocess.CompletedProcess([], 0, "", "diagnostic\n")
        with (
            mock.patch.object(subprocess, "run", return_value=result),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(errors),
            self.assertRaisesRegex(RuntimeError, "diagnostics to stderr"),
        ):
            self.namespace["dryrun"](["storage"])
        self.assertNotIn("diagnostic", output.getvalue())
        self.assertEqual(errors.getvalue(), "diagnostic\n")

    def test_policy_probes_use_zero_without_lstat(self):
        """Confirm that only the explicit policy probes use mode 0."""
        self.filesystem.lstat.side_effect = AssertionError("Probes must not be stat-ed")
        with contextlib.redirect_stdout(io.StringIO()):
            self.namespace["check_equivalence"]()
        self.assertEqual(
            self.policy.matchpathcon.call_args_list,
            [
                mock.call(str(self.storage / "overlay-layers"), 0),
                mock.call(str(self.storage / "volumes/x/_data/y"), 0),
            ],
        )
        self.filesystem.getxattr.assert_not_called()

    def test_existing_file_types_are_passed_without_permission_bits(self):
        """Confirm policy lookups with the file type for directory, file, socket and FIFO."""
        path = self.storage / "overlay/sample"
        self.filesystem.getxattr.return_value = b"u:r:container_ro_file_t:s0"
        for kind in (stat.S_IFDIR, stat.S_IFREG, stat.S_IFSOCK, stat.S_IFIFO):
            with self.subTest(kind=kind), contextlib.redirect_stdout(io.StringIO()):
                self.filesystem.lstat.return_value = types.SimpleNamespace(
                    st_mode=kind | 0o755
                )
                self.namespace["check_label"](path)
                self.policy.matchpathcon.assert_called_with(str(path), kind)
                self.filesystem.getxattr.assert_called_with(
                    str(path), "security.selinux", follow_symlinks=False
                )

    def test_mtab_and_dangling_link_use_link_type_without_following_target(self):
        """Confirm S_IFLNK for mtab and a dangling link without looking up the target."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "etc").mkdir()
            mtab = root / "etc/mtab"
            mtab.symlink_to("/proc/mounts")
            dangling = root / "dangling"
            dangling.symlink_to(root / "absent-target")
            self.filesystem.lstat.side_effect = os.lstat
            self.filesystem.getxattr.return_value = b"u:r:container_ro_file_t:s0"
            self.policy.matchpathcon.side_effect = None
            self.policy.matchpathcon.return_value = (0, "u:r:container_ro_file_t:s0")
            for path in (mtab, dangling):
                with self.subTest(path=path), contextlib.redirect_stdout(io.StringIO()):
                    self.namespace["check_label"](path)
                self.policy.matchpathcon.assert_called_with(str(path), stat.S_IFLNK)
                self.filesystem.lstat.assert_called_with(str(path))
                self.filesystem.getxattr.assert_called_with(
                    str(path), "security.selinux", follow_symlinks=False
                )

    def test_lstat_failure_has_no_zero_mode_fallback(self):
        """Confirm FAIL on an lstat error before the policy lookup, without a mode-0 fallback."""
        path = self.storage / "overlay/disappeared"
        for error in (FileNotFoundError("missing"), PermissionError("denied")):
            with self.subTest(error=error):
                self.filesystem.lstat.side_effect = error
                with self.assertRaisesRegex(
                    RuntimeError, "lstat failed for"
                ) as failure:
                    self.namespace["policy_type"](path)
                self.assertIn(str(path), str(failure.exception))
                self.policy.matchpathcon.assert_not_called()

    def test_actual_run6_storage_lines_have_named_rules(self):
        """Confirm that known storage lines get a named rule."""
        storage = str(self.storage) + "/"
        lines = [line for line in self.lines if storage in line]
        self.assertEqual(len(lines), 157)
        for line in lines:
            rule = self.namespace["classify_line"](
                line, {"container_file_t"}, self.upper_layers
            )
            self.assertIn(
                rule,
                (
                    "ARTIFACT_DIRECTORY_TRANSITION",
                    "CUSTOM_VOLUME_CONTENT",
                    "CUSTOM_WRITABLE_LAYER",
                    "CUSTOM_WRITABLE_ROOTFS",
                ),
            )

    def test_writable_layer_rule_rejects_image_layer(self):
        """Accept container_file_t only on known container UpperDirs, never an image layer."""
        layer = "a" * 64
        line = (
            str(self.storage / "overlay" / layer / "diff/file")
            + " not reset as customized by admin to u:r:container_file_t:s0"
        )
        self.assertEqual(
            self.namespace["classify_line"](line, {"container_file_t"}, {layer}),
            "CUSTOM_WRITABLE_LAYER",
        )
        with self.assertRaisesRegex(RuntimeError, "Unclassified"):
            self.namespace["classify_line"](line, {"container_file_t"}, {"b" * 64})

    def test_upper_dirs_require_valid_container_storage_paths(self):
        """Reject empty or misplaced inspect paths before storage classification."""
        path = str(self.storage / "overlay" / ("a" * 64) / "diff")
        self.assertEqual(self.namespace["writable_layers"](path + "\n"), {"a" * 64})
        for output in ("", "/tmp/overlay/" + "a" * 64 + "/diff", "<no value>"):
            with self.subTest(output=output), self.assertRaises(RuntimeError):
                self.namespace["writable_layers"](output)

    def test_run6_outside_storage_lines_fail(self):
        """Confirm that every run-6 line outside storage gives FAIL."""
        lines = [
            line
            for line in self.lines
            if line.startswith("Would relabel /var/lib/myproduct/.config")
        ]
        self.assertEqual(len(lines), 9)
        for line in lines:
            with self.assertRaisesRegex(RuntimeError, "outside storage"):
                self.namespace["classify_line"](
                    line, {"container_file_t"}, self.upper_layers
                )

    def test_unknown_line_and_unknown_storage_path_fail(self):
        """Confirm that unknown storage lines and diagnostic messages are rejected."""
        for line in (
            "unexpected diagnostic",
            "Would relabel "
            + str(self.storage / "unknown")
            + " from u:r:container_ro_file_t:s0 to u:r:container_var_lib_t:s0",
        ):
            with (
                self.subTest(line=line),
                self.assertRaisesRegex(RuntimeError, "Unclassified"),
            ):
                self.namespace["classify_line"](
                    line, {"container_file_t"}, self.upper_layers
                )

    def test_wrong_overlay_and_container_metadata_types_fail(self):
        """Confirm that wrong types on layers and container metadata are rejected."""
        for name, actual in (
            ("overlay-layers", "container_var_lib_t"),
            ("overlay-containers", "container_ro_file_t"),
        ):
            with (
                mock.patch.object(
                    self.filesystem,
                    "getxattr",
                    return_value=("u:r:" + actual + ":s0").encode(),
                ),
                contextlib.redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(RuntimeError, "deviates from the policy"),
            ):
                self.namespace["check_label"](self.storage / name)

    def test_missing_equivalence_fails(self):
        """Confirm that wrong policy probes reveal a missing equivalence."""
        self.policy.matchpathcon.return_value = (0, "u:r:var_lib_t:s0")
        self.policy.matchpathcon.side_effect = None
        with (
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(RuntimeError, "equivalence"),
        ):
            self.namespace["check_equivalence"]()

    def test_missing_selinux_module_fails_clearly(self):
        """Confirm a clear FAIL when the selinux Python module is missing."""
        with (
            mock.patch.dict("sys.modules", {"selinux": None}),
            self.assertRaisesRegex(SystemExit, "selinux Python module is missing"),
        ):
            exec(  # noqa: S102 - trusted repo heredoc under test
                compile(self.code, "remote.sh:LABELS", "exec"),
                {"__name__": "fixture"},
            )

    def test_customized_label_requires_customizable_policy(self):
        """Confirm that customized labels require the host's customizable policy."""
        line = next(line for line in self.lines if " not reset " in line)
        with self.assertRaisesRegex(RuntimeError, "Unclassified"):
            self.namespace["classify_line"](line, set(), self.upper_layers)

    def test_storage_dryrun_is_logged_when_outside_reports_stderr(self):
        """Keep both read-only dry runs even when the first writes diagnostics."""
        self.namespace.update(
            check_equivalence=lambda: None,
            check_label=lambda path: None,
            writable_layers=lambda output: {"a" * 64},
            sys=types.SimpleNamespace(argv=["labels", "fixture"]),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "volumes/app/_data").mkdir(parents=True)
            self.namespace["STORAGE"] = root
            dryrun = mock.Mock(
                side_effect=[RuntimeError("stderr diagnostic"), "inside evidence"]
            )
            self.namespace["dryrun"] = dryrun
            with (
                contextlib.redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(RuntimeError, "stderr diagnostic"),
            ):
                self.namespace["main"]()
            self.assertEqual(dryrun.call_count, 2)

    def test_storage_dryrun_is_logged_even_when_outside_fails(self):
        """Confirm that the storage dry run is logged even when the outside check fails."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "volumes/app/_data").mkdir(parents=True)
            self.namespace.update(
                STORAGE=root,
                check_equivalence=lambda: None,
                check_label=lambda path: None,
                writable_layers=lambda output: {"a" * 64},
                sys=types.SimpleNamespace(argv=["labels", "fixture"]),
            )
            dryrun = mock.Mock(
                side_effect=["Would relabel outside", "storage diagnostic"]
            )
            self.namespace["dryrun"] = dryrun
            with (
                contextlib.redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(RuntimeError, "outside storage"),
            ):
                self.namespace["main"]()
            self.assertEqual(dryrun.call_count, 2)


class SnapshotTests(unittest.TestCase):
    """Test that snapshot preparation changes only dev and preserves the source."""

    def setUp(self):
        """Create a synthetic Proxmox client and snapshot data."""
        spec = importlib.util.spec_from_file_location(
            "prepare", Path(__file__).with_name("prepare_dev_snapshot.py")
        )
        assert spec is not None and spec.loader is not None
        self.prepare = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.prepare)
        self.config = {
            "DEV_VMID": "107",
            "PROD_VMID": "108",
            "DEV_IP": "192.0.2.107",
            "SSH_USER": "tester",
        }
        self.client = mock.Mock()
        self.snapshots = [{"name": "clean-agent"}]

        def request(method, path):
            """Return synthetic Proxmox data for the snapshot tests."""
            if path.endswith("/snapshot"):
                return self.snapshots
            if path.endswith("/config"):
                return {"name": "unchanged source"}
            if path.endswith("/status/current"):
                return {"status": "running"}
            if path == "/cluster/ha/resources":
                return []
            raise AssertionError(path)

        self.client.request.side_effect = request

    def test_existing_snapshot_is_never_replaced(self):
        """Confirm that an existing clean-dev is never replaced."""
        self.snapshots.append({"name": "clean-dev"})
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            self.prepare.prepare(self.config, self.client)
        self.client.task.assert_not_called()

    def test_only_dev_mutated_and_source_snapshot_preserved(self):
        """Confirm dev operations and an unchanged clean-agent without prod calls."""
        ssh = mock.patch.object(self.prepare, "ssh")
        wait = mock.patch.object(self.prepare, "wait_ssh")
        with ssh as commands, wait, contextlib.redirect_stdout(io.StringIO()):
            self.prepare.prepare(self.config, self.client)
        paths = [call.args[0] for call in self.client.task.call_args_list]
        base = "/nodes/{node}/qemu/107"
        self.assertEqual(
            paths,
            [
                base + "/status/stop",
                base + "/snapshot/clean-agent/rollback",
                base + "/status/start",
                base + "/status/shutdown",
                base + "/snapshot",
                base + "/status/start",
            ],
        )
        self.assertEqual(
            self.client.task.call_args_list[4].args[1]["snapname"], "clean-dev"
        )
        self.assertIn("disable --now fapolicyd", commands.call_args_list[0].args[1])
        self.assertNotIn("disable --now firewalld", commands.call_args_list[0].args[1])
        self.assertIn("getenforce", commands.call_args_list[1].args[1])


if __name__ == "__main__":
    unittest.main()
