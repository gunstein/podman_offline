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
