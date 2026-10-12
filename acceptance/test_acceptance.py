"""Safety/stop rules tested without SSH, Proxmox, root or network."""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import types
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
    """Test kjøringens stoppregler, hemmeligheter og livssyklus uten labtilgang."""

    def setUp(self):
        """Opprett en isolert run-mappe og skjul testenes konsolloutput."""
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(mock.patch.object(runner, "RUNS", self.root))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.harness = runner.Run("test", "not-used")

    def test_existing_run_cannot_be_reused(self):
        """Bekreft at en eksisterende run-id aldri overskrives."""
        with self.assertRaises(FileExistsError):
            runner.Run("test", "not-used")

    def test_failed_command_is_recorded_and_not_clean(self):
        """Bekreft at kommandoens feilstatus logges og gir NOT CLEAN."""
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
        """Bekreft at en ufullført kjøring ikke kan få CLEAN PASS."""
        self.harness.step("00", lambda: None)
        self.assertFalse(self.harness.report())

    def test_duplicate_step_cannot_be_reexecuted(self):
        """Bekreft at et tidligere kjørt steg ikke utføres en gang til."""
        action = mock.Mock()
        self.harness.step("00", action)
        with self.assertRaises(FileExistsError):
            self.harness.step("00", action)
        action.assert_called_once()

    def test_no_steps_after_first_failure(self):
        """Bekreft at feil i readiness stopper videre VM-operasjoner."""
        self.harness.readiness = mock.Mock(side_effect=RuntimeError("readiness"))
        self.harness.reset = mock.Mock()
        with self.assertRaises(RuntimeError):
            self.harness.execute()
        self.harness.reset.assert_not_called()

    def test_token_and_password_are_redacted_from_logs(self):
        """Bekreft at kjente token og passord maskeres i logger og bevis."""
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
        """Bekreft at Podman-feil med exit 0 likevel stopper kjøringen."""
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
        """Bekreft at forventede negative eksempler ikke gir falsk testfeil."""
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
        """Bekreft private config-rettigheter og avvisning av dupliserte nøkler."""
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
        """Bekreft lokal hemmelighetsrydding selv når SSH-oppryddingen feiler."""
        self.harness.private = self.root / "secret"
        self.harness.private.mkdir()
        self.harness.dev_private = "/run/user/1000/test"
        self.harness.guest = mock.Mock(side_effect=RuntimeError("SSH failed"))
        with self.assertRaises(RuntimeError):
            self.harness.cleanup()
        self.assertFalse(self.harness.private.exists())

    def test_cleanup_failure_prevents_clean_pass(self):
        """Bekreft at feil i opprydding hindrer CLEAN PASS."""
        self.harness.finished = True
        with self.assertRaises(RuntimeError):
            self.harness.step(
                "11-cleanup", lambda: (_ for _ in ()).throw(RuntimeError("cleanup"))
            )
        self.assertFalse(self.harness.report())

    def test_prod_audit_is_collected_after_failure_and_preserved_in_full(self):
        """Bekreft full audit-innsamling og bevaring også etter et feilet steg."""
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
        """Bekreft opprydding og NOT CLEAN når audit ikke kan hentes."""
        self.harness.finished = True
        self.harness.prod_ready = True
        self.harness.guest = mock.Mock(side_effect=RuntimeError("audit unavailable"))
        self.harness.cleanup = mock.Mock()
        self.harness.finalize()
        self.harness.cleanup.assert_called_once()
        self.assertFalse(self.harness.report())

    def test_audit_uses_locale_date_separate_time_and_both_denial_types(self):
        """Bekreft ausearch-formatet og innsamling av FANOTIFY og AVC."""
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

    def test_denial_check_rejects_fanotify_avc_and_audit_errors(self):
        """Bekreft stopp ved avvisninger eller ugyldig audit-oppslag."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        a = remote.index(
            "LABELS\n", remote.index("    sudo -n python3 - <<'LABELS'")
        ) + len("LABELS\n")
        block = remote[
            a : remote.index("    as_product podman exec myproduct-todo-backend")
        ]
        stubs = r"""
