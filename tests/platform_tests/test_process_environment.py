"""@@$NAME@@: variables of the process environment in placeholders (backlog 86).

Every test sets common.ENVIRON to its own dictionary, so the developer's or
the test runner's environment never takes part. Expected values are written
out here, never computed with the resolver under test.
"""

import base64
import contextlib
import copy
import io
import json
import shutil
from unittest import mock

import bundle
import yaml
from deployment import catalog, common, deploy, mounts, templates
from deployment import render as rendering

from helpers.product_fixture import ProductFixture, pod
from platform_tests.test_environment_components import (
    TargetEffectTests,
    environment_file,
)
from platform_tests.test_environment_overrides import config_maps, documents

# A value that must never appear in a message.
MARKER = "marker-must-not-leak"


def environ(**values):
    """common.ENVIRON for one test: exactly these variables."""
    return mock.patch.object(common, "ENVIRON", dict(values))


class ResolverTests(ProductFixture):
    """templates.environment_text and the template pass, on their own."""

    def test_whole_embedded_and_several_references(self):
        with environ(A="alpha", B="beta", EMPTY=""):
            for text, expected in (
                ("@@$A@@", "alpha"),
                ("https://@@$A@@:8443/x", "https://alpha:8443/x"),
                ("@@$A@@-@@$B@@-@@$A@@", "alpha-beta-alpha"),
                ("[@@$EMPTY@@]", "[]"),
                # Other placeholders and plain shell text stay as they are.
                (
                    "@@NAME@@ @@$A@@ @@secret:shop-tokens/key@@",
                    "@@NAME@@ alpha @@secret:shop-tokens/key@@",
                ),
                ("echo $A ${B} $$", "echo $A ${B} $$"),
            ):
                with self.subTest(text):
                    self.assertEqual(templates.environment_text(text, "here"), expected)

    def test_names_are_case_sensitive_and_checked(self):
        with environ(Name="mixed", name="lower"):
            self.assertEqual(templates.environment_text("@@$Name@@", "x"), "mixed")
            self.assertEqual(templates.environment_text("@@$name@@", "x"), "lower")
            for text in ("@@$1A@@", "@@$A-B@@", "@@$@@", "@@$A B@@", "@@${A}@@"):
                with self.subTest(text):
                    with self.assertRaisesRegex(
                        common.DeployError,
                        r"here: invalid environment variable in @@\$\.\.\.@@",
                    ):
                        templates.environment_text(text, "here")

    def test_a_missing_variable_names_itself_and_the_place(self):
        with environ():
            with self.assertRaisesRegex(
                common.DeployError,
                r"^PUBLIC_ORIGIN in dev\.yaml: environment variable HOSTNAME is not "
                r"set; export it in the shell that runs this command "
                r"\(export HOSTNAME=\.\.\.\), then run the command again$",
            ):
                templates.environment_text(
                    "https://@@$HOSTNAME@@:8443", "PUBLIC_ORIGIN in dev.yaml"
                )

    def test_a_value_is_text_never_a_placeholder(self):
        for value in ("@@$B@@", "@@NAME@@", MARKER + "@@"):
            with self.subTest(value), environ(A=value, B="beta", NAME="n"):
                with self.assertRaises(common.DeployError) as raised:
                    templates.environment_text("x=@@$A@@", "here")
                self.assertIn(
                    "environment variable A contains @@", str(raised.exception)
                )
                self.assertNotIn(MARKER, str(raised.exception))
        # No shell: the text of the value is inserted, never run.
        with environ(A="$(hostname) `id` ${HOME}"):
            self.assertEqual(
                templates.environment_text("@@$A@@", "x"), "$(hostname) `id` ${HOME}"
            )

    def test_values_are_text(self):
        with environ(PORT="8443", ON="true"):
            config = rendering.resolve_settings(
                {"LABEL": "@@$ON@@", "COUNT": "@@$PORT@@"}, "config.yaml"
            )
            self.assertEqual(config, {"LABEL": "true", "COUNT": "8443"})
            # HTTPS_PORT is an integer: a variable cannot give one.
            with self.assertRaisesRegex(
                common.DeployError, "HTTPS_PORT in config.yaml"
            ):
                rendering.resolve_settings({"HTTPS_PORT": "@@$PORT@@"}, "config.yaml")


