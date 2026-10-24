# Host setup and operator procedure (backlog 65)

Implemented on `feature/65-host-setup`, based on `f52b797` (2026-10-24).
**All nine scenarios passed on `2d36d71`; unassisted human verification
remains outstanding under backlog item 68.** The first failed attempt is retained below.
Historical item 39/54/64 lab results do not verify this change.

## Successful real OL9 verification (2026-10-24)

The operator supplied `akseptanselogger-20261024-165715.tar.gz`, SHA256
`3a5eb6f0a667f5449f55b75e4215aac106757a0730f3c2eb08affdd68e9971b5`.
All runs in `host65-20261024-144821-*` record clean source revision
`2d36d718e50b1163a9b7eda2393392f681078625`. All 582 step records passed with
exit 0; all 582 log hashes matched the recorded evidence.

| Scenario suffix | Steps | Result |
| --- | ---: | --- |
| normal | 36 | CLEAN PASS |
| renamed | 37 | CLEAN PASS |
| minimal | 32 | CLEAN PASS |
| platform-help | 39 | CLEAN PASS |
| app1 | 126 | CLEAN PASS |
| app2 | 126 | CLEAN PASS |
| help | 61 | CLEAN PASS |
| identity | 67 | CLEAN PASS |
| renamed-regression | 58 | CLEAN PASS |

The first three scenarios exercise the literal manual setup path: documented
cache diagnosis/remedy, authenticated publication, initial/repeated/interrupted
setup and retry, retained release hashes, bootstrap, actual runtime SSH without
sudo or XDG injection, installation, endpoint checks, status and readable journal.
The other six exercise the existing regression matrix. Five status-retry probes
verify an active old service remains pending/incomplete after failed reinstall,
then observe the changed public value inside the container after retry and
restore the original configuration without modifying protected release code.

All nine final audits report no FANOTIFY/AVC events since run start. The renamed
regression recorded nine early subject-cache evictions, without a denial or
failed step; retain this as a cache-monitoring observation, not a diagnosed
regression. Other runs recorded zero early subject-cache evictions.

These are real Podman/systemd/SELinux/fapolicyd results for `2d36d71`. Subsequent
English translations were checked locally and were not rerun on the VMs. They
preserve command flow apart from placeholder/diagnostic text. Python 3.6 execution,
unassisted human usability (item 68) and the complete SSH lifecycle in item 67
remain separate gaps. No agent-initiated VM reset or lab run was performed.

## First real lab attempt and sudo regression (2026-10-24)

Run `host65-20261024-141431-normal` at clean revision `8559a2a` ended
**NOT CLEAN** at `06-manual-setup-first`. Delivery and the manual tool bootstrap
passed; later setup, runtime SSH and install steps were not tested. Final audit
and cleanup passed. Source evidence is `akseptanselogger-20261024-142333.tar.gz`,
SHA256 `5cb35020815a466602217f9f947482acdefcc7a675ea44cd5ad1f3705af31b57`.

Preflight reported the expected fapolicyd cache prerequisite and an unexpected
sudo-policy rejection. A read-only follow-up on the same OL9.8 host, using the
helper's clean PATH/LC_ALL environment, confirmed `sudo -n -l -U myproduct-ops`
returned **0**, stdout `User myproduct-ops is not allowed to run sudo on
todo-standby.`, and empty stderr. The implementation incorrectly required exit 1
even for that explicit denial. SSH/PIP warnings were not the stopping cause.

The fix retains the bounded command exit codes (0/1) and requires the complete
denial for the selected account; a zero exit alone, grants, wrong account,
additional output and policy errors remain insufficient. The new regression
failed against the original code for both stdout/stderr placement. The real
signed-publication/fresh-process retry fixture now also uses the observed zero
exit. No harness bypass or permission change is introduced. The existing harness
still only applies the documented cache remedy when it is the sole failure.

Understanding/operator recheck: the same preflight remains before product writes
and repeats under the lock; successful denial continues through existing setup,
while ambiguous results stop with the existing administrator diagnosis and same
retry command. The manual requires no change. No VM reset or lab rerun was
performed for this fix; only the read-only policy query was executed remotely.

