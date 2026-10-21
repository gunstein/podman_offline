# Portable bundled component files (backlog 57)

Implemented on 2026-10-21 from main `afbf70f`. Real Podman/systemd/SELinux/fapolicyd
verification passed on 2026-10-21 at `cda22e7`; see [Real runtime verification](#real-runtime-verification). Existing installations can be discarded; no migration,
schema compatibility layer or old-release fallback was added.

## Contract and information flow

A source entry has exactly one of `path` or `component_file`.
`component_file: sql/010-reference.sql` selects the current component's
`files/sql/010-reference.sql` in the active source checkout or unpacked release.
`resolve_file_source` is the shared resolver; ordinary `resolve_path` keeps its
relative/absolute/tilde semantics for ordinary paths and public client certificates.
Component IDs are passed explicitly through config, validation, Secret key
discovery and materialization; no component is inferred from cwd or config paths.
The bundle guard supplies its explicit build root to the same resolver.

`file_group_sources` validates the new mutually exclusive fields and refuses
`generate`, including an empty list, on a component input. Portable source checks
inspect ancestors and the full selected tree, refuse traversal, symlinks, missing
sources and special files, and reuse delivery's Secret key/type/duplicate checks.
They read no input bytes and run before generation. Secret sizes are still
checked when file bytes are materialized. Database binding validation refuses
component files as password sources. Standalone callers lack component context
and refuse this source kind.

`init-config` retains logical declarations in the private persistent config.
Install/validate resolve them against the incoming release, so changed bytes in
version two reach a new import archive without editing that config. Newly added
defaults do not overwrite retained config. A missing new-release input fails
before output/host operations; the old installed YAML and old release are never
used as fallback input. Ordinary generation, credential retention, import PVCs,
uninstall and durable retry records keep their existing owners and behavior.

The bundle guard distinguishes explicitly public `component_file` Secret inputs
from ordinary private Secret paths. An ordinary/private declaration or credential
alias protecting the same file still blocks copying it. Actual bundle archives
are tested for both permitted public Secret content and private-alias refusal.

## Demo and runtime assertions

App1's production defaults select `sql/010-reference.sql`; its component dev map
repeats that input and adds `sql-dev/900-dev-sample.sql`. Both harmless public
files ship. Sensitive dev seeds belong outside `files/`, selected by ordinary
`path` in dev config; a platform test deletes that external file and the source
checkout before production validation/install.

The existing Postgres image runs `seed-database` after `prepare-database`, with a
read-only imported seed PVC and the existing password Secret. A folded, single-line
shell command sorts `*.sql` by C locale, stops on psql errors and withholds psql
diagnostics. Password bytes enter `PGPASSWORD` only in the container. SQL is not
templated or executed by the deployment engine. The demo has 8 pods, 10 regular
app containers, 2 init containers and the same 6 image names.

`seed_content` checks the actual PostgreSQL container's public marker rows:
DEV requires `reference=release-v1` and `dev-sample=dev-only`; PROD requires only
`reference` with the selected installed release's value. It derives that expected
fixture value from that release's public SQL, and the upgrade separately forces
`release-v2`, so an unchanged/old bundle cannot pass. Raw diagnostics and
unexpected row values are withheld. Normal and renamed (`orders`/`inventory`)
dev/prod flows share the assertions. The renamed generator carries `files/` and
renames resource IDs in both defaults and component dev maps.

`seed_upgrade.py` clones the tested revision into an isolated temporary checkout,
changes exactly app1 VERSION and reference SQL, builds only app1, and copies only
its bundle/checksum/optional signature and image inventory back. Real Git fixture
tests protect unchanged operator source and checksum failure handling. The
existing app1-first/app2-first upgrade then queries `release-v2`. Persistent
comparison permits only `app1/files/app1-seed.tar` to change; config, credentials,
Todo data and sibling checks remain required. The verified archive hash becomes the
baseline for the later platform and Identity upgrades, which still fail if it
changes again. Item 53's actual image upgrade is
still separate work and can extend this builder and its changed-file check.

`database_test.seed_retry_check` is a runnable disposable Podman probe. It imports
the actual reference SQL plus a later failing statement, requires failed init
and no started consumer, and queries the earlier committed reference row. It
repairs/reimports that input and runs twice more, requiring one reference row and
the existing Todo row. Its pod and own seed volume are cleaned up; the existing
database harness owns database/network cleanup. Harness regressions reject false
init success, a started consumer, failed repair and invalid exit status.

Imports overwrite matching files but retain unlisted ones. Removing a declared
file does not delete its old imported copy; wildcard SQL execution can encounter
that old file. The demo uses idempotent upserts, one transaction per file
(`--single-transaction`) and retry, not migration tracking or cross-file
rollback. The real probe's failing file inserts a row before its error and
requires that row to be absent while the earlier file's row is committed
(review follow-up 2026-10-21; passed in `03-database-runtime` of the `t10` runs). Do not reuse disposable
dev data volumes as fresh production volumes.

## Local verification

These are results for this worktree. No local stub result constitutes actual
Podman/systemd verification.

- Focused portable-file and actual-init tests: 21 passed.
- Acceptance harness: 206 passed.
- `python3 -B tests/run.py demo`: 65 passed.
- `TMPDIR=/workspace/scratch/0780781d7ca6/t python3 -B tests/run.py platform --isolate`:
  363 executed, 360 passed; three signing tests failed their environment
  prerequisite. GPG-agent sockets are prohibited in this environment, as
  diagnosed for item 56; the isolated suite is not reported wholly green.
- Ruff lint/formatting, ShellCheck, relative documentation links and
  `git diff --check`: passed.
- Pyright: 0 errors, one existing environment warning for missing `requests`
  source in `dev/smoke-test.py`.
- Vermin: minimum Python 3.6. This is static compatibility analysis, not execution
  on a real Python 3.6 host.

The first isolated platform run executed 362 tests: 359 passed and three signing
tests failed their GPG-agent prerequisite, with the same socket permission
restriction documented for item 56. The final 363-test run includes the additional
directory delivery regression and the stricter pre-generation key/type check.

## Understandability review

Success: `component_defaults` produces logical config; component validation
checks portable declarations without bytes. `validate_component` and standalone
`effective_documents` repeat the same portable checks before a host action.
`materialize` rechecks those declarations before generation, then resolves public
files with explicit component context, delivers Secret bytes/import lists, and
the existing archive/PVC code publishes the output. The source of file bytes is
the selected release, while persistent config owns the stable reference and
ordinary credential files retain their existing authority.

Failure/retry: a missing, traversing or unsafe new-release source fails shared
validation before writes or host commands. Existing installed config, YAML,
credentials and archives remain available. Correcting the selected input and
retrying uses the ordinary lifecycle; no source-path cache or new persistent
state is introduced. The SQL probe separately checks application-level partial
commits and replay. Existing pending-operation handling still owns service retry.

The only new generic concepts are one source field and one shared resolver with
small metadata checks. The existing module layout remains. The optional component
argument distinguishes supported component callers from standalone callers and
is deliberately explicit; config never carries hidden release metadata. Public
SQL execution, marker parsing and the isolated upgrade builder are demo/harness
code. No generic SQL runner, expansion engine, plugin or transaction framework
was added. Review traced config ownership, validation ordering, side effects,
completion and failure boundaries in the affected flow.

## Real runtime verification

| Run | Revision | Result |
| --- | --- | --- |
| `t9-app2` | `101bc54` | Stopped at `10-platform-persistent`: harness compared against the pre-app1-upgrade baseline (fixed in `cda22e7`) |
| `t10-app1` | `cda22e7` | CLEAN PASS: full app1-first flow, app1/help/platform/Identity upgrades, uninstall |
| `t10-app2` | `cda22e7` | CLEAN PASS: full app2-first flow, same upgrades and uninstall |
| `t10-help` | `cda22e7` | CLEAN PASS: help-only upgrade |
| `t10-platform` | `cda22e7` | CLEAN PASS: platform/help without Identity |
| `t10-identity` | `cda22e7` | CLEAN PASS: Identity-only upgrade with declared config change |
| `t10-shop` | `cda22e7` | CLEAN PASS: renamed product, registration removal and retained-bundle uninstall |

Runs used the two disposable lab VMs (Oracle Linux 9.8, Podman 5.8.2, systemd 252,
SELinux Enforcing, fapolicyd active on PROD) from clean checkouts. Evidence is
stored outside Git under `~/podman-offline-acceptance-runs/<run>/`. Results
earlier than `cda22e7` are not evidence for this revision.

The app1-first and app2-first runs include the disposable SQL failure/retry probe
(`03-database-runtime`), DEV seed rows, offline install, changed-SQL upgrade to
`release-v2`, retained config/Todo data and untouched siblings. The renamed run
checks the same base rows with renamed file references and components. The lab
`03-unit` step (`tests/run.py all`) passed on the DEV VM, where GPG-agent sockets are permitted.
