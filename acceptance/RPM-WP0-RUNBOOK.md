# WP0 runner: local implementation, not lab verification

This runner implements the investigation matrix in plan revision 3.2.
The [second authorized run](RPM-WP0-LAB-20261025-RUN02.md) at `9b2cfb3` passed
13 case/profile runs, then stopped in R4/P1 on a trust-dump assertion.
WP0 remains incomplete; no later cases were run after that failure.
The implementation-stage review and a later explicit product-owner authorization
were followed by an [authorized lab run](RPM-WP0-LAB-20261025.md) at `0060a24`.
It stopped in A/P1; WP0 remains incomplete. A separate code review and explicit
product-owner authorization remain required before another `--execute` run.
The [follow-up diagnosis and runner fixes](RPM-WP0-FIXES-20261025.md) do not
replace that stopped run's verdict.
The [previous attempt](RPM-WP0.md) is historical evidence, not a result for
this implementation. No WP1/product implementation is delivered here.

## Prerequisites and commands

Machine: controller laptop. User: repository contributor with the existing
lab SSH/API access. Working directory: `~/koding/podman_offline`, branch
`feature/69-wp0`, with a clean committed checkout. Require Git, Python 3.11+,
SSH/scp/ssh-keygen, GnuPG, OpenSSL,
rootless Podman and the existing OL9 build image. The laptop build container
needs network for RPM build tools. PROD remains offline during probes.

The private configuration stays at
`~/.config/podman-offline-acceptance/lab.env`, mode 0600; never print it.
The lab signing home stays at `~/.podman-offline-rpm-gnupg`. The builder copies
its regular key material into a private temporary directory; it never mounts
or runs GnuPG against the original. Temporary signing/subkey/foreign-key
fixtures, SSH keys and test certificates are outside Git and removed on exit.
The controller checks the original regular key files byte-for-byte afterwards.

Input bundles default to
`~/podman-offline-acceptance-runs/host65-20261024-144821-app1/`:
platform 0.4.12, identity 0.4.12, platform 0.4.13. Override with `--bundles DIR`.
Certificates are generated there only in a separate temporary tree using
the existing `dev/generate-certificates.sh`; no real credentials are required.

Safe local inventory (no configuration read, API or SSH):

```sh
python3 -B acceptance/rpm_wp0/run.py --list
```

After the separate review and authorization, one command runs the entire
24-run matrix (use a new run ID every time):

```sh
python3 -B acceptance/rpm_wp0/run.py --run wp0-matrix-01 --execute
```

No measured duration is available: this implementation has not run in the lab.
The matrix performs 24 serial rollbacks/boots and includes the real deployment
in A; machine waits and RPM fixture building will dominate. Infrastructure
timeouts are failure bounds, not an estimate of completion time.

One command per case group, optionally restricted to a supported profile:

```sh
python3 -B acceptance/rpm_wp0/run.py --run wp0-c1-p2-01 --case C1 --profile P2 --execute
```

Groups: `A`, `B`, `C1`, `C2`, `R1`, `R2`, `R3`, `R4`, `R5`, `D`, `E`, `F`,
`G`, `H`. `R1`–`R5` are C3's individually isolated repair states. C1, C2 and
each repair state support P1 and P2. A/E/F support both, B only P2, D/G/H only
P1. Omitting `--profile` runs every supported profile for that group.
Unsupported combinations stop locally. `--config PATH` selects a private
configuration file; it never authorizes another VM role.

## Allowed operations and isolation

`ProdAPI` permits only configured PROD VM reads (`config`, `status/current`,
snapshot list and configurations of snapshots actually returned by that list),
the four authorized POST operations (`status/stop`, `status/shutdown`,
`status/start`, `snapshot/clean-agent/rollback`), and status reads for tasks
returned by those POSTs with that PROD VMID. Cluster-wide reads, other VMs,
unknown tasks and all snapshot creation/deletion/update operations are refused.
No DEV access or Proxmox configuration changes are implemented.

Before the first mutation and again before every reset, preflight requires
an explicit non-HA state from PROD status, `clean-agent` present, coverage of
all current writable disks in its snapshot configuration, no newer snapshot
of any current volume, no child of `clean-agent`, and the current parent
`clean-agent`. Missing metadata or an excluded/unknown disk stops the run.
This check uses Proxmox-managed snapshot metadata; storage snapshots created
outside Proxmox are outside its visibility and must not exist in the declared
lab baseline. Older managed snapshots are never changed.

If preflight rejects managed snapshot metadata, stop and give the product owner
the sanitized stop reason; do not delete snapshots or change the baseline.
An unmanaged storage snapshot cannot be detected by this preflight. If it causes
rollback to fail, PROD may already be stopped. Preserve the evidence and ask
the product owner/storage administrator to investigate outside this runner;
only after resolution, review and authorization use a fresh run ID.

