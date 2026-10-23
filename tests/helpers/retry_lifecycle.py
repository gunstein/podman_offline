"""Retry failures in fresh processes against the same actual installed files/import archives."""

import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml
from deployment import common
from deployment import render as rendering

from helpers.component_fixture import ComponentFixture
from helpers.retry_fixture import DRIVER, REAL_RUN, SOURCE, service


class RetryFixture(ComponentFixture):
    def setUp(self):
        super().setUp()
        self.imports_fixture()
        self.registration_fixture()
        manifest = self.root / "components/app1/manifests/10-pod.yaml"
        pod = yaml.safe_load(manifest.read_text())
        pod["spec"]["volumes"] = [
            {"name": name, "persistentVolumeClaim": {"claimName": "app1-" + name}}
            for name in ("data", "session")
        ]
        documents = [
            {"kind": "PersistentVolumeClaim", "metadata": {"name": "app1-" + name}}
            for name in ("data", "session")
        ] + [pod]
        manifest.write_text(yaml.safe_dump_all(documents))
        self.write(
            "home/app1/credentials/database/password",
            b"retained-private-password",
            0o600,
        )
        self.write("home/PKI/private/ca.key", b"retained-CA", 0o600)
        self.sequence = 0
        self.pids = []
        self.attempt()
        self.mark_installed("app2", "1.2.3")
        self.write("home/app2/config.yaml", "retained sibling config\n")
        self.write("home/app2/credentials/key", b"retained sibling key", 0o600)
        self.before = self.protected()

    def protected(self):
        return {
            str(path.relative_to(common.STATE)): (path.read_bytes(), path.stat().st_mode)
            for path in common.STATE.rglob("*")
            if path.is_file()
            and (
                "credentials/" in str(path)
                or "PKI/" in str(path)
                or path.name == "config.yaml"
                or "app2" in str(path)
            )
        }

    def attempt(self, action="install", expected=0, **options):
        self.sequence += 1
        record = self.root / ("attempt-" + str(self.sequence) + ".json")
        parameters = dict(
            root=str(self.root),
            source=str(SOURCE),
            record=str(record),
            action=action,
            **options,
        )
        result = REAL_RUN(
            [sys.executable, "-B", str(DRIVER)],
            input=json.dumps(parameters),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=dict(os.environ),
            check=False,
        )
        self.assertEqual(
            result.returncode,
            expected,
            result.stdout
            + result.stderr
            + (record.read_text() if record.exists() else ""),
        )
        evidence = json.loads(record.read_text())
        self.assertNotIn(evidence["pid"], self.pids)
        self.pids.append(evidence["pid"])
        self.assertNotEqual(evidence["pid"], os.getpid())
        return evidence["events"]

    def pending(self):
        return json.loads((common.STATE / "pending-operation.json").read_text())

    def actual_app_credentials(self, source=None):
        """Use declarative fixture inputs, or an explicit demo source for demo tests."""
        repo = source or Path(__file__).resolve().parents[1] / "fixtures/catalog"
        manifests = self.root / "components/app1/manifests"
        shutil.rmtree(manifests)
        shutil.copytree(repo / "components/app1/manifests", manifests)
        if (repo / "components/app1/files").exists():
            shutil.copytree(
                repo / "components/app1/files", self.root / "components/app1/files"
            )
        config = rendering.merge_config(
            repo / "config/common.defaults.yaml",
            repo / "components/app1/config.defaults.yaml",
            overrides={"PUBLIC_ORIGIN": "https://example.test:8443"},
        )
        self.write("home/app1/config.yaml", yaml.safe_dump(config), 0o600)
        for name in ("session-key", "todo-client.key", "ca.crt"):
            self.write(
                "home/app1/credentials/todo/" + name, b"private-" + name.encode(), 0o600
            )
        self.before = self.protected()
        self.attempt()

    def changed(self):
        self.write("components/app1/route.conf", "location /app1/ { return 202; }\n")
        self.write(
            "home/app1/credentials/todo/todo-client.crt",
            "-----BEGIN CERTIFICATE-----\nYW5vdGhlcg==\n-----END CERTIFICATE-----\n",
        )
        self.before = self.protected()

    def assert_finished(self, events, owners):
        self.assertEqual(
            [
                event
                for event in events
                if event[:3] == ["systemctl", "--user", "restart"]
            ],
            [service(owner) for owner in owners],
        )
        self.assertFalse((common.STATE / "pending-operation.json").exists())
        for owner in owners:
            if owner in ("identity", "platform"):
                archive = ["archives", str(common.STATE / owner / "files")]
                self.assertLess(events.index(archive), events.index(service(owner)))
        self.assertEqual(self.protected(), self.before)

    def assert_imports(self, installed):
        for owner, group, index in (
            ("platform", "platform-routes", "installed.conf"),
            ("identity", "identity-clients", "installed.json"),
        ):
            with tarfile.open(
                str(common.STATE / owner / "files" / (group + ".tar"))
            ) as archive:
                stream = archive.extractfile(index)
                self.assertIsNotNone(stream)
                assert stream is not None
                with stream:
                    data = stream.read()
            self.assertEqual(b"app1" in data, installed)
