"""Retry failures in fresh processes against the same actual installed files/import archives."""

import base64
import json
from pathlib import Path

import yaml
from deployment import catalog, common

from helpers.retry_fixture import service
from helpers.retry_lifecycle import RetryFixture


class DemoRetryTests(RetryFixture):
    def actual_app_credentials(self, source=None):
        return super().actual_app_credentials(
            source or Path(__file__).resolve().parents[2]
        )

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
                (common.HOME / "app1/credentials/todo" / name).read_bytes(),
            )
        self.assertFalse((common.HOME / "app1/files/app1-signing.tar").exists())
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
        self.assertFalse((common.HOME / "app1").exists())
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
