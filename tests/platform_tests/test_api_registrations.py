"""API secrets (backlogs 72 and 77): the API's own declared secret, named on both sides.

A product with none of the demo names: accounts is identity and receives
ApiResources__<n>__ApiSecrets__0__Value from the platform-rendered Secret
accounts-apis; ledger and reports each declare and use their own generated
secret <api>-api-secret/value. Both sides get the raw value; Identity hashes
it itself.
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
import sys
from unittest import mock

import yaml
from deployment import catalog, common, deploy, registrations, validation
from deployment import render as rendering

from helpers.product_fixture import ProductFixture
from helpers.retry_fixture import DRIVER, REAL_RUN


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


def secret(api):
    return f"@@secret:{api}-api-secret/value@@"


def api_component(name):
    """An API backend: it declares its generated secret; ENVIRONMENT hands it over."""
    return {
        "manifests": [api_pod(name + "-server")],
        "defaults": {
            "SECRET_FILES": {
                name + "-api-secret": [
                    {"path": "credentials/api-secret", "generate": ["value"]}
                ]
            }
        },
        "env": {
            "main": {
                "Authentication__ApiName": name,
                "Authentication__ApiSecret": secret(name),
            }
        },
    }


def identity_lines(*apis):
    """accounts' ENVIRONMENT.main: one API resource per API, its secret line last."""
    lines = {}
    for index, api in enumerate(apis):
        lines[f"ApiResources__{index}__Name"] = api
        lines[f"ApiResources__{index}__ApiSecrets__0__Value"] = secret(api)
    return lines