Follow-up local verification: 19 focused host-setup tests, 481 isolated platform
tests and 264 acceptance-harness tests passed. Changed Python files passed Ruff
lint/format and Vermin (minimum Python 3.6); the full documented Pyright check
reported zero errors. `git diff --check` passed. The 66 demo tests passed in the
operator's preceding run at `8559a2a`; they were not rerun for this account-check
fix. These local results do not establish real setup/install completion.

## Contract and implementation

### Review follow-up: manual failure, bootstrap interruption and host diagnostics

Review of the two commits through `15f6e4b` found three gaps despite green local
tests. Gateway config could continue editing after failed init-config;
init-layout could leave an empty final bootstrap after SIGKILL; setup discarded
actionable host-script errors. The earlier AI assessment of complete execution
instructions was too strong and is superseded by the findings in
[OPERATOR-REVIEW.md](OPERATOR-REVIEW.md).

The manual now owns fail-stop behavior in its multi-command config, transfer and
status blocks. The focused harness supplies worksheet assignments and ordinary
`bash -s`, without adding `set -eu` or `bash -e`. A literal-block regression
injects init-config exit 23, then checks the original config and absence of later
directory creation. It failed against the old block (exit 0). Separate first-scp
failure checks ensure later transfers are not attempted.

`layout.initialize` writes a private exclusive temporary file through the held
directory, flushes/fsyncs it, and uses Linux `renameat2(RENAME_NOREPLACE)` before
syncing the directories. The single rename avoids both truncation and the
two-hard-link interruption window that would violate bootstrap-reader checks.
A concurrent final file is validated and retained; no replacing rename fallback
is used. Each attempt cleans only its own temporary file on ordinary failure.
SIGKILL may leave a private temporary file, which is not authoritative and does
not block retry. The regression kills a separate process just after creation,
after fsync and after publication, then retries in a fresh process. Before the
fix it reproduced the empty final file. Another test races publication against
a concurrently created valid bootstrap and requires preservation.

The authenticated host script emits fixed phase names. The release command's
optional diagnostic callback is used only for this script; it maps recognized
errors such as overlapping/exhausted subordinate IDs and conflicting SELinux
equivalences to distinct fixed diagnoses and administrator actions. Unknown
output is not forwarded: a recognized phase gives a bounded action, exit code
and the same setup command from manual step 3. Tests cover distinct failures,
suppression of arbitrary/private/control-character output and real setup-flow
failure followed by fresh-process retry using retained authenticated releases.

Understanding review: preflight and signed publication still precede privileged
host execution. The bootstrap's sole authoritative name becomes visible only
after complete file content is durable; failure before it leaves retryable
temporary state, and failure after it leaves a complete private file. The host
script owns phase reporting and the release coordinator owns safe presentation;
no new pending protocol or silent host repair is introduced. Code review passes
for these focused changes. The subsequent real OL9 results above cover the
corrected flow; unassisted human usability remains outstanding (item 68).

Follow-up verification: 40 focused layout/setup tests and 18 host-script tests
passed. The final isolated platform suite passed 485 tests, the demo suite
passed 66 tests, and the acceptance-harness suite passed 266 tests. Changed Python lint and full
format checks passed (155 files); full documented Pyright reported zero errors,
and Vermin retained minimum Python 3.6. No real host commands or VM resets were
run for this review follow-up. All 20 manual Bash blocks passed syntax checking,
198 relative file links across the changed documents exist, the reviewed manual
digest matches, and `git diff --check` passed.

### Original implementation

`scripts/release.py setup` takes the product, an existing unprivileged login
account, HTTPS port, input directory, independently authenticated public-key
digest, explicit `--release COMPONENT@VERSION` selections, and one selected
`--host-release`. No directory discovery, dependency engine, automatic account
creation, package download, key rotation or runtime installation is added.

The separately authenticated gzip/stdin helper remains the sole release engine.
Its canonical initial bootstrap is the `tool-bootstrap` block in
[the production manual](../docs/PRODUCTION-INSTALL.md), executed in regression
coverage. It snapshots the candidate into an exclusive file under validated
root-protected ancestors, hashes that exact copy, retains the old helper on
mismatch, and fsyncs/atomically publishes only matching bytes. No unverified code
is imported. Bootstrap failures report a safe action and continuation.

