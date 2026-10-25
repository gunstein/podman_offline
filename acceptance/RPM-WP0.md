# RPM delivery WP0: stopped before the probes

**NO GO / investigation incomplete.** On 2026-10-25, creating the authorized
`clean-strict` snapshot succeeded, but the subsequent rollback to `clean-agent`
failed. Proxmox/ZFS requires that snapshot to be the most recent on this disk.
No probe A–H ran. No signature, runtime, retirement or locking mechanism has
passed WP0. This report makes no proposal to change the design or pass criteria.

The stop rule was applied to this infrastructure failure too: no further
probes, snapshot changes, policy repairs or alternative lab runs followed it.

## Revision, artifacts and machines

- Base: `main`, `9a933a92cd9bda6a1ca7e79d85c696f244d5efff`.
- Branch: `feature/69-wp0`; executed investigation code:
  `6806591` (the controller was started at this revision). Subsequent commits
  add local tests, preserve reporting after audit failure, and record evidence;
  these changes were not rerun against the VM.
- Target: configured `PROD_VMID`, actual Proxmox name `todo-standby-clean`
  (the task calls it `todo-standby`). DEV and other VMs were not accessed.
  No change to Proxmox storage, permissions, networking or other VMs was made.
- Original `clean-agent` was rolled back successfully before deriving P2.
  Its snapshot configuration, excluding Proxmox's computed digest, compared
  equal before and after creating `clean-strict`. It was not edited or deleted.
- `clean-strict` was created from `clean-agent`, without product files or
  product RPMs. It remains present. Policy was measured before taking the
  snapshot; booting/rolling back to that new snapshot was not verified.
- Final read-only API check: PROD **stopped**. The failed rollback did not
  reach its start step. No start or further rollback was attempted after stop.
- Input bundles: platform 0.4.12, identity 0.4.12 and platform 0.4.13 from
  `~/podman-offline-acceptance-runs/host65-20261024-144821-app1/`.
  The existing prototype rebuilt them on the laptop, with tools version
  `0.202610250832`, using an OL9 container. Build passed (114.905 seconds).
  Nothing was uploaded or installed on PROD.

Private run evidence remains outside Git at
`~/podman-offline-acceptance-runs/wp0-20261025-signatures-p1-02/`.
The sanitized [step records](rpm_wp0/results/record.jsonl) and effective
policies are retained in this repository (trailing whitespace trimmed in the
policy copies; original captures remain in the private run folder). Historical prototype results are
not evidence for this change.

## Effective policy

Full effective `fapolicyd-cli --list`, configuration, RPM filter and plugin:
[P1](rpm_wp0/results/policy-P1.txt), [P2](rpm_wp0/results/policy-P2.txt).

| Setting | P1, clean-agent | P2, clean-strict preparation |
| --- | --- | --- |
| OS | OL9.8 | OL9.8 |
| SELinux | Enforcing | Enforcing |
| fapolicyd / firewalld | active / active | active / active |
| fapolicyd | 1.4.5-1.1.el9_8 | same |
| RPM / DNF | 4.16.1.3-40.el9 / 4.14.0-34.0.1.el9_8 | same |
| rpm-plugin-fapolicyd | installed; `/usr/lib64/rpm-plugins/fapolicyd.so` | same |
| dnf-plugins-core | 4.3.0-26.0.1.el9 installed | same; download not exercised |
| trust | rpmdb,file | rpmdb |
| integrity | none | sha256 |
| permissive | 0 | 0 |
| subj_cache_size | 4099, unchanged | 4099, unchanged |
| rules | 14, matching the recorded P1 baseline | 11; original rules 1, 2, 12 removed |
| RPM filter | captured in linked policy | identical to P1 |

A local comparison of the captured policies confirmed P2 equals P1 with
exactly those three rules removed and only `trust` and `integrity` changed
in the configuration. Rule numbers in the effective P2 list are renumbered.
P1 was not weakened. No `file` trust or additional allow rule was added.