API_PRODUCT = {
    "accounts": {
        "role": "identity",
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
                if secret(name) in str(product.get(name, {}).get("env"))
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
        validated = self.quiet(validation.validate)
        self.assertIn(
            "[OK] API secret ledger-api-secret/value: declared by ledger, delivered "
            "to accounts ApiResources__0__ApiSecrets__0__Value while ledger is "
            "installed",
            validated,
        )
        self.assertIn(
            "[OK] accounts/main: ENVIRONMENT -> 2 settings (ConfigMap "
            "accounts-main-env), 2 API secrets (Secret accounts-apis, each only "
            "while its API is installed)",
            validated,
        )
        self.assertIn(
            "[OK] ledger: API secret -> accounts; requires accounts", validated
        )
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

        def two_containers(product):
            line = "ApiResources__1__ApiSecrets__0__Value"
            environment = product["accounts"]["env"]
            environment["side"] = {line: environment["main"].pop(line)}

        def undeclared(product):
            del product["reports"]["defaults"]
            del product["reports"]["env"]["main"]["Authentication__ApiSecret"]

        for label, change, pattern in (
            (
                "foreign use",
                env("reports", Other=secret("ledger")),
                (
                    "ledger-api-secret is another component's secret; reports may use "
                    "only its own"
                ),
            ),
            (
                "wrong key",
                identity(Other=secret("ledger")),
                "only as the whole value of ApiResources__<n>__ApiSecrets__0__Value",
            ),
            (
                "not the whole value",
                identity(ApiResources__1__ApiSecrets__0__Value="x" + secret("reports")),
                "only as the whole value",
            ),
            (
                "API lines in two containers",
                two_containers,
                "API secret lines must all be in one container",
            ),
            (
                "two lines for one API",
                identity(ApiResources__5__ApiSecrets__0__Value=secret("ledger")),
                "each API needs exactly one line and its own <n>",
            ),
            (
                "own undeclared secret",
                identity(ApiResources__5__ApiSecrets__0__Value=secret("accounts")),
                "SECRET_FILES has no accounts-api-secret",
            ),
            (
                "unlisted API",
                identity(ApiResources__5__ApiSecrets__0__Value=secret("billing")),
                "no listed component owns billing-api-secret",
            ),
            ("owner declares it", owner_declares, "platform renders it"),
            (
                "API does not declare the named secret",
                undeclared,
                (
                    "ApiResources__1__ApiSecrets__0__Value names "
                    "reports-api-secret/value; declare SECRET_FILES.reports-api-secret"
                ),
            ),
            (
                "API does not provide the named key",
                identity(
                    ApiResources__1__ApiSecrets__0__Value=(
                        "@@secret:reports-api-secret/other@@"
                    )
                ),
                "reports-api-secret in .* provides no key 'other'",
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
            {
                "ledger": {"index": 0, "secret": "ledger-api-secret/value"},
                "reports": {"index": 1, "secret": "reports-api-secret/value"},
            },
        )

        with self.subTest("unchanged reinstall leaves the owner alone"):
            self.assertEqual(self.install(releases["ledger"]), ["ledger"])

        with self.subTest("a newer owner keeps the registrations"):
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
            # registration that resource is simply inactive. The source accounts
            # no longer names reports' secret, so reports 1.2.0 is no API; it
            # still uses its own secret itself.
            plain = self.product()
            plain["accounts"]["env"]["main"] = identity_lines("ledger")
            shutil.rmtree(self.source)
            self.write_product(plain, version="1.2.0")
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
            "install the accounts release that lists reports first",
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

    def install_in_new_process(self, release, secret):
        """deploy.install() of release in a new interpreter (retry_driver.py).

        The driver runs the release's own deployment/ code against this home;
        it substitutes the paths, identity and layout checks, health checks
        and host commands. Returns the recorded commands. A failure message
        is fixed text: the child's output and events can hold the secret.
        """
        record = self.root / "new-process.json"
        result = REAL_RUN(
            [sys.executable, "-B", str(DRIVER)],
            input=json.dumps(
                {
                    "root": str(release),
                    "home": str(common.STATE),
                    "source": str(release / "deployment/deploy.py"),
                    "record": str(record),
                    "action": "install",
                }
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
            timeout=120,
        )
        evidence = json.loads(record.read_text()) if record.exists() else {}
        events = evidence.get("events", [])
        if any(
            secret in text
            for text in (result.stdout, result.stderr, json.dumps(events))
        ):
            self.fail("the new process showed the secret value (output withheld)")
        if result.returncode:
            errors = [event[1] for event in events if event[:1] == ["error"]]
            self.fail(
                f"the new process exited {result.returncode} after "
                f"{len(events)} recorded events; errors: {errors or 'none'}"
            )
        self.assertNotEqual(evidence["pid"], os.getpid())
        return events

    def test_new_process_diagnostics_never_show_the_secret(self):
        """A failing or leaking child is reported with fixed text only."""
        driver = self.root / "leaking-driver.py"
        driver.write_text(
            "import json, os, sys\n"
            "parameters = json.loads(sys.stdin.read())\n"
            "mode = os.environ['LEAK']\n"
            "events = [['podman', 'load', 'PRIVATE-VALUE' if mode == 'event' else 'x']]\n"
            "if mode == 'failure':\n"
            "    events.append(['error', 'OSError', 'PRIVATE-VALUE'])\n"
            "with open(parameters['record'], 'w') as record:\n"
            "    json.dump({'pid': os.getpid(), 'events': events}, record)\n"
            "stream = sys.stderr if mode in ('stderr', 'failure') else sys.stdout\n"
            "stream.write('PRIVATE-VALUE\\n' if mode != 'event' else 'ok\\n')\n"
            "sys.exit(1 if mode == 'failure' else 0)\n"
        )

        def failure(mode, secret="PRIVATE-VALUE"):
            """The failure message install_in_new_process gives for one mode."""
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch(__name__ + ".DRIVER", driver))
                stack.enter_context(mock.patch.dict(os.environ, {"LEAK": mode}))
                failed = stack.enter_context(self.assertRaises(self.failureException))
                self.install_in_new_process(self.root, secret=secret)
            return str(failed.exception)

        for mode in ("stdout", "stderr", "event"):
            with self.subTest(mode):
                self.assertEqual(
                    failure(mode),
                    "the new process showed the secret value (output withheld)",
                )
        message = failure("failure", secret="OTHER-VALUE")
        self.assertEqual(
            message,
            "the new process exited 1 after 2 recorded events; errors: ['OSError']",
        )
        self.assertNotIn("PRIVATE-VALUE", message)

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
        # A new Python process runs the same unpacked bundle's own code against
        # the same home: it reads what remains (the pending record, the old
        # owner YAML) from disk, not from this process's memory.
        events = self.install_in_new_process(releases["ledger"], secret="rotated")
        self.assertEqual(
            [
                args[-1]
                for args in events
                if args[:3] == ["systemctl", "--user", "restart"]
            ],
            ["myproduct-ledger.service", "myproduct-accounts.service"],
        )
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

    def test_first_install_interrupted_before_the_value_is_retried(self):
        """A registration directory without value (power loss) does not block retry."""
        self.write_product(self.product())
        releases = self.build_and_unpack()
        self.install(releases["accounts"])
        write_private = rendering.write_private

        def power_loss(path, text):
            if path == common.STATE / "apis/ledger/value":
                raise OSError("injected power loss before the value")
            return write_private(path, text)

        with mock.patch.object(rendering, "write_private", side_effect=power_loss):
            with self.assertRaises(OSError):
                self.install(releases["ledger"])
        self.assertEqual(list((common.STATE / "apis/ledger").iterdir()), [])
        self.assertTrue((common.STATE / "pending-operation.json").exists())
        self.process.reset_mock()
        self.quiet(deploy.install)  # The same bundle again finishes the install.
        self.assertEqual(
            self.owner_secret()["ApiResources__0__ApiSecrets__0__Value"],
            self.value("ledger"),
        )
        self.assertFalse((common.STATE / "pending-operation.json").exists())
        # Another component's incomplete registration is still refused.
        self.install(releases["reports"])
        (common.STATE / "apis/reports/value").unlink()
        with self.assertRaisesRegex(common.DeployError, "Invalid API registration"):
            self.install(releases["ledger"])

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