Each case/profile is an independent run, in this order:

1. Preflight, stop PROD if needed, rollback `clean-agent`, start, wait for SSH.
   `prod_ready` is cleared before stopping; a failed rollback cannot trigger
   an audit against an assumed running VM.
2. Check OL9.8, SELinux Enforcing, active fapolicyd/firewalld, exact P1 rules,
   configuration, languages, filter and plugin against committed policy
   evidence. Refuse product/probe RPMs, keys, accounts, roots and WP0 artifacts.
3. Keep P1 unchanged or derive P2 in the running VM: validate all rule sources
   before writes, remove exactly original rules 1/2/12 by text, change only
   `trust` and `integrity`, compile/restart, capture and check the whole profile.
4. Run the existing harness network isolation and all three network checks.
5. Check both product public-key fixtures against the independent constant,
   then transfer inputs. No fingerprint/expected-value file is accepted in
   the input directory. The expected fingerprint travels in the SSH program.
6. Provision the ordinary runtime account and a lab-only public SSH key, start
   an audit window, run the case and check every named predicate.
7. Collect FANOTIFY/AVC records from that window. No case intentionally needs
   policy denials: guard/signature/lock refusals are expected CLI errors,
   recorded separately. Any FANOTIFY/AVC event fails. Missing audit is failure,
   never evidence of no events.

A, B and E never share a run with negative case groups. A uses a fresh real
runtime SSH session and the current manual's config/credential/install blocks;
it requires complete status, HTTPS checks and three healthy application
containers, excluding infrastructure containers. A's trust inventory checks
every installed `deployment/` and host-tools file against RPM size/SHA256 and
rejects any `file` trust record in the release trees. Non-code documentation
excluded by the OS RPM filter is not claimed as executable trust.
B executes the real packaged host preparation and root Python stdin.
E polls before the first `wp0-selfcheck`, then executes it over runtime SSH.
The final A health program selects the installed product layout and validates
the user manager before querying Podman. It records public container names,
flags and states before its predicate, including on a health/count failure.

## Signature, repair and mechanism cases

`contracts.APPROVED_FINGERPRINT` is pinned independently from the public lab
fingerprint recorded in `RPM-PROTOTYPE.md`. Compare it with the approved paper
value during the separate review. Exactly one primary and that fingerprint
are required before every authorizing import, including the subkey fixture.
Foreign-key imports are explicitly labeled negative setup, checked for one
primary, and never enter an authorizing product database.

C1 checks all seven signature variants with the actual paper OS commands on
fresh private copies/databases. `paper_delivery` constructs one disposable
medium directory per case containing only its public key and assigned tools
candidate. Old/new repair setup RPMs remain outside that directory. Signature
variants are renamed to the paper's `myproduct-tools-*.rpm` basename without
changing bytes; the source, target, SHA256 and temporary GnuPG environment are
recorded as fixture setup. `paper_verify` executes `rm`, `mkdir`, `cd`, `cp`,
ordinary `gpg --show-keys` and the wildcard `rpmkeys -K` command. Scripted reading
counts the ordinary `pub` lines, compares the following full fingerprint with
the independent constant, then requires exactly one signature result line.
No colon-format output replaces the paper's displayed key check. D continues
to test the installed tools' safe-open implementation of the same predicates.

C2 runs the actual bootstrap against two-primary and wrong-primary keys and
asserts the stop diagnostic, absent isolated database, unchanged global keys
and absent tools. Its leftovers case first establishes the foreign artifacts,
then checks their removal, the product-only database and delivered installation.
Two-primary `rpmkeys --import` behavior is recorded in a separate disposable
observation database; its outcome is never a pass criterion or authorization.

C3 performs the specified deterministic fault injection and diagnostic:
R1 deletes wrapper/module, R2 removes only rpmdb registration, R3 registers
old and delivered versions together, R4 installs clean older tools, and R5
installs newer tools. Repair selection comes from the observed rpmdb versions.
R3 uses exactly the plan's `dnf ... remove --duplicates`, without a package
argument, rechecks versions, then takes the same-version
reinstall branch. R1–R4 require exact version, clean RPM verification, trust,
root wrapper execution, and clean audit. R3 also retains an installed sibling
release. R5 takes the newer-version stop without installation and checks that
package identity and files remain unchanged. First install is not repair
coverage; R4 is explicitly ordinary upgrade coverage.
Every repair runs the paper copy/key/isolated-verification lines before deciding
or changing the installed package set. R1–R4 then use `rpm --import` and the
paper wildcard `dnf` install/reinstall line. R5 stops before those lines.

