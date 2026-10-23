# Production layout outside the login home (backlog 64)

Implemented on `claude/friendly-mendel-8u3bqs`, built on the unmerged item 54
branch `feature/protected-releases` (`f72d520`) merged with `main` (`22b9134`).
**Real OL9/SELinux/fapolicyd verification of this change is pending.** Until a
CLEAN PASS of the scenarios below is recorded here, the layout and the
[operator guide](../docs/PRODUCTION-INSTALL.md) are not ready for a customer
installation. Earlier lab evidence (items 46, 54, 61) used the service-home
layout and does not verify this change.

## What changed

- `deployment/layout.py` reads `~/.<product>/<product>.env` as private data and
  assigns `common.STATE`, `QUADLET_DIR` and `FILES_DIR` under
  `/var/lib/<product>`; `common.HOME` keeps only its identity meaning.
- `scripts/prepare-host.sh --user <existing account>` prepares the root-owned
  root, the account's `state/`, `config/`, `storage/`, SELinux equivalence,
  linger, port and the `user@<uid>` drop-in with `XDG_CONFIG_HOME`/`XDG_DATA_HOME`.
- `scripts/release.py` publishes under `/var/lib/<product>/releases`.
- Install/uninstall/init-config refuse a user manager whose `XDG_*` differ.
- Component bundles include `docs/PRODUCTION-INSTALL.md`.

