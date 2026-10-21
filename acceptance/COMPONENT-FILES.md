# Portable bundled component files (backlog 57)

Implemented on 2026-10-21 from main `afbf70f`. Real Podman/systemd/SELinux/fapolicyd
verification is outstanding. Existing installations can be discarded; no migration,
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
Todo data and sibling checks remain required. Item 53's actual image upgrade is
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
(review follow-up 2026-10-21; real runtime result pending). Do not reuse disposable
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

## Outstanding real runtime verification

Commit this work before running the clean-checkout lab harness. Use the disposable
VM prerequisites in [README.md](README.md) and a new run ID for each scenario:

```sh
python3 acceptance/acceptance.py --run component-files-app1-first --first-app app1 run
python3 acceptance/acceptance.py --run component-files-app2-first --first-app app2 run
python3 acceptance/acceptance.py --run component-files-shop --renamed-product run
```

The first two scenarios include the disposable SQL failure/retry probe, source
dev markers, offline install, changed-SQL upgrade, retained config/Todo data and
untouched siblings. The renamed scenario checks the same DEV/PROD base rows with
renamed file references and components. All real runtime, mount/import, startup,
SELinux and fapolicyd assertions are implemented but unverified here. Rerun the
isolated platform suite on a host permitting GPG-agent sockets to close that
separate local verification gap.
