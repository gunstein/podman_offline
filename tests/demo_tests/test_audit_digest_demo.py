"""The demo's Identity publishes the SHA-256 of its audit key for app1 (backlog 88).

The documented first run (demo-credentials, validate, dev.sh up's prepare)
with no audit files, and validate's checks of app1's promised digest file.
"""

import base64
import hashlib
import shutil
import subprocess
from pathlib import Path

import yaml
from deployment import common, deploy, validation
from deployment import render as rendering

from demo_tests.demo_fixture import DEMO_COMPONENTS, DEMO_PUBLIC, write_secret_fixtures
from helpers.deploy_fixture import DeployFixture

REPO = Path(__file__).resolve().parents[2]
KEY = "identity/credentials/audit/audit_key"
DIGEST = "identity/credentials/audit-sha256/audit_key"


class AuditDigestDemoTests(DeployFixture):
    def setUp(self):
        super().setUp()
        bundle = self.root / "bundle.yaml"
        if bundle.exists():
            bundle.unlink()
        shutil.rmtree(self.root / "components", ignore_errors=True)
        shutil.copytree(REPO / "components", self.root / "components")
        shutil.copy2(REPO / "bundles.yaml", self.root / "bundles.yaml")
        shutil.rmtree(self.root / "config", ignore_errors=True)
        shutil.copytree(
            REPO / "config",
            self.root / "config",
            ignore=shutil.ignore_patterns("dev.yaml"),
        )
        self.write(
            "config/dev.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\n"
            "IP_ADDRESS: 127.0.0.1\n",
        )
        # The credentials demo-credentials.sh delivers; no database volume exists.
        self.process.return_value = subprocess.CompletedProcess([], 1)
        self.dev = common.BUILD / "dev"
        for component in DEMO_COMPONENTS:
            config = rendering.merge_config(
                REPO / "components" / component / "config.defaults.yaml",
                overrides=DEMO_PUBLIC,
            )
            write_secret_fixtures(self.dev / component, config, component)
            if component.startswith("app"):
                certificate = yaml.safe_load(
                    (REPO / "components" / component / "client.yaml").read_text()
                )["certificate"]
                self.write(
                    "build/dev/" + component + "/" + certificate,
                    "-----BEGIN CERTIFICATE-----\nY2VydA==\n-----END CERTIFICATE-----\n",
                )
        # First run: no audit files (the fixture plays Identity for app1's file).
        shutil.rmtree(self.dev / "identity/credentials/audit-sha256")
        self.assertFalse((self.dev / KEY).exists())

    def findings(self):
        try:
            validation.validate()
        except common.DeployError as error:
            return str(error)
        return ""

    def app1_documents(self):
        return [
            doc
            for doc in yaml.safe_load_all((common.BUILD / "install.yaml").read_text())
            if doc["metadata"]["name"].startswith("app1")
        ]

    def test_first_run_validate_then_prepare(self):
        self.assertEqual(self.findings(), "")
        # validate reads and creates neither audit file.
        self.assertFalse((self.dev / KEY).exists())
        self.assertFalse((self.dev / DIGEST).exists())
        deploy.prepare()
        key = (self.dev / KEY).read_bytes()
        digest = hashlib.sha256(key).hexdigest().encode()
        self.assertEqual(len(key), 32)
        self.assertEqual((self.dev / DIGEST).read_bytes(), digest)
        documents = self.app1_documents()
        secret = next(
            doc
            for doc in documents
            if doc["metadata"]["name"] == "app1-backend-env-secret"
        )
        self.assertEqual(base64.b64decode(secret["data"]["AUDIT_KEY_SHA256"]), digest)
        text = yaml.safe_dump_all(documents)
        self.assertNotIn(key.decode(), text)
        self.assertNotIn(base64.b64encode(key).decode(), text)
        self.assertNotIn(key.decode(), self.stdout.getvalue() + self.stderr.getvalue())
        self.assertNotIn(
            digest.decode(), self.stdout.getvalue() + self.stderr.getvalue()
        )

    def test_prepare_again_keeps_the_key_and_repairs_the_digest(self):
        deploy.prepare()
        key = (self.dev / KEY).read_bytes()
        digest = (self.dev / DIGEST).read_bytes()
        before = (self.dev / DIGEST).stat().st_mtime_ns
        deploy.prepare()
        self.assertEqual((self.dev / KEY).read_bytes(), key)
        self.assertEqual((self.dev / DIGEST).stat().st_mtime_ns, before)
        (self.dev / DIGEST).write_bytes(b"wrong")
        deploy.prepare()
        self.assertEqual((self.dev / DIGEST).read_bytes(), digest)
        (self.dev / DIGEST).unlink()
        deploy.prepare()
        self.assertEqual((self.dev / DIGEST).read_bytes(), digest)
        self.assertEqual((self.dev / KEY).read_bytes(), key)

    def edit_defaults(self, component, change):
        path = self.root / "components" / component / "config.defaults.yaml"
        path.write_text(change(path.read_text()))

    def test_validate_refuses_misspelled_keys_of_the_promised_file(self):
        right = "@@secret:app1-audit-key-sha256/audit_key@@"
        wrong = "@@secret:app1-audit-key-sha256/audit_kee@@"
        self.edit_defaults("app1", lambda text: text.replace(right, wrong))
        self.assertIn(
            "missing declared source SECRET_FILES.app1-audit-key-sha256/audit_kee",
            self.findings(),
        )
        self.edit_defaults("app1", lambda text: text.replace(wrong, right))
        self.edit_defaults(
            "app1",
            lambda text: text.replace(
                "    /seed-secret/020-report-role.sql: sql/020-report-role.sql",
                "    /seed-secret/020-report-role.sql: sql/020-report-role.sql\n"
                "    /run/audit: '@@secret:app1-audit-key-sha256/audit_kee@@'",
            ),
        )
        self.assertIn("app1-audit-key-sha256 has no key audit_kee", self.findings())

    def test_validate_refuses_a_misspelled_manifest_selection(self):
        manifest = next(
            path
            for path in sorted((self.root / "components/app1/manifests").glob("*.yaml"))
            if "kind: Pod" in path.read_text() and "name: backend" in path.read_text()
        )
        documents = list(yaml.safe_load_all(manifest.read_text()))
        pod = next(doc for doc in documents if doc and doc.get("kind") == "Pod")
        pod["spec"].setdefault("volumes", []).append(
            {
                "name": "audit",
                "secret": {
                    "secretName": "app1-audit-key-sha256",
                    "items": [{"key": "audit_kee", "path": "audit"}],
                },
            }
        )
        manifest.write_text(yaml.safe_dump_all(documents, sort_keys=False))
        self.assertIn(
            "uses key 'audit_kee' of Secret 'app1-audit-key-sha256', which provides "
            "only audit_key",
            self.findings(),
        )

    def test_validate_refuses_the_promised_name_twice_in_one_secret(self):
        self.edit_defaults(
            "app1",
            lambda text: text.replace(
                "  - path: ../identity/credentials/audit-sha256/audit_key\n",
                "  - path: ../identity/credentials/audit-sha256/audit_key\n"
                "  - path: credentials/audit-copy\n    generate:\n    - audit_key\n",
            ),
        )
        self.assertIn(
            "SECRET_FILES.app1-audit-key-sha256 has several files with the same name",
            self.findings(),
        )

    def test_validate_accepts_promises_only_from_earlier_components(self):
        """platform comes before identity, so identity's file is not promised to it."""
        self.edit_defaults(
            "platform",
            lambda text: text.replace(
                "SECRET_FILES:\n",
                "SECRET_FILES:\n  platform-audit:\n"
                "  - path: ../identity/credentials/audit-sha256/audit_key\n",
                1,
            ).replace(
                "  nginx:\n",
                "  nginx:\n    AUDIT: '@@secret:platform-audit/audit_key@@'\n",
                1,
            ),
        )
        self.assertRegex(
            self.findings(),
            r"platform: Missing .*identity/credentials/audit-sha256/audit_key "
            r"\(SECRET_FILES.platform-audit\)",
        )

    def test_redirected_credentials_are_refused_before_any_dev_write(self):
        credentials = self.dev / "identity/credentials"
        inside = self.dev / "identity/elsewhere"
        shutil.move(str(credentials), str(inside))
        credentials.symlink_to(inside)
        before = sorted(str(p) for p in inside.rglob("*"))
        configs = {
            component: (self.dev / component / "config.yaml").exists()
            for component in DEMO_COMPONENTS
        }
        with self.assertRaisesRegex(common.DeployError, "must be a directory"):
            deploy.prepare()
        self.assertEqual(sorted(str(p) for p in inside.rglob("*")), before)
        self.assertEqual(
            {
                component: (self.dev / component / "config.yaml").exists()
                for component in DEMO_COMPONENTS
            },
            configs,
        )
        self.assertFalse((common.BUILD / "install.yaml").exists())
