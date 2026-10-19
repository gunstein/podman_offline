"""Secret recipes: declaration safety, private materialization and lifecycle replay."""

import base64
import copy
import subprocess
from pathlib import Path
from unittest import mock

import yaml
from deployment import catalog, common, deploy, templates, validation
from deployment import render as rendering

from helpers.deploy_fixture import DeployFixture, document
from helpers.product_fixture import WORKER, ProductFixture


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

    def test_missing_operator_file_stops_before_template_materialization(self):
        self.config["SECRET_FILES"]["app-password"] = [
            {"path": "credentials/db/password"}
        ]
        self.password.unlink()
        documents = self.checked()
        failure = self.assertRaisesRegex(
            common.DeployError, r"Missing .*SECRET_FILES.app-password"
        )
        with mock.patch.object(templates, "documents") as compose:
            with failure as error:
                rendering.materialize(
                    self.config, self.path, documents, self.root / "files"
                )
        compose.assert_not_called()
        self.assertNotIn("PrivatePassword", str(error.exception))
        self.assertFalse(self.password.exists())
        self.process.assert_not_called()

    def test_standalone_prepare_and_validate_check_templates_before_side_effects(self):
        self.config["SECRET_TEMPLATES"]["app-settings"]["connection"] = "@@MISSING@@"
        self.write_config()
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for operation in (deploy.prepare, validation.validate):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(common.DeployError, "MISSING") as error:
                    operation()
                self.assertNotIn("PrivatePassword", str(error.exception))
        self.assertEqual(
            before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        )
        self.process.assert_not_called()

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
        with limit:
            with failure:
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
    def test_worker_delivers_only_binary_pfx_with_explicit_mapping(self):
        product = copy.deepcopy(WORKER)
        product["worker"]["defaults"] = {
            "SECRET_FILES": {
                "worker-signing": [{"path": "credentials/signing/signing-cert.pfx"}]
            }
        }
        spec = product["worker"]["manifests"][0]["spec"]
        spec["volumes"] = [
            {
                "name": "signing",
                "secret": {
                    "secretName": "worker-signing",
                    "defaultMode": 0o400,
                    "items": [{"key": "signing-cert.pfx", "path": "signing-cert.pfx"}],
                },
            }
        ]
        spec["containers"][0]["volumeMounts"] = [
            {
                "name": "signing",
                "mountPath": "/run/secrets",
                "readOnly": True,
            }
        ]
        self.write_product(product)
        release = self.build_and_unpack()["worker"]
        binary = bytes(range(256)) + b"\x00\xff"

        def provide(directory):
            signing = directory / "credentials/signing"
            signing.mkdir(parents=True)
            for name, value in (
                ("signing-cert.pfx", binary),
                ("pfx-password", b"NeverDeliveredPassword"),
                ("signing-cert.key", b"NeverDeliveredPEMKey"),
            ):
                path = signing / name
                path.write_bytes(value)
                path.chmod(0o600)

        self.install(release, configure=provide)
        output = catalog.component_paths("worker")[2]
        docs = list(yaml.safe_load_all(output.read_text()))
        secrets = [doc for doc in docs if doc["kind"] == "Secret"]
        self.assertEqual(len(secrets), 1)
        self.assertEqual(set(secrets[0]["data"]), {"signing-cert.pfx"})
        self.assertEqual(
            base64.b64decode(secrets[0]["data"]["signing-cert.pfx"]), binary
        )
        pod = next(doc for doc in docs if doc["kind"] == "Pod")
        self.assertEqual(pod["spec"]["volumes"], spec["volumes"])
        self.assertEqual(
            pod["spec"]["containers"][0]["volumeMounts"],
            spec["containers"][0]["volumeMounts"],
        )
        self.assertEqual(self.mode(output), 0o600)
        self.assertNotIn("NeverDelivered", output.read_text() + self.stdout.getvalue())

    def operator_product(self):
        product = copy.deepcopy(WORKER)
        product["worker"]["defaults"] = {
            "SECRET_FILES": {"worker-token": [{"path": "credentials/api/token"}]},
            "SECRET_TEMPLATES": {
                "worker-settings": {"URL": "Token=@@secret:worker-token/token@@"}
            },
        }
        product["worker"]["manifests"][0]["spec"]["containers"][0]["env"] = [
            {
                "name": "URL",
                "valueFrom": {
                    "secretKeyRef": {"name": "worker-settings", "key": "URL"}
                },
            }
        ]
        return product

    def operator_release(self, product=None):
        self.write_product(self.operator_product() if product is None else product)
        release = self.build_and_unpack()["worker"]
        self.use_root(release)
        self.process.reset_mock()
        return release

    def test_init_config_allows_declared_operator_source_before_delivery(self):
        self.operator_release()
        deploy.init_config("worker")
        config = common.HOME / "worker/config.yaml"
        self.assertEqual(self.mode(config), 0o600)
        self.assertEqual(
            yaml.safe_load(config.read_text()),
            self.operator_product()["worker"]["defaults"],
        )
        self.assertFalse((config.parent / "credentials").exists())
        self.process.assert_not_called()

    def test_validate_missing_operator_source_reports_file_without_writes(self):
        self.operator_release()
        # Model the persistent config independently of init-config so this
        # regression also reaches validate on the pre-fix implementation.
        config = common.HOME / "worker/config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(yaml.safe_dump(self.operator_product()["worker"]["defaults"]))
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(
            common.DeployError,
            r"Missing .*credentials/api/token \(SECRET_FILES.worker-token\)",
        ) as error:
            validation.validate()
        self.assertNotIn("missing declared source", str(error.exception))
        self.assertNotIn("OperatorToken", str(error.exception))
        self.assertEqual(
            before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        )
        self.process.assert_not_called()

    def test_install_uses_delivered_operator_source_and_retains_bytes(self):
        release = self.operator_release()

        def provide(directory):
            source = directory / "credentials/api/token"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"OperatorToken\n\n")
            source.chmod(0o600)

        self.install(release, configure=provide)
        output = catalog.component_paths("worker")[2]
        docs = list(yaml.safe_load_all(output.read_text()))
        secret = next(d for d in docs if d["metadata"]["name"] == "worker-settings")
        self.assertEqual(
            base64.b64decode(secret["data"]["URL"]), b"Token=OperatorToken"
        )
        self.assertEqual(self.mode(output), 0o600)
        self.assertEqual(
            (common.HOME / "worker/credentials/api/token").read_bytes(),
            b"OperatorToken\n\n",
        )
        self.assertNotIn("OperatorToken", self.stdout.getvalue())

    def test_init_config_refuses_unknown_operator_group_before_writing(self):
        product = self.operator_product()
        product["worker"]["defaults"]["SECRET_FILES"] = {}
        self.operator_release(product)
        with self.assertRaisesRegex(
            common.DeployError,
            "missing declared source SECRET_FILES.worker-token/token",
        ) as error:
            deploy.init_config("worker")
        self.assertNotIn("OperatorToken", str(error.exception))
        self.assertFalse((common.HOME / "worker/config.yaml").exists())
        self.process.assert_not_called()

    def test_init_config_refuses_known_directory_without_referenced_key(self):
        self.operator_release()
        directory = common.HOME / "worker/credentials/api/token"
        directory.mkdir(parents=True)
        (directory / "other").write_text("OperatorToken")
        with self.assertRaisesRegex(
            common.DeployError,
            "missing declared source SECRET_FILES.worker-token/token",
        ) as error:
            deploy.init_config("worker")
        self.assertNotIn("OperatorToken", str(error.exception))
        self.assertFalse((common.HOME / "worker/config.yaml").exists())
        self.process.assert_not_called()

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


