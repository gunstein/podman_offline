# Item 66 implementation plan: install published components with one command

Status: plan, revised 2026-10-24 after discussion with the product owner; not
implemented. Read
[item 66](../BACKLOG.md#66-install-sets-several-signed-bundles-through-one-entry-point),
the [review guide](REVIEW_GUIDE.md) (including section 7), the
[item 65 plan](HOST-SETUP-PLAN.md) and the current
[production manual](PRODUCTION-INSTALL.md) before implementing.

## Outcome and scope

Today the runtime user installs each component with its own block in the manual:
`init-config`, an inline Python edit of public settings, a shell loop that
copies credential files, then `validate` and `install`, repeated per component
in a dependency order the operator must know. The manual run of backlog 64 and
the item 65 operator review show this is the hardest part for the operator.

Bundles reach customers in different ways: sometimes one DVD per bundle, at
different times; sometimes many bundles on one USB stick. Updates are usually
one new bundle for one component. The design must work the same for all three.

After item 66:

- The administrator copies whatever bundles arrived into the upload directory
  and runs item 65's `setup` to publish them. Publishing a release means it is
  intended to be installed.
- The runtime user, over SSH without sudo, runs **one command**,
  `deploy.sh install-set`, as many times as needed. It installs or upgrades
  every published component to its newest published version, in dependency
  order, skips components that are already done, and stops with one concrete
  instruction when it needs operator input or hits an error.

Not in scope: a supplier-made set manifest (dropped, see decisions), a second
deployment engine, automatic retirement, rollback/downgrade (a real rollback
needs a database restore; backlog 3), migration of old installations,
credential generation (backlog 45b), changes to the per-component commands.

## Decisions

| Question | Decision |
| --- | --- |
| Supplier set manifest | **Dropped.** Bundles arrive one per DVD, at different times, or many on a USB stick; a supplier list does not fit all. Each bundle's own signed `bundle.yaml` already gives dependencies and version ranges, so order and compatibility are computed from the bundles. |
| What gets installed | For each component, the newest release published under `/var/lib/<product>/releases/` (root-owned, signature-verified, trusted by fapolicyd). The upload directory is never read by the runtime user. |
| What the administrator selects | Publication is the selection. `setup` keeps explicit `--release COMPONENT@VERSION`, and gets `--all-in-input-dir` for a full USB stick: publish every signed bundle for this product found in the upload directory, after printing the list. |
| Guard for `--all-in-input-dir` | Never publish a version older than one already published or installed for that component; refuse two versions of one component in one run; ignore other products' archives with a message. Every archive is still signature-checked before extraction. |
| What `install.sh` becomes | Not a script in the delivery: code in the upload directory is unauthenticated, and root must not run it. The runtime command is `deploy.sh install-set` in a published release; `setup` prints its exact path. |
| Who runs component code | `install-set` runs each component's **own** published `deploy.sh` (`init-config`, `validate`, `install`) as a child process. It never imports another release's Python, so every component keeps the lifecycle code of its own version. |
| Order and compatibility | `catalog.dependency_order` over the newest published descriptors. Before any change, check every dependency range between them and against installed components that will stay. A missing or incompatible dependency stops with the component, the required range and who must act. |
| Progress record | None new. Every run recomputes from durable state: published releases, installed markers/metadata, `state/pending-operation.json`, existing config and credential files. |
| Already installed | A component complete at its newest published version is **skipped**, also for `upgrade: always` components, so a rerun restarts nothing that is done. To apply a changed config the operator runs that component's own `install` (manual section "Change configuration"). |
| Older installed | Upgrade through that component's own `install`; existing config, credentials, database passwords and volumes are kept as today. |
| Newer installed than published | Stop: downgrade is refused. Rollback is a database restore plus reinstall, outside this item; the manual tells the administrator to take a backup before upgrades. |
| Public settings | Optional `--settings <file>`: data-only `component.KEY=value` lines (parsed like the bootstrap file, never executed), applied only when `init-config` creates a new config. An existing config with a different value stops with the key name, never the value. Replaces the inline Python edit in the manual. |
| Credentials | Optional `--credentials <dir>`: a private directory that mirrors the state layout, `<component>/credentials/<group>/<file>`. Before `validate`, copy only missing files (0600, regular, no links); identical existing files are kept; a different existing file stops. Never overwrite, never print contents. Replaces the copy loops in the manual. |
| Stops for input | When `validate` fails, stop with component, config path, the validate message, what to supply and the same `install-set` command. Exit 3 for "needs input", 1 for failure, 0 when every published component is complete and active. |
| Retirement | Stays an explicit administrator `retire` after the runtime user reports success. Until then the old release stays published and is ignored because a newer one exists. |

## Delivery and update flows the plan must support

| Situation | Administrator | Runtime user |
| --- | --- | --- |
| First installation from a USB stick | copy all files, `setup --all-in-input-dir` | `install-set` until `PASS` |
| One DVD per bundle, at different times | per DVD: copy, `setup --release <it>` | `install-set` after each; a component whose dependency is not yet published stops with that message and nothing changes |
| Update of one app | copy the new bundle, `setup --release app1@<new>`; after success `retire` the old one | `install-set`: other components skipped, app upgraded |
| App needs a newer platform | publish both | `install-set` upgrades platform first, then the app |
| New platform incompatible with an installed app | publish | `install-set` stops before touching platform, naming the app and range |

## Sequence (planned)

```mermaid
sequenceDiagram
    autonumber
    actor S as Supplier
    actor A as Administrator (sudo)
    participant U as Upload dir<br/>/var/tmp/myproduct-upload
    participant R as release.py setup (root)
    participant P as Published releases<br/>/var/lib/myproduct/releases
    actor D as Runtime user (SSH, no sudo)
    participant I as deploy.sh install-set
    participant C as Component deploy.sh<br/>(own release)
    participant Y as systemd --user / Podman

    S->>A: signed bundles (.tar.gz + .asc) on DVD or USB
    A->>U: copy files (scp / mount)
    A->>R: setup --all-in-input-dir (or --release c@v)
    R->>R: preflight: OS, SELinux, fapolicyd, account, space
    loop each selected bundle
        R->>U: snapshot archive + signature
        R->>R: verify signature with pinned key
        R->>P: extract, publish immutable release
        R->>R: fapolicyd trust for exactly these files
    end
    R->>R: host preparation (first time only)
    R-->>A: PASS + exact install-set command

    D->>I: install-set --settings file --credentials dir
    I->>P: newest published version per component
    I->>I: dependency order + version range checks
    alt missing or incompatible dependency
        I-->>D: STOP: who must act; nothing changed
    else plan ok
        loop each component in dependency order
            alt already installed at this version
                I-->>D: [OK] skipped, no restart
            else not installed or older
                I->>C: init-config (only if config missing)
                I->>I: apply settings to new config, copy missing credentials
                I->>C: validate
                alt needs input
                    I-->>D: STOP (exit 3): file/key to supply, same command
                else valid
                    I->>C: install
                    C->>Y: load images, write Quadlets, restart service
                    Y-->>C: healthy
                    C-->>I: complete
                end
            end
        end
        I-->>D: status table + PASS
    end
    opt after an upgrade has been checked
        A->>R: retire old release
    end
```

On a stop the runtime user supplies what is named and runs the same command; a
failure inside one component leaves its pending record and the next run resumes
that component first.

## Runtime algorithm (`deploy.sh install-set`)

Read-only first:

1. `service_user()` and `production_environment()` as for every lifecycle command.
2. List published releases for this product (validated names, published records
   present, protected ownership as `layout`/`release.py` already require). Pick
   the newest version per component; ignore older ones.
3. Load their descriptors and the installed metadata. Check same product, id
   prefixes, role owners, dependency ranges, dependents, cycles. Stop before
   changes on any conflict.
4. Pending record: if it belongs to a published component, that component goes
   first through its own `install`, which resumes owner work. Otherwise stop
   and print that component's own continuation command.
5. For each component in dependency order:
   - complete at the selected version: `[OK] <component> <version> already installed`;
   - newer installed: stop (downgrade);
   - missing config: run its `init-config`, then apply `--settings` for it;
   - apply `--credentials` for it;
   - run its `validate`; on failure stop as "needs input";
   - run its `install`; on failure stop with the safe diagnosis it already
     prints and the continuation command;
   - confirm it is complete with `status --json` before the next one.
6. Finish with the `status` table and `PASS: all published components installed`.

One module, `deployment/install_set.py`, with small named functions:
`published_releases`, `plan`, `apply_settings`, `apply_credentials`,
`run_component`. No plugin system, no new state file.

## Failure and retry table

| Where it stops | Durable state | Next run |
| --- | --- | --- |
| Plan conflict (missing/incompatible dependency, downgrade) | nothing written | administrator publishes the missing bundle or the supplier provides a compatible one; same command |
| `init-config` of component N | earlier components done; N may have a new config | config retained; continues |
| `validate` needs input | as above, plus copied credentials | operator supplies the named input; same command |
| `install` of N fails mid-way | pending record for N | N first, through its own `install` |
| Interrupted between components | earlier ones complete | skipped without restart |
| Upgrade of N fails | components before N upgraded; old release of N still published | same command finishes N and the rest; retire only after success |

## Administrator side (`scripts/release.py`)

- `setup --all-in-input-dir`: list `<product>-<component>-<version>-offline.tar.gz`
  with matching `.asc` in the input directory, validate names with `identity()`,
  apply the guard above, print the selection, then the existing per-release
  `publish`/`enroll`. Host preparation runs as today; `--host-release` defaults
  to the selected release that carries `scripts/prepare-host.sh` only when
  exactly one does, otherwise it must be given.
- After an initial setup, `setup` for further bundles skips completed host work
  through its existing postcondition checks; the manual uses the same command.
- Print the exact `install-set` command for the runtime user.
- Keep Python 3.6 compatibility and existing commands unchanged.

## Manual changes

Replace the per-component runtime sections of `docs/PRODUCTION-INSTALL.md` with:
deliver the private credential directory, write the small settings file from the
values block, run `install-set` and follow its instruction until `PASS`. Add an
"Update" section: copy new bundle, `setup`, `install-set`, check, `retire`, with
a backup reminder. Keep per-component commands under "Advanced: one component".
The values block loses per-component names and versions.

Count commands, edits and account switches before and after for the AI operator
walkthrough (review guide section 7); the goal is fewer of each, not the same
steps hidden inside one command.

## Required tests

Product/unit tests with arbitrary names (product `cedar`, components `base`,
`login`, `worker`, account `operator-a`), real bundles, real signatures where
the signature path is tested, host commands replaced:

- Selection: newest published version per component; older published ignored;
  unpublished upload files never opened by `install-set`; `--all-in-input-dir`
  with other products' archives, two versions of one component, an older
  version than published/installed, unsigned archive.
- Order and compatibility: dependency order; dependency published later
  (DVD-at-a-time); incompatible ranges both ways; cycle.
- Converge: first install of three components; rerun starts and restarts nothing
  (trace `systemctl` calls); `upgrade: always` component at the same version is
  skipped; upgrade of one component only; platform-then-app upgrade order;
  downgrade refused.
- Stops: missing credential, missing setting, `validate` failure; exit code 3;
  message names component, file/key and continuation, never a value.
- Retry: failure inside component 2 install in a fresh process resumes through
  its own `install`; pending record for an unpublished component stops.
- Settings/credentials: applied only to new config; conflicting value or file
  stops; links, non-regular files and unsafe modes refused; contents never printed.
- Each component's own `deploy.sh` is executed (not imported).

Acceptance harness: a new scenario using only the manual's public commands:
item 65 bootstrap and `setup --all-in-input-dir`, SSH login as the non-sudo
runtime account (item 67's path), `install-set` with a deliberate stop for a
missing credential, an unchanged rerun (assert no restarts), an interruption
inside one component continued in a fresh SSH session, then a one-app update
through `setup --release` + `install-set` + `retire`. Drift tests fail if the
harness uses lower-level component commands for this path.

Existing gates: `tests/run.py platform --isolate`, `tests/run.py demo`, the
acceptance-harness suite, Ruff, Pyright, Vermin 3.6 and shellcheck as in
`tests/README.md`, link checks in source and unpacked bundles, `git diff --check`.
Real OL9: the new scenario plus the six-scenario matrix, because `release.py`
changes.

## Work packages

1. `install-set` core: published-release selection, plan, order, skip, stop,
   retry, with tests.
2. `--settings` and `--credentials` inputs with tests.
3. `setup --all-in-input-dir` and default host release, with tests.
4. Manual rewrite (install and update) and the AI operator walkthrough with
   command counts.
5. Harness scenario and drift tests; lab run instructions (not run by the agent).

Package 1 is useful alone; 2–4 are what make the manual short.

## Understandability review to complete

- Success: upload → signature → published release → newest published per
  component → dependency plan → each component's own lifecycle code → status.
- Update: new bundle published → only that component differs → its own
  `install` upgrades it → others skipped → administrator retires the old release.
- Failure/retry: component 2 `install` fails → pending record → fresh SSH login
  → same command → its own `install` resumes → remaining components → no
  restart of component 1.
