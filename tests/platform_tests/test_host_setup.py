"""Host setup authority, real signed publication and durable fresh-process retry."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from helpers.host_setup_fixture import ROOT, archive, release_module

release = release_module()


class HostSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.TemporaryDirectory(prefix="h65-")
        cls.home = Path(cls.keys.name)
        cls.gpg(
            "--passphrase",
            "",
            "--quick-gen-key",
            "Host fixture <host@invalid>",
            "ed25519",
            "sign",
            "never",
        )
        cls.public = cls.gpg("--export", raw=True).stdout

    @classmethod
    def tearDownClass(cls):
        subprocess.run(
            ["gpgconf", "--homedir", str(cls.home), "--kill", "gpg-agent"], check=False
        )
        cls.keys.cleanup()

    @classmethod
    def gpg(cls, *args, raw=False):
        return subprocess.run(
            [
                "gpg",
                "--homedir",
                str(cls.home),
                "--batch",
                "--pinentry-mode",
                "loopback",
                *args,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=not raw,
            check=True,
        )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("lib", "tmp", "log", "systemd", "trust", "upload", "home"):
            (self.root / name).mkdir(mode=0o755)
        (self.root / "os-release").write_text('ID="ol"\nVERSION_ID="9.8"\n')
        (self.root / "fapolicyd.conf").write_text(
            "permissive = 0\nintegrity = none\nsubj_cache_size = 16381\n"
        )
        (self.root / "journald.conf").write_text(
            "[Journal]\n#Storage=auto\n#SplitMode=uid\n"
        )
        (self.root / "fapolicyd.conf").chmod(0o644)
        self.upload = self.root / "upload"
        (self.upload / "keyring.gpg").write_bytes(self.public)
        for component, version in (("worker", "1.0.0"), ("processor", "2.3.4")):
            self.sign(archive(self.upload, component, version))
        self.args = types.SimpleNamespace(
            product="cedar",
            user="operator-a",
            port=8443,
            input_dir=self.upload,
            keyring=self.upload / "keyring.gpg",
            key_sha256=hashlib.sha256(self.public).hexdigest(),
            release=["worker@1.0.0", "processor@2.3.4"],
            host_release="worker@1.0.0",
            component=None,
            version=None,
            archive=None,
            signature=None,
            old_version=None,
        )

    def sign(self, path):
        self.gpg("--yes", "--armor", "--detach-sign", str(path))

    def run_setup(self, failure="", success=True):
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                str(ROOT / "tests/helpers/host_setup_driver.py"),
                str(self.root),
                failure,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS: host setup", result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("PASS: host setup", result.stdout)
        return result

    def calls(self):
        return [
            json.loads(line)
            for line in (self.root / "calls.jsonl").read_text().splitlines()
        ]

    def test_signed_first_run_repeat_and_explicit_selection(self):
        ignored = self.upload / "cedar-ignored-9.9.9-offline.tar.gz"
        ignored.write_bytes(b"must not be opened")
        self.run_setup()
        key = self.root / "lib/cedar/keyring.gpg"
        record = self.root / "lib/cedar/releases/cedar-worker-1.0.0/.release.json"
        retained = (key.read_bytes(), record.read_bytes(), record.stat().st_ino)
        pending = self.root / "lib/cedar/state/pending-operation.json"
        pending.write_bytes(b"private pending record must remain untouched")
        self.run_setup()
        self.assertEqual(
            pending.read_bytes(), b"private pending record must remain untouched"
        )
        self.assertEqual(
            (key.read_bytes(), record.read_bytes(), record.stat().st_ino), retained
        )
        self.assertTrue(pending.exists())
        self.assertEqual(list((self.root / "home").iterdir()), [])
        calls = self.calls()
        host = next(i for i, call in enumerate(calls) if call[0] == "/usr/bin/bash")
        self.assertEqual(sum(call[0] == "gpgv" for call in calls[:host]), 2)
        self.assertEqual(calls[host][-4:], ["--port", "8443", "--user", "operator-a"])
        self.assertFalse(any("ignored" in str(call) for call in calls))

    def test_invalid_second_signature_preserves_first_without_host_execution(self):
        path = self.upload / "cedar-processor-2.3.4-offline.tar.gz"
        path.write_bytes(path.read_bytes() + b"corrupt")
        self.run_setup(success=False)
        self.assertTrue(
            (self.root / "lib/cedar/releases/cedar-worker-1.0.0/.release.json").exists()
        )
        self.assertFalse(
            any(c[0] in ("/usr/bin/bash", "journalctl") for c in self.calls())
        )
        self.sign(path)
        self.run_setup()

    def test_every_persistence_boundary_retries_in_a_new_process(self):
        for failure in ("trust", "flush", "host", "kill-journal"):
            with self.subTest(failure=failure):
                failed = self.run_setup(failure, success=False)
                if failure == "host":
                    self.assertIn("overlapping subordinate ID ranges", failed.stdout)
                    self.assertIn("/etc/subuid and /etc/subgid", failed.stdout)
                    self.assertIn("same administrator setup command", failed.stdout)
                record = (
                    self.root / "lib/cedar/releases/cedar-worker-1.0.0/.release.json"
                )
                before = record.read_bytes()
                self.run_setup()
                self.assertEqual(record.read_bytes(), before)
                self.assertTrue((self.root / "manager-ready").exists())

    def test_killed_initial_setup_keeps_partial_journal_and_retries(self):
        self.run_setup("kill-journal", success=False)
        self.assertTrue((self.root / "log/journal").is_dir())
        self.assertEqual(list((self.root / "log/journal").iterdir()), [])
        self.assertFalse((self.root / "manager-ready").exists())
        self.run_setup()
        self.assertTrue((self.root / "manager-ready").exists())

    def test_killed_signature_snapshot_is_not_published_or_scavenged(self):
        self.run_setup("kill-signature", success=False)
        product = self.root / "lib/cedar"
        abandoned = list(product.glob(".staging-*"))
        self.assertEqual(len(abandoned), 1)
        self.assertEqual(list((product / "releases").iterdir()), [])
        self.assertFalse(any(c[0] == "/usr/bin/bash" for c in self.calls()))
        self.run_setup()
        self.assertTrue(abandoned[0].exists())
        self.assertTrue(
            (product / "releases/cedar-worker-1.0.0/.release.json").exists()
        )

    def test_journal_conflict_stops_before_product_changes_and_preserves_policy(self):
        config = self.root / "journald.conf"
        text = "[Journal]\nStorage=volatile\n"
        config.write_text(text)
        result = self.run_setup(success=False)
        self.assertIn("Storage", result.stdout)
        self.assertEqual(config.read_text(), text)
        self.assertEqual(list((self.root / "lib").iterdir()), [])

    def test_preflight_collects_errors_before_any_product_write(self):
        (self.root / "fapolicyd.conf").write_text(
            "permissive = 1\nintegrity = none\nsubj_cache_size = 4099\n"
        )
        (self.upload / "keyring.gpg").write_bytes(b"wrong")
        # Driver takes the digest of the input, so also exercise missing selected input.
        (self.upload / "cedar-worker-1.0.0-offline.tar.gz.asc").unlink()
        result = self.run_setup(success=False)
        self.assertIn("preflight failed before changes", result.stdout)
        self.assertIn("permissive", result.stdout)
        self.assertEqual(list((self.root / "lib").iterdir()), [])

    def test_missing_package_and_cache_baseline_name_exact_remedies(self):
        result = self.run_setup("missing-tools", success=False)
        self.assertIn("policycoreutils-python-utils", result.stdout)
        self.assertEqual(list((self.root / "lib").iterdir()), [])
        (self.root / "fapolicyd.conf").write_text(
            "permissive = 0\nintegrity = none\nsubj_cache_size = 4099\n"
        )
        result = self.run_setup(success=False)
        self.assertIn("set subj_cache_size = 16381", result.stdout)
        self.assertEqual(list((self.root / "lib").iterdir()), [])

    def test_explicit_selection_rejects_duplicates_conflicts_and_unsafe_ids(self):
        for selections in (
            [],
            ["worker@1.0.0"] * 2,
            ["worker@1.0.0", "worker@2.0.0"],
            ["../x@1.0.0"],
            ["worker@latest"],
        ):
            with self.subTest(selections=selections):
                self.args.release = selections
                with self.assertRaises(release.ReleaseError):
                    release.setup_request(self.args)
        self.args.release = ["worker@1.0.0"]
        self.args.host_release = "unknown@1.0.0"
        with self.assertRaises(release.ReleaseError):
            release.setup_request(self.args)

    def test_journal_effective_file_order_and_section_scope(self):
        text = "# /etc/systemd/journald.conf\n[Journal]\nStorage=volatile\n[Other]\nStorage=none\n# /etc/systemd/journald.conf.d/site.conf\n[Journal]\nStorage=persistent\n"
        self.assertEqual(release.journal_settings(text)["Storage"][0], "persistent")
        for text in ("[Journal]\nStorage=none", "[Journal]\nSplitMode=none"):
            with self.assertRaises(release.ReleaseError):
                release.journal_settings(text)

    def test_space_combines_shared_filesystems_and_rejects_low_capacity(self):
        with mock.patch.object(release, "RESERVE", 10), mock.patch.object(
            release.shutil, "disk_usage", return_value=types.SimpleNamespace(free=21)
        ):
            with self.assertRaisesRegex(release.ReleaseError, "required=22 free=21"):
                release.check_space([(self.root, 5), (self.upload, 7)])

    def test_regular_input_refuses_links_and_fifo_without_waiting(self):
        link = self.root / "key-link"
        link.symlink_to(self.args.keyring)
        with self.assertRaises(OSError):
            release.input_digest(link)
        fifo = self.root / "fifo"
        os.mkfifo(str(fifo))
        with self.assertRaises(release.ReleaseError):
            release.input_digest(fifo)

    def test_missing_authenticated_host_script_never_runs_host(self):
        self.sign(archive(self.upload, host=False))
        result = self.run_setup(success=False)
        self.assertIn("no authenticated host script", result.stdout)
        self.assertFalse(
            any(c[0] in ("journalctl", "/usr/bin/bash") for c in self.calls())
        )


class HostDiagnosticsTests(unittest.TestCase):
    def test_host_failures_keep_distinct_safe_reason_and_next_action(self):
        cases = (
            (
                "subordinate-ids",
                "ERROR: Overlap in subuid/subgid",
                "overlapping subordinate ID ranges",
                "/etc/subuid",
            ),
            (
                "subordinate-ids",
                "ERROR: No free subuid/subgid block",
                "no free subordinate ID block",
                "65536",
            ),
            (
                "selinux",
                "ERROR: Unexpected SELinux equivalence: private-value",
                "conflicting SELinux equivalence",
                "semanage fcontext -l -C",
            ),
            ("firewall", "private-value", "phase=firewall", "firewall-cmd --state"),
            ("user-manager", "private-value", "phase=user-manager", "systemctl"),
        )
        for phase, error, expected, action in cases:
            result = types.SimpleNamespace(
                returncode=42,
                stdout="private-value",
                stderr="HOST-PHASE: " + phase + "\n" + error + "\n",
            )
            with self.subTest(phase=phase, error=error), mock.patch.object(
                release.subprocess, "run", return_value=result
            ):
                with self.assertRaises(release.ReleaseError) as caught:
                    release.command(
                        ["/usr/bin/bash", "protected/prepare-host.sh"],
                        diagnose=release.host_preparation_error,
                    )
                message = str(caught.exception)
                self.assertIn(expected, message)
                self.assertIn(action, message)
                self.assertIn("manual step 3", message)
                self.assertNotIn("private-value", message)

    def test_unknown_child_output_is_not_exposed(self):
        result = types.SimpleNamespace(
            returncode=1,
            stdout="private-value" * 10000,
            stderr="HOST-PHASE: attacker-secret\nERROR: secret-token\x1b[31m",
        )
        message = str(release.host_preparation_error(result))
        self.assertLess(len(message), 500)
        self.assertIn("phase=host-script", message)
        for private in ("private-value", "attacker-secret", "secret-token", "\x1b"):
            self.assertNotIn(private, message)


class HostAccountTests(unittest.TestCase):
    def account(self, uid=1000):
        return types.SimpleNamespace(
            pw_uid=uid, pw_gid=1000, pw_dir="/home/operator-a", pw_shell="/bin/bash"
        )

    def check(self, uid=1000, result=None, groups="operator-a"):
        with tempfile.TemporaryDirectory() as directory:

            def command(args, allowed=(0,)):
                return (
                    types.SimpleNamespace(stdout=groups, stderr="", returncode=0)
                    if args[0] == "id"
                    else result
                )

            with mock.patch.object(release, "BASE", Path(directory)), mock.patch.object(
                release, "SYSTEMD", Path(directory)
            ), mock.patch.object(release, "ancestors"), mock.patch.object(
                release.pwd, "getpwnam", return_value=self.account(uid)
            ), mock.patch.object(release, "command", side_effect=command):
                return release.check_host_account(
                    types.SimpleNamespace(product="cedar", user="operator-a")
                )

    def test_uid_boundaries_and_explicit_denial(self):
        denied = types.SimpleNamespace(
            stdout="User operator-a is not allowed to run sudo on host.example.\n",
            stderr="",
            returncode=1,
        )
        for uid in (1000, 60000, 1000001):
            self.assertEqual(self.check(uid, denied).pw_uid, uid)
        for uid in (0, 999, 61184, 65519, 65534):
            with self.subTest(uid=uid), self.assertRaises(release.ReleaseError):
                self.check(uid, denied)

    def test_sudo_grants_ambiguous_failures_and_privileged_groups_are_refused(self):
        for code, output in (
            (0, "(ALL) ALL"),
            (0, "(root) /bin/true"),
            (1, "sudo: policy lookup failed"),
            (1, "a password is required"),
            (1, ""),
            (0, ""),
            (0, "User other-user is not allowed to run sudo on host."),
            (
                0,
                "User operator-a is not allowed to run sudo on host.\n(root) /bin/true",
            ),
        ):
            result = types.SimpleNamespace(stdout=output, stderr="", returncode=code)
            with self.subTest(output=output), self.assertRaises(release.ReleaseError):
                self.check(result=result)
        denied = types.SimpleNamespace(
            stdout="User operator-a is not allowed to run sudo on host.\n",
            stderr="",
            returncode=1,
        )
        for group in ("wheel", "adm", "systemd-journal", "root"):
            with self.subTest(group=group), self.assertRaises(release.ReleaseError):
                self.check(result=denied, groups="operator-a " + group)

    def test_ol9_successful_policy_query_reports_no_sudo_grants(self):
        # Observed on OL9.8: a successful root policy query returns zero even
        # when the named account has no grants. Require the complete denial.
        for stream in ("stdout", "stderr"):
            result = types.SimpleNamespace(stdout="", stderr="", returncode=0)
            setattr(
                result,
                stream,
                "User operator-a is not allowed to run sudo on todo-standby.\n",
            )
            with self.subTest(stream=stream):
                self.assertEqual(self.check(result=result).pw_uid, 1000)


class HostSetupCliTests(unittest.TestCase):
    def arguments(self):
        return [
            "release.py",
            "setup",
            "--product",
            "cedar",
            "--user",
            "operator-a",
            "--port",
            "8443",
            "--input-dir",
            "/var/tmp/incoming",
            "--keyring",
            "/var/tmp/keyring.gpg",
            "--key-sha256",
            "a" * 64,
            "--release",
            "worker@1.0.0",
            "--host-release",
            "worker@1.0.0",
        ]

    def test_setup_clears_caller_shell_and_executable_environment(self):
        captured = []
        with mock.patch.dict(
            os.environ,
            {
                "PATH": "/tmp/untrusted",
                "BASH_ENV": "/tmp/untrusted.sh",
                "PYTHONPATH": "/tmp/untrusted",
            },
            clear=True,
        ), mock.patch.object(sys, "argv", self.arguments()), mock.patch.object(
            release.os, "geteuid", return_value=0
        ), mock.patch.object(
            release,
            "setup_host",
            side_effect=lambda args, selected: captured.append(
                (dict(os.environ), selected)
            ),
        ):
            release.main()
        self.assertEqual(
            captured[0][0], {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
        )
        self.assertEqual(captured[0][1][0][:2], ("worker", "1.0.0"))

    def test_missing_or_mixed_setup_arguments_refuse_before_lock_or_actions(self):
        for argv in (
            self.arguments()[:-2],
            self.arguments() + ["--component", "worker"],
        ):
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                release, "product_lock"
            ) as lock, self.assertRaises(SystemExit) as error:
                release.main()
            self.assertEqual(error.exception.code, 2)
            lock.assert_not_called()

    def test_missing_yaml_has_a_concrete_package_and_continuation(self):
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(ROOT / "scripts/release.py"),
                "--help",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("python3-pyyaml", result.stderr)
        self.assertIn("repeat setup", result.stderr)
