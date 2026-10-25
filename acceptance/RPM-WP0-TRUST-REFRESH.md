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

`operations.capture_trust_cursor` now first waits for journal-observed idle
state from the active daemon in the current boot: the latest refresh state
must be `Updated`, or startup must have reached `Starting to listen for events`.
It examines the last 100 messages for that PID. An in-progress or unrecognized
state cannot publish a cursor or start DNF. PID is checked again after reading
the journal. This pre-transaction wait has its own 30-second bound using
`TRUST_TIMEOUT`; it does not consume or extend the separate post-install
30-second trust-poll budget. The published cursor is the last observed record,
including completion of any previous refresh. This applies before every DNF
install/reinstall, including `paper_install`. The paper
commands themselves are unchanged; the surrounding observations are a declared
automation adaptation in controller metadata and the runbook.

`wait_trust` uses the same 30-second budget for all following observations:

1. Require the original daemon PID to remain active.
2. Look only after the pre-transaction cursor, in the current boot and for
   that daemon PID. Require the refresh's `It looks like... Syncing DB.` start
   message before `Updated`. A lone completion or only the later backend
   `Updating trust database` line cannot establish a new refresh. A subsequent
   start invalidates the preceding completion.
3. Execute the original `fapolicyd-cli --dump-db`, without a native wrapper.
4. Require the same completed refresh cursor and the same active daemon PID
   after the dump; an overlapping refresh never yields PASS.
5. Apply the unchanged exact path/size/SHA256/`rpmdb` predicate. Unknown sources
   and file-trust duplicates are still refused.

The baseline [daemon source](https://github.com/linux-application-whitelisting/fapolicyd/blob/v1.4.5/src/library/database.c)
emits `Updated` only after the refresh succeeds. The
[CLI source](https://github.com/linux-application-whitelisting/fapolicyd/blob/v1.4.5/src/cli/fapolicyd-cli.c)
uses an unregistered reader. The earlier implementation could mistake the tail of a previous refresh for
a new completed refresh. The current gate excludes that observed ordering.
Journal observations are not a database lock or a transaction identifier. The isolated cases have
no other authorized package writer. A concurrent unexpected refresh can still
make the CLI fail; errors stop, are never retried as successful output, and do
not relax the acceptance criteria. Missing/malformed journal observations,
service death/restart and timeout also stop. No explicit refresh, database edit,
policy change, daemon restart or extra sleep is introduced.

## Local evidence and understandability

The obsolete native-reader tests are replaced by
`test_rpm_wp0_trust.py`: both DNF entry points capture first; missing cursor or
failed daemon stops; only a completed current refresh opens the dump gate;
a lone old completion, an observed in-progress refresh and an observed
overlap cannot open the gate; daemon death/restart,
unknown trust source, CLI failure and deadline expiry cannot pass. The existing
real-shell paper bootstrap fixture now supplies journal and systemctl stubs
while still asserting exact paper arguments and refusal before installation.
These stubs are harness evidence, not actual fapolicyd behavior.

Before the historical selected lab run at `47b14ca`: 334 acceptance-harness
tests passed (68 WP0 tests). WP0 Ruff,
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
`47b14ca`, including clean per-case audits. Those six selected outcomes are historical. Independent review subsequently
identified that the old gate could accept an old refresh completion; both R4
cursors were taken during an existing refresh. They do not verify the corrected
gate or establish full WP0 PASS.

## Independent-review correction (local only)

The review of `b0baf2a..de2ea44` identified that an `Updated` after the cursor
could finish a refresh that started before it. The old code neither waited
for observed idle state nor required the enclosing refresh start after the
cursor. The present changes implement both checks. Tests include a cursor
attempt during an old refresh, a lone `Updated`, the old refresh's backend
start followed by completion, a complete new cycle, pre-transaction timeout
without DNF/cursor publication, and PID change before cursor publication.

`command` now catches `TimeoutExpired` only to record `timed_out`, the limit,
arguments and partial stdout/stderr, then rethrows the same exception. Missing
output becomes an empty string; byte output is decoded with replacement for
invalid UTF-8. No exit code is invented (`exit` is null). Tests exercise both
journal and CLI arguments with bytes, text and missing partial output.

The pre-transaction state and subsequent start/completion are observations,
not a causal transaction token from fapolicyd. An unrelated writer or queued
unobserved request remains outside the isolated-case assumption; this change
must not be described as eliminating every possible native read/write race.
Missing or truncated readiness history stops rather than assuming idle state.
No changes were made to policy, trust predicates, snapshots or product code.

Static understandability review: **pass with stated limitations**. DNF's
observation dependency remains explicit in its wrapper and `paper_install`;
failed capture clears the globals, and only a completed bounded wait publishes
them. The poll retains the before/after PID and refresh checks. Timeout evidence
is appended before the normal guest/controller failure path receives the same
exception. The procedure still uses one command per selected case group.

No VM/Proxmox contact, RPM build or new lab run was performed for this correction.
Separate review and new authorized lab evidence are outstanding. R1/R3 should
be included because same-byte reinstall exposed the missing association;
R4 and E/A need current-revision verification too. Human usability is untested.

The plan still enumerates only the three original automation adaptations;
journal/daemon observations are declared in the runner metadata and runbook.
The task explicitly forbids editing `docs/`, so this plan discrepancy is left
for the product owner/plan author, not silently rewritten here.

Local checks after the independent-review correction: 338 acceptance-harness
tests passed (72 WP0 tests). WP0 Ruff, formatting, Pyright, ShellCheck and
`git diff --check` passed. Relative links and the public historical JSON
projection were checked. Product/unit tests and real OL9/Podman/systemd tests
were not rerun. The selected-05 results remain historical at `47b14ca`.
