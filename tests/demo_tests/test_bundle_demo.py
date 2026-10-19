"""Build real bundle archives with only the Podman subprocess stubbed."""

import hashlib
import shutil
import tarfile
from pathlib import Path

import bundle
import yaml

from helpers.bundle_fixture import BundleFixture


class DemoBundleTests(BundleFixture):
    def test_actual_platform_bundle_ships_yaml_proxy_and_stock_image_with_checksums(
        self,
    ):
        repo = Path(__file__).resolve().parents[2]
        self.write(
            "bundles.yaml",
            "product: myproduct\ncomponents:\n  platform:\n"
            "    upgrade: newer-only\n    accepts: {routes: platform-routes}\n",
        )
        self.write(
            "config/common.defaults.yaml",
            (repo / "config/common.defaults.yaml").read_text(),
        )
        shutil.copytree(repo / "components/platform", self.root / "components/platform")
        self.write("components/platform/VERSION", "1.2.4\n")
        bundle.build()
        image = "docker.io/library/nginx:1.28-alpine"
        self.assertEqual(
            self.process.call_args_list[0].args[0],
            ["podman", "pull", "--policy=always", image],
        )
        self.assertEqual(self.process.call_args_list[1].args[0][-1], image)
        path = bundle.DIST / "myproduct-platform-1.2.4-offline.tar.gz"
        with tarfile.open(str(path)) as archive:
            prefix = "myproduct-platform-1.2.4/"
            images = archive.extractfile(prefix + "images/images.txt")
            assert images is not None
            with images:
                self.assertEqual(images.read().decode().splitlines(), [image])
            for filename in ("20-proxy-config.yaml", "80-proxy.yaml"):
                self.assertIn(
                    prefix + "components/platform/manifests/" + filename,
                    archive.getnames(),
                )
            self.assertFalse(any("apps/proxy" in name for name in archive.getnames()))
            checksums = archive.extractfile(prefix + "checksums.sha256")
            assert checksums is not None
            with checksums:
                rows = checksums.read().decode().splitlines()
            for row in rows:
                digest, filename = row.split("  ", 1)
                content = archive.extractfile(prefix + filename)
                assert content is not None
                with content:
                    self.assertEqual(hashlib.sha256(content.read()).hexdigest(), digest)

    def test_actual_app1_bundle_includes_init_image_once_and_retains_init_command(self):
        repo = Path(__file__).resolve().parents[2]
        # Only the app1 manifests matter here, so the catalog has no registrations.
        self.write("bundles.yaml", "product: myproduct\ncomponents:\n  app1: {}\n")
        self.write(
            "config/common.defaults.yaml",
            (repo / "config/common.defaults.yaml").read_text(),
        )
        shutil.copytree(repo / "components/app1", self.root / "components/app1")
        for name in ("route.conf", "client.yaml"):
            (self.root / "components/app1" / name).unlink()
        self.write("components/app1/VERSION", "1.2.3\n")
        bundle.build()
        image = "localhost/demo-todo-backend:0.2.2"
        with tarfile.open(
            str(bundle.DIST / "myproduct-app1-1.2.3-offline.tar.gz")
        ) as archive:
            prefix = "myproduct-app1-1.2.3/"
            image_list = archive.extractfile(prefix + "images/images.txt")
            assert image_list is not None
            with image_list:
                self.assertEqual(
                    image_list.read().decode().splitlines().count(image), 1
                )
            manifest = archive.extractfile(
                prefix + "components/app1/manifests/60-todo.yaml"
            )
            assert manifest is not None
            with manifest:
                pod = yaml.safe_load(manifest.read())
            init = pod["spec"]["initContainers"][0]
            self.assertEqual(init["image"], image)
            self.assertEqual(init["command"], ["python", "/app/schema.py"])
            self.assertEqual(init["imagePullPolicy"], "Never")
        save = next(
            call.args[0]
            for call in self.process.call_args_list
            if call.args[0][1] == "save"
        )
        self.assertEqual(save.count(image), 1)
