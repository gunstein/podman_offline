"""The normal scenario's dev-seed step (backlog 81) without lab access.

The step runs against a stand-in seed-db.sh and podman that behave like the
product, with one wrong behaviour at a time; each must fail the step.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

from test_acceptance import shell_code

REMOTE = Path(__file__).with_name("remote.sh").read_text()

# $W/rows holds demo_seed's dev-seed rows; $W/starts the container start.
SEED_DB = r"""#!/bin/bash
case $2 in
*insert.sql)
    if [[ $FAULT != norow ]] && { [[ $FAULT == duplicate ]] || ! grep -qx 'dev-seed|v1' "$W/rows"; }; then
        echo 'dev-seed|v1' >> "$W/rows"
    fi
    [[ $FAULT != restart ]] || echo restarted > "$W/starts"
    [[ $FAULT != credential ]] || echo changed > build/dev/app1/credentials/database/password
    echo "[OK] seeded app1 from $2";;
*failing.sql)
    [[ $FAULT != partial ]] || echo 'dev-seed-partial|x' >> "$W/rows"
    [[ $FAULT != succeed ]] || { echo "[OK] seeded app1 from $2"; exit 0; }
    line=' at line 3'
    [[ $FAULT != noline ]] || line=
    echo "ERROR: seeding app1 from $2 failed: the SQL failed$line; fix the SQL; its changes were rolled back${MARKER:-}" >&2
    exit 1;;
esac
"""
PODMAN = r"""#!/bin/bash
case $1 in
ps) echo "c1 app1-postgres-db $(cat "$W/starts")";;
exec) sort "$W/rows";;
esac
"""


class DevSeedStepTests(unittest.TestCase):
    def run_step(self, fault=""):
        work = Path(self.enterContext(tempfile.TemporaryDirectory()))
        src = work / "src"
        for path, text in (
            ("src/dev/seed-db.sh", SEED_DB),
            ("bin/podman", PODMAN),
            ("src/build/dev/app1/credentials/database/password", "secret\n"),
            ("rows", ""),
            ("starts", "started"),
        ):
            (work / path).parent.mkdir(parents=True, exist_ok=True)
            (work / path).write_text(text)
        for name in ("src/dev/seed-db.sh", "bin/podman"):
            (work / name).chmod(0o755)
        script = (
            "set -euo pipefail\n"
            + shell_code(REMOTE, function="expect_refusal")
            + f"\nbase={work} src={src}\n"
            + shell_code(REMOTE, action="dev-seed")
        )
        return subprocess.run(
            ["bash", "-c", script],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
            env={
                "PATH": f"{work / 'bin'}:/usr/bin:/bin",
                "W": str(work),
                "FAULT": fault,
                "MARKER": " PRIVATE_MARKER" if fault == "marker" else "",
            },
        )

    def test_the_step_passes_for_the_products_behaviour(self):
        result = self.run_step()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: seed-db inserted once", result.stdout)

    def test_the_step_fails_for_each_wrong_result(self):
        for fault, message in (
            ("norow", "after the first seed demo_seed lacks exactly one dev-seed row"),
            ("duplicate", "after the repeated seed demo_seed lacks exactly one"),
            ("succeed", "succeeded"),
            ("noline", "the SQL failure does not name line 3"),
            ("marker", "the failure shows SQL text"),
            ("partial", "the failed seed left a row"),
            ("restart", "seeding replaced or added a container"),
            ("credential", "seeding changed a credential"),
        ):
            with self.subTest(fault):
                result = self.run_step(fault)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("FAIL: ", result.stdout)
                self.assertIn(message, result.stdout)

    def test_the_step_has_its_action(self):
        self.assertRegex(REMOTE, r"(?m)^dev-seed\)$")
        self.assertIn('seed_dir="$base/dev seed"', REMOTE)
