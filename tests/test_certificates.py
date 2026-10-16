"""Exercise the certificate script only in disposable directories."""

import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL is needed for the PKI script")
class CertificateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        scripts = self.project / "scripts"
        scripts.mkdir(parents=True)
        self.script = scripts / "generate-certificates.sh"
        shutil.copyfile(
            Path(__file__).resolve().parent.parent / "scripts/generate-certificates.sh",
            self.script,
        )

        stub = self.root / "host-bin"
        stub.mkdir()
        podman = stub / "podman"
        podman.write_text(
            '#!/bin/sh\necho unexpected-podman-call > "$CERTIFICATE_PODMAN_LOG"\nexit 125\n'
        )
        podman.chmod(0o755)
        self.environment = dict(
            os.environ,
            PATH=str(stub) + os.pathsep + os.environ["PATH"],
            CERTIFICATE_PODMAN_LOG=str(self.root / "podman-calls"),
        )

    def run_script(self, *args):
        return subprocess.run(
            ["bash", str(self.script)] + list(args),
            cwd=str(self.root),
            env=self.environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,  # noqa: UP021 - Python 3.6
        )

    def fingerprints(self, root):
        return {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*")
            if path.is_file()
        }

    def test_explicit_root_preserves_existing_material_and_permissions(self):
        target = self.root / "persistent home"
        first = self.run_script("--root", str(target), "example.test")
        self.assertEqual(first.returncode, 0, first.stdout)
        self.assertFalse((self.project / "credentials").exists())
        self.assertTrue((target / "PKI/private/ca.key").is_file())
        for directory in ("PKI/private", "credentials"):
            self.assertEqual(stat.S_IMODE((target / directory).stat().st_mode), 0o700)
        for path in target.rglob("*"):
            if path.is_file():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        before = self.fingerprints(target)
        repeated = self.run_script("--root", str(target), "different.test")
        self.assertNotEqual(repeated.returncode, 0)
        self.assertIn("PKI already exists", repeated.stdout)
        self.assertEqual(before, self.fingerprints(target))
        cert = subprocess.run(
            [
                "openssl",
                "x509",
                "-in",
                str(target / "credentials/web/web.crt"),
                "-noout",
                "-text",
            ],
            check=True,
            stdout=subprocess.PIPE,
            universal_newlines=True,  # noqa: UP021 - Python 3.6
        )
        self.assertIn("DNS:example.test", cert.stdout)

    def test_default_root_is_project_even_from_another_working_directory(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((self.project / "PKI/private/ca.key").is_file())
        self.assertTrue((self.project / "credentials/users/alice-password").is_file())
        self.assertFalse((self.root / "credentials").exists())

    def test_component_credentials_are_independent_and_generated_once(self):
        """Keep platform/app1 private bytes unchanged when app2 is added or scripts repeat."""
        target = self.root / "component-home"
        for component in ("platform", "identity", "app1"):
            result = self.run_script("--root", str(target), component, "example.test")
            self.assertEqual(result.returncode, 0, result.stdout)
        before = self.fingerprints(target)
        result = self.run_script("--root", str(target), "app2", "example.test")
        self.assertEqual(result.returncode, 0, result.stdout)
        after = self.fingerprints(target)
        self.assertTrue(
            all(
                after[name] == digest
                for name, digest in before.items()
                if name != "PKI/private/ca.srl"
            ),
            "Adding app2 changed existing credentials",
        )
        self.assertFalse((target / "identity/credentials/app").exists())
        self.assertFalse((self.root / "podman-calls").exists())
        before_repeat = after
        for component in ("platform", "identity", "app1", "app2"):
            result = self.run_script("--root", str(target), component, "example.test")
            self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(
            before_repeat == self.fingerprints(target),
            "Repeated generation changed files",
        )
        # Database passwords now belong exclusively to deploy's GENERATED_SECRETS.
        for component, relative in (
            ("identity", "identity-db"),
            ("app1", "database"),
            ("app2", "database"),
        ):
            self.assertFalse(
                (target / component / "credentials" / relative / "password").exists()
            )
        for path in target.rglob("*"):
            if path.is_file():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_invalid_arguments_do_not_generate_material(self):
        for args in (("--root",), ("--root", ""), ("bad/name",), ("one", "two")):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("Usage:", result.stdout)
        self.assertFalse((self.project / "credentials").exists())
