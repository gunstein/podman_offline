"""The opt-in --whoami scenario (backlog 71) without lab access."""

import contextlib
import importlib.util
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from test_acceptance import runner, shell_code

REMOTE = Path(__file__).with_name("remote.sh").read_text()
FUNCTIONS = (
    "whoami_trust_chain",
    "whoami_login",
    "whoami_configure",
    "whoami_backend_log",
    "whoami_log",
    "whoami_log_safety",
    "demo_credentials",
)
MARKER = re.search(r"^whoami_marker=.*$", REMOTE, re.MULTILINE).group(0)
# Stand-ins for the runtime account's commands: curl and podman answer from
# CURL/LOG; every call is recorded.
STUBS = """
as_product() {
    printf '%s\\n' "$*" >> "$CALLS"
    case "$1" in
        curl) printf '%s' "$CURL";;
        podman) printf '%s\\n' "$LOG"; return "${PODMAN_STATUS:-0}";;
    esac
}
install_checked() { echo install >> "$CALLS"; }
healthy() { echo healthy >> "$CALLS"; }
state=/S prod_host=example.invalid port=8443 prod_ip=192.0.2.2
"""


class ScenarioFixture(unittest.TestCase):
    """A runner whose lab, transfer and reboot calls are mocks."""

    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(mock.patch.object(runner, "RUNS", self.root))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.harness = runner.Run("test", "not-used")

    def prepare(self, guest):
        self.harness.whoami = True
        for name in ("readiness", "reset", "source", "record_bundles", "credentials"):
            setattr(self.harness, name, mock.Mock())
        self.harness.transfer = mock.Mock()
        self.harness.reboot = mock.Mock()
        self.harness.guest = mock.Mock(side_effect=guest)


