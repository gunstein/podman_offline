"""Test actual proxy YAML and its shell/envsubst startup without a container runtime."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from deployment import render as rendering

REPO = Path(__file__).resolve().parent.parent
MANIFESTS = REPO / "components/platform/manifests"


class ProxyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pod = rendering.load_yaml_all(MANIFESTS / "80-proxy.yaml")[0]
        self.container = self.pod["spec"]["containers"][0]
        self.config = rendering.load_yaml_all(MANIFESTS / "20-proxy-config.yaml")[0]

    def test_platform_renders_stock_nginx_with_public_config_and_unchanged_interfaces(
        self,
    ):
        base = self.root / "platform"
        (base / "credentials/web").mkdir(parents=True)
        for name in ("web.crt", "web.key"):
            (base / "credentials/web" / name).write_text("synthetic fixture")
        routes = self.root / "routes"
        routes.mkdir()
        (routes / "installed.conf").write_text("")
        config = rendering.merge_config(
            REPO / "config/common.defaults.yaml",
            REPO / "components/platform/config.defaults.yaml",
        )
        path = base / "config.yaml"
        path.write_text(yaml.safe_dump(config))
        rendered = rendering.materialize_and_render(
            base / "files", config_path=path, manifests=MANIFESTS, component="platform"
        )
        docs = list(yaml.safe_load_all(rendered))
        pod = next(doc for doc in docs if doc["kind"] == "Pod")
        app = pod["spec"]["containers"][0]
        self.assertEqual(app["image"], "docker.io/library/nginx:1.28-alpine")
        self.assertEqual(app["imagePullPolicy"], "Never")
        self.assertEqual(
            app["ports"],
            [
                {
                    "containerPort": 8443,
                    "hostPort": 8443,
                    "hostIP": "127.0.0.1",
                    "protocol": "TCP",
                }
            ],
        )
        self.assertEqual(pod["spec"]["hostname"], "myproduct-proxy")
        self.assertEqual(
            app["envFrom"], [{"configMapRef": {"name": "platform-settings"}}]
        )
        mounts = {mount["name"]: mount for mount in app["volumeMounts"]}
        for name, target in (
            ("tls", "/run/secrets/web"),
            ("routes", "/routes"),
            ("proxy-config", "/etc/nginx/proxy-template"),
        ):
            self.assertEqual(
                mounts[name], {"name": name, "mountPath": target, "readOnly": True}
            )
        volumes = {volume["name"]: volume for volume in pod["spec"]["volumes"]}
        self.assertEqual(volumes["tls"]["secret"]["secretName"], "platform-web-tls")
        self.assertEqual(volumes["tls"]["secret"]["defaultMode"], 0o400)
        self.assertEqual(
            volumes["routes"]["persistentVolumeClaim"]["claimName"], "platform-routes"
        )
        self.assertEqual(volumes["proxy-config"]["configMap"]["defaultMode"], 0o444)
        template = self.config["data"]["default.conf.template"]
        config_doc = next(
            doc
            for doc in docs
            if doc.get("metadata", {}).get("name") == "platform-proxy-config"
        )
        self.assertEqual(config_doc["data"]["default.conf.template"], template)
        for setting in (
            "ssl_protocols TLSv1.2 TLSv1.3",
            "client_max_body_size 16k",
            "location = /livez",
            "include /routes/installed.conf",
            "location / { return 404; }",
        ):
            self.assertIn(setting, template)
        for component in ("app1", "app2", "identity", "help"):
            self.assertNotIn("location /" + component, template)
        self.assertIn(
            "${HTTPS_PORT}/livez", app["livenessProbe"]["exec"]["command"][-1]
        )

    def startup(self, resolvers, port="9443", envsubst_failure=False):
        """Run manifest shell with actual awk/envsubst; replace only filesystem paths/nginx."""
        resolver = self.root / "resolv.conf"
        resolver.write_text(resolvers)
        template = self.root / "template"
        template.write_text(
            self.config["data"]["default.conf.template"]
            + "# $host ${host} $http_host $app1_backend\n"
        )
        template.chmod(0o444)
        output = self.root / "default.conf"
        record = self.root / "nginx.json"
        binaries = self.root / "bin"
        binaries.mkdir()
        nginx = binaries / "nginx"
        nginx.write_text(
            "#!"
            + sys.executable
            + '\nimport json, os, sys\nfrom pathlib import Path\nPath(os.environ["STARTUP_RECORD"]).write_text(json.dumps({"args": sys.argv[1:], "pid": os.getpid()}))\n'
        )
        nginx.chmod(0o755)
        if envsubst_failure:
            (binaries / "envsubst").write_text("#!/bin/sh\nexit 17\n")
            (binaries / "envsubst").chmod(0o755)
        code = self.container["args"][0]
        code = code.replace(
            " /etc/resolv.conf)", " " + shlex.quote(str(resolver)) + ")"
        )
        code = code.replace(
            "/etc/nginx/proxy-template/default.conf.template",
            shlex.quote(str(template)),
        )
        code = code.replace("/etc/nginx/conf.d/default.conf", shlex.quote(str(output)))
        env = dict(
            os.environ,
            PATH=str(binaries) + os.pathsep + os.environ["PATH"],
            STARTUP_RECORD=str(record),
            host="do-not-substitute",
            http_host="do-not-substitute",
            app1_backend="do-not-substitute",
        )
        env.pop("HTTPS_PORT", None)
        if port:
            env["HTTPS_PORT"] = port
        with subprocess.Popen(
            self.container["command"] + [code],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        ) as process:
            stdout, stderr = process.communicate(timeout=10)
            status, pid = process.returncode, process.pid
        return status, pid, stdout, stderr, output, record

    @unittest.skipUnless(
        shutil.which("envsubst"), "GNU envsubst is needed for the startup regression"
    )
    def test_real_shell_substitution_uses_runtime_dns_and_preserves_nginx_variables(
        self,
    ):
        status, pid, stdout, stderr, output, record = self.startup(
            "search example.test\nnameserver 192.0.2.53\nnameserver 192.0.2.54\n"
        )
        self.assertEqual(status, 0, stderr)
        self.assertEqual(stdout, "")
        text = output.read_text()
        self.assertIn("listen 9443 ssl;", text)
        self.assertIn("resolver 192.0.2.53 valid=10s ipv6=off;", text)
        self.assertNotIn("192.0.2.54", text)
        self.assertIn("# $host ${host} $http_host $app1_backend", text)
        self.assertNotIn("do-not-substitute", text)
        self.assertEqual(
            json.loads(record.read_text()), {"args": ["-g", "daemon off;"], "pid": pid}
        )

    def test_missing_dns_stops_before_config_write_or_nginx(self):
        status, _, _, stderr, output, record = self.startup("search example.test\n")
        self.assertNotEqual(status, 0)
        self.assertIn("No DNS server", stderr)
        self.assertFalse(output.exists())
        self.assertFalse(record.exists())

    def test_missing_port_stops_before_config_write_or_nginx(self):
        status, _, _, stderr, output, record = self.startup(
            "nameserver 192.0.2.53\n", port=""
        )
        self.assertNotEqual(status, 0)
        self.assertIn("HTTPS_PORT is required", stderr)
        self.assertFalse(output.exists())
        self.assertFalse(record.exists())

    def test_template_failure_never_starts_nginx(self):
        status, _, _, _, _, record = self.startup(
            "nameserver 192.0.2.53\n", envsubst_failure=True
        )
        self.assertEqual(status, 17)
        self.assertFalse(record.exists())
