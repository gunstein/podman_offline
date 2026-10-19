"""Exercise the certificate script only in disposable directories."""

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class CertificateFixture(unittest.TestCase):
    def setUp(self):
        if not shutil.which("openssl"):
            self.fail(
                "OpenSSL is required for certificate tests; install it before running"
            )
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        scripts = self.project / "dev"
        scripts.mkdir(parents=True)
        self.script = scripts / "generate-certificates.sh"
        shutil.copyfile(
            Path(__file__).resolve().parents[2] / "dev/generate-certificates.sh",
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
            universal_newlines=True,
        )

    def fingerprints(self, root):
        return {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*")
            if path.is_file()
        }

    def signing_setup(self, component="my-identity", password=b"PrivateTestPassword\n"):
        target = self.root / "signing state"
        directory = target / component / "credentials/signing"
        directory.mkdir(parents=True)
        for path in (target / component, directory.parent, directory):
            path.chmod(0o700)
        secret = directory / "pfx-password"
        secret.write_bytes(password)
        secret.chmod(0o600)
        return target, directory

    def signing(self, target, component="my-identity", stdin=False, settings=()):
        args = (
            [
                "--root",
                str(target),
            ]
            + list(settings)
            + [
                "--component",
                component,
                "--purpose",
                "signing",
                "--pfx",
            ]
        )
        if not stdin:
            return self.run_script(*args)
        return subprocess.run(
            ["bash", "-s", "--"] + args,
            input=self.script.read_text(),
            cwd=str(self.root),
            env=self.environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )

    def pem_pair(self, directory, stem="signing-cert"):
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(directory / (stem + ".key")),
                "-out",
                str(directory / (stem + ".crt")),
                "-days",
                "1",
                "-subj",
                "/CN=External signing fixture",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        (directory / (stem + ".key")).chmod(0o600)

    def assert_signing_failure(self, target, before, component="my-identity"):
        result = self.signing(target, component)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("PrivateTestPassword", result.stdout)
        self.assertEqual(before, self.fingerprints(target))
        self.assertFalse((target / ".signing-provision.lock").exists())
        self.assertFalse(list(target.glob("*/credentials/signing/.pfx-*")))
        return result
