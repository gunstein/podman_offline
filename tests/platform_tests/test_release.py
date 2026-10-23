"""Protected release publication and exact trust, with real archives/filesystem."""

import contextlib
import hashlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import yaml

SPEC = importlib.util.spec_from_file_location(
    "release_tool", Path(__file__).resolve().parents[2] / "scripts/release.py"
)
assert SPEC is not None and SPEC.loader is not None
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ProtectedReleaseTests(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "opt"
        self.base.mkdir()
        # Unit tests model root ownership without requiring root. Real separate-UID
        # enforcement is exercised by the OL9 acceptance probe.
        self.patch = mock.patch.object(release, "OWNER", os.getuid())
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.anchor = mock.patch.object(release, "ancestors")
        self.anchor.start()
        self.addCleanup(self.anchor.stop)
        self.product = self.base / "shop"
        # Explicit modes: a umask such as 0002 must not make the protected
        # anchor group-writable (release.py rightly refuses that).
        for directory in (self.product, self.product / "releases"):
            directory.mkdir()
            directory.chmod(0o755)
        self.trust_dir = self.root / "fapolicyd/trust.d"
        self.trust_dir.mkdir(parents=True)
        trust_patch = mock.patch.object(release, "TRUST_DIR", self.trust_dir)
        trust_patch.start()
        self.addCleanup(trust_patch.stop)
        self.key = self.product / "keyring.gpg"
        self.key.write_bytes(b"IndependentKey")
        self.key.chmod(0o644)
        self.signature = self.root / "signature"
        self.signature.write_bytes(b"Signature")
        self.name = "shop-worker-1.2.3"
        self.files = {
            "VERSION": b"1.2.3\n",
            "bundle.yaml": yaml.safe_dump(
                {"product": "shop", "name": "worker", "version": "1.2.3"}
            ).encode(),
            "deployment/common.py": b"original package\n",
            "components/worker/files/public.txt": b"public component file\n",
        }
        self.archive = self.root / "input.tar.gz"
        self.make_archive()
        self.calls = []

    def make_archive(self, extras=(), checksum_extra=True):
        files = dict(self.files)
        checks = "".join(
            hashlib.sha256(value).hexdigest() + "  " + key + "\n"
            for key, value in sorted(files.items())
        )
        files["checksums.sha256"] = checks.encode()
        if not checksum_extra:
            files["deployment/extra.py"] = b"unlisted"
        with tarfile.open(str(self.archive), "w:gz") as output:
            directories = {self.name}
            for key in files:
                directories.update(
                    str(parent)
                    for parent in (Path(self.name) / key).parents
                    if str(parent) != "."
                )
            for key in sorted(directories, key=lambda key: (key.count("/"), key)):
                member = tarfile.TarInfo(key)
                member.type = tarfile.DIRTYPE
                member.mode = 0o755
                output.addfile(member)
            for key, value in files.items():
                member = tarfile.TarInfo(self.name + "/" + key)
                member.size = len(value)
                member.mode = 0o644
                output.addfile(member, io.BytesIO(value))
            for member in extras:
                output.addfile(
                    member, io.BytesIO(b"x" * member.size) if member.isreg() else None
                )

    def command(self, arguments, allowed=(0,)):
        self.calls.append(arguments)
        if arguments[0] == "gpgv":
            # Snapshot, not caller-controlled original paths, is verified.
            self.assertNotEqual(arguments[-1], str(self.archive))
            self.assertEqual(
                Path(arguments[-1]).read_bytes(), self.archive.read_bytes()
            )
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    def publish(self):
        with mock.patch.object(release, "command", side_effect=self.command):
            return release.publish(
                self.product,
                self.archive,
                self.signature,
                "shop",
                "worker",
                "1.2.3",
            )

    def rows(self, path):
        record = release.published(path)
        return "".join(
            "file "
            + str(path / key)
            + " "
            + str(value["size"])
            + " "
            + value["sha256"]
            + "\n"
            for key, value in record["files"].items()
            if key.startswith("deployment/")
        )

    def test_publish_repeats_identical_archive_and_rejects_modified_existing_tree(self):
        path = self.publish()
        self.assertEqual(self.publish(), path)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(
            (path / "components/worker/files/public.txt").read_bytes(),
            self.files["components/worker/files/public.txt"],
        )
        self.assertEqual(path.stat().st_mode & 0o777, 0o755)
        for value in path.rglob("*"):
            self.assertFalse(value.stat().st_mode & 0o022)
        # Original reproduction: locally rewrite package AND checksums.
        (path / "deployment/common.py").write_bytes(b"attacker package\n")
        (path / "checksums.sha256").write_text("attacker checksum list")
        with self.assertRaisesRegex(release.ReleaseError, "inventory changed"):
            self.publish()

    def test_additional_published_file_and_same_version_new_archive_are_refused(self):
        path = self.publish()
        extra = path / "deployment/extra.py"
        extra.write_text("unlisted")
        extra.chmod(0o644)
        with self.assertRaises(release.ReleaseError):
            release.published(path)
        extra.unlink()
        # Fixture reset: directory mtime correctly records even removed extra files.
        shutil.rmtree(str(path))
        self.publish()
        self.files["deployment/common.py"] = b"different signed release"
        self.make_archive()
        with self.assertRaisesRegex(release.ReleaseError, "version conflict"):
            self.publish()
        self.assertEqual(
            (path / "deployment/common.py").read_bytes(), b"original package\n"
        )

    def test_archive_rejects_unlisted_files_identity_links_special_and_ambiguous_paths(
        self,
    ):
        for name, kind, mode in (
            ("../escape", tarfile.REGTYPE, 0o644),
            (self.name + "/deployment/link", tarfile.SYMTYPE, 0o644),
            (self.name + "/deployment/hard", tarfile.LNKTYPE, 0o644),
            (self.name + "/deployment/fifo", tarfile.FIFOTYPE, 0o644),
            (self.name + "/deployment/device", tarfile.CHRTYPE, 0o644),
            (self.name + "/deployment/../alias", tarfile.REGTYPE, 0o644),
            (self.name + "/deployment/common.py", tarfile.REGTYPE, 0o644),
            (self.name + "/deployment/setuid", tarfile.REGTYPE, 0o4755),
            (self.name + "/deployment/writable", tarfile.REGTYPE, 0o666),
        ):
            with self.subTest(name=name, kind=kind):
                member = tarfile.TarInfo(name)
                member.type, member.mode, member.linkname = kind, mode, "/outside"
                self.make_archive([member])
                with self.assertRaises(release.ReleaseError):
                    self.publish()
                self.assertEqual(list((self.product / "releases").iterdir()), [])
        self.make_archive(checksum_extra=False)
        with self.assertRaisesRegex(release.ReleaseError, "checksum inventory"):
            self.publish()
        self.files["bundle.yaml"] = b"product: other\nname: worker\nversion: 1.2.3\n"
        self.make_archive()
        with self.assertRaisesRegex(release.ReleaseError, "identity mismatch"):
            self.publish()

    def test_signature_rejection_happens_before_extraction_or_host_execution(self):
        with mock.patch.object(
            release, "command", side_effect=release.ReleaseError("bad signature")
        ), mock.patch.object(release, "extract") as extract, self.assertRaises(
            release.ReleaseError
        ):
            release.publish(
                self.product,
                self.archive,
                self.signature,
                "shop",
                "worker",
                "1.2.3",
            )
        extract.assert_not_called()
        self.assertEqual(list((self.product / "releases").iterdir()), [])

    def test_failed_command_preserves_executable_and_status_for_signature_probe(self):
        result = types.SimpleNamespace(returncode=2, stdout="private", stderr="private")
        with mock.patch.object(release.subprocess, "run", return_value=result):
            with self.assertRaises(release.CommandError) as observed:
                release.command(["gpgv", "signature", "archive"])
        self.assertEqual(observed.exception.executable, "gpgv")
        self.assertEqual(observed.exception.returncode, 2)
        self.assertIsInstance(observed.exception, release.ReleaseError)
        self.assertNotIn("private", str(observed.exception))

    def test_live_trust_requires_authenticated_size_hash_and_unique_exact_paths(self):
        path = self.publish()
        valid = self.rows(path)
        cases = (
            "",
            "invalid\n",
            valid.replace(" 17 ", " 18 "),
            valid[:-65] + "a" * 64 + "\n",
            valid + valid,
            valid
            + "file "
            + str(path / "deployment/extra.py")
            + " 0 "
            + "a" * 64
            + "\n",
        )
        for rows in cases:
            with self.subTest(rows=rows), mock.patch.object(
                release, "command", return_value=types.SimpleNamespace(stdout=rows)
            ), self.assertRaises(release.ReleaseError):
                release.wait_trust(path, attempts=1)
        unrelated = "rpmdb /usr/lib/file with spaces 1 " + "b" * 64 + "\n"
        with mock.patch.object(
            release,
            "command",
            return_value=types.SimpleNamespace(stdout=unrelated + valid),
        ):
            release.wait_trust(path, attempts=1)

    def test_interrupted_trust_keeps_published_tree_for_new_process_retry(self):
        path = self.publish()
        with mock.patch.object(release, "integrity_policy"), mock.patch.object(
            release, "command", side_effect=release.ReleaseError("trust failed")
        ), self.assertRaises(release.ReleaseError):
            release.enroll(path)
        self.assertEqual(self.publish(), path)
        with mock.patch.object(release, "integrity_policy"), mock.patch.object(
            release,
            "command",
            return_value=types.SimpleNamespace(
                returncode=0, stdout=self.rows(path), stderr=""
            ),
        ) as commands:
            release.enroll(path)
        self.assertTrue(
            all("--file" not in call.args[0] for call in commands.call_args_list)
        )
        expected = self.rows(path).replace("file ", "")
        self.assertIn(
            expected, (self.trust_dir / "podman-offline-shop.worker").read_text()
        )

    def test_replaced_input_after_signature_check_does_not_change_extracted_snapshot(
        self,
    ):
        original = self.archive.read_bytes()

        def replace_original(arguments, allowed=(0,)):
            self.assertEqual(Path(arguments[-1]).read_bytes(), original)
            self.archive.write_bytes(b"replaced input after snapshot verification")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(release, "command", side_effect=replace_original):
            path = release.publish(
                self.product,
                self.archive,
                self.signature,
                "shop",
                "worker",
                "1.2.3",
            )
        self.assertEqual(
            (path / "deployment/common.py").read_bytes(), b"original package\n"
        )
        self.assertEqual(
            release.published(path)["archive_sha256"],
            hashlib.sha256(original).hexdigest(),
        )

    def test_publication_failure_exposes_no_partial_release_and_retry_works(self):
        with mock.patch.object(
            release.os, "rename", side_effect=OSError("publication failed")
        ):
            with self.assertRaises(OSError):
                self.publish()
        self.assertEqual(list((self.product / "releases").iterdir()), [])
        self.assertEqual(list(self.product.glob(".staging-*")), [])
        self.assertEqual(self.publish().name, self.name)

    def test_product_lock_blocks_concurrent_helper_and_refuses_linked_parent(self):
        with mock.patch.object(release, "BASE", self.base):
            with release.product_lock("shop"):
                with mock.patch.object(release.time, "monotonic", side_effect=[0, 61]):
                    with self.assertRaisesRegex(release.ReleaseError, "lock timed out"):
                        with release.product_lock("shop"):
                            self.fail("concurrent lock acquired")
            releases = self.product / "releases"
            releases.rmdir()
            releases.symlink_to(self.root, target_is_directory=True)
            with self.assertRaises(release.ReleaseError):
                with release.product_lock("shop"):
                    self.fail("symlink parent accepted")

    def test_retirement_failure_preserves_old_tree_and_retry_removes_only_old_release(
        self,
    ):
        old = self.publish()
        # Build a second authenticated release without borrowing old provenance.
        self.name = "shop-worker-1.2.4"
        self.files["VERSION"] = b"1.2.4\n"
        self.files["bundle.yaml"] = b"product: shop\nname: worker\nversion: 1.2.4\n"
        self.make_archive()
        with mock.patch.object(release, "command", side_effect=self.command):
            new = release.publish(
                self.product,
                self.archive,
                self.signature,
                "shop",
                "worker",
                "1.2.4",
            )
        sibling = self.product / "releases/shop-other-1.0.0"
        sibling.mkdir()
        marker = sibling / "retained"
        marker.write_text("sibling data")
        argv = [
            "release.py",
            "retire",
            "--product",
            "shop",
            "--component",
            "worker",
            "--version",
            "1.2.4",
            "--old-version",
            "1.2.3",
        ]
        calls = []

        def command(arguments, allowed=(0,)):
            calls.append(arguments)
            return types.SimpleNamespace(
                returncode=0, stdout=self.rows(new) + self.rows(old), stderr=""
            )

        with mock.patch.object(release, "BASE", self.base), mock.patch.object(
            release, "withdraw"
        ), mock.patch.object(release.os, "geteuid", return_value=0), mock.patch(
            "sys.argv", argv
        ):
            with mock.patch.object(
                release, "command", side_effect=command
            ), mock.patch.object(
                release, "wait_trust", side_effect=release.ReleaseError("not ready")
            ):
                with self.assertRaises(release.ReleaseError):
                    release.main()
            self.assertTrue(old.is_dir())
            with mock.patch.object(
                release, "command", side_effect=command
            ), mock.patch.object(release, "wait_trust") as ready:
                release.main()
            ready.assert_called_once_with(new, old)
        self.assertFalse(old.exists())
        self.assertTrue(new.is_dir())
        self.assertEqual(marker.read_text(), "sibling data")
        self.assertTrue(all(str(sibling) not in arg for call in calls for arg in call))

    def test_interrupted_retirement_deletion_resumes_from_protected_journal(self):
        old = self.publish()
        # The keep tree only supplies an authenticated ready boundary in this
        # filesystem regression; full lifecycle/identity checks have separate tests.
        keep = self.product / "releases/shop-worker-1.2.4"
        with mock.patch.object(release, "withdraw"), mock.patch.object(
            release, "wait_trust"
        ):

            def interrupt(directory):
                (Path(directory) / "deployment/common.py").unlink()
                raise OSError("interrupted retirement deletion")

            with mock.patch.object(release.shutil, "rmtree", side_effect=interrupt):
                with self.assertRaises(OSError):
                    release.retire(self.product, keep, old)
            self.assertFalse(old.exists())
            self.assertTrue((self.product / (".retired-" + old.name)).exists())
            self.assertTrue(
                (self.product / (".retirement-" + old.name + ".json")).exists()
            )
            retry = """import os,sys
from pathlib import Path
namespace = {'__name__': 'fresh_retry_helper'}
exec(compile(Path(sys.argv[1]).read_text(), sys.argv[1], 'exec'), namespace)
namespace['OWNER'] = os.getuid()
namespace['ancestors'] = lambda path: None
namespace['wait_trust'] = lambda *args: None
namespace['withdraw'] = lambda *args: None
namespace['retire'](Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
"""
            assert release.__file__ is not None
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    retry,
                    str(Path(release.__file__)),
                    str(self.product),
                    str(keep),
                    str(old),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.product / (".retired-" + old.name)).exists())
        self.assertFalse(
            (self.product / (".retirement-" + old.name + ".json")).exists()
        )

    def test_withdraw_waits_for_removal_without_deleting_release_or_unrelated_trust(
        self,
    ):
        path = self.publish()
        release.scoped_trust(path)
        own = self.rows(path)
        sibling = (
            "file /opt/shop/releases/shop-other-1.0.0/deployment/main.py 1 "
            + "b" * 64
            + "\n"
        )
        outputs = iter((own + sibling, own + sibling, sibling))
        calls = []

        def command(arguments, allowed=(0,)):
            calls.append(arguments)
            return types.SimpleNamespace(
                stdout=next(outputs) if arguments[-1] == "--dump-db" else "",
                returncode=0,
            )

        with mock.patch.object(
            release, "command", side_effect=command
        ), mock.patch.object(release.time, "sleep"):
            release.withdraw(path)
        self.assertTrue(path.is_dir())
        self.assertFalse(any("--file" in args for args in calls))
        self.assertNotIn(
            str(path / "deployment"),
            (self.trust_dir / "podman-offline-shop.worker").read_text(),
        )

    def test_no_payload_read_before_trust_and_same_size_writes_invalidate_bindings(
        self,
    ):
        original_open = Path.open

        def no_untrusted_open(path, mode="r", *args, **kwargs):
            if path.suffix == ".py" and "r" in mode:
                raise PermissionError("simulated fapolicyd language denial")
            return original_open(path, mode, *args, **kwargs)

        with mock.patch.object(Path, "open", no_untrusted_open):
            path = self.publish()
            self.publish()
            release.scoped_trust(path)
        source = path / "deployment/common.py"
        source.write_bytes(b"x" * source.stat().st_size)
        with self.assertRaisesRegex(release.ReleaseError, "inventory changed"):
            release.published(path)

    def test_scoped_trust_updates_preserve_other_versions_and_refuse_unauthenticated_rows(
        self,
    ):
        old = self.publish()
        release.scoped_trust(old)
        original = (self.trust_dir / "podman-offline-shop.worker").read_text()
        release.scoped_trust(old)
        self.assertEqual(
            (self.trust_dir / "podman-offline-shop.worker").read_text(), original
        )
        self.name = "shop-worker-1.2.4"
        self.files["VERSION"] = b"1.2.4\n"
        self.files["bundle.yaml"] = b"product: shop\nname: worker\nversion: 1.2.4\n"
        self.make_archive()
        with mock.patch.object(release, "command", side_effect=self.command):
            new = release.publish(
                self.product,
                self.archive,
                self.signature,
                "shop",
                "worker",
                "1.2.4",
            )
        release.scoped_trust(new)
        text = (self.trust_dir / "podman-offline-shop.worker").read_text()
        self.assertIn(str(old / "deployment/common.py"), text)
        self.assertIn(str(new / "deployment/common.py"), text)
        with mock.patch.object(
            release.os, "replace", side_effect=OSError("atomic write failed")
        ):
            with self.assertRaises(OSError):
                release.scoped_trust(old, remove=True)
        self.assertEqual(
            (self.trust_dir / "podman-offline-shop.worker").read_text(), text
        )
        release.scoped_trust(old, remove=True)
        self.assertNotIn(
            str(old / "deployment/common.py"),
            (self.trust_dir / "podman-offline-shop.worker").read_text(),
        )
        self.assertIn(
            str(new / "deployment/common.py"),
            (self.trust_dir / "podman-offline-shop.worker").read_text(),
        )
        (self.trust_dir / "podman-offline-shop.worker").write_text(
            text.replace(" 17 ", " 18 ")
        )
        with self.assertRaisesRegex(release.ReleaseError, "differs from authenticated"):
            release.scoped_trust(new)

    def test_independent_key_digest_is_checked_on_snapshot_and_rotation_is_refused(
        self,
    ):
        self.key = self.root / "incoming-keyring"
        self.key.write_bytes(b"IndependentKey")
        (self.product / "keyring.gpg").unlink()
        expected = hashlib.sha256(self.key.read_bytes()).hexdigest()
        argv = [
            "release.py",
            "provision-key",
            "--product",
            "shop",
            "--keyring",
            str(self.key),
            "--key-sha256",
            "0" * 64,
        ]
        target = self.product / "keyring.gpg"
        with mock.patch.object(release, "BASE", self.base), mock.patch.object(
            release.os, "geteuid", return_value=0
        ), mock.patch("sys.argv", argv):
            with self.assertRaisesRegex(
                release.ReleaseError, "authentication mismatch"
            ):
                release.main()
            self.assertFalse(target.exists())
            argv[-1] = expected
            release.main()
            release.main()
            retained = target.read_bytes()
            self.key.write_bytes(b"different key")
            with self.assertRaisesRegex(
                release.ReleaseError, "authentication mismatch"
            ):
                release.main()
            argv[-1] = hashlib.sha256(self.key.read_bytes()).hexdigest()
            with self.assertRaisesRegex(
                release.ReleaseError, "existing keyring differs"
            ):
                release.main()
            self.assertEqual(target.read_bytes(), retained)

    def test_protected_checks_reject_writable_links_hardlinks_and_acl(self):
        path = self.root / "file"
        path.write_text("bytes")
        path.chmod(0o666)
        with self.assertRaises(release.ReleaseError):
            release.protected(path)
        path.chmod(0o644)
        link = self.root / "link"
        link.symlink_to(path)
        with self.assertRaises(release.ReleaseError):
            release.protected(link)
        link.unlink()
        os.link(str(path), str(link))
        with self.assertRaises(release.ReleaseError):
            release.protected(path)
        link.unlink()
        with mock.patch.object(
            release.os, "getxattr", return_value=b"acl"
        ), self.assertRaises(release.ReleaseError):
            release.protected(path)

    def test_relabel_preserves_repeat_publication_old_trust_and_retirement(self):
        old = self.publish()
        before = release.published(old)
        release.scoped_trust(old)
        payload = old / "deployment/common.py"
        ctime = payload.stat().st_ctime_ns
        # SELinux also changes xattrs/ctime. A user xattr needs no SELinux host.
        for entry in [old] + list(old.rglob("*")):
            os.setxattr(str(entry), "user.relabel-test", b"new-label")
        self.assertNotEqual(payload.stat().st_ctime_ns, ctime)
        self.assertEqual(release.published(old), before)
        self.assertEqual(self.publish(), old)
        self.name = "shop-worker-1.2.4"
        self.files["VERSION"] = b"1.2.4\n"
        self.files["bundle.yaml"] = b"product: shop\nname: worker\nversion: 1.2.4\n"
        self.make_archive()
        with mock.patch.object(release, "command", side_effect=self.command):
            new = release.publish(
                self.product, self.archive, self.signature, "shop", "worker", "1.2.4"
            )
        release.scoped_trust(new)  # Must still validate retained relabeled version.
        with mock.patch.object(
            release,
            "command",
            return_value=types.SimpleNamespace(stdout=self.rows(new)),
        ):
            release.wait_trust(new)
            release.retire(self.product, new, old)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        trust = (self.trust_dir / "podman-offline-shop.worker").read_text()
        self.assertNotIn(str(old), trust)
        self.assertIn(str(new), trust)

    def test_publication_uses_only_pinned_key_and_unsigned_cli_is_refused(self):
        self.publish()
        self.assertEqual(self.calls[-1][4], str(self.product / "keyring.gpg"))
        argv = [
            "release.py",
            "publish",
            "--product",
            "shop",
            "--component",
            "worker",
            "--version",
            "1.2.3",
            "--archive",
            str(self.archive),
        ]
        with mock.patch.object(release, "BASE", self.base), mock.patch.object(
            release.os, "geteuid", return_value=0
        ), mock.patch.object(release, "publish") as publish, mock.patch(
            "sys.argv", argv
        ):
            with self.assertRaisesRegex(release.ReleaseError, "unsigned production"):
                release.main()
            publish.assert_not_called()
            argv.extend(
                ["--signature", str(self.signature), "--keyring", str(self.key)]
            )
            with self.assertRaisesRegex(
                release.ReleaseError, "only accepted for provision-key"
            ):
                release.main()
            publish.assert_not_called()
            del argv[-2:]
            release.main()
            self.assertEqual(
                publish.call_args.args,
                (self.product, self.archive, self.signature, "shop", "worker", "1.2.3"),
            )

    def test_diagnostics_identify_step_and_public_path_without_private_error_text(self):
        for error in (
            OSError(13, "secret-password", "/credentials/private-value"),
            KeyError("secret-password"),
            ValueError("secret-password"),
        ):
            with self.subTest(kind=type(error).__name__):
                try:
                    with release.diagnostic("publish", Path("deployment/common.py")):
                        raise error
                except release.ReleaseError as observed:
                    text = str(observed)
                self.assertIn("publish [deployment/common.py]", text)
                self.assertNotIn("secret-password", text)
                self.assertNotIn("credentials", text)
        path = self.publish()
        (path / release.RECORD).write_text("{}")
        with self.assertRaisesRegex(
            release.ReleaseError,
            "validate published inventory.*missing provenance field",
        ):
            release.published(path)

    def test_anchor_chain_rejects_service_writable_ancestor_and_existing_symlink(self):
        self.anchor.stop()
        anchor = self.root / "anchor"
        anchor.mkdir(mode=0o777)
        anchor.chmod(0o777)
        with self.assertRaises(release.ReleaseError):
            release.ancestors(anchor / "child")
        with mock.patch.object(release, "BASE", self.base):
            (self.product / "releases").rmdir()
            (self.product / "releases").symlink_to(self.root, target_is_directory=True)
            # /tmp itself is also writable and is deliberately rejected.
            with self.assertRaises(release.ReleaseError):
                with release.product_lock("shop"):
                    self.fail("unsafe anchor was accepted")
