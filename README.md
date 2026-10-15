# Rootless offline Podman demo

Build on a machine with network, transfer checksummed bundles, then install as
one service user on an offline host. Python 3.6+ and PyYAML 5.4.1/6.x are the only
product Python requirements. Podman 5.x, Quadlet, systemd, OpenSSL and Bash are
required on the target. The demo uses Duende IdentityServer, PostgreSQL, two Todo
instances, nginx and a static help app.

Planned work is tracked in [BACKLOG.md](BACKLOG.md).

## Components and bundles

| Bundle | Components | Dependencies | Public paths |
| --- | --- | --- | --- |
| `myproduct-platform-<v>-offline.tar.gz` | platform | none | HTTPS proxy and routing |
| `myproduct-identity-<v>-offline.tar.gz` | identity | platform | `/identity/` |
| `myproduct-app1-<v>-offline.tar.gz` | app1 | platform + identity | `/app1/` |
| `myproduct-app2-<v>-offline.tar.gz` | app2 | platform + identity | `/app2/` |
| `myproduct-help-<v>-offline.tar.gz` | help | platform | `/help/` |

Platform owns the HTTPS proxy, web TLS and public route imports. Identity owns
IdentityServer, its PostgreSQL database, signing keys, API secret, demo users,
Data Protection and public client registrations. Each Todo owns its PostgreSQL
pod, frontend/backend pod, private client key and session material. Both apps
share Identity users but have separate clients, database volumes and cookies.
With all components installed there are 8 pods and 10 app containers. The root
path `/` returns 404; use `/app1/`, `/app2/` or `/help/`.

`components/<name>/` holds manifests, defaults and public route/client
registrations. `bundles.yaml` defines five separate bundles. `VERSION` versions
app/help releases; `PLATFORM_VERSION` and `IDENTITY_VERSION` independently version
the two shared components. All Pod, Secret, PVC and ConfigMap names must start
with their component prefix; the renderer rejects other names before writes.

Each component has its own `myproduct-<component>` Quadlet service. The identical
`myproduct.network` is shared and never removed by component uninstall. Install
platform, then Identity, then either app. Help needs only platform; the proxy
starts without Identity DNS. Bundles contain only their own resources and images.
Only a component's own bundle upgrades it. Equal shared versions retain installed
files, newer versions upgrade and downgrades refuse. New required settings are
checked when that component is rendered. Apps retry their databases for 60 seconds.

| Registration change | Shared service restarted |
| --- | --- |
| Public route only | platform |
| OIDC metadata/public certificate only | identity |
| Both | identity and platform |
| Neither | neither |

The selected app itself restarts on install. Public indexes control active
registrations even when old files remain in imported volumes. An app's private
client key never goes to Identity. Issuer, public paths, client IDs, scopes and
cookies retain their existing values.

Release 0.4.0 separates Identity from the former combined platform of 0.3.0.
It requires a fresh installation. Concrete old core/combined platform config,
credentials, services, version markers or retained volumes cause refusal before
secret generation, image loading or installed-state writes. Missing markers do
not bypass volume checks; failed checks also refuse. Mixed/partial layouts are
refused. No data, keys or credentials are automatically migrated or deleted.
Manage retained installations with their previous release pending a separately
reviewed migration procedure. Monolithic 0.1.x likewise needs a separate plan.

Every `bundle.yaml` declares exact dependencies with inclusive `min` and exclusive
`before` ranges, for example `{platform: {min: 0.4.0, before: 0.5.0}, identity:
{min: 0.4.0, before: 0.5.0}}` for app1/app2. For 0.x, compatibility follows the
minor series; for 1.x and later, the declared major series. Installed requirements
are retained privately under `dependencies/`, independently of old release
directories. Incoming dependencies and every installed dependent's range must
allow a shared upgrade. Missing, malformed or incompatible metadata refuses
before mutation. See [Identity verification](acceptance/IDENTITY-SPLIT.md) for
coverage, local evidence and pending lab commands.

## Configuration and initialization

| File | Role |
| --- | --- |
| `config/common.defaults.yaml` | Shared defaults for initialization and dev |
| `config/dev.yaml.example` | Small example of local dev overrides |
| `config/dev.yaml` | Developer overrides, ignored by Git and excluded from bundles |
| `components/<component>/config.defaults.yaml` | Component-specific defaults, including secret and volume references |
| `/var/lib/myproduct/<component>/config.yaml` | Authoritative persistent production config |

