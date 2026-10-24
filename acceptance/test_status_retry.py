"""Negative gates and opt-in wiring for the real status failure/retry probe."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import status_retry_test as probe
import test_acceptance as base
import yaml


class StatusRetryProbeTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.release, self.state, self.config_root = (
            root / "release",
            root / "state",
            root / "config",
        )
        self.component, self.product, self.version = "orders", "cedar", "1.0.0"
        self.config = self.state / "orders/config.yaml"
        self.output = self.config_root / "containers/systemd/cedar-orders.yaml"
        self.marker = self.state / "installed/orders"
        self.pending = self.state / "pending-operation.json"
        for path in (
            self.config,
            self.output,
            self.marker,
            self.release / "deployment/code.py",
            self.release / "quadlet/template.kube",
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(
            yaml.safe_dump({probe.KEY: "original", "PRIVATE": "DoNotPrint"})
        )
        self.original = self.config.read_bytes()
        self.marker.write_text("1.0.0\n")
        (self.release / "bundle.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "orders",
                    "product": "cedar",
                    "version": "1.0.0",
                    "upgrade": "always",
                }
            )
        )
        self.live = "original"
        self.ident = "old-container"
        self.render()
        self.bad = None
        self.installs = 0
        self.trace = []
        self.stack.enter_context(
            mock.patch.dict(
                os.environ,
                PRODUCT_STATE=str(self.state),
                XDG_CONFIG_HOME=str(self.config_root),
            )
        )
        self.stack.enter_context(
            mock.patch.object(probe.os, "geteuid", return_value=1001)
        )
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(
            mock.patch.object(probe.subprocess, "run", side_effect=self.command)
        )

    def render(self):
        value = yaml.safe_load(self.config.read_text())[probe.KEY]
        self.output.write_text(
            yaml.safe_dump({"kind": "ConfigMap", "data": {probe.KEY: value}})
        )

    def report(self):
        pending = (
            {"operation": "install", "component": "orders", "owners": []}
            if self.pending.exists()
            else None
        )
        return {
            "product": "cedar",
            "pending": pending,
            "components": [
                {
                    "name": "orders",
                    "version": "1.0.0",
                    "recorded_version": "1.0.0",
                    "state": "active",
                    "complete": pending is None,
                }
            ],
        }

    def command(self, args, **kwargs):
        self.trace.append(args)
        self.assertFalse(kwargs["check"])
        self.assertEqual(kwargs["timeout"], 300)
        code, output = 0, ""
        if args[-2:] == ["status", "--json"]:
            data = self.report()
            code = 1 if self.pending.exists() else 0
            if self.pending.exists():
                if self.bad == "false-success":
                    code, data["components"][0]["complete"] = 0, True
                if self.bad == "missing-pending":
                    data["pending"] = None
                if self.bad == "owners":
                    assert data["pending"] is not None
                    data["pending"]["owners"] = ["gateway"]
                if self.bad == "status-write":
                    self.pending.write_text("changed by status")
            output = json.dumps(data)
        elif kwargs.get("input") == probe.FAIL_INSTALL:
            self.render()
            self.pending.write_text(
                json.dumps(
                    {
                        "operation": "install",
                        "component": "orders",
                        "product": "cedar",
                        "owners": [],
                    }
                )
            )
            code, output = 73, probe.INJECTED + "\n"
            if self.bad == "wrong-failure":
                output = "PrivateUnrelatedFailure"
            if self.bad == "yaml":
                self.output.write_text("{}")
            if self.bad == "early-restart":
                self.ident = "unexpected-container"
            if self.bad == "marker":
                self.marker.write_text("1.0.1\n")
        elif args[-1] == "install":
            self.installs += 1
            self.render()
            value = yaml.safe_load(self.config.read_text())[probe.KEY]
            self.live = (
                "stale" if self.bad == "runtime" and self.installs == 1 else value
            )
            self.ident = "replacement-" + str(self.installs)
            if self.pending.exists():
                self.pending.unlink()
            if self.bad == "cleanup" and self.installs == 2:
                code = 1
        elif args[:2] == ["podman", "exec"]:
            output = self.live + "\n"
        elif args[:2] == ["podman", "inspect"]:
            output = self.ident + "\n"
        else:
            self.fail("unexpected command " + repr(args))
        return subprocess.CompletedProcess(args, code, output, "PrivateStderr")

    def test_complete_probe_injects_only_attempt_then_uses_normal_retry_and_restores(
        self,
    ):
        probe.run(self.release, self.component)
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(self.live, "original")
        self.assertFalse(self.pending.exists())
        self.assertEqual(self.installs, 2)  # Retry then restore, both ordinary CLI.
        self.assertIn([sys.executable, "-I", "-B", "-", str(self.release)], self.trace)
        self.assertEqual(sum(args[-1] == "install" for args in self.trace), 2)

    def test_false_success_and_each_missing_proof_fail_and_restore_config(self):
        for bad in (
            "false-success",
            "missing-pending",
            "owners",
            "status-write",
            "wrong-failure",
            "yaml",
            "early-restart",
            "marker",
            "runtime",
            "cleanup",
        ):
            with self.subTest(bad=bad):
                self.bad, self.installs = bad, 0
                self.ident, self.live = "old-container", "original"
                self.marker.write_text("1.0.0\n")
                if self.pending.exists():
                    self.pending.unlink()
                self.render()
                with self.assertRaises(probe.ProbeError):
                    probe.run(self.release, self.component)
                self.assertEqual(self.config.read_bytes(), self.original)

    def test_injection_runs_real_transport_except_exact_daemon_reload(self):
        for fail_before in (False, True):
            with self.subTest(fail_before=fail_before):
                calls = []

                def lifecycle(fail_before=fail_before):
                    subprocess.run(
                        ["systemctl", "--user", "show-environment"], check=True
                    )
                    if fail_before:
                        return 1
                    try:
                        subprocess.run(
                            ["systemctl", "--user", "daemon-reload"], check=True
                        )
                    except subprocess.CalledProcessError:
                        return 1
                    self.fail("injection missed")

                cli = types.SimpleNamespace(main=lifecycle)
                package = types.ModuleType("deployment")
                vars(package)["cli"] = cli
                with contextlib.ExitStack() as stack:
                    stack.enter_context(
                        mock.patch.dict(sys.modules, deployment=package)
                    )
                    stack.enter_context(
                        mock.patch.object(sys, "argv", ["-", str(self.release)])
                    )
                    stack.enter_context(mock.patch.object(sys, "path", list(sys.path)))
                    stack.enter_context(
                        mock.patch.object(
                            subprocess,
                            "run",
                            side_effect=lambda args, calls=calls, **kw: calls.append(
                                args
                            ),
                        )
                    )
                    with self.assertRaises(SystemExit) as error:
                        exec(probe.FAIL_INSTALL, {})  # noqa: S102 - repository-owned probe
                self.assertEqual(error.exception.code, 74 if fail_before else 73)
                self.assertEqual(calls, [["systemctl", "--user", "show-environment"]])

    def test_private_failures_are_withheld(self):
        with (
            mock.patch.object(probe, "run", side_effect=ValueError("PrivateValue")),
            mock.patch.object(sys, "argv", ["probe", "/release", "orders"]),
            contextlib.redirect_stderr(io.StringIO()) as output,
        ):
            self.assertEqual(probe.main(), 1)
        self.assertNotIn("PrivateValue", output.getvalue())


class StatusRetryWiringTests(unittest.TestCase):
    def test_cli_selects_probe_and_refuses_an_unsupported_scenario_before_run(self):
        for arguments, accepted in (
            (["--status-retry"], True),
            (["--status-retry", "--renamed-product"], True),
            (["--status-retry", "--platform-help-only"], False),
        ):
            with (
                self.subTest(arguments=arguments),
                mock.patch.object(base.runner, "Run") as constructor,
                mock.patch.object(
                    sys,
                    "argv",
                    ["acceptance.py", "--run", "probe"] + arguments + ["run"],
                ),
                mock.patch.object(base.runner.os, "umask"),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                if accepted:
                    constructor.return_value.report.return_value = True
                    self.assertEqual(base.runner.main(), 0)
                    self.assertTrue(constructor.return_value.status_retry)
                    constructor.return_value.execute.assert_called_once_with()
                else:
                    with self.assertRaises(SystemExit) as error:
                        base.runner.main()
                    self.assertEqual(error.exception.code, 2)
                    constructor.assert_not_called()

    def test_opt_in_runs_after_install_before_baselines_for_normal_and_renamed(self):
        for renamed, component in ((False, "app1"), (True, "orders")):
            for enabled in (False, True):
                with (
                    self.subTest(renamed=renamed, enabled=enabled),
                    tempfile.TemporaryDirectory() as directory,
                    mock.patch.object(base.runner, "RUNS", Path(directory)),
                ):
                    run = base.runner.Run("test", "unused")
                    run.renamed_product, run.status_retry = renamed, enabled
                    run.meta["bundles_built"] = [
                        "gateway",
                        "login-service",
                        "orders",
                        "inventory",
                        "manual",
                    ]
                    observed = []

                    # Execute real orchestration; stop just after our insertion point.
                    def step(name, action, observed=observed):
                        observed.append(name)
                        if name in ("07-registry-offline", "08-credentials"):
                            raise StopIteration
                        if name == "07-status-retry":
                            action()

                    run.step, run.guest = step, mock.Mock()
                    with self.assertRaises(StopIteration):
                        run.execute()
                    self.assertEqual("07-status-retry" in observed, enabled)
                    if enabled:
                        self.assertLess(
                            observed.index("06-install-" + component),
                            observed.index("07-status-retry"),
                        )
                        run.guest.assert_called_once_with(
                            "PROD", "status-retry", bundle=component
                        )

    def test_guest_embeds_controller_probe_and_runs_as_runtime_account_over_stdin(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(base.runner, "RUNS", Path(directory)),
        ):
            run = base.runner.Run("test", "unused")
            run.cfg = {
                "LAB_CIDR": "192.0.2.0/24",
                "PROD_IP": "192.0.2.2",
                "PROD_HOST": "example.invalid",
                "HTTPS_PORT": "8443",
            }
            run.ssh = mock.Mock(return_value="")
            run.guest("PROD", "status-retry", "1.0.0", bundle="app1")
            script = run.ssh.call_args.args[1]
        body = base.shell_code(script, action="status-retry")
        self.assertIn(
            'status_retry_source | as_product python3 -I -B - "$product" "$bundle"',
            body,
        )
        function = base.shell_code(script, function="status_retry_source")
        result = subprocess.run(
            ["bash", "-se"],
            input=function + "\nstatus_retry_source\n",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, Path(probe.__file__).read_text() + "\n")
        self.assertNotIn("# STATUS_RETRY_BODY", script)
