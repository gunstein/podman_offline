# WP0 selected reruns: E, A and R4 passed on both profiles

**SELECTED CASES PASS; full WP0 remains incomplete.** Tested runner revision:
`47b14cadb9db216bcf58d99878ea9c03ae70500c`, clean `feature/69-wp0` checkout.
The owner authorized correction and relevant acceptance tests. The
[refresh correction](RPM-WP0-TRUST-REFRESH.md) removes native LMDB reader
registration, observes refresh completion, and preserves the exact trust gate
and 30-second bound. All six selected case/profile runs passed on actual OL9.
No failed case was bypassed or retried.

## Subsequent independent-review finding

These are historical script verdicts at `47b14ca`, not verification of the
later gate correction. Review found that both R4 pre-paper-DNF cursors were
taken during a previous refresh. P1's cursor was at `16:18:29.465055Z`; that
refresh completed at `16:18:30.166126Z`, before the next refresh began at
`16:18:30.383511Z`. P2 likewise had a 313 ms completion/start gap. The old gate
could have opened inside either gap. The observed runs passed, but their timing
does not establish that the old gate was safe or associated with the intended
transaction. What originally triggered the earlier refresh was not established.

The [public observation projection](rpm_wp0/results/authorized-20261025-selected05-refresh-observations.json)
now supplies ordered journal messages, cursor timestamps/references, daemon
PID/state results and a bounded trust-dump sample from the original private
records. Cursor references are SHA256 prefixes, not raw cursor identifiers;
timestamps are decoded from the original cursor's realtime field. No new lab
operations were used to produce this projection. The original summary remains
unchanged. See the [corrected flow and outstanding verification](RPM-WP0-TRUST-REFRESH.md#independent-review-correction-local-only).

## Exact commands and evidence

Controller laptop, repository contributor, sequentially (continue only after
exit 0; each command separately builds fixtures and resets PROD per profile):

```sh
python3 -B acceptance/rpm_wp0/run.py --run wp0-e-20261025-authorized-05 --case E --execute
python3 -B acceptance/rpm_wp0/run.py --run wp0-a-20261025-authorized-05 --case A --execute
python3 -B acceptance/rpm_wp0/run.py --run wp0-r4-20261025-authorized-05 --case R4 --execute
```

All exited 0 with `SELECTED CASES PASS`. Private run directories are beneath
`~/podman-offline-acceptance-runs/`, named by the respective run IDs. Each has
`metadata.json`, `record.jsonl`, `REPORT.md`, controller/guest command records,
per-profile baseline/policy and independent audits.

| Run | Start UTC | Last audit start UTC | Controller command records |
| --- | --- | --- | --- |
| E | 16:07:28 | 16:10:29 | 29 |
| A | 16:10:32 | 16:15:56 | 61 |
| R4 | 16:16:01 | 16:19:05 | 27 |

The [public summary](rpm_wp0/results/authorized-20261025-selected05-summary.json)
contains all step verdicts, audit output, guest trust/repair predicates and
bounded source-count projections. Full repeated trust dumps remain private.

Only configured PROD was operated on. Every profile started with preflight,
rollback to unchanged `clean-agent`, a clean baseline, profile validation,
network isolation and transfer. P2 was derived in the running VM; no snapshot
was created, changed or deleted. DEV and other VMs were untouched. DNF used
disabled repositories and local package signature checking. No fapolicyd rule,
SELinux setting, trust-source requirement or timeout was relaxed.

All three original signing-home inventory comparisons were unchanged. Signing
and certificate fixtures were temporary, outside Git, and cleaned on runner
exit. Protected configuration and credentials were not emitted into public
evidence. Diagnostic SSH before the runs was read-only and is documented in
the correction note; the first normal rollback discarded the failed prior state.

## Expected versus actual

| Case | Required result and actual evidence | P1 | P2 |
| --- | --- | --- | --- |
| E | Automatic refresh observed, exact rpmdb trust within 30 seconds, first execution over ordinary-account SSH succeeds, clean audit | **PASS** | **PASS** |
| A | Prototype tools/platform/identity installed; exact rpmdb trust; real runtime SSH installation, three healthy application containers, complete installed status, HTTPS 204/200, clean audit | **PASS** | **PASS** |
| C3/R4 | Clean older tools upgraded through paper flow; delivered version, clean rpm verification, exact rpmdb trust and wrapper execution; clean audit | **PASS** | **PASS** |

Each E profile needed one CLI dump after daemon refresh completion. A crossed
the trust boundary where runs 03/04 stopped and completed the real application
flow. R4 crossed the upgrade boundary where run 02 stopped; its recorded
predicates were `diagnosis`, `repair-version`, `repair-integrity`,
`repair-trust`, `repair-execution` on both profiles. These observations establish the selected script outcomes at this revision;
the review limitation above prevents treating them as proof of the gate's
transaction association; they do not prove
the exact native cause of the removed reader's interaction with fapolicyd.

C1, C2, C3/R1–R3/R5, B, D, F, G and H were not rerun. C has no aggregate PASS,
and these six results are not a full WP0 go/no-go approval. The miniature tools
remain probe implementations, not production implementations.

## Policy and FANOTIFY/AVC

The full observed [P1 policy](rpm_wp0/results/authorized-20261025-selected05-policy-P1.json)
and [P2 policy](rpm_wp0/results/authorized-20261025-selected05-policy-P2.json)
include configuration, effective rules, RPM filters, languages and plugin.
Every profile passed the exact baseline/derivation predicate. P1 retained all
14 rules, `trust = rpmdb,file`, `integrity = none`, `permissive = 0`. P2 removed
only original rules 1/2/12 and changed trust to `rpmdb`, integrity to `sha256`.
SELinux was Enforcing. The daemon's active PID was checked before and after
each successful trust dump.

Each of the six independent audit windows returned explicit:

```text
<no matches>
```

There are no FANOTIFY/AVC lines to reproduce. Positive E/A runs and the R4
repair cases had separate rollbacks and audit windows; no negative result was
used to satisfy a positive audit gate.

## Last recorded lab state

PROD was last running/reachable during R4/P2's successful final audit. Its last
recorded policy is P2, created in memory/on the running disk, not a snapshot.
Tools 2.0 was installed, rpm verification was clean, trust matched rpmdb, and
the wrapper ran. The daemon was active with the same PID across the trust dump;
no later service-state query was made. R4 installed no prototype application
release packages or application services; the earlier A installations were
discarded by rollback before R4.

Expected residual state includes the probe tools and public key, runtime
account/lab authorized public SSH key, `/root/pkg`, `/var/tmp/wp0-input`, P2
policy and harness network isolation. Residual files were not re-enumerated
after the last audit. No final shutdown or rollback ran. The VM must not be
assumed to be clean P1; a new authorized run begins with normal rollback to
`clean-agent`, which remains the only selected baseline snapshot.

## Local checks and review scope

334 acceptance-harness tests passed, including 68 WP0 tests. WP0 Ruff,
formatting, Pyright, ShellCheck and diff checks passed. The paper-command shell
fixture and new journal/deadline/service-state regressions ran locally.
Product/unit tests were not rerun because product code did not change.
Real Podman/systemd/HTTPS verification here belongs specifically to A/P1 and
A/P2; local tests and historical results are not substitutes for those runs.

Static developer and operator understandability reviews passed for the bounded
correction, with success and failure flows recorded in its note. No separate
independent code review or unassisted human usability trial occurred. The
native daemon failure's precise cause remains unproven; the unsafe reader
interaction was removed, not declared repaired inside fapolicyd.
