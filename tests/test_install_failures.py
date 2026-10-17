"""Observe real component install state at image and service failure boundaries."""

import subprocess

import yaml
from test_components import ComponentFixture

from deployment import common, deploy


class InstallFailureTests(ComponentFixture):
    """Upgrade an installed app/platform while keeping a sibling's private state."""

    def setUp(self):
        super().setUp()
        self.registration_fixture()
        for component in ("platform", "app1"):
            path = common.HOME / component / "config.yaml"
            config = yaml.safe_load(path.read_text())
            config["VOLUME_FILES"] = {component + "-payload": [{"path": "payload"}]}
            config["SECRET_FILES"] = {
                component + "-private": [
                    {"path": "private", "generate": ["credential"]}
                ]
            }
            path.write_text(yaml.safe_dump(config))
            manifest = common.ROOT / "components" / component / "manifests/10-pod.yaml"
            pod = yaml.safe_load(manifest.read_text())
            pod["spec"]["containers"][0]["envFrom"] = [
                {"secretRef": {"name": component + "-private"}}
            ]
            # Keep the owner's registration import volume next to the payload.
            pod["spec"].setdefault("volumes", []).append(
                {
                    "name": "payload",
                    "persistentVolumeClaim": {"claimName": component + "-payload"},
                }
            )
            manifest.write_text(yaml.safe_dump(pod))
            self.write("home/" + component + "/payload", "old import")
            self.write(
                "home/" + component + "/private/credential", "retained secret\n", 0o600
            )
        for name in (
            "app2/config.yaml",
            "app2/credential",
            "app2/files/app2-data.tar",
            "routes/app2.conf",
            "clients/app2/client.json",
            "clients/app2/client.crt",
            "installed/app2",
            ".config/containers/systemd/myproduct-app2.yaml",
            ".config/containers/systemd/myproduct-app2.kube",
        ):
            self.write("home/" + name, "sibling fixture")
        # Staging reads each registered client's ID; installed app2 needs metadata.
        self.write("home/clients/app2/client.json", '{"Id": "app2"}')
        self.mark_installed("app2", "1.2.3")
        deploy.install()
        self.write("VERSION", "1.2.4\n")
        self.write("PLATFORM_VERSION", "1.1.0\n")
        self.select("app1")
        manifest = common.ROOT / "components/app1/manifests/10-pod.yaml"
        pod = yaml.safe_load(manifest.read_text())
        pod["metadata"]["name"] = "app1-new-worker"
        manifest.write_text(yaml.safe_dump(pod))
        self.write("home/app1/payload", "new import")
        self.before = self.snapshot()
        self.write("components/app1/route.conf", "location /app1/ { return 201; }\n")
        self.process.reset_mock()

    def snapshot(self):
        """Include contents and modes, and detect newly added/deleted files."""
        return {
            str(path.relative_to(common.HOME)): (path.read_bytes(), self.mode(path))
            for path in common.HOME.rglob("*")
            if path.is_file()
        }

    def fail_at(self, failure, exit_code=125):
        def command(args, **kwargs):
            if args == failure:
                raise subprocess.CalledProcessError(exit_code, args)

        (common.HOME / "routes/app1.conf").write_bytes(
            self.before["routes/app1.conf"][0]
        )
        self.process.side_effect = command

    def test_image_failures_leave_every_persistent_file_unchanged(self):
        """Load and both image checks must finish before live registration/archive writes."""
        failures = [
            ["podman", "load", "-i", str(common.ROOT / "images/images.tar")],
            ["podman", "image", "exists", "localhost/app1:1"],
        ]
        for failure in failures:
            for exit_code in (125,) if failure[1] == "load" else (1, 125):
                with self.subTest(command=failure, exit=exit_code):
                    self.process.reset_mock()
                    self.fail_at(failure, exit_code)
                    with self.assertRaises(
                        (common.DeployError, subprocess.CalledProcessError)
                    ):
                        deploy.install()
                    self.assertEqual(self.snapshot(), self.before)
                    calls = [call.args[0] for call in self.process.call_args_list]
                    self.assertEqual(calls[-1], failure)
                    self.assertTrue(all(args[0] == "podman" for args in calls))

    def test_platform_image_failure_preserves_existing_state(self):
        """The standalone platform upgrade has its own pre-write image boundary."""
        self.select("platform")
        failure = ["podman", "image", "exists", "localhost/platform:1"]
        for exit_code in (1, 125):
            with self.subTest(exit=exit_code):
                self.process.reset_mock()
                self.fail_at(failure, exit_code)
                with self.assertRaises(common.DeployError):
                    deploy.install()
                self.assertEqual(self.snapshot(), self.before)
                self.assertEqual(self.process.call_args_list[-1].args[0], failure)

    def test_service_failures_stop_with_new_files_but_old_version_markers(self):
        """No rollback exists: rendered files/imports commit before the first restart."""
        for component, operation in (
            ("app1", "restart"),
            ("app1", "is-active"),
            ("platform", "restart"),
            ("platform", "is-active"),
        ):
            with self.subTest(component=component, operation=operation):
                failure = ["systemctl", "--user", operation]
                if operation == "is-active":
                    failure.append("--quiet")
                failure.append("myproduct-" + component + ".service")
                self.process.reset_mock()
                self.fail_at(failure)
                with self.assertRaises(subprocess.CalledProcessError):
                    deploy.install()
                after = self.snapshot()
                for name, value in self.before.items():
                    if (
                        "app2" in name
                        or name.startswith(("installed/", "clients/"))
                        or name.endswith(("config.yaml", "credential"))
                    ):
                        self.assertEqual(after[name], value, name)
                self.assertIn(
                    "app1-new-worker", deploy.component_paths("app1")[2].read_text()
                )
                self.assertNotEqual(
                    after["app1/files/app1-payload.tar"],
                    self.before["app1/files/app1-payload.tar"],
                )
                self.assertIn(
                    "return 201", (common.HOME / "routes/app1.conf").read_text()
                )
                calls = [call.args[0] for call in self.process.call_args_list]
                self.assertEqual(calls[-1], failure)
                expected = [
                    ["systemctl", "--user", "restart", "myproduct-app1.service"]
                ]
                if component == "platform":
                    expected.append(
                        ["systemctl", "--user", "restart", "myproduct-platform.service"]
                    )
                self.assertEqual(
                    [
                        args
                        for args in calls
                        if args[:3] == ["systemctl", "--user", "restart"]
                    ],
                    expected,
                )
                self.assertNotIn(["podman", "ps", "--all", "--pod"], calls)
