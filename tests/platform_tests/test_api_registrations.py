"""API secret registrations (backlog 72): the API owns its secret, its owner receives it.

A product with none of the demo names: accounts accepts apis and reads
ApiResources__<index>__ApiSecrets__0__Value from its registration Secret;
ledger (sha256) and reports (plain) register their own generated secrets.
"""

import base64
import contextlib
import copy
import hashlib
import io
import json
import shutil

import yaml
from deployment import catalog, common, deploy, registrations, validation

from helpers.product_fixture import ProductFixture


def api_pod(name, env=(), env_from=()):
    """One container that takes variables from Secrets, as a .NET backend would."""
    container = {
        "name": "main",
        "image": "localhost/" + name.split("-")[0] + ":1",
        "imagePullPolicy": "Never",
    }
    if env:
        container["env"] = [
            {
                "name": variable,
                "valueFrom": {"secretKeyRef": {"name": secret, "key": variable}},
            }
            for variable, secret in env
        ]
    if env_from:
        container["envFrom"] = [{"secretRef": {"name": name}} for name in env_from]
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": name},
        "spec": {"containers": [container]},
    }


def api_component(name, index, hash_name):
    """An API backend: its own generated secret, given to it and registered."""
    return {
        "catalog": {"requires": ["accounts"], "apis": "accounts"},
        "defaults": {
            "SECRET_FILES": {
                name + "-api-secret": [
                    {"path": "credentials/api", "generate": ["value"]}
                ]
            },
            "SECRET_TEMPLATES": {
                name + "-authentication": {
                    "Authentication__ApiSecret": "@@secret:"
                    + name
                    + "-api-secret/value@@"
                }
            },
        },
        "manifests": [
            api_pod(
                name + "-server",
                env=[("Authentication__ApiSecret", name + "-authentication")],
            )
        ],
        "api": {
            "index": index,
            "secret": name + "-api-secret/value",
            "hash": hash_name,
        },
    }


API_PRODUCT = {
    "accounts": {
        "catalog": {"upgrade": "newer-only", "accepts": {"apis": "accounts-apis"}},
        "manifests": [api_pod("accounts-server", env_from=["accounts-apis"])],
    },
    "ledger": api_component("ledger", 0, "sha256"),
    "reports": api_component("reports", 1, "none"),
}


def sha256(value):
    return base64.b64encode(hashlib.sha256(value.encode()).digest()).decode()


def decoded(secret):
    return {key: base64.b64decode(value).decode() for key, value in secret.items()}


