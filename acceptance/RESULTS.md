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
| `--whoami` | `c82-whoami-53d4591` | 46 | CLEAN PASS |
| normal | `c83b-normal-df929ac` | 118 | CLEAN PASS |
| `--first-app app2` | `c83b-app2-df929ac` | 118 | CLEAN PASS |
| `--identity-only` | `c83b-identity-df929ac` | 58 | CLEAN PASS |
| `--help-only` | `c82-help-53d4591` | 52 | CLEAN PASS |
| `--platform-help-only` | `c82-platform-help-53d4591` | 31 | CLEAN PASS |
| `--renamed-product` | `c83b-renamed-df929ac` | 57 | CLEAN PASS |

Normal, app2, identity, renamed and status-retry on `df929ac` (2026-11-06, backlog 83), the others on `53d4591` (2026-11-03); later commits add only harness checks and backlog 83. Clean detached checkout, Oracle Linux Server
9.8 and Podman 5.8.2 on DEV and PROD, no failed or skipped step. This commit
includes backlog 80: app3's trust chain is mounted from its Secret through
`MOUNTS` secret files, and `07-whoami-chain-mounts` found both files in the
running backend with the environment's CA and as read-only mounts
(`podman inspect`); the Secret key check now runs before the first write of
`prepare` and `install`. It also includes backlog 82: app2's database reads
its password from a `MOUNTS` secret file (app1 keeps the directory mount);
`07-database-auth` connected with it, and the new `07-password-guard`
(normal, app2, identity) found that install stops for the kept `app2-data`
volume without the password file and generates none. In `envup-6a0f319`,
`03-database-runtime` also ran `environment_update_test.py`: after a second
`./dev/dev.sh up` the new container had the added `ENVIRONMENT` variable with
its exact value, the existing one unchanged and the generated secret kept.
On `df929ac` (backlog 83) app2's database takes `POSTGRES_PASSWORD_FILE` from
`ENVIRONMENT` (app1 from the manifest): `07-database-auth` connected, and
`07-password-guard` stopped for the kept volume without generating, then
completed the same install once the original file was back. The init Secret probe runs
inside `03-database-runtime` and `03-renamed-generate`, so these runs cover
it. The harness defects found on the way to this matrix are listed in
[backlog 78](../BACKLOG.md#78-keep-the-acceptance-harness-in-step-with-the-product).

## Other scenarios

| Scenario | Latest run | Steps | Result |
| --- | --- | --- | --- |
| `--status-retry` | `c83b-status-retry-df929ac` | 119 | CLEAN PASS |
| `--host-setup` | `c82-host-setup-53d4591` | 36 | CLEAN PASS |

Same commit, date, checkout, OS and Podman as the matrix. Status/retry: a
same-version failure stays pending with the old container active, a plain
retry completes, and the restore leaves protected code unchanged. Host setup:
procedure and evidence in [HOST-SETUP.md](HOST-SETUP.md).

The protected-release and production-layout matrices and the RPM prototype
have no run on the current code; their last runs are in the git history. The
AI operator walkthrough is [OPERATOR-REVIEW.md](OPERATOR-REVIEW.md); the
unassisted human trial (backlog 68) is outstanding.
