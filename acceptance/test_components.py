"""Test component acceptance ordering and strict public observations without lab access."""

import ast
import contextlib
import io
import json
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import test_acceptance as base

REMOTE = Path(__file__).with_name("remote.sh").read_text()


def guest_code(tag):
    """Load only declarations from a named repository heredoc, without its CLI entry point."""
    tree = ast.parse(base.shell_code(REMOTE, heredoc=tag))
    tree.body = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.FunctionDef))
    ]
    namespace: dict = {"__name__": "fixture"}
    exec(compile(tree, tag, "exec"), namespace)  # noqa: S102 - repository code under test
    return namespace


class ComponentHarnessTests(unittest.TestCase):
    """Verify both install orders, scoped transfers and stop rules with guest calls stubbed."""

    def setUp(self):
        """Create a private controller run with every external operation stubbed."""
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(mock.patch.object(base.runner, "RUNS", root))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.harness = base.runner.Run("components", "unused")
        self.harness.meta["version"] = "0.2.0"
        for name in (
            "readiness",
            "reset",
            "source",
            "transfer",
            "registry_transfer",
            "credentials",
            "reboot",
            "persistent_state",
        ):
            setattr(self.harness, name, mock.Mock())
        self.harness.guest = mock.Mock()

    def test_both_install_orders_finish_with_scoped_upgrade_and_uninstall(self):
        """Require help-alone first, both apps then help, and survivor checks after removal."""
        for first, second in (("app1", "app2"), ("app2", "app1")):
            with self.subTest(first=first):
                self.harness.first_app = first
                self.harness.guest.reset_mock()
                self.harness.step = mock.Mock(side_effect=lambda name, action: action())
                self.harness.execute()
                calls = self.harness.guest.call_args_list
                installs = [
                    call.kwargs["bundle"] for call in calls if call.args[1] == "install"
                ]
                self.assertEqual(installs, [first, second, "help"])
                actions = [call.args[1] for call in calls]
                self.assertLess(actions.index("help-alone"), actions.index("install"))
                self.assertLess(
                    actions.index("shared-login"), actions.index("markers-create")
                )
                self.assertLess(
                    actions.index("siblings-before"), actions.index("upgrade")
                )
                self.assertLess(
                    actions.index("upgrade"), actions.index("siblings-after")
                )
                self.assertLess(
                    actions.index("uninstall"), actions.index("survivor-e2e")
                )
                self.assertIn("survivor-markers", actions)
                self.assertTrue(self.harness.finished)

    def test_three_bundle_transfers_are_scoped_and_upgrade_is_app1_only(self):
        """Transfer all fresh bundles and only the app1 release for its upgrade."""
        self.harness.transfer_bundles()
        self.assertEqual(
            self.harness.transfer.call_args_list,
            [mock.call(bundle=name) for name in ("app1", "app2", "help")],
        )
        self.harness.transfer.reset_mock()
        self.harness.step = mock.Mock(side_effect=lambda name, action: action())
        self.harness.upgrade()
        self.harness.transfer.assert_called_once_with("0.2.1")

    def run_upgrade_build(self, corrupt=False):
        """Run the real upgrade action against scoped fixture archives and Git/build stubs."""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "VERSION").write_text("0.2.0\n")
            build = source / "build-bundle.sh"
            build.write_text(
                '#!/usr/bin/env bash\n# Create only the three scoped upgrade artifacts for the test.\nset -euo pipefail\nversion=$(cat VERSION)\nfor bundle in app1 app2 help; do\n    mkdir -p dist "build/bundle/myproduct-$bundle-$version/images"\n    archive="myproduct-$bundle-$version-offline.tar.gz"\n    printf fixture > "dist/$archive"\n    (cd dist && sha256sum "$archive" > "$archive.sha256")\n    printf \'localhost/upgrade-fixture:1\\n\' > "build/bundle/myproduct-$bundle-$version/images/images.txt"\ndone\n'
                + (
                    "printf damaged >> dist/myproduct-app1-0.2.1-offline.tar.gz\n"
                    if corrupt
                    else ""
                )
            )
            build.chmod(0o700)
            stubs = 'git() { if [[ "$*" == "diff --name-only" ]]; then echo VERSION; fi; }\n'
            code = base.shell_code(REMOTE, action="upgrade-bundle")
            result = subprocess.run(
                ["bash", "-se"],
                input="set -euo pipefail\nsrc="
                + str(source)
                + "\nrequested_version=0.2.1\n"
                + stubs
                + code,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual((source / "VERSION").read_text(), "0.2.1\n")
            self.assertFalse(
                (source / "dist/myproduct-0.2.1-offline.tar.gz.sha256").exists()
            )
            return result

    def test_upgrade_build_checks_scoped_app1_archive(self):
        """Accept three scoped artifacts without requiring the obsolete monolithic filename."""
        result = self.run_upgrade_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("myproduct-app1-0.2.1-offline.tar.gz: OK", result.stdout)
        self.assertIn("localhost/upgrade-fixture:1", result.stdout)

    def test_upgrade_build_bad_checksum_stops_before_image_list(self):
        """Reject a damaged app1 upgrade before printing or transferring its image list."""
        result = self.run_upgrade_build(corrupt=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout)
        self.assertNotIn("localhost/upgrade-fixture:1", result.stdout)

    def test_sibling_change_stops_before_later_e2e(self):
        """Reject a changed sibling observation before reporting upgrade checks as passed."""

        def guest(role, action, *args, **kwargs):
            """Fail only the observation after the upgrade."""
            if action == "siblings-after":
                raise RuntimeError("Changed sibling")

        self.harness.guest.side_effect = guest
        with self.assertRaisesRegex(RuntimeError, "10-siblings-after"):
            self.harness.upgrade()
        self.assertNotIn(
            mock.call("DEV", "prod-e2e"), self.harness.guest.call_args_list
        )
        self.assertFalse(self.harness.finished)

    def test_guest_parameter_carries_bundle_without_changing_other_arguments(self):
        """Include the validated bundle selection in stdin arguments for fixed remote steps."""
        self.harness.cfg = {
            "LAB_CIDR": "192.0.2.0/24",
            "PROD_IP": "192.0.2.2",
            "PROD_HOST": "proxy",
            "HTTPS_PORT": "8443",
        }
        self.harness.ssh = mock.Mock()
        self.harness.guest = types.MethodType(base.runner.Run.guest, self.harness)
        self.harness.guest("PROD", "install", bundle="app2")
        header = self.harness.ssh.call_args.args[1].splitlines()[0]
        self.assertTrue(header.endswith(" app2"))


class ComponentObservationTests(unittest.TestCase):
    """Verify strict dependencies, inventory unions, persistence and untouched sibling proofs."""

    def test_inventory_combines_installed_component_manifests(self):
        """Require all containers across separate installed YAML files to be healthy."""
        code = guest_code("HEALTHY")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / ".config/containers/systemd"
            units.mkdir(parents=True)
            for name in ("core", "app1", "app2", "help"):
                (units / ("myproduct-" + name + ".yaml")).write_text(
                    "kind: Pod\nmetadata: {name: "
                    + name
                    + "-pod}\nspec:\n  containers: [{name: app}]\n"
                )
            names = {name + "-pod-app" for name in ("core", "app1", "app2", "help")}
            rows = [
                {
                    "Name": name,
                    "IsInfra": False,
                    "IsService": False,
                    "State": {"Status": "running", "Health": {"Status": "healthy"}},
                }
                for name in names
            ]

            def podman(arguments):
                """Return a complete safe inventory while keeping inspect private."""
                return json.dumps(rows) if "inspect" in arguments else "id\n"

            code["podman"] = podman
            with (
                mock.patch.object(Path, "home", return_value=root),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                code["main"]()
            self.assertIn("all 4 app containers", output.getvalue())
            rows.pop()
            with (
                mock.patch.object(Path, "home", return_value=root),
                self.assertRaisesRegex(RuntimeError, "Missing"),
            ):
                code["main"]()

    def test_duplicate_names_across_components_fail_before_inventory_command(self):
        """Reject duplicate installed names before asking Podman for container state."""
        code = guest_code("HEALTHY")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / ".config/containers/systemd"
            units.mkdir(parents=True)
            for name in ("core", "app1"):
                (units / ("myproduct-" + name + ".yaml")).write_text(
                    "kind: Pod\nmetadata: {name: duplicate}\nspec:\n  containers: [{name: app}]\n"
                )
            code["podman"] = mock.Mock()
            with (
                mock.patch.object(Path, "home", return_value=root),
                self.assertRaisesRegex(RuntimeError, "across components"),
            ):
                code["main"]()
            code["podman"].assert_not_called()

    def test_help_alone_requires_exact_failure_without_state_writes(self):
        """Accept only the documented dependency refusal and an unchanged component home."""
        code = guest_code("HELP_ALONE")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.CompletedProcess(
                [],
                1,
                "",
                "ERROR: Install an app bundle with core before installing help\n",
            )
            with (
                mock.patch.object(Path, "home", return_value=root),
                mock.patch.object(code["sys"], "argv", ["guest", "deploy.py"]),
                mock.patch.object(subprocess, "run", return_value=result),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                code["main"]()
                (root / "app1").mkdir()
                with self.assertRaisesRegex(SystemExit, "changed"):
                    code["main"]()
                (root / "app1").rmdir()
                result.returncode = 0
                with self.assertRaisesRegex(SystemExit, "did not refuse"):
                    code["main"]()

    def test_sibling_observation_compares_every_public_field_and_trust(self):
        """Reject any PID, start, restart, version or trust change without printing trust hashes."""
        code = guest_code("SIBLINGS")
        before = {
            "containers": {
                "app2-todo-backend": {
                    "Pid": 1234,
                    "StartedAt": "before",
                    "RestartCount": 0,
                }
            },
            "versions": {"app2": "0.2.0"},
            "trust": ["public script trust hash withheld"],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "siblings.json"
            code["observe"] = lambda: before
            with (
                mock.patch.object(
                    code["sys"], "argv", ["guest", "siblings-before", str(path)]
                ),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                code["main"]()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(before["trust"][0], output.getvalue())
            changes = [
                {
                    "containers": {
                        "app2-todo-backend": {
                            "Pid": 4321,
                            "StartedAt": "before",
                            "RestartCount": 0,
                        }
                    }
                },
                {"versions": {"app2": "other"}},
                {"trust": []},
            ]
            for change in changes:
                code["observe"] = lambda change=change: dict(before, **change)
                with (
                    mock.patch.object(
                        code["sys"], "argv", ["guest", "siblings-after", str(path)]
                    ),
                    self.assertRaisesRegex(SystemExit, "changed"),
                ):
                    code["main"]()
            code["observe"] = lambda: before
            with (
                mock.patch.object(
                    code["sys"], "argv", ["guest", "siblings-after", str(path)]
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                code["main"]()

    def test_uninstall_checks_retained_data_and_inactive_route_before_e2e(self):
        """Keep survivor health and retired route/data/network checks in the removal step."""
        block = base.shell_code(REMOTE, action="uninstall")
        for text in (
            "deploy.py uninstall",
            "volume exists app1-data",
            "network exists myproduct",
            'test "$http" = 404',
            "healthy",
            "--trust-file myproduct-app1",
        ):
            self.assertIn(text, block)
        self.assertNotIn("--delete-data", block)
        self.assertNotIn("volume rm", block)

    def test_shared_login_failure_withholds_callback_details(self):
        """Report cross-app failures without an exception's callback URL or credentials."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "acceptance").mkdir()
            (root / "dev").mkdir()
            (root / "acceptance/shared_login.py").write_text(
                Path(__file__).with_name("shared_login.py").read_text()
            )
            (root / "dev/smoke-test.py").write_text(
                'def login(user):\n    raise RuntimeError("https://proxy/app1/auth/callback?code=secret-code&state=secret-state")\n'
            )
            result = subprocess.run(
                ["python3", str(root / "acceptance/shared_login.py")],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            for value in ("secret-code", "secret-state", "callback?"):
                self.assertNotIn(value, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
