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

| Scenario | Latest run | Commit | Result | Steps |
| --- | --- | --- | --- | --- |
| `--whoami` | `c77b-whoami-318d394` | `318d394` | CLEAN PASS | 46 |
| normal | `c77b-normal-318d394` | `318d394` | CLEAN PASS | 125 |
| `--first-app app2` | `c77b-app2-318d394` | `318d394` | CLEAN PASS | 125 |
| `--identity-only` | `c77b-identity-318d394` | `318d394` | CLEAN PASS | 66 |
| `--help-only` | `c77b-help-318d394` | `318d394` | CLEAN PASS | 60 |
| `--platform-help-only` | `c77b-platform-help-318d394` | `318d394` | CLEAN PASS | 39 |
| `--renamed-product` | `c77b-renamed-318d394` | `318d394` | CLEAN PASS | 57 |

DEV and PROD: Oracle Linux Server 9.8 (el9_8), Podman 5.8.2.

The `c77c-*` runs on `7f22375` have finished but are not recorded here yet.
Commits after `318d394` (no legacy handling, release defaults for missing
config names, demo settings in `ENVIRONMENT`, client id and path written once,
no shared or per-component dev config file) have unit and harness tests only.

## Other scenarios

Host setup (`--host-setup`, procedure and evidence in
[HOST-SETUP.md](HOST-SETUP.md)), status/retry (`--status-retry`), the init
Secret probe, the protected-release and production-layout matrices and the RPM
prototype have no run on the current code; their last runs are in the git
history. The AI operator walkthrough is [OPERATOR-REVIEW.md](OPERATOR-REVIEW.md);
the unassisted human trial (backlog 68) is outstanding.
