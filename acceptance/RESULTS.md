# Latest acceptance results

This file holds only the latest real Podman/systemd results for the current
code. Each new run replaces its row. Older results, reports and fault analyses
are in the git history (`git log -- acceptance/`); they never count as evidence
for newer code.

## Product matrix

Run from a clean detached checkout. Each command resets the disposable VMs.
Require CLEAN PASS for every run and record the commit, step counts and the
OS/Podman versions from each run's `EVIDENCE.md`:

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
| `--whoami` | `c63b-whoami-d111718` | 46 | CLEAN PASS |
| normal | `m69-normal-30704b3` | 118 | CLEAN PASS |
| `--first-app app2` | `c63b-app2-d111718` | 118 | CLEAN PASS |
| `--identity-only` | `c63b-identity-d111718` | 58 | CLEAN PASS |
| `--help-only` | `c63b-help-d111718` | 52 | CLEAN PASS |
| `--platform-help-only` | `c63b-platform-help-d111718` | 31 | CLEAN PASS |
| `--renamed-product` | `c63b-renamed-d111718` | 57 | CLEAN PASS |

Normal: on `30704b3` (2026-11-07), the RPM branch (backlog 69 WP1-WP4)
with main (backlogs 82, 83 and 63) merged; clean detached checkout, Oracle
Linux Server 9.8 and Podman 5.8.2 on DEV and PROD, no failed or skipped step.
The other rows: on `d111718` (main, 2026-11-07, backlog 63), same checkout
rules, OS and Podman, no failed or skipped step; not rerun on the RPM
branch, whose WP4 change touches no deploy code. Backlog 63: the demo manifests take their images from
`config/images.yaml` (`REGISTRY`, `LOCAL_REGISTRY` and version variables) and
help and identity from `@@COMPONENT_VERSION@@`. Every health step checked
that each app container runs the image its installed YAML names (`podman
inspect`, `ImageName` only), and the help and identity upgrades found the
image tagged with the new `VERSION` (`localhost/demo-help:0.4.15`,
`localhost/demo-identity:0.4.16`); the release builders changed only
`VERSION`. These runs also cover the earlier items: app3's trust chain through
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
| `--status-retry` | `c63b-status-retry-d111718` | 119 | CLEAN PASS |
| `--host-setup` | `c63b-host-setup-d111718` | 36 | CLEAN PASS |
| `--rpm-manual` (fapolicyd P1) | `rpm-manual-3bff57b` | 58 | CLEAN PASS |
| `--rpm-manual --strict-fapolicyd` (P2) | `rpm-manual-p2-3bff57b` | 59 | CLEAN PASS |

Status/retry and host setup: on `d111718`, with the matrix rows from main.
Status/retry: a
same-version failure stays pending with the old container active, a plain
retry completes, and the restore leaves protected code unchanged. Host setup:
procedure and evidence in [HOST-SETUP.md](HOST-SETUP.md).

RPM manual (backlog 69 WP6): both on `3bff57b` (2026-11-07), clean detached
checkout, Oracle Linux Server 9.8 and Podman 5.8.2 on DEV and PROD, no failed
or skipped step; P1 is `clean-agent`, P2 the strict WP0 profile applied after
the reset (`strict_fapolicyd: true`). This commit is the RPM branch (backlog
69 WP1-WP6 part 1) with main merged. Every operator step ran the command
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
sharing; no FANOTIFY/AVC event. Earlier attempts: `edd3be5` stopped at the
interruption (its stop text is printed only by `validate`), `2fdd633` at the
check after the upgrade (credentials for an installed component were left
unused without a word; fixed in the runtime command and the manual). Not
covered: mounting a medium, the restart after newer tools.

The protected-release and production-layout matrices and the RPM prototype
have no run on the current code; their last runs are in the git history. The
AI operator walkthrough is [OPERATOR-REVIEW.md](OPERATOR-REVIEW.md); the
unassisted human trial (backlog 68) is outstanding.
