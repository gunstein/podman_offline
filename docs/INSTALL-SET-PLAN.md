# Item 66 implementation plan: install sets

Status: plan, 2026-10-24; not implemented. Read
[item 66](../BACKLOG.md#66-install-sets-several-signed-bundles-through-one-entry-point),
the [review guide](REVIEW_GUIDE.md) (including section 7), the
[item 65 plan](HOST-SETUP-PLAN.md) and the current
[production manual](PRODUCTION-INSTALL.md) before implementing. Decisions marked
**(confirm)** are recommendations the product owner should confirm first.

## Outcome and scope

Today the runtime user installs each component with its own block in the manual:
`init-config`, an inline Python edit of public settings, a shell loop that
copies credential files, then `validate` and `install`, repeated per component
in a dependency order the operator must know. The manual run of backlog 64 and
the item 65 operator review show this is the hardest part for the operator.

After item 66:

- The supplier delivers one **install set**: a small signed manifest naming the
  product and exact component versions, next to the signed bundles.
- The administrator runs item 65's `setup` once with `--set <manifest>` instead
  of one `--release` per component. Setup authenticates the manifest, publishes
  exactly the listed bundles and stores the authenticated manifest root-owned.
- The runtime user, over SSH without sudo, runs **one command**,
  `deploy.sh install-set`, as many times as needed. Each run brings the
  installation one step closer to the manifest, in dependency order, and stops
  with one concrete instruction when it needs operator input or hits an error.

Not in scope: a second deployment engine, automatic retirement of old releases,
migration of old installations, credential generation (backlog 45b), changing
the per-component commands, or a general config-management language.

## Decisions

| Question | Decision |
| --- | --- |
| What is an install set | A YAML manifest `<product>-set-<set>-<version>.yaml` with a detached `.asc` from the same bundle signing key: `product`, `set` (name), `version`, `host_release` (`component@version`) and a list of `component`, `version`, `archive_sha256`. Built from the source catalog by `bundle.py`/`build-bundle.sh`. **(confirm)** |
| Why signed | It decides which signed bundles become the installation; an unsigned list could silently select an older signed version or drop a component. The archive digests bind the exact archives. Each bundle signature is still checked separately. |
| Administrator entry point | `setup --set <manifest>` in `scripts/release.py`, mutually exclusive with `--release`/`--host-release` (which stay for single components). No new privileged tool. |
| Where the runtime reads it | Setup publishes the verified manifest immutably as `/var/lib/<product>/sets/<set>-<version>.yaml` (root-owned, 0644, protected ancestors), after all listed releases are ready. The runtime account never reads the upload directory. |
| What `install.sh` becomes | Not a script in the delivery: code in the upload directory is unauthenticated. The runtime command is `deploy.sh install-set` in the authenticated host release; setup prints the exact path. **(confirm)** |
| Who runs component code | `install-set` runs each member's **own** published `deploy.sh` (`init-config`, `validate`, `install`) as a child process. It never imports another release's Python, so every component keeps the lifecycle code of its own version. |
| Order | `catalog.dependency_order` over the members' published `bundle.yaml` descriptors. A dependency outside the set must already be installed in a compatible range; otherwise stop before any change. |
| Progress record | None new. Every run recomputes from durable state: installed markers/metadata, `state/pending-operation.json`, existing config and credential files. |
| Already installed | A member installed and complete at the manifest version is **skipped**, also for `upgrade: always` components, so a rerun restarts nothing that is done. To apply a changed config, the operator runs that component's own `install` (manual section "Change configuration"). **(confirm)** |
| Older installed | Upgrade in dependency order through the member's own `install`. |
| Newer installed | Stop: downgrade, also for `upgrade: always` components. |
| Public settings | Optional `--settings <file>`: data-only `component.KEY=value` lines (parsed like the bootstrap file, never executed), applied only when `init-config` creates a new config. An existing config with a different value stops with the key name, never the value; equal values are fine. Replaces the inline Python edit in the manual. **(confirm)** |
| Credentials | Optional `--credentials <dir>`: a private directory that mirrors the state layout, `<component>/credentials/<group>/<file>`. Before `validate`, copy only missing files (0600, no links, regular files); identical existing files are kept; a different existing file stops. Never overwrite, never print contents. Replaces the copy loops in the manual. **(confirm)** |
| Stops for input | When `validate` fails for a member, stop with: component, config path, the validate message, what to supply (config key or credential file), and the same `install-set` command to continue. Exit 3 for "needs input", 1 for failure, 0 when every member is complete and active. |

## Runtime algorithm (`deploy.sh install-set`)

Parse arguments (`--set <name>` only needed when more than one set is
published; `--settings`, `--credentials`). Then, read-only first:

1. `service_user()` and `production_environment()` as for every lifecycle command.
2. Load the protected manifest; check product, set and that every listed
   release exists under `releases/` with a matching published record. Never
   unpack or read the upload directory.
3. Load member descriptors from their releases and the installed metadata.
   Check same product, id prefixes, role owners, dependency ranges between
   members and against installed non-members, cycles. Stop before changes on
   any conflict.
4. Pending record: if it belongs to a member, that member goes first, through
   its own `install`, which resumes owner work. If it belongs to a non-member,
   stop and print that component's own continuation command.
5. For each member in dependency order:
   - complete at the manifest version: print `[OK] <component> <version> already installed` and continue;
   - newer installed: stop (downgrade);
   - missing config: run member `init-config`, then apply `--settings` values
     for that component to the new file;
   - apply `--credentials` for that component;
   - run member `validate`; on failure stop as "needs input";
   - run member `install`; on failure stop, print the safe diagnosis lines the
     component already prints and the continuation command;
   - check the member is complete in `status --json` before the next one.
6. Finish with the `status` table and `PASS: install set <set> <version>`.

The coordinator is one module (`deployment/install_set.py`) with small named
functions: `load_set`, `plan_members`, `apply_settings`, `apply_credentials`,
`run_member`. No plugin system, no new state file.

## Failure and retry table

| Where it stops | Durable state | Next run |
| --- | --- | --- |
| Manifest/plan conflict | nothing written | fix delivery or installed state, same command |
| `init-config` of member N | earlier members installed; member N may have a new config | config is retained; continues with settings/credentials/validate |
| `validate` needs input | as above, plus copied credentials | operator supplies the named input; same command |
| `install` of member N fails mid-way | pending record for N | N runs first through its own `install` and completes |
| Interrupted between members | earlier members complete | skipped without restart; continues with the next member |
| Upgrade set, member N fails | members before N upgraded | same command finishes N and the rest; old releases are still published for the administrator to retire after success |

## Supplier and administrator side

- `bundle.py`/`build-bundle.sh`: new option to write the set manifest for the
  selected components with their own `VERSION`s and archive digests, and sign
  it with the existing `BUNDLE_SIGNING_KEY` flow. Refuse components missing
  from the build or a dependency missing from the set unless explicitly listed
  as already installed.
- `scripts/release.py setup --set`: verify the manifest signature with the
  pinned key before reading it as a selection, validate fields with
  `identity()`, derive the archive names, compare each archive's SHA256 with the
  manifest after snapshot and before extraction, then the existing
  `publish`/`enroll`, host script and journal steps. Publish the manifest last,
  immutably; a different manifest with the same set and version is refused.
  Keep Python 3.6 compatibility and existing commands unchanged.
- Retirement stays an explicit administrator command. The manual's upgrade
  section shows it after `install-set` reports success.

## Manual changes

Replace sections 5–7 of `docs/PRODUCTION-INSTALL.md` with one runtime step:
deliver the private credential directory, write the small settings file from the
values block, then run `install-set` and follow its instruction until it prints
`PASS`. The values block loses the per-component version and component name
entries; it gets the set file name. Keep the per-component commands in an
"Advanced: one component" section for configuration changes.

Count commands, edits and account switches before and after for the AI operator
walkthrough (review guide section 7); the goal is fewer of each, not the same
steps hidden inside one command.

## Required tests

Product/unit tests with arbitrary names (product `cedar`, components `base`,
`login`, `worker`, account `operator-a`), real bundles, real signatures where
the signature path is tested, host commands replaced:

- Manifest: valid set, wrong signature, wrong product, duplicate component,
  version mismatch with archive, digest mismatch, unlisted archive present in
  the upload directory (must not be opened), missing host release.
- Order: dependency order, dependency outside the set installed or missing,
  incompatible ranges, cycle.
- Converge: first install of three members; rerun with everything done starts
  and restarts nothing (trace `systemctl` calls); `upgrade: always` member at the
  same version is skipped; downgrade refused; upgrade of one member only.
- Stops: missing credential, missing setting, `validate` failure; exit code 3;
  message names component, file/key and continuation, never a value.
- Retry: failure inside member 2 install in a fresh process resumes through its
  own `install`; pending record for a non-member stops with its command.
- Settings/credentials: applied only to new config; conflicting existing value
  or file stops; links, non-regular files and unsafe modes refused; contents
  never printed.
- Each member's own `deploy.sh` is executed (not imported) and receives no
  extra environment.

Acceptance harness: a new `--install-set` scenario that uses the manual's public
commands only: item 65's bootstrap/`setup --set`, then SSH login as the non-sudo
runtime account (item 67's path) and `install-set`, including a deliberate stop
for a missing credential, an unchanged rerun (assert no restarts) and an
interruption inside one member continued in a fresh SSH session. Drift tests
fail if the harness uses lower-level component commands for the set path.

Existing gates: `tests/run.py platform --isolate`, `tests/run.py demo`, the
acceptance-harness suite, Ruff, Pyright, Vermin 3.6 and shellcheck as in
`tests/README.md`, link checks in source and unpacked bundles, `git diff --check`.
Real OL9: the new scenario plus the six-scenario matrix, because `release.py`
changes.

## Work packages

1. Manifest format, build-side writer and signature, `setup --set` with tests.
2. `deploy.sh install-set` core: plan, order, skip, stop, retry, with tests.
3. `--settings` and `--credentials` inputs with tests.
4. Manual rewrite and the AI operator walkthrough with command counts.
5. Harness scenario, drift tests; lab run instructions (not run by the agent).

Packages 1–2 are useful alone; 3–4 are what makes the manual short. Each package
leaves existing commands and tests working.

## Understandability review to complete

- Success: supplier manifest → signature with pinned key → exact archives
  published → protected manifest → runtime plan from protected data and
  installed state → each member's own lifecycle code → status.
- Failure/retry: member 2 `install` fails → pending record → fresh SSH login →
  same command → member 2's own `install` resumes → remaining members → no
  restart of member 1.

Open questions for the product owner are the **(confirm)** rows above; the
largest are skipping same-version `upgrade: always` components and the two
optional input files.