class WhoamiScenarioTests(ScenarioFixture):
    """Step order and flag rules of the focused scenario."""

    def test_scenario_installs_only_its_components_and_restores_app3(self):
        self.prepare(lambda *args, **kwargs: "")
        self.harness.execute()
        self.assertTrue(self.harness.finished)
        self.harness.reboot.assert_called_once()
        self.assertEqual(
            [call.kwargs["bundle"] for call in self.harness.transfer.call_args_list],
            ["platform", "identity", "app3"],
        )
        installs = [
            call.kwargs["bundle"]
            for call in self.harness.guest.call_args_list
            if call.args[:2] == ("PROD", "install")
        ]
        self.assertEqual(installs, ["platform", "identity", "app3"])
        records = [
            json.loads(line)["step"]
            for line in (self.harness.folder / "record.jsonl").read_text().splitlines()
        ]
        ordered = [
            "03-dev-whoami-e2e",
            "06-prepare-host",
            "06-persistent-journal",
            "06-install-platform",
            "06-install-app3",
            "07-whoami-chain-mounts",
            "08-credentials",
            "08-whoami-e2e",
            "08-whoami-log-safety",
            "08-whoami-session-create",
            "09-whoami-restart",
            "09-whoami-session-restart",
            "09-reboot",
            "09-check-after-reboot",
            "09-whoami-session-reboot",
            "10-whoami-chain-break",
            "10-whoami-internal",
            "10-whoami-internal-e2e",
            "10-whoami-restore",
            "10-whoami-restored-e2e",
            "10-check-restored",
        ]
        self.assertEqual([step for step in records if step in ordered], ordered)
        for other in ("app1", "app2", "help", "registry", "example"):
            self.assertFalse([step for step in records if other in step], other)
        # Every app3-specific PROD action names the app3 release.
        for call in self.harness.guest.call_args_list:
            if call.args[0] == "PROD" and call.args[1].startswith("whoami-"):
                self.assertEqual(call.kwargs["bundle"], "app3")

    def test_flag_is_a_separate_focused_scenario(self):
        for flag in (
            "--status-retry",
            "--host-setup",
            "--identity-only",
            "--help-only",
            "--platform-help-only",
            "--renamed-product",
        ):
            with (
                self.subTest(flag=flag),
                mock.patch(
                    "sys.argv",
                    ["acceptance.py", "--run", "x", "--whoami", flag, "run"],
                ),
                mock.patch.object(runner, "Run") as run,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                with self.assertRaises(SystemExit) as error:
                    runner.main()
                self.assertEqual(error.exception.code, 2)
                run.assert_not_called()
        with (
            mock.patch("sys.argv", ["acceptance.py", "--run", "x", "--whoami", "run"]),
            mock.patch.object(runner, "Run") as run,
        ):
            self.assertEqual(runner.main(), 0)
        self.assertTrue(run.return_value.whoami)
        run.return_value.execute.assert_called_once()


class WhoamiRemoteTests(unittest.TestCase):
    """The PROD steps' shell code with stubbed runtime commands."""

    def run_shell(self, body, curl="", log="", podman_status=0):
        with tempfile.TemporaryDirectory() as directory:
            calls = Path(directory) / "calls"
            calls.write_text("")
            (Path(directory) / "generate-certificates.sh").write_text("")
            script = (
                "set -euo pipefail\n"
                + "\n".join(shell_code(REMOTE, function=name) for name in FUNCTIONS)
                + STUBS
                + MARKER
                + "\nbase="
                + directory
                + "\n"
                + body
            )
            result = subprocess.run(
                ["bash", "-c", script],
                capture_output=True,
                text=True,
                check=False,
                env={
                    "PATH": "/usr/bin:/bin",
                    "CALLS": str(calls),
                    "CURL": curl,
                    "LOG": log,
                    "PODMAN_STATUS": str(podman_status),
                },
            )
            return result, calls.read_text().splitlines()

    def test_demo_credentials_copy_the_environment_ca_only_for_app3(self):
        result, calls = self.run_shell("demo_credentials app3")
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("root.crt", "ca.crt"):
            self.assertIn(
                "install -m 0644 /S/PKI/private/ca.crt /S/app3/cert/" + name, calls
            )
        result, calls = self.run_shell("demo_credentials app2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse([call for call in calls if "/cert/" in call])

    def test_chain_break_needs_failed_sign_in_and_a_chain_error(self):
        body = shell_code(REMOTE, action="whoami-chain-break")
        error = "The remote certificate is invalid because of errors in the certificate chain: PartialChain"
        result, calls = self.run_shell(body, curl="500 ", log=error)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: without the environment CA", result.stdout)
        self.assertIn(
            "install -m 0644 /S/app3/unrelated-ca.crt /S/app3/cert/ca.crt", calls
        )
        self.assertIn("install", calls)
        for curl, log in (("302 https://x/", error), ("500 ", "no chain error here")):
            with self.subTest(curl=curl, log=log):
                result, _ = self.run_shell(body, curl=curl, log=log)
                self.assertEqual(result.returncode, 1)
                self.assertIn("FAIL:", result.stdout)

    def test_internal_and_restore_keep_the_browser_on_the_public_authorize_endpoint(
        self,
    ):
        public = (
            "302 https://example.invalid:8443/identity/connect/authorize?client_id=app3"
        )
        internal = shell_code(REMOTE, action="whoami-internal")
        log = "Identity metadata through the internal address http://identity-server:8080/identity; issuer"
        result, calls = self.run_shell(internal, curl=public, log=log)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "install -m 0644 /S/app3/unrelated-ca.crt /S/app3/cert/root.crt", calls
        )
        leaked = (
            "302 http://identity-server:8080/identity/connect/authorize?client_id=app3"
        )
        result, _ = self.run_shell(internal, curl=leaked, log=log)
        self.assertEqual(result.returncode, 1)
        restore = shell_code(REMOTE, action="whoami-restore")
        result, calls = self.run_shell(
            restore, curl=public, log="Identity metadata through the public origin"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "install -m 0644 /S/PKI/private/ca.crt /S/app3/cert/ca.crt", calls
        )
        self.assertIn("rm -f -- /S/app3/unrelated-ca.crt", calls)
        result, _ = self.run_shell(restore, curl=public, log=log)
        self.assertEqual(result.returncode, 1)

    def test_a_failed_log_read_is_never_evidence(self):
        """A matching line followed by a Podman error must fail the step."""
        body = shell_code(REMOTE, action="whoami-chain-break")
        error = "errors in the certificate chain: PartialChain"
        result, _ = self.run_shell(body, curl="500 ", log=error, podman_status=125)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("FAIL: could not read the app3 backend log", result.stderr)
        self.assertNotIn("PASS: without the environment CA", result.stdout)

    def test_log_safety_requires_the_fixed_line_and_no_marker(self):
        body = shell_code(REMOTE, action="whoami-log-safety")
        fixed = "OIDC sign-in failed: OpenIdConnectProtocolException (trace 0HN1:1)"
        marker = MARKER.split("=", 1)[1]
        result, _ = self.run_shell(body, log=fixed)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS:", result.stdout)
        for log, status in (
            (fixed + "\nerror_description: 'Synthetic " + marker + "'", 0),
            ("no OIDC failure was logged", 0),
            (fixed, 125),
        ):
            with self.subTest(log=log, status=status):
                result, _ = self.run_shell(body, log=log, podman_status=status)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertNotIn("PASS:", result.stdout)

    def test_persistent_journal_runs_the_helper_function_without_main(self):
        body = shell_code(REMOTE, action="persistent-journal")
        helper = (
            "def prepare_persistent_journal():\n"
            "    print('PASS: persistent journal verified')\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit('FAIL: main ran')\n"
        )
        script = (
            "set -euo pipefail\n"
            'sudo() { shift; "$@"; }\n'
            "release_source() { printf '%s' \"$HELPER\"; }\n" + body
        )
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=False,
            env={"PATH": os.environ["PATH"], "HELPER": helper},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "PASS: persistent journal verified")
        source = (runner.ROOT / "scripts/release.py").read_text()
        self.assertIn("def prepare_persistent_journal():", source)
        self.assertIn('if __name__ == "__main__":', source)

    def test_marker_matches_the_smoke_test(self):
        source = (runner.ROOT / "dev/whoami-smoke-test.py").read_text()
        self.assertIn('LOG_MARKER = "' + MARKER.split("=", 1)[1] + '"', source)


