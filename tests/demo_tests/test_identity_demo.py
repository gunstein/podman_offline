"""Identity ownership, independent registration restarts, dependencies and scoped deletion."""

from pathlib import Path

from deployment import render as rendering

from demo_tests.demo_fixture import DEMO
from helpers.component_fixture import ComponentFixture


class DemoIdentityTests(ComponentFixture):
    def test_identity_owns_database_signing_and_clients_and_proxy_has_no_fixed_identity(
        self,
    ):
        repo = Path(__file__).resolve().parents[2]
        platform = rendering.merge_config(
            repo / "config/common.defaults.yaml",
            repo / "components/platform/config.defaults.yaml",
        )
        identity = rendering.merge_config(
            repo / "config/common.defaults.yaml",
            repo / "components/identity/config.defaults.yaml",
        )
        self.assertFalse(any(name.startswith("DB_") for name in platform))
        self.assertNotIn("GENERATED_SECRETS", platform)
        # The catalog, not the config, names each owner's registration volume.
        self.assertNotIn("VOLUME_FILES", platform)
        self.assertNotIn("VOLUME_FILES", identity)
        self.assertEqual(DEMO["platform"]["accepts"], {"routes": "platform-routes"})
        self.assertEqual(
            DEMO["identity"]["accepts"],
            {"clients": "identity-clients", "apis": "identity-apis"},
        )
        self.assertEqual(identity["DB_HOST"], "identity-postgres")
        self.assertEqual(identity["DB_USER"], "identity")
        proxy = rendering.load_yaml_all(
            repo / "components/platform/manifests/20-proxy-config.yaml"
        )[0]
        self.assertNotIn("/identity/", proxy["data"]["default.conf.template"])
        route = (repo / "components/identity/route.conf").read_text()
        self.assertIn("location /identity/", route)
        self.assertIn("set $identity_upstream identity-server:8080", route)
        self.assertIn("proxy_pass http://$identity_upstream", route)