## Commands and stop evidence

Controller working directory: `~/koding/podman_offline`. Configuration was
read privately from `~/.config/podman-offline-acceptance/lab.env`; no contents
or credentials are included here.

```sh
git switch main
git switch -c feature/69-wp0
python3 -B acceptance/rpm_wp0/run.py --run wp0-20261025-signatures-p1
python3 -B acceptance/rpm_wp0/run.py --run wp0-20261025-signatures-p1-02
```

The first attempt stopped in a read-only check because the initial literal
name check expected `todo-standby`; it made no VM changes. The name check was
corrected to the actual configured PROD name before the second command.

The second command built private fixtures, then performed these operations
only on configured PROD:

1. Stop, rollback `clean-agent`, start, wait for SSH; capture P1 policy.
2. Run [strict.sh](rpm_wp0/strict.sh) as root over SSH. It verifies the three
   original rules, removes exactly those source rules, sets `trust = rpmdb`
   and `integrity = sha256`, runs `fagenrules --load` and
   `systemctl restart fapolicyd`, and checks that product files/RPMs are absent.
3. Capture P2 policy using [policy.sh](rpm_wp0/policy.sh).
4. Shutdown PROD, create snapshot `clean-strict` through the Proxmox API,
   check that the original snapshot configuration is unchanged.
5. Attempt rollback `clean-agent`; **FAIL**, then stop. The API returned:

```text
Proxmox task failed: can't rollback, 'clean-agent' is not most recent snapshot on 'local-zfs:vm-108-disk-0'
```

6. Read-only audit collection attempted SSH, but PROD was stopped:

```text
ssh: connect to host 192.168.0.108 port 22: Connection timed out
```

No FANOTIFY or AVC lines were collected. This is **missing evidence**, not
`<no matches>` and not a clean positive run. The initial finalizer let this
audit failure interrupt summary generation; the original per-step logs and
records survived. A local regression now checks that metadata/report generation
survives an unavailable audit. That correction was not lab-rerun.

One command to repeat the implemented investigation prefix, using a new run ID:

```sh
python3 -B acceptance/rpm_wp0/run.py --run wp0-new-investigation
```

**This is not a complete A–H runner.** It implements profile preparation and
probe C, starting with C/P1 because product-bound verification is prerequisite
to installing candidate RPMs. It always reports NOT CLEAN for this incomplete
investigation. Existing snapshots are not replaced or deleted. No repeated
lab command was executed after the infrastructure stop.

## Probe results

