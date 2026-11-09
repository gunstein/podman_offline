"""Environment-specific ENVIRONMENT overrides (backlog 84).

A build environment file config/<environment>.yaml, or the reserved overrides
block of config/dev.yaml, adds or replaces single variables of named
containers. Expected values are written out here, never computed with the
merge under test.
"""

import copy
import hashlib
import io
import shutil
import tarfile
from contextlib import redirect_stderr, redirect_stdout

import bundle
import yaml
from deployment import catalog, common, deploy, environment, validation
from deployment import render as rendering

from helpers.product_fixture import RENAMED, ProductFixture, pod

# A value that must never appear in an error message.
MARKER = "marker-must-not-leak"


def shop():
    """One component with a regular, an init and an ENVIRONMENT-less container."""
    web = pod("shop-web", "localhost/shop:1", env={"FIXED": "1"})
    web["spec"]["initContainers"] = [
        {"name": "migrate", "image": "localhost/shop:1", "imagePullPolicy": "Never"}
    ]
    worker = pod("shop-worker", "localhost/shop:1")
    worker["spec"]["containers"][0]["name"] = "worker"
    return {
        "shop": {
            "defaults": {
                "DB_USER": "shop",
                "WORKERS": 4,
                "SECRET_FILES": {
                    "shop-tokens": [
                        {"path": "credentials/tokens", "generate": ["signing", "other"]}
                    ]
                },
            },
            "manifests": [web, worker],
            "env": {
                "main": {
                    "Logging__Level": "Information",
                    "Feature": "false",
                    "User": "@@DB_USER@@",
                    "Signing": "@@secret:shop-tokens/signing@@",
                },
                "migrate": {"Mode": "full"},
            },
            "mounts": {"main": {"/etc/shop/app.conf": "app.conf"}},
            "files": {"app.conf": "user=@@DB_USER@@\n"},
        }
    }


def documents(path):
    return {
        (doc["kind"], doc["metadata"]["name"]): doc
        for doc in yaml.safe_load_all(path.read_text())
        if doc
    }


def config_maps(path):
    return {
        name: doc["data"]
        for (kind, name), doc in documents(path).items()
        if kind == "ConfigMap" and name.endswith("-env")
    }


class OverrideFixture(ProductFixture):
    def put(self, relative, text):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def archive_file(self, archive, relative):
        """One member's text from a built archive, without unpacking it."""
        with tarfile.open(str(archive)) as tar:
            name = archive.name[: -len("-offline.tar.gz")]
            member = tar.extractfile(f"{name}/{relative}")
            assert member is not None
            return member.read().decode()

    def defaults_file(self, label, text):
        """Write text where merge_config reads it as a release's defaults."""
        path = self.root / label / "components/shop/config.defaults.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(text)
        return path

    def source_bytes(self):
        return {
            str(path.relative_to(self.source)): path.read_bytes()
            for path in self.source.rglob("*")
            if path.is_file()
            and path.relative_to(self.source).parts[0] not in ("dist", "build")
            and "__pycache__" not in path.parts
        }


DEV_OVERRIDES = """\
DB_USER: devshop
SECRET_FILES:
  shop-tokens:
  - path: credentials/dev-tokens
    generate: [signing, other]
overrides:
  shop:
    ENVIRONMENT:
      main:
        Logging__Level: Debug
        Reports__MaxRows: 500
        Enabled: yes
        Empty: ''
        Word: 'null'
      migrate:
        Mode: quick
      worker:
        Role: batch
"""


