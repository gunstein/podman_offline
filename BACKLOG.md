# Backlog

Use [the review guide](docs/REVIEW_GUIDE.md) for product contracts, lifecycle
review, evidence levels and the required understandability check. Follow
[AGENTS.md](AGENTS.md) when implementing or reviewing these tasks.

Planned work, not implemented behavior. Each item requires separate implementation
and verification. Item numbers are stable references, not execution priority.
The recommended implementation sequence through item 1 is complete. Remaining
items retain their individual scopes below; agree the next priority separately.

## Status

Open items follow, newest first. Finished and superseded items were removed on
2026-10-31; their full text is in the git history (`git log -p -- BACKLOG.md`).

| Item | Title | State |
| --- | --- | --- |
| 1 | Deploy maintainability refactor | done |
| 4 | Migration from retained monolithic 0.1.x installations | superseded |
| 6 | Runtime connection strings for existing .NET images | superseded |
| 8 | Rename core to platform | done |
| 9 | Extract Identity into a separate component and bundle | done |
| 11 | Plan an explicit retained core-to-platform migration | superseded |
| 12 | Rename component credential paths | done |
| 14 | Tighten app credential delivery and remove unused API secret | done |
| 15 | Remove obsolete legacy layout refusal checks | done |
| 16 | Combine secret generation and file delivery declarations | done |
| 17 | Use an init container for database preparation in one demo app | done |
| 18 | Move proxy configuration out of apps and use stock nginx from YAML | done |
| 19 | Remove branches whose changes are already in main | done |
| 20 | Make components and bundles declarative instead of hardcoding demo names | done |
| 21 | Fix manifest validation gaps and removal of obsolete registrations | done |
| 23 | Explicit side-effect-free validation command for YAML, secrets, volumes and placeholders | done |
| 25 | Smaller follow-ups from the item 20 review | done |
| 26 | Make reserved configuration names and shared settings visible | done |
| 27 | Declare the product name instead of hardcoding `myproduct` | done |
| 28 | Clarify the `install_standalone` docstring | done |
| 29 | fapolicyd denies systemd's Podman launch just after a trust update | done |
| 31 | Refuse component IDs that are prefixes of each other | done |
| 32 | Move registration and pending-record code out of deploy.py | done |
| 33 | Refuse Secret item keys that no source provides | done |
| 34 | Wait for healthy containers after install and upgrade | done |
| 38 | Sign bundles so the target can authenticate them | done |
| 40 | One version file per component in its own directory | done |
| 41 | Build Secret and ConfigMap values from templates at install time | done |
| 43 | Separate reusable platform tests from demo application tests | done |
| 46 | Prevent root host preparation from following service-user symlinks | done |
| 56 | Add component-specific dev configuration overrides | removed again by backlog 77 (no per-component dev file) |
| 58 | Clarify global dev overrides of owner-shared settings | done |
| 61 | Verify Secret-derived environment values in init containers | done |
| 70 | Provision a component's CA trust chain from the environment's PKI | done |
| 71 | Add a .NET and TypeScript demo app that signs in through Duende | done |
| 72 | Register API resource secrets with Identity | done |
| 76 | Reach the public origin from containers when the host maps it to loopback | done |

## 77. Make a component intuitive to write: env files, mounts and shared secrets

Status: **implemented**; the form on `318d394` passed all seven lab scenarios
(CLEAN PASS, [latest results](acceptance/RESULTS.md)). Later commits on the same
branch have unit and harness tests; their lab run is outstanding.

What a component author writes now ([contract](docs/COMPONENTS.md)):

- `bundles.yaml`: `product`, `gateway`, `identity` and `components: [ids]`.
  Dependencies, routes, clients and API secrets are derived from the files.
- One `config.defaults.yaml` per component: settings, `SECRET_FILES` (with
  path) and `ENVIRONMENT` (each container's variables, shipped with the
  release). One secret form, `@@secret:<id>/<key>@@`; an API declares its own
  secret and Identity's `ApiResources__<n>__ApiSecrets__0__Value` line names it.
  `@@CLIENT_ID@@`/`@@CLIENT_BASE_PATH@@` come from `client.yaml`.
- `PUBLIC_ORIGIN`/`HTTPS_PORT` only in the gateway's `config.yaml`. Every
  install renders again; only a downgrade is refused. Settings or secret IDs
  missing from the operator's `config.yaml` come from the release defaults.

Decisions by the product owner (2026-10-30 and 2026-10-31): config in as few
files as possible, easy to read, no name or path that no file states, only what
is needed now, and no code for earlier formats (there are no customer
installations). The design history is in git.

Remaining in this item:

- Remove the standalone mode (install/prepare/validate without `components/`,
  `examples/`) and `SECRET_TEMPLATES` as something authors write (also removes
  templated secret files). About 100 tests use them and must move to a product
  fixture with `ENVIRONMENT`.
- Not started from the original scope: `mounts/`, CA trust profiles, an example
  application for the organisation's SPA/.NET architecture.

## 73. Parse command lines with argparse subcommands

Status: implemented with local tests (2026-10-28); no real Podman/systemd run
yet. Split out of item 69, where the product owner asked for it on 2026-10-26
as part of WP2/WP3.

Delivered: `deployment/cli.py` uses argparse subcommands (one parser per
command, `allow_abbrev=False`, repeated flags refused, per-command `--help`)
and accepts exactly the earlier forms plus `--verbose`; `bundle.py` parses
`[<component> ...] [--verbose]` the same way. Decision on the usage stream:
usage errors now go to stderr (with the `Usage:` line and `ERROR:`), and
`--help` exits 0 on stdout instead of 2; the two wrapper tests and one CLI test
that read usage on stdout changed with it. Tests: `test_cli_output.py`.

Review of `731b97f` (2026-10-29), fixed in the follow-up commit: a repeated
`--verbose` before and after the command passed (subparsers have their own
namespace), `build-bundle.sh` accepted repeats and printed lowercase
`usage:`/`error:`, and `uninstall --` or `init-config -- app1` were accepted
where the old parser refused them. `deployment/arguments.py` now holds the
shared parser (`Usage:`/`ERROR:`), counts repeated flags over the whole line
and refuses `--`; both commands use it.

