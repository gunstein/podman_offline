# Test baseline before structural changes

Implementation for backlog item 10 (also supplies item 5's historical-upgrade
scenario). Product deploy/bundle behavior is unchanged.

## Baseline and existing coverage

Baseline: `05d909d0b7e95bf6c6e4ec74f848d1860c0c655f` on main.
On 2026-10-15, Python 3.12.14 / PyYAML 6.0.3:

- Product suite: 181 tests, 13 errors. All errors came from component test staging
  using the synthetic `/run/user/1000`, absent on this host. The fixture previously
  mocked directory existence but did not redirect temporary staging there.
- Acceptance harness: 142 tests, all passed. These are local framework tests, not
  VM acceptance results.
- Redirecting only that synthetic staging location into the fixture's temporary
  directory restored all 181 product tests. The production account/runtime guards
  and their assertions remain unchanged.

Existing tests already cover config precedence and authoritative persistent config,
rootless environment guards, private credentials and volume preflight, namespace
validation, import archives and checksums, equal/newer/older core decisions,
registration staging, scoped uninstall, and sibling isolation. The existing lab
flow covers login, database authentication, CRUD, reboot/crash/hang and scoped
upgrades, but its version-only app upgrade does not prove a historical 0.2.0
transition.

## Added coverage

- `tests/test_install_failures.py`: upgrade an existing core/app1 installation;
  inject load failure, image-exists missing/error exits (1 and 125), and restart
  or is-active failure in either service. Compare configs, credentials, imports,
  route/client registrations, Quadlet/YAML and version markers, preserving app2.
  Image failures leave persistent files unchanged. Service failures leave already
  committed renders/registrations/imports in place, retain old version markers and
  stop the service sequence immediately. This explicitly documents the existing
  non-atomic install; it does not promise rollback.
- `tests/test_database.py`: each missing DB_HOST/DB_PORT/DB_USER/DB_NAME in either
  selected legacy config refuses installation before any command or state write,
  even when incoming defaults contain the key.
- `tests/test_wrappers.py`: actual absolute-path deploy/build entry points from an
  unrelated cwd, a real built/extracted component archive, source prepare/build
  and release init-config/install/uninstall. Resource/output paths and authoritative
  persistent configs are checked; caller config is untouched. Only host account,
  runtime and Podman/systemd transport are stubbed in private child processes.
- `acceptance/test_upgrade_020.py`: ordered historical build/migrations/checks,
  failure stops before trust retirement, real guest snapshot/migration comparison,
  password/config drift, replaced volumes, restarted sibling containers, and the
  actual trust-retirement shell refusing changed sibling trust before deletion.

No product defect was identified. The test-fixture portability issue above was
fixed. No product refactor, automatic product migration, password rotation or
rollback was introduced.

## Run the historical upgrade in the lab

From a clean, committed checkout, using the existing private lab configuration:

```sh
python3 acceptance/acceptance.py --run upgrade-020-20261015 --upgrade-020 run
```

Use a new run ID for each attempt. This mode uses the existing runner's readiness,
configured disposable VM snapshot reset, production offline isolation, logs,
audit finalization and private credential cleanup. It resets both configured lab
VMs, just like the full acceptance run. It does not run the reboot/crash/hang,
registry or example matrix again. Normal acceptance mode remains available.

Historical source is pinned to
`86e8e27ed38d6e209eecf018299fd48ec2ce0b1b` (VERSION and CORE_VERSION 0.2.0,
before the database-generator transition). The source Git bundle includes this
ancestor. A separate detached dev worktree builds the old images and genuine
0.2.0 archives before any new images are built. Old versions are never simulated
by editing VERSION in current code. Old application images are rebuilt from the
pinned source; registry/base-image tags use the existing builders and are not
a claim of byte-identical archived images from the original release. New source is the committed HEAD selected by
readiness (initial implementation targets VERSION/CORE_VERSION 0.2.1); both source
revisions and transferred archive hashes are recorded in run metadata.

The scenario installs old app1/core and app2, then creates Alice/Bob Todo markers
through the existing authenticated clients. A private service-user snapshot records
config/credential/import/registration/render hashes and modes, installed versions,
database volume identity, systemd invocation/start identity and healthy container
IDs/PIDs/start times/restart counts. Password bytes and hashes are never logged.

The test then applies exactly README's operator steps to core/app1: add four DB
fields and append the existing password path to GENERATED_SECRETS, keeping all
other values. App2's config remains old until its own stage. Each stage installs
its new bundle through the actual release wrapper from the service user's home,
checks health, login/CRUD and old markers in both apps, and compares private state.
After the second stage it also runs the existing installed database-auth checks.
Passwords and configs may not change during installation; database volumes retain
their identity. App2's service, processes, files and version remain unchanged during
the first stage. Unselected core/app1 are protected during the second stage.
Sibling trust is compared across install and retirement; old own trust is removed
only after all stage checks succeed. A failed check retains old trust and stops.
The private `.upgrade-020.json` comparison file remains on the disposable prod VM;
normal run reports contain safe PASS/FAIL evidence, not its private hashes.

## Verification and remaining gate

Local verification: 185 product tests and 148 acceptance-harness tests pass.
Ruff lint/format, Pyright, Vermin (host/product tests require Python 3.6), Bash
syntax and ShellCheck checks pass. See the repository test READMEs for commands.

Actual VM/Podman/systemd/fapolicyd historical upgrade: **NOT RUN** in this environment.
Python 3.6 execution and the PyYAML 5.4.1 compatibility matrix were not rerun here;
Python 3.6 evidence for this change is static. No lab credentials/configuration
were supplied in this workspace. Existing runtime evidence remains valid only for
its documented runs; local harness tests do not extend it.

The local baseline is sufficient to proceed with review of the structural work.
Close the historical-upgrade verification gate with a CLEAN PASS from the command
above before claiming that retained 0.2.0 installations are operationally verified.
Items 8 and 9 still precede the deploy refactor; preserve the behavior established
by each step. If later structural changes alter the bundle model, adapt this pinned
historical scenario explicitly rather than removing its retained-data assertions.
