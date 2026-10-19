"""Explicit config layers and authoritative production state, without host operations."""

from pathlib import Path

from deployment import common, deploy
from deployment import render as rendering

from demo_tests.demo_fixture import DEMO_COMPONENTS
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
            self.write(
                "components/" + component + "/config.defaults.yaml", source.read_bytes()
            )
            self.select(component)
            target = common.HOME / component / "config.yaml"
            if target.exists():
                target.unlink()
            deploy.init_config(component)
            production = rendering.load_config(target)
            dev = rendering.component_defaults(component, dev=True)
            for settings in (production, dev):
                paths = []
                for group in ("SECRET_FILES", "VOLUME_FILES"):
                    for entries in settings.get(group, {}).values():
                        paths.extend(
                            source["path"]
                            for source in entries
                            if not source["path"].startswith("../")
                        )
                self.assertTrue(all(path.startswith("credentials/") for path in paths))
            self.assertEqual(production.get("SECRET_FILES"), dev.get("SECRET_FILES"))
