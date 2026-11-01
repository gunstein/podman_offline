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
harness tests only. The matrix no longer has the `03-example-*` steps; its
seed checks now also log in as `todo_report`, created by app1's `MOUNTS` SQL file.
The first real run, `whoami-ff53717` (2026-10-31), was NOT CLEAN at
`03-dev-up`: "a wrong password was accepted". A harness defect: the check
logged in over `127.0.0.1`, which the postgres image's `pg_hba.conf` trusts
(initdb's default), so no password was checked. The check now connects to the
container's own address (`scram-sha-256`); verified against a local
`postgres:17.11` container. The rerun `whoami-64a2c65` is CLEAN PASS (46
steps). `c77d-normal-64a2c65` was then NOT CLEAN at `03-registry-test`:
"Missing component catalog …/registry-fixture/bundles.yaml". Another harness
defect: the registry fixture still used the removed standalone layout. It is
now a one-component catalog product (`myproduct-registry-0.0.0`); a test runs
the copied `bundle.py` on it.

Matrix on `131f362` (2026-10-31, clean checkout, Oracle Linux Server 9.8,
Podman 5.8.2): `whoami` 46, `normal` 117, `app2` 117, `identity` 57, `help`
52 and `platform-help` 31 steps, all CLEAN PASS. `renamed` was NOT CLEAN at
`10-install-inventory-without-registrations` after 48 passed steps: install
refused "APP_ID: @@CLIENT_ID@@ comes from client.yaml, which
components/inventory does not have". A harness defect: the inventory-drop
action removed `client.yaml` but left the placeholders in `ENVIRONMENT`. It
now writes the client's values (`inventory`, `/stock`) there; its test runs
the real `./deploy.sh validate` on the result. The rerun
`c77e-renamed-68fd050` is CLEAN PASS (57 steps, clean checkout, same OS and
Podman). `68fd050` changes only the harness and this file relative to
`131f362`, so the six runs above still cover the product code.

## Other scenarios

Host setup (`--host-setup`, procedure and evidence in
[HOST-SETUP.md](HOST-SETUP.md)), status/retry (`--status-retry`), the init
Secret probe, the protected-release and production-layout matrices and the RPM
prototype have no run on the current code; their last runs are in the git
history. The AI operator walkthrough is [OPERATOR-REVIEW.md](OPERATOR-REVIEW.md);
the unassisted human trial (backlog 68) is outstanding.
