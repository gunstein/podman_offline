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
Actual OL9 results are recorded separately in the subsequent lab report.
