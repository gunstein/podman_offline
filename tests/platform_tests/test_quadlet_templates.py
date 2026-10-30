"""Quadlet-only names, early refusal and relocated offline lifecycle (item 59)."""

import shutil
from unittest import mock

from deployment import common, deploy, layout, validation
from deployment import render as rendering

from helpers.deploy_fixture import DeployFixture
from helpers.product_fixture import ProductFixture, pod

INVALID = (
    "@@UNKNOWN@@",
    "@@PUBLIC_ORIGIN@@",
    "@@secret:processor-password/password@@",
    "@@UNIT_NAME",
    "@@PRODUCT NAME@@",
    "@@UNIT_NAME@@@@",
    "@@@@",
    "{name}",
    "{product}",
    "@@UNIT_NAME@@ {product}",
)


def snapshot(root):
    return {
        str(path.relative_to(root)): (
            path.stat().st_mode,
            path.read_bytes() if path.is_file() else None,
        )
        for path in root.rglob("*")
    }


class QuadletTextTests(DeployFixture):
    def test_inline_repeated_tokens_and_unrelated_syntax(self):
        text = (
            "[Unit]\nDescription=@@UNIT_NAME@@ / @@PRODUCT_NAME@@ / @@UNIT_NAME@@\n"
            "[Service]\nEnvironment=TEXT={literal} ${HOME} ${name} ${product} %n %%\n"
        )
        common.QUADLET_TEMPLATE.write_text(text)
        self.assertEqual(
            deploy.quadlet_text(".kube", "cedar", "cedar-processor"),
            "[Unit]\nDescription=cedar-processor / cedar / cedar-processor\n"
            "[Service]\nEnvironment=TEXT={literal} ${HOME} ${name} ${product} %n %%\n",
        )
        # A template does not have to use every allowed marker, or any marker.
        common.QUADLET_TEMPLATE.write_text("[Service]\nRestart=on-failure\n")
        self.assertEqual(
            deploy.quadlet_text(".kube", "cedar", "cedar-processor"),
            "[Service]\nRestart=on-failure\n",
        )

    def test_invalid_tokens_name_template_without_dumping_contents(self):
        for suffix in (".kube", ".network"):
            path = common.QUADLET_TEMPLATE.with_suffix(suffix)
            for token in INVALID:
                with self.subTest(suffix=suffix, token=token):
                    path.write_text("PrivateTemplateContent\nValue=" + token)
                    with self.assertRaises(common.DeployError) as error:
                        deploy.quadlet_text(suffix, "cedar", "cedar-processor")
                    message = str(error.exception)
                    self.assertIn(str(path), message)
                    self.assertNotIn("PrivateTemplateContent", message)
            path.write_bytes(b"\xff")
            with self.assertRaisesRegex(
                common.DeployError, "Quadlet template must be UTF-8"
            ):
                deploy.quadlet_text(suffix, "cedar", "cedar-processor")
        common.QUADLET_TEMPLATE.write_text("@@UNIT_NAME@@")
        with self.assertRaisesRegex(
            common.DeployError, "unresolved placeholder marker"
        ):
            deploy.quadlet_text(".kube", "cedar", "@@PRODUCT_NAME@@")

    def test_standalone_uses_internal_names_despite_config(self):
        self.install_fixture()
        self.config.update(UNIT_NAME="untrusted-unit", PRODUCT_NAME="untrusted-product")
        self.write_config()
        deploy.install()
        self.assertEqual(
            common.QUADLET_TARGET.read_text(), "[Kube]\nYaml=myproduct.yaml\n"
        )
        self.assertEqual(
            common.QUADLET_TARGET.with_suffix(".network").read_text(),
            "[Network]\nNetworkName=myproduct\n",
        )

    def test_standalone_rejects_before_host_queries_generation_or_output(self):
        self.install_fixture()
        before_templates = {
            suffix: common.QUADLET_TEMPLATE.with_suffix(suffix).read_text()
            for suffix in (".kube", ".network")
        }
        for suffix, original in before_templates.items():
            path = common.QUADLET_TEMPLATE.with_suffix(suffix)
            path.write_text("Value=@@BAD@@")
            before = snapshot(self.root)
            for operation in (validation.validate, deploy.prepare, deploy.install):
                with self.subTest(suffix=suffix, operation=operation.__name__):
                    self.process.reset_mock()
                    with mock.patch.object(layout, "check_user_manager") as manager:
                        with mock.patch.object(rendering, "materialize") as materialize:
                            with self.assertRaisesRegex(
                                common.DeployError, "unknown Quadlet token"
                            ):
                                operation()
                    manager.assert_not_called()
                    materialize.assert_not_called()
                    self.process.assert_not_called()
                    self.assertEqual(snapshot(self.root), before)
            path.write_text(original)


