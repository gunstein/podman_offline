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
| `--whoami` | `c77g-whoami-7f58936` | 46 | CLEAN PASS |
| normal | `c77g-normal-7f58936` | 117 | CLEAN PASS |
| `--first-app app2` | `c77g-app2-7f58936` | 117 | CLEAN PASS |
| `--identity-only` | `c77g-identity-7f58936` | 57 | CLEAN PASS |
| `--help-only` | `c77g-help-7f58936` | 52 | CLEAN PASS |
| `--platform-help-only` | `c77g-platform-help-7f58936` | 31 | CLEAN PASS |
| `--renamed-product` | `c77g-renamed-7f58936` | 57 | CLEAN PASS |

All on `7f58936` (2026-11-01), clean detached checkout, Oracle Linux Server
9.8 and Podman 5.8.2 on DEV and PROD, no failed or skipped step. Later
commits up to `f7b237c` change only `BACKLOG.md`. The init Secret probe runs
inside `03-database-runtime` and `03-renamed-generate`, so these runs cover
it. The harness defects found on the way to this matrix are listed in
[backlog 78](../BACKLOG.md#78-keep-the-acceptance-harness-in-step-with-the-product).

## Other scenarios

| Scenario | Latest run | Steps | Result |
| --- | --- | --- | --- |
| `--status-retry` | `c77g-status-retry-7f58936` | 118 | CLEAN PASS |
| `--host-setup` | `c77g-host-setup-7f58936` | 36 | CLEAN PASS |

Same commit, date, checkout, OS and Podman as the matrix. Status/retry: a
same-version failure stays pending with the old container active, a plain
retry completes, and the restore leaves protected code unchanged. Host setup:
procedure and evidence in [HOST-SETUP.md](HOST-SETUP.md).

The protected-release and production-layout matrices and the RPM prototype
have no run on the current code; their last runs are in the git history. The
AI operator walkthrough is [OPERATOR-REVIEW.md](OPERATOR-REVIEW.md); the
unassisted human trial (backlog 68) is outstanding.
