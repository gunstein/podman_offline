"""The components of a build environment (backlog 85).

config/<environment>.yaml's components: is the environment's product; its
overrides: keep item 84's meaning for those components. Expected names and
values are written out here, never computed with the selection under test.
"""

import contextlib
import copy
import io
import shutil
import sys
import tarfile
from pathlib import Path
from unittest import mock

import bundle
import rpms
import yaml
from deployment import catalog, common, deploy, status

from helpers.product_fixture import RENAMED, ProductFixture, pod

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
        "env": {"main": {"Logging__Level": "Information", "Features__Export": "false"}},
    },
    "ledger": api_component("ledger"),
    "reports": api_component("reports"),
}


def registration(index, api):
    return {
        f"ApiResources__{index}__Name": api,
        f"ApiResources__{index}__ApiSecrets__0__Value": f"@@secret:{api}-api-secret/value@@",
    }


def environment_file(components=None, **overrides):
    document = {}
    if components is not None:
        document["components"] = components
    if overrides:
        document["overrides"] = {
            name: {"ENVIRONMENT": containers} for name, containers in overrides.items()
        }
    return yaml.safe_dump(document, sort_keys=False)


class SelectionFixture(ProductFixture):
    def setUp(self):
        super().setUp()
        self.write_product(copy.deepcopy(PRODUCT))
        # prod1: every API; prod2: accounts and reports only.
        self.put(
            "config/prod1.yaml",
            environment_file(
                ["accounts", "ledger", "reports"],
                accounts={
                    "main": dict(
                        registration(0, "ledger"), **registration(1, "reports")
                    )
                },
            ),
        )
        self.put(
            "config/prod2.yaml",
            environment_file(
                ["accounts", "reports"],
                accounts={
                    "main": dict(
                        registration(0, "reports"),
                        Logging__Level="Debug",
                        Export__MaxRows="1000",
                    )
                },
            ),
        )

    def put(self, relative, text):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def listed(self, name):
        return (bundle.DIST / name / "current-bundles.txt").read_text().split()

    def member(self, archive, relative):
        with tarfile.open(str(archive)) as tar:
            stream = tar.extractfile(
                archive.name[: -len("-offline.tar.gz")] + "/" + relative
            )
            assert stream is not None
            return stream.read().decode()


