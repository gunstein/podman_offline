# WP0 trust refresh observation correction

After run 04, the owner authorized correction and relevant acceptance tests.
Read-only PROD journal/status diagnostics established that fapolicyd had exited
with status 1 during its RPM-triggered refresh:

```text
Updating trust database
Cannot delete database (1)
Cannot update trust database!
fapolicyd.service: Main process exited, code=exited, status=1/FAILURE
```

The [bounded journal evidence](rpm_wp0/results/trust-daemon-20261025.json)
contains no credentials. The observed package versions were fapolicyd
1.4.5-1.1.el9_8 and lmdb-libs 0.9.29-3.el9. `systemctl is-active fapolicyd`
returned 3, `failed`. This updates the last-known service state left by run 04;
no service restart, policy change or further installation was used to diagnose it.

## Correction and limits

The registered LMDB reader introduced after run 02 is removed. It writes reader
bookkeeping in the live lock file and was not demonstrated safe with fapolicyd
and fanotify. Local tests with a concurrent writer did not model that interaction.
A further local check with a persistent WRITEMAP writer, four reader slots,
3,000 transactions and 50 guard reads also succeeded; it did not reproduce the
actual daemon failure. The precise native failure is therefore **not proven**.
This correction avoids opening the live LMDB lock file altogether rather than
retaining that unverified interaction.

`operations.capture_trust_cursor` observes the active daemon PID and a journal
cursor before each DNF install/reinstall, including `paper_install`. The paper
commands themselves are unchanged; the surrounding observations are a declared
automation adaptation in controller metadata and the runbook.

`wait_trust` uses the same 30-second budget for all following observations:

1. Require the original daemon PID to remain active.
2. Look only after the pre-transaction cursor. Wait until the last refresh
   message is `Updated`, not the start of another refresh.
3. Execute the original `fapolicyd-cli --dump-db`, without a native wrapper.
4. Require the same completed refresh cursor and the same active daemon PID
   after the dump; an overlapping refresh never yields PASS.
5. Apply the unchanged exact path/size/SHA256/`rpmdb` predicate. Unknown sources
   and file-trust duplicates are still refused.

The baseline [daemon source](https://github.com/linux-application-whitelisting/fapolicyd/blob/v1.4.5/src/library/database.c)
emits `Updated` only after the refresh succeeds. The
[CLI source](https://github.com/linux-application-whitelisting/fapolicyd/blob/v1.4.5/src/cli/fapolicyd-cli.c)
uses an unregistered reader. Waiting for completion avoids intentionally racing
that reader against the runner's installation refresh. The isolated cases have
no other authorized package writer. A concurrent unexpected refresh can still
make the CLI fail; errors stop, are never retried as successful output, and do
not relax the acceptance criteria. Missing/malformed journal observations,
service death/restart and timeout also stop. No explicit refresh, database edit,
policy change, daemon restart or extra sleep is introduced.

## Local evidence and understandability

The obsolete native-reader tests are replaced by
`test_rpm_wp0_trust.py`: both DNF entry points capture first; missing cursor or
failed daemon stops; only a completed current refresh opens the dump gate;
stale/in-progress/overlapping refreshes cannot pass; daemon death/restart,
unknown trust source, CLI failure and deadline expiry cannot pass. The existing
real-shell paper bootstrap fixture now supplies journal and systemctl stubs
while still asserting exact paper arguments and refusal before installation.
These stubs are harness evidence, not actual fapolicyd behavior.

Before lab: 334 acceptance-harness tests passed (68 WP0 tests). WP0 Ruff,
formatting, Pyright, ShellCheck and diff checks passed. Product/unit tests were
not rerun because product code is unchanged.

Developer understandability review: **pass, static AI assessment**. The cursor
and PID belong to the guest action, are captured before the transaction, and
are never persisted as an authorization token. `completed_refresh` decides
journal readiness; `wait_trust` controls ordering and the deadline; the existing
predicate decides trust. Success goes through the normal case/audit gates;
failure goes through preserved evidence and the stop rule. Retry means a new
run ID and rollback, not resuming a stale cursor. Removing ctypes and native
transaction management simplifies the affected flow.

Operator review: **pass, static AI assessment** for the changed scope. Existing
one-command case selection and stop/recovery instructions remain applicable.
The runbook declares the additional observations. No human usability trial or
independent review occurred. Relevant real cases are E/P1+P2 first, then A/P1+P2
and R4/P1+P2 only if preceding cases pass; each retains the runner's isolation
and first-failure stop rule. Their results must be recorded separately.

## Actual selected lab verification

[E, A and R4 on P1/P2](RPM-WP0-LAB-20261025-SELECTED05.md) all passed at
`47b14ca`, including clean per-case audits. These six selected results verify
the new observation flow on install and upgrade; they are not full WP0 PASS.
