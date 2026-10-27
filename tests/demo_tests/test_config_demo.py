"""Explicit config layers and authoritative production state, without host operations."""

import shutil
from pathlib import Path

from deployment import common, deploy
from deployment import render as rendering

from demo_tests.demo_fixture import DEMO_COMPONENTS, write_descriptor
from helpers.config_fixture import ConfigFixture


class DemoConfigTests(ConfigFixture):
    def test_real_defaults_initialize_component_credentials_in_dev_and_production(self):
        """The same shipped host paths resolve beneath each fresh component state."""
        repo = Path(__file__).resolve().parents[2]
        self.write(
            "config/common.defaults.yaml",
            (repo / "config/common.defaults.yaml").read_bytes(),
        )
        for component in DEMO_COMPONENTS:
            source = repo / "components" / component / "config.defaults.yaml"
            if (source.parent / "files").exists():
                shutil.copytree(
                    source.parent / "files",
                    self.root / "components" / component / "files",
                )
            self.write(
                "components/" + component + "/config.defaults.yaml", source.read_bytes()
            )
            dev_source = source.with_name("config.dev.yaml")
            if dev_source.exists():
                self.write(
                    "components/" + component + "/config.dev.yaml",
                    dev_source.read_bytes(),
                )
            if not (self.root / "components" / component / "VERSION").exists():
                self.write("components/" + component + "/VERSION", "1.2.3\n")
            write_descriptor(self.root, component)
            target = common.STATE / component / "config.yaml"
            if target.exists():
                target.unlink()
            deploy.init_config(component)
            production = rendering.load_config(target)
            dev = rendering.component_defaults(component, dev=True)
            if component == "app1":
                self.assertEqual(production["DEMO_CONFIG_LAYER"], "defaults")
                self.assertEqual(dev["DEMO_CONFIG_LAYER"], "component-dev")
            else:
                self.assertNotIn("DEMO_CONFIG_LAYER", dev)
            for settings in (production, dev):
                paths = []
                for group in ("SECRET_FILES", "VOLUME_FILES"):
                    for entries in settings.get(group, {}).values():
                        paths.extend(
                            source["path"]
                            for source in entries
                            if "path" in source and not source["path"].startswith("../")
                        )
                # Private files live under credentials/; app3's public CA chain
                # uses backlog 70's documented cert/ directory.
                self.assertTrue(
                    all(
                        path.startswith("credentials/") or path == "cert"
                        for path in paths
                    )
                )
            self.assertEqual(production.get("SECRET_FILES"), dev.get("SECRET_FILES"))
