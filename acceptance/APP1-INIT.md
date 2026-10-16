# App1 database init container (0.4.8)

Backlog item 17 uses an actual app1 init container to perform required database
schema creation. App1 is suitable because it already has a separate PostgreSQL
pod and shares the small Todo backend image with app2. No component split or
new host lifecycle mechanism is necessary.

## Startup and data ownership

`components/app1/manifests/40-postgres.yaml` precedes `60-todo.yaml`. The existing
renderer sorts manifest filenames, preserving that order in both production's
app1 YAML and dev's combined YAML. PostgreSQL is started in its own pod before
the Todo pod begins init; it does not wait behind that pod's init containers.
The configured DB_HOST still points at that separate database pod. Init waits
for database availability, not for another ordinary container in the Todo pod.

Podman 5.7.0 source was inspected directly:

- [play.go](https://github.com/containers/podman/blob/v5.7.0/pkg/domain/infra/abi/play.go):
  `sortKubeKinds()` retains relative Pod order, the document loop calls
  `playKubePod()` sequentially, and that function starts the pod before returning.
- [pod_api.go](https://github.com/containers/podman/blob/v5.7.0/libpod/pod_api.go):
  `Pod.Start()` runs init before ordinary containers; `startInitContainers()`
  waits and returns an error on nonzero init exit.
- [kube-play documentation](https://docs.podman.io/en/latest/markdown/podman-kube-play.1.html):
  the pod annotation `io.podman.annotations.init.container.type: always` selects
  init execution on pod start rather than removing it after its first success.

This source review supports the design; it is not a run on the target's Podman
version. The existing Quadlet still supplies the same component YAML, shared
network and 180-second startup timeout. No host deploy, render or dev helper
code changed.

The init command `python /app/schema.py` uses the backend image. It validates
the existing file-secret interface and executes the same `CREATE TABLE IF NOT
EXISTS todos` DDL previously used by backend startup. PostgreSQL, init and
backend consume the same `app1-database-password` Secret/key. Init mounts only
that Secret read-only, without client keys/session material or the data PVC.

Connection attempts use a two-second driver timeout. Availability retries have
a 60-second deadline; authentication and SQL/schema errors fail immediately.
SQL and lock waits are limited to five seconds. A process alarm imposes a hard
75-second limit covering other blocking work, and the CLI emits only controlled
failure text with exit 1. No supplied password/config/driver exception or complete
connection string is logged.

App1 backend selects `TODO_SCHEMA_MODE=external` and verifies the required table
and columns with a SELECT, without DDL. Init failure cannot be masked by backend
creation. App2 has no init container or mode override and retains its existing
startup creation/retry behavior, using the same shared DDL. Ordinary container
probes and sibling/platform/Identity restart ownership are unchanged.

Repeated creation changes neither existing rows nor identity values and does
not rotate credentials or reset volumes. Fix the cause of failure, then repeat
the same dev or bundle install command. Normal deployment retry and retained-data
uninstall semantics remain unchanged. No migration, fallback, destructive reset
or general schema-migration framework was introduced.

## Changed files and delivery

| Files | Change |
| --- | --- |
| apps/todo-backend/schema.py | Standalone idempotent init CLI and backend readiness check |
| apps/todo-backend/app.py, database.py, Containerfile | Select external schema for app1, share DDL, allow bounded connect timeout, include schema module |
| components/app1/manifests/60-todo.yaml | Init container, always annotation, backend mode and image 0.2.2 |
| components/app2/manifests/60-todo.yaml | Shared backend image 0.2.2; behavior unchanged |
| tests/test_init_database.py, test_bundle.py, test_images.py | Startup/failure/preservation, actual app1 archive and current build tag coverage |
| acceptance/database_test.py, test_database_init.py, test_acceptance.py | Real disposable init/replay probe, local harness tests and correct init inventory expectation |
| VERSION | App/help release 0.4.8; platform/Identity remain 0.4.7 |
| README.md, ARCHITECTURE.md, BACKLOG.md, tests/README.md, acceptance/README.md, this report | Current behavior, checks and target gaps |

Rebuild `localhost/myproduct-todo-backend:0.2.2` with `dev/build-images.sh` on
the build machine. Existing image discovery deduplicates app1's init/backend
reference, includes it in the offline archive and loads it before install.
Both apps reference that image; other image tags/build recipes are unchanged.
Init requires no target download or new runtime package. Config/credential paths,
Secret/PVC names, DB parameters and the dependency graph are unchanged.

## Local checks

Executed 2026-10-16 with Python 3.12.14 and PyYAML 6.0.3:

| Check | Result |
| --- | --- |
| Product tests | 253 passed (241 baseline plus 12 focused tests) |
| Acceptance-harness tests | 162 passed |
| Ruff lint / format | Passed for host, harness, tests and Todo backend; 62 Python files |
| Pyright | 0 errors/warnings for project checks and separately schema.py/database.py with declared psycopg 3.2.10 dependency |
| Vermin | Minimum Python 3.6 for host tools/product tests |
| ShellCheck | Passed for all documented shell entry points |
| git diff --check | Passed |

Product tests render actual app1 YAML, compare PostgreSQL/init/backend Secret
and parameters, check separate earlier DB pod and exact init image/command,
exercise backend mode selection and reject missing schema without backend DDL.
Driver failures cover unavailable DB, authentication, SQL permission error,
invalid credentials and retry deadline; the CLI strips private diagnostics.
A child process tests an actual alarm interrupting blocked preparation, with
the same handler but a shortened one-second test alarm.

Repeated SQL creation/data/ID preservation is exercised with SQLite, adapting
only PostgreSQL's identity syntax and connection-local SET commands. Driver
transport is otherwise stubbed. This is not PostgreSQL correctness evidence.
The real app1 tar test checks the init command, Never policy and deduplicated
backend image list/save request; image save/build transport remains stubbed.

The existing `database-runtime` lab action now plays the actual app1 init command
in a disposable probe pod, verifies the table before its ordinary client runs,
inserts one row, then recreates the pod/init and verifies that row unchanged.
It uses the action's UUID-scoped PostgreSQL/Secret/network and configured special
credentials. Two local harness tests cover construction, replay and failure
cleanup only. The real lab action has not been run here.

## Remaining runtime verification

Podman, systemd targets and a lab were unavailable; no real image build, container,
PostgreSQL init/replay or SELinux/fapolicyd check was performed. Python 3.6 support
is checked statically; no 3.6 interpreter or second PyYAML version was available.
Historical reports/evidence remain unchanged and do not verify this release.

On the authorized disposable lab, rebuild images and run the existing
database-runtime action plus fresh app1-first/app2-first and platform/help-only
matrix. The runner resets its configured VMs; no reset was performed here.
Check actual startup order, successful fresh table creation, failed init keeping
the backend stopped, timeout/failure diagnostics without credentials, successful
retry after restoring availability, restart/redeploy/reboot with retained Todo
rows and credential/config bytes, and unchanged app2/Identity behavior. Verify
offline image availability and target policy/audit results. Record these as fresh
evidence rather than reusing earlier lab results.
