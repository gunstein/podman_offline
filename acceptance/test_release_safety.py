"""Probe failures identify their phase without exposing captured private output."""

import contextlib
import io
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

import release_safety_test as probe


class ReleaseSafetyDiagnosticsTests(unittest.TestCase):
    def test_relabel_requires_a_changed_label_and_restores_it_even_on_failure(self):
        path = Path("/opt/shop/releases/shop-worker-1.2.3")
        original = b"system_u:object_r:usr_t:s0"
        changed = b"system_u:object_r:tmp_t:s0"
        for labels, expected in (
            ([original, changed, original], None),
            ([original, original], "chcon did not change"),
            ([original, changed, changed], "did not restore"),
        ):
            with (
                self.subTest(labels=labels),
                mock.patch.object(probe.os, "getxattr", side_effect=labels),
                mock.patch.object(
                    probe.subprocess,
                    "run",
                    return_value=types.SimpleNamespace(returncode=0),
                ) as command,
            ):
                if expected:
                    with self.assertRaisesRegex(probe.ProbeError, expected):
                        probe.relabel_release(path)
                else:
                    probe.relabel_release(path)
                self.assertEqual(
                    [call.args[0] for call in command.call_args_list],
                    [
                        ["chcon", "-t", "tmp_t", str(path / "deployment/common.py")],
                        ["restorecon", "-R", str(path)],
                    ],
                )

    def test_bad_signature_probe_accepts_only_gpgv_signature_failure(self):
        class ReleaseError(Exception):
            pass

        class CommandError(ReleaseError):
            def __init__(self, executable, returncode):
                self.executable, self.returncode = executable, returncode

        for error, accepted in (
            (CommandError("gpgv", 1), True),
            (CommandError("gpgv", 2), True),
            (CommandError("gpgv", 127), False),
            (CommandError("fapolicyd-cli", 1), False),
            (ReleaseError("lock failed"), False),
            (None, False),
        ):
            publish = mock.Mock(side_effect=error)
            namespace = {"publish": publish, "CommandError": CommandError}
            with self.subTest(error=error):
                if accepted:
                    probe.reject_bad_signature(namespace, "archive")
                elif isinstance(error, ReleaseError) and not isinstance(
                    error, CommandError
                ):
                    with self.assertRaisesRegex(ReleaseError, "lock failed"):
                        probe.reject_bad_signature(namespace, "archive")
                else:
                    with self.assertRaises(probe.ProbeError):
                        probe.reject_bad_signature(namespace, "archive")
                publish.assert_called_once_with("archive")

    def test_restorecon_failure_names_phase_and_exit_but_hides_output(self):
        helper = "ancestors = lambda path: None\npublished = lambda path: {}\n"
        failure = types.SimpleNamespace(
            returncode=23, stdout="private-stdout", stderr="private-password"
        )
        success = types.SimpleNamespace(returncode=0)
        labels = [b"system_u:object_r:usr_t:s0", b"system_u:object_r:tmp_t:s0"]
        with (
            mock.patch.object(probe.os, "getxattr", side_effect=labels),
            mock.patch.object(probe, "HELPER_SOURCE", helper),
            mock.patch.object(probe.os, "geteuid", return_value=0),
            mock.patch.object(probe.pwd, "getpwnam") as account,
            mock.patch.object(
                probe.subprocess, "run", side_effect=[success, failure]
            ) as command,
            mock.patch.object(
                sys,
                "argv",
                [
                    "probe",
                    "/var/lib/shop/releases/shop-worker-1.2.3",
                    "shop",
                    "/archive",
                    "shop-ops",
                ],
            ),
            self.assertRaises(probe.ProbeError) as error,
        ):
            probe.run()
        self.assertEqual(
            command.call_args.args[0],
            ["restorecon", "-R", "/var/lib/shop/releases/shop-worker-1.2.3"],
        )
        # The separate runtime account, never a user named after the product.
        account.assert_called_once_with("shop-ops")
        self.assertEqual(
            str(error.exception),
            "SELinux restorecon of protected release: restorecon exit=23",
        )
        self.assertNotIn("private", probe.error_message(error.exception))

    def test_validate_runs_as_the_runtime_account_not_the_product(self):
        command = probe.validate_command(
            Path("/var/lib/shop/releases/shop-worker-1.2.3"), "shop-ops"
        )
        self.assertEqual(command[:5], ["sudo", "-n", "-H", "-u", "shop-ops"])
        self.assertNotIn("shop", command[:5])

    def test_remote_passes_the_runtime_account_separately(self):
        remote = (Path(__file__).with_name("remote.sh")).read_text()
        line = next(
            line for line in remote.splitlines() if "release_safety_source |" in line
        )
        self.assertTrue(line.rstrip().endswith('"$service_user"'), line)
        self.assertIn('service_user="${product_name:0:27}-ops"', remote)

    def test_phase_hides_external_exception_values_and_reports_errno(self):
        for error in (
            OSError(13, "secret-value", "/credentials/private"),
            ValueError("secret-value"),
            KeyError("secret-value"),
        ):
            with self.subTest(kind=type(error).__name__):
                with (
                    self.assertRaises(probe.ProbeError) as observed,
                    probe.phase("service-user deploy.sh validate"),
                ):
                    raise error
                text = probe.error_message(observed.exception)
                self.assertIn("service-user deploy.sh validate:", text)
                self.assertNotIn("secret-value", text)
                self.assertNotIn("credentials", text)
                if isinstance(error, OSError):
                    self.assertIn("errno=13", text)

    def test_successful_phase_preserves_normal_pass_output(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), probe.phase("host facts"):
            print("PASS: host facts")
        self.assertEqual(output.getvalue(), "PASS: host facts\n")
