"""Isolated renderer/installer tests; no Podman, systemd, root or network."""

import shutil
from pathlib import Path

import yaml
from deployment import catalog
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
            source_files = repo / "components" / component / "files"
            if source_files.exists():
                shutil.copytree(
                    source_files, self.root / "components" / component / "files"
                )
            # ENVIRONMENT is read from the release's config.defaults.yaml.
            (self.root / "components" / component).mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                str(repo / "components" / component / "config.defaults.yaml"),
                str(self.root / "components" / component / "config.defaults.yaml"),
            )
            config = rendering.merge_config(
                repo / "config/common.defaults.yaml",
                repo / "components" / component / "config.defaults.yaml",
            )
            base = self.root / "state" / component
            for group in ("SECRET_FILES", "VOLUME_FILES"):
                for paths in config.get(group, {}).values():
                    for source in paths:
                        if "component_file" in source:
                            continue
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
                for volume in catalog.imported_volumes(DEMO[component])
            }
            # The owner's API Secret, as registrations.owner_secrets renders it.
            secrets = [
                {
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "metadata": {"name": name},
                    "data": {"ApiResources__0__ApiSecrets__0__Value": "ZHVtbXk="},
                }
                for name in catalog.imported_secrets(DEMO[component])
            ]
            text = materialize_and_render(
                base / "files",
                write_archives=False,
                config_path=path,
                manifests=repo / "components" / component / "manifests",
                component=component,
                extra_volumes=imports or None,
                extra_secrets=secrets,
            )
            docs.extend(yaml.safe_load_all(text))
        kinds = [doc["kind"] for doc in docs]
        self.assertEqual(kinds.count("Pod"), 9)
        # app3's API secret and recipe, and Identity's registration Secret (72).
        self.assertEqual(kinds.count("Secret"), 14)
        self.assertEqual(kinds.count("PersistentVolumeClaim"), 8)
        self.assertEqual(kinds.count("ConfigMap"), 6)
        self.assertEqual(len(rendering.find_images(docs)), 8)
        rendering.check_links(docs, {})
        self.process.assert_not_called()
