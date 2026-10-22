"""Container field placement in a minimal external-image product (backlog 62)."""

import copy
import shutil
from pathlib import Path
from unittest import mock

import bundle
import yaml
from deployment import cli, common, deploy, validation
from deployment import render as rendering

from helpers.product_fixture import ProductFixture, pod


class ManifestStructureTests(ProductFixture):
    def setUp(self):
        super().setUp()
        ref = {"secretKeyRef": {"name": "processor-settings", "key": "connection"}}
        self.job = pod("processor-job", "localhost/worker:1")
        container = self.job["spec"]["containers"][0]
        container["env"] = [{"name": "CONTROL", "valueFrom": ref}]
        init = copy.deepcopy(container)
        init["name"] = "migration"
        init["env"] = [
            {"name": "APP_CONNECTIONSTRING", "valueFrom": ref},
            {"name": "SECOND_CONNECTION", "valueFrom": copy.deepcopy(ref)},
        ]
        self.job["spec"]["initContainers"] = [init]
        self.defaults = {
            "SECRET_FILES": {
                "processor-password": [
                    {"path": "credentials/database", "generate": ["password"]}
                ]
            },
            "SECRET_TEMPLATES": {
                "processor-settings": {
                    "connection": "Password=@@secret:processor-password/password@@"
                }
            },
        }
        self.write_product(
            {
                "processor": {
                    "catalog": {},
                    "defaults": self.defaults,
                    "manifests": [self.job],
                }
            }
        )
        self.manifest_path = Path("components/processor/manifests/10-resources.yaml")
        self.password = common.BUILD / "dev/processor/credentials/database/password"
        self.password.parent.mkdir(parents=True)
        self.password.write_bytes(b"retained-test-password")

    def write_job(self, root, job=None):
        (root / self.manifest_path).write_text(yaml.safe_dump_all([job or self.job]))

    def snapshot(self):
        return {
            str(path.relative_to(self.root)): (
                path.stat().st_mode,
                path.read_bytes() if path.is_file() else None,
            )
            for path in self.root.rglob("*")
        }

    def without_credential_reads(self):
        original = Path.open

        def checked(path, *args, **kwargs):
            if "credentials" in path.parts:
                raise AssertionError("validation read credential contents")
            return original(path, *args, **kwargs)

        return mock.patch.object(Path, "open", checked)

    def test_all_guarded_fields_fail_before_side_effects_in_source(self):
        # Existing output and sibling data must survive every rejection.
        deploy.prepare()
        sibling = common.BUILD / "dev/sibling/state"
        sibling.parent.mkdir()
        sibling.write_bytes(b"unrelated")
        for field in (
            "env",
            "envFrom",
            "command",
            "args",
            "image",
            "imagePullPolicy",
            "volumeMounts",
            "volumeDevices",
            "ports",
            "workingDir",
            "livenessProbe",
            "readinessProbe",
            "startupProbe",
            "lifecycle",
            "stdin",
            "stdinOnce",
            "tty",
            "terminationMessagePath",
            "terminationMessagePolicy",
        ):
            with self.subTest(field=field):
                broken = copy.deepcopy(self.job)
                broken["spec"][field] = "private-value-must-not-appear"
                self.write_job(self.source, broken)
                before = self.snapshot()
                self.process.reset_mock()
                with self.without_credential_reads():
                    with mock.patch.object(cli.sys, "argv", ["deploy", "validate"]):
                        self.assertEqual(cli.main(), 1)
                error = self.stderr.getvalue()
                self.assertIn("10-resources.yaml: spec." + field, error)
                self.assertIn("spec.containers[] or spec.initContainers[]", error)
                self.assertNotIn("private-value-must-not-appear", error)
                with self.assertRaisesRegex(common.DeployError, "is not allowed here"):
                    deploy.prepare()
                with self.assertRaisesRegex(bundle.BundleError, "is not allowed here"):
                    bundle.build()
                self.assertEqual(self.commands(), [])
                self.assertEqual(self.snapshot(), before)

    def test_secret_reference_with_existing_key_rejected_in_relocated_release(self):
        self.check_relocated_release("always")

    def test_newer_only_repeat_reports_manifest_in_validate_and_install(self):
        self.check_relocated_release("newer-only")

    def check_relocated_release(self, upgrade):
        self.write_catalog({"processor": {"upgrade": upgrade}})
        release = self.build_and_unpack()["processor"]
        shutil.rmtree(self.source)
        relocated = self.root / "relocated-release"
        shutil.move(str(release), str(relocated))
        self.install(relocated)
        sibling = common.HOME / "sibling/state"
        sibling.parent.mkdir()
        sibling.write_bytes(b"unrelated")
        # Move a valid reference out of the init container; its Secret/key exist.
        broken = copy.deepcopy(self.job)
        broken["spec"]["env"] = broken["spec"]["initContainers"][0].pop("env")
        self.write_job(relocated, broken)
        before = self.snapshot()
        self.process.reset_mock()
        self.assertEqual(deploy.install_checks()[-1], upgrade == "always")
        for operation in (validation.validate, deploy.install):
            with self.subTest(upgrade=upgrade, operation=operation.__name__):
                with self.without_credential_reads():
                    with self.assertRaisesRegex(
                        common.DeployError, r"10-resources.yaml: spec\.env"
                    ):
                        operation()
                self.assertEqual(self.commands(), [])
                self.assertEqual(self.snapshot(), before)
        # Repair and retry consumes the same retained production config/credentials.
        self.write_job(relocated)
        validation.validate()
        deploy.install()

    def test_valid_container_env_indentation_and_arbitrary_data_keys(self):
        job = copy.deepcopy(self.job)
        job["metadata"]["annotations"] = {"env": "command", "image": "env"}
        # These names also belong to Pod spec and must stay accepted there.
        job["spec"].update(securityContext={}, restartPolicy="Always")
        words = {"env": "command", "image": "volumeMounts", "command": "args"}
        documents = [
            {
                "kind": "ConfigMap",
                "metadata": {"name": "processor-public"},
                "data": words,
            },
            {
                "kind": "Secret",
                "metadata": {"name": "processor-inline"},
                "stringData": words,
            },
            job,
        ]

        class IndentedDumper(yaml.SafeDumper):
            def increase_indent(self, flow=False, indentless=False):
                return super().increase_indent(flow, indentless=False)

        for dumper in (yaml.SafeDumper, IndentedDumper):
            with self.subTest(dumper=dumper.__name__):
                (self.source / self.manifest_path).write_text(
                    yaml.dump_all(documents, Dumper=dumper, sort_keys=False)
                )
                with self.without_credential_reads():
                    validation.validate()
                deploy.prepare()
                rendered = rendering.effective_documents(
                    self.defaults,
                    self.password.parents[2] / "config.yaml",
                    self.source / self.manifest_path.parent,
                    "processor",
                )
                self.assertEqual(
                    rendered[-1]["spec"]["initContainers"][0]["env"],
                    job["spec"]["initContainers"][0]["env"],
                )
                self.assertEqual(rendered[0]["data"], words)
                self.assertEqual(rendered[1]["stringData"], words)
