# Platform and demo test groups (backlog 43)

Use the standard-library unittest runner through these explicit entry points:

```sh
python3 -B tests/run.py platform
python3 -B tests/run.py demo
python3 -B tests/run.py all
python3 -B tests/run.py platform --isolate
```

`platform_tests/` exercises deployment, bundles, validation, templates, retry,
database safety and external images with synthetic declarations in `fixtures/`.
It does not read `apps/` or the shipped demo component declarations.
The synthetic `fixtures/catalog` keeps `platform`, `identity`, `app1`, `app2`
and `help` as fixture IDs; that separation alone does not prove arbitrary names.
The renamed-product and minimal-worker fixtures provide that additional evidence.
`demo_tests/` contains application-source assertions, shipped manifests, demo
builds, demo credential recipes and their integration assumptions. Organisations
using other images run their own integration tests in addition to the platform
group. `helpers/` contains reusable fixtures without test methods or imports from
test modules. Historical module names in the coverage notes below refer to files
now located in one of these groups; mixed modules were split.

The offline runtime prerequisites are Python 3.6+, PyYAML, bash, standard host
utilities, OpenSSL, gpg/gpgv/gpgconf and a writable temporary directory supporting
gpg-agent sockets (set a short `TMPDIR` if needed). Missing prerequisites fail
clearly; tests do not silently disappear or skip because demo files are absent.
The temporary directory must also allow execution: tests run wrappers, Podman/
OpenSSL stubs and copied `deploy` scripts from it. On hosts where `/tmp` is
mounted `noexec`, this shows up as `PermissionError`, a failing OpenSSL wrapper
test or a wrong-error failure in the failures example, not as a prerequisite
message. Use an executable directory instead:

```sh
mkdir -p ~/t && TMPDIR=~/t python3 -B tests/run.py platform
```

Run the suite from one consistent copy of a single commit. A copy that mixes
older `examples/` or `deployment/` files with newer tests can fail the example
checks (for example `partial-placeholder unexpectedly succeeded`).
A venv, network, Podman, systemd and root are not required. Ruff, pyright, vermin
and ShellCheck are contributor checks, not offline runtime prerequisites.

To transfer a self-contained platform suite to an offline organisation:

```sh
python3 -B tests/run.py platform --export /path/to/new/platform-suite
# Transfer that whole directory, with executable permissions preserved.
cd /path/to/new/platform-suite
python3 -B tests/run.py platform
```

The export contains the runner, platform tests/helpers/declarative fixtures,
`deployment/`, bundle/entry-point scripts, Quadlet/examples and the three dev
helpers tested by the platform group. Its root catalog/components/version files
come from synthetic fixtures. It contains neither `apps/`, `demo_tests/` nor the
shipped demo component tree. `--isolate` builds and runs the same copy temporarily;
`--list` prints exact test IDs for inventory comparison. Export refuses an
existing destination. The renamed-product generator uses tracked files: stage
new helpers before running its regression tests. Acceptance's `03-unit` step runs
`all`; acceptance-harness tests remain a separate command below and do not prove
real Podman/systemd behaviour. No hosted CI is added.

Discovery previously counted seven imported `RenamedProductTests` methods twice:
410 executions represented 403 distinct tests. Extracting fixtures removes that
duplication while retaining every original test method. New suite-layout and
renamed-inventory regressions protect the separation. Current inventory: 378
platform tests and 65 demo tests (443 unique tests), plus 218 separate
acceptance-harness tests. Inventory counts do not imply real runtime verification.

# Host preparation boundary (backlog 46)

`test_prepare_host.py` covers argument/product behavior, SELinux-rule ordering,
the real shell helper's privilege-drop arguments, failure stopping and refusal
of a symlink home before root chmod. `test_prepare_home.py` exercises the actual
helper, extracted from its here-document in `prepare-host.sh`, on disposable
filesystem trees: all managed directory links, dangling
links, special/wrong-owner objects, retained CNI lock bytes/inode, atomic lock
creation races, directory replacement before open and after open, and retry.
It also guards fapolicyd delivery: host preparation references no `.py` file,
`scripts/` ships only `prepare-host.sh`, and bash passes the embedded helper
through a pipe (a large here-document would fall back to a temporary file that
fapolicyd checks). `test_bundle.py` checks that the actual helper ships with its
checksum.
These tests need neither root nor SELinux. The CLI refuses root; unit tests call
the filesystem function on trees owned by the current test identity.

