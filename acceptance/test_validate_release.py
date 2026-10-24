"""The lab requires ./deploy.sh validate to pass before every install (backlog 23)."""

import subprocess
import unittest
from pathlib import Path


class ValidateReleaseTests(unittest.TestCase):
    def run_helper(self, output, status=0):
        remote = Path(__file__).with_name("remote.sh").read_text()
        start = remote.index("validate_release() {")
        helper = remote[start : remote.index("\n}\n", start) + 3]
        stub = f"sudo() {{ printf '%s\\n' {output!r}; return {status}; }}\n"
        return subprocess.run(
            [
                "bash",
                "-c",
                "set -euo pipefail\nproduct_name=myproduct\nservice_user=myproduct-ops\nbundle=orders\nproduct=/r\n"
                + stub
                + helper
                + "validate_release",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_passes_only_on_the_bundles_ok_line(self):
        ok = "[OK] validated orders; nothing written, no Podman or systemd commands"
        self.assertEqual(self.run_helper(ok).returncode, 0)
        for output, status in (
            ("[OK] validated inventory; nothing written", 0),
            ("ERROR: 1 validation finding(s)", 1),
            ("", 0),
        ):
            with self.subTest(output=output):
                result = self.run_helper(output, status)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
