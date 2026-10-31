# Simple catalog, one config file per component and API secrets (backlog 77)

Status: the first implementation (`env/` files, `@@api-secret:`) is verified
on real Podman/systemd: all seven lab scenarios are CLEAN PASS (six on
`0459e5a`, the renamed product on `6210670` after a harness fix); see
[lab results](#lab-results-2026-10-30). The product owner's later changes (one
config file per component, one secret form, declared API secrets, and on
2026-10-31 no `upgrade:`/`shares:` with public settings read from the gateway)
have product/unit and harness coverage only; **their lab run is outstanding**
with the commands below.

## Change

- `bundles.yaml` names `gateway:` and `identity:`; entries keep only
  `requires` (2026-10-31: `upgrade` and `shares` removed). `catalog.derive_entries`
  derives the normalized entries from them and the component files; compiled
  descriptors keep the earlier normalized form plus Identity's `api_secrets`.
- One config file per component (product owner, 2026-10-30): `ENVIRONMENT` in
  `config.defaults.yaml` holds each container's variables
  (`deployment/environment.py`); it belongs to the release and never reaches
  the operator's `config.yaml`. Values are the written text. There are no
  `env/` files.
- One secret form: a declared `SECRET_FILES` source with its path and
  `@@secret:<id>/<key>@@`. The short `<id>: generate` declaration and
  `@@secret:<id>@@` reference of the first implementation are removed: they
  created a path (`credentials/<id>/value`) that no file named.
- API secrets: the API declares its secret in `SECRET_FILES`; Identity's
  `ApiResources__<n>__ApiSecrets__0__Value` line names it. `api.yaml`, its
  index, platform hashing and the first implementation's
  `@@api-secret:<component>@@` (a secret no file declared) are removed. The
  demo Identity hashes the raw value itself (image
  `localhost/demo-identity:0.2.4`).
- Demo: Identity's connection string, settings and API resources and app3's
  backend settings are in `ENVIRONMENT`; Identity's `SECRET_TEMPLATES` and both
  hand-written ConfigMaps are gone, so the operator's Identity `config.yaml`
  holds only `DB_*` and the secret sources. All components advance one patch
  version because every bundle carries the changed deployment code.
- Every install renders the component again; only a downgrade is refused
  (`deploy.check_not_downgrade`). Descriptors still write `upgrade: always`
  and `shares: []` for older readers and drop them on read.
- `PUBLIC_ORIGIN` and `HTTPS_PORT` live only in the gateway's `config.yaml`;
  other components read them at init-config (validation only), validate,
  install and staging (`catalog.with_gateway_settings`) and may not hold a
  copy. `config/common.defaults.yaml` is gone from the demo.
- Contracts: [the catalog](../docs/COMPONENTS.md#the-catalog-bundlesyaml),
  [one config file per component](../docs/COMPONENTS.md#one-config-file-per-component-configdefaultsyaml),
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

- `--whoami`: app3's and Identity's `ENVIRONMENT`, app3's generated
  `credentials/api-secret/value`, Identity hashing it itself, introspection
  through `dev/whoami-smoke-test.py`, and app3's restart.
- normal and app2-first: the derived catalog on the fixed demo, platform and
  Identity upgrades that always render, no `PUBLIC_ORIGIN` in any component
  config except platform's, and Identity's injected `envFrom` with an empty
  `identity-apis` (app3 is not installed).
- `--identity-only`: the pinned old Identity baseline (its own ConfigMap, no
  `ENVIRONMENT`) upgrading to the `ENVIRONMENT` Identity without any operator
  config addition (the harness adds none when the release has no recipe).
- platform/help and help-only: products without Identity links.
- `--renamed-product`: the renamed generator's catalog (`gateway:`/`identity:`
  renamed), renamed `ENVIRONMENT` without Identity's app3 line, and the
  `renamed-init-check` step: only gateway's `config.yaml` holds the public
  settings (it replaced the earlier `SHOP_NAME` share check).

Record unit/product tests, harness tests and real runs separately. Keep
failures and their output before any repair.

### Lab results (2026-10-30)

These cover the first implementation only (`0459e5a`/`6210670`), not the
later changes listed under Change. Real Podman/systemd runs; OS and Podman details are in each run's
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
- `--identity-only` assumes the pinned 0.4.11 config declares `DB_*` and
  `identity-database-password` with key `password`: the earlier harness added a
  recipe naming exactly these to that config and passed the lab, but the
  pinned commit is not in this shallow clone, so it was not rechecked here.
- A release that stops using a secret leaves its declaration in the operator's
  persistent `config.yaml`, which is then refused as unused (existing
  behaviour for every secret); the operator removes the entry.
- Upgrades in the lab start from releases built before this change: their
  installed metadata carries `upgrade`/`shares` (read and ignored) and their
  other components' `config.yaml` files still hold `PUBLIC_ORIGIN` and
  `HTTPS_PORT`, which install now refuses ("remove it here"). Pre-customer
  installations may be discarded (review guide); a lab run across this change
  must remove those two lines or start fresh. Not run.
- Older releases reading metadata written by this one: `upgrade`/`shares` are
  still written, but `api_secrets` (since the first backlog 77 commit) is not
  in pre-77 readers' field list. Not run.
- No unassisted human trial of the conversion checklist.
