"""Current platform CLI and external systemd diagnostic names."""

import contextlib
import io
import unittest
from unittest import mock

import test_acceptance as base
import test_components as components


class PlatformHarnessTests(unittest.TestCase):
    """Unsupported historical scenario flags never start a current lab run."""

    def test_systemd_core_dump_remains_an_external_result_name(self):
        diagnostics = components.guest_code("LAUNCH_DIAGNOSTICS")
        self.assertIsNotNone(
            diagnostics["RESULT_ERROR"].fullmatch("Failed with result 'core-dump'")
        )
        self.assertIsNone(
            diagnostics["RESULT_ERROR"].fullmatch("Failed with result 'platform-dump'")
        )

    def test_unsupported_historical_flags_fail_before_lab_or_run_creation(self):
        for flag in ("--legacy-refusal", "--upgrade-020"):
            with (
                self.subTest(flag=flag),
                mock.patch.object(
                    base.runner.sys,
                    "argv",
                    ["acceptance.py", "--run", "old", flag, "run"],
                ),
                mock.patch.object(base.runner, "Run") as create,
                contextlib.redirect_stderr(io.StringIO()) as errors,
                self.assertRaises(SystemExit) as caught,
            ):
                base.runner.main()
            self.assertEqual(caught.exception.code, 2)
            create.assert_not_called()
            self.assertIn("unrecognized arguments", errors.getvalue())
