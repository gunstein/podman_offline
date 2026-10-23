"""Exercise Secret lab probes and the explicit upgrade config edit without a VM."""

import base64
import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import database_test
import identity_template_baseline
import secret_templates_test as probe
import yaml
from test_acceptance import shell_code

REMOTE = Path(__file__).with_name("remote.sh").read_text()


class SecretProbeHarnessTests(unittest.TestCase):
    def test_real_probe_flow_checks_both_transports_and_replacements_and_cleans_up(
        self,
    ):
        calls, manifests, values = [], [], []
        active = {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def command(arguments, allowed=(0,)):
                calls.append(arguments)
                if arguments[:3] == ["podman", "kube", "play"]:
                    manifest = Path(arguments[-1])
                    active["manifest"] = manifest
                if arguments[:3] in (
                    ["systemctl", "--user", "start"],
                    ["systemctl", "--user", "restart"],
                ):
                    unit = next(root.glob(".config/containers/systemd/*.kube"))
                    active["manifest"] = Path(
                        unit.read_text().split("Yaml=", 1)[1].strip()
                    )
                if arguments[:2] == ["podman", "inspect"]:
                    docs = list(yaml.safe_load_all(active["manifest"].read_text()))
                    manifests.append(docs)
                    value = base64.b64decode(docs[0]["data"]["value"]).decode()
                    values.append(value)
                    return types.SimpleNamespace(
                        returncode=0,
                        stdout=json.dumps(
                            [
                                {
                                    "State": {"Status": "running"},
                                    "Config": {"Env": ["PROBE_VALUE=" + value]},
                                }
                            ]
                        ),
                        stderr="",
                    )
                if arguments[:2] == ["podman", "logs"]:
                    return types.SimpleNamespace(
                        returncode=0, stdout="Secret env and file verified", stderr=""
                    )
                return types.SimpleNamespace(returncode=0, stdout="", stderr="")

            with (
                mock.patch.object(probe.os, "geteuid", return_value=1000),
                mock.patch.object(probe.os, "umask"),
                mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(root)}),
                mock.patch.object(Path, "home", return_value=root),
                mock.patch.object(probe, "command", side_effect=command),
                mock.patch.object(
                    probe, "image", return_value="localhost/backend:fixture"
                ),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                probe.run()
            self.assertEqual(len(manifests), 4)
            self.assertEqual(len(set(values)), 4)
            self.assertEqual(
                sum(call[:3] == ["podman", "kube", "play"] for call in calls), 2
            )
            self.assertEqual(
                sum(call[:3] == ["systemctl", "--user", "restart"] for call in calls), 1
            )
            for docs in manifests:
                container = docs[1]["spec"]["containers"][0]
                self.assertIn("secretKeyRef", container["env"][0]["valueFrom"])
                self.assertEqual(
                    docs[1]["spec"]["volumes"][0]["secret"]["items"],
                    [{"key": "value", "path": "value"}],
                )
            for value in values:
                self.assertNotIn(value, output.getvalue())
                self.assertFalse(
                    any(value in argument for call in calls for argument in call)
                )
            self.assertFalse(list(root.glob(".config/containers/systemd/*.kube")))
            self.assertIn(
                ["podman", "volume", "rm", manifests[0][0]["metadata"]["name"]], calls
            )

    def test_stale_environment_is_a_failure_without_echoing_secret(self):
        responses = [
            types.SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "State": {"Status": "running"},
                            "Config": {"Env": ["PROBE_VALUE=stale"]},
                        }
                    ]
                ),
            ),
            types.SimpleNamespace(
                returncode=0, stdout="Secret env and file verified", stderr=""
            ),
        ]
        with (
            mock.patch.object(probe, "command", side_effect=responses),
            self.assertRaises(RuntimeError) as error,
        ):
            probe.verify("disposable", "private-expected")
        self.assertNotIn("private-expected", str(error.exception))

    def test_identity_client_uses_only_secret_ref_and_removes_pod_after_failure(self):
        docs, calls = [], []

        def podman(arguments):
            calls.append(arguments)
            if arguments[:2] == ["kube", "play"]:
                docs.extend(yaml.safe_load_all(Path(arguments[-1]).read_text()))
            if arguments[0] == "wait":
                return types.SimpleNamespace(stdout="2")
            if arguments[0] == "logs":
                return types.SimpleNamespace(
                    stdout="", stderr="Database authentication failed (28P01)"
                )
            return types.SimpleNamespace(stdout="", stderr="")

        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(database_test, "podman", side_effect=podman),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            database_test.identity_check(
                Path(directory),
                "network",
                "identity-check",
                "db-host",
                'private;quote"password',
                2,
            )
        container = docs[1]["spec"]["containers"][0]
        self.assertEqual(
            [item["name"] for item in container["env"]], ["ConnectionStrings__Default"]
        )
        self.assertNotIn("volumeMounts", container)
        self.assertIn(
            b'Password="private;quote""password"',
            base64.b64decode(docs[0]["data"]["connection"]),
        )
        self.assertEqual(calls[-1][:2], ["kube", "down"])


