# Production layout outside the login home (backlog 64)

Implemented on `claude/friendly-mendel-8u3bqs`, built on the unmerged item 54
branch `feature/protected-releases` (`f72d520`) merged with `main` (`22b9134`).
**The full automated OL9/SELinux/fapolicyd matrix passed CLEAN on `5b8ab69`**
(merged to `main`; six scenarios, see "Recorded results"). The manual checks
listed below (runtime without cached sudo, the
[operator guide](../docs/PRODUCTION-INSTALL.md)'s literal commands on a fresh
host, a small separate `/home`) are still open, so the layout is not yet ready
for a customer installation. Earlier lab evidence (items 46, 54, 61) used the
service-home layout and does not verify this change.

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

## Real OL9 scenarios

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
  downgrade refusal, scoped uninstall, and the renamed product;
- `check` (also after reboot without interactive login): the user manager's
  `XDG_*`, every unit's `SourcePath` under `config/containers/systemd`, the
  Podman graphroot and container layers under `storage/`, private modes,
  SELinux labels, no AVC/FANOTIFY;
- `home-unchanged` after reboot and at the end: no product writes in the home;
- `host-path-safety`: real separate-UID link refusal under `config/`.

Not covered by an automated step: see the list after "Recorded results"
(no cached sudo, the guide's literal commands, OL9 failure/retry, logout, a
small `/home`). Record those manually.

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

Review follow-up (2026-10-23, after `75c49e3`):

| Finding | Fix | Regression |
| --- | --- | --- |
| A repeated `prepare-host.sh` did not activate a drop-in written by an interrupted run | Activation now reads the running manager's `show-environment`, starts or restarts it until both `XDG_*` values are present, and fails otherwise | `HostUserManagerTests` (interrupted repeat, no needless restart, start when stopped, failure when still wrong); three of these failed against `75c49e3` |
| `release_safety_test.py` used the product name as the runtime account (`07-release-safety` would stop on a clean lab host) | The account is a separate fourth argument from `remote.sh` (`$service_user`), used for `getpwnam` and `sudo -u` | `test_release_safety.py` asserts `shop-ops` for both and the `remote.sh` argument |
| The shipped guide linked the PFX guide, ARCHITECTURE and this report, none in the bundle | Bundles ship `bundle.RELEASE_DOCS` (guide and PFX guide); the guide names source-only documents without links and explains offline delivery of `generate-certificates.sh` | `test_bundle_demo.py` requires every relative link in shipped documents to resolve inside the release (failed against the old guide); `test_wrappers.py` checks both files ship |

Tests that previously needed `chown` when run as root (`test_layout.py`,
`test_wrappers.py`) now replace only deploy's effective UID, so they also run
where root lacks `CAP_CHOWN`. `home` parameters that meant the state directory
are renamed `state` in `catalog.py` and `registrations.py`.

Follow-up results, same environment: `tests/run.py all` 499 OK (1 skipped);
`platform --isolate` 433 OK; harness 242 OK; ruff, pyright, vermin and
shellcheck as above (the same 12 pre-existing ruff findings).

An operator run on Ubuntu (umask 0002) failed one item 54 unit test because its
fixture created the protected anchor without an explicit mode; the fixture now
sets 0755, and `tests/run.py all` passes under both umask 0002 and 0022.

Real OL9 runs (record each with run ID, commit, verdict and the manual checks
above):

| Run | Commit | Verdict | Notes |
| --- | --- | --- | --- |
| `layout64-20261023-1628-app1` | `2373cba` | **CLEAN PASS** (126 steps) | Runtime account `myproduct-ops`, home 0555, `/home` on its own 18 GB volume. Install of platform, identity, app1, app2, help; host-path- and release-safety; `07-check`, `09-check-after-reboot` (new boot ID, no interactive login), `10-check-upgrade` and `10-check-uninstall`: the generator loaded every Quadlet from `/var/lib/myproduct/config/containers/systemd`, policy/labels classified, no AVC/FANOTIFY, no pull attempts. Stop/start/restart/crash/hang, help/app1/platform/identity upgrades with all 44 persistent state files unchanged, downgrade refusal, scoped app1 uninstall. `09-home-unchanged` and `10-home-unchanged` PASS. |
| `layout64-20261023-1651-renamed` | `2373cba` | **CLEAN PASS** (57 steps) | Product `shop`, account `shop-ops`, root `/var/lib/shop` (prepare-host output). Renamed install of gateway, login-service, orders, inventory, manual; host-path- and release-safety; init-container check; restart, redeploy, registration removal, scoped uninstalls; `10-home-unchanged` PASS. This scenario has no `check` or reboot step, so `SourcePath`/graphroot after reboot are verified only for `myproduct`. |
| `layout64-20261023-1607-app1` | `1eba4d4` | NOT CLEAN at `09-home-unchanged` | Every step through `09-markers-after-reboot` passed: prepare-host, install of all components, host-path-safety, release-safety as `myproduct-ops`, `check` (manager `XDG_*`, `SourcePath` and graphroot under `/var/lib/myproduct`, no AVC/FANOTIFY), restart/crash/hang, reboot without login and database-auth. The inventory diff was empty; the step then ran `du` without sudo on the home, which cannot read the 0700 `.myproduct` (harness defect, exit 1). Upgrades, uninstall and `10-home-unchanged` did not run. |

