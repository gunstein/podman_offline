"""Dev config (component defaults, then config/dev.yaml) with arbitrary components."""

import base64
import copy
import tarfile

import yaml
from deployment import common, deploy, validation
from deployment import render as rendering

from helpers.product_fixture import RENAMED, WORKER, ProductFixture, pod


class ComponentDevTests(ProductFixture):
    def layer(self, relative, config):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(config))
        return path

    def snapshot(self):
        return {
            str(path.relative_to(self.source)): path.read_bytes()
            for path in self.source.rglob("*")
            if path.is_file()
        }

    def test_precedence_optional_layers_and_whole_map_replacement(self):
        self.write_product(WORKER)
        component = self.layer(
            "components/worker/config.defaults.yaml",
            {"CHOICE": "component", "SECRET_FILES": {"worker-old": [{"path": "old"}]}},
        )
        global_dev = self.layer(
            "config/dev.yaml",
            {
                "CHOICE": "global",
                "SECRET_FILES": {
                    "worker-new": [{"path": "new", "generate": ["token"]}]
                },
            },
        )
        config = deploy.dev_settings()[1]["worker"]
        self.assertEqual(config["CHOICE"], "global")
        self.assertEqual(
            config["SECRET_FILES"],
            {"worker-new": [{"path": "new", "generate": ["token"]}]},
        )
        for path, expected in ((global_dev, "component"), (component, None)):
            path.unlink()
            self.assertEqual(deploy.dev_settings()[1]["worker"].get("CHOICE"), expected)
        self.assertFalse((self.source / "apps").exists())
        self.process.assert_not_called()

    def test_two_independent_file_maps_validate_and_prepare_use_the_same_layers(self):
        product = {}
        for name in ("processor", "notifier"):
            product[name] = {
                "manifests": [
                    pod(
                        name + "-job",
                        "localhost/worker:1",
                        ["secret:" + name + "-input", "pvc:" + name + "-files"],
                    )
                ],
            }
        self.write_product(product)
        for name in product:
            self.layer(
                "components/" + name + "/config.defaults.yaml",
                {
                    "SECRET_FILES": {name + "-input": [{"path": "inputs/message"}]},
                    "VOLUME_FILES": {name + "-files": [{"path": "inputs/message"}]},
                },
            )
            self.layer(
                "build/dev/" + name + "/config.yaml",
                {"SHOULD_NOT_BE_READ": "old-output"},
            )
            path = common.BUILD / "dev" / name / "inputs/message"
            path.parent.mkdir()
            path.write_text(name)
        before = self.snapshot()
        validation.validate()
        self.assertEqual(self.snapshot(), before)
        self.process.assert_not_called()
        deploy.prepare()
        documents = list(
            yaml.safe_load_all((common.BUILD / "install.yaml").read_text())
        )
        for name in product:
            config_path = common.BUILD / "dev" / name / "config.yaml"
            config = rendering.load_config(config_path)
            self.assertEqual(config, deploy.dev_settings()[1][name])
            secret = next(
                doc
                for doc in documents
                if doc["kind"] == "Secret"
                and doc["metadata"]["name"] == name + "-input"
            )
            self.assertEqual(base64.b64decode(secret["data"]["message"]), name.encode())
            with tarfile.open(
                str(common.BUILD / "dev" / name / "files" / (name + "-files.tar"))
            ) as archive:
                stream = archive.extractfile("message")
                assert stream is not None
                self.assertEqual(stream.read(), name.encode())
        self.assertFalse((self.source / "apps").exists())

    def test_invalid_local_layers_fail_in_validate_and_prepare_without_writes(self):
        self.write_product(WORKER)
        path = self.layer("config/dev.yaml", {})
        for content in (
            "CHOICE: private-one\nCHOICE: private-two\n",
            "CHOICE: [private-value\n",
            "- private-value\n",
        ):
            path.write_text(content)
            before = self.snapshot()
            errors = []
            for action in (validation.validate, deploy.prepare):
                with self.subTest(content=content, action=action.__name__):
                    with self.assertRaises(
                        (common.DeployError, yaml.YAMLError)
                    ) as failure:
                        action()
                    message = str(failure.exception)
                    self.assertIn(str(path), message)
                    self.assertNotIn("private-", message)
                    errors.append(message)
            self.assertEqual(errors[0], errors[1])
            self.assertEqual(self.snapshot(), before)
            self.process.assert_not_called()

    def test_dependent_cannot_set_gateway_public_keys_even_with_equal_values(self):
        self.write_product(copy.deepcopy(RENAMED))
        for key, value in (
            ("PUBLIC_ORIGIN", "https://shop.test:9443"),
            ("HTTPS_PORT", 9443),
        ):
            path = self.layer("components/orders/config.defaults.yaml", {key: value})
            before = self.snapshot()
            for action in (validation.validate, deploy.prepare):
                with self.subTest(key=key, action=action.__name__):
                    with self.assertRaises(common.DeployError) as failure:
                        action()
                    message = str(failure.exception)
                    for expected in (key, str(path), "gateway"):
                        self.assertIn(expected, message)
                    self.assertNotIn(str(value), message)
            self.assertEqual(self.snapshot(), before)
            self.process.assert_not_called()
            path.unlink()

    def test_owner_dev_settings_reach_dependents(self):
        self.write_product(copy.deepcopy(RENAMED))
        expected = {"PUBLIC_ORIGIN": "https://dev.test:9555", "HTTPS_PORT": 9555}
        self.layer("config/dev.yaml", expected)
        known, settings = deploy.dev_settings()
        for name in (
            name
            for name in known
            if name == "gateway" or known[name]["public_from"] == "gateway"
        ):
            for key, value in expected.items():
                self.assertEqual(settings[name][key], value)
        self.process.assert_not_called()

    def test_production_ignores_hand_copied_dev_layers_and_archive_excludes_them(self):
        product = copy.deepcopy(WORKER)
        product["worker"]["defaults"] = {"CHOICE": "production"}
        product["worker"]["manifests"] = [
            pod("worker-job", "localhost/worker:1", env={"CHOICE": "@@CHOICE@@"})
        ]
        self.write_product(product)
        external = self.root / "external-local-file"
        external.write_text("not-bundled")
        self.layer(
            "config/dev.yaml",
            {
                "CHOICE": "dev",
                "LOCAL_FILE": str(external),
                "SECRET_FILES": {"worker-private": [{"path": str(external)}]},
            },
        )
        release = self.build_and_unpack()["worker"]
        self.assertFalse((release / "config/dev.yaml").exists())
        archive_path = next((self.source / "dist").glob("*-offline.tar.gz"))
        with tarfile.open(str(archive_path)) as archive:
            self.assertFalse(
                any(
                    name.endswith(("config/dev.yaml", "external-local-file"))
                    for name in archive.getnames()
                )
            )
        (release / "config").mkdir(exist_ok=True)
        (release / "config/dev.yaml").write_text("invalid: [private-value\n")
        self.use_root(release)
        self.process.reset_mock()
        deploy.init_config("worker")
        config_path = common.STATE / "worker/config.yaml"
        before = config_path.read_bytes()
        self.assertEqual(rendering.load_config(config_path)["CHOICE"], "production")
        self.assertEqual(validation.validate_bundle()[1], [])
        self.process.assert_not_called()
        deploy.install()
        self.assertEqual(config_path.read_bytes(), before)
        installed = (common.QUADLET_DIR / "myproduct-worker.yaml").read_text()
        self.assertIn("production", installed)
        self.assertNotIn("CHOICE: dev", installed)

    def test_changed_dev_layer_retains_password_and_existing_volume_guard(self):
        product = copy.deepcopy(RENAMED)
        self.write_product(product)
        self.provide_credentials(product, common.BUILD / "dev")
        self.layer("config/dev.yaml", {"CHOICE": "first"})
        deploy.prepare()
        password = common.BUILD / "dev/orders/credentials/database/password"
        before = password.read_bytes(), password.stat().st_mtime_ns
        self.volumes.add("orders-data")
        self.layer("config/dev.yaml", {"CHOICE": "second"})
        deploy.prepare()
        self.assertEqual((password.read_bytes(), password.stat().st_mtime_ns), before)
        self.assertEqual(
            rendering.load_config(common.BUILD / "dev/orders/config.yaml")["CHOICE"],
            "second",
        )
        password.unlink()
        self.process.reset_mock()
        before_files = self.snapshot()
        with self.assertRaisesRegex(common.DeployError, "existing volume orders-data"):
            deploy.prepare()
        self.assertEqual(self.snapshot(), before_files)
        self.assertEqual(
            self.commands(), [["podman", "volume", "exists", "orders-data"]]
        )
        password.write_bytes(before[0])
        password.chmod(0o600)
        self.process.reset_mock()
        deploy.prepare()
        self.assertEqual(password.read_bytes(), before[0])
        self.assertEqual(self.commands(), [])
