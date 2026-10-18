"""Retry failures in fresh processes against the same actual installed files/import archives."""

import base64
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml
from test_components import ComponentFixture

from deployment import catalog, common
from deployment import render as rendering

REAL_RUN = subprocess.run
SOURCE = Path(__file__).resolve().parent.parent / "deployment/deploy.py"
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
        self.mark_installed("app2", "1.2.3")
        self.write("home/app2/config.yaml", "retained sibling config\n")
        self.write("home/app2/credentials/key", b"retained sibling key", 0o600)
        self.before = self.protected()

    def protected(self):
        return {
            str(path.relative_to(common.HOME)): (path.read_bytes(), path.stat().st_mode)
            for path in common.HOME.rglob("*")
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
        return json.loads((common.HOME / "pending-operation.json").read_text())

    def actual_app_credentials(self):
        """Use shipped app manifests/defaults with synthetic persistent private files."""
        repo = Path(__file__).resolve().parent.parent
        manifests = self.root / "components/app1/manifests"
        shutil.rmtree(manifests)
        shutil.copytree(repo / "components/app1/manifests", manifests)
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

    def test_actual_app_secret_bytes_survive_failed_upgrade_and_fresh_process_retry(
        self,
    ):
        self.actual_app_credentials()
        self.write("VERSION", "1.2.4\n")
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
        self.assertFalse((common.HOME / "pending-operation.json").exists())
        for owner in owners:
            if owner in ("identity", "platform"):
                archive = ["archives", str(common.HOME / owner / "files")]
                self.assertLess(events.index(archive), events.index(service(owner)))
        self.assertEqual(self.protected(), self.before)

    def assert_imports(self, installed):
        for owner, group, index in (
            ("platform", "platform-routes", "installed.conf"),
            ("identity", "identity-clients", "installed.json"),
        ):
            with tarfile.open(
                str(common.HOME / owner / "files" / (group + ".tar"))
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
                    self.mode(common.HOME / "pending-operation.json"), 0o600
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
        old = (common.HOME / "identity/files/identity-clients.tar").read_bytes()
        self.attempt(expected=1, archive_failure="identity")
        self.assertEqual(
            (common.HOME / "identity/files/identity-clients.tar").read_bytes(), old
        )
        self.assert_finished(self.attempt(), ["app1", "identity", "platform"])
        self.assertNotEqual(
            (common.HOME / "identity/files/identity-clients.tar").read_bytes(), old
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
        (common.HOME / "clients/app1/client.crt").unlink()
        self.attempt(expected=1, write_failure="clients/app1/client.crt")
        self.assert_finished(self.attempt(), ["app1", "identity", "platform"])
        self.assert_imports(True)

    def test_identity_install_records_resume_before_publishing_completion(self):
        """Metadata is written before registrations and services; the marker last."""
        # Start without installed dependents, as on a first Identity installation.
        for component in ("app1", "app2"):
            (common.HOME / "installed" / component).unlink()
        self.before = self.protected()
        marker = common.HOME / "installed/identity"
        metadata = common.HOME / "metadata/identity.json"
        for first_install in (True, False):
            for target in ("metadata/identity.json", "installed/identity"):
                for interrupted in (False, True):
                    with self.subTest(
                        first_install=first_install,
                        target=target,
                        interrupted=interrupted,
                    ):
                        if first_install:
                            marker.unlink()
                            metadata.unlink()
                            previous = None
                        else:
                            self.mark_installed("identity", "1.1.0")
                            previous = metadata.read_bytes(), marker.read_bytes()
                        self.write("IDENTITY_VERSION", "1.2.0\n")
                        descriptor = self.select("identity")
                        option = "record_interrupt" if interrupted else "record_failure"
                        events = self.attempt(
                            expected=99 if interrupted else 1, **{option: target}
                        )
                        current = (
                            (metadata.read_bytes(), marker.read_bytes())
                            if marker.exists()
                            else None
                        )
                        if target == "metadata/identity.json":
                            # Nothing was registered or restarted with old metadata.
                            self.assertNotIn(service("identity"), events)
                            self.assertEqual(current, previous)
                            if first_install:
                                self.assertFalse(metadata.exists())
                        else:
                            self.assertIn(service("identity", "is-active"), events)
                            self.assertEqual(
                                json.loads(metadata.read_text()), descriptor
                            )
                            self.assertEqual(
                                marker.read_bytes() if marker.exists() else None,
                                previous[1] if previous else None,
                            )
                        events = self.attempt()
                        self.assertIn(service("identity"), events)
                        self.assertEqual(marker.read_bytes(), b"1.2.0\n")
                        self.assertEqual(json.loads(metadata.read_text()), descriptor)
                        for path in (marker, metadata):
                            self.assertEqual(self.mode(path), 0o600)
                        self.assertEqual(self.protected(), self.before)
        # A later platform upgrade can read the completed Identity contract.
        self.write("PLATFORM_VERSION", "1.2.0\n")
        self.select("platform")
        self.attempt()

    def test_uninstall_owner_failure_resumes_without_yaml_and_preserves_data(self):
        self.attempt("uninstall", expected=1, failure=service("platform", "is-active"))
        self.assertFalse(catalog.component_paths("app1")[2].exists())
        self.assertTrue(self.pending()["stopped"])
        self.assertEqual(self.pending()["owners"], ["platform"])
        events = self.attempt("uninstall")
        self.assertNotIn(service("app1", "stop"), events)
        self.assert_finished(events, ["platform"])
        self.assert_imports(False)
        self.assertFalse((common.HOME / "installed/app1").exists())
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
        self.assertFalse((common.HOME / "app1").exists())
        self.assertFalse((common.HOME / "pending-operation.json").exists())
        after = self.protected()
        self.assertEqual(
            after,
            {
                name: value
                for name, value in self.before.items()
                if not name.startswith("app1/")
            },
        )

    def test_mounted_config_map_deletion_survives_retry_after_yaml_is_removed(self):
        manifest = self.root / "components/app1/manifests/10-pod.yaml"
        documents = list(yaml.safe_load_all(manifest.read_text()))
        pod = next(doc for doc in documents if doc.get("kind") == "Pod")
        pod["spec"]["volumes"].append(
            {"name": "public", "configMap": {"name": "app1-public-config"}}
        )
        documents.append(
            {
                "kind": "ConfigMap",
                "metadata": {"name": "app1-public-config"},
                "data": {"template": "public configuration"},
            }
        )
        manifest.write_text(yaml.safe_dump_all(documents))
        self.attempt()
        volumes = ["app1-data", "app1-public-config", "app1-session", "app2-data"]
        self.write("host-volumes.json", json.dumps(volumes))
        self.attempt(
            "uninstall",
            expected=1,
            delete_data=True,
            failure=["podman", "volume", "rm", "app1-session"],
        )
        self.assertEqual(self.pending()["volumes"], volumes[:3])
        self.assertFalse(catalog.component_paths("app1")[2].exists())
        self.assertEqual(
            json.loads((self.root / "host-volumes.json").read_text()), volumes[2:]
        )
        events = self.attempt("uninstall", delete_data=True)
        self.assertEqual(
            [event for event in events if event[:3] == ["podman", "volume", "rm"]],
            [["podman", "volume", "rm", "app1-session"]],
        )
        self.assertEqual(
            json.loads((self.root / "host-volumes.json").read_text()), volumes[3:]
        )
        self.assertFalse((common.HOME / "pending-operation.json").exists())
        self.assertEqual(
            self.protected(),
            {
                name: value
                for name, value in self.before.items()
                if not name.startswith("app1/")
            },
        )

    def test_uninstall_retry_after_marker_and_data_are_already_gone(self):
        self.write("host-volumes.json", '["app1-data", "app1-session"]')
        self.attempt("uninstall", expected=1, delete_data=True, clear_failure=True)
        self.assertFalse((common.HOME / "installed/app1").exists())
        self.assertFalse((common.HOME / "app1").exists())
        self.assertEqual(self.pending()["owners"], [])
        events = self.attempt("uninstall", delete_data=True)
        self.assertNotIn(service("app1", "stop"), events)
        self.assertFalse(
            any(event[:3] == ["podman", "volume", "rm"] for event in events)
        )
        self.assertFalse((common.HOME / "pending-operation.json").exists())

    def test_unfinished_first_install_names_the_retry_for_uninstall(self):
        """Metadata without a marker: uninstall explains, and the retry finishes."""
        (common.HOME / "installed/app1").unlink()
        (common.HOME / "metadata/app1.json").unlink()
        events = self.attempt(expected=1, failure=service("app1"))
        self.assertTrue((common.HOME / "metadata/app1.json").is_file())
        self.assertFalse((common.HOME / "installed/app1").exists())
        self.assertFalse((common.HOME / "pending-operation.json").exists())
        events = self.attempt("uninstall", expected=1)
        self.assertEqual(events[-1][:2], ["error", "DeployError"])
        self.assertIn("app1 has an unfinished first install", events[-1][2])
        self.assertIn("Run ./deploy install from its bundle again", events[-1][2])
        self.assertEqual([event for event in events if event[0] != "error"], [])
        self.attempt()
        self.assertTrue((common.HOME / "installed/app1").is_file())
        self.attempt("uninstall")
        self.assertFalse((common.HOME / "metadata/app1.json").exists())

    def test_flag_conflicts_installs_and_dependencies_refuse_during_uninstall(self):
        self.attempt("uninstall", expected=1, failure=service("app1", "stop"))
        before = (common.HOME / "pending-operation.json").read_bytes()
        for action, options in (
            ("uninstall", {"delete_data": True}),
            ("install", {}),
            ("init-config", {}),
        ):
            events = self.attempt(action, expected=1, **options)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0][0], "error")
            self.assertEqual(
                (common.HOME / "pending-operation.json").read_bytes(), before
            )
        self.select("identity")
        # Model an uninstalling dependency: start its pending record in a fresh fixture state.
        state = self.pending()
        state.update(component="identity", owners=[], volumes=[])
        (common.HOME / "pending-operation.json").write_text(json.dumps(state))
        self.select("app1")
        events = self.attempt(expected=1)
        self.assertIn("Pending uninstall for identity", events[0][-1])

    def test_uninstall_cannot_discard_pending_install_or_another_components_work(self):
        self.changed()
        self.attempt(expected=1, failure=service("app1"))
        before = (common.HOME / "pending-operation.json").read_bytes()
        self.attempt("uninstall", expected=1)
        self.select("identity")
        self.attempt(expected=1)
        self.assertEqual((common.HOME / "pending-operation.json").read_bytes(), before)

    def test_invalid_or_symlinked_pending_state_refuses_before_host_calls(self):
        path = common.HOME / "pending-operation.json"
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
        self.assertTrue((common.HOME / "pending-operation.json").exists())
        self.assertEqual(
            json.loads((self.root / "host-volumes.json").read_text()),
            ["app1-data", "app1-session"],
        )
        self.attempt("uninstall", delete_data=True)
        self.assertFalse((common.HOME / "pending-operation.json").exists())
