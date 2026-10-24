"""Execute the canonical manual bootstrap, with a private target/UID stand-in."""

import errno
import hashlib
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers.product_fixture import WORKER, ProductFixture

ROOT = Path(__file__).resolve().parents[2]


def bootstrap_source():
    manual = (ROOT / "docs/PRODUCTION-INSTALL.md").read_text()
    match = re.search(
        r"<!-- operator: tool-bootstrap -->\n```sh\n[^\n]+<<'PY'\n(.*?)\nPY\n```",
        manual,
        re.DOTALL,
    )
    assert match is not None
    return match.group(1)


class HostBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "libexec/helper.gz"
        self.incoming = self.root / "incoming.gz"
        self.incoming.write_bytes(b"unexecutable compressed transport stand-in")
        self.expected = hashlib.sha256(self.incoming.read_bytes()).hexdigest()

    def run_bootstrap(self, expected=None):
        # Only substitute the fixed destination and modeled root UID; the
        # documented validation/copy/hash/publish algorithm is executed intact.
        source = bootstrap_source().replace(
            "Path('/usr/local/libexec/podman-offline-release.py.gz')",
            "Path(" + repr(str(self.target)) + ")",
        )
        source = source.replace(
            "info.st_uid != 0", "info.st_uid != " + str(os.getuid())
        )
        ancestors = set(self.root.parents)
        original = os.getxattr

        def xattr(path, attribute, **kwargs):
            # Real system ancestors are outside the fixture's ownership scope.
            if Path(path) in ancestors:
                raise OSError(errno.ENODATA, "no fixture ACL")
            return original(path, attribute, **kwargs)

        # The trusted-ancestor loop uses this fixture as its top anchor.
        source = source.replace(
            "reversed((target.parent,) + tuple(target.parent.parents))",
            "[Path(" + repr(str(self.root)) + "), target.parent]",
        )
        with mock.patch.object(os, "geteuid", return_value=0), mock.patch.object(
            os, "getxattr", side_effect=xattr
        ), mock.patch.object(
            sys, "argv", ["-", str(self.incoming), expected or self.expected]
        ):
            exec(compile(source, "manual-bootstrap", "exec"), {})  # noqa: S102 - canonical trusted snippet

    def test_authenticates_snapshot_before_publication_and_retains_on_mismatch(self):
        self.run_bootstrap()
        original = self.target.read_bytes(), self.target.stat().st_mode & 0o777
        self.incoming.write_bytes(b"wrong upload")
        with self.assertRaisesRegex(SystemExit, "SHA256 mismatch"):
            self.run_bootstrap()
        self.assertEqual(
            (self.target.read_bytes(), self.target.stat().st_mode & 0o777), original
        )
        self.assertEqual(list(self.target.parent.glob(".bootstrap-*")), [])

    def test_rejects_link_fifo_and_unsafe_existing_target(self):
        self.target.parent.mkdir(mode=0o755)
        self.target.symlink_to(self.incoming)
        with self.assertRaisesRegex(SystemExit, "Unsafe protected path"):
            self.run_bootstrap()
        self.target.unlink()
        os.mkfifo(str(self.target))
        with self.assertRaisesRegex(SystemExit, "Unsafe protected path"):
            self.run_bootstrap()
        self.target.unlink()
        self.target.write_bytes(b"old")
        self.target.chmod(0o666)
        with self.assertRaisesRegex(SystemExit, "Unsafe protected path"):
            self.run_bootstrap()
        self.assertEqual(self.target.read_bytes(), b"old")

    def test_rejects_source_link_hardlink_target_and_acl(self):
        real = self.root / "real"
        self.incoming.rename(real)
        self.incoming.symlink_to(real)
        with self.assertRaisesRegex(SystemExit, "I/O failure"):
            self.run_bootstrap()
        self.incoming.unlink()
        real.rename(self.incoming)
        self.target.parent.mkdir(exist_ok=True)
        os.link(str(self.incoming), str(self.target))
        with self.assertRaisesRegex(SystemExit, "Unsafe protected path"):
            self.run_bootstrap()
        self.target.unlink()
        with mock.patch.object(
            os, "getxattr", return_value=b"acl"
        ), self.assertRaisesRegex(SystemExit, "ACL"):
            self.run_bootstrap()

    def test_upload_replacement_does_not_change_the_authenticated_copy(self):
        previous = self.incoming.read_bytes()
        original_replace = os.replace

        def replace(source, target):
            self.incoming.write_bytes(b"replacement after copy")
            original_replace(source, target)

        with mock.patch.object(os, "replace", side_effect=replace):
            self.run_bootstrap()
        self.assertEqual(self.target.read_bytes(), previous)

    def test_bootstrap_refuses_unsafe_ancestor_without_publishing(self):
        self.target.parent.mkdir(mode=0o755)
        self.target.parent.chmod(0o777)
        with self.assertRaisesRegex(SystemExit, "Unsafe protected path"):
            self.run_bootstrap()
        self.assertFalse(self.target.exists())
        self.target.parent.chmod(0o755)
        self.target.parent.rmdir()
        other = self.root / "other"
        other.mkdir()
        self.target.parent.symlink_to(other)
        with self.assertRaisesRegex(SystemExit, "Unsafe protected path"):
            self.run_bootstrap()
        self.assertEqual(list(other.iterdir()), [])


class OperatorBundleDocsTests(ProductFixture):
    def test_manual_and_required_links_work_after_source_deletion(self):
        self.product_name = "cedar"
        self.write_product(WORKER)
        (self.source / "docs").mkdir()
        for name in ("PRODUCTION-INSTALL.md", "PFX-CREDENTIALS.md"):
            shutil.copy2(ROOT / "docs" / name, self.source / "docs" / name)
        unpacked = self.build_and_unpack()["worker"]
        shutil.rmtree(str(self.source))
        manual = unpacked / "docs/PRODUCTION-INSTALL.md"
        self.assertEqual(
            manual.read_bytes(), (ROOT / "docs/PRODUCTION-INSTALL.md").read_bytes()
        )
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", manual.read_text()):
            if "://" not in target:
                self.assertTrue(
                    (manual.parent / target.split("#")[0]).is_file(), target
                )
        self.assertIn("init-layout", manual.read_text())
