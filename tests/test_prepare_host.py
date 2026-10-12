"""Test the host script's SELinux migration with shell stubs, without root."""

import subprocess
import unittest
from pathlib import Path


class HostLabelTests(unittest.TestCase):
    def run_labels(self, old=False, correct=False, conflict=False):
        script = (
            Path(__file__).resolve().parent.parent / "scripts/prepare-host.sh"
        ).read_text()
        block = script[
            script.index("# SELinux: lageret") : script.index("loginctl enable-linger")
        ]
        stubs = r"""
service_home=/var/lib/myproduct
semanage() {
    if [[ $* == 'fcontext -l -C' ]]; then
        [[ $old == 0 ]] || echo "$service_home = /home"
        [[ $correct == 0 ]] || echo "$service_home/.local/share/containers = /var/lib/containers"
        return 0
    fi
    echo "semanage $*"
    if [[ $2 == -d ]]; then old=0; else
        [[ $conflict == 0 ]] || return 1
        correct=1
    fi
}
id() { echo myproduct; }
install() { echo "install $*"; }
restorecon() { echo "restorecon $*"; }
"""
        settings = f"old={int(old)}; correct={int(correct)}; conflict={int(conflict)}\n"
        return subprocess.run(
            ["bash", "-eu", "-c", settings + stubs + block + block],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,  # noqa: UP021 - Python 3.6
        )

    def test_fresh_rule_added_once_before_restorecon(self):
        result = self.run_labels()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.count("semanage fcontext -a"), 1)
        self.assertIn(
            "-e /var/lib/containers /var/lib/myproduct/.local/share/containers",
            result.stdout,
        )
        self.assertLess(
            result.stdout.index("install -d"), result.stdout.index("restorecon")
        )
        self.assertEqual(result.stdout.count("restorecon -R /var/lib/myproduct"), 2)

    def test_old_home_rule_deleted_before_new_rule_only_once(self):
        result = self.run_labels(old=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            result.stdout.count("semanage fcontext -d /var/lib/myproduct"), 1
        )
        self.assertLess(
            result.stdout.index("fcontext -d"), result.stdout.index("fcontext -a")
        )

    def test_existing_rule_is_not_added_again(self):
        result = self.run_labels(correct=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("semanage fcontext", result.stdout)

    def test_conflicting_policy_stops_before_relabel(self):
        result = self.run_labels(conflict=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("restorecon", result.stdout)
