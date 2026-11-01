"""Image assumptions the harness relies on, checked with real local Podman (backlog 78).

Optional and never a replacement for the lab: these run only with
LOCAL_PODMAN=1 and a working podman, and are skipped otherwise. Each test
starts a disposable container and removes it again.

  LOCAL_PODMAN=1 python3 -B -m unittest test_local_podman
"""

import os
import shutil
import subprocess
import time
import unittest
import uuid

IMAGE = "docker.io/library/postgres:17.11"
ENABLED = os.environ.get("LOCAL_PODMAN") == "1" and shutil.which("podman")


def podman(*args, stdin=None):
    return subprocess.run(
        ["podman", *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


@unittest.skipUnless(ENABLED, "set LOCAL_PODMAN=1 with podman installed")
class PostgresImageTests(unittest.TestCase):
    """seed_content's report login check (remote.sh) depends on the image's pg_hba.conf."""

    def setUp(self):
        self.name = "harness-check-" + uuid.uuid4().hex[:8]
        started = podman(
            "run", "-d", "--rm", "--name", self.name,
            "-e", "POSTGRES_PASSWORD=owner-secret", IMAGE,
        )  # fmt: skip
        self.assertEqual(started.returncode, 0, started.stderr)
        self.addCleanup(podman, "rm", "-f", self.name)
        for _ in range(60):
            if (
                podman("exec", self.name, "pg_isready", "-U", "postgres").returncode
                == 0
            ):
                break
            time.sleep(1)
        else:
            self.fail("postgres did not become ready")
        created = podman(
            "exec", self.name, "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1",
            "-c", "CREATE ROLE report LOGIN PASSWORD 'right-password'",
        )  # fmt: skip
        self.assertEqual(created.returncode, 0, created.stderr)

    def login(self, host, password):
        """Log in as report over host, with the password on stdin like remote.sh."""
        script = (
            'PGPASSWORD="$(cat)"; export PGPASSWORD; exec psql -X -A -t -h ' + host
            + ' -U report -d postgres -c "SELECT 1"'
        )  # fmt: skip
        return podman("exec", "-i", self.name, "sh", "-ec", script, stdin=password)

    def test_loopback_trusts_and_the_container_address_checks_the_password(self):
        # Why the check may not use 127.0.0.1: any password is accepted there.
        self.assertEqual(self.login("127.0.0.1", "wrong").returncode, 0)
        address = podman("exec", self.name, "hostname", "-i").stdout.split()
        address = [item for item in address if not item.startswith(("127.", "::1"))]
        self.assertTrue(address, "the container has no non-loopback address")
        refused = self.login(address[0], "wrong")
        self.assertNotEqual(refused.returncode, 0)
        # check_report_login (remote.sh) requires exactly this refusal.
        self.assertIn(
            'password authentication failed for user "report"', refused.stderr
        )
        self.assertEqual(self.login(address[0], "right-password").returncode, 0)


if __name__ == "__main__":
    unittest.main()
