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
| `--whoami` | `whoami-9c00aca` | 48 | CLEAN PASS |
| normal | `normal-9c00aca` | 118 | CLEAN PASS |
| `--first-app app2` | `app2-9c00aca` | 112 | CLEAN PASS |
| `--identity-only` | `identity-9c00aca` | 52 | CLEAN PASS |
| `--help-only` | `help-9c00aca` | 46 | CLEAN PASS |
| `--platform-help-only` | `platform-help-9c00aca` | 25 | CLEAN PASS |
| `--renamed-product` | `renamed-9c00aca` | 56 | CLEAN PASS |

All on `9c00aca` (2026-11-10, one batch of ten runs with `--status-retry`
and both `--rpm-manual` runs below), clean detached checkout of
`claude/compassionate-wright-mzz19z`, Oracle Linux Server 9.8 and Podman
5.8.2 on DEV and PROD, no failed or skipped step. This commit is backlog 85's
revised model (component selection and `ENVIRONMENT` overrides applied on
the target from `state/<environment>.yaml`; neutral bundles and RPMs; the
product owner's option C) with its review rounds, on top of backlog 84.
`--whoami` has 48 steps (45 before, for the environment file); the other
matrix step counts are unchanged.

Backlog 84/85 in these runs:

- `--whoami`: the bundles were built without an environment. The demo's
  `config/whoami.yaml` (components platform, identity and app3, and
  Identity's override with app3's API registration) was copied to PROD and
  placed as the runtime account in the state directory
  (`06-environment-file`, `06-whoami-environment`) before any install.
  Every PROD install used `--environment whoami`. Then `whoami-api-registration`
  found Identity's installed `api_secrets` naming app3. app3's own
  generated secret, its registration (`state/apis/app3/value`) and the key
  of Identity's installed `identity-apis` Secret were the same bytes.
- normal and `--first-app app2`: the app1 upgrade was a neutral bundle.
  Before its validate and install, `upgrade` placed a `lab` environment
  file on PROD (components platform, identity, app1, app2 and help, and
  app1's `DEMO_CONFIG_LAYER: environment-lab`), and every later install of
  the run used `--environment lab`. After the upgrade, PROD's installed YAML
  and the running app1 backend had `environment-lab`, app2 did not receive
  the variable, the database held `release-v2`, and `10-persistent-after`
  found config and credentials unchanged. Before it, and in the scenarios
  without it, `healthy()` found the release default `defaults`.
- In normal, `03-database-runtime` ran `environment_update_test.py`: dev's
  `config/dev.yaml` `overrides` block (unchanged by backlog 85) reached a
  regular and an `always` init container with their exact values.

Not covered by the lab (product and harness tests only): a plain
`myproduct` after an environment install with an upgraded API (option C:
refused, nothing changed), another API secret line in Identity for the same
version, a pending API install with a changed environment file, and the
refusal of invalid environment records.

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
| `--status-retry` | `status-retry-9c00aca` | 113 | CLEAN PASS |
| `--rpm-manual` (fapolicyd P1) | `rpm-manual-9c00aca` | 63 | CLEAN PASS |
| `--rpm-manual --strict-fapolicyd` (P2) | `rpm-manual-p2-9c00aca` | 64 | CLEAN PASS |

Status/retry: on `9c00aca` (2026-11-10, in the same batch), clean detached
checkout, OS and Podman as the matrix, no failed or skipped step. A same-version failure stays pending
with the old container active, a plain retry completes, and the restore
leaves protected code unchanged.
The `--host-setup` scenario (the `release.py` manual) was removed in backlog
69 WP6; its last run is in the git history.

RPM manual (backlog 69 WP6): both on `9c00aca` (2026-11-10), same checkout, OS
and Podman as the matrix. Five steps more than before, for backlog 85's manual
steps 6, 7 and 9. P1 is `clean-agent`, P2 the strict WP0 profile applied after the
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
FANOTIFY/AVC event. Backlog 85, with the manual's blocks:
- the first delivery was `./build-rpms.sh platform help` with exactly those
  two release RPMs and the tools RPM in `dist/delivery/`;
- the help upgrade came from its own `dist/release-help-<version>/`;
- `prod1.yaml` (`components: [platform, help]`) was copied with the
  manual's `scp` line;
- `myproduct --environment prod1` checked it in both releases ("fits
  environment prod1");
- `./deploy.sh uninstall` in help's release removed help with its data
  kept;
- the same environment command then stopped with help still listed;
- `myproduct --environment prod1 help` installed it again.

Not covered: mounting a medium, the restart after newer tools.

The protected-release and production-layout matrices and the RPM prototype
have no run on the current code; their last runs are in the git history. The
AI operator walkthrough is [OPERATOR-REVIEW.md](OPERATOR-REVIEW.md); the
unassisted human trial (backlog 68) is outstanding.