Design and trust boundaries: [ARCHITECTURE](../ARCHITECTURE.md#production-paths-outside-the-login-home-backlog-64).

## Local evidence (2026-10-23)

| Evidence | Command | Result |
| --- | --- | --- |
| Product/unit, both groups | `python3 -B tests/run.py all` | see "Recorded results" |
| Platform, isolated copy | `python3 -B tests/run.py platform --isolate` | see "Recorded results" |
| Acceptance harness | `python3 -B -m unittest discover -s acceptance -p 'test_*.py'` | see "Recorded results" |
| Static checks | ruff check/format, pyright, vermin 3.6, shellcheck as in [tests](../tests/README.md) | see "Recorded results" |

Focused regressions:

- `tests/platform_tests/test_layout.py`: path assignment, missing file, malformed
  and command-like values (never executed, never echoed), private modes, symlinked
  and hardlinked files, writable/linked roots, unprepared account directories,
  product Quadlets left in the login home, user manager mismatch, and that source
  dev/validate never read the bootstrap file. The product is `orders` and the
  account home `operator-account`, so nothing repeats demo names.
- `tests/platform_tests/test_wrappers.py`: real bundle build, extraction and
  fresh-process `deploy` runs with the real `layout.select()`; the login home
  ends with only the bootstrap file, an unknown `$(touch ...)` setting is not
  executed, every production Podman call carries the installation `XDG_*` while
  bundle building carries none, the guide ships in the release, and dev prepare
  of a component with a route works without production paths (a defect found by
  the harness and reproduced before the fix).
- `tests/platform_tests/test_prepare_host.py`: explicit account and product
  independence, root/state link and foreign-owner refusal before chown/chmod,
  drop-in creation, idempotence, manager restart only on change, refusal of a
  changed drop-in or a second product.
- The embedded unprivileged helper keeps its item 46 race/link tests on the new
  tree (`config/cni` is the first account-replaceable directory).

These are mocked/simulated host checks; no Podman, systemd, SELinux or
fapolicyd ran.

## Real OL9 scenarios (pending)

Prerequisites as in [acceptance](README.md): disposable DEV/PROD snapshots
`clean-agent`, OL9 with SELinux Enforcing, active fapolicyd and firewalld.

```sh
python3 acceptance/acceptance.py --run layout64-app1 --first-app app1 run
python3 acceptance/acceptance.py --run layout64-renamed --renamed-product run
```

They exercise, with separate administrator (`sudo`) and runtime identities
(`myproduct-ops` / `shop-ops`, ordinary `/home` account with bash):

- signed protected publication into `/var/lib/<product>/releases` and exact trust;
- `prepare-host --user`, the bootstrap file written by the account, then the
  login home made read-only (0555) and its inventory recorded;
- first install in dependency order, init-container Secret/migration probes,
  HTTPS health, restart, crash/hang recovery, upgrades retaining data,
  failure/retry, scoped uninstall, and the renamed product;
- `check` (also after reboot without interactive login): the user manager's
  `XDG_*`, every unit's `SourcePath` under `config/containers/systemd`, the
  Podman graphroot and container layers under `storage/`, private modes,
  SELinux labels, no AVC/FANOTIFY;
- `home-unchanged` after reboot and at the end: no product writes in the home;
- `host-path-safety`: real separate-UID link refusal under `config/`.

Not yet covered by an automated step: a run without cached sudo for the runtime
account's own commands (the harness uses `sudo -u` as the lab user), the
operator guide's literal command sequence, and a host whose `/home` is a
separate small filesystem. Record those manually with the first lab run.

## Recorded results

Local, 2026-10-23, Python 3.13 container without Podman/systemd/SELinux
(the final commit of this change on `claude/friendly-mendel-8u3bqs`):

| Evidence | Result |
| --- | --- |
| `python3 -B tests/run.py all` | 494 tests OK (1 skipped, unchanged) |
| `python3 -B tests/run.py platform --isolate` | 429 tests OK |
| Acceptance harness (`unittest discover -s acceptance`) | 240 tests OK |
| `ruff format --check` (documented paths) | 137 files formatted |
| `ruff check` (documented paths) | 12 findings, all in the three unchanged item 61 files noted under item 54 |
| `pyright` (documented paths) | 0 errors |
| `vermin -t=3.6-` | minimum 3.6 |
| `shellcheck` (documented scripts) | clean |

Baseline before this change (merge of `main` and item 54): 411 isolated platform
tests and 240 harness tests passed. The harness found one product defect (dev
prepare of a routed component needed the unset Quadlet directory); it is fixed
with a wrapper regression that failed before the fix.

Real OL9 runs: **none yet**. Record each with run ID, commit, verdict and the
manual checks above.

## Understandability review

- Authoritative inputs: the release descriptor (product), the account database
  (identity home) and the bootstrap file (installation root). `layout.select()`
  is the one function that turns them into `common.STATE`, `QUADLET_DIR`,
  `FILES_DIR` and Podman's `XDG_*`; it runs once per production command from
  `deploy.service_user()`, never in source dev or bundle building.
- Before writes: the bootstrap file, root ownership chain and account
  directories (all commands, validate included), then the user manager's
  environment (lifecycle only, a read-only `systemctl --user show-environment`).
  Validate still runs no host command.
- Side effects stay where they were: `install_component_plan()` and
  `uninstall()` write only below `STATE`/`QUADLET_DIR`; the root helper and
  `prepare-host.sh` own every privileged change and never read the user file.
- Successful install traced: `service_user()` → `select()` → `check_user_manager()`
  → unchanged `install_checks()`/staging/`install_component_plan()`, writing
  `state/metadata`, `state/routes`, `config/containers/systemd/*.kube` and
  finally `state/installed/<id>`; systemd's generator reads the same `config/`
  through the drop-in.
- Failure/retry traced: a failed restart leaves `state/pending-operation.json`;
  a fresh `bash ./deploy install` re-runs `select()` with the same bootstrap file,
  finds the record in the same `STATE` and resumes owner work exactly as before.
  A missing/changed bootstrap file or drop-in stops before reading that record.
- Remaining complexity: production paths are module globals assigned at command
  start (kept because every lifecycle function already reads them; tests replace
  `layout.select` and set them directly). `catalog.state_paths()` was split from
  `component_paths()` so dev never needs Quadlet paths. No new mode flags.
