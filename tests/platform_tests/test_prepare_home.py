"""Real disposable filesystem tests; separate-UID/SELinux proof lives in acceptance."""

import os
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/prepare-host.sh"
# Upper bound for passing the here-document through a pipe on Linux bash builds.
PIPE_LIMIT = 16384


def helper_source():
    """The Python helper embedded in prepare-host.sh as a quoted here-document."""
    text = SCRIPT.read_text()
    start = text.index("<<'PREPARE_HOME'")
    return text[text.index("\n", start) + 1 : text.index("\nPREPARE_HOME\n", start) + 1]


HOME = types.ModuleType("prepare_home")
exec(compile(helper_source(), str(SCRIPT), "exec"), HOME.__dict__)  # noqa: S102 - trusted repository code


class HomeFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.home = self.base / "home"
        self.home.mkdir(mode=0o700)
        self.outside = self.base / "outside"
        self.outside.mkdir(mode=0o755)
        (self.outside / "sentinel").write_bytes(b"unchanged")

    def snapshot(self):
        return [
            (
                str(path.relative_to(self.outside)),
                path.stat().st_uid,
                stat.S_IMODE(path.stat().st_mode),
                path.read_bytes() if path.is_file() else None,
            )
            for path in [self.outside] + sorted(self.outside.rglob("*"))
        ]

    def test_fresh_repeat_keeps_lock_inode_contents_and_storage(self):
        HOME.prepare(str(self.home))
        lock = self.home / HOME.LOCK
        lock.write_bytes(b"existing lock")
        inode = lock.stat().st_ino
        storage = self.home / ".local/share/containers/storage"
        data = storage / "retained"
        data.write_bytes(b"container data")
        data.chmod(0o644)
        HOME.prepare(str(self.home))
        self.assertEqual(lock.stat().st_ino, inode)
        self.assertEqual(lock.read_bytes(), b"existing lock")
        self.assertEqual(data.read_bytes(), b"container data")
        self.assertEqual(stat.S_IMODE(data.stat().st_mode), 0o644)
        for relative in HOME.DIRECTORIES:
            self.assertEqual(stat.S_IMODE((self.home / relative).stat().st_mode), 0o700)

    def test_static_directory_links_and_dangling_links_refused_without_target_changes(
        self,
    ):
        for relative in HOME.DIRECTORIES:
            for dangling in (False, True):
                with self.subTest(relative=relative, dangling=dangling):
                    target = self.home / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(
                        self.outside / "missing" if dangling else self.outside
                    )
                    before = self.snapshot()
                    with self.assertRaises(OSError):
                        HOME.prepare(str(self.home))
                    self.assertEqual(self.snapshot(), before)
                    target.unlink()

    def test_existing_file_in_directory_chain_refused(self):
        (self.home / ".config").write_bytes(b"not a directory")
        with self.assertRaises(OSError):
            HOME.prepare(str(self.home))
        self.assertFalse((self.home / ".local").exists())

    def test_existing_lock_links_fifo_and_directory_refused(self):
        HOME.prepare(str(self.home))
        lock = self.home / HOME.LOCK
        for kind in ("link", "dangling", "fifo", "directory"):
            with self.subTest(kind=kind):
                lock.unlink()
                if kind == "fifo":
                    os.mkfifo(str(lock))
                elif kind == "directory":
                    lock.mkdir()
                else:
                    lock.symlink_to(
                        self.outside / ("missing" if kind == "dangling" else "sentinel")
                    )
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    HOME.prepare(str(self.home))
                self.assertEqual(self.snapshot(), before)
                if kind == "directory":
                    lock.rmdir()
                    lock.touch()

    def test_wrong_owner_refused_before_chmod(self):
        (self.home / ".config").mkdir(mode=0o755)
        original = HOME.os.geteuid()
        with mock.patch.object(
            HOME.os, "geteuid", side_effect=[original, original + 1]
        ):
            with self.assertRaisesRegex(
                ValueError, "owned by another user: .*\\.config"
            ):
                HOME.prepare(str(self.home))
        self.assertEqual(stat.S_IMODE((self.home / ".config").stat().st_mode), 0o755)
        self.assertFalse((self.home / ".local").exists())

    def test_directory_swap_before_open_is_refused_without_target_changes(self):
        real_open = os.open
        before = self.snapshot()

        def replace(path, flags, *args, **kwargs):
            if path == ".config" and not (self.home / ".config").exists():
                (self.home / ".config").symlink_to(self.outside)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(HOME.os, "open", side_effect=replace):
            with self.assertRaises(OSError):
                HOME.prepare(str(self.home))
        self.assertEqual(self.snapshot(), before)

    def test_directory_swap_after_open_chmods_only_held_object(self):
        HOME.prepare(str(self.home))
        real_chmod = os.fchmod
        before = self.snapshot()
        replaced = []

        def replace(descriptor, mode):
            if not replaced:
                (self.home / ".config").rename(self.home / ".config-held")
                (self.home / ".config").symlink_to(self.outside)
                replaced.append(True)
            real_chmod(descriptor, mode)

        with mock.patch.object(HOME.os, "fchmod", side_effect=replace):
            HOME.prepare(str(self.home))
        self.assertTrue(replaced)
        self.assertEqual(self.snapshot(), before)

    def test_lock_creation_race_preserves_regular_file_and_refuses_link(self):
        HOME.prepare(str(self.home))
        lock = self.home / HOME.LOCK
        real_open = os.open
        for symlink in (False, True):
            with self.subTest(symlink=symlink):
                lock.unlink()
                before = self.snapshot()

                def replace(path, flags, *args, symlink=symlink, **kwargs):
                    if path == "cni.lock" and flags & os.O_CREAT:
                        if symlink:
                            lock.symlink_to(self.outside / "sentinel")
                        else:
                            lock.write_bytes(b"concurrently created")
                    return real_open(path, flags, *args, **kwargs)

                with mock.patch.object(HOME.os, "open", side_effect=replace):
                    if symlink:
                        with self.assertRaises(ValueError):
                            HOME.prepare(str(self.home))
                    else:
                        HOME.prepare(str(self.home))
                        self.assertEqual(lock.read_bytes(), b"concurrently created")
                self.assertEqual(self.snapshot(), before)

    def test_retry_after_refusal(self):
        (self.home / ".config").symlink_to(self.outside)
        with self.assertRaises(OSError):
            HOME.prepare(str(self.home))
        (self.home / ".config").unlink()
        HOME.prepare(str(self.home))
        self.assertTrue((self.home / HOME.LOCK).is_file())

    def test_command_refuses_root(self):
        with mock.patch.object(HOME.os, "geteuid", return_value=0), mock.patch.object(
            sys, "argv", [str(SCRIPT), str(self.home)]
        ):
            with self.assertRaisesRegex(SystemExit, "non-root"):
                HOME.main()
        self.assertFalse((self.home / ".config").exists())

    def test_python_command_on_stdin_does_not_write_bytecode(self):
        result = subprocess.run(
            [sys.executable, "-B", "-"],
            input=helper_source(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-root", result.stderr)


class FapolicydDeliveryTests(unittest.TestCase):
    """fapolicyd denies reading untrusted Python files before a release is trusted."""

    def test_host_preparation_reads_no_shipped_python_file(self):
        shell = SCRIPT.read_text().replace(helper_source(), "")
        code = [
            line for line in shell.splitlines() if not line.lstrip().startswith("#")
        ]
        self.assertEqual([line for line in code if ".py" in line], [])
        self.assertEqual(
            sorted(
                path.name
                for path in SCRIPT.parent.iterdir()
                if path.name != "__pycache__"
            ),
            ["prepare-host.sh", "release.py"],
        )

    def test_embedded_helper_fits_a_pipe(self):
        """Larger here-documents fall back to a temporary file that fapolicyd checks."""
        self.assertLess(len(helper_source().encode()), PIPE_LIMIT)

    def test_bash_passes_the_here_document_through_a_pipe(self):
        program = (
            "python3 - <<'PREPARE_HOME'\n"
            "import os\nprint(os.readlink('/proc/self/fd/0'))\n"
            + helper_source().replace("if __name__", "if False and __name__")
            + "PREPARE_HOME\n"
        )
        result = subprocess.run(
            ["bash", "-c", program],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True,
        )
        self.assertTrue(result.stdout.startswith("pipe:"), result.stdout)