class SelectionBuildTests(SelectionFixture):
    def test_two_environments_build_their_own_products(self):
        bundle.build(environment_name="prod1")
        bundle.build(environment_name="prod2")
        self.assertEqual(
            self.listed("prod1"),
            [
                "myproduct-accounts-1.0.0-offline.tar.gz",
                "myproduct-ledger-1.0.0-offline.tar.gz",
                "myproduct-reports-1.0.0-offline.tar.gz",
            ],
        )
        self.assertEqual(
            self.listed("prod2"),
            [
                "myproduct-accounts-1.0.0-offline.tar.gz",
                "myproduct-reports-1.0.0-offline.tar.gz",
            ],
        )
        self.assertFalse(
            (bundle.DIST / "prod2/myproduct-ledger-1.0.0-offline.tar.gz").exists()
        )
        descriptors = {}
        for name in ("prod1", "prod2"):
            archive = bundle.DIST / name / "myproduct-accounts-1.0.0-offline.tar.gz"
            descriptors[name] = yaml.safe_load(self.member(archive, "bundle.yaml"))
        self.assertEqual(
            descriptors["prod1"]["api_secrets"],
            {
                "ledger": {"index": 0, "secret": "ledger-api-secret/value"},
                "reports": {"index": 1, "secret": "reports-api-secret/value"},
            },
        )
        self.assertEqual(
            descriptors["prod2"]["api_secrets"],
            {"reports": {"index": 0, "secret": "reports-api-secret/value"}},
        )
        self.assertEqual(descriptors["prod2"]["accepts"], {"apis": "accounts-apis"})
        # prod2's overrides of the selected accounts: one replaced, one kept,
        # one added, as item 84 merges them.
        archive = bundle.DIST / "prod2/myproduct-accounts-1.0.0-offline.tar.gz"
        bundled = yaml.safe_load(
            self.member(archive, "components/accounts/config.defaults.yaml")
        )["ENVIRONMENT"]["main"]
        self.assertEqual(bundled["Logging__Level"], "Debug")
        self.assertEqual(bundled["Features__Export"], "false")
        self.assertEqual(bundled["Export__MaxRows"], "1000")
        reports = bundle.DIST / "prod2/myproduct-reports-1.0.0-offline.tar.gz"
        self.assertEqual(
            yaml.safe_load(self.member(reports, "bundle.yaml"))["apis"], "accounts"
        )
        self.assertEqual(
            self.member(reports, "images/images.txt"), "localhost/reports:1\n"
        )

    def test_without_components_the_environment_has_the_whole_catalog(self):
        self.put("config/prod3.yaml", environment_file(accounts={"main": {"A": "b"}}))
        bundle.build(environment_name="prod3")
        self.assertEqual(
            self.listed("prod3"),
            [
                "myproduct-accounts-1.0.0-offline.tar.gz",
                "myproduct-ledger-1.0.0-offline.tar.gz",
                "myproduct-reports-1.0.0-offline.tar.gz",
            ],
        )

    def test_a_build_without_an_environment_has_no_optional_api(self):
        """The common declarations name no API secret: no registration, no error."""
        descriptors = catalog.source_descriptors(self.source)
        self.assertEqual(descriptors["accounts"]["api_secrets"], {})
        self.assertEqual(descriptors["accounts"]["accepts"], {})
        self.assertIsNone(descriptors["ledger"]["apis"])
        bundle.build()
        self.assertEqual(
            len((bundle.DIST / "current-bundles.txt").read_text().split()), 3
        )

    def test_invalid_selections_fail_before_any_output(self):
        for label, text, pattern in (
            ("unknown", environment_file(["accounts", "billing"]),
             ("config/prod3.yaml: components: billing is not a component in "
              "bundles.yaml; listed: accounts, ledger, reports")),
            ("duplicate", environment_file(["accounts", "accounts"]),
             "config/prod3.yaml: components: lists accounts twice"),
            ("empty", "components: []\n",
             ("config/prod3.yaml: components: list at least one component, or "
              "omit components for the whole catalog")),
            ("null", "components:\n", "components: list at least one component"),
            ("not a list", "components: accounts\n",
             "components: must be a list of component IDs"),
            ("invalid ID", environment_file(["Accounts"]),
             "config/prod3.yaml: components: 'Accounts' is not a component ID"),
            ("override outside the set",
             environment_file(["accounts", "reports"], ledger={"main": {"A": "b"}}),
             ("config/prod3.yaml: overrides.ledger: ledger is not in components:; "
              "add it there or remove its overrides")),
            ("empty override outside the set",
             "components: [accounts]\noverrides:\n  ledger: {}\n",
             "overrides.ledger: ledger is not in components:"),
            ("Identity names an excluded API",
             environment_file(["accounts", "reports"],
                              accounts={"main": registration(0, "ledger")}),
             "no listed component owns ledger-api-secret"),
        ):  # fmt: skip
            with self.subTest(label):
                self.put("config/prod3.yaml", text)
                with self.assertRaisesRegex(common.DeployError, pattern):
                    bundle.build(environment_name="prod3")
                self.assertFalse(bundle.DIST.exists())
                self.assertFalse(common.BUILD.exists())

    def test_partial_builds_inside_and_outside_the_set(self):
        bundle.build(["reports"], environment_name="prod2")
        self.assertTrue(
            (bundle.DIST / "prod2/myproduct-reports-1.0.0-offline.tar.gz").is_file()
        )
        self.assertFalse((bundle.DIST / "prod2/current-bundles.txt").exists())
        with self.assertRaisesRegex(
            bundle.BundleError,
            r"ledger is not in config/prod2.yaml components:; build it with an "
            "environment that includes it",
        ):
            bundle.build(["ledger"], environment_name="prod2")
        self.assertFalse(
            (bundle.DIST / "prod2/myproduct-ledger-1.0.0-offline.tar.gz").exists()
        )

    def test_excluded_components_are_not_read(self):
        """A broken manifest, an unknown image and no credentials outside the set."""
        manifests = self.source / "components/ledger/manifests"
        (manifests / "10-resources.yaml").write_text("kind: [unclosed\n")
        (manifests / "20-image.yaml").write_text(
            yaml.safe_dump(pod("ledger-other", "@@NO_SUCH_IMAGE@@"))
        )
        bundle.build(environment_name="prod2")
        self.assertEqual(len(self.listed("prod2")), 2)
        with self.assertRaises(
            (common.DeployError, bundle.BundleError, yaml.YAMLError)
        ):
            bundle.build(environment_name="prod1")

    def test_reducing_the_set_lists_only_the_current_bundles(self):
        bundle.build(environment_name="prod1")
        self.put(
            "config/prod1.yaml",
            environment_file(
                ["accounts", "reports"], accounts={"main": registration(0, "reports")}
            ),
        )
        bundle.build(environment_name="prod1")
        # The earlier archive stays (it may still be installed somewhere); the
        # list names only the current product.
        self.assertTrue(
            (bundle.DIST / "prod1/myproduct-ledger-1.0.0-offline.tar.gz").is_file()
        )
        self.assertEqual(
            self.listed("prod1"),
            [
                "myproduct-accounts-1.0.0-offline.tar.gz",
                "myproduct-reports-1.0.0-offline.tar.gz",
            ],
        )


