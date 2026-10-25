# WP0 follow-up: production health context and audit input

These fixes follow the [stopped A/P1 run](RPM-WP0-LAB-20261025.md) at
`0060a24`, after the product owner requested correction. **No new matrix run
was started and no previous verdict was changed.**

## Diagnosis on retained PROD

Bounded diagnostic commands used only configured PROD over administrator SSH.
There were no Proxmox calls, rollbacks, restarts, snapshot operations, package
transactions or new SSH keys. Podman ran under the account's numeric UID/GID
without supplementary groups. This is diagnostic evidence, not the probe's
required real-runtime-SSH execution. The first two inventory attempts failed
because they inherited the administrator working directory; their counts are
unusable. After selecting the account home, the comparison succeeded:

| Context | Observed inventory |
| --- | --- |
| Default login Podman paths | Exit 0, zero containers |
| Configured production Podman paths | Exit 0, three application containers, all running/healthy, plus infrastructure/service containers |

The applications were `platform-proxy-nginx`, `identity-postgres-db` and
`identity-server-app`, matching the three declared in the assigned bundles.
This later observation supports the diagnosis; it does not reconstruct the
missing inventory at the original failure instant. The status subprocess
selects production paths only for its own children. It cannot update its
parent health-check process, which previously inspected the default store.

The installed audit version is `audit-3.1.5-8.0.1.el9.x86_64`. Ausearch reads
inherited piped stdin unless told to use the logs, and raw mode suppresses
`<no matches>`. See the [upstream source](https://github.com/linux-audit/audit-userspace/blob/v3.1.5/src/ausearch.c#L172)
and [manual](https://github.com/linux-audit/audit-userspace/blob/v3.1.5/docs/ausearch.8).
The old empty status-1 result therefore did not establish a log search.
A bounded later query ending before follow-up diagnostics used:

```sh
LC_ALL=C ausearch --input-logs -m FANOTIFY,AVC \
  -ts 10/25/26 13:46:48 -te 10/25/26 13:48:00
```

Observed: exit 1, empty stdout, stderr `<no matches>`. Unbounded diagnostic
queries also encountered events outside this window; those are not attributed
to the original probe. The [safe diagnostic projection](rpm_wp0/results/diagnostic-20261025.json)
records the successful inventory, bounded audit and timestamps. Full records
are private under
`~/podman-offline-acceptance-runs/wp0-matrix-20261025-authorized-01-diagnostic/`.
Original-run evidence is unchanged.

## Fixes, tests and understandability

The A health program imports the installed, RPM-trusted `deployment.layout`,
calls `layout.select('myproduct')`, then `layout.check_user_manager(root)`
before Podman. Both APIs exist in the assigned 0.4.12 bundle. The account's
bootstrap remains authoritative; no login environment or manager check is
bypassed. The predicate still requires three running, healthy application
containers, complete installed status and active units. `runtime_projection`
prints public inventory before the predicate, without inspect environment,
credentials or pending-record contents, so future failures retain evidence.

`guest.audit` uses `--input-logs`, `stdin=DEVNULL` and the existing C-locale
start validation. It omits raw mode to retain the explicit no-match diagnostic.
Empty status 1, ambiguous errors and malformed output remain failures; any
FANOTIFY/AVC event still fails the case. The no-denial criterion is unchanged.

Regression tests execute the actual emitted A program with mocked host
boundaries. They start without production XDG variables, require layout and
manager validation before Podman, and exercise healthy, empty and unhealthy
inventories. Failure output retains observations and excludes private
sentinels. Audit tests assert log-source/stdin arguments and still reject empty
status-1 output. **327 harness tests passed, including 61 WP0 tests**; WP0 Ruff,
formatting, Pyright, ShellCheck and diff checks passed.

Developer understandability review: the installed layout remains authoritative,
`runtime_health` decides, and `runtime_projection` owns safe evidence. Success
selects/validates paths, queries, prints and decides. Failure prints, raises and
uses the existing failure-audit/report path; no repair/resume was added.
Static operator review: commands and account switches are unchanged, and future
failure records contain diagnostic counts/states. Human usability is untested.

Product code is unchanged; product/unit tests were not rerun. The modified
runner has not completed A/P1 or any new probe on OL9. Retained PROD was not
reset. Review and authorization are required before another matrix run.
WP0 remains incomplete and the stopped run remains NOT CLEAN.
