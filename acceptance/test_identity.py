"""Independent Identity upgrade evidence and focused lab ordering without external services."""

import contextlib
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_acceptance as base
import test_components as components

import bundle


class IdentityHarnessTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(mock.patch.object(base.runner, "RUNS", root))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.harness = base.runner.Run("identity", "unused")
        self.harness.meta.update(
            version="0.4.0", platform_version="0.4.0", identity_version="0.4.0"
        )
        self.harness.step = mock.Mock(side_effect=lambda name, action: action())
        for name in (
            "readiness",
            "reset",
            "source",
            "transfer",
            "record_bundles",
            "credentials",
            "registry_transfer",
            "reboot",
            "persistent_state",
            "guest",
        ):
            setattr(self.harness, name, mock.Mock())

    def test_identity_upgrade_transfers_only_identity_and_retires_after_all_checks(
        self,
    ):
        self.harness.upgrade_identity()
        self.harness.transfer.assert_called_once_with("0.4.1", bundle="identity")
        calls = self.harness.guest.call_args_list
        names = [call.args[1] for call in calls]
        self.assertLess(names.index("identity-before"), names.index("identity-upgrade"))
        self.assertLess(names.index("identity-after"), names.index("prod-e2e"))
        for check in (
            "identity-after",
            "identity-siblings-after",
            "prod-e2e",
            "markers-check",
            "database-auth",
        ):
            self.assertLess(names.index(check), names.index("identity-retire"))
        self.assertEqual(names[-1], "identity-siblings-after")
        build = next(
            call for call in calls if call.args[1] == "identity-upgrade-bundle"
        )
        self.assertEqual(build.kwargs["bundle"], "identity")
        self.assertEqual(build.args[2], "0.4.1")
        self.harness.persistent_state.assert_called_once_with("after")

    def test_identity_failure_stops_without_retiring_old_trust(self):
        for failure in ("identity-after", "prod-e2e", "markers-check", "database-auth"):
            with self.subTest(action=failure):
                self.harness.guest.reset_mock()

                def guest(role, action, *args, failure=failure, **kwargs):
                    if action == failure:
                        raise RuntimeError("fixture failure")

                self.harness.guest.side_effect = guest
                with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                    self.harness.upgrade_identity()
                self.assertNotIn(
                    "identity-retire",
                    [call.args[1] for call in self.harness.guest.call_args_list],
                )

    def test_focused_identity_run_keeps_both_apps_and_skips_crash_matrix(self):
        self.harness.identity_only = True
        self.harness.execute()
        calls = self.harness.guest.call_args_list
        self.assertEqual(
            [call.kwargs["bundle"] for call in calls if call.args[1] == "install"],
            ["platform", "identity", "app1", "app2", "help"],
        )
        actions = [call.args[1] for call in calls]
        self.assertIn("shared-login", actions)
        self.assertIn("identity-upgrade", actions)
        self.assertNotIn("crash", actions)
        self.assertNotIn("hang", actions)
        self.harness.reboot.assert_not_called()
        self.assertTrue(self.harness.finished)

    def test_platform_help_run_does_not_install_identity_or_read_its_credentials(self):
        self.harness.platform_help_only = True
        self.harness.execute()
        calls = self.harness.guest.call_args_list
        self.assertEqual(
            [call.kwargs["bundle"] for call in calls if call.args[1] == "install"],
            ["platform", "help"],
        )
        self.assertIn("help-without-identity", [call.args[1] for call in calls])
        self.harness.credentials.assert_not_called()
        self.harness.persistent_state.assert_not_called()
        self.assertTrue(self.harness.finished)


