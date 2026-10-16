# Remove obsolete layout checks (0.4.5)

Backlog item 15 removes detection/refusal of former core and combined
platform/Identity layouts. No existing installations require migration. The
supported layout remains five separate components, with persistent config,
credentials and data retained during normal upgrades/repeated installs.

## Changes

- `deployment/deploy.py`: removed `reject_legacy_layout()`,
  `reject_combined_platform()`, `legacy_volume_exists()` and their lifecycle/dev
  call sites. No historical paths, markers, generated systemd units or volumes
  are searched before init-config/install/uninstall/prepare.
- `deployment/cli.py`: removed the special core-rename diagnostic. Init-config
  validates names against the current component set; invalid names use the
  ordinary usage error before host commands. Supported root commands are intact.
- `dev/dev.sh`: retained current database preflight, removed historical preflight.
- `scripts/generate-certificates.sh`: removed old-layout scans/volume queries
  and special migration messages. Component certificate preparation no longer
  needs Podman. Existing certificate/password bytes, modes and incomplete-pair
  checks are unchanged.
- `acceptance/acceptance.py`, `remote.sh`: retired the old-layout refusal
  scenario and its CLI option. Removed `legacy_refusal.py`, the orchestration
  that asserted the now-removed current behavior. The current runner also no
  longer advertises the rejected historical `--upgrade-020` flag; unknown flags
  fail through argparse before creating a run or contacting/resetting the lab.
- Tests drop the obsolete refusal assertions/stubs and retain current safety
  checks. Added coverage confirms fresh/repeated config initialization needs no
  obsolete Podman query; certificate tests use a Podman stub that would fail if
  invoked. The no-database wrapper fixture now expects no host commands during
  prepare. The real dev preflight still checks exactly three database volumes.
- README, ARCHITECTURE and test/acceptance guides explain current behavior.
  VERSION, PLATFORM_VERSION and IDENTITY_VERSION are 0.4.5 because all bundles
  ship the changed lifecycle/certificate tools. Images/manifests are unchanged.

Database preflight (including missing password + existing volume refusal),
dependency/version contracts, credential generation, private/symlink-safe output,
pending-operation validation, retry acknowledgments, scoped volume deletion,
bundle/checksum protections and SELinux/fapolicyd setup were not replaced or
weakened. Their existing product/harness tests remain.

There is no migration, old-layout fallback, alias, compatibility branch or new
procedure to clean up or move old state. Removing a detector does not relocate, delete or
change any historical files/volumes. No old names were replaced with current
volume names in those checks; the checks themselves were deleted.

## Deliberately retained historical references

- `acceptance/upgrade_020.py`, `upgrade_020_guest.py` and `test_upgrade_020.py`
  are unchanged historical 0.2.0 fixtures/tests, pinned to genuine old sources.
  Their old paths, volumes and manual config-upgrade logic are not part of the
  current deploy/CLI. Historical runs require the documented checkout at
  `511099e`; they are not a current migration feature.
- `legacy-build`, `legacy-install` and `legacy-retire` blocks in `remote.sh`
  remain byte-for-byte unchanged for those explicit historical fixtures. The
  removed `legacy-refusal` action was an assertion about current deploy behavior.
- Earlier verification/evidence reports, including PLATFORM-RENAME.md,
  IDENTITY-SPLIT.md, CREDENTIAL-PATHS.md and DEPLOY-REFACTOR.md, are unchanged.
  Their old refusal/results describe those releases, not 0.4.5.
- BACKLOG keeps original completed task messages as history, with item 15 marked
  implemented. Migration items 4/11 remain superseded. Item 18 was already
  requested locally and is retained as planned work, not implemented here.
- `core-dump` is an external systemd result string, not a component name; its
  diagnostic test remains. Harness tests mention the retired flags only to prove
  ordinary unknown-option handling cannot start a lab operation.

## Verification and limits

Executed on 2026-10-16 with Python 3.12.14 / PyYAML 6.0.3:

| Check | Result |
| --- | --- |
| Product tests | 222 passed |
| Acceptance-harness tests | 160 passed |
| Ruff lint / format | passed, 52 Python files |
| Pyright | 0 errors, 0 warnings |
| Vermin | minimum Python 3.6 for host tools/product tests |
| ShellCheck | passed for all documented shell entry points |
| git diff --check | passed |

The previous baseline had 229 product tests / 162 harness tests. Eight obsolete
product refusal tests were removed and one focused config test added; three
old-boundary harness tests became one unknown-option safety test. The decrease
does not remove database preflight, current version/downgrade, pending-state,
credential preservation or scoped-deletion coverage. The wrapper regression was
updated for the intentional absence of old-volume queries.

An AST comparison of the lifecycle module shows only three deleted functions
and changes to init_config/install_components/prepare_components/uninstall,
where their obsolete calls or special core diagnostic were removed. The
database-preflight and pending/retry helper bodies are unchanged.

Product and acceptance-harness checks run locally with host transport stubbed;
they do not prove real Podman/systemd behavior. No application/image change,
lab VM reset, existing credential regeneration or database cleanup was performed.
The current fresh install/app orders, shared upgrades, persistence, retry and
scoped uninstall matrix remains the target verification path. Previous lab
results are not verification of this change.

Python 3.6 compatibility is checked statically with the project's vermin setup;
this workspace has no Python 3.6 runtime or second PyYAML version. Real
Podman/SELinux/fapolicyd verification remains pending in the authorized lab.
