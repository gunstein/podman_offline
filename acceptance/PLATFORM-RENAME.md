# Platform 0.3.0 rename and separate bundle

Backlog item 8, based on main `511099e7e056d0d18c4ade95067c30a54c48bec4`.
The user explicitly chose a separate platform bundle at this step. Identity
remains inside platform until item 9; the deploy module refactor is deferred.

## Names and scope

| Former active name | Current name |
| --- | --- |
| `components/core/` | `components/platform/` |
| `CORE_VERSION` | `PLATFORM_VERSION` |
| `~/core/config.yaml`, `~/installed/core` | `~/platform/config.yaml`, `~/installed/platform` |
| `myproduct-core.service/.kube/.yaml` | `myproduct-platform.service/.kube/.yaml` |
| `core-identity`, `core-identity-postgres`, `core-proxy` | `platform-identity`, `platform-identity-postgres`, `platform-proxy` |
| `core-identity-data`, `core-identity-protection` | corresponding `platform-` PVCs |
| `core-settings`, `core-*` Secrets/imports | corresponding `platform-` ConfigMap/Secrets/imports |
| `DB_HOST: core-identity-postgres` | `DB_HOST: platform-identity-postgres` |
| active core functions/variables/errors | platform functions/variables/errors |

Manifests, references, config defaults, dev credentials/paths, certificate helper,
active acceptance runner, source/bundle entry points and local tests use platform.
The shared network/product name `myproduct`, public `/identity/`, `/app1/`,
`/app2/`, `/help/` paths, database names/users, OIDC IDs/scopes, app resources,
proxy HTTPS hostname and image repositories are retained. Microsoft.AspNetCore
namespaces and the external policycoreutils package and systemd core-dump result names are unrelated to the
component and remain unchanged.

Both VERSION and PLATFORM_VERSION are 0.3.0 because old persistent resources are
incompatible with the new layout. Only `myproduct-proxy:0.3.0` is a new image tag:
its internal Identity upstream changed. Identity remains at 0.2.1, backend at
0.2.1 and frontend/help at 0.2.0; PostgreSQL is unchanged. Their application image
contents did not change. Existing private bytes are never regenerated as a rename.

## Separate offline bundles and dependencies

```yaml
platform: [platform]
app1: [app1]
app2: [app2]
help: [help]
```

A platform archive is named `myproduct-platform-<PLATFORM_VERSION>-offline.tar.gz`.
Other bundle filenames retain their existing patterns and use VERSION. Every
archive includes only its selected component resources/images and shared host
code/metadata/defaults. App/help archives never embed platform or install it
implicitly. Install platform first; either app can then be the first app.

Each descriptor includes `requires`: `{}` for platform, and an explicit platform
range for apps/help, initially `{platform: {min: 0.3.0, before: 0.4.0}}`. The lower
bound is inclusive and upper bound exclusive. The builder declares compatibility
within the configured major series, or minor series for 0.x. It does not accept
all newer platform releases. This is the small dependency contract for this
separation; independent Identity requirements are added by item 9.

The installed requirement is saved privately in `~/dependencies/<component>.json`.
A platform upgrade validates all installed app/help requirements without reading
old release directories. Missing, malformed or incompatible metadata is an error.
App/help init-config and install require an installed compatible platform.

Only the platform bundle upgrades/downgrades platform or uninstalls platform.
Equal platform version retains existing YAML/Quadlet; newer versions explicitly
restart platform and older versions are refused. Apps/help preserve platform
files/version; changed public route/OIDC registrations refresh its import archives
and restart it, while unchanged registrations do not. Platform uninstall is
blocked while any dependent marker exists. Explicit data deletion uses only the
selected component's validated resource names. Shared network and CA remain.

## Retained data compatibility boundary

There is no automatic core-to-platform migration, cleanup or volume renaming.
Production init/install/uninstall and component dev/certificate preparation check
known old config/state directories, markers, Quadlet and user service files,
and generated runtime unit files. The checks use lstat, so a broken old alias or
empty retained core directory also causes refusal. All old/mixed state is retained.

The known persistent old volumes `core-identity-data`,
`core-identity-protection`, `core-routes` and `core-clients` are checked even when
installed markers have been removed. Only Podman's explicit absent status 1 means
absence. Present status 0 refuses; other exits, an unavailable executable, failed
filesystem checks or timeout cause refusal. No output from private Podman checks
is included in errors. These checks precede secret/certificate generation, image
load, registration/config/service-file writes and service operations. They are
read-only; they do not claim an atomic transaction against concurrent operators.

Old `core` CLI arguments fail with a clear rename message. Use the previous
release to manage old installations. A separate reviewed migration/backup/recovery
procedure is backlog item 11, outside this refactor. Never manually substitute new
empty database volumes for retained ones or regenerate passwords against old data.

## Historical evidence and local verification

Before edits, 185 product tests and 148 acceptance-harness tests passed at
`511099e`, with Python 3.12.14 / PyYAML 6.0.3. The final local suites have
195 product tests and 152 harness tests. Ruff lint/format, Pyright, Vermin
(Python 3.6 host/product test APIs), ShellCheck and Bash syntax checks pass.
No actual Python 3.6 interpreter or PyYAML 5.4.1 matrix was available for rerun.

The updated tests preserve namespace/link validation, credential/config
preservation, per-component services/imports, first-app order, equal/newer/older
platform handling, help/app-only changes, volume/Secret bindings, scoped deletion,
bundle contents/images/checksums and wrapper cwd behavior. New regressions cover
old/mixed files, broken old aliases, old volumes without markers, failed/time-limited
volume checks, legacy arguments, certificate refusal, dependency persistence and
incompatible/missing installed requirements. Host operations remain stubbed locally.

The historical `upgrade_020.py`, `upgrade_020_guest.py`, their fixtures/tests,
CONFIG-VERIFICATION.md, DATABASE-VERIFICATION.md and TEST-BASELINE.md are preserved
with their original core names. Acceptance README retains its historical body
verbatim beneath current instructions. Those names and old run results must not
be interpreted as platform runtime evidence.

## Lab commands and remaining verification

Actual 0.3.0 VM/container/systemd/fapolicyd execution is **NOT RUN** here. The
controller configuration and credentials are unavailable. Run these from a clean,
committed current checkout with the existing private lab configuration and new
run IDs. Each command resets the two configured disposable lab VMs:

```sh
python3 acceptance/acceptance.py --run platform-app1-first --first-app app1 run
python3 acceptance/acceptance.py --run platform-app2-first --first-app app2 run
python3 acceptance/acceptance.py --run platform-help --help-only run
python3 acceptance/acceptance.py --run platform-core-refusal --legacy-refusal run
```

The refusal scenario builds genuine old images/bundles from pinned 0.2.0 commit
`86e8e27`, with the unchanged historical helper from `511099e`. It installs old
core/apps and creates Alice/Bob markers, then requires new platform
init/install/uninstall to refuse before mutation. The original private snapshot
compares credentials/config/imports/volumes/versions/service and container identity;
login/CRUD and retained user data are rechecked after refusal. The scenario does
not attempt a successful migration across the rename boundary.

To run the previously supplied successful 0.2.0-to-0.2.1 upgrade, use a clean
checkout of `511099e` and its `--upgrade-020` command. Current `--upgrade-020`
refuses before allocating a run or touching lab VMs and points to that commit.
Do that historical run before another resettable platform scenario if preserving
its lab state matters. Passing local harness tests does not prove either real run.

Next implementation is item 9, extracting Identity; keep these assertions and
explicitly adapt dependency contracts and acceptance scenarios to that split.
