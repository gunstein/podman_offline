"""Exercise the certificate script only in disposable directories."""

import datetime
import stat
import subprocess

from helpers.certificate_fixture import CertificateFixture


class DemoCertificateTests(CertificateFixture):
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
            universal_newlines=True,
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
        # Database passwords now belong exclusively to deploy's file-source generate declarations.
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

    def test_legacy_modes_use_configured_ca_and_certificate_settings(self):
        for mode in (("example.test",), ("platform", "example.test")):
            with self.subTest(mode=mode):
                target = self.root / ("full" if len(mode) == 1 else "component")
                result = self.run_script(
                    "--root",
                    str(target),
                    "--ca-subject",
                    "/CN=Organisation CA",
                    "--ca-days",
                    "19",
                    "--cert-days",
                    "4",
                    *mode,
                )
                self.assertEqual(result.returncode, 0, result.stdout)
                certificates = list(target.rglob("*.crt"))
                self.assertTrue(certificates)
                for certificate in certificates:
                    result = subprocess.run(
                        [
                            "openssl",
                            "x509",
                            "-in",
                            str(certificate),
                            "-noout",
                            "-issuer",
                            "-dates",
                        ],
                        check=True,
                        stdout=subprocess.PIPE,
                        universal_newlines=True,
                    )
                    self.assertIn("Organisation CA", result.stdout)
                    dates = [
                        datetime.datetime.strptime(
                            line.split("=", 1)[1], "%b %d %H:%M:%S %Y %Z"
                        ).replace(tzinfo=datetime.timezone.utc)
                        for line in result.stdout.splitlines()
                        if line.startswith(("notBefore=", "notAfter="))
                    ]
                    expected = 19 if certificate.name == "ca.crt" else 4
                    self.assertEqual((dates[1] - dates[0]).days, expected)

    def test_relative_root_in_legacy_modes_is_not_nested_by_shared_ca_helper(self):
        for mode in (("example.test",), ("platform", "example.test")):
            with self.subTest(mode=mode):
                relative = "relative-full" if len(mode) == 1 else "relative-component"
                result = self.run_script("--root", relative, *mode)
                self.assertEqual(result.returncode, 0, result.stdout)
                target = self.root / relative
                self.assertTrue((target / "PKI/private/ca.crt").is_file())
                self.assertFalse((target / relative).exists())
