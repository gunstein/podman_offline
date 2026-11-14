"""The normal scenario's dev-seed step (backlog 81) without lab access.

The step runs against a stand-in seed-db.sh and podman that act on what the
step actually sends: the stand-in seed-db.sh runs the SQL file's statements
as one transaction on $W/rows, and the stand-in podman answers the step's
query for the names it asks about, in the container it names. One wrong
behaviour at a time (FAULT) must fail the step, and nothing private
(PRIVATE_MARKER) may reach the step's own output.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

from test_acceptance import shell_code

REMOTE = Path(__file__).with_name("remote.sh").read_text()

SEED_DB = r"""#!/usr/bin/env python3
import os, re, sys
from pathlib import Path

work, fault = Path(os.environ["W"]), os.environ["FAULT"]
rows = (work / "rows").read_text().split()
component, sql = sys.argv[1:]
if component != "app1":
    sys.exit("stand-in: wrong component")
INSERT = re.compile(
    r"INSERT INTO demo_seed \(name, value\) VALUES \('([^']*)', '([^']*)'\)"
    r"( ON CONFLICT \(name\) DO NOTHING)?;"
)


def fail(line):
    where = "" if fault == "noline" else f" at line {line}"
    marker = " PRIVATE_MARKER" if fault == "marker" else ""
    print(f"ERROR: seeding app1 from {sql} failed: the SQL failed{where}; "
          f"fix the SQL; its changes were rolled back{marker}", file=sys.stderr)
    sys.exit(1)


pending = []
for number, line in enumerate(Path(sql).read_text().splitlines(), 1):
    found = INSERT.fullmatch(line)
    if found:
        name, value, ignore = found.groups()
        if any(row.split("|")[0] == name for row in rows + pending):
            if ignore and fault != "duplicate":
                continue
            if not ignore:
                fail(number)
        if fault != "norow":
            pending.append(name + "|" + value)
    elif line == "SELECT 1;":
        pass
    elif line == "SELECT 'PRIVATE_MARKER'::integer;":
        if fault == "partial":
            (work / "rows").write_text("\n".join(rows + pending) + "\n")
        if fault != "succeed":
            fail(number)
    else:
        sys.exit("stand-in: unexpected SQL")
(work / "rows").write_text("\n".join(rows + pending) + "\n")
if fault == "restart":
    (work / "starts").write_text("restarted")
if fault == "credential":
    Path("build/dev/app1/credentials/database/password").write_text("changed\n")
print(f"[OK] seeded app1 from {sql}")
"""
PODMAN = r"""#!/usr/bin/env python3
import os, re, sys
from pathlib import Path

work = Path(os.environ["W"])
if sys.argv[1] == "ps":
    print("c1 app1-postgres-db " + (work / "starts").read_text())
    sys.exit()
# exec <container> sh -ec <script> sh <query>
if sys.argv[1:3] != ["exec", "app1-postgres-db"]:
    sys.exit(125)
# Only the step's two queries, for its two keys, are answered.
KEYS = "name IN ('dev-seed', 'dev-seed-partial')"
query = sys.argv[-1]
rows = (work / "rows").read_text().split()
owned = [row for row in rows if row.split("|")[0] in ("dev-seed", "dev-seed-partial")]
if query == "SELECT name, value FROM demo_seed WHERE " + KEYS + " ORDER BY name":
    print("\n".join(sorted(owned)))
elif query == "DELETE FROM demo_seed WHERE " + KEYS:
    (work / "rows").write_text("\n".join(r for r in rows if r not in owned) + "\n")
    print("DELETE", len(owned))
else:
    sys.exit("stand-in: unexpected query")
"""


class DevSeedStepTests(unittest.TestCase):
    def run_step(self, fault="", rows=""):
        work = Path(self.enterContext(tempfile.TemporaryDirectory()))
        src = work / "src"
        for path, text in (
            ("src/dev/seed-db.sh", SEED_DB),
            ("bin/podman", PODMAN),
            ("src/build/dev/app1/credentials/database/password", "secret\n"),
            ("rows", rows),
            ("starts", "started"),
        ):
            (work / path).parent.mkdir(parents=True, exist_ok=True)
            (work / path).write_text(text)
        for name in ("src/dev/seed-db.sh", "bin/podman"):
            (work / name).chmod(0o755)
        script = (
            "set -euo pipefail\n"
            + f"base={work} src={src}\n"
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
            },
        )

    def test_the_step_passes_for_the_products_behaviour(self):
        result = self.run_step()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: seed-db inserted once", result.stdout)
        self.assertNotIn("PRIVATE_MARKER", result.stdout + result.stderr)

    def test_the_step_fails_for_each_wrong_result(self):
        for fault, message in (
            ("norow", "after the first seed demo_seed lacks exactly one dev-seed row"),
            ("duplicate", "after the repeated seed demo_seed lacks exactly one"),
            ("succeed", "the failing seed succeeded"),
            ("noline", "the SQL failure is not the fixed message naming line 3"),
            ("marker", "the failure shows SQL text"),
            ("partial", "the failed seed left a row"),
            ("restart", "seeding replaced or added a container"),
            ("credential", "seeding changed a credential"),
        ):
            with self.subTest(fault):
                result = self.run_step(fault)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("FAIL: " + message, result.stdout)
                # The step prints its verdicts, never the command's output.
                self.assertNotIn("PRIVATE_MARKER", result.stdout + result.stderr)

    def test_rows_of_an_earlier_attempt_never_count(self):
        earlier = "dev-seed|v1\ndev-seed-partial|x\nreference|release-v1\n"
        result = self.run_step(rows=earlier)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.run_step("norow", rows=earlier)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("FAIL: after the first seed demo_seed lacks", result.stdout)

    def test_the_step_has_its_action(self):
        self.assertRegex(REMOTE, r"(?m)^dev-seed\)$")
        self.assertIn('seed_dir="$base/dev seed"', REMOTE)
