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
        self.harness.meta["version"] = "0.3.0"
        self.harness.meta["platform_version"] = "0.3.0"
        self.harness.meta["identity_version"] = "0.4.0"
        for name in (
            "readiness",
            "reset",
            "source",
            "transfer",
            "record_bundles",
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
                self.assertEqual(
                    installs, ["platform", "identity", first, second, "help"]
                )
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
            [
                mock.call(bundle=name)
                for name in ("platform", "identity", "app1", "app2", "help")
            ],
        )
        self.harness.transfer.reset_mock()
        self.harness.step = mock.Mock(side_effect=lambda name, action: action())
        self.harness.upgrade()
        self.harness.transfer.assert_called_once_with("0.3.1")

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
                input="set -euo pipefail\nproduct_name=myproduct\nsrc="
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

    def test_help_upgrade_transfers_only_help_and_retires_after_all_checks(self):
        """A genuine content/image upgrade cannot retire old trust before HTTPS/e2e checks."""
        self.harness.step = mock.Mock(side_effect=lambda name, action: action())
        self.harness.upgrade_help()
        self.harness.transfer.assert_called_once_with("0.3.2", bundle="help")
        calls = self.harness.guest.call_args_list
        actions = [call.args[1] for call in calls]
        self.assertLess(
            actions.index("help-siblings-before"), actions.index("help-upgrade")
        )
        self.assertLess(actions.index("help-upgrade"), actions.index("help-content"))
        self.assertLess(
            actions.index("help-siblings-after"), actions.index("help-retire")
        )
        self.assertLess(actions.index("prod-e2e"), actions.index("help-retire"))
        self.assertLess(actions.index("markers-check"), actions.index("help-retire"))
        self.assertEqual(actions[-1], "help-siblings-after")
        self.harness.persistent_state.assert_called_once_with("after")
        build = base.shell_code(REMOTE, action="help-upgrade-bundle")
        self.assertIn("catalog.source_descriptors(release)[kind]", build)
        self.assertIn('bundle.build_release(descriptor["version"], descriptor)', build)
        self.assertIn('"localhost/myproduct-help:" + version', build)
        self.assertIn('"<p>help-release-" + version', build)
        self.assertNotIn("./build-bundle.sh", build)

    def test_platform_upgrade_checks_siblings_e2e_and_downgrade_before_retirement(self):
        """New platform changes deliberately while siblings remain; old platform refuses before writes."""
        self.harness.meta["upgrade_version"] = "0.2.1"
        self.harness.step = mock.Mock(side_effect=lambda name, action: action())
        self.harness.upgrade_platform()
        self.harness.transfer.assert_called_once_with("0.3.1", bundle="platform")
        actions = [call.args[1] for call in self.harness.guest.call_args_list]
        self.assertLess(
            actions.index("platform-siblings-before"), actions.index("platform-upgrade")
        )
        self.assertLess(
            actions.index("platform-upgrade"), actions.index("platform-after")
        )
        self.assertLess(
            actions.index("platform-siblings-after"), actions.index("prod-e2e")
        )
        self.assertLess(
            actions.index("platform-downgrade"), actions.index("platform-retire")
        )
        self.assertEqual(actions.count("prod-e2e"), 2)
        self.assertEqual(actions[-1], "platform-siblings-after")
        call = next(
            call
            for call in self.harness.guest.call_args_list
            if call.args[1] == "platform-downgrade"
        )
        self.assertEqual(call.kwargs["old_version"], "0.3.0")

    def test_help_upgrade_failure_preserves_old_release_and_trust(self):
        """Any content, sibling or e2e failure stops before old help trust is removed."""
        for failure in (
            "help-content",
            "help-siblings-after",
            "prod-e2e",
            "markers-check",
        ):
            with self.subTest(failure=failure):
                self.harness.guest.reset_mock()

                def guest(role, action, *args, failure=failure, **kwargs):
                    if action == failure:
                        raise RuntimeError("verification failed")

                self.harness.guest.side_effect = guest
                self.harness.step = mock.Mock(side_effect=lambda name, action: action())
                with self.assertRaisesRegex(RuntimeError, "verification failed"):
                    self.harness.upgrade_help()
                self.assertNotIn(
                    "help-retire",
                    [call.args[1] for call in self.harness.guest.call_args_list],
                )

    def test_help_only_run_installs_app1_then_help_without_second_app(self):
        """Keep a focused target scenario alongside both full installation orders."""
        self.harness.help_only = True
        self.harness.step = mock.Mock(side_effect=lambda name, action: action())
        self.harness.execute()
        calls = self.harness.guest.call_args_list
        self.assertEqual(
            [call.kwargs["bundle"] for call in calls if call.args[1] == "install"],
            ["platform", "identity", "app1", "help"],
        )
        actions = [call.args[1] for call in calls]
        self.assertIn("app1-e2e", actions)
        self.assertIn("app1-markers-check", actions)
        self.assertIn("help-upgrade", actions)
        self.assertNotIn("upgrade", actions)
        self.assertEqual(
            self.harness.transfer.call_args_list,
            [
                mock.call(bundle="platform"),
                mock.call(bundle="identity"),
                mock.call(bundle="app1"),
                mock.call(bundle="help"),
                mock.call("0.3.2", bundle="help"),
            ],
        )
        self.assertTrue(self.harness.finished)

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
        # The product name under test follows the bundle as the last argument.
        self.assertTrue(header.endswith(" app2 myproduct"), header)


