# Installed component status (backlog 39)

Implemented on `feature/39-component-status` (2026-10-24), based on the CLI rename
commit `88f3110` (which includes item 59). These local branches have not been
merged into main by this work.

## Command and authority

`./deploy.sh status` and `./deploy.sh status --json` run as the runtime account
from any same-product component bundle. The prepared bootstrap/layout is required;
source checkouts and standalone fixtures are refused. The bundle selects the
product/code, while `/var/lib/<product>/state` supplies installed versions,
dependencies and unfinished work. No release config, manifests, templates,
credentials or sibling release directories are read to decide installed state.

The completion marker is authoritative for the completed version; metadata gives
the recorded version and dependencies. Missing markers are incomplete first
installs. Different marker/metadata versions expose the previous completed version
and the recorded upgrade target rather than calling the target installed.
A pending attempt makes its component incomplete even if the two versions match
and its old service is still active. The previous completion marker is retained.
Orphaned, invalid or symlinked markers, malformed metadata/pending state and
foreign products are refused through existing catalog/pending guards plus the
regular version-marker check.

Text rows contain name, completed version, unit, systemd state and completion,
followed by product and pending operation/component/owners. JSON contains
`product`, `components`, `pending`; component rows contain `name`, `version`,
`recorded_version`, `unit`, `state`, `complete`. Missing versions and absent pending
work are JSON null. Pending uninstall work remains visible after its component's
metadata has been removed.

The only host calls are one bounded `systemctl --user is-active <unit>` per
recorded component. Failed/inactive/missing units are findings; missing command,
manager/bus errors, malformed command output and timeouts produce `unavailable`
without echoing captured diagnostics. No user-manager environment query, Podman,
repair, initialization or lifecycle action runs. The unit state is not a fresh
container/application health probe. The report is observational, not a lock or
atomic transaction snapshot across a concurrent install.

Exit 0 requires a nonempty set of complete, active components and no pending work.
Other findings return 1; invalid CLI arguments return 2. Structural state errors
use the normal concise stderr error path rather than emitting partial JSON.

## Lifecycle and understandability review

Successful path: `deploy.sh` -> `deployment.__main__` -> `cli.main` ->
`status.status` -> `collect`. `deploy.service_user`/`layout.select` validate the
account/bootstrap and select production paths without writing them. Existing
catalog functions validate descriptors/markers, order dependencies and derive
product-prefixed unit names; `registrations.load_pending` only reads the record.
All file checks finish before `unit_state` queries units. The same report feeds
text/JSON and the exit-code decision, with no separate status-state model.

Install success: after declaration/staging/precondition checks,
`install_component_plan` materializes YAML and verifies images, then calls
`registrations.begin_install` before writing installed metadata or service files.
Image failures preserve the existing deployed state and do not open a new attempt.
The existing private, atomic/fsynced pending record identifies the attempt even
with an empty owner list. `owners=[]` means no registration owner remains to be
confirmed; it does not mean the selected component's install is finished.
Registration changes merge their required owners into
that record; `acknowledge_owner` saves progress without clearing it. After all
required restarts/health checks, `write_installed_marker` durably publishes the
completed version, then `clear_pending` closes the attempt.

Failure/retry: same-version reinstall can write new YAML and fail at daemon-reload
while the old service remains active. Its previous version marker is retained,
but `collect` sees the pending component and reports `complete: false`, exit 1.
Status changes no bytes. A new install process reads that record, follows the
existing render/upgrade policy, repeats the work and clears pending only after
completion. Owner acknowledgement and marker/cleanup failures retain the attempt.
Equal-version `newer-only` retries still skip rendering/restarting the component.
The record also blocks conflicting uninstall, so it cannot discard that work.

The source and diff were reviewed separately from tests. The understandability
review passed: durable authority, pure file checks, bounded host queries, output
formatting and exit-code decisions are explicit. This adds one focused status
module. The review follow-up extends the existing install record's lifetime and
allows an empty owner list; its fields stay unchanged. No second journal, lock
or transaction framework is introduced. JSON status remains a report format.

## Product/unit evidence

