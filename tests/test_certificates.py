"""Exercise the certificate script only in disposable directories."""

import hashlib
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

    def run_script(self, *args):
        return subprocess.run(
            ["bash", str(self.script)] + list(args),
            cwd=str(self.root),
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
        self.assertFalse((self.project / "generated-certificates").exists())
        self.assertTrue((target / "PKI/private/ca.key").is_file())
        for directory in ("PKI/private", "generated-certificates"):
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
                str(target / "generated-certificates/web/web.crt"),
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
        self.assertTrue(
            (self.project / "generated-certificates/users/alice-password").is_file()
        )
        self.assertFalse((self.root / "generated-certificates").exists())

    def test_invalid_arguments_do_not_generate_material(self):
        for args in (("--root",), ("--root", ""), ("bad/name",), ("one", "two")):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("Usage:", result.stdout)
        self.assertFalse((self.project / "generated-certificates").exists())
