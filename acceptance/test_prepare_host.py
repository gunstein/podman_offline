"""Harness checks, with identity/SELinux mocked; these are not real-host proof."""
# ruff: noqa: UP021, UP022

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import prepare_host_test as probe


class HostProbeTests(unittest.TestCase):
    def run_plant(self, script, account, home, arguments, code):
        """Execute the real planting program under the current test identity."""
        return probe.command([sys.executable] + arguments[1:], code)

    def test_planted_link_restores_original_after_success_or_body_failure(self):
        for body_failure in (False, True):
            for directory in (False, True):
                with (
                    self.subTest(body_failure=body_failure, directory=directory),
                    tempfile.TemporaryDirectory() as name,
                ):
                    home = Path(name)
                    path = home / "original"
                    if directory:
                        path.mkdir()
                        (path / "retained").write_bytes(b"original bytes")
                    else:
                        path.write_bytes(b"original bytes")
                    inode = path.stat().st_ino
                    with mock.patch.object(
                        probe, "as_user", side_effect=self.run_plant
                    ):
                        try:
                            with probe.planted_link(
                                None, None, home, path, home / "missing"
                            ):
                                self.assertTrue(path.is_symlink())
                                if body_failure:
                                    raise RuntimeError("body failed")
                        except RuntimeError as error:
                            self.assertTrue(body_failure)
                            self.assertEqual(str(error), "body failed")
                    self.assertFalse(path.is_symlink())
                    self.assertEqual(path.stat().st_ino, inode)
                    retained = path / "retained" if directory else path
                    self.assertEqual(retained.read_bytes(), b"original bytes")
                    self.assertEqual(list(home.glob("*-probe-*")), [])

    def test_planted_link_restores_after_partial_setup_failure(self):
        for after_rename in (False, True):
            with (
                self.subTest(after_rename=after_rename),
                tempfile.TemporaryDirectory() as name,
            ):
                home = Path(name)
                path = home / "cni"
                path.mkdir()
                (path / "retained").write_bytes(b"original bytes")
                inode = path.stat().st_ino

                def fail_plant(
                    script, account, home, arguments, code, after_rename=after_rename
                ):
                    failure = 'raise OSError("injected setup failure")\n'
                    if after_rename:
                        code = code.replace(
                            "os.symlink(sys.argv[3], sys.argv[1])\n", failure
                        )
                    else:
                        code = "import os, sys\n" + failure
                    return self.run_plant(script, account, home, arguments, code)

                with (
                    mock.patch.object(probe, "as_user", side_effect=fail_plant),
                    self.assertRaisesRegex(RuntimeError, "injected setup failure"),
                    probe.planted_link(None, None, home, path, home / "missing"),
                ):
                    self.fail("Probe body ran after failed setup")
                self.assertEqual(path.stat().st_ino, inode)
                self.assertEqual((path / "retained").read_bytes(), b"original bytes")
                self.assertEqual(list(home.glob("*-probe-*")), [])

    def test_planted_link_preserves_unexpected_replacement_and_backup(self):
        with tempfile.TemporaryDirectory() as name:
            home = Path(name)
            path = home / "lock"
            path.write_bytes(b"original bytes")
            with (
                mock.patch.object(probe, "as_user", side_effect=self.run_plant),
                self.assertRaisesRegex(RuntimeError, "original retained at"),
                probe.planted_link(None, None, home, path, home / "missing"),
            ):
                path.unlink()
                path.write_bytes(b"unexpected replacement")
            self.assertEqual(path.read_bytes(), b"unexpected replacement")
            backups = list(home.glob("*-probe-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b"original bytes")

    def test_label_gate_requires_actual_default_type_not_just_a_success_exit(self):
        expected = subprocess.CompletedProcess(
            [], 0, "system_u:object_r:var_t:s0\n", ""
        )
        with mock.patch.object(probe, "command", return_value=expected):
            with mock.patch.object(
                probe, "label", return_value="unconfined_u:object_r:var_t:s0"
            ):
                probe.require_default_type(Path("/fixture/home"))
            for context in ("unconfined_u:object_r:user_home_t:s0", "?"):
                with (
                    mock.patch.object(probe, "label", return_value=context),
                    self.assertRaises(RuntimeError),
                ):
                    probe.require_default_type(Path("/fixture/home"))

    def test_path_without_policy_context_is_refused_not_vacuous(self):
        """matchpathcon prints <<none>> for /var/tmp/.*; that must not pass or crash."""
        none = subprocess.CompletedProcess([], 0, "<<none>>\n", "")
        with mock.patch.object(probe, "command", return_value=none):
            with self.assertRaisesRegex(RuntimeError, "vacuous"):
                probe.default_type(Path("/var/tmp/fixture/home/.config"))
            with (
                mock.patch.object(
                    probe, "label", return_value="unconfined_u:object_r:user_tmp_t:s0"
                ),
                self.assertRaisesRegex(RuntimeError, "vacuous"),
            ):
                probe.require_default_type(Path("/var/tmp/fixture/home"))
        self.assertEqual(probe.PROBE_PARENT, "/var/lib")

    def test_outside_fixture_refuses_a_default_equal_to_its_wrong_label(self):
        home = subprocess.CompletedProcess(
            [], 0, "system_u:object_r:user_home_t:s0\n", ""
        )
        with (
            tempfile.TemporaryDirectory() as name,
            mock.patch.object(probe, "command", return_value=home),
            self.assertRaisesRegex(RuntimeError, "equals its wrong label"),
        ):
            probe.outside_fixture(Path(name))

    def authority(self):
        return {
            "Uid": "123 123 123 123",
            "Gid": "456 456 456 456",
            "Groups": "",
            "CapInh": "0",
            "CapPrm": "0",
            "CapEff": "0",
            "CapBnd": "0",
            "CapAmb": "0",
            "NoNewPrivs": "1",
            "SELinux": "unconfined_u:unconfined_r:unconfined_t:s0",
        }

    def test_authority_requires_every_identity_group_and_capability_slot(self):
        probe.check_authority(self.authority(), 123, 456)
        for key, value in (
            ("Uid", "123 123 0 123"),
            ("Gid", "456 0 456 456"),
            ("Groups", "0"),
            ("NoNewPrivs", "0"),
            ("SELinux", "unconfined"),
        ):
            values = self.authority()
            values[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                probe.check_authority(values, 123, 456)
        for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
            values = self.authority()
            values[key] = "00000001"
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                probe.check_authority(values, 123, 456)
        with self.assertRaises(RuntimeError):
            probe.check_authority(self.authority(), 0, 456)

    def test_controlled_replacement_executes_real_helper_for_both_boundaries(self):
        script = Path(__file__).resolve().parent.parent / "scripts/prepare-home.py"
        code = probe.RACE.replace("__HELPER_SOURCE__", repr(script.read_text()))
        for phase in ("before-open", "after-open", "lock-file", "lock-link"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                home, outside = base / "home", base / "outside"
                home.mkdir()
                outside.mkdir(mode=0o755)
                sentinel = outside / "sentinel"
                sentinel.write_bytes(b"outside bytes")
                # Initialize through the real helper's public function; its CLI
                # refuses root, while this harness may run under the current UID.
                initialize = (
                    'namespace={"__name__":"fixture"}\nexec('
                    + repr(script.read_text())
                    + ', namespace)\nnamespace["prepare"]('
                    + repr(str(home))
                    + ")\n"
                )
                result = subprocess.run(
                    [sys.executable, "-B", "-"],
                    input=initialize,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                info = outside.stat()
                result = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        "-",
                        str(script),
                        str(home),
                        str(outside),
                        phase,
                    ],
                    input=code,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                if not phase.startswith("lock-"):
                    self.assertTrue((home / ".config").is_symlink())
                self.assertEqual(outside.stat().st_uid, info.st_uid)
                self.assertEqual(
                    stat.S_IMODE(outside.stat().st_mode), stat.S_IMODE(info.st_mode)
                )
                self.assertEqual(sentinel.read_bytes(), b"outside bytes")
                self.assertEqual(
                    sorted(path.name for path in outside.iterdir()), ["sentinel"]
                )

    def test_snapshot_detects_mode_content_owner_and_label_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            file = target / "sentinel"
            file.write_bytes(b"private-looking-marker")
            with mock.patch.object(probe, "label", return_value="fixture_t"):
                before = probe.snapshot(target)
                probe.require_unchanged(target, before)
                name, uid, gid, mode, label, contents = before[1]
                changes = {
                    "mode": (name, uid, gid, mode ^ 0o010, label, contents),
                    "content": (name, uid, gid, mode, label, b"changed"),
                    "owner": (name, uid + 1, gid, mode, label, contents),
                    "label": (name, uid, gid, mode, "changed_t", contents),
                }
                for kind, row in changes.items():
                    changed = list(before)
                    changed[1] = row
                    with (
                        self.subTest(kind=kind),
                        mock.patch.object(probe, "snapshot", return_value=changed),
                        self.assertRaises(RuntimeError) as error,
                    ):
                        probe.require_unchanged(target, before)
                    self.assertNotIn("private-looking-marker", str(error.exception))

    def test_shell_loads_real_helper_and_passes_identity_without_interpolation(self):
        with mock.patch.object(probe, "command") as execute:
            probe.shell(
                Path("/trusted/scripts/prepare-host.sh"),
                123,
                456,
                Path("/var/lib/svc-orders"),
                "prepare_service_home",
                code="fixture",
                arguments=["with space"],
                check=False,
            )
        args, kwargs = execute.call_args
        command = args[0]
        self.assertEqual(command[:3], ["bash", "-eu", "-c"])
        self.assertIn('source "$1"', command[3])
        self.assertEqual(
            command[5:],
            [
                Path("/trusted/scripts/prepare-host.sh"),
                123,
                456,
                Path("/var/lib/svc-orders"),
                Path("/trusted/scripts/prepare-home.py"),
                "with space",
            ],
        )
        self.assertEqual(args[1:], ("fixture", False))
        self.assertFalse(kwargs)

    def test_failed_command_is_not_silently_accepted(self):
        failure = subprocess.CompletedProcess(["probe"], 1, stdout="", stderr="refused")
        with mock.patch.object(probe.subprocess, "run", return_value=failure):
            with self.assertRaisesRegex(RuntimeError, "refused"):
                probe.command(["probe"])
            self.assertIs(probe.command(["probe"], check=False), failure)

    def test_disposable_user_cleanup_does_not_follow_home_metadata(self):
        account = mock.Mock(pw_uid=os.geteuid(), pw_gid=os.getegid())
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(probe, "command") as execute,
            mock.patch.object(probe.pwd, "getpwnam", return_value=account),
            self.assertRaisesRegex(RuntimeError, "injected"),
            probe.temporary_account(Path(directory)),
        ):
            raise RuntimeError("injected")
        first, last = (
            execute.call_args_list[0].args[0],
            execute.call_args_list[-1].args[0],
        )
        self.assertEqual(first[0], "useradd")
        self.assertEqual(last, ["userdel", first[-1]])
        self.assertNotIn("--remove", last)
