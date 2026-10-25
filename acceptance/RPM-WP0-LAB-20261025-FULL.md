# WP0 final full matrix: all 24 case/profile runs passed

**WP0 MATRIX PASS** at runner revision
`3222efb08643e4655e1f05b7d69f2a398888e816`, clean `feature/69-wp0` checkout.
This completes the WP0 investigation matrix of
[plan revision 3.3](../docs/RPM-DELIVERY-PLAN.md#work-package-0-investigation-decides-gono-go).
It is evidence for the investigation only: it is not a product
implementation, and it does not by itself authorize WP1. The go/no-go decision
belongs to the product owner.

## Command and evidence

Controller laptop, repository contributor. The run used the full-matrix
defaults (`complete_matrix_selected: true`, default bundle input); the exact
argv is not recorded in metadata, so this command is an inference from the
recorded run ID and selection:

```sh
python3 -B acceptance/rpm_wp0/run.py --run wp0-full-20261025-192009 --execute
```

Steps ran from `18:20:09Z` (`controller-source`) to `18:40:45Z` (H/P1 audit
start). The private run directory
`~/podman-offline-acceptance-runs/wp0-full-20261025-192009/` holds
`metadata.json`, `record.jsonl`, `REPORT.md`, 331 controller command records
and per-case baseline, policy, provision, probe and audit files. The
[public summary](rpm_wp0/results/authorized-20261025-full-summary.json)
contains all 172 step records, every case's predicates, ausearch start/exit/output
and the policy comparison. Trust dumps, transcripts and credentials stay private.

Metadata records the revision above, the complete 24-case selection,
`TRUST_TIMEOUT = 30`, `LOCK_TIMEOUT = 5`, the four declared automation
adaptations and `original_signing_home_unchanged: true`. The runner's
`controller-source` step requires a clean checkout of `feature/69-wp0`.

## Lab rules, snapshot and profiles

Only the configured PROD VM was operated on. Snapshot preflight passed once;
each of the 24 case/profile runs then rolled back to `clean-agent`, checked the
clean baseline, applied/validated its profile, isolated the network and
transferred inputs before the probe. No snapshot was created, changed or
deleted. All 24 baselines record Oracle Linux 9.8, SELinux Enforcing, active
fapolicyd and firewalld, and no product packages, imported product keys or
WP0 artifacts.

Each effective policy equals the previously published
[P1](rpm_wp0/results/authorized-20261025-selected05-policy-P1.json) or
[P2](rpm_wp0/results/authorized-20261025-selected05-policy-P2.json) record:

- P1: 14 baseline rules, `trust = rpmdb,file`, `integrity = none`,
  `permissive = 0`.
- P2: exactly original rules 1, 2 and 12 removed, remaining order kept;
  `trust = rpmdb`, `integrity = sha256`; no other configuration change.
  Created in the running VM after rollback, never snapshotted.

RPM filter, languages and `rpm-plugin-fapolicyd-4.16.1.3-40.el9` were equal
across profiles.

## Result matrix

Each run's seven steps (rollback, baseline, profile, isolation, transfer,
probe, audit) passed. The probe predicate set equalled the runner's expected
set exactly, with no duplicates.

| Case | Predicates established | P1 | P2 |
| --- | --- | --- | --- |
| A | prototype trust; real runtime SSH installation, healthy services and HTTPS checked by the controller | PASS | PASS |
| B | prototype trust, root stdin Python, account Python | not specified | PASS |
| C1 | product, product subkey accepted; unsigned, foreign, tampered header/payload, foreign subkey refused | PASS | PASS |
| C2 | two-primary and foreign-key stops, leftover replacement; import observation recorded separately, not a gate | PASS | PASS |
| R1–R4 | diagnosis, repaired version, `rpm -V` clean, rpmdb trust, execution; R3 also duplicate cleanup and retained release | PASS | PASS |
| R5 | diagnosis, newer-version stop, unchanged state | PASS | PASS |
| D | C1 set plus repository download | PASS | not specified |
| E | trust visible, first execution over runtime SSH | PASS | PASS |
| F | plain dnf/rpm release and dnf tools removal refused; four forged records refused; non-ancestor refused; user manager running/stopped; authorized erase of exactly one package | PASS | PASS |
| G | bounded runtime wait, inherited/forged descriptor, lock held after check-child and admin exit, preun/dnf completion, release | PASS | not specified |
| H | bypass upgrade; admin/runtime stop on mismatching and missing identity before release code | PASS | not specified |