def shop():
    """One component using @@$NAME@@ in every supported place."""
    web = pod(
        "shop-web",
        "localhost/shop:1",
        env={"POD_LABEL": "@@SERVICE_LABEL@@", "POD_HOST": "@@$LOG_HOST@@"},
    )
    web["spec"]["containers"][0]["volumeMounts"] = []
    page = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "shop-page"},
        "data": {
            "endpoint": "https://@@$LOG_HOST@@:9443/@@SERVICE_LABEL@@",
            "whole": "@@$LOG_HOST@@",
            "shell": "echo $HOME ${PATH}",
        },
    }
    return {
        "shop": {
            "defaults": {
                "SERVICE_LABEL": "@@$SERVICE_LABEL@@",
                # Replaced in config/dev.yaml: its variable is never needed.
                "LOG_ENDPOINT": "https://@@$UNUSED_DEFAULT@@:9443",
                "DB_USER": "shop",
                "SECRET_FILES": {
                    "shop-tokens": [
                        {"path": "credentials/tokens", "generate": ["signing"]}
                    ]
                },
            },
            "manifests": [web, page],
            "env": {
                "main": {
                    "Label": "@@SERVICE_LABEL@@",
                    "Endpoint": "https://@@$LOG_HOST@@:9443/@@$LOG_PATH@@",
                    "Shell": "echo $HOME ${PATH}",
                    "Level": "@@$UNUSED_LEVEL@@",
                    "Signing": "@@secret:shop-tokens/signing@@",
                    "Token": "@@$LOG_PATH@@-@@secret:shop-tokens/signing@@",
                },
            },
            "mounts": {"main": {"/etc/shop/app.conf": "app.conf"}},
            "files": {
                "app.conf": "host=@@$LOG_HOST@@\nuser=@@DB_USER@@\n"
                "token=@@secret:shop-tokens/signing@@\nshell=$HOME ${PATH}\n"
            },
        }
    }


DEV = """\
LOG_ENDPOINT: https://logs.example:9443
overrides:
  shop:
    ENVIRONMENT:
      main:
        Level: '@@$APP_LOG_LEVEL@@'
"""

VALUES = {
    "SERVICE_LABEL": "blue",
    "LOG_HOST": "logs.example",
    "LOG_PATH": "v1",
    "APP_LOG_LEVEL": "Information",
}


def secret_data(path, name):
    return {
        key: base64.b64decode(value).decode()
        for key, value in documents(path)[("Secret", name)]["data"].items()
    }


