# MyProduct: Todo with Duende and PostgreSQL

A small, runnable Podman example with six pods. The frontend is plain
HTML and JavaScript. The Python backend signs users in with Duende using
Authorization Code + PKCE and `private_key_jwt`. The browser gets an HttpOnly cookie;
the OIDC tokens are never sent to JavaScript. Each user has their own tasks.

```text
Browser ── HTTPS :8443 ── nginx reverse proxy (own pod)
                          ├── /             → frontend :8080 (Todo pod)
                          ├── /auth/, /api/ → Python backend :8000 (same Todo pod)
                          │                    └── Todo PostgreSQL (own pod)
                          ├── /help/        → help pages (own pod)
                          └── /identity/    → Duende (own pod)
                                               └── Identity PostgreSQL (own pod)
```

Only nginx publishes a port. All pods use the Podman network `myproduct`.
There are no Kubernetes Services or Ingress controller; Podman DNS uses the
pod names in the manifests. The Todo pod `myproduct-todo` shares its network
between the frontend on port 8080 and the backend on port 8000.

Todo links to the help pages at **/help/**. The help app runs in its own pod
(`myproduct-help`) and serves plain HTML/CSS through the same HTTPS proxy.
The help is available without signing in and uses no database. The pages live
in `apps/help/`; rebuild the help image when the content changes.

## Run locally, rootless

Requires Podman, OpenSSL, Python 3.6+ and PyYAML on the host. .NET and the Python
app's dependencies are installed only in the images. The first build needs internet.

```sh
./dev/build-images.sh
./scripts/generate-certificates.sh
cp config.example.yaml config.yaml
chmod 600 config.yaml
./dev/dev.sh up
```

Add this line to the host's `/etc/hosts` manually:

```text
127.0.0.1 myproduct-proxy
```

Import **only the CA certificate** `PKI/private/ca.crt` into the browser's local
CA store, and open **https://myproduct-proxy:8443**. Podman resolves the same name
internally, so the browser and the backend use an identical OIDC issuer.
The default setup is meant for one local machine. On other machines, the
DNS name, certificate, `PUBLIC_ORIGIN` and port setup must be adapted together.

The users `alice` and `bob` are created on first start. Their passwords are
generated locally in `generated-certificates/users/alice-password` and
`bob-password`. The passwords are stored as hashes in Duende's PostgreSQL database.
Existing user passwords are not changed automatically if the source files change later.

```sh
podman ps --all --pod
./dev/dev.sh down
```

`down` keeps the database volumes and the Todo certificate volume. A new `up`
imports the `VOLUME_FILES` files again but keeps the existing database content.
The network and named volumes are only removed manually when no longer needed.

## Manifests and certificates

- `manifests/10-configmap.yaml`: shared public address through a config placeholder.
- `20-storage.yaml`: separate PVCs for the two databases and Duende's cookie keys.
- `30-identity-postgres.yaml` and `40-todo-postgres.yaml`: one PostgreSQL pod each.
- `50-identity.yaml`: Duende with a private signing key and certificate from a Secret.
- `60-todo.yaml`: frontend and Python backend in the same pod. Only the backend mounts
  the Todo client certificate/key from a PVC and the database password from a Secret.
- `70-help.yaml`: static help app about signing in, tasks and troubleshooting.
- `80-proxy.yaml`: nginx reverse proxy with the HTTPS certificate from a Secret.

`SECRET_FILES` generates the Secret documents. `VOLUME_FILES.todo-signing`
generates the import archive and the PVC that is mounted read-only in the Python backend.
It contains `todo-client.key`, `todo-client.crt`, the CA certificate and a separate
cookie signing secret. Duende gets only the client's **public** certificate
and verifies the client's signed JWT at the token endpoint. Duende's own
signing key is used for the OIDC tokens. TLS uses a third key pair.
See [PKI](PKI/README.md).

This is a small demo setup: Duende's users live in PostgreSQL, while client and
scope configuration is in code and short-lived OAuth grants are kept in memory.
A sign-in in progress must therefore be restarted after Duende restarts.
Signing out ends the Todo session; the next sign-in always asks for the password again.
The databases use one role per app, without separate migration roles. The PostgreSQL
image's `POSTGRES_USER` creates a superuser in the app's separate cluster; the apps
create and own their tables themselves. Automatic schema creation is only for this simple example.
Duende requires a suitable
[license for production](https://docs.duendesoftware.com/identityserver/overview/licensing/).

## Checking the whole flow

With the app's dependencies in a local test environment:

```sh
python3 -m venv .venv-app
.venv-app/bin/pip install -r apps/todo-backend/requirements.txt
.venv-app/bin/python dev/smoke-test.py
```

This test uses real HTTPS and Duende sign-in with both users, and verifies
CRUD, separation between users, CSRF protection and local sign-out.
It also follows the help links from Todo and checks the pages, navigation,
stylesheet, the /help redirect and 404 for unknown help pages. It
verifies CA/host name and needs no change to `/etc/hosts`. This is an
HTTP integration test; the frontend JavaScript must also be tried in a browser.
The isolated renderer/bundle tests run with `python3 -m unittest discover -s tests`.
See also the small [Podman examples](examples/README.md).

Verified 2026-10-12 with real rootless Podman 5.7.0: all six pods start,
and the whole HTTP integration test passes through nginx. The 84 unit tests
pass with both PyYAML 5.4.1 and 6.0.3. Ruff, Pyright and the Python 3.6
compatibility check for deploy/bundle/tests were clean in that dev run.
This does not document the prod Quadlet or reboot.

## Health checks

All seven app containers have one exec-based `livenessProbe`, enforced by Podman:

| Container | Local check |
| --- | --- |
| identity-postgres-db / todo-postgres-db | `pg_isready` with the same user and database as the PostgreSQL environment variables. |
| identity-app | Bash `/dev/tcp` requires HTTP 200 from `127.0.0.1:8080/identity/health`. |
| todo-backend | Python `urllib.request` requires HTTP 204 from `127.0.0.1:8000/livez`, without database or sign-in. |
| todo-frontend / help-web | BusyBox `wget` against its own `127.0.0.1:8080/`. |
| proxy-nginx | BusyBox `wget` against its own HTTPS `/livez`, with `HTTPS_PORT` from the environment and no certificate check. |

Liveness never depends on other pods. `/api/health` still checks the database
for checks/e2e; it is not used as a probe. The proxy's `/livez` returns 204
itself and never routes to the backend's `/livez`.

`initialDelaySeconds: 90` covers startup, including the apps' up to 60 seconds of
waiting for the database. Podman runs no check during this period; the status is
`starting` for up to 90 seconds after each start, and becomes `healthy` after the next
successful check. The probe runs every 30 seconds with a 5-second timeout; three
failures in a row give `unhealthy` and an automatic restart with `restartPolicy: Always`.
No readiness probe or Containerfile HEALTHCHECK is used.

With `as_product` defined as in the prod instructions:

```sh
as_product podman ps
as_product podman inspect --format '{{.State.Health.Status}}' myproduct-todo-backend
as_product podman healthcheck run myproduct-todo-backend
```

A manual check during the start period is skipped as well. `systemctl is-active` is
still not a health check for individual containers. Rootless Podman uses transient
timers in the service user's systemd instance; linger must be enabled.

## Adding an app

A manifest in `manifests/` makes the app's image visible to the bundle build.
There is no app registry. Go through the points below when you add an app;
database and OIDC are only needed for apps that use them.

| Need | Files and changes |
| --- | --- |
| Code and image | `apps/<app>/Containerfile`; add the app and the right tag to `dev/build-images.sh`, or build/pull the image manually. |
| Pod | `manifests/NN-<app>.yaml`: full image name, `imagePullPolicy: Never`, `restartPolicy: Always`. |
| Health check | One local exec-based `livenessProbe` per container: initialDelay 90, period 30, timeout 5, failureThreshold 3. Init containers have no probe. |
| Product tests | Update the fixed resource counts in `test_real_product_manifests_render_with_dummy_files` in `tests/test_deploy.py`; `tests/test_health.py` checks all probes automatically. |
| Proxy route | A new `location` in `apps/proxy/default.conf`; rebuild the proxy image. |
| Database | Its own postgres pod following `30-identity-postgres.yaml`/`40-todo-postgres.yaml`, a PVC in `20-storage.yaml`, a password file and `SECRET_FILES` in config. For new installations, also update `scripts/generate-certificates.sh`. |
| OIDC | Client, redirect URI and scope in `apps/identity/Program.cs`; client certificate and Secret/PVC in config and manifest. Rebuild the identity image. |
| E2E | A new check in `dev/smoke-test.py`, called from `main`; try the frontend JavaScript in a browser. |
| Acceptance | `healthy()` in `acceptance/remote.sh` reads names from the installed YAML; add the needed DB/OIDC and e2e checks. |
| Documentation | Update the app overview, the Secret volumes listed under uninstall, `acceptance/README.md` and `examples/VM-CHECKLIST.md`. |

Run the unit tests, `./deploy prepare` and dev e2e before building the bundle.
A new tag in a manifest requires exactly that name to be built or pulled locally.
When extending an existing installation, create only the new secrets,
as described under upgrade; keep all existing files.

## Offline bundle and rootless Quadlet

The manifests are the only source of images. The build reads `containers` and
`initContainers` from all `manifests/*.yaml`, removes duplicates and sorts the names.
The images must already be pulled with `podman pull` or built with `podman build`
on the build machine, with exactly the same full name and tag as in the manifest.
`./dev/build-images.sh` does this for the demo.

Prefer full original names, for example `registry.example.com/team/app:1.2.3`,
and `imagePullPolicy: Never`. `localhost/myapp:1.0.0` and names with a registry port
are also accepted. Short names like `postgres:16` and `team/app:1` are rejected. Placeholders in
image names are not supported at build time, and the manifests must contain at least one image.
The bundle needs no separate image list: for a new image version, change the tag
in the manifest; the new image must exist locally before the build. The demo's
`dev/build-images.sh`, however, has a fixed app list and tag that must also be updated
if you use the script to build a new app or version.

Run `./build-bundle.sh` with Podman 4.4 or newer. `bundle.py` uses
`podman save -m` with the default docker-archive format and creates
`dist/myproduct-0.1.0-offline.tar.gz` with manifests, deploy, scripts, Quadlet and
checksums. `images/images.tar` is one archive with all images and their full names
and tags. `images/images.txt` lists the names, one per line. Both files are part
of the checksums. Private keys, local config and PKI are not packaged.

The target machine uses a dedicated system user `myproduct`, with home
`/var/lib/myproduct` (0700), rootless Podman and linger. Host prerequisites:
Podman 5.x with user Quadlet, Python 3.6+/PyYAML, OpenSSL, `newuidmap`/`newgidmap`,
`semanage`, `restorecon`, active firewalld and SELinux Enforcing. On OL9,
`semanage` comes from `policycoreutils-python-utils`; install it before the machine is isolated.
The product installs no packages.

### First installation

The following runs as a normal operator with sudo, from the directory with the archive and
the checksum file. Adjust version, IP, host name and port. The host name must match
DNS, the certificate and `PUBLIC_ORIGIN`; `HTTPS_PORT` and the port in `PUBLIC_ORIGIN`
must change together. The demo's internal OIDC name is `myproduct-proxy`.
Edit `IP_ADDRESS`, `PUBLIC_ORIGIN` and `HTTPS_PORT` in the config with sudoedit.
The port must be identical in `--port`, `HTTPS_PORT` and `PUBLIC_ORIGIN`.

`fapolicyd-cli --update` notifies the daemon and does not wait for the update to finish.
Define this function in the operator's shell before installing or upgrading.
It reads the database until the new and any removed paths match, and stops
on errors or timeout. Only paths and status are printed.

```sh
# Wait, read-only, for exact trust paths after the daemon's asynchronous update.
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

```sh
version=0.1.0
hostname=myproduct-proxy
https_port=8443
archive="myproduct-$version-offline.tar.gz"
release="/var/lib/myproduct/releases/myproduct-$version"
sha256sum -c "$archive.sha256"
stage=$(mktemp -d /tmp/myproduct-install.XXXXXXXX)
tar xzf "$archive" -C "$stage"
sudo bash "$stage/myproduct-$version/scripts/prepare-host.sh" --port "$https_port"
sudo -H -u myproduct mkdir -p /var/lib/myproduct/releases
# The operator opens the archive: myproduct needs no access to the operator's home.
sudo -H -u myproduct tar xzf - -C /var/lib/myproduct/releases < "$archive"
rm -rf -- "$stage"
sudo bash -c 'cd "$1" && sha256sum -c --quiet checksums.sha256' bash "$release"
sudo fapolicyd-cli --file add "$release/deploy.py" --trust-file myproduct
sudo fapolicyd-cli --update
wait_trust "$release/deploy.py"
sudo -H -u myproduct bash "$release/scripts/generate-certificates.sh" --root /var/lib/myproduct "$hostname"
sudo install -o myproduct -g myproduct -m 0600 "$release/config.example.yaml" /var/lib/myproduct/config.yaml
sudoedit /var/lib/myproduct/config.yaml
sudo -H -u myproduct bash -c 'cd "$1" && exec python3 deploy.py install' bash "$release"
sudo systemctl --user -M myproduct@ status myproduct.service
```

The operator does not need to `cd` into the service user's private home. `sudo -H`
sets the right HOME but does not change the working directory. That is why bash does an
explicit `cd` as the service user before install: rootless Podman must be able to open
the working directory again when the process starts in the user's namespace. The operator's
private home is not accessible to the service user. `sudo bash` reads
the preparation script from `/tmp`; the script is not executed directly, so `noexec` on
`/tmp` does not block this form. Any policy denial must still be
investigated, not bypassed with changed permissions or broad trust.

`prepare-host.sh --port <port>` is idempotent and requires an integer 1024–65535.
It reads no config and has no example fallback. The script creates
the account with nologin, assigns at least 65536 subuid/subgid without overlap, sets
the home mode, enables linger and opens the port permanently in firewalld.
Every check gives a clear error. An unexpected equivalence starting with
`/var/lib/myproduct` stops the script and must be removed manually before preparing.

The system user does not get the usual HOME_DIR rules from container-selinux.
Storage therefore uses the equivalence
`/var/lib/myproduct/.local/share/containers = /var/lib/containers`, as described
[in Podman's troubleshooting guide, item 11](https://github.com/containers/podman/blob/main/troubleshooting.md#11-changing-the-location-of-the-graphroot-leads-to-permission-denied).
Overlay, overlay-layers and overlay-images have container_ro_file_t;
overlay-containers has container_var_lib_t; volume content has container_file_t.

The script creates `.config/cni/net.d`, cni.lock and the user's Quadlet directory
before the first Podman call. This prevents the runtime type on the config paths that was
observed in run-6. It labels the home with storage excluded, and only the storage
directory itself without recursion. **Never run restorecon -R or -F on populated
storage.** The script does not change the enforcing state of SELinux or fapolicyd.

Acceptance step 07 compares actual types with selinux.matchpathcon. Outside
storage, `restorecon -n -v -R -e <storage> /var/lib/myproduct` must give empty output.
The separate storage dry run is always logged, and each line must match a justified,
named rule; unknown lines give FAIL. See the [SELinux diagnosis](acceptance/SELINUX-DIAGNOSIS.md).
No AVC/USER_AVC/FANOTIFY denials are allowed. Rootless uses a normal
host socket on port 1024 or higher; the lab filter restricts access to the lab subnet.

The certificate generation above is for demo/test. In real production the
certificates are issued outside the target machine and delivered to the paths in the config. The CA's private
key must not be copied there.

`install` reads config.yaml from the home in the user database (`pwd.getpwuid`).
All prod paths follow this home; install rejects a set `$HOME` that
differs, for example from a wrong sudo configuration. `prepare` still reads the config in the repo root.
Relative paths in `SECRET_FILES` and `VOLUME_FILES` are resolved from the config file's
directory. Absolute paths and `~` work as before. The example config's
paths can therefore be used unchanged in both dev and prod.

`install` rejects root, checks the runtime directory and renders the YAML. If
`XDG_RUNTIME_DIR` is missing, `/run/user/<euid>` is used. A set variable must be
exactly this path; a mismatch is rejected before rendering. A missing directory gives an
error with a hint about linger. Then `podman load -i images/images.tar`
and `podman image exists` run in the service user's storage. Only after a successful
image check are the file archives and Quadlet files written, and `systemctl --user`
runs daemon-reload, restart and is-active. `prepare` is unchanged.

```text
/var/lib/myproduct/                         0700, owned by myproduct
├── config.yaml                            0600, used by all versions
├── generated-certificates/                 0700, persistent keys and passwords
├── PKI/private/                            0700, demo CA
├── .config/containers/systemd/
│   ├── myproduct.kube                     0644
│   ├── myproduct.network                  0644
│   └── myproduct.yaml                     0600 (includes secrets)
├── .local/share/containers/storage/        images, volumes and databases
├── files/                                 0700; tar archives 0600
└── releases/myproduct-<version>/            code, manifests and images; can be deleted
```

`myproduct.network` creates the network automatically and gives the main service a
dependency on `myproduct-network.service`. All pods keep
`restartPolicy: Always`. The user Quadlet uses `WantedBy=default.target` and
linger to start without a login. Podman 5.x adds
`podman-user-wait-network-online.service`; check the generator as the user:

```sh
# Use this function for the Podman commands in operations/uninstall as well.
as_product() {
    sudo -H -u myproduct bash -c '
        cd "$HOME" || exit
        export XDG_RUNTIME_DIR="/run/user/$(id -u)"
        exec "$@"
    ' bash "$@"
}
as_product /usr/lib/systemd/user-generators/podman-user-generator --dryrun
```

`myproduct.kube` gives one service, `myproduct.service`, for all pods. Every
installation, including an upgrade, restarts all pods and the databases.
The service fails if a pod fails at startup. There is no start order
between pods; the apps try to connect to the database for 60 seconds. There is one
installation per service user, with fixed names for the service and the network.
`systemctl is-active` shows the service's state and does not guarantee that every
container is running. Operational checks must also check container status and HTTPS/e2e;
the service can be active even if one container is stopped.

### Upgrade

Config, keys, passwords, CA and the Podman storage belong to the installation, not to a
release. **Do not run generate-certificates.sh when upgrading**, and do not copy
a new example config over the existing config. PostgreSQL sets the password only
at first initialization, the demo users keep their old password hashes,
and the clients must keep trusting the same CA. The script's guard against existing
keys also applies when `--root` is used.

If a new app needs a new database password, create only the new file before
the installation. Example for a new `new-app-db` id (rename it in both config and manifest):

```sh
sudo -H -u myproduct bash -c '
    set -euC
    umask 077
    mkdir -p "$HOME/generated-certificates/new-app-db"
    openssl rand -hex 32 > "$HOME/generated-certificates/new-app-db/password"
'
sudoedit /var/lib/myproduct/config.yaml
```

`set -C` refuses to overwrite an existing password file. Add the new path
under `SECRET_FILES`, and update any other config values the new app needs.
New signing/client certificates are issued separately, in real prod by an external CA,
and delivered as the service user with `umask 077` to new paths. Also update
Duende's public client certificate/client configuration when needed. Do not replace
the existing CA, database passwords, demo passwords or keys by running the whole generator.

Run from the directory with the new archive and checksum file:

```sh
old_version=0.1.0
version=0.1.1
archive="myproduct-$version-offline.tar.gz"
release="/var/lib/myproduct/releases/myproduct-$version"
sha256sum -c "$archive.sha256"
sudo -H -u myproduct tar xzf - -C /var/lib/myproduct/releases < "$archive"
sudo bash -c 'cd "$1" && sha256sum -c --quiet checksums.sha256' bash "$release"
sudo fapolicyd-cli --file add "$release/deploy.py" --trust-file myproduct
sudo fapolicyd-cli --update
wait_trust "$release/deploy.py"
sudo -H -u myproduct bash -c 'cd "$1" && exec python3 deploy.py install' bash "$release"
sudo systemctl --user -M myproduct@ is-active myproduct.service
```

Check that the installation succeeded, that the service is active and that all
containers are running. If anything fails, stop here and keep the old trust. After
a successful installation and check, remove the trust for the old release:

```sh
sudo fapolicyd-cli --file delete "/var/lib/myproduct/releases/myproduct-$old_version/deploy.py" --trust-file myproduct
sudo fapolicyd-cli --update
wait_trust "$release/deploy.py" "/var/lib/myproduct/releases/myproduct-$old_version/deploy.py"
```

After a successful upgrade, old release directories can be deleted once their
trust has been removed. Keep `/var/lib/myproduct/config.yaml`,
`generated-certificates/`, `PKI/`, `files/` and the Podman storage, also when deleting
releases. Back up the persistent state, including the databases.
`PKI/private/ca.key` on the host is only for the demo; in real prod the
certificates are issued externally and delivered to `generated-certificates/` without the CA key.

### fapolicyd and rootless

The checksum check inside the bundle runs as root: the lab's policy allows
root with a trusted RPM program to read Python files too. Then only
the verified `deploy.py` is added to the trust database, so that Python running as
`myproduct` can read it. Repeat the checksum and trust for every newly unpacked version.
Shell scripts run with `bash`, which reads the files without executing scripts directly.
No directories, container runtime or private keys are added to the trust.

On the OL9.8 lab even `sudo crun --version` fails with fapolicyd rule 5.
The audit shows crun's `open_tree` on `/proc/self/exe`, `mount_setattr` and `execveat`,
then `exe=/` and denials when opening libraries. This supports
the explanation that crun runs from a detached mount that fapolicyd has not observed,
so the process is classified as a directly started dynamic loader.
[Red Hat describes the same symptom](https://access.redhat.com/solutions/7072618).

The rootless model uses its own mount namespace. With the lab's
`allow_filesystem_mark = 0`, the containers are expected to be outside fapolicyd's
observation; this is not an approval of their content by fapolicyd.
SELinux stays Enforcing. This explanation must be kept separate from actual
prod verification: the acceptance test and audit document what works on
the target machine. No crun rules, broad trust rules or binary changes are used.

## Secrets on disk and uninstalling

Podman kube play writes Secret content to named volumes under
`/var/lib/myproduct/.local/share/containers/storage/volumes/<secret-name>/_data/`.
The home is 0700, but private keys and passwords stay after `kube down`
or stop. Files removed from the Secret definition can still remain in the volume;
defined files are overwritten. Secret, PVC and ConfigMap names must be unique.
`defaultMode: 0400` protects private keys inside the container, but does not delete
data from the host's disk.

Stop the service before deleting a Secret volume. The operator runs the commands
below. Repeat the trust removal for every installed release that is removed:

```sh
sudo systemctl --user -M myproduct@ stop myproduct.service
as_product podman volume ls
# Example; delete only identified volumes that are not to be kept.
as_product podman volume rm identity-signing
sudo fapolicyd-cli --file delete "$release/deploy.py" --trust-file myproduct
sudo fapolicyd-cli --update
sudo -H -u myproduct rm /var/lib/myproduct/.config/containers/systemd/myproduct.{kube,network,yaml}
sudo systemctl --user -M myproduct@ daemon-reload
sudo loginctl disable-linger myproduct
```

The Secret volumes are `identity-signing`, `identity-client-certificate`,
`identity-database-password`, `identity-demo-users`, `todo-database-password`
and `web-tls`. Keep the database/app data volumes unless they are deliberately deleted.
Do not enable `KubeDownForce`: it can delete the database volumes too.
When all data is deliberately to be removed, an administrator can stop the user instance,
delete the user/home and remove the SELinux equivalence:

```sh
sudo systemctl stop "user@$(id -u myproduct).service"
sudo userdel -r myproduct
sudo semanage fcontext -d /var/lib/myproduct/.local/share/containers
```

Deleting volumes or running `userdel` does not guarantee physical deletion from disk or
backups. The installation flow assumes a clean prod host. Use the [acceptance test](acceptance/README.md)
for prod verification with systemd and reboot.
