"""Safety/stop rules tested without SSH, Proxmox, root or network."""

import contextlib
import importlib.util
import io
import json
import os
import re
import shlex
import stat
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

    def test_completed_run_with_final_audit_denials_is_not_clean(self):
        """La avvisninger etter siste e2e underkjenne en ellers fullført kjøring."""
        self.harness.finished = True
        self.harness.prod_ready = True
        self.harness.cleanup = mock.Mock()

        def audit(role, action):
            """Simuler audit-hendelser og avvis dem bare i kontrollmodus."""
            self.harness.write("type=AVC denied\n")
            if action == "audit-check":
                raise RuntimeError("FANOTIFY/AVC events recorded")

        self.harness.guest = mock.Mock(side_effect=audit)
        self.harness.finalize()
        self.harness.guest.assert_called_once_with("PROD", "audit-check")
        self.assertFalse(self.harness.report())
        self.assertIn(
            "type=AVC denied", (self.harness.folder / "EVIDENCE.md").read_text()
        )
        self.harness.cleanup.assert_called_once()

    def test_unknown_stderr_warning_is_named_and_redacted_in_report(self):
        """Registrer også ukjente advarsler uten å eksponere kjente hemmeligheter."""
        self.harness.redactions.append("synthetic-secret")
        self.harness.step(
            "warning",
            lambda: self.harness.log_streams(
                "", "Warning: synthetic-secret uses an old key\n"
            ),
        )
        self.harness.report()
        report = (self.harness.folder / "REPORT.md").read_text()
        self.assertIn("stderr warning: Warning: [REDACTED] uses an old key", report)
        self.assertNotIn("synthetic-secret", report)

    def boot_service_fixture(self, states):
        """Kjør ekte venteløkke med stubbet systemctl og uten tidsforsinkelse."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        function = remote[
            remote.index("wait_boot_service() {") : remote.index(
                "# Bekreft blokkert internett"
            )
        ]
        state_file, calls = self.root / "boot-states", self.root / "boot-calls"
        state_file.write_text("\n".join(states) + "\n")
        calls.write_text("")
        stubs = r"""