`setup_request` validates selections without host access. `check_host_prerequisites`
checks the documented OL9/security/account baseline, effective sudo denial,
journald policy, selected inputs/key, conflicting product roots/drop-ins and
filesystem-grouped lower-bound space. It runs before `product_lock` can create
product directories and repeats relevant checks while holding the lock. Missing
PyYAML is handled before module import with a concrete package instruction.

`provision_key` is extracted from the existing command; both entry points share
its snapshot/digest/no-rotation behavior. `publish`/`enroll` remain the authority
for signature, archive inventory, immutable release and exact trust. Shared
`archive_members` validation also feeds the setup-only post-authentication space
check. Existing individual publication commands acquire no new reserve policy.

After all selected releases are ready, `published` and an explicit authenticated
script hash authorize the chosen host script. Compatible journal policy permits
safe directory creation, systemd tmpfiles and flush; explicit incompatible
Storage/SplitMode stops before product changes. No journal deletion, new groups
or automatic policy rewrite occurs. The existing protected `prepare-host.sh`
retains its numeric UID/GID/capability drop and descriptor-based descendant work.
The coordinator checks live linger, manager XDG values, directory ownership/modes,
firewall runtime/permanent state and persistent journal before final success.

`deploy.sh init-layout` is a small additional public command justified by the
operator review: the runtime account no longer writes a bootstrap by hand.
`service_identity` is shared with existing identity checks; `layout.initialize`
validates the prepared root, exclusively creates a private file, or validates
and preserves an existing matching file byte-for-byte. It refuses root/source,
links, conflicting roots and unsafe ownership/modes. Root setup never opens the
bootstrap, credentials, config or runtime pending record.

## Success and failure/retry understanding review

Success: independently authenticated manual/tool -> `setup_request` -> read-only
preflight -> product lock -> pinned key -> selected `publish`/`enroll` calls ->
authenticated host script -> guarded journal -> existing host preparation -> live
postconditions. The completion statement represents host preparation, not an
installed component. The next command is an absolute `deploy.sh init-layout`
path, executed after actual runtime SSH login. Normal lifecycle receipts are
still owned by `install_component_plan` and are unchanged.

Failure/retry: a second bad signature can leave the first release ready but
runs no host script. Trust failure retains authenticated publication; a new
process revalidates inventory and waits for exact trust. Journal mkdir followed
by a killed process leaves a directory that does not count as completion: retry
rechecks policy and flushes. A kill during signature verification can leave a
private staging directory; retry uses a new authenticated snapshot, does not
publish that residue and does not scavenge it. Host-manager activation is derived
from live state even when the existing drop-in already exists.

There is no new setup pending record, completion flag, class hierarchy or
transaction engine. Side effects are explicit named steps. The single-file root
helper is larger because it must run independently over isolated stdin; checks
are grouped by request, account, host policy, journal, space and postconditions.
The detailed existing host checks remain at their own mutation boundaries after
authentication; not every possible I/O or host failure can be discovered before
publication. This layering and the two authority boundaries were reviewed
separately from test success. Code-understandability review: passed. Subsequent
real-host verification is recorded above; human usability is still outstanding.

## Product/unit and harness evidence

The fixture is `cedar` with `worker@1.0.0`, `processor@2.3.4`, account
`operator-a`, no gateway roles, database, demo source or credentials. Real archives,
GPG signatures, immutable release records and filesystem state drive first/repeat
and fresh-process retry; host commands and account identity are simulated.

Coverage includes invalid second signature and successful retry, omitted host
script, duplicates/unsafe identities, grouped space, regular-file/link/FIFO
checks, effective journal ordering/conflicts, sudo grants versus denial/errors,
UID boundaries and privilege groups, caller environment isolation, all existing
release operations, interruption at signature/journal boundaries, retained
runtime pending bytes and no root bootstrap creation. Manual bootstrap tests
model a private root target/UID while executing its actual algorithm, including
bad hash, upload replacement, unsafe target, link/FIFO/hardlink/ACL refusal.
Layout tests verify no-clobber private creation, conflicts and missing setup.

The harness uses executable manual blocks with unique step IDs. Missing/duplicate
IDs, invalid Bash, wrong HTTP results, unexpected preflight failures, wrong
interruption, mode conflicts and scenario wiring have focused tests. Only a sole
recognized cache-size preflight failure permits the manual's explicit remedy;
it cannot hide unrelated failures. Ordinary first/repeat/retry use the unchanged
manual bootstrap/setup commands. The fault probe is separately authenticated
controller instrumentation in memory: it checks the installed helper digest and
kills that attempt just before journal tmpfiles, with no on-disk release/policy
changes or production failure switch. Retry must retain key/release records.