class IdentityEvidenceTests(unittest.TestCase):
    def test_runtime_image_content_and_credentials_are_required_beyond_version_marker(
        self,
    ):
        code = components.guest_code("IDENTITY_STATE")
        old = {
            "files": {"config.yaml": "private-config-hash"},
            "volumes": {
                "identity-data": "retained-data",
                "identity-protection": "retained-protection",
            },
            "image": "old-id",
            "image_name": "localhost/myproduct-identity:0.2.1",
        }
        new = dict(old, image="new-id", image_name="localhost/myproduct-identity:0.4.1")
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            root = Path(directory)
            (root / "installed").mkdir()
            (root / "installed/identity").write_text("0.4.1\n")
            code["observe"] = lambda: old
            with (
                mock.patch.object(Path, "home", return_value=root),
                mock.patch.object(
                    code["sys"], "argv", ["guest", "identity-before", ""]
                ),
            ):
                code["main"]()
            code["observe"] = lambda: new
            code["command"] = mock.Mock(
                side_effect=lambda args: (
                    "new-id\n"
                    if args[1:3] == ["image", "inspect"]
                    else 'HTTP/1.0 200 OK\r\n\r\n{"status":"ok","release":"0.4.1"}'
                )
            )
            with (
                mock.patch.object(Path, "home", return_value=root),
                mock.patch.object(
                    code["sys"], "argv", ["guest", "identity-after", "0.4.1"]
                ),
            ):
                code["main"]()
                for bad in (
                    dict(new, image="old-id"),
                    dict(new, files={}),
                    dict(new, volumes={}),
                    dict(new, image_name="localhost/myproduct-identity:0.2.1"),
                ):
                    code["observe"] = lambda bad=bad: bad
                    with self.assertRaises(RuntimeError):
                        code["main"]()
                code["observe"] = lambda: new
                code["command"] = lambda args: (
                    "new-id\n"
                    if args[1:3] == ["image", "inspect"]
                    else '{"release":"old"}'
                )
                with self.assertRaisesRegex(RuntimeError, "not observable"):
                    code["main"]()
            self.assertEqual(
                (root / "identity-lifecycle.json").stat().st_mode & 0o777, 0o600
            )
            self.assertNotIn("private-config-hash", output.getvalue())

    def test_identity_build_rebuilds_changed_code_and_packages_only_identity(self):
        code = base.shell_code(
            Path(__file__).with_name("remote.sh").read_text(), heredoc="HELP_BUILD"
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            texts = {
                "VERSION": "0.4.0\n",
                "PLATFORM_VERSION": "0.4.0\n",
                "IDENTITY_VERSION": "0.4.0\n",
                "deploy": "#!/bin/sh\n",
                "deployment/__init__.py": "# fixture\n",
                "deployment/__main__.py": "# fixture\n",
                "README.md": "fixture\n",
                "config/common.defaults.yaml": "HTTPS_PORT: 8443\n",
                "bundles.yaml": "product: myproduct\ncomponents:\n  platform:\n    version_file: PLATFORM_VERSION\n  identity:\n    requires: [platform]\n    version_file: IDENTITY_VERSION\n    upgrade: newer-only\n",
                "components/platform/manifests/10-proxy.yaml": "kind: Pod\n",
                "components/identity/config.defaults.yaml": "{}\n",
                "components/identity/manifests/50-identity.yaml": "kind: Pod\nspec:\n  containers:\n  - name: app\n    image: localhost/myproduct-identity:0.2.1\n    imagePullPolicy: Never\n",
                "apps/identity/Program.cs": 'app.MapGet("/health", () => Results.Ok(new { status = "ok" }));\n',
                "apps/identity/Containerfile": "FROM fixture\n",
                "scripts/prepare-host.sh": "#!/bin/sh\n",
                "quadlet/template.kube": "[Kube]\n",
            }
            for name, text in texts.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            builds = []

            def command(args, **kwargs):
                if args[:2] == ["git", "clone"]:
                    shutil.copytree(source, Path(args[-1]))
                elif args[:2] == ["podman", "build"]:
                    builds.append((args, (Path(args[-1]) / "Program.cs").read_text()))
                elif args[:2] == ["podman", "save"]:
                    Path(args[4]).write_bytes(b"stub image transport")
                else:
                    raise AssertionError("Unexpected external command: " + str(args))

            with (
                mock.patch.object(Path, "cwd", return_value=source),
                mock.patch.object(subprocess, "run", side_effect=command),
                mock.patch.multiple(
                    bundle, ROOT=source, STAGE=source / "unused", DIST=source / "dist"
                ),
                mock.patch.dict(
                    os.environ, HELP_RELEASE_VERSION="0.4.1", RELEASE_KIND="identity"
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                exec(compile(code, "HELP_BUILD", "exec"), {})  # noqa: S102 - repository action under test
            self.assertEqual(len(builds), 1)
            self.assertIn("localhost/myproduct-identity:0.4.1", builds[0][0])
            self.assertIn('release = "0.4.1"', builds[0][1])
            with tarfile.open(
                str(source / "dist/myproduct-identity-0.4.1-offline.tar.gz")
            ) as archive:
                prefix = "myproduct-identity-0.4.1/"
                names = archive.getnames()
                self.assertFalse(
                    any(
                        "components/platform" in name or "components/app1" in name
                        for name in names
                    )
                )
                images = archive.extractfile(prefix + "images/images.txt")
                assert images is not None
                self.assertEqual(
                    images.read().decode().splitlines(),
                    ["localhost/myproduct-identity:0.4.1"],
                )
                descriptor = archive.extractfile(prefix + "bundle.yaml")
                assert descriptor is not None
                self.assertIn("platform:", descriptor.read().decode())