Initialization and dev use exactly one merge rule: common defaults first,
component defaults next, explicit overrides last. Merge is at the top level.
A later value replaces the entire earlier value, including `SECRET_FILES`,
`VOLUME_FILES` and `GENERATED_SECRETS` maps/lists; no recursive merge or list
concatenation takes place. Duplicate YAML keys are rejected in each source file.
Individual layers may be incomplete; the complete merged result is validated.
Dev overrides apply to all rendered components, with no per-component override
syntax. A missing dev file means no overrides; an invalid existing file fails.
`IP_ADDRESS` belongs to platform because only its proxy binds the host address.

From a verified, unpacked bundle, run as the service user:

```sh
as_product python3 "$release/deploy.py" init-config platform
# Or, from the release directory as myproduct: ./deploy init-config platform
```

Only components included in that bundle may be initialized. The command writes
one complete persistent config, mode 0600 in a private 0700 component directory,
without generating secrets, copying certificates, loading images or starting
services. Symlink paths are rejected. An existing file is retained exactly,
even if empty or invalid; installation still validates it.

On a fresh host, initialize platform from its own bundle, edit its settings, prepare
its credentials and install it. Next initialize and install Identity from its own
bundle before either app. Prepare each component’s certificates/credentials with the certificate script,
edit component-specific settings, then install. When a platform config already
exists, Identity/app/help initialization explicitly uses only its actual `PUBLIC_ORIGIN`
and `HTTPS_PORT` as final overrides. Other platform settings are never copied.
An invalid platform config or missing shared setting fails instead of falling back
to release defaults. If platform is installed but its config file is missing, restore
that authoritative file from a private backup before initializing a new component. A help bundle cannot install platform or run without installed
platform. Installation rejects inconsistent shared values; it never rewrites config
to resolve a mismatch.

Production install and upgrade read only persistent component config. Release
defaults are never merged into it, and config is never overwritten or extended
automatically. Existing complete files continue to work unchanged. If a new
release needs an absent key, install fails before image operations with the
persistent file path and key name, without its value. Before retrying, back up
that file privately and explicitly add the required key using `sudoedit`; consult
the release’s defaults and notes for its type and meaning. Add shared changes
consistently to platform and dependents. Defaults are examples for this manual step,
not an automatic migration mechanism. Explicit edits take effect when that
component is rendered during installation. An equal-platform app/help install keeps
installed platform YAML/Quadlet; use a controlled newer-platform release to apply changes
that require rendering platform again. Public route/client imports are updated
independently and restart their respective owners without upgrading their versions.

Relative paths in all three file settings resolve from the materialized config
folder: `/var/lib/myproduct/<component>/` in production and
`build/dev/<component>/` in dev, never from the defaults file. Existing absolute
and `~` paths remain supported for secret/volume inputs. Generated secrets must
stay confined to that component’s config folder, including through symlinks.
Initialization writes path references only; credentials must be prepared separately.

Manifests are rendered before Podman sees them. Whole-value placeholders such as
`Clients__0__AllowedCorsOrigins__0: '@@ALLOWED_CORS_ORIGIN@@'` require a complete
config value, for example `ALLOWED_CORS_ORIGIN: "https://example.test"`.
They preserve YAML types; ConfigMap data is converted to text. Partial string
interpolation and `envsubst` are not supported. Missing values identify their key
and config file without exposing secret values.

Standalone manifest fixtures in `examples/` and registry acceptance retain their
explicit fixture `config.yaml` and persistent `~/config.yaml` paths. These are
separate from the product’s component config model. Historical reports under `~/podman-offline-acceptance-runs/` may retain old
config names; those evidence files are not rewritten.

## Run locally

```sh
./dev/build-images.sh
./dev/pull-images.sh
cp config/dev.yaml.example config/dev.yaml   # optional local overrides
chmod 600 config/dev.yaml
./dev/dev.sh up
python3 -m venv .venv-app
.venv-app/bin/pip install -r apps/todo-backend/requirements.txt
APP_BASE_PATH=/app1 .venv-app/bin/python dev/smoke-test.py
APP_BASE_PATH=/app2 .venv-app/bin/python dev/smoke-test.py
./dev/dev.sh down
```

