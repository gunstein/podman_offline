# Rootless offline Podman demo

Build on a machine with network, transfer checksummed bundles, then install as
one service user on an offline host. Python 3.6+ and PyYAML 5.4.1/6.x are the only
product Python requirements. Podman 5.x, Quadlet, systemd, OpenSSL and Bash are
required on the target. The demo uses Duende IdentityServer, PostgreSQL, two Todo
instances, nginx and a static help app.

## Components and bundles

| Bundle | Components | Public paths |
| --- | --- | --- |
| `myproduct-app1-<v>-offline.tar.gz` | core + app1 | `/identity/`, `/app1/` |
| `myproduct-app2-<v>-offline.tar.gz` | core + app2 | `/identity/`, `/app2/` |
| `myproduct-help-<v>-offline.tar.gz` | help; requires installed core | `/help/` |

Core contains identity, its PostgreSQL pod and the HTTPS proxy. Each Todo has
its own PostgreSQL pod, plus frontend and backend in one pod. Both apps share
identity users but have separate OIDC clients, database volumes and session
cookies. With all components installed there are 8 pods and 10 app containers.
The root path `/` returns 404; use `/app1/` or `/app2/`.

`components/<name>/` holds manifests, an example config and any route/client
registration. `bundles.yaml` defines the three bundle selections. `VERSION`
versions app/help releases; `CORE_VERSION` independently versions shared core.
All Pod, Secret, PVC and ConfigMap names must start with their component prefix;
the renderer rejects other names before generating files.

There is one Quadlet service per component: `myproduct-core`, `myproduct-app1`,
`myproduct-app2` and `myproduct-help`. The identical `myproduct.network` is shared,
installed idempotently and never removed by uninstalling one bundle. App bundles
install missing core, retain equal core, upgrade newer core and refuse older core.
Changed public routes or OIDC clients restart core even when its version is equal.
This causes a short shared sign-in/proxy interruption; app2/help services and data
are not restarted by an app1 upgrade. Unchanged registrations leave equal core
untouched. There is no start order between pods in one component; apps retry their
databases for up to 60 seconds.

This component layout is for fresh installations. It does not automatically
migrate the former monolithic 0.1.x data/config or remove its service. Preserve
that data and plan an explicit migration before replacing an existing deployment.

## Run locally

```sh
./dev/build-images.sh
./dev/pull-images.sh
cp config.example.yaml config.yaml   # edit common dev settings if needed
chmod 600 config.yaml
./dev/dev.sh up
python3 -m venv .venv-app
.venv-app/bin/pip install -r apps/todo-backend/requirements.txt
APP_BASE_PATH=/app1 .venv-app/bin/python dev/smoke-test.py
APP_BASE_PATH=/app2 .venv-app/bin/python dev/smoke-test.py
./dev/dev.sh down
```

The dev helper creates missing demo credentials under `build/dev/`, reuses them
on subsequent starts, and runs `./deploy prepare` followed by `podman kube play`.
Prepare reads the repo's `config.yaml`; per-component dev config, keys and import
archives live under `build/dev/<component>/`. `build/install.yaml` is private
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

One invocation creates all three bundles. Each contains only its components,
`deploy`/`deploy.py`, scripts, Quadlet templates, version metadata and its own
`images/images.tar` (standard docker-archive, `podman save -m`) and `images.txt`.
Checksums cover all shipped files. Apps/dev/tests/examples/acceptance and local
config, passwords and keys are not shipped. Optional component `files/` is for
public product payloads. Declarations in local/example configs prevent generated
secrets from being copied into bundles, including through symlink aliases. Keep
private files out of shipped directories and retain their declarations.

## Config, secrets and persistence

Prod reads `~/core/config.yaml`, `~/app1/config.yaml`, `~/app2/config.yaml` and
`~/help/config.yaml`. Relative `SECRET_FILES`/`VOLUME_FILES` paths are resolved
from that config's directory; absolute paths and `~` are supported. Config keys
are strings, ordinary values are text/integers and `HTTPS_PORT` is an integer.
Duplicate YAML keys, partial placeholders, unresolved references, missing mounts
and colliding Secret/PVC/ConfigMap names are rejected. Whole `@@NAME@@` values
preserve int/string types; ConfigMap data becomes text.

