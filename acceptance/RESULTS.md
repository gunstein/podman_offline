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
| `--whoami` | `c69c-whoami-14491ae` | 46 | CLEAN PASS |
| normal | `c69c-normal-14491ae` | 117 | CLEAN PASS |
| `--first-app app2` | `c69c-app2-14491ae` | 117 | CLEAN PASS |
| `--identity-only` | `c69c-identity-14491ae` | 57 | CLEAN PASS |
| `--help-only` | `c69c-help-14491ae` | 52 | CLEAN PASS |
| `--platform-help-only` | `c69c-platform-help-14491ae` | 31 | CLEAN PASS |
| `--renamed-product` | `c69c-renamed-14491ae` | 57 | CLEAN PASS |

All on `14491ae` (2026-11-02), clean detached checkout, Oracle Linux Server
9.8 and Podman 5.8.2 on DEV and PROD, no failed or skipped step. This commit
includes backlog 69 WP1/WP2 (`prepare-host.sh` creates `incoming/`) and the
stricter checks of `14491ae`: the wrong report password must be refused by
PostgreSQL, the inline endpoint is compared with the scenario's address, and
`--renamed-product` asks the running Identity to refuse the removed client.
An earlier attempt on this commit (`c69b-*`) stopped at `00-readiness`
(DEV unreachable) before any VM change. The init Secret probe runs
inside `03-database-runtime` and `03-renamed-generate`, so these runs cover
it. The harness defects found on the way to this matrix are listed in
[backlog 78](../BACKLOG.md#78-keep-the-acceptance-harness-in-step-with-the-product).

## Other scenarios

| Scenario | Latest run | Steps | Result |
| --- | --- | --- | --- |
| `--status-retry` | `c69c-status-retry-14491ae` | 118 | CLEAN PASS |
| `--host-setup` | `c69c-host-setup-14491ae` | 36 | CLEAN PASS |
| `--admin-rpm` | `c69c-admin-rpm-14491ae` | 20 | CLEAN PASS |

Same commit, date, checkout, OS and Podman as the matrix. Status/retry: a
same-version failure stays pending with the old container active, a plain
retry completes, and the restore leaves protected code unchanged. Host setup:
procedure and evidence in [HOST-SETUP.md](HOST-SETUP.md). Admin RPM (backlog
69 WP2): DEV built the platform, help and tools RPMs; on PROD the tools
installed with `dnf`, `myproduct-admin` stopped in preflight before any change
while the account was missing, then installed both releases in one offline
transaction, prepared the host, ran each release as the runtime account
(fapolicyd trust), repeated unchanged without options, copied credentials into
`incoming/` as the account and refused a different file; `dnf remove` and
`rpm -e` of a release and of the tools were refused; no FANOTIFY/AVC event.
Not covered: the restart after newer tools, and any runtime installation
(WP3).

The protected-release and production-layout matrices and the RPM prototype
have no run on the current code; their last runs are in the git history. The
AI operator walkthrough is [OPERATOR-REVIEW.md](OPERATOR-REVIEW.md); the
unassisted human trial (backlog 68) is outstanding.