class ConfigMapTemplateTests(DeployFixture):
    def setUp(self):
        super().setUp()
        self.config.update(HOST="api.test", PORT=8080)
        self.path = common.CONFIG

    def write_map(self, data, **extra):
        doc = document("ConfigMap", "settings", data=data, **extra)
        self.write("manifests/settings.yaml", yaml.safe_dump(doc))

    def checked(self):
        return deploy.validate_component(self.config, self.path, common.MANIFESTS)

    def test_inline_multiline_and_nginx_dollars_are_preserved(self):
        self.write_map(
            {
                "endpoint": "http://@@HOST@@:@@PORT@@/v1",
                "file.conf": "server {\n  listen @@PORT@@;\n  server_name @@HOST@@;\n  set $upstream ${UPSTREAM};\n}\n",
                "literal": "${HTTPS_PORT} ${DNS_SERVER} $host",
                "whole": "@@PORT@@",
            }
        )
        data = self.checked()[0]["data"]
        self.assertEqual(data["endpoint"], "http://api.test:8080/v1")
        self.assertEqual(
            data["file.conf"],
            "server {\n  listen 8080;\n  server_name api.test;\n  set $upstream ${UPSTREAM};\n}\n",
        )
        self.assertEqual(data["literal"], "${HTTPS_PORT} ${DNS_SERVER} $host")
        self.assertEqual(data["whole"], "8080")

    def test_public_values_are_not_subject_to_secret_character_rules(self):
        self.config["TEXT"] = " leading;quotes\"'\ntrailing "
        self.write_map({"file": "start\n@@TEXT@@\nend"})
        self.assertEqual(
            self.checked()[0]["data"]["file"], "start\n" + self.config["TEXT"] + "\nend"
        )

        self.config["PATH_TEXT"] = r"\g<1>\1\$host"
        self.write_map({"path": "prefix-@@PATH_TEXT@@"})
        self.assertEqual(
            self.checked()[0]["data"]["path"], "prefix-" + self.config["PATH_TEXT"]
        )

    def test_whole_values_keep_existing_conversion_inline_requires_scalar(self):
        for value in (False, None, ["public"], {"name": "public"}):
            self.config["VALUE"] = value
            self.write_map({"whole": "@@VALUE@@"})
            self.assertEqual(self.checked()[0]["data"]["whole"], str(value))
            self.write_map({"inline": "prefix-@@VALUE@@"})
            with self.assertRaisesRegex(common.DeployError, "VALUE") as error:
                self.checked()
            self.assertNotIn("public", str(error.exception))

    def test_secret_refs_rejected_before_generation_or_content_read(self):
        self.config["SECRET_FILES"] = {
            "private-password": [{"path": "credentials/db", "generate": ["password"]}]
        }
        for text in (
            "@@secret:private-password/password@@",
            "Password=@@secret:private-password/password@@",
        ):
            self.write_map({"connection": text})
            reader = mock.patch.object(
                Path, "read_bytes", side_effect=AssertionError("credential read")
            )
            failure = self.assertRaisesRegex(common.DeployError, "SECRET_TEMPLATES")
            with reader:
                with failure:
                    self.checked()
            self.assertFalse((self.root / "credentials").exists())
        self.process.assert_not_called()

    def test_missing_unknown_nested_and_literal_markers_fail_without_values(self):
        for text in (
            "@@MISSING@@/v1",
            "@@bad@@",
            "@@outer:@@HOST@@@@",
            "literal @@ marker",
            "@@HOST@@ @@",
        ):
            self.write_map({"public-key": text})
            with self.assertRaises(common.DeployError) as error:
                self.checked()
            self.assertNotIn("api.test", str(error.exception))

    def test_substituted_markers_are_never_expanded_recursively(self):
        self.config["HOST"] = "@@OTHER@@"
        self.config["OTHER"] = "do-not-insert"
        for text in ("http://@@HOST@@", "@@HOST@@"):
            self.write_map({"endpoint": text})
            with self.assertRaises(common.DeployError) as error:
                self.checked()
            self.assertNotIn("do-not-insert", str(error.exception))

    def test_inline_outside_data_remains_refused(self):
        pod = document(
            "Pod",
            "app",
            spec={
                "containers": [
                    {
                        "name": "web",
                        "image": "localhost/app:1",
                        "imagePullPolicy": "Never",
                    }
                ]
            },
        )
        for field in ("metadata", "image", "env", "volume"):
            current = copy.deepcopy(pod)
            container = current["spec"]["containers"][0]
            if field == "metadata":
                current["metadata"]["name"] = "app-@@HOST@@"
            elif field == "image":
                container["image"] = "localhost/@@HOST@@:1"
            elif field == "env":
                container["env"] = [{"name": "URL", "value": "http://@@HOST@@"}]
            else:
                current["spec"]["volumes"] = [
                    {
                        "name": "data",
                        "persistentVolumeClaim": {"claimName": "data-@@HOST@@"},
                    }
                ]
            self.write("manifests/pod.yaml", yaml.safe_dump(current))
            with self.assertRaisesRegex(common.DeployError, "Only whole values"):
                self.checked()
        (common.MANIFESTS / "pod.yaml").unlink()
        self.write_map({"text": "public"}, metadata={"name": "settings-@@HOST@@"})
        with self.assertRaisesRegex(common.DeployError, "Only whole values"):
            self.checked()

    def test_validate_is_write_free_and_reads_no_secret_contents(self):
        self.write_map({"endpoint": "http://@@HOST@@:@@PORT@@"})
        self.write("config.yaml", yaml.safe_dump(self.config))
        before = {
            path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()
        }
        with mock.patch.object(
            Path, "read_bytes", side_effect=AssertionError("private read")
        ):
            validation.validate()
        self.assertEqual(
            before,
            {
                path: path.read_bytes()
                for path in self.root.rglob("*")
                if path.is_file()
            },
        )
        self.process.assert_not_called()