class SelectionRpmTests(SelectionFixture):
    """build-rpms.sh --environment wraps exactly the environment's current bundles."""

    def setUp(self):
        super().setUp()
        self.stack.enter_context(
            mock.patch.multiple(rpms, ROOT=self.source, DIST=self.source / "dist")
        )
        self.stack.enter_context(
            mock.patch.object(rpms.shutil, "which", return_value="/usr/bin/rpmbuild")
        )
        self.wrapped = []

        def build_rpm(archive, product, component, version, target):
            """Stands in for rpmbuild; the selection and the files are real."""
            self.wrapped.append(archive.name)
            rpm = target / f"{product}-{component}-{version}-{version}-1.noarch.rpm"
            rpms.refuse_existing(rpm, component)
            target.mkdir(parents=True, exist_ok=True)
            rpm.write_text(archive.name)
            return rpm

        def build_tools(product, target):
            version = (self.source / "tools/VERSION").read_text().strip()
            rpm = target / f"{product}-tools-{version}-1.noarch.rpm"
            target.mkdir(parents=True, exist_ok=True)
            rpm.write_text("tools")
            return rpm

        self.stack.enter_context(mock.patch.object(rpms, "build_rpm", build_rpm))
        self.stack.enter_context(mock.patch.object(rpms, "build_tools", build_tools))

    def test_a_stale_archive_of_a_larger_set_is_never_wrapped(self):
        bundle.build(environment_name="prod1")
        self.put(
            "config/prod1.yaml",
            environment_file(
                ["accounts", "reports"], accounts={"main": registration(0, "reports")}
            ),
        )
        bundle.build(environment_name="prod1")
        rpms.build(environment_name="prod1")
        self.assertEqual(
            self.wrapped,
            [
                "myproduct-accounts-1.0.0-offline.tar.gz",
                "myproduct-reports-1.0.0-offline.tar.gz",
            ],
        )
        with self.assertRaisesRegex(
            rpms.RpmError, "ledger is not in config/prod1.yaml"
        ):
            rpms.build(["ledger"], environment_name="prod1")

    def test_the_delivery_holds_exactly_the_current_rpms(self):
        """A larger delivery, then a smaller one: the old RPM is never delivered."""
        delivery = bundle.DIST / "prod1/delivery"
        bundle.build(environment_name="prod1")
        rpms.build(environment_name="prod1")
        tools = "myproduct-tools-" + (self.source / "tools/VERSION").read_text().strip()
        self.assertEqual(
            sorted(path.name for path in delivery.iterdir()),
            [
                "myproduct-accounts-1.0.0-1.0.0-1.noarch.rpm",
                "myproduct-ledger-1.0.0-1.0.0-1.noarch.rpm",
                "myproduct-reports-1.0.0-1.0.0-1.noarch.rpm",
                tools + "-1.noarch.rpm",
            ],
        )
        # prod1 drops ledger; accounts gets a new version, reports stays.
        self.put(
            "config/prod1.yaml",
            environment_file(
                ["accounts", "reports"], accounts={"main": registration(0, "reports")}
            ),
        )
        (self.source / "components/accounts/VERSION").write_text("1.1.0\n")
        bundle.build(environment_name="prod1")
        rpms.build(["accounts"], environment_name="prod1")
        # Every RPM ever built stays in rpm/; the delivery has only the current.
        self.assertTrue(
            (
                bundle.DIST / "prod1/rpm/myproduct-ledger-1.0.0-1.0.0-1.noarch.rpm"
            ).is_file()
        )
        self.assertEqual(
            sorted(path.name for path in delivery.iterdir()),
            [
                "myproduct-accounts-1.1.0-1.1.0-1.noarch.rpm",
                "myproduct-reports-1.0.0-1.0.0-1.noarch.rpm",
                tools + "-1.noarch.rpm",
            ],
        )

    def test_an_rpm_of_an_earlier_archive_is_not_delivered(self):
        """Same version, other bundle bytes: the reused RPM is refused."""
        bundle.build(environment_name="prod1")
        rpms.build(environment_name="prod1")
        self.put(
            "config/prod1.yaml",
            environment_file(
                ["accounts", "ledger", "reports"],
                accounts={
                    "main": dict(
                        registration(0, "ledger"), **registration(1, "reports")
                    )
                },
                reports={"main": {"Export": "changed"}},
            ),
        )
        (self.source / "components/accounts/VERSION").write_text("1.1.0\n")
        bundle.build(environment_name="prod1")
        with self.assertRaisesRegex(
            rpms.RpmError,
            "dist/prod1/delivery not written: myproduct-reports-1.0.0-1.0.0-1.noarch.rpm "
            "wraps another myproduct-reports-1.0.0-offline.tar.gz than the current "
            "one; one version has one content, so give reports a new VERSION",
        ):
            rpms.build(["accounts"], environment_name="prod1")
        self.assertFalse((bundle.DIST / "prod1/delivery").exists())

    def test_a_failed_copy_leaves_no_delivery(self):
        bundle.build(environment_name="prod1")
        rpms.build(environment_name="prod1")
        copies = []

        def copy(source, target):
            copies.append(target)
            if len(copies) == 2:
                raise OSError("disk full")
            return shutil.copyfile(source, target)

        with mock.patch.object(rpms.shutil, "copy2", copy), self.assertRaises(OSError):
            rpms.build(
                ["--never"] if False else [], tools=True, environment_name="prod1"
            )
        self.assertEqual(len(copies), 2)
        self.assertFalse((bundle.DIST / "prod1/delivery").exists())
        self.assertFalse((bundle.DIST / "prod1/.delivery-partial").exists())

    def test_a_delivery_with_a_missing_rpm_is_not_written(self):
        bundle.build(environment_name="prod1")
        delivery = bundle.DIST / "prod1/delivery"
        with self.assertRaisesRegex(
            rpms.RpmError,
            "dist/prod1/delivery not written: no RPM yet for ledger, reports, "
            "--tools; run ./build-rpms.sh --environment prod1 ledger reports --tools",
        ):
            rpms.build(["accounts"], environment_name="prod1")
        self.assertFalse(delivery.exists())

    def test_a_list_from_another_set_is_refused(self):
        bundle.build(environment_name="prod1")
        # The environment shrank after the last complete build.
        self.put(
            "config/prod1.yaml",
            environment_file(
                ["accounts", "reports"], accounts={"main": registration(0, "reports")}
            ),
        )
        with self.assertRaisesRegex(
            rpms.RpmError,
            r"dist/prod1/current-bundles.txt does not match the environment's "
            r"components \(myproduct-ledger-1.0.0-offline.tar.gz\); run "
            r"./build-bundle.sh --environment prod1",
        ):
            rpms.build(environment_name="prod1")
        self.assertEqual(self.wrapped, [])
        shutil.rmtree(bundle.DIST / "prod1")
        with self.assertRaisesRegex(
            rpms.RpmError, "Missing dist/prod1/current-bundles.txt"
        ):
            rpms.build(environment_name="prod1")


