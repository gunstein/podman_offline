"""Historical upgrade orchestration and private-state regressions without lab access."""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_acceptance as base
import upgrade_020 as upgrade
import upgrade_020_guest as guest
import yaml


class HistoricalHarnessTests(unittest.TestCase):
    """Retire trust only after real-source build, staged migrations and all checks."""

    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(mock.patch.object(base.runner, "RUNS", root))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.harness = base.runner.Run("historical", "unused")
        self.harness.meta.update(version="0.2.1", core_version="0.2.1")
        self.harness.revision = "current-fixture-revision"
        self.harness.step = mock.Mock(side_effect=lambda name, action: action())
        for name in (
            "readiness",
            "reset",
            "source",
            "transfer",
            "record_bundles",
            "credentials",
            "guest",
        ):
            setattr(self.harness, name, mock.Mock())
        self.private_guest = self.stack.enter_context(
            mock.patch.object(upgrade, "guest")
        )

    def test_real_old_bundles_and_staged_upgrades_precede_trust_retirement(self):
        upgrade.execute(self.harness)
        names = [call.args[0] for call in self.harness.step.call_args_list]
        self.assertEqual(self.harness.meta["legacy_revision"], upgrade.LEGACY_REVISION)
        self.assertEqual(
            self.harness.meta["upgrade_revision"], "current-fixture-revision"
        )
        self.assertLess(
            names.index("03-legacy-build"), names.index("07-current-images")
        )
        self.assertLess(names.index("06-markers"), names.index("08-migrate-app1"))
        self.assertLess(names.index("08-observe-app1"), names.index("08-retire-app1"))
        self.assertLess(names.index("08-retire-app1"), names.index("08-migrate-app2"))
        self.assertLess(names.index("08-database-auth"), names.index("08-retire-app2"))
        self.assertEqual(
            self.harness.transfer.call_args_list,
            [
                mock.call("0.2.0", bundle="app1"),
                mock.call("0.2.0", bundle="app2"),
                mock.call(bundle="app1"),
                mock.call(bundle="app2"),
            ],
        )
        for component in ("app1", "app2"):
            for check in ("health", "e2e", "markers", "observe"):
                self.assertLess(
                    names.index("08-" + check + "-" + component),
                    names.index("08-retire-" + component),
                )
        self.assertTrue(self.harness.finished)

    def test_failure_never_retires_unverified_release_or_continues_upgrade(self):
        for failure in (
            "08-e2e-app1",
            "08-markers-app1",
            "08-observe-app1",
            "08-database-auth",
        ):
            with self.subTest(step=failure):
                self.harness.guest.reset_mock()
                self.harness.finished = False

                def step(name, action, failure=failure):
                    if name == failure:
                        raise RuntimeError("fixture failure")
                    action()

                self.harness.step.side_effect = step
                with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                    upgrade.execute(self.harness)
                retired = [
                    call.kwargs["bundle"]
                    for call in self.harness.guest.call_args_list
                    if call.args[1] == "legacy-retire"
                ]
                self.assertEqual(
                    retired, ["app1"] if failure == "08-database-auth" else []
                )
                self.assertFalse(self.harness.finished)