Ten new `test_status.py` tests use a renamed `cedar` product, arbitrary component
IDs, external images and no apps, gateway, Identity, public URL or database.
They cover distinct versions in dependency order rather than filename order,
text/JSON agreement, installed versus incoming versions, source/sibling-release
removal, empty state, incomplete first install and upgrade, repair, pending
install/uninstall, failed/missing/unavailable units and CLI argument/exit behavior.

Snapshots compare all fixture bytes and modes, including pending and credentials;
a read guard refuses config/credential opens during status. Invalid/symlinked
markers and foreign products fail before host queries. Tests assert exact unit
query arguments and bounded execution and reject arbitrary private subprocess
output. `test_wrappers.py` runs the actual command in a new process from another
working directory after source deletion and release relocation, using a different
same-product bundle and deliberately broken app config.

Review regression: `StatusLifecycleTests` builds a minimal external-image
`cedar/worker` bundle and deletes the source. Each init/install/status/retry runs
in a fresh interpreter using actual lifecycle code and files, with host transport
stubbed. Changed configuration followed by daemon-reload failure or process death
leaves new YAML, no restart, the old completed version and an incomplete status
despite an active unit. Marker-write and pending-cleanup failures are covered too.
Status snapshots preserve every state byte/mode; retry retains config/credentials
and restores exit 0. A separate upgrade/equal-version `newer-only` test retains
version reporting and skip behavior. Existing retry tests now also assert that
completion-marker failures retain the attempt even when the owner list is empty.

The coverage follow-up makes `upgrade: always` explicit and guards both ordinary
and pathlib file opens in the fresh status process: config/credential reads fail
the test. Retry observes the actual atomic marker replacement and pending removal
boundaries, requiring pending to exist through the completed marker write.
`test_last_owner_acknowledgement_does_not_finish_the_install` changes actual route
and client inputs, confirms both owner services, injects failure at the marker
write, then requires `owners=[]` to remain pending. A new process restarts only
the selected app and completes; confirmed owners are not restarted again.
Existing uninstall failure/deletion/conflict and owner retry coverage is retained.

### Demonstrating the original defect

The current same-version lifecycle regression was run in a temporary exported
platform tree with `deploy.py`, `registrations.py` and `status.py` replaced by
their actual `b46d548` contents. The working checkout was untouched. It failed
at the daemon-reload subcase with `0 != 1` and this status:

```json
{"components":[{"complete":true,"name":"worker","recorded_version":"1.0.0","state":"active","unit":"cedar-worker.service","version":"1.0.0"}],"pending":null,"product":"cedar"}
```

The same regression passes with the fix. Reproduce the negative control locally
(the unittest command is expected to fail):

```sh
status_baseline=$(mktemp -d)
python3 -B tests/run.py platform --export "$status_baseline/tree"
for file in deploy.py registrations.py status.py; do
    git show "b46d548:deployment/$file" > "$status_baseline/tree/deployment/$file"
done
(cd "$status_baseline/tree" && PYTHONPATH=tests:. python3 -B -m unittest platform_tests.test_status.StatusLifecycleTests.test_same_version_failures_remain_incomplete_until_fresh_process_retry)
rm -rf -- "$status_baseline"
```

## Acceptance-harness evidence

`remote.sh` calls `status_release` after every successful `install_checked`
(normal, renamed, repeat and upgrade installs). It runs the deployed
`deploy.sh status --json` as the separate runtime account and checks the selected
installed version against the independently transferred release version, plus
product, unique component names, units, completion and active states. Evidence
prints only a validated public projection. Failed installation preserves its
exit code and skips the status check.

Four new harness tests exercise the actual embedded probe and shell wiring:
correct CLI/JSON, wrong versions/products/pending/completion/unit values,
subprocess failures/redaction, install-failure propagation and scenario wiring.
These tests stub runtime; the real lab steps are runnable but have not run here.

## Opt-in same-version lab probe

