"""Exercise the certificate script only in disposable directories."""

import datetime
import shutil
import stat
import subprocess

from helpers.certificate_fixture import CertificateFixture


class CertificateTests(CertificateFixture):
    def test_pfx_new_issuance_stdin_retention_permissions_and_recovery(self):
        target, directory = self.signing_setup()
        result = self.signing(target, stdin=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        pfx = directory / "signing-cert.pfx"
        self.assertTrue(pfx.is_file())
        self.assertFalse((target / "identity").exists())
        self.assertFalse((directory.parent / "users").exists())
        self.assertFalse((self.root / "podman-calls").exists())
        for path in target.rglob("*"):
            self.assertEqual(
                stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600
            )
        before = self.fingerprints(target)
        result = self.signing(target)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(before, self.fingerprints(target))
        pfx.unlink()
        result = self.signing(target)
        self.assertEqual(result.returncode, 0, result.stdout)
        after = self.fingerprints(target)
        self.assertTrue(
            all(
                after[name] == digest
                for name, digest in before.items()
                if not name.endswith(".pfx")
            )
        )
        # Export salts/IVs intentionally differ; existing PFX retention was checked above.
        self.assertNotEqual(
            before[str(pfx.relative_to(target))], after[str(pfx.relative_to(target))]
        )

    def test_pfx_external_pem_wins_without_ca_and_has_explicit_algorithms(self):
        target, directory = self.signing_setup(component="token-service")
        self.pem_pair(directory)
        before = self.fingerprints(target)
        result = self.signing(target, component="token-service")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse((target / "PKI").exists())
        self.assertTrue(
            all(
                self.fingerprints(target)[name] == digest
                for name, digest in before.items()
            )
        )
        result = subprocess.run(
            [
                "openssl",
                "pkcs12",
                "-in",
                str(directory / "signing-cert.pfx"),
                "-passin",
                "file:" + str(directory / "pfx-password"),
                "-info",
                "-noout",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertIn(b"AES-256-CBC", result.stderr)
        self.assertIn(b"MAC: sha256", result.stderr)

    def test_pfx_external_pfx_wins_without_pem_or_ca(self):
        target, directory = self.signing_setup()
        self.pem_pair(directory)
        result = self.signing(target)
        self.assertEqual(result.returncode, 0, result.stdout)
        (directory / "signing-cert.crt").unlink()
        (directory / "signing-cert.key").unlink()
        before = self.fingerprints(target)
        result = self.signing(target)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(before, self.fingerprints(target))
        self.assertFalse((target / "PKI").exists())

    def test_pfx_missing_invalid_or_public_password_refused_without_writes(self):
        target, directory = self.signing_setup()
        password = directory / "pfx-password"
        for value in (
            b"",
            b"one\ntwo",
            b"one\n\n",
            b"bad\r\n",
            b"bad\0value",
            b"x" * 1024,
        ):
            with self.subTest(value=value):
                password.write_bytes(value)
                self.assert_signing_failure(target, self.fingerprints(target))
        password.write_bytes(b"PrivateTestPassword")
        password.chmod(0o644)
        self.assert_signing_failure(target, self.fingerprints(target))
        password.unlink()
        self.assert_signing_failure(target, self.fingerprints(target))

    def test_pfx_partial_pem_and_incomplete_ca_refused(self):
        target, directory = self.signing_setup()
        (directory / "signing-cert.key").write_bytes(b"PrivateTestPassword")
        (directory / "signing-cert.key").chmod(0o600)
        result = self.signing(target)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remove only the orphan file and retry", result.stdout)
        self.assertIn("never remove an in-use key or CA", result.stdout)
        self.assert_signing_failure(target, self.fingerprints(target))
        (directory / "signing-cert.key").unlink()
        ca = target / "PKI/private"
        ca.mkdir(parents=True)
        (ca / "ca.crt").write_bytes(b"incomplete")
        result = self.signing(target)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Incomplete existing CA", result.stdout)
        self.assertIn("remove only the orphan file and retry", result.stdout)
        self.assert_signing_failure(target, self.fingerprints(target))
        (ca / "ca.crt").unlink()
        (ca / "ca.key").write_bytes(b"unused interrupted CA key")
        (ca / "ca.key").chmod(0o600)
        before = self.fingerprints(target)
        result = self.signing(target)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Incomplete existing CA", result.stdout)
        self.assertIn("never remove an in-use key or CA", result.stdout)
        self.assertEqual(self.fingerprints(target), before)

    def test_pfx_wrong_password_corruption_and_pem_mismatch_refused(self):
        target, directory = self.signing_setup()
        self.pem_pair(directory)
        self.assertEqual(self.signing(target).returncode, 0)
        password = directory / "pfx-password"
        password.write_bytes(b"WrongPrivateTestPassword")
        self.assert_signing_failure(target, self.fingerprints(target))
        password.write_bytes(b"PrivateTestPassword\n")
        self.pem_pair(directory, "other")
        for extension in ("crt", "key"):
            path = directory / ("signing-cert." + extension)
            previous = path.read_bytes()
            path.write_bytes((directory / ("other." + extension)).read_bytes())
            self.assert_signing_failure(target, self.fingerprints(target))
            path.write_bytes(previous)
        pfx = directory / "signing-cert.pfx"
        for value in (b"", b"corrupt PrivateTestPassword"):
            pfx.write_bytes(value)
            self.assert_signing_failure(target, self.fingerprints(target))

    def test_pfx_certificate_only_archive_refused(self):
        target, directory = self.signing_setup()
        self.pem_pair(directory)
        subprocess.run(
            [
                "openssl",
                "pkcs12",
                "-export",
                "-nokeys",
                "-in",
                str(directory / "signing-cert.crt"),
                "-out",
                str(directory / "signing-cert.pfx"),
                "-passout",
                "file:" + str(directory / "pfx-password"),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        (directory / "signing-cert.pfx").chmod(0o600)
        self.assert_signing_failure(target, self.fingerprints(target))

    def test_pfx_symlinked_sources_outputs_and_ancestors_refused(self):
        target, directory = self.signing_setup()
        external = self.root / "outside"
        external.write_bytes(b"PrivateTestPassword")
        external.chmod(0o600)
        for name in (
            "signing-cert.pfx",
            "signing-cert.crt",
            "signing-cert.key",
            "pfx-password",
        ):
            path = directory / name
            previous = path.read_bytes() if path.exists() else None
            path.unlink() if path.exists() else None
            path.symlink_to(external)
            self.assert_signing_failure(target, self.fingerprints(target))
            path.unlink()
            if previous is not None:
                path.write_bytes(previous)
                path.chmod(0o600)
        alias = self.root / "alias"
        alias.symlink_to(target, target_is_directory=True)
        self.assert_signing_failure(alias, self.fingerprints(alias))

    def test_pfx_invalid_component_and_unknown_purpose_fail_before_writes(self):
        target, _directory = self.signing_setup()
        before = self.fingerprints(target)
        for component in ("../escape", "Bad", "a/b", "-bad", "bad-"):
            self.assert_signing_failure(target, before, component=component)
        result = self.run_script(
            "--root", str(target), "--component", "worker", "--purpose", "web", "--pfx"
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(before, self.fingerprints(target))

    def test_pfx_export_failure_cleans_temporary_files_and_keeps_sources(self):
        target, directory = self.signing_setup()
        self.pem_pair(directory)
        real = shutil.which("openssl")
        wrapper = self.root / "host-bin/openssl"
        wrapper.write_text(
            '#!/bin/sh\nif [ "$1" = pkcs12 ] && [ "$2" = -export ]; then\n'
            ' while [ "$#" -gt 0 ]; do\n'
            '  if [ "$1" = -out ]; then shift; printf partial > "$1"; break; fi\n'
            '  shift\n done\n echo PrivateTestPassword >&2; exit 71\nfi\nexec "'
            + str(real)
            + '" "$@"\n'
        )
        wrapper.chmod(0o755)
        self.assert_signing_failure(target, self.fingerprints(target))
        # A real termination during export must also unwind scratch/lock state.
        wrapper.write_text(
            wrapper.read_text().replace(
                "echo PrivateTestPassword >&2; exit 71",
                'kill -TERM "$PPID"; exit 71',
            )
        )
        self.assert_signing_failure(target, self.fingerprints(target))
        wrapper.unlink()
        self.assertEqual(self.signing(target).returncode, 0)

    def test_pfx_password_is_not_in_process_arguments_or_logs(self):
        target, directory = self.signing_setup()
        self.pem_pair(directory)
        real = shutil.which("openssl")
        wrapper = self.root / "host-bin/openssl"
        argument_log = self.root / "openssl-arguments"
        self.environment["OPENSSL_ARGUMENT_LOG"] = str(argument_log)
        wrapper.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$@" >> "$OPENSSL_ARGUMENT_LOG"\nexec "'
            + str(real)
            + '" "$@"\n'
        )
        wrapper.chmod(0o755)
        result = self.signing(target)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "file:" + str(directory / "pfx-password"), argument_log.read_text()
        )
        self.assertNotIn(
            "PrivateTestPassword", argument_log.read_text() + result.stdout
        )

    def test_pfx_no_clobber_publish_and_concurrent_invocation_refused(self):
        target, directory = self.signing_setup()
        self.pem_pair(directory)
        self.assertEqual(self.signing(target).returncode, 0)
        saved = self.root / "external.pfx"
        shutil.copyfile(directory / "signing-cert.pfx", saved)
        (directory / "signing-cert.pfx").unlink()
        real = shutil.which("openssl")
        wrapper = self.root / "host-bin/openssl"
        wrapper.write_text(
            '#!/bin/sh\n"'
            + str(real)
            + '" "$@" || exit $?\nif [ "$1" = pkcs12 ] && [ "$2" = -export ]; then\n cp "$PFX_RACE_SOURCE" "$PFX_RACE_TARGET"\nfi\n'
        )
        wrapper.chmod(0o755)
        self.environment.update(
            PFX_RACE_SOURCE=str(saved),
            PFX_RACE_TARGET=str(directory / "signing-cert.pfx"),
        )
        result = self.signing(target)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            saved.read_bytes(), (directory / "signing-cert.pfx").read_bytes()
        )
        self.assertFalse(list(directory.glob(".pfx-*")))
        wrapper.unlink()
        lock = target / ".signing-provision.lock"
        lock.mkdir()
        before = self.fingerprints(target)
        result = self.signing(target)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("busy or interrupted", result.stdout)
        self.assertEqual(before, self.fingerprints(target))
        lock.rmdir()


class CASettingsTests(CertificateFixture):
    def certificate_info(self, path):
        result = subprocess.run(
            [
                "openssl",
                "x509",
                "-in",
                str(path),
                "-noout",
                "-subject",
                "-nameopt",
                "RFC2253",
                "-dates",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        lines = result.stdout.splitlines()
        dates = {}
        for line in lines:
            if line.startswith(("notBefore=", "notAfter=")):
                name, value = line.split("=", 1)
                dates[name] = datetime.datetime.strptime(
                    value, "%b %d %H:%M:%S %Y %Z"
                ).replace(tzinfo=datetime.timezone.utc)
        return lines[0], (dates["notAfter"] - dates["notBefore"]).days

    def test_configured_ca_and_leaf_lifetimes_and_retention(self):
        target, directory = self.signing_setup()
        settings = (
            "--ca-subject",
            "/C=NO/O=Offline Org/CN=Company CA",
            "--ca-days",
            "17",
            "--cert-days",
            "3",
        )
        result = self.signing(target, stdin=True, settings=settings)
        self.assertEqual(result.returncode, 0, result.stdout)
        ca = target / "PKI/private/ca.crt"
        subject, days = self.certificate_info(ca)
        self.assertIn("CN=Company CA,O=Offline Org,C=NO", subject)
        self.assertEqual(days, 17)
        self.assertEqual(self.certificate_info(directory / "signing-cert.crt")[1], 3)
        before = self.fingerprints(target)
        changed = ("--ca-days", "30", "--cert-days", "5")
        result = self.signing(target, settings=changed)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("--ca-days applies only to newly created CAs", result.stdout)
        self.assertEqual(self.fingerprints(target), before)
        _, second = self.signing_setup(component="another-service")
        before = self.fingerprints(target)
        mismatch = ("--ca-subject", "/CN=Changed CA")
        # Refuse even a retained PFX invocation and stdin issuance for a new component.
        for component in ("my-identity", "another-service"):
            result = self.signing(
                target, component=component, stdin=True, settings=mismatch
            )
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(
                "Explicit --ca-subject differs from the existing CA", result.stdout
            )
            self.assertEqual(self.fingerprints(target), before)
        result = self.signing(
            target, component="another-service", settings=settings[:2] + changed
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(
            all(
                self.fingerprints(target)[name] == value
                for name, value in before.items()
            )
        )
        self.assertEqual(self.certificate_info(ca), (subject, 17))
        self.assertEqual(self.certificate_info(second / "signing-cert.crt")[1], 5)
        # Demo issuance uses the same preflight and cannot silently use another CA.
        before = self.fingerprints(target)
        paths = sorted(str(path.relative_to(target)) for path in target.rglob("*"))
        result = self.run_script(
            "--root", str(target), *mismatch, "platform", "localhost"
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Explicit --ca-subject differs", result.stdout)
        self.assertEqual(self.fingerprints(target), before)
        self.assertEqual(
            sorted(str(path.relative_to(target)) for path in target.rglob("*")), paths
        )

    def test_invalid_ca_settings_write_nothing_in_all_modes(self):
        target = self.root / "must-not-exist"
        invalid = (
            ("--ca-days", "0"),
            ("--cert-days", "-1"),
            ("--ca-days", "abc"),
            ("--cert-days", "9999999"),
            ("--ca-subject", "CN=Missing slash"),
            ("--ca-subject", "/Unknown=value"),
            ("--ca-subject", "/C=NOR"),
            ("--ca-subject", "/CN=bad\nsubject"),
            ("--ca-subject", "/CN="),
            ("--ca-days", ""),
        )
        for options in invalid:
            for mode in (
                ("example.test",),
                ("platform", "example.test"),
                ("--component", "worker", "--purpose", "signing", "--pfx"),
            ):
                with self.subTest(options=options, mode=mode):
                    result = self.run_script("--root", str(target), *options, *mode)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("PrivateTestPassword", result.stdout)
                    self.assertFalse(target.exists())
        target, _ = self.signing_setup()
        before = self.fingerprints(target)
        result = self.signing(target, settings=("--ca-days", "0"))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.fingerprints(target), before)

    def test_relative_root_keeps_signing_material_in_requested_directory(self):
        target, directory = self.signing_setup()
        result = self.signing(target.relative_to(self.root))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((directory / "signing-cert.pfx").is_file())
        self.assertTrue((target / "PKI/private/ca.crt").is_file())
        self.assertFalse((target / target.name).exists())
