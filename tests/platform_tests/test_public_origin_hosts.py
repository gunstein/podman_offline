"""Host /etc/hosts entries stay out of the containers (backlog 76).

A host that maps the public host name to loopback must not hand that line to
the containers: they resolve the name to the proxy in the product network.
Both start paths (source dev and installed Quadlet units) therefore run
`podman kube play --no-hosts`, and hostAliases, which conflicts with it, is
refused before anything is written.
"""

import copy
from pathlib import Path
from unittest import mock

import bundle
import yaml
from deployment import cli, common, deploy

from helpers.product_fixture import ProductFixture, pod

REPO = Path(__file__).resolve().parents[2]


class NoHostsTests(ProductFixture):
    def setUp(self):
        super().setUp()
        self.job = pod("processor-job", "localhost/worker:1")
        self.write_product({"processor": {"catalog": {}, "manifests": [self.job]}})
        self.manifest = self.source / "components/processor/manifests/10-resources.yaml"

    def snapshot(self):
        return {
            str(path.relative_to(self.root)): (
                path.stat().st_mode,
                path.read_bytes() if path.is_file() else None,
            )
            for path in self.root.rglob("*")
        }

    def test_installed_units_run_kube_play_without_host_entries(self):
        text = deploy.quadlet_text(".kube", self.product_name, "myproduct-processor")
        section, options = None, {}
        for line in text.splitlines():
            if line.startswith("["):
                section = line
            elif section == "[Kube]" and "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                options.setdefault(key, []).append(value)
        self.assertEqual(options["PodmanArgs"], ["--no-hosts"])
        self.assertEqual(options["Yaml"], ["myproduct-processor.yaml"])

    def test_source_dev_runs_kube_play_without_host_entries(self):
        plays = [
            line.split()
            for line in (REPO / "dev/dev.sh").read_text().splitlines()
            if line.strip().startswith("podman kube play")
        ]
        self.assertEqual(len(plays), 1)
        self.assertIn("--no-hosts", plays[0])

    def test_host_aliases_refused_before_side_effects(self):
        deploy.prepare()
        broken = copy.deepcopy(self.job)
        broken["spec"]["hostAliases"] = [
            {"ip": "192.0.2.10", "hostnames": ["private-host.example.test"]}
        ]
        self.manifest.write_text(yaml.safe_dump_all([broken]))
        before = self.snapshot()
        self.process.reset_mock()
        with mock.patch.object(cli.sys, "argv", ["deploy.sh", "validate"]):
            self.assertEqual(cli.main(), 1)
        error = self.stderr.getvalue()
        self.assertIn("10-resources.yaml", error)
        self.assertIn("spec.hostAliases is not supported", error)
        self.assertNotIn("private-host.example.test", error)
        with self.assertRaisesRegex(common.DeployError, "hostAliases"):
            deploy.prepare()
        with self.assertRaisesRegex(bundle.BundleError, "hostAliases"):
            bundle.build()
        self.assertEqual(self.commands(), [])
        self.assertEqual(self.snapshot(), before)
