"""Current platform orchestration preserves historical core sources and refusal evidence."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import legacy_refusal
import test_acceptance as base
import test_components as components
import upgrade_020
import upgrade_020_guest


class PlatformHarnessTests(unittest.TestCase):
    """Historical successful upgrades remain separate from the new refusal boundary."""

    def test_systemd_core_dump_remains_an_external_result_name(self):
        diagnostics = components.guest_code("LAUNCH_DIAGNOSTICS")
        self.assertIsNotNone(
            diagnostics["RESULT_ERROR"].fullmatch("Failed with result 'core-dump'")
        )
        self.assertIsNone(
            diagnostics["RESULT_ERROR"].fullmatch("Failed with result 'platform-dump'")
        )

    def test_refusal_evidence_requires_absent_new_platform_files_and_volumes(self):
        code = components.guest_code("LEGACY_REFUSAL")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code["new_paths"] = [root / "platform", root / "installed/platform"]
            with mock.patch.object(
                code["subprocess"], "run", return_value=mock.Mock(returncode=1)
            ) as host:
                code["no_parallel_platform"]()
                self.assertEqual(host.call_count, 4)
                (root / "platform").mkdir()
                host.reset_mock()
                with self.assertRaisesRegex(SystemExit, "parallel platform files"):
                    code["no_parallel_platform"]()
                host.assert_not_called()
                (root / "platform").rmdir()
                host.return_value.returncode = 125
                with self.assertRaisesRegex(SystemExit, "absence cannot be verified"):
                    code["no_parallel_platform"]()

    def test_historical_upgrade_flag_refuses_before_lab_or_run_creation(self):
        with (
            mock.patch.object(
                base.runner.sys,
                "argv",
                ["acceptance.py", "--run", "old", "--upgrade-020", "run"],
            ),
            mock.patch.object(base.runner, "Run") as create,
            contextlib.redirect_stderr(io.StringIO()) as errors,
            self.assertRaises(SystemExit) as caught,
        ):
            base.runner.main()
        self.assertEqual(caught.exception.code, 2)
        create.assert_not_called()
        self.assertIn("511099e", errors.getvalue())
        self.assertIn("--legacy-refusal", errors.getvalue())

    def test_refusal_flow_installs_real_old_sources_then_compares_state_and_user_data(
        self,
    ):
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(base.runner, "RUNS", Path(directory)),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            run = base.runner.Run("refusal", "unused")
            run.meta.update(version="0.3.0", platform_version="0.3.0")
            run.cfg = {
                key: "fixture"
                for key in ("LAB_CIDR", "PROD_IP", "PROD_HOST", "HTTPS_PORT")
            }
            run.revision = "new-fixture"
            run.step = mock.Mock(side_effect=lambda name, action: action())
            for name in (
                "readiness",
                "reset",
                "source",
                "transfer",
                "credentials",
                "guest",
                "ssh",
            ):
                setattr(run, name, mock.Mock())
            run.command = mock.Mock(
                return_value="# unchanged core-layout historical remote\n"
            )
            with mock.patch.object(upgrade_020, "guest") as private_check:
                legacy_refusal.execute(run)
            run.command.assert_called_once_with(
                [
                    "git",
                    "show",
                    legacy_refusal.HISTORICAL_HARNESS + ":acceptance/remote.sh",
                ]
            )
            self.assertEqual(upgrade_020_guest.COMPONENTS, ("core", "app1", "app2"))
            run.credentials.assert_called_once_with(component="core")
            self.assertEqual(
                run.transfer.call_args_list,
                [
                    mock.call("0.2.0", bundle="app1"),
                    mock.call("0.2.0", bundle="app2"),
                    mock.call(bundle="platform"),
                ],
            )
            names = [call.args[0] for call in run.step.call_args_list]
            self.assertLess(names.index("06-baseline"), names.index("08-refusal"))
            self.assertLess(names.index("08-refusal"), names.index("08-state"))
            self.assertLess(names.index("08-state"), names.index("08-e2e"))
            private_check.assert_has_calls(
                [mock.call(run, "baseline"), mock.call(run, "trust-app1")]
            )
            self.assertTrue(run.finished)
            self.assertEqual(run.meta["legacy_revision"], upgrade_020.LEGACY_REVISION)
