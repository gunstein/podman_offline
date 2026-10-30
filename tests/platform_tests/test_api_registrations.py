"""API secrets (backlogs 72 and 77): @@api-secret:<api>@@ on both sides.

A product with none of the demo names: accounts is identity and receives
ApiResources__<n>__ApiSecrets__0__Value from the platform-rendered Secret
accounts-apis; ledger and reports each use their own generated secret. Both
sides get the raw value; Identity hashes it itself.
"""

import base64
import builtins
import contextlib
import copy
import io
import json
import os
import shutil
import subprocess
from unittest import mock

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


def api_component(name):
    """An API backend: the platform generates its secret; env/ hands it over."""
    return {
        "catalog": {"requires": ["accounts"]},
        "manifests": [api_pod(name + "-server")],
        "env": {
            "main": {
                "Authentication__ApiName": name,
                "Authentication__ApiSecret": "@@api-secret:" + name + "@@",
            }
        },
    }


def identity_lines(*apis):
    """accounts' env/main.yaml: one API resource per API, its secret line last."""
    lines = {}
    for index, api in enumerate(apis):
        lines[f"ApiResources__{index}__Name"] = api
        lines[f"ApiResources__{index}__ApiSecrets__0__Value"] = f"@@api-secret:{api}@@"
    return lines


API_PRODUCT = {
    "accounts": {
        "role": "identity",
        "catalog": {"upgrade": "newer-only"},
        "manifests": [api_pod("accounts-server")],
        "env": {"main": identity_lines("ledger", "reports")},
    },
    "ledger": api_component("ledger"),
    "reports": api_component("reports"),
}


def decoded(secret):
    return {key: base64.b64decode(value).decode() for key, value in secret.items()}