The separate acceptance probe records and checks real dropped identities,
groups, capabilities and SELinux context, then tests malicious outside targets
and repeat preparation on the resettable lab. See
[verification and outstanding lab gates](../acceptance/PREPARE-HOST.md).

# Component dev configuration (backlog 56)

`test_component_dev.py` uses arbitrary components and no `apps/` to cover optional
layers, precedence, whole-map replacement, independent Secret/volume mappings,
validate/prepare agreement without validation writes or host commands, safe YAML
diagnostics, owner-shared key refusal and inheritance, private-source guards,
real bundle exclusion and production ignoring even malformed hand-copied dev
files. Credential tests retain password bytes across layer changes, refuse a
missing password with an existing database volume and retry after restoration.
The test module is included automatically in `--export` and `--isolate`.
`test_config_demo.py` checks the demo's production/dev marker values; acceptance
harness tests check running-value assertions, sibling isolation and renamed
declarations with Podman stubbed. See [verification](../acceptance/COMPONENT-DEV.md)
for actual results and the outstanding real runtime checks.

# Portable bundled files (backlog 57)

`test_component_files.py` uses a minimal renamed processor with no `apps/`:
source dev, readonly validate, real bundle contents, source removal and release
relocation, init-config retaining logical references, and newer bytes delivered
to install archives with unchanged persistent config. It tests public Secret
keys/size/redaction, directory delivery, private aliases, unsafe references,
symlinked ancestors/descendants, FIFOs, generation/database-password/standalone
refusal, and a sensitive external dev seed absent from production. Existing
file-source tests retain ordinary path behavior. Export/isolation automatically
include the new test and reusable context-aware render helper.

Demo tests cover the actual two-init-container manifest and the sorted shell
command's successful/failed exit and redaction with `psql` stubbed. Harness tests
exercise real isolated Git upgrade builds, strict seed rows and the disposable
SQL failure/repair/replay wiring with Podman stubbed. See
[COMPONENT-FILES.md](../acceptance/COMPONENT-FILES.md) for results and lab commands.

# Configurable CA coverage (backlog 45a)

Real OpenSSL tests check configured CA subject/lifetime and leaf lifetime in
explicit signing, full-demo and component-demo modes, stdin execution, unchanged
existing CA/credentials when settings change, issuance for a new component from
the retained CA, and invalid settings rejected without writes. CA renewal,
production tool delivery and actual application/runtime verification remain
separate work.

# PFX provisioning coverage (backlog 44)

