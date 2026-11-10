"""A target environment's components, and environment-neutral deliveries (backlog 85).

Bundles and RPMs are built without an environment; the operator's file
/var/lib/<product>/state/<environment>.yaml selects the components and their
overrides at deployment. Expected names and values are written out here,
never computed with the selection under test.
"""

import contextlib
import copy
import io
import json
import shutil
import sys
from pathlib import Path
from unittest import mock

import bundle
import rpms
import yaml
from deployment import catalog, common, deploy, status

from helpers.product_fixture import RENAMED, ProductFixture

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import runtime  # pyright: ignore[reportMissingImports] - tools/ above


def api_pod(name):
    container = {"name": "main", "image": f"localhost/{name}:1"}
    container["imagePullPolicy"] = "Never"
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": name + "-server"},
        "spec": {"containers": [container]},
    }


def api_component(name):
    """An API backend that declares and uses its own generated secret."""
    return {
        "manifests": [api_pod(name)],
        "defaults": {
            "SECRET_FILES": {
                name + "-api-secret": [
                    {"path": "credentials/api-secret", "generate": ["value"]}
                ]
            }
        },
        "env": {
            "main": {"Authentication__ApiSecret": f"@@secret:{name}-api-secret/value@@"}
        },
    }


# accounts (Identity) has no API registration of its own: ledger and reports
# are optional APIs, registered only by the environments that include them.
PRODUCT = {
    "accounts": {
        "role": "identity",
        "manifests": [api_pod("accounts")],
        "env": {"main": {"Logging__Level": "Information"}},
    },
    "ledger": api_component("ledger"),
    "reports": api_component("reports"),
}


def registration(index, api):
    return {
        f"ApiResources__{index}__Name": api,
        f"ApiResources__{index}__ApiSecrets__0__Value": f"@@secret:{api}-api-secret/value@@",
    }


def environment_file(components, accounts=None):
    document = {"components": components}
    if accounts:
        document["overrides"] = {"accounts": {"ENVIRONMENT": {"main": accounts}}}
    return yaml.safe_dump(document, sort_keys=False)


