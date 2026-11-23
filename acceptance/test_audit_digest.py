"""The audit key handoff check (audit-digest) with Podman stubbed; not lab results."""

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

    def refused(self, replies, message):
        with self.assertRaisesRegex(RuntimeError, message) as failure:
            self.run_check("dev", "myproduct", replies)
        for value in (KEY, DIGEST, DIGEST.upper()):
            self.assertNotIn(value.decode(), str(failure.exception))

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

    def test_a_retained_key_of_another_length_is_compared_by_its_bytes(self):
        key = b"retained-key-of-another-length"
        digest = hashlib.sha256(key).hexdigest().encode()
        output, _ = self.run_check(
            "dev", "myproduct", [done(key + b"\n"), done(digest + b"\n")]
        )
        self.assertIn("PASS: app1 has the SHA-256", output)
        self.assertNotIn(key.decode(), output)

    def test_a_wrong_digest_is_refused_without_values(self):
        for digest in (b"0" * 64, DIGEST + b"x", DIGEST.upper(), b""):
            with self.subTest(digest=digest[:8]):
                self.refused(
                    [done(KEY + b"\n"), done(digest + b"\n")],
                    "AUDIT_KEY_SHA256 is not the lowercase SHA-256",
                )

    def test_a_missing_or_empty_value_is_named_clearly(self):
        self.refused(
            [done(b"", 1)],
            "Audit__Key is not set in identity-server-app; this revision",
        )
        self.refused(
            [done(KEY + b"\n"), done(b"", 1)],
            "AUDIT_KEY_SHA256 is not set in app1-todo-backend",
        )
        self.refused([done(b"\n")], "identity's Audit__Key is empty")
        self.refused([done(b"", 125)], r"Cannot read Audit__Key .*\(exit 125\)")

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

    def test_it_is_a_separate_action_not_part_of_the_standard_run(self):
        """main does not deliver the variables yet, so no scenario calls it."""
        self.assertIn("audit-digest)\n    # Separate check", REMOTE)
        self.assertEqual(REMOTE.count("    audit_digest "), 1)  # only in its action
        acceptance = (Path(__file__).with_name("acceptance.py")).read_text()
        self.assertNotIn("audit-digest", acceptance)


if __name__ == "__main__":
    unittest.main()