class DevTests(ProductFixture):
    """dev: settings, ENVIRONMENT, overrides, manifests and MOUNTS from the shell."""

    def setUp(self):
        super().setUp()
        self.write_product(shop())
        (self.source / "config").mkdir(exist_ok=True)
        (self.source / "config/dev.yaml").write_text(DEV)

    def test_every_place_renders_the_exported_values(self):
        with environ(**VALUES):
            deploy.prepare()
        install = common.BUILD / "install.yaml"
        self.assertEqual(
            config_maps(install)["shop-main-env"],
            {
                "Label": "blue",
                "Endpoint": "https://logs.example:9443/v1",
                "Shell": "echo $HOME ${PATH}",
                "Level": "Information",
            },
        )
        rendered = documents(install)
        self.assertEqual(
            rendered[("ConfigMap", "shop-page")]["data"],
            {
                "endpoint": "https://logs.example:9443/blue",
                "whole": "logs.example",
                "shell": "echo $HOME ${PATH}",
            },
        )
        env = rendered[("Pod", "shop-web")]["spec"]["containers"][0]["env"]
        self.assertEqual(
            env,
            [
                {"name": "POD_LABEL", "value": "blue"},
                {"name": "POD_HOST", "value": "logs.example"},
            ],
        )
        signing = (common.BUILD / "dev/shop/credentials/tokens/signing").read_text()
        self.assertEqual(
            secret_data(install, "shop-main-env-secret"),
            {"Signing": signing, "Token": "v1-" + signing},
        )
        self.assertEqual(
            secret_data(install, mounts.secret_name("shop", "main")),
            {
                "app.conf": f"host=logs.example\nuser=shop\ntoken={signing}\n"
                "shell=$HOME ${PATH}\n"
            },
        )

    def test_a_missing_variable_stops_before_any_output(self):
        for missing, place in (
            ("SERVICE_LABEL", "SERVICE_LABEL in "),
            ("LOG_HOST", ""),
            ("LOG_PATH", "ENVIRONMENT.main: Endpoint"),
            ("APP_LOG_LEVEL", "overrides.shop.ENVIRONMENT.main: Level"),
        ):
            values = dict(VALUES, SERVICE_LABEL=MARKER)
            del values[missing]
            with self.subTest(missing), environ(**values):
                with self.assertRaises(common.DeployError) as raised:
                    deploy.prepare()
                message = str(raised.exception)
                self.assertIn(f"environment variable {missing} is not set", message)
                self.assertIn(place, message)
                self.assertNotIn(MARKER, message)
                self.assertFalse((common.BUILD / "install.yaml").exists())

    def test_an_empty_variable_is_empty_text_and_its_place_decides(self):
        with environ(**dict(VALUES, LOG_PATH="")):
            deploy.prepare()
        self.assertEqual(
            config_maps(common.BUILD / "install.yaml")["shop-main-env"]["Endpoint"],
            "https://logs.example:9443/",
        )
        # A secret line's inserted text is checked as before: no leading space.
        with environ(**dict(VALUES, LOG_PATH=" " + MARKER)):
            with self.assertRaises(common.DeployError) as raised:
                deploy.prepare()
        self.assertIn("unsafe substituted text from $LOG_PATH", str(raised.exception))
        self.assertNotIn(MARKER, str(raised.exception))


class BundleTests(ProductFixture):
    """Images resolve when the bundle is built; everything else on the target."""

    def setUp(self):
        super().setUp()
        product = shop()
        product["shop"]["manifests"][0]["spec"]["containers"][0]["image"] = (
            "@@$REGISTRY@@/shop:1"
        )
        self.write_product(product)

    def test_build_host_and_target_host_values_stay_apart(self):
        with environ(REGISTRY="localhost", **dict(VALUES, SERVICE_LABEL="build")):
            release = self.build_and_unpack()["shop"]
        shutil.rmtree(self.source)
        manifest = yaml.safe_load_all(
            (release / "components/shop/manifests/10-resources.yaml").read_text()
        )
        shipped = {doc["kind"]: doc for doc in manifest}
        self.assertEqual(
            shipped["Pod"]["spec"]["containers"][0]["image"], "localhost/shop:1"
        )
        self.assertEqual(shipped["ConfigMap"]["data"]["whole"], "@@$LOG_HOST@@")
        defaults = yaml.safe_load(
            (release / "components/shop/config.defaults.yaml").read_text()
        )
        self.assertEqual(defaults["SERVICE_LABEL"], "@@$SERVICE_LABEL@@")
        self.assertEqual(
            defaults["ENVIRONMENT"]["main"]["Endpoint"],
            "https://@@$LOG_HOST@@:9443/@@$LOG_PATH@@",
        )
        # The target has its own values and no REGISTRY at all.
        target = dict(
            VALUES,
            SERVICE_LABEL="target",
            LOG_HOST="logs.target",
            UNUSED_LEVEL="Warning",
            UNUSED_DEFAULT="unused.target",
        )
        with environ(**target), self.environment():
            self.install(release)
        config = yaml.safe_load((common.STATE / "shop/config.yaml").read_text())
        # init-config keeps the references: nothing exported is frozen.
        self.assertEqual(config["SERVICE_LABEL"], "@@$SERVICE_LABEL@@")
        installed = common.QUADLET_DIR / "myproduct-shop.yaml"
        self.assertEqual(config_maps(installed)["shop-main-env"]["Label"], "target")
        self.assertEqual(
            config_maps(installed)["shop-main-env"]["Endpoint"],
            "https://logs.target:9443/v1",
        )
        self.assertNotIn("build", installed.read_text())

    def test_a_missing_build_variable_stops_the_build(self):
        with environ(**VALUES), self.assertRaisesRegex(
            bundle.BundleError, "environment variable REGISTRY is not set"
        ):
            self.build_and_unpack()


