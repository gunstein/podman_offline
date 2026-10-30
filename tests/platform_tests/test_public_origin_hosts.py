"""Host /etc/hosts entries stay out of the containers (backlog 76).

A host that maps the public host name to loopback must not hand that line to
the containers: they resolve the name to the proxy in the product network.
Both start paths select the bundled hosts-policy override. Tests exercise dev
command scoping and relocated offline installs, with Podman transport stubbed;
they do not establish that Podman generates localhost entries at runtime.
"""

import configparser
import copy
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import bundle
import yaml
from deployment import cli, common, deploy, validation

from helpers.product_fixture import ProductFixture, pod

REPO = Path(__file__).resolve().parents[2]
REAL_RUN = subprocess.run


class HostsPolicyTests(ProductFixture):
    def setUp(self):
        super().setUp()
        self.job = pod("processor-job", "localhost/worker:1")
        self.write_product({"processor": {"catalog": {}, "manifests": [self.job]}})
        self.manifest_path = (
            self.source / "components/processor/manifests/10-resources.yaml"
        )

    def snapshot(self):
        return {
            str(path.relative_to(self.root)): (
                path.stat().st_mode,
                path.read_bytes() if path.is_file() else None,
            )
            for path in self.root.rglob("*")
        }

    def override_from_unit(self, text):
        unit = configparser.ConfigParser(interpolation=None)
        unit.read_string(text)
        self.assertNotIn("--no-hosts", unit.get("Kube", "PodmanArgs", fallback=""))
        (assignment,) = shlex.split(unit["Service"]["Environment"])
        key, value = assignment.split("=", 1)
        self.assertEqual(key, "CONTAINERS_CONF_OVERRIDE")
        return Path(value.replace("%%", "%"))

    def check_policy(self, path):
        # The shipped fragment uses only the shared INI/TOML subset. Keep this
        # test compatible with Python 3.6 without adding a runtime TOML parser.
        config = configparser.ConfigParser()
        config.read(str(path))
        self.assertEqual(config["containers"]["base_hosts_file"], '"none"')
        self.assertFalse(config.getboolean("containers", "no_hosts"))

    def test_relocated_bundle_uses_its_own_policy_without_user_config_writes(self):
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        relocated = self.root / "relocated releases"
        shutil.move(str(self.releases), str(relocated))
        release = relocated / releases["processor"].name
        user_config = self.write("home/.config/containers/containers.conf", "retained")
        self.install(release)
        unit = common.QUADLET_DIR / "myproduct-processor.kube"
        policy = self.override_from_unit(unit.read_text())
        self.assertEqual(policy, release / "quadlet/containers-hosts.conf")
        self.check_policy(policy)
        self.assertIn(
            "quadlet/containers-hosts.conf", (release / "checksums.sha256").read_text()
        )
        self.assertEqual(user_config.read_text(), "retained")
        self.assertEqual(self.restarts(), ["processor"])

    def test_missing_or_symlinked_policy_is_refused_before_prepare_effects(self):
        deploy.prepare()
        policy = self.source / "quadlet/containers-hosts.conf"
        saved = policy.read_bytes()
        for linked in (False, True):
            with self.subTest(linked=linked):
                policy.unlink()
                if linked:
                    other = self.write("untrusted-policy", "private-sentinel")
                    policy.symlink_to(other)
                before = self.snapshot()
                self.process.reset_mock()
                with self.assertRaises(common.DeployError) as raised:
                    validation.validate()
                self.assertNotIn("private-sentinel", str(raised.exception))
                with self.assertRaises(common.DeployError):
                    deploy.prepare()
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.commands(), [])
                if linked:
                    policy.unlink()
                policy.write_bytes(saved)

    def test_policy_path_is_literal_even_with_systemd_specifiers_and_quotes(self):
        folder = self.root / 'release "quoted" %n \\literal'
        shutil.copytree(self.source / "quadlet", folder)
        common.QUADLET_TEMPLATE = folder / "template.kube"
        text = deploy.quadlet_text(".kube", "cedar", "cedar-processor")
        self.assertEqual(
            self.override_from_unit(text), folder / "containers-hosts.conf"
        )
        self.assertIn("%%n", text)

        invalid = self.root / "release\ncontrol"
        shutil.copytree(self.source / "quadlet", invalid)
        common.QUADLET_TEMPLATE = invalid / "template.kube"
        with self.assertRaisesRegex(common.DeployError, "Control character"):
            deploy.quadlet_text(".kube", "cedar", "cedar-processor")

    def test_dev_scopes_the_override_to_kube_play_and_preserves_user_settings(self):
        script = self.source / "dev/dev.sh"
        script.parent.mkdir()
        shutil.copy2(REPO / "dev/dev.sh", script)
        record = self.root / "commands.jsonl"
        fake_home = self.root / "dev-home"
        user_config = self.write(
            "dev-home/.config/containers/containers.conf", "retained"
        )
        inherited = self.write("inherited.conf", "retained override")
        podman = self.write(
            "bin/podman",
            '#!/usr/bin/env python3\nimport configparser, json, os, sys\nargs = sys.argv[1:]\noverride = os.environ.get("CONTAINERS_CONF_OVERRIDE")\nevent = {"args": args, "override": override, "config": os.environ.get("CONTAINERS_CONF")}\nif args[:2] == ["kube", "play"]:\n    policy = configparser.ConfigParser()\n    policy.read(override)\n    event["base_hosts_file"] = policy["containers"]["base_hosts_file"]\n    event["no_hosts"] = policy.getboolean("containers", "no_hosts")\nwith open(os.environ["HOSTS_TEST_RECORD"], "a") as stream:\n    stream.write(json.dumps(event) + "\\n")\n',
            0o755,
        )
        env = dict(
            os.environ,
            HOME=str(fake_home),
            PATH=str(podman.parent) + os.pathsep + os.environ["PATH"],
            CONTAINERS_CONF=str(user_config),
            CONTAINERS_CONF_OVERRIDE=str(inherited),
            HOSTS_TEST_RECORD=str(record),
        )
        result = REAL_RUN(
            ["bash", str(script), "up"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        events = [json.loads(line) for line in record.read_text().splitlines()]
        (play,) = [event for event in events if event["args"][:2] == ["kube", "play"]]
        self.assertNotIn("--no-hosts", play["args"])
        self.assertEqual(
            play["override"], str(self.source / "quadlet/containers-hosts.conf")
        )
        self.assertEqual(play["base_hosts_file"], '"none"')
        self.assertFalse(play["no_hosts"])
        self.assertTrue(
            all(
                event["override"] == str(inherited)
                for event in events
                if event is not play
            )
        )
        self.assertTrue(all(event["config"] == str(user_config) for event in events))
        self.assertEqual(user_config.read_text(), "retained")
        self.assertEqual(inherited.read_text(), "retained override")

    def test_host_aliases_refused_before_side_effects(self):
        deploy.prepare()
        broken = copy.deepcopy(self.job)
        broken["spec"]["hostAliases"] = [
            {"ip": "192.0.2.10", "hostnames": ["private-host.example.test"]}
        ]
        self.manifest_path.write_text(yaml.safe_dump_all([broken]))
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