class ComponentObservationTests(unittest.TestCase):
    """Verify strict dependencies, inventory unions, persistence and untouched sibling proofs."""

    def test_inventory_combines_installed_component_manifests(self):
        """Require all containers across separate installed YAML files to be healthy."""
        code = guest_code("HEALTHY")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / ".config/containers/systemd"
            units.mkdir(parents=True)
            for name in ("platform", "identity", "app1", "app2", "help"):
                (units / ("myproduct-" + name + ".yaml")).write_text(
                    "kind: Pod\nmetadata: {name: "
                    + name
                    + "-pod}\nspec:\n  containers: [{name: app}]\n"
                )
            names = {
                name + "-pod-app"
                for name in ("platform", "identity", "app1", "app2", "help")
            }
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
            self.assertIn("all 5 app containers", output.getvalue())
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
            for name in ("platform", "app1"):
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
                "ERROR: Install the separate platform bundle before installing help\n",
            )
            with (
                mock.patch.object(Path, "home", return_value=root),
                mock.patch.object(code["sys"], "argv", ["guest", "deploy"]),
                mock.patch.object(subprocess, "run", return_value=result) as process,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                code["main"]()
                self.assertEqual(
                    process.call_args.args[0], ["bash", "deploy", "install"]
                )
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

    def test_platform_lifecycle_requires_restart_and_preserves_state_on_downgrade(self):
        """Reject unchanged platform identity and any mutation during an older-platform refusal."""
        code = guest_code("PLATFORM_LIFECYCLE")
        before = {
            "containers": {
                "platform-proxy-nginx": {
                    "Pid": 1234,
                    "StartedAt": "before",
                    "RestartCount": 0,
                }
            },
            "files": {"platform/config.yaml": "private-hash"},
            "version": "0.2.0",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "platform.json"
            snapshot.write_text(json.dumps(before))
            (root / "VERSION").write_text("0.2.1\n")  # The bundle's version copy.
            current: dict = dict(before, version="0.2.1")
            code["observe"] = lambda: current
            with (
                mock.patch.object(
                    code["sys"],
                    "argv",
                    ["guest", "platform-after", str(snapshot), str(root), str(root)],
                ),
                self.assertRaisesRegex(
                    SystemExit, "expected explicit platform restart"
                ),
            ):
                code["main"]()
            current["containers"] = {
                "platform-proxy-nginx": {
                    "Pid": 9999,
                    "StartedAt": "after",
                    "RestartCount": 0,
                }
            }
            with (
                mock.patch.object(
                    code["sys"],
                    "argv",
                    ["guest", "platform-after", str(snapshot), str(root), str(root)],
                ),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                code["main"]()
            self.assertNotIn("private-hash", output.getvalue())
            result = subprocess.CompletedProcess(
                [], 1, "", "ERROR: Platform downgrade refused"
            )
            with (
                mock.patch.object(
                    code["sys"],
                    "argv",
                    [
                        "guest",
                        "platform-downgrade",
                        str(snapshot),
                        str(root),
                        str(root),
                    ],
                ),
                mock.patch.object(subprocess, "run", return_value=result),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                code["main"]()
                code["observe"] = mock.Mock(
                    side_effect=[current, dict(current, files={})]
                )
                with self.assertRaisesRegex(SystemExit, "changed persistent"):
                    code["main"]()
                code["observe"] = lambda: current
                result.stdout = "+ podman load images.tar"
                with self.assertRaisesRegex(SystemExit, "before image operations"):
                    code["main"]()

    def test_sibling_observation_requires_exact_recursive_package_trust(self):
        code = guest_code("SIBLINGS")
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)

            def rooted(*parts):
                path = Path(*parts)
                return (
                    home / path.relative_to("/var/lib/myproduct")
                    if str(path).startswith("/var/lib/myproduct")
                    else path
                )

            code["pathlib"] = types.SimpleNamespace(Path=rooted)
            code["HOME"] = home
            contents = {
                "installed/platform": "0.4.3",
                "platform/config.yaml": "retained",
                ".config/containers/systemd/myproduct-platform.yaml": "retained",
                ".config/containers/systemd/myproduct-platform.kube": "retained",
            }
            for name, value in contents.items():
                path = home / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value)
            package = home / "releases/myproduct-platform-0.4.3/deployment"
            files = [
                package / "__main__.py",
                package / "common.py",
                package / "nested/render.py",
            ]
            for path in files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
            rows = ["file " + str(path) + " 123 " + "a" * 64 for path in files]
            trust = list(rows)

            def command(arguments):
                if arguments == ["fapolicyd-cli", "--dump-db"]:
                    return "\n".join(trust)
                if "network" in arguments:
                    return '[{"id":"network-id"}]'
                return json.dumps(
                    [
                        {
                            "Name": "platform-proxy-nginx",
                            "RestartCount": 0,
                            "State": {
                                "Status": "running",
                                "Health": {"Status": "healthy"},
                                "Pid": 1234,
                                "StartedAt": "before",
                            },
                        }
                    ]
                )

            code["command"] = command
            with mock.patch.object(
                code["sys"],
                "argv",
                ["guest", "identity-siblings-before", "unused", "identity"],
            ):
                self.assertEqual(code["observe"]()["trust"], sorted(rows))
                for broken in (
                    rows[:-1],
                    rows + rows[:1],
                    rows + [rows[0].replace("0.4.3", "0.4.2")],
                ):
                    trust = broken
                    with self.assertRaisesRegex(SystemExit, "exact package trust"):
                        code["observe"]()

    def test_help_siblings_compare_platform_identity_state_network_and_other_trust(
        self,
    ):
        """Unchanged route permits no arbitrary platform restart or mutation of protected fields."""
        code = guest_code("SIBLINGS")
        before = {
            "containers": {
                "platform-proxy-nginx": {
                    "Pid": 1234,
                    "StartedAt": "before",
                    "RestartCount": 0,
                }
            },
            "versions": {"platform": "0.2.0", "app1": "0.2.0"},
            "trust": ["app1 trust"],
            "state": {"app1/config.yaml": "private-hash"},
            "network": "network-id",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "help.json"
            code["observe"] = lambda: before
            with (
                mock.patch.object(
                    code["sys"],
                    "argv",
                    ["guest", "help-siblings-before", str(path), "help"],
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                code["main"]()
            for key, value in (
                (
                    "containers",
                    {
                        "platform-proxy-nginx": {
                            "Pid": 9999,
                            "StartedAt": "after",
                            "RestartCount": 0,
                        }
                    },
                ),
                ("state", {}),
                ("versions", {"platform": "0.2.1"}),
                ("network", "other"),
                ("trust", []),
            ):
                with self.subTest(key=key):
                    code["observe"] = lambda key=key, value=value: dict(
                        before, **{key: value}
                    )
                    with (
                        mock.patch.object(
                            code["sys"],
                            "argv",
                            ["guest", "help-siblings-after", str(path), "help"],
                        ),
                        self.assertRaisesRegex(SystemExit, "changed"),
                    ):
                        code["main"]()
            code["observe"] = lambda: before
            with (
                mock.patch.object(
                    code["sys"],
                    "argv",
                    ["guest", "help-siblings-after", str(path), "help"],
                ),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                code["main"]()
            self.assertNotIn("private-hash", output.getvalue())
            self.assertNotIn("app1 trust", output.getvalue())

    def test_uninstall_checks_retained_data_and_inactive_route_before_e2e(self):
        """Keep survivor health and retired route/data/network checks in the removal step."""
        block = base.shell_code(REMOTE, action="uninstall")
        for text in (
            "./deploy uninstall",
            "volume exists app1-data",
            'network exists "$product_name"',
            'test "$http" = 404',
            "healthy",
            '--trust-file "$product_name-app1"',
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


class DatabaseHarnessTests(unittest.TestCase):
    """Verify installed authentication checks with private stdin and bounded evidence."""

    def test_installed_checks_use_environment_and_both_sibling_directions(self):
        namespace = guest_code("DATABASE_AUTH")
        namespace["logs_safe"] = mock.Mock()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            secret = "sensitive;double\"' $ equals= end "
            for component in ("app1", "app2"):
                (home / "installed").mkdir(exist_ok=True)
                (home / "installed" / component).write_text("0.2.1\n")
                password = home / component / "credentials/database/password"
                password.parent.mkdir(parents=True)
                password.write_text(secret + "\n")
            positive = subprocess.CompletedProcess(
                [],
                0,
                "PASS: correct secret connects; sibling password authentication rejected\n",
                "",
            )
            identity = subprocess.CompletedProcess(
                [],
                0,
                "Database connection verified via ConnectionStrings__Default\n",
                "",
            )
            output = io.StringIO()
            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.object(
                    subprocess, "run", side_effect=[identity, positive, positive]
                ) as process,
                contextlib.redirect_stdout(output),
            ):
                namespace["main"]()
            self.assertEqual(process.call_count, 3)
            self.assertIn("--database-check", process.call_args_list[0].args[0])
            self.assertEqual(
                [call.args[0][3] for call in process.call_args_list[1:]],
                ["app1-todo-backend", "app2-todo-backend"],
            )
            for call in process.call_args_list[1:]:
                self.assertEqual(
                    json.loads(call.kwargs["input"])["sibling_password"], secret
                )
                self.assertNotIn(secret, " ".join(call.args[0]))
            self.assertNotIn(secret, output.getvalue())
            self.assertEqual(output.getvalue().count("authentication rejected"), 2)
            self.assertIn("if not authentication_failed(error)", namespace["CHECK"])
            self.assertLess(
                namespace["CHECK"].index("values = parameters()"),
                namespace["CHECK"].index('values["password"] ='),
            )

    def test_identity_failure_withholds_subprocess_output(self):
        namespace = guest_code("DATABASE_AUTH")
        namespace["logs_safe"] = mock.Mock()
        failure = subprocess.CompletedProcess(
            [], 2, "private-connection-string", "private-password"
        )
        with (
            mock.patch.object(subprocess, "run", return_value=failure),
            self.assertRaisesRegex(RuntimeError, "Identity runtime") as caught,
        ):
            namespace["main"]()
        self.assertNotIn("private-", str(caught.exception))

    def test_container_log_credentials_fail_without_echoing_content(self):
        namespace = guest_code("DATABASE_AUTH")
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "installed").mkdir()
            (home / "installed/identity").write_text("0.4.0\n")
            password = home / "identity/credentials/identity-db/password"
            password.parent.mkdir(parents=True)
            password.write_text("private-password\n")
            exposed = subprocess.CompletedProcess([], 0, "private-password", "")
            with (
                mock.patch.object(subprocess, "run", return_value=exposed),
                self.assertRaisesRegex(RuntimeError, "content withheld") as failure,
            ):
                namespace["logs_safe"](home)
            self.assertNotIn("private-password", str(failure.exception))
            clean = subprocess.CompletedProcess([], 0, "Database started", "")
            with (
                mock.patch.object(subprocess, "run", return_value=clean) as process,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                namespace["logs_safe"](home)
            self.assertEqual(
                [call.args[0] for call in process.call_args_list],
                [
                    ["podman", "logs", "identity-server-app"],
                    ["podman", "logs", "identity-postgres-db"],
                ],
            )


if __name__ == "__main__":
    unittest.main()