class InitConfigTests(ProductFixture):
    """init-config validates resolved values and writes the references."""

    def setUp(self):
        super().setUp()
        self.write_product(shop())
        self.release = self.build_and_unpack()["shop"]
        shutil.rmtree(self.source)

    def test_references_are_written_and_validated_resolved(self):
        with environ(**dict(VALUES, UNUSED_LEVEL="x", UNUSED_DEFAULT="y")):
            with self.environment():
                self.use_root(self.release)
                with contextlib.redirect_stdout(io.StringIO()):
                    deploy.init_config("shop")
        written = yaml.safe_load((common.STATE / "shop/config.yaml").read_text())
        self.assertEqual(written["SERVICE_LABEL"], "@@$SERVICE_LABEL@@")
        self.assertEqual(written["LOG_ENDPOINT"], "https://@@$UNUSED_DEFAULT@@:9443")

    def test_a_missing_variable_writes_no_config(self):
        with environ(), self.environment():
            self.use_root(self.release)
            with self.assertRaisesRegex(
                common.DeployError, "environment variable SERVICE_LABEL is not set"
            ):
                deploy.init_config("shop")
        self.assertFalse((common.STATE / "shop/config.yaml").exists())


class SettingsTests(ProductFixture):
    """The operator's config.yaml and the gateway's public settings."""

    def test_an_overridden_default_needs_no_variable(self):
        self.write_product(shop())
        (self.source / "config").mkdir(exist_ok=True)
        (self.source / "config/dev.yaml").write_text(DEV)
        with environ(**VALUES):
            _, settings, _ = deploy.dev_settings()
        self.assertEqual(settings["shop"]["LOG_ENDPOINT"], "https://logs.example:9443")
        self.assertEqual(settings["shop"]["SERVICE_LABEL"], "blue")

    def test_db_settings_are_checked_after_resolution(self):
        with environ(PORT="5432", BAD="54x"):
            self.assertEqual(
                rendering.resolve_settings({"DB_PORT": "@@$PORT@@"}, "config.yaml"),
                {"DB_PORT": "5432"},
            )
            with self.assertRaisesRegex(common.DeployError, "DB_PORT in config.yaml"):
                rendering.resolve_settings({"DB_PORT": "@@$BAD@@"}, "config.yaml")
        # The declarations keep their text: SECRET_FILES is no setting.
        files = {"shop-tokens": [{"path": "credentials/@@$X@@"}]}
        with environ():
            self.assertEqual(
                rendering.resolve_settings({common.SECRET_FILES: files}, "c")[
                    common.SECRET_FILES
                ],
                files,
            )

    def test_the_gateway_and_its_dependents_share_one_origin(self):
        product = {
            "gateway": {
                "role": "gateway",
                "defaults": {
                    "PUBLIC_ORIGIN": "https://@@$HOSTNAME@@:9443",
                    "HTTPS_PORT": 9443,
                },
                "manifests": [
                    pod(
                        "gateway-proxy",
                        "localhost/gateway:1",
                        ["pvc:gateway-routes"],
                        {"ORIGIN": "@@PUBLIC_ORIGIN@@"},
                        hostname="@@PUBLIC_HOSTNAME@@",
                    )
                ],
            },
            "orders": {
                "manifests": [
                    pod(
                        "orders-server",
                        "localhost/orders:1",
                        env={"ORIGIN": "@@PUBLIC_ORIGIN@@"},
                    )
                ]
            },
        }
        self.write_product(copy.deepcopy(product))
        with environ(HOSTNAME="dev.example"):
            _, settings, _ = deploy.dev_settings()
            deploy.prepare()
        self.assertEqual(
            settings["gateway"]["PUBLIC_ORIGIN"], "https://dev.example:9443"
        )
        rendered = documents(common.BUILD / "install.yaml")
        self.assertEqual(
            rendered[("Pod", "gateway-proxy")]["spec"]["hostname"], "dev.example"
        )
        self.assertEqual(
            rendered[("Pod", "orders-server")]["spec"]["containers"][0]["env"],
            [{"name": "ORIGIN", "value": "https://dev.example:9443"}],
        )
        # On the target: the gateway's own config.yaml keeps its reference.
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        with environ(HOSTNAME="prod.example"), self.environment():
            for name in ("gateway", "orders"):
                self.install(releases[name])
        written = yaml.safe_load((common.STATE / "gateway/config.yaml").read_text())
        self.assertEqual(written["PUBLIC_ORIGIN"], "https://@@$HOSTNAME@@:9443")
        with environ(HOSTNAME="prod.example"):
            self.assertEqual(
                catalog.gateway_settings("gateway")["PUBLIC_ORIGIN"],
                "https://prod.example:9443",
            )
        orders = documents(common.QUADLET_DIR / "myproduct-orders.yaml")
        self.assertEqual(
            orders[("Pod", "orders-server")]["spec"]["containers"][0]["env"],
            [{"name": "ORIGIN", "value": "https://prod.example:9443"}],
        )