24 of 24 required runs passed; none failed or was skipped.

D, F, G and H use small probe implementations (`wp0-admin`, `wp0-runtime`,
probe guard scriptlets and identity records). Their pass shows that the
mechanisms work on OL9; it does not verify the later `<product>-admin`,
`<product>`, guard or identity implementation. C uses the paper commands with
the declared automation adaptations. A uses the RPM prototype, not WP1 output.

## Audit

Every audit window starts at the probe's guest-side UTC timestamp
(`LC_ALL=C TZ=UTC`) and runs to collection. All 24 starts lie within one
second of the recorded probe step. Every ausearch exited 1 with exactly
`<no matches>`, and every audit result has `no_events: true` with no lines.
Positive runs (A, B, E) had their own rollbacks and windows.

The query is known to detect events on this VM: the earlier run
`wp0-full-20261025-190455` returned a real FANOTIFY denial, which led to the
[UTC correction](RPM-WP0-AUDIT-UTC.md).

## Deviations and limitations

- **Review scope.** The [directory-ownership fix](RPM-WP0-ERASE-FIX.md)
  (`f1ea688`) was independently reviewed before lab use. The
  [H working-directory fix](RPM-WP0-IDENTITY-CWD.md) (`7e15f0a`) went to the
  lab without separate review, by explicit product-owner choice. The
  [UTC audit fix](RPM-WP0-AUDIT-UTC.md) (`3222efb`) was also not separately
  reviewed before this run. A bounded review of both followed afterwards.
- **Pre-probe denial outside the window.** In `wp0-full-20261025-190455`,
  fapolicyd denied an `execve` by systemd (`comm="(direxec)"`, root,
  `subj_trust=2 obj_trust=1`) at `18:15:17Z`, during R2/P2's isolation step,
  about one second after P2 was applied. The plan's window starts at the probe,
  so this event does not affect any verdict, and the target executable was not
  identified. Pre-probe phases were not audited in the final run, so whether
  P2 regularly denies such a service start is unknown. This matters before P2
  is declared a supported production profile.
- **Trust observation.** The [journal/daemon observation](RPM-WP0-TRUST-REFRESH.md)
  is an automation adaptation. It reduces, but does not eliminate, overlap
  with fapolicyd refreshes. It is not a design for the product trust poll.
- **Isolation, not air gap.** Administration SSH remained available and inputs
  arrived by SCP instead of a mounted medium. Console typing, media handling
  and human usability were not tested.
- **Earlier runs.** Earlier lab reports remain historical; their verdicts
  are not changed by this run.

## Last recorded lab state

Observed: the last remote action was the H/P1 audit query, started at
`18:40:45Z`, which succeeded. The runner code issues no rollback, shutdown or
cleanup after the final audit; only the local signing-home comparison and
evidence save follow.

Inferred from the H probe and the code, not re-enumerated:

- PROD running with P1 policy and harness network isolation.
- Probe tools 2.0 installed, plus `wp0-release-base` and `wp0-release-sibling`
  at 2.0, installed without admin recording.
- The base identity record still describes 1.0; the sibling record is absent.
- The imported product key, runtime account and lab public SSH key,
  `/root/pkg`, `/var/tmp/wp0-input`, `/var/lib/wp0-probe` and
  `/run/wp0-probe` files remain.

PROD must not be treated as clean; any further run starts with the normal
rollback to `clean-agent`.

## Local checks and review

Rerun on the tested commit while writing this report:

- `python3 -B -m unittest discover -s acceptance -p 'test_*.py'`: 341 passed.
- `python3 -B -m unittest acceptance.test_rpm_wp0 acceptance.test_rpm_wp0_trust`:
  75 passed.
- WP0-scoped Ruff, Ruff format, Pyright and ShellCheck: passed.
- Mutation checks in a temporary copy: the tests fail if `cwd="/"` is removed
  from either H call site, or `TZ=UTC` from the start command or the ausearch
  environment.

Product/unit tests were not run because WP0 changes no product code.

The real OL9, RPM, fapolicyd, SELinux, systemd, Podman and HTTPS behaviour
described here comes from this lab run only.

Bounded post-run review of `7e15f0a` and `3222efb`:

- Neither fix relaxes a predicate, privilege drop, identity check or audit
  condition.
- Product lesson for WP3: `rpm -V` needs an accessible working directory, so
  product commands should choose their own directory, not inherit the caller's.

No human usability trial was performed.
