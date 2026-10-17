"""Test host validation and idempotent labels using shell stubs, without root."""

import subprocess
import tempfile
import unittest
from pathlib import Path


class HostLabelTests(unittest.TestCase):
    def run_labels(self, old=False, correct=False, conflict=False):
        script = (
            Path(__file__).resolve().parent.parent / "scripts/prepare-host.sh"
        ).read_text()
        block = script[
            script.index("# SELinux: storage needs") : script.index(
                "loginctl enable-linger"
            )
        ]
        stubs = r"""
service_home=/var/lib/myproduct
die() { echo "ERROR: $*" >&2; exit 1; }
semanage() {
    if [[ $* == 'fcontext -l -C' ]]; then
        [[ $old == 0 ]] || echo "$service_home = /home"
        [[ $correct == 0 ]] || echo "$service_home/.local/share/containers = /var/lib/containers"
        return 0
    fi
    echo "semanage $*"
    [[ $conflict == 0 ]] || return 1
    correct=1
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
        outside = "restorecon -R -e /var/lib/myproduct/.local/share/containers/storage /var/lib/myproduct"
        storage = "restorecon /var/lib/myproduct/.local/share/containers/storage"
        calls = [
            line
            for line in result.stdout.splitlines()
            if line.startswith("restorecon ")
        ]
        self.assertEqual(calls, [outside, storage] * 2)
        self.assertIn(
            "install -d -m 0700 -o myproduct -g myproduct /var/lib/myproduct/.config/containers/systemd",
            result.stdout,
        )

    def test_old_home_rule_requires_manual_removal(self):
        result = self.run_labels(old=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected SELinux equivalence", result.stdout)
        self.assertIn("Remove it manually", result.stdout)
        self.assertNotIn("fcontext -d", result.stdout)
        self.assertNotIn("restorecon", result.stdout)

    def test_existing_rule_is_not_added_again(self):
        result = self.run_labels(correct=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("semanage fcontext", result.stdout)

    def test_conflicting_policy_stops_before_relabel(self):
        result = self.run_labels(conflict=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("restorecon", result.stdout)


class HostPortTests(unittest.TestCase):
    def test_required_port_and_bounds(self):
        script = (
            Path(__file__).resolve().parent.parent / "scripts/prepare-host.sh"
        ).read_text()
        block = script[
            script.index("# The required port") : script.index("for command in")
        ]
        for args, valid in (
            ([], False),
            (["--port", "1024"], True),
            (["--port", "65535"], True),
            (["--port", "8443"], True),
            (["--port", "1023"], False),
            (["--port", "65536"], False),
            (["--port", "999999999999999999"], False),
            (["--port", "abc"], False),
            (["config.yaml"], False),
            (["--port", "8443", "extra"], False),
        ):
            with self.subTest(args=args):
                result = subprocess.run(
                    [
                        "bash",
                        "-eu",
                        "-c",
                        'die() { echo "ERROR: $*"; exit 1; }\n' + block,
                        "bash",
                    ]
                    + args,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,  # noqa: UP021 - Python 3.6
                )
                self.assertEqual(result.returncode == 0, valid, result.stdout)
                if not valid:
                    self.assertIn("ERROR:", result.stdout)


class HostFapolicydTests(unittest.TestCase):
    """Only a warning: fapolicyd's settings belong to the host's baseline."""

    def run_check(self, content):
        script = (
            Path(__file__).resolve().parent.parent / "scripts/prepare-host.sh"
        ).read_text()
        block = script[script.index("# fapolicyd:") : script.index("service_home=")]
        with tempfile.TemporaryDirectory() as directory:
            conf = Path(directory) / "fapolicyd.conf"
            if content is not None:
                conf.write_text(content)
            block = block.replace("/etc/fapolicyd/fapolicyd.conf", str(conf))
            return subprocess.run(
                ["bash", "-eu", "-c", block],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,  # noqa: UP021 - Python 3.6
            )

    def test_small_or_missing_subject_cache_warns_without_failing(self):
        for content, shown in (
            ("permissive = 0\nsubj_cache_size = 4099\n", "4099"),
            ("permissive = 0\n", "unset"),
            ("subj_cache_size = 16381\nsubj_cache_size = 8191\n", "8191"),
        ):
            with self.subTest(content=content):
                result = self.run_check(content)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn(
                    "WARNING: fapolicyd subj_cache_size is " + shown, result.stdout
                )

    def test_large_cache_or_no_fapolicyd_is_silent(self):
        for content in ("subj_cache_size = 16381\n", " subj_cache_size=32749 \n", None):
            with self.subTest(content=content):
                result = self.run_check(content)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(result.stdout, "")
