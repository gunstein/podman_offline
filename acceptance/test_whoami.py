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
        self.harness.transfer_whoami_environment = mock.Mock()
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
        # Backlog 85: neutral bundles; the environment file is placed on PROD
        # after the host is prepared and before the first install.
        dev = [
            call.args[1]
            for call in self.harness.guest.call_args_list
            if call.args[0] == "DEV"
        ]
        self.assertIn("bundle", dev)
        prod = [
            call.args[1]
            for call in self.harness.guest.call_args_list
            if call.args[0] == "PROD"
        ]
        self.assertLess(prod.index("prepare-host"), prod.index("whoami-environment"))
        self.assertLess(prod.index("whoami-environment"), prod.index("install"))
        records = [
            json.loads(line)["step"]
            for line in (self.harness.folder / "record.jsonl").read_text().splitlines()
        ]
        ordered = [
            "03-dev-whoami-e2e",
            "06-prepare-host",
            "06-install-platform",
            "06-install-app3",
            "06-whoami-api-registration",
            "07-release-protection",
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
            # Backlog 85: the four target-environment cases, then a check.
            "10-environment-plain",
            "10-environment-records",
            "10-environment-rotate",
            "10-environment-rotate-e2e",
            "10-environment-pending",
            "10-environment-pending-e2e",
            # Backlogs 86 and 87: a variable and escaped text in app3's overrides.
            "10-variables",
            "10-variables-e2e",
            "10-check-environment",
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
            "--rpm-manual",
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


class EnvironmentStepTests(unittest.TestCase):
    """Backlog 85's lab steps: their Python parts, run as the guest runs them."""

    def run_python(self, heredoc, *arguments):
        return subprocess.run(
            [sys.executable, "-", *map(str, arguments)],
            input=shell_code(REMOTE, heredoc=heredoc),
            capture_output=True,
            text=True,
            check=False,
        )

    def run_plain(self, deploy_output, runtime_output, changed=False):
        """whoami-environment-plain with as_product and the fingerprint stubbed."""
        script = (
            "set -euo pipefail\nproduct_name=myproduct product=/R\n"
            + shell_code(REMOTE, function="expect_refusal")
            + "\nas_product() {\n"
            + '    if [[ $1 == bash ]]; then printf "%s\\n" "$DEPLOY"; else printf "%s\\n" "$RUNTIME"; fi\n'
            + "    return 1\n}\n"
            + 'environment_fingerprint() { echo "state $CHANGED"; }\n'
            + shell_code(REMOTE, action="whoami-environment-plain")
        )
        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=False,
            env={
                "PATH": "/usr/bin:/bin",
                "DEPLOY": deploy_output,
                "RUNTIME": runtime_output,
                "CHANGED": "",
            },
        )

    def test_the_plain_step_expects_the_products_own_messages(self):
        """The strings the step greps, worded as the product tests pin them
        (test_environment_components, test_runtime)."""
        deploy = (
            "ERROR: app3 was installed with --environment whoami, which gave it "
            "overrides or an API secret line; an install without it would remove "
            "them. Run myproduct --environment whoami app3 (or ./deploy.sh install "
            "--environment whoami); nothing was changed"
        )
        runtime = (
            "ERROR: app3 was installed with --environment whoami, which gave it "
            "overrides or an API secret line; nothing was changed. Run myproduct "
            "--environment whoami app3"
        )
        result = self.run_plain(deploy, runtime)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "PASS: an install without the environment is refused", result.stdout
        )
        result = self.run_plain("ERROR: something else", runtime)
        self.assertNotEqual(result.returncode, 0)

    def test_the_variable_lines_are_added_to_app3s_overrides(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = root / "whoami.yaml"
        source = Path(__file__).resolve().parents[1] / "config/whoami.yaml"
        path.write_text(source.read_text())
        result = self.run_python("LAB_LINES", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        import yaml

        document = yaml.safe_load(path.read_text())
        self.assertEqual(
            document["overrides"]["app3"]["ENVIRONMENT"]["backend"],
            {
                "Lab__Level": "@@$APP3_LAB_LEVEL@@",
                "Lab__Literal": "SELECT @@@@VERSION; "
                "@@@@secret:app3-api-secret/value@@@@ @@@@$APP3_LAB_LEVEL@@@@",
            },
        )
        # Identity's registration of app3 is kept as it was.
        self.assertEqual(
            document["overrides"]["identity"],
            yaml.safe_load(source.read_text())["overrides"]["identity"],
        )

    def test_the_variable_step_expects_the_products_rendering(self):
        """The step's expected container text is what the product renders."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from deployment import common, templates

        text = "SELECT @@@@VERSION; @@@@secret:app3-api-secret/value@@@@ @@@@$APP3_LAB_LEVEL@@@@"
        with mock.patch.object(common, "ENVIRON", {}):
            rendered = templates.substitute(text, lambda *a: "never", "t")
        body = shell_code(REMOTE, action="whoami-variables")
        found = re.search(r"literal='Lab__Literal=([^']*)'", body)
        assert found is not None
        self.assertEqual(rendered, found[1])
        # The dev step's origin line is the one config/dev.yaml.example has.
        example = (
            Path(__file__).resolve().parents[1] / "config/dev.yaml.example"
        ).read_text()
        self.assertIn("PUBLIC_ORIGIN: https://myproduct-proxy:8443\n", example)
        self.assertIn("export DEV_PUBLIC_HOST=myproduct-proxy", REMOTE)

    def test_every_step_has_its_action(self):
        for name in ("plain", "records", "rotate", "pending"):
            self.assertRegex(REMOTE, r"(?m)^whoami-environment-" + name + r"\)$")
        self.assertRegex(REMOTE, r"(?m)^whoami-variables\)$")
        compile(shell_code(REMOTE, heredoc="PENDING_INSTALL"), "pending", "exec")

    def test_the_installs_of_a_runtime_run_are_read_in_order(self):
        output = (
            "[OK] platform 0.4.3 is installed with environment whoami\n"
            "[OK] identity 0.4.3 installed\n"
            "[OK] app3 0.1.0 installed\n"
            "PASS: myproduct completed\n"
        )
        self.assertEqual(
            self.run_python("RUNTIME_INSTALLS", output, "identity app3").returncode, 0
        )
        for expected in ("app3 identity", "identity", ""):
            with self.subTest(expected):
                result = self.run_python("RUNTIME_INSTALLS", output, expected)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL: installed", result.stderr)
        unfinished = output.replace("PASS: myproduct completed\n", "")
        result = self.run_python("RUNTIME_INSTALLS", unfinished, "identity app3")
        self.assertIn("did not complete", result.stderr)

    def test_the_key_edit_changes_only_identitys_app3_line(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = root / "whoami.yaml"
        source = Path(__file__).resolve().parents[1] / "config/whoami.yaml"
        path.write_text(source.read_text())
        result = self.run_python("WHOAMI_KEY", path, "rotated")
        self.assertEqual(result.returncode, 0, result.stderr)
        import yaml

        document = yaml.safe_load(path.read_text())
        self.assertEqual(
            document["overrides"]["identity"]["ENVIRONMENT"]["app"][
                "ApiResources__0__ApiSecrets__0__Value"
            ],
            "@@secret:app3-api-secret/rotated@@",
        )
        self.assertEqual(
            path.read_text().replace("/rotated@@", "/value@@"), source.read_text()
        )

    def test_the_key_check_reads_metadata_record_and_secret(self):
        import base64

        import yaml

        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        state = root / "state"
        for directory in ("metadata", "environment", "app3/credentials/api-secret"):
            (state / directory).mkdir(parents=True)
        entry = {"index": 0, "secret": "app3-api-secret/rotated"}
        (state / "metadata/identity.json").write_text(
            json.dumps({"api_secrets": {"app3": entry}})
        )
        (state / "environment/app3.json").write_text(
            json.dumps({"api_secret": entry, "environment": "whoami", "overrides": {}})
        )
        (state / "app3/credentials/api-secret/rotated").write_bytes(b"secret-bytes")
        identity = root / "myproduct-identity.yaml"

        def secret(value):
            line = "ApiResources__0__ApiSecrets__0__Value"
            identity.write_text(
                yaml.safe_dump_all(
                    [
                        {"kind": "Pod", "metadata": {"name": "identity"}},
                        {
                            "kind": "Secret",
                            "metadata": {"name": "identity-apis"},
                            "data": {line: base64.b64encode(value).decode()},
                        },
                    ]
                )
            )

        secret(b"secret-bytes")
        result = self.run_python("WHOAMI_KEY_CHECK", state, identity, "rotated")
        self.assertEqual(result.returncode, 0, result.stderr)
        secret(b"other-bytes")
        result = self.run_python("WHOAMI_KEY_CHECK", state, identity, "rotated")
        self.assertIn("identity-apis does not hold", result.stderr)
        secret(b"secret-bytes")
        result = self.run_python("WHOAMI_KEY_CHECK", state, identity, "value")
        self.assertIn("installed identity does not name", result.stderr)


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


class ChainMountCheckTests(unittest.TestCase):
    """whoami-chain-mounts: the CA files' content and read-only mounts (backlogs 70, 80)."""

    def check(self, writable_root=False, other_ca=False):
        """Run the check's in-account script with podman answering from a fixture."""
        body = REMOTE[REMOTE.index("whoami-chain-mounts)") :]
        script = body[
            body.index("as_product bash -c '") + len("as_product bash -c '") :
        ]
        script = script[: script.index("\n    ' bash ")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "PKI/private").mkdir(parents=True)
            (root / "PKI/private/ca.crt").write_text("environment CA\n")
            stub = root / "podman"
            stub.write_text(
                "#!/bin/bash\n"
                'case "$1 $2" in\n'
                '  "exec app3-whoami-backend")\n'
                '    if [[ $3 == cat ]]; then printf "%s" "$CA"; else echo 140; fi;;\n'
                '  "inspect app3-whoami-backend") printf "%s" "$MOUNTS";;\n'
                "esac\n"
            )
            stub.chmod(0o755)
            mounts = (
                "/etc/hosts false\n"
                f"/etc/ssl/certs/myproduct-root.pem {str(writable_root).lower()}\n"
                "/etc/ssl/certs/myproduct-ca.pem false\n"
            )
            return subprocess.run(
                ["bash", "-c", script, "bash", "myproduct", str(root)],
                env=dict(
                    os.environ,
                    PATH=directory + os.pathsep + os.environ["PATH"],
                    CA="unrelated CA\n" if other_ca else "environment CA\n",
                    MOUNTS=mounts,
                ),
                capture_output=True,
                text=True,
                check=False,
            )

    def test_read_only_files_with_the_environment_ca_pass(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "PASS: read-only subPath files hold the environment CA", result.stdout
        )

    def test_a_writable_mount_or_another_ca_fails(self):
        result = self.check(writable_root=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("myproduct-root.pem is not a read-only mount", result.stdout)
        result = self.check(other_ca=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not the environment CA", result.stdout)


if __name__ == "__main__":
    unittest.main()


class WhoamiApiRegistrationTests(unittest.TestCase):
    """The PROD check of app3's registration, against fixture state files."""

    def state(self, directory, registration=b"app3-secret", rendered=b"app3-secret"):
        import base64

        import yaml

        state = Path(directory) / "state"
        files = {
            "metadata/identity.json": json.dumps(
                {
                    "api_secrets": {
                        "app3": {"index": 0, "secret": "app3-api-secret/value"}
                    }
                }
            ).encode(),
            "app3/credentials/api-secret/value": b"app3-secret",
            "apis/app3/value": registration,
        }
        for relative, data in files.items():
            (state / relative).parent.mkdir(parents=True, exist_ok=True)
            (state / relative).write_bytes(data)
        identity = Path(directory) / "myproduct-identity.yaml"
        secret = {
            "kind": "Secret",
            "metadata": {"name": "identity-apis"},
            "data": {
                "ApiResources__0__ApiSecrets__0__Value": base64.b64encode(
                    rendered
                ).decode()
            },
        }
        identity.write_text(
            yaml.safe_dump_all([{"kind": "Pod", "metadata": {"name": "x"}}, secret])
        )
        return state, identity

    def check(self):
        from test_components import guest_code

        return guest_code("WHOAMI_API")["check_registration"]

    def test_the_secret_registration_and_identity_key_agree(self):
        with tempfile.TemporaryDirectory() as directory:
            self.check()(*self.state(directory))

    def test_each_wrong_link_fails(self):
        for label, kwargs, cause in (
            (
                "registration",
                {"registration": b"other"},
                "registration is not app3's secret",
            ),
            (
                "rendered",
                {"rendered": b"other"},
                "identity-apis Secret lacks app3's secret",
            ),
            (
                "empty registration",
                {"registration": b""},
                "registration is not app3's secret",
            ),
        ):
            with self.subTest(label), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(RuntimeError, cause) as raised:
                    self.check()(*self.state(directory, **kwargs))
                self.assertNotIn("app3-secret", str(raised.exception))
        with tempfile.TemporaryDirectory() as directory:
            state, identity = self.state(directory)
            (state / "metadata/identity.json").write_text('{"api_secrets": {}}')
            with self.assertRaisesRegex(RuntimeError, "does not register app3"):
                self.check()(state, identity)


class PlaceEnvironmentTests(unittest.TestCase):
    """place_environment: the runtime account writes state/<name>.yaml (0600)."""

    def test_the_file_is_private_and_later_installs_name_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "state").mkdir()
            (root / "base").mkdir()
            script = (
                "set -euo pipefail\n"
                f"state={root / 'state'}\nbase={root / 'base'}\n"
                'as_product() { "$@"; }\n'
                + shell_code(REMOTE, function="place_environment")
                + "place_environment prod1 <<'FILE'\ncomponents: [platform]\nFILE\n"
                + 'printf "%s\\n" "${environment_option[@]}"\n'
            )
            result = subprocess.run(
                ["bash", "-c", script], capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            path = root / "state/prod1.yaml"
            self.assertEqual(path.read_text(), "components: [platform]\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / "base/environment").read_text(), "prod1\n")
            self.assertEqual(result.stdout, "--environment\nprod1\n")
