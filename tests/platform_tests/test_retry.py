"""Retry failures in fresh processes against the same actual installed files/import archives."""

import base64
import json

import yaml
from deployment import catalog, common

from helpers.retry_fixture import service
from helpers.retry_lifecycle import RetryFixture


class RetryTests(RetryFixture):
    def test_template_secret_survives_failure_and_retry_in_new_processes(self):
        self.actual_app_credentials()
        config_path = common.STATE / "app1/config.yaml"
        config = yaml.safe_load(config_path.read_text())
        config["SECRET_TEMPLATES"] = {
            "app1-connection": {
                "connection": "@@DB_HOST@@:@@secret:app1-database-password/password@@"
            }
        }
        config_path.write_text(yaml.safe_dump(config))
        manifest = self.root / "components/app1/manifests/60-todo.yaml"
        pod = yaml.safe_load(manifest.read_text())
        pod["spec"]["containers"][0]["env"].append(
            {
                "name": "COMPLETE_CONNECTION",
                "valueFrom": {
                    "secretKeyRef": {"name": "app1-connection", "key": "connection"}
                },
            }
        )
        manifest.write_text(yaml.safe_dump(pod))
        self.before = self.protected()
        self.attempt()
        password = (common.STATE / "app1/credentials/database/password").read_bytes()
        self.write("components/app1/VERSION", "1.2.4\n")
        self.changed()
        self.attempt(expected=1, failure=service("app1"))
        self.assertEqual(self.protected(), self.before)
        self.attempt()
        docs = list(yaml.safe_load_all(catalog.component_paths("app1")[2].read_text()))
        derived = next(
            doc for doc in docs if doc["metadata"]["name"] == "app1-connection"
        )
        self.assertEqual(
            base64.b64decode(derived["data"]["connection"]),
            config["DB_HOST"].encode() + b":" + password,
        )
        self.assertEqual(self.protected(), self.before)

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
                    self.mode(common.STATE / "pending-operation.json"), 0o600
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

    def test_unhealthy_owner_stays_pending_and_the_retry_finishes(self):
        """An active but unhealthy owner is not acknowledged (backlog 34)."""
        for owner, expected in (
            ("identity", ["identity", "platform"]),
            ("platform", ["platform"]),
        ):
            with self.subTest(owner=owner):
                self.changed()
                self.write(
                    "components/app1/route.conf",
                    "location /app1/ { return " + str(230 + self.sequence) + "; }\n",
                )
                self.write(
                    "home/app1/credentials/todo/todo-client.crt",
                    "-----BEGIN CERTIFICATE-----\n"
                    + base64.b64encode(str(self.sequence).encode("ascii")).decode()
                    + "\n-----END CERTIFICATE-----\n",
                )
                self.before = self.protected()
                self.attempt(expected=1, unhealthy=owner)
                self.assertEqual(set(self.pending()["owners"]), set(expected))
                self.assert_finished(self.attempt(), ["app1"] + expected)

    def test_unhealthy_first_install_writes_no_marker_and_the_retry_finishes(self):
        (common.STATE / "installed/app1").unlink()
        (common.STATE / "metadata/app1.json").unlink()
        self.attempt(expected=1, unhealthy="app1")
        self.assertTrue((common.STATE / "metadata/app1.json").is_file())
        self.assertFalse((common.STATE / "installed/app1").exists())
        self.attempt()
        self.assertTrue((common.STATE / "installed/app1").is_file())

    def test_import_failure_rebuilds_actual_archives_with_identical_registrations(self):
        self.changed()
        old = (common.STATE / "identity/files/identity-clients.tar").read_bytes()
        self.attempt(expected=1, archive_failure="identity")
        self.assertEqual(
            (common.STATE / "identity/files/identity-clients.tar").read_bytes(), old
        )
        self.assert_finished(self.attempt(), ["app1", "identity", "platform"])
        self.assertNotEqual(
            (common.STATE / "identity/files/identity-clients.tar").read_bytes(), old
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
        (common.STATE / "clients/app1/client.crt").unlink()
        self.attempt(expected=1, write_failure="clients/app1/client.crt")
        self.assert_finished(self.attempt(), ["app1", "identity", "platform"])
        self.assert_imports(True)

    def test_identity_install_records_resume_before_publishing_completion(self):
        """Metadata is written before registrations and services; the marker last."""
        # Start without installed dependents, as on a first Identity installation.
        for component in ("app1", "app2"):
            (common.STATE / "installed" / component).unlink()
        self.before = self.protected()
        marker = common.STATE / "installed/identity"
        metadata = common.STATE / "metadata/identity.json"
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
                        self.write("components/identity/VERSION", "1.2.0\n")
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
                            # Even after every owner is acknowledged, a failed
                            # completion-marker write must leave the attempt open.
                            self.assertEqual(self.pending()["component"], "identity")
                            self.assertEqual(self.pending()["owners"], [])
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
        self.write("components/platform/VERSION", "1.2.0\n")
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
        self.assertFalse((common.STATE / "installed/app1").exists())
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
        self.assertFalse((common.STATE / "app1").exists())
        self.assertFalse((common.STATE / "pending-operation.json").exists())
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
        self.assertFalse((common.STATE / "pending-operation.json").exists())
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
        self.assertFalse((common.STATE / "installed/app1").exists())
        self.assertFalse((common.STATE / "app1").exists())
        self.assertEqual(self.pending()["owners"], [])
        events = self.attempt("uninstall", delete_data=True)
        self.assertNotIn(service("app1", "stop"), events)
        self.assertFalse(
            any(event[:3] == ["podman", "volume", "rm"] for event in events)
        )
        self.assertFalse((common.STATE / "pending-operation.json").exists())

    def test_unfinished_first_install_names_the_retry_for_uninstall(self):
        """A first install stays pending; uninstall points to the install retry."""
        (common.STATE / "installed/app1").unlink()
        (common.STATE / "metadata/app1.json").unlink()
        events = self.attempt(expected=1, failure=service("app1"))
        self.assertTrue((common.STATE / "metadata/app1.json").is_file())
        self.assertFalse((common.STATE / "installed/app1").exists())
        self.assertEqual(self.pending()["component"], "app1")
        self.assertEqual(self.pending()["owners"], [])
        events = self.attempt("uninstall", expected=1)
        self.assertEqual(events[-1][:2], ["error", "DeployError"])
        self.assertIn("Pending install for app1", events[-1][2])
        self.assertIn(
            "finish with that component's bundle: ./deploy.sh install", events[-1][2]
        )
        self.assertEqual([event for event in events if event[0] != "error"], [])
        self.attempt()
        self.assertTrue((common.STATE / "installed/app1").is_file())
        self.attempt("uninstall")
        self.assertFalse((common.STATE / "metadata/app1.json").exists())

    def test_flag_conflicts_installs_and_dependencies_refuse_during_uninstall(self):
        self.attempt("uninstall", expected=1, failure=service("app1", "stop"))
        before = (common.STATE / "pending-operation.json").read_bytes()
        for action, options in (
            ("uninstall", {"delete_data": True}),
            ("install", {}),
            ("init-config", {}),
        ):
            events = self.attempt(action, expected=1, **options)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0][0], "error")
            self.assertEqual(
                (common.STATE / "pending-operation.json").read_bytes(), before
            )
        self.select("identity")
        # Model an uninstalling dependency: start its pending record in a fresh fixture state.
        state = self.pending()
        state.update(component="identity", owners=[], volumes=[])
        (common.STATE / "pending-operation.json").write_text(json.dumps(state))
        self.select("app1")
        events = self.attempt(expected=1)
        self.assertIn("Pending uninstall for identity", events[0][-1])

    def test_uninstall_cannot_discard_pending_install_or_another_components_work(self):
        self.changed()
        self.attempt(expected=1, failure=service("app1"))
        before = (common.STATE / "pending-operation.json").read_bytes()
        self.attempt("uninstall", expected=1)
        self.select("identity")
        self.attempt(expected=1)
        self.assertEqual((common.STATE / "pending-operation.json").read_bytes(), before)

    def test_invalid_or_symlinked_pending_state_refuses_before_host_calls(self):
        path = common.STATE / "pending-operation.json"
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
        self.assertTrue((common.STATE / "pending-operation.json").exists())
        self.assertEqual(
            json.loads((self.root / "host-volumes.json").read_text()),
            ["app1-data", "app1-session"],
        )
        self.attempt("uninstall", delete_data=True)
        self.assertFalse((common.STATE / "pending-operation.json").exists())
