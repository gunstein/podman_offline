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
| `--whoami` | `c80-whoami-a6197bf` | 46 | CLEAN PASS |
| normal | `c80-normal-a6197bf` | 117 | CLEAN PASS |
| `--first-app app2` | `c80-app2-a6197bf` | 117 | CLEAN PASS |
| `--identity-only` | `c80-identity-a6197bf` | 57 | CLEAN PASS |
| `--help-only` | `c80-help-a6197bf` | 52 | CLEAN PASS |
| `--platform-help-only` | `c80-platform-help-a6197bf` | 31 | CLEAN PASS |
| `--renamed-product` | `c80-renamed-a6197bf` | 57 | CLEAN PASS |

All on `a6197bf` (2026-11-02), clean detached checkout, Oracle Linux Server
9.8 and Podman 5.8.2 on DEV and PROD, no failed or skipped step. This commit
includes backlog 80: app3's trust chain is mounted from its Secret through
`MOUNTS` secret files, and `07-whoami-chain-mounts` found both files in the
running backend with the environment's CA and as read-only mounts
(`podman inspect`); the Secret key check now runs before the first write of
`prepare` and `install`. The init Secret probe runs
inside `03-database-runtime` and `03-renamed-generate`, so these runs cover
it. The harness defects found on the way to this matrix are listed in
[backlog 78](../BACKLOG.md#78-keep-the-acceptance-harness-in-step-with-the-product).

## Other scenarios

| Scenario | Latest run | Steps | Result |
| --- | --- | --- | --- |
| `--status-retry` | `c80-status-retry-a6197bf` | 118 | CLEAN PASS |
| `--host-setup` | `c80-host-setup-a6197bf` | 36 | CLEAN PASS |
| `--admin-rpm` | `admin-rpm-14a8114` | 25 | CLEAN PASS |

Status/retry and host setup: same commit, date, checkout, OS and Podman as
the matrix. Admin RPM: on `14a8114` (2026-11-02, the RPM branch with main
and backlog 80 merged; OL9.8, Podman 5.8.2). Status/retry: a
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
no FANOTIFY/AVC event. The first attempt on `8b23e4e` stopped at the final
`status` because the harness gave no `XDG_RUNTIME_DIR` (a login has it); fixed
in the harness. Not covered: the restart after newer tools, and a real SSH
login running `myproduct` (WP6).

The protected-release and production-layout matrices and the RPM prototype
have no run on the current code; their last runs are in the git history. The
AI operator walkthrough is [OPERATOR-REVIEW.md](OPERATOR-REVIEW.md); the
unassisted human trial (backlog 68) is outstanding.
