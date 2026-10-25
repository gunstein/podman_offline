# WP0 audit timezone correction

Run `wp0-full-20261025-190455` at `7e15f0a` stopped after R2/P2's probe
passed. Audit and failure-audit returned the same FANOTIFY denial, event 207,
with epoch timestamp `1792952117.238` (19:15:17 local time). The requested
start was 19:15:23. H was not reached; this run remains NOT CLEAN.

## Cause and correction

The [audit 3.1.5 time parser](https://github.com/linux-audit/audit-userspace/blob/v3.1.5/src/ausearch-time.c)
normalizes the date at midnight using `mktime`, then parses the requested
clock time into that structure and calls `mktime` again. The midnight DST
flag can survive into the second conversion. On 2026-10-25 in Europe/Oslo,
midnight is summer time and the evening is standard time. The requested
19:15:23 boundary consequently becomes 18:15:23 local time, admitting the
earlier event. A C locale alone does not prevent this timezone error.

`contracts.AUDIT_START_COMMAND` now captures the guest time with both
`LC_ALL=C` and `TZ=UTC`. `guest.audit` explicitly supplies the same values
to ausearch. This changes neither the guest clock nor its system timezone.
There is no post-filter, ignored denial, retry or weakened audit predicate.
Every FANOTIFY/AVC event returned for the corrected window still stops the run.
The original denial remains in the historical evidence; its initiating service
and target executable have not been established.

## Actual local OL9 reproduction

A disposable local `docker.io/library/oraclelinux:9` container, using
`--pull=never --rm`, installed audit from its container repositories. This
used network access inside the local container only, with no lab contact or
host package changes. The installed package was
`audit-3.1.5-8.0.1.el9.x86_64`.

The input file contained this public event, copied from the failure:

```text
type=FANOTIFY msg=audit(1792952117.238:207): resp=2 fan_type=1 fan_info=3 subj_trust=2 obj_trust=1
```

The command, with the zone and start substituted from the table, was:

```sh
LC_ALL=C TZ=<zone> ausearch -if /tmp/wp0-audit.log -m FANOTIFY,AVC -ts 10/25/26 <start>
```

| Zone | Start | Exit | Result |
| --- | --- | --- | --- |
| Europe/Oslo | 19:15:23 | 0 | incorrectly returned the earlier event |
| UTC | 18:15:23 | 1 | `<no matches>` on stderr, empty stdout |
| UTC | 18:15:17 | 0 | returned the event at the start boundary |

This verifies real OL9 ausearch parsing against a synthetic log file, not a
new VM run or live audit capture. The container was removed afterwards.

## Tests, review and remaining work

- Full acceptance-harness suite: 341 passed.
- WP0 tests separately: 75 passed.
- WP0 Ruff, formatting, Pyright and ShellCheck: passed.
- `git diff --check`: passed.

The regression uses the real capture shell command and GNU date with a fixed
instant. It passes the actual query arguments/environment to a child-process
model of the upstream two-stage parser. Spring/fall transitions and a UTC/local
date boundary are covered under three inherited timezones. Existing malformed
output, empty status-1 output and denial tests retain their stop behavior.
Product/unit tests were not run; product code is unchanged.

Static understandability review: pass. The two audit endpoints explicitly
agree on UTC and C locale; the controller still captures the boundary before
the probe and collects evidence afterwards. Failures retain the original
error and audit output. Operator commands are unchanged; audit display times
in new evidence are UTC. Human usability was not tested.

The lab VM was left untouched. The latest full run and all earlier reports
remain historical; none is reclassified as PASS. Full final-revision lab
verification remains outstanding, including H. This correction does not
establish WP0 completion.
