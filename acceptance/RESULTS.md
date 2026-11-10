# Latest acceptance results

This file holds only the latest real Podman/systemd results for the current
code. Each new run replaces its row. Older results, reports and fault analyses
are in the git history (`git log -- acceptance/`); they never count as evidence
for newer code.

## Product matrix

Run from a clean detached checkout. Each command resets the disposable VMs.
Require CLEAN PASS for every run and record the commit, step counts and the
OS/Podman versions from each run's `EVIDENCE.md`. The DEV source checks
(`03-host-path-safety`, `03-unit`, `03-database-runtime`, `03-dev-up`,
`03-dev-e2e`) do not depend on the scenario and run only in normal; the other
scenarios build only the images, the smoke-test venv and the registry fixture:

```sh
git rev-parse HEAD
test -z "$(git status --porcelain)" && echo clean
rev=$(git rev-parse --short HEAD)
python3 acceptance/acceptance.py --run "whoami-$rev" --whoami run
python3 acceptance/acceptance.py --run "normal-$rev" run
python3 acceptance/acceptance.py --run "app2-$rev" --first-app app2 run
python3 acceptance/acceptance.py --run "identity-$rev" --identity-only run
python3 acceptance/acceptance.py --run "help-$rev" --help-only run
python3 acceptance/acceptance.py --run "platform-help-$rev" --platform-help-only run
python3 acceptance/acceptance.py --run "renamed-$rev" --renamed-product run
```

| Scenario | Latest run | Steps | Result |
| --- | --- | --- | --- |
| `--whoami` | `whoami-9c85e2f` | 45 | CLEAN PASS |
| normal | `normal-9c85e2f` | 118 | CLEAN PASS |
| `--first-app app2` | `app2-9c85e2f` | 112 | CLEAN PASS |
| `--identity-only` | `identity-9c85e2f` | 52 | CLEAN PASS |
| `--help-only` | `help-9c85e2f` | 46 | CLEAN PASS |
| `--platform-help-only` | `platform-help-9c85e2f` | 25 | CLEAN PASS |
| `--renamed-product` | `renamed-9c85e2f` | 56 | CLEAN PASS |

All on `9c85e2f` (2026-11-09, one batch with both `--rpm-manual` runs below),
clean detached checkout, Oracle Linux Server 9.8 and Podman 5.8.2 on DEV and
PROD, no failed or skipped step; the step counts equal the previous matrix.
This commit is backlog 84 (environment-specific `ENVIRONMENT` overrides) with
its three review rounds, on top of `8cc668f`.