class DevOverrideTests(OverrideFixture):
    def setUp(self):
        super().setUp()
        self.write_product(shop())

    def test_dev_adds_and_replaces_single_variables(self):
        self.put("config/dev.yaml", DEV_OVERRIDES)
        deploy.prepare()
        install = common.BUILD / "install.yaml"
        self.assertEqual(
            config_maps(install),
            {
                "shop-main-env": {
                    "Logging__Level": "Debug",
                    "Feature": "false",
                    "User": "devshop",
                    "Reports__MaxRows": "500",
                    "Enabled": "yes",
                    "Empty": "",
                    "Word": "null",
                },
                "shop-migrate-env": {"Mode": "quick"},
                "shop-worker-env": {"Role": "batch"},
            },
        )
        rendered = documents(install)
        web = rendered[("Pod", "shop-web")]["spec"]
        self.assertEqual(
            web["initContainers"][0]["envFrom"],
            [{"configMapRef": {"name": "shop-migrate-env"}}],
        )
        worker = rendered[("Pod", "shop-worker")]["spec"]["containers"][0]
        self.assertEqual(
            worker["envFrom"], [{"configMapRef": {"name": "shop-worker-env"}}]
        )
        # dev.yaml's settings and file-source overrides still apply.
        dev = common.BUILD / "dev/shop"
        self.assertTrue((dev / "credentials/dev-tokens/signing").is_file())
        self.assertFalse((dev / "credentials/tokens").exists())
        written = yaml.safe_load((dev / "config.yaml").read_text())
        self.assertEqual(written["DB_USER"], "devshop")
        self.assertNotIn(common.OVERRIDES, written)
        self.assertNotIn(common.ENVIRONMENT, written)

    def test_validate_reports_the_merged_containers(self):
        self.put("config/dev.yaml", DEV_OVERRIDES)
        stream = io.StringIO()
        with redirect_stdout(stream), redirect_stderr(stream):
            validation.validate()
        report = stream.getvalue()
        self.assertIn(
            "[OK] shop/main: ENVIRONMENT -> 7 settings (ConfigMap shop-main-env), "
            "1 secret (Secret shop-main-env-secret: shop-tokens)",
            report,
        )
        self.assertIn("[OK] shop/worker: ENVIRONMENT -> 1 settings", report)
        self.assertFalse(common.BUILD.exists())

    def test_replacing_secret_and_public_lines_rebuilds_both(self):
        self.put(
            "config/dev.yaml",
            "overrides:\n  shop:\n    ENVIRONMENT:\n      main:\n"
            "        Signing: public-text\n"
            "        Logging__Level: '@@secret:shop-tokens/other@@'\n",
        )
        deploy.prepare()
        install = common.BUILD / "install.yaml"
        self.assertEqual(
            config_maps(install)["shop-main-env"],
            {"Feature": "false", "User": "shop", "Signing": "public-text"},
        )
        secret = documents(install)[("Secret", "shop-main-env-secret")]
        self.assertEqual(sorted(secret["data"]), ["Logging__Level"])

    def test_empty_overrides_have_no_effect(self):
        deploy.prepare()
        before = (common.BUILD / "install.yaml").read_text()
        for text in (
            "overrides: {}\n",
            "overrides:\n  shop: {}\n",
            "overrides:\n  shop:\n    ENVIRONMENT: {}\n",
            "overrides:\n  shop:\n    ENVIRONMENT:\n      main: {}\n",
        ):
            with self.subTest(text):
                self.put("config/dev.yaml", text)
                deploy.prepare()
                self.assertEqual((common.BUILD / "install.yaml").read_text(), before)

    def test_invalid_overrides_fail_before_any_write(self):
        twin = pod("shop-twin-a", "localhost/shop:1")
        twin_b = pod("shop-twin-b", "localhost/shop:1")
        for spec in (twin, twin_b):
            spec["spec"]["containers"][0]["name"] = "twin"

        def overrides(variables, container="main"):
            lines = "".join(f"        {line}\n" for line in variables)
            return f"overrides:\n  shop:\n    ENVIRONMENT:\n      {container}:\n{lines}"

        place = "config/dev.yaml: overrides.shop.ENVIRONMENT"
        for label, text, pattern in (
            ("empty assignment", overrides(["Logging__Level:"]),
             (f"{place}.main: Logging__Level has no value .YAML null.; write "
              "Logging__Level: '' for an empty value. There is no deletion")),
            ("null", overrides(["Logging__Level: null"]), "has no value .YAML null."),
            ("tilde", overrides(["Logging__Level: ~"]), "has no value .YAML null."),
            ("null block", "overrides:\n", "config/dev.yaml: overrides is empty"),
            ("null container", overrides([], "main"), f"{place}.main must hold"),
            ("duplicate key", overrides([f"A: {MARKER}", f"A: {MARKER}"]),
             "duplicate key 'A'"),
            ("case collision", overrides([f"logging__level: {MARKER}"]),
             (f"{place}.main: logging__level and Logging__Level "
              r"\(components/shop/config.defaults.yaml\) differ only in case")),
            ("case inside override", overrides([f"Ab: {MARKER}", f"AB: {MARKER}"]),
             f"{place}.main: Ab and AB differ only in case"),
            ("unknown component",
             "overrides:\n  nope:\n    ENVIRONMENT:\n      main:\n        A: b\n",
             ("config/dev.yaml: overrides.nope: nope is not a component in "
              "bundles.yaml; listed: shop")),
            ("unknown container", overrides([f"A: {MARKER}"], "web"),
             (f"{place}.web: the component must have exactly one container "
              "named web; it has 0")),
            ("ambiguous container", overrides([f"A: {MARKER}"], "twin"),
             "exactly one container named twin; it has 2"),
            ("forbidden field",
             "overrides:\n  shop:\n    MOUNTS:\n      main: {}\n",
             ("overrides.shop: MOUNTS cannot be overridden; an environment "
              "changes only ENVIRONMENT")),
            ("manifest env", overrides([f"fixed: {MARKER}"]),
             f"{place}.main: fixed is also set in the manifest's env"),
            ("undeclared secret", overrides(["A: '@@secret:shop-missing/value@@'"]),
             (f"{place}.main: A: SECRET_FILES has no shop-missing; declared: "
              "shop-tokens")),
            ("foreign secret", overrides(["A: '@@secret:other-x/value@@'"]),
             f"{place}.main.A: other-x is another component's secret"),
            ("unknown placeholder", overrides([f"A: '{MARKER}@@nope@@'"]),
             "A: unknown or nested placeholder"),
            ("list", overrides([f"A: [{MARKER}]"]), "A must be one line of text"),
            ("colon", overrides(["'A:B': x"]), "use __ instead of :"),
        ):  # fmt: skip
            with self.subTest(label):
                product = shop()
                product["shop"]["manifests"] += [twin, twin_b]
                shutil.rmtree(self.source)
                self.write_product(product)
                self.put("config/dev.yaml", text)
                with self.assertRaisesRegex(common.DeployError, pattern) as raised:
                    deploy.prepare()
                self.assertNotIn(MARKER, str(raised.exception))
                self.assertFalse(common.BUILD.exists())


