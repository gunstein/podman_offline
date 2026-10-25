# WP0 H working-directory correction

The full run `wp0-full-20261025-184031` at `f1ea688` passed 23 of 24
case/profile combinations, including F/P1, F/P2 and G/P1. H/P1 stopped in
its positive runtime control with `STOP: installed package damaged`.
No H predicate passed; the negative identity cases were not reached.
The failure audit contained no events. The run remains NOT CLEAN.

## Diagnosis and correction

The probe inherited the root SSH session's working directory when dropping
to the runtime account. `rpm -V` opens its current directory even when given
an explicit package name. Setting HOME does not change that directory.
The inner RPM diagnostic was not exported by the runtime wrapper, so the
historical transcript alone does not prove why its verification failed.

A local disposable OL9 container reproduced the relevant failure using its
installed `oraclelinux-release` package and numeric UID/GID 65534, with
supplementary groups and capabilities cleared, no new privileges, and a
cleared environment:

| Subprocess working directory | RPM exit | stdout | stderr |
| --- | --- | --- | --- |
| `/root` | 1 | empty | `error: Unable to open current directory: Permission denied` |
| `/` | 0 | empty | empty |

The container used the existing `docker.io/library/oraclelinux:9` image with
`--pull=never --network=none --rm`. No lab connection, signing material,
RPM build or package installation was needed. This is a local RPM reproduction,
not verification of the WP0 packages on the lab VM.

`guest.identities` now passes `cwd="/"` for the positive runtime control and
all four admin/runtime mismatch/missing-record checks. It does not change
account privileges, directory permissions, RPM verification, identity matching,
checksum checking or the requirement to stop before release code executes.

## Verification and review

- Full acceptance-harness suite: 340 tests passed.
- WP0-scoped Ruff, formatting, Pyright and ShellCheck: passed.
- `git diff --check`: passed.
- The new regression follows all five entry-point calls, executes a real
  local subprocess to check their working directory, and asserts the complete
  H predicate set. An injected positive-control failure stops before upgrades
  and before any predicate passes. RPM, privilege switching and package
  changes are stubbed in this regression.

Static developer understandability review: pass. The controller-side guest
probe chooses the subprocess directory explicitly; installed tools still own
identity verification and release execution. Success retains the existing
marker and identity predicates; failure propagates to the existing evidence
and stop handling. The shared privilege-drop helper and F/G are unchanged.

Operator commands are unchanged; no human usability test was performed.
Product/unit tests were not run because product code is unchanged. No real
OL9 VM, fapolicyd or systemd verification was run for this change. The lab VM
was left untouched. Separate review and an authorized lab run remain required;
the full final-revision matrix must pass before WP0 is complete.
