# WP0 trust-dump reader correction

The second matrix run stopped in R4/P1 when `fapolicyd-cli --dump-db`
aborted inside LMDB. The historical evidence remains in
[RPM-WP0-LAB-20261025-RUN02.md](RPM-WP0-LAB-20261025-RUN02.md).

## Cause and bounded correction

The baseline uses fapolicyd 1.4.5. Its
[CLI source](https://github.com/linux-application-whitelisting/fapolicyd/blob/v1.4.5/src/cli/fapolicyd-cli.c)
opens the trust database with `MDB_RDONLY | MDB_NOLOCK`, while the
[daemon](https://github.com/linux-application-whitelisting/fapolicyd/blob/v1.4.5/src/library/database.c)
updates it using normal LMDB transactions. An unregistered reader can traverse
pages recycled by a concurrent writer. This is consistent with the observed
cursor assertion; the lab evidence alone does not prove the precise race.

`operations.guarded_trust_dump` now supervises the CLI in a separate process.
Before launching the unchanged CLI, that process opens a normal `MDB_RDONLY`
transaction through the installed `liblmdb.so.0` and holds it until the CLI
exits. LMDB's oldest registered reader prevents page recycling across the
newer CLI snapshot. See the
[LMDB API contract](https://github.com/LMDB/lmdb/blob/LMDB_0.9.29/libraries/liblmdb/lmdb.h).
The guard changes LMDB reader bookkeeping in the lock file; it does not write
trust records, change policy, restart the daemon or authorize an executable.

The entire process group shares the remaining 30-second polling budget,
including reader acquisition and CLI execution. A timeout kills both guard
and CLI, records partial output and stops. A guard failure or nonzero CLI exit
also stops immediately. There is no retry after a CLI error. Normal successful
dumps still pass through the existing exact path, size, SHA256 and `rpmdb`
source predicate. `src_unknown` is still rejected, even alongside a valid
`rpmdb` row. The 5-second lock limit is unaffected.

## Local evidence and review

`acceptance/test_rpm_wp0_reader.py` requires the shared LMDB library on the
contributor machine. It uses a temporary database, a real unregistered LMDB
reader and a separate writer performing 128 transactions. The protected
snapshot remains intact. Other tests cover guard failure before CLI execution,
process-group timeout with preserved output, and CLI failure without retry or
accepting otherwise valid partial output. These are local harness tests, not
OL9 evidence or product tests.

Understandability review: **pass, static AI assessment**. The successful flow is
`wait_trust` → `guarded_trust_dump` → registered reader → CLI →
`trust_matches`. The supervisor owns the reader lifetime; the caller owns the
deadline and transcript. On error, the existing guest/controller failure path
preserves evidence and stops the matrix. A new run starts with a fresh run ID
and rollback. The embedded helper exists to put native mutex waits and the CLI
under one killable process group; it is probe infrastructure, not product code.

Operator review: **pass, static AI assessment** for this correction's scope.
The runbook command, credentials, account switches and stop/recovery procedure
are unchanged. Missing LMDB or a reader error produces a failed probe and
requires investigation before a new authorized run. No unassisted human trial
has been performed. The product owner explicitly authorized fixing the error
and starting a fresh full matrix directly; this change has no separate
independent review before that run. The new lab report must distinguish local
checks from actual OL9 verification.

Checks executed before the new lab run:

- `python3 -B -m unittest discover -s acceptance -p 'test_*.py'`: 331 passed.
- `python3 -B -m unittest acceptance.test_rpm_wp0 acceptance.test_rpm_wp0_reader`:
  65 passed, including the real local LMDB fixture (no skip).
- WP0-scoped Ruff, Ruff formatting, Pyright and ShellCheck: passed.
- `git diff --check`: passed.

The product/unit suite was not rerun: only probe infrastructure changed.
The [third lab run](RPM-WP0-LAB-20261025-RUN03.md) failed in A/P1 because
OL9 could not resolve `liblmdb.so.0`. The correction is therefore not verified
on the required baseline; the original R4 failure was not reached.

## OL9 library-name correction after run 03

The owner's next instruction authorized correction and another matrix run.
Two bounded read-only SSH diagnostics on retained PROD found the installed
SONAME `liblmdb.so.0.0.0`, then successfully loaded it and resolved all five
required reader API symbols. The [public observation](rpm_wp0/results/lmdb-library-20261025.json)
contains only the library name and symbol-check result. Neither diagnostic
opened the trust database or changed the VM policy/package state.

The supervisor now uses `ctypes.util.find_library("lmdb")`, requiring a nonempty
result before `CDLL`. It never falls back to `CDLL(None)`. A regression executes
the actual helper source with a mocked resolver to verify the OL9 SONAME is
passed unchanged and a missing library stops before loading anything. The real
local concurrent-writer fixture still tests the complete reader lifetime.

Before run 04, all 332 acceptance-harness tests passed, including 66 WP0 tests.
WP0 Ruff, formatting, Pyright, ShellCheck and diff checks passed. Product/unit
tests were not rerun. Static understandability review: pass; library discovery
is explicit before reader acquisition, with the existing error/evidence path.
Static operator review: pass for this bounded correction; commands and recovery
are unchanged. Human usability remains untested. These diagnostics verify
library loading on OL9, not the full trust-poll mechanism or a WP0 PASS.

[Run 04](RPM-WP0-LAB-20261025-RUN04.md) verified the corrected library loading
on OL9 and completed 198 guarded dumps without CLI errors. A/P1 nevertheless
failed because product trust remained `src_unknown` until the 30-second
boundary. No subsequent cases ran; WP0 remains incomplete.
