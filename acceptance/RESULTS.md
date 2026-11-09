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
| `--whoami` | `whoami-ee5e270-20261109-162355` | 45 | CLEAN PASS |
| normal | `normal-ee5e270-20261109-162355` | 118 | CLEAN PASS |
| `--first-app app2` | `app2-ee5e270-20261109-162355` | 112 | CLEAN PASS |
| `--identity-only` | `identity-ee5e270-20261109-162355` | 52 | CLEAN PASS |
| `--help-only` | `help-ee5e270-20261109-162355` | 46 | CLEAN PASS |
| `--platform-help-only` | `platform-help-ee5e270-20261109-162355` | 25 | CLEAN PASS |
| `--renamed-product` | `renamed-ee5e270-20261109-162355` | 56 | CLEAN PASS |

All on `ee5e270` (2026-11-09, one batch, run IDs ending `-20261109-162355`), clean
detached checkout, Oracle Linux Server 9.8 and Podman 5.8.2 on DEV and PROD,
no failed or skipped step. This commit is the RPM branch (backlog 69 WP1-WP6
and both review follow-ups) with main merged, with RPM payloads at zstd
level 3, the DEV source checks only in normal (`2384eee`; each other
fixed-flow scenario has six steps fewer than with them, and renamed, whoami
and both RPM manual runs one fewer, `03-host-path-safety`) and the
operator-message fixes of the item 68 procedure verification (`40b37c4`): no
run recorded firewalld's `ALREADY_ENABLED` warning, which every earlier run
had. The Ctrl+C message has local tests only (the lab's interruption closes
the terminal). In these runs every scenario delivered its PROD releases as RPMs built on DEV and
installed them with `sudo myproduct-admin <directory>` (which also prepared
the host and retired older releases), and the sibling checks found every
`deployment/` file of each sibling's installed version trusted through
`rpmdb` with the delivered RPM's size and digest. Every scenario's
release-protection probe, whoami's included, proved it ran as the runtime
account and found its target, and counted only refusals. With zstd level 3
the transfer steps (`05-*`, where DEV builds the release RPMs) took 1252 s
over 24 steps in all ten runs.
Backlog 63: the demo manifests take their images from
`config/images.yaml` (`REGISTRY`, `LOCAL_REGISTRY` and version variables) and
help and identity from `@@COMPONENT_VERSION@@`. Every health step checked
that each app container runs the image its installed YAML names (`podman
inspect`, `ImageName` only), and the help and identity upgrades found the
image tagged with the new `VERSION` (`localhost/demo-help:0.4.15`,
`localhost/demo-identity:0.4.16`); the release builders changed only
`VERSION`. Limit (product owner, 2026-11-08): the per-container image check
shows agreement between the installed YAML and the running container, not
that the YAML names the intended image; only help and identity are compared
with the scenario's own version. These runs also cover the earlier items: app3's trust chain through
`MOUNTS` secret files (`07-whoami-chain-mounts`, backlog 80); app2's database
password from a `MOUNTS` secret file with `POSTGRES_PASSWORD_FILE` in
`ENVIRONMENT` (`07-database-auth`, backlogs 82 and 83); install stopping for
a kept database volume without its password file, and completing once it is
back (`07-password-guard`); and, in `03-database-runtime`, the init Secret
probe and `environment_update_test.py` (a new `ENVIRONMENT` variable reaches
the container on the next `./dev/dev.sh up`). The first attempt (`c63`) stopped at
`03-database-runtime` because `database_test.py` read source manifests
without resolving image variables; fixed in `d111718` with a regression test.
The harness defects found on the way to this matrix are listed in
[backlog 78](../BACKLOG.md#78-keep-the-acceptance-harness-in-step-with-the-product).

## Other scenarios

| Scenario | Latest run | Steps | Result |
| --- | --- | --- | --- |
| `--status-retry` | `status-retry-ee5e270-20261109-162355` | 113 | CLEAN PASS |
| `--rpm-manual` (fapolicyd P1) | `rpm-manual-ee5e270-20261109-162355` | 58 | CLEAN PASS |
| `--rpm-manual --strict-fapolicyd` (P2) | `rpm-manual-p2-ee5e270-20261109-162355` | 59 | CLEAN PASS |

Status/retry: same commit, date, checkout, OS and Podman as the matrix. A
same-version failure stays pending with the old container active, a plain
retry completes, and the restore leaves protected code unchanged. The
`--host-setup` scenario (the `release.py` manual) was removed in backlog 69
WP6; its last run is in the git history.

RPM manual (backlog 69 WP6): both on `ee5e270` (2026-11-09), same checkout, OS
and Podman as the matrix. P1 is `clean-agent`, P2 the strict WP0 profile
applied after the reset (`strict_fapolicyd: true`). In both runs every
operator step ran the command
block of `docs/PRODUCTION-INSTALL.md` literally (only its example values
replaced), with the answers typed at the prompts and the runtime user logged
in over real SSH without sudo: the tools with `dnf`; the admin command
stopping in preflight with nothing changed while the account was missing,
then installing and preparing the host, and an unchanged repeat; plain
`dnf remove`/`rpm -e` refused; `myproduct` stopping on the missing web
credentials, `--credentials` (kept on a repeat, a different file refused),
then platform and help installed without new questions (`/livez` 204,
`/help/` 200), a repeat restarting nothing and `myproduct help` restarting
only help; credentials sent with `scp`, the warning of plain `myproduct` and
`myproduct platform` taking them; help 0.4.14 delivered and the older help
kept, `myproduct` interrupted once podman had loaded the new image (help
still completed at 0.4.13) and completed in a fresh login with platform
running; the next admin run removing help 0.4.13 and its tree with the guard
still closed; with a tools module removed, the documented symptom, `rpm -q`,
the documented reinstall and a working admin command; the journal lines for
sharing; no FANOTIFY/AVC event. Earlier attempts: `af22327` stopped at the
last step (journalctl prints `prepare-host.sh`'s notice lines in bold in the
terminal; the check now reads the text an operator sees), `edd3be5` at the
interruption (its stop text is printed only by `validate`), `2fdd633` at the
check after the upgrade (credentials for an installed component were left
unused without a word; fixed in the runtime command and the manual). Not
covered: mounting a medium, the restart after newer tools.

The protected-release and production-layout matrices and the RPM prototype
have no run on the current code; their last runs are in the git history. The
AI operator walkthrough is [OPERATOR-REVIEW.md](OPERATOR-REVIEW.md); the
unassisted human trial (backlog 68) is outstanding.