class HistoricalTrustTests(unittest.TestCase):
    """Execute the remote trust-retirement shell with a recording fapolicyd stub."""

    def test_changed_sibling_trust_prevents_retirement(self):
        for changed in (False, True):
            with (
                self.subTest(changed=changed),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                sibling = "file /var/lib/myproduct/releases/myproduct-app2-0.2.0/deploy.py 123 "
                (root / "legacy-trust-before").write_text(sibling + "old\n")
                shell = base.shell_code(
                    Path(__file__).with_name("remote.sh").read_text(),
                    action="legacy-retire",
                )
                body = shell
                script = (
                    r"""set -euo pipefail
base=$1
bundle=app1
state=/var/lib/myproduct
product=$state/releases/myproduct-app1-0.2.1
old_version=0.2.0
sibling=$2
sudo() {
    if [[ $* == *--dump-db* ]]; then
        printf '%s\n' "$sibling"
    else
        printf '%s\n' "$*" >> "$base/mutations"
    fi
}
wait_trust() { printf 'wait\n' >> "$base/mutations"; }
"""
                    + body
                )
                result = subprocess.run(
                    [
                        "bash",
                        "-c",
                        script,
                        "bash",
                        str(root),
                        sibling + ("changed" if changed else "old"),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                mutations = root / "mutations"
                if changed:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(mutations.exists())
                else:
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )
                    self.assertIn(
                        "--file delete /var/lib/myproduct/releases/myproduct-app1-0.2.0/deploy.py --trust-file myproduct-app1",
                        mutations.read_text(),
                    )
                    self.assertNotIn(
                        "--trust-file myproduct-app2", mutations.read_text()
                    )


class HistoricalStateTests(unittest.TestCase):
    """Run actual migration/observation code with private temporary files and host stubs."""

    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(mock.patch.object(guest, "HOME", self.root))
        self.stack.enter_context(
            mock.patch.object(guest, "SNAPSHOT", self.root / ".upgrade-020.json")
        )
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.host = self.stack.enter_context(
            mock.patch.object(guest, "command", side_effect=self.command)
        )
        self.changed_volume = False
        self.changed_sibling = False
        for component in guest.COMPONENTS:
            self.write(
                component + "/config.yaml",
                "GENERATED_SECRETS: [retained/session]\nSECRET_FILES: {retained: [private]}\n",
            )
            password = "identity-db" if component == "core" else "database"
            self.write(
                component + "/generated-certificates/" + password + "/password",
                "legacy secret with LF\n",
            )
            self.write(component + "/files/import.tar", "old import")
            self.write("installed/" + component, "0.2.0\n")
            for suffix in ("yaml", "kube"):
                self.write(
                    ".config/containers/systemd/myproduct-" + component + "." + suffix,
                    "old render",
                )
        guest.main("baseline", "0.2.1")

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        path.chmod(0o600)
        return path

    def command(self, args):
        if args[:3] == ["podman", "volume", "inspect"]:
            return json.dumps(
                [
                    {
                        "Name": args[-1],
                        "Mountpoint": "/fixture/" + args[-1],
                        "CreatedAt": "changed" if self.changed_volume else "old",
                    }
                ]
            )
        if args[0] == "systemctl":
            return "ActiveState=active\nInvocationID=fixture\nExecMainStartTimestampMonotonic=123"
        self.assertEqual(args[:4], ["podman", "inspect", "--format", "json"])
        return json.dumps(
            [
                {
                    "Name": name,
                    "Id": name + "-id",
                    "RestartCount": 0,
                    "State": {
                        "Status": "running",
                        "Health": {"Status": "healthy"},
                        "Pid": 999
                        if self.changed_sibling and name.startswith("app2-")
                        else 100,
                        "StartedAt": "fixture",
                    },
                }
                for name in args[4:]
            ]
        )

    def installed(self, components):
        for component in components:
            self.write("installed/" + component, "0.2.1\n")
            self.write(
                ".config/containers/systemd/myproduct-" + component + ".yaml",
                "new render",
            )
            self.write(component + "/files/import.tar", "new import")

    def test_manual_additions_then_each_upgrade_preserve_legacy_passwords(self):
        before = guest.observe()
        guest.main("migrate-app1", "0.2.1")
        core = yaml.safe_load((self.root / "core/config.yaml").read_text())
        self.assertEqual(core["DB_USER"], "identity")
        self.assertEqual(
            core["GENERATED_SECRETS"],
            ["retained/session", "generated-certificates/identity-db/password"],
        )
        self.assertNotIn(
            "DB_HOST", yaml.safe_load((self.root / "app2/config.yaml").read_text())
        )
        self.installed(("core", "app1"))
        guest.main("check-app1", "0.2.1")
        guest.main("trust-app1", "0.2.1")
        guest.main("migrate-app2", "0.2.1")
        self.installed(("app2",))
        guest.main("check-app2", "0.2.1")
        guest.main("trust-app2", "0.2.1")
        after = guest.observe()
        self.assertEqual(before["volumes"], after["volumes"])
        self.assertEqual(guest.SNAPSHOT.stat().st_mode & 0o777, 0o600)
        for component in guest.COMPONENTS:
            for name, digest in before["files"][component].items():
                if "/generated-certificates/" in name:
                    self.assertEqual(after["files"][component][name], digest)

    def test_volume_replacement_and_sibling_restart_are_rejected(self):
        guest.main("migrate-app1", "0.2.1")
        self.installed(("core", "app1"))
        self.changed_volume = True
        with self.assertRaisesRegex(RuntimeError, "volume identity"):
            guest.main("check-app1", "0.2.1")
        self.changed_volume = False
        self.changed_sibling = True
        with self.assertRaisesRegex(RuntimeError, "sibling container"):
            guest.main("check-app1", "0.2.1")

    def test_credential_rewrite_and_automatic_config_change_are_rejected(self):
        guest.main("migrate-app1", "0.2.1")
        self.installed(("core", "app1"))
        for name in (
            "app1/generated-certificates/database/password",
            "core/config.yaml",
        ):
            with self.subTest(path=name):
                path = self.root / name
                before = path.read_bytes()
                path.write_bytes(before + b"changed")
                with self.assertRaisesRegex(
                    RuntimeError, "Credentials or persistent config"
                ):
                    guest.main("check-app1", "0.2.1")
                path.write_bytes(before)
