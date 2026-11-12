"""@@@@ is a literal @@ in every template, read once (backlog 87).

Expected outputs are written out here. Each test that checks an escaped
output also shows that reading that output again as a template would change
it, so a second pass (or no escape at all) fails the test.
"""

import base64
import contextlib
import io
import shutil
from unittest import mock

import yaml
from deployment import common, deploy, mounts, templates
from deployment import render as rendering

from helpers.product_fixture import ProductFixture, pod
from platform_tests.test_environment_overrides import config_maps, documents

MARKER = "marker-must-not-leak"


def environ(**values):
    return mock.patch.object(common, "ENVIRON", dict(values))


def no_lookup(group, field):
    raise AssertionError(f"looked up {group}/{field}")


def settings(**values):
    """A resolve for templates.substitute: settings only, by name."""

    def resolve(group, field):
        if group is not None:
            raise AssertionError("read a secret")
        return str(values[field])

    return resolve


def reread(test, output, resolve):
    """Reading output again as a template would fail or change it."""
    try:
        again = templates.substitute(output, resolve, "again")
    except common.DeployError:
        return
    test.assertNotEqual(again, output)


class ParserTests(ProductFixture):
    """templates.substitute: one left-to-right pass over the source text."""

    def test_a_literal_at_the_start_middle_and_end(self):
        for text, expected in (
            ("@@@@x", "@@x"),
            ("a@@@@b", "a@@b"),
            ("x@@@@", "x@@"),
            ("@@@@", "@@"),
        ):
            with self.subTest(text):
                self.assertEqual(templates.substitute(text, no_lookup, "t"), expected)

    def test_the_decided_examples_look_nothing_up(self):
        with environ():
            for text, expected in (
                ("SELECT @@@@VERSION;", "SELECT @@VERSION;"),
                ("@@@@NAME@@@@", "@@NAME@@"),
                ("@@@@$HOSTNAME@@@@", "@@$HOSTNAME@@"),
                ("@@@@secret:db/password@@@@", "@@secret:db/password@@"),
            ):
                with self.subTest(text):
                    self.assertEqual(
                        templates.substitute(text, no_lookup, "t"), expected
                    )
                    # No placeholder in the source: no dependency, no secret.
                    self.assertEqual(templates.tokens(text, "t"), [])
                    self.assertEqual(templates.environment_text(text, "t"), text)

    def test_escapes_and_placeholders_together(self):
        text = "Literal @@@@NAME@@@@; configured value @@NAME@@"
        output = templates.substitute(text, settings(NAME="example"), "t")
        self.assertEqual(output, "Literal @@NAME@@; configured value example")
        # Read again, the literal would be filled in: the one pass matters.
        reread(self, output, settings(NAME="example"))

    def test_runs_of_at_signs_are_read_left_to_right(self):
        resolve = settings(NAME="example")
        for text, expected in (
            ("@@@@", "@@"),
            ("@@@@@@@@", "@@@@"),
            ("@@@@@@NAME@@", "@@example"),
            ("@@NAME@@@@@@", "example@@"),
            ("@@NAME@@@@NAME@@", "exampleexample"),  # two placeholders
            ("@@@@@@", None),  # an escape and a stray @@
            ("@@@@@@@@@@", None),  # two escapes and a stray @@
            ("@@NAME@@@@@@NAME@@", None),  # placeholder, escape, stray @@
            ("@@NAME@@@@@@@@NAME@@", "example@@example"),
        ):
            with self.subTest(text):
                if expected is None:
                    with self.assertRaisesRegex(
                        common.DeployError, "t: malformed placeholder"
                    ):
                        templates.substitute(text, resolve, "t")
                else:
                    self.assertEqual(templates.substitute(text, resolve, "t"), expected)

    def test_malformed_and_unknown_placeholders_still_fail(self):
        for text, message in (
            ("@@NAME", "malformed placeholder"),
            ("@@@", "malformed placeholder"),
            ("a@@b", "malformed placeholder"),
            ("@@lower@@", "unknown or nested placeholder"),
            ("@@@@x@@lower@@", "unknown or nested placeholder"),
        ):
            with self.subTest(text):
                with self.assertRaisesRegex(common.DeployError, message):
                    templates.substitute(text, settings(), "t")

    def test_an_inserted_value_is_never_template_text(self):
        for value in ("@@OTHER@@", "a@@@@b", MARKER + "@@"):
            with self.subTest(value):
                with self.assertRaises(common.DeployError) as raised:
                    templates.substitute("x=@@NAME@@", settings(NAME=value), "t")
                self.assertIn("unresolved placeholder marker", str(raised.exception))
                self.assertNotIn(MARKER, str(raised.exception))

    def test_typed_whole_values_and_escapes_in_manifest_values(self):
        config = {"HTTPS_PORT": 8443, "NAME": "example"}
        self.assertEqual(
            rendering.replace({"port": "@@HTTPS_PORT@@"}, config), {"port": 8443}
        )
        self.assertEqual(
            rendering.replace(
                {"a": "@@@@HTTPS_PORT@@@@", "b": ["SELECT @@@@VERSION;"]}, config
            ),
            {"a": "@@HTTPS_PORT@@", "b": ["SELECT @@VERSION;"]},
        )
        # An embedded placeholder outside ConfigMap data is still refused.
        for value in ("x-@@NAME@@", "@@@@ and @@NAME@@", "stray @@"):
            with self.subTest(value):
                with self.assertRaisesRegex(common.DeployError, "Unreplaced @@"):
                    rendering.check_unresolved({"kind": "Pod", "spec": {"v": value}})
        rendering.check_unresolved(
            {
                "kind": "ConfigMap",
                "data": {"k": "x-@@NAME@@"},
                "metadata": {"n": "@@@@"},
            }
        )
        # A setting's inserted @@ is refused in a whole value too.
        with self.assertRaises(common.DeployError) as raised:
            rendering.replace({"v": "@@NAME@@"}, {"NAME": MARKER + "@@"})
        self.assertNotIn(MARKER, str(raised.exception))

    def test_a_setting_is_resolved_once(self):
        with environ(HOST="h.example"):
            self.assertEqual(
                rendering.resolve_settings(
                    {"QUERY": "SELECT @@@@VERSION", "REF": "@@@@$HOST@@@@ @@$HOST@@"},
                    "config.yaml",
                ),
                {"QUERY": "SELECT @@VERSION", "REF": "@@$HOST@@ h.example"},
            )
            with self.assertRaisesRegex(
                common.DeployError, "a setting may use only @@\\$NAME@@"
            ):
                rendering.resolve_settings({"Q": "@@OTHER@@"}, "config.yaml")

    def test_quadlet_templates_read_the_escape_once(self):
        template = self.root / "quadlet-test" / "template.kube"
        template.parent.mkdir()
        template.write_text("[Kube]\nYaml=@@UNIT_NAME@@.yaml\n# @@@@UNIT_NAME@@@@\n")
        with mock.patch.object(common, "QUADLET_TEMPLATE", template):
            text = deploy.quadlet_text(".kube", "myproduct", "myproduct-web")
        self.assertEqual(text, "[Kube]\nYaml=myproduct-web.yaml\n# @@UNIT_NAME@@\n")