Backlog 84 in these runs: in normal, `03-database-runtime` ran the extended
`environment_update_test.py`: after a first `./dev/dev.sh up`, a variable
added to `config.defaults.yaml` and two overrides in `config/dev.yaml`'s
`overrides` block (one regular container, one `always` init container that
prints its value) reached the new containers with their exact values, the
common `EXISTING_SETTING` was kept and the generated secret was unchanged.
In normal and `--first-app app2`, `10-build-upgrade` built the app1 upgrade with `./build-bundle.sh
--environment lab app1` from an isolated checkout whose `config/lab.yaml`
overrides app1's `DEMO_CONFIG_LAYER`; it was delivered as a release RPM and
installed with `sudo myproduct-admin <directory>`. After the upgrade, PROD's
installed YAML and the running app1 backend had `environment-lab` (the
scenario's expectation, `seed_upgrade.LAYER`), app2 did not receive the
variable, the database held `release-v2`, and `10-persistent-after` found
config and credentials unchanged (only the public seed archive changed).
Before that upgrade, and in the scenarios without it, `healthy()` found the
release default `defaults` wherever app1 (or renamed's orders) was
installed, so builds without `--environment` behave as before. Not covered by the lab:
`./build-rpms.sh --environment <name>` (the harness wraps the copied archive
with `rpms.build_rpm`; the command has local tests only) and an interruption
and retry of an environment-built release.

As before, every scenario delivered its PROD releases as RPMs built on DEV and
installed them with `sudo myproduct-admin <directory>` (which also prepared
the host and retired older releases); the sibling checks found every
`deployment/` file of each sibling's installed version trusted through
`rpmdb` with the delivered RPM's size and digest, and every scenario's
release-protection probe ran as the runtime account and counted only
refusals. Every health step checked that each app container runs the image
its installed YAML names (`podman inspect`, `ImageName` only), and the help
and identity upgrades found the image tagged with their new `VERSION`.
Limit (product owner, 2026-11-08): the per-container image check shows
agreement between the installed YAML and the running container, not that the
YAML names the intended image; only help and identity are compared with the
scenario's own version. The runs also cover app3's trust chain through
`MOUNTS` secret files (`07-whoami-chain-mounts`, backlog 80), app2's database
password from a `MOUNTS` secret file with `POSTGRES_PASSWORD_FILE` in
`ENVIRONMENT` (`07-database-auth`, backlogs 82 and 83), install stopping for a
kept database volume without its password file and completing once it is
back (`07-password-guard`), and the init Secret probe in
`03-database-runtime`. The Ctrl+C message has local tests only (the lab's
interruption closes the terminal). The harness defects found on the way to
the earlier matrices are listed in
[backlog 78](../BACKLOG.md#78-keep-the-acceptance-harness-in-step-with-the-product).

## Other scenarios

| Scenario | Latest run | Steps | Result |
| --- | --- | --- | --- |
| `--status-retry` | `status-retry-9c85e2f` | 113 | CLEAN PASS |
| `--rpm-manual` (fapolicyd P1) | `rpm-manual-9c85e2f` | 58 | CLEAN PASS |
| `--rpm-manual --strict-fapolicyd` (P2) | `rpm-manual-p2-9c85e2f` | 59 | CLEAN PASS |

Status/retry: on `9c85e2f` (2026-11-10, after the matrix), clean detached
checkout, no failed or skipped step; OS and Podman versions were not
extracted from this run's `EVIDENCE.md`. A same-version failure stays pending
with the old container active, a plain retry completes, and the restore
leaves protected code unchanged.
The `--host-setup` scenario (the `release.py` manual) was removed in backlog
69 WP6; its last run is in the git history.

RPM manual (backlog 69 WP6): both on `9c85e2f` (2026-11-09), same checkout, OS
and Podman as the matrix; backlog 84 added one sentence to the manual and no
command. P1 is `clean-agent`, P2 the strict WP0 profile applied after the
reset (`strict_fapolicyd: true`). In both runs every operator step ran the
command block of `docs/PRODUCTION-INSTALL.md` literally (only its example
values replaced), with the answers typed at the prompts and the runtime user
logged in over real SSH without sudo: the tools with `dnf`; the admin command
stopping in preflight with nothing changed while the account was missing,
then installing and preparing the host, and an unchanged repeat; plain
`dnf remove`/`rpm -e` refused; `myproduct` stopping on the missing web
credentials, `--credentials` (kept on a repeat, a different file refused),
then platform and help installed without new questions, a repeat restarting
nothing and `myproduct help` restarting only help; credentials sent with
`scp`, the warning of plain `myproduct` and `myproduct platform` taking them;
a newer help delivered and the older one kept, `myproduct` interrupted once
podman had loaded the new image and completed in a fresh login; the next
admin run removing the older help and its tree with the guard still closed;
with a tools module removed, the documented symptom, `rpm -q`, the documented
reinstall and a working admin command; the journal lines for sharing; no
FANOTIFY/AVC event. Not covered: mounting a medium, the restart after newer
tools.

The protected-release and production-layout matrices and the RPM prototype
have no run on the current code; their last runs are in the git history. The
AI operator walkthrough is [OPERATOR-REVIEW.md](OPERATOR-REVIEW.md); the
unassisted human trial (backlog 68) is outstanding.
