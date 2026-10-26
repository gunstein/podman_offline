"""The opt-in --whoami scenario (backlog 71) without lab access."""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_acceptance import runner, shell_code

REMOTE = Path(__file__).with_name("remote.sh").read_text()
FUNCTIONS = (
    "whoami_trust_chain",
    "whoami_login",
    "whoami_configure",
    "whoami_log",
    "demo_credentials",
)
# Stand-ins for the runtime account's commands: curl and podman answer from
# CURL/LOG; every call is recorded.
STUBS = """
as_product() {
    printf '%s\\n' "$*" >> "$CALLS"
    case "$1" in
        curl) printf '%s' "$CURL";;
        podman) printf '%s\\n' "$LOG";;
    esac
}
install_checked() { echo install >> "$CALLS"; }
healthy() { echo healthy >> "$CALLS"; }
state=/S prod_host=example.invalid port=8443 prod_ip=192.0.2.2
"""


class WhoamiScenarioTests(unittest.TestCase):
    """Step order and flag rules of the focused scenario."""

    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(mock.patch.object(runner, "RUNS", self.root))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.harness = runner.Run("test", "not-used")

    def test_scenario_installs_only_its_components_and_restores_app3(self):
        self.harness.whoami = True
        for name in ("readiness", "reset", "source", "record_bundles", "credentials"):
            setattr(self.harness, name, mock.Mock())
        self.harness.transfer = mock.Mock()
        self.harness.reboot = mock.Mock()
        self.harness.guest = mock.Mock(return_value="")
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
            "06-install-app3",
            "07-whoami-chain-mounts",
            "08-credentials",
            "08-whoami-e2e",
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

    def run_shell(self, body, curl="", log=""):
        with tempfile.TemporaryDirectory() as directory:
            calls = Path(directory) / "calls"
            calls.write_text("")
            (Path(directory) / "generate-certificates.sh").write_text("")
            script = (
                "set -euo pipefail\n"
                + "\n".join(shell_code(REMOTE, function=name) for name in FUNCTIONS)
                + STUBS
                + "base="
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


if __name__ == "__main__":
    unittest.main()
