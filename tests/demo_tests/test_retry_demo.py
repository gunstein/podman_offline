"""Retry failures in fresh processes against the same actual installed files/import archives."""

import base64
import hashlib
import json
from pathlib import Path

import yaml
from deployment import catalog, common

from demo_tests.demo_fixture import write_published_file
from helpers.retry_fixture import service
from helpers.retry_lifecycle import RetryFixture

# What Identity's install leaves (backlog 88): its retained audit key and the
# SHA-256 it published of it. The producer's own install is tested in
# platform_tests/test_secret_digests.py; here app1 is installed on its own.
AUDIT_KEY = b"Synthetic0Key1For2Digest3Tests45"
AUDIT_DIGEST = hashlib.sha256(AUDIT_KEY).hexdigest().encode()


class DemoRetryTests(RetryFixture):
    def actual_app_credentials(self, source=None):
        write_published_file(
            common.STATE / "identity/credentials/audit/audit_key", AUDIT_KEY
        )
        write_published_file(
            common.STATE / "identity/credentials/audit-sha256/audit_key",
            AUDIT_DIGEST,
        )
        return super().actual_app_credentials(
            source or Path(__file__).resolve().parents[2]
        )

    def attempt(self, action="install", expected=0, **options):
        """Every app1 run here fails if it opens Identity's raw key directory."""
        options.setdefault("guard_reads", "identity/credentials/audit")
        return super().attempt(action, expected, **options)

    def test_actual_app_secret_bytes_survive_failed_upgrade_and_fresh_process_retry(
        self,
    ):
        self.actual_app_credentials()
        self.write("components/app1/VERSION", "1.2.4\n")
        self.changed()
        self.attempt(expected=1, failure=service("app1"))
        self.assertEqual(self.protected(), self.before)
        events = self.attempt()
        self.assert_finished(events, ["app1", "identity", "platform"])
        documents = list(
            yaml.safe_load_all(catalog.component_paths("app1")[2].read_text())
        )
        secret = next(
            doc for doc in documents if doc["metadata"]["name"] == "app1-signing"
        )
        self.assertEqual(secret["kind"], "Secret")
        for name, value in secret["data"].items():
            self.assertEqual(
                base64.b64decode(value),
                (common.STATE / "app1/credentials/todo" / name).read_bytes(),
            )
        self.assertFalse((common.STATE / "app1/files/app1-signing.tar").exists())
        self.assertEqual(
            catalog.component_paths("app1")[2].stat().st_mode & 0o777, 0o600
        )

    def test_actual_app_secret_uninstall_retry_retains_state_and_delete_data_is_scoped(
        self,
    ):
        self.actual_app_credentials()
        volumes = self.root / "host-volumes.json"
        names = [
            "app1-data",
            "app1-signing",
            "app1-database-password",
            "app2-data",
            "app2-signing",
        ]
        volumes.write_text(json.dumps(names))
        self.attempt("uninstall", expected=1, failure=service("identity"))
        self.attempt("uninstall")
        self.assertEqual(self.protected(), self.before)
        self.assertEqual(json.loads(volumes.read_text()), names)
        self.attempt()
        self.attempt(
            "uninstall", expected=1, delete_data=True, failure=service("identity")
        )
        self.attempt("uninstall", delete_data=True)
        self.assertFalse((common.STATE / "app1").exists())
        self.assertEqual(json.loads(volumes.read_text()), ["app2-data", "app2-signing"])
        self.assertEqual(
            {
                name: value
                for name, value in self.protected().items()
                if name.startswith("app2/")
            },
            {
                name: value
                for name, value in self.before.items()
                if name.startswith("app2/")
            },
        )

    def app1_env_secret(self):
        documents = yaml.safe_load_all(catalog.component_paths("app1")[2].read_text())
        return next(
            doc
            for doc in documents
            if doc["metadata"]["name"] == "app1-backend-env-secret"
        )

    def test_separate_app1_install_and_retry_use_the_published_digest(self):
        """Backlog 88: app1's own install reads only Identity's published file.

        attempt() guards every run, so an open of Identity's raw key directory
        would end it with exit 97 instead of the expected status.
        """
        raw = common.STATE / "identity/credentials/audit/audit_key"
        digest = common.STATE / "identity/credentials/audit-sha256/audit_key"
        self.actual_app_credentials()
        before = {
            path: (path.stat().st_ino, path.stat().st_mtime_ns)
            for path in (raw, digest)
        }
        self.assertEqual(
            base64.b64decode(self.app1_env_secret()["data"]["AUDIT_KEY_SHA256"]),
            AUDIT_DIGEST,
        )
        # A fresh-process retry after a failed upgrade uses it again.
        self.write("components/app1/VERSION", "1.2.4\n")
        self.changed()
        self.attempt(expected=1, failure=service("app1"))
        self.attempt()
        self.assertEqual(
            base64.b64decode(self.app1_env_secret()["data"]["AUDIT_KEY_SHA256"]),
            AUDIT_DIGEST,
        )
        # Neither Identity file was written or replaced.
        self.assertEqual(
            {
                path: (path.stat().st_ino, path.stat().st_mtime_ns)
                for path in (raw, digest)
            },
            before,
        )
        self.assertEqual(raw.read_bytes(), AUDIT_KEY)

    def test_the_guard_catches_an_open_of_the_raw_key(self):
        """The guard itself: a run that opens the guarded directory fails."""
        self.actual_app_credentials()
        events = self.attempt(expected=97, guard_reads="app1/credentials/todo")
        self.assertEqual(events[-1][0], "guarded-read")

    def test_missing_digest_stops_app1_with_the_next_step(self):
        self.actual_app_credentials()
        (common.STATE / "identity/credentials/audit-sha256/audit_key").unlink()
        self.write("components/app1/VERSION", "1.2.4\n")
        events = self.attempt(expected=1)
        message = events[-1][2]
        self.assertRegex(
            message,
            r"^Missing .*/identity/credentials/audit-sha256/audit_key "
            r"\(SECRET_FILES.app1-audit-key-sha256\); if another component "
            r"publishes this file, install that component again first",
        )
        self.assertNotIn(AUDIT_DIGEST.decode(), json.dumps(events))
        self.assertNotIn(AUDIT_KEY.decode(), json.dumps(events))
        # Stopped in materialization: nothing of the new version was published.
        self.assertNotIn("1.2.4", (common.STATE / "installed/app1").read_text())
