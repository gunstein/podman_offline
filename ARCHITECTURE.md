# Deployment architecture

Use the root `./deploy prepare|install|uninstall` and `./deploy init-config
<component>` commands. The wrapper changes to its own directory and executes
`python3 -B -m deployment`, so callers need not enter a release directory and
trusted code creates no `.pyc`/`__pycache__`. `./build-bundle.sh` is the stable
build entrypoint and also uses `-B`.

## Modules

| Module | Responsibility |
| --- | --- |
| `deployment/__main__.py` | Minimal CLI delegation |
| `deployment/cli.py` | Arguments, exit codes and concise errors |
| `deployment/common.py` | Release/service-user paths, fixed component contracts, shared constants and DeployError |
| `deployment/render.py` | Config/YAML loading and validation, generated-secret helpers, file groups, manifests, images and import archives |
| `deployment/deploy.py` | Initialization, DB/host checks, dependency/version checks, registrations, retry state, Quadlet/systemd and component lifecycle |

`common.ROOT` is the directory above the package, both in source and unpacked
bundles. `common.HOME` follows the service account's user-database home. There
are no lifecycle actions during package import. Modules share these explicit
paths without circular imports or a dependency framework.

`materialize_and_render()` advertises its filesystem side effects: it validates
config/component names, creates allowed missing generated secrets, renders YAML
and optionally writes import archives. Secret creation stays at the same
validation boundary as before this refactor. General secret generation never
performs database volume checks; lifecycle preflight does that first.

## Fixed component graph

| Component | Owns | Requires |
| --- | --- | --- |
| platform | HTTPS proxy, web TLS, public routes | none |
| identity | IdentityServer/DB, users, signing material, Data Protection, public OIDC clients | platform |
| app1 / app2 | Own app, DB, private client/session credentials | platform + identity |
| help | Static help and public route | platform |

`common.DEPENDENCIES` is the fixed graph; COMPONENTS is derived from its keys.
`bundles.yaml` selects separate bundles; the builder validates selections and
writes dependency ranges from the same graph. No generic plugin mechanism is
introduced. PLATFORM_VERSION and IDENTITY_VERSION remain independent; VERSION
versions app/help. Existing inclusive-min/exclusive-before checks and saved
installed dependency metadata are unchanged.

## Lifecycle

`install_components()` checks the host, pending conflicts, bundle/dependency
contracts, versions, resource/config names, authoritative shared settings and DB
state before staging registrations. Equal shared versions are excluded from
rendering; the incoming bundle still has its images verified.

`install_component_plan()` then reads as explicit steps:

1. Check the existing shared network and materialize selected manifests.
2. Load this bundle's archive and verify every required image.
3. Record unfinished registration owners, then write public registrations.
4. Write selected imports/YAML/Quadlets and changed shared-owner imports.
5. Reload systemd, restart required services and check `is-active`.
6. Acknowledge completed owners and write installed versions/dependency contracts.

The sequence describes the established behavior, including secret materialization
before image loading and possible persistent file changes before a service
failure. It is not rollback or permission to move safety checks earlier/later.
Image failures leave deployed registrations/services untouched. Route changes
restart platform, client metadata/certificate changes restart Identity; unchanged
registrations with no pending work restart neither shared service. Sibling apps
remain running.

Uninstall records its validated own volume inventory, deletion choice, stop
checkpoint and unfinished owners before destructive work. It can resume after
YAML, markers or data are gone. The private `pending-operation.json` persists
across process runs; conflicts are refused rather than guessed away. See
[retry safety](acceptance/RETRY-SAFETY.md). Run one lifecycle command at a time.

Source dev preparation uses the same defaults, registration indexes and renderer
against `build/dev/<component>`. `prepare_standalone()` and
`install_standalone()` isolate the supported root-config examples/test fixtures
from the component path; they are not migration or old-release adapters.

## Persistent state and trust

Component config and `credentials/`, imported archives, registration directories,
installed/dependency markers, retry metadata and Podman data belong to the service
home. Shared CA/network ownership is unchanged. Release code, defaults, manifests
and images are disposable; production never merges new defaults over existing
config or credentials.

Each offline bundle ships the complete `deployment/` package with checksums and
only its own resources/images. Bytecode and private state, including aliases to
declared secrets/credential files, stay out of archives.

