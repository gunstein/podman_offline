"""Safety/stop rules tested without SSH, Proxmox, root or network."""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pve import env_file

spec = importlib.util.spec_from_file_location(
    "runner", Path(__file__).with_name("acceptance.py")
)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(mock.patch.object(runner, "RUNS", self.root))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.harness = runner.Run("test", "not-used")

    def test_existing_run_cannot_be_reused(self):
        with self.assertRaises(FileExistsError):
            runner.Run("test", "not-used")

    def test_failed_command_is_recorded_and_not_clean(self):
        with self.assertRaises(RuntimeError):
            self.harness.step(
                "01",
                lambda: self.harness.command(["python3", "-c", "raise SystemExit(7)"]),
            )
        self.assertFalse(self.harness.report())
        row = json.loads((self.harness.folder / "record.jsonl").read_text())
        self.assertEqual(row["result"], "FAIL")
        self.assertIn("exit=7", (self.harness.folder / row["log"]).read_text())
        self.assertIn("NOT CLEAN", (self.harness.folder / "EVIDENCE.md").read_text())

    def test_partial_pass_is_not_clean(self):
        self.harness.step("00", lambda: None)
        self.assertFalse(self.harness.report())

    def test_duplicate_step_cannot_be_reexecuted(self):
        action = mock.Mock()
        self.harness.step("00", action)
        with self.assertRaises(FileExistsError):
            self.harness.step("00", action)
        action.assert_called_once()

    def test_no_steps_after_first_failure(self):
        self.harness.readiness = mock.Mock(side_effect=RuntimeError("readiness"))
        self.harness.reset = mock.Mock()
        with self.assertRaises(RuntimeError):
            self.harness.execute()
        self.harness.reset.assert_not_called()

    def test_token_and_password_are_redacted_from_logs(self):
        self.harness.redactions = ["synthetic-token", "synthetic-password"]
        self.harness.step(
            "00", lambda: self.harness.write("synthetic-token synthetic-password")
        )
        self.harness.report()
        for path in self.harness.folder.rglob("*"):
            if path.is_file():
                self.assertNotIn("synthetic-token", path.read_text())
                self.assertNotIn("synthetic-password", path.read_text())

    def test_podman_zero_exit_error_is_a_failure(self):
        process = mock.patch.object(
            runner.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                [], 0, "Error: network cleanup failed"
            ),
        )
        with process, self.assertRaises(RuntimeError):
            self.harness.step(
                "00", lambda: self.harness.command(["podman", "kube", "down"])
            )
        self.assertFalse(self.harness.report())

    def test_expected_example_validation_error_is_not_false_failure(self):
        process = mock.patch.object(
            runner.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                [], 0, "ERROR: expected config failure\nPASS: failures"
            ),
        )
        with process:
            self.harness.step(
                "00", lambda: self.harness.command(["examples/run.sh", "failures"])
            )

    def test_configuration_permissions_and_duplicate_keys(self):
        path = self.root / "lab.env"
        path.write_text("KEY=one\n")
        path.chmod(0o644)
        with self.assertRaises(RuntimeError):
            env_file(path)
        path.chmod(0o600)
        self.assertEqual(env_file(path), {"KEY": "one"})
        path.write_text("KEY=one\nKEY=two\n")
        with self.assertRaises(RuntimeError):
            env_file(path)

    def test_cleanup_local_secrets_even_if_remote_cleanup_fails(self):
        self.harness.private = self.root / "secret"
        self.harness.private.mkdir()
        self.harness.dev_private = "/run/user/1000/test"
        self.harness.guest = mock.Mock(side_effect=RuntimeError("SSH failed"))
        with self.assertRaises(RuntimeError):
            self.harness.cleanup()
        self.assertFalse(self.harness.private.exists())

    def test_cleanup_failure_prevents_clean_pass(self):
        self.harness.finished = True
        with self.assertRaises(RuntimeError):
            self.harness.step(
                "11-cleanup", lambda: (_ for _ in ()).throw(RuntimeError("cleanup"))
            )
        self.assertFalse(self.harness.report())

    def test_prod_audit_is_collected_after_failure_and_preserved_in_full(self):
        self.harness.prod_ready = True
        with self.assertRaises(RuntimeError):
            self.harness.step("05", lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        self.harness.guest = mock.Mock(
            side_effect=lambda *args: self.harness.write(
                "\n".join("audit-event-" + str(i) for i in range(100))
            )
        )
        self.harness.finalize()
        self.harness.guest.assert_called_once_with("PROD", "audit")
        self.assertFalse(self.harness.report())
        evidence = (self.harness.folder / "EVIDENCE.md").read_text()
        self.assertIn("audit-event-0", evidence)
        self.assertIn("audit-event-99", evidence)

    def test_failed_audit_still_cleans_secrets_and_prevents_clean_pass(self):
        self.harness.finished = True
        self.harness.prod_ready = True
        self.harness.guest = mock.Mock(side_effect=RuntimeError("audit unavailable"))
        self.harness.cleanup = mock.Mock()
        self.harness.finalize()
        self.harness.cleanup.assert_called_once()
        self.assertFalse(self.harness.report())

    def test_audit_uses_locale_date_separate_time_and_both_denial_types(self):
        remote = Path(__file__).with_name("remote.sh").read_text()
        action = remote[
            remote.index("audit)\n") + len("audit)\n") : remote.index("cleanup)")
        ]
        action = action.rsplit(";;", 1)[0]
        stubs = """
run_started=1791821932
date() { if [[ $3 == +%x ]]; then echo 10/12/26; else echo 18:18:52; fi; }
sudo() {
    if [[ $2 == systemctl ]]; then echo active; return 0; fi
    [[ $* == '-n env LC_ALL=C ausearch -m FANOTIFY,AVC,USER_AVC --input-logs -ts 10/12/26 18:18:52 -i' ]] || return 99
    echo 'type=FANOTIFY resp=deny'
    echo 'type=AVC denied'
}
"""
        result = subprocess.run(
            ["bash", "-eu", "-c", stubs + action],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("type=FANOTIFY resp=deny", result.stdout)
        self.assertIn("type=AVC denied", result.stdout)

    def test_selinux_check_rejects_relabel_avc_and_audit_errors(self):
        remote = Path(__file__).with_name("remote.sh").read_text()
        block = remote[
            remote.index("    proposed=$(sudo -n restorecon") : remote.index(
                "    as_product podman exec myproduct-todo-backend"
            )
        ]
        stubs = r"""
run_started=1791821932
date() { echo 10/12/26; }
sudo() {
    if [[ $2 == restorecon ]]; then
        [[ $* == '-n restorecon -n -v -R /var/lib/myproduct' ]] || return 99
        [[ $mode != relabel ]] || echo 'Would relabel storage'
        return 0
    fi
    case "$mode" in
      clean|relabel) echo '<no matches>'; return 1;;
      avc) echo 'type=AVC denied'; return 0;;
      error) echo 'Invalid start date'; return 1;;
    esac
}
"""
        for mode in ("clean", "relabel", "avc", "error"):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    ["bash", "-eu", "-c", "mode=" + mode + "\n" + stubs + block],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode == 0, mode == "clean", result.stdout)

    def test_upgrade_preserves_credentials_and_orders_checks(self):
        self.harness.meta["version"] = "0.1.0"
        self.harness.meta["persistent_before"] = {"ca_der_sha256": "unchanged"}
        self.harness.guest = mock.Mock(return_value='{"ca_der_sha256": "unchanged"}')
        self.harness.transfer = mock.Mock()
        self.harness.credentials = mock.Mock()
        self.harness.upgrade()
        self.harness.credentials.assert_not_called()
        self.harness.transfer.assert_called_once_with("0.1.1")
        self.assertEqual(
            self.harness.guest.call_args_list,
            [
                mock.call("DEV", "upgrade-bundle", "0.1.1"),
                mock.call("PROD", "upgrade", "0.1.0"),
                mock.call("PROD", "check"),
                mock.call("PROD", "persistent-state"),
                mock.call("DEV", "prod-e2e"),
                mock.call("DEV", "markers-check"),
            ],
        )

    def test_upgrade_hash_change_stops_before_e2e(self):
        self.harness.meta["version"] = "0.1.0"
        self.harness.meta["persistent_before"] = {"ca_der_sha256": "old"}
        self.harness.guest = mock.Mock(return_value='{"ca_der_sha256": "new"}')
        self.harness.transfer = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "10-persistent-after"):
            self.harness.upgrade()
        self.assertNotIn(
            mock.call("DEV", "prod-e2e"), self.harness.guest.call_args_list
        )
        self.assertFalse(self.harness.report())

    def test_failed_upgrade_install_stops_before_other_checks(self):
        self.harness.meta["version"] = "0.1.0"
        self.harness.transfer = mock.Mock()
        self.harness.guest = mock.Mock(
            side_effect=["built", RuntimeError("install failed")]
        )
        with self.assertRaisesRegex(RuntimeError, "10-install-upgrade"):
            self.harness.upgrade()
        self.assertEqual(self.harness.guest.call_count, 2)
        self.assertFalse(self.harness.finished)

    def test_credentials_stream_to_private_files_without_logging_content(self):
        self.harness.private = self.root / "private"
        self.harness.private.mkdir(mode=0o700)
        self.harness.meta["version"] = "0.1.0"
        self.harness.cfg = {
            "SSH_USER": "operator",
            "PROD_IP": "192.0.2.2",
            "DEV_IP": "192.0.2.1",
        }
        self.harness.ssh = mock.Mock(side_effect=["/run/user/1000", ""])
        self.harness.command = mock.Mock()

        def transfer(args, stdout, **kwargs):
            self.assertIn(
                "sudo -n -H -u myproduct cat /var/lib/myproduct/",
                args[-1],
            )
            stdout.write(b"synthetic-private-content")
            return subprocess.CompletedProcess(args, 0)

        with mock.patch.object(runner.subprocess, "run", side_effect=transfer):
            self.harness.step("credentials", self.harness.credentials)
        self.assertNotIn(
            "synthetic-private-content",
            (self.harness.folder / "logs/credentials.log").read_text(),
        )
        self.assertEqual(
            (self.harness.private / "alice-password").read_bytes(),
            b"synthetic-private-content",
        )

    def test_product_commands_enter_service_home_and_set_runtime(self):
        remote = Path(__file__).with_name("remote.sh").read_text()
        function = remote[
            remote.index("as_product() {") : remote.index("user_service() {")
        ]
        home = self.root / "service home"
        home.mkdir(mode=0o700)
        operator = self.root / "operator-private"
        operator.mkdir(mode=0o700)
        probe = "import json,os,sys; print(json.dumps([os.getcwd(), os.environ['HOME'], os.environ['XDG_RUNTIME_DIR'], sys.argv[1:]]))"
        # Simulate sudo changing identity/HOME while retaining the caller's cwd.
        stub = 'sudo() { shift 4; "$@"; }\n'
        script = (
            stub
            + function
            + "as_product python3 -c "
            + runner.shlex.quote(probe)
            + " 'argument with spaces'"
        )
        result = subprocess.run(
            ["bash", "-eu", "-c", script],
            cwd=operator,
            env=dict(
                os.environ, HOME=str(home), XDG_RUNTIME_DIR="/wrong/operator/runtime"
            ),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [
                str(home),
                str(home),
                "/run/user/" + str(os.getuid()),
                ["argument with spaces"],
            ],
        )

    def test_missing_service_home_stops_before_command(self):
        remote = Path(__file__).with_name("remote.sh").read_text()
        function = remote[
            remote.index("as_product() {") : remote.index("user_service() {")
        ]
        script = (
            'sudo() { shift 4; "$@"; }\n' + function + "as_product echo SHOULD_NOT_RUN"
        )
        result = subprocess.run(
            ["bash", "-eu", "-c", script],
            cwd=self.root,
            env=dict(os.environ, HOME=str(self.root / "missing-home")),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("SHOULD_NOT_RUN", result.stdout)

    def test_documented_install_enters_release_from_operator_directory(self):
        remote = Path(__file__).with_name("remote.sh").read_text()
        command = next(
            line.strip()
            for line in remote.splitlines()
            if "exec python3 deploy.py install" in line
        )
        readme = (Path(__file__).resolve().parent.parent / "README.md").read_text()
        self.assertIn(
            command.replace("sudo -n ", "sudo ").replace('"$product"', '"$release"'),
            readme,
        )
        release = self.root / "service home/releases/myproduct-test"
        release.mkdir(parents=True)
        (release / "deploy.py").write_text(
            "import os,sys; print(os.getcwd()); print(sys.argv[1])\n"
        )
        operator = self.root / "operator-private"
        operator.mkdir(mode=0o700)
        script = 'sudo() { shift 4; "$@"; }\nproduct=$1\n' + command
        result = subprocess.run(
            ["bash", "-eu", "-c", script, "bash", str(release)],
            cwd=operator,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [str(release), "install"])

    def test_guest_security_profile_checks(self):
        remote = Path(__file__).with_name("remote.sh").read_text()
        function = remote[remote.index("profile() {") : remote.index("facts() {")]
        stubs = """
getenforce() { echo "$selinux_value"; }
systemctl() {
    if [[ $2 == fapolicyd ]]; then
        if [[ $4 == ActiveState ]]; then echo "$policy_value"; else echo "$enabled_value"; fi
    else echo "$firewall_value"; fi
}
"""
        for role, policy, enabled, selinux, firewall, expected in (
            ("DEV", "inactive", "disabled", "Enforcing", "active", 0),
            ("DEV", "active", "enabled", "Enforcing", "active", 1),
            ("DEV", "inactive", "enabled", "Enforcing", "active", 1),
            ("PROD", "active", "enabled", "Enforcing", "active", 0),
            ("PROD", "inactive", "disabled", "Enforcing", "active", 1),
            ("PROD", "active", "enabled", "Permissive", "active", 1),
            ("DEV", "inactive", "disabled", "Enforcing", "inactive", 1),
        ):
            with self.subTest(
                role=role, policy=policy, selinux=selinux, firewall=firewall
            ):
                settings = (
                    f"role={role}; policy_value={policy}; enabled_value={enabled}; "
                    f"selinux_value={selinux}; firewall_value={firewall}\n"
                )
                result = subprocess.run(
                    ["bash", "-e", "-c", settings + stubs + function + "profile"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.returncode, expected, result.stdout + result.stderr
                )


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "prepare", Path(__file__).with_name("prepare_dev_snapshot.py")
        )
        assert spec is not None and spec.loader is not None
        self.prepare = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.prepare)
        self.config = {
            "DEV_VMID": "107",
            "PROD_VMID": "108",
            "DEV_IP": "192.0.2.107",
            "SSH_USER": "tester",
        }
        self.client = mock.Mock()
        self.snapshots = [{"name": "clean-agent"}]

        def request(method, path):
            if path.endswith("/snapshot"):
                return self.snapshots
            if path.endswith("/config"):
                return {"name": "unchanged source"}
            if path.endswith("/status/current"):
                return {"status": "running"}
            if path == "/cluster/ha/resources":
                return []
            raise AssertionError(path)

        self.client.request.side_effect = request

    def test_existing_snapshot_is_never_replaced(self):
        self.snapshots.append({"name": "clean-dev"})
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            self.prepare.prepare(self.config, self.client)
        self.client.task.assert_not_called()

    def test_only_dev_mutated_and_source_snapshot_preserved(self):
        ssh = mock.patch.object(self.prepare, "ssh")
        wait = mock.patch.object(self.prepare, "wait_ssh")
        with ssh as commands, wait, contextlib.redirect_stdout(io.StringIO()):
            self.prepare.prepare(self.config, self.client)
        paths = [call.args[0] for call in self.client.task.call_args_list]
        base = "/nodes/{node}/qemu/107"
        self.assertEqual(
            paths,
            [
                base + "/status/stop",
                base + "/snapshot/clean-agent/rollback",
                base + "/status/start",
                base + "/status/shutdown",
                base + "/snapshot",
                base + "/status/start",
            ],
        )
        self.assertEqual(
            self.client.task.call_args_list[4].args[1]["snapname"], "clean-dev"
        )
        self.assertIn("disable --now fapolicyd", commands.call_args_list[0].args[1])
        self.assertNotIn("disable --now firewalld", commands.call_args_list[0].args[1])
        self.assertIn("getenforce", commands.call_args_list[1].args[1])


if __name__ == "__main__":
    unittest.main()
