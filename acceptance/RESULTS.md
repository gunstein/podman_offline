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
| `--admin-rpm` | `m69-admin-rpm-b5b86d9` | 31 | CLEAN PASS |
| `--rpm-manual` (P1, P2) | none yet | | outstanding |

Status/retry and host setup: on `d111718`, with the matrix rows from main.
Admin RPM: the WP2-WP5 scenario, replaced by `--rpm-manual` (backlog 69 WP6), which has no run yet; on `b5b86d9` (2026-11-07), clean detached checkout, Oracle Linux
Server 9.8 and Podman 5.8.2 on DEV and PROD, no failed or skipped step; this
commit adds backlog 69 WP5 (the RPM manual) to `30704b3`, including the
changed `prepare-host.sh` and admin/runtime messages, which the normal run
does not cover. Status/retry: a
same-version failure stays pending with the old container active, a plain
retry completes, and the restore leaves protected code unchanged. Host setup:
procedure and evidence in [HOST-SETUP.md](HOST-SETUP.md). Admin RPM (backlog
69 WP2): DEV built the platform, help and tools RPMs; on PROD the tools
installed with `dnf`, `myproduct-admin` stopped in preflight before any change
while the account was missing, then installed both releases in one offline
transaction, prepared the host, ran each release as the runtime account
(fapolicyd trust), repeated unchanged without options, copied credentials into
`incoming/` as the account and refused a different file; `dnf remove` and
`rpm -e` of a release and of the tools were refused. Then, as the runtime
account in a login-like environment (WP3), `myproduct` with
`--public-origin`/`--ip-address` installed platform and help (`/livez` 204,
`/help/` 200, the web certificate moved from `incoming/` to `state/`), an
unchanged repeat restarted nothing, and `myproduct help` restarted only help;
no FANOTIFY/AVC event. Retirement (WP4): DEV built help 0.4.14 and its RPM;
`myproduct-admin` installed it and kept `myproduct-help-0.4.13` as the
installed version (read from the newest release's `status --json` as the
runtime account), `myproduct` installed help 0.4.14 without restarting
platform and `/help/` served the new content, and the next
`myproduct-admin` removed `myproduct-help-0.4.13` and its tree, left no erase
authorization, removed nothing on a repeat, and a plain `rpm -e` of 0.4.14
was still refused. The first attempt on `f09d677` stopped at
`09-runtime-upgrade` on a harness defect (`invocations | grep -q` under
`pipefail`), fixed in `30704b3` with a regression test. Not covered: the restart after newer tools, and a real SSH
login running `myproduct` (WP6).

The protected-release and production-layout matrices and the RPM prototype
have no run on the current code; their last runs are in the git history. The
AI operator walkthrough is [OPERATOR-REVIEW.md](OPERATOR-REVIEW.md); the
unassisted human trial (backlog 68) is outstanding.