def environment_file(**containers):
    """config/<environment>.yaml text overriding shop's containers."""
    return yaml.safe_dump(
        {"overrides": {"shop": {"ENVIRONMENT": containers}}}, sort_keys=False
    )


class EnvironmentBuildTests(OverrideFixture):
    def setUp(self):
        super().setUp()
        self.write_product(shop())
        self.put(
            "config/prod1.yaml",
            "overrides:\n  shop:\n    ENVIRONMENT:\n      main:\n"
            "        Logging__Level: Warning\n        Reports__MaxRows: 500\n"
            "        Enabled: true\n        Word: 'null'\n        Empty: ''\n",
        )
        self.put("config/prod2.yaml", environment_file(migrate={"Mode": "none"}))
        # Dev overrides never reach a bundle.
        self.put("config/dev.yaml", DEV_OVERRIDES)

    def bundled(self, environment_name=None):
        dist = bundle.DIST / (environment_name or "")
        archive = dist / "myproduct-shop-1.0.0-offline.tar.gz"
        return self.archive_file(archive, "components/shop/config.defaults.yaml")

    def test_environment_builds_are_separate_and_source_stays_unchanged(self):
        source = self.source_bytes()
        bundle.build(environment_name="prod1")
        bundle.build(environment_name="prod2")
        bundle.build()
        self.assertEqual(self.source_bytes(), source)
        archive = "myproduct-shop-1.0.0-offline.tar.gz\n"
        for directory in ("dist/prod1", "dist/prod2", "dist"):
            with self.subTest(directory):
                self.assertEqual(
                    (self.source / directory / "current-bundles.txt").read_text(),
                    archive,
                )
        loaded = {}
        for name in ("prod1", "prod2", None):
            loaded[name] = self.defaults_file(str(name), self.bundled(name))
        self.assertEqual(
            environment.read_defaults(loaded["prod1"]),
            {
                "main": {
                    "Logging__Level": "Warning",
                    "Feature": "false",
                    "User": "@@DB_USER@@",
                    "Signing": "@@secret:shop-tokens/signing@@",
                    "Reports__MaxRows": "500",
                    "Enabled": "true",
                    "Word": "null",
                    "Empty": "",
                },
                "migrate": {"Mode": "full"},
            },
        )
        self.assertEqual(
            environment.read_defaults(loaded["prod2"]),
            {
                "main": {
                    "Logging__Level": "Information",
                    "Feature": "false",
                    "User": "@@DB_USER@@",
                    "Signing": "@@secret:shop-tokens/signing@@",
                },
                "migrate": {"Mode": "none"},
            },
        )
        # Without an environment the file is shipped byte for byte.
        self.assertEqual(
            self.bundled(),
            (self.source / "components/shop/config.defaults.yaml").read_text(),
        )
        # Settings keep their types; MOUNTS keeps its text.
        for name in ("prod1", "prod2"):
            settings = rendering.merge_config(loaded[name])
            self.assertEqual(settings["WORKERS"], 4)
            self.assertEqual(settings["DB_USER"], "shop")
            self.assertEqual(
                environment.load(loaded[name])["MOUNTS"],
                {"main": {"/etc/shop/app.conf": "app.conf"}},
            )
        digests = {
            hashlib.sha256(
                (self.source / directory / archive.strip()).read_bytes()
            ).hexdigest()
            for directory in ("dist/prod1", "dist/prod2", "dist")
        }
        self.assertEqual(len(digests), 3)

    def test_a_partial_build_keeps_the_environment_list(self):
        bundle.build(environment_name="prod1")
        current = (bundle.DIST / "prod1/current-bundles.txt").read_text()
        (bundle.DIST / "prod1/current-bundles.txt").write_text("kept\n")
        bundle.build(["shop"], environment_name="prod1")
        self.assertEqual(
            (bundle.DIST / "prod1/current-bundles.txt").read_text(), "kept\n"
        )
        self.assertTrue(current)
        self.assertFalse((bundle.DIST / "current-bundles.txt").exists())

    def test_isolated_bundle_installs_and_rerenders_its_environment(self):
        releases = self.build_and_unpack("prod1")
        shutil.rmtree(self.source)  # No checkout, no config/prod1.yaml.
        with self.environment():
            self.install(releases["shop"])
            installed = common.QUADLET_DIR / "myproduct-shop.yaml"
            expected = {
                "Logging__Level": "Warning",
                "Feature": "false",
                "User": "shop",
                "Reports__MaxRows": "500",
                "Enabled": "true",
                "Word": "null",
                "Empty": "",
            }
            self.assertEqual(config_maps(installed)["shop-main-env"], expected)
            written = yaml.safe_load((common.STATE / "shop/config.yaml").read_text())
            self.assertNotIn(common.ENVIRONMENT, written)
            self.assertNotIn(common.OVERRIDES, written)
            self.assertEqual(written["WORKERS"], 4)
            # An equal-version install renders the compiled declarations again.
            self.process.reset_mock()
            deploy.install()
            self.assertEqual(config_maps(installed)["shop-main-env"], expected)

    def test_invalid_selections_fail_before_any_output(self):
        for label, name, text, pattern in (
            ("traversal", "../prod1", None, "use lowercase letters"),
            ("upper case", "Prod1", None, "use lowercase letters"),
            ("reserved dev", "dev", None, "config/dev.yaml has another meaning"),
            ("reserved images", "images", None, "config/images.yaml has another"),
            ("missing file", "prod9", None, "missing file config/prod9.yaml"),
            ("components", "prod3", "components: [shop]\n",
             "config/prod3.yaml: components: .* is not implemented yet"),
            ("other key", "prod3", "DB_USER: x\n",
             "config/prod3.yaml: 'DB_USER' is not allowed"),
            ("unknown component", "prod3",
             "overrides:\n  nope:\n    ENVIRONMENT:\n      main:\n        A: b\n",
             "config/prod3.yaml: overrides.nope: nope is not a component"),
            ("unknown container", "prod3", environment_file(web={"A": MARKER}),
             ("config/prod3.yaml: overrides.shop.ENVIRONMENT.web: the component "
              "must have exactly one container named web; it has 0")),
            ("null value", "prod3",
             "overrides:\n  shop:\n    ENVIRONMENT:\n      main:\n        A:\n",
             "config/prod3.yaml: overrides.shop.ENVIRONMENT.main: A has no value"),
            ("undeclared secret", "prod3",
             environment_file(main={"A": "@@secret:shop-nope/x@@"}),
             "SECRET_FILES has no shop-nope"),
            ("case collision", "prod3",
             environment_file(main={"logging__level": MARKER}), "differ only in case"),
        ):  # fmt: skip
            with self.subTest(label):
                if text is not None:
                    self.put(f"config/{name}.yaml", text)
                with self.assertRaisesRegex(common.DeployError, pattern) as raised:
                    bundle.build(environment_name=name)
                self.assertNotIn(MARKER, str(raised.exception))
                self.assertFalse(bundle.DIST.exists())
                self.assertFalse(common.BUILD.exists())

    def test_a_selected_build_refuses_overrides_outside_the_catalog(self):
        self.put(
            "config/prod3.yaml",
            "overrides:\n  gone:\n    ENVIRONMENT:\n      main:\n        A: b\n",
        )
        with self.assertRaisesRegex(common.DeployError, "gone is not a component"):
            bundle.build(["shop"], environment_name="prod3")
        self.assertFalse(bundle.DIST.exists())

    def test_build_bundle_command_reports_errors_on_one_line(self):
        stream = io.StringIO()
        with redirect_stdout(stream), redirect_stderr(stream):
            self.assertEqual(bundle.main(["--environment", "prod9"]), 1)
        self.assertIn(
            "ERROR: --environment prod9: missing file config/prod9.yaml",
            stream.getvalue(),
        )


