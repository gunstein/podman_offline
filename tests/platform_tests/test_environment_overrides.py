"""ENVIRONMENT overrides in dev and on the target (backlogs 84 and 85).

config/dev.yaml's reserved overrides block, or a target environment file
/var/lib/<product>/state/<environment>.yaml applied at deployment
(deploy.sh install --environment), adds or replaces single variables of named
containers. Bundles are built without any environment. Expected values are
written out here, never computed with the merge under test.
"""

import base64
import copy
import io
import shutil
import subprocess
from contextlib import redirect_stderr, redirect_stdout

import yaml
from deployment import catalog, common, deploy, environment, validation

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


def environment_file(components, **containers):
    """A target environment file: its components and the first one's containers."""
    document = {"components": components}
    if containers:
        document["overrides"] = {components[0]: {"ENVIRONMENT": containers}}
    return yaml.safe_dump(document, sort_keys=False)


class OverrideFixture(ProductFixture):
    def put(self, relative, text):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def state_bytes(self):
        """Every state file except the environment files, for "nothing changed"."""
        return {
            str(path.relative_to(common.STATE)): path.read_bytes()
            for path in common.STATE.rglob("*")
            if path.is_file() and path.parent != common.STATE
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

    def test_overrides_is_no_setting_of_a_component(self):
        product = shop()
        product["shop"]["defaults"]["overrides"] = "x"
        shutil.rmtree(self.source)
        self.write_product(product)
        with self.assertRaisesRegex(
            common.DeployError,
            "config.defaults.yaml: overrides is reserved for config/dev.yaml",
        ):
            deploy.prepare()
        self.assertFalse(common.BUILD.exists())

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
            ("null name", overrides([f"null: {MARKER}"]),
             f"{place}.main: None is not a variable name"),
            ("malformed placeholder", overrides([f"A: '{MARKER}@@DB_USER'"]),
             f"{place}.main: A: malformed placeholder"),
            ("client setting", overrides(["A: '@@CLIENT_ID@@'"]),
             "A: @@CLIENT_ID@@ comes from client.yaml, which components/shop"),
            ("empty unknown component", "overrides:\n  nope: {}\n",
             "overrides.nope: nope is not a component"),
            ("empty unknown container",
             "overrides:\n  shop:\n    ENVIRONMENT:\n      web: {}\n",
             f"{place}.web: the component must have exactly one container"),
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


PROD1 = (
    "components: [shop]\n"
    "overrides:\n  shop:\n    ENVIRONMENT:\n      main:\n"
    "        Logging__Level: Warning\n        Reports__MaxRows: 500\n"
    "        Enabled: true\n        Word: 'null'\n        Empty: ''\n"
)


class TargetEnvironmentTests(OverrideFixture):
    """One neutral bundle, the environment applied by deploy.sh install --environment."""

    def setUp(self):
        super().setUp()
        self.write_product(shop())
        # Dev overrides never reach a bundle or a target.
        self.put("config/dev.yaml", DEV_OVERRIDES)
        self.releases_built = self.build_and_unpack()
        shutil.rmtree(self.source)  # No checkout on the target.
        self.installed = None

    def install_shop(self, environment_name=None):
        with self.environment():
            self.install(self.releases_built["shop"], environment_name=environment_name)
        return config_maps(common.QUADLET_DIR / "myproduct-shop.yaml")

    def test_one_bundle_in_two_environments(self):
        release = self.releases_built["shop"]
        bundled = release / "components/shop/config.defaults.yaml"
        self.assertEqual(
            environment.read_defaults(bundled)["main"]["Logging__Level"], "Information"
        )
        self.place_environment("prod1", PROD1)
        self.assertEqual(
            self.install_shop("prod1")["shop-main-env"],
            {
                "Logging__Level": "Warning",
                "Feature": "false",
                "User": "shop",
                "Reports__MaxRows": "500",
                "Enabled": "true",
                "Word": "null",
                "Empty": "",
            },
        )
        config = (common.STATE / "shop/config.yaml").read_bytes()
        written = yaml.safe_load(config)
        self.assertNotIn(common.ENVIRONMENT, written)
        self.assertNotIn(common.OVERRIDES, written)
        self.assertEqual(written["WORKERS"], 4)
        # The same release in another environment: its overrides only.
        self.place_environment(
            "prod2", environment_file(["shop"], migrate={"Mode": "none"})
        )
        maps = self.install_shop("prod2")
        self.assertEqual(maps["shop-main-env"]["Logging__Level"], "Information")
        self.assertNotIn("Reports__MaxRows", maps["shop-main-env"])
        self.assertEqual(maps["shop-migrate-env"], {"Mode": "none"})
        # The operator's config is the same file; the release is unchanged.
        self.assertEqual((common.STATE / "shop/config.yaml").read_bytes(), config)
        self.assertEqual(
            environment.read_defaults(bundled)["main"]["Logging__Level"], "Information"
        )
        # Without an environment the release's declarations would silently
        # replace prod2's overrides: refused before any change (backlog 85).
        before = self.state_bytes()
        with self.assertRaisesRegex(
            common.DeployError,
            "shop was installed with --environment prod2, which gave it overrides "
            "or an API secret line; an install without it would remove them. Run "
            "myproduct --environment prod2",
        ):
            self.install_shop()
        self.assertEqual(self.state_bytes(), before)
        # After an explicit uninstall: the release's declarations alone.
        with self.environment(), redirect_stdout(io.StringIO()):
            deploy.uninstall()
        self.assertEqual(self.install_shop()["shop-migrate-env"], {"Mode": "full"})

    def test_a_secret_line_and_a_public_line_swap(self):
        self.place_environment(
            "prod1",
            environment_file(
                ["shop"],
                main={
                    "Signing": "public",
                    "Logging__Level": "@@secret:shop-tokens/other@@",
                },
            ),
        )
        maps = self.install_shop("prod1")
        self.assertEqual(maps["shop-main-env"]["Signing"], "public")
        self.assertNotIn("Logging__Level", maps["shop-main-env"])
        secret = documents(common.QUADLET_DIR / "myproduct-shop.yaml")[
            ("Secret", "shop-main-env-secret")
        ]
        self.assertEqual(sorted(secret["data"]), ["Logging__Level"])

    def test_interrupted_install_retries_with_the_file(self):
        self.place_environment("prod1", PROD1)
        failed = []

        def restart(arguments, **kwargs):
            if list(arguments)[:3] == ["systemctl", "--user", "restart"] and not failed:
                failed.append(arguments)
                raise subprocess.CalledProcessError(1, arguments)
            return self.host_command(arguments, **kwargs)

        self.process.side_effect = restart
        with self.environment():
            self.use_root(self.releases_built["shop"])
            deploy.init_config("shop", environment_name="prod1")
            with self.assertRaises(subprocess.CalledProcessError):
                deploy.install("prod1")
            self.assertTrue((common.STATE / "pending-operation.json").is_file())
            deploy.install("prod1")
        self.assertFalse((common.STATE / "pending-operation.json").exists())
        maps = config_maps(common.QUADLET_DIR / "myproduct-shop.yaml")
        self.assertEqual(maps["shop-main-env"]["Logging__Level"], "Warning")
        self.assertEqual((common.STATE / "installed/shop").read_text(), "1.0.0\n")

    def test_invalid_environments_change_nothing(self):
        self.place_environment("prod1", PROD1)
        self.install_shop("prod1")
        before = self.state_bytes()
        rendered = (common.QUADLET_DIR / "myproduct-shop.yaml").read_bytes()
        for label, name, text, pattern in (
            ("bad name", "Prod9", None, "use lowercase letters"),
            ("missing file", "prod9", None, "missing file .*prod9.yaml"),
            ("no components", "prod3", "overrides: {}\n",
             "components: is missing; list the components of this installation"),
            ("empty components", "prod3", "components: []\n",
             "components: list at least one component"),
            ("repeated", "prod3", "components: [shop, shop]\n", "lists shop twice"),
            ("other key", "prod3", "components: [shop]\nDB_USER: x\n",
             "'DB_USER' is not allowed"),
            ("not listed", "prod3", "components: [other]\n",
             "shop is not in components:"),
            ("override outside", "prod3",
             ("components: [shop]\noverrides:\n  other:\n    ENVIRONMENT:\n"
              "      main:\n        A: b\n"),
             "overrides.other: other is not in components:"),
            ("unknown container", "prod3", environment_file(["shop"], web={"A": MARKER}),
             "overrides.shop.ENVIRONMENT.web: the component must have exactly one"),
            ("null value", "prod3",
             ("components: [shop]\noverrides:\n  shop:\n    ENVIRONMENT:\n"
              "      main:\n        A:\n"),
             "main: A has no value .YAML null."),
            ("undeclared secret", "prod3",
             environment_file(["shop"], main={"A": "@@secret:shop-nope/x@@"}),
             "SECRET_FILES has no shop-nope"),
            ("case collision", "prod3",
             environment_file(["shop"], main={"logging__level": MARKER}),
             "differ only in case"),
            ("malformed placeholder", "prod3",
             environment_file(["shop"], main={"A": MARKER + "@@DB_USER"}),
             "A: malformed placeholder"),
            ("client setting", "prod3",
             environment_file(["shop"], main={"A": "@@CLIENT_ID@@"}),
             "@@CLIENT_ID@@ comes from client.yaml"),
        ):  # fmt: skip
            with self.subTest(label):
                if text is not None:
                    self.place_environment(name, text)
                self.process.reset_mock()
                with self.environment():
                    self.use_root(self.releases_built["shop"])
                    with self.assertRaisesRegex(common.DeployError, pattern) as raised:
                        deploy.install(name)
                    # check-environment refuses the same files without config.
                    if text is not None and label not in ("not listed",):
                        with self.assertRaisesRegex(common.DeployError, pattern):
                            deploy.check_environment(name)
                self.assertNotIn(MARKER, str(raised.exception))
                self.process.assert_not_called()
                self.assertEqual(self.state_bytes(), before)
                self.assertEqual(
                    (common.QUADLET_DIR / "myproduct-shop.yaml").read_bytes(), rendered
                )

    def test_check_environment_needs_no_config(self):
        self.place_environment("prod1", PROD1)
        self.process.reset_mock()  # The build ran podman save.
        with self.environment():
            self.use_root(self.releases_built["shop"])
            deploy.check_environment("prod1")
        self.assertFalse((common.STATE / "shop").exists())
        self.process.assert_not_called()

    def test_validate_applies_the_environment(self):
        self.place_environment("prod1", PROD1)
        self.install_shop("prod1")
        with self.environment():
            self.use_root(self.releases_built["shop"])
            with self.assertLogs("deployment", "INFO") as shown:
                validation.validate("prod1")
        self.assertIn(
            "[OK] shop/main: ENVIRONMENT -> 7 settings (ConfigMap shop-main-env)",
            "\n".join(shown.output),
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


LINE = "@@secret:ledger-api-secret/value@@"
API_LINE = (
    "overrides:\n  accounts:\n    ENVIRONMENT:\n      main:\n"
    f"        ApiResources__0__ApiSecrets__0__Value: '{LINE}'\n"
)


class ApiOverrideTests(OverrideFixture):
    def setUp(self):
        super().setUp()
        self.write_product(api_product())

    def neutral_releases(self):
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        return releases

    def test_the_target_environment_registers_the_api(self):
        releases = self.neutral_releases()
        accounts = catalog.load_bundle_descriptor(releases["accounts"])
        self.assertEqual(accounts["api_secrets"], {})
        self.assertEqual(accounts["identity"], "accounts")
        self.place_environment("prod1", "components: [accounts, ledger]\n" + API_LINE)
        with self.environment():
            self.install(releases["accounts"], environment_name="prod1")
            self.install(releases["ledger"], environment_name="prod1")
        installed = catalog.load_installed_metadata(common.STATE)
        self.assertEqual(
            installed["accounts"]["api_secrets"],
            {"ledger": {"index": 0, "secret": "ledger-api-secret/value"}},
        )
        self.assertEqual(installed["accounts"]["accepts"], {"apis": "accounts-apis"})
        self.assertEqual(installed["ledger"]["apis"], "accounts")
        self.assertEqual(list(installed["ledger"]["requires"]), ["accounts"])
        # Both sides hold the API's own generated secret, byte for byte.
        value = (common.STATE / "ledger/credentials/api-secret/value").read_bytes()
        self.assertTrue(value)
        self.assertEqual((common.STATE / "apis/ledger/value").read_bytes(), value)
        identity = documents(common.QUADLET_DIR / "myproduct-accounts.yaml")
        self.assertEqual(
            base64.b64decode(
                identity[("Secret", "accounts-apis")]["data"][
                    "ApiResources__0__ApiSecrets__0__Value"
                ]
            ),
            value,
        )
        # An Identity release deployed without the line would drop the
        # installed API: refused, nothing changed.
        self.place_environment("prod2", "components: [accounts, ledger]\n")
        before = self.state_bytes()
        with self.environment():
            self.use_root(releases["accounts"])
            with self.assertRaisesRegex(
                common.DeployError,
                "no API secret line for installed ledger; uninstall ledger first",
            ):
                deploy.install("prod2")
        self.assertEqual(self.state_bytes(), before)

    def test_without_the_line_the_same_bundles_have_no_api(self):
        releases = self.neutral_releases()
        self.place_environment("prod2", "components: [accounts, ledger]\n")
        with self.environment():
            self.install(releases["accounts"], environment_name="prod2")
            self.install(releases["ledger"], environment_name="prod2")
        installed = catalog.load_installed_metadata(common.STATE)
        self.assertEqual(installed["accounts"]["api_secrets"], {})
        self.assertIsNone(installed["ledger"]["apis"])
        self.assertFalse((common.STATE / "apis/ledger").exists())

    def test_references_outside_the_environment_are_refused(self):
        releases = self.neutral_releases()
        for label, release, text, pattern in (
            ("excluded API", "accounts", "components: [accounts]\n" + API_LINE,
             "no listed component owns ledger-api-secret"),
            ("not Identity", "ledger",
             ("components: [accounts, ledger]\noverrides:\n  ledger:\n"
              "    ENVIRONMENT:\n      main:\n        Other: '@@secret:accounts-key/x@@'\n"),
             "Other names another component's secret"),
            ("undeclared API secret", "ledger",
             ("components: [accounts, ledger]\noverrides:\n  accounts:\n"
             "    ENVIRONMENT:\n      main:\n"
             "        ApiResources__0__ApiSecrets__0__Value: '@@secret:ledger-other/value@@'\n"),
             "names ledger-other, which ledger does not declare"),
        ):  # fmt: skip
            with self.subTest(label):
                self.place_environment("prod3", text)
                with self.environment():
                    self.use_root(releases[release])
                    with self.assertRaisesRegex(common.DeployError, pattern):
                        deploy.check_environment("prod3")
                self.assertFalse((common.STATE / "installed").exists())

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

    def test_target_override_keeps_the_password_guard_at_install(self):
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        self.provide_credentials(self.product, common.STATE)
        self.place_environment(
            "prod1", "components: [gateway, login-service, orders]\n" + PASSWORD_LINE
        )
        with self.environment():
            for name in ("gateway", "login-service"):
                self.install(releases[name], environment_name="prod1")
            self.use_root(releases["orders"])
            deploy.init_config("orders", environment_name="prod1")
            self.volumes.add("orders-data")
            before = self.files_under(common.STATE)
            self.process.reset_mock()
            with self.assertRaisesRegex(
                common.DeployError, "existing volume orders-data"
            ):
                deploy.install("prod1")
            self.assertEqual(
                self.commands(), [["podman", "volume", "exists", "orders-data"]]
            )
            self.assertEqual(self.files_under(common.STATE), before)
