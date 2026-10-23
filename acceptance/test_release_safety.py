"""Probe failures identify their phase without exposing captured private output."""

import contextlib
import io
import sys
import types
import unittest
from unittest import mock

import release_safety_test as probe


class ReleaseSafetyDiagnosticsTests(unittest.TestCase):
    def test_restorecon_failure_names_phase_and_exit_but_hides_output(self):
        helper = "ancestors = lambda path: None\npublished = lambda path: {}\n"
        failure = types.SimpleNamespace(
            returncode=23, stdout="private-stdout", stderr="private-password"
        )
        with mock.patch.object(probe, "HELPER_SOURCE", helper), mock.patch.object(
            probe.os, "geteuid", return_value=0
        ), mock.patch.object(probe.pwd, "getpwnam"), mock.patch.object(
            probe.subprocess, "run", return_value=failure
        ) as command, mock.patch.object(
            sys, "argv", ["probe", "/opt/shop/releases/shop-worker-1.2.3", "shop"]
        ), self.assertRaises(probe.ProbeError) as error:
            probe.run()
        self.assertEqual(
            command.call_args.args[0],
            ["restorecon", "-R", "/opt/shop/releases/shop-worker-1.2.3"],
        )
        self.assertEqual(
            str(error.exception),
            "SELinux restorecon of protected release: restorecon exit=23",
        )
        self.assertNotIn("private", probe.error_message(error.exception))

    def test_phase_hides_external_exception_values_and_reports_errno(self):
        for error in (
            OSError(13, "secret-value", "/credentials/private"),
            ValueError("secret-value"),
            KeyError("secret-value"),
        ):
            with self.subTest(kind=type(error).__name__):
                with self.assertRaises(probe.ProbeError) as observed:
                    with probe.phase("service-user deploy validate"):
                        raise error
                text = probe.error_message(observed.exception)
                self.assertIn("service-user deploy validate:", text)
                self.assertNotIn("secret-value", text)
                self.assertNotIn("credentials", text)
                if isinstance(error, OSError):
                    self.assertIn("errno=13", text)

    def test_successful_phase_preserves_normal_pass_output(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), probe.phase("host facts"):
            print("PASS: host facts")
        self.assertEqual(output.getvalue(), "PASS: host facts\n")
