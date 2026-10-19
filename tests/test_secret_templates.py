"""Secret recipes: declaration safety, private materialization and lifecycle replay."""

import base64
import copy
import subprocess
from pathlib import Path
from unittest import mock

import yaml
from product_fixture import WORKER, ProductFixture
from test_deploy import DeployFixture, document

from deployment import catalog, common, deploy, templates, validation
from deployment import render as rendering


class SecretTemplateTests(DeployFixture):
    def setUp(self):
        super().setUp()
        self.config.update(
            {
                "HOST": "database",
                "PORT": 5432,
                "SECRET_FILES": {
                    "app-password": [
                        {"path": "credentials/db", "generate": ["password"]}
                    ]
                },
                "SECRET_TEMPLATES": {
                    "app-settings": {
                        "connection": "Host=@@HOST@@;Port=@@PORT@@;Password=@@secret:app-password/password@@"
                    }
                },
            }
        )
        self.write("credentials/db/password", b"PrivatePassword\n\n", 0o600)
        self.password = self.root / "credentials/db/password"
        self.pod = document(
            "Pod",
            "app-web",
            spec={
                "containers": [
                    {
                        "name": "main",
                        "image": "localhost/worker:1",
                        "imagePullPolicy": "Never",
                        "env": [
                            {
                                "name": "CONNECTION",
                                "valueFrom": {
                                    "secretKeyRef": {
                                        "name": "app-settings",
                                        "key": "connection",
                                    }
                                },
                            }
                        ],
                    }
                ]
            },
        )
        self.write("manifests/pod.yaml", yaml.safe_dump(self.pod))
        self.path = self.root / "config.yaml"

    def checked(self):
        return deploy.validate_component(
            self.config, self.path, common.MANIFESTS, "app"
        )

    def materialize(self):
        return rendering.materialize(
            self.config, self.path, self.checked(), self.root / "files"
        )[0]

    def test_render_integer_lf_and_no_extra_files_or_logs(self):
        before = set(self.root.rglob("*"))
        text = self.materialize()
        docs = list(yaml.safe_load_all(text))
        secret = next(d for d in docs if d["metadata"]["name"] == "app-settings")
        self.assertEqual(
            base64.b64decode(secret["data"]["connection"]),
            b"Host=database;Port=5432;Password=PrivatePassword",
        )
        self.assertEqual(set(self.root.rglob("*")), before)
        self.assertNotIn("PrivatePassword", text + self.stdout.getvalue())
        self.assertEqual(self.password.read_bytes(), b"PrivatePassword\n\n")
        self.assertEqual(text, self.materialize())
        self.password.write_bytes(b"ChangedPassword")
        self.assertNotEqual(text, self.materialize())
        self.config["HOST"] = "another-host"
        self.assertIn(
            b"Host=another-host",
            base64.b64decode(
                list(yaml.safe_load_all(self.materialize()))[1]["data"]["connection"]
            ),
        )

    def test_validate_reads_no_credential_contents_and_runs_no_host_commands(self):
        self.write("config.yaml", yaml.safe_dump(self.config))
        original = Path.open

        def no_credentials(path, *args, **kwargs):
            if "credentials" in path.parts:
                raise AssertionError("credential read")
            return original(path, *args, **kwargs)

        with mock.patch.object(Path, "open", no_credentials):
            validation.validate()
        self.process.assert_not_called()

    def test_generated_source_can_be_missing_until_materialization(self):
        self.password.unlink()
        self.checked()
        text = self.materialize()
        self.assertEqual(len(self.password.read_bytes()), 32)
        self.assertEqual(self.mode(self.password), 0o600)
        self.assertNotIn(self.password.read_text(), text)

    def test_invalid_recipes_fail_before_generation_and_do_not_echo_input(self):
        bad = [
            "@@MISSING@@",
            "@@SECRET_FILES@@",
            "@@FLAG@@",
            "@@NOTHING@@",
            "@@LIST@@",
            "@@bad@@",
            "@@HOST",
            "@@outer:@@HOST@@@@",
            "@@secret:missing/password@@",
            "@@secret:app-password/missing@@",
            "@@secret:app-settings/connection@@",
        ]
        self.config.update(FLAG=True, NOTHING=None, LIST=["PrivatePassword"])
        self.password.unlink()
        for recipe in bad:
            with self.subTest(recipe=recipe):
                self.config["SECRET_TEMPLATES"]["app-settings"]["connection"] = recipe
                with self.assertRaises(common.DeployError) as error:
                    self.checked()
                self.assertNotIn("PrivatePassword", str(error.exception))
                self.assertFalse(self.password.exists())
        self.process.assert_not_called()

    def test_all_rejected_characters_are_redacted_and_only_trailing_lf_is_removed(self):
        for value in [
            "Private;Password",
            'Private"Password',
            "Private'Password",
            " PrivatePassword",
            "PrivatePassword ",
            "Private\tPassword",
            "Private\nPassword",
            "Private\rPassword",
            "Private\x00Password",
            "Private\x7fPassword",
            "Private\x85Password",
            "Private@@HOST@@Password",
        ]:
            for source in ("secret", "config"):
                with self.subTest(source=source, value=repr(value)):
                    self.password.write_bytes(value.encode())
                    self.config["HOST"] = value if source == "config" else "database"
                    with self.assertRaises(common.DeployError) as error:
                        self.materialize()
                    self.assertNotIn(value, str(error.exception))
                    self.assertIn("app-settings.connection", str(error.exception))
        for value in (b"", b"\n\n", b"\xff"):
            self.config["HOST"] = "database"
            self.password.write_bytes(value)
            with self.assertRaises(common.DeployError) as error:
                self.materialize()
            self.assertNotIn("PrivatePassword", str(error.exception))

    def test_schema_collisions_keys_and_prefix(self):
        for recipes in (
            [],
            {"Bad": {"x": "text"}},
            {"app-password": {"x": "text"}},
            {"app-settings": {}},
            {"app-settings": {"bad/key": "text"}},
            {"app-settings": {"key": 3}},
            {"other-settings": {"key": "text"}},
        ):
            with self.subTest(recipes=recipes):
                self.config["SECRET_TEMPLATES"] = recipes
                with self.assertRaises(common.DeployError):
                    self.checked()
        self.config["SECRET_TEMPLATES"] = {"app-settings": {"key": "text"}}
        self.config["VOLUME_FILES"] = {"app-settings": [{"path": "credentials"}]}
        with self.assertRaisesRegex(common.DeployError, "collides"):
            self.checked()

    def test_selected_template_key_and_size_limit(self):
        self.pod["spec"]["containers"][0]["env"][0]["valueFrom"]["secretKeyRef"][
            "key"
        ] = "missing"
        self.write("manifests/pod.yaml", yaml.safe_dump(self.pod))
        with self.assertRaisesRegex(common.DeployError, "key 'missing'"):
            self.materialize()
        file_docs = rendering.secret_documents(
            rendering.load_file_group(self.config, common.SECRET_FILES, self.root)
        )
        limit = mock.patch.object(common, "MAX_SECRET_SIZE", 100)
        failure = self.assertRaisesRegex(common.DeployError, "too large")
        with limit, failure:
            templates.documents(self.config, file_docs)

    def test_inline_collision_and_partial_manifest_placeholders_remain_refused(self):
        self.write(
            "manifests/secret.yaml",
            yaml.safe_dump(
                document("Secret", "app-settings", stringData={"connection": "public"})
            ),
        )
        with self.assertRaisesRegex(common.DeployError, "more than once"):
            self.checked()
        (common.MANIFESTS / "secret.yaml").unlink()
        self.pod["spec"]["containers"][0]["env"].append(
            {"name": "HOST", "value": "prefix-@@HOST@@"}
        )
        self.write("manifests/pod.yaml", yaml.safe_dump(self.pod))
        with self.assertRaisesRegex(common.DeployError, "Only whole values"):
            self.checked()