run_started=1791821932
date() { echo 10/12/26; }
sudo() {
    case "$mode" in
      clean) echo '<no matches>'; return 1;;
      avc) echo 'type=AVC denied'; return 0;;
      fanotify) echo 'type=FANOTIFY resp=deny'; return 0;;
      error) echo 'Invalid start date'; return 1;;
    esac
}
"""
        for mode in ("clean", "avc", "fanotify", "error"):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    ["bash", "-eu", "-c", "mode=" + mode + "\n" + stubs + block],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode == 0, mode == "clean", result.stdout)

    def test_upgrade_preserves_credentials_and_orders_checks(self):
        """Bekreft oppgraderingsrekkefølge og gjenbruk av opprinnelige passord."""
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
        """Bekreft stopp før e2e når oppgraderingen endrer varig tilstand."""
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
        """Bekreft at en feilet oppgradering stopper senere kontroller."""
        self.harness.meta["version"] = "0.1.0"
        self.harness.transfer = mock.Mock()
        self.harness.guest = mock.Mock(
            side_effect=["built", RuntimeError("install failed")]
        )
        with self.assertRaisesRegex(RuntimeError, "10-install-upgrade"):
            self.harness.upgrade()
        self.assertEqual(self.harness.guest.call_count, 2)
        self.assertFalse(self.harness.finished)

    def test_full_run_rechecks_after_reboot_and_upgrade(self):
        """Bekreft at prod-kontroller gjentas etter reboot og oppgradering."""
        self.harness.meta["version"] = "0.1.0"
        self.harness.readiness = mock.Mock()
        self.harness.reset = mock.Mock()
        self.harness.source = mock.Mock()
        self.harness.transfer = mock.Mock()
        self.harness.credentials = mock.Mock()
        self.harness.reboot = mock.Mock()
        self.harness.guest = mock.Mock(
            return_value='{"files_sha256": {"files/volume.tar": "unchanged"}}'
        )
        self.harness.execute()
        self.harness.reboot.assert_called_once()
        self.assertTrue(self.harness.finished)
        records = [
            json.loads(line)["step"]
            for line in (self.harness.folder / "record.jsonl").read_text().splitlines()
        ]
        expected = [
            "09-reboot",
            "09-offline-after-reboot",
            "09-check-after-reboot",
            "09-e2e-after-reboot",
            "09-markers-after-reboot",
            "10-build-upgrade",
            "10-transfer-upgrade",
            "10-install-upgrade",
            "10-check-upgrade",
            "10-persistent-after",
            "10-e2e-upgrade",
            "10-markers-upgrade",
        ]
        self.assertEqual(records[records.index("09-reboot") :], expected)
        self.assertEqual(
            self.harness.guest.call_args_list.count(mock.call("PROD", "check")), 3
        )

    def test_persistent_snapshot_hashes_config_pki_and_files_without_content(self):
        """Bekreft filhashdekning uten at hemmelig filinnhold skrives ut."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        code = remote.split("    as_product python3 - <<'HASHES'\n", 1)[1].split(
            "\nHASHES\n", 1
        )[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = b"synthetic-secret-that-must-not-be-printed"
            for name in (
                "config.yaml",
                "generated-certificates/key",
                "PKI/private/key",
                "files/volume.tar",
            ):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(private)
            (root / "PKI/private/ca.crt").write_text(
                "-----BEGIN CERTIFICATE-----\nAQID\n-----END CERTIFICATE-----\n"
            )
            result = subprocess.run(
                ["python3", "-c", code],
                env=dict(os.environ, HOME=temporary),
                check=True,
                capture_output=True,
                text=True,
            )
            state = json.loads(result.stdout)
            self.assertEqual(len(state["files_sha256"]), 5)
            self.assertIn("files/volume.tar", state["files_sha256"])
            self.assertNotIn(private.decode(), result.stdout)

    def test_credentials_stream_to_private_files_without_logging_content(self):
        """Bekreft direkte overføring av passord til private filer uten logginnhold."""
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
            """Simuler SSH-overføring og kontroller at den bruker privat filoutput."""
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
        """Bekreft tjenestebrukerens cwd, HOME og runtime ved sudo-kjøring."""
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
        """Bekreft at et manglende tjenestehjem stopper kommandoen."""
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
        """Bekreft at README-kommandoen bytter fra operatørens cwd til releasen."""
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
        """Bekreft aksept og avvisning av VM-rollenes sikkerhetsprofiler."""
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


class SelinuxTests(unittest.TestCase):
    """Test policyoppslag og smal klassifisering med run-6-fixtures."""

    def setUp(self):
        """Last heredoc-kontrollen med syntetisk policy og faktiske run-6-linjer."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        self.code = remote.split("    sudo -n python3 - <<'LABELS'\n", 1)[1].split(
            "\nLABELS\n", 1
        )[0]
        self.policy = types.SimpleNamespace(
            matchpathcon=mock.Mock(side_effect=self.matchpathcon)
        )
        self.namespace: dict = {"__name__": "fixture"}
        with mock.patch.dict("sys.modules", {"selinux": self.policy}):
            exec(compile(self.code, "remote.sh:LABELS", "exec"), self.namespace)  # noqa: S102 - trusted repo heredoc under test
        self.storage = self.namespace["STORAGE"]
        self.lines = (
            Path(__file__)
            .with_name("fixtures")
            .joinpath("run-6-restorecon.log")
            .read_text()
            .splitlines()
        )

    def matchpathcon(self, path, mode):
        """Returner syntetiske policytyper for lagerets kjente stiprofiler."""
        self.assertEqual(mode, 0)
        if "/volumes/" in path:
            kind = "container_file_t"
        elif (
            any("/" + name in path for name in ("overlay-layers", "overlay-images"))
            or path.endswith("/overlay")
            or "/overlay/" in path
        ):
            kind = "container_ro_file_t"
        else:
            kind = "container_var_lib_t"
        return 0, "system_u:object_r:" + kind + ":s0"

    def test_actual_run6_storage_lines_have_named_rules(self):
        """Bekreft at kjente lagerlinjer får en navngitt regel."""
        storage = str(self.storage) + "/"
        lines = [line for line in self.lines if storage in line]
        self.assertEqual(len(lines), 157)
        for line in lines:
            rule = self.namespace["classify_line"](line, {"container_file_t"})
            self.assertIn(
                rule,
                (
                    "ARTIFACT_DIRECTORY_TRANSITION",
                    "CUSTOM_VOLUME_CONTENT",
                    "CUSTOM_WRITABLE_LAYER",
                    "CUSTOM_WRITABLE_ROOTFS",
                ),
            )

    def test_run6_outside_storage_lines_fail(self):
        """Bekreft at alle run-6-linjer utenfor lageret gir FAIL."""
        lines = [
            line
            for line in self.lines
            if line.startswith("Would relabel /var/lib/myproduct/.config")
        ]
        self.assertEqual(len(lines), 9)
        for line in lines:
            with self.assertRaisesRegex(RuntimeError, "utenfor lageret"):
                self.namespace["classify_line"](line, {"container_file_t"})

    def test_unknown_line_and_unknown_storage_path_fail(self):
        """Bekreft at ukjente lagerlinjer og diagnostikkmeldinger avvises."""
        for line in (
            "unexpected diagnostic",
            "Would relabel "
            + str(self.storage / "unknown")
            + " from u:r:container_ro_file_t:s0 to u:r:container_var_lib_t:s0",
        ):
            with (
                self.subTest(line=line),
                self.assertRaisesRegex(RuntimeError, "Uklassifisert"),
            ):
                self.namespace["classify_line"](line, {"container_file_t"})

    def test_wrong_overlay_and_container_metadata_types_fail(self):
        """Bekreft at feil typer på lag og containermetadata avvises."""
        for name, actual in (
            ("overlay-layers", "container_var_lib_t"),
            ("overlay-containers", "container_ro_file_t"),
        ):
            with (
                mock.patch.object(
                    os, "getxattr", return_value=("u:r:" + actual + ":s0").encode()
                ),
                contextlib.redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(RuntimeError, "avviker fra policyen"),
            ):
                self.namespace["check_label"](self.storage / name)

    def test_missing_equivalence_fails(self):
        """Bekreft at feil policy-prober avslører manglende ekvivalens."""
        self.policy.matchpathcon.return_value = (0, "u:r:var_lib_t:s0")
        self.policy.matchpathcon.side_effect = None
        with (
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(RuntimeError, "ekvivalensen"),
        ):
            self.namespace["check_equivalence"]()

    def test_missing_selinux_module_fails_clearly(self):
        """Bekreft tydelig FAIL når Python-modulen selinux mangler."""
        with (
            mock.patch.dict("sys.modules", {"selinux": None}),
            self.assertRaisesRegex(SystemExit, "selinux mangler"),
        ):
            exec(  # noqa: S102 - trusted repo heredoc under test
                compile(self.code, "remote.sh:LABELS", "exec"),
                {"__name__": "fixture"},
            )

    def test_customized_label_requires_customizable_policy(self):
        """Bekreft at tilpassede labels krever vertens customizable-policy."""
        line = next(line for line in self.lines if " not reset " in line)
        with self.assertRaisesRegex(RuntimeError, "Uklassifisert"):
            self.namespace["classify_line"](line, set())

    def test_storage_dryrun_is_logged_even_when_outside_fails(self):
        """Bekreft at lagerets dry-run logges selv når kontrollen utenfor feiler."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "volumes/app/_data").mkdir(parents=True)
            self.namespace.update(
                STORAGE=root,
                check_equivalence=lambda: None,
                check_label=lambda path: None,
            )
            dryrun = mock.Mock(
                side_effect=["Would relabel outside", "storage diagnostic"]
            )
            self.namespace["dryrun"] = dryrun
            with self.assertRaisesRegex(RuntimeError, "utenfor lageret"):
                self.namespace["main"]()
            self.assertEqual(dryrun.call_count, 2)


class SnapshotTests(unittest.TestCase):
    """Test at snapshot-klargjøring bare endrer dev og bevarer kilden."""

    def setUp(self):
        """Opprett syntetisk Proxmox-klient og snapshot-data."""
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
            """Returner syntetiske Proxmox-data for snapshot-testene."""
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
        """Bekreft at et eksisterende clean-dev aldri erstattes."""
        self.snapshots.append({"name": "clean-dev"})
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            self.prepare.prepare(self.config, self.client)
        self.client.task.assert_not_called()

    def test_only_dev_mutated_and_source_snapshot_preserved(self):
        """Bekreft dev-operasjoner og uendret clean-agent uten prod-kall."""
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
