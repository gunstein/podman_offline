"""Explicit config layers and authoritative production state, without host operations."""

from helpers.component_fixture import ComponentFixture


class ConfigFixture(ComponentFixture):
    def setUp(self):
        """Provide component defaults; platform's hold the public settings."""
        super().setUp()
        self.write(
            "components/platform/config.defaults.yaml",
            "PUBLIC_ORIGIN: https://defaults.test:8443\nHTTPS_PORT: 8443\n"
            "CHOICE: component\n",
        )
        for name in ("identity", "app1"):
            self.write(
                "components/" + name + "/config.defaults.yaml", "CHOICE: component\n"
            )
