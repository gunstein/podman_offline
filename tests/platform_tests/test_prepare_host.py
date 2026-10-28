"""Test host validation and idempotent labels using shell stubs, without root."""

import os
import shutil
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
            script.index("# SELinux: Podman storage") : script.index(
                "# The user's systemd manager"
            )
        ]
        stubs = r"""
user=operator1
install_root=/var/lib/myproduct
container_home=$install_root/storage/containers
die() { echo "ERROR: $*" >&2; exit 1; }
semanage() {
    if [[ $* == 'fcontext -l -C' ]]; then
        [[ $old == 0 ]] || echo "$install_root = /home"
        [[ $correct == 0 ]] || echo "$install_root/storage/containers = /var/lib/containers"
        return 0
    fi
    echo "semanage $*"
    [[ $conflict == 0 ]] || return 1
    correct=1
}
id() { echo myproduct; }
prepare_install_directories() { echo "prepare_install_directories"; }
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
            "-e /var/lib/containers /var/lib/myproduct/storage/containers",
            result.stdout,
        )
        self.assertLess(
            result.stdout.index("fcontext -a"),
            result.stdout.index("prepare_install_directories"),
        )
        self.assertEqual(result.stdout.count("prepare_install_directories"), 2)

    def test_old_home_rule_requires_manual_removal(self):
        result = self.run_labels(old=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected SELinux equivalence", result.stdout)
        self.assertIn("Remove it manually", result.stdout)
        self.assertNotIn("fcontext -d", result.stdout)
        self.assertNotIn("restorecon", result.stdout)
        self.assertNotIn("prepare_install_directories", result.stdout)

    def test_existing_rule_is_not_added_again(self):
        result = self.run_labels(correct=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("semanage fcontext", result.stdout)

    def test_conflicting_policy_stops_before_relabel(self):
        result = self.run_labels(conflict=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("restorecon", result.stdout)
        self.assertNotIn("prepare_install_directories", result.stdout)


class HostBoundaryTests(unittest.TestCase):
    """The real shell functions delegate every descendant mutation unprivileged."""

    def run_home(self, failure=0):
        script = Path(__file__).resolve().parents[2] / "scripts/prepare-host.sh"
        return subprocess.run(
            [
                "bash",
                "-eu",
                "-c",
                r"""
source "$1"
service_uid=12345
service_gid=12346
install_root=/var/lib/orders
container_home=$install_root/storage/containers
calls=0
failure=$2
# The function's arguments are independent of this shell's positional args.
setpriv() {
    calls=$((calls + 1))
    printf '%s\n' "setpriv $*"
    [[ $calls != "$failure" ]]
}
prepare_install_directories
echo later-host-actions
""",
                "probe",
                str(script),
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
                prefix + "python3 -B - /var/lib/orders",
                prefix
                + "restorecon -R -e /var/lib/orders/storage/containers/storage "
                + "/var/lib/orders/state /var/lib/orders/config /var/lib/orders/storage",
                prefix + "restorecon /var/lib/orders/storage/containers/storage",
                "later-host-actions",
            ],
        )

    def test_each_failure_stops_without_root_retry_or_later_actions(self):
        for failure in (1, 2, 3):
            with self.subTest(failure=failure):
                result = self.run_home(failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout.count("setpriv --"), failure)
                self.assertIn("inspect /var/lib/orders", result.stdout)
                self.assertNotIn("later-host-actions", result.stdout)

    def run_root_block(self, prepare):
        """Run the root/account-directory checks against a disposable anchor."""
        script = (
            Path(__file__).resolve().parents[2] / "scripts/prepare-host.sh"
        ).read_text()
        block = script[
            script.index("if [[ ! -e $install_root") : script.index(
                "# Keep ID mappings"
            )
        ]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "orders"
            outside = base / "outside"
            outside.mkdir(mode=0o755)
            prepare(root, outside)
            result = subprocess.run(
                [
                    "bash",
                    "-eu",
                    "-c",
                    "install_root=$1\nservice_uid=$2\nservice_gid=$2\nuser=operator1\nproduct=orders\n"
                    'die() { echo "ERROR: $*"; exit 1; }\n'
                    'stat() { if [[ $1 == -c && $2 == %u && $3 == "$install_root" ]]; then echo 0; else command stat "$@"; fi; }\n'
                    'getfacl() { :; }\nchown() { echo "chown $*"; }\nchmod() { echo "chmod $*"; }\n'
                    + block.replace("/etc/systemd/system", str(base / "etc")),
                    "probe",
                    str(root),
                    str(os.geteuid()),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                check=False,
            )
            return result, sorted(path.name for path in outside.iterdir())

    def test_root_link_or_foreign_state_is_refused_before_changes(self):
        def link(root, outside):
            root.symlink_to(outside)

        def foreign(root, outside):
            root.mkdir(mode=0o755)
            (root / "state").symlink_to(outside)

        for prepare, message in (
            (link, "must be a root-owned directory"),
            (foreign, "belongs to another account"),
        ):
            with self.subTest(case=prepare.__name__):
                result, outside = self.run_root_block(prepare)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stdout)
                self.assertNotIn("chown", result.stdout)
                self.assertNotIn("chmod", result.stdout)
                self.assertEqual(outside, [])

    def test_fresh_root_creates_only_the_three_account_directories(self):
        def fresh(root, outside):
            pass

        result, _ = self.run_root_block(fresh)
        self.assertEqual(result.returncode, 0, result.stdout)
        for name in ("state", "config", "storage"):
            self.assertIn("chown -h ", result.stdout)
            self.assertIn("chmod 0700 ", result.stdout)
            self.assertIn("/orders/" + name, result.stdout)


class HostUserManagerTests(unittest.TestCase):
    """The persistent drop-in is the one place services get their storage.

    The systemctl stub models a user manager: start/restart reread the drop-in
    unless broken, and show-environment reports what the manager carries.
    """

    EXPECTED = "XDG_CONFIG_HOME=/var/lib/orders/config\nXDG_DATA_HOME=/var/lib/orders/storage\n"

    def run_dropin(
        self, existing=None, other=False, active=False, current="", broken=False
    ):
        script = (
            Path(__file__).resolve().parents[2] / "scripts/prepare-host.sh"
        ).read_text()
        guard = script[
            script.index("dropin_dir=/etc") : script.index(
                "# The root creates the account's directories"
            )
        ]
        block = script[
            script.index("# The user's systemd manager") : script.index(
                "firewall-cmd --permanent"
            )
        ]
        stubs = r"""
