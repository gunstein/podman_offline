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

Failure/retry path: an interrupted install can leave metadata without a marker,
a prior marker with newer metadata, or pending owner work. Status exposes that
state and returns 1 without creating, clearing or acknowledging anything. The
normal install retry therefore sees the same pending bytes and retained config/
credentials, resumes existing work and writes its completion marker in the
existing order. A later status can report completion. The local tests cover the
incomplete-to-complete marker transition and unchanged pending bytes; the existing
fresh-process lifecycle retry regressions remain part of the platform suite.

The source and diff were reviewed separately from tests. The understandability
review passed: durable authority, pure file checks, bounded host queries, output
formatting and exit-code decisions are explicit. This adds one focused status
module; lifecycle schemas, completion rules, credentials and retry ownership do
not change. JSON is a report format, not new persistent state.

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

## Current-change checks

| Evidence | Result |
| --- | --- |
| Focused status and real-wrapper product tests | 11 passed |
| `python3 -B tests/run.py platform --isolate` | 451 passed |
| `python3 -B tests/run.py demo` | 66 passed |
| `python3 -B -m unittest discover -s acceptance -p 'test_*.py'` | 247 passed |
| Ruff on changed Python files / full documented format and Pyright checks | Passed |
| Vermin for documented product/tests paths | Minimum Python 3.6 |
| `bash -n acceptance/remote.sh`, local documentation links, `git diff --check` | Passed |

Full-tree Ruff retains the 12 existing findings in the three item 61 files noted
in [CLI wrapper verification](CLI-WRAPPER.md); this separate gate is not green.
ShellCheck is unavailable. No real Podman/systemd/SELinux/fapolicyd run or Python
3.6 interpreter run was performed for this change. Historical/manual installation
results do not verify this new command. Fresh committed lab scenarios from
[acceptance instructions](README.md), including ordinary and renamed installs,
will now exercise the status CLI automatically after installation.
