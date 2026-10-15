"""Retry failures in fresh processes against the same actual installed files/import archives."""

import base64
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml
from test_components import ComponentFixture

import deploy

REAL_RUN = subprocess.run
SOURCE = Path(__file__).resolve().parent.parent / "deploy.py"
DRIVER = Path(__file__).with_name("retry_driver.py")


def service(owner, operation="restart"):
    command = ["systemctl", "--user", operation]
    if operation == "is-active":
        command.append("--quiet")
    return command + ["myproduct-" + owner + ".service"]


class RetryTests(ComponentFixture):
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
        self.write("home/installed/app2", "1.2.3\n")
        self.write("home/app2/config.yaml", "retained sibling config\n")
        self.write("home/app2/credentials/key", b"retained sibling key", 0o600)
        self.before = self.protected()

    def protected(self):
        return {
            str(path.relative_to(deploy.HOME)): (path.read_bytes(), path.stat().st_mode)
            for path in deploy.HOME.rglob("*")
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
            [sys.executable, str(DRIVER)],
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
        return json.loads((deploy.HOME / "pending-operation.json").read_text())

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
        self.assertFalse((deploy.HOME / "pending-operation.json").exists())
        for owner in owners:
            if owner in ("identity", "platform"):
                archive = ["archives", str(deploy.HOME / owner / "files")]
                self.assertLess(events.index(archive), events.index(service(owner)))
        self.assertEqual(self.protected(), self.before)

    def assert_imports(self, installed):
        for owner, group, index in (
            ("platform", "platform-routes", "installed.conf"),
            ("identity", "identity-clients", "installed.json"),
        ):
            with tarfile.open(
                str(deploy.HOME / owner / "files" / (group + ".tar"))
            ) as archive:
                stream = archive.extractfile(index)
                self.assertIsNotNone(stream)
                assert stream is not None
                with stream:
                    data = stream.read()
            self.assertEqual(b"app1" in data, installed)

    def test_app_restart_failure_and_process_interruption_preserve_both_owners(self):
        for interrupt in (False, True):
            with self.subTest(interrupt=interrupt):
                self.changed()
                # Change each iteration so a successful previous attempt isn't a no-op.
                self.write(
                    "components/app1/route.conf",
                    "location /app1/ { return " + str(203 + interrupt) + "; }\n",
                )
                self.write(
                    "home/app1/credentials/todo/todo-client.crt",
                    "-----BEGIN CERTIFICATE-----\n"
                    + ("YQ==" if interrupt else "Yg==")
                    + "\n-----END CERTIFICATE-----\n",
                )
                self.before = self.protected()
                if interrupt:
                    self.attempt(expected=99, interrupt=service("app1"))
                else:
                    self.attempt(expected=1, failure=service("app1"))
                self.assertEqual(
                    set(self.pending()["owners"]), {"identity", "platform"}
                )
                self.assertEqual(
                    self.mode(deploy.HOME / "pending-operation.json"), 0o600
                )
                self.assert_finished(self.attempt(), ["app1", "identity", "platform"])
                self.assert_imports(True)

    def test_owner_restart_or_active_check_failure_only_retries_unconfirmed_owners(
        self,
    ):
        for owner in ("identity", "platform"):
            for operation in ("restart", "is-active"):
                with self.subTest(owner=owner, operation=operation):
                    self.changed()
                    self.write(
                        "components/app1/route.conf",
                        "location /app1/ { return "
                        + str(210 + self.sequence)
                        + "; }\n",
                    )
                    self.write(
                        "home/app1/credentials/todo/todo-client.crt",
                        "-----BEGIN CERTIFICATE-----\n"
                        + base64.b64encode(str(self.sequence).encode("ascii")).decode(
                            "ascii"
                        )
                        + "\n-----END CERTIFICATE-----\n",
                    )
                    self.before = self.protected()
                    self.attempt(expected=1, failure=service(owner, operation))
                    expected = (
                        ["identity", "platform"]
                        if owner == "identity"
                        else ["platform"]
                    )
                    self.assertEqual(set(self.pending()["owners"]), set(expected))
                    self.assert_finished(self.attempt(), ["app1"] + expected)

    def test_import_failure_rebuilds_actual_archives_with_identical_registrations(self):
        self.changed()
        old = (deploy.HOME / "identity/files/identity-clients.tar").read_bytes()
        self.attempt(expected=1, archive_failure="identity")
        self.assertEqual(
            (deploy.HOME / "identity/files/identity-clients.tar").read_bytes(), old
        )
        self.assert_finished(self.attempt(), ["app1", "identity", "platform"])
        self.assertNotEqual(
            (deploy.HOME / "identity/files/identity-clients.tar").read_bytes(), old
        )
        self.assert_imports(True)

    def test_pending_route_work_combines_with_a_new_client_change(self):
        self.write("components/app1/route.conf", "location /app1/ { return 220; }\n")
        self.attempt(expected=1, failure=service("app1"))
        self.assertEqual(self.pending()["owners"], ["platform"])
        self.changed()
        self.assert_finished(self.attempt(), ["app1", "identity", "platform"])
        self.assert_imports(True)

    def test_partial_public_client_write_resumes_from_the_incoming_descriptor(self):
        self.changed()
        (deploy.HOME / "clients/app1/client.crt").unlink()
        self.attempt(expected=1, write_failure="clients/app1/client.crt")
        self.assert_finished(self.attempt(), ["app1", "identity", "platform"])
        self.assert_imports(True)

    def test_uninstall_owner_failure_resumes_without_yaml_and_preserves_data(self):
        self.attempt("uninstall", expected=1, failure=service("platform", "is-active"))
        self.assertFalse(deploy.component_paths("app1")[2].exists())
        self.assertTrue(self.pending()["stopped"])
        self.assertEqual(self.pending()["owners"], ["platform"])
        events = self.attempt("uninstall")
        self.assertNotIn(service("app1", "stop"), events)
        self.assert_finished(events, ["platform"])
        self.assert_imports(False)
        self.assertFalse((deploy.HOME / "installed/app1").exists())
        self.assertFalse(any(event[:2] == ["podman", "volume"] for event in events))

    def test_uninstall_import_failure_retries_before_owner_restart(self):
        self.attempt("uninstall", expected=1, archive_failure="identity")
        self.assertEqual(set(self.pending()["owners"]), {"identity", "platform"})
        self.assert_finished(self.attempt("uninstall"), ["identity", "platform"])
        self.assert_imports(False)

    def test_delete_data_retry_handles_already_removed_volumes_and_scopes_deletion(
        self,
    ):
        volumes = ["app1-data", "app1-session", "app2-data", "identity-data"]
        self.write("host-volumes.json", json.dumps(volumes))
        self.attempt(
            "uninstall",
            expected=1,
            delete_data=True,
            failure=["podman", "volume", "rm", "app1-session"],
        )
        self.assertEqual(
            json.loads((self.root / "host-volumes.json").read_text()), volumes[1:]
        )
        events = self.attempt("uninstall", delete_data=True)
        self.assertEqual(
            [event for event in events if event[:3] == ["podman", "volume", "rm"]],
            [["podman", "volume", "rm", "app1-session"]],
        )
        self.assertEqual(
            json.loads((self.root / "host-volumes.json").read_text()), volumes[2:]
        )
        self.assertFalse((deploy.HOME / "app1").exists())
        self.assertFalse((deploy.HOME / "pending-operation.json").exists())
        after = self.protected()
        self.assertEqual(
            after,
            {
                name: value
                for name, value in self.before.items()
                if not name.startswith("app1/")
            },
        )

    def test_uninstall_retry_after_marker_and_data_are_already_gone(self):
        self.write("host-volumes.json", '["app1-data", "app1-session"]')
        self.attempt("uninstall", expected=1, delete_data=True, clear_failure=True)
        self.assertFalse((deploy.HOME / "installed/app1").exists())
        self.assertFalse((deploy.HOME / "app1").exists())
        self.assertEqual(self.pending()["owners"], [])
        events = self.attempt("uninstall", delete_data=True)
        self.assertNotIn(service("app1", "stop"), events)
        self.assertFalse(
            any(event[:3] == ["podman", "volume", "rm"] for event in events)
        )
        self.assertFalse((deploy.HOME / "pending-operation.json").exists())

    def test_flag_conflicts_installs_and_dependencies_refuse_during_uninstall(self):
        self.attempt("uninstall", expected=1, failure=service("app1", "stop"))
        before = (deploy.HOME / "pending-operation.json").read_bytes()
        for action, options in (
            ("uninstall", {"delete_data": True}),
            ("install", {}),
            ("init-config", {}),
        ):
            events = self.attempt(action, expected=1, **options)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0][0], "error")
            self.assertEqual(
                (deploy.HOME / "pending-operation.json").read_bytes(), before
            )
        self.select("identity")
        # Model an uninstalling dependency: start its pending record in a fresh fixture state.
        state = self.pending()
        state.update(component="identity", owners=[], volumes=[])
        (deploy.HOME / "pending-operation.json").write_text(json.dumps(state))
        self.select("app1")
        events = self.attempt(expected=1)
        self.assertIn("Pending uninstall for identity", events[0][-1])

    def test_uninstall_cannot_discard_pending_install_or_another_components_work(self):
        self.changed()
        self.attempt(expected=1, failure=service("app1"))
        before = (deploy.HOME / "pending-operation.json").read_bytes()
        self.attempt("uninstall", expected=1)
        self.select("identity")
        self.attempt(expected=1)
        self.assertEqual((deploy.HOME / "pending-operation.json").read_bytes(), before)

    def test_invalid_or_symlinked_pending_state_refuses_before_host_calls(self):
        path = deploy.HOME / "pending-operation.json"
        invalid = [
            "{",
            "[]",
            json.dumps({"operation": "unknown"}),
            json.dumps(
                {
                    "operation": "uninstall",
                    "component": "app1",
                    "owners": [],
                    "delete_data": True,
                    "stopped": True,
                    "volumes": ["identity-data"],
                }
            ),
        ]
        for text in invalid:
            self.write("home/pending-operation.json", text, 0o600)
            for action in ("install", "uninstall"):
                events = self.attempt(action, expected=1)
                self.assertEqual(len(events), 1)
                self.assertIn("Invalid pending-operation", events[0][-1])
                self.assertEqual(path.read_text(), text)
        path.chmod(0o644)
        self.attempt(expected=1)
        path.unlink()
        other = self.write("elsewhere", "untouched", 0o600)
        path.symlink_to(other)
        self.attempt(expected=1)
        self.attempt("uninstall", expected=1)
        self.assertEqual(other.read_text(), "untouched")

    def test_volume_inspection_error_remains_pending_and_is_not_absence(self):
        self.write("host-volumes.json", '["app1-data", "app1-session"]')
        self.attempt(
            "uninstall", expected=1, delete_data=True, volume_check_error="app1-data"
        )
        self.assertTrue((deploy.HOME / "pending-operation.json").exists())
        self.assertEqual(
            json.loads((self.root / "host-volumes.json").read_text()),
            ["app1-data", "app1-session"],
        )
        self.attempt("uninstall", delete_data=True)
        self.assertFalse((deploy.HOME / "pending-operation.json").exists())