Operators recursively add only `<release>/deployment/` to the existing per-bundle
fapolicyd trust file. The CLI expands directory trust to individual file records.
The read-only wait helper requires every current package file, rejects incomplete
or malformed/duplicate records, and checks that all old package entries disappear
after retirement. Other release files and credentials are not trusted. The
wrapper executes via Bash and Python imports run with `-B`; no new allow/crun/memfd
or SELinux rules are introduced. Directory add/delete semantics follow the
[upstream fapolicyd guidance](https://github.com/linux-application-whitelisting/fapolicyd#managing-the-file-trust-source).

No migration code, fallback root deploy.py or compatibility layer for existing
installations is added. Historical pinned-release helpers and reports retain
their original layouts. Fresh target verification of directory trust is still
required; see [refactor verification](acceptance/DEPLOY-REFACTOR.md).

## Private app file delivery (0.4.4)

App `credentials/todo/` files, including the session key and private OIDC client
key, use `SECRET_FILES` (`app1-signing` / `app2-signing`). The backend alone mounts
the Secret read-only at `/certificates`, with explicit keys and file mode `0400`
for the current container-root process. These files no longer use `VOLUME_FILES`
or a signing-PVC import archive. Shared route/client imports keep their existing
public archive normalization. Source files, credential generation, persistent
config precedence and lifecycle retry state are unchanged.

Identity no longer generates or delivers the unused API-secret environment
value. Its API scopes, signing credentials, users and database are unchanged.
There are no new images, automatic migration, credential cleanup or rotation.
Real Podman permissions/isolation remain unverified; see
[credential delivery verification](acceptance/CREDENTIAL-DELIVERY.md).

## Supported layout checks (0.4.5)

Lifecycle commands, dev preparation and the certificate script no longer inspect
historical core/combined-platform paths, services, markers or volumes. There is
no old-layout detector, migration, fallback or automatic cleanup. The supported
component graph and ordinary version/dependency contracts are unchanged. Current
DB preflight still refuses a missing password for an existing database volume;
private path checks, pending-operation validation and scoped deletion remain.
Certificate preparation no longer requires Podman just to check obsolete volumes.

The active acceptance runner no longer offers historical migration/refusal
scenarios. Pinned 0.2.0 fixtures and verification reports remain unchanged;
[cleanup verification](acceptance/LEGACY-CHECK-CLEANUP.md) lists the retained
historical references and current checks.

## File sources and generation (0.4.6)

`SECRET_FILES` and `VOLUME_FILES` each map resource IDs to lists of sources:
`{path: credentials/database, generate: [password]}` creates the missing local
password and delivers files from that directory. `{path: ../clients}` only reads
prepared files. Multiple file/directory sources are supported by one model.
`file_group_sources()` validates the structure; `generated_secret_paths()` resolves
and validates generation without creating or reading files. Generation still
occurs at the same lifecycle boundary after database preflight. The obsolete
separate top-level field and string-only source entries are rejected.

Bundle protection follows every declared Secret source and generated file,
including generation under VOLUME_FILES and symlink aliases outside credentials/.
No config migration/fallback or eager credential creation is introduced.
Persistent config precedence, mounts/names, images and the current component
architecture remain unchanged. See
[file-source verification](acceptance/FILE-SOURCES.md) for results and limits.

## Standard nginx proxy (0.4.7)

Platform now references the stock `docker.io/library/nginx:1.28-alpine` image.
Its public ConfigMap template and the short shell startup command live entirely
in platform manifests; apps/proxy/ is removed. The startup command uses the
container's DNS and a two-variable envsubst whitelist before exec nginx. TLS,
public route imports, dynamic upstreams and health/port settings are preserved.
No deployment renderer, app build/pull helper or bundle builder code changed.
The existing image discovery/pull/archive path handles nginx as a registry image.
Explicit data deletion also removes mounted ConfigMap volumes declared by the
selected component; environment-only ConfigMaps add no volume to that list.
The validated names are saved in the existing uninstall pending record before
any destructive steps, so retry still works after the rendered YAML is removed.
Ordinary uninstall retains these volumes along with the component's other data.
See [proxy verification](acceptance/NGINX-YAML.md) for scope, source review and
checks; real nginx/Podman/SELinux behavior still requires the lab.

## App1 schema initialization (0.4.8)

App1 retains separate database and Todo pods. Sorted manifest order places the
database first in dev and production. The Todo pod's `prepare-database` init
container uses the shared backend image and database password Secret to create
the Todo table idempotently. Podman init type `always` reruns preparation on pod
start; failure prevents ordinary Todo containers from starting. Connection/SQL
timeouts, an availability deadline and a hard process alarm bound the init step.

The app1 backend checks the table under `TODO_SCHEMA_MODE=external`; app2 retains
backend-driven creation using the same DDL. The shared image becomes 0.2.2 and
app/help release VERSION becomes 0.4.8. Platform/Identity versions stay 0.4.7.
No host lifecycle/render/build code, credentials, volumes or dependency rules
change. The existing database-runtime lab action also exercises real init and
replay with a retained row in its disposable database. See
[init verification](acceptance/APP1-INIT.md) for local tests and runtime gaps.
