"""Explicit config layers and authoritative production state, without host operations."""

from helpers.component_fixture import ComponentFixture


class ConfigFixture(ComponentFixture):
    def setUp(self):
        """Provide deliberately different common and component values."""
        super().setUp()
        self.write(
            "config/common.defaults.yaml",
            "PUBLIC_ORIGIN: https://defaults.test:8443\nHTTPS_PORT: 8443\nCHOICE: common\n",
        )
        for name in ("platform", "identity", "app1"):
            self.write(
                "components/" + name + "/config.defaults.yaml", "CHOICE: component\n"
            )