class TemplateUpgradeHarnessTests(unittest.TestCase):
    def test_pinned_baseline_is_read_from_git_before_any_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in identity_template_baseline.FILES:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
            with (
                mock.patch.object(
                    subprocess,
                    "run",
                    return_value=types.SimpleNamespace(
                        returncode=0, stdout=b"old fixture"
                    ),
                ) as run,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                identity_template_baseline.prepare(root)
            files = len(identity_template_baseline.FILES)
            self.assertEqual(run.call_count, files + 2)
            self.assertTrue(
                all(call.args[0][3] == "show" for call in run.call_args_list[:files])
            )
            add, commit = (call.args[0] for call in run.call_args_list[files:])
            self.assertEqual(
                add[3:], ["add", "--"] + list(identity_template_baseline.FILES)
            )
            self.assertIn("commit", commit)
            self.assertEqual(
                (root / "apps/identity/DatabaseEnvironment.cs").read_bytes(),
                b"old fixture",
            )

    def test_explicit_config_addition_preserves_password_and_existing_settings(self):
        code = shell_code(REMOTE, heredoc="IDENTITY_TEMPLATE_CONFIG")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "identity/config.yaml"
            path.parent.mkdir()
            config = {
                "DB_HOST": "existing-host",
                "DB_PORT": "5544",
                "SECRET_FILES": {"identity-password": [{"path": "password"}]},
            }
            path.write_text(yaml.safe_dump(config))
            password = root / "identity/password"
            password.write_bytes(b"retained-password\n\n")
            snapshot = root / "identity-lifecycle.json"
            snapshot.write_text(
                json.dumps(
                    {
                        "files": {
                            "config.yaml": {
                                "hash": hashlib.sha256(path.read_bytes()).hexdigest(),
                                "mode": 384,
                            }
                        }
                    }
                )
            )
            recipe = {"identity-database": {"connection": "@@DB_HOST@@"}}
            release = root / "release"
            defaults = release / "components/identity/config.defaults.yaml"
            defaults.parent.mkdir(parents=True)
            defaults.write_text(
                yaml.safe_dump({"DB_HOST": "new-default", "SECRET_TEMPLATES": recipe})
            )
            namespace = {"__name__": "fixture"}
            with (
                mock.patch.dict(
                    os.environ, {"PRODUCT_STATE": str(root), "PRODUCT_ROOT": str(root)}
                ),
                mock.patch("sys.argv", ["guest", str(release)]),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                exec(compile(code, "IDENTITY_TEMPLATE_CONFIG", "exec"), namespace)  # noqa: S102 - fixed repository heredoc
            self.assertEqual(
                yaml.safe_load(path.read_text()), dict(config, SECRET_TEMPLATES=recipe)
            )
            self.assertEqual(password.read_bytes(), b"retained-password\n\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(json.loads(snapshot.read_text())["template_config_added"])

    def test_install_diagnostics_are_checked_before_being_printed(self):
        code = shell_code(REMOTE, heredoc="PRIVATE_INSTALL")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            password = root / "identity/credentials/identity-db/password"
            password.parent.mkdir(parents=True)
            password.write_text("private-fixture")
            with (
                mock.patch.dict(
                    os.environ, {"PRODUCT_STATE": str(root), "PRODUCT_ROOT": str(root)}
                ),
                mock.patch("sys.argv", ["guest", str(root)]),
                mock.patch.object(
                    subprocess,
                    "run",
                    return_value=types.SimpleNamespace(
                        returncode=0, stdout="private-fixture", stderr=""
                    ),
                ),
                contextlib.redirect_stdout(io.StringIO()) as output,
                self.assertRaises(SystemExit) as error,
            ):
                exec(compile(code, "PRIVATE_INSTALL", "exec"), {})  # noqa: S102 - fixed repository heredoc
            self.assertNotIn(
                "private-fixture", output.getvalue() + str(error.exception)
            )


class ConfigMapInlineHarnessTests(unittest.TestCase):
    def fixture(self, directory, component="platform"):
        docs = [
            {
                "kind": "ConfigMap",
                "metadata": {"name": component + "-settings"},
                "data": {
                    "PUBLIC_ORIGIN": "https://gateway.test:8443",
                    "HTTPS_PORT": "9443",
                    "PUBLIC_ENDPOINT": "https://gateway.test:9443",
                },
            },
            {
                "kind": "Pod",
                "metadata": {"name": component + "-proxy"},
                "spec": {
                    "containers": [
                        {
                            "name": "nginx",
                            "envFrom": [
                                {"configMapRef": {"name": component + "-settings"}}
                            ],
                        }
                    ]
                },
            },
        ]
        path = Path(directory) / ("myproduct-" + component + ".yaml")
        path.write_text(yaml.safe_dump_all(docs))
        return path, docs

    def test_runtime_check_follows_configmap_consumers_for_demo_and_shop(self):
        from test_components import guest_code

        for component in ("platform", "gateway"):
            code = guest_code("HEALTHY")
            with tempfile.TemporaryDirectory() as directory:
                path, _ = self.fixture(directory, component)
                code["podman"] = mock.Mock(return_value="https://gateway.test:9443\n")
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    code["check_configmap_inline"]([path])
                code["podman"].assert_called_once_with(
                    ["exec", component + "-proxy-nginx", "printenv", "PUBLIC_ENDPOINT"]
                )
                self.assertIn("PASS: inline ConfigMap", output.getvalue())
                self.assertNotIn("gateway.test", output.getvalue())

    def test_wrong_rendered_or_running_value_and_missing_coverage_fail(self):
        from test_components import guest_code

        code = guest_code("HEALTHY")
        with tempfile.TemporaryDirectory() as directory:
            path, docs = self.fixture(directory)
            code["podman"] = mock.Mock(return_value="stale endpoint")
            with self.assertRaisesRegex(RuntimeError, "did not reach"):
                code["check_configmap_inline"]([path])
            docs[0]["data"]["PUBLIC_ENDPOINT"] = (
                "https://@@PUBLIC_HOSTNAME@@:@@HTTPS_PORT@@"
            )
            path.write_text(yaml.safe_dump_all(docs))
            with self.assertRaisesRegex(RuntimeError, "rendered incorrectly"):
                code["check_configmap_inline"]([path])
            path.write_text(yaml.safe_dump_all(docs[1:]))
            with self.assertRaisesRegex(RuntimeError, "Missing inline"):
                code["check_configmap_inline"]([path])

    def test_healthy_main_requires_runtime_configmap_value_before_success(self):
        from test_components import guest_code

        code = guest_code("HEALTHY")
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            folder = home / "config/containers/systemd"
            folder.mkdir(parents=True)
            self.fixture(folder)
            row = {
                "Name": "platform-proxy-nginx",
                "IsInfra": False,
                "IsService": False,
                "State": {"Status": "running", "Health": {"Status": "healthy"}},
            }

            def podman(arguments):
                if arguments[0] == "exec":
                    return "wrong endpoint"
                return (
                    json.dumps([row]) if arguments[0] == "inspect" else "container-id\n"
                )

            code["podman"] = podman
            with (
                mock.patch.dict(
                    os.environ, {"PRODUCT_STATE": str(home), "PRODUCT_ROOT": str(home)}
                ),
                contextlib.redirect_stdout(io.StringIO()) as output,
                self.assertRaisesRegex(RuntimeError, "did not reach"),
            ):
                code["main"]()
            self.assertNotIn("PASS: all", output.getvalue())