def api_product():
    """accounts (Identity) has ledger's resource name only; environments add its secret."""
    return {
        "accounts": {
            "role": "identity",
            "manifests": [pod("accounts-server", "localhost/accounts:1")],
            "env": {"main": {"ApiResources__0__Name": "ledger"}},
        },
        "ledger": {
            "manifests": [pod("ledger-server", "localhost/ledger:1")],
            "defaults": {
                "SECRET_FILES": {
                    "ledger-api-secret": [
                        {"path": "credentials/api-secret", "generate": ["value"]}
                    ]
                }
            },
            "env": {
                "main": {
                    "Authentication__ApiSecret": "@@secret:ledger-api-secret/value@@"
                }
            },
        },
    }


API_LINE = (
    "overrides:\n  accounts:\n    ENVIRONMENT:\n      main:\n"
    "        ApiResources__0__ApiSecrets__0__Value: '@@secret:ledger-api-secret/value@@'\n"
)


class ApiOverrideTests(OverrideFixture):
    def setUp(self):
        super().setUp()
        self.write_product(api_product())

    def test_identity_mapping_follows_the_effective_declarations(self):
        self.put("config/prod1.yaml", API_LINE)
        common_descriptors = catalog.source_descriptors(self.source)
        self.assertEqual(common_descriptors["accounts"]["api_secrets"], {})
        self.assertIsNone(common_descriptors["ledger"]["apis"])
        releases = self.build_and_unpack("prod1")
        accounts = catalog.load_bundle_descriptor(releases["accounts"])
        ledger = catalog.load_bundle_descriptor(releases["ledger"])
        self.assertEqual(
            accounts["api_secrets"],
            {"ledger": {"index": 0, "secret": "ledger-api-secret/value"}},
        )
        self.assertEqual(accounts["accepts"], {"apis": "accounts-apis"})
        self.assertEqual(ledger["apis"], "accounts")
        self.assertEqual(list(ledger["requires"]), ["accounts"])
        bundled = environment.read_defaults(
            releases["accounts"] / "components/accounts/config.defaults.yaml"
        )
        self.assertEqual(
            bundled["main"]["ApiResources__0__ApiSecrets__0__Value"],
            "@@secret:ledger-api-secret/value@@",
        )

    def test_dev_renders_the_api_secret_named_by_an_override(self):
        self.put("config/dev.yaml", API_LINE)
        deploy.prepare()
        rendered = documents(common.BUILD / "install.yaml")
        self.assertEqual(
            sorted(rendered[("Secret", "accounts-apis")]["data"]),
            ["ApiResources__0__ApiSecrets__0__Value"],
        )
        main = rendered[("Pod", "accounts-server")]["spec"]["containers"][0]
        self.assertIn({"secretRef": {"name": "accounts-apis"}}, main["envFrom"])

    def test_only_identity_may_name_another_components_secret(self):
        self.put(
            "config/prod1.yaml",
            "overrides:\n  ledger:\n    ENVIRONMENT:\n      main:\n"
            "        Other: '@@secret:accounts-key/value@@'\n",
        )
        with self.assertRaisesRegex(
            common.DeployError,
            "config/prod1.yaml: overrides.ledger.ENVIRONMENT.main.Other: "
            "accounts-key is another component's secret",
        ):
            bundle.build(environment_name="prod1")