# Hent neste systemd-tilstand og logg alle kommandoer.
user_service() {
    echo "$*" >> "$calls"
    if [[ $1 == status ]]; then echo 'service diagnostics'; return 3; fi
    value=$(head -1 "$state_file")
    if [[ $(wc -l < "$state_file") -gt 1 ]]; then tail -n +2 "$state_file" > "$state_file.next"; mv "$state_file.next" "$state_file"; fi
    echo "$value"
    [[ $value == active ]] && return 0
    return 3
}
# Unngå virkelig venting i testen.
sleep() { :; }
"""
        script = (
            "set -eu\nstate_file="
            + shlex.quote(str(state_file))
            + "\ncalls="
            + shlex.quote(str(calls))
            + "\n"
            + stubs
            + function
            + "\nwait_boot_service\n"
        )
        result = subprocess.run(
            ["bash", "-se"], input=script, capture_output=True, text=True, check=False
        )
        commands = calls.read_text().splitlines()
        self.assertTrue(all(c.startswith(("is-active ", "status ")) for c in commands))
        return result, commands

    def test_boot_service_waits_until_active_without_starting(self):
        """Godta aktivering som ender aktiv uten start- eller restart-kall."""
        result, commands = self.boot_service_fixture(
            ["activating", "activating", "active"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(commands, ["is-active myproduct.service"] * 3)

    def test_boot_service_failed_stops_immediately_with_status(self):
        """Stopp straks systemd melder failed og ta med statusdiagnostikk."""
        result, commands = self.boot_service_fixture(["failed", "active"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            commands,
            ["is-active myproduct.service", "status --no-pager myproduct.service"],
        )
        self.assertIn("service diagnostics", result.stdout)

    def test_boot_service_timeout_fails_without_starting(self):
        """Avvis en tjeneste som aldri blir aktiv innen venteløkkens grense."""
        result, commands = self.boot_service_fixture(["activating"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(commands.count("is-active myproduct.service"), 120)
        self.assertIn("within 240s", result.stdout)

    def test_audit_uses_separate_streams_and_locale_date(self):
        """Bekreft datoformat, adskilte audit-strømmer og streng feilbehandling."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        code = remote.split("<<'AUDIT'\n", 1)[1].split("\nAUDIT", 1)[0]
        self.assertIn(
            'LC_ALL=C date -d "$run_started"',
            remote.replace("@$run_started", "$run_started"),
        )
        cases = (
            (1, "", "<no matches>\n", "check", True),
            (0, "type=AVC denied\n", "warning\n", "check", False),
            (0, "type=FANOTIFY resp=deny\n", "", "check", False),
            (0, "type=AVC denied\n", "warning\n", "collect", True),
            (1, "", "Invalid start date\n", "check", False),
            (1, "<no matches>\n", "", "check", False),
            (0, "", "", "collect", False),
        )
        for status, stdout, stderr, mode, success in cases:
            with self.subTest(status=status, mode=mode, stdout=stdout):
                out, err = io.StringIO(), io.StringIO()
                result = subprocess.CompletedProcess([], status, stdout, stderr)
                with (
                    mock.patch.object(
                        subprocess, "run", return_value=result
                    ) as command,
                    mock.patch("sys.argv", ["audit", "10/12/26", "18:18:52", mode]),
                    contextlib.redirect_stdout(out),
                    contextlib.redirect_stderr(err),
                ):
                    if success:
                        exec(code, {"__name__": "audit_test"})  # noqa: S102 - test the repository-owned audit heredoc
                    else:
                        with self.assertRaises(SystemExit):
                            exec(code, {"__name__": "audit_test"})  # noqa: S102 - test the repository-owned audit heredoc
                self.assertEqual(out.getvalue().startswith(stdout), True)
                self.assertEqual(err.getvalue(), stderr)
                self.assertEqual(command.call_args.kwargs["stderr"], subprocess.PIPE)
                self.assertIn("FANOTIFY,AVC,USER_AVC", command.call_args.args[0])
                self.assertEqual(
                    command.call_args.args[0][-3:], ["10/12/26", "18:18:52", "-i"]
                )

    def state_fixture(self, digest="a"):
        """Lag syntetiske hashdata uten hemmeligheter for 24 varige filer."""
        names = (
            "config.yaml",
            "PKI/private/ca.crt",
            "PKI/private/ca.key",
            "PKI/private/ca.srl",
            "PKI/private/identity.csr",
            "PKI/private/identity.ext",
            "PKI/private/todo-client.csr",
            "PKI/private/todo-client.ext",
            "PKI/private/web.csr",
            "PKI/private/web.ext",
            "files/todo-signing.tar",
            "generated-certificates/client/todo-client.crt",
            "generated-certificates/identity-db/password",
            "generated-certificates/identity/identity.crt",
            "generated-certificates/identity/identity.key",
            "generated-certificates/todo-db/password",
            "generated-certificates/todo/ca.crt",
            "generated-certificates/todo/session-key",
            "generated-certificates/todo/todo-client.crt",
            "generated-certificates/todo/todo-client.key",
            "generated-certificates/users/alice-password",
            "generated-certificates/users/bob-password",
            "generated-certificates/web/web.crt",
            "generated-certificates/web/web.key",
        )
        return {
            "ca_der_sha256": digest * 64,
            "files_sha256": dict.fromkeys(names, digest * 64),
        }

    def test_json_stdout_with_ssh_warning_passes_without_hash_disclosure(self):
        """Bekreft gyldig JSON med SSH-advarsel og bare filstatus i bevisene."""
        state = self.state_fixture()
        warning = "** WARNING: connection is not using a post-quantum key exchange algorithm.\n"
        self.harness.guest = lambda *args, **kwargs: self.harness.command(
            ["ssh"], log_stdout=kwargs["log_stdout"]
        )
        result = subprocess.CompletedProcess([], 0, json.dumps(state), warning)
        with mock.patch.object(
            runner.subprocess, "run", return_value=result
        ) as command:
            self.harness.step("before", lambda: self.harness.persistent_state("before"))
            self.harness.step("after", lambda: self.harness.persistent_state("after"))
        self.assertTrue(command.call_args.kwargs["capture_output"])
        self.harness.report()
        for name in ("logs/before.log", "logs/after.log", "REPORT.md", "EVIDENCE.md"):
            data = (self.harness.folder / name).read_text()
            self.assertNotIn("a" * 64, data)
            self.assertIn("post-quantum key exchange", data)
            for filename in state["files_sha256"]:
                self.assertIn(
                    filename + (": likt" if name.startswith("logs/") else ""), data
                )

    def test_invalid_or_empty_json_and_nonzero_valid_json_fail(self):
        """Avvis ugyldig stdout og feilstatus selv når JSON er gyldig."""
        for status, output in (
            (0, ""),
            (0, "not json"),
            (0, "{}"),
            (7, json.dumps(self.state_fixture())),
        ):
            with self.subTest(status=status, output=output):
                self.harness.guest = lambda *args, **kwargs: self.harness.command(
                    ["ssh"], log_stdout=False
                )
                result = subprocess.CompletedProcess(
                    [], status, output, "SSH warning\n"
                )
                log = io.StringIO()
                self.harness.log = log
                with (
                    mock.patch.object(runner.subprocess, "run", return_value=result),
                    self.assertRaises(RuntimeError),
                ):
                    self.harness.persistent_state("before")
                self.assertIn("[stderr]\nSSH warning", log.getvalue())
                self.harness.log = None

    def test_zero_exit_error_on_stderr_is_still_failure(self):
        """Behold kontrollen av Podman-feil også når de skrives til stderr."""
        result = subprocess.CompletedProcess([], 0, "", "Error: failure\n")
        with (
            mock.patch.object(runner.subprocess, "run", return_value=result),
            self.assertRaises(RuntimeError),
        ):
            self.harness.command(["podman"])

    def isolation_script(
        self,
        status,
        diagnostic="Error: dial tcp: lookup registry-1.docker.io: no such host",
    ):
        """Lag isolasjonssteget med lokale stubber for nett, sudo og verktøy."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        function = remote[
            remote.index("offline() {") : remote.index("# Kontroller aktiv tjeneste")
        ]
        stubs = """
