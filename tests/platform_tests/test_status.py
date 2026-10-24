"""Read-only installed status, independent of release defaults and pending work."""

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Tuple
from unittest import mock

from deployment import catalog, cli, common, layout, registrations, status

from helpers.product_fixture import ProductFixture, pod


def snapshot(root):
    return {
        str(path.relative_to(root)): (
            path.stat().st_mode,
            path.read_bytes() if path.is_file() else None,
        )
        for path in root.rglob("*")
    }


class StatusTests(ProductFixture):
    def setUp(self):
        super().setUp()
        self.product_name = "cedar"
        self.write_product(
            {
                "a-worker": {
                    "catalog": {"requires": ["z-hub"]},
                    "manifests": [pod("a-worker-job", "localhost/worker:1")],
                },
                "z-hub": {
                    "catalog": {},
                    "manifests": [pod("z-hub-job", "localhost/hub:1")],
                },
            }
        )
        (self.source / "components/z-hub/VERSION").write_text("2.0.0\n")
        self.descriptors = catalog.source_descriptors(self.source)
        releases = self.build_and_unpack()
        self.use_root(releases["a-worker"])
        self.other_release = releases["z-hub"]
        common.STATE.mkdir(exist_ok=True)
        self.responses = {}
        self.process.reset_mock()
        self.process.side_effect = self.query
        self.stack.enter_context(
            mock.patch.dict("os.environ", {"HOME": str(common.HOME)})
        )

    def query(self, args, **kwargs):
        self.assertEqual(args[:3], ["systemctl", "--user", "is-active"])
        self.assertEqual(len(args), 4)
        self.assertFalse(kwargs["check"])
        self.assertEqual(kwargs["timeout"], 10)
        response = self.responses.get(args[3], (0, "active\n"))
        if isinstance(response, Exception):
            raise response
        code, text = response
        return subprocess.CompletedProcess(args, code, text, "PrivateBusDiagnostic")

    def installed(self, name, version, marker=True):
        descriptor = copy.deepcopy(self.descriptors[name])
        descriptor["version"] = version
        path = catalog.metadata_path(common.STATE, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(descriptor))
        if marker:
            path = common.STATE / "installed" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(version + "\n")
        return descriptor

    def invoke(self, json_output=True) -> Tuple[int, Any]:  # noqa: FA100 - Python 3.6
        before = snapshot(self.root)
        original = Path.open

        def guarded(path, *args, **kwargs):
            if "credentials" in path.parts or path.name == "config.yaml":
                raise AssertionError("status read config or credentials")
            return original(path, *args, **kwargs)

        self.stdout.seek(0)
        self.stdout.truncate()
        self.process.reset_mock()
        with mock.patch.object(layout, "check_user_manager") as manager:
            try:
                with mock.patch.object(Path, "open", guarded):
                    result = status.status(json_output=json_output)
            finally:
                manager.assert_not_called()
                self.assertEqual(snapshot(self.root), before)
        output = self.stdout.getvalue()
        self.assertNotIn("PrivateBusDiagnostic", output)
        return result, json.loads(output) if json_output else output

    def test_versions_order_text_json_and_no_config_or_credential_reads(self):
        # Completed state, not the incoming bundle's 1.0.0 version, is authoritative.
        shutil.rmtree(self.source)
        shutil.rmtree(self.other_release)
        self.installed("a-worker", "4.5.6")
        self.installed("z-hub", "2.3.4")
        secret = common.STATE / "a-worker/credentials/password"
        secret.parent.mkdir(parents=True)
        secret.write_bytes(b"DoNotReadOrDisplay")
        code, report = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(report["product"], "cedar")
        self.assertIsNone(report["pending"])
        self.assertEqual(
            report["components"],
            [
                {
                    "name": "z-hub",
                    "version": "2.3.4",
                    "recorded_version": "2.3.4",
                    "unit": "cedar-z-hub.service",
                    "complete": True,
                    "state": "active",
                },
                {
                    "name": "a-worker",
                    "version": "4.5.6",
                    "recorded_version": "4.5.6",
                    "unit": "cedar-a-worker.service",
                    "complete": True,
                    "state": "active",
                },
            ],
        )
        self.assertEqual(
            [call.args[0] for call in self.process.call_args_list],
            [
                ["systemctl", "--user", "is-active", "cedar-z-hub.service"],
                ["systemctl", "--user", "is-active", "cedar-a-worker.service"],
            ],
        )
        code, text = self.invoke(json_output=False)
        self.assertEqual(code, 0)
        self.assertIn("z-hub 2.3.4 cedar-z-hub.service active installed", text)
        self.assertIn("a-worker 4.5.6 cedar-a-worker.service active installed", text)
        self.assertIn("Product: cedar\nPending: none", text)
        self.assertNotIn("DoNotReadOrDisplay", text)

    def test_empty_installation_is_reported_without_commands(self):
        code, report = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(report["components"], [])
        self.process.assert_not_called()
        self.assertIn("No installed components.", self.invoke(False)[1])

    def test_unfinished_first_install_and_repair_are_visible(self):
        self.installed("z-hub", "2.3.4", marker=False)
        code, report = self.invoke()
        self.assertEqual(code, 1)
        self.assertIsNone(report["components"][0]["version"])
        self.assertFalse(report["components"][0]["complete"])
        self.assertIn("incomplete (recorded 2.3.4)", self.invoke(False)[1])
        self.installed("z-hub", "2.3.4")
        self.assertEqual(self.invoke()[0], 0)

    def test_upgrade_metadata_never_overwrites_the_reported_completed_version(self):
        self.installed("z-hub", "1.2.3")
        self.installed("z-hub", "2.3.4", marker=False)
        code, report = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(report["components"][0]["version"], "1.2.3")
        self.assertEqual(report["components"][0]["recorded_version"], "2.3.4")
        self.assertFalse(report["components"][0]["complete"])

    def test_pending_install_is_reported_without_acknowledgement(self):
        self.installed("z-hub", "2.3.4")
        pending = {
            "operation": "install",
            "component": "a-worker",
            "product": "cedar",
            "owners": ["z-hub"],
        }
        registrations.save_pending(pending)
        code, report = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(
            report["pending"],
            {"operation": "install", "component": "a-worker", "owners": ["z-hub"]},
        )
        self.assertIn("Pending: install a-worker; owners: z-hub", self.invoke(False)[1])
        self.assertEqual(registrations.load_pending(), pending)

    def test_pending_uninstall_survives_removal_of_component_metadata(self):
        registrations.save_pending(
            {
                "operation": "uninstall",
                "component": "a-worker",
                "product": "cedar",
                "owners": [],
                "delete_data": False,
                "volumes": [],
                "stopped": True,
            }
        )
        code, report = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(report["components"], [])
        self.assertEqual(report["pending"]["operation"], "uninstall")

    def test_failed_missing_and_unavailable_units_are_findings(self):
        self.installed("z-hub", "2.3.4")
        for response, expected in [
            ((3, "inactive\n"), "inactive"),
            ((3, "failed\n"), "failed"),
            ((4, "unknown\n"), "unknown"),
            ((0, "reloading\n"), "reloading"),
            ((1, ""), "unavailable"),
            ((3, "active\n"), "unavailable"),
            ((0, "PrivateOutput"), "unavailable"),
            ((0, "active\nfailed\n"), "unavailable"),
            (OSError("PrivateFailure"), "unavailable"),
            (subprocess.TimeoutExpired("PrivateArgs", 10), "unavailable"),
        ]:
            with self.subTest(expected=expected, response=repr(response)):
                self.responses["cedar-z-hub.service"] = response
                code, report = self.invoke()
                self.assertEqual(code, 1)
                self.assertEqual(report["components"][0]["state"], expected)
                self.assertNotIn("Private", json.dumps(report))

    def test_other_product_and_pending_product_refused_before_host_queries(self):
        descriptor = self.installed("z-hub", "2.3.4")
        path = catalog.metadata_path(common.STATE, "z-hub")
        descriptor["product"] = "another"
        path.write_text(json.dumps(descriptor))
        with self.assertRaisesRegex(common.DeployError, "already runs product another"):
            self.invoke()
        self.process.assert_not_called()
        descriptor["product"] = "cedar"
        path.write_text(json.dumps(descriptor))
        registrations.save_pending(
            {
                "operation": "install",
                "component": "a-worker",
                "product": "another",
                "owners": ["z-hub"],
            }
        )
        with self.assertRaisesRegex(common.DeployError, "another product"):
            self.invoke()
        self.process.assert_not_called()

    def test_invalid_or_linked_markers_and_orphans_are_refused_without_values(self):
        self.installed("z-hub", "2.3.4")
        marker = common.STATE / "installed/z-hub"
        secret = common.STATE / "credentials/password"
        secret.parent.mkdir()
        secret.write_text("PrivateVersion")
        for mode in ("invalid", "link", "directory", "orphan"):
            with self.subTest(mode=mode):
                if marker.is_dir():
                    marker.rmdir()
                elif marker.exists() or marker.is_symlink():
                    marker.unlink()
                if mode == "link":
                    marker.symlink_to(secret)
                elif mode == "directory":
                    marker.mkdir()
                else:
                    marker.write_text("PrivateVersion")
                if mode == "orphan":
                    catalog.metadata_path(common.STATE, "z-hub").unlink()
                with self.assertRaises(common.DeployError) as error:
                    self.invoke()
                self.assertNotIn("PrivateVersion", str(error.exception))
                self.process.assert_not_called()

    def test_cli_exit_codes_arguments_and_source_refusal(self):
        self.installed("z-hub", "2.3.4")
        for arguments, expected in [
            (["status"], 0),
            (["status", "--json"], 0),
            (["status", "worker"], 2),
            (["status", "--delete-data"], 2),
            (["status", "--json", "--json"], 2),
        ]:
            with mock.patch.object(cli.sys, "argv", ["deploy.sh"] + arguments):
                self.assertEqual(cli.main(), expected)
        self.responses["cedar-z-hub.service"] = (3, "failed\n")
        with mock.patch.object(cli.sys, "argv", ["deploy.sh", "status"]):
            self.assertEqual(cli.main(), 1)
        self.use_root(self.source)
        with self.assertRaisesRegex(common.DeployError, "unpacked component bundle"):
            status.collect()
