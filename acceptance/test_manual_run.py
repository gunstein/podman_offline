"""Local checks of the --rpm-manual scenario (backlog 69 WP6), without lab hosts.

The mapping from manual steps to the lab, the pseudo-terminal driver, the
output checks and the host-state checks in remote.sh each have a negative
case that fails for exactly the defect they report.
"""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import manual_run

REMOTE = Path(__file__).with_name("remote.sh").read_text()
VALUES = {
    "delivery": "/srv/delivery",
    "account": "myproduct-ops",
    "host": "prod.lab.test",
    "ip": "192.0.2.77",
    "port": "9443",
    "product": "myproduct",
}


class MappingTests(unittest.TestCase):
    def test_every_manual_step_has_one_lab_mapping(self):
        self.assertEqual(set(manual_run.blocks()), set(manual_run.STEPS))
        manual = manual_run.MANUAL.read_text()
        added = manual + "\n<!-- operator: new-step -->\n```sh\nmyproduct\n```\n"
        with self.assertRaisesRegex(ValueError, "Manual step IDs changed"):
            manual_run.blocks(added)
        removed = manual.replace("<!-- operator: umount -->\n", "")
        with self.assertRaisesRegex(ValueError, "Manual step IDs changed"):
            manual_run.blocks(removed)

    def test_only_the_example_values_are_replaced(self):
        self.assertEqual(set(manual_run.examples()), set(manual_run.EXAMPLE))
        self.assertEqual(
            manual_run.command("tools", VALUES),
            "sudo dnf --disablerepo='*' --setopt=localpkg_gpgcheck=0 install "
            "/srv/delivery/myproduct-tools-*.rpm",
        )
        self.assertEqual(
            manual_run.command("credentials-scp", VALUES),
            "scp -r platform myproduct-ops@prod.lab.test:/var/lib/myproduct/incoming/",
        )
        self.assertEqual(
            manual_run.command("admin", VALUES), "sudo myproduct-admin /srv/delivery"
        )
        with self.assertRaisesRegex(ValueError, "substituted, not executed"):
            manual_run.command("mount", VALUES)

    def test_a_changed_example_table_stops_the_scenario(self):
        changed = manual_run.MANUAL.read_text().replace(
            "| `produser` |", "| `opsuser` |"
        )
        with (
            mock.patch.object(
                manual_run, "examples", return_value=manual_run.examples(changed)
            ),
            self.assertRaisesRegex(ValueError, "example values changed"),
        ):
            manual_run.substitute("myproduct", VALUES)