class SameVersionTests(TargetEffectTests):
    """An unchanged reference with another exported value is another effect."""

    def file(self):
        document = yaml.safe_load(environment_file(["accounts", "ledger"]))
        document["overrides"] = {
            "ledger": {
                "ENVIRONMENT": {
                    "main": {"Logging__LogLevel__Default": "@@$APP_LOG_LEVEL@@"}
                }
            }
        }
        return yaml.safe_dump(document)

    def level(self):
        installed = common.QUADLET_DIR / "myproduct-ledger.yaml"
        return config_maps(installed)["ledger-main-env"]["Logging__LogLevel__Default"]

    def test_a_changed_value_installs_again_and_an_unchanged_one_does_not(self):
        self.place_environment("prod1", self.file())
        with environ(APP_LOG_LEVEL="Information"):
            self.assertEqual(self.run_runtime("prod1"), ["accounts", "ledger"])
            self.assertEqual(self.level(), "Information")
            self.assertEqual(self.run_runtime("prod1"), [])
        with environ(APP_LOG_LEVEL="Debug"):
            self.assertEqual(self.run_runtime("prod1"), ["ledger"])
            self.assertEqual(self.level(), "Debug")
            self.assertEqual(self.run_runtime("prod1"), [])
        record = json.loads(
            catalog.environment_record_path(common.STATE, "ledger").read_text()
        )
        self.assertEqual(
            record["overrides"],
            {"main": {"Logging__LogLevel__Default": "Debug"}},
        )

    def test_a_missing_value_stops_in_the_checks(self):
        self.place_environment("prod1", self.file())
        with environ(APP_LOG_LEVEL="Information"):
            self.run_runtime("prod1")
        before = sorted(str(path) for path in common.STATE.rglob("*"))
        with environ(), self.assertRaises(runtime_error()):
            self.run_runtime("prod1")
        self.assertEqual(sorted(str(path) for path in common.STATE.rglob("*")), before)

    def test_option_c_still_protects_a_resolved_override(self):
        self.place_environment("prod1", self.file())
        with environ(APP_LOG_LEVEL="Information"):
            self.run_runtime("prod1")
            self.use_root(self.releases_built["ledger"])
            with self.environment(), self.assertRaisesRegex(
                common.DeployError, "ledger was installed with --environment prod1"
            ):
                deploy.install()


def runtime_error():
    import runtime  # pyright: ignore[reportMissingImports] - tools/ on sys.path

    return runtime.ToolError
