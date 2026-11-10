"""The .NET/TypeScript whoami demo (app3, backlog 71): credentials and source contracts."""

import json
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml
from deployment import catalog as deployment_catalog
from deployment import environment as deployment_environment

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

    def test_demo_credentials_copy_the_dev_ca_as_app3_trust_chain(self):
        """Run dev/demo-credentials.sh with the real certificate script.

        Only the dev settings lookup is replaced: it needs the shipped catalog
        and Podman, which this offline test does not use.
        """
        script = self.project / "dev/demo-credentials.sh"
        script.write_bytes((ROOT / "dev/demo-credentials.sh").read_bytes())
        package = self.project / "deployment"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "deploy.py").write_text(
            "def dev_settings():\n"
            "    return {}, {'platform': {'PUBLIC_ORIGIN': 'https://example.test:8443'}}, None\n"
            "def check_dev_components(known, settings, env_overrides):\n"
            "    pass\n"
        )
        cert = self.project / "build/dev/app3/cert"
        snapshots = []
        for _ in range(2):
            result = subprocess.run(
                ["bash", str(script)],
                env=self.environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            ca = (self.project / "build/dev/PKI/private/ca.crt").read_bytes()
            self.assertEqual(stat.S_IMODE(cert.stat().st_mode), 0o700)
            for name in ("root.crt", "ca.crt"):
                self.assertEqual((cert / name).read_bytes(), ca, name)
                self.assertEqual(stat.S_IMODE((cert / name).stat().st_mode), 0o644)
            snapshots.append(self.fingerprints(self.project / "build/dev"))
        # A repeat keeps every key and the CA; only the copies are rewritten.
        self.assertEqual(snapshots[0], snapshots[1])


class WhoamiSourceTests(unittest.TestCase):
    def test_client_certificate_and_trust_chain_paths_match_their_consumers(self):
        """client.yaml, SECRET_FILES, the mounts and Program.cs name the same files."""
        defaults = yaml.safe_load((COMPONENT / "config.defaults.yaml").read_text())
        files = defaults["SECRET_FILES"]
        client = yaml.safe_load((COMPONENT / "client.yaml").read_text())
        self.assertEqual(
            client["certificate"], files["app3-client"][0]["path"] + "/client.crt"
        )
        self.assertEqual(files["app3-ingress-trust-chain"], [{"path": "cert"}])
        # The trust chain's two files, mounted unchanged from their Secret (backlog 80).
        self.assertEqual(
            defaults["MOUNTS"]["backend"],
            {
                "/etc/ssl/certs/myproduct-root.pem": "@@secret:app3-ingress-trust-chain/root.crt@@",
                "/etc/ssl/certs/myproduct-ca.pem": "@@secret:app3-ingress-trust-chain/ca.crt@@",
            },
        )
        pod, backend = backend_container()
        mounts = {m["mountPath"]: m for m in backend["volumeMounts"]}
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
        # The issuer pin and its build-time check (Checks/), and no exception
        # messages from the OIDC handler in the log.
        self.assertIn("Oidc.PublicIssuer(issuer, actual)", program)
        containerfile = (BACKEND / "Containerfile").read_text()
        self.assertLess(
            containerfile.index(
                "RUN dotnet run --no-restore -c Release --project Checks"
            ),
            containerfile.index("RUN dotnet publish"),
        )
        self.assertIn(
            'AddFilter("Microsoft.AspNetCore.Authentication.OpenIdConnect"', program
        )
        self.assertNotIn(".Message", program)
        self.assertIn(
            "ASPNETCORE_HTTP_PORTS=8000", (BACKEND / "Containerfile").read_text()
        )
        route = (COMPONENT / "route.conf").read_text()
        self.assertEqual(set(re.findall(r"app3-whoami:(\d+)", route)), {"8000", "8080"})
        self.assertIn("proxy_set_header X-Forwarded-Proto https;", route)

    def test_api_registration_matches_identity_and_the_backend(self):
        """Backlog 77: app3 declares its secret; both sides name it, nothing else."""
        backend_env = yaml.safe_load((COMPONENT / "config.defaults.yaml").read_text())[
            "ENVIRONMENT"
        ]["backend"]
        # app3 is an optional API (backlog 85): the demo's target environment
        # file (copied to state/whoami.yaml on the target) and dev's overrides
        # hold the same Identity lines.
        with tempfile.TemporaryDirectory() as state:
            shutil.copy2(str(ROOT / "config/whoami.yaml"), state + "/whoami.yaml")
            environment = deployment_environment.read_environment_file(
                Path(state), "whoami"
            )
        self.assertEqual(environment.selected, ["platform", "identity", "app3"])
        identity_env = environment.components["identity"]["app"]
        dev = yaml.safe_load((ROOT / "config/dev.yaml.example").read_text())
        self.assertEqual(
            dev["overrides"]["identity"]["ENVIRONMENT"]["app"], identity_env
        )
        reference = "@@secret:app3-api-secret/value@@"
        self.assertEqual(backend_env["Authentication__ApiSecret"], reference)
        self.assertEqual(
            identity_env["ApiResources__0__ApiSecrets__0__Value"], reference
        )
        self.assertEqual(
            identity_env["ApiResources__0__Name"],
            backend_env["Authentication__ApiName"],
        )
        self.assertEqual(identity_env["ApiResources__0__Scopes__0"], "app3")
        self.assertFalse((COMPONENT / "api.yaml").exists())
        config = yaml.safe_load((COMPONENT / "config.defaults.yaml").read_text())
        self.assertNotIn("SECRET_TEMPLATES", config)
        self.assertEqual(
            config["SECRET_FILES"]["app3-api-secret"],
            [{"path": "credentials/api-secret", "generate": ["value"]}],
        )
        # The neutral bundles have no API registration; the environment adds it
        # on the target (catalog.environment_descriptor).
        neutral = deployment_catalog.source_descriptors(ROOT)
        self.assertIsNone(neutral["app3"]["apis"])
        self.assertEqual(neutral["identity"]["api_secrets"], {})
        identity = deployment_catalog.environment_descriptor(
            neutral["identity"], environment, {}, ROOT
        )
        self.assertEqual(identity["accepts"]["apis"], "identity-apis")
        self.assertEqual(
            identity["api_secrets"],
            {"app3": {"index": 0, "secret": "app3-api-secret/value"}},
        )
        _, backend = backend_container()
        self.assertNotIn("envFrom", backend)
        # Identity hashes the raw value itself (Duende compares hashes).
        identity_program = (ROOT / "apps/identity/Program.cs").read_text()
        self.assertIn(
            "secret.secret.Value = secret.secret.Value.Sha256();", identity_program
        )
        program = (BACKEND / "Program.cs").read_text()
        self.assertIn('Required("Authentication:ApiName")', program)
        self.assertIn('Required("Authentication:ApiSecret")', program)
        self.assertIn("configuration.IntrospectionEndpoint", program)
        # Only the result leaves the endpoint; the secret is never logged.
        self.assertNotIn("Log", program[program.index('"/api/secret-check"') :])

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