class ApiRegistrationTests(ProductFixture):
    def product(self, changes=None):
        """API_PRODUCT with changes; identity lines follow the remaining APIs."""
        product = copy.deepcopy(API_PRODUCT)
        for name, spec in (changes or {}).items():
            if spec is None:
                product.pop(name)
            else:
                product[name] = spec
        if "accounts" not in (changes or {}):
            apis = [
                name
                for name in ("ledger", "reports")
                if f"@@api-secret:{name}@@" in str(product.get(name, {}).get("env"))
            ]
            product["accounts"]["env"]["main"] = identity_lines(*apis)
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
        ledger = (dev / "ledger/credentials/api-secret/value").read_text()
        reports = (dev / "reports/credentials/api-secret/value").read_text()
        secrets = self.secrets(common.BUILD / "install.yaml")
        self.assertEqual(
            secrets["accounts-apis"],
            {
                "ApiResources__0__ApiSecrets__0__Value": ledger,
                "ApiResources__1__ApiSecrets__0__Value": reports,
            },
        )
        self.assertEqual(
            secrets["ledger-main-env-secret"], {"Authentication__ApiSecret": ledger}
        )
        self.assertEqual(
            secrets["reports-main-env-secret"], {"Authentication__ApiSecret": reports}
        )
        # The generated source, the recipe and the owner see one value.
        self.assertEqual(secrets["ledger-api-secret"], {"value": ledger})
        self.assertEqual(secrets["reports-api-secret"], {"value": reports})
        for path in [dev / "apis"] + list((dev / "apis").rglob("*")):
            self.assertEqual(path.stat().st_mode & 0o077, 0, path)
        self.assertEqual(
            sorted(p.name for p in (dev / "apis/ledger").iterdir()), ["value"]
        )
        for value in (ledger, reports):
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
        self.assertFalse((common.BUILD / "dev/apis/reports").exists())

    def test_invalid_declarations_are_refused_before_dev_writes(self):
        def env(name, **values):
            def change(product):
                product[name]["env"]["main"].update(values)

            return change

        def identity(**values):
            def change(product):
                product["accounts"]["env"]["main"] = dict(
                    identity_lines("ledger", "reports"), **values
                )

            return change

        def owner_declares(product):
            product["accounts"]["defaults"] = {
                "SECRET_FILES": {"accounts-apis": [{"path": "x", "generate": ["v"]}]}
            }

        def own_source(product):
            product["reports"]["defaults"] = {
                "SECRET_FILES": {"reports-api-secret": "generate"}
            }

        def no_line(product):
            product["accounts"]["env"]["main"] = identity_lines("ledger")

        for label, change, pattern in (
            (
                "foreign use",
                env("reports", Other="@@api-secret:ledger@@"),
                "a component may use only its own API secret",
            ),
            (
                "missing identity line",
                no_line,
                "uses @@api-secret:reports@@, but identity has no line for it",
            ),
            (
                "wrong key",
                identity(Other="@@api-secret:ledger@@"),
                "only as the whole value of ApiResources__<n>__ApiSecrets__0__Value",
            ),
            (
                "not the whole value",
                identity(
                    ApiResources__1__ApiSecrets__0__Value="x@@api-secret:reports@@"
                ),
                "only as the whole value",
            ),
            (
                "two lines for one API",
                identity(ApiResources__5__ApiSecrets__0__Value="@@api-secret:ledger@@"),
                "each API needs exactly one line and its own <n>",
            ),
            (
                "self reference",
                identity(
                    ApiResources__5__ApiSecrets__0__Value="@@api-secret:accounts@@"
                ),
                "accounts is not a listed component that uses",
            ),
            (
                "unlisted API",
                identity(
                    ApiResources__5__ApiSecrets__0__Value="@@api-secret:billing@@"
                ),
                "billing is not a listed component",
            ),
            ("owner declares it", owner_declares, "platform renders it"),
            (
                "explicit source collides",
                own_source,
                "credentials/api-secret is the API secret the platform generates",
            ),
        ):
            with self.subTest(label):
                if self.source.exists():
                    shutil.rmtree(self.source)
                product = self.product()
                change(product)
                self.write_product(product)
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
        return (common.STATE / name / "credentials/api-secret/value").read_text()

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
                "ApiResources__0__ApiSecrets__0__Value": self.value("ledger"),
                "ApiResources__1__ApiSecrets__0__Value": self.value("reports"),
            },
        )
        registration = common.STATE / "apis/ledger"
        for path in (registration, registration / "value"):
            self.assertEqual(path.stat().st_mode & 0o077, 0, path)
        self.assertEqual((registration / "value").read_text(), self.value("ledger"))
        self.assertEqual(
            catalog.load_installed_metadata(common.STATE)["accounts"]["api_secrets"],
            {"ledger": 0, "reports": 1},
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
            rotated = common.STATE / "ledger/credentials/api-secret/value"
            rotated.write_text("rotated-ledger-secret")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                restarts = self.install(releases["ledger"])
            self.assertEqual(restarts, ["ledger", "accounts"])
            self.assertEqual(
                self.owner_secret()["ApiResources__0__ApiSecrets__0__Value"],
                "rotated-ledger-secret",
            )
            self.assertEqual(
                self.secrets(catalog.component_paths("ledger")[2])[
                    "ledger-main-env-secret"
                ],
                {"Authentication__ApiSecret": "rotated-ledger-secret"},
            )
            self.assertNotIn("rotated-ledger-secret", output.getvalue())

        with self.subTest("a release without the role removes the registration"):
            # The installed accounts 1.1.0 keeps its line for reports; without a
            # registration that resource is simply inactive.
            plain = copy.deepcopy(API_PRODUCT["reports"])
            del plain["env"]["main"]["Authentication__ApiSecret"]
            shutil.rmtree(self.source)
            self.write_product(self.product({"reports": plain}), version="1.2.0")
            # Only reports is new; it requires the installed accounts version.
            (self.source / "components/accounts/VERSION").write_text("1.1.0\n")
            removed = self.build_and_unpack()
            self.assertEqual(self.install(removed["reports"]), ["reports", "accounts"])
            self.assertEqual(
                list(self.owner_secret()), ["ApiResources__0__ApiSecrets__0__Value"]
            )
            self.assertFalse((common.STATE / "apis/reports").exists())

        with self.subTest("uninstalling the API removes its resource"):
            self.use_root(releases["ledger"])
            self.process.reset_mock()
            self.quiet(deploy.uninstall)
            self.assertEqual(self.restarts(), ["accounts"])
            self.assertEqual(self.owner_secret(), {})
            self.assertFalse((common.STATE / "apis/ledger").exists())

    def test_newer_only_api_keeps_the_registration_it_runs_with(self):
        """Same version, not rendered: a changed file must not reach the owner alone."""
        ledger = copy.deepcopy(API_PRODUCT["ledger"])
        ledger["catalog"]["upgrade"] = "newer-only"
        releases, _ = self.install_all(self.product({"ledger": ledger}))
        before = self.owner_secret()
        (common.STATE / "ledger/credentials/api-secret/value").write_text(
            "not-yet-active"
        )
        self.assertEqual(self.install(releases["ledger"]), [])
        self.assertEqual(self.owner_secret(), before)
        self.assertTrue((common.STATE / "apis/ledger/value").is_file())

    def test_api_must_be_in_the_installed_identity_lines(self):
        """An isolated API bundle needs an installed Identity that lists it."""
        self.write_product(self.product({"reports": None}))
        early = self.build_and_unpack()
        self.install(early["accounts"])
        shutil.rmtree(self.source)
        shutil.rmtree(self.releases)
        self.write_product(self.product())
        releases = self.build_and_unpack()
        self.use_root(releases["reports"])
        deploy.init_config("reports")
        before = self.snapshot(common.STATE)
        self.process.reset_mock()
        with self.assertRaisesRegex(
            common.DeployError,
            "the accounts release has no line for it; install the accounts release "
            "that lists reports first",
        ):
            deploy.install()
        self.assertEqual(self.snapshot(common.STATE), before)
        self.process.assert_not_called()

    def test_identity_upgrade_keeps_installed_apis_and_may_move_lines(self):
        self.install_all(self.product())
        with self.subTest("a release that drops an installed API is refused"):
            shutil.rmtree(self.source)
            shutil.rmtree(self.releases)
            self.write_product(self.product({"reports": None}), version="1.1.0")
            dropped = self.build_and_unpack()
            self.use_root(dropped["accounts"])
            before = self.snapshot(common.STATE)
            with self.assertRaisesRegex(
                common.DeployError,
                "no API secret line for installed reports; uninstall reports first",
            ):
                deploy.install()
            self.assertEqual(self.snapshot(common.STATE), before)

        moved = self.product()
        moved["accounts"]["env"]["main"] = identity_lines("reports", "ledger")
        with self.subTest("the same skipped version may not change its lines"):
            shutil.rmtree(self.source)
            shutil.rmtree(self.releases)
            self.write_product(moved)
            same = self.build_and_unpack()
            self.use_root(same["accounts"])
            with self.assertRaisesRegex(common.DeployError, "raise accounts's version"):
                deploy.install()

        with self.subTest("a newer release moves the lines; values follow by API"):
            shutil.rmtree(self.source)
            shutil.rmtree(self.releases)
            self.write_product(moved, version="1.1.0")
            newer = self.build_and_unpack()
            self.assertEqual(self.install(newer["accounts"]), ["accounts"])
            self.assertEqual(
                self.owner_secret(),
                {
                    "ApiResources__0__ApiSecrets__0__Value": self.value("reports"),
                    "ApiResources__1__ApiSecrets__0__Value": self.value("ledger"),
                },
            )

    def fail_on(self, *failing):
        """Make the recorded host command fail once for each listed argv."""
        remaining = [list(argv) for argv in failing]
        recorder = self.process.side_effect

        def host_command(arguments, **kwargs):
            args = list(map(str, arguments))
            if args in remaining:
                remaining.remove(args)
                raise subprocess.CalledProcessError(1, args)
            return recorder(arguments, **kwargs)

        self.process.side_effect = host_command

    def test_interrupted_owner_rewrite_keeps_the_old_yaml_and_retry_finishes(self):
        releases, _ = self.install_all(self.product())
        output = catalog.component_paths("accounts")[2]
        before = output.read_bytes()
        (common.STATE / "ledger/credentials/api-secret/value").write_text("rotated")
        replace = os.replace

        def interrupted(source, target):
            if str(target) == str(output):
                raise OSError("disk full")
            return replace(source, target)

        with mock.patch.object(os, "replace", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.install(releases["ledger"])
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(output.stat().st_mode & 0o077, 0)
        self.assertEqual(sorted(p.name for p in output.parent.glob(".install-*")), [])
        pending = json.loads((common.STATE / "pending-operation.json").read_text())
        self.assertEqual(pending["owners"], ["accounts"])
        # A fresh process with the same bundle finishes the pending install.
        self.process.reset_mock()
        self.quiet(deploy.install)
        self.assertEqual(self.restarts(), ["ledger", "accounts"])
        self.assertEqual(
            self.owner_secret()["ApiResources__0__ApiSecrets__0__Value"],
            "rotated",
        )
        self.assertFalse((common.STATE / "pending-operation.json").exists())

        with self.subTest("a missing registration Secret is added again"):
            documents = [
                doc
                for doc in yaml.safe_load_all(output.read_text())
                if doc["metadata"]["name"] != "accounts-apis"
            ]
            output.write_text(yaml.safe_dump_all(documents))
            (common.STATE / "ledger/credentials/api-secret/value").write_text("again")
            self.install(releases["ledger"])
            self.assertEqual(
                self.owner_secret()["ApiResources__0__ApiSecrets__0__Value"],
                "again",
            )

        with self.subTest("an unreadable owner YAML names a pending-safe recovery"):
            output.write_text("- [unbalanced")
            (common.STATE / "ledger/credentials/api-secret/value").write_text("third")
            with self.assertRaisesRegex(
                common.DeployError,
                r"Restore that file from backup, then run ./deploy.sh install "
                r"from this bundle again",
            ) as raised:
                self.install(releases["ledger"])
            self.assertNotIn("third", str(raised.exception))
            self.assertTrue((common.STATE / "pending-operation.json").exists())

    def test_skipped_newer_only_retry_of_another_version_is_refused(self):
        ledger = copy.deepcopy(API_PRODUCT["ledger"])
        ledger["catalog"]["upgrade"] = "newer-only"
        product = self.product({"ledger": ledger})
        old, _ = self.install_all(product)
        self.write_product(product, version="1.1.0")
        for name in ("accounts", "reports"):
            (self.source / "components" / name / "VERSION").write_text("1.0.0\n")
        new = self.build_and_unpack()
        (common.STATE / "ledger/credentials/api-secret/value").write_text("upgraded")
        self.fail_on(["systemctl", "--user", "restart", "myproduct-accounts.service"])
        with self.assertRaises(subprocess.CalledProcessError):
            self.install(new["ledger"])
        self.assertEqual((common.STATE / "installed/ledger").read_text(), "1.0.0\n")
        # The 1.0.0 bundle would skip rendering and restart only the owner.
        self.use_root(old["ledger"])
        before = self.snapshot(common.STATE)
        self.process.reset_mock()
        with self.assertRaisesRegex(
            common.DeployError, r"Pending install of ledger 1\.1\.0; this 1\.0\.0"
        ):
            deploy.install()
        self.assertEqual(self.snapshot(common.STATE), before)
        self.process.assert_not_called()
        # The attempted release finishes it; both sides hold the new value.
        self.use_root(new["ledger"])
        self.quiet(deploy.install)
        self.assertEqual(self.restarts(), ["ledger", "accounts"])
        self.assertEqual(
            self.owner_secret()["ApiResources__0__ApiSecrets__0__Value"],
            "upgraded",
        )
        self.assertEqual(
            self.secrets(catalog.component_paths("ledger")[2])[
                "ledger-main-env-secret"
            ],
            {"Authentication__ApiSecret": "upgraded"},
        )

    def test_validate_never_opens_or_copies_api_values(self):
        releases, _ = self.install_all(self.product())
        opened = []
        real_open, real_io_open = builtins.open, io.open

        def recording(opener):
            def wrapper(file, *args, **kwargs):
                opened.append(str(file))
                return opener(file, *args, **kwargs)

            return wrapper

        for name in ("accounts", "ledger", "reports"):
            with self.subTest(name):
                self.use_root(releases[name])
                del opened[:]
                with mock.patch.object(
                    builtins, "open", recording(real_open)
                ), mock.patch.object(io, "open", recording(real_io_open)):
                    self.quiet(validation.validate)
                values = [
                    path
                    for path in opened
                    if path.startswith(str(common.STATE)) and path.endswith("/value")
                ]
                self.assertEqual(values, [])

    def test_secret_text_that_consumers_would_see_differently_is_refused(self):
        self.write_product(self.product())
        retained = common.BUILD / "dev/reports/credentials/api-secret/value"
        retained.parent.mkdir(parents=True)
        retained.write_text("retained-secret\n")
        with self.assertRaisesRegex(
            common.DeployError, "without a trailing newline"
        ) as raised:
            self.quiet(deploy.prepare)
        self.assertNotIn("retained-secret", str(raised.exception))
        self.assertFalse((common.BUILD / "install.yaml").exists())
        self.assertFalse((common.BUILD / "dev/apis").exists())

        shutil.rmtree(common.BUILD)
        self.install_all(self.product({"reports": None}))
        # accounts 1.1.0 adds the line for reports; then reports may install.
        shutil.rmtree(self.source)
        shutil.rmtree(self.releases)
        self.write_product(self.product(), version="1.1.0")
        releases = self.build_and_unpack()
        self.install(releases["accounts"])
        self.use_root(releases["reports"])
        deploy.init_config("reports")
        retained = common.STATE / "reports/credentials/api-secret/value"
        retained.parent.mkdir(parents=True)
        retained.write_text("retained-secret\n")
        before = self.snapshot(common.STATE)
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "trailing newline"):
            self.quiet(deploy.install)
        self.assertEqual(self.snapshot(common.STATE), before)
        self.process.assert_not_called()

    def test_registration_records_never_echo_values(self):
        record = self.root / "apis/ledger"
        record.mkdir(parents=True)
        (record / "index").write_text("0")
        (record / "value").write_text("do-not-show")
        with self.assertRaises(common.DeployError) as raised:
            registrations.check_api_registration(record)
        self.assertNotIn("do-not-show", str(raised.exception))
        (record / "index").unlink()
        registrations.check_api_registration(record)
        (record / "value").write_bytes(b"\xff do-not-show")
        with self.assertRaises(common.DeployError) as raised:
            registrations.api_value(record / "value", "ledger")
        self.assertNotIn("do-not-show", str(raised.exception))
