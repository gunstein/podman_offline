# Simple catalog, `env/` files and API secrets (backlog 77)

Status: implemented with product/unit and acceptance-harness test coverage
(2026-10-30) and verified on real Podman/systemd: all seven lab scenarios are
CLEAN PASS (six on `0459e5a`, the renamed product on `6210670` after a harness
fix). See [lab results](#lab-results-2026-10-30).

## Change

- `bundles.yaml` names `gateway:` and `identity:`; entries keep only
  `requires`, `upgrade` and (gateway) `shares`. `catalog.derive_entries`
  derives the normalized entries from them and the component files; compiled
  descriptors keep the earlier normalized form plus Identity's `api_secrets`.
- `env/<container>.yaml` (`deployment/envfiles.py`), the short
  `<id>: generate` declaration and `@@secret:<id>@@`.
- API secrets as `@@api-secret:<component>@@` on both sides; `api.yaml`, its
  index and platform hashing are removed. The demo Identity hashes the raw
  value itself (image `localhost/demo-identity:0.2.4`).
- Demo: Identity and app3 use `env/` files; all components advance one patch
  version because every bundle carries the changed deployment code.
- Contracts: [the catalog](../docs/COMPONENTS.md#the-catalog-bundlesyaml),
  [environment files](../docs/COMPONENTS.md#environment-files-envcontaineryaml),
  [API secrets](../docs/COMPONENTS.md#api-secrets) and the
  [conversion checklist](../docs/COMPONENTS.md#converting-a-service).

## Local evidence

Run in the development container at the implementation commit; Podman and
systemd stubbed:

- `python3 -B tests/run.py all`: 600 tests; all pass except 9 tests in
  `platform_tests.test_host_setup`, which refuse to run as root
  ("use an ordinary non-root login account"); the same 21 host-setup tests
  pass when run as an ordinary user.
- `python3 -B -m unittest discover -s acceptance -p 'test_*.py'`: 358 tests,
  OK.

These do not establish real Podman/systemd/Duende behaviour.

## Lab check (controller)

Run from a clean `main` checkout that contains this change. Each command
resets the disposable VMs. Require CLEAN PASS for each and record the exact
commit, step counts and OS/Podman versions:

```sh
git rev-parse HEAD
test -z "$(git status --porcelain)" && echo clean
rev=$(git rev-parse --short HEAD)
python3 acceptance/acceptance.py --run "c77-whoami-$rev" --whoami run
python3 acceptance/acceptance.py --run "c77-normal-$rev" run
python3 acceptance/acceptance.py --run "c77-app2-$rev" --first-app app2 run
python3 acceptance/acceptance.py --run "c77-identity-$rev" --identity-only run
python3 acceptance/acceptance.py --run "c77-help-$rev" --help-only run
python3 acceptance/acceptance.py --run "c77-platform-help-$rev" --platform-help-only run
python3 acceptance/acceptance.py --run "c77-renamed-$rev" --renamed-product run
```

What each part exercises for this change:

- `--whoami`: app3's and Identity's `env/` files, the generated
  `credentials/api-secret/value`, Identity hashing it itself, introspection
  through `dev/whoami-smoke-test.py`, and app3's restart.
- normal and app2-first: the derived catalog on the fixed demo,
  `newer-only` platform/Identity upgrades and Identity's injected `envFrom`
  with an empty `identity-apis` (app3 is not installed).
- `--identity-only`: the pinned old Identity baseline (its own ConfigMap, no
  `env/`) upgrading to the `env/` Identity.
- platform/help and help-only: products without Identity links.
- `--renamed-product`: the renamed generator's catalog (`gateway:`/`identity:`
  renamed) and renamed `env/` files without app3's line.

Record unit/product tests, harness tests and real runs separately. Keep
failures and their output before any repair.

### Lab results (2026-10-30)

Real Podman/systemd runs; OS and Podman details are in each run's
`EVIDENCE.md`.

| Run | Result | Passed steps |
| --- | --- | --- |
| `c77-whoami-0459e5a` | CLEAN PASS | 46 |
| `c77-normal-0459e5a` | CLEAN PASS | 125 |
| `c77-app2-0459e5a` | CLEAN PASS | 125 |
| `c77-identity-0459e5a` | CLEAN PASS | 66 |
| `c77-help-0459e5a` | CLEAN PASS | 60 |
| `c77-platform-help-0459e5a` | CLEAN PASS | 39 |
| `c77-renamed-0459e5a` | **NOT CLEAN** | 46, then FAIL at `10-inventory-drop-registrations` |
| `c77-renamed-6210670` | CLEAN PASS | 57 |

The renamed failure is a harness defect: the `renamed-inventory-drop` action
still removed `routes` and `clients` from the inventory catalog entry, which
phase 1 had replaced with `route.conf`/`client.yaml`, and stopped with
`KeyError: 'routes'` before building. All product steps before it passed.
The action now only removes the two files and bumps the version;
`test_inventory_drop_action_removes_derived_route_and_client` runs it against
the generated tree with only the build stubbed. The rerun `c77-renamed-6210670`
is CLEAN PASS, including the inventory release without route and client
(`/stock` 404, client gone, orders kept). `6210670` changes only the harness
and documentation relative to `0459e5a`, so the six earlier runs still cover
the product code.

## Verification gaps

- A manual API secret rotation on PROD (replace
  `credentials/api-secret/value`, reinstall a newer app3) is not part of the automated scenarios.
- An Identity that declares `<identity>-apis` itself while no API exists is not
  refused (with an API it is).
- No unassisted human trial of the conversion checklist.
