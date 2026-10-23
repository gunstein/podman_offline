"""Secret keys a pod selects must exist before anything is generated or started."""

import copy
import tempfile
import unittest
from pathlib import Path

from deployment import common, deploy, validation
from deployment import render as rendering

from helpers.product_fixture import RENAMED, ProductFixture


def pod(volumes=(), env=()):
    """A Pod mounting Secret items and reading Secret keys into its environment."""
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "app-web"},
        "spec": {
            "containers": [
                {"name": "main", "image": "localhost/app:1", "env": list(env)}
            ],
            "volumes": list(volumes),
        },
    }


def secret_volume(name, *keys, optional=False):
    secret = {"secretName": name, "items": [{"key": k, "path": k} for k in keys]}
    if optional:
        secret["optional"] = True
    return {"name": name, "secret": secret}


def secret_env(name, key, optional=False):
    ref = {"name": name, "key": key}
    if optional:
        ref["optional"] = True
    return {"name": "VALUE", "valueFrom": {"secretKeyRef": ref}}


class SecretKeyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "config.yaml"
        (self.root / "credentials/todo").mkdir(parents=True)
        (self.root / "credentials/todo/session-key").write_text("private")
        (self.root / "single.pem").write_text("private")
        self.config = {
            common.SECRET_FILES: {
                "app-files": [{"path": "credentials/todo"}],
                "app-single": [{"path": "single.pem"}],
                "app-db": [{"path": "credentials/db", "generate": ["password"]}],
                "app-later": [{"path": "credentials/missing"}],
            }
        }

    def check(self, *documents):
        rendering.check_secret_keys(self.config, self.path, list(documents))

    def test_declared_keys_pass(self):
        self.check(
            pod(
                [
                    secret_volume("app-files", "session-key"),
                    secret_volume("app-single", "single.pem"),
                    secret_volume("app-db", "password"),  # generated later
                ],
                [secret_env("app-db", "password")],
            )
        )

    def test_missing_item_key_names_the_secret_and_the_keys_it_has(self):
        with self.assertRaisesRegex(
            common.DeployError,
            "Pod 'app-web' volume 'app-files' uses key 'nonexistent-key' of Secret "
            "'app-files', which provides only session-key",
        ):
            self.check(pod([secret_volume("app-files", "nonexistent-key")]))

    def test_missing_secret_key_ref_is_refused(self):
        with self.assertRaisesRegex(
            common.DeployError,
            "container 'main' env 'VALUE' uses key 'token' of Secret 'app-db', "
            "which provides only password",
        ):
            self.check(pod(env=[secret_env("app-db", "token")]))

    def test_inline_secret_keys_come_from_its_data(self):
        inline = {
            "kind": "Secret",
            "metadata": {"name": "app-inline"},
            "stringData": {"mode": "x"},
            "data": {"token": "eA=="},
        }
        self.check(inline, pod([secret_volume("app-inline", "mode", "token")]))
        with self.assertRaisesRegex(common.DeployError, "provides only mode, token"):
            self.check(inline, pod([secret_volume("app-inline", "other")]))

    def test_optional_and_unknown_sources_are_not_judged(self):
        """A missing source is reported by the source check, with its own message."""
        self.check(
            pod(
                [
                    secret_volume("app-files", "absent", optional=True),
                    secret_volume("app-later", "anything"),
                ],
                [secret_env("app-files", "absent", optional=True)],
            )
        )

    def test_no_file_contents_are_read(self):
        (self.root / "credentials/todo/session-key").chmod(0)
        self.addCleanup((self.root / "credentials/todo/session-key").chmod, 0o600)
        self.check(pod([secret_volume("app-files", "session-key")]))


class LifecycleAgreementTests(ProductFixture):
    """validate, prepare and install report the same missing key before writes."""

    def product(self):
        product = copy.deepcopy(RENAMED)
        orders = product["orders"]
        web = [m for m in orders["manifests"] if m["metadata"]["name"] == "orders-web"]
        for volume in web[0]["spec"]["volumes"]:
            if volume.get("secret", {}).get("secretName") == "orders-client":
                volume["secret"]["items"] = [{"key": "client.key", "path": "tls.key"}]
        self.write_product(product)
        return product

    def test_missing_key_is_found_by_every_path_before_writes(self):
        product = self.product()
        self.provide_credentials(product, common.BUILD / "dev")
        pattern = (
            "volume 'orders-client' uses key 'client.key' of Secret 'orders-client', "
            "which provides only client.crt"
        )
        for action in (validation.validate, deploy.prepare):
            with self.subTest(action=action.__name__):
                with self.assertRaisesRegex(common.DeployError, pattern):
                    action()
        self.assertFalse((common.BUILD / "install.yaml").exists())
        self.assertFalse(
            (common.BUILD / "dev/orders/credentials/database/password").exists()
        )
        releases = self.build_and_unpack()
        self.provide_credentials(product, common.STATE)
        for name in ("gateway", "login-service"):
            self.install(releases[name])
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, pattern):
            self.install(releases["orders"])
        self.assertFalse(
            (common.STATE / "orders/credentials/database/password").exists()
        )
        self.assertFalse((common.STATE / "installed/orders").exists())


if __name__ == "__main__":
    unittest.main()