Implementation remains owned here; [item 75](#75-make-python-lifecycle-code-easier-to-follow-diagnose-and-change)
reuses the resulting parser and does not commission a parallel CLI rewrite.

### Problem

`deploy.sh` (`deployment/cli.py`) parses `sys.argv` by hand: one compound
validity expression decides which forms of `validate`, `prepare`, `install`,
`uninstall [<component>] [--delete-data]`, `init-layout`,
`init-config <component>` and `status [--json]` are accepted. It works for
today's few options but is hard to extend, gives no per-command `--help`, and
every new option (item 66's `install-set`, WP3's `init-config --settings`)
would grow the same condition. `scripts/release.py` uses one flat `argparse`
parser whose options are shared by every operation and checked afterwards
("setup arguments are only accepted for setup").

### Task

Use standard-library `argparse` with subcommands (`add_subparsers`, one parser
per command declaring only its own arguments, `allow_abbrev=False`) for
`deploy.sh`, and for every new command line from its first version: item 66's
install-set entry point and item 69's `<product>-admin` and `<product>`
commands. No third-party CLI library (offline hosts, fapolicyd, Python 3.6).

### Constraints

- Release interface: newer tools call older releases' `deploy.sh`, and the
  manual, the harness and the tests use its current forms. Keep accepting
  exactly those forms with the same meaning.
- Keep the exit codes (2 usage, 1 failure, 3 needs input where defined) and the
  usage and error messages and streams that tests, the harness and the manual
  rely on, or change them together with those consumers. argparse writes usage
  errors to stderr where `cli.py` prints its usage line to stdout today: decide
  once and update the consumers in the same change.
- Component arguments keep their current check (`common.ID`, then the bundle's
  own descriptor); argparse does not validate component names against a list.
- Prompts with defaults for paper operation (item 69) are a separate layer on
  top of parsing: ask only when an option is missing and stdin is a terminal;
  otherwise fail as today.
- `scripts/release.py` is not converted: item 69's WP6 removes that flow.

### Verification

Parser tests per command: every accepted form, unknown and misplaced options,
refused abbreviations, a missing or extra component, `--help` per command and
the exit codes. Existing CLI tests and the acceptance harness pass unchanged
(or are changed together with a deliberate message change). Python 3.6
compatibility (vermin). Update README's command section and the review guide's
"CLI entry point" contract.

## 74. One operator message convention and Python logging

Status: implemented with local tests (2026-10-28); the journal lines are not
yet verified on a real host. Split out of item 69, where the product owner
asked for it on 2026-10-26 as part of WP2/WP3.

Delivered: `deployment/output.py` (standard-library `logging`, `%(message)s`,
INFO to stdout and WARNING/ERROR to stderr through handlers that follow the
current streams, `--verbose` for DEBUG); every operator `print` in
`deployment/` and `bundle.py` goes through it, data stays `print`. Convention
chosen: the existing `[OK]`, a final `PASS: ./deploy.sh <command> completed`,
`WARNING:`/`ERROR:` on stderr; `bundle.py`'s `[WARN]` became `WARNING:` on
stderr. `+ command` lines are DEBUG, so they are hidden without `--verbose`;
the harness's platform-downgrade check, which proves no image operation by
their absence, now asks the old release's `install --help` and passes
`--verbose` only where it exists (older releases print them unconditionally).
Journal: `init-layout`, `init-config`, `install` and `uninstall` write a start
and a result line (one syslog datagram per line, identifier `<product>[pid]`),
naming the executing bundle's version and, for uninstall, the removed
installed version; `prepare-host.sh` does the same with `logger`; neither stops
a command without a journal.

Review of `731b97f` (2026-10-29), fixed in the follow-up commit: on Python
3.6 a failed `SysLogHandler` connection could leave a handler without a
socket, so a later `configure()` or interpreter exit raised; the
`SysLogHandler` is replaced by `output.JournalHandler`, which opens and closes
one datagram socket per line and keeps no state. The downgrade probe passed
`--verbose` to releases that refuse it. The uninstall line named the bundle's
version instead of the removed one. `HOST-PHASE:` and the
harness's `[OK] validated`/`PASS:` lines are documented as parsed interfaces
in the review guide. Outstanding: `journalctl -t <product>` on a real OL9 host
after install and uninstall (the per-user journal must be persistent, item 64),
and a run under a real Python 3.6 (not available where the fix was made).

[Item 75](#75-make-python-lifecycle-code-easier-to-follow-diagnose-and-change) owns
additional lifecycle decision/phase DEBUG context after this infrastructure is
integrated; handlers, streams, audit policy and existing review fixes stay here.

### Problem

Operator output is `print` in Python (about 24 calls in `deployment/`, 5 in
`bundle.py`, 14 in `scripts/release.py`) and `printf`/`echo` in shell, with no
documented convention and no Python `logging`. Prefixes vary (`[OK]`, `PASS:`,
`INFO:`, `START:`, `ERROR:`, `WARNING:`, `HOST-PHASE:`, `+ command`), stdout and
stderr are mixed without a rule, `release.py` parses `HOST-PHASE:` from
`prepare-host.sh`, many assertions in the tests and the acceptance harness match
these strings, and nothing records afterwards what the administrator or runtime
account did, which matters on closed networks.

### Task

- One convention, written into the review guide: completed steps `OK:` (or the
  existing `[OK]`, chosen once), `WARNING:`/`ERROR:` on stderr with the next
  action in the same message, a final `PASS:` line, no secret values. Results
  and data (the `status` table, `--json`, rendered output) stay plain `print`
  on stdout.
- Python: standard-library `logging` (Python 3.6, no extra packages) configured
  once in each command's entry point (`deployment/cli.py`, `bundle.py`), format
  `%(message)s` so visible text is unchanged; `INFO` to stdout,
  `WARNING`/`ERROR` to stderr (two handlers, since the default handler writes
  everything to stderr). `--verbose` (item 73) enables `DEBUG`, which carries
  today's `+ command` lines.
- Audit trail: one line per operator action and result to the journal via
  `logging.handlers.SysLogHandler` (`/dev/log`), identifier `<product>`, so
  support can ask for `journalctl -t <product>`. Shell scripts use
  `logger -t <product>` for the same; their terminal output stays `printf`.
  Without `/dev/log` (tests, containers) the command still works.
- Markers that other code parses (`HOST-PHASE:`, `PASS:`) become a documented,
  tested interface or are replaced by exit codes or `--json`.

### Constraints

- Keep existing messages and streams that tests, the harness and the manual
  rely on, or change them together with those consumers.
- Never log secret values, complete connection strings or config contents,
  also not at `DEBUG` or in the journal (credential-retention contract).
- Not in scope: `scripts/release.py` (removed in item 69's WP6) and
  application/container logs (already in journald through systemd and Podman).

### Verification

Tests for format and stream per message class, `--verbose`, the syslog handler
(with a fake socket), absence of secret values in every handler, and logging
reset between tests (configuration is global). Existing tests and the
acceptance harness pass unchanged. A real Podman/systemd run checks
`journalctl -t <product>` after install and uninstall. Update the review guide
with the convention and README where it shows output.

## 75. Make Python lifecycle code easier to follow, diagnose and change

Status: **planned; not implemented**, requested 2026-10-29.
Static analysis is recorded below; implementation remains future work.
This entry does not implement a refactor or establish a functional defect.
It follows the completed item 1 (git history), rather
than reopening that package extraction. No new priority over agreed operator
work is implied; select a small first slice with the product owner.

### Audience, outcome and preserved strengths

The reader is an ordinary developer with some Python experience who already
understands Podman, Kubernetes-like manifests and this project's configuration
model. Maintenance difficulty must be addressed in the Python, not attributed
to missing Podman training. Make it reasonably easy to find a behavior, follow
its control/data flow, distinguish checks from effects, locate a failure,
correct it without changing unrelated paths, and place an extension in one
clear home with a bounded set of related edits.

Retain ordinary functions, standard-library dependencies, the catalog/render/
registrations/lifecycle/CLI/status module boundaries, declarative dict lookups,
named install stages, shared validation, and host-independent lifecycle fixtures.
This is incremental code and testability work, not a rewrite, a new deployment
engine, a framework, or documentation as a substitute for clearer code. A large
developer guide and an organised trial with a new developer are deferred.

### Checked revision and coordination

The initial analysis inspected `120d4eb` and the in-flight 73–74 work at
`5bb5e26`. Before delivery, fetched and integrated latest `main`,
`870e85225557da63062dc06801a9fccb161899fe`, and rechecked the affected code
and updated review-guide contracts on 2026-10-29. This is the primary checked revision below. It includes
both `731b97f` (the product owner's review base) and its review fixes in
`5bb5e26`; the earlier `120d4eb` main did not. These are static observations,
not new test results. Reconfirm the base and ongoing work before each slice.

- [73](#73-parse-command-lines-with-argparse-subcommands) and
  [74](#74-one-operator-message-convention-and-python-logging) are now integrated
  on the checked main: argparse, `deployment/arguments.py`,
  `deployment/output.py`, `--verbose` command diagnostics, agreed terminal
  streams and a separate journal audit logger already exist. The earlier
  no-verbose observation applied only to `120d4eb` and is superseded. The
  original observation about command-focused verbose output remains relevant:
  `deploy.run` emits DEBUG command lines, while lifecycle decisions still lack
  comparable phase context. Do not commission parsing, logging handlers,
  operator/audit conventions or the review fixes in 73–74 again. Reuse their
  integrated interfaces; this item adds only justified lifecycle diagnostics.
- [69](#69-paper-first-installation-for-closed-networks),
  [66](#66-install-sets-several-signed-bundles-through-one-entry-point) and
  [RPM plan](docs/RPM-DELIVERY-PLAN.md) own new command boundaries, release
  selection, operation locking, RPM layout/authentication and replacement of
  `scripts/release.py`. Do not refactor that retiring publication tool here,
  redesign its replacement, or create a competing runtime entry point/context.
  Agree ownership before changing a shared lifecycle/path interface; defer
  larger path changes where the selected RPM work is actively changing it.
- Existing `install_checks`, `install_preconditions`, write/restart helpers,
  `uninstall_plan`, atomic owner-YAML publication, pending records and shared
  validation are already present. Do not propose creating these from scratch,
  re-extracting the package, or making all work pure before secret generation.

### Current observations, maintenance assessment and candidate actions

The evidence below is at the checked main revision. Line numbers identify
starting points, not stable interfaces. Maintenance assessments are review
judgments; proposed actions require justification and tests before coding.

| Area | Observed code/dependency | Maintenance assessment | Candidate action, not an implemented fix |
| --- | --- | --- | --- |
| A. Production dependencies | `layout.select` (`deployment/layout.py:308`) assigns `common.STATE`, `FILES_DIR`, `QUADLET_DIR`, `QUADLET_TARGET`, `QUADLET_YAML` and updates the process's XDG environment. `service_user` establishes this; `catalog.component_paths`, pending functions and lifecycle functions then read it implicitly. `DeployFixture.setUp` patches a dictionary of paths and `layout.select`; the fresh-process retry driver patches another subset. | A caller must know earlier initialisation and the selected product. Debugging crosses both the operation and its environment setup; test patching shows concrete coupling. This is not evidence that repeated commands currently fail. | Later, choose a coherent production-path boundary and pass a small explicit path value from the command boundary to its consumers. Assess `ROOT`/release identity and child-process environment separately. Keep stable constants, regex rules and account identity as constants unless a real variable dependency requires otherwise. |
| B. Boundary data | `install_checks` returns a five-position tuple; `known` overlays the incoming descriptor on installed descriptors. `checked` maps component to `(effective config, effective documents)`; `rendered` maps component to `(YAML text, import volumes)`. `registration_stage` returns `(imports, updates, removals)`. `imports` is both volume-to-path-list and, for APIs, an ordered `[staged API directory, persistent API directory]`; after `api_updates`, update bytes include private registered values. | Shape, validation state, source/installed/effective meaning and privacy must be reconstructed from producers and consumers. Positional API inputs hide why two directories are required. Rendered YAML contains Secret data and is sensitive despite base64 encoding. | Name these distinctions at the producer/consumer boundaries; consider small Python 3.6-compatible named results for checked components, staged registration results and materialized manifests where that reduces unpacking ambiguity. Keep dicts for natural lookup and YAML; do not wrap every document in a parallel model. |
| C. Effect names | `install_component_plan` (`deployment/deploy.py:984`) materializes/generates secrets, loads images, persists pending/metadata/registrations, writes units/imports, restarts services, writes the marker and clears pending. `materialize_component_manifests` explicitly permits secret generation; `registration_stage` writes temporary files. | "plan" suggests calculation, although the function executes. Staging and materialization are also not pure checks. Existing docstrings help, but names should not require reading the entire body to discover critical effects. | Rename the executor to describe execution (for example `apply_component_install`, subject to review), update callers, and make short contracts distinguish read/check, calculation, generation/temporary staging, persistent publication, host commands, health and acknowledgement/completion. Do not invent a plan object merely to justify its old name. |
| D. Interleaved responsibilities | `registration_stage` (`deployment/registrations.py:31`) retains non-selected registrations, validates incoming role declarations, records removals, stages route/client bytes, defers API values and builds aggregate indexes/imports. `uninstall` (`deployment/deploy.py:1201`) resumes a durable record, stops/removes resources, rebuilds/restarts owners, optionally deletes data and finalizes. `uninstall_plan` already validates a first attempt and captures volumes/owners before YAML deletion. | Changing one role or failure boundary requires tracking several independent branches and the durability order. Length alone is not the problem. | First consider three cohesive staging steps: retain existing registrations, stage selected declarations/removals, build/check derived indexes/import inputs. Keep role-specific cases explicit. Separately consider owner-refresh and optional data-removal extraction in uninstall, leaving its stop/persist/delete/rebuild/acknowledge/finalize order visible at the top level. Accept an extraction only if it reduces simultaneous concepts rather than adding forwarding calls. |
| E. Diagnosis | On main `deploy.run` (`deployment/deploy.py:516`) emits command lines at DEBUG; `install_needed`, pending-owner selection and render-skip decisions have no comparable phase trace. CLI catches expected subprocess/OS/deploy/YAML errors; it does not catch all programming exceptions. The integrated 74 implementation already separates terminal diagnostics from journal action/result audit. | A failed host command is easier to identify than the preceding decision that selected it or skipped rendering. This is a diagnostic limitation, not proof of wrong decisions. | Through the existing logger, add only useful DEBUG boundaries: operation/component, render/skip reason, resumed pending operation/version, remaining owner IDs, and phase reached. Preserve useful existing causes and narrow expected-error handling; do not wrap all exceptions in "install failed". |

For A, a later slice must first list the exact changing globals and consumers
it replaces. Establish checked paths/process settings at the command boundary;
use explicit inputs for the selected core functions, and configure child
command environment explicitly where needed. A small immutable path record may
help, but must not contain logger/catalog/secrets/services or the whole app.
Do not retain two mutable sources of truth: migrate a bounded call chain and
its fixtures together, with one authoritative selection. Keep an adapter only
at an explicit boundary with no independent mutable copy. Preserve source dev,
bundle install and standalone contexts; test independent roots and repeated
operations in the same process where this dependency is changed. Global-path
work is not a prerequisite for the smaller staging/naming improvements.

For B, describe whether each field holds public metadata, effective config,
paths, documents or finished bytes, and whether it can contain sensitive data.
Use names such as installed descriptors versus effective descriptors rather
than indiscriminately renaming every local variable. Choose a plain record or
simple class only where named fields help; type hints should explain rather
than create a complex type system. Never log a record/config/document with
`repr`, formatting, `vars` or automatic object dumps; consider suppressing a
sensitive record's automatic representation. No new serialized schema, bundle
metadata, registration format or pending format follows from an internal type.

For E, use allowlisted scalar context (operation, component, owner IDs,
version, phase, finite reason), not config, paths read from arbitrary secrets,
connection strings, exception-object dumps or whole plans. Keep operator text,
DEBUG diagnostics, machine-readable output and journal action/result audit
separate. Add no log line without a concrete debugging question it answers;
logging every helper is not the task. Context added to expected failures must
identify operation/phase/component while preserving the underlying cause.
Coordinate any visible message/stream changes with 74 and its consumers.

### Extension placement analysis (F)

No new feature is requested by these examples. Record the actual affected
implementation/caller/test sites in each slice; a lower line count is not a
success measure and a numeric edit budget is not a universal requirement.

| Representative change | Current authoritative home and consumers | Proposed boundary to protect |
| --- | --- | --- |
| A new manifest declaration rule | `render.effective_documents` and its checks, through `deploy.validate_component`; called by `check_manifests` in prepare/install and by `validation.validate_catalog`, `validate_bundle`, `validate_standalone`. `test_secret_keys.test_missing_key_is_found_by_every_path_before_writes` is an existing cross-path example. A bundle/installed-state rule instead belongs in `install_checks`; it need not run in a source-only context. | One rule implementation in the appropriate shared check plus focused fixtures for relevant contexts; do not copy it into each CLI mode or `validation.py`. Keep validation-only source checks and later workload-volume inspection explicitly distinct. |
| A new install decision | `install_checks` / `install_needed` decide against the descriptor, installed markers, config and pending version; `install_components` selects `checked`, then the executor consumes it. `validation.validate_bundle` also calls `install_checks` / `install_preconditions`. | A named decision result with an explicit reason and render eligibility, if justified; the executor acts on it and diagnostics describe it. Declaration-only decisions remain shared with validate; decisions requiring generated bytes or host queries stay at their necessary later boundary. No duplicate decision in CLI, validation and execution. |
| Change how a registration updates its owner | `registration_stage` / `api_updates` create inputs; `apply_registration_updates` persists owner work before mutations; `write_changed_owner_imports` and uninstall's owner loop publish imports and `replace_owner_secrets`; `restart_component_services` / uninstall restart and acknowledge. | Consider one cohesive owner-publication helper reused at those two publication sites, while each caller retains visible restart/health/acknowledgement ordering. Keep API Secret and route/client-volume differences explicit. Do not introduce a plugin/role registry or merge whole install/uninstall paths behind boolean flags. |

Concrete current fan-out: `install_checks` has two direct consumers,
`install_components` and `validation.validate_bundle`; changing its result
requires reviewing both, rather than patching only the executor. Registration
staging has six call sites across `deploy.py` and `validation.py` (dev prepare,
install, uninstall planning, uninstall owner refresh, catalog validate, bundle
validate). An owner-publication change has two orchestration sites (install's
`write_changed_owner_imports` and uninstall's owner loop), already sharing
`replace_owner_secrets`. These are review surfaces, not a demand to edit every
caller. A new shared declaration predicate normally needs one implementation
plus tests for its consumers, not six copies. Record actual changes per slice.

The first row does not claim all rules fit one universal validator. Preserve
necessary dev/source, installed-bundle and standalone differences visibly,
without forcing them through one function with accumulating mode flags.

### Staged delivery and dependencies

1. Recheck main and relevant in-flight 69/73/74 changes; choose **registration
   staging plus the install executor name/data boundary** as the proposed
   first slice, or justify a smaller alternative. Trace a successful operation
   and an interrupted retry before editing. Inventory existing tests and
   agree which behavior/effect boundaries the slice touches.
2. Fix the misleading executor name and clarify selected boundary results and
   data names. Keep behavior, serialization and side-effect timing unchanged.
   Do not turn this into a wholesale renaming/type-annotation exercise.
3. Extract only the cohesive interleaved responsibilities justified above,
   keeping orchestration order apparent. Review staging first; uninstall is a
   separate later slice, not an automatic addition to the first patch.
4. Add bounded diagnostic context through the integrated 74 logger. Reassess
   its current diagnostics first: missing lifecycle decision context is this
   item's scope; parser/audit follow-ups remain with 73–74. Do not introduce a
   second logger or reconfigure handlers in lifecycle helpers.
5. Reassess remaining global dependencies with concrete caller/test evidence.
   A later small explicit-path migration may be warranted; do not make moving
   every global/module a condition for landing earlier useful improvements.

Each slice must explain what dependencies/branches a maintainer no longer has
to reconstruct, what complexity deliberately remains, and why the changed
call graph is simpler. Reject extraction that only shortens a file or adds
one-line forwarding layers. Keep functional fixes in separate patches/items
where practical; record newly discovered defects separately with reproductions.
Do not quietly alter retry/validation semantics as part of this structural task.

### Preserved contracts

Follow [the complete review guide](docs/REVIEW_GUIDE.md), especially sections
1–6. Preserve Python 3.6, standard/offline dependencies, CLI forms, exit codes
and agreed message/data streams (including status JSON). Preserve declaration
checks before relevant writes and workload commands: validate reads no
credential contents, generates no secrets and runs no workload commands; its
existing temporary staging is not permission for persistent writes.

Keep private modes, credential retention, secret-safe diagnostics, installed
metadata and all registration/pending on-disk formats unchanged. Preserve the
actual install sequence: declaration checks and environment checks -> temporary
staging/checks -> materialization (which may generate retained credentials) ->
image load/verification -> pending record -> installed metadata -> changed-owner
work durably recorded -> registration publication/removal -> unit/import and
owner-YAML publication -> component/owner restart and health -> acknowledgement
-> completed marker -> clear pending. Do not move generation earlier or imply
rollback of already performed writes. The temporary stage may check API indexes
before secret bytes exist; API value validation happens after generation and
before pending/live registration publication.

Keep a fresh process able to resume every partial attempt, including after
registration deletion or loss of installed YAML. Ordinary uninstall retains
config/credentials/data; `--delete-data` removes only the selected component's
recorded volumes and state. Preserve unaffected component data/config/services,
owner restart eligibility/order and pending conflict/version guards. Path
clarification must not weaken user-manager/XDG agreement, symlink/ownership
checks, SELinux/fapolicyd boundaries, isolated bundles or source-dev separation.

### Current success and interrupted-operation traces

For a component bundle, `cli.main` parses/configures logging and audit, then
`cli.run` dispatches `deploy.install` to
`install_components`: `service_user`/`layout.select` establish paths;
`install_checks` decides render eligibility; environment checks and temporary
`registration_stage` precede checked manifests and `install_component_plan`.
That executor materializes, verifies images, calls `begin_install`, publishes
metadata and registration work, writes units/owner imports, restarts/checks
services, writes the marker and clears pending. The API owns its source secret;
registrations own derived per-component records; the owner's installed YAML
holds the rendered Secret; the pending record owns unfinished owner work.

For failure during owner YAML replacement, `write_install_record` keeps the old
file when replacement fails; registration changes and pending owners can
already exist. A later process must reconstruct the same operation from
installed metadata and `pending-operation.json`, rebuild the owner's Secret,
restart/check it and acknowledge only after success, then mark completion.
`install_checks` also guards a non-rendering retry against a different pending
version. This is a static trace of the intended existing code and test
assertions, not new process-retry evidence (see the API test limitation below).
In uninstall, the stored plan retains volumes/owners after YAML removal; it
must remain the source for retry instead of rediscovering deleted information.

### Existing coverage, specific gaps and verification plan

This inventory is **inspection**, not a claim that tests ran for this entry.
Read test bodies and fixtures before adding cases; do not replace behavior
assertions with checks for proposed internal names or function counts.

| Boundary | Existing coverage inspected | Remaining work for an affected slice |
| --- | --- | --- |
| Validation before effects / rendered bytes | `test_validation_order.py` checks prepare/install/standalone ordering, registration refusal before workload commands, archive checks before generation, and exact bytes installed from the single materialization. `test_validate.py`, `test_secret_keys.py`, `test_manifest_structure.py` and `test_api_registrations.py` cover shared declaration/credential-read refusals. | Reuse these guards. Add only a demonstrated missing path, with a malformed synthetic input and before/after files/host-call assertions, not a second string copy of the implementation. |
| Pending, registration/import writes, restart/health and completion | `test_retry.py` uses `helpers/retry_lifecycle.py` / `retry_driver.py`: each attempt starts `sys.executable -B`, checks distinct PIDs and retains actual files/archives. It covers partial client writes, owner import failure, restart/active/health failure, metadata/marker replacement interruption, completion cleanup, pending conflicts and owner acknowledgement ordering. `test_install_failures.py` protects image-failure state and old markers after service failure; `test_health_wait.py` covers the wait itself. | Do not commission an entirely new retry framework. Inventory explicit injection at pending-record replacement/fsync and acknowledgement persistence before claiming all durability boundaries are covered; the inspected record-failure matrix targets installed metadata/markers, not every `save_pending` boundary. Add focused fresh-process cases only where absent and touched. |
| Registration removal / uninstall | `test_registration_removal.py` checks exact removals/restarts, a component omitted from source not being removed, and interruption after deletion with a fresh-process continuation. `test_retry.py` covers uninstall after YAML removal, owner/import failure, partial `--delete-data`, mounted ConfigMap deletion, removed marker/data, conflicting flags and volume-inspection errors. | Preserve separate retention/deletion cases and actual sibling snapshots; extend only for extracted behavior not already protected. |
| API owner YAML update | `test_api_registrations.py::test_interrupted_owner_rewrite_keeps_the_old_yaml_and_retry_finishes` verifies atomic replacement, retained old YAML, pending owners and successful retry. Despite its "fresh process" comment, the retry calls `self.quiet(deploy.install)` in the same interpreter, after resetting the subprocess mock. This is not a real process restart. | Add an API owner-YAML publication failure followed by a genuinely fresh-process attempt using the existing driver/fixtures; assert owner Secret bytes, restart order, pending/completion, modes and sibling retention. Correct the misleading test comment when that test is changed. This coverage finding is not a demonstrated product retry bug and does not rewrite historical lab reports. |
| Paths / global initialisation | `DeployFixture` patches paths/layout/environment; retry transport patches a separate path subset. `test_layout.py` covers production selection, XDG agreement, refusing unsafe bootstrap/root state, and source-dev ignoring production layout; bootstrap interruption has fresh-process coverage. | If paths become explicit, retain those guards and add independent-root/repeated-operation isolation without recreating conflicting global and explicit states. Avoid tests tied to a particular context class name. |

For implementation, run the repository's existing product groups
(`python3 -B tests/run.py all`, plus `platform --isolate` for a generic lifecycle
slice), and applicable established static/Python 3.6 checks from the test/CI
instructions. Separately run
`python3 -B -m unittest discover -s acceptance -p 'test_*.py'` for harness wiring.
Test assertions must check observable outputs,
private-file access/modes, durable bytes and host effects, not the new helper
names. Add safe sentinel coverage for any new diagnostic's handlers/streams;
`test_cli_output.py` already covers parser forms, verbose command visibility,
terminal stream routing, secret-safe lifecycle audit and unreachable journal
sockets (including a fresh interpreter); extend it for new decision context
only where coverage is missing, rather than rebuilding 73–74 infrastructure. Test unexpected programming exceptions
remain diagnosable instead of being converted into generic success/failure text.

Select real Podman/systemd verification according to the actual slice: normal
and renamed lifecycle for changed staging/owner publication; include declaration
removal and unchanged siblings, and a minimal external-image worker fixture for
generic assumptions. For install/uninstall/paths, exercise restart, reboot,
upgrade/skip, retention and `--delete-data` on configured disposable lab VMs,
plus a controlled relevant failure and retry in a fresh process. For API-owner
or API path changes, include focused `--whoami` with registration/introspection
and rotation/removal, and the owner-publication/restart interruption missed by
ordinary happy-path smoke. If diagnostics change, check the agreed terminal
streams/status JSON and relevant journal audit on a real host without exposing
values. Never reset unrelated environments. Record exact tested revisions,
commands, results and gaps separately for product/unit, harness and real
runtime. Historical green lab runs cannot verify a future refactor.

### Understandability acceptance gate

Green tests and shorter files are insufficient. The final review of each slice
must answer the review guide's six questions and trace one success and one
interrupted operation/retry, naming state ownership and functions. Show that:

- The command entry and principal operation sequence are easy to find.
- Names and placement reveal important effects; temporary staging/generation,
  persistent publication and host commands are distinguishable from checks.
- Central inputs/results reveal shape, validation stage, origin and sensitivity
  without a long producer/consumer hunt; named results serve actual readers.
- Required paths/process settings and any remaining initialisation order are
  visible; no competing implicit/explicit source can drift.
- A new declaration rule has one identifiable authoritative home and can be
  exercised across relevant flows without copying the rule.
- Safe diagnostic context identifies the relevant component/phase/reason while
  preserving useful failure causes and existing machine-readable interfaces.
- The retry can be explained from files left by the first process, including
  owner work and completion; unrelated components remain untouched.
- The new call graph reduces hidden relationships rather than multiplying
  helpers. Document intentional complexity (three roles, source versus bundle,
  generation-dependent checks, existing durable protocol) and why it remains.

Record this as a code-review assessment, not empirical proof of human
comprehension. The larger developer guide/new-developer trial are deferred.
No operator commands/prerequisites are changed by this planning entry, so the
section 7 AI operator walkthrough and human trial are not performed here. If
implementation changes such procedures, apply section 7 then; green code tests
are not a human/operator usability result.

## 64. Support new rootless installations outside the login home

Status: implemented with local regressions on `claude/friendly-mendel-8u3bqs`
(2026-10-23), built on the unmerged item 54 branch; merged to `main`; full OL9
matrix CLEAN PASS on `5b8ab69`; manual ssh run without sudo worked 2026-10-23
with extensive help and found the missing persistent-journal prerequisite (now
in the guide). Not ready for the operator: the guide is not verified literally
and host preparation is too hard (items 65–67); small `/home` still untested. Requested 2026-10-23.

Delivered: `deployment/layout.py` (bootstrap file `~/.<product>/<product>.env`
with required `INSTALL_ROOT=/var/lib/<product>`, read as data; root/ancestor and
account-directory checks; refusal of product Quadlets in the login home);
`common.STATE` separate from the identity `common.HOME`; `prepare-host.sh --user`
for an existing account with a `user@<uid>` drop-in setting
`XDG_CONFIG_HOME=/var/lib/<product>/config` and `XDG_DATA_HOME=/var/lib/<product>/storage`;
user manager agreement check before lifecycle commands; `release.py` anchor moved
to `/var/lib/<product>`; the harness runs as `<product>-ops` with a read-only
home and checks unit sources, graphroot and home inventory after reboot; the
Norwegian [operator guide](docs/PRODUCTION-INSTALL.md) ships in every component
bundle. Open: the manual checks listed in the verification report; item 54 must be reviewed/merged first or together.
The operator needs to test an offline production installation immediately after
implementation. Scope is **new installations only**: no migration of an old
home-based installation, images, volumes or users. Ordinary upgrades, retries,
restarts and retention within the new layout remain required.

Deliver the implementation and a short, precise production installation guide.
The [operator-flow draft](docs/PRODUCTION-INSTALL.md) records the agreed target;
it is explicitly not a runnable recipe for the current bundles. Replace its
planned status with actual tested commands when implemented.

### Operator requirements and scope

- Run rootless as an existing non-root login account. Its real name, UID/GID and
  home can vary and need not match the product. `produser` and product `sms` are
  examples only. Keep the account's registered home, shell and login working;
  do not require `nologin`, rename the account, move its home or spoof `HOME`.
- The home has almost no free space. For product `sms`, the sole intended
  persistent product file there is `~/.sms/sms.env`, containing installation
  settings. All other product-persistent files belong under `/var/lib/sms`:
  releases, component config and credentials, rendered YAML, installed metadata,
  pending operations, route/client registrations, import archives, Podman
  configuration, images, volumes and product caches. Generalise from the catalog
  product name; do not hardcode `sms`, `produser` or `/home/<user>` in core code.
- System-owned `/etc` configuration, system journal and transient
  `/run/user/<uid>` are deliberate exceptions, not hidden relocations into the
  login home. Keep per-UID runtime semantics. Document archive staging and image
  import temporary-space requirements; no home-sized archive copies or caches.
- Administrator/sudo may prepare the host and protected release/trust boundary.
  Starting/stopping services, inspecting health/logs and ordinary product
  operations after publication must work as the selected account without sudo.
  Do not promise completely unprivileged publication of new executable releases:
  protected release installation and fapolicyd enrollment remain administrator
  operations unless an explicit safe delegation is implemented separately.
- Preserve dev behavior: `build/dev`, existing dev override precedence,
  `dev/dev.sh up/down`, image helpers and bundle creation must not start reading
  production `sms.env` or silently switch to production Podman storage. No need
  for application or manifest edits just to relocate host storage.

### Detailed instructions for the implementation agent

1. Read [AGENTS.md](AGENTS.md), [the review guide](docs/REVIEW_GUIDE.md),
   [architecture](ARCHITECTURE.md), [component contracts](docs/COMPONENTS.md),
   [tests](tests/README.md) and [acceptance](acceptance/README.md), plus items 46,
   54, 56, 57 and 60. Inspect current main and any ongoing item 54 work before
   selecting helpers/layout; the task text does not prove those fixes are merged.
   Trace `common.HOME`, `FILES_DIR`, `QUADLET_DIR`, `catalog.component_paths`,
   metadata, registrations and pending-state paths through init-config, validate,
   install, retry, upgrade and uninstall. Trace all shell/acceptance paths too.
2. Introduce one explicit production path model separating actual user home,
   release inputs, installation/state root, Podman storage/config and runtime.
   Keep common.HOME's identity meaning if retained; do not globally substitute
   `/var/lib/...` for the user's home. Derive consumer paths consistently instead
   of scattering new environment lookups or fallback chains. Use small functions
   and existing lifecycle boundaries, not a plugin or configuration framework.
3. Define a minimal, documented bootstrap format at
   `~/.<product>/<product>.env` (the sms example is `~/.sms/sms.env`). Find the
   actual user/home through account identity, and the product through the release
   descriptor. Specify supported fields, precedence, quoting, missing-file and
   unknown-key behavior, and how existing application settings in this file are
   treated. Read data, not shell code: no `eval`, shell `source`, substitutions
   or execution. Bootstrap fields select paths; they do not implicitly replace
   authoritative component config or forward secrets to all containers. Keep
   secret values out of diagnostics and redact invalid input. Require private
   ownership/modes and safely handle symlinks. Do not ship this file in bundles.
4. Use `/var/lib/<product>` as the target layout's root-owned anchor. A proposed
   layout is protected `releases/`, user-private `state/`, Podman `storage/` and
   `config/`; map all other durable outputs explicitly. The service user may
   manage its designated data directories but must not rename/replace the root
   anchor or protected release entries. Validate ancestors and ACL/mode exposure.
   Coordinate with item 54: reuse its verifier/publisher and update its layout
   assumptions if needed; keep final trusted release bytes and ancestors
   protected before and after verification. Never fix this with recursive chown
   of the whole installation tree or a root-owned directory inside a replaceable
   user-owned parent. Root must not source or blindly follow paths in sms.env;
   privileged destinations must come from explicit validated administrator input
   or protected configuration. Validate agreement with user bootstrap settings.
5. Adapt host preparation to an explicitly selected existing login account.
   Preserve its home, shell, contents and existing non-overlapping subordinate
   ID ranges; verify required mappings instead of overwriting them. Preserve
   item 46's non-root filesystem operations and race/symlink protections while
   preparing the new data locations. Support rootless linger, correct SELinux
   labels/equivalences and scoped fapolicyd trust. Do not disable enforcement,
   broaden executable trust to data, globally chown mapped volume contents or
   recursively relabel already populated container storage.
6. Configure Podman and the user systemd manager so CLI deployment, image load,
   kube/Quadlet services, interactive diagnostics and unattended reboot use the
   same storage and config. Work out Quadlet discovery before generation: merely
   adding `EnvironmentFile=` to a generated service or exporting variables in an
   interactive shell cannot establish the generator's environment. Verify the
   supported Podman/systemd versions and choose a small persistent integration.
   Preserve `/run/user/<uid>`; no fake HOME or persistent runtime directory.
   Avoid global shell exports that redirect dev or unrelated user workloads.
   Provide an explicit supported way to run production `podman` diagnostics if
   they require scoped configuration. Retain the one-product-per-account
   contract; general multi-product account support is not part of this item.
7. New-layout creation must refuse conflicting existing state or a changed root
   instead of silently creating a second installation, switching storage or
   migrating data. Cover restart and fresh-process retry on the same new layout.
   Keep credentials and DB volumes on ordinary uninstall; scoped delete-data
   must never remove the user home, shared anchor, protected releases, another
   product or unrelated containers. Preserve side-effect-free validate: no
   Podman/systemd commands, writes or reads of credential contents. Loading
   public bootstrap path settings is distinct from reading Secret source bytes.
8. Update bundles and host/deploy helpers as needed so a release operates offline
   without source checkout, sibling source directories or apps. Source dev and
   bundle building ignore installed production bootstrap settings. Preserve
   component_file resolution against the selected read-only release; ordinary
   path sources resolve against the new persistent component-config directory.
   Never copy local sms.env, credentials or production state into a bundle.
   Coordinate CLI spelling with item 60 instead of introducing another alias.

### Tests and real acceptance requirements

- Use synthetic products and a runtime user whose name differs from the product,
  with an actual home outside the install root and ordinary login shell. Include
  a renamed-product case. Test root derivation, malformed/missing bootstrap,
  permission/symlink failures, retained config, Secret templates, component files,
  installed metadata, registration updates, retry and scoped uninstall. Do not
  write tests that merely repeat the implementation's derived path strings.
- Test that command-like env values cannot execute, invalid inputs fail before
  side effects, root helpers cannot be redirected through user-controlled
  bootstrap/ancestors, and private content is absent from logs and artifacts.
- Add a real OL9 scenario with Enforcing SELinux and active fapolicyd, separate
  administrator and runtime identities, an effectively unwritable or tightly
  constrained login home after bootstrap, and sufficient space under /var/lib.
  Check actual Podman graphroot/volume paths and home file inventory. Distinguish
  unrelated OS/login files from product writes; no large files or product
  config/Quadlets may silently appear in the old home layout.
- Exercise protected bundle publication, first install in dependency order,
  actual init-container Secret/migration-probe delivery, HTTPS health, component
  upgrade retaining data, failed operation/retry, stop/start, logout and reboot
  without interactive login. Confirm that generated Quadlets are discovered and
  services use the intended storage after reboot, not only during install.
  Runtime operations must not rely on cached sudo credentials.
- Use real separate-UID checks for release write/replace denial, and verify that
  no unexpected SELinux AVC/fapolicyd denial is needed to make the normal flow
  work. Keep bounded waits and cleanup confined to disposable test resources.
- Run the appropriate platform/demo suites, platform --isolate, acceptance-harness
  tests and required static checks. Include a dev regression with a production
  env file present and an isolated bundle export; neither may inherit production
  paths/settings. Record commit and exact commands, separating unit, harness and
  real runtime evidence. If OL9 execution is unavailable, mark it pending and do
  not label the new deployment model ready for the operator.

### Required short production installation guide

Finish [docs/PRODUCTION-INSTALL.md](docs/PRODUCTION-INSTALL.md) as a short
Norwegian operator guide with concrete copy/paste commands, linked prominently
from README and included or explicitly delivered with the offline release.
Keep deep design/verification details in linked documents, not in the operator
flow. Use one coherent example with product sms and a different, replaceable
runtime username; never assume all component versions are equal. It must show:

1. Prerequisites, actual-user/root paths, required disk space and transfer of the
   right archives/checksums/signatures. Explicit signed-policy versus approved
   unsigned test flow; never run privileged code from an unverified archive.
2. Administrator host preparation for the existing account, bounded ownership
   and labels, port 8443, UID mapping/linger and protected release publication
   plus exact fapolicyd trust verification. State which steps repeat per release.
3. The exact minimal sms.env content and its permissions; no manual HOME change
   or terminal-only environment required. Show actual config/credential paths.
4. Rootless platform init-config, config edits, TLS provisioning, validate and
   install; then STS and dependencies with signing-PFX, DB credentials and the
   production migration/seed selection. Do not copy the entire dev credentials
   directory or ship dev overrides. Respect component-specific secret names.
5. Rootless status/log/Podman commands, local and external HTTPS checks, restart,
   logout/reboot verification and a few safe diagnostics for wrong paths/storage,
   permissions, missing credentials or fapolicyd trust. Show the execution user
   and success condition for each step; fail clearly instead of continuing.

Run the guide's commands as an acceptance scenario on a fresh host. Keep
README, architecture, review contracts, current helper usage and this backlog
status consistent with the final implementation. Complete the understandability
review by tracing one successful install and one failure/retry, explaining path
ownership, bootstrap loading and systemd startup. No automatic legacy migration,
application refactoring or unrelated backlog cleanup belongs in this task.

## 65. One-command host preparation and a short operator guide

Status: implemented on `feature/65-host-setup` with local regression coverage
(2026-10-24). The first real OL9 run at `8559a2a` stopped in preflight: sudo
reported explicit denial with exit 0, which setup incorrectly rejected. The
follow-up fix has regression coverage. All nine scenarios in lab series
`host65-20261024-144821-*` passed at `2d36d71`; unassisted human
verification remains outstanding under item 68. Review follow-up fixes literal manual
fail-stop behavior, interruption-safe bootstrap publication and bounded host
phase/error diagnostics, with regression coverage and a revised AI operator
assessment.
[Implementation, evidence and lab commands](acceptance/HOST-SETUP.md). Read the
[implementation plan](docs/HOST-SETUP-PLAN.md) before starting: it fixes the CLI,
bootstrap trust, journal policy, scope against 66/67, failure/retry behavior and
test gates. The focused `--host-setup` scenario uses the manual blocks and real
runtime SSH without sudo. `deploy.sh init-layout` replaces manual bootstrap-file
creation. The complete reboot/upgrade SSH path remains item 67. Found in the manual backlog 64 run
([report](acceptance/RESULTS.md)).
The operator's verdict: "Host preparation must be simpler. I did not
understand what was happening." (translated from Norwegian) Installation worked only with step-by-step help.

Today the administrator reconstructs the order from the guide, README and the
PFX guide: fapolicyd cache, persistent journal, transfer area, checksums,
independent key/tool hashes, protected copy of the release tool,
`provision-key`, `prepare` per release, `prepare-host.sh`, later `retire`.

Deliver one administrator entry point (`setup` in the existing independently
authenticated `scripts/release.py`, calling the protected `prepare-host.sh`;
no second release helper) that takes product, existing
runtime account, HTTPS port, the trusted public key with its independent SHA256,
the transfer directory, explicit release selections and a selected host-script
release, and then:

- checks every prerequisite first and names the exact fix (OL9, SELinux
  Enforcing, fapolicyd and `subj_cache_size`, firewalld, packages, account
  exists and has no sudo, space under `/var/lib` and `/var/tmp`);
- establishes the persistent journal for supported `auto`/`persistent` plus
  `SplitMode=uid` policy, without extra groups; refuses explicit incompatible
  policy rather than overwriting it. Document the host-wide change;
- uses the separately installed/authenticated release tool and pins the key
  once; consolidate and test the initial tool bootstrap procedure;
- runs the existing `prepare` for the selected bundles and the existing host
  preparation once. Publication follows explicit selection order; dependency
  ordering for runtime installation belongs to item 66;
- is safe to rerun after interruption and says which step completed;
- ends with a short report and the exact next command for the runtime account.

Keep the trust boundaries: authenticate before any privileged execution of
archive code, keep the runtime account without sudo, no wildcard or shell
expansion inside root-only directories, no hidden network access.

Rewrite `docs/PRODUCTION-INSTALL.md` around it: each step names machine,
account, one command and the expected output; one example product that matches
the demo (or a clear substitution table); PEM and PFX credential paths shown
separately; HTTPS checks against endpoints the component answers. Move design
detail to linked documents; keep every required action, including tool bootstrap
and the selected credential path, in the one manual.

Apply the [mandatory operator review](docs/REVIEW_GUIDE.md#7-mandatory-operator-and-procedure-understanding-review).
For 65, the AI walkthrough must cover transfer/tool authentication, prerequisite
failure and remedy, initial setup, identical rerun and interrupted setup retry,
then handoff to real SSH login as the non-sudo runtime account. Each step states
machine, user, access, copyable command and expected result. Count commands,
manual edits and account switches; simplify the tool if these make setup hard.
Errors must give a safe diagnosis, corrective action and exact continuation.

The acceptance path must execute the manual's bootstrap and `setup` command,
including first run, repeat and interruption/retry, with a checked mapping to
manual steps. No controller-provided helper execution, direct `prepare-host.sh`
call, journal setup or product/bootstrap-file creation may substitute for those
operator steps. Runtime steps use real SSH without sudo; coordinate this shared
path with 67, and mark its absence as a verification gap until implemented.
Preserve the existing hostile-input/security probes as additional tests.

Record a separate fresh-host trial by a person with limited Linux experience,
without oral help: time, errors, stops and explanations needed. Human verification
is outstanding; the assisted 2026-10-23 run does not qualify. The current
[AI assessment](acceptance/OPERATOR-REVIEW.md) has findings; repeat it on the final
manual. Automated success alone does not make 65 customer-ready.

## 68. Human operator trial on a fresh VM

Status: outstanding verification (2026-10-24). Required before declaring the
operator flow customer-ready; does not block merging the implementation of 65.
Coordinate with items 65–67 and repeat affected tasks when their manual changes.

A person with limited Linux experience must follow the English
[production manual](docs/PRODUCTION-INSTALL.md) on a fresh disposable VM at its
declared OS/account baseline, without oral help or internal architecture
knowledge. Supply only the documented delivery, substitution worksheet and
manual. An observer records events without coaching or silently repairing state.

Use a printed manual without copy/paste (backlog 69), with a console-only variant and one person holding both accounts. In item 69's phase 1 (unsigned RPMs) the trial has no key or fingerprint steps; repeat the affected tasks when phase 2 adds signing. Cover transfer and trusted tool bootstrap, prerequisite diagnosis/remedy, first
setup, repeated setup and continuation after an interruption, then real SSH login
as the runtime user without sudo, configuration/credential delivery, installation,
status and safe journal access. Include install sets and reboot/upgrade/retire
when items 66–67 provide those procedures. Record unsupported tasks as pending.

Record code/manual revision, VM starting state, relevant participant experience,
elapsed and active time, machine waits, commands, edits, account switches, errors,
stopping points and every requested explanation. Do not record sensitive values.
If assistance is needed, mark the task assisted, fix the manual or workflow and
repeat the affected task without help. Assess whether the tool needs simplifying
rather than merely adding more instructions.

Store the result in [the operator assessment](acceptance/OPERATOR-REVIEW.md),
following the [mandatory review criteria](docs/REVIEW_GUIDE.md#7-mandatory-operator-and-procedure-understanding-review).
Keep AI walkthrough, automated acceptance and human outcomes separate. The
assisted 2026-10-23 trial and green automated lab runs do not satisfy this item.
Completion requires an unassisted pass for each claimed task, with remaining
scope and usability findings explicitly recorded.

## 69. Paper-first installation for closed networks

Status: requirement and investigation (2026-10-25), lab questions answered and
an RPM prototype run the same day (see below); **direction chosen by the
product owner on 2026-10-25: signed RPM delivery with one command per role**
(see "Chosen direction"); **phased on 2026-10-26: unsigned RPMs first, signing
deferred, not dropped** (see "Phasing decision"); high priority. It
applies to items 65 (implemented for pasted commands), 66 (planned) and 68
(human trial), and must be settled before 66's operator-facing commands are
fixed.

Status 2026-10-27: the WP0 investigation matrix passed (all 24 case/profile
runs at `3222efb`, 2026-10-25,
[report](acceptance/RESULTS.md)). Nothing is implemented.
WP1 waits for the product owner's go/no-go and the two open phase 1 decisions
under "Phasing decision"; both are still open.

Many customers install in a closed server lab, often from a **printed manual**,
sometimes with **only a console** (bundles on DVD or USB, no SSH), and the
administrator and the runtime user are often **the same person** using two
accounts. Whatever the scenario, installation must be easy. The current manual
assumes copy and paste: a ~60-line Python block for the tool bootstrap, a long
multi-line `setup` command, a variable "values block" and 64-character digests.
None of this can be typed reliably from paper.

### Scenarios to support

| Dimension | Variants |
| --- | --- |
| Bundle delivery | one DVD per bundle, possibly at different times; many bundles on a USB stick; a lab network share; `scp` from a laptop |
| Server access | console only; SSH from a laptop in the closed network |
| Manual | printed; PDF on another machine without copy/paste; copy/paste (not the default assumption) |
| Tool provisioning | organisation has an internal package repository; it does not; only supplier media |
| Security baseline | SELinux Enforcing and fapolicyd as today; possibly stricter local rules |
| Task | first installation; adding a component later; updating one app; a new server |
| People | separate administrator and runtime user; one person with both accounts |
| Credentials | files from the supplier; the organisation's PKI; PEM or PFX |

### Requirements for the manual and the tools

1. Every command can be typed from paper without error: short, few options, no
   pipes, line continuations, quoting or long paths in the ordinary flow.
2. Tools ask for missing values with a suggested default (runtime account, port,
   public address, which found bundles to publish) and accept the same values
   as options for automation and tests.
3. Sensible defaults: product from the bundles, bundles from the current or
   mounted directory, port 8443.
4. The operator compares, never types, digests and key fingerprints: tools print
   them in groups of four characters and ask for confirmation.
5. The same flow for every delivery medium: mount or copy, then one command.
6. One command per role, repeated after a stop or interruption until it reports
   success.
7. Errors in one or two lines: what is wrong and what to do now; no tracebacks,
   no reference to another document for ordinary remedies.
8. Account switches that work at a console: log out and log in as the runtime
   user (a real login session). `su -` and `sudo -iu` do not start the user's
   systemd session and must not appear in the manual.
9. A measurable limit on commands and typed characters per task, checked in the
   AI walkthrough and the human trial (item 68).

### Questions to answer in the lab before choosing a design

Recipe and results: [latest results](acceptance/RESULTS.md), run on
2026-10-25 on OL9.8 with the default fapolicyd policy. Findings:

- Untrusted shell scripts run for everyone (rule `allow perm=any all :
  ftype=text/x-shellscript`), and root may run untrusted Python. Only non-root
  opening of untrusted Python is denied. fapolicyd does not protect a delivered
  `setup.sh`; authenticity must come from a signature check.
- RPM-installed files are trusted through `trust = rpmdb` without extra rules.
- `dnf install ./file.rpm` does not check signatures by default
  (`localpkg_gpgcheck = 0`); `rpm -K` prints `digests OK` for an unsigned file,
  so the manual must require the words `signatures OK` or the host must enable
  `localpkg_gpgcheck`.
- `sudo -iu` gives no user session; `machinectl` needs `systemd-container`
  (not installed); `ssh <runtime>@localhost` and a console login both give a
  real session with working `systemctl --user` and user journal.

The questions below are answered there; they are kept for reference.

**Policy variation (product owner, 2026-10-25).** The lab host has the default,
permissive OL9 policy. Customers may have stricter fapolicyd settings, and the
design must not depend on rules that a site can remove, nor ask a site to relax
its policy. Variants to support or refuse clearly:

| Setting | Lab default | Stricter variant | Affects |
| --- | --- | --- | --- |
| Rule 12 (shell scripts allowed for all) | present | removed | any delivered script run from media |
| Rules 1/2 (root may open/run anything) | present | removed | root running untrusted Python/scripts |
| `trust` | `rpmdb,file` | `rpmdb` only | today's release publication, which enrolls releases in the `file` trust database for the runtime user's Python |
| `integrity` | `none` | `sha256` or `ima` | today's release helper accepts `none`, `size` and `sha256` (`scripts/release.py`); runtime verification of the others is outstanding |
| Mount options | default | `noexec` on `/var/tmp` or media | executing from upload/media |

Design principles: build only on `trust = rpmdb` and on no other permissive
rule; detect the actual policy in preflight and name what is missing and who
must act, never change it; document one explicit supported policy range and
refuse anything outside it before changes. Add a lab profile with
`trust = rpmdb`, `integrity = sha256` and rules 1, 2 and 12 removed, and repeat
the recipe there before choosing a design; RPM delivery is the only option
expected to work under every variant.

**RPM prototype (2026-10-25).** At the product owner's request a lab prototype
wraps built bundles as signed, side-by-side-versioned RPMs plus a
`<product>-host-setup` command: [latest results](acceptance/RESULTS.md)
(`rpm-prototype/`). Run once on the lab on 2026-10-25 (network on, default
policy): install, upgrade and `dnf remove` worked with trust from rpmdb only
and no FANOTIFY/AVC denials; the administrator's part was typeable from
paper, the runtime user's part was not (see the results). Strict profile not
tested. No product code changes; no automated regression coverage.

- Does the default OL9 fapolicyd policy deny `bash setup.sh` for an untrusted
  shell script on DVD/USB or in the upload directory? (For Python this was
  observed in the item 54 lab runs; for shell it is not verified.)
- Is a tool installed from an RPM trusted and runnable under the default policy
  and the `integrity = none` baseline, without extra rules?
- How does OL9 verify the signature of a local RPM file (`rpm -K`, `dnf install
  ./file.rpm` with `localpkg_gpgcheck`), and what does the operator see?
- Does `sudo machinectl shell <runtime>@` give the runtime user a real session
  (user manager, `XDG_RUNTIME_DIR`, `journalctl --user`) so one person can
  switch roles without logging out at the console?

### Chosen direction (product owner, 2026-10-25)

Decided after the [RPM prototype run](acceptance/RESULTS.md),
which showed that RPM delivery works with the default fapolicyd policy (trust
from rpmdb only, no denials) and makes the administrator's part typeable from
paper, but leaves the runtime user's part (about 3 700 characters of pasted
shell) unchanged. The product owner also stated that long guided sessions on
the closed lab are not feasible.

- **Delivery:** every release and the administrator tool are signed RPMs.
  The main scenario is a **standalone server on a very restricted network**
  without a package repository. A delivery is a directory of files (RPMs,
  public key) that may arrive on USB, DVD, a network
  share or by `scp`; nothing is executed from it, so `noexec` mounts do not
  matter, and an incomplete copy fails the signature/checksum checks before
  changes. An organisation's internal package repository must keep working
  with the same RPMs but is not a separate feature.
- **Administrator:** on a new server, once, with OS tools only (supplier code
  must not run before the key is checked): compare `gpg --show-keys` with the
  fingerprint on paper, verify the tools package against that key alone, and
  install it.
  Trust stays bound to the product's own key (product owner, 2026-10-25): a
  signature from another imported RPM key never authorizes this product. After that, every installation, upgrade and
  retirement is **one command**, `sudo <product>-admin [delivery directory]`:
  it verifies and installs what is new, prepares the host (asking for the
  account and port the first time), retires old releases only when they are
  not needed (plain `dnf remove` of product packages is refused), and says
  what the runtime user does next.
- **Runtime user:** logs in directly (console or SSH), then **one command**,
  `<product>`: it detects the state, asks only for missing values with
  defaults (public address; the port comes from the administrator), takes
  credentials from a private incoming directory, installs the delivered
  releases in dependency order, runs the health checks and prints status. A
  repeat continues after interruption; an upgrade asks nothing unless a new
  release needs a new setting or credential. No values
  block and no shell blocks in the manual.
- **Preflight stops** before changes for anything the host must already have
  (OS packages from the OS media, by name; `subj_cache_size`; journald), and
  says who acts.
- **`release.py` flow:** phased out before the first customer installation;
  one supported flow, one manual.
- **Verification:** the acceptance harness runs exactly the paper commands
  (review guide section 7), including the strict fapolicyd profile above,
  first installation, upgrade, retirement and interruption/retry. Manual lab
  sessions are limited to one short paper/human trial (item 68).

### Phasing decision (product owner, 2026-10-26)

For now the bundles are delivered as RPMs **without signatures**: the RPMs are
placed in a fixed location on the server and installed with `dnf`. Signing must
be supported later, possibly in about two years. **Signing and every challenge
that comes with it are deferred, not removed.** Nothing in "Chosen direction",
the plan or the WP0 evidence about signatures is deleted or weakened in text; it
becomes phase 2.

- **Phase 1 (now):** unsigned release and tools RPMs, installed with `dnf` from
  the fixed location; trust in fapolicyd from the RPM database (WP0 probes A,
  B, E: unaffected by signing); host preparation, runtime command, retirement,
  lock and repair as planned where they do not depend on signatures.
- **Phase 2 (deferred, unchanged scope):** product-key-bound signature
  verification, the paper fingerprint and key bootstrap, isolated keyring
  checks, signature predicates in the manual, and the WP0 signature evidence
  (probes C1, C2 and the signature part of D). Rerun those probes when phase 2
  starts; the 2026-10-25 evidence is historical by then.
- **Phase 1 must not make phase 2 harder:** keep package names, file layout and
  versions as planned; keep the build able to sign (`rpm --addsign` stays in the
  pipeline, just not required); keep a clear place in the administrator flow
  where the signature check will go; do not bake "no signature" assumptions into
  code or file formats; anything that turns signature checking off (for example
  `gpgcheck=0` in a repository file) is one explicit, documented setting.
- **Temporary security exception, documented in the review guide:** without
  signatures, whoever can place an RPM in the fixed location and get the
  administrator to install it gets code run as root and trusted by fapolicyd.
  Interim protection: a root-owned location, delivery on trusted media, release
  RPMs with no scriptlets that change the host. The exception ends with phase 2.
- **`release.py`:** stays until phase 1 replaces it; its signed flow is not
  carried into phase 1 and returns as phase 2 design, not as code to keep.
- **Installing RPMs requires root (2026-10-26).** `dnf install`, `dnf upgrade`,
  `dnf remove` and `rpm -i/-e` write the RPM database and system directories and
  refuse to run without superuser privileges; an ordinary account can only
  query (`rpm -q`, `rpm -qi`, `rpm -ql`, `dnf list installed`, `dnf info`).
  Installing, upgrading and removing product RPMs is therefore always an
  **administrator** task with sudo; the runtime user never installs packages and
  keeps no sudo. Workarounds that would let the runtime user install (a sudoers
  rule for `dnf`, polkit/PackageKit `pkcon install-local`) conflict with the
  no-sudo requirement and are not used. The manual's prerequisites must say
  that someone with root access is needed for every delivery; if the person on
  site has no sudo, nothing can be installed. To confirm on a lab host as an
  ordinary user: `dnf install -y /tmp/missing.rpm` must report the superuser
  error, and `sudo -l` must show `not allowed` for the runtime account.
- **Open decisions for phase 1:** (1) the fixed location: a local repository
  (`repodata/` plus a `.repo` file, `dnf install <name>`) or a plain directory
  (`dnf install /path/*.rpm`); (2) whether the administrator installs with
  plain `sudo dnf` or through the administrator command (either way it is the
  administrator, see above). (2) decides whether WP0 probes F (removal guard)
  and H (stop on a release installed outside the administrator command) remain
  phase 1 requirements. Consequences, to inform the decisions (not decided):
  - (1) Local repository: shorter commands from paper (`dnf install <name>`)
    and one explicit, documented signature-check setting in the `.repo` file,
    as the phase rules ask; but the build must produce `repodata/` and the
    administrator must place a `.repo` file once. Plain directory: no
    repository metadata and nothing to place, but longer commands with a path
    and glob, and the signature-check setting goes on each command line
    (`--setopt`) or into `dnf.conf`.
  - (2) Administrator command: one command per role (requirement 6), and the
    retirement guard, selection checks and trust poll stay in one place, so F
    and H remain phase 1 requirements. Plain `sudo dnf`: fewer tools to build
    in phase 1, but the administrator types dnf options and file names, and
    the 2026-10-25 decision "a conservative guard also for plain `dnf remove`"
    must then hold through package scriptlets alone (F); H would not apply.
  - Both choices keep phase 2 possible; neither changes package names, file
    layout or versions.

Implementation plan: [RPM-DELIVERY-PLAN.md](docs/RPM-DELIVERY-PLAN.md),
revision 3.3; the WP0 matrix passed at `3222efb` after an earlier attempt that
stopped before any probe ([report](acceptance/RESULTS.md)); not implemented. Product-owner
decisions recorded there: trust bound to the product key, immutable versions,
and a conservative guard also for plain `dnf remove`. Work package 0 is an
investigation with explicit go/no-go criteria.

Open points for the design: how answers are given non-interactively for the
harness; dependency order and version selection when several releases are
installed; the retirement guard; how credentials of the organisation's PKI or
PFX fit the credential-folder prompt; package naming for side-by-side versions
(no automatic `dnf upgrade`); disk space (images are stored uncompressed);
supplier signing key management; console-only and one-person use; whether the
strict profile holds.

### Design options considered before the decision

- Trusted tool delivery: a signed RPM installed once (`rpm --import` with a
  fingerprint compared against paper, `rpm -K`, `dnf install`), so the
  per-delivery command is `sudo <product>-setup`; or a short verified copy into
  a protected path; the current stdin bootstrap stays only for automation.
- An interactive `setup` front end over the existing authenticated `release.py`
  operations, with the same trust boundaries.
- Runtime `install-set` (item 66) with prompts or default locations for settings
  and credentials instead of options.
- Larger and not decided: shipping the bundles themselves as RPMs so `rpm` and
  fapolicyd's RPM trust replace parts of the custom publication; assess image
  size, upgrade and retention before considering it.

Deliverables: lab findings for the questions above, a chosen design recorded in
a plan document, then changes to 65/66 and a printed-manual human trial under
item 68 (console-only and SSH variants, one person with both accounts).

### Command-line parsing and operator logging

Split out on 2026-10-28 into
[item 73](#73-parse-command-lines-with-argparse-subcommands) (argparse
subcommands) and [item 74](#74-one-operator-message-convention-and-python-logging)
(message convention and Python `logging`), so they can be done before the RPM
work. The new `<product>-admin` and `<product>` commands of WP2/WP3 use both
from their first version.
[Item 75](#75-make-python-lifecycle-code-easier-to-follow-diagnose-and-change) is
limited to incremental lifecycle readability/testability; coordinate any shared
path interfaces with this RPM work rather than redesigning either command flow.

## 66. Install sets: several signed bundles through one entry point

Status: planned, high priority (2026-10-23), after item 65. Implementation
plan: [INSTALL-SET-PLAN.md](docs/INSTALL-SET-PLAN.md), revised 2026-10-24 with
the product owner: no supplier set manifest (bundles arrive one per DVD or many
per USB stick); `install-set` installs the newest published version of every
published component; publication is the selection; no rollback (needs a
database restore, backlog 3). Where the text below says manifest, the plan
supersedes it. Requested by the
operator after the manual backlog 64 run: put e.g. platform, identity and app1
in one directory and have one `install.sh` install them all.

Shape to investigate: an install set directory with an explicit manifest
(product, components, versions) and the signed bundles with `.asc`/`.sha256`.
Bundles stay separate component releases (each has its own `bundle.yaml`,
`VERSION`, `deploy.sh` and modules), so never unpack them on top of each other.
The administrator part authenticates and publishes every listed bundle (item
65); the runtime account then runs one command that, in declared dependency
order, runs `init-config` where needed, stops for required operator edits or
credentials with a clear message, and runs `validate`/`install` per component.

Contracts: install only what the manifest lists (not every archive that happens
to be present); keep independent component versions; keep existing config and
credentials; offline only; a rerun after interruption continues without
restarting finished components needlessly; the runtime account needs no sudo.
Coordinate with item 60 (CLI name) and the per-component lifecycle; do not add a
second deployment engine. New command-line options follow
[item 73](#73-parse-command-lines-with-argparse-subcommands) (argparse subcommands, no hand-written `sys.argv`
conditions). Tests: dependency order, partial failure and retry,
manifest/bundle mismatch, and a real OL9 run.

Apply the [mandatory operator review](docs/REVIEW_GUIDE.md#7-mandatory-operator-and-procedure-understanding-review)
to the complete multi-bundle task. One manual must show how to supply/select the
install set, run 65's administrator preparation, log in through SSH without sudo,
provide required public config/credentials, and invoke the runtime installation
command. Give exact continuation commands when it stops for input or fails after
one component. Do not make the operator infer dependency order, choose internal
helpers or display sensitive values to diagnose a stop.

The automated scenario must use those same public commands and manual steps for
first installation, unchanged rerun and partial-failure continuation in a fresh
SSH session, asserting retained config/credentials and no unnecessary restart of
completed components. No harness loop over lower-level component commands may
stand in for the documented install-set entry point. Reuse 65/67's preparation
and SSH path, with drift tests for the manual-command mapping.

Document an AI walkthrough and a separate unassisted human trial of the whole
install set, including command/edit counts, elapsed time, errors, stops and
explanations requested. Both assessments of the future install-set procedure
remain outstanding; existing per-component tests/manual runs do not prove them.
The [current operator baseline](acceptance/OPERATOR-REVIEW.md) records the gaps.

## 67. Acceptance scenario with a real ssh login as the runtime account

Status: planned, high priority (2026-10-23). Item 65 now supplies a focused
manual-matched setup/initial-install SSH path; this item must extend it through
logout/reboot/upgrade/retirement and retention assertions. Its real lab execution
and human usability evidence are still pending. The ordinary automated matrix runs runtime
commands through the administrator's `sudo -u`; it passed while a real login
could not read its user journal on a fresh host (manual backlog 64 run).

Add a harness scenario that creates a runtime account without sudo (and asserts
`sudo -l -U` denies it), installs a lab-only ssh key for it, and runs every
runtime step over `ssh <account>@prod` without setting `XDG_*` or other login
environment: bootstrap file, `init-config`, credentials, `validate`/`install`,
`systemctl --user`, `journalctl --user` (must show the service's entries),
HTTPS including the identity discovery endpoint, logout, reboot before login,
a fresh login with the same checks, upgrade with state comparison and `retire`.
Start from a host without `/var/log/journal` so the journal contract chosen in
item 65 is verified. Do not grant `systemd-journal`/`adm` or sudo to make it
pass. Drive the commands from `docs/PRODUCTION-INSTALL.md` or a tested explicit
mapping from its step IDs; fail harness tests when command, account, prerequisites
or order drift. Remove the lab key in cleanup.

Exercise the exact manual bootstrap/preparation command from 65 and the runtime
flow from 66 when available. Cover first execution on a fresh host, successful
repeat, and interrupted preparation/installation followed by a new SSH session
and the documented continuation command. Do not pre-create journals, product
directories, pinned keys, manager drop-ins or the runtime bootstrap file through
private harness logic. VM reset, artifact delivery and the disposable SSH key
are test infrastructure; any supplied OS/account baseline must match the stated
manual prerequisites. Missing prerequisites must exercise documented diagnosis
and remedy, not an invisible harness fix.

Apply the [mandatory operator review](docs/REVIEW_GUIDE.md#7-mandatory-operator-and-procedure-understanding-review)
separately from harness/code review. Record an AI literal walkthrough of the
tested manual and a separate limited-Linux-experience human trial on a fresh
host, without oral help. Record time, errors, stops, command/edit counts and
explanations needed; assisted tasks require a new unassisted trial after fixes.
The human trial is outstanding, and the [current AI baseline](acceptance/OPERATOR-REVIEW.md)
has findings. A green SSH acceptance scenario proves execution of that path,
not that the manual is easy to understand; report these outcomes separately.

## 10. Supplement test coverage before structural changes

Status: implemented at `511099e`; the test baseline runs in every lab run
(`03-unit`). The historical 0.2.0 upgrade lab run was never done and is tracked
in item 5. Item 8 proceeded with explicit user authorization.
See [test baseline and lab command](acceptance/RESULTS.md) for coverage,
results and the retained 0.2.0 upgrade gate. The original task is preserved below.
This task includes the retained 0.2.0 upgrade scenario already tracked in item 5;
implement it once and cross-reference its evidence rather than duplicating it.

Supplement test coverage in `gunstein/podman_offline` before the planned deploy-code refactor.

The goal is to establish a clear, tested baseline for existing behaviour. This is a bounded testing task, not the refactor itself.

### 1. Map existing coverage and run the baseline

Read the current code, tests and verification reports. In particular, check:

- `tests/`
- `acceptance/`
- `deploy.py`
- `bundle.py`
- Root commands and bundle contents.

Run existing product and acceptance-harness tests before changes. Record the commit and results.

Reuse existing fixtures and test tools. Do not duplicate tests already covering the requirements below.

### 2. Test a real upgrade from 0.2.0

Add a focused acceptance scenario upgrading an actual 0.2.0 installation to the current version.

Use an identified historical commit for old code and images. Do not simulate an old release by changing only `VERSION` in current code.

Scenario:

1. Build and install old app1/core and app2.
2. Create user data through the existing e2e/marker mechanism.
3. Record existing versions, config, credential files, database volumes and relevant service observations.
4. Follow the currently documented manual upgrade steps: add required DB fields and `GENERATED_SECRETS` entries to persistent config.
5. Transfer and install the new app1/core bundle.
6. Verify that app1/core works and old app2 still works without unintended changes.
7. Then upgrade app2 and verify the entire installation.

In particular, check:

- Existing database passwords are retained byte-for-byte.
- Database volumes are retained and existing user data remains available.
- Persistent config changes only through explicit operator steps.
- No credentials are regenerated or database users changed automatically.
- The app1 upgrade does not change app2's service, version, config or credentials.
- Login and database operations work after each upgrade stage.
- Trust for the old release is removed only after successful verification, without affecting sibling bundles.

Also test that missing required config additions are rejected before image operations or installed-state changes. A focused local test may cover this if existing coverage is sufficient.

Keep the scenario bounded. Do not repeat the entire reboot, crash and hang matrix if those cases are already covered separately.

### 3. Establish installation failure behaviour

Review existing coverage and supplement it for:

- Failure during `podman load`.
- Failure or a missing image during `podman image exists`.
- Failure during restart or `is-active` for an affected systemd service.

Use existing component installation as the starting point.

Test relevant observations:

- Persistent config and credentials.
- Import archives.
- Route and OIDC client registrations.
- Quadlet and YAML files.
- Version markers.
- Which services were targeted for restart, and in which order.
- Preservation of unaffected sibling components.

Distinguish failures before and after installation begins changing state. Do not assume installation is atomic or rollback already exists.

For a service failure, describe the actual partial state and check that later steps stop and version markers do not falsely claim a completed installation.

Use concrete failure scenarios rather than tests that merely repeat internal function calls.

If you find an existing bug, document it with a focused reproduction. Do not lock in a known bug as desired behaviour or make unrelated product changes without identifying them.

### 4. Test root commands from another working directory

Add integration tests launching the actual wrapper scripts from a working directory outside the checkout/release:

```text
./deploy.sh prepare
./deploy.sh init-config <component>
./deploy.sh install
./deploy.sh uninstall
./build-bundle.sh
```

Use the wrapper's absolute path in the test.

Test commands in the appropriate context:

- `prepare` and bundling from source.
- `init-config`, `install` and `uninstall` from an unpacked bundle.

Verify that resource paths and config selection work independently of the caller's working directory, and that output is not accidentally written there.

Use isolated temporary directories and existing Podman/systemd stubs where appropriate. Do not run production commands against the developer's actual home or container environment.

Where realistic testing requires a service account, user home and systemd runtime, put the check in the existing authorised lab scenario rather than building a complicated new mock framework.

### 5. Scope

Do not implement:

- Extraction into the `deployment/` package.
- A new CLI architecture.
- Directory trust for fapolicyd.
- Password rotation.
- Automatic config or database migration.
- A new rollback mechanism.

Tests for the future package structure, `python -B`, bytecode exclusion and directory trust belong to the refactoring task.

Retain existing security checks and test assertions. Do not weaken them to make new scenarios pass.

### 6. Verification

After changes, run:

- All product tests.
- All acceptance-harness tests.
- Relevant ruff, format, pyright, vermin and shellcheck checks using the project's existing setup.

Retain Python 3.6 compatibility for host tools and product tests.

Run the new real upgrade scenario if the established lab is available and execution is authorised. Do not reset or change other environments.

Clearly distinguish local tests, harness tests and actual target-host runs. If a lab run is unavailable, implement the scenario and report that the upgrade remains operationally unverified.

### 7. Delivery

Briefly report:

1. Baseline commit and test results before changes.
2. Coverage that already existed.
3. New tests and the concrete failures they guard against.
4. Historical and new revisions used in the upgrade scenario.
5. Test results, including actual lab execution.
6. Any product bugs found and verification gaps.
7. Whether the baseline is sufficient to begin refactoring.

Update relevant test documentation with guarantees and limitations.

Prefer a few strong tests over many overlapping tests.

## 2. PostgreSQL password rotation

Status: planned; separate from the deploy refactor.

- Define an explicit operator-controlled procedure coordinating the database role
  password, persistent secret file and running clients for core/app1/app2.
- Use the existing ownership, file paths, Secret keys and volume mapping in
  [README.md](README.md#postgresql-configuration-and-credentials).
- After an explicit password change, re-render Secret templates and recreate
  client containers; changing a source file or restarting systemd alone is not
  database-role rotation. Preserve the `newer-only` render policy.
- Define failure handling and verification before selecting a mechanism. Verify
  authentication after rotation and retention of database data.
- Keep session keys, demo-user passwords, OIDC keys and certificates outside this
  database-specific procedure. Never rotate implicitly during install or upgrade.

## 3. Database backup and credential recovery procedures

Status: planned; separate from password rotation.

- Document and exercise coordinated backup/restore of database volumes and their
  persistent password files, including private permissions.
- Define an explicit recovery procedure for missing credentials or a mismatched
  database password, with operator prerequisites and authentication checks.
- Preserve refusal to generate a replacement password when database state exists.
  Do not delete/reinitialize volumes or assume that changing the secret file
  changes the PostgreSQL role password.
- Keep credentials and connection strings out of logs and acceptance evidence.

## 5. Close documented runtime verification gaps

Status: planned verification work; current evidence remains unchanged.
The retained 0.2.0 upgrade scenario below is implemented as part of item 10;
run the [focused lab scenario](acceptance/RESULTS.md)
and cross-reference its evidence here rather than implementing it again.

- Run a full retained 0.2.0 → 0.2.1 upgrade with the documented manual DB config
  additions, verifying existing credentials, volumes and sibling state.
  Prioritize this before upgrading an important retained installation. Start with
  the old release's real config, initialized database volumes and credentials;
  apply only the documented manual additions, then install the new images and
  verify authentication, CRUD, persistent data and unaffected siblings. Existing
  legacy-password fixtures do not replace this end-to-end upgrade scenario.
- Verify supported Podman versions beyond the currently tested 5.8.2 before
  claiming runtime coverage for them.
- Verify localized PostgreSQL authentication diagnostics, preserving the distinction
  between authentication refusal and DNS/network failures.
- Run host tooling on an actual Python 3.6 interpreter if a suitable environment
  is available; current Python 3.6 compatibility evidence is static.
- Report local/harness checks separately from actual target-machine results.

Source and existing evidence: [latest results](acceptance/RESULTS.md).

## 7. PostgreSQL preflight manifest compatibility

Status: follow up when adding another PostgreSQL image or mount layout.

- Document and test the current assumptions in `database_preflight()`, including
  the `/var/lib/postgresql/data` mount and explicit Secret `items` mapping.
- Before supporting a different layout, ensure the guard identifies its actual
  password source and persistent database volume. Unsupported layouts must fail
  clearly before secret generation or persistent changes.
- Add focused regressions for each newly supported layout. Keep database-state
  checks in the lifecycle layer and avoid a generic PostgreSQL framework.
- Since 0.4.10 a container that mounts `/var/lib/postgresql/data` counts as a
  database container even without any `POSTGRES_PASSWORD*` variable, so
  `PGPASSWORD`, `envFrom` and missing password settings are refused there.

Review source for items 6–7 and the expanded upgrade scenario: static code review
of `improvements-0-2` through `87f4e98`. These are follow-up requirements and
verification gaps, not evidence of completed runtime support.

## 13. Retry-safe install and uninstall

Status: done in 0.4.2. Failure injection is verified in fresh local processes
(`tests/test_retry.py`); on real hosts the normal lifecycle is verified by
the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS), but no failure is injected there. See [retry verification](acceptance/RESULTS.md).
This is a bounded correctness fix for retrying failed operations, not a transaction
framework or module refactor. The full agent message follows, with Markdown
formatting adjusted for this document.

Implement safe retries after installation and uninstallation failures in gunstein/podman_offline.

This task addresses two concrete deploy.py bugs:

1. A retry can skip required Identity/platform restarts after a failed installation.
2. Uninstall can remain incomplete while the next attempt is rejected because the installation marker has already been deleted.

This is a bounded correctness fix. Do not perform the planned module refactor, change component architecture or introduce a general transaction framework.

### 1. Read and understand the existing flow

First read:

- install_components()
- install_component_plan()
- write_registrations()
- registration_stage()
- component_imports()
- uninstall()
- Relevant installation-failure, component and Identity tests.

Function names may have changed. Find the equivalent current-branch code.

The component model is:

- platform owns the proxy and route registrations.
- identity owns IdentityServer and client registrations.
- app1 and app2 depend on platform and identity.
- help depends on platform.

Route and client registrations must remain separate. A route change normally affects platform, while a client change affects identity.

### 2. Installation bug

The current flow writes registrations before all necessary services have restarted.

For example:

1. App1 has a new route and client registration.
2. The installer writes both registrations to persistent state.
3. App1 restart fails.
4. The installer exits before Identity and platform restart.
5. The operator repeats the same installation.
6. Registration files already contain the intended content and are considered unchanged.
7. Identity and platform therefore do not restart.

The second attempt can report success even though running services have not applied the registrations.

A similar failure can occur if writing import archives or restarting a registration owner fails.

Requirement: a retry must complete required work from the previous attempt. Comparing new registrations with files already on disk is insufficient.

### 3. Installation solution

Choose a simple, explicit mechanism to remember incomplete work between processes.

A small persistent pending file is one option. It could record that identity and/or platform registrations have not yet been confirmed applied.

Adapt the filename and format to existing code. Follow these rules:

- Record required work before changes that could hide its necessity.
- Pending state must survive installer exit or process interruption.
- On retry, read pending state and combine it with new changes.
- Rewrite required import archives if the previous attempt did not complete them.
- Restart affected services and check them against existing success criteria.
- Remove pending state only for work actually completed.
- If restart or validation fails, unfinished work must remain recorded.
- A retry with identical registration files must still perform pending work.

Pending state contains only required metadata, never passwords, private keys or complete configurations.

Use existing private-permission and safe-write patterns. Do not follow symlinks to arbitrary locations. Invalid pending state must produce a clear error, not be ignored.

Do not solve this by restarting all services on every install.

Preserve normal behaviour:

- Unchanged registrations without pending work do not restart Identity/platform.
- Route-only changes normally restart platform.
- Client-only changes normally restart identity.
- Both changes restart both.
- Sibling apps must not restart as a side effect.

If choosing an alternative to pending state, cover the same failure cases and explain it clearly.

### 4. Uninstall bug

Current uninstall deletes the installation marker, among other things, before the entire operation completes.

For example:

1. App1 stops.
2. Quadlet/YAML and registrations are deleted.
3. The installation marker is deleted.
4. Identity or platform restart fails.
5. The operator retries uninstall.
6. The installer rejects the attempt because app1 is no longer considered installed.

With --delete-data, volume removal can also fail after the installation marker is gone.

Requirement: the operator can repeat and complete uninstall without manually reconstructing markers, YAML or registrations.

### 5. Uninstall solution

Make partially completed uninstall resumable.

Do not solve this only by moving marker deletion to the end. Previously deleted YAML or other files may still be needed to determine remaining work.

Before destructive steps, validate and retain enough information for the next run to know:

- Which component is being uninstalled.
- Whether --delete-data is included.
- Which services must stop or update.
- Which registration owners must update.
- Which specific volumes, if any, must be deleted.

Use small, explicit state for ongoing uninstall if needed. Do not build a general operation engine.

Follow these requirements:

- Run dependency checks before uninstall starts.
- A component undergoing uninstall must not count as a healthy available dependency for new installations.
- Repeated deletion of files already removed by the same operation must be safe.
- A missing volume on retry can count as already deleted.
- A volume-inspection error remains an error; do not interpret it as absence.
- The volume list must come from validated component-scoped information.
- Do not expand deletion to other components' volumes or state.
- Registration updates and required restarts must be repeatable.
- Mark completion only after every required step succeeds.
- Clean up pending state after completion.

Preserve the distinction between:

- uninstall: retain data, config and credentials.
- uninstall --delete-data: delete only the selected component's relevant data and state.

A retry must not accidentally change a retaining uninstall into a data-deleting uninstall. Define and document handling of conflicting flags. The simplest solution is to require the original selection and clearly reject a mismatch.

### 6. Interaction between installation and uninstallation

Define simple, clear behaviour when a new command encounters unfinished work.

For example:

- install must not ignore an ongoing uninstall of the same component.
- uninstall must not delete or ignore pending registration work in a way that leaves incorrect runtime state.
- An operation must not remove another operation's pending work.

It is acceptable to reject a conflict with a clear message naming the command the operator must complete first.

Do not introduce automatic rollback or automatic repair of unknown state.

### 7. Installation tests

Use existing test infrastructure and fault injection. Add at least these scenarios:

#### A. App restart fails after registration writes

1. Install an app with changed route and client registration.
2. Fail app restart after registration writes.
3. Verify installation fails.
4. Repeat installation without the fault.
5. Verify required import archives update and both Identity and platform restart.
6. Verify pending state is removed after success.

#### B. A registration owner fails

1. Fail Identity/platform restart or its subsequent check.
2. Repeat installation.
3. Verify unfinished work runs even with identical registration files.

#### C. Import archive write fails

1. Fail a required import archive write after registration writes.
2. Repeat installation.
3. Verify the import archive actually updates before completion is acknowledged.

#### D. Normal installation remains scoped

Continue checking all four combinations:

- No registration change.
- Route-only change.
- Client-only change.
- Both changes.

Without pending work, no additional shared services should restart.

### 8. Uninstall tests

Add at least these scenarios:

#### A. Registration-owner restart fails

1. Begin uninstalling an installed app.
2. Fail Identity or platform restart.
3. Repeat uninstall.
4. Verify completion even though some files are already deleted.
5. Verify registrations are removed from updated import archives.
6. Verify pending-state cleanup.

#### B. Volume deletion fails

1. Begin uninstall --delete-data with several component volumes.
2. Fail deletion of a later volume after an earlier volume is removed.
3. Repeat the same command.
4. Verify already deleted volumes are handled and remaining work completes.
5. Verify other components' state is unchanged.

#### C. Uninstall without data deletion

A failed attempt and retry must preserve config/credential bytes and database volumes.

#### D. Conflicts and invalid state

Test:

- Retry with a conflicting --delete-data selection.
- Installation while the same component is being uninstalled.
- A new installation depending on a component being uninstalled.
- Invalid or symlinked pending state.

Retry tests must represent a new process: the solution must not depend on variables from the first attempt. Use the same persistent test directory but reset temporary state between attempts.

### 9. Scope and compatibility

Preserve:

- Existing root commands.
- Python 3.6 compatibility for deploy code.
- Bundle dependencies and version rules.
- Checksums and offline installation.
- Existing secret generation and credential paths.
- SELinux and fapolicyd checks.
- Component isolation and persistent data.

Do not:

- Move deploy into a Python package as part of this task.
- Add password rotation.
- Regenerate credentials on retry.
- Introduce migration logic.
- Change normal service restarts beyond what the fix requires.
- Put pending state in the release directory or offline bundle.

### 10. Documentation, checks and report

Briefly document how the operator retries failed install/uninstall and how conflicts are reported.

Run:

- Product tests.
- Acceptance-harness tests.
- ruff.
- Format checks.
- pyright.
- vermin.
- shellcheck.

Add real acceptance scenarios only where they provide necessary coverage beyond focused fault-injection tests. Do not claim stubbed tests prove actual Podman/systemd behaviour.

Report:

1. Causes of the two bugs.
2. How unfinished work is stored and completed on retry.
3. Files changed.
4. New failure scenarios covered by tests.
5. Actual test results and checks that could not run.
6. Limitations.

Prefer small, clear functions and explicit steps. A moderately experienced Python developer should readily understand why retry is safe.

## 22. One scoped mutation-testing round for the riskiest deployment decisions

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its section on
assessing evidence, including the tests themselves.

Status: planned, narrowed on 2026-10-17. One bounded round, not a permanent
tool or gate. Do after items 29 and 31.

### Background

The suites pass, but passing tests do not show that they would detect a wrong
decision. The independent review of item 21 found tests that could not fail
(four tests patched a function install never calls) and a retry test that
accepted any owner set. Code and tests were largely written by the same
agent, so they may share blind spots. Mutation testing finds such gaps
systematically: it changes the code in small ways (a `<` becomes `<=`, a
condition is negated, a call is removed) and reports which changes no test
detects.

A full run is not worth it here: about 3000 lines of product code and an
80-second suite give thousands of mutants and hours of run time, many
survivors are uninteresting (message text), and a permanent threshold adds
maintenance for a moderately experienced developer. Mutation results say
nothing about real Podman, systemd or fapolicyd; the lab runs do.

### Scope

Only these decisions, where an undetected change does the most harm:

- `registrations.registration_stage` and `registrations.registration_changes`
  (which registrations are removed, which owners restart)
- the pending record in `registrations.py`: `save_pending`, `load_pending`,
  `check_pending`, `acknowledge_owner`, `apply_registration_updates`
- `deploy.database_preflight` and `deploy.postgres_binding`
- `deploy.uninstall_plan`
- catalog validation in `catalog.load_catalog`, `catalog.role_owners` and
  `catalog.dependency_order`

Exclude everything else, including demo applications, the acceptance harness,
rendering helpers and logging or message text.

### Task

1. Pick one maintained Python mutation tool that can restrict mutation to the
   functions above and run only the tests that cover each mutant (for example
   mutmut or cosmic-ray). Give the reason. Install it only for this round, in
   a virtual environment or with `pipx run`; do not add it to the product or
   to the bundles. Host Python 3.6 compatibility is unchanged.
2. Use the existing product tests as the kill criterion. Stay offline, with no
   Podman, systemd or network calls; keep the existing stubs. Target a run of
   at most about an hour.
3. Classify each survivor: missing test, equivalent mutant (one-line
   justification) or code that can be simplified.
4. Add focused regression tests for the survivors that matter. Assert the
   exact arguments and state transitions, not just the exit status. Do not
   change production behavior only to kill a mutant; simplifying dead or
   redundant code is allowed when the review guide's contracts hold.
5. Document one command in `tests/README.md` that reruns the round before a
   large change to these functions. No automatic gate or threshold.

### Verification and delivery

Run the product tests, acceptance-harness tests, ruff, format, pyright, vermin,
shellcheck and `git diff --check` as usual. Report the tool and version, the
command, mutants killed and surviving per function before and after, the
tests added, the remaining survivors with their classification, and the run
time.

## 24. Optional disaster recovery (DR), adapted from podman_test

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: planned; large. Requested 2026-10-17. Requires a separate analysis and
an agreed plan before any implementation. Analysis and a proposed agent plan
were prepared on 2026-10-18: [DR implementation plan](docs/DR-IMPLEMENTATION-PLAN.md).
Read that document in full; it adds the code reuse analysis, runtime ownership
design, declaration proposals, failure/retry contracts, delivery gates and
acceptance scenarios. It is not implementation approval or runtime evidence.
Once agreed, its detailed delivery sequence supersedes the outline below.
Builds on items 20 (declarative components) and 21; recheck the current baseline.
Coordinate with items 2 (password rotation), 3 (backup and credential recovery)
and 7 (PostgreSQL layouts). Backup/recovery must remain usable without standby,
even if its implementation is delivered by this optional operations package.

### Source of the existing implementation

`gunstein/podman_test`, branch `feature/platform` (checked 2026-10-17 at
`5171197`), has a working DR design with a clean acceptance record:

- `deploy/dr/app_ops`: `python3 -m app_ops`, one command per DR operation, run
  from a controller over plain SSH (`BatchMode=yes`, pinned host keys,
  `sudo -n`), driven by a small YAML inventory of `primary`/`standby` hosts.
- `deploy/dr/app_dr_host`: building blocks staged on each host: streaming
  replication and its TLS, secret export/import between hosts, standby reseed,
  promoted application deploy and pair checks.
- `deploy/dr/scripts/app_dr.py` (fencing-gated promotion) and `app_backup.py`
  (physical base backup, WAL archive and point-in-time restore into disposable
  containers), plus systemd timers for a scheduled DR check and nightly backup.
- Commands such as `preflight-standby`, `bootstrap-standby`,
  `replication-status`, `failover --confirm-primary-fenced ...
  --confirm-promotion ...`, `deploy-promoted-application`, `configure-backup`
  and `rebuild-standby --confirm-fenced ... --confirm-reseed ...`.
- Boundaries: DR imports the single-host installer, never the reverse
  (`tests/test_dr_boundary.py`); every operation acts on one complete group of
  replicated databases and refuses a partial group; destructive steps need
  explicit confirmations; runbooks in `docs/runbooks/`.

### Differences to resolve in podman_offline

- The reference already derives its replicated group from its declared
  `Platform`/apps model, but has its own naming, database and Identity conventions.
  Here components and databases must follow this product's model (item 20),
  without copying a second `Platform` model. The replicated set must come from declarations,
  for example an optional per-component DR declaration, and be recorded in
  installed metadata so the target knows it without the source checkout.
- Each component is a separate offline bundle with its own version and
  dependency checks; podman_test promotes one product bundle.
- Credentials here are files delivered as kube Secret YAML from component
  config directories, not `podman secret` objects; secret transfer to a
  standby must keep the credential-retention and logging contracts.
- Host constraints: Python 3.6 with PyYAML, no Jinja2, rootless user systemd,
  SELinux, fapolicyd trust per bundle, strictly offline targets.
- Existing safety guards must stay intact: database preflight, retry/pending
  state, scoped uninstall and `--delete-data`.

### DR must be optional

A single-host installation without DR must keep working exactly as today,
with no new requirement, service, timer, port or package. DR is enabled
explicitly, for example as a separate operations bundle and explicit
commands. Component bundles must not depend on DR code, and the deploy
package must never import DR code (add a boundary test). Disabling DR or
never enabling it must not leave active replication resources or orphaned
timers behind. Enablement after ordinary installation must retain existing data
and credentials. Disablement must restore ordinary deployment ownership and
remove owned replication slots/endpoints and DR timers, while retaining backup
history and standby data by default. Retained resources must be inventoried;
purging them requires a separate explicit destructive operation. A separately
enabled backup feature may retain its own archive and timer. Do not silently
delete recovery history to satisfy cleanup; see the plan's disablement contract.

### Phase 1: analysis and plan (deliver before implementing)

1. Read podman_test `feature/platform`: `deploy/dr/`, the installer's
   `backup.py`, `docs/runbooks/`, `docs/manual-recipes/03-DR-TWO-VM.md`,
   `04-BACKUP-PITR.md` and the acceptance record. List what can be reused
   unchanged, what must be adapted and what does not apply.
2. Propose a scope for the first delivery, for example: replication of
   declared PostgreSQL components to one standby, fencing-gated promotion,
   backup/PITR, and standby rebuild, with the rest deferred.
3. Propose the declaration schema, installed metadata, the operations
   package layout, the inventory format and the command list.
4. Describe the failure and retry model of every destructive step, and how
   each of the guide's contracts is preserved.
5. Plan the tests: unit tests with stubbed transport, harness tests, and the
   real two-VM acceptance scenarios with exact commands.
6. Get the user's approval of the plan before phase 2.

### Phase 2: implementation

- Develop on a separate branch, for example `feature/dr`, branched from
  `main` after item 20 has been merged.
- Deliver in reviewable steps that each keep the tests green: declarations
  and metadata, then replication, then promotion and fencing, then
  backup/PITR, then standby rebuild.
- Use a pull request to `main`. Open it as a draft early so the plan, the
  phased commits and the CI results are reviewed in one place; mark it ready
  only when the agreed scope, the tests and the real two-VM acceptance are
  complete. A pull request fits here because the change is large, touches
  safety-critical paths and needs review before it reaches `main`.

### Verification and delivery

Run product tests, acceptance-harness tests, ruff, format, pyright, vermin,
shellcheck and `git diff --check`. Add runnable real two-VM acceptance
scenarios (replication, fenced failover, promoted application access,
backup/PITR restore and standby rebuild) and document them even if no lab is
available; report unexecuted runtime scenarios as outstanding. Never count
podman_test's acceptance results as evidence for this repository.

## 30. Make the acceptance runs much faster

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: step 1 done in 0.4.10, on the operator's decision (2026-10-17): every
liveness probe now uses initialDelaySeconds 10, periodSeconds 10, timeoutSeconds
5 and failureThreshold 6 (was 90/30/5/3), without a startupProbe. Measured on
`a688c30`: each health wait about 11 s (was 92), the hang test 100 s (was 199),
app1-first 25 min (was 44), identity-only 14 min (was 22), renamed 20 min
(was 32). Step 2 done on `main`: bundles are written with gzip level 6
instead of 9 (measured locally on 3 GB of binaries: 150 s instead of 484 s,
archives 0.6 % larger), and `./build-bundle.sh <component>` builds only the
named bundles; the app1 upgrade and the inventory release without registrations
now build only that bundle. Measured in `speed-app1-first` on `bbce76d`
(CLEAN PASS): `04-bundle` 107 s (was 263), `10-build-upgrade` 32 s (was 269),
`10-identity-build` 43 s (was 94); transfer 52 s (was 47). app1-first now takes
about 17 min (44 min before step 1, 25 min after it). Steps 3–4 are optional;
weigh them against the rule that each clean run builds from source.
Raised by the operator on 2026-10-17: the item 21 matrix (six scenarios) took
several hours, which is far too long.

### Where the time goes

Measured from the step tables of the item 20 runs on `8e62153`:

| Run | Total | Health waits (85–115 s steps) | Bundle builds (~263 s each) | Everything else |
| --- | ---: | ---: | ---: | ---: |
| `decl-app1-first-3` | 44 min | 15 steps, 24 min | 2 builds, 9 min | 11 min, including the 200 s hang test |
| `decl-renamed-4` | 27 min | 9 steps, 14 min | 2 builds, 9 min | 4 min |
| `decl-help-2` | 12 min | 2 steps, 3 min | 1 build, 4 min | 4 min |

1. **Health waits are more than half of every run.** Every container has
   `initialDelaySeconds: 90` and `periodSeconds: 30`, so after any install,
   start, restart, reboot or upgrade, `healthy` cannot pass in less than about
   90 seconds, even when everything is up in five. The hang test (200 s) is
   also derived from these numbers.
2. **Bundle builds take about 4.5 minutes each.** `build-bundle.sh` builds all
   five bundles, and `bundle.py` writes them with `tarfile` `w:gz`, which is
   single-threaded gzip at level 9. The upgrade steps rebuild every bundle to
   change one.
3. **The six scenarios repeat the same work.** Each one resets both VMs and
   rebuilds images, runs the unit suite and builds bundles from the same
   revision.

### Task

Measure first, on the lab VMs, then change in this order. Stop once the full
matrix is comfortably under an hour.

1. **Health timing (product decision, largest gain).** Check on Podman 5.8.2
   what `kube play` does with `startupProbe` and with a shorter
   `initialDelaySeconds`: when the status becomes `healthy`, and how a hung
   container is detected. Then propose one of these to the operator, with
   measured times:
   - a `startupProbe` with a short period and a generous total budget (slow
     first starts such as Identity and PostgreSQL initialization keep their
     time), plus a liveness probe without a long initial delay
   - or a shorter `initialDelaySeconds` and period

   This changes the documented product contract (README "Health checks and
   acceptance", `tests/test_health.py`, the VM checklist and the hang-test
   limit), so it needs the operator's approval before it changes.
2. **Bundle builds.** Time `podman save` against compression separately. Then
   consider a lower gzip level or a faster compressor available on the build
   host, and building only the changed component in the upgrade steps. The
   archive format and checksums must stay the same for the target.
3. **Repeated work across scenarios.** Consider a matrix mode that builds
   images, the unit suite and bundles once per revision and reuses them,
   checked by hash, in each scenario. This conflicts with the current rule
   that every clean run builds from source, so weigh it last and keep single
   scenarios unchanged.
4. Record before and after times per scenario in the acceptance README, and
   keep every check that exists today. Speed must not come from dropping
   evidence.

## 35. Run demo apps with a database role that is not a superuser

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md).

Status: planned. Found by the best-practice review at `689156b` (finding 1,
CONFIRMED). Matters if the demo apps or their manifests are used in production.

The official PostgreSQL image creates `POSTGRES_USER` as a superuser, and the
demo backends (app1, app2, Identity) connect with that same user
(`components/*/manifests/40-postgres.yaml`, `60-todo.yaml`). A compromised web
application thus has administrator rights in its database instance.

Separate administration and migration from normal operation: the init/schema
step uses the superuser; the application gets its own role with only the
rights it needs and its own password (a second generated secret). Adapt the
database preflight, which today assumes one password shared by server and
client, and item 7 (PostgreSQL layouts). Document the pattern for products in
docs/COMPONENTS.md. Lab run required (fresh install and upgrade with retained
volumes, which must keep working: existing databases need the role created by
an idempotent init step).

## 36. Harden the demo application containers

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md).

Status: planned. Found by the best-practice review at `689156b` (finding 3).

`apps/todo-backend/Containerfile` and `apps/identity/Containerfile` set no
`USER`; the manifests set no `securityContext` and no CPU/memory limits.
Rootless Podman already means container root is not host root, but the apps can
be confined further: a non-root container user, `allowPrivilegeEscalation:
false`, dropped capabilities, `readOnlyRootFilesystem` where the app allows it
(with explicit writable mounts), and realistic resource limits.

Do it together with the secret file modes: signing keys and other mounted
secrets are 0400 for container UID 0 today, so changing the user alone breaks
startup. Use only fields Podman 5.8.2 `kube play` supports (for example
`runAsUser`, `capabilities`, `readOnlyRootFilesystem`; not `runAsNonRoot`,
`fsGroup`, `readinessProbe`, `startupProbe`), and add manifest validation for
fields Podman would silently ignore if that proves necessary. Lab run required.

## 37. Document and protect credential copies at rest

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md).

Status: planned. Found by the best-practice review at `689156b` (finding 4,
a deliberate limitation today). Coordinate with items 2, 3 and 24.

Private files are written 0600 from the first byte and existing credentials are
kept, but nothing is encrypted at rest: source credentials, the rendered YAML
(base64 Secrets, not encryption) and Podman's Secret volumes all hold the
values, and removed keys can remain in volumes. `SECRET_TEMPLATES` adds composed
values to the same YAML/Podman stores; there is no separate derived credential
file to back up. Config recipes plus original passwords reconstruct them. An
item 44 PFX is another copy of a signing key at rest; its password does not
protect against anyone who can read both the PFX and the password file. The
organisation's Identity image has the PFX password hardcoded as "password", so
the PFX encryption gives no real protection there; file modes, Secret delivery
and backups protect the key. A production CA key on the target (item 45) is
another copy of key material that needs the same care. Identity stores Data
Protection keys with `PersistKeysToFileSystem` (apps/identity/Program.cs)
without key encryption.

Document every copy of each credential (where, who can read it, how it is
backed up, rotated and removed), and offer an encrypted backup procedure and an
explicit at-rest protection choice for the Identity keys (for example a
certificate) that an organisation can apply offline. No online secret service
is required.

## 39. Show the installed components and versions on the target

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: implemented with local product and harness checks (2026-10-24), on
`feature/39-component-status`, based on CLI rename commit `88f3110`.
`./deploy.sh status [--json]` reports installed versions and unit states in
recorded dependency order, incomplete installs/upgrades/reinstalls and pending work;
it reads `/var/lib/<product>/state` without config/credential reads or writes.
Review follow-up: the existing pending record now covers the full install attempt,
including same-version reinstalls without owners, until the completion-marker
write succeeds. Fresh-process install/failure/status/retry regression coverage
preserves the previous completed version and the `newer-only` skip policy.
The fix is committed as `bd0cc77`. The coverage follow-up demonstrates the test
failing against `b46d548` and adds an opt-in `--status-retry` acceptance probe,
including actual container consumption after retry. The 2026-10-24 six-scenario
matrix is CLEAN PASS, including the probe in all five applicable scenarios.
[Verification and understandability review](acceptance/RESULTS.md).
Current-change real Podman/systemd verification is recorded with exact revisions,
477 verified step logs and the non-blocking fapolicyd counter observation in that
report. Python 3.6 runtime and the separate 65–67 operator work remain outstanding.
The original request (2026-10-19) and task follow.

### Problem

The target already records everything: `installed/<id>` holds the completed
version, `metadata/<id>.json` the installed descriptor (product, version,
dependencies, roles), and `pending-operation.json` unfinished work. But there is
no command that shows it; an operator has to read private files in the service
home by hand, for example
`sudo -u <user> sh -c 'cd /var/lib/<user>/installed && grep -H . *'`.

### Task

1. Add `./deploy.sh status`, run as the service user from any unpacked bundle of
   the product (the bundle only supplies the code; status reads the installation's
   `state/` directory). Output, one line per installed component in dependency order:
   component, installed version, unit name and `systemctl --user is-active`
   state; then the product name and any pending operation (operation,
   component, owners). Show an unfinished first install (metadata without
   marker) explicitly.
2. Read-only: no writes, no pending record, no Podman calls beyond reading
   unit state; it must work while another component's install is pending and
   when a unit is failed. Refuse a bundle of another product the same way
   install does, or print the installed product and say the bundle differs.
3. Optional `--json` with the same fields for collection by other tools.
4. Exit 0 when everything listed is installed and active, non-zero otherwise,
   so scripts can use it as a check.
5. Tests: several components with different versions, an unfinished install,
   a pending operation, a failed unit, an empty home; the harness runs it on
   PROD after installs and checks the versions it expects. Document it in
   README (operations) and COMPONENTS (installed state).

## 42. Explain client registration and import volumes in the architecture diagrams

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: planned; requested by the operator on 2026-10-19. Documentation only.

### Problem

The install sequence diagram in ARCHITECTURE.md shows registration staging,
materialization, import archives and owner restarts, but does not explain how
an application's client.yaml becomes files in Identity's /clients mount. It is
also unclear why identity-clients needs no VOLUME_FILES entry in config.defaults.yaml.

### Task

1. Add a focused sequence diagram and supporting text in ARCHITECTURE.md for
   public client registration delivery. Keep the main install diagram readable;
   link it to this detail rather than expanding every internal call there.
2. Trace client.yaml and the public certificate through client_registration(),
   registration_stage() (client.json, client.crt and installed.json),
   component_imports(), materialize()/volume_claims() and write_file_archives().
   Explain the PVC import annotation and Podman's import of the archive when
   Quadlet starts the service, ending with Identity reading /clients at startup.
3. Show that bundles.yaml accepts.clients selects the volume name, using
   identity-clients as an example, not a hardcoded platform requirement. Explain
   how this differs from an ordinary data PVC and operator-declared VOLUME_FILES.
4. Cover an app install/update while Identity is already installed:
   write_changed_owner_imports() rebuilds the owner's archive and
   restart_component_services() restarts the affected owner when registration
   data changes. Distinguish durable host registrations from temporary staging,
   import archives and the container mount; private client keys stay with apps.
5. Check every arrow against current code, validate Mermaid syntax and any
   rendered diagram artifacts using the existing documentation workflow, and
   run git diff --check. Do not change runtime code or configuration contracts.
6. Cover the failure, retry and removal path, as the route/client trace in
   docs/REVIEW_GUIDE.md section 3 requires (declaration -> planned change ->
   pending state -> persistent registration -> import -> owner restart/check ->
   acknowledgement). Show that registration_changes() decides the owners and
   save_pending() records pending-operation.json before registrations and import
   archives are written; what a new process does after a failed Identity restart
   or health check; and that removing client.yaml (backlog 21) rebuilds the
   owner's archive and restarts it.
7. Routes use the same mechanism: accepts.routes (platform-routes) receives
   route.conf from components with routes:. State this in one or two sentences,
   or mark it explicitly out of scope, so clients do not read as a special case.
8. Name the actual durable locations below the service user's home: persistent
   registrations, import archives in FILES_DIR and the pending record. Say which
   of them are rebuilt from registrations and which an operator must keep, so
   item 3 (backup and recovery) can refer to this text.
9. Runtime claims need evidence. deployment/common.py says Podman imports the
   archives "on every start"; cite existing lab evidence for that and for the
   annotation's behaviour on an existing volume, or mark the statement as
   unverified. Do not describe Podman behaviour that no evidence covers.
10. dev/render-diagrams.sh renders a fixed list of diagrams selected by
    ARCHITECTURE.md headings. Add the new diagram to that list, commit its PNG in
    docs/diagrams/ and link it beside the existing install/build images. If
    rendering is not possible in the agent's environment, say so and leave the
    exact command; do not commit a stale or hand-made image.

Done when a reader can follow the source declarations to the running Identity
container and explain who builds the files, who imports the volume and why no
config.defaults.yaml entry is needed. This task does not establish new runtime
verification evidence or close the outstanding lab work in other items.

## 44. Generate optional PFX signing credentials in dev and production

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: implemented (2026-10-19). Matrix `t6-*` on `b3f3cf1` was CLEAN PASS,
but no acceptance step runs the signing/PFX mode; it shows only that the shared
CA path and the demo recipes still work. Verification of the signing mode on a
lab host, of the organisation's external Duende image and of its mount path is
still pending. Do not close this
item until that evidence is recorded. The missing /run/secrets/signing-cert.pfx
reported by the operator motivated the explicit signing mode; the shipped demo
keeps PEM and its existing commands.

`dev/generate-certificates.sh --root DIR --component ID --purpose signing --pfx`
now provisions any valid component ID without demo users or manual directory
moves. The same standalone/stdin invocation supports dev and production roots.
Private password-file validation precedes writes; external PFX/PEM wins over
issuance; exports are verified in private scratch and hard-linked without
clobbering existing files. Only an explicitly declared PFX is delivered through
existing Secrets. No deployment/ code, image, bundle schema or CA renewal is
changed. The helper embeds Python 3.6-compatible code to keep stdin execution
self-contained; existing PEM/CA recipes remain separate for backward compatibility.
See [PFX credentials](docs/PFX-CREDENTIALS.md) for input names, password creation,
Secret/mount examples, failure recovery and the runnable external-image check.

Understandability review: password/path/mode checks -> per-root lock ->
provision (existing PFX, PEM, or issuance) -> verify_pfx -> publish. On an export
failure, temporary files and the lock are removed, existing PEM/password remain,
and retry reuses them. Uncatchable interruptions can leave a stale lock or
partial PEM pair; recovery is explicit, never automatic key replacement.
Deployment still loads a single binary source -> Opaque Secret in 0600 YAML ->
explicit secret.items mapping. Actual UID/HOME/mount and .NET loading remain
organisation-specific runtime checks, not established by local tests.

Local verification (2026-10-19, Python 3.12.14/OpenSSL 3.0.13): final full
product rerun collected 410 tests: 407 passed, 3 GnuPG tests explicitly skipped
only in the invocation after the ordinary run confirmed missing `/tmp` setup
errors. The ordinary run also had two failures in unchanged retry tests; both
passed separately and in the final full rerun (cause not established). After the
last SIGTERM-cleanup change, all 43 certificate/template tests passed, including
16 certificate tests with real OpenSSL. All 195 acceptance-harness tests passed.
Ruff check/format, Pyright (0 errors/warnings), ShellCheck, shell syntax, relative
Markdown links and diff checks pass. Extracted embedded Python was included in
lint/type/static Python 3.6 gates; Python 3.6 was not executed. Real .NET,
Podman/systemd, service-user mount access, SELinux/fapolicyd and OpenSSL 1.1.1
remain unverified for this change; historical lab results are not reused.

### Analysis and recommended scope

Baseline before implementation: dev/generate-certificates.sh issued PEM .crt/.key
pairs, preserves existing complete pairs, refuses partial pairs, and sets umask
077. Its component mode accepts fixed demo names; Identity's branch also creates
demo user passwords. It did not export PKCS#12/PFX. The shipped Identity reads
PEM, so its successful operation does not verify an external PFX-consuming image.
SECRET_FILES can already deliver a PFX as ordinary binary file data; no new
Secret type, renderer, template syntax or deploy lifecycle is needed.

Recommended: add a small, explicit opt-in PFX export to the dev provisioning
helper, reusing retained PEM material. Do not switch the demo to PFX or require
PFX for all Identity servers/apps. This belongs to development credential
provisioning; production continues to accept externally supplied certificates.
Do not add automatic certificate issuance to prepare/install or validation.

Not yet confirmed: the external application's PFX password setting, its required
password policy, UID/file access and exact mount configuration. The reported
file path establishes only that the file is missing; it does not establish that
the resulting certificate or password will be accepted. Resolve these inputs
before implementing the application-specific example. Do not infer them from
the demo's Program.cs or add changes to the external C# image as a prerequisite.

### Task

1. Add an opt-in export step after successful signing PEM issuance/reuse. Use
   OpenSSL's PKCS#12 export and verify compatibility with supported developer
   OpenSSL versions and the consuming .NET runtime. Keep existing invocations,
   PEM paths and certificate identities unchanged when PFX is not requested.
2. Accept an explicit private password-file input; do not put the password in a
   command-line argument, source file or logs. Prefer this bounded file interface
   over an additional interactive/configuration system. Document how the same
   password is supplied through existing Secret delivery to the application's
   actual configuration setting. No silent password generation/change or fallback
   to an empty password; make any supported empty-password mode an explicit,
   separately justified development choice.
3. Support the target component/output path explicitly so my-identity can receive
   signing-cert.pfx directly without generating in identity/ and copying files.
   Keep issuance purpose separate from the chosen component name; do not add a
   hardcoded my-identity branch or rename the demo globally. Choose the smallest
   backward-compatible CLI extension, with validated paths, not a new general
   certificate configuration framework. PFX export must not implicitly create
   demo users for an external application.
4. Preserve existing credentials byte-for-byte on repeated runs. Produce new PFX
   files with mode 0600 under private directories (0700), and prevent publishing
   partially written exports or overwriting an existing output. Verify an
   existing PFX can be opened with the supplied password and corresponds to the
   source certificate/key before reporting success; refuse empty, corrupt,
   mismatched or symlinked outputs safely. Never regenerate signing keys or
   replace an existing PFX/password automatically to repair an error. A missing
   PFX may be regenerated from the retained PEM pair and password; concurrent
   invocations/failure cleanup must preserve existing files.
5. Document a complete example: generation, SECRET_FILES source, explicit
   secret.items key/path, password delivery and a mount that exposes
   /run/secrets/signing-cert.pfx. Check existing /run/secrets mounts so the new
   mount does not hide other credentials. Avoid delivering extra PEM private
   keys or the CA private key when only PFX is needed. Document that PFX passwords
   do not replace host file protection or remove at-rest credential copies.
6. Keep the original dev CA/certificate workflow, offline operation, and host
   Python compatibility intact. No changes to generic deployment modules,
   Duende configuration models, rotation, automatic trust installation or
   production PKI integration belong in this task.

### Operator decisions (2026-10-19)

These decisions replace the dev-only scope and the open password question above.

- **Dev and production.** Production usually issues credentials from the
  organisation's own PKI in the same way as dev; an external certificate must be
  able to override that, though rarely. The same invocation works in both.
  Production keeps using the current script until item 45 makes it a supported
  production tool.
- **Precedence (external files always win).** In the component's
  `credentials/signing/`, the script takes the first case that applies:
  1. `signing-cert.pfx` exists (external or earlier): keep it unchanged; verify
     only that it opens with the password and contains a private key, and, when
     a PEM key/certificate is also present, that they match.
  2. Only a PEM key and certificate exist (external or earlier): export the PFX
     from them.
  3. Nothing exists: issue a key and certificate from the configured CA, then
     export the PFX.
  Overriding means placing files before running the same command; there is no
  separate mode or flag for it.
- **Password.** The organisation's image has the PFX password hardcoded as
  "password" and cannot be changed. The password is read from
  `credentials/signing/pfx-password` (outside git, mode 0600, retained like other
  credentials) in both dev (`build/dev/<component>/`) and production
  (`/var/lib/<product>/<component>/`). It is created once per machine as part of
  credential provisioning. It is not stored in `config/dev.yaml` or any config
  file, and the script has no built-in default password. Missing or invalid
  password files fail clearly.
- **No password delivery to the container.** The application already knows the
  password, so only the PFX is mounted; no `secretKeyRef` or extra Secret file.
- **Delivery.** `SECRET_FILES` in `components/<id>/config.defaults.yaml` points to
  `credentials/signing/...` relative to the component directory, so the same
  entry works in dev and production.
- **Mount path, still to confirm.** The operator believes a subdirectory such as
  `/run/secrets/signing/signing-cert.pfx` is configurable. Confirm whether the
  application's PFX path is also hardcoded. If it is, mount a Secret volume with
  only that key at `/run/secrets`, verify in the lab that nothing else is needed
  there and that host `mounts.conf` entries do not conflict.
- Document that the hardcoded password gives no real protection (item 37).

### Operator findings (2026-10-20)

From the organisation's old docker-compose test file for `identity-server`:

- The only secret is `signing-cert` (host file `./cert/signing-cert-for-test-pfx`)
  with `target: signing-cert.pfx`, so the application reads
  `/run/secrets/signing-cert.pfx`. No other secret has to share `/run/secrets`.
  Whether the path is hardcoded or only a default is still unknown; the compose
  file sets no path in `environment`.
- The secret has `uid: '999'`, `gid: '999'`, `mode: 0400` and the service has no
  `user:`, so the image runs as a non-root container user (expected 999).
- Decision: the requirement is that it works and is secure enough, not a copy
  of compose. Keep the application's non-root user and mount the PFX-only Secret
  at `/run/secrets` with `defaultMode: 0444`. `kube play` has no per-file owner
  or `fsGroup` for Secret volumes, so the earlier `0400` (container root) example
  would be unreadable for UID 999. `0444` is readable only inside this single-app
  container; host protection (service user's private storage) is unchanged, and
  the hardcoded password already makes host file access the real boundary. Do not
  use `runAsUser: 0`. [docs/PFX-CREDENTIALS.md](docs/PFX-CREDENTIALS.md) is updated.
- Lab evidence still required: `id` in the container shows the non-root user,
  `stat` of the mounted file shows its owner/mode, the host `mounts.conf` does not
  conflict, and the application starts, loads the key and issues a real token.
  Readability alone is not proof. Until then the mode choice is unverified.

### Review additions (2026-10-19)

Decisions and facts from the review of this item; they refine the task above.

- **Export command.** Use `openssl pkcs12 -export ... -passout file:<path>
  -keypbe AES-256-CBC -certpbe AES-256-CBC -macalg sha256`. OpenSSL 1.1.1 and
  3.x have different defaults (3DES/RC2 versus AES/PBKDF2); explicit algorithms
  give the same format on every supported developer host. Do not use `-legacy`.
  `file:` keeps the password out of argv and reads only the first line, so the
  password file must hold a single line; refuse anything else. Checked locally
  with OpenSSL 3.0.13: the certificate fingerprint inside the PFX matched the
  PEM, a wrong password gave exit 1 and `umask 077` produced mode 0600.
- **Re-export is not byte-identical.** Exporting the same key and password
  twice gives different bytes (random salt and IV). "Byte-for-byte" retention
  applies to an existing PFX; a regenerated PFX is only equivalent. It changes
  the rendered YAML, so it reaches the container through the normal upgrade
  path; an equal `newer-only` version does not apply it. Document this.
- **Verifying an existing PFX.** Open it with `-passin file:`, compare the
  certificate's SHA-256 fingerprint with the PEM certificate, and compare the
  public key with the PEM key (`openssl pkey -pubout`). Any mismatch, wrong
  password or unreadable file refuses without changing files.
- **Atomic, no-clobber publish.** Write the export to a temporary file in the
  target directory, publish it with `ln` (fails if the target exists) and remove
  the temporary file; a `trap` removes it on failure. Do not use `mv`, which
  overwrites, or rely on `mv -n`, whose behaviour differs between versions.
- **Purpose versus component name.** `generate-certificates.sh` accepts only
  `platform|identity|app1|app2|help`, and the purpose (signing, web, client)
  follows the name. `acceptance/remote.sh` (`demo_credentials`) works around this
  for the renamed product by moving directories. Add the explicit component and
  purpose without changing that workaround in this item; note a possible
  simplification in the backlog. Validate the component name with the deploy ID
  rule (`common.ID`) so it cannot form an unexpected path. `dev/demo-credentials.sh`
  keeps its demo list; the organisation's component calls the script directly.
- **Stdin execution on targets.** The script also runs as the product user via
  `bash -s -- --root DIR ... < generate-certificates.sh` in the lab and on
  targets. Password and PFX paths are relative to `--root` and must not depend
  on the source checkout.
- **No silent skips.** `tests/test_certificates.py` uses `skipUnless(openssl)`.
  Item 43 requires a missing requirement to fail clearly. Treat OpenSSL as a
  required tool for these tests, at least in the lab's `03-unit` step, and do
  not add new tests that skip silently.
- **.NET verification.** Verify with the organisation's image that the app
  loads the PFX with its private key and the supplied password, as the app's
  UID, from a read-only mount, with the container's actual `HOME` (.NET may try
  to write key material; relates to item 36). Record this under pending real
  evidence; it cannot be verified in this repository.

### Tests and completion

Extend tests/test_certificates.py using the existing isolated fixtures and real
OpenSSL where available: opt-in export, default PEM behavior unchanged, target
component/output name independent of identity, PFX certificate/private-key
readability, password-file handling, repeat-run byte retention, permissions,
missing/partial inputs, incorrect password, corrupt/mismatched existing output,
symlink refusal, interrupted export and redacted diagnostics. Add focused
Secret-delivery coverage for binary PFX and the declared file mapping if existing
coverage does not already establish it; do not add application names to generic
platform assertions. Update the relevant dev/PKI instructions and harness tests
only where their invocations change. Coordinate test placement with item 43.

Run the applicable product and harness gates and inspect the end-to-end flow.
Provide a runnable dev verification for the external app (or a clearly scoped
PFX-loading container fixture) checking the exact mount and password consumption;
record actual runtime results separately from certificate/unit tests. The user
must verify their external Identity image, which is not available in this repo.
Done when one documented provisioning invocation places a valid, retained PFX
at the configured component path and the unchanged application can consume it
through existing Secrets, without manual copying or exposed passwords.

## 45. Production PKI from the certificate provisioning tool

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: planned; requested by the operator on 2026-10-19 and split into 45a,
45b and 45c the same day. Production usually issues certificates from the
organisation's own PKI in the same way as dev, with external certificates as a
rare override (item 44's precedence rules). Each part is a separate task with
its own verification; do them in order.

### Problem

`dev/generate-certificates.sh` is a demo tool: the CA is "Demo Development CA",
certificates last 365 days, the script is not in bundles, and README/ARCHITECTURE
state that organisations bring their own certificates. The lab runs it on PROD
only as demo provisioning (`demo_credentials` in `acceptance/remote.sh`).

### 45a. Configurable production CA (small; after item 44)

Status: done and lab-verified: six-scenario matrix `t6-*` CLEAN PASS on `b3f3cf1` (2026-10-19; Oracle Linux 9.8, rootless Podman 5.8.2, SELinux Enforcing, fapolicyd on PROD). The demo recipes in every
scenario create and reuse the CA through the shared `ensure_ca()` path with
default settings; explicit CA options are covered by product tests only.
Earlier status: implemented on main (2026-10-19).
Prefix options `--ca-subject`, `--ca-days` and `--cert-days` are checked before
writes. All modes share `ensure_ca()` in the stdin-compatible embedded tool;
existing CA/credentials remain authoritative when settings change. Five new
real-OpenSSL regressions cover settings/retention/invalid input and relative roots
across explicit signing and both demo recipes. The 16 existing certificate tests
and all five new tests have passed locally with OpenSSL 3.0.13. Python 3.6 and
OpenSSL 1.1.1 execution, real Duende/Podman/systemd, delivery (45b) and renewal
(45c) remain unverified or separate work; old lab runs are not evidence here.

Review follow-up (2026-10-19): explicit --ca-subject conflicting with a retained
CA is refused before new credentials, including repeated PFX calls and demo
modes. Omitted subject keeps reuse; explicit --ca-days reports that it affects
only new CAs. Partial-pair messages now distinguish backup restoration from
confirmed unused orphans after interrupted first issuance; no automatic deletion.
Independent review's green product/harness runs apply to the reviewed revision;
focused verification of this follow-up is recorded separately below.

Follow-up verification (2026-10-19): all 21 platform/demo certificate tests
passed together with real local OpenSSL after the final fixes. They cover
subject mismatch through stdin and the demo entry point, same-subject reuse,
omitted-subject reuse, CA-days notice, private-file retention and partial-pair
recovery messages. The documented Ruff lint/format commands, explicit DTZ007
check, scoped Pyright (zero errors/warnings), ShellCheck, bash syntax, diff
check and static Python 3.6 compatibility passed. Full product/harness suites
were not rerun for this follow-up; independent review's earlier green runs
are recorded under items 40/43. No lab, .NET, Python 3.6 or OpenSSL 1.1.1 run.

Understandability follow-up: check_retained_ca_subject owns the public DN
comparison and runs in the existing preflight before writes. ensure_ca repeats
the subject check before using a CA; provision/publish keep credential ownership
and no-clobber semantics. Mismatch fails without new credentials; retry with
the retained subject or without the option reuses existing material. The larger
embedded-tool/demo issuance consolidation is explicitly assigned to 45b.

Already true and to be kept: the CA lives in `<root>/PKI/private/`, and `--root`
differs per environment (`build/dev` in dev, `/var/lib/<product>` on targets), so
dev and production already have separate CAs. An existing complete CA is kept
and a partial one is refused. Demo component names select issued certificates
only (item 44), not the CA.

1. Make the CA subject and lifetime configurable. Today `/CN=Demo Development CA`
   and `-days 3650` are duplicated across provisioning modes; consolidate
   CA creation while preserving standalone/stdin execution. Keep the current
   values as the demo default.
2. Make the issued certificate lifetime configurable (currently hardcoded `-days 365`
   across provisioning modes).
3. Validate values before any file is written (subject syntax, positive integer
   days); invalid values fail without creating or changing files.
4. Tests in `tests/platform_tests/test_certificates.py` and
   `tests/demo_tests/test_certificates_demo.py` with real OpenSSL: the configured
   subject and lifetimes are used for a new CA and certificates; an existing CA
   is never modified or recreated when settings change; invalid values write
   nothing; existing invocations without settings behave as before.
5. Document where the CA key lives (mode 0600, `PKI/private/`), that it must be
   backed up and protected (items 3 and 37), and that new settings apply only to
   CAs created afterwards. Replacing an existing CA means reissuing every
   certificate and distributing the new CA; that is a separate operation and
   not part of 45a.

Keep the current stdin delivery; no deploy, bundle or lab-scenario changes.

### 45b. Delivery to targets (medium)

1. Deliver the tool in a supported way, for example signed inside the platform
   bundle (item 38) or as a signed tool archive, that works with fapolicyd and
   offline execution; no network or package installs.
2. Update the lab to use the delivered tool instead of copying the script, and
   remove the renamed-product directory workaround in `demo_credentials` if the
   tool supports arbitrary component names (item 44).
3. Keep demo provisioning available for the shipped demo without making demo
   names part of the production tool.

4. Resolve the understandability finding from the 2026-10-19 review: when the
   tool is delivered in a bundle, extract the embedded Python into a dedicated
   module and route demo leaf issuance through the same issuance function.
   Preserve supported offline execution and document how standalone/stdin
   delivery is replaced or retained. Avoid three independent issuance paths;
   do not expand the production tool with hardcoded demo names.

### 45c. Renewal and expiry (medium; after item 39)

1. Renew issued certificates before expiry without silently replacing keys or
   the CA; define when renewal is allowed and how consumers (nginx, Identity,
   app clients) pick up the new certificate through the normal upgrade/restart
   path.
2. Report certificate expiry in `./deploy.sh status` (item 39).
3. Test expiry and renewal with short-lived fixtures, and verify on PROD in the
   lab. Plan it well before the first production certificates expire.

### Out of scope

An online CA, ACME, HSM integration, replacing an existing CA, and rotation of
database passwords (item 2).

Done when (all three parts): production installs can issue, retain, renew and
back up their certificates from a documented per-environment CA with the same
tool, external certificates still override it, and the lab verifies the flow on
PROD.


## 47. Refuse unsafe permissions on retained generated secrets

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply credential
retention and validation-before-side-effects; coordinate with item 37.

Status: planned; low-priority hardening. Found by the same 2026-10-19 scan at
`b3f3cf1`. Separate from encryption at rest and backup implementation.

### Finding and evidence

`deployment/render.py:generate_secrets` accepts an existing declared generated
file when it is regular and nonempty, then skips the private-mode creation path.
An isolated call retained a synthetic password with mode 0644 beneath a 0755
credential directory. New generated files already use 0600 and new credential
directories use 0700; this finding concerns retained/restored material only.

This is not proof of disclosure in the normal production layout: the service
home's 0700 blocks other local users. Exposure depends on the complete ancestor
permissions and becomes relevant when credentials are restored or staged under
more accessible directories. Do not report 0644 alone as demonstrated disclosure.

### Task and verification

1. Define and enforce an explicit permission/ownership policy for existing
   files declared with `generate`. At minimum refuse group/other access to
   retained generated secrets; specify accepted private modes and ownership.
   Assess ancestor access and document which checks apply to dev, standalone
   fixtures and production. Preserve bytes and valid existing credentials.
2. Fail with a safe, actionable message before install side effects; do not
   regenerate or rotate the secret, print its contents, or silently repair
   ownership. Keep declaration-only `validate` free of credential-content reads
   and host commands; document where permission checks occur in the lifecycle.
3. Add focused tests for safe reuse, 0644/group-readable retained files, the
   selected ownership policy and restored credential directories. Confirm
   refusal preserves bytes and performs no Podman/systemd calls. Include the
   existing-file branch after a competing create where relevant.
4. Keep public certificates and ordinary non-generated VOLUME_FILES outside a
   blanket private-secret policy. This item adds no backup engine or encryption
   dependency. Run focused product tests and the relevant existing checks.


## 48. Validate public hosts and proxy-header trust

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve declarative
components, independent images, shared public settings, offline delivery and
credential-retention contracts; complete the understandability review.

Status: planned; medium severity, high implementation priority after item 46.
Found in the reverse-proxy security assessment of main at `593de60` on
2026-10-19. Static configuration/source evidence; no demonstrated authentication
bypass or end-to-end exploit. Must be addressed before wider production exposure.

### Finding

The sole server in `components/platform/manifests/20-proxy-config.yaml` has
`server_name _`, which does not reject unexpected Host headers. The shipped
Identity and Todo backend routes pass `$http_host` upstream. Identity's route
sets X-Forwarded-Proto and X-Forwarded-For, but does not clear/replace a supplied
X-Forwarded-Host. Nginx normally forwards other request headers unchanged.

`apps/identity/Program.cs` enables XForwardedHost and clears KnownNetworks and
KnownProxies without an allowed-host restriction. A supplied X-Forwarded-Host
can therefore influence the request host used by the demo middleware. IssuerUri
is pinned to PUBLIC_ORIGIN, but that alone is not proof that every generated URL
or redirect is safe. A private shared container network and absence of host
ports on backend pods do not establish that nginx is their only possible caller.
The organisation's external Identity image has not been inspected or tested.

### Task and verification

1. Derive the permitted public authority from the existing PUBLIC_ORIGIN model;
   reject unexpected Host values before proxying. Merely replacing `_` with a
   configured server_name does not reject requests handled by the default server.
   Define handling of ports, supported IP/IPv6 origins and missing/malformed Host
   without hardcoding demo names. Keep the loopback health probe functional with
   an intentional Host policy; do not add an unrestricted backend bypass.
2. Define the minimal forwarded-header contract for each hop. Clear or replace
   client-controlled X-Forwarded-Host, X-Forwarded-Proto, X-Forwarded-For and other
   forwarded metadata actually consumed by supported apps. Audit all shipped
   routes and the custom-route documentation. Preserve legitimate authentication
   headers, cookies and external-app compatibility.
3. Implement header rules in each relevant location or a shared include used
   there: nginx does not inherit server-level proxy_set_header directives when
   a location declares its own. Add a regression for this inheritance trap.
4. Align the demo Identity middleware with that contract: consume only required
   forwarded fields, restrict accepted hosts and avoid unrestricted proxy trust
   justified solely by private networking. Choose a rootless-compatible trust
   mechanism; do not hardcode transient pod IPs. Document external applications'
   responsibilities and the limits of a shared network/origin trust boundary.
5. Add focused config tests and actual nginx/backend lab probes using synthetic
   Host and forwarded-header values. Check legitimate OIDC discovery/login,
   callback and generated URL authorities; unexpected Host rejection; spoofed
   X-Forwarded-Host and client-IP handling; renamed product; and health checks.
   Verify the real app contract without claiming an unseen external image is
   covered. Current five proxy tests exercise rendering/startup, not this boundary.
6. Run relevant product/harness and static checks. Keep current TLS versions,
   read-only mounts, credential privacy and scoped component lifecycle unchanged.

References:
- [nginx request processing](https://nginx.org/en/docs/http/request_processing.html)
- [nginx proxy header handling and inheritance](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header)
- [ASP.NET Core forwarded headers and allowed hosts](https://learn.microsoft.com/en-us/aspnet/core/host-and-deploy/proxy-load-balancer?view=aspnetcore-8.0)

## 49. Define safe proxy logging for authentication and API requests

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Coordinate with
credential retention and item 37; this is logging protection, not backup work.

Status: planned; medium severity, after item 48. Identified by the 2026-10-19
reverse-proxy assessment at `593de60`. No actual credential leak was reproduced
in the product's nginx container; verify the deployed image/configuration first.

### Finding

Shipped Identity/auth routes disable access_log, which reduces normal-path
exposure. Other routes inherit the image's access-log configuration and have no
explicit safe log format. Nginx's standard combined access format includes the
request line and Referer. Its HTTP error-log context can include the request
line and upstream URL independently of access_log. An upstream failure during a
callback can therefore expose sensitive query parameters despite access_log off.
This does not establish that reusable tokens/passwords have actually leaked or
that logged authorization codes are redeemable without PKCE/client credentials.

### Task and verification

1. Inspect the actual supported stock nginx image's nginx -T output, access/error
   formats and stdout/stderr/journal routing. Reproduce with synthetic markers
   only: normal callback, upstream unavailable/timeout, malformed request and
   API query/Referer cases. Never put real codes, tokens or passwords in evidence.
2. Define useful access logging that excludes sensitive query/Referer fields by
   default, retaining safe path/status/timing information where appropriate.
   Keep the public proxy generic across arbitrary component routes.
3. Handle error logs separately: changing log_format or access_log does not
   sanitize error_log. Choose a practical policy supported by the pinned nginx
   version and delivery model; do not indiscriminately disable all error logging.
   If residual sensitive error context cannot be removed without losing required
   diagnostics, document it and bound log access, retention and export. Do not
   claim unconditional secret-free logs while that exposure remains.
4. Add actual nginx regression scenarios checking synthetic marker presence or
   absence against the chosen policy, including failure paths and inherited
   location configuration. Confirm safe diagnostics remain available. Run the
   relevant product/harness checks and document unexecuted runtime scenarios.

References:
- [nginx access-log formats](https://nginx.org/en/docs/http/ngx_http_log_module.html#log_format)
- [nginx development guide: HTTP error-log request context](https://nginx.org/en/docs/dev/development_guide.html)

## 50. Define configurable production proxy limits and security headers

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve independent
external applications and keep product policy declarative. Coordinate container
user/capability/filesystem hardening with item 36 instead of duplicating it here.

Status: planned; lower-priority production hardening, alongside item 36. Found
in the 2026-10-19 assessment at `593de60`; exposure depends on the real bind
address and surrounding controls. The shipped default binds only 127.0.0.1.

### Scope and boundaries

- The shipped proxy has no configured limit_req or limit_conn policy. The demo
  Identity login has no implemented account lockout/throttling. This is not a
  finding about the organisation's external Identity image. Determine which
  controls that application already provides before duplicating them.
- The proxy has no common HSTS, Referrer-Policy or nosniff policy; the Todo
  backend sets nosniff itself, but the static frontends do not. Existing
  application/framework response headers still need runtime inspection.
- Retain the good defaults: TLS 1.2/1.3, 16k request-body limit, no implicit public
  backend ports, read-only route/config/TLS mounts and private TLS-key delivery.
  Absence of custom timeout directives does not mean nginx has no default timeouts.

### Task and verification

1. Define optional production request/connection limits, especially for login
   and token endpoints. Account for legitimate OIDC flows, clients sharing an IP,
   correct client-IP trust from item 48, and load-test/health traffic. Keep
   per-account brute-force defenses and lockout under the application's control;
   rate limiting alone is not an authentication security guarantee. Avoid a
   hardcoded Identity component/path dependency in generic deployment code.
2. Provide a documented compatible response-header baseline: nosniff and an
   appropriate Referrer-Policy; configurable HSTS for production HTTPS after
   trust/deployment validation. Do not force HSTS preload or includeSubDomains
   onto dev hosts or unrelated services. Evaluate CSP/frame protection per app;
   a blanket policy must not silently break OIDC frames, inline scripts or
   supported external applications. Check nginx header inheritance and error
   responses, not just the successful root page.
3. Add focused configuration tests and runnable lab checks for intended 429
   behavior, legitimate login/client traffic, spoof-resistant limiting, headers
   on representative success/error responses and unchanged health checks. Test
   renamed components and document defaults, overrides and ownership of each
   control. Real limits must be chosen from the product's exposure/load needs.
4. No new WAF, online service, custom proxy image or mandatory security framework
   is required. Run relevant product/harness/static checks and report actual
   nginx/.NET verification separately from template assertions.


## 51. Add an optional Grafana and Loki logging demo

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve declarative
components, independent images, isolated offline bundles, credential retention,
scoped lifecycle and compatibility. Coordinate log privacy with items 37 and 49.

Status: planned; low priority, requested on 2026-10-19. Medium-sized demo
extension, not a prerequisite for core deployment, backup or DR. This task is
planning only; no Grafana/Loki integration or rootless collection is verified.

### First delivery

Add optional self-hosted Grafana OSS and Loki OSS, with a maintained collector
(for example Grafana Alloy), to demonstrate searchable PostgreSQL logs. Start
with errors and slow queries; make full statement logging an explicit diagnostic
choice. Keep ordinary deployment fully usable without the logging components.
Application-wide instrumentation, OIDC login, advanced dashboards, metrics and
traces are separate later scope, not prerequisites for this delivery. Item 52
is the planned metrics follow-up and reuses this Grafana instance.

### Task

1. First prove a minimal collection path from the actual rootless Podman setup:
   determine the log driver, journal/file locations, permissions and restart
   behavior. Compare service-user journal ingestion with a suitably scoped file
   path before choosing the collector configuration. Do not require a rootful
   daemon, expose a writable container-engine socket, or grant access to unrelated
   host/users' logs. Record any required narrowly scoped host preparation.
2. Use existing component/catalog/bundle declarations, stock version-pinned OSS
   images, persistent volumes and config/Secret delivery. Provision Loki as a
   Grafana data source and one useful saved view/dashboard automatically.
   Aim to leave generic deployment Python/Bash unchanged; justify any concrete
   platform gap rather than embedding Grafana/Loki names in deploy code.
3. Define PostgreSQL logging modes declaratively. Default to errors and a
   documented slow-query threshold; provide opt-in full statement logging for
   demo/troubleshooting. Explain that statement logging does not record result
   sets or guarantee an audit trail of every attempted statement. Preserve
   database data/passwords when changing logging settings.
4. Keep SQL text and parameter values out of Loki labels. Use bounded labels
   such as component/database, with SQL in log content or structured metadata.
   Avoid user IDs, request IDs and arbitrary query text as indexed stream labels.
   Document that SQL literals/bind values can disclose personal data or secrets;
   parameter-log suppression does not redact literals written into SQL text.
   Use synthetic data for examples and test evidence. Logging failures must not
   become a prerequisite for the application's database operations.
5. Configure Grafana authentication through existing private credential handling;
   do not enable anonymous public log access or use committed/default passwords.
   Keep Loki ingestion/query endpoints internal unless explicitly secured.
   Integrate the UI with the reverse-proxy contract from item 48; define the
   supported base path or host route and verify it in the browser. OIDC is not
   required in this first delivery.
6. Bound retention/disk use in both local source logs and Loki. Define rotation,
   collector checkpoints, persistence, behavior when Loki is unavailable and
   recovery after restart, plus scoped uninstall/data-retention behavior. Do not
   claim exactly-once/lossless delivery without evidence. Keep database volumes
   and unrelated component state untouched during cleanup.
7. Package all required images, configuration and any required plugins for
   offline installation; prefer built-in functionality without extra plugins.
   Select the OSS editions and record their licences/distribution requirements.
   Ensure operation does not require Grafana Cloud, online plugin downloads or
   update/usage-reporting connectivity. Do not add new host Python dependencies.

### Verification and delivery

Add appropriate product/config tests and runnable real Podman/systemd acceptance
checks: install without logging; enable it; emit synthetic error, slow and opt-in
full-SQL events; find them through Loki/Grafana with correct source labels; check
authentication; restart collector/Loki; verify persistence and bounded retention;
uninstall logging without touching application/database data. Verify the offline
bundle and rootless/SELinux/fapolicyd permissions rather than relying on a Docker
quickstart. Report template/unit, harness and real-runtime evidence separately.
Run relevant existing static checks and complete the understandability review.
Document setup, logging modes, resource requirements, privacy limits and the
optional nature of the demo. Do not introduce a general observability framework.


## 52. Add optional Prometheus metrics after the logging demo

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve declarative
components, independent external images, offline delivery, scoped lifecycle and
rootless/SELinux/fapolicyd compatibility. Build on item 51's optional Grafana UI.

Status: planned; low priority, requested on 2026-10-19. Schedule immediately
following item 51 in the observability work, without blocking core deployment,
backup or DR. No exporter, application instrumentation or real metric collection
has been verified in this repository.

### Scope

Use Prometheus OSS for numeric time series, Loki for logs and the same Grafana
instance for visualization. Demonstrate CPU/memory per container and aggregated
by pod/component, plus backend HTTP request count/rate, duration and errors.
Provide an explicit extension path for GraphQL-specific operation/error metrics.
No Grafana Cloud or paid product is required; record licences for the selected
stock images and exporter. Distributed tracing and a general observability
framework are out of scope.

### Task

1. Prove a collection path on the supported rootless Podman/cgroup setup using a
   maintained Podman exporter (evaluate containers/prometheus-podman-exporter)
   or another narrow source. Verify actual CPU/memory availability, permissions,
   container identity and restart behavior before selecting the delivery model.
   Prefer collection without a container-engine socket where supported. A
   read-only bind mount of a Podman socket does not make its API read-only;
   assess the privileges of the actual interface. Do not enable a rootful daemon,
   privileged collector or access to other service accounts as a shortcut.
2. Add optional declarative Prometheus/exporter components and persistent storage
   using the existing bundle/config model. Reuse Grafana and provision the data
   source plus a small dashboard. Keep scrape/query endpoints internal or
   explicitly authenticated, bound retention/disk usage and support fully
   offline image/config delivery. Avoid new host Python dependencies or hardcoded
   component lists in generic deployment code; justify any needed host integration.
3. Display container CPU rate and memory bytes with stable pod/component labels.
   Define CPU percentage denominators, memory semantics and aggregation clearly;
   handle multiple containers and the infra container without double-counting.
   Do not sum percentages with incompatible denominators or show missing metrics
   as healthy zeroes. Document which measurements are unavailable on a host.
4. Export HTTP metrics from a representative backend using supported application
   instrumentation (for .NET, evaluate built-in HTTP meters/OpenTelemetry), or
   explicit proxy metrics if appropriate. Show requests per second, cumulative
   count, latency and HTTP error rates. Adding Prometheus alone does not
   instrument apps; document exactly what external images must expose and how
   scraping/authentication is configured. Avoid counting the same hop twice.
5. Distinguish HTTP requests to a GraphQL endpoint from GraphQL operation counts
   and execution errors. HTTP 200 does not imply GraphQL success; batching and
   subscriptions also need explicit counting semantics if supported. For detailed
   GraphQL metrics, document/instrument the actual framework or use a focused
   representative fixture; do not add an unrelated GraphQL API to the Todo demo.
   Bound any operation-name labels; never label metrics with raw queries,
   variables, user/request IDs, tokens or other unbounded/sensitive input.
6. Make instrumentation and collection optional. Missing telemetry must not
   prevent application startup, database operations or ordinary install/uninstall.
   Preserve existing data/credentials and item 51's log behavior. Document counter
   resets and sampling gaps; operational monitoring is not an exact billing or
   security-audit ledger.

### Verification and delivery

Add focused product/config tests and runnable lab checks: metrics-disabled
installation; enable collection; apply controlled CPU/memory load and locate the
correct container/pod series; emit synthetic requests and inspect counts/rates,
latency and error classifications; exercise GraphQL HTTP-200 execution errors
where that integration is implemented; restart apps/exporter/Prometheus and
verify identity, reset handling and persistence; uninstall metrics without
removing app data or breaking logging. Verify rootless permissions and actual
Podman/systemd/SELinux/fapolicyd behavior, not only dashboard JSON. Run relevant
harness/static checks, complete the understandability review and report unit,
harness and real-runtime evidence separately. Document integration steps,
resource cost and the remaining external-app instrumentation requirements.


## 53. Upgrade app1 with an actually changed application image

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve isolated
offline bundles, independent images, credential retention, database safety and
scoped lifecycle.

Status: planned; requested on 2026-10-19. A focused extension of the existing
acceptance flow. After item 57, the app1 upgrade changes `components/app1/VERSION`
and reference SQL in an isolated checkout (`acceptance/seed_upgrade.py`), then
rebuilds its bundle using unchanged application images. Extend that builder and
its exact changed-file check when implementing this item. Help and Identity have
separate upgrade scenarios with changed content/code and rebuilt images; they
provide an existing pattern to reuse, but do not prove this app1 path.

### Task

1. Extend the existing app1 upgrade in both full acceptance scenarios (app1-first
   and app2-first), rather than adding another complete VM installation. In an
   isolated build checkout, make a small deterministic change to an observable
   app1 backend response, build a new image with a distinct release tag, update
   the relevant manifest image references and bump `components/app1/VERSION`.
   Do not overwrite published image tags or modify the operator's checkout.
2. Build and transfer only the app1 offline bundle and its required verification
   files to the already installed PROD host. Include the new image in the
   archive; do not preload it on PROD or transfer sibling bundles as a shortcut.
   Keep network image pulls disabled. Reuse the established help/Identity build
   helpers where that keeps the flow simple and avoids duplicate shell logic.
3. After installation, assert both the new backend response through the existing
   public route and the running backend's expected image ID. Bundle version and
   health alone are insufficient evidence that the new application is running.
4. Retain existing E2E and persistence assertions: previously created application
   data remains readable, config/credentials/certificates remain unchanged and
   app1 stays functional. Keep route/client declarations unchanged in this
   scenario, so platform, Identity, app2 and help must retain their running
   processes, versions, state, trust entries and shared network identity using
   the existing sibling checks. App1 itself is expected to restart.
5. Add focused harness regression coverage for the changed-image build/transfer
   wiring and assertions. Demonstrate that the checks reject an old backend
   response or wrong running image; avoid assertions that only repeat a new tag
   string. Update acceptance documentation and keep added build time modest.

### Verification and delivery

Run relevant acceptance-harness and static checks, then the real app1-first and
app2-first scenarios on supported rootless Podman/systemd with SELinux and
fapolicyd. Report harness results separately from real-runtime results; until
those lab runs pass, record the scenario as implemented but unverified. This
item covers a compatible application-image upgrade, not database schema
migration, zero-downtime deployment or automatic rollback. Complete the
understandability review of build, transfer, install and observable evidence.

## 54. Keep root release verification and trust off service-writable paths

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply the
signed-bundle, isolation and fapolicyd contracts to the operator's privileged
release steps; coordinate with items 38 and 46.

Status: implementation delivered on branch `feature/protected-releases`, based on
`a37f4e4`; implementation and local regressions delivered, merged to `main` with
item 64; six-scenario OL9 matrix CLEAN PASS on `5b8ab69`. Open: actual Python 3.6
and a non-baseline integrity strategy.
Coordinated with urgent item 64; not marked resolved. Found in the item 46 review on 2026-10-19. Analysis updated on
2026-10-22 against `07f8d56`: three local reproductions confirm gaps in release
verification/trust wiring. That analysis predates this implementation;
current-change real-host verification remains pending.

Implementation: shared `scripts/release.py` authenticates a protected snapshot,
strictly validates/extracts archives and publishes immutable root-owned releases
under `/opt/<product>/releases`, with protected provenance and exact live
size/SHA256 trust checks. README and the harness share this helper; independently
authenticated bootstrap, service-user config editing, scoped retirement after
health/e2e, resumable retirement cleanup and separate-UID lab probes are documented in
[latest results](acceptance/RESULTS.md). No old-layout migration
or global integrity-policy changes are included. Current dev/lab installations
may be discarded; after the first real customer installation, incompatible
changes require an explicit migration preserving customer data and credentials.
Initial local results (2026-10-22): 50 focused and
234 harness tests passed; isolated platform suite ran 403 tests with 399 passes,
three unchanged gpg-agent fixture failures and one unchanged `/proc/self/fd/0`
error. Static checks and understandability review passed; real OL9 matrix remains
required before resolution. The original analysis and task
below remain the review baseline, not claims of current runtime verification.

Review follow-up (2026-10-23): mandatory production signatures and pinned-key-only
publication; SELinux relabel-compatible device/inode/mtime bindings (ctime excluded);
explicit removal of obsolete service-writable release trust on disposable hosts;
cache-tolerant script inventory test; step-scoped sanitized diagnostics and
`publish-release` harness naming. Migration after the first customer is a future requirement,
not a compatibility framework to implement before the first customer installation.
Follow-up checks: 21 focused tests and 237 harness tests passed (also without
`-B`); isolated platform suite ran 410 tests, with 406 passes and the same three
gpg-agent fixture failures plus one `/proc/self/fd/0` error in this environment.
Scoped Ruff plus Bash/Pyright/Vermin checks passed; the full documented Ruff gate
was not green (correction below). See the dated verification report for
regression scope and understandability recheck. Current-change lab verification
remains pending.

Lint correction and probe hardening (2026-10-23): previous Ruff claims used a
limited rule selection/target version, not the documented full commands. Item 54
files now pass those lint/format settings; full lint still reports 12 findings in
three unchanged item 61 Secret test files. Full formatting passes (134 files).
The lab probe now forces tmp_t on one deployment file and verifies restoration;
the negative signature probe requires a typed gpgv rejection, never any generic
ReleaseError. Current-change lab coverage is still pending. The operator reports
410/410 platform and 237/237 harness passes at `7bb05dd`. Current follow-up
checks: 21 release and 239 harness tests passed; Pyright 0 errors/0 warnings and
Vermin Python 3.6 compatibility passed. Real OL9 verification remains pending.

First supplied real run (2026-10-23): `release54-20261023-055311-app1`
at `7bb05dd` passed component installation/health and the then-current release
safety probe, but was NOT CLEAN at `07-registry-offline`: fapolicyd denied the
unprivileged checksum reader access to extracted `scripts/release.py`. The data
fixture now checks the full inventory from compressed tar streams and extracts
only image data. Regression checks modified/unlisted/missing payload refusal
before Podman loading; current lab rerun and full matrix remain required. See
[the dated verification report](acceptance/RESULTS.md) for exact scope.

Coordination (2026-10-23): [item 64](#64-support-new-rootless-installations-outside-the-login-home)
requires an existing login user and product files under a separate root-owned
`/var/lib/<product>` anchor. Reconcile the final release path with that item;
preserve this item's protected publication/trust boundary and shared helper.
Do not assume product name equals user name or that the installation root is
also the registered user home.

### Problem

The README operator recipe unpacks a release as the service user into
`/var/lib/<product>/releases`, then runs privileged steps on that
service-writable tree: `sudo ... sha256sum -c checksums.sha256` and
`sudo fapolicyd-cli --file add "$release/deployment/"`. A compromised service
account can replace files between the checksum and the trust step (check/use
race), so root may trust content that was never verified. A race is not required:
the account can also change the package and its local checksum list before the
operator starts. Signing the original archive does not authenticate an existing,
service-writable extraction of it.

`prepare_release()` in `acceptance/remote.sh` verifies the incoming archive but
skips extraction when the release directory already exists. Root then reads
that directory's own `checksums.sha256` and registers all files in `deployment/`.
`sha256sum -c` does not reject additional files absent from the list. The current
`wait_trust` derives its expected file set from the live directory and checks
paths and record syntax, without comparing size/hash with authenticated content.

With fapolicyd `integrity = none`, the trust decision has no content-integrity
check. Files must therefore remain protected after enrollment as well as before
it. `sudoedit` of `config.yaml` currently targets root in the README despite the
config living in the service-owned data directory; use service-user authority.
These findings establish a broken verification/trust boundary, not proof of
direct root code execution.

### Analysis and local evidence (2026-10-22)

The actual `prepare_release` and `wait_trust` shell functions were exercised
with disposable files outside the checkout. Hashing, file enumeration and the
archive were real. The signature step was simulated by checking a fixed digest
of the original archive; fapolicyd enrollment/database output and sudo identity
changes were simulated. This tests binding to the authenticated input, not
OpenPGP, separate-UID enforcement or the real daemon.

| Reproduction | Observed result |
| --- | --- |
| Replace a package file and rewrite the extracted checksum list before invoking `prepare_release` | Exit 0; the changed file was passed to simulated trust enrollment while the original archive remained unchanged |
| Add `deployment/extra.py`, absent from both the original archive and its checksum list | Exit 0; the extra file was included in simulated trust enrollment |
| Supply a live trust record with the expected path but arbitrary size and a syntactically valid unrelated hash | `wait_trust` returned success |

Nine existing harness tests for trust waiting, release retry, README parity,
upgrade ordering and retention of old trust on failure passed. Those tests do
not cover the three gaps above. No new real Podman/systemd/SELinux/fapolicyd run
was performed for this analysis; item 46's successful lab matrix does not verify
item 54.

Another boundary to include: the harness's `prepare-host` action checks only
the archive checksum before extracting and running its script as root. Unlike
the README recipe, it does not call `gpgv` there. Require signature verification
before the first privileged execution of bundle code, not only later in
`prepare_release`. Review other archive consumers such as `unpack` and the
separate registry fixture according to whether they execute code or import data.

### Chosen direction and scope

Use a final root-owned release tree outside the service home, for example
`/opt/<product>/releases/<product>-<component>-<version>/`. The service user may
read/traverse it but must not modify files, add entries or replace any ancestor.
Config, credentials, installed metadata, import archives, Quadlets and Podman
storage remain service-owned under `/var/lib/<product>` and its runtime directory.

Root ownership of a `releases` directory under the service-owned home is not
enough: the service user can rename that directory entry and replace it because
it controls the parent. Check the entire trusted anchor chain. A protected
verification copy alone is also insufficient if trust or execution still uses
a different, service-writable final copy. Do not recursively chown an existing
service-owned release tree as the repair mechanism.

The existing production code already separates these paths: `common.ROOT`
locates release inputs, `catalog.component_paths` locates persistent output,
and `install_components` stages under `XDG_RUNTIME_DIR`. The wrapper uses
`python3 -B`. This suggests limited deploy-engine changes, but read-only release
operation must be tested for init-config, validate, install, retry, upgrade and
uninstall, including `component_file` inputs and standalone fixtures. Dev
`prepare` deliberately writes source build output and keeps its existing role.

Prefer one small shared release helper used by the operator recipe and the
acceptance harness. It should own staging, verification, publication and trust
ordering explicitly. Keep the existing deploy lifecycle and pending-operation
model; a second generic transaction framework is unnecessary. Existing
dev/lab installations may currently be discarded: no migration, old-layout
aliases or compatibility layer is required before the first real customer installation. Normal repeated operations and data retention still apply.

### Task

1. Trace every root operation on release and data paths in the README recipe,
   `acceptance/remote.sh` and any helper, and classify which paths the service
   user can write or replace.
2. Implement the protected final layout above, with service-readable files and
   no service write permission through modes or ACLs. Validate product/component
   identifiers, version and all ancestor directories before privileged writes.
   Keep private persistent state out of the release and out of fapolicyd trust.
3. Stage the archive in a fresh protected area, then verify that exact snapshot
   against a separately provisioned trusted keyring. Do not verify one pathname
   and later extract a replaceable copy. Verify the signature before unpacking
   or executing archive-provided setup code. Document how the release helper
   itself is initially obtained and authenticated; an unverified helper cannot
   establish its own trust. Preserve item 46's fapolicyd lesson: opening a new
   untrusted Python helper file can fail before enrollment. Keep bootstrap
   execution compatible with the actual OL9 policy and Python 3.6.
4. Validate archive members before extraction: expected single top directory,
   relative confined paths, no duplicate/ambiguous destinations, symbolic or hard
   links, devices, FIFOs or other special files. Reject unsafe names and metadata;
   establish explicit ownership/modes rather than accepting service-writable or
   privileged modes from the tar. Extract into a new empty protected directory,
   never over an existing release. Validate descriptor identity against the
   requested product/component/version and require an exact authenticated file
   inventory, including refusal of unlisted extra files.
5. Publish the complete verified tree at its final path before enrolling that
   path. Publication must not overwrite an existing release or expose a partial
   extraction. Retain protected provenance sufficient to distinguish the exact
   authenticated archive and file set. A repeated call for the same content may
   resume trust setup; the same product/component/version with different content
   must fail. Refuse unexpected existing ownership/content rather than silently
   repairing it. Define behavior for concurrent publication and interrupted
   staging/publication/trust updates; preserve a previously usable release.
6. Trust only the verified `deployment/` inventory. Update `wait_trust` to compare
   expected paths, sizes and hashes with the authenticated inventory, not a
   service-controlled directory listing. Preserve bounded polling, scoped trust
   files, duplicate-add diagnostics and explicit failures. Confirm OL9 handling
   of initial/intermediate/final symlinks and special files; the helper's own
   checks and protected paths must make safety independent of CLI traversal
   behavior.
7. Document the integrity policy explicitly. `size` is not protection against
   deliberate same-size replacement. `sha256` is additional content verification,
   not a substitute for verifying the bytes before enrollment or protecting the
   final release. Decide whether the protected layout supports the existing
   `none` baseline or requires `sha256`; test any stronger setting with startup,
   upgrades and `wait_trust`. Do not silently change global host policy. Warn or
   refuse settings incompatible with the documented design.
8. Use `sudoedit -u "$product_name"` consistently for service-owned config,
   including the README's missing-config-key recovery instructions. Run deploy
   and ordinary data operations as the service user. Keep root release retirement
   scoped to validated protected paths; update old-release deletion, trust removal,
   final host removal and all harness release-path assumptions. Retain old trust
   and release files until install, health and required application checks pass;
   preserve sibling releases, trust and persistent data.
9. Add regressions for the three reproductions, signature failure before host
   setup, archive/link/special-file rejection, protected ancestors and final
   ownership/modes, immutable-version conflicts, exact live trust records and
   interrupted/repeated operations. Verify the production lifecycle against a
   service-readable but nonwritable release. Include renamed products and the
   platform/help-only scenario without assuming app1 is present.
10. Add separate-UID malicious OL9 lab probes: attempt replacement before/after
    verification and after enrollment, addition of unlisted files, ancestor
    replacement and symlink insertion. Require protected writes to fail, no
    unauthenticated trust enrollment and no execution of substituted package
    content through the tested file-based launch path. Do not generalize this to
    a claim that a service user cannot execute arbitrary code at all. Record
    exact package versions, SELinux/fapolicyd settings and outside-target state;
    handle expected negative-probe audit evidence explicitly without broadly
    suppressing unrelated denials. Run the full six-scenario acceptance matrix.

### Sources and remaining host questions

- [Upstream fapolicyd integrity documentation](https://github.com/linux-application-whitelisting/fapolicyd/blob/main/README.md):
  size checking is intended for accidental overwrites; SHA256 compares content
  with the stored digest. Neither authenticates an attacker-controlled initial
  enrollment.
- [fapolicyd release notes](https://github.com/linux-application-whitelisting/fapolicyd/releases):
  version 1.4.5 explicitly mentions reporting skipped symlinks. Do not assume all
  symlinks are followed; test the installed OL9 build and path positions above.
- [GNU tar security guidance](https://www.gnu.org/software/tar/manual/html_section/Security.html):
  use a new empty extraction directory protected from untrusted modification.

Understandability review: the authoritative input should be the authenticated
archive snapshot; the protected published release is its durable representation.
The shared helper decides and performs privileged release/trust work, while deploy
owns service-user configuration and lifecycle state. On success, publish, enroll,
wait and deploy in that order. After failure, discard incomplete private staging
or resume an already verified identical release; never reinterpret a writable
directory as verified just because it exists. Validate this flow in tests and
document the remaining real-host assumptions before declaring completion.

### Done when

No root verification, trust or config-edit step operates on a path the service
user can replace. Authenticated content, the complete published file set and
live trust records agree, and the service user cannot change the final release
or its ancestors. Bootstrap signature verification, failure/retry behavior and
retirement are covered by the shared helper and consistent operator instructions.
Regressions and malicious lab probes pass with SELinux Enforcing and fapolicyd;
normal install, retry, upgrade and uninstall preserve credentials, data and
sibling isolation in the six-scenario matrix. Update the review guide and record
current-change lab evidence before marking this item resolved.


## 55. Add an explicit component-scoped dev reset

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve database
safety, declarative component names, scoped lifecycle, credential retention and
offline/rootless operation. Coordinate recovery documentation with item 3.

Status: planned; requested on 2026-10-20 after a real dev startup was refused
because `sts-db-data` existed while its database password file was missing.
Manual removal of that disposable volume allowed startup. The reset command
below is proposed functionality, not implemented behavior.

Scope update 2026-10-22: the operator also requests one simple way to delete all
Secrets and volumes of the dev installation. Add the explicit whole-dev mode
below alongside the component mode; no reset command exists yet.

### Why

An existing database volume may contain valuable data. Generating a replacement
password file does not change the database's initialized password. Consequently,
ordinary `dev/dev.sh up` must continue to refuse a missing-password/existing-volume
combination, with recovery guidance; it must never silently delete or reinitialize
the database. For disposable dev installations, provide an explicit alternative
to manually discovering containers, volumes and retained credential copies.

### Proposed command and task

```sh
./dev/dev.sh reset sts --delete-data
```

1. Require a catalog component ID and `--delete-data`; `sts` is an example, not
   a special case. Limit the command to a source checkout's dev installation and
   current rootless user. Do not operate on production state or require `apps/`,
   network access, sudo or new host Python dependencies.
2. Resolve the selected component's actual resources from effective declarations
   and the last rendered dev state. Show what will be stopped/deleted, explicitly
   warn that database data is lost and require confirmation before destruction.
   Refuse unknown components, ambiguous ownership, shared/external volumes and
   unsafe paths before destructive actions. Do not infer ownership solely from
   a component-name prefix or accept arbitrary volume/path deletion arguments.
3. Stop/remove only the selected component's containers/pods, then remove its
   exclusively owned dev data volumes, including the database and relevant
   retained Secret/import copies. Define the cleanup set explicitly so a later
   prepare cannot reuse stale rendered credentials accidentally. Preserve
   operator config, source manifests, external credential files, TLS/signing
   certificates and CA material. Retain valid generated source passwords by
   default; allow the normal generation path when a password is absent and its
   database volume has actually been removed. Never print secret contents.
4. Keep siblings, their data/credentials, shared network and shared owners intact.
   Do not run aggregate `kube down` on `build/install.yaml` as a component reset.
   Report resources still in use or other inspection/deletion failures without
   forced removal of unrelated containers. Make partial cleanup safely repeatable;
   inspection failure is not evidence that a resource is absent.
5. Reset performs cleanup only and explains how to start again with the existing
   `./dev/dev.sh up`. Document that this existing startup command applies the
   whole dev catalog; reset itself must not restart siblings. Keep normal `up`
   and `down` data-retention behavior unchanged.

### Whole-dev reset: all development Secrets and volumes

Also implement:

```sh
./dev/dev.sh reset --all --delete-data
```

This is an explicit fresh start of this checkout's dev installation, including
new passwords. The component mode above keeps its narrower retention contract;
its preservation of generated passwords/certificates is not the contract of
`--all`. Make the distinction clear in help, preview, confirmation and docs.

- Require `--all` and `--delete-data`; reject a component combined with `--all`.
  Show a read-only plan with exact owned pods, volumes, Podman Secrets and local
  credential paths, never their contents. Require explicit confirmation that all
  listed dev database contents and dev credentials will be lost. Cancel/no input
  must leave everything unchanged.
- Stop/remove all pods and containers of this dev product, then remove all their
  exclusively owned declared dev volumes, including database, import and
  Secret-backed copies where present. Remove matching Podman Secret objects too,
  so startup cannot consume a stale retained value. Never use global prune,
  `podman volume rm --all`, `podman secret rm --all` or ownership inferred only
  from a name prefix. Refuse resources still used by unrelated containers.
- Remove local dev Secret source files under `build/dev/`, including generated
  passwords/session keys and local dev TLS/signing/PFX credentials. Include the
  dev-only CA/private material under `build/dev/PKI` when present. Preserve source
  manifests, config defaults, global/component dev overrides, application files
  and unrelated non-secret input files. Do not simply delete the entire `build/`
  directory: it may contain manually supplied component files and other outputs.
- Do not delete or follow Secret sources outside the managed dev tree. Report
  those external inputs as retained and explain that any desired replacement is
  an explicit operator action. Preserve production state, root/source PKI,
  external organisation certificates, original images and the shared network.
  A secret copied into the managed dev tree is disposable in this mode, even if
  originally provided by the operator; list it clearly before confirmation.
- Invalidate/rebuild the affected generated dev config, rendered YAML and import
  artifacts so no secret survives in an old generated output that can be replayed
  accidentally. Keep the last successful resource inventory or a cleanup record
  until cleanup completes; it must support a retry after partial deletion.
  Coordinate with the retained state needed by component reset instead of adding
  separate competing ownership models.
- Resolve ownership from effective declarations and the last rendered dev state,
  covering removed/renamed components where the old inventory identifies them.
  Refuse ambiguous or external ownership before deletion. Reset must not depend
  on reading Secret contents, generating replacement secrets or passing ordinary
  startup's missing-password/existing-volume guard; that is exactly the broken
  state it must help clean up. Validate paths and symlinks without following them
  outside the dev tree.
- Cleanup is safely repeatable: absent owned resources are acceptable, inspection
  errors are not absence, and deletion failure stops success reporting while
  preserving enough inventory to resume. Preflight the full plan before mutation.
- Reset itself does not start apps or generate credentials. Explain the next steps:
  generated `generate:` sources are recreated by normal prepare/up; externally
  supplied Secrets/PFX/password inputs must be reprovisioned first. The shipped
  demo can use `./dev/demo-credentials.sh` before `./dev/dev.sh up`, but generic
  products must not implicitly invoke demo provisioning. Confirm that full reset
  followed by provisioning/start produces a new database with matching new
  client/server passwords and recomposed `SECRET_TEMPLATES` values.

### Verification and delivery

Add focused platform tests with arbitrary component IDs and no `apps/`: explicit
flag/confirmation requirements, invalid/shared resource refusal before deletion,
correct scoped commands, valid retained password preservation, missing-password
recovery, partial-failure retry and unchanged siblings/certificates/config. Add a
runnable real Podman check that reproduces the missing-password guard, resets a
disposable component, starts again and verifies database initialization and
sibling data/process retention across reset. Keep unit/harness and actual runtime
evidence separate. Document the command, irreversible data loss and the backup
recovery alternative; complete the understandability review of resource ownership
and deletion order. For `--all`, add positive and negative coverage for the complete cleanup set,
new generated passwords after reinitialization, dev certificate/CA disposal,
preserved external credentials/non-secret files/config/images/other products,
confirmation/cancellation, stale Secret copies, invalid startup state and partial
cleanup retry. Provide a focused real Podman fresh-start scenario using synthetic
resources and no private organisation image. No new general recovery framework
is required.


## 57. Add portable references to bundled component files

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve isolated
offline bundles, authoritative production config, scoped file access, credential
retention, read-only validation and Python 3.6 compatibility. High-priority
follow-up to item 56; a separate feature, not an implicit part of its merge rules.

Status: done. Implemented on 2026-10-21; real Podman/systemd/SELinux/fapolicyd
verification passed in lab matrix `t10` at `cda22e7`
([latest results](acceptance/RESULTS.md)). `component_file` resolves public inputs in the selected component/release,
with shared validation/materialization, logical retained config and existing
private-source guards. The app1 demo and isolated SQL upgrade/failure-retry
acceptance checks are implemented. See [verification and understandability
review](acceptance/RESULTS.md) for actual results and lab evidence.
The review notes below describe the baseline and implementation requirements.

Review follow-up (2026-10-21): the demo seed runs each SQL file with
`--single-transaction`, so a failed file rolls back entirely while completed files
stay committed; the real failure/retry probe now requires the failing file's
earlier row to be absent. The `sts` README example uses a relative dev path under
`build/dev/sts/` instead of a machine-specific path in a tracked file, and the docs
recommend an explicit file list or history table for real migrations instead of
executing every imported file.

The operator clarification in item 56 applies: no transition from pre-feature
installations is required. Test upgrades between releases of the new model.

### Problem and intended behavior

An SQL source under `components/<id>/files/` currently needs a dev path such as
`../../../components/<id>/files/permissions/9000_CreateUsers.sql`, resolved from
`build/dev/<id>/`. Production resolves ordinary relative paths from the persistent
component config directory instead; the file lives under an unpacked release.
Operators must hand-edit production release paths, which can become stale after
an upgrade or relocation. The same logical declaration should select the current
component's shipped file in both source dev and an unpacked offline bundle.

### Task

1. Define and document a small explicit source syntax for referencing a path
   under the selected component's `files/`. Choose the exact syntax during
   implementation; examples in the task are conceptual, not supported settings.
   Support non-generated sources in `VOLUME_FILES` and `SECRET_FILES` using a
   shared resolver, with their existing type/size rules. Do not introduce general
   shell/environment expansion, templating of arbitrary paths or app-specific SQL
   logic. Never execute referenced files as part of resolving them.
2. Resolve the reference against `components/<id>/files/` in the active source
   checkout or selected unpacked bundle. Carry that explicit context through
   config, validation and materialization; do not infer it from the caller's cwd,
   require `apps/`, use sibling release directories or depend on original build
   paths. Preserve ordinary relative, absolute and tilde path semantics.
3. Keep logical references in initialized persistent config instead of converting
   them to a versioned release's absolute paths. Later installs with that retained
   config must read files from the selected new bundle, including changed SQL,
   without rewriting operator config. Missing files must fail clearly; never
   fall back silently to an old release or source checkout. A newly published
   default still must not overwrite an existing authoritative config.
4. Reject absolute/traversing component-file references and symlink escapes,
   cross-component access and unsupported file types. Component-file sources are
   immutable inputs, never generation targets: refuse `generate` for this source
   kind before writes. Avoid exposing secret values in errors. Real secret inputs
   should remain external/generated credentials; do not commit or bundle passwords
   just because the file-reference mechanism can deliver a Secret.
5. Keep file delivery through the existing Secret/import-archive/PVC mechanisms,
   including init-container consumers and existing retention/uninstall behavior.
   Do not bind-mount build-machine paths into production containers. Confirm that
   current-release content actually reaches imported volumes after upgrade rather
   than merely asserting archive paths. Document existing stale/unlisted-file
   behavior and dev-seed inclusion explicitly; no automatic prod seeding toggle
   or new SQL runner is part of this task.
6. Document source/default config examples and relocated offline install/upgrade
   commands, including how it combines with item 56. Update relevant contracts,
   diagram text and tests only where affected; no general file-routing framework.

### Review additions (2026-10-21)

Code facts and decisions from the review; they refine the task above.

- **Current code.** `render.resolve_path(value, base_dir)` resolves relative paths
  from `build/dev/<id>/` in dev and the persistent config directory in production;
  the release is `common.ROOT`. It is used by `render.load_file_group`,
  `render.check_file_sources`, `render.secret_keys`,
  `deploy.database_password_path` and `bundle.generated_secret_guard` (which reads
  `entry["path"]` directly). All must use one shared resolver for the new kind.
  `file_group_sources` validates entry shape. VOLUME_FILES archives are written
  under `HOME/files` at install; Podman imports them at every start, overwriting
  matching files and keeping unlisted ones (README).
- **Recommended syntax.** A separate key, not a path prefix, so it cannot be
  mistaken for an ordinary relative path and `path` semantics stay unchanged:

  ```yaml
  VOLUME_FILES:
    app1-seed:
    - component_file: sql/010-reference.sql
  ```

  An entry has exactly one of `path` or `component_file`; `generate` with
  `component_file` is refused before writes. Confirm or justify another choice.
- **Selected release.** The base is `common.ROOT/components/<current component>/files/`:
  the source checkout in dev, the unpacked bundle running `./deploy.sh` in production,
  for validate and install alike. No release path is stored in config. Refuse the
  reference when there is no component context (standalone fixtures), and as a
  database password source or any generated credential.
- **Bundle guard and Secret delivery.** `bundle.generated_secret_guard()` currently
  excludes all declared `SECRET_FILES` sources from bundles, even without
  `generate`. Merely using the new resolver there would therefore reject an
  intentional bundled source. Define `component_file` in `SECRET_FILES` as an
  explicit declaration of shipped, non-secret content delivered through a Secret;
  it does not make the bundle a safe place for credentials. Permit this source
  kind without weakening the guard for ordinary private paths, generated files,
  credential directories or aliases. Test both successful archive inclusion and
  continued refusal when a file is also protected by a private declaration.
- **Recursive source checks.** If a component-file reference selects a directory,
  inspect all descendants, not only its root. `write_file_archives()` currently
  uses `dereference=True`, so an unchecked nested symlink could copy data outside
  the component. Reject symlinks and unsupported special files throughout the
  selected tree before generation or archive writes, using the same checks for
  validate and materialization. Cover a deeply nested escaping link, a symlinked
  ancestor and a special file without reading its contents. Preserve existing
  ordinary `path` semantics; apply the new confinement rules to `component_file`.
- **Dev selection versus bundle contents.** `bundle.py` copies the whole component
  `files/` tree. Consequently `files/sql-dev/900-dev-sample.sql` is included in the
  production bundle, even though production config does not select it for
  delivery or execution. Document and test that distinction; only harmless demo
  content belongs there. Excluding `config.dev.yaml` does not exclude files it
  references under `files/`, and these items add no selective packaging mechanism.
- **Sensitive dev-only seed data stays outside `files/`.** Because every file under
  `files/` ships, dev seed content that must not reach production (test users,
  test passwords, personal or customer-like data) belongs outside the component's
  `files/`, referenced with an ordinary `path` from `config.dev.yaml` (relative
  to `build/dev/<id>/` as today, or a local credential path). For the
  organisation's `sts` migration init container, the shipped migrations use
  `component_file` while such dev seeds use `path`. Document this rule with that
  example in README/docs/COMPONENTS.md, and add a test showing that a dev-only
  `path` source is neither packaged nor needed by production validate/install.
  Secret test passwords still belong in `credentials/`, never in tracked files.
- **Stale files.** Because Podman keeps unlisted files in an imported volume, a file
  removed from a later release still exists there. The demo makes every SQL file
  idempotent; document the limitation for the organisation's own migrations. No
  migration framework.
- **Demo usage (app1).** `components/app1/files/sql/010-reference.sql` creates a
  marker table (for example `demo_seed(name text primary key, value text)`) and
  upserts `reference` with a value identifying the release content;
  `files/sql-dev/900-dev-sample.sql` upserts `dev-sample`. `config.defaults.yaml`
  maps only the reference file to `VOLUME_FILES.app1-seed`; the item 56
  `config.dev.yaml` repeats it and adds the dev file (whole-map replacement). A new
  init container `seed-database`, after `prepare-database`, uses the already
  bundled `localhost/demo-postgres` image (official postgres with `psql`), mounts
  the PVC read-only and the existing database password Secret, and runs an
  explicit sorted list of `*.sql` files with `ON_ERROR_STOP`. The password goes
  from the mounted file into `PGPASSWORD` inside the container and is never
  printed. No new image or app rebuild; todo data, probes and app2 unchanged;
  update demo inventory counts intentionally.
- **SQL failure and retry.** The app1 pod already declares init-container type
  `always`; seeding must tolerate restart and repeated installation. Add a focused
  runnable Podman check that fails a SQL step after an earlier step succeeds,
  verifies startup is not reported as successful, then retries with corrected
  input and verifies no lost Todo data or duplicate seed rows. Add harness
  regressions for false success and report actual runtime execution separately.
  `ON_ERROR_STOP` stops processing but does not roll back earlier committed
  statements: use idempotent demo SQL and explain its transaction boundaries,
  without promising automatic migration rollback or adding a migration engine.
- **Acceptance.** DEV after dev-up: `demo_seed` has `reference` and `dev-sample`
  (query in the app1 postgres container, print only these rows). PROD after
  install: `reference` present, `dev-sample` absent. App1 upgrade in both app1-first
  and app2-first: build the new bundle with a changed reference value in an
  isolated build checkout (as the help/Identity builders do, never the operator's
  checkout). The `upgrade-bundle` step in `acceptance/remote.sh` currently requires
  that only `components/app1/VERSION` changed; require exactly VERSION plus that
  SQL file. After upgrade `reference` has the new value, the existing
  `persistent_state` check proves unchanged config, todo data stays readable and
  sibling checks pass. Coordinate with item 53, which changes the same step. The
  renamed `shop` scenario must carry component files and references and assert
  the same rows. Harness regressions reject the old value after upgrade, a
  `dev-sample` row on PROD and a missing `reference` row.
- **Additional tests.** Refuse absolute, `..`, empty, symlinked file or `files/`
  directory, cross-component, `path` plus `component_file`, `generate`, database
  password use and missing component context; SECRET_FILES use keeps key/size rules
  without printing values; the bundle guard handles entries without `path`; a
  relocated unpacked bundle with the source checkout removed resolves the same
  declaration; init-config keeps the logical reference and a newer bundle with
  changed bytes and unchanged config delivers the new bytes.

### Verification and delivery

Use renamed/minimal components without `apps/` to test identical declarations in
source dev and an unpacked relocated bundle with the original checkout removed.
Exercise config initialization, read-only validation, materialization and a new
bundle version with changed file bytes while persistent config is unchanged.
Cover missing sources, path/symlink escapes, generation refusal, ordinary paths,
Secret redaction and preservation of credentials, config and sibling state.
Add runnable real Podman acceptance coverage that reads an imported SQL/marker
file in an init-container before and after the selected-component upgrade. No
actual organisation SQL, passwords or Duende image is needed for the generic
fixture. Run relevant platform/isolation, harness and static checks; distinguish
these from real lab results. Complete the understandability review of reference
resolution, config persistence and release selection.


## 59. Standardise Quadlet placeholder syntax

Status: implemented with local product/harness regression checks (2026-10-23).
`@@UNIT_NAME@@` / `@@PRODUCT_NAME@@` use the existing single-pass parser with
an internal-only resolver; both templates are checked before host queries,
generation or writes, including standalone and equal-version `newer-only`.
[Verification and understandability review](acceptance/RESULTS.md).
Real Podman/systemd verification passed in the 2026-10-24 six-scenario matrix;
see [run provenance and limits](acceptance/RESULTS.md).
The original analysis and task follow.

### Analysis and decision

The Quadlet templates currently use `{name}` and `{product}`, while the YAML,
ConfigMap and Secret templates use `@@...@@`. The Quadlet spelling is a project
convention implemented by two literal replacements in `deploy.quadlet_text()`;
it is not syntax required by Podman or systemd. There is no technical need for
two placeholder spellings. Literal replacement also leaves misspelled markers
in the output without reporting the template error.

Standardise Quadlet on `@@UNIT_NAME@@` and `@@PRODUCT_NAME@@`. Keep the distinct
sources and rendering rules: these are internally calculated unit/product names,
not user configuration keys. Sharing marker syntax does not mean exposing the
YAML config or Secret resolvers to Quadlet, or changing YAML type preservation.

### Implementation brief for the AI agent

Read [AGENTS.md](AGENTS.md) and [the review guide](docs/REVIEW_GUIDE.md), then trace
both component and standalone flows before editing. Inspect:

- `quadlet/template.kube` and `quadlet/template.network`;
- `deployment/deploy.py`: `quadlet_text()`, `check_shared_network()`,
  `write_component_units_and_imports()` and `install_standalone()`;
- `deployment/common.py`, `deployment/catalog.py` and `deployment/validation.py`
  for template paths, authoritative names and read-only validation;
- `deployment/templates.py` and `deployment/render.py` for existing token parsing
  and the deliberately different config/Secret/YAML rendering contracts;
- the Quadlet fixtures in `tests/helpers/`, plus relevant validation, deployment,
  renamed-product, retry and bundle tests in `tests/platform_tests/`.

Implement the following contract:

1. Change the shipped `.kube` template to use these values, preserving its other
   directives:

   ```ini
   [Unit]
   Description=@@UNIT_NAME@@

   [Kube]
   Yaml=@@UNIT_NAME@@.yaml
   Network=@@PRODUCT_NAME@@.network
   ```

   The `.network` template becomes:

   ```ini
   [Network]
   NetworkName=@@PRODUCT_NAME@@
   ```

2. Resolve only these two names from explicit internal arguments. Product name
   comes from the existing catalog contract (`product:` in the source/compiled
   descriptor); unit name uses the existing component naming contract. Standalone
   fixtures retain `common.STANDALONE_PRODUCT`. Do not derive names from demo
   component IDs, environment variables, arbitrary config values or secrets.
   Do not introduce `UNIT_NAME` / `PRODUCT_NAME` as configurable settings.

3. Render text in one nonrecursive pass, supporting inline and repeated tokens.
   Reject unknown names, malformed `@@...@@` syntax and unresolved markers with
   a useful template-path/token diagnostic. Explicitly reject the obsolete
   `{name}` and `{product}` markers rather than silently accepting a mixed
   template. Preserve unrelated literal braces, shell `${...}` expressions and
   systemd `%` specifiers; do not ban every brace expression. Errors must not dump
   whole templates or configuration/Secret contents. Do not require every allowed
   marker to occur in every template.

4. Use the same pure rendering/validation logic for read-only `deploy validate`
   and install. Check both required templates for the selected operation during
   early preflight, including standalone mode, before image import, generated
   credentials, unit writes or host commands. Trace the existing ordering:
   validating `.kube` only in `write_component_units_and_imports()` is too late.
   Keep validation side-effect free and avoid a second parser with different
   acceptance rules. Respect component isolation and existing lifecycle checks.

5. Preserve generated unit/network names, YAML references, permissions, service
   directives and shared-network comparison/retry behavior. For equivalent valid
   template content, rendering must produce the same bytes as before. Renamed
   products and standalone fixtures must work without special demo assumptions.
   New source templates and the renderer must travel together in offline bundles.

6. Update affected test fixtures, comments, docstrings and current documentation.
   Explain that the marker syntax is shared but the allowed values depend on the
   template context. Historical backlog descriptions may remain historical.
   Existing installations can be discarded: no migration, dual-syntax fallback
   or compatibility aliases are required. Normal retry and retained-data contracts
   still apply to installations made with the new code.

Keep this small. Reuse a suitable existing tokenizer/substitution helper with a
Quadlet-specific resolver if that keeps the code clearer; do not reuse a resolver
that grants arbitrary config or Secret access. Do not add Jinja, another external
dependency, a generic template framework or unrelated deployment refactoring.
Retain Python 3.6 and offline operation. Do not change YAML typed substitution,
ConfigMap inline composition or Secret template policies.

### Verification and acceptance criteria

Add focused regression coverage for:

- Both templates, repeated/inline tokens and exact expected rendered output.
- A renamed product with a distinct component ID: the full unit name is used
  once, while the shared network uses only the product name; also standalone.
- Unknown, malformed and obsolete markers, config/Secret references being refused,
  and unrelated braces/shell expressions/systemd specifiers being preserved.
  Config values must not override the two internally supplied names.
- Identical rejection through read-only validation and install, with assertions
  that invalid templates cause no host commands or installation mutations.
- Repeated install/shared-network comparisons and sibling resource preservation.
- Current templates and renderer in an unpacked relocated offline bundle, using
  a minimal/renamed fixture without `apps/` or access to the original checkout.

Run the relevant platform, isolation and acceptance-harness checks using existing
repository conventions, plus `git diff --check`. Reuse existing bundle/retry tests
where they already prove the contract instead of duplicating the implementation
in tests. If real Podman/systemd verification is performed, report it separately
from unit/harness results; otherwise state that gap explicitly. Historical lab
results are not evidence for this change.

Complete an understandability review: a reader should be able to trace where the
two values originate, which tokens are allowed, when validation runs, what can
have changed when an error occurs, and why retry still works. Delivery is complete
when the templates, shared validation, fixtures and current documentation agree,
the relevant checks pass, and any runtime verification gaps are recorded.


## 60. Rename the CLI wrapper to deploy.sh

Status: implemented with local product and harness regression checks (2026-10-24).
`./deploy.sh` is the sole current wrapper in source, bundles, callers, usage and
current documentation; no old-name alias is shipped. Based on item 59 commit
`6c9a461`, on branch `fix/60-deploy-sh`.
[Verification and understandability review](acceptance/RESULTS.md).
Real Podman/systemd verification passed in the 2026-10-24 six-scenario matrix;
see [run provenance and limits](acceptance/RESULTS.md).
The original rename brief follows.

### Analysis and implementation brief

The current `deploy` is a small Bash wrapper: it changes to its own directory and
executes `python3 -B -m deployment`, forwarding all arguments. Renaming the wrapper
is straightforward; the work is making every caller and delivered bundle agree.
The suffix is a usability/naming decision, not a change of interpreter or CLI
behavior.

Read [AGENTS.md](AGENTS.md) and [the review guide](docs/REVIEW_GUIDE.md). Implement
this as a focused rename:

1. Rename the root executable `deploy` to `deploy.sh`, preserving its executable
   bit, Bash shebang, directory handling, argument forwarding and exit behavior.
   Keep the Python package `deployment` and its modules, including `deploy.py`,
   named as they are. Subcommands and arguments remain the same.
2. Find all executable-path references, including shell/Python callers, bundle
   file lists, checksums, executable permissions, host-preparation/trust handling,
   dev tooling, acceptance scripts, CI and test fixtures. Update active references
   to the new filename. Inspect each match; do not globally replace the word
   `deploy`, Python identifiers or conceptual uses of deployment terminology.
3. Update current README/docs, help and error messages, command examples and
   instructions emitted by scripts. Update active instructions in planned backlog
   items (including item 59) where they refer to the executable. Preserve historical
   verification reports and pinned historical fixtures as historical evidence.
4. New bundles must include executable `deploy.sh`, with checksum/trust handling
   matching the new path. Verify that an unpacked, relocated offline bundle works
   without its source checkout. Keep Python 3.6 and the existing offline dependency
   contract; no new runtime dependencies or installation steps are needed.
5. Existing installations can be discarded. Make `deploy.sh` the sole current
   entry point; no `deploy` alias, compatibility wrapper or migration is required.
   Preserve ordinary install, retry and retained-data behavior in new installations.

### Verification and completion

Adapt existing wrapper, bundle and acceptance-harness tests. Cover invocation from
another working directory, argument forwarding and exit status, executable mode,
help/validation and a relocated bundle using the new path. Exercise relevant
existing lifecycle tests through the renamed wrapper instead of adding duplicate
business-logic tests. Include a minimal/renamed product fixture without `apps/`
where appropriate, so verification is not limited to the demo checkout.

Search for remaining old executable references and explain intentional historical
matches. Run relevant platform/isolation and harness checks, documentation/link
checks and `git diff --check`. Report exact results and any real Podman/systemd
verification gap separately. Complete the understandability check by tracing the
public command through the wrapper to Python in both source and bundle, including
an error exit. Done means the source, release contents, callers, help, tests and
current documentation all agree on `./deploy.sh`.


## 62. Reject misplaced container fields in manifest validation

Status: implemented with local product regression coverage (2026-10-22).
Shared `render.pod_specs` rejects nineteen container-only fields directly under
Pod `spec`; validate, prepare, install and bundle building use the guard with
source-file context, including equal-version `newer-only` repeat installs after
review follow-up. Exact scope, checks and limitations:
[latest results](acceptance/RESULTS.md).
This closes the confirmed structural validation gap, distinct from item 61's
completed runtime verification. The original finding and task follow.

### Finding and reproduction

The operator placed `env` beside `initContainers` under a Pod's `spec`, instead
of inside the selected init-container object:

```yaml
spec:
  initContainers:
  - name: migration
    image: localhost/probe:1
    imagePullPolicy: Never
  containers:
  - name: main
    image: localhost/probe:1
    imagePullPolicy: Never
  env:                         # Wrong: belongs to a container, not Pod spec.
  - name: APP_CONNECTIONSTRING
    valueFrom:
      secretKeyRef:
        name: worker-settings
        key: connection
```

This is syntactically valid YAML, but `spec.env` is not a valid Pod field.
The operator observed empty/missing init environment variables. After correcting
the indentation, inspect showed the expected environment; the remaining migration
failure is separate and is not diagnosed by this finding.

A read-only synthetic reproduction at `7063f57` confirmed that
`render.effective_documents()` accepts the wrong structure above with a declared
`worker-settings` Secret template. `check_pod_specs()` checks selected supported
properties, but does not reject this misplaced field. Recursive reference scanning
can still count its Secret reference as used; a successful reference check is not
proof that the field belongs to a container or will be consumed by Podman.

### Implementation brief for the AI agent

Read [AGENTS.md](AGENTS.md), [the review guide](docs/REVIEW_GUIDE.md) and item 61.
Trace `render.effective_documents()`, `check_pod_specs()`, `pod_specs()`,
`containers()` and `references()` in `deployment/render.py`, then
`deploy.validate_component()` and its callers in `deployment/validation.py` and
`deployment/deploy.py`. Inspect bundle manifest validation too.

- Add structural validation that rejects misplaced container fields. At minimum,
  reject `env`, `envFrom`, `command`, `args`, `image`, `imagePullPolicy` and
  `volumeMounts` directly under Pod `spec`, with regression coverage for the
  operator's `spec.env` case. Assess other common misplaced fields and document
  the exact enforced scope; do not call a small guard complete schema validation.
- Put the check in the shared declaration-validation path used by validate,
  prepare and install, before credential generation, output writes or host
  commands. Reuse the same check for bundle building where applicable; do not
  add a validate-only rule or a late install-only check.
- Report the source manifest and field path, and explain the correct location.
  For example: `pod.yaml: spec.env is not allowed here; place env under
  spec.containers[] or spec.initContainers[]`. Do not print field values,
  passwords, connection strings or whole YAML documents. Carry source context
  explicitly where needed instead of relying on a generic filename in errors.
- Reject the error rather than silently moving fields into a container: a Pod
  may have several ordinary/init containers, so the intended recipient is unknown.
  Preserve valid `env` on each individual container and support both ordinary YAML
  sequence indentation styles. The problem is object structure, not an exact
  number of spaces or where the sequence dash is aligned.
- Keep Python 3.6, offline operation and supported Podman annotations/fields.
  Choose a small maintainable structural guard unless broader schema validation
  has a clear justified scope. Do not require a Kubernetes cluster, network schema
  downloads or a new mandatory external CLI. Do not apply a recursive keyword ban:
  ConfigMap `data`, Secret key maps and annotation values may legitimately contain
  words such as `env`, `image` or `command`.
- Review existing schema/shape checks before extending them. Avoid duplicate
  allowlists or independent validation engines. A broader strict field allowlist
  must be tied to documented supported structures and must not accidentally reject
  otherwise supported manifests. Do not expand supported resource kinds or add
  unrelated lifecycle/Secret behavior while addressing this gap.

### Regression coverage and completion

Use synthetic renamed/minimal components without `apps/`. Prove that misplaced
`spec.env` is rejected even when its Secret and key exist and the reference would
otherwise pass. Cover the other guarded fields, correct placement in ordinary and
init containers, multiple Secret-based env entries in the same init container,
and valid arbitrary keys in ConfigMaps/Secrets/annotations.

Exercise the public validate command and prepare/install paths, including an
unpacked relocated component bundle with retained production config. Assert that
refusal preserves config, credentials, existing rendered output and sibling state,
reads no credential contents during validate, and causes no Podman/systemd call.
Adapt relevant existing tests rather than building another harness. Cover bundle
build refusal before image operations if the shared check applies there.

Run relevant product tests, `python3 -B tests/run.py platform --isolate`, acceptance
harness tests if changed, and appropriate static checks plus `git diff --check`.
Report environment-blocked checks and real runtime verification separately.
Complete an understandability review of source context -> structural check ->
semantic checks -> materialization, including the error path before side effects.
Update current validation documentation and this item's status with the actual
scope and evidence. Success means this concrete YAML mistake fails clearly at
validation; it does not establish the cause of the remaining private Grate failure.

## 63. Parameterise image versions with build-time variables

Status: planned, high priority (2026-10-22, extended 2026-10-27). Requested by
the operator: image versions must be controlled by parameters, not edited
inside each manifest. Decision (operator, 2026-10-22): one shared variables file
`config/images.yaml`, placeholders only in container image references, resolved
at bundle build and in dev; plus a built-in `COMPONENT_VERSION` for images that
follow their component's release. Production keeps receiving fixed literal
tags.

Product owner, 2026-10-27:
- **Registry too, not only versions.** The organisation pulls images through
  Artifactory; when its address changes, it must change in one place. A
  variable can therefore hold the registry host and path, not only a tag, and
  the demo uses one (see "Demo adoption").
- **Optional per image.** Not every image uses the registry or any variable;
  some are written as plain literal references and must keep working.
- **`@@NAME@@`, not `{{NAME}}`.** Use the repository's existing placeholder
  spelling. `@@` already depends on where it stands (whole config values,
  inline ConfigMap and Secret-template text, `@@secret:…@@`, Quadlet
  `@@UNIT_NAME@@`); an `image` field becomes one more such place, read from
  `config/images.yaml` at build time. The rules under "Target behaviour" keep
  the two sources of `@@` values apart.

### Why image versions must not live in component config

Analysis on `a37f4e4`:

- `config/common.defaults.yaml` and `components/<id>/config.defaults.yaml` are
  copied into the authoritative production config by `init-config`. Later
  defaults are never merged into it (review-guide contract "Authoritative
  production config"). An image version there would keep the old image after an
  upgrade, or let an operator select an image the offline bundle does not
  contain.
- The bundle must know its images at build time. `bundle.build_release` calls
  `manifest_images(directory / "manifests")` on the source manifests and saves
  exactly those images in `images/images.tar` and `images/images.txt`.
  `render.find_images` deliberately rejects `@@` placeholders in `image:`
  ("placeholders are not supported").
- `@@NAME@@` elsewhere in a manifest (`common.PH`, resolved by
  `render.replace` from config at render time) means "comes from installation
  config". Inside an `image` field it is rejected today, so no existing
  manifest uses it there; giving it the build-time meaning in that one field
  breaks nothing. A reviewer must still be able to tell the two apart, hence
  the name rules below (target behaviour 2).

### Current image flow (all places that read source manifests for images)

- `bundle.manifest_images()` is used by `build_release`, `dev/build-images.sh`
  and `dev/pull-images.sh`. It parses source manifests through
  `render.load_yaml_all` and `render.find_images`.
- `bundle.build_release` copies `components/<id>/manifests` verbatim into the
  release with `shutil.copytree`.
- `render.py` around line 186 loads source component manifests for dev and
  validate. Rendered output (`deploy.py` near line 982, `health.py`) must not be
  token-resolved again.
- `deploy.load_and_verify_images` and the code near `deploy.py:854` load the
  release's `components/<id>/manifests` at install and check that every image
  exists after `podman load`.
- `dev/build-images.sh` maps `localhost/demo-postgres:<tag>` to
  `docker.io/library/postgres:<tag>` and builds other `localhost/demo-<app>`
  images from `apps/<app>/Containerfile`. It works on resolved names.
- `install_needed` (`deploy.py`): with `upgrade: newer-only` an equal installed
  version is kept. Installed metadata is the compiled descriptor
  (`deploy.py:830`) and records no images. A changed variable, for example
  `POSTGRES_VER`, without a `VERSION` bump would therefore be silently ignored
  on an existing installation. This is the main correctness risk of the
  feature.
- The acceptance harness hard-codes tags. `remote.sh` help and identity upgrade
  builders regex-replace `localhost/demo-help:X.Y.Z` and
  `localhost/demo-identity:X.Y.Z` in manifests (with a count==1 check) and build
  the new tag. Literal tags also appear in `tests/demo_tests/test_images_demo.py`,
  `test_bundle_demo.py`, `test_proxy.py`, `acceptance/test_identity.py`,
  `acceptance/test_components.py`, `acceptance/renamed_product.py` (keeps image
  names), README, ARCHITECTURE and acceptance documents.

### Target behaviour

1. `config/images.yaml` (optional; absent means no variables) is a flat mapping:
   ```yaml
   REGISTRY: artifactory.example.com/docker-remote
   POSTGRES_VER: '17.11'
   NGINX_VER: 1.28-alpine
   TODO_BACKEND_VER: 0.2.2
   TODO_FRONTEND_VER: 0.2.0
   ```
   Keys match `^[A-Z][A-Z0-9_]*$`. Values must be nonempty YAML strings. Reject
   numbers (`17.11` parses as a float) with a message telling the author to
   quote them. `COMPONENT_VERSION` is reserved. The file is build input. It
   never enters component or production config and is not merged by
   `merge_config`.
2. Placeholders are optional, per image reference. A literal reference
   (`image: docker.io/library/nginx:1.28-alpine`) stays valid, needs no
   variable and is copied unchanged; one manifest and one Pod may mix literal
   and templated references, and a manifest without `@@` in its `image` fields
   needs no change. Where wanted, manifests may use `@@NAME@@` inside a
   container or initContainer `image` string, in any part of it and more than
   once: registry host and path, name or tag. Examples:
   `image: localhost/demo-postgres:@@POSTGRES_VER@@`,
   `image: '@@REGISTRY@@/library/nginx:@@NGINX_VER@@'` (quoted: YAML would
   otherwise read a leading `@` as reserved). No nesting, defaults or
   expressions. Rules that keep the two `@@` sources apart, checked before any
   write:
   - In an `image` field, `@@NAME@@` comes only from `config/images.yaml` (or
     `COMPONENT_VERSION`); a name not defined there is an error, never a
     fallback to installation config.
   - Outside `image` fields, `@@NAME@@` keeps today's meaning (installation
     config). A name defined in `config/images.yaml` used outside an `image`
     field is an error naming file and field, so a build-time value cannot be
     mistaken for an installation setting.
   - A name may not be both an image variable and a key in common or component
     config defaults (or a reserved configuration name); refuse the build and
     name both files.
   - The resolved reference must be a valid image reference: no URL scheme
     (`https://` is refused with a hint to give only host and path), no
     whitespace or `@@` left, registry host with an optional port. Variable
     values are public (they end up in the release); never treat them as
     credentials.
3. `@@COMPONENT_VERSION@@` resolves to the owning component's
   `components/<id>/VERSION`. It requires component context; the standalone
   `manifests/` fixture has no component and must reject it clearly.
4. Resolution happens in one shared function used by every source-manifest
   reader listed above: bundle image discovery, bundle release copy, dev,
   validate, build-images and pull-images. Unknown names fail with file,
   component, container and variable name. Only names appear in messages, never
   unrelated file contents.
5. The release contains resolved literal manifests. `bundle.build_release` writes
   the resolved text instead of copying verbatim, before checksums are computed.
   `images.txt` must equal the images found in the shipped manifests. Production
   install, validate, upgrade and health then need no knowledge of the variables,
   and `render.find_images` keeps rejecting any unresolved `@@` in a release's
   `image` fields.
   Do not ship `config/images.yaml` in bundles.
6. Equal version, different images: record the resolved, sorted image list in
   the compiled descriptor (`bundle.yaml`), which installed metadata already
   stores. When `install_needed` would keep an equal installed version but the
   recorded images differ, refuse with a clear message to bump the component's
   `VERSION`; do not reinstall silently. Metadata from before this change has no
   image list. Treat that as "unknown" and allow the normal equal-version
   behaviour; existing lab installations may be discarded, so no migration
   layer is needed. Check `catalog.check_descriptor` and descriptor comparisons
   (`check_kept_shares`, sibling checks) so the new field does not break them.
7. A variable defined but unused by any selected manifest prints a warning at
   bundle build. That catches typos and leftovers without blocking.

### Demo adoption

Convert the demo so the templated forms and literal references are all
exercised; not every image is converted:
- help and identity: `@@COMPONENT_VERSION@@`. Their images are built per
  component.
- todo-backend and todo-frontend: `TODO_BACKEND_VER` and `TODO_FRONTEND_VER`.
  app1 and app2 share these images and may have different component versions.
- postgres in app1, app2 and identity: `POSTGRES_VER`.
- platform nginx: `REGISTRY` and `NGINX_VER`
  (`@@REGISTRY@@/library/nginx:@@NGINX_VER@@`, demo value `docker.io`), so the
  registry form is exercised; changing `REGISTRY` alone must change the pulled,
  bundled and installed image name. `dev/pull-images.sh` and
  `dev/build-images.sh` work on resolved names; check that the
  `localhost/demo-postgres` source mapping still holds.
- app3's whoami images stay literal (`localhost/demo-whoami-backend:0.1.0` and
  `localhost/demo-whoami-frontend:0.1.0`): a release must ship them unchanged,
  and the bundle's image list, `images.txt` and descriptor images must include
  them exactly as written.

This changes the demo's help and identity tags to the component version (for
example `localhost/demo-identity:0.4.12`). Update the harness accordingly:
- The help and identity upgrade builders in `remote.sh` should set only `VERSION`
  (plus content and marker changes) and build the image tagged with the new
  version. Remove the manifest regex replacement and its count check.
- `seed_upgrade.py` bumps app1 `VERSION` only. Its image must stay unchanged
  because todo images use variables. Assert that.
- `renamed_product.py` must carry `config/images.yaml` into the generated
  product (it copies Git-tracked files; verify) and keep image names unchanged.

### Detailed instructions for the implementation agent

1. Read [AGENTS.md](AGENTS.md), [the review guide](docs/REVIEW_GUIDE.md),
   `docs/COMPONENTS.md`, [tests/README.md](tests/README.md) and
   [acceptance/README.md](acceptance/README.md), and items 20, 21, 41, 56 and
   57. Re-check the code paths above on the current baseline before changing
   anything; line numbers will drift.
2. Implement one loader and resolver, for example a small function next to
   `render.load_yaml_all`. It should take the component (or none), parse the
   YAML, find tokens only in `image` fields of `pod_specs`/containers/
   initContainers, and reject tokens elsewhere. Keep YAML loading safe
   (`yaml.safe_load_all`) and Python 3.6 compatible on the target; the release
   never resolves.
3. For the release copy, prefer substituting resolved values into the original
   text after the parsed check has proved that every token sits in an image
   field. That preserves comments and formatting. Re-parse the written release
   manifest and require that `find_images` equals the bundle's image list.
4. Wire the resolver into `bundle.manifest_images`, `build_release`, the dev and
   validate source paths and both dev image scripts. Make sure renders of
   generated output and release manifests do not resolve a second time.
5. Implement the equal-version image guard (target behaviour 6), with a
   message naming the component and telling the operator to bump `VERSION`.
   Never print config or credential data.
6. Convert the demo and harness as described, keeping existing upgrade, sibling
   and persistent-state assertions.
7. Documentation:
   - `docs/COMPONENTS.md`: a new "Image versions" section.
   - README build and upgrade sections: how to change an image, and that a
     changed image needs a `VERSION` bump.
   - `docs/REVIEW_GUIDE.md`: a contract row "Image references", covering
     build-time only, literal in release, equal-version guard.
   - `ARCHITECTURE.md`: replace hard-coded tag references where they describe
     current behaviour.

### Tests

- Platform/product (generic, runnable with `platform --isolate`, no demo):
  - resolution in image fields, including a registry variable with a path
    and several variables in one reference;
  - literal references unchanged, alone and mixed with templated ones in the
    same Pod, and a product without `config/images.yaml` whose manifests
    have no image placeholders;
  - `COMPONENT_VERSION`;
  - an image variable name used outside an image field; a config name used
    in an image field; a name defined both as image variable and in config
    defaults;
  - a registry value with a URL scheme or whitespace;
  - unknown variable;
  - token outside image (env value, name, command, annotation);
  - non-string value;
  - reserved name;
  - missing file with and without tokens;
  - standalone fixture rejecting `COMPONENT_VERSION`;
  - nested or malformed tokens;
  - unused-variable warning;
  - release manifests contain no tokens and match `images.txt` and descriptor
    images;
  - comments preserved;
  - equal-version different-images refusal;
  - old metadata without images accepted.
- Demo tests: updated expected images, now resolved from `config/images.yaml`.
- Harness tests: upgrade builders no longer edit manifests. The identity and help
  builds tag `COMPONENT_VERSION`, and `seed_upgrade` keeps the todo image.
- Real lab: this touches every bundle and the upgrade flows. Run the full
  six-scenario matrix (app1, app2, help, platform, identity, shop) and record
  the run IDs and commit. Product, harness and real-runtime results must be
  reported separately.

### Acceptance criteria

- Changing a value in `config/images.yaml` (or a component `VERSION` for
  `COMPONENT_VERSION` images) changes the built, bundled, installed and running
  image tags, with no manifest edits. Changing the registry variable changes
  every image that uses it, in one place, and no literal image.
- Literal image references keep working unchanged; using placeholders is a
  choice per image, never a requirement.
- Production config never contains image versions. Releases contain only
  literal, fully qualified images.
- An equal-version release with different images is refused with guidance and
  never silently ignored.
- All existing contracts and lab scenarios stay green. The understandability
  review covers one normal build and upgrade flow and one failure flow (unknown
  variable or equal-version refusal).

Out of scope: operator overrides of image versions in production config,
registry credentials, automatic `VERSION` bumps and image pruning.

Open question (product owner, not decided): the Artifactory address may also be
needed outside manifests, for example in the `FROM` lines of the demo
Containerfiles (`docker.io/…`, `mcr.microsoft.com/…`) and in package sources
used while building images (NuGet, npm, pip). `config/images.yaml` covers only
manifest image references; the build side would need build arguments or
registry mirrors and is a separate decision.