Original implementation results before the review follow-up (kept as historical
local evidence; current follow-up results are recorded above):

| Evidence | Result |
| --- | --- |
| Focused bootstrap/setup/layout product tests | 41 passed |
| `python3 -B tests/run.py platform --isolate` | 480 passed |
| `python3 -B tests/run.py demo` | 66 passed |
| `python3 -B -m unittest discover -s acceptance -p 'test_*.py'` | 264 passed (10 new focused harness tests) |
| Full documented Pyright | 0 errors |
| Vermin for the documented product/tests paths | Minimum Python 3.6; interpreter not exercised |
| Full Ruff format | Passed; 154 files checked |
| Manual heredoc Python snippets | Both parse; Vermin minimum Python 3.4 (within 3.6 baseline) |
| Bash/manual syntax | All manual shell blocks plus changed remote script passed |
| ShellCheck | Unavailable on PATH; Bash syntax checked instead |
| Ruff lint | Changed/new Python files pass; 12 pre-existing findings remain in the item 61 files |

No real Podman/systemd or human result is inferred from these tests. Fresh-process
setup fixtures and manual source snippets execute on the local Python interpreter;
they model root ownership and host commands and do not prove real root privilege
separation. Bash/manual syntax passed; 310 local links/anchors across 10 changed documents
passed, as did `git diff --check`. No raw logs or credentials are staged.

## Focused runnable real-lab checks

From a committed clean checkout with the usual [lab prerequisites](README.md):

```sh
python3 acceptance/acceptance.py --run host65-normal-UNIQUE --host-setup run
python3 acceptance/acceptance.py --run host65-renamed-UNIQUE --renamed-product --host-setup run
python3 acceptance/acceptance.py --run host65-minimal-UNIQUE --platform-help-only --host-setup run
```

These reset both disposable VMs; run sequentially only when the operator
instructs a lab run. They have **not** been executed for this implementation.
The minimal flag in this focused mode means gateway-only, with no Identity or
database; the ordinary matrix's platform/help behavior remains unchanged.
`--host-setup` refuses `--help-only`, `--identity-only` and `--status-retry`
before creating a run/resetting a VM.

Declared test infrastructure: existing OS baseline, disposable ordinary account,
lab-only SSH key, artifact transport and external credentials generated on DEV.
No source/demo credential provisioner executes on PROD. Product/journal state
must be absent at the fresh-host check. Preparation is not bypassed with private
harness mkdir/key/drop-in/prepare-host/bootstrap logic. Runtime init-layout,
config/credential steps, validate/install, endpoint checks and nonempty service
journal metadata (without MESSAGE contents) run through real SSH without sudo or XDG injection. Temporary controller
secrets and the disposable authorized key are cleaned up; installed credentials
are retained.

This focused path deliberately stops after initial installation/status/journal.
The complete logout/reboot-before-login, new-login, upgrade/hash retention and
retirement scenario remains backlog 67; multi-bundle runtime orchestration
remains 66. The full existing six-scenario matrix passed in the series above.
Its sudo-u runtime paths do not substitute for the full SSH lifecycle in 67.

## Operator assessment and remaining limits

The separate [operator assessment](OPERATOR-REVIEW.md) records the current AI
walkthrough and the historical findings. The new manual keeps required commands,
prerequisite remedies, PEM and optional externally supplied PFX, expected results
and continuation in one sequence. The bootstrap block remains substantial because
it establishes the root trust boundary; this is an identified usability burden,
not something automated tests can approve. Further simplification must retain
independent authentication; an organisation-reviewed package is an alternative
trusted provisioner, not a claim that new packaging was built here.

A person with limited Linux experience must still follow the manual on a fresh
host without oral help, with time, errors, stops, command/edit counts and questions
recorded. No qualifying trial has occurred. Customer readiness is not declared.
Real OL9 SELinux/fapolicyd/SSH/journal behavior, Python 3.6 interpreter execution,
non-default security policies, external PFX applications and site-specific NSS/sudo
providers remain outside the local verification. Ambiguous sudo inspection is
refused, not treated as proof of no grants.
