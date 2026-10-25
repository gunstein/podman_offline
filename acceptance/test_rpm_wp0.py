"""WP0 harness gates without root, SSH, Proxmox, signing keys or RPM tools."""

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent / "rpm_wp0"
spec = importlib.util.spec_from_file_location("wp0_controller", HERE / "run.py")
assert spec is not None and spec.loader is not None
wp0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wp0)


class PaperSignatureGateTests(unittest.TestCase):
    def verify(self, output, status=0):
        """Run the actual probe's predicate with bounded fake rpmkeys output."""
        source = (HERE / "bootstrap.sh").read_text()
        function = source.split("verify() {\n", 1)[1].split("\n}\n", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "rpmkeys"
            executable.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$WP0_OUTPUT"\nexit "$WP0_STATUS"\n'
            )
            executable.chmod(0o755)
            env = dict(
                os.environ,
                PATH=directory + os.pathsep + os.environ["PATH"],
                WP0_OUTPUT=output,
                WP0_STATUS=str(status),
            )
            return subprocess.run(
                ["bash", "-c", "verify() {\n" + function + "\n}\nverify candidate.rpm"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            ).returncode

    def test_signed_requires_signature_digest_and_success(self):
        self.assertEqual(self.verify("candidate.rpm: digests signatures OK"), 0)
        for output, status in (
            ("candidate.rpm: digests OK", 0),
            ("candidate.rpm: digests SIGNATURES NOT OK", 1),
            ("candidate.rpm: digests signatures OK", 1),
            (
                "candidate.rpm: digests signatures OK\nextra.rpm: digests signatures OK",
                0,
            ),
            ("candidate.rpm: digests signatures OK\nwarning", 0),
        ):
            with self.subTest(output=output, status=status):
                self.assertNotEqual(self.verify(output, status), 0)


class ControllerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.controller = wp0.Investigation.__new__(wp0.Investigation)
        self.controller.pve = mock.Mock()
        self.controller.endpoint = "/nodes/{node}/qemu/PROD_ONLY"
        self.controller.wait_ssh = mock.Mock()

    def test_unauthorized_snapshot_stops_before_api(self):
        with self.assertRaisesRegex(ValueError, "Unauthorized snapshot"):
            self.controller.rollback("clean-dev")
        self.controller.pve.assert_not_called()
        self.controller.pve.request.assert_not_called()
        self.controller.pve.task.assert_not_called()

    def test_rollback_uses_only_configured_prod_endpoint(self):
        self.controller.pve.request.return_value = {"status": "running"}
        self.controller.rollback("clean-agent")
        self.assertEqual(
            self.controller.pve.task.call_args_list,
            [
                mock.call(self.controller.endpoint + "/status/stop"),
                mock.call(self.controller.endpoint + "/snapshot/clean-agent/rollback"),
                mock.call(self.controller.endpoint + "/status/start"),
            ],
        )
        self.controller.wait_ssh.assert_called_once_with("PROD")

    def test_failure_stops_before_start(self):
        self.controller.pve.request.return_value = {"status": "stopped"}
        self.controller.pve.task.side_effect = RuntimeError("rollback failed")
        with self.assertRaisesRegex(RuntimeError, "rollback failed"):
            self.controller.rollback("clean-agent")
        self.controller.pve.task.assert_called_once_with(
            self.controller.endpoint + "/snapshot/clean-agent/rollback"
        )
        self.controller.wait_ssh.assert_not_called()

    def test_key_inventory_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "key-file").write_text("fixture")
            (root / "link").symlink_to(root / "key-file")
            inventory = wp0.key_inventory(root)
            self.assertEqual(set(inventory), {"key-file"})
            (root / "key-file").write_text("changed")
            self.assertNotEqual(wp0.key_inventory(root), inventory)


if __name__ == "__main__":
    unittest.main()