class SelectionInstallTests(SelectionFixture):
    def quiet(self, action):
        with contextlib.redirect_stdout(io.StringIO()):
            action()

    def test_moving_to_a_smaller_set_needs_an_explicit_uninstall_of_the_api(self):
        releases = self.build_and_unpack("prod1")
        with self.environment():
            for name in ("accounts", "ledger", "reports"):
                self.install(releases[name])
            # prod2 drops ledger; its accounts release has no line for it.
            (self.source / "components/accounts/VERSION").write_text("1.1.0\n")
            smaller = self.build_and_unpack("prod2")
            self.use_root(smaller["accounts"])
            before = sorted(str(p) for p in common.STATE.rglob("*"))
            with self.assertRaisesRegex(
                common.DeployError,
                "This accounts release has no API secret line for installed "
                "ledger; uninstall ledger first",
            ):
                deploy.install()
            self.assertEqual(sorted(str(p) for p in common.STATE.rglob("*")), before)
            self.use_root(releases["ledger"])
            self.quiet(deploy.uninstall)
            self.install(smaller["accounts"])
            installed = catalog.load_installed_metadata(common.STATE)
            self.assertNotIn("ledger", installed)
            self.assertEqual(
                installed["accounts"]["api_secrets"],
                {"reports": {"index": 0, "secret": "reports-api-secret/value"}},
            )
            # The next runtime run leaves ledger out although its release stays:
            # the real status report and the runtime command's own selection.
            report = status.collect()
            self.assertEqual(report["uninstalled"], ["ledger"])
            order = ["accounts", "ledger", "reports"]
            versions = {"accounts": "1.1.0", "ledger": "1.0.0", "reports": "1.0.0"}
            with contextlib.redirect_stdout(io.StringIO()) as shown:
                targets = runtime.selected(
                    report,
                    order,
                    versions,
                    None,
                    "myproduct",
                    runtime.uninstalled(common.STATE),
                )
            self.assertEqual(targets, [])
            self.assertIn("ledger was uninstalled", shown.getvalue())
            # A plain status run reports it, without an error.
            with contextlib.redirect_stdout(io.StringIO()) as shown:
                status.status()
            self.assertIn("Uninstalled: ledger", shown.getvalue())