Full matrix from `main` at `5b8ab69` (operator-supplied summaries, 2026-10-23;
evidence under `~/podman-offline-acceptance-runs/<run>/EVIDENCE.md` on the
controller):

| Run | Verdict |
| --- | --- |
| `main-20261023-1731-app1` | CLEAN PASS, 125/125 |
| `main-20261023-1731-app2` | CLEAN PASS, 125/125 |
| `main-20261023-1731-renamed` | CLEAN PASS, 57/57 |
| `main-20261023-1731-plathelp` (`--platform-help-only`) | CLEAN PASS, 39/39 |
| `main-20261023-1731-help` (`--help-only`) | CLEAN PASS, 60/60 |
| `main-20261023-1731-identity` (`--identity-only`) | CLEAN PASS, 66/66 |

In every scenario with a `check` step (app1, app2, help, identity) the check
reported `user manager, generated units and Podman graphroot use
/var/lib/myproduct`, owner `myproduct-ops` and modes 0700/0644/0600 on
`config/`, `state/` and the Quadlet files, and the generator loaded them from
`/var/lib/myproduct/config/containers/systemd`; app1 and app2 did so again after
reboot, upgrade and uninstall. `home-unchanged` passed in every scenario that
has it. The renamed scenario still has no `check` or reboot step.

The `du` call is removed (the inventory already records sizes through sudo);
`test_home_unchanged_reads_the_private_home_only_through_sudo` runs the step
with a 0700 bootstrap folder and fails on any unprivileged read of the home
(it failed against `1eba4d4`).

Not covered by these runs (record manually before operator use): the runtime
account's commands in its own ssh login (done manually once, see "Manual run";
not automated, backlog 67), the guide's literal command sequence on a fresh
host (not achieved: the manual run needed extensive help), a deliberate failed
operation followed by a fresh-process retry on OL9 (covered only by local
tests), logout as distinct from reboot, and a small separate `/home` (the lab
`/home` is an 18 GB volume, so it does not prove behaviour on a nearly full
home).

## Manual run as `produser` over ssh (2026-10-23)

Operator-run on PROD (`todo-standby`, OL9), administrator `gunstein` with sudo,
runtime account `produser` (UID 1001) created for the test without sudo
(`sudo -l -U` output not captured). Bundles from `main-20261023-1731-app1`;
release and certificate tools from `5b8ab69`. Platform and identity 0.4.12,
then platform 0.4.13. Results are taken from the terminal output the operator
shared; no machine-readable report exists.

Administrator: checksums, independent hash check of tools and key, protected
tool copies in `/usr/local/libexec`, `provision-key`, signed `prepare` of both
releases (`integrity=none`), `prepare-host.sh --port 8443 --user produser`.
`produser`, in its own ssh login without sudo or manual `XDG_*` exports:
bootstrap file, `init-config`, new lab certificates under `state/`,
`validate`/`install` of platform and identity, `systemctl --user`, restart,
logout, reboot before login, platform upgrade, and operation after `retire`.

| Check | Result |
| --- | --- |
| Install platform / identity | 1 and 2 containers running and healthy |
| `systemctl --user` in a real ssh login | worked without exports |
| `journalctl --user` | **failed first** (see below); worked after the admin fix and after reboot |
| Logout; reboot before `produser` logged in | both services active |
| `show-environment`, `SourcePath`, GraphRoot (also after reboot) | `/var/lib/myproduct/config`, `.../config/containers/systemd/*.kube`, `/var/lib/myproduct/storage/containers/storage` |
| HTTPS with test CA and `--resolve` | `/livez` 204, `/identity/.well-known/openid-configuration` 200, before and after upgrade; `/identity/` 404 |
| Platform upgrade | healthy; identity kept running; platform config and TLS file hashes unchanged |
| `retire` of old platform | `PASS: protected release retire`; services active |
| `find ~ -newer ~/.myproduct/myproduct.env` | only `.lesshst`, `.bash_history` |

**Journal finding.** On the fresh host `/var/log/journal` did not exist
(default `Storage=auto`, `SplitMode=uid`), only the runtime system journal, so
`journalctl --user` reported `No journal files were opened due to insufficient
permissions`. The administrator ran `mkdir -p /var/log/journal`,
`systemd-tmpfiles --create --prefix /var/log/journal` and `journalctl --flush`;
after one service restart the user journal worked, also after reboot. No group
was added to `produser`. The automated harness did not catch this because it
reads logs through the administrator. The guide now lists it as an explicit
administrator prerequisite; making it part of host preparation and detecting it
automatically are backlog 65 and 67.

**Usability finding.** The run needed extensive step-by-step help: which
machine and account each command runs on, where signed bundles come from, the
key/tool bootstrap, `sms`/`sts` versus `myproduct`/`identity`, PEM versus PFX
credentials for the demo identity, and a wildcard in an assisted command
(`sudo chown ... /var/tmp/myproduct-inn/*`) that the admin shell could not
expand in the root-only directory. The operator's verdict: host preparation must
be much simpler. The guide therefore is **not** verified as followed literally,
and the flow is not customer-ready. The guide now states where commands run,
shows a concrete transfer, the journal prerequisite and a precise HTTPS check;
the larger simplification is backlog 65 and 66.

Not covered by this run: SELinux/fapolicyd audit collection, a deliberate
failure and retry, a small or nearly full `/home`, browser OIDC sign-in, a full
persistent-state comparison or full home inventory, and the customer's private
images.

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
