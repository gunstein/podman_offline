"""The lab's audit digest check (backlog 88) with Podman stubbed; not lab results."""

import contextlib
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_components import REMOTE, guest_code

KEY = b"Synthetic0Key1For2Digest3Tests45"
DIGEST = hashlib.sha256(KEY).hexdigest().encode()


def done(stdout, code=0):
    return subprocess.CompletedProcess([], code, stdout, b"")


class AuditDigestHarnessTests(unittest.TestCase):
    def run_check(self, mode, product, replies, installed=()):
        code = guest_code("AUDIT_DIGEST")
        with tempfile.TemporaryDirectory() as state:
            (Path(state) / "installed").mkdir()
            for name in installed:
                (Path(state) / "installed" / name).write_text("1.0.0\n")
            run = mock.Mock(side_effect=list(replies))
            with (
                mock.patch.object(subprocess, "run", run),
                mock.patch.dict(
                    os.environ, {"PRODUCT_NAME": product, "PRODUCT_STATE": state}
                ),
                mock.patch.object(sys, "argv", ["audit", mode]),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                code["main"]()
        return output.getvalue(), run

    def test_both_containers_agree_and_only_a_verdict_is_printed(self):
        for product, identity, app in (
            ("myproduct", "identity", "app1"),
            ("shop", "login-service", "orders"),
        ):
            with self.subTest(product=product):
                output, run = self.run_check(
                    "dev", product, [done(KEY + b"\n"), done(DIGEST + b"\n")]
                )
                self.assertEqual(
                    [call.args[0] for call in run.call_args_list],
                    [
                        [
                            "podman",
                            "exec",
                            identity + "-server-app",
                            "printenv",
                            "Audit__Key",
                        ],
                        [
                            "podman",
                            "exec",
                            app + "-todo-backend",
                            "printenv",
                            "AUDIT_KEY_SHA256",
                        ],
                    ],
                )
                self.assertIn("PASS: " + app + " has the SHA-256", output)
                self.assertNotIn(KEY.decode(), output)
                self.assertNotIn(DIGEST.decode(), output)

    def test_a_wrong_digest_or_unreadable_value_fails_without_values(self):
        for replies in (
            [done(KEY + b"\n"), done(b"0" * 64 + b"\n")],
            [done(KEY + b"\n"), done(DIGEST + b"x\n")],
            [done(b"", 125)],
        ):
            with (
                self.subTest(replies=len(replies)),
                self.assertRaises(RuntimeError) as failure,
            ):
                self.run_check("dev", "myproduct", replies)
            self.assertNotIn(KEY.decode(), str(failure.exception))
            self.assertNotIn(DIGEST.decode(), str(failure.exception))

    def test_prod_without_the_app_installed_is_not_applicable(self):
        output, run = self.run_check("prod", "myproduct", [], installed=("platform",))
        self.assertIn("not applicable; app1 is not installed", output)
        run.assert_not_called()
        output, _ = self.run_check(
            "prod",
            "myproduct",
            [done(KEY + b"\n"), done(DIGEST + b"\n")],
            installed=("identity", "app1"),
        )
        self.assertIn("PASS: app1 has the SHA-256", output)

    def test_every_config_layer_check_is_followed_by_the_digest_check(self):
        for mode in ("dev", "prod"):
            self.assertEqual(
                REMOTE.count("    config_layers " + mode + "\n"),
                REMOTE.count(
                    "    config_layers " + mode + "\n    audit_digest " + mode + "\n"
                ),
            )


if __name__ == "__main__":
    unittest.main()