SQL = (
    "SELECT @@@@VERSION;\n"
    "CREATE USER @@DB_USER@@;\n"
    "-- literal @@@@DB_USER@@@@ and @@@@secret:shop-tokens/signing@@@@\n"
)
SQL_RENDERED = (
    "SELECT @@VERSION;\n"
    "CREATE USER shop;\n"
    "-- literal @@DB_USER@@ and @@secret:shop-tokens/signing@@\n"
)


def shop():
    web = pod(
        "shop-web",
        "localhost/shop:1",
        env={"POD_QUERY": "SELECT @@@@VERSION", "POD_USER": "@@DB_USER@@"},
    )
    web["spec"]["containers"][0]["volumeMounts"] = []
    page = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "shop-page"},
        "data": {
            "query": "SELECT @@@@VERSION; -- @@DB_USER@@",
            "literal": "@@@@DB_USER@@@@",
        },
    }
    return {
        "shop": {
            "defaults": {
                "DB_USER": "shop",
                "SECRET_FILES": {
                    "shop-tokens": [
                        {"path": "credentials/tokens", "generate": ["signing"]}
                    ],
                    "shop-raw": [{"path": "credentials/raw"}],
                },
            },
            "manifests": [web, page],
            "env": {
                "main": {
                    "Query": "SELECT @@@@VERSION",
                    "User": "@@@@DB_USER@@@@ is @@DB_USER@@",
                    "Escaped": "@@@@secret:shop-tokens/signing@@@@",
                    "Signing": "@@@@x @@secret:shop-tokens/signing@@",
                }
            },
            "mounts": {
                "main": {
                    "/docker-entrypoint-initdb.d/init.sql": "init.sql",
                    "/etc/raw/key": "@@secret:shop-raw/key@@",
                }
            },
            "files": {"init.sql": SQL},
        }
    }


DEV = """\
overrides:
  shop:
    ENVIRONMENT:
      main:
        Override: '@@@@$HOSTNAME@@@@'
"""
RAW = b"raw @@@@ bytes @@DB_USER@@\n"


def secret_data(path, name):
    return {
        key: base64.b64decode(value)
        for key, value in documents(path)[("Secret", name)]["data"].items()
    }