class TemplateLifecycleTests(ProductFixture):
    def test_install_upgrade_failure_retry_and_retention(self):
        product = copy.deepcopy(WORKER)
        worker = product["worker"]
        worker["defaults"] = {
            "HOST": "first-host",
            "SECRET_FILES": {
                "worker-password": [
                    {"path": "credentials/db", "generate": ["password"]}
                ]
            },
            "SECRET_TEMPLATES": {
                "worker-settings": {
                    "connection": "@@HOST@@:@@secret:worker-password/password@@"
                }
            },
        }
        worker["manifests"][0]["spec"]["containers"][0]["env"] = [
            {
                "name": "CONNECTION",
                "valueFrom": {
                    "secretKeyRef": {"name": "worker-settings", "key": "connection"}
                },
            }
        ]
        self.write_product(product)
        releases = self.build_and_unpack()
        self.install(releases["worker"])
        password = common.HOME / "worker/credentials/db/password"
        before = password.read_bytes()
        output = catalog.component_paths("worker")[2]
        initial = output.read_bytes()
        self.install(releases["worker"])
        self.assertEqual(initial, output.read_bytes())
        config_path = common.HOME / "worker/config.yaml"
        config = yaml.safe_load(config_path.read_text())
        config["HOST"] = "second-host"
        config_path.write_text(yaml.safe_dump(config))
        original = self.host_command

        def fail_restart(arguments, **kwargs):
            if arguments[:3] == ["systemctl", "--user", "restart"]:
                raise subprocess.CalledProcessError(1, arguments)
            return original(arguments, **kwargs)

        self.process.side_effect = fail_restart
        with self.assertRaises(subprocess.CalledProcessError):
            self.install(releases["worker"])
        self.assertNotEqual(initial, output.read_bytes())
        self.assertEqual(before, password.read_bytes())
        self.process.side_effect = original
        self.install(releases["worker"])
        password.write_bytes(b"ControlledReplacement")
        previous = output.read_bytes()
        self.install(releases["worker"])
        self.assertNotEqual(previous, output.read_bytes())
        self.assertEqual(password.read_bytes(), b"ControlledReplacement")
        self.assertNotIn("ControlledReplacement", self.stdout.getvalue())
        # Preserve the existing equal-version newer-only contract.
        descriptor_path = releases["worker"] / "bundle.yaml"
        descriptor = yaml.safe_load(descriptor_path.read_text())
        descriptor["upgrade"] = "newer-only"
        descriptor_path.write_text(yaml.safe_dump(descriptor))
        config["HOST"] = "not-applied-at-equal-version"
        config_path.write_text(yaml.safe_dump(config))
        kept = output.read_bytes()
        self.assertEqual(self.install(releases["worker"]), [])
        self.assertEqual(kept, output.read_bytes())
        deploy.uninstall("worker")
        self.assertTrue(password.exists())
