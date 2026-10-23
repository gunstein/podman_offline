"""Test component namespace and rootless isolation without Podman or systemd."""

import shutil
import subprocess
from pathlib import Path

import yaml
from deployment import common, deploy
from deployment import render as rendering

from demo_tests.demo_fixture import (
    DEMO_COMPONENTS,
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
                repo / "config/common.defaults.yaml",
                repo / "components" / component / "config.defaults.yaml",
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
                self.write(
                    "build/dev/" + component + "/credentials/todo/todo-client.crt",
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
        self.assertEqual(sum(doc["kind"] == "Pod" for doc in docs), 8)
        proxy = next(
            doc
            for doc in docs
            if doc.get("kind") == "Pod" and doc["metadata"]["name"] == "platform-proxy"
        )
        self.assertEqual(proxy["spec"]["hostname"], "example.test")
        self.process.assert_not_called()
