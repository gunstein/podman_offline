"""Manual-step mapping and focused setup scenario gates, without a lab."""

import shlex
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import host_setup
from test_acceptance import runner


class HostSetupHarnessTests(unittest.TestCase):
    def test_literal_gateway_config_stops_before_editing_after_init_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / "cedar/releases/cedar-worker-1.0.0"
            release.mkdir(parents=True)
            (release / "deploy.sh").write_text("exit 23\n")
            config = root / "cedar/state/worker/config.yaml"
            config.parent.mkdir(parents=True)
            original = "PUBLIC_ORIGIN: https://retained.invalid\n"
            config.write_text(original)
            values = dict(
                self.values,
                public_origin="https://new.invalid",
                bind_ip="127.0.0.1",
                credentials=str(root / "incoming"),
            )
            # Exactly the pasted block, with only public worksheet values and
            # fixture paths. No harness assignments(), bash -e or outer set -e.
            code = "\n".join(k + "=" + shlex.quote(v) for k, v in values.items()) + "\n"
            code += host_setup.blocks()["gateway-config"].replace("/var/lib", str(root))
            result = subprocess.run(
                ["bash"], input=code, capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 23, result.stderr)
            self.assertEqual(config.read_text(), original)
            self.assertFalse((root / "incoming").exists())

    def setUp(self):
        self.values = {
            "product": "cedar",
            "runtime": "operator-a",
            "gateway": "worker",
            "gateway_version": "1.0.0",
            "login_component": "processor",
            "login_version": "2.0.0",
            "with_identity": "yes",
            "credential_format": "pem",
            "discovery_path": "/identity/.well-known/openid-configuration",
            "helper_sha256": "a" * 64,
            "key_sha256": "b" * 64,
            "upload": "/var/tmp/incoming",
            "port": "8443",
        }
        self.harness = mock.Mock()
        self.harness.meta = {}
        self.harness.operator_ssh = ["ssh", "-i", "/private/key", "operator-a@host"]
        self.harness.host.return_value = "admin@host"

    def test_all_manual_blocks_are_unique_complete_and_shell_parseable(self):
        blocks = host_setup.blocks()
        self.assertEqual(set(blocks), set(host_setup.STEPS))
        for step in blocks:
            result = subprocess.run(
                ["bash", "-n"],
                input=host_setup.script(step, self.values),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, step + result.stderr)
        with self.assertRaises(ValueError):
            host_setup.blocks(
                host_setup.MANUAL.read_text().replace(
                    "<!-- operator: setup -->", "<!-- operator: renamed-setup -->"
                )
            )

    def test_literal_transfers_stop_on_first_scp_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stub = root / "scp"
            calls = root / "calls"
            stub.write_text(
                "#!/bin/sh\nprintf 'called\\n' >> "
                + shlex.quote(str(calls))
                + "\nexit 17\n"
            )
            stub.chmod(0o700)
            values = dict(
                self.values,
                admin="admin",
                server="host",
                credentials="/private/incoming",
            )
            for step in ("transfer", "credentials-transfer"):
                with self.subTest(step=step):
                    code = host_setup.assignments(values)
                    code += "PATH=" + shlex.quote(str(root)) + ":$PATH\n"
                    code += host_setup.blocks()[step]
                    result = subprocess.run(
                        ["bash"],
                        input=code,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 17, result.stderr)
                    self.assertEqual(calls.read_text(), "called\n")
                    calls.unlink()

    def test_runtime_transport_is_ssh_without_sudo_or_xdg_injection(self):
        host_setup.operator(self.harness, "init-layout", self.values, True)
        args, script = self.harness.command.call_args.args
        self.assertEqual(args[-2:], ["operator-a@host", "bash -s"])
        self.assertIn(" init-layout", script)
        self.assertNotIn("sudo", script)
        self.assertNotIn("XDG_", script)
        self.harness.ssh.assert_not_called()
        self.assertFalse(script.startswith("set -"))
        host_setup.operator(self.harness, "init-layout", self.values, False)
        self.assertEqual(self.harness.command.call_args.args[0][-1], "bash -s")
        self.harness.ssh.assert_not_called()
        self.assertEqual(host_setup.blocks()["login"], 'ssh "$runtime@$server"')

    def test_first_setup_recognizes_only_the_exact_sole_prerequisite_failure(self):
        error = "ERROR: setup: preflight failed before changes:\n- set subj_cache_size = 16381 in /etc/fapolicyd/fapolicyd.conf and restart fapolicyd as administrator before retry\n"
        failure = types.SimpleNamespace(returncode=1, stdout="", stderr=error)
        with (
            mock.patch.object(host_setup.subprocess, "run", return_value=failure),
            mock.patch.object(host_setup, "operator") as operator,
        ):
            host_setup.initial_setup(self.harness, self.values)
            self.assertEqual(
                [c.args[1] for c in operator.call_args_list], ["cache-remedy", "setup"]
            )
        for stderr in ("permission denied", error + "- keyring mismatch\n"):
            with (
                mock.patch.object(
                    host_setup.subprocess,
                    "run",
                    return_value=types.SimpleNamespace(
                        returncode=1, stdout="", stderr=stderr
                    ),
                ),
                mock.patch.object(host_setup, "operator") as operator,
            ):
                with self.assertRaises(RuntimeError):
                    host_setup.initial_setup(self.harness, self.values)
                operator.assert_not_called()

    def test_http_assertions_refuse_successful_curl_with_wrong_status(self):
        for step, value in (("gateway-check", "404\n"), ("identity-check", "502\n")):
            with (
                mock.patch.object(host_setup, "operator", return_value=value),
                self.assertRaises(RuntimeError),
            ):
                host_setup.checked_runtime(self.harness, step, self.values)

    def test_interruption_is_authenticated_bounded_and_not_a_production_flag(self):
        result = types.SimpleNamespace(
            returncode=137,
            stdout="PROBE: publications authenticated; interrupt before journal flush\n",
            stderr="",
        )
        with mock.patch.object(
            host_setup.subprocess, "run", return_value=result
        ) as run:
            host_setup.interrupted_setup(self.harness, self.values)
            code = run.call_args.kwargs["input"]
            self.assertIn("hashlib.sha256(data).hexdigest() != sys.argv[1]", code)
            self.assertIn("namespace['main']()", code)
            self.assertIn("signal.SIGKILL", code)
        # Above subprocess is deliberately mocked; independently parse outside it.
        parsed = subprocess.run(
            ["bash", "-n"], input=code, capture_output=True, text=True, check=False
        )
        self.assertEqual(parsed.returncode, 0, parsed.stderr)
        with (
            mock.patch.object(
                host_setup.subprocess,
                "run",
                return_value=types.SimpleNamespace(
                    returncode=1, stdout="unrelated failure", stderr=""
                ),
            ),
            self.assertRaises(RuntimeError),
        ):
            host_setup.interrupted_setup(self.harness, self.values)

    def test_focused_scenario_wiring_for_normal_renamed_and_gateway_only(self):
        for renamed, minimal in ((False, False), (True, False), (False, True)):
            with (
                self.subTest(renamed=renamed, minimal=minimal),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                run = mock.Mock()
                run.id = "host65-unit"
                run.host.return_value = "admin@host"
                run.ssh.return_value = "public-record-hashes"
                run.product = "shop" if renamed else "myproduct"
                run.platform_help_only, run.renamed_product = minimal, renamed
                run.folder = run.private = root
                run.cfg = {
                    "PROD_IP": "192.0.2.2",
                    "PROD_HOST": "host.invalid",
                    "SSH_USER": "admin",
                    "HTTPS_PORT": "8443",
                }
                gateway, identity = (
                    ("gateway", "login-service")
                    if renamed
                    else ("platform", "identity")
                )
                run.meta = {"bundles_built": {gateway: "1.0.0", identity: "2.0.0"}}
                (root / "bundle-signing.gpg").write_bytes(b"public fixture")
                seen = []
                run.step.side_effect = lambda name, action, seen=seen: (
                    seen.append(name),
                    action(),
                )[-1]

                def command(args, *unused, **kwargs):
                    if (
                        args[0] == "scp"
                        and len(args) > 2
                        and "host65-credentials/" in str(args[-2])
                    ):
                        Path(args[-1]).write_bytes(b"private fixture")
                    return ""

                run.command.side_effect = command
                with (
                    mock.patch.object(host_setup, "infrastructure"),
                    mock.patch.object(
                        host_setup,
                        "operator",
                        return_value='{"_SYSTEMD_USER_UNIT": "'
                        + run.product
                        + "-"
                        + gateway
                        + '.service"}\n',
                    ) as operator,
                    mock.patch.object(host_setup, "initial_setup"),
                    mock.patch.object(host_setup, "interrupted_setup"),
                    mock.patch.object(host_setup, "checked_runtime"),
                ):
                    host_setup.execute(run)
                self.assertTrue(run.finished)
                self.assertEqual(run.transfer.call_count, 1 if minimal else 2)
                self.assertTrue(
                    all(
                        c.kwargs["publish"] is False
                        for c in run.transfer.call_args_list
                    )
                )
                self.assertLess(
                    seen.index("06-manual-tool-bootstrap"),
                    seen.index("06-manual-setup-first"),
                )
                self.assertLess(
                    seen.index("06-setup-interruption"),
                    seen.index("06-manual-setup-retry"),
                )
                self.assertIn("08-runtime-status-journal", seen)
                self.assertFalse(
                    any(
                        c.args[:2] == ("PROD", "prepare-host")
                        for c in run.guest.call_args_list
                    )
                )
                self.assertTrue(
                    any(
                        c.args[1] == "init-layout" and c.args[3] is True
                        for c in operator.call_args_list
                    )
                )

    def test_flag_dispatch_and_incompatible_modes_stop_before_reset(self):
        for flag in ("--status-retry", "--identity-only", "--help-only"):
            with (
                mock.patch(
                    "sys.argv",
                    ["acceptance.py", "--run", "x", "--host-setup", flag, "run"],
                ),
                mock.patch.object(runner, "Run") as run,
            ):
                with self.assertRaises(SystemExit) as error:
                    runner.main()
                self.assertEqual(error.exception.code, 2)
                run.assert_not_called()

    def test_cleanup_key_code_is_valid_and_removes_only_the_disposable_key(self):
        self.harness.operator_public_key = "ssh-ed25519 lab-public-key"
        self.harness.operator_values = {"runtime": "operator-a"}
        host_setup.cleanup(self.harness)
        code = (
            self.harness.ssh.call_args.args[1]
            .split("<<'CLEAN_KEY'\n", 1)[1]
            .split("\nCLEAN_KEY")[0]
        )
        compile(code, "cleanup-key", "exec")
        self.assertIn("line != key", code)
        self.assertIsNone(self.harness.operator_public_key)

    def test_manual_pfx_files_go_to_signing_and_mismatch_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = dict(
                self.values, credential_format="pfx", credentials=str(root / "incoming")
            )
            incoming = Path(values["credentials"])
            incoming.mkdir(mode=0o700)
            for name in ("signing-cert.pfx", "pfx-password"):
                (incoming / name).write_text("private fixture " + name)
            release = root / "lib/cedar/releases/cedar-processor-2.0.0"
            release.mkdir(parents=True)
            (release / "deploy.sh").write_text('#!/bin/sh\ntest "$1" = init-config\n')
            code = host_setup.script("identity-config", values).replace(
                "/var/lib/", str(root / "lib") + "/"
            )

            def execute():
                return subprocess.run(
                    ["bash", "-s"],
                    input=code,
                    capture_output=True,
                    text=True,
                    check=False,
                )

            result = execute()
            self.assertEqual(result.returncode, 0, result.stderr)
            target = root / "lib/cedar/state/processor/credentials/signing/pfx-password"
            original = target.read_bytes(), target.stat().st_ino
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertFalse((target.parent.parent / "users/pfx-password").exists())
            self.assertEqual(execute().returncode, 0)
            (incoming / "pfx-password").write_text("other-secret")
            result = execute()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("credential conflict", result.stderr)
            self.assertNotIn("other-secret", result.stderr)
            self.assertEqual((target.read_bytes(), target.stat().st_ino), original)

    def test_manual_journal_projection_omits_message_contents(self):
        code = host_setup.blocks()["status"]
        projection = code.split("--output-fields=", 1)[1].split()[0]
        self.assertNotIn("MESSAGE", projection)
        self.assertIn("_SYSTEMD_USER_UNIT", projection)
        self.assertIn("__REALTIME_TIMESTAMP", projection)