die() { echo "ERROR: $*"; exit 1; }
loginctl() { echo "loginctl $*"; }
systemctl() {
    echo "systemctl $*" >> "$state/calls"
    case "$*" in
        "is-active --quiet user@4321.service") [[ -f $state/active ]];;
        "start user@4321.service"|"restart user@4321.service")
            touch "$state/active"
            if [[ $broken == 0 && -f $dropin ]]; then
                printf 'XDG_CONFIG_HOME=/var/lib/orders/config
XDG_DATA_HOME=/var/lib/orders/storage
' > "$state/env"
            fi;;
        "--user -M operator1@ show-environment") cat "$state/env";;
        *) :;;
    esac
}
"""
        with tempfile.TemporaryDirectory() as directory:
            etc = Path(directory) / "etc"
            state = Path(directory) / "manager"
            state.mkdir()
            (state / "env").write_text(current)
            (state / "calls").write_text("")
            if active:
                (state / "active").write_text("")
            dropins = etc / "user@4321.service.d"
            dropins.mkdir(parents=True)
            if existing is not None:
                (dropins / "podman-offline-orders.conf").write_text(existing)
            if other:
                (dropins / "podman-offline-shop.conf").write_text("")
            result = subprocess.run(
                [
                    "bash",
                    "-eu",
                    "-c",
                    "service_uid=4321\nuser=operator1\nproduct=orders\n"
                    "install_root=/var/lib/orders\nstate=$1\nbroken=$2\n"
                    + stubs
                    + (guard + block).replace("/etc/systemd/system", str(etc)),
                    "probe",
                    str(state),
                    "1" if broken else "0",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                check=False,
            )
            written = dropins / "podman-offline-orders.conf"
            calls = (state / "calls").read_text().splitlines()
            return (
                result,
                written.read_text() if written.exists() else None,
                calls,
            )

    def dropin_text(self):
        result, text, _ = self.run_dropin()
        self.assertEqual(result.returncode, 0, result.stdout)
        assert text is not None
        return text

    def test_fresh_dropin_sets_both_variables_and_restarts_a_running_manager(self):
        result, text, calls = self.run_dropin(active=True, current="PATH=/usr/bin\n")
        self.assertEqual(result.returncode, 0, result.stdout)
        assert text is not None
        self.assertIn(
            "Environment=XDG_CONFIG_HOME=/var/lib/orders/config "
            "XDG_DATA_HOME=/var/lib/orders/storage",
            text,
        )
        self.assertIn("systemctl restart user@4321.service", calls)

    def test_repeat_after_interrupted_activation_restarts_the_manager(self):
        """The drop-in exists, but the manager still has the old environment."""
        result, _, calls = self.run_dropin(
            existing=self.dropin_text(), active=True, current="PATH=/usr/bin\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("systemctl restart user@4321.service", calls)

    def test_active_manager_with_the_settings_is_not_restarted(self):
        result, _, calls = self.run_dropin(
            existing=self.dropin_text(), active=True, current=self.EXPECTED
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(
            [call for call in calls if "restart" in call or " start " in call]
        )

    def test_stopped_manager_is_started_not_restarted(self):
        result, _, calls = self.run_dropin()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("systemctl start user@4321.service", calls)
        self.assertNotIn("systemctl restart user@4321.service", calls)

    def test_manager_without_the_settings_after_activation_fails(self):
        result, _, _ = self.run_dropin(active=True, broken=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not use /var/lib/orders/config", result.stdout)

    def test_changed_dropin_or_second_product_is_refused(self):
        result, text, calls = self.run_dropin(existing="[Service]\nEnvironment=X=1\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("differs from the expected settings", result.stdout)
        self.assertEqual(text, "[Service]\nEnvironment=X=1\n")
        self.assertEqual(calls, [])
        result, text, calls = self.run_dropin(other=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already runs another product", result.stdout)
        self.assertIsNone(text)
        self.assertEqual(calls, [])


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
                    + 'echo "user=$user port=$port product=$product"\n',
                    str(release / "scripts/prepare-host.sh"),
                ]
                + args,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            )

    def test_required_port_account_and_bounds(self):
        for args, valid in (
            ([], False),
            (["--port", "8443"], False),
            (["--user", "operator1"], False),
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
                if valid:
                    args = args + ["--user", "operator1"]
                result = self.run_arguments(args)
                self.assertEqual(result.returncode == 0, valid, result.stdout)
                if not valid:
                    self.assertIn("ERROR:", result.stdout)

    def test_account_is_explicit_and_independent_of_the_product(self):
        """The product names the root; the account is any existing login name."""
        cases = (
            (
                ["--user", "operator1"],
                None,
                "user=operator1 port=8443 product=myproduct",
            ),
            (
                ["--user", "Ops.User"],
                "hubbabubba",
                "user=Ops.User port=8443 product=hubbabubba",
            ),
            (["--user", "svc-shop"], "on", "user=svc-shop port=8443 product=on"),
        )
        for extra, product, expected in cases:
            with self.subTest(extra=extra, product=product):
                result = self.run_arguments(["--port", "8443"] + extra, product)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(result.stdout.strip(), expected)
        for user in ("1shop", "a" * 33, "shop;id", "../x", ""):
            with self.subTest(user=user):
                result = self.run_arguments(["--port", "8443", "--user", user])
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ERROR", result.stdout)


class HostFapolicydTests(unittest.TestCase):
    """Only a warning: fapolicyd's settings belong to the host's baseline."""

    def run_check(self, content):
        script = (
            Path(__file__).resolve().parents[2] / "scripts/prepare-host.sh"
        ).read_text()
        block = script[
            script.index("# fapolicyd:") : script.index(
                "# The account must already exist"
            )
        ]
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


class HostAuditTests(unittest.TestCase):
    """prepare-host.sh records its start and result with logger (backlog 74)."""

    def run_audit(self, body):
        script = (
            Path(__file__).resolve().parents[2] / "scripts/prepare-host.sh"
        ).read_text()
        block = script[
            script.index("audit() {") : script.index("trap audit_result EXIT")
        ]
        block += "trap audit_result EXIT\n"
        with tempfile.TemporaryDirectory() as directory:
            stub = Path(directory) / "logger"
            stub.write_text('#!/bin/sh\necho "$*" >> "$LOGGER_OUT"\n')
            stub.chmod(0o755)
            out = Path(directory) / "out"
            subprocess.run(
                ["bash", "-c", "product=shop user=ops port=9443\n" + block + body],
                check=False,
                env=dict(
                    os.environ,
                    PATH=directory + ":" + os.environ["PATH"],
                    LOGGER_OUT=str(out),
                ),
            )
            return out.read_text().splitlines()

    def test_start_and_result_reach_the_journal(self):
        for body, result in (("true", "completed"), ("exit 3", "failed (exit 3)")):
            with self.subTest(result=result):
                self.assertEqual(
                    self.run_audit(body),
                    [
                        "-t shop -- prepare-host --user ops --port 9443: started",
                        "-t shop -- prepare-host --user ops --port 9443: " + result,
                    ],
                )

    def test_missing_logger_does_not_stop_preparation(self):
        script = (
            Path(__file__).resolve().parents[2] / "scripts/prepare-host.sh"
        ).read_text()
        block = script[script.index("audit() {") : script.index("audit_result() {")]
        result = subprocess.run(
            [
                shutil.which("bash"),
                "-euc",
                "product=shop\n" + block + 'audit "x"; echo done',
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=dict(os.environ, PATH="/nonexistent"),
        )
        self.assertEqual(
            (result.returncode, result.stdout, result.stderr), (0, "done\n", "")
        )
