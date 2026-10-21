"""Test host validation and idempotent labels using shell stubs, without root."""

import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


class HostLabelTests(unittest.TestCase):
    def run_labels(self, old=False, correct=False, conflict=False):
        script = (
            Path(__file__).resolve().parents[2] / "scripts/prepare-host.sh"
        ).read_text()
        block = script[
            script.index("# SELinux: storage needs") : script.index(
                "loginctl enable-linger"
            )
        ]
        stubs = r"""
user=myproduct
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
prepare_service_home() { echo "prepare_service_home"; }
"""
        settings = f"old={int(old)}; correct={int(correct)}; conflict={int(conflict)}\n"
        return subprocess.run(
            ["bash", "-eu", "-c", settings + stubs + block + block],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )

    def test_fresh_rule_added_once_before_home_preparation(self):
        result = self.run_labels()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.count("semanage fcontext -a"), 1)
        self.assertIn(
            "-e /var/lib/containers /var/lib/myproduct/.local/share/containers",
            result.stdout,
        )
        self.assertLess(
            result.stdout.index("fcontext -a"),
            result.stdout.index("prepare_service_home"),
        )
        self.assertEqual(result.stdout.count("prepare_service_home"), 2)

    def test_old_home_rule_requires_manual_removal(self):
        result = self.run_labels(old=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected SELinux equivalence", result.stdout)
        self.assertIn("Remove it manually", result.stdout)
        self.assertNotIn("fcontext -d", result.stdout)
        self.assertNotIn("restorecon", result.stdout)
        self.assertNotIn("prepare_service_home", result.stdout)

    def test_existing_rule_is_not_added_again(self):
        result = self.run_labels(correct=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("semanage fcontext", result.stdout)

    def test_conflicting_policy_stops_before_relabel(self):
        result = self.run_labels(conflict=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("restorecon", result.stdout)
        self.assertNotIn("prepare_service_home", result.stdout)


class HostBoundaryTests(unittest.TestCase):
    """The real shell functions delegate every descendant mutation unprivileged."""

    def run_home(self, failure=0):
        script = Path(__file__).resolve().parents[2] / "scripts/prepare-host.sh"
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "helper.py"
            helper.write_text("# trusted code supplied on stdin\n")
            return subprocess.run(
                [
                    "bash",
                    "-eu",
                    "-c",
                    r"""
source "$1"
service_uid=12345
service_gid=12346
service_home=/var/lib/svc-orders
container_home=$service_home/.local/share/containers
home_helper=$2
calls=0
failure=$3
# The function's arguments are independent of this shell's positional args.
setpriv() {
    calls=$((calls + 1))
    printf '%s\n' "setpriv $*"
    [[ $calls != "$failure" ]]
}
prepare_service_home
echo later-host-actions
""",
                    "probe",
                    str(script),
                    str(helper),
                    str(failure),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                check=False,
            )

    def test_all_home_commands_drop_identity_groups_and_capabilities(self):
        result = self.run_home()
        self.assertEqual(result.returncode, 0, result.stdout)
        lines = result.stdout.splitlines()
        prefix = (
            "setpriv --reuid=12345 --regid=12346 --clear-groups "
            "--inh-caps=-all --ambient-caps=-all --bounding-set=-all --no-new-privs -- "
        )
        self.assertEqual(
            lines,
            [
                prefix + "python3 -B - /var/lib/svc-orders",
                prefix
                + "restorecon -R -e /var/lib/svc-orders/.local/share/containers/storage /var/lib/svc-orders",
                prefix
                + "restorecon /var/lib/svc-orders/.local/share/containers/storage",
                "later-host-actions",
            ],
        )

    def test_each_failure_stops_without_root_retry_or_later_actions(self):
        for failure in (1, 2, 3):
            with self.subTest(failure=failure):
                result = self.run_home(failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout.count("setpriv --"), failure)
                self.assertIn("inspect /var/lib/svc-orders", result.stdout)
                self.assertNotIn("later-host-actions", result.stdout)

    def test_home_link_is_refused_before_root_chmod(self):
        script = (
            Path(__file__).resolve().parents[2] / "scripts/prepare-host.sh"
        ).read_text()
        block = script[
            script.index("# /var/lib is the root-controlled anchor.") : script.index(
                "# Keep ID mappings"
            )
        ]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            outside = base / "outside"
            outside.mkdir(mode=0o755)
            home = base / "home"
            home.symlink_to(outside)
            result = subprocess.run(
                [
                    "bash",
                    "-eu",
                    "-c",
                    'service_home=$1\nservice_uid=$2\nuser=svc\ndie() { echo "ERROR: $*"; exit 1; }\nchmod() { echo privileged-chmod; }\n'
                    + block,
                    "probe",
                    str(home),
                    str(outside.stat().st_uid),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink home", result.stdout)
            self.assertNotIn("privileged-chmod", result.stdout)
            self.assertEqual(outside.stat().st_mode & 0o777, 0o755)


class HostPortTests(unittest.TestCase):
    def run_arguments(self, args, product=None):
        """Run only the argument block, as scripts/prepare-host.sh of a release."""
        script = (
            Path(__file__).resolve().parents[2] / "scripts/prepare-host.sh"
        ).read_text()
        block = script[script.index("# Arguments:") : script.index("for command in")]
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory)
            (release / "scripts").mkdir()
            (release / "scripts/prepare-home.py").write_text("# helper fixture\n")
            if product:
                # Serialized like bundle.py, which quotes values such as 'on'.
                (release / "bundle.yaml").write_text(
                    yaml.safe_dump(
                        {"name": "app", "product": product, "version": "1.0.0"},
                        sort_keys=False,
                    )
                )
            return subprocess.run(
                [
                    "bash",
                    "-eu",
                    "-c",
                    'die() { echo "ERROR: $*"; exit 1; }\n'
                    + block
                    + 'echo "user=$user port=$port"\n',
                    str(release / "scripts/prepare-host.sh"),
                ]
                + args,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            )

    def test_required_port_and_bounds(self):
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
            (["--port"], False),
            (["--port", "8443", "--user"], False),
            (["--port", "8443", "--port", "9443"], False),
            (["--port", "8443", "--user", "a", "--user", "b"], False),
        ):
            with self.subTest(args=args):
                result = self.run_arguments(args)
                self.assertEqual(result.returncode == 0, valid, result.stdout)
                if not valid:
                    self.assertIn("ERROR:", result.stdout)

    def test_service_user_defaults_to_the_bundle_product(self):
        """A renamed product needs no extra argument; --user overrides it."""
        cases = (
            ([], None, "user=myproduct port=8443"),
            ([], "hubbabubba", "user=hubbabubba port=8443"),
            ([], "on", "user=on port=8443"),
            ([], "null", "user=null port=8443"),
            (["--user", "svc-shop"], "hubbabubba", "user=svc-shop port=8443"),
        )
        for extra, product, expected in cases:
            with self.subTest(extra=extra, product=product):
                result = self.run_arguments(["--port", "8443"] + extra, product)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(result.stdout.strip(), expected)
        for user in ("Shop", "1shop", "shop_", "a" * 33, "shop;id"):
            with self.subTest(user=user):
                result = self.run_arguments(["--port", "8443", "--user", user])
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid service user", result.stdout)


class HostFapolicydTests(unittest.TestCase):
    """Only a warning: fapolicyd's settings belong to the host's baseline."""

    def run_check(self, content):
        script = (
            Path(__file__).resolve().parents[2] / "scripts/prepare-host.sh"
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
                universal_newlines=True,
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