D installs signed, rpmdb-trusted miniature tools, runs the same seven candidate
checks using their code, then downloads a valid product candidate from a local
file repository using `dnf download` and applies the same isolated gate.
The local repository needs no enabled host or external repository.

F/G/H use signed **probe implementations**, not future product code:
`myproduct-tools`, `wp0-release-base`, `wp0-release-sibling`, `wp0-admin` and
`mechanisms.py`. Their files/state are confined to `/usr/libexec/wp0`, the
`wp0-*` wrappers (including the ordinary-account `wp0-runtime` entry point),
`/var/lib/wp0-probe` and `/run/wp0-probe`.
The F/G check child models the uninitialized retirement-state row only; the
later product eligibility planner is not implemented by these fixtures.
Release fixtures declare both `Requires: myproduct-tools` and
`Requires(preun): myproduct-tools`, including the scriptlet-ordering dependency.

F checks plain release/tools erase refusals and intact siblings, exact package
authorization, wrong package/boot/dead/reused PID records, non-ancestor refusal,
and unchanged guard behavior with the user manager stopped. G tests SCM_RIGHTS
handover, bounded concurrent lock refusal, inherited/forged descriptors,
check-child exit, and admin SIGKILL after preun approval while dnf retains the
descriptor. Explicit barriers make fault injection deterministic. Cleanup
unblocks an already started transaction and terminates the probe admin if
needed; it never starts a repair transaction. A killed admin can leave stale
authorization/identity records, which the next rollback discards.
H verifies a positive execution control, then detects mismatching/missing
root-owned identities in both entry points before `init-layout`. The upgrade
scriptlet records that new content was present when old `%preun` ran.

Audit production and parsing both use `LC_ALL=C`: the controller captures
`date '+%x %X'`, matching ausearch's locale date format (two-digit year).
The guest rejects malformed or four-digit-year input before invoking ausearch.
Audit explicitly uses `--input-logs` with stdin disconnected. It keeps the
default output format so no matches must include the `<no matches>` diagnostic;
raw mode suppresses that diagnostic and is not used. Empty status 1 is still
failure, never proof of a clean window.

`TRUST_TIMEOUT = 30` and `LOCK_TIMEOUT = 5` are controller constants approved
by the product owner. Local fake-clock tests cover timeout and late success.
Other SSH/transaction timeouts bound infrastructure hangs, not these criteria.
Before each installing DNF command, trust observation waits up to 30 seconds
for journal-observed idle state and only then captures a cursor. After DNF, a
separate 30-second trust budget requires a new enclosing refresh start followed
by completion after that cursor before dumping. A lone completion is rejected. The daemon must stay
active with the same PID; the refresh must remain unchanged across the dump.
All post-install observations share that post-install budget. No LMDB reader is registered by
the runner. See the [refresh correction](RPM-WP0-TRUST-REFRESH.md).
Automation adaptations are recorded separately: `dnf -y`, SCP input instead
of mounted media, scripted reading of paper output, and journal/daemon
observations surrounding DNF (the paper command lines remain unchanged). No paper usability,
console/media handling or human trial is established by automation.

## Evidence, stop and local verification

Evidence is private, outside Git:
`~/podman-offline-acceptance-runs/<run-id>/` (0700):

- `metadata.json`: source revision, selected matrix, constants, adaptations,
  current case, stop reason, original signing-home comparison.
- `record.jsonl`: ordered step verdicts. A step must return explicit `True`;
  missing/false predicates fail. Guest completion requires every named predicate.
- `command-NNNN.json`: sanitized controller argv, exit and separate streams.
- `<case>-baseline.json`, `<case>-policy.json`: full observed starting/profile
  evidence; action JSON files also retain guest commands and probe predicates.
- `<case>-audit.json`: bounded-window audit output and parsed event lines.
- `REPORT.md`: overall result and steps; unreached cases remain NOT TESTED.

An overall pass additionally requires every selected case's seven steps, the
four controller setup steps, unique step names, and a successful original-key
inventory comparison. The full selection reports `WP0 MATRIX PASS`; a smaller
selection reports only `SELECTED CASES PASS`.

The first failure stops later steps/cases. Only bounded read-only failure audit
and local evidence finalization follow; there is no retry, automatic repair,
reset-on-error or PASS for partial completion. Metadata, records and report
are written after every step, including initialization/transport failures.
An unavailable failure audit cannot overwrite the original failure.
The VM and its last state remain for inspection; do not assume P1 after a P2
case or a clean baseline after a stop. Controller temporary secrets are removed;
delivered runtime credentials remain only on disposable PROD until rollback.