class ConfigMapLifecycleTests(ProductFixture):
    def product(self):
        product = copy.deepcopy(WORKER)
        worker = product["worker"]
        worker["defaults"] = {"API_HOST": "worker.test", "API_PORT": 8080}
        worker["manifests"].insert(
            0,
            document(
                "ConfigMap",
                "worker-settings",
                data={"API_URL": "http://@@API_HOST@@:@@API_PORT@@"},
            ),
        )
        worker["manifests"][1]["spec"]["containers"][0]["envFrom"] = [
            {"configMapRef": {"name": "worker-settings"}}
        ]
        return product

    def test_worker_install_and_config_change_use_same_rendered_values(self):
        self.write_product(self.product())
        releases = self.build_and_unpack()
        self.install(releases["worker"])
        output = catalog.component_paths("worker")[2]

        def endpoint():
            docs = list(yaml.safe_load_all(output.read_text()))
            return next(
                doc["data"]["API_URL"] for doc in docs if doc["kind"] == "ConfigMap"
            )

        self.assertEqual(endpoint(), "http://worker.test:8080")
        config_path = common.HOME / "worker/config.yaml"
        config = yaml.safe_load(config_path.read_text())
        config.update(API_HOST="changed.test", API_PORT=9090)
        config_path.write_text(yaml.safe_dump(config))
        self.install(releases["worker"])
        self.assertEqual(endpoint(), "http://changed.test:9090")
        self.assertEqual(self.mode(output), 0o600)
        self.assertFalse((common.HOME / "worker/credentials").exists())

    def test_init_config_refuses_missing_inline_key_before_writing(self):
        product = self.product()
        del product["worker"]["defaults"]["API_PORT"]
        self.write_product(product)
        releases = self.build_and_unpack()
        self.use_root(releases["worker"])
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "API_PORT"):
            deploy.init_config("worker")
        self.assertFalse((common.HOME / "worker/config.yaml").exists())
        self.process.assert_not_called()
        product = self.product()
        product["worker"]["manifests"][0]["metadata"] = None
        self.write_product(product)
        with self.assertRaisesRegex(common.DeployError, "metadata must be a map"):
            rendering.component_defaults("worker")
        self.assertFalse((common.HOME / "worker/config.yaml").exists())