The dev helper creates missing demo credentials under `build/dev/`, reuses them
on subsequent starts, and runs `./deploy prepare` followed by `podman kube play`.
Run `./deploy prepare` from the source checkout; product bundles reject dev
prepare and use persistent config through install. Standalone fixtures retain
their explicit prepare flow. Component prepare merges common defaults, component
defaults and optional `config/dev.yaml`.
The local overrides apply to every rendered component. Generated config under
`build/dev/<component>/` is output, never an input layer; credentials and data
are retained between renders. Keys and import archives also live there. `build/install.yaml` is private
(0600). Down preserves data volumes. Do not delete dev credentials while keeping
the corresponding database volumes: their initialized passwords would differ.
The default HTTPS name is `myproduct-proxy:8443`; the smoke test maps it locally
without editing `/etc/hosts`. A manual browser needs suitable DNS/hosts and CA
trust. Each app uses `/app1/` or `/app2/`; help is public at `/help/`.

Smoke tests use actual HTTPS, OIDC code/PKCE/private_key_jwt, user isolation,
CRUD, CSRF and help navigation. They withhold auth URLs and response bodies on
failure. Set `PUBLIC_ORIGIN`, `CONNECT_IP`, `SMOKE_CA_FILE` and
`SMOKE_PASSWORD_DIR` when checking another installation. JavaScript behavior
still needs a browser check; this is an HTTP integration test.

## Images and offline bundles

Manifests are the only image list. The build reads containers/initContainers
structurally, deduplicates and sorts full names. Every container must use
`imagePullPolicy: Never`; image placeholders and short names are rejected.

- `localhost/<name>:<tag>` is prepared locally before bundling. The demo build
  helper discovers `localhost/myproduct-<app>:<tag>` from manifests and builds
  `apps/<app>/Containerfile`; the PostgreSQL alias is pulled/tagged explicitly.
- All other full names, including `localhost:<port>/...`, are registry sources.
  Bundling pulls each with `--policy=always` before save. A failed pull stops;
  no cached-image or build fallback is used.

A registry can be any OCI-compatible container registry. Build and publish
those images in your external pipeline, then put their full immutable tags in
component manifests, for example `registry.example.test/team/todo:1.2.3`.
Log in with `podman login <registry>` beforehand; no credentials are handled in
code. For an internal CA use `/etc/containers/certs.d/<registry>/ca.crt` (or the
user-specific certs.d directory). Never disable TLS verification. Prefer tags
that are never reused; digest pinning is deferred until save/load/name behavior
has been verified. Demo localhost tags may be rebuilt while developing an
unreleased version; published release tags must remain immutable.

```sh
./build-bundle.sh
(cd dist && sha256sum -c ./*.sha256)
```

One invocation creates all five bundles. Each contains
`config/common.defaults.yaml`, its components’ `config.defaults.yaml`, only its
components,
`deploy`/`deploy.py`, scripts, Quadlet templates, version metadata and its own
`images/images.tar` (standard docker-archive, `podman save -m`) and `images.txt`.
Checksums cover all shipped files. Apps/dev/tests/examples/acceptance and local
config, passwords and keys are not shipped. Optional component `files/` is for
public product payloads. Declarations in common/component defaults and local/materialized dev config prevent generated
secrets from being copied into bundles, including through symlink aliases. Keep
private files out of shipped directories and retain their declarations.

## Config, secrets and persistence

Component `credentials/` directories contain passwords, session keys, private
keys and certificates, whether generated locally or supplied externally.
`GENERATED_SECRETS` selects the files deploy creates; `SECRET_FILES` and
`VOLUME_FILES` describe how files reach containers. Dev uses
`build/dev/<component>/credentials/`; production uses
`/var/lib/myproduct/<component>/credentials/`. Shared `PKI/private` stays in place.
Release 0.4.1 uses this layout for fresh state only, with no path migration,
aliases or fallback. Container mounts, Secret/PVC names and image tags are unchanged.
See [credential-path verification](acceptance/CREDENTIAL-PATHS.md) for results
and remaining historical references.

`PUBLIC_ORIGIN` must be an HTTPS origin with no credentials, path, query or fragment.
Invalid values are rejected with the config path and field name; their contents
are never included in the error.

Prod reads `~/platform/config.yaml`, `~/identity/config.yaml`, `~/app1/config.yaml`, `~/app2/config.yaml` and
`~/help/config.yaml`. Relative `SECRET_FILES`/`VOLUME_FILES` paths are resolved
from that config's directory; absolute paths and `~` are supported. Config keys
are strings, ordinary values are text/integers and `HTTPS_PORT` is an integer.
Duplicate YAML keys, partial placeholders, unresolved references, missing mounts
and colliding Secret/PVC/ConfigMap names are rejected. Whole `@@NAME@@` values
preserve int/string types; ConfigMap data becomes text.