class RenderingTests(ProductFixture):
    """Every rendering place in dev, and a credential file left as it is."""

    def setUp(self):
        super().setUp()
        self.write_product(shop())
        (self.source / "config").mkdir(exist_ok=True)
        (self.source / "config/dev.yaml").write_text(DEV)

    def prepare(self):
        raw = common.BUILD / "dev/shop/credentials/raw/key"
        raw.parent.mkdir(parents=True, mode=0o700)
        raw.write_bytes(RAW)
        with environ():  # No variable: an escaped @@$HOSTNAME@@ needs none.
            deploy.prepare()
        return common.BUILD / "install.yaml"

    def test_each_place_writes_the_literal_once(self):
        install = self.prepare()
        self.assertEqual(
            config_maps(install)["shop-main-env"],
            {
                "Query": "SELECT @@VERSION",
                "User": "@@DB_USER@@ is shop",
                "Escaped": "@@secret:shop-tokens/signing@@",
                "Override": "@@$HOSTNAME@@",
            },
        )
        signing = (common.BUILD / "dev/shop/credentials/tokens/signing").read_bytes()
        self.assertEqual(
            secret_data(install, "shop-main-env-secret"),
            {"Signing": b"@@x " + signing},
        )
        rendered = documents(install)
        self.assertEqual(
            rendered[("ConfigMap", "shop-page")]["data"],
            {"query": "SELECT @@VERSION; -- shop", "literal": "@@DB_USER@@"},
        )
        self.assertEqual(
            rendered[("Pod", "shop-web")]["spec"]["containers"][0]["env"],
            [
                {"name": "POD_QUERY", "value": "SELECT @@VERSION"},
                {"name": "POD_USER", "value": "shop"},
            ],
        )
        # The SQL file rendered through MOUNTS, and the credential file
        # mounted from its Secret unchanged, @@@@ and placeholder included.
        files = secret_data(install, mounts.secret_name("shop", "main"))
        self.assertEqual(files, {"init.sql": SQL_RENDERED.encode()})
        self.assertEqual(secret_data(install, "shop-raw"), {"key": RAW})
        # Read again, the literal text would fail or change: no second pass.
        reread(self, SQL_RENDERED, settings(DB_USER="shop"))

    def test_an_unescaped_stray_at_pair_still_fails(self):
        product = shop()
        product["shop"]["files"]["init.sql"] = "SELECT @@VERSION;\n"
        self.write_product(product)
        with self.assertRaisesRegex(
            common.DeployError, "init.sql: malformed placeholder"
        ):
            self.prepare()


class BundleTests(ProductFixture):
    """The escape survives packaging and is applied once on the target."""

    def test_an_isolated_bundle_ships_the_source_and_renders_it_once(self):
        self.write_product(shop())
        release = self.build_and_unpack()["shop"]
        shutil.rmtree(self.source)
        shipped = (release / "components/shop/files/init.sql").read_text()
        self.assertEqual(shipped, SQL)
        manifest = (release / "components/shop/manifests/10-resources.yaml").read_text()
        self.assertIn("SELECT @@@@VERSION; -- @@DB_USER@@", manifest)
        defaults = yaml.safe_load(
            (release / "components/shop/config.defaults.yaml").read_text()
        )
        self.assertEqual(defaults["ENVIRONMENT"]["main"]["Query"], "SELECT @@@@VERSION")
        raw = common.STATE / "shop/credentials/raw/key"

        def configure(directory):
            raw.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            raw.write_bytes(RAW)

        with environ(), self.environment():
            self.install(release, configure)
        installed = common.QUADLET_DIR / "myproduct-shop.yaml"
        self.assertEqual(
            config_maps(installed)["shop-main-env"]["Query"], "SELECT @@VERSION"
        )
        self.assertEqual(
            secret_data(installed, mounts.secret_name("shop", "main")),
            {"init.sql": SQL_RENDERED.encode()},
        )
        self.assertEqual(secret_data(installed, "shop-raw"), {"key": RAW})
        # The operator's config keeps what the release declared.
        config = yaml.safe_load((common.STATE / "shop/config.yaml").read_text())
        self.assertEqual(config["DB_USER"], "shop")

    def test_messages_show_no_secret_or_variable_value(self):
        product = shop()
        product["shop"]["env"]["main"]["Bad"] = "@@@@ @@$LEVEL@@"
        self.write_product(product)
        (self.source / "config").mkdir(exist_ok=True)
        for value in (" " + MARKER, MARKER + "@@"):
            with self.subTest(value), environ(LEVEL=value):
                with self.assertRaises(common.DeployError) as raised:
                    with contextlib.redirect_stdout(io.StringIO()):
                        deploy.prepare()
                self.assertNotIn(MARKER, str(raised.exception))