class TargetSelectionTests(ProductFixture):
    """One set of neutral releases; the target's file decides the product."""

    def setUp(self):
        super().setUp()
        self.write_product(copy.deepcopy(PRODUCT))
        self.releases_built = self.build_and_unpack()
        shutil.rmtree(self.source)

    def quiet(self, action, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return action(*args)

    def test_moving_to_a_smaller_environment_needs_an_explicit_uninstall(self):
        releases = self.releases_built
        self.place_environment(
            "prod1",
            environment_file(
                ["accounts", "ledger", "reports"],
                dict(registration(0, "ledger"), **registration(1, "reports")),
            ),
        )
        with self.environment():
            for name in ("accounts", "ledger", "reports"):
                self.install(releases[name], environment_name="prod1")
            installed = catalog.load_installed_metadata(common.STATE)
            self.assertEqual(
                sorted(installed["accounts"]["api_secrets"]), ["ledger", "reports"]
            )
            # The operator's smaller environment: the same releases, no ledger.
            self.place_environment(
                "prod1",
                environment_file(["accounts", "reports"], registration(0, "reports")),
            )
            self.use_root(releases["accounts"])
            before = sorted(str(path) for path in common.STATE.rglob("*"))
            with self.assertRaisesRegex(
                common.DeployError,
                "This accounts release has no API secret line for installed "
                "ledger; uninstall ledger first",
            ):
                deploy.install("prod1")
            self.assertEqual(
                sorted(str(path) for path in common.STATE.rglob("*")), before
            )
            # ledger is not in the environment: its own install is refused too.
            self.use_root(releases["ledger"])
            with self.assertRaisesRegex(
                common.DeployError, "ledger is not in components:"
            ):
                deploy.install("prod1")
            self.quiet(deploy.uninstall)
            self.install(releases["accounts"], environment_name="prod1")
            installed = catalog.load_installed_metadata(common.STATE)
            self.assertNotIn("ledger", installed)
            self.assertEqual(
                installed["accounts"]["api_secrets"],
                {"reports": {"index": 0, "secret": "reports-api-secret/value"}},
            )
            report = status.collect()
            self.assertEqual(report["uninstalled"], ["ledger"])
            self.assertEqual(runtime.uninstalled(common.STATE), ["ledger"])
            with contextlib.redirect_stdout(io.StringIO()) as shown:
                status.status()
            self.assertIn("Uninstalled: ledger", shown.getvalue())
        # The environment file is the operator's and stays as written.
        self.assertIn("reports", (common.STATE / "prod1.yaml").read_text())


class TargetEffectTests(ProductFixture):
    """The same versions, another file: what changed is installed again."""

    def setUp(self):
        super().setUp()
        self.write_product(copy.deepcopy(PRODUCT))
        self.releases_built = self.build_and_unpack()
        shutil.rmtree(self.source)

    def applied(self, name, environment_name="prod1"):
        """deploy.sh check-environment <environment> --json, as the runtime asks it."""
        self.use_root(self.releases_built[name])
        with contextlib.redirect_stdout(io.StringIO()) as shown:
            deploy.check_environment(environment_name, True)
        answer = json.loads(shown.getvalue().splitlines()[-1])
        self.assertEqual(answer["component"], name)
        return answer["applied"]

    def test_a_changed_override_or_api_role_is_not_yet_applied(self):
        releases = self.releases_built
        self.place_environment("prod1", environment_file(["accounts", "ledger"]))
        with self.environment():
            for name in ("accounts", "ledger"):
                self.install(releases[name], environment_name="prod1")
            self.assertTrue(self.applied("accounts"))
            self.assertTrue(self.applied("ledger"))
            self.assertEqual(
                json.loads(
                    catalog.environment_record_path(common.STATE, "ledger").read_text()
                ),
                {},
            )
            # An override changes: only accounts, which it names, is not applied.
            self.place_environment(
                "prod1",
                environment_file(["accounts", "ledger"], {"Logging__Level": "Debug"}),
            )
            self.assertFalse(self.applied("accounts"))
            self.assertTrue(self.applied("ledger"))
            self.install(releases["accounts"], environment_name="prod1")
            self.assertTrue(self.applied("accounts"))
            output = catalog.component_paths("accounts")[2]
            self.assertIn("Debug", output.read_text())
            # Identity now registers ledger: ledger's role changes only once the
            # new Identity is installed, which the runtime does first.
            self.place_environment(
                "prod1",
                environment_file(
                    ["accounts", "ledger"],
                    dict(registration(0, "ledger"), Logging__Level="Debug"),
                ),
            )
            self.assertFalse(self.applied("accounts"))
            self.assertTrue(self.applied("ledger"))
            self.install(releases["accounts"], environment_name="prod1")
            self.assertFalse(self.applied("ledger"))
            self.install(releases["ledger"], environment_name="prod1")
            self.assertTrue(self.applied("ledger"))
            self.assertEqual(
                catalog.load_installed_metadata(common.STATE)["ledger"]["apis"],
                "accounts",
            )
            # Uninstall removes the record with the marker and metadata.
            self.use_root(releases["ledger"])
            with contextlib.redirect_stdout(io.StringIO()):
                deploy.uninstall()
            self.assertFalse(
                catalog.environment_record_path(common.STATE, "ledger").exists()
            )

    def test_effective_dependencies_and_foreign_secrets_are_refused_first(self):
        releases = self.releases_built
        self.place_environment(
            "prod1",
            environment_file(["accounts", "ledger"], registration(0, "ledger")),
        )
        with self.environment():
            for name in ("accounts", "ledger"):
                self.install(releases[name], environment_name="prod1")
            # ledger alone: the installed accounts makes it an API of accounts.
            self.place_environment("solo", environment_file(["ledger"]))
            # Only Identity may name another component's secret, also in an override.
            foreign = {
                "components": ["accounts", "ledger", "reports"],
                "overrides": {
                    "ledger": {
                        "ENVIRONMENT": {
                            "main": {
                                "ApiResources__0__ApiSecrets__0__Value": (
                                    "@@secret:reports-api-secret/value@@"
                                )
                            }
                        }
                    }
                },
            }
            self.place_environment("foreign", yaml.safe_dump(foreign))
            before = sorted(str(path) for path in common.STATE.rglob("*"))
            self.use_root(releases["ledger"])
            for name, pattern in (
                (
                    "solo",
                    (
                        "ledger requires accounts \\(the installed accounts registers "
                        "ledger as an API\\); add it to components:"
                    ),
                ),
                ("foreign", "reports-api-secret is another component's secret"),
            ):
                with self.subTest(name):
                    with self.assertRaisesRegex(common.DeployError, pattern):
                        deploy.check_environment(name)
                    with self.assertRaisesRegex(common.DeployError, pattern):
                        deploy.install(name)
                    self.assertEqual(
                        sorted(str(path) for path in common.STATE.rglob("*")), before
                    )


class TargetDependencyTests(ProductFixture):
    """A selected component's dependency must be selected and installed."""

    def setUp(self):
        super().setUp()
        self.write_product(copy.deepcopy(RENAMED))
        self.releases_built = self.build_and_unpack()
        shutil.rmtree(self.source)
        self.provide_credentials(RENAMED, common.STATE)

    def test_a_selected_set_installs_and_uninstall_retry_keeps_its_record(self):
        """gateway and manual only: no Identity, no client, nothing else deployed."""
        releases = self.releases_built
        self.place_environment("small", environment_file(["gateway", "manual"]))
        with self.environment():
            for name in ("gateway", "manual"):
                self.install(releases[name], environment_name="small")
        installed = catalog.load_installed_metadata(common.STATE)
        self.assertEqual(sorted(installed), ["gateway", "manual"])
        self.assertEqual(
            sorted(path.name for path in (common.STATE / "routes").iterdir()),
            ["manual.conf"],
        )
        # An uninstall interrupted after the marker is gone keeps the version.
        with self.environment():
            self.use_root(releases["manual"])
            failing = mock.patch.object(
                deploy.registrations, "clear_pending", side_effect=OSError("stop")
            )
            with failing, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(OSError):
                    deploy.uninstall()
            record = catalog.uninstalled_path(common.STATE, "manual")
            with contextlib.redirect_stdout(io.StringIO()):
                deploy.uninstall()
            self.assertEqual(record.read_text(), "1.0.0\n")
            self.install(releases["manual"], environment_name="small")
            self.assertFalse(record.exists())

    def test_a_release_outside_its_environment_or_without_its_file_is_refused(self):
        releases = self.releases_built
        self.place_environment("small", environment_file(["gateway", "manual"]))
        with self.environment():
            self.use_root(releases["orders"])
            for name, pattern in (
                ("small", "orders is not in components:"),
                ("absent", "missing file .*absent.yaml"),
            ):
                with self.subTest(name):
                    with self.assertRaisesRegex(common.DeployError, pattern):
                        deploy.init_config("orders", environment_name=name)
                    self.assertFalse((common.STATE / "orders/config.yaml").exists())


def stub_rpms(fixture):
    """rpmbuild stands in; selection, reuse, files and the delivery are real.

    Returns the list of what the stand-in wrapped, in order.
    """
    fixture.stack.enter_context(
        mock.patch.multiple(rpms, ROOT=fixture.source, DIST=fixture.source / "dist")
    )
    fixture.stack.enter_context(
        mock.patch.object(rpms.shutil, "which", return_value="/usr/bin/rpmbuild")
    )
    wrapped = []

    def build_rpm(archive, product, component, version, target):
        wrapped.append(archive.name)
        rpm = target / f"{product}-{component}-{version}-{version}-1.noarch.rpm"
        rpms.refuse_existing(rpm, component)
        target.mkdir(parents=True, exist_ok=True)
        rpm.write_text(archive.name)
        return rpm

    def build_tools(product, target):
        version = (fixture.source / "tools/VERSION").read_text().strip()
        rpm = target / f"{product}-tools-{version}-1.noarch.rpm"
        rpms.refuse_existing(rpm, "tools")
        target.mkdir(parents=True, exist_ok=True)
        rpm.write_text("tools")
        wrapped.append(rpm.name)
        return rpm

    fixture.stack.enter_context(mock.patch.object(rpms, "build_rpm", build_rpm))
    fixture.stack.enter_context(mock.patch.object(rpms, "build_tools", build_tools))
    return wrapped


class DeliveryTests(ProductFixture):
    """dist/delivery/ holds exactly one run's RPMs; one version has one content."""

    def setUp(self):
        super().setUp()
        self.write_product(copy.deepcopy(PRODUCT))
        self.wrapped = stub_rpms(self)
        self.tools = (
            "myproduct-tools-" + (self.source / "tools/VERSION").read_text().strip()
        )

    def delivered(self):
        return sorted(path.name for path in (bundle.DIST / "delivery").iterdir())

    def test_a_delivery_holds_exactly_its_components(self):
        bundle.build()
        rpms.build()
        self.assertEqual(
            self.delivered(),
            [
                "myproduct-accounts-1.0.0-1.0.0-1.noarch.rpm",
                "myproduct-ledger-1.0.0-1.0.0-1.noarch.rpm",
                "myproduct-reports-1.0.0-1.0.0-1.noarch.rpm",
                self.tools + "-1.noarch.rpm",
            ],
        )
        # A customer without ledger: the same RPMs, reused, without ledger.
        self.wrapped.clear()
        bundle.build()  # A rebuild changes the archive bytes, not the content.
        rpms.build(["accounts", "reports"])
        self.assertEqual(self.wrapped, [])
        self.assertEqual(
            self.delivered(),
            [
                "myproduct-accounts-1.0.0-1.0.0-1.noarch.rpm",
                "myproduct-reports-1.0.0-1.0.0-1.noarch.rpm",
                self.tools + "-1.noarch.rpm",
            ],
        )
        self.assertTrue(
            (bundle.DIST / "rpm/myproduct-ledger-1.0.0-1.0.0-1.noarch.rpm").is_file()
        )
        # A dependency's new version keeps the earlier dependent RPM.
        (self.source / "components/accounts/VERSION").write_text("1.1.0\n")
        bundle.build()
        rpms.build(["accounts", "reports"])
        self.assertIn("myproduct-reports-1.0.0-1.0.0-1.noarch.rpm", self.delivered())

    def test_other_content_under_one_version_is_refused(self):
        bundle.build()
        rpms.build()
        for label, change, refused in (
            (
                "declarations",
                lambda: (
                    self.source / "components/reports/config.defaults.yaml"
                ).write_text(
                    (self.source / "components/reports/config.defaults.yaml")
                    .read_text()
                    .replace("Authentication__ApiSecret", "Auth__Secret")
                ),
                "reports",
            ),
            (
                "same tag, other image",
                lambda: self.image_ids.update({"localhost/ledger:1": "rebuilt"}),
                "ledger",
            ),
        ):
            with self.subTest(label):
                change()
                bundle.build()
                with self.assertRaisesRegex(
                    rpms.RpmError,
                    f"myproduct-{refused}-1.0.0-1.0.0-1.noarch.rpm already exists "
                    f"with other content; one version has one content, so give "
                    f"{refused} a new VERSION",
                ):
                    rpms.build([refused])
                self.assertFalse((bundle.DIST / "delivery").exists())

    def test_the_releases_own_runtime_files_are_its_content(self):
        """deploy.sh's code, scripts and Quadlet policy ship in every release."""
        bundle.build()
        rpms.build()
        for relative, old, new in (
            ("quadlet/template.kube", "Restart=on-failure", "Restart=no"),
            ("deployment/output.py", '"""', '"""Changed. '),
            ("scripts/prepare-host.sh", "\n", "\n# changed\n"),
        ):
            with self.subTest(relative):
                original = (self.source / relative).read_text()
                self.replace_text(relative, old, new, count=1)
                bundle.build()
                with self.assertRaisesRegex(
                    rpms.RpmError,
                    "myproduct-accounts-1.0.0-1.0.0-1.noarch.rpm already exists "
                    "with other content",
                ):
                    rpms.build(["accounts"])
                (self.source / relative).write_text(original)
                bundle.build()
                rpms.build(["accounts"])  # The same content again: reused.

    def replace_text(self, relative, old, new, count=-1):
        path = self.source / relative
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, count))

    def test_tools_changed_without_a_new_version_are_refused(self):
        bundle.build()
        rpms.build()
        runtime_file = self.source / "tools/runtime.py"
        runtime_file.write_text(runtime_file.read_text() + "\n# changed\n")
        with self.assertRaisesRegex(
            rpms.RpmError, "tools-.* already exists with other content"
        ):
            rpms.build(["accounts"])

    def test_a_failed_copy_leaves_no_delivery(self):
        bundle.build()
        copies = []

        def copy(source, target):
            copies.append(target)
            if len(copies) == 2:
                raise OSError("disk full")
            return shutil.copyfile(source, target)

        with mock.patch.object(rpms.shutil, "copy2", copy), self.assertRaises(OSError):
            rpms.build()
        self.assertFalse((bundle.DIST / "delivery").exists())
        self.assertFalse((bundle.DIST / ".delivery-partial").exists())