`NOT RUN` is neither PASS nor a failed mechanism. A dash means the plan does
not require that profile. Every mandatory result remains outstanding.
Criteria below summarize the [authoritative table](../docs/RPM-DELIVERY-PLAN.md#work-package-0-investigation-decides-gono-go).

| Probe | Required result | Actual P1 | Actual P2 |
| --- | --- | --- | --- |
| A | Healthy services over real runtime SSH; rpmdb-only release trust; no FANOTIFY/AVC | NOT RUN | NOT RUN |
| B | Root Python stdin and prepare-host account Python both run | — | NOT RUN |
| C | Full isolated paper bootstrap signature matrix, stop rules and tools repair | NOT RUN | NOT RUN |
| D | Candidate checks match C, including repository download | NOT RUN | — |
| E | Exact trust appears within poll bound; first execution allowed | NOT RUN | NOT RUN |
| F | Every plain erase refused; exact authorized erase succeeds; invalid records refused; manager independence | NOT RUN | NOT RUN |
| G | Bounded runtime exclusion, inherited descriptor validation and lock survival through child/admin exit | NOT RUN | — |
| H | Missing/mismatching identity detected before all release code, including init-layout | NOT RUN | — |

No probe failed: the **P1 reset prerequisite failed before C/P1**. The
positive/negative probe separation was not exercised. No real runtime SSH
account, Podman workload, systemd product service, tools repair, signature
gate, repository download, first execution, erase guard, lock handover or
identity check was tested on the VM.

## Delivered scope and limitations

- New files are confined to `acceptance/`. No product code, production manual
  or RPM delivery plan changed. This investigation closes no product gap.
- [build.sh](rpm_wp0/build.sh) calls the unchanged prototype from a temporary
  directory with the three required bundles. [signatures.sh](rpm_wp0/signatures.sh)
  creates unsigned, foreign-primary, foreign-subkey, product-subkey,
  tampered-header, tampered-payload, two-primary-key and older-tools fixtures.
  They built locally; their expected security behavior is **unverified**.
- GnuPG worked only on a disposable copy of the lab key and temporary test
  keys outside Git. The original home was not mounted in a container or opened
  by gpg. The temporary tree was removed. The intended final byte-inventory
  comparison did not run because of the original finalizer failure, so that
  independent preservation assertion is a verification gap for this run.
- The C script uses the prototype's `myproduct-host-tools` name and SCP input
  directory in place of the plan's future `myproduct-tools` and mounted `/mnt`.
  No USB/DVD or console flow was exercised. The older-tools package is a
  minimal repair fixture, not a product implementation.
- Harness network isolation was scheduled after reset; it was **not reached**.
  No target DNF operation ran. Target repositories were not contacted; the
  laptop build container used network to obtain build prerequisites.
- No test certificates were generated because the runtime probe was not reached.
- Deviation from the requested deliverable: the complete A–H scripts and lab
  matrix were not completed. D/F/G/H probe implementations were not written.
  Work stopped at the infrastructure failure rather than changing the lab or
  claiming an uncertain result passed. No WP1 work was started.

## Local verification and review

Final local commands (repository root):

```sh
python3 -B -m unittest discover -s acceptance -p 'test_*.py'
.venv-tools/bin/ruff check acceptance/rpm_wp0 acceptance/test_rpm_wp0.py
.venv-tools/bin/ruff format --check acceptance/rpm_wp0 acceptance/test_rpm_wp0.py
.venv-tools/bin/pyright acceptance/rpm_wp0 acceptance/test_rpm_wp0.py
.venv-tools/bin/shellcheck acceptance/rpm_wp0/*.sh
git diff --check
```

- Product/unit tests: not run; no product changes.
- Acceptance-harness tests: **272 passed**, including six new tests for the
  actual signature-output predicate, authorized rollback scope, stopping on
  rollback failure, key inventory behavior and reporting after audit failure.
- Ruff, formatting, Pyright, ShellCheck and diff whitespace checks: **PASS**.
  Relative report links checked locally: **PASS**.
- Real OL9: policy inspection, stricter profile application, fapolicyd restart
  and snapshot creation succeeded; subsequent rollback and audit failed.
  This is no Podman/systemd product verification.

Review-guide contracts checked: protected authentication must not be claimed
from local fixtures, offline isolation must not be inferred before execution,
P1 remains unchanged, evidence classes stay separate, and planned RPM lifecycle
behavior is not represented as implemented behavior.

Understandability review: **PASS for the delivered investigation prefix**.
`main` names ordered steps; `strict_snapshot` owns policy/snapshot side effects;
`root_file` transports fixed root probe source; the existing harness `step`
decides PASS/FAIL and stops. Success reaches captured policy and a product-free
snapshot. The observed failure stops before isolation/upload/C; only audit and
local evidence finalization follow. There is no automatic repair or hidden
retry. `finalize` now retains reporting after audit failure. The incomplete
A–H scope is explicit rather than hidden behind a successful runner exit.

AI procedure review: **findings** — the supplied snapshot sequence could not
complete on this storage backend, and the full one-command WP0 runner remains
unfinished. This is lab procedure evidence, not a production-manual usability
assessment. Human trial: **not performed**; no operator usability or
customer-readiness claim is made.