`SECRET_FILES: {id: [paths]}` encodes files into Secrets (about 375 kB per id).
Directories expand one level; nested directories are not allowed for Secrets.
`VOLUME_FILES` creates private import tar archives and PVCs. Podman imports at
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
├── core/, app1/, app2/, help/
│   ├── config.yaml                        0600, retained across releases
│   ├── generated-certificates/            0700, keys/passwords retained
│   └── files/                             0700; import archives 0600
├── PKI/private/                           0700; shared demo CA
├── routes/<component>.conf                public route registrations
├── clients/<component>/                   public OIDC metadata/certificate
├── installed/<component>                  installed version, 0600
├── .config/containers/systemd/             scoped .kube/.yaml + shared .network
├── .local/share/containers/storage/        images, DB data and secret volumes
└── releases/myproduct-<bundle>-<version>/   code/manifests/images, disposable
```

Proxy and identity consume imported volumes, not host bind mounts. The renderer
collects public registrations into current route/client indexes. Only those
indexes are used at runtime: Podman imports do not delete removed files, so stale
files left in volumes must not keep an uninstalled route/client active.

The shared demo CA and core keys/passwords are generated once. Each app gets
its own client private key/certificate and database password; session keys use
GENERATED_SECRETS. Identity receives only public client certificates. Its signing
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
bundle=app1
version=0.2.0
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
for component in core "$bundle"; do
    as_product bash "$release/scripts/generate-certificates.sh" --root /var/lib/myproduct "$component" myproduct-proxy
    if ! sudo test -e "/var/lib/myproduct/$component/config.yaml"; then
        sudo install -o myproduct -g myproduct -m 0600 "$release/components/$component/config.example.yaml" "/var/lib/myproduct/$component/config.yaml"
    fi
done
sudoedit /var/lib/myproduct/core/config.yaml /var/lib/myproduct/app1/config.yaml
sudo -H -u myproduct bash -c 'cd "$1" && exec python3 deploy.py install' bash "$release"
sudo systemctl --user -M myproduct@ status myproduct-core.service myproduct-app1.service
```

Set IP_ADDRESS in core to the target's host IP. Set PUBLIC_ORIGIN/HTTPS_PORT
consistently in each component; use the DNS name passed to the certificate
script. The proxy pod's hostname is derived from PUBLIC_ORIGIN, so app pods
resolve that same HTTPS name internally. Each install validates the user database
home and runtime, renders, loads/verifies images, writes component imports/units
and calls `systemctl --user`. It does not wait for health; do the checks below.

To add app2, repeat checksum/unpack/trust with `bundle=app2`, initialize only app2
credentials/config (keep core's existing config), edit it to match core and install.
To add help, repeat with `bundle=help`; copy only its missing config and install.
Help needs no new credentials. These installs update shared routing/client imports
and restart core, while retaining the other app's service/data.

## Upgrade and uninstall

For an upgrade, verify/unpack/trust the new bundle as above, using the same own
trust file. Reuse persistent config and credentials: do not copy example config
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
client; core reloads the remaining registrations. Network and sibling data/units
are retained. Remove the own deploy.py trust entries after uninstall and update
the trust database. Core is retained while any app or help remains; after removing
all dependents, use `uninstall core` (optionally `--delete-data`) from an app bundle.

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
| Config | Update the component config.example.yaml and its existing prod config; never overwrite existing credentials. |
| Pod/health | Prefixed Pod/Secret/PVC/ConfigMap names, Never pull policy, Always restart and the agreed exec liveness timings. |
| Database | Own PostgreSQL pod/PVC/password; do not reuse another app's cluster/password. |
| Proxy/OIDC | Own route.conf/client.yaml and public certificate; registrations go through imported core volumes and current indexes. |
| Tests | Update real resource counts in tests/test_deploy.py and app-specific assertions; probe tests discover every manifest. |
| E2E | Extend dev/smoke-test.py and acceptance/markers.py with new app/isolation/persistence checks. |
| Docs | Update overview, install/uninstall dependencies, tests/README and acceptance/README. |