class QuadletBundleTests(ProductFixture):
    def setUp(self):
        super().setUp()
        self.product_name = "cedar"
        job = pod("processor-job", "localhost/worker:1")
        job["spec"]["containers"][0]["env"] = [
            {
                "name": "PASSWORD",
                "valueFrom": {
                    "secretKeyRef": {"name": "processor-password", "key": "password"}
                },
            }
        ]
        self.write_product(
            {
                "processor": {
                    "catalog": {},
                    "manifests": [job],
                    "defaults": {
                        "UNIT_NAME": "UntrustedUnit",
                        "PRODUCT_NAME": "UntrustedProduct",
                        "SECRET_FILES": {
                            "processor-password": [
                                {
                                    "path": "credentials/database",
                                    "generate": ["password"],
                                }
                            ]
                        },
                    },
                },
                "observer": {
                    "catalog": {},
                    "manifests": [pod("observer-job", "localhost/observer:1")],
                },
            }
        )

    def test_source_validate_and_prepare_reject_before_any_mutation(self):
        common.QUADLET_TEMPLATE.write_text("[Kube]\nYaml=@@BAD@@.yaml\n")
        before = snapshot(self.root)
        for operation in (validation.validate, deploy.prepare):
            with self.subTest(operation=operation.__name__):
                self.process.reset_mock()
                with self.assertRaisesRegex(
                    common.DeployError, "unknown Quadlet token"
                ):
                    operation()
                self.assertEqual(snapshot(self.root), before)
                self.process.assert_not_called()

    def test_first_install_refuses_before_generating_password(self):
        release = self.build_and_unpack()["processor"]
        self.use_root(release)
        deploy.init_config("processor")
        common.QUADLET_TEMPLATE.write_text("[Kube]\nYaml=@@BAD@@.yaml\n")
        before = snapshot(self.root)
        self.process.reset_mock()
        with mock.patch.object(layout, "check_user_manager") as manager:
            with self.assertRaisesRegex(common.DeployError, "unknown Quadlet token"):
                deploy.install()
        manager.assert_not_called()
        self.process.assert_not_called()
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse(
            (common.STATE / "processor/credentials/database/password").exists()
        )

    def test_relocated_bundle_repeat_and_sibling_preservation(self):
        self.check_relocated_bundle("always")

    def test_equal_version_newer_only_checks_both_templates(self):
        self.check_relocated_bundle("newer-only")

    def check_relocated_bundle(self, upgrade):
        self.write_catalog({"processor": {"upgrade": upgrade}, "observer": {}})
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        relocated = self.root / "offline"
        shutil.move(str(self.releases), str(relocated))
        releases = {name: relocated / path.name for name, path in releases.items()}
        self.install(releases["observer"])
        self.install(releases["processor"])
        self.assertFalse((common.ROOT / "apps").exists())
        unit = common.QUADLET_DIR / "cedar-processor.kube"
        expected = (
            "# ./deploy.sh install fills in the product name (bundles.yaml) and the unit name\n"
            "# (<product>-<component>, or the product for a standalone fixture).\n"
            "[Unit]\nDescription=cedar-processor\n\n[Kube]\nYaml=cedar-processor.yaml\n"
            "Network=cedar.network\n"
            "[Service]\n"
            "# Generate localhost entries without copying the host's /etc/hosts.\n"
            'Environment="CONTAINERS_CONF_OVERRIDE='
            + str(releases["processor"] / "quadlet/containers-hosts.conf")
            + '"\n'
            "Restart=on-failure\nTimeoutStartSec=180\n"
            "\n[Install]\nWantedBy=default.target\n"
        )
        self.assertEqual(unit.read_text(), expected)
        self.assertEqual(unit.stat().st_mode & 0o777, 0o644)
        network = common.QUADLET_DIR / "cedar.network"
        self.assertEqual(
            network.read_text(),
            "# ./deploy.sh install fills in the product name: the network every component shares.\n"
            "[Network]\nNetworkName=cedar\n",
        )
        sibling_paths = [
            common.STATE / "observer",
            common.QUADLET_DIR / "cedar-observer.kube",
            common.QUADLET_DIR / "cedar-observer.yaml",
        ]
        sibling_before = {
            str(p): snapshot(p) if p.is_dir() else p.read_bytes() for p in sibling_paths
        }
        network_before = (network.stat().st_ino, network.read_bytes())
        templates = {
            suffix: common.QUADLET_TEMPLATE.with_suffix(suffix).read_text()
            for suffix in (".kube", ".network")
        }
        for suffix, original in templates.items():
            path = common.QUADLET_TEMPLATE.with_suffix(suffix)
            for token in INVALID:
                with self.subTest(upgrade=upgrade, suffix=suffix, token=token):
                    path.write_text(original + "\nValue=" + token)
                    before = snapshot(self.root)
                    errors = []
                    for operation in (validation.validate, deploy.install):
                        self.process.reset_mock()
                        with mock.patch.object(layout, "check_user_manager") as manager:
                            with self.assertRaises(common.DeployError) as error:
                                operation()
                        errors.append(str(error.exception))
                        manager.assert_not_called()
                        self.process.assert_not_called()
                        self.assertEqual(snapshot(self.root), before)
                    self.assertIn(errors[1], errors[0])
                    self.assertIn(str(path), errors[1])
            path.write_text(original)
        # Repair and repeat: the shared network is retained and siblings are untouched.
        validation.validate()
        deploy.install()
        self.assertEqual((network.stat().st_ino, network.read_bytes()), network_before)
        self.assertEqual(
            {
                str(p): snapshot(p) if p.is_dir() else p.read_bytes()
                for p in sibling_paths
            },
            sibling_before,
        )
        self.assertEqual(unit.read_text(), expected)
