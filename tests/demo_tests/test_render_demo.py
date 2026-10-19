"""Isolated renderer/installer tests; no Podman, systemd, root or network."""

from pathlib import Path

import yaml
from deployment import render as rendering

from demo_tests.demo_fixture import DEMO, DEMO_COMPONENTS, write_secret_fixtures
from helpers.deploy_fixture import DeployFixture
from helpers.render_helper import materialize_and_render


class DemoRenderTests(DeployFixture):
    def test_real_product_manifests_render_with_dummy_files(self):
        """Render the demo manifests with merged defaults and local dummy files."""
        repo = Path(__file__).resolve().parents[2]
        docs = []
        for component in DEMO_COMPONENTS:
            config = rendering.merge_config(
                repo / "config/common.defaults.yaml",
                repo / "components" / component / "config.defaults.yaml",
            )
            base = self.root / "state" / component
            for group in ("SECRET_FILES", "VOLUME_FILES"):
                for paths in config.get(group, {}).values():
                    for source in paths:
                        target = base / source["path"]
                        target.mkdir(parents=True, exist_ok=True)
                        (target / "dummy").write_bytes(b"dummy")
            write_secret_fixtures(base, config, component)
            path = self.write(
                "state/" + component + "/config.yaml", yaml.safe_dump(config)
            )
            # Registration owners always receive their declared import volume.
            imports = {
                volume: [self.write("state/imports/" + volume, "dummy")]
                for volume in DEMO[component]["accepts"].values()
            }
            text = materialize_and_render(
                base / "files",
                write_archives=False,
                config_path=path,
                manifests=repo / "components" / component / "manifests",
                component=component,
                extra_volumes=imports or None,
            )
            docs.extend(yaml.safe_load_all(text))
        kinds = [doc["kind"] for doc in docs]
        self.assertEqual(kinds.count("Pod"), 8)
        self.assertEqual(kinds.count("Secret"), 9)
        self.assertEqual(kinds.count("PersistentVolumeClaim"), 6)
        self.assertEqual(kinds.count("ConfigMap"), 5)
        self.assertEqual(len(rendering.find_images(docs)), 6)
        rendering.check_links(docs, {})
        self.process.assert_not_called()