# Simuler sudo og Podman med valgt pull-status uten privilegier.
sudo() {
    if [[ $* == '-n podman pull '* ]]; then
        echo 'pull stdout'
        echo "$diagnostic" >&2
        return "$pull_status"
    fi
}
# Simuler en blokkert HTTPS-forbindelse uten nett.
curl() { echo 'curl: DNS blocked' >&2; return 6; }
# Simuler DNS-proben uten å gjøre noe oppslag.
python3() { echo 'PASS: public DNS lookup failed'; }
# Kjør den stubbede kommandoen uten en virkelig timeout.
timeout() { shift; "$@"; }
echo '** WARNING: connection is not using a post-quantum key exchange algorithm.' >&2
"""
        return (
            "set -euo pipefail\npull_status="
            + str(status)
            + "\ndiagnostic="
            + shlex.quote(diagnostic)
            + "\n"
            + stubs
            + function
            + "\noffline\n"
        )

    def test_isolation_expected_pull_failures_preserve_separate_stderr(self):
        """Godta blokkerte pull-prober og behold SSH-advarsel og diagnose på stderr."""
        for status in (125, 124):
            with self.subTest(status=status):
                name = "isolation-" + str(status)
                self.harness.step(
                    name,
                    lambda code=status: self.harness.command(
                        ["bash", "-se"], self.isolation_script(code)
                    ),
                )
                log = (self.harness.folder / ("logs/" + name + ".log")).read_text()
                stdout, stderr = log.rsplit("[stdout]\n", 1)[1].split("[stderr]\n", 1)
                self.assertIn(
                    "PASS: public pull failed (exit " + str(status) + ")", stdout
                )
                self.assertNotIn("Error: dial tcp", stdout)
                self.assertIn("pull stdout", stdout)
                self.assertNotIn("pull stdout", stderr)
                self.assertIn(
                    "pull-probe: Error: dial tcp: lookup registry-1.docker.io: no such host",
                    stderr,
                )
                self.assertIn(
                    "** WARNING: connection is not using a post-quantum", stderr
                )

    def test_isolation_permission_failure_is_not_network_evidence(self):
        """Avvis Podman exit 125 når feilen gjelder rettigheter fremfor nett."""
        with self.assertRaisesRegex(RuntimeError, "Command exited 1"):
            self.harness.command(
                ["bash", "-se"],
                self.isolation_script(125, "Error: storage: permission denied"),
            )

    def test_isolation_successful_pull_is_failure(self):
        """Avvis isolasjonssteget når et offentlig image kan hentes."""
        with self.assertRaisesRegex(RuntimeError, "Command exited 1"):
            self.harness.command(["bash", "-se"], self.isolation_script(0))

    def test_isolation_unexpected_pull_status_is_failure(self):
        """Avvis uventede pull-statuser selv når stderr har probeprefiks."""
        for status in (1, 126, 127):
            with (
                self.subTest(status=status),
                self.assertRaisesRegex(RuntimeError, "Command exited 1"),
            ):
                self.harness.command(["bash", "-se"], self.isolation_script(status))

    def test_empty_resource_stdout_does_not_hide_failed_command(self):
        """Avvis feil i ressurskommandoen før en tom stdout kan godtas."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        block = remote.split("clean)\n    facts\n", 1)[1].split("    if [[ $role", 1)[0]
        stubs = "podman() { echo 'resource warning' >&2; return 7; }\n"
        result = subprocess.run(
            ["bash", "-eu", "-c", stubs + block],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, "")
        self.assertIn("resource warning", result.stderr)

    def test_boot_id_rejects_empty_or_mixed_stdout(self):
        """Godta bare én gyldig boot-ID fra stdout."""
        boot = "12345678-1234-1234-1234-123456789abc"
        self.assertEqual(self.harness.boot_id(boot + "\n"), boot)
        for output in ("", "warning\n" + boot):
            with self.assertRaises(RuntimeError):
                self.harness.boot_id(output)

    def trust_procedure(self, source, install_status=0, health_status=0):
        """Kjør README- eller VM-prosedyren med stubbede trust- og installasjonskall."""
        if source == "remote":
            remote = Path(__file__).with_name("remote.sh").read_text()
            code = remote.split("\nupgrade)\n", 1)[1].split("\n    ;;", 1)[0]
        else:
            readme = (
                Path(__file__).resolve().parent.parent.joinpath("README.md").read_text()
            )
            section = readme.split("### Oppgradering", 1)[1].split("### fapolicyd", 1)[
                0
            ]
            code = "\n".join(re.findall(r"```sh\n(.*?)```", section, re.DOTALL))
        (self.root / "version").write_text("0.1.1\n")
        (self.root / "myproduct-0.1.1-offline.tar.gz").touch()
        calls = self.root / "trust-calls"
        calls.write_text("")
        stubs = r"""
# Registrer trust-handlinger og simuler installasjonsfeil.
sudo() {
    case "$*" in
        *'--file add'*) echo add >> "$calls";;
        *'--file delete'*) echo delete >> "$calls";;
        *'--update'*) echo update >> "$calls";;
        *'deploy.py install'*) echo install >> "$calls"; return "$install_status";;
        *'--dump-db'*) echo "fake $product/deploy.py digest";;
        *'systemctl --user'*) healthy;;
    esac
}
# Simuler bestått checksum uten å lese et virkelig arkiv.
sha256sum() { :; }
# Simuler helsekontroll etter installasjon.
healthy() { echo health >> "$calls"; return "$health_status"; }
"""
        prefix = (
            "set -eu\nbase="
            + shlex.quote(str(self.root))
            + "\nproduct=/var/lib/myproduct/releases/myproduct-0.1.1\nold_version=0.1.0\ncalls="
            + shlex.quote(str(calls))
            + "\ninstall_status="
            + str(install_status)
            + "\nhealth_status="
            + str(health_status)
            + "\n"
        )
        result = subprocess.run(
            ["bash", "-se"],
            input=prefix + stubs + code,
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result, calls.read_text().splitlines()

    def test_upgrade_trust_removed_only_after_install_and_health(self):
        """Bekreft samme trygge trust-rekkefølge i README og VM-prosedyren."""
        for source in ("remote", "README"):
            with self.subTest(source=source):
                result, calls = self.trust_procedure(source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    calls, ["add", "update", "install", "health", "delete", "update"]
                )

    def test_failed_upgrade_keeps_old_trust(self):
        """Behold gammel trust når installasjon eller helsekontroll feiler."""
        for source in ("remote", "README"):
            for install, health in ((1, 0), (0, 1)):
                with self.subTest(source=source, install=install, health=health):
                    result, calls = self.trust_procedure(source, install, health)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("delete", calls)

    def test_upgrade_preserves_credentials_and_orders_checks(self):
        """Bekreft oppgraderingsrekkefølge og gjenbruk av opprinnelige passord."""
        self.harness.meta["version"] = "0.1.0"
        self.harness.persistent_before = self.state_fixture()
        self.harness.guest = mock.Mock(return_value=json.dumps(self.state_fixture()))
        self.harness.transfer = mock.Mock()
        self.harness.credentials = mock.Mock()
        self.harness.upgrade()
        self.harness.credentials.assert_not_called()
        self.harness.transfer.assert_called_once_with("0.1.1")
        self.assertEqual(
            self.harness.guest.call_args_list,
            [
                mock.call("DEV", "upgrade-bundle", "0.1.1"),
                mock.call("PROD", "upgrade", old_version="0.1.0"),
                mock.call("PROD", "check"),
                mock.call("PROD", "persistent-state", log_stdout=False),
                mock.call("DEV", "prod-e2e"),
                mock.call("DEV", "markers-check"),
            ],
        )

    def test_upgrade_hash_change_stops_before_e2e(self):
        """Bekreft stopp før e2e når oppgraderingen endrer varig tilstand."""
        self.harness.meta["version"] = "0.1.0"
        self.harness.persistent_before = self.state_fixture()
        self.harness.guest = mock.Mock(return_value=json.dumps(self.state_fixture("b")))
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
        self.harness.guest = mock.Mock(return_value=json.dumps(self.state_fixture()))
        self.harness.execute()
        self.harness.reboot.assert_called_once()
        self.assertTrue(self.harness.finished)
        records = [
            json.loads(line)["step"]
            for line in (self.harness.folder / "record.jsonl").read_text().splitlines()
        ]
        expected = [
            "09-reboot",
            "09-wait-boot-service",
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
            for name in self.state_fixture()["files_sha256"]:
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
            self.assertEqual(len(state["files_sha256"]), 24)
            self.assertIn("files/todo-signing.tar", state["files_sha256"])
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
            return subprocess.CompletedProcess(
                args, 0, stderr=b"SSH transfer warning\n"
            )

        with mock.patch.object(runner.subprocess, "run", side_effect=transfer):
            self.harness.step("credentials", self.harness.credentials)
        self.assertNotIn(
            "synthetic-private-content",
            (self.harness.folder / "logs/credentials.log").read_text(),
        )
        self.assertIn(
            "[stderr]\nSSH transfer warning",
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


class CrashTests(unittest.TestCase):
    """Test uventet prosesskrasj med stubbet inspect, signal og klokke."""

    def setUp(self):
        """Last krasjstegets Python-kode uten å kjøre kommandoer på verten."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        code = remote.split("    python3 - <<'CRASH'\n", 1)[1].split("\nCRASH\n", 1)[0]
        self.namespace: dict = {"__name__": "fixture"}
        exec(compile(code, "remote.sh:CRASH", "exec"), self.namespace)  # noqa: S102 - repository-owned heredoc under test
        self.now = 0
        self.namespace["time"] = types.SimpleNamespace(
            monotonic=lambda: self.now, sleep=self.advance
        )
        self.calls = []
        self.output = io.StringIO()

    def advance(self, seconds):
        """Flytt testklokken uten faktisk venting."""
        self.now += seconds

    def state(
        self,
        pid: object = 1200,
        count=0,
        started="2026-10-12 21:00:00 +0200 CEST",
        stopped=False,
    ):
        """Lag inspect-JSON med starttid som inneholder mellomrom og privat kontrollfelt."""
        return {
            "State": {
                "Pid": pid,
                "Running": True,
                "StartedAt": started,
                "StoppedByUser": stopped,
            },
            "RestartCount": count,
            "Config": {"Env": ["PRIVATE=DO_NOT_LOG"]},
        }

    def run_crash(self, states, inspect_exit=0):
        """Kjør hele krasjkontrollen med kontrollerte inspect-svar og signalstatus."""
        pending = list(states)

        def run(arguments, **kwargs):
            """Returner neste inspect-svar og registrer signalet uten å sende det."""
            self.calls.append(arguments)
            if "inspect" in arguments:
                row = pending.pop(0) if len(pending) > 1 else pending[0]
                output = row if isinstance(row, str) else json.dumps([row])
                return subprocess.CompletedProcess(arguments, inspect_exit, output, "")
            self.assertEqual(arguments[:4], ["sudo", "-n", "kill", "-KILL"])
            return subprocess.CompletedProcess(arguments, 0, "", "")

        with (
            mock.patch.object(subprocess, "run", side_effect=run),
            contextlib.redirect_stdout(self.output),
        ):
            self.namespace["main"]()

    def test_valid_restart_passes_without_podman_kill_or_private_output(self):
        """Krev ny PID, starttid og teller etter nøyaktig ett verts-SIGKILL."""
        before = self.state()
        after = self.state(pid=1300, count=1, started="2026-10-12 21:00:02 +0200 CEST")
        self.run_crash([before, after])
        self.assertEqual(
            sum(call[:4] == ["sudo", "-n", "kill", "-KILL"] for call in self.calls), 1
        )
        self.assertIn(["sudo", "-n", "kill", "-KILL", "1200"], self.calls)
        self.assertFalse(
            any("podman" in call and "kill" in call for call in self.calls)
        )
        self.assertIn("PASS: én automatisk restart", self.output.getvalue())
        self.assertNotIn("DO_NOT_LOG", self.output.getvalue())
        self.assertIn("2026-10-12 21:00:02 +0200 CEST", self.output.getvalue())

    def test_invalid_or_empty_pid_fails_before_signal(self):
        """Avvis manglende, tom, negativ og farlig PID før signalet sendes."""
        for pid in (None, "", 0, 1, -1, "1200", True):
            with self.subTest(pid=pid), self.assertRaisesRegex(RuntimeError, "Ugyldig"):
                self.run_crash([self.state(pid=pid)])
        self.assertFalse(any("-KILL" in call for call in self.calls))

    def test_empty_json_or_failed_inspect_prevents_signal(self):
        """Avvis tom JSON og feilstatus selv om stdout ellers har gyldig JSON."""
        for data, status in (("", 0), (self.state(), 7)):
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                self.run_crash([data], inspect_exit=status)
        self.assertFalse(any("-KILL" in call for call in self.calls))

    def test_unchanged_restart_count_times_out(self):
        """Avvis en ny prosess uten økt Podman-restartteller etter 60 sekunder."""
        with self.assertRaisesRegex(RuntimeError, "innen 60s"):
            self.run_crash([self.state(), self.state(pid=1300, started="later")])
        self.assertEqual(self.now, 60)

    def test_same_pid_times_out(self):
        """Avvis økt teller når containerens PID ikke er ny."""
        with self.assertRaisesRegex(RuntimeError, "innen 60s"):
            self.run_crash([self.state(), self.state(count=1, started="later")])
        self.assertEqual(self.now, 60)

    def test_same_start_time_times_out(self):
        """Avvis ny PID og teller når starttid ikke har endret seg."""
        with self.assertRaisesRegex(RuntimeError, "innen 60s"):
            self.run_crash([self.state(), self.state(pid=1300, count=1)])
        self.assertEqual(self.now, 60)

    def test_stopped_by_user_fails(self):
        """Avvis brukerstopp selv om PID, starttid og teller ser nye ut."""
        with self.assertRaisesRegex(RuntimeError, "StoppedByUser"):
            self.run_crash(
                [
                    self.state(),
                    self.state(pid=1300, count=1, started="later", stopped=True),
                ]
            )

    def test_multiple_restarts_fail(self):
        """Avvis ustabil restart med teller større enn baseline pluss én."""
        with self.assertRaisesRegex(RuntimeError, "mer enn én"):
            self.run_crash(
                [self.state(), self.state(pid=1300, count=2, started="later")]
            )

    def test_crash_checks_containers_then_https_health(self):
        """Kontroller at vellykket restart følges av container- og proxyhelse."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        block = remote.split("\ncrash)\n", 1)[1].split("\nreboot)", 1)[0]
        self.assertNotIn("podman kill", block)
        self.assertIn("CRASH\n    healthy\n    wait_backend\n", block)
        function = remote[
            remote.index("wait_backend() {") : remote.index('case "$action" in\n')
        ]
        script = """set -eu
state=/var/lib/myproduct
prod_host=myproduct-proxy
prod_ip=192.0.2.2
port=8443
# Simuler et HTTP-svar som blir klart på andre forsøk.
as_product() { if [[ -f $ready ]]; then printf 200; else touch "$ready"; printf 503; fi; }
# Unngå faktisk venting i testen.
sleep() { :; }
"""
        with tempfile.TemporaryDirectory() as temporary:
            script = (
                "ready="
                + shlex.quote(temporary + "/ready")
                + "\n"
                + script
                + function
                + "\nwait_backend\n"
            )
            result = subprocess.run(
                ["bash", "-se"],
                input=script,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HTTP=503", result.stdout)
        self.assertIn("HTTP=200", result.stdout)
        self.assertIn('"https://$prod_host:$port/api/health"', function)
        self.assertIn('--cacert "$state/PKI/private/ca.crt"', function)


class SelinuxTests(unittest.TestCase):
    """Test policyoppslag og smal klassifisering med run-6-fixtures."""

    def setUp(self):
        """Last heredoc-kontrollen med syntetisk policy og faktiske run-6-linjer."""
        remote = Path(__file__).with_name("remote.sh").read_text()
        self.code = remote.split(
            "    sudo -n python3 - \"$upper_dirs\" <<'LABELS'\n", 1
        )[1].split("\nLABELS\n", 1)[0]
        self.policy = types.SimpleNamespace(
            matchpathcon=mock.Mock(side_effect=self.matchpathcon)
        )
        self.namespace: dict = {"__name__": "fixture"}
        with mock.patch.dict("sys.modules", {"selinux": self.policy}):
            exec(compile(self.code, "remote.sh:LABELS", "exec"), self.namespace)  # noqa: S102 - trusted repo heredoc under test
        self.storage = self.namespace["STORAGE"]
        self.upper_layers = set()
        self.filesystem = types.SimpleNamespace(
            lstat=mock.Mock(
                return_value=types.SimpleNamespace(st_mode=stat.S_IFREG | 0o600)
            ),
            getxattr=mock.Mock(),
            walk=os.walk,
        )
        self.namespace["os"] = self.filesystem
        self.lines = (
            Path(__file__)
            .with_name("fixtures")
            .joinpath("run-6-restorecon.log")
            .read_text()
            .splitlines()
        )
        self.upper_layers = set(
            re.findall(r"/overlay/([0-9a-f]{64})/diff", "\n".join(self.lines))
        )

    def matchpathcon(self, path, mode):
        """Returner syntetiske policytyper for lagerets kjente stiprofiler."""
        probes = {
            str(self.storage / "overlay-layers"),
            str(self.storage / "volumes/x/_data/y"),
        }
        if mode == 0:
            self.assertIn(path, probes)
        else:
            self.assertIn(
                mode,
                (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK, stat.S_IFSOCK, stat.S_IFIFO),
            )
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

    def test_restorecon_stderr_is_logged_and_fails(self):
        """Avvis restorecon-diagnostikk ved exit 0 og behold den på stderr."""
        output, errors = io.StringIO(), io.StringIO()
        result = subprocess.CompletedProcess([], 0, "", "diagnostic\n")
        with (
            mock.patch.object(subprocess, "run", return_value=result),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(errors),
            self.assertRaisesRegex(RuntimeError, "diagnostikk på stderr"),
        ):
            self.namespace["dryrun"](["storage"])
        self.assertNotIn("diagnostic", output.getvalue())
        self.assertEqual(errors.getvalue(), "diagnostic\n")

    def test_policy_probes_use_zero_without_lstat(self):
        """Bekreft at bare de eksplisitte policy-probene bruker modus 0."""
        self.filesystem.lstat.side_effect = AssertionError("Prober skal ikke stat-es")
        with contextlib.redirect_stdout(io.StringIO()):
            self.namespace["check_equivalence"]()
        self.assertEqual(
            self.policy.matchpathcon.call_args_list,
            [
                mock.call(str(self.storage / "overlay-layers"), 0),
                mock.call(str(self.storage / "volumes/x/_data/y"), 0),
            ],
        )
        self.filesystem.getxattr.assert_not_called()

    def test_existing_file_types_are_passed_without_permission_bits(self):
        """Bekreft policyoppslag med filtypen for katalog, fil, socket og FIFO."""
        path = self.storage / "overlay/sample"
        self.filesystem.getxattr.return_value = b"u:r:container_ro_file_t:s0"
        for kind in (stat.S_IFDIR, stat.S_IFREG, stat.S_IFSOCK, stat.S_IFIFO):
            with self.subTest(kind=kind), contextlib.redirect_stdout(io.StringIO()):
                self.filesystem.lstat.return_value = types.SimpleNamespace(
                    st_mode=kind | 0o755
                )
                self.namespace["check_label"](path)
                self.policy.matchpathcon.assert_called_with(str(path), kind)
                self.filesystem.getxattr.assert_called_with(
                    str(path), "security.selinux", follow_symlinks=False
                )

    def test_mtab_and_dangling_link_use_link_type_without_following_target(self):
        """Bekreft S_IFLNK for mtab og hengende lenke uten oppslag av målet."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "etc").mkdir()
            mtab = root / "etc/mtab"
            mtab.symlink_to("/proc/mounts")
            dangling = root / "dangling"
            dangling.symlink_to(root / "absent-target")
            self.filesystem.lstat.side_effect = os.lstat
            self.filesystem.getxattr.return_value = b"u:r:container_ro_file_t:s0"
            self.policy.matchpathcon.side_effect = None
            self.policy.matchpathcon.return_value = (0, "u:r:container_ro_file_t:s0")
            for path in (mtab, dangling):
                with self.subTest(path=path), contextlib.redirect_stdout(io.StringIO()):
                    self.namespace["check_label"](path)
                self.policy.matchpathcon.assert_called_with(str(path), stat.S_IFLNK)
                self.filesystem.lstat.assert_called_with(str(path))
                self.filesystem.getxattr.assert_called_with(
                    str(path), "security.selinux", follow_symlinks=False
                )

    def test_lstat_failure_has_no_zero_mode_fallback(self):
        """Bekreft FAIL ved lstat-feil før policyoppslag uten modus-0-reserve."""
        path = self.storage / "overlay/disappeared"
        for error in (FileNotFoundError("missing"), PermissionError("denied")):
            with self.subTest(error=error):
                self.filesystem.lstat.side_effect = error
                with self.assertRaisesRegex(
                    RuntimeError, "lstat feilet for"
                ) as failure:
                    self.namespace["policy_type"](path)
                self.assertIn(str(path), str(failure.exception))
                self.policy.matchpathcon.assert_not_called()

    def test_actual_run6_storage_lines_have_named_rules(self):
        """Bekreft at kjente lagerlinjer får en navngitt regel."""
        storage = str(self.storage) + "/"
        lines = [line for line in self.lines if storage in line]
        self.assertEqual(len(lines), 157)
        for line in lines:
            rule = self.namespace["classify_line"](
                line, {"container_file_t"}, self.upper_layers
            )
            self.assertIn(
                rule,
                (
                    "ARTIFACT_DIRECTORY_TRANSITION",
                    "CUSTOM_VOLUME_CONTENT",
                    "CUSTOM_WRITABLE_LAYER",
                    "CUSTOM_WRITABLE_ROOTFS",
                ),
            )

    def test_writable_layer_rule_rejects_image_layer(self):
        """Godta container_file_t bare på kjente container-UpperDir, aldri et image-lag."""
        layer = "a" * 64
        line = (
            str(self.storage / "overlay" / layer / "diff/file")
            + " not reset as customized by admin to u:r:container_file_t:s0"
        )
        self.assertEqual(
            self.namespace["classify_line"](line, {"container_file_t"}, {layer}),
            "CUSTOM_WRITABLE_LAYER",
        )
        with self.assertRaisesRegex(RuntimeError, "Uklassifisert"):
            self.namespace["classify_line"](line, {"container_file_t"}, {"b" * 64})

    def test_upper_dirs_require_valid_container_storage_paths(self):
        """Avvis tomme eller feilplasserte inspect-stier før lagerklassifisering."""
        path = str(self.storage / "overlay" / ("a" * 64) / "diff")
        self.assertEqual(self.namespace["writable_layers"](path + "\n"), {"a" * 64})
        for output in ("", "/tmp/overlay/" + "a" * 64 + "/diff", "<no value>"):
            with self.subTest(output=output), self.assertRaises(RuntimeError):
                self.namespace["writable_layers"](output)

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
                self.namespace["classify_line"](
                    line, {"container_file_t"}, self.upper_layers
                )

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
                self.namespace["classify_line"](
                    line, {"container_file_t"}, self.upper_layers
                )

    def test_wrong_overlay_and_container_metadata_types_fail(self):
        """Bekreft at feil typer på lag og containermetadata avvises."""
        for name, actual in (
            ("overlay-layers", "container_var_lib_t"),
            ("overlay-containers", "container_ro_file_t"),
        ):
            with (
                mock.patch.object(
                    self.filesystem,
                    "getxattr",
                    return_value=("u:r:" + actual + ":s0").encode(),
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
            self.namespace["classify_line"](line, set(), self.upper_layers)

    def test_storage_dryrun_is_logged_when_outside_reports_stderr(self):
        """Behold begge lesende dry-runs selv når den første skriver diagnostikk."""
        self.namespace.update(
            check_equivalence=lambda: None,
            check_label=lambda path: None,
            writable_layers=lambda output: {"a" * 64},
            sys=types.SimpleNamespace(argv=["labels", "fixture"]),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "volumes/app/_data").mkdir(parents=True)
            self.namespace["STORAGE"] = root
            dryrun = mock.Mock(
                side_effect=[RuntimeError("stderr diagnostic"), "inside evidence"]
            )
            self.namespace["dryrun"] = dryrun
            with (
                contextlib.redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(RuntimeError, "stderr diagnostic"),
            ):
                self.namespace["main"]()
            self.assertEqual(dryrun.call_count, 2)

    def test_storage_dryrun_is_logged_even_when_outside_fails(self):
        """Bekreft at lagerets dry-run logges selv når kontrollen utenfor feiler."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "volumes/app/_data").mkdir(parents=True)
            self.namespace.update(
                STORAGE=root,
                check_equivalence=lambda: None,
                check_label=lambda path: None,
                writable_layers=lambda output: {"a" * 64},
                sys=types.SimpleNamespace(argv=["labels", "fixture"]),
            )
            dryrun = mock.Mock(
                side_effect=["Would relabel outside", "storage diagnostic"]
            )
            self.namespace["dryrun"] = dryrun
            with (
                contextlib.redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(RuntimeError, "utenfor lageret"),
            ):
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
