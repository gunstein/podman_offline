"""The .NET/TypeScript whoami demo (app3, backlog 71): credentials and source contracts."""

import json
import re
import stat
import subprocess
import unittest
from pathlib import Path

import yaml

from helpers.certificate_fixture import CertificateFixture

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "components/app3"
BACKEND = ROOT / "apps/whoami-backend"
FRONTEND = ROOT / "apps/whoami-frontend"


def openssl(*arguments):
    return subprocess.run(
        ["openssl"] + list(arguments),
        check=True,
        stdout=subprocess.PIPE,
        universal_newlines=True,
    ).stdout


def backend_container():
    pod = yaml.safe_load((COMPONENT / "manifests/60-whoami.yaml").read_text())
    return pod, next(c for c in pod["spec"]["containers"] if c["name"] == "backend")


class WhoamiCredentialTests(CertificateFixture):
    def test_client_pair_is_issued_once_by_the_environment_ca(self):
        """private_key_jwt needs a clientAuth pair from the same CA as the proxy."""
        target = self.root / "state"
        for component in ("platform", "app3"):
            result = self.run_script("--root", str(target), component, "example.test")
            self.assertEqual(result.returncode, 0, result.stdout)
        client = target / "app3/credentials/client"
        self.assertEqual(stat.S_IMODE((client / "client.key").stat().st_mode), 0o600)
        verified = openssl(
            "verify",
            "-CAfile",
            str(target / "PKI/private/ca.crt"),
            str(client / "client.crt"),
        )
        self.assertIn(": OK", verified)
        text = openssl("x509", "-in", str(client / "client.crt"), "-noout", "-text")
        self.assertIn("TLS Web Client Authentication", text)
        self.assertIn("CN=app3-client", text.replace(" = ", "="))
        before = self.fingerprints(target)
        result = self.run_script("--root", str(target), "app3", "example.test")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(before, self.fingerprints(target))


class WhoamiSourceTests(unittest.TestCase):
    def test_client_certificate_and_trust_chain_paths_match_their_consumers(self):
        """client.yaml, SECRET_FILES, demo provisioning and the mounts name the same files."""
        defaults = yaml.safe_load((COMPONENT / "config.defaults.yaml").read_text())
        files = defaults["SECRET_FILES"]
        client = yaml.safe_load((COMPONENT / "client.yaml").read_text())
        self.assertEqual(
            client["certificate"], files["app3-client"][0]["path"] + "/client.crt"
        )
        self.assertEqual(files["app3-ingress-trust-chain"], [{"path": "cert"}])
        provisioning = (ROOT / "dev/demo-credentials.sh").read_text()
        for name in ("root.crt", "ca.crt"):
            self.assertIn(
                "build/dev/PKI/private/ca.crt build/dev/app3/cert/" + name,
                provisioning,
            )
        pod, backend = backend_container()
        mounts = {m["mountPath"]: m for m in backend["volumeMounts"]}
        self.assertEqual(
            mounts["/etc/ssl/certs/myproduct-root.pem"]["subPath"], "root.crt"
        )
        self.assertEqual(mounts["/etc/ssl/certs/myproduct-ca.pem"]["subPath"], "ca.crt")
        program = (BACKEND / "Program.cs").read_text()
        secrets = mounts["/run/secrets/client"]["name"]
        volume = next(v for v in pod["spec"]["volumes"] if v["name"] == secrets)
        self.assertEqual(volume["secret"]["secretName"], "app3-client")
        for name in ("client.crt", "client.key"):
            self.assertIn('"/run/secrets/client/' + name + '"', program)
        # Data Protection keys must be on the persistent volume, or restarts sign users out.
        self.assertIn(
            'PersistKeysToFileSystem(new DirectoryInfo("/data/protection"))', program
        )
        volume = next(
            v
            for v in pod["spec"]["volumes"]
            if v["name"] == mounts["/data/protection"]["name"]
        )
        self.assertEqual(
            volume["persistentVolumeClaim"]["claimName"], "app3-protection"
        )

    def test_backend_uses_the_client_protocol_behind_the_proxy(self):
        """Callback path, forwarded scheme, private_key_jwt and the backend port."""
        program = (BACKEND / "Program.cs").read_text()
        self.assertIn('options.CallbackPath = "/auth/callback";', program)
        self.assertIn("app.UsePathBase(basePath);", program)
        self.assertIn("ForwardedHeaders.XForwardedProto", program)
        self.assertLess(
            program.index("app.UseForwardedHeaders();"),
            program.index("app.UseAuthentication();"),
        )
        self.assertIn("client-assertion-type:jwt-bearer", program)
        self.assertIn(
            "ASPNETCORE_HTTP_PORTS=8000", (BACKEND / "Containerfile").read_text()
        )
        route = (COMPONENT / "route.conf").read_text()
        self.assertEqual(set(re.findall(r"app3-whoami:(\d+)", route)), {"8000", "8080"})
        self.assertIn("proxy_set_header X-Forwarded-Proto https;", route)

    def test_frontend_compiles_typescript_only_at_build_time(self):
        """Node builds; the runtime stage is nginx with only static files."""
        stages = re.findall(
            r"^FROM (\S+)", (FRONTEND / "Containerfile").read_text(), re.MULTILINE
        )
        self.assertEqual(len(stages), 2)
        self.assertTrue(stages[0].startswith("docker.io/library/node:"))
        self.assertTrue(stages[1].startswith("docker.io/library/nginx:"))
        package = json.loads((FRONTEND / "package.json").read_text())
        lock = json.loads((FRONTEND / "package-lock.json").read_text())
        pinned = package["devDependencies"]["typescript"]
        self.assertRegex(pinned, r"^[0-9]+\.[0-9]+\.[0-9]+$")
        self.assertEqual(lock["packages"]["node_modules/typescript"]["version"], pinned)
        self.assertNotIn("dependencies", package)