def override_orders():
    """RENAMED orders with POSTGRES_PASSWORD_FILE only in an override."""
    product = copy.deepcopy(RENAMED)
    db = product["orders"]["manifests"][1]["spec"]["containers"][0]
    db["env"] = [e for e in db["env"] if e["name"] != "POSTGRES_PASSWORD_FILE"]
    return product


PASSWORD_LINE = (
    "overrides:\n  orders:\n    ENVIRONMENT:\n      db:\n"
    "        POSTGRES_PASSWORD_FILE: /run/secrets/database/password\n"
)


class OverridePasswordTests(OverrideFixture):
    def setUp(self):
        super().setUp()
        self.product = override_orders()
        self.write_product(self.product)
        self.password = common.BUILD / "dev/orders/credentials/database/password"

    def test_dev_override_keeps_the_password_guard(self):
        self.put("config/dev.yaml", PASSWORD_LINE)
        self.provide_credentials(self.product, common.BUILD / "dev")
        self.volumes.add("orders-data")
        with self.assertRaisesRegex(
            common.DeployError, "with existing volume orders-data; .*no password"
        ):
            deploy.prepare()
        self.assertFalse(self.password.exists())
        self.volumes.clear()
        deploy.prepare()
        self.assertTrue(self.password.is_file())

    def test_compiled_override_keeps_the_password_guard_at_install(self):
        self.put("config/prod1.yaml", PASSWORD_LINE)
        releases = self.build_and_unpack("prod1")
        shutil.rmtree(self.source)
        self.provide_credentials(self.product, common.STATE)
        with self.environment():
            for name in ("gateway", "login-service"):
                self.install(releases[name])
            self.use_root(releases["orders"])
            deploy.init_config("orders")
            self.volumes.add("orders-data")
            before = self.files_under(common.STATE)
            self.process.reset_mock()
            with self.assertRaisesRegex(
                common.DeployError, "existing volume orders-data"
            ):
                deploy.install()
            self.assertEqual(
                self.commands(), [["podman", "volume", "exists", "orders-data"]]
            )
            self.assertEqual(self.files_under(common.STATE), before)


class CompiledTextTests(OverrideFixture):
    def test_compiled_file_reads_back_as_the_merged_text(self):
        """Values YAML would read as another type stay the written text."""
        self.write_product(shop())
        values = {
            "Octal": "0022",
            "Float": "1.10",
            "Bool": "yes",
            "Null": "null",
            "Tilde": "~",
            "Empty": "",
            "Reference": "@@secret:shop-tokens/other@@",
            "Spaces": "  padded  ",
            "Long": "x" * 300 + " y",
            "Unicode": "blåbær",
            "Colon": "a: b",
            "Hash": "a #b",
        }
        overrides = environment.Overrides(
            "config/prod1.yaml", {"shop": {"main": values}}
        )
        path = self.source / "components/shop/config.defaults.yaml"
        compiled = self.defaults_file(
            "compiled", bundle.compiled_defaults(path, "shop", overrides)
        )
        self.assertEqual(
            environment.read_defaults(compiled)["main"],
            dict(environment.read_defaults(path)["main"], **values),
        )
        self.assertEqual(rendering.merge_config(compiled), rendering.merge_config(path))