`SECRET_FILES: {id: [paths]}` encodes files into Secrets (about 375 kB per id).
Directories expand one level; nested directories are not allowed for Secrets.
`VOLUME_FILES` creates private import tar archives and PVCs. Import archives
normalize ownership, modes and timestamps (mtime 0), so identical imported
content has a stable checksum across fresh staging directories. Podman imports at
start, overwriting matching files while preserving app-created/unlisted files.
Symlinks in product output/state paths are refused to prevent sibling writes.

`GENERATED_SECRETS` lists relative files beneath the config directory. Missing
files are created exclusively with 32 random alphanumeric characters, mode 0600
and private parents. Existing nonempty files are retained; empty files are errors.
Absolute/traversing/escaping paths are rejected. Only filenames are logged.
Add new entries to an existing component's persistent config when upgrading,
then deliver them through `SECRET_FILES`; never replace old database passwords.
Back these files up with all other persistent state. See the
[generated-secrets example](examples/generated-secrets/README.md).

```text
/var/lib/myproduct/                         service-user home, 0700
├── platform/, identity/, app1/, app2/, help/
│   ├── config.yaml                        0600, retained across releases
│   ├── credentials/                       0700, passwords/keys/certificates retained
│   └── files/                             0700; import archives 0600
├── PKI/private/                           0700; shared demo CA
├── routes/<component>.conf                public route registrations
├── clients/<component>/                   public OIDC metadata/certificate
├── installed/<component>                  installed version, 0600
├── dependencies/<component>.json          installed version requirements, 0600
├── .config/containers/systemd/             scoped .kube/.yaml + shared .network
├── .local/share/containers/storage/        images, DB data and secret volumes
└── releases/myproduct-<bundle>-<version>/   code/manifests/images, disposable
```

Proxy and identity consume imported volumes, not host bind mounts. The renderer
collects public registrations into current route/client indexes. Only those
indexes are used at runtime: Podman imports do not delete removed files, so stale
files left in volumes must not keep an uninstalled route/client active.