class DependencyTests(ProductFixture):
    """A selection that misses a dependency is refused; nothing is added."""

    def setUp(self):
        super().setUp()
        self.write_product(copy.deepcopy(RENAMED))

    def test_missing_gateway_or_identity_names_both(self):
        cases = (
            (
                "route",
                ["login-service", "orders"],
                (
                    "config/prod3.yaml: login-service requires gateway .it has "
                    "route.conf.; add gateway to components"
                ),
            ),
            (
                "identity",
                ["gateway", "orders"],
                (
                    "config/prod3.yaml: orders requires login-service .it has "
                    "client.yaml.; add login-service to components"
                ),
            ),
            (
                "public settings",
                ["manual"],
                (
                    "config/prod3.yaml: manual requires gateway .its public "
                    "settings.; add gateway to components"
                ),
            ),
        )
        (self.source / "config").mkdir()
        for label, components, pattern in cases:
            with self.subTest(label):
                if label == "public settings":
                    # Without route.conf, manual still takes the public settings.
                    (self.source / "components/manual/route.conf").unlink()
                (self.source / "config/prod3.yaml").write_text(
                    environment_file(components)
                )
                with self.assertRaisesRegex(common.DeployError, pattern):
                    bundle.build(environment_name="prod3")
                self.assertFalse(bundle.DIST.exists())

    def test_isolated_install_of_a_selected_set(self):
        """gateway and manual only: no Identity, no client, no excluded bundle."""
        (self.source / "config").mkdir()
        (self.source / "config/small.yaml").write_text(
            environment_file(["gateway", "manual"])
        )
        releases = self.build_and_unpack("small")
        self.assertEqual(sorted(releases), ["gateway", "manual"])
        shutil.rmtree(self.source)
        self.provide_credentials(RENAMED, common.STATE)
        with self.environment():
            for name in ("gateway", "manual"):
                self.install(releases[name])
        installed = catalog.load_installed_metadata(common.STATE)
        self.assertEqual(sorted(installed), ["gateway", "manual"])
        # Uninstall leaves a record; installing again removes it. An uninstall
        # interrupted after the marker is gone keeps the version on retry.
        with self.environment():
            self.use_root(releases["manual"])
            failing = mock.patch.object(
                deploy.registrations, "clear_pending", side_effect=OSError("stop")
            )
            with failing, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(OSError):
                    deploy.uninstall()
            record = catalog.uninstalled_path(common.STATE, "manual")
            self.assertFalse((common.STATE / "installed/manual").exists())
            with contextlib.redirect_stdout(io.StringIO()):
                deploy.uninstall()
            self.assertEqual(record.read_text(), "1.0.0\n")
            self.install(releases["manual"])
            self.assertFalse(record.exists())
        self.assertEqual(installed["gateway"]["accepts"], {"routes": "gateway-routes"})
        self.assertEqual(
            sorted(path.name for path in (common.STATE / "routes").iterdir()),
            ["manual.conf"],
        )