`test_certificates.py` requires OpenSSL (absence fails clearly, not a skip).
It exercises the existing demo workflow and explicit named-component signing
mode with real local OpenSSL: external PFX/PEM precedence, password validation,
stdin execution, private modes, no-clobber publication, retention/re-export,
corrupt/mismatched inputs, concurrency refusal and export failure cleanup.
The worker Secret test checks that only the declared binary PFX reaches the
0600 install YAML with its explicit file mapping; neither the password nor the
PEM key is delivered. These are local product tests, not .NET/Podman proof.
See [runtime verification](../docs/PFX-CREDENTIALS.md#dev-production-and-runtime-verification).

# Secret template and ConfigMap coverage (backlog 41)

`test_secret_templates.py` tests schema, config/file-key references, rejected
characters and redaction, LF handling, deterministic private rendering, key/size
checks, missing generated sources, install/config/password changes and retry.
Operator-supplied sources may be absent at init-config: tests check private config
creation without host commands, write-free validate diagnostics, delivery before
install with LF removal/byte retention, unknown groups and known missing keys,
and missing-file rejection before template materialization. A standalone regression
checks that prepare and validate reject invalid templates before any side effects,
even though those entry points bypass effective_config.
ConfigMap tests cover multiple placeholders, multi-line text, whole-value type
compatibility, preserved dollar/backslash syntax, forbidden Secret references,
invalid/non-recursive markers, non-scalar inputs and unchanged scopes elsewhere.
A minimal worker has no Identity, .NET, database, gateway or certificates; its
sources can be consumed only by a template. Existing database/file-source tests
still protect password retention and the existing-volume guard.

The acceptance harness tests exercise the disposable env/file/restart probe,
Identity's ready-string positive/negative/missing cases, explicit upgrade config
addition and output redaction. These stub runtime commands and are not proof of
Podman or systemd behavior. See [lab verification](../acceptance/SECRET-TEMPLATES.md).

---

# Validate command (backlog 23)

`test_validate.py` runs `./deploy validate` on the renamed product in the source
checkout, in an unpacked bundle and on a standalone fixture. Every case asserts
that no file under the fixture changes and that no Podman or systemd command
runs. It covers each finding type (the five broken orders manifests, a
placeholder only in an init container, an unused id, a missing or directory
Secret source, an undefined ConfigMap, an invalid `client.yaml` and a missing
client certificate), two components reported in one run, the same message as
`prepare` for the same manifest, the bundle's dependency, config and image
archive checks, and the CLI exit codes. `acceptance/test_validate_release.py`
checks the lab helper that requires the command to pass before every install.
After the independent review, every case compares bytes, type and mode of the
whole fixture tree. `BundleAgreementTests` runs the same broken bundle state
through `install()` and `validate()` (differing shared network, component
without images, invalid generated Secret name, existing database volume with a
missing password, where install keeps its restore message). Malformed manifest
fields and invalid UTF-8 are findings, not tracebacks, and the bundle mode works
without a runtime directory.

---

# Manifest validation and registration removal (0.4.10)

Backlog item 21. `test_validation_order.py` breaks one orders manifest five ways
(undefined mount, missing reference, duplicate, online pull policy, unreplaced
placeholder) and requires no secret, archive, YAML or host command on install,
dev prepare and both standalone paths, plus a single render per install.
`test_database_preflight.py` takes the volume, Secret and password path from
config and asserts the configured name reaches Podman; absent, existing and
failing checks; and refuses other `POSTGRES_PASSWORD*` forms (F2).
`test_registration_removal.py` drops inventory's route, client or both, checks
exact owner restarts and imported indexes, injects failures after the deletion
and finishes them in a fresh process, and uninstalls afterwards. See
[verification](../acceptance/MANIFEST-VALIDATION.md).

After the independent review, `test_validation_order.py` also requires that an
invalid `client.yaml` stops install and dev prepare before any write or host
command, and that a missing image archive stops standalone install before
generation. `test_database_preflight.py` treats a data-directory mount as a
database container. `test_registration_removal.py` asserts the exact owners
left and restarted per failure point, including an interrupt after the first
removal, and that an ownerless role is never recorded. `render_helper.py` holds
the render-only `materialize_and_render` shortcut used by tests; product code
calls `check_manifests` and then `materialize`.

---

# Declarative components (0.4.9)

Components come from `bundles.yaml`; see [components](../docs/COMPONENTS.md).
`test_catalog.py` covers catalog/descriptor/installed-metadata validation,
`test_renamed_product.py` a fully renamed product offline without its source,
and `test_product_changes.py` a minimal worker plus adding/removing a service
by YAML only. `catalog_fixture.py` compiles demo descriptors from the real
catalog; `product_fixture.py` writes other products. See
[verification](../acceptance/DECLARATIVE-COMPONENTS.md) for results and gaps.

---

# App1 database init (0.4.8)

App1 creates its Todo table in an init container using the existing database
Secret; its backend verifies the schema and app2 retains backend creation.
Tests cover real manifest order/credentials, bounded waiting and hard alarm,
sanitized failures, backend dispatch, repeated SQL/data preservation through a
documented SQLite adapter, and offline image inclusion. See
[init verification](../acceptance/APP1-INIT.md) for results and runtime limits.

---

# Standard nginx from YAML (0.4.7)

Platform uses stock nginx and a mounted public ConfigMap template. New tests
exercise real YAML rendering and shell/envsubst startup, unchanged app builds,
registry pulls, offline archive checksums and scoped/retry-safe ConfigMap volume
deletion. Podman/systemd transport and nginx itself are stubbed; see
[proxy verification](../acceptance/NGINX-YAML.md) for results and target gaps.

---

# File source declarations (0.4.6)

Current SECRET_FILES/VOLUME_FILES IDs contain lists of `{path: ...}` sources
with optional `generate: [filename]`. Generation and delivery share one
source declaration; there is no separate generation field or old-format fallback.
See [file-source verification](../acceptance/FILE-SOURCES.md) for local checks and target gaps.
Earlier schema/counts below are historical, not the active config contract.

---

# Supported layout cleanup (0.4.5)

Legacy core/combined-platform detectors and their refusal tests have been removed.
Current config initialization performs no obsolete Podman checks; certificate
preparation works even when a stubbed Podman command would fail. The real dev
preflight still checks exactly the three current database volumes. Existing
DB preflight, safe paths, dependency/version checks, fresh-process retry,
credential preservation, bundle protections and scoped uninstall tests remain.
See [cleanup verification](../acceptance/LEGACY-CHECK-CLEANUP.md) for results.

---

# App credential delivery (0.4.4)

Apps now deliver session/client credentials through backend-only read-only
Secrets with requested file mode `0400`; the unused Identity API-secret is
removed. Source files, generation and retry preservation remain unchanged.
See [credential delivery verification](../acceptance/CREDENTIAL-DELIVERY.md)
for local coverage and required fresh target checks. Earlier reports below are
historical evidence, not verification of this change.

---

# Deployment package (0.4.3)

Current local check entry points:

```sh
python3 -B tests/run.py all
python3 -B -m unittest discover -s acceptance -p 'test_*.py'
ruff check deployment/ bundle.py tests/ acceptance/ dev/smoke-test.py
ruff format --check deployment/ bundle.py tests/ acceptance/ dev/smoke-test.py
pyright deployment/ bundle.py tests/ acceptance/ dev/smoke-test.py
vermin -t=3.6- deployment/ bundle.py tests/ acceptance/prepare_host_test.py
shellcheck deploy build-bundle.sh dev/*.sh scripts/*.sh acceptance/remote.sh examples/run.sh PKI/generate.sh
```

Existing safety and fresh-process retry tests import the owning package modules;
the shared path fixture patches `deployment.common`. Package regressions cover
real module inclusion/checksums, private-file aliases, bytecode exclusion and
source/unpacked wrappers from outside their directories without a bytecode env
setting. Acceptance-harness tests check recursive directory trust completeness,
old entry removal, exact sibling trust and cleanup ordering. See
[DEPLOY-REFACTOR.md](../acceptance/DEPLOY-REFACTOR.md) for current evidence.
Older commands/counts below are historical; use the commands above for this layout.

---

# Lifecycle retries (0.4.2)

`test_retry.py` invokes `retry_driver.py` in a fresh Python interpreter for each
attempt against the same persistent test home. Actual deploy/files/import archives
run unchanged; only environment checks and Podman/systemd transport are stubbed.
It covers failed/crashed installs, partially written registrations, failed owner
checks/imports, resumable uninstalls, partial volume deletion and invalid/conflicting
retry state. Existing four-way route/client restart tests remain in place.
See [RETRY-SAFETY.md](../acceptance/RETRY-SAFETY.md) for results and limitations.

---

# Credential paths (0.4.1)

Active tests use fresh `credentials/` state. Config tests initialize real defaults
for all five components in dev/production; generation, database preflight,
registration, preservation and archive tests use the same paths. Bundle tests
also reject externally delivered credentials and symlink aliases while retaining
the declaration-based secret checks for arbitrary paths. See
[CREDENTIAL-PATHS.md](../acceptance/CREDENTIAL-PATHS.md) for current results;
older counts and lab evidence below remain historical.

---

# Current test baseline (Identity split 0.4.0)

Five separate bundles implement the fixed platform/Identity/app/help dependency
graph. `test_identity.py` covers independent versions, exact route/client restart
ownership, help without Identity and scoped
Identity deletion. Bundle tests inspect real archives and checksums. See
[IDENTITY-SPLIT.md](../acceptance/IDENTITY-SPLIT.md) for current results and lab gaps.
Host code and product tests retain Python 3.6 compatibility. Commands below remain
valid; earlier baseline counts and runtime evidence are historical.

---

# Current test baseline (platform 0.3.0)

The active component is `platform`, shipped in its own offline bundle. The current
suite covers separate installation/dependencies, renamed resources, preserved
sibling state, equal/newer/older platform versions and scoped deletion. Historical
layout checks were removed in 0.4.5; current database/credential guards remain.
See [PLATFORM-RENAME.md](../acceptance/PLATFORM-RENAME.md) for the full mapping,
checks and lab commands. Host code and product tests retain Python 3.6 syntax/APIs.

The coverage notes and runtime evidence below are retained from the earlier core
layout. Their historical counts/results do not assert platform lab verification.
Use the current commands above; the commands below are historical.

---

# Unit tests

`test_deploy.py` and `test_bundle.py` use only the standard library
and PyYAML. `test_certificates.py` requires bash and OpenSSL,
with all key material in a temporary directory. All paths point into `TemporaryDirectory`; Podman/systemd calls and the user check
are stubbed. No network, Podman, systemd or root is required. The bundle tests write
and read real tar archives and verify every SHA-256 line, but stub the image save.

```sh
python3 -m unittest discover -s tests
.venv54/bin/python -m unittest discover -s tests
ruff check deploy.py bundle.py tests/
ruff format --check deploy.py bundle.py tests/
pyright deploy.py bundle.py tests/
vermin -t=3.6- deploy.py bundle.py tests/
```

For PyYAML 5.4.1, use a Python version it can be built on (tested with 3.11):

```sh
python3.11 -m venv .venv54
.venv54/bin/pip install setuptools wheel 'cython<3'
.venv54/bin/pip install --no-build-isolation pyyaml==5.4.1
```

Lint/type/vermin are development tools, not new runtime dependencies.
The tests use Python 3.6-compatible syntax and standard library APIs.

## Images from the manifests

181 tests pass with PyYAML 6.0.3 (Python 3.14.4) and 5.4.1 (Python 3.11.17).
The image tests cover Pods, init containers, several files/documents,
flow maps, duplicates, full names and expected validation errors. The bundle tests
check one sorted multi-image save, the name list, tar content and checksums.
Registry tests require sorted deduplicated pulls with policy=always before save,
skip localhost/ names, and reject failed pulls without build/save fallback or
private registry diagnostic output. `test_images.py` runs the actual dev helpers
with a recording Podman stub, including manifest tags and localhost:port names.
The installer tests check the render/load/exists order, rendered names,
a missing archive/image and that existing Quadlet files are kept on check failures.
Standalone prepare tests run without Podman calls. Component dev preparation
checks the actual database volumes before creating a missing password; those
Podman calls are stubbed in unit tests.

A real save/load was verified on 2026-10-12 with **Podman 5.7.0, rootless**.
Three existing names were saved with `podman save -m -o images.tar ...` and loaded
with `podman load -i images.tar` into an empty, temporary VFS image store
(`--root`, `--runroot`, `--storage-driver vfs`). All three
`podman image exists` checks returned 0. `podman images` after the load showed:

```text
docker.io/library/nginx:1.28-alpine dc73b49f5124
localhost/offline-example:1 30ecbe150909
docker.io/library/busybox:1.37.0 30ecbe150909
```

Full names and tags were preserved, including two names for the same image ID.
The test store was removed afterwards. This was a separate save/load test with small
test images; the full product bundle and the prod Quadlet installation were not run
as part of that change.

The regression tests cover name collisions between Secret/PVC/ConfigMap,
validation without writing archives, keeping old archives on load/exists failures,
the network Quadlet and rejection of duplicate manifest keys during the build.
Real systemd, reboot and upgrade are checked by the [acceptance test](../acceptance/README.md).

## Rootless prod

The install tests reject root before rendering/commands, check the user-database-based
Quadlet/archive paths, systemctl --user in the right order, the runtime fallback and
the error for a missing runtime directory, plus file permissions. No product files
are written to the system instance's Quadlet directory. The bundle test includes prepare-host.
The acceptance harness's local tests also check that the sudo commands change
the working directory before install/Podman, without root, Podman or network.

Persistent config is tested separately from the release config: install uses the home from the user database, component prepare
merges common/component defaults with optional local dev overrides, and relative secret/volume paths follow the config directory.
The certificate tests check --root, the default root, file modes, the host name
and that a repeated generation is rejected without changing any files.

The prod paths are tested with a mock of pwd.getpwuid, also with a wrong HOME. Install
rejects a mismatch before rendering and commands; an absent HOME uses pw_dir.

The host script tests check the required port, rejection of an old equivalence,
the idempotent rule and that recursive restorecon always excludes storage.
The runtime tests reject every XDG_RUNTIME_DIR value other than /run/user/<euid>.
The bundle test includes the two prod scripts and excludes the dev/ directory.

Manifest errors are tested with the file path and image errors with the container name. A separate
test renders the real product manifests with merged defaults and dummy files,
without Podman, and checks resources and image names.

`test_health.py` requires one exec liveness probe in every real app manifest,
with initialDelay 10, period 10, timeout 5 and failureThreshold 6. Init containers
have no probe. The backend's /livez and its authentication guard are tested in isolation, without
importing the app, a database or the app's dependencies.

Manifest validation tests cover defined and missing ConfigMaps in all three
reference forms, pod-local mounts, and required Never pull policies on ordinary
and init containers. Unsupported kinds (Deployment, List, no kind) are refused
before generation, output or Podman calls, also at build and on install of a
renamed release, where a Deployment cannot take another component's name or
skip the database preflight.

Generated-secret tests verify exclusive creation, 32 alphanumeric characters,
0600/0700 modes, reuse by prepare and install, empty-file errors, path confinement
including symlinks, concurrent creation and output without secret values.

The 142 acceptance-framework tests also cover pre-reboot launcher diagnostics:
separate streams, safe journal/unit projections, strict command/parsing errors,
audit collection after a diagnostic error, and stopping before reboot on a denial.
The run-19 regression fixture distinguishes removed transient units from loaded
services, without relaxing required properties for a loaded launcher.
Registry framework tests cover separate log streams, strict JSON/Combined format
parsing (including escaped quoted fields and final newlines), public run-21
manifest/blob request fixtures, private query/header omission, malformed or
unknown records, failing log commands and missing HTTP 200 GET evidence,
expected negative exits, no build fallback, offline load/run ordering and cleanup
of TLS keys/registry resources. Existing user registry certificates are preserved.

Review regressions reject false-like non-map file groups and accept ConfigMap
`data.spec` as ordinary data. Invalid config and YAML errors retain field/line
context without echoing source values. Bundle tests reject declared generated
secrets in shipped directories and symlink aliases before image operations.
`test_smoke.py` isolates the login and CLI code without requests: callback URLs,
form/session tokens and HTTP exception contents never appear in failure output.
The generated-secrets example is rendered twice with temporary private files.

## Component lifecycle

Component tests cover strict resource/file-group prefixes, per-component output paths,
unchanged siblings, immutable shared networking, core version comparisons, staged
public route/client imports, current registration indexes, and scoped uninstall.
Default uninstall retains private state and data volumes; explicit deletion targets
only the selected component. Certificate tests verify component idempotence and the
shared CA. The real app fixture has 8 pods, 10 app containers, 2 init containers
and 6 distinct images; SQL seeding reuses the existing Postgres image.

Component acceptance regressions cover both install orders, help-alone without
state writes, all three archive transfers, app1-only upgrade, cross-file inventory
collisions, untouched sibling observations/trust and retained-data uninstall.
The cross-app SSO CLI regression withholds callback details on failure.

Malformed PUBLIC_ORIGIN regressions cover both core rendering and public client
staging, pre-generation refusal and CLI diagnostics without supplied values.


## Explicit configuration layers

`test_config.py` covers common/component/override precedence, whole-map/list
replacement, incomplete layers and duplicate keys, authoritative persistent config,
changed release defaults, missing required placeholders before writes, exclusive
initialization with private modes, symlink rejection, inherited core common values,
and regenerated dev output with retained credentials/data. Existing standalone
fixtures still test their explicit `config.yaml` paths separately.

Bundle regressions cover the new defaults files, exclusion of dev/private config
and bytecode, and generated-secret symlink aliases resolved from materialized dev
folders for all new config sources. Component lifecycle tests require exactly the
expected restart set for both help registration cases and protect sibling files
through newer-core upgrades and older-core refusal in both app orders.


Import-archive regression tests normalize timestamps in addition to ownership and
modes. Fresh staging-directory/file timestamps cannot change an archive checksum,
while changed file contents must change its bytes. This keeps unchanged public
core imports stable across controlled core upgrades without excluding them from
persistent-state comparisons.


## PostgreSQL credentials

`test_database.py` covers text-only DB parameters/port validation, identical
server/client Secret keys, exactly one GENERATED_SECRETS declaration per DB,
exclusive private generation, independent app passwords, preservation of legacy
password bytes, missing-file/existing-volume refusal, empty/invalid file refusal,
volume-check failures, non-regular file refusal, actual generated Secret payloads,
and pre-generation/pre-image/pre-state ordering in both dev
and production. Python secret-reader tests preserve quotes, dollar signs, equals,
semicolons, spaces and only remove trailing LF. These are unit/integration tests
with Podman transport stubbed; they do not prove PostgreSQL authentication.

Acceptance's `database-runtime` action uses disposable UUID-scoped PostgreSQL
volumes on the dev VM. It tests actual initdb through kube Secrets, non-default
host/port/user/database, Identity's environment connection interface and Python's
file interface, special/Unicode credentials and legacy trailing LF, wrong-secret
authentication and sanitized missing/invalid parameter/password failures. `database-auth` checks installed
Identity and both Todo applications before lifecycle tests, after reboot and after
upgrade. Each Todo must connect with its own secret before a sibling-secret attempt
is allowed. Negative checks change only transient client input, never stored
passwords. See [database verification](../acceptance/DATABASE-VERIFICATION.md) for real-run
results and limits. Harness tests separately check private stdin, safe evidence and sequencing.


## Baseline before structural changes

See [TEST-BASELINE.md](../acceptance/TEST-BASELINE.md) for the recorded main
baseline, existing coverage, additional install failure/legacy config/wrapper
regressions, verification results and the historical-upgrade gate. The current
local suite has 185 tests. Wrapper tests use actual scripts and real bundles but
stub host account/runtime and Podman/systemd in isolated child processes. Runtime
staging in component fixtures stays within TemporaryDirectory even when the
synthetic `/run/user/1000` is absent; production guards remain tested separately.


## Generated Secret values in init containers (backlog 61)

`test_secret_templates.py` checks exact Secret bytes and preserved init
`secretKeyRef`/`always` declarations, wrong/missing keys before generation,
credential-free validation, component dev overrides and isolated production
init-config/install/retry with retained config/passwords. These are product tests
with host commands stubbed. `acceptance/test_init_secret.py` separately checks the
runtime probe's negative assertions and orchestration. Separate normal and renamed
real Podman/systemd runs passed at `52f28e4`; see
[the evidence, scenario and operator diagnostics](../acceptance/INIT-SECRET.md).