class WhoamiFailureTests(ScenarioFixture):
    """After a failed step PROD is left alone, and the report names its state."""

    def run_failing(self, fails):
        """Run until fails(role, action) is true; return REPORT.md."""

        def guest(role, action, *args, **kwargs):
            if fails(role, action):
                raise RuntimeError("injected failure")
            return ""

        self.prepare(guest)
        with self.assertRaises(RuntimeError):
            self.harness.execute()
        self.assertFalse(self.harness.finished)
        restores = [
            call
            for call in self.harness.guest.call_args_list
            if call.args[1] == "whoami-restore"
        ]
        self.assertFalse(restores)
        self.assertFalse(self.harness.report())
        return (self.harness.folder / "REPORT.md").read_text()

    def test_chain_break_failure_names_the_unrelated_ca(self):
        report = self.run_failing(lambda role, action: action == "whoami-chain-break")
        self.assertIn("may still hold " + runner.WHOAMI_INJECTED["chain"], report)

    def test_internal_failure_names_the_internal_variant(self):
        report = self.run_failing(lambda role, action: action == "whoami-internal")
        self.assertIn("may still hold " + runner.WHOAMI_INJECTED["internal"], report)

    def test_internal_smoke_failure_names_the_internal_variant(self):
        smoke = []

        def fails(role, action):
            smoke.append(action == "whoami-e2e")
            return sum(smoke) == 2  # The second whoami-e2e is 10-whoami-internal-e2e.

        report = self.run_failing(fails)
        self.assertIn("may still hold " + runner.WHOAMI_INJECTED["internal"], report)

    def test_failure_before_injection_names_no_state(self):
        report = self.run_failing(lambda role, action: action == "whoami-e2e")
        self.assertNotIn("may still hold", report)


class FakeRequests(types.ModuleType):
    """Enough of requests for whoami_session without the package installed."""

    class RequestException(Exception):
        pass

    def __init__(self):
        super().__init__("requests")
        self.Session = mock.Mock


def load_session_module():
    """Import acceptance/whoami_session.py with a fake requests module."""
    original = socket.getaddrinfo
    with mock.patch.dict(sys.modules, {"requests": FakeRequests()}):
        spec = importlib.util.spec_from_file_location(
            "whoami_session_under_test",
            str(Path(__file__).with_name("whoami_session.py")),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    socket.getaddrinfo = original  # The smoke helper redirects DNS on import.
    return module


class Response:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def json(self):
        return self.body


class WhoamiSessionTests(unittest.TestCase):
    """The saved-session helper: deadline, retry limits and private file."""

    def setUp(self):
        self.module = load_session_module()
        self.clock = [0.0]
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(
            mock.patch.object(self.module.time, "monotonic", lambda: self.clock[0])
        )
        self.stack.enter_context(
            mock.patch.object(self.module.time, "sleep", self.advance)
        )

    def advance(self, seconds):
        self.clock[0] += seconds

    def session(self, answers):
        """A session whose /auth/me answers come from a list; each call takes 5 s."""
        timeouts = []

        def get(url, timeout):
            timeouts.append(timeout)
            self.advance(5)
            answer = answers.pop(0) if answers else Response(200, {"user": None})
            if isinstance(answer, Exception):
                raise answer
            return answer

        session = mock.Mock()
        session.get.side_effect = get
        return session, timeouts

    def test_a_permanently_anonymous_session_fails_at_the_wall_clock_deadline(self):
        session, timeouts = self.session([])
        with self.assertRaisesRegex(AssertionError, "within 60 seconds"):
            self.module.signed_in(session)
        self.assertLessEqual(self.clock[0], 66)
        self.assertTrue(all(timeout <= 15 for timeout in timeouts))
        # The last request may use only the time left, not a full 15 seconds.
        self.assertLess(timeouts[-1], 15)

    def test_transient_failures_then_the_same_session_pass(self):
        alice = Response(200, {"user": {"sub": "alice"}, "csrf": "token"})
        session, _ = self.session(
            [self.module.requests.RequestException(), Response(502, {}), alice]
        )
        with mock.patch.object(
            self.module.smoke, "claims", return_value={"sub": ["alice"]}
        ):
            self.assertEqual(self.module.signed_in(session), "token")
        # It never signs in again; only /auth/me was requested.
        self.assertEqual(session.get.call_count, 3)

    def test_saved_cookies_are_private_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            session = types.SimpleNamespace(
                cookies=[
                    types.SimpleNamespace(
                        name="app3-session", value="v", domain="", path="/app3/"
                    )
                ]
            )
            self.module.save(session, path)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                self.module.save(session, path)


if __name__ == "__main__":
    unittest.main()