class DriverTests(unittest.TestCase):
    """The pseudo-terminal driver, run locally against a scripted command."""

    def drive(self, command, answers=(), stop=""):
        script = manual_run.driver_script(command, answers, stop).replace(
            "IDLE = 30", "IDLE = 1"
        )
        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def test_answers_are_typed_only_at_their_prompts(self):
        result = self.drive(
            'read -r -p "Runtime account (an account): " a; read -r -p "HTTPS port [8443]: " p;'
            ' echo "got $a/${p:-default}"',
            [["Runtime account", "ops"], ["HTTPS port", ""]],
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("got ops/default", result.stdout)

    def test_the_exit_status_is_the_commands(self):
        self.assertEqual(self.drive("echo stop; exit 7").returncode, 7)

    def test_an_unexpected_prompt_fails(self):
        result = self.drive('read -r -p "Something else: " a; echo "$a"')
        self.assertEqual(result.returncode, 3)
        self.assertIn("FAIL: unexpected prompt: Something else:", result.stdout)

    def test_a_prompt_that_never_comes_fails(self):
        result = self.drive("echo done", [["Public address", "https://x"]])
        self.assertEqual(result.returncode, 3)
        self.assertIn("FAIL: prompt not shown: Public address", result.stdout)

    def test_an_earlier_mention_of_the_question_is_not_the_prompt(self):
        result = self.drive(
            'echo "Runtime account already checked"; read -r -p "Different question: " a',
            [["Runtime account", "ops"]],
        )
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("FAIL: unexpected prompt: Different question:", result.stdout)
        self.assertNotIn("ops", result.stdout.replace("Runtime account", ""))

    def test_other_prompt_forms_and_a_prompt_after_the_last_answer_fail(self):
        for command in (
            'read -r -p "Proceed? " a',
            'read -r -p "Proceed [y/N] " a',
            'read -r -p "Runtime account: " a; read -r -p "One more: " b',
        ):
            with self.subTest(command=command):
                result = self.drive(command, [["Runtime account", "ops"]])
                self.assertEqual(result.returncode, 3, result.stdout)
                self.assertIn("FAIL: unexpected prompt", result.stdout)

    def test_a_question_split_over_two_writes_is_answered(self):
        result = self.drive(
            'printf "Runtime "; sleep 0.3; read -r -p "account: " a; echo "got $a"',
            [["Runtime account", "ops"]],
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("got ops", result.stdout)

    def test_a_command_ignoring_the_closed_terminal_is_killed(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "survived"
            # The shell dies on HUP; its child ignores HUP and TERM and would
            # still write the marker.
            result = self.drive(
                f"(trap '' HUP TERM; sleep 2; touch {marker}) & "
                "echo '[OK] validated help;'; wait",
                stop="[OK] validated help;",
            )
            self.assertEqual(result.returncode, 129, result.stdout)
            time.sleep(3)
            self.assertFalse(marker.exists())

    def test_the_terminal_closes_after_the_stop_text(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "survived"
            result = self.drive(
                f'echo "[OK] validated help;"; sleep 3; touch "{marker}"',
                stop="[OK] validated help;",
            )
            self.assertEqual(result.returncode, 129)
            self.assertIn(
                "INTERRUPTED: terminal closed after [OK] validated help;", result.stdout
            )
            self.assertFalse(marker.exists())


ADMIN_FIRST = """[OK] preflight
[OK] myproduct-tools 0.3.1 is installed
[OK] installed myproduct-help-0.4.13
[OK] installed myproduct-platform-0.4.14
[OK] myproduct-ops can run myproduct-help-0.4.13
[OK] myproduct-ops can run myproduct-platform-0.4.14
[OK] next: log in as myproduct-ops (at the console, or ssh myproduct-ops@<server>) and run myproduct
PASS: myproduct-admin completed
"""
ADMIN_REPEAT = """[OK] preflight
[OK] myproduct-help-0.4.13 0.4.13 is installed
[OK] myproduct-platform-0.4.14 0.4.14 is installed
PASS: myproduct-admin completed
"""
STATUS = """COMPONENT VERSION UNIT STATE INSTALLATION
platform 0.4.14 myproduct-platform.service active installed
help 0.4.13 myproduct-help.service active installed
Product: myproduct
Pending: none
"""
RUNTIME = (
    "[OK] platform 0.4.14 installed\n[OK] help 0.4.13 installed\n"
    + STATUS
    + "PASS: myproduct completed\n"
)
BOTH = {"platform": "0.4.14", "help": "0.4.13"}


class OutputCheckTests(unittest.TestCase):
    def fails(self, check, *arguments):
        with self.assertRaises(RuntimeError) as caught:
            check(*arguments)
        return str(caught.exception)

    def test_admin_first_run(self):
        both = {"platform": "0.4.14", "help": "0.4.13"}
        manual_run.check_admin_first(ADMIN_FIRST, VALUES, both)
        for output, cause in (
            (ADMIN_FIRST.replace("[OK] installed myproduct-help-0.4.13\n", ""), "help was not installed"),
            (ADMIN_FIRST.replace("can run myproduct-platform", "cannot run myproduct-platform"),
             "cannot run platform"),
            (ADMIN_FIRST.replace(" and run myproduct", ""), "next line differs"),
            (ADMIN_FIRST.replace("installed myproduct-help-0.4.13", "installed myproduct-help-0.4.12"),
             "help was not installed"),
            (ADMIN_FIRST.replace("PASS: myproduct-admin completed\n", ""), "no PASS line"),
        ):  # fmt: skip
            with self.subTest(cause=cause):
                self.assertIn(
                    cause,
                    self.fails(manual_run.check_admin_first, output, VALUES, both),
                )

    def test_admin_repeat_installs_nothing(self):
        both = {"platform": "0.4.14", "help": "0.4.13"}
        manual_run.check_admin_repeat(ADMIN_REPEAT, VALUES, both)
        for output, cause in (
            (ADMIN_REPEAT + "[OK] installed myproduct-help-0.4.14\n", "installed or removed"),
            (ADMIN_REPEAT.replace("myproduct-help-0.4.13 0.4.13 is installed", "x"),
             "help 0.4.13 is not reported"),
            (ADMIN_REPEAT.replace("myproduct-help-0.4.13 0.4.13", "myproduct-help-0.4.12 0.4.12"),
             "help 0.4.13 is not reported"),
        ):  # fmt: skip
            with self.subTest(cause=cause):
                self.assertIn(
                    cause,
                    self.fails(manual_run.check_admin_repeat, output, VALUES, both),
                )

    def test_runtime_runs(self):
        installed = {"platform": "0.4.14", "help": "0.4.13"}
        asked = "Public address (https://<host name>:<port>) [x]: y\n" + RUNTIME
        manual_run.check_runtime(asked, VALUES, installed, BOTH, asked=True)
        repeat = STATUS + "PASS: myproduct completed\n"
        manual_run.check_runtime(repeat, VALUES, {}, BOTH)
        for output, expected, status, cause in (
            (RUNTIME, {}, BOTH, "other components were installed"),
            (RUNTIME, {"help": "0.4.14"}, BOTH, "help 0.4.14 was not installed"),
            (RUNTIME.replace("Pending: none", "Pending: install help"), installed, BOTH,
             "pending work"),
            (asked, installed, BOTH, "prompts were not as expected"),
            # The status table must show exactly the expected rows, active and installed.
            (RUNTIME.replace("platform 0.4.14 myproduct-platform.service active installed\n", ""),
             installed, BOTH, "status rows"),
            (RUNTIME.replace("help 0.4.13 myproduct-help.service active", "help 0.4.13 myproduct-help.service failed"),
             installed, BOTH, "status rows"),
            (RUNTIME.replace("help 0.4.13 myproduct-help.service", "help 0.4.12 myproduct-help.service"),
             installed, BOTH, "status rows"),
            (RUNTIME.replace("Product: myproduct", "Product: oak"), installed, BOTH, "another product"),
            (RUNTIME, installed, dict(BOTH, app1="0.1.0"), "status rows"),
            ("".join(line + "\n" for line in RUNTIME.splitlines() if "COMPONENT" not in line),
             installed, BOTH, "no status table"),
        ):  # fmt: skip
            with self.subTest(cause=cause):
                self.assertIn(
                    cause,
                    self.fails(
                        manual_run.check_runtime, output, VALUES, expected, status
                    ),
                )

    def test_missing_credential_stop(self):
        stop = (
            "ERROR: Missing /var/lib/myproduct/state/platform/credentials/web (SECRET_FILES)\n"
            "ERROR: deploy.sh install stopped; fix what it names, then run the same command again\n"
        )
        manual_run.check_runtime_missing_credential(stop, VALUES)
        other = stop.replace("credentials/web", "images/images.tar")
        self.assertIn(
            "does not name the missing web credentials",
            self.fails(manual_run.check_runtime_missing_credential, other, VALUES),
        )

    def test_credentials_never_print_contents(self):
        files = ["platform/credentials/web/web.key"]
        manual_run.check_credentials(
            "[OK] incoming/platform/credentials/web/web.key\n", files
        )
        manual_run.check_credentials(
            "[OK] incoming/platform/credentials/web/web.key is already there\n",
            files,
            True,
        )
        printed = "[OK] incoming/platform/credentials/web/web.key\n-----BEGIN PRIVATE KEY-----\n"
        self.assertIn(
            "content printed", self.fails(manual_run.check_credentials, printed, files)
        )

    def test_upgrade_retire_tools_and_journal(self):
        upgrade = (
            "[OK] installed myproduct-help-0.4.14\n"
            "[OK] myproduct-help-0.4.13 kept: help 0.4.13 is the installed version\n"
        )
        manual_run.check_admin_upgrade(upgrade, VALUES, "0.4.14", "0.4.13")
        self.assertIn("was not kept", self.fails(
            manual_run.check_admin_upgrade, upgrade.replace(" kept:", " x:"), VALUES, "0.4.14", "0.4.13"))  # fmt: skip
        retire = (
            "[OK] removed myproduct-help-0.4.13, which myproduct-ops no longer uses\n"
        )
        manual_run.check_admin_retire(retire, VALUES, "0.4.13")
        self.assertIn(
            "was not removed",
            self.fails(manual_run.check_admin_retire, "", VALUES, "0.4.13"),
        )
        manual_run.check_tools_version(
            "myproduct-tools-0.3.1-1.noarch\n", VALUES, "0.3.1"
        )
        for output in ("myproduct-tools-0.3.0-1.noarch\n",
                       "myproduct-tools-0.3.0-1.noarch\nmyproduct-tools-0.3.1-1.noarch\n"):  # fmt: skip
            with self.subTest(output=output):
                self.assertIn("tools version", self.fails(
                    manual_run.check_tools_version, output, VALUES, "0.3.1"))  # fmt: skip
        journal = (
            "-- Logs begin --\n"
            "Nov 07 20:25:04 prod myproduct[812]: myproduct-admin /srv/delivery: started\n"
            "Nov 07 20:25:09 prod myproduct[812]: myproduct-admin /srv/delivery: completed\n"
            "Nov 07 20:26:00 prod myproduct[901]: install help (bundle 0.4.14): failed (exit 1)\n"
            # The tools write a bare "failed" (tools/admin.py, tools/runtime.py);
            # prepare-host.sh's logger may write no PID.
            "Nov 07 20:26:30 prod myproduct[950]: myproduct: failed\n"
            "Nov 07 20:26:40 prod myproduct: prepare-host --user myproduct-ops --port 8443: started\n"
        )
        manual_run.check_journal(journal, VALUES)
        # As in the af22327 lab runs: journalctl in a terminal prints logger's
        # notice-level lines in bold; run_step removes that before the checks.
        bold = journal.replace(
            "myproduct: prepare-host --user myproduct-ops --port 8443: started",
            "myproduct: \x1b[0;1;39mprepare-host --user myproduct-ops --port 8443: started\x1b[0m",
        )
        self.assertNotEqual(bold, journal)
        self.assertIn(
            "unexpected journal content",
            self.fails(manual_run.check_journal, bold, VALUES),
        )
        manual_run.check_journal(
            manual_run.terminal_text(bold.replace("\n", "\r\n")), VALUES
        )
        started, completed = journal.splitlines()[1], journal.splitlines()[2]
        for output, cause in (
            ("", "unexpected journal content"),
            (journal.replace(started + "\n", ""), "no start record"),
            (journal.replace(completed + "\n", ""), "no result record"),
            (journal + "Nov 07 20:27:00 prod myproduct[9]: password=hunter2\n",
             "unexpected journal content"),
        ):  # fmt: skip
            with self.subTest(cause=cause):
                failed = self.fails(manual_run.check_journal, output, VALUES)
                self.assertIn(cause, failed)
                self.assertNotIn("hunter2", failed)


class ScenarioTests(unittest.TestCase):
    def test_steps_run_the_manual_and_every_remote_action_exists(self):
        run = mock.Mock()
        run.id, run.product = "rpm-manual-1", "myproduct"
        run.cfg = {
            "PROD_HOST": "prod.lab.test",
            "PROD_IP": "192.0.2.77",
            "HTTPS_PORT": "8443",
        }
        names = []
        run.step.side_effect = lambda name, action: names.append(name)
        manual_run.execute(run, strict=True)
        self.assertEqual(names[0], "03-build-images")
        self.assertIn("06-fapolicyd-p2", names)
        manual = [name for name in names if "-manual-" in name]
        # Each ordinary manual step runs, including the stops and the repair.
        for expected in (
            "06-manual-tools", "06-manual-admin-no-account", "06-manual-admin",
            "07-manual-runtime-no-credentials", "07-manual-credentials",
            "07-manual-credentials-other", "07-manual-runtime", "07-manual-runtime-repeat",
            "08-manual-credentials-scp", "08-manual-runtime-waiting",
            "08-manual-runtime-platform", "09-manual-runtime-interrupted",
            "09-manual-runtime-resumed", "09-manual-admin-retire",
            "10-manual-tools-version", "10-manual-tools-reinstall", "10-manual-help-journal",
        ):  # fmt: skip
            self.assertIn(expected, manual)
        self.assertLess(
            names.index("06-nothing-changed"), names.index("06-account-created")
        )
        self.assertLess(names.index("07-manual-runtime-no-credentials"),
                        names.index("07-manual-credentials"))  # fmt: skip
        self.assertLess(names.index("09-manual-runtime-interrupted"),
                        names.index("09-left-unfinished"))  # fmt: skip
        self.assertLess(names.index("09-left-unfinished"),
                        names.index("09-manual-runtime-resumed"))  # fmt: skip
        self.assertTrue(run.finished)
        for name in ("rpm-nothing-changed", "rpm-host-check", "rpm-other-medium",
                     "rpm-credentials-check", "rpm-runtime-check", "rpm-no-restart",
                     "rpm-reinstall-check", "rpm-before-upgrade", "rpm-interrupted-check",
                     "rpm-upgrade-check",
                     "rpm-retire-check",
                     "rpm-tools-damage", "rpm-tools-intact", "rpm-release-protection", "admin-baseline",
                     "admin-erase-guard", "admin-medium", "rpms", "release-rpm",
                     "help-upgrade-bundle"):  # fmt: skip
            self.assertRegex(
                REMOTE, r"(?m)^(?:[a-z0-9|-]*\|)?" + name + r"(?:\|[a-z0-9|-]*)?\)"
            )

    def test_only_the_runtime_step_takes_a_component(self):
        run = mock.Mock()
        with self.assertRaisesRegex(ValueError, "does not document"):
            manual_run.run_step(run, "admin", VALUES, component="help")


class HostCheckTests(unittest.TestCase):
    """remote.sh observation actions on local files, with the host commands stubbed."""

    def run_action(self, action, installed=(), setup=""):
        body = REMOTE[REMOTE.index("\n" + action + ")\n") + len(action) + 3 :]
        body = body[: body.index("\n    ;;\n")]
        refusal = REMOTE[REMOTE.index("expect_refusal() {") :]
        refusal = refusal[: refusal.index("\n}\n") + 3]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "db").write_text("".join(name + "\n" for name in installed))
            for name in ("invocations-first", "invocations-before-upgrade"):
                (root / name).write_text(
                    "myproduct-platform.service p1\nmyproduct-help.service h1\n"
                )
            (root / "invocations-now").write_text(
                "myproduct-platform.service p1\nmyproduct-help.service h1\n"
            )
            (root / "help-page").write_text("<p>help-release-0.4.14</p>\n")
            (root / "lib/incoming").mkdir(parents=True)
            stubs = refusal + (
                # One line at a time with a pause, as on the VM.
                'invocations() { while IFS= read -r line; do printf "%s\\n" "$line";'
                ' sleep 0.1; done < "$root/invocations-now"; }\n'
                'curl() { cat "$root/help-page"; }\n'
                'sudo() { [[ $1 == -n ]] && shift; "$@"; }\n'
                "rpm() {\n"
                '  case "$1" in\n'
                '    -q) for name in "${@:2}"; do grep -Fxq "$name" "$root/db" || return 1; done;;\n'
                '    -qa) grep "^${2%\\*}" "$root/db" || true;;\n'
                '    -V) for name in "${@:2}"; do if grep -Fxq "$name" "$root/damaged" 2>/dev/null; then return 1; fi; done; return 0;;\n'
                "    -e) if [[ -e $root/guard-open ]]; then return 0; fi\n"
                '        echo "myproduct: removing $2 is refused; use: sudo myproduct-admin" >&2; return 1;;\n'
                "  esac\n"
                "}\n"
            )
            result = subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + stubs + setup + "\n" + body],
                env=dict(
                    os.environ,
                    root=str(root),
                    base=str(root),
                    product_name="myproduct",
                    service_user="myproduct-ops",
                    install_root=str(root / "lib"),
                    release_root=str(root / "releases"),
                    erase_authorization=str(root / "erase-authorization"),
                    requested_version="0.4.14",
                    old_version="0.4.13",
                    prod_host="prod.lab.test",
                    prod_ip="192.0.2.10",
                    port="8443",
                ),
                capture_output=True,
                text=True,
                check=False,
            )
        return result

    def expect(self, action, cases, installed=()):
        for setup, cause in cases:
            with self.subTest(cause=cause):
                result = self.run_action(action, installed, setup)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                failed = [
                    line
                    for line in result.stdout.splitlines()
                    if line.startswith("FAIL: ")
                ]
                self.assertTrue(failed and cause in failed[-1], result.stdout)

    def test_retire_check(self):
        after = [
            "myproduct-help-0.4.14",
            "myproduct-platform-0.4.14",
            "myproduct-tools",
        ]
        result = self.run_action("rpm-retire-check", after)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.expect("rpm-retire-check", [
            ('echo myproduct-help-0.4.13 >> "$root/db"', "myproduct-help-0.4.13 is still installed"),
            ('mkdir -p "$release_root/myproduct-help-0.4.13"', "is left"),
            ('touch "$erase_authorization"', "the erase authorization is left"),
            ('touch "$root/guard-open"', "sudo -n rpm -e myproduct-help-0.4.14 succeeded"),
            ('echo myproduct-platform-0.4.14 > "$root/damaged"', "a remaining package is damaged"),
        ], after)  # fmt: skip

    def test_restart_checks_read_every_line(self):
        # The SIGPIPE defect of f09d677: an unchanged platform must pass.
        self.assertEqual(self.run_action("rpm-upgrade-check").returncode, 0)
        self.assertEqual(self.run_action("rpm-no-restart").returncode, 0)
        restarted = 'echo "myproduct-platform.service p9" > "$root/invocations-now"'
        self.expect("rpm-upgrade-check", [
            (restarted, "platform restarted"),
            ('echo old > "$root/help-page"', "/help/ does not serve help 0.4.14"),
        ])  # fmt: skip
        self.expect("rpm-no-restart", [(restarted, "a service restarted")])
        help_restarted = (
            'printf "myproduct-platform.service p1\\nmyproduct-help.service h2\\n"'
            ' > "$root/invocations-now"'
        )
        self.assertEqual(
            self.run_action("rpm-reinstall-check", setup=help_restarted).returncode, 0
        )
        self.expect("rpm-reinstall-check", [
            ("", "expected platform and one restarted help service"),
            ('printf "myproduct-platform.service p1\\n" > "$root/invocations-now"',
             "expected platform and one restarted help service"),
            (('printf "myproduct-platform.service p9\\nmyproduct-help.service h2\\n"'
              ' > "$root/invocations-now"'), "platform restarted"),
        ])  # fmt: skip

    def test_before_upgrade_requires_the_credentials_taken(self):
        result = self.run_action("rpm-before-upgrade")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.expect("rpm-before-upgrade", [
            ('mkdir -p "$install_root/incoming/platform"', "credentials sent with scp left"),
        ])  # fmt: skip

    def test_interrupted_check(self):
        old = 'state="$root/state"; mkdir -p "$state/installed"; echo 0.4.13 > "$state/installed/help"'
        result = self.run_action("rpm-interrupted-check", setup=old)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.expect("rpm-interrupted-check", [
            (old.replace("0.4.13", "0.4.14"), "help is completed at 0.4.14, not left at 0.4.13"),
        ])  # fmt: skip

    def test_nothing_changed_after_the_preflight_stop(self):
        fresh = 'rm -r "$install_root"'
        result = self.run_action("rpm-nothing-changed", ["myproduct-tools"], fresh)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.expect("rpm-nothing-changed", [
            (fresh + '; echo myproduct-help-0.4.13 >> "$root/db"', "a package was installed"),
            ("", "was created"),
        ], ["myproduct-tools"])  # fmt: skip


class ReleaseProtectionTests(unittest.TestCase):
    """rpm-release-protection: each attempt, run as the account, must be refused.

    The probe's Python runs with pathlib's changing operations replaced: all
    refuse (PermissionError) except the one ALLOW names, which then "succeeds"
    without changing anything; ERROR names one that fails for another reason.
    """

    PRELUDE = (
        "import io, os, pathlib\n"
        "ALLOW, ERROR = os.environ.get('ALLOW', ''), os.environ.get('ERROR', '')\n"
        "def replace(name):\n"
        "    def operation(self, *args, **kwargs):\n"
        "        if ALLOW == name + ':' + self.name:\n"
        "            return io.BytesIO() if name == 'open' else None\n"
        "        if ERROR == name:\n"
        "            raise FileNotFoundError(2, 'gone')\n"
        "        raise PermissionError(13, 'denied')\n"
        "    setattr(pathlib.Path, name, operation)\n"
        "for name in ('open', 'touch', 'symlink_to', 'rename', 'unlink', 'chmod', 'mkdir'):\n"
        "    replace(name)\n"
    )

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tree = (
            Path(directory.name) / "myproduct/releases/myproduct-platform-0.4.14"
        )
        (self.tree / "deployment").mkdir(parents=True)
        (self.tree / "deployment/__init__.py").write_text("")
        start = "<<'RELEASE_PROTECTION'\n"
        body = REMOTE[REMOTE.index(start) + len(start) :]
        self.source = body[: body.index("\nRELEASE_PROTECTION\n")]

    def probe(self, uid=None, allow="", error=""):
        return subprocess.run(
            [sys.executable, "-", str(self.tree), str(os.geteuid() if uid is None else uid)],
            input=self.PRELUDE + self.source, env=dict(os.environ, ALLOW=allow, ERROR=error),
            capture_output=True, text=True, check=False,
        )  # fmt: skip

    def test_all_refused_passes(self):
        result = self.probe()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: runtime UID confirmed", result.stdout)

    def test_each_permitted_change_fails_for_its_own_attempt(self):
        for allow, label in (
            ("open:__init__.py", "append to a packaged file"),
            ("touch:added.py", "add a module"),
            ("symlink_to:linked", "add a symlink"),
            ("rename:myproduct-platform-0.4.14", "rename the release"),
            ("unlink:__init__.py", "remove a packaged file"),
            ("chmod:myproduct-platform-0.4.14", "change release permissions"),
            ("mkdir:protection-probe-new-release", "add a release"),
            ("rename:releases", "rename releases"),
            ("rename:myproduct", "rename the product root"),
        ):
            with self.subTest(label=label):
                result = self.probe(allow=allow)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("FAIL: runtime account could " + label, result.stderr)

    def test_a_probe_that_cannot_prove_anything_fails(self):
        result = self.probe(uid=os.geteuid() + 1)
        self.assertIn("FAIL: protection probe ran as the wrong UID", result.stderr)
        result = self.probe(error="chmod")
        self.assertIn(
            "FAIL: protection probe could not test: change release permissions",
            result.stderr,
        )
        (self.tree / "deployment/__init__.py").unlink()
        result = self.probe()
        self.assertIn("FAIL: protection probe target is missing", result.stderr)

    def test_the_action_runs_the_probe_as_the_account(self):
        body = REMOTE[REMOTE.index("\nrpm-release-protection)\n") + 25 :]
        body = body[: body.index("\n    ;;\n")]
        self.assertIn(
            'sudo -n -u "$service_user" python3 - "$tree" "$(id -u "$service_user")"',
            body,
        )
        # Without the account's restrictions every attempt works: the action fails.
        stubs = (
            'rpm() { case "$1" in -qa) echo myproduct-platform-0.4.14;; -V) return 0;; esac; }\n'
            "id() { command id -u; }\n"
            'sudo() { [[ $1 == -n ]] && shift; [[ $1 == -u ]] && shift 2; "$@"; }\n'
        )
        result = subprocess.run(
            ["bash", "-c", "set -euo pipefail\n" + stubs + body],
            env=dict(os.environ, product_name="myproduct", bundle="platform",
                     service_user="myproduct-ops", release_root=str(self.tree.parent)),
            capture_output=True, text=True, check=False,
        )  # fmt: skip
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "FAIL: runtime account could append to a packaged file", result.stderr
        )


if __name__ == "__main__":
    unittest.main()