Local checks (none contact the lab):

```sh
python3 -B -m unittest discover -s acceptance -p 'test_*.py'
.venv-tools/bin/ruff check acceptance/rpm_wp0 acceptance/test_rpm_wp0.py
.venv-tools/bin/ruff format --check acceptance/rpm_wp0 acceptance/test_rpm_wp0.py
.venv-tools/bin/pyright acceptance/rpm_wp0 acceptance/test_rpm_wp0.py
.venv-tools/bin/shellcheck acceptance/rpm_wp0/*.sh
git diff --check
```

These are acceptance-harness tests, not product/unit or real OL9/Podman/systemd
verification. The legacy `strict.sh`, `policy.sh` and `audit.sh` are retained
solely for historical report links; the new controller never invokes them.
AI procedure review is static only; an unassisted human trial was not performed.

## Implementation map and local review

| Plan boundary | Implementation |
| --- | --- |
| PROD operations and preflight | `run.ProdAPI.request/preflight`, `contracts.snapshot_preflight` |
| Isolated sequence and stop | `run.main`, `Investigation.reset/baseline/profile/isolate/transfer` |
| Exact policies and live P2 | `contracts.check_profile/derive_p2_sources`, `guest.apply_p2` |
| A: real SSH runtime and health | `Investigation.prototype`, `contracts.runtime_health` |
| B/E: Python and immediate execution | `guest.main`, `Investigation.probe`, `operations.wait_trust` |
| C1/D: signatures and downloaded candidate | `guest.signature_matrix`, `operations.paper_verify`, `operations.import_product/verify` |
| C2: pre-import stop and separate observation | `guest.stop_rules`, `contracts.authorize_paper_key`, `operations.bootstrap` |
| C3: injected states and repair | `guest.repair`, `contracts.repair_decision` |
| F: erase guard | `guest.guards`, `mechanisms.guard_record/guard/erase` |
| G: bounded lock and descriptor handover | `guest.locks`, `mechanisms.acquire/inherited/locked_check` |
| H: identity before execution | `guest.identities`, `mechanisms.record_identity/verify_identity/main` |
| Predicates, audit and failure evidence | `run.check_probe`, `Evidence.step/save`, `guest.audit` |

Developer understandability review: completed by static inspection of the diff
and affected flow, separately from tests. `contracts.py` owns expected values
and pure decisions; `operations.py` owns checked commands; `guest.py` assembles
case predicates; `mechanisms.py` is explicitly disposable probe code. The
controller owns ordering and persistent evidence. The fixture builder is tied
to the named historical bundles because these are the assigned WP0 inputs.

Success trace: `main` preflights before mutation, then resets, validates the
baseline, applies the profile, isolates and transfers. A installs verified
private copies, polls RPM trust, prepares the host, uses real runtime SSH, and
checks health before its independent audit. Completion is recorded only after
all selected predicates, audits and the signing-home comparison succeed.

Failure trace: C2 passes the bad key through the actual bootstrap. Authorization
stops before database creation/import; the probe checks the diagnostic and
unchanged global/package state. An unexpected result raises, preserves the
failed step, gathers a bounded audit if possible and stops subsequent cases.
There is no resume of partial VM state: a separately authorized fresh run ID
starts with rollback. Root owns key databases, identities and authorization;
the ordinary account owns runtime state and the operation lock.

AI procedure walkthrough: static, with no commands against the lab. The runbook
identifies the laptop/user, prerequisites and one matrix command or one selected
case command; no manual edits or account switches are needed after configuration.
Success is visible in `REPORT.md`; after interruption the operator retains the
evidence and VM state, requests review of the stop reason, and does not retry
blindly. The first execution blocker is intentional: separate code review and
product-owner authorization are still required. This is an investigator's
procedure, not a paper installation or human-usability result.

Local verification of this implementation: **327 acceptance-harness tests
passed**, including 61 focused WP0 tests. Ruff, Ruff formatting, Pyright,
ShellCheck and `git diff --check` passed. The tests use disposable local files,
real local locks/sockets, actual shell copying/glob expansion and local glibc
date parsing, with mocked host/API/RPM/GnuPG/DNF boundaries. Regression cases
cover a contaminated three-package medium, pre-import key stops, and B's
account-created descendants rather than root-created parent directories.
These checks do not establish OL9 ausearch, RPM or DNF behavior. Product tests were not
rerun because product code is unchanged. These statements describe the local
implementation phase. The subsequent authorized run built the RPMs and reached
A/P1 on PROD before stopping; see the linked lab report for actual runtime scope.
No WP0 go/no-go approval is claimed.
