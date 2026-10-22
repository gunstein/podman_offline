"""Init-process assertions, independent oracle and scoped cleanup without a VM."""

import base64
import contextlib
import hashlib
import io
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import init_secret_test as probe
import yaml


class InitSecretHarnessTests(unittest.TestCase):
    def process(self, value, expected, nonce="fresh", fresh_expected=None):
        environment = {"PROBE_RUN": nonce, "PROBE_ROLE": "init"}
        if value is not None:
            environment["APP_CONNECTIONSTRING"] = value
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch("builtins.open", return_value=io.StringIO(expected)),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            try:
                check = probe.CHECK.replace(
                    "EXPECTED_DIGEST",
                    hashlib.sha256(
                        (
                            expected if fresh_expected is None else fresh_expected
                        ).encode()
                    ).hexdigest(),
                )
                exec(compile(check, "fixed-probe", "exec"), {})  # noqa: S102 - repository probe
                status = 0
            except SystemExit as error:
                status = error.code
        return status, output.getvalue()

    def test_actual_process_check_requires_exact_nonempty_environment(self):
        expected = "Host=example.invalid;Password=PrivateSynthetic"
        for value in (None, "", "wrong", "Host=old.invalid;Password=PrivateSynthetic"):
            with self.subTest(value=value):
                status, logs = self.process(value, expected)
                self.assertEqual(status, 17)
                self.assertEqual(logs, "PROBE-FAIL\n")
                self.assertNotIn(expected, logs)
        self.assertEqual(self.process(expected, expected), (0, "PROBE-OK:fresh\n"))
        self.assertEqual(self.process("", "")[0], 17)
        self.assertEqual(self.process("stale", "stale", fresh_expected=expected)[0], 17)

    def commands(
        self,
        init_logs="PROBE-OK:fresh\n",
        init_status="exited",
        exit_code=0,
        missing=False,
    ):
        def command(arguments, allowed=(0,)):
            role = arguments[-1].rsplit("-", 1)[-1]
            if arguments[1] == "inspect":
                if role == "init" and missing:
                    return types.SimpleNamespace(returncode=125, stdout="", stderr="")
                state = {
                    "Status": init_status if role == "init" else "running",
                    "ExitCode": exit_code if role == "init" else 0,
                }
                return types.SimpleNamespace(
                    returncode=0, stdout=json.dumps([{"State": state}]), stderr=""
                )
            logs = init_logs if role == "init" else "PROBE-OK:fresh\n"
            return types.SimpleNamespace(returncode=0, stdout=logs, stderr="")

        return command

    def test_exited_always_init_requires_its_own_fresh_success(self):
        with mock.patch.object(probe, "command", side_effect=self.commands()):
            probe.verify("fixture", "fresh")

    def test_healthy_main_cannot_hide_missing_stale_failed_or_timed_out_init(self):
        cases = (
            ("", "exited", 0, False),
            ("PROBE-OK:old\n", "exited", 0, False),
            ("PROBE-FAIL\n", "exited", 0, False),
            ("PROBE-OK:fresh\n", "exited", 17, False),
            ("PROBE-OK:fresh\n", "exited", 0, True),
            ("PROBE-OK:fresh\n", "running", 0, False),
        )
        for case in cases:
            with (
                self.subTest(case=case),
                mock.patch.object(probe, "command", side_effect=self.commands(*case)),
                mock.patch.object(probe.time, "monotonic", side_effect=[0, 0, 2]),
                mock.patch.object(probe.time, "sleep"),
                self.assertRaises(RuntimeError),
            ):
                probe.verify("fixture", "fresh", timeout=1)

    def test_real_product_render_and_independent_oracle_never_use_plain_env(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            config = probe.fixture(source, "renamed-worker", "localhost/probe:1")
            config["HOST"] = "retained.invalid"
            path = root / "persistent/config.yaml"
            probe.private_yaml(path, config)
            password = path.parent / "credentials/password"
            password.parent.mkdir()
            password.write_bytes(b"SyntheticPassword\n")
            output = root / "rendered.yaml"
            probe.render_release(source, path, output, "renamed-worker")
            docs = list(yaml.safe_load_all(output.read_text()))
            secret = next(
                d for d in docs if d["metadata"]["name"] == "renamed-worker-settings"
            )
            self.assertEqual(
                base64.b64decode(secret["data"]["connection-string"]),
                b"Host=retained.invalid;Password=SyntheticPassword",
            )
            manifest = root / "runtime.yaml"
            # Intentionally different: instrument must not derive the oracle from
            # the rendered Secret. A real process would now reject this value.
            probe.instrument(
                output, manifest, "renamed-worker", "independent-value", "fresh"
            )
            docs = list(yaml.safe_load_all(manifest.read_text()))
            oracle = next(
                d for d in docs if d["metadata"]["name"] == "renamed-worker-expected"
            )
            self.assertEqual(
                base64.b64decode(oracle["data"]["value"]), b"independent-value"
            )
            pod = next(d for d in docs if d["kind"] == "Pod")
            self.assertEqual(
                pod["metadata"]["annotations"][
                    "io.podman.annotations.init.container.type"
                ],
                "always",
            )
            for group in ("initContainers", "containers"):
                env = pod["spec"][group][0]["env"]
                self.assertIn("secretKeyRef", env[0]["valueFrom"])
                self.assertNotIn("value", env[0])
                self.assertEqual(env[-2]["value"], "fresh")
            self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)
            self.assertFalse((source / "apps").exists())
            self.assertEqual(password.read_bytes(), b"SyntheticPassword\n")

    def test_cleanup_attempts_remaining_owned_resources_after_stop_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            unit = Path(directory) / "fixture.kube"
            unit.write_text("[Kube]\n")
            calls = []

            def command(arguments, allowed=(0,)):
                calls.append(arguments)
                if arguments[:3] == ["systemctl", "--user", "stop"]:
                    raise RuntimeError("stop failed")
                return types.SimpleNamespace(returncode=0)

            with (
                mock.patch.object(probe, "command", side_effect=command),
                self.assertRaisesRegex(RuntimeError, "cleanup failed"),
            ):
                probe.cleanup(
                    unit, Path(directory) / "private.yaml", "fixture", True, True
                )
            self.assertFalse(unit.exists())
            self.assertIn(
                ["podman", "kube", "down", str(Path(directory) / "private.yaml")], calls
            )
            for suffix in ("-password", "-settings", "-expected"):
                self.assertIn(["podman", "volume", "rm", "fixture" + suffix], calls)
            self.assertFalse(any("-a" in call or "--all" in call for call in calls))

    def test_full_flow_renders_dev_then_relocated_bundle_with_fresh_assertions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stub = root / "bin/podman"
            stub.parent.mkdir()
            stub.write_text(
                "#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\nif sys.argv[1] == 'save': Path(sys.argv[sys.argv.index('-o')+1]).write_bytes(b'archive')\n"
            )
            stub.chmod(0o755)
            calls, observed = [], []
            active = {}
            real_command = probe.command

            def command(arguments, allowed=(0,)):
                calls.append(arguments)
                if arguments[:2] == ["podman", "version"]:
                    return types.SimpleNamespace(
                        returncode=0, stdout="5.8.2\n", stderr=""
                    )
                if arguments == ["systemctl", "--version"]:
                    return types.SimpleNamespace(
                        returncode=0, stdout="systemd 252\n", stderr=""
                    )
                if arguments[0].endswith("/deploy") or arguments[-1].endswith(
                    "/bundle.py"
                ):
                    return real_command(arguments, allowed)
                if arguments[:3] == ["podman", "kube", "play"] or arguments[:3] in (
                    ["systemctl", "--user", "start"],
                    ["systemctl", "--user", "restart"],
                ):
                    manifest = next(root.glob("init-probe-*/runtime.yaml"))
                    docs = list(yaml.safe_load_all(manifest.read_text()))
                    pod = next(d for d in docs if d["kind"] == "Pod")
                    name = pod["metadata"]["name"][: -len("-job")]
                    secret = next(
                        d for d in docs if d["metadata"]["name"] == name + "-settings"
                    )
                    value = base64.b64decode(
                        secret["data"]["connection-string"]
                    ).decode()
                    oracle = next(
                        d for d in docs if d["metadata"]["name"] == name + "-expected"
                    )
                    self.assertEqual(
                        base64.b64decode(oracle["data"]["value"]).decode(), value
                    )
                    active["nonce"] = pod["spec"]["initContainers"][0]["env"][-2][
                        "value"
                    ]
                    observed.append((value, active["nonce"]))
                    if arguments[0] == "systemctl":
                        self.assertFalse(list(root.glob("init-probe-*/source")))
                        self.assertTrue(
                            list(root.glob("init-probe-*/relocated/*/bundle.yaml"))
                        )
                if arguments[:2] == ["podman", "inspect"]:
                    status = "exited" if arguments[-1].endswith("-init") else "running"
                    return types.SimpleNamespace(
                        returncode=0,
                        stdout=json.dumps(
                            [{"State": {"Status": status, "ExitCode": 0}}]
                        ),
                        stderr="",
                    )
                if arguments[:2] == ["podman", "logs"]:
                    return types.SimpleNamespace(
                        returncode=0,
                        stdout="PROBE-OK:" + active["nonce"] + "\n",
                        stderr="",
                    )
                return types.SimpleNamespace(returncode=0, stdout="", stderr="")

            with (
                mock.patch.object(probe.os, "geteuid", return_value=1000),
                mock.patch.object(probe.os, "umask"),
                mock.patch.dict(
                    os.environ,
                    {
                        "XDG_RUNTIME_DIR": str(root),
                        "PATH": str(stub.parent) + os.pathsep + os.environ["PATH"],
                    },
                ),
                mock.patch.object(Path, "home", return_value=root),
                mock.patch.object(probe, "command", side_effect=command),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                probe.run("localhost/test:available")
            self.assertEqual(len(observed), 4)
            self.assertEqual(len({nonce for _, nonce in observed}), 4)
            for index, (value, _) in enumerate(observed):
                host = ("dev-" if index < 2 else "prod-") + str(index % 2) + ".invalid"
                self.assertTrue(value.startswith("Host=" + host + ";Password="))
                self.assertNotIn(value, output.getvalue())
                self.assertFalse(any(value in arg for call in calls for arg in call))
            self.assertEqual(
                len({value.split(";Password=")[1] for value, _ in observed}), 1
            )
            self.assertFalse(list(root.glob("init-probe-*")))
            self.assertFalse(list(root.glob(".config/containers/systemd/*.kube")))
            self.assertEqual(calls[-1][:2], ["podman", "untag"])

    def test_render_errors_withhold_private_subprocess_diagnostics(self):
        with (
            mock.patch.object(
                probe.subprocess,
                "run",
                return_value=types.SimpleNamespace(
                    returncode=1, stdout="PrivateSynthetic", stderr="PrivateSynthetic"
                ),
            ),
            self.assertRaises(RuntimeError) as error,
        ):
            probe.render_release(Path("."), Path("config"), Path("output"), "worker")
        self.assertNotIn("PrivateSynthetic", str(error.exception))

    def test_failed_command_reports_status_without_private_argv_or_output(self):
        with (
            mock.patch.object(
                probe.subprocess,
                "run",
                return_value=types.SimpleNamespace(
                    returncode=125, stdout="PrivateOutput", stderr="PrivateError"
                ),
            ),
            contextlib.redirect_stdout(io.StringIO()) as output,
            self.assertRaisesRegex(
                probe.ProbeFailure, "start Quadlet: command exit=125"
            ) as error,
        ):
            with probe.phase("start Quadlet"):
                probe.command(["podman", "PrivateArgument"])
        for private in ("PrivateOutput", "PrivateError", "PrivateArgument"):
            self.assertNotIn(private, output.getvalue() + str(error.exception))

    def test_phase_hides_unknown_errors_and_timeout_command(self):
        cases = (
            (ValueError("PrivateValue"), "operation failed"),
            (OSError(13, "PrivatePath"), "OS error errno=13"),
            (
                probe.subprocess.TimeoutExpired(
                    ["PrivateArgument"],
                    180,
                    output="PrivateOutput",
                    stderr="PrivateError",
                ),
                "command timed out",
            ),
        )
        for error, expected in cases:
            with (
                self.subTest(expected=expected),
                contextlib.redirect_stdout(io.StringIO()) as output,
                self.assertRaises(probe.ProbeFailure) as caught,
            ):
                with probe.phase("relocate"):
                    raise error
            self.assertEqual(str(caught.exception), "relocate: " + expected)
            self.assertNotIn("Private", output.getvalue())

    def test_cleanup_failure_preserves_primary_failure_and_is_reported(self):
        with (
            contextlib.redirect_stdout(io.StringIO()) as output,
            self.assertRaisesRegex(probe.ProbeFailure, "render: command exit=1"),
        ):
            try:
                with probe.phase("render"):
                    raise probe.ProbeFailure("command exit=1")
            finally:
                with probe.phase("cleanup", cleanup=True):
                    raise RuntimeError("PrivateCleanupError")
        self.assertIn("FAIL: init probe cleanup: operation failed", output.getvalue())
        self.assertNotIn("PrivateCleanupError", output.getvalue())
        # Cleanup alone must still fail the test, never turn an incomplete cleanup green.
        with (
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(probe.ProbeFailure, "cleanup: operation failed"),
        ):
            with probe.phase("cleanup", cleanup=True):
                raise RuntimeError("PrivateCleanupError")

    def test_lab_wires_both_normal_and_renamed_flows(self):
        remote = Path(__file__).with_name("remote.sh").read_text()
        for action in ("database-runtime)", "renamed-generate)"):
            body = remote.split(action, 1)[1].split(";;", 1)[0]
            self.assertIn("python3 acceptance/init_secret_test.py", body)