class ApiRegistrationTests(ProductFixture):
    def product(self, changes=None):
        product = copy.deepcopy(API_PRODUCT)
        for name, spec in (changes or {}).items():
            if spec is None:
                product.pop(name)
            else:
                product[name] = spec
        return product

    def secrets(self, path):
        """Secret name -> decoded data in one rendered YAML file."""
        return {
            doc["metadata"]["name"]: decoded(doc["data"])
            for doc in yaml.safe_load_all(path.read_text())
            if doc and doc["kind"] == "Secret"
        }

    def snapshot(self, directory):
        return {
            str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob("*")
            if path.is_file()
        }

    def quiet(self, action):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            action()
        return output.getvalue()

    def test_dev_prepare_gives_the_owner_every_api_secret(self):
        self.write_product(self.product())
        output = self.quiet(deploy.prepare)
        dev = common.BUILD / "dev"
        ledger = (dev / "ledger/credentials/api/value").read_text()
        reports = (dev / "reports/credentials/api/value").read_text()
        secrets = self.secrets(common.BUILD / "install.yaml")
        self.assertEqual(
            secrets["accounts-apis"],
            {
                "ApiResources__0__ApiSecrets__0__Value": sha256(ledger),
                "ApiResources__1__ApiSecrets__0__Value": reports,
            },
        )
        self.assertEqual(
            secrets["ledger-authentication"], {"Authentication__ApiSecret": ledger}
        )
        self.assertEqual(
            secrets["reports-authentication"], {"Authentication__ApiSecret": reports}
        )
        for name in ("ledger", "reports"):
            self.assertEqual(
                (dev / "apis" / (name + ".json")).stat().st_mode & 0o077, 0
            )
        self.assertEqual((dev / "apis").stat().st_mode & 0o077, 0)
        for value in (ledger, reports, sha256(ledger)):
            self.assertNotIn(value, output)
        # Prepare again: the same secrets, and validate agrees with prepare.
        self.quiet(deploy.prepare)
        self.assertEqual(self.secrets(common.BUILD / "install.yaml"), secrets)
        self.quiet(validation.validate)
        self.process.assert_not_called()

    def test_dev_drops_an_api_removed_from_the_catalog(self):
        self.write_product(self.product())
        self.quiet(deploy.prepare)
        shutil.rmtree(self.source / "components/reports")
        self.write_product(self.product({"reports": None}))
        self.quiet(deploy.prepare)
        self.assertEqual(
            list(self.secrets(common.BUILD / "install.yaml")["accounts-apis"]),
            ["ApiResources__0__ApiSecrets__0__Value"],
        )
        self.assertFalse((common.BUILD / "dev/apis/reports.json").exists())

    def test_invalid_declarations_are_refused_before_dev_writes(self):
        reports = API_PRODUCT["reports"]
        no_role = copy.deepcopy(reports)
        no_role["catalog"].pop("apis")
        no_file = copy.deepcopy(reports)
        no_file.pop("api")
        undeclared = copy.deepcopy(reports)
        undeclared["api"]["secret"] = "reports-other/value"
        no_key = copy.deepcopy(reports)
        no_key["api"]["secret"] = "reports-api-secret/token"
        unknown_hash = copy.deepcopy(reports)
        unknown_hash["api"]["hash"] = "md5"
        boolean_index = copy.deepcopy(reports)
        boolean_index["api"]["index"] = True
        name_field = copy.deepcopy(reports)
        name_field["api"]["name"] = "reports"
        own_secret = copy.deepcopy(API_PRODUCT["accounts"])
        own_secret["defaults"] = {
            "SECRET_FILES": {"accounts-apis": [{"path": "x", "generate": ["v"]}]}
        }
        not_accepted = copy.deepcopy(API_PRODUCT["accounts"])
        not_accepted["catalog"]["accepts"] = {}
        not_accepted["manifests"] = [api_pod("accounts-server")]
        duplicate = copy.deepcopy(reports)
        duplicate["api"]["index"] = 0
        for label, changes, pattern in (
            ("api.yaml without role", {"reports": no_role}, "declare apis"),
            ("role without api.yaml", {"reports": no_file}, "is missing for apis"),
            ("undeclared secret", {"reports": undeclared}, "needs SECRET_FILES"),
            ("missing key", {"reports": no_key}, "no key 'token'"),
            ("unknown hash", {"reports": unknown_hash}, "Invalid API registration"),
            ("boolean index", {"reports": boolean_index}, "Invalid API registration"),
            ("name field", {"reports": name_field}, "Invalid API registration"),
            ("owner declares it", {"accounts": own_secret}, "platform renders it"),
            ("no owner", {"accounts": not_accepted}, "does not accept apis"),
            ("duplicate index", {"reports": duplicate}, "both use index 0"),
        ):
            with self.subTest(label):
                if self.source.exists():
                    shutil.rmtree(self.source)
                self.write_product(self.product(changes))
                with self.assertRaisesRegex(common.DeployError, pattern):
                    self.quiet(deploy.prepare)
                self.assertFalse(common.BUILD.exists())

    def install_all(self, product):
        self.write_product(product)
        releases = self.build_and_unpack()
        restarts = {
            name: self.install(releases[name])
            for name in ("accounts", "ledger", "reports")
            if name in releases
        }
        return releases, restarts

    def owner_secret(self):
        return self.secrets(catalog.component_paths("accounts")[2])["accounts-apis"]

    def value(self, name):
        return (common.STATE / name / "credentials/api/value").read_text()

    def test_install_rotation_removal_and_uninstall_update_the_owner(self):
        releases, restarts = self.install_all(self.product())
        self.assertEqual(
            restarts,
            {
                "accounts": ["accounts"],
                "ledger": ["ledger", "accounts"],
                "reports": ["reports", "accounts"],
            },
        )
        self.assertEqual(
            self.owner_secret(),
            {
                "ApiResources__0__ApiSecrets__0__Value": sha256(self.value("ledger")),
                "ApiResources__1__ApiSecrets__0__Value": self.value("reports"),
            },
        )
        registration = common.STATE / "apis/ledger.json"
        self.assertEqual(registration.stat().st_mode & 0o077, 0)
        self.assertEqual(
            json.loads(registration.read_text()),
            {"Index": 0, "Value": sha256(self.value("ledger"))},
        )

        with self.subTest("unchanged reinstall leaves the owner alone"):
            self.assertEqual(self.install(releases["ledger"]), ["ledger"])

        with self.subTest("a newer owner keeps the registrations"):
            self.assertEqual(self.install(releases["accounts"]), [])
            self.write_product(self.product(), version="1.1.0")
            newer = self.build_and_unpack()
            self.assertEqual(self.install(newer["accounts"]), ["accounts"])
            self.assertEqual(len(self.owner_secret()), 2)

        with self.subTest("a rotated secret restarts the API, then the owner"):
            rotated = common.STATE / "ledger/credentials/api/value"
            rotated.write_text("rotated-ledger-secret")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                restarts = self.install(releases["ledger"])
            self.assertEqual(restarts, ["ledger", "accounts"])
            self.assertEqual(
                self.owner_secret()["ApiResources__0__ApiSecrets__0__Value"],
                sha256("rotated-ledger-secret"),
            )
            self.assertEqual(
                self.secrets(catalog.component_paths("ledger")[2])[
                    "ledger-authentication"
                ],
                {"Authentication__ApiSecret": "rotated-ledger-secret"},
            )
            self.assertNotIn("rotated-ledger-secret", output.getvalue())
            self.assertNotIn(sha256("rotated-ledger-secret"), output.getvalue())

        with self.subTest("a release without the role removes the registration"):
            plain = copy.deepcopy(API_PRODUCT["reports"])
            plain["catalog"].pop("apis")
            plain.pop("api")
            (self.source / "components/reports/api.yaml").unlink()
            self.write_product(self.product({"reports": plain}), version="1.2.0")
            # Only reports is new; it requires the installed accounts version.
            (self.source / "components/accounts/VERSION").write_text("1.1.0\n")
            removed = self.build_and_unpack()
            self.assertEqual(self.install(removed["reports"]), ["reports", "accounts"])
            self.assertEqual(
                list(self.owner_secret()), ["ApiResources__0__ApiSecrets__0__Value"]
            )
            self.assertFalse((common.STATE / "apis/reports.json").exists())

        with self.subTest("uninstalling the API removes its resource"):
            self.use_root(releases["ledger"])
            self.process.reset_mock()
            self.quiet(deploy.uninstall)
            self.assertEqual(self.restarts(), ["accounts"])
            self.assertEqual(self.owner_secret(), {})
            self.assertFalse((common.STATE / "apis/ledger.json").exists())

    def test_newer_only_api_keeps_the_registration_it_runs_with(self):
        """Same version, not rendered: a changed file must not reach the owner alone."""
        ledger = copy.deepcopy(API_PRODUCT["ledger"])
        ledger["catalog"]["upgrade"] = "newer-only"
        releases, _ = self.install_all(self.product({"ledger": ledger}))
        before = self.owner_secret()
        (common.STATE / "ledger/credentials/api/value").write_text("not-yet-active")
        self.assertEqual(self.install(releases["ledger"]), [])
        self.assertEqual(self.owner_secret(), before)
        self.assertTrue((common.STATE / "apis/ledger.json").is_file())

    def test_duplicate_index_is_refused_before_production_writes(self):
        duplicate = copy.deepcopy(API_PRODUCT["reports"])
        duplicate["api"]["index"] = 0
        self.write_product(self.product({"reports": duplicate}))
        releases = self.build_and_unpack()
        self.install(releases["accounts"])
        self.install(releases["ledger"])
        self.use_root(releases["reports"])
        deploy.init_config("reports")
        before = self.snapshot(common.STATE)
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "ledger and reports both"):
            deploy.install()
        self.assertEqual(self.snapshot(common.STATE), before)
        self.process.assert_not_called()

    def test_api_descriptor_and_records_never_echo_values(self):
        path = self.root / "api.yaml"
        for metadata in (
            {"index": -1, "secret": "a-b/value", "hash": "none"},
            {"index": 0, "secret": "a-b", "hash": "none"},
            {"index": 0, "secret": "a-b/value"},
            [],
        ):
            with self.subTest(metadata=metadata):
                path.write_text(yaml.safe_dump(metadata))
                with self.assertRaisesRegex(common.DeployError, "Invalid API"):
                    registrations.api_descriptor(path)
        record = self.root / "ledger.json"
        record.write_text(json.dumps({"Index": "0", "Value": "do-not-show"}))
        with self.assertRaises(common.DeployError) as raised:
            registrations.api_record(record)
        self.assertNotIn("do-not-show", str(raised.exception))