`acceptance/status_retry_test.py` is a focused guest probe delivered on stdin by
the controller through the existing `as_product` transport. Select it with
`--status-retry`; `07-status-retry` runs after installation/health, before the
persistent-state baseline. It uses app1 in normal scenarios and orders in the
renamed scenario. Platform/help-only is refused because it has no marker consumer.
The probe's demo-specific part is the public `DEMO_CONFIG_LAYER` ConfigMap value
and the `<component>-todo-backend` container; the product regression uses the
minimal owner-free cedar/worker model instead.

The probe requires an active, completed, equal-version `upgrade: always`
installation. It changes only that public config key. A fresh Python process
imports the authenticated release package and intercepts exactly
`systemctl --user daemon-reload`, returning a distinctive failure after the real
YAML write. All preceding transport is real. No on-disk release code, unit template,
trust inventory, fapolicyd policy or root-owned file is edited. An unrelated
failure cannot count as successful injection.

It checks new YAML, unchanged completed marker, unchanged old container ID/value,
and active/incomplete status with an empty-owner pending install. File/mode hashes
in memory verify that status did not change persistent state. An ordinary fresh
`bash deploy.sh install`, with no injection, must replace the container, clear
pending and restore status exit 0. Crucially, `podman exec ... printenv
DEMO_CONFIG_LAYER` must return the new value; YAML alone is not evidence of use.

Finally, the probe restores original config bytes and runs ordinary install again,
also after assertion failures. It verifies the original running value and
unchanged protected package/template files. Cleanup failure fails the step;
pending is never deleted by the probe. Captured deploy output, private hashes and
credentials are never printed. A failing step still stops the surrounding run.

Commands for a later operator-authorized run, from a clean committed checkout
with the usual [lab prerequisites](README.md):

```sh
python3 acceptance/acceptance.py --run status-retry-normal --status-retry run
python3 acceptance/acceptance.py --run status-retry-renamed --renamed-product --status-retry run
```

These are normal harness runs and include its VM snapshot resets. **Neither has
been executed for this implementation.** The existing six-scenario matrix does
not cover this failure path unless the new flag is explicitly supplied. Earlier
matrix results cannot verify it. Logs identify `07-status-retry`; run metadata
records whether the flag was selected.

Seven focused harness tests cover the probe's success/restoration, false-success
status, missing/wrong pending owners, status writes, wrong injection, missing YAML,
unexpected restart, changed marker, stale container value and cleanup failure.
They exercise the exact injection source, controller stdin delivery and opt-in
normal/renamed scenario ordering, and CLI refusal of unsupported scenarios before
any run is created. These are simulated runtime checks, not lab runs.

## Current-change checks

The lifecycle fix was committed as `bd0cc77`. The coverage/lab-probe follow-up
is based on that commit. Current local results are recorded below; real runtime
verification is still outstanding.

| Evidence | Result |
| --- | --- |
| Focused status, retry, registration removal and image-failure product tests | 41 passed |
| Original `b46d548` lifecycle with current regression (negative control) | Fails as expected: exit 0 / complete true / pending null after daemon-reload failure |
| `python3 -B tests/run.py platform --isolate` | 454 passed |
| `python3 -B tests/run.py demo` | 66 passed |
| `python3 -B -m unittest discover -s acceptance -p 'test_*.py'` | 254 passed |
| Full documented Ruff format / Pyright checks | Passed / 0 errors |
| Full documented Ruff lint | 12 existing findings; no new findings |
| Vermin for documented product/tests paths plus the new guest probe | Minimum Python 3.6 |
| Bash syntax, local documentation links, `git diff --check` | Passed |

`ARCHITECTURE.md` and its diagram were corrected in `bd0cc77`: the read-only
systemd-manager environment check precedes database Podman queries. This follow-up
retains that ordering and changes no production lifecycle code.

Full-tree Ruff retains the 12 existing findings in the three item 61 files noted
in [CLI wrapper verification](CLI-WRAPPER.md); this separate gate is not green.
ShellCheck is unavailable. No real Podman/systemd/SELinux/fapolicyd run or Python
3.6 interpreter run was performed for this change. Historical/manual installation
results do not verify this new command. Fresh committed lab scenarios from
[acceptance instructions](README.md), including ordinary and renamed installs,
will now exercise the status CLI automatically after installation.
