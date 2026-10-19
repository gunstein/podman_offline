"""Exercise the certificate script only in disposable directories."""

import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


class CertificateTests(unittest.TestCase):
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
            Path(__file__).resolve().parent.parent / "dev/generate-certificates.sh",
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

    def signing(self, target, component="my-identity", stdin=False):
        args = [
            "--root",
            str(target),
            "--component",
            component,
            "--purpose",
            "signing",
            "--pfx",
        ]
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
            universal_newlines=True,  # noqa: UP021 - Python 3.6
        )

    def pem_pair(self, directory, stem="signing-cert"):
        subprocess.run(  # noqa: UP022 - Python 3.6
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
        result = subprocess.run(  # noqa: UP022 - Python 3.6
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
        self.assert_signing_failure(target, self.fingerprints(target))
        (directory / "signing-cert.key").unlink()
        ca = target / "PKI/private"
        ca.mkdir(parents=True)
        (ca / "ca.crt").write_bytes(b"incomplete")
        self.assert_signing_failure(target, self.fingerprints(target))

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
        subprocess.run(  # noqa: UP022 - Python 3.6
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
