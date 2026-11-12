"""Test component namespace and rootless isolation without Podman or systemd."""

import shutil
import subprocess
from pathlib import Path
from unittest import mock

import yaml
from deployment import common, deploy
from deployment import render as rendering

from demo_tests.demo_fixture import (
    DEMO_COMPONENTS,
    DEMO_PUBLIC,
    write_secret_fixtures,
)
from helpers.component_fixture import ComponentFixture


class DemoComponentTests(ComponentFixture):
    def test_dev_host_helper_imports_package_and_preflights_before_writes(self):
        repo = Path(__file__).resolve().parents[2]
        shutil.rmtree(self.root / "components")
        shutil.copytree(repo / "components", self.root / "components")
        shutil.copytree(
            repo / "config",
            self.root / "config",
            ignore=shutil.ignore_patterns("dev.yaml"),
        )
        for name in ("bundles.yaml",):
            shutil.copy2(repo / name, self.root / name)
        helper = (
            (repo / "dev/demo-credentials.sh")
            .read_text()
            .split("<<'DEMO_HOST'\n", 1)[1]
            .split("\nDEMO_HOST", 1)[0]
        )
        self.process.return_value = subprocess.CompletedProcess([], 1)
        exec(compile(helper, "dev/demo-credentials.sh:DEMO_HOST", "exec"), {})  # noqa: S102 - repository helper under test
        self.assertIn("myproduct-proxy", self.stdout.getvalue())
        self.assertFalse((common.BUILD / "dev").exists())
        self.assertEqual(len(self.process.call_args_list), 3)
        self.assertTrue(
            all(
                call.args[0][:3] == ["podman", "volume", "exists"]
                for call in self.process.call_args_list
            )
        )

    def test_certificates_and_deployment_resolve_one_exported_host_name(self):
        """Backlog 86: demo-credentials.sh's host name is dev_settings' resolved origin."""
        repo = Path(__file__).resolve().parents[2]
        shutil.rmtree(self.root / "components")
        shutil.copytree(repo / "components", self.root / "components")
        shutil.copytree(
            repo / "config",
            self.root / "config",
            ignore=shutil.ignore_patterns("dev.yaml"),
        )
        shutil.copy2(repo / "bundles.yaml", self.root / "bundles.yaml")
        self.write("config/dev.yaml", "PUBLIC_ORIGIN: 'https://@@$HOSTNAME@@:8443'\n")
        helper = (
            (repo / "dev/demo-credentials.sh")
            .read_text()
            .split("<<'DEMO_HOST'\n", 1)[1]
            .split("\nDEMO_HOST", 1)[0]
        )
        self.process.return_value = subprocess.CompletedProcess([], 1)
        with mock.patch.object(common, "ENVIRON", {"HOSTNAME": "dev.example"}):
            exec(compile(helper, "dev/demo-credentials.sh:DEMO_HOST", "exec"), {})  # noqa: S102 - repository helper under test
            _, settings, _ = deploy.dev_settings()
        self.assertEqual(self.stdout.getvalue().split()[-1], "dev.example")
        for component, config in settings.items():
            if "PUBLIC_ORIGIN" in config:
                self.assertEqual(
                    config["PUBLIC_ORIGIN"], "https://dev.example:8443", component
                )
        # Unexported: the helper stops before any certificate is issued.
        with mock.patch.object(common, "ENVIRON", {}):
            with self.assertRaisesRegex(
                common.DeployError, "environment variable HOSTNAME is not set"
            ):
                exec(compile(helper, "dev/demo-credentials.sh:DEMO_HOST", "exec"), {})  # noqa: S102 - repository helper under test
        self.assertFalse((common.BUILD / "dev").exists())

    def test_dev_prepare_uses_dev_state_instead_of_service_home(self):
        """Render all real components without reading or writing the account's prod state."""
        (self.root / "bundle.yaml").unlink()
        shutil.rmtree(self.root / "components")
        repo = Path(__file__).resolve().parents[2]
        shutil.copytree(repo / "components", self.root / "components")
        for name in ("bundles.yaml",):
            shutil.copy2(repo / name, self.root / name)
        shutil.copytree(
            repo / "config",
            self.root / "config",
            ignore=shutil.ignore_patterns("dev.yaml"),
        )
        self.write(
            "config/dev.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\nIP_ADDRESS: 127.0.0.1\n",
        )
        for component in DEMO_COMPONENTS:
            config = rendering.merge_config(
                repo / "components" / component / "config.defaults.yaml",
                overrides=DEMO_PUBLIC,
            )
            for group in ("SECRET_FILES", "VOLUME_FILES"):
                for entries in config.get(group, {}).values():
                    for source in entries:
                        if "component_file" in source:
                            continue
                        entry = source["path"]
                        if ".." not in Path(entry).parts:
                            self.write(
                                "build/dev/" + component + "/" + entry + "/dummy",
                                b"dummy",
                            )
            write_secret_fixtures(
                self.root / "build/dev" / component, config, component
            )
            if component.startswith("app"):
                certificate = yaml.safe_load(
                    (repo / "components" / component / "client.yaml").read_text()
                )["certificate"]
                self.write(
                    "build/dev/" + component + "/" + certificate,
                    "-----BEGIN CERTIFICATE-----\nY2VydA==\n-----END CERTIFICATE-----\n",
                )
        for component, relative in (
            ("identity", "identity-db"),
            ("app1", "database"),
            ("app2", "database"),
        ):
            self.write(
                "build/dev/" + component + "/credentials/" + relative + "/password",
                b"retained-db-password\n",
            )
        before = (common.STATE / "app1/config.yaml").read_bytes()
        deploy.prepare()
        self.assertEqual((common.STATE / "app1/config.yaml").read_bytes(), before)
        self.assertTrue((common.BUILD / "dev/clients/app2/client.json").exists())
        docs = list(yaml.safe_load_all((common.BUILD / "install.yaml").read_text()))
        self.assertEqual(sum(doc["kind"] == "Pod" for doc in docs), 9)
        proxy = next(
            doc
            for doc in docs
            if doc.get("kind") == "Pod" and doc["metadata"]["name"] == "platform-proxy"
        )
        self.assertEqual(proxy["spec"]["hostname"], "example.test")
        self.process.assert_not_called()