The certificate script creates the shared demo CA and platform web TLS pair once.
Identity owns its signing pair and demo-user passwords. Deploy generates database passwords separately. Each app gets
its own client private key/certificate and database password. Database passwords,
session keys and API keys use GENERATED_SECRETS. Identity receives only public client certificates. Its signing
key is a Secret; each Todo's private signing/session material is in its own PVC.
`PKI/private/ca.key` on the target is for the demo only. In real prod, issue
certificates elsewhere and deliver them to the persistent component paths.
See [PKI](PKI/README.md). PostgreSQL's entrypoint creates a superuser in each
separate cluster; each app creates/owns its tables, with no migration/GRANT role.
Duende needs an appropriate [production license](https://docs.duendesoftware.com/identityserver/overview/licensing/).
Local Todo logout clears only that app's session; shared identity SSO remains.

## First production installation

Run as the operator with sudo. Choose an app bundle first; help alone fails.
`--port`, every `HTTPS_PORT` and the port in `PUBLIC_ORIGIN` must agree.
The archive is opened by the operator and streamed to myproduct, which cannot
read the operator's private home. No `cd` by the operator into the 0700 service
home is needed. Shell scripts run through `bash` under fapolicyd.

```sh
bundle=platform
version=0.4.2
archive="myproduct-$bundle-$version-offline.tar.gz"
sha256sum -c "$archive.sha256"
stage=$(mktemp -d /tmp/myproduct-install.XXXXXXXX)
tar xzf "$archive" -C "$stage"
sudo bash "$stage/myproduct-$bundle-$version/scripts/prepare-host.sh" --port 8443
rm -rf -- "$stage"
```

prepare-host creates the system user myproduct with home `/var/lib/myproduct`
and nologin shell, allocates noncolliding subuid/subgid ranges, enables linger
and opens the HTTPS port permanently. SELinux stays Enforcing. Storage outside
the normal home uses Podman's [troubleshooting guide, point 11](https://github.com/containers/podman/blob/v5.8.2/troubleshooting.md#11-podman-run-fails-with-cannot-open-shared-object-file):
`/var/lib/containers` is mapped to `/var/lib/myproduct/.local/share/containers`.
Unexpected existing equivalences fail instead of being deleted automatically.
Recursive restorecon excludes storage; only the storage directory itself is
restored nonrecursively. Never run recursive or force restorecon on filled storage.

Use these helpers for subsequent commands:

```sh
# Run commands as the service user from its home and systemd runtime.
as_product() {
    sudo -H -u myproduct bash -c '
        cd "$HOME" || exit
        export XDG_RUNTIME_DIR="/run/user/$(id -u)"
        exec "$@"
    ' bash "$@"
}
# Require every installed component container to be running and healthy.
healthy() {
    as_product python3 - <<'HEALTH'
import pathlib
import subprocess
import yaml


def main():
    """Check each installed Pod container without printing private inspect fields."""
    paths = sorted((pathlib.Path.home() / ".config/containers/systemd").glob("myproduct-*.yaml"))
    if not paths:
        raise SystemExit("No installed component manifests")
    for path in paths:
        with path.open() as stream:
            for doc in yaml.safe_load_all(stream):
                if doc.get("kind") != "Pod":
                    continue
                for container in doc["spec"]["containers"]:
                    name = doc["metadata"]["name"] + "-" + container["name"]
                    state = subprocess.check_output(
                        ["podman", "inspect", "--format", "{{.State.Status}} {{.State.Health.Status}}", name],
                        universal_newlines=True, timeout=10).strip()
                    print(name + " " + state)
                    if state != "running healthy":
                        raise SystemExit("Wait for healthy before continuing")


main()
HEALTH
}
# Wait for an exact trust entry and, optionally, removal of an old release.
wait_trust() {
    local wanted=$1 removed=${2:-} dump status attempt
    for attempt in {1..30}; do
        dump=$(timeout 10 sudo -n fapolicyd-cli --dump-db) || {
            echo 'FAIL: could not read trust database' >&2; return 1;
        }
        status=0
        awk -v wanted="$wanted" -v removed="$removed" '
            {
                path=$0
                sub(/^[^[:space:]]+[[:space:]]+/, "", path)
                sub(/[[:space:]]+[0-9]+[[:space:]]+[[:xdigit:]]+[[:space:]]*$/, "", path)
                if (NF < 4 || path !~ /^\// || $(NF-1) !~ /^[0-9]+$/ ||
                    length($NF) != 64 || $NF !~ /^[[:xdigit:]]+$/) invalid=1
                if (path == wanted) found=1
                if (removed != "" && path == removed) old=1
            }
            END { if (NR == 0 || invalid) exit 2; if (!found || old) exit 1 }
        ' <<< "$dump" || status=$?
        case "$status" in
            0) printf 'PASS: trust ready for %s; removed=%s\n' "$wanted" "${removed:-none}"; return;;
            1) printf 'WAIT: trust update pending for %s; removed=%s (%s/30)\n' "$wanted" "${removed:-none}" "$attempt";;
            *) echo 'FAIL: invalid or empty trust database output' >&2; return 1;;
        esac
        if [[ $attempt != 30 ]]; then sleep 1; fi
    done
    echo 'FAIL: trust update did not finish within 30 checks' >&2
    return 1
}
```

Unpack and trust only the verified release's deploy.py. Trust uses one file per
bundle; never add directory trust, private keys, crun rules or memfd rules.
Repeat checksum/trust for each release directory:

```sh
release="/var/lib/myproduct/releases/myproduct-$bundle-$version"
as_product mkdir -p /var/lib/myproduct/releases
as_product tar xzf - -C /var/lib/myproduct/releases < "$archive"
sudo bash -c 'cd "$1" && sha256sum -c --quiet checksums.sha256' bash "$release"
sudo fapolicyd-cli --file add "$release/deploy.py" --trust-file "myproduct-$bundle"
sudo fapolicyd-cli --update
wait_trust "$release/deploy.py"
# Start with bundle=platform, then identity, then app1/app2; help needs only platform.
as_product python3 "$release/deploy.py" init-config "$bundle"
sudoedit "/var/lib/myproduct/$bundle/config.yaml"
# On platform, set PUBLIC_ORIGIN, HTTPS_PORT and IP_ADDRESS first.
as_product bash "$release/scripts/generate-certificates.sh" --root /var/lib/myproduct "$bundle" myproduct-proxy
sudoedit "/var/lib/myproduct/$bundle/config.yaml"
sudo -H -u myproduct bash -c 'cd "$1" && exec python3 deploy.py install' bash "$release"
sudo systemctl --user -M myproduct@ status myproduct-platform.service myproduct-app1.service
```

Set IP_ADDRESS in platform to the target's host IP. Set PUBLIC_ORIGIN/HTTPS_PORT
consistently in each component; use the DNS name passed to the certificate
script. The proxy pod's hostname is derived from PUBLIC_ORIGIN, so app pods
resolve that same HTTPS name internally. Each install validates the user database
home and runtime, renders, loads/verifies images, writes component imports/units
and calls `systemctl --user`. It does not wait for health; do the checks below.

After platform, repeat checksum/unpack/trust with `bundle=identity` and
`IDENTITY_VERSION`; initialize Identity, prepare its credentials and install.
Then repeat with `bundle=app1` and `VERSION`; initialize and install only app1.
To add app2, repeat checksum/unpack/trust with `bundle=app2`, initialize only app2
config with `as_product python3 "$release/deploy.py" init-config app2`, prepare its
credentials, edit component-specific settings and install. Keep existing platform config.
To add help, repeat with `bundle=help`; run `as_product python3 "$release/deploy.py" init-config help` and install.
Help needs no new credentials. These installs update shared routing/client imports
and restart their changed owners (platform for routes, Identity for clients),
while retaining the other app's service/data.

## Upgrade and uninstall

Identity can be upgraded alone: transfer the newer Identity archive/checksum,
verify/unpack/trust it, retain `~/identity/config.yaml` and all credentials, and
install from that bundle. Verify new running image/content, login, both apps'
retained data and database operations before retiring old Identity trust. An
unchanged Identity route leaves platform running; app services remain running.
Platform/app bundles need no retransmission. Installed apps' Identity requirements
must allow the requested version.

Failed lifecycle commands can be repeated from the same component's verified,
trusted bundle. Retry `./deploy install`, or repeat `./deploy uninstall` with
exactly the original `--delete-data` choice. The private
`~/pending-operation.json` records unfinished registration owners or the scoped
uninstall plan before relevant changes. Required imports are rebuilt and owners
restart until the existing `is-active` check succeeds. Confirmed owners are
removed from pending work individually; uninstall remains resumable after its
YAML or data has been removed. Config and credentials remain untouched unless
the original uninstall explicitly requested data deletion.

An unfinished operation blocks other component installs/uninstalls and config
initialization, with a message naming the component and command to finish first.
A changed deletion flag, invalid record or symlinked state is refused. Do not
delete/edit the pending file to bypass the check. Run one lifecycle command at a
time; the record is retry metadata, not a concurrency lock or rollback mechanism.
It cannot reconstruct unknown partial operations performed by older installers.
See [retry verification](acceptance/RETRY-SAFETY.md) for coverage and limits.

Help can be upgraded alone: transfer only the new help archive/checksum, verify
and trust its deploy.py in the help trust file, install, verify healthy services
and new HTTPS help content, then retire the old help release/trust entry. App
bundles need no retransmission. With an unchanged route, platform is not restarted.
A changed help route restarts platform explicitly, without changing platform version or
restarting app services.


For an upgrade, verify/unpack/trust the new bundle as above, using the same own
trust file. Reuse persistent config and credentials: do not copy defaults
or generate a new CA/password set. Install and check health/e2e first. Only after
success remove the old own trust entry, leaving other bundles' trust untouched:

```sh
sudo fapolicyd-cli --file add "$release/deploy.py" --trust-file "myproduct-$bundle"
sudo fapolicyd-cli --update
wait_trust "$release/deploy.py"
sudo -H -u myproduct bash -c 'cd "$1" && exec python3 deploy.py install' bash "$release"
as_product podman ps
healthy
sudo fapolicyd-cli --file delete "/var/lib/myproduct/releases/myproduct-$bundle-$old_version/deploy.py" --trust-file "myproduct-$bundle"
sudo fapolicyd-cli --update
wait_trust "$release/deploy.py" "/var/lib/myproduct/releases/myproduct-$bundle-$old_version/deploy.py"
```

Use the `healthy` helper defined above. Also verify HTTPS and application e2e
before removing the previous trust entry.

Then old release directories can be deleted. Keep component configs, credentials,
files, shared PKI and Podman storage. Back up databases and private persistent
state; none of it belongs to a release directory.

Use a currently trusted release of the bundle to uninstall its own component:

```sh
as_product python3 "$release/deploy.py" uninstall
# Destructive option: also delete this component's data/secret volumes and state.
as_product python3 "$release/deploy.py" uninstall --delete-data
```

Choose one of those commands. Default uninstall retains data/config/credentials
for reinstall. It removes only the own service, version marker, route and public
client; only the changed registration owners reload their imports. Network and sibling data/units
are retained. Remove the own deploy.py trust entries after uninstall and update
the trust database. Identity cannot be removed while either app remains; help
does not block it. Platform cannot be removed while Identity, apps or help remain.
After removing dependents, uninstall Identity and platform from their own bundles.

Podman Secret contents also remain in named volumes after down/stop; removed
Secret keys can remain there. The private home/storage restricts host access.
Explicit own-data deletion removes those volumes too. Never enable KubeDownForce:
it can delete database volumes. At final host removal, remove all release trust,
`loginctl disable-linger myproduct`, remove the storage fcontext equivalence with
`semanage fcontext -d /var/lib/myproduct/.local/share/containers`, and optionally
`userdel -r myproduct`. These are destructive operator choices, not bundle install steps.

Rootless is the only production mode. On the OL9.8 lab, rootful crun fails with
fapolicyd rule 5 while loading libraries after its detached-mount clone; see
[Red Hat's symptom](https://access.redhat.com/solutions/7072618).
With allow_filesystem_mark=0, rootless container namespaces are outside fapolicyd's
observation, not approved by it. SELinux remains Enforcing. Host systemd health
launchers still need clean audit evidence; no security rules are weakened.

## Health checks and acceptance

Every ordinary container has one exec liveness probe: initial delay 90 seconds,
period 30, timeout 5, three failures. Status is starting during the start period
after each restart. PostgreSQL uses pg_isready, identity checks its local /health
via Bash /dev/tcp, backend uses Python against local /livez, frontend/help use
local wget and proxy uses wget against its own HTTPS /livez. No probe depends on
another pod. Backend /api/health checks the database only for e2e/control.

```sh
as_product podman ps
as_product podman inspect --format '{{.State.Health.Status}}' app1-todo-backend
as_product podman healthcheck run app1-todo-backend
as_product /usr/lib/systemd/user-generators/podman-user-generator --dryrun
```

systemctl is-active is not an individual container health check. Linger must
keep the rootless timer/user instance alive. The manual
[VM checklist](examples/VM-CHECKLIST.md) covers policy-based labels and read-only
restorecon classifications. Local [unit tests](tests/README.md) need no Podman;
[examples](examples/README.md) exercise real Podman; the
[acceptance harness](acceptance/README.md) tests clean dev-to-offline-prod snapshots,
registry-only downloads, HTTPS, crash/hang recovery, reboot and upgrades.
Previous monolithic run-23 passed on 2277a71; component acceptance results must
be recorded separately and old evidence is never changed.

## Adding an app

| Need | Files and changes |
| --- | --- |
| Component/bundle | Add component manifests/config, bundle selection and validated names/services/state paths. Extend the fixed demo component IDs and dependencies deliberately. |
| Image | Add apps/<app>/Containerfile for a local myproduct image, or publish a full registry tag; image lists come from manifests. |
| Config | Update common/component defaults for future initialization and dev. Operators explicitly edit existing prod config; never overwrite credentials. |
| Pod/health | Prefixed Pod/Secret/PVC/ConfigMap names, Never pull policy, Always restart and the agreed exec liveness timings. |
| Database | Own PostgreSQL pod/PVC/password; do not reuse another app's cluster/password. |
| Proxy/OIDC | Own route.conf/client.yaml and public certificate; routes go to platform imports, public client metadata to Identity imports, through current indexes. |
| Tests | Update real resource counts in tests/test_deploy.py and app-specific assertions; probe tests discover every manifest. |
| E2E | Extend dev/smoke-test.py and acceptance/markers.py with new app/isolation/persistence checks. |
| Docs | Update overview, install/uninstall dependencies, tests/README and acceptance/README. |


## PostgreSQL configuration and credentials

Host, port, user and database name are ordinary component configuration. The
password is generated once with `GENERATED_SECRETS` and retained as persistent
secret state. `SECRET_FILES` delivers it as a Kubernetes Secret. PostgreSQL uses
that Secret for first initialization, and its client uses the same password.
Applications requiring a complete connection string build it at runtime and
consume it as an environment variable.

Each database-owning component has `DB_HOST`, `DB_PORT`, `DB_USER` and `DB_NAME`
in its `config.defaults.yaml`. The port must be quoted text containing an integer
from 1 through 65535. A top-level dev `DB_PORT` override applies to all database
components; help can carry that unused value without requiring a database. Server `POSTGRES_USER`, `POSTGRES_DB` and `PGPORT`, and client
`DB_*` environment values use whole-value placeholders; no password placeholder
or complete connection string is rendered into YAML or written to disk.

| Owner | DB host | User / database | Persistent password below component directory | Secret / key | PostgreSQL volume | Client |
| --- | --- | --- | --- | --- | --- | --- |
| identity | identity-postgres | identity / identity | credentials/identity-db/password | identity-database-password / password | identity-data | Identity |
| app1 | app1-postgres | todo / todo | credentials/database/password | app1-database-password / password | app1-data | app1 Todo backend |
| app2 | app2-postgres | todo / todo | credentials/database/password | app2-database-password / password | app2-data | app2 Todo backend |

The component directory is `/var/lib/myproduct/<component>` in production and
`build/dev/<component>` in dev. No DB settings belong in common defaults.
The table documents default identities; manifests/config remain the source of
truth. The two Todo users have the same name in **different clusters** and have
independently generated credentials.

Identity's in-image `DatabaseEnvironment.cs` runs before ASP.NET startup. It reads
ordinary `DB_*` environment values and `/run/secrets/database/password`, validates
parameters, and uses [NpgsqlConnectionStringBuilder](https://www.npgsql.org/doc/connection-string-parameters.html) to set
`ConnectionStrings__Default`. Identity then connects **only** through that environment
value. The bootstrap and web application share the same process: there is no
shell wrapper, child process, host executable or signal-forwarding problem.
The existing entrypoint remains `dotnet Identity.dll`. Its `--database-check`
mode performs a real connection and `SELECT 1` through the same environment path,
with only a pass/fail result; it never prints the string. New code and its existing
Npgsql dependency are built into the offline Identity image. There is no Podman
`$(VAR)` expansion dependency, startup download, `eval` or secret in argv.

The Todo examples keep an alternative application interface: `database.py` reads
the same `DB_*` values and mounted Secret file, and passes separate keyword
parameters to `psycopg`. It does not use .NET connection-string syntax. Dev and
production use the same images, secret keys, parameter validation and startup code.

Password files must contain nonempty UTF-8 text. Like the PostgreSQL image’s
[`file_env`](https://github.com/docker-library/postgres/blob/master/17/bookworm/docker-entrypoint.sh)
shell command substitution, clients remove **only trailing LF bytes**;
spaces, tabs, dollar signs, semicolons, quotes and equals signs are preserved.
Embedded LF, CR (including CRLF) and NUL are rejected because initdb's password-file
interface cannot safely represent multiline credentials consistently. Existing
files are never rewritten to normalize them. Npgsql handles connection-string
quoting; psycopg receives keyword arguments. Passwords are not restricted to the
new generator's alphanumeric alphabet.

Before component rendering or secret generation, deploy derives the server's
password Secret and database PVC from its manifest. If the file exists, it must
be valid and is retained byte-for-byte. If it is missing, `podman volume exists`
must explicitly report absence before generation is allowed. An existing volume
is conservatively treated as retained database state, even if empty or there is
no installed marker. Podman failures stop the operation. The error names the file
and volume and tells the operator to restore the password from backup or follow a
separate recovery procedure. No volume is deleted, inspected for reinitialization,
or repaired automatically. Dev preparation now needs access to its rootless Podman
volume store when a DB password is missing; `dev/dev.sh up` performs this preflight
before creating certificate state, and `./deploy prepare` performs it before
config output or any generated secrets. Ordinary YAML rendering has no Podman lookup.

PostgreSQL does not update an existing user's password when its Secret file changes.
Client startup verifies authentication with an actual connection. Npgsql reports
SQLSTATE 28P01 for wrong passwords. Psycopg/libpq can omit SQLSTATE during
handshake failure; its private PostgreSQL FATAL password-authentication reply is
classified without printing it. DNS/network failures do not match that reply. Mismatches fail
with a sanitized authentication error; no `ALTER ROLE`, privilege changes or automatic
recovery occurs. Back up and restore the database volume **and** its password file
together. A lost password cannot be replaced with a fresh random password for an
existing database.

### Historical database-password upgrade

The 0.2.0-to-0.2.1 manual database-config upgrade applies only to the former core
layout. Its original instructions and evidence are retained at
[commit 511099e](https://github.com/gunstein/podman_offline/tree/511099e7e056d0d18c4ade95067c30a54c48bec4).
Do not apply those steps as a migration to 0.4.0: this release explicitly
refuses retained core and combined platform/Identity state. See [IDENTITY-SPLIT.md](acceptance/IDENTITY-SPLIT.md)
for the compatibility boundary and lab commands.

Credentials in the runtime environment are sensitive: do not dump environment,
full inspect objects or connection strings during diagnosis. Administrators and
people with container runtime access can access that state. Acceptance emits only
bounded pass/fail observations and authentication classification, with private input
kept out of argv and evidence.

Password rotation is a separate future task. For each row above it must coordinate
the database user's password, persistent password file and running clients. Session
keys, demo-user passwords, OIDC keys and certificates have different lifecycles.
This release implements no rotation command, dual credentials or rollback framework.
