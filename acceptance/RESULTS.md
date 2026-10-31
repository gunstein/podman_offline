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

| Scenario | Latest run | Commit | Result |
| --- | --- | --- | --- |
| `--whoami` | `c77c-whoami-7f22375` | `7f22375` | CLEAN PASS |
| normal | `c77c-normal-7f22375` | `7f22375` | CLEAN PASS |
| `--first-app app2` | `c77c-app2-7f22375` | `7f22375` | CLEAN PASS |
| `--identity-only` | `c77c-identity-7f22375` | `7f22375` | CLEAN PASS |
| `--help-only` | `c77c-help-7f22375` | `7f22375` | CLEAN PASS |
| `--platform-help-only` | `c77c-platform-help-7f22375` | `7f22375` | CLEAN PASS |
| `--renamed-product` | `c77c-renamed-7f22375` | `7f22375` | CLEAN PASS |

Reported by the product owner on 2026-10-31: all seven runs were CLEAN PASS.
Step counts and `EVIDENCE.md` were lost when the lab disk filled up and the
run directories were deleted, so only the result is recorded.

Commits after `7f22375` (demo settings in `ENVIRONMENT`, client id and path
written once, no shared or per-component dev config file, `MOUNTS`, no
standalone mode or `examples/`, no authored `SECRET_TEMPLATES`) have unit and
harness tests only. The matrix no longer has the `03-example-*` steps.

## Other scenarios

Host setup (`--host-setup`, procedure and evidence in
[HOST-SETUP.md](HOST-SETUP.md)), status/retry (`--status-retry`), the init
Secret probe, the protected-release and production-layout matrices and the RPM
prototype have no run on the current code; their last runs are in the git
history. The AI operator walkthrough is [OPERATOR-REVIEW.md](OPERATOR-REVIEW.md);
the unassisted human trial (backlog 68) is outstanding.
