"""Signed bundles: a detached OpenPGP signature the target checks with gpgv."""

import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import bundle


class SigningTests(unittest.TestCase):
    def setUp(self):
        for command in ("gpg", "gpgv", "gpgconf"):
            if not shutil.which(command):
                self.fail("Signing tests require " + command + " on PATH")
        # Prefer the host's temporary directory; there is no hardcoded /tmp.
        try:
            directory = tempfile.TemporaryDirectory(prefix="gpg-")
        except OSError:
            self.fail("Signing tests require a writable temporary directory (TMPDIR)")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.home = self.root / "gnupg"
        self.home.mkdir(mode=0o700)
        environment = mock.patch.dict(os.environ, {"GNUPGHOME": str(self.home)})
        environment.start()
        self.addCleanup(environment.stop)
        self.addCleanup(
            subprocess.run,
            ["gpgconf", "--kill", "gpg-agent"],
            check=False,
            env=dict(os.environ, GNUPGHOME=str(self.home)),
        )
        try:
            self.gpg(
                "--passphrase",
                "",
                "--quick-gen-key",
                "Bundle test <bundle@invalid>",
                "ed25519",
                "sign",
                "never",
            )
        except subprocess.CalledProcessError:
            self.fail(
                "Signing tests require working gpg-agent key generation and a writable short TMPDIR"
            )
        listing = self.gpg("--list-secret-keys", "--with-colons").stdout
        self.key = next(
            line.split(":")[9]
            for line in listing.splitlines()
            if line.startswith("fpr")
        )
        self.keyring = self.root / "organisation.gpg"
        self.keyring.write_bytes(self.gpg("--export", self.key, text=False).stdout)
        self.archive = self.root / "myproduct-app1-1.0.0-offline.tar.gz"
        self.archive.write_bytes(b"archive bytes")

    def gpg(self, *arguments, text=True):
        return subprocess.run(
            ["gpg", "--batch", "--pinentry-mode", "loopback", *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=text,
        )

    def sign(self, key):
        """Return the signature and the operator messages (stdout, then stderr)."""
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {bundle.SIGNING_KEY: key}):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                signature = bundle.sign(self.archive)
        self.warnings = errors.getvalue()
        return signature, output.getvalue()

    def verify(self):
        """The documented target check: gpgv against the organisation's key only."""
        return subprocess.run(
            [
                "gpgv",
                "--keyring",
                str(self.keyring),
                str(self.archive) + ".asc",
                str(self.archive),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        ).returncode

    def test_signed_archive_verifies_and_a_changed_one_does_not(self):
        signature, _ = self.sign(self.key)
        self.assertEqual(signature, self.root / (self.archive.name + ".asc"))
        self.assertEqual(self.verify(), 0)
        self.archive.write_bytes(b"replaced archive bytes")
        self.assertNotEqual(self.verify(), 0)

    def test_unsigned_build_says_so_and_drops_an_old_signature(self):
        self.sign(self.key)
        signature, output = self.sign("")
        self.assertIsNone(signature)
        # A warning with its next action, on stderr (backlog 74).
        self.assertIn(
            f"WARNING: {self.archive.name} is unsigned; set BUNDLE_SIGNING_KEY",
            self.warnings,
        )
        self.assertNotIn("unsigned", output)
        self.assertFalse((self.root / (self.archive.name + ".asc")).exists())

    def test_unknown_key_fails_the_build(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.sign("0000000000000000000000000000000000000000")
        self.assertFalse((self.root / (self.archive.name + ".asc")).exists())


if __name__ == "__main__":
    unittest.main()
