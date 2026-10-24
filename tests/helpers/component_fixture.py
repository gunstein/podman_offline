"""Test component namespace and rootless isolation without Podman or systemd."""

from pathlib import Path

import yaml
from deployment import catalog, common, deploy

from helpers.catalog_fixture import (
    DEMO,
    mark_installed,
    write_descriptor,
)
from helpers.deploy_fixture import DeployFixture, document


class ComponentFixture(DeployFixture):
    """Exercise independent component services with temporary persistent state."""

    def setUp(self):
        """Create a minimal app1 release and two persistent configs."""
        super().setUp()
        for component in ("app1", "app2", "help"):
            self.write("components/" + component + "/VERSION", "1.2.3\n")
        self.write("components/platform/VERSION", "1.0.0\n")
        self.write("components/identity/VERSION", "1.0.0\n")
        self.write(
            "quadlet/template.kube",
            "[Kube]\nYaml=@@UNIT_NAME@@.yaml\nNetwork=@@PRODUCT_NAME@@.network\n",
        )
        self.write(
            "quadlet/template.network", "[Network]\nNetworkName=@@PRODUCT_NAME@@\n"
        )
        self.write("images/images.tar")
        for component in ("platform", "identity", "app1"):
            self.write(
                "home/" + component + "/config.yaml",
                "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\n",
            )
            self.component_manifest(component)

        self.select("platform")
        deploy.install()
        self.select("identity")
        deploy.install()
        self.select("app1")
        self.process.reset_mock()

    def select(self, component, **changes):
        """Unpack the demo component's compiled descriptor as this release's bundle.yaml."""
        return write_descriptor(self.root, component, **changes)

    def mark_installed(self, component, version):
        """Record a completed install of a component this test does not install."""
        mark_installed(self.root, common.STATE, component, version)
        return common.STATE / "installed" / component

    def known(self):
        """Installed metadata plus the selected bundle, as install_components builds it."""
        known = catalog.load_installed_metadata(common.STATE)
        descriptor = deploy.bundle_descriptor()
        known[descriptor["name"]] = descriptor
        return known

    def component_manifest(self, component, name=None):
        """Write a prefixed Pod with one prepared image; owners mount their imports."""
        spec = {
            "containers": [
                {
                    "name": "app",
                    "image": "localhost/" + component + ":1",
                    "imagePullPolicy": "Never",
                }
            ]
        }
        if component in ("app1", "app2"):
            # Matches the demo client.yaml, which names APP_ID and BASE_PATH.
            spec["containers"][0]["env"] = [
                {"name": "APP_ID", "value": component},
                {"name": "BASE_PATH", "value": "/" + component},
            ]
        accepts = DEMO.get(component, {}).get("accepts", {})
        if accepts:
            spec["volumes"] = [
                {"name": role, "persistentVolumeClaim": {"claimName": volume}}
                for role, volume in sorted(accepts.items())
            ]
        return self.write(
            "components/" + component + "/manifests/10-pod.yaml",
            yaml.safe_dump(document("Pod", name or component + "-worker", spec=spec)),
        )

    def imports_fixture(self):
        """Reinstall both owners in a newer version; they import current registrations."""
        for component in ("platform", "identity"):
            self.write("components/" + component + "/VERSION", "1.1.0\n")
            self.select(component)
            deploy.install()
        self.select("app1")

    def registration_fixture(self):
        """Create matching origins, a public client descriptor and a synthetic PEM."""
        for component in ("platform", "app1"):
            self.write(
                "home/" + component + "/config.yaml",
                "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\n",
            )
        source = (
            Path(__file__).resolve().parents[1] / "fixtures/catalog/components/app1"
        )
        for name in ("route.conf", "client.yaml"):
            self.write("components/app1/" + name, (source / name).read_bytes())
        self.select("app1")
        self.write(
            "home/app1/credentials/todo/todo-client.crt",
            "-----BEGIN CERTIFICATE-----\nY2VydA==\n-----END CERTIFICATE-----\n",
        )
        work = self.root / "registration-stage"
        work.mkdir()
        return work
