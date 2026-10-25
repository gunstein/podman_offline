"""Local LMDB concurrency and fail-closed tests; no lab access."""

import ctypes
import ctypes.util
import importlib
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent / "rpm_wp0"))
op = importlib.import_module("operations")

# Real LMDB fixture, separate processes as required by LMDB's environment API.
LMDB = r"""
import ctypes as c
import os
import sys
lib = c.CDLL("liblmdb.so.0")
class Value(c.Structure):
    _fields_ = [("size", c.c_size_t), ("data", c.c_void_p)]
def bind(name, args, result=c.c_int):
    fn = getattr(lib, name)
    fn.argtypes, fn.restype = args, result
    return fn
ptr = c.c_void_p
create = bind("mdb_env_create", [c.POINTER(ptr)])
size = bind("mdb_env_set_mapsize", [ptr, c.c_size_t])
open_env = bind("mdb_env_open", [ptr, c.c_char_p, c.c_uint, c.c_uint])
begin = bind("mdb_txn_begin", [ptr, ptr, c.c_uint, c.POINTER(ptr)])
dbi_open = bind("mdb_dbi_open", [ptr, c.c_char_p, c.c_uint, c.POINTER(c.c_uint)])
put = bind("mdb_put", [ptr, c.c_uint, c.POINTER(Value), c.POINTER(Value), c.c_uint])
get = bind("mdb_get", [ptr, c.c_uint, c.POINTER(Value), c.POINTER(Value)])
commit = bind("mdb_txn_commit", [ptr])
abort = bind("mdb_txn_abort", [ptr], None)
close = bind("mdb_env_close", [ptr], None)
def check(code):
    assert code == 0, code
def environment(flags):
    env = ptr()
    check(create(c.byref(env)))
    check(size(env, 64 * 1024 * 1024))
    check(open_env(env, os.fsencode(os.environ["WP0_TEST_DB"]), flags, 0o600))
    return env
def transaction(env, flags):
    txn, db = ptr(), c.c_uint()
    check(begin(env, None, flags, c.byref(txn)))
    check(dbi_open(txn, None, 0, c.byref(db)))
    return txn, db
key_bytes = c.create_string_buffer(b"key")
key = Value(3, c.cast(key_bytes, ptr))
"""
WRITER = (
    LMDB
    + r"""
env = environment(0)
for i in range(int(sys.argv[1])):
    txn, db = transaction(env, 0)
    data = c.create_string_buffer(bytes([65 + i % 26]) * 8192)
    value = Value(8192, c.cast(data, ptr))
    check(put(txn, db, c.byref(key), c.byref(value), 0))
    check(commit(txn))
close(env)
"""
)
READER = (
    LMDB
    + r"""
import subprocess
# Match the CLI's unregistered reader, with a concurrent writer recycling pages.
env = environment(0x20000 | 0x400000)
txn, db = transaction(env, 0x20000)
value = Value()
check(get(txn, db, c.byref(key), c.byref(value)))
assert c.string_at(value.data, value.size) == b"A" * 8192
subprocess.run([sys.executable, os.environ["WP0_TEST_WRITER"], "128"], check=True)
assert c.string_at(value.data, value.size) == b"A" * 8192
abort(txn)
close(env)
print("snapshot preserved across 128 writer transactions")
"""
)


class TrustReaderTests(unittest.TestCase):
    def setUp(self):
        op.TRANSCRIPT.clear()

    def test_reader_resolves_ol9_soname_and_refuses_missing_library(self):
        for library in ("liblmdb.so.0.0.0", None):
            with (
                self.subTest(library=library),
                mock.patch.object(
                    ctypes.util, "find_library", return_value=library
                ) as find,
                mock.patch.object(
                    ctypes, "CDLL", side_effect=RuntimeError("load sentinel")
                ) as load,
                self.assertRaisesRegex(
                    RuntimeError, "load sentinel" if library else "not found"
                ),
            ):
                exec(op.TRUST_DUMP_READER, {})  # noqa: S102 - fixed repository helper source
            find.assert_called_once_with("lmdb")
            if library:
                load.assert_called_once_with(library)
            else:
                load.assert_not_called()

    def test_registered_reader_protects_real_lmdb_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "db"
            db.mkdir()
            writer = root / "writer.py"
            writer.write_text(WRITER)
            cli = root / "fapolicyd-cli"
            cli.write_text("#!" + sys.executable + "\n" + READER)
            cli.chmod(0o700)
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "PATH": str(root) + os.pathsep + os.environ["PATH"],
                        "WP0_TEST_DB": str(db),
                        "WP0_TEST_WRITER": str(writer),
                    },
                ),
                mock.patch.object(op, "TRUST_DB", db),
            ):
                subprocess.run([sys.executable, str(writer), "1"], check=True)
                self.assertEqual(
                    op.guarded_trust_dump(10).strip(),
                    "snapshot preserved across 128 writer transactions",
                )
            self.assertEqual(op.TRANSCRIPT[-1]["exit"], 0)

    def test_guard_failure_never_runs_cli_or_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "executed"
            cli = root / "fapolicyd-cli"
            cli.write_text("#!/bin/sh\ntouch '" + str(marker) + "'\n")
            cli.chmod(0o700)
            with (
                mock.patch.dict(os.environ, {"PATH": str(root)}),
                mock.patch.object(op, "TRUST_DB", root / "missing"),
                mock.patch.object(
                    op.subprocess, "Popen", wraps=subprocess.Popen
                ) as popen,
            ):
                # Keep Python reachable while hiding all possible real CLI binaries.
                (root / "python3").symlink_to(sys.executable)
                with self.assertRaisesRegex(RuntimeError, "guarded fapolicyd-cli"):
                    op.guarded_trust_dump(5)
                self.assertEqual(popen.call_count, 1)
            self.assertFalse(marker.exists())
            self.assertNotEqual(op.TRANSCRIPT[-1]["exit"], 0)

    def test_timeout_kills_guard_and_cli_group_and_preserves_evidence(self):
        process = mock.Mock(pid=12345, returncode=-9)
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("guard", 0.25),
            ("partial dump", "partial diagnostic"),
        ]
        with (
            mock.patch.object(op.subprocess, "Popen", return_value=process) as popen,
            mock.patch.object(op.os, "killpg") as kill,
            self.assertRaisesRegex(RuntimeError, "poll deadline"),
        ):
            op.guarded_trust_dump(0.25)
        kill.assert_called_once_with(12345, signal.SIGKILL)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(process.communicate.call_args_list[0], mock.call(timeout=0.25))
        self.assertTrue(op.TRANSCRIPT[-1]["timed_out"])
        self.assertEqual(op.TRANSCRIPT[-1]["stdout"], "partial dump")

    def test_cli_failure_stops_poll_without_retry_or_accepting_partial_dump(self):
        process = mock.Mock(returncode=134)
        process.communicate.return_value = ("rpmdb /x 1 abc", "CLI aborted")
        with (
            mock.patch.object(op, "trust_inventory", return_value={"/x": (1, "abc")}),
            mock.patch.object(op.subprocess, "Popen", return_value=process) as popen,
            self.assertRaisesRegex(RuntimeError, "guarded fapolicyd-cli"),
        ):
            op.wait_trust(["fixture"])
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(op.TRANSCRIPT[-1]["exit"], 134)


if __name__ == "__main__":
    unittest.main()
