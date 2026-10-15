# Credential paths (0.4.1)

Fresh installations use `credentials/` below each component's state directory,
including `build/dev/<component>/credentials/` in dev. The older sections below
retain their historical paths and evidence. No credentials are migrated and no
fallback path is provided. See [CREDENTIAL-PATHS.md](CREDENTIAL-PATHS.md) for current
verification results and pending fresh-install lab commands.

---

# Current Identity acceptance (0.4.0)

From a clean committed checkout, run each against disposable lab snapshots:

```sh
python3 acceptance/acceptance.py --run identity-app1-first --first-app app1 run
python3 acceptance/acceptance.py --run identity-app2-first --first-app app2 run
python3 acceptance/acceptance.py --run identity-upgrade --identity-only run
python3 acceptance/acceptance.py --run help-no-identity --platform-help-only run
```

These commands reset both configured lab VMs. The full matrix retains reboot,
app-only, help-only and platform-only checks and adds an actual Identity-only
image/content upgrade. `--identity-only` focuses on that upgrade with both apps;
`--platform-help-only` installs no Identity and checks HTTPS help through the proxy.
Only the changed component's archive/checksum is transferred during its upgrade.
See [IDENTITY-SPLIT.md](IDENTITY-SPLIT.md) for evidence and remaining lab work.

The former platform/core documentation below is historical. Current bundles are
platform, identity, app1, app2 and help; current credentials belong under identity.
`--legacy-refusal` still checks retained genuine core 0.2.0 against current code.
The successful historical `--upgrade-020` must run at commit `511099e`.

---

# Current platform acceptance (0.3.0)

Run the normal fresh-install/lifecycle matrix from a clean committed checkout:

```sh
python3 acceptance/acceptance.py --run platform-app1-first --first-app app1 run
python3 acceptance/acceptance.py --run platform-app2-first --first-app app2 run
python3 acceptance/acceptance.py --run platform-help --help-only run
```

Each run resets the configured disposable lab VMs. Platform is transferred and
installed separately before the chosen first app. All four bundles are checked;
app-only, help-only and platform-only upgrades preserve unaffected components.
Platform version requirements and installed dependency metadata are enforced.

Check the new compatibility boundary against genuine old code/images:

```sh
python3 acceptance/acceptance.py --run platform-core-refusal --legacy-refusal run
```

This installs pinned core 0.2.0 using the unchanged historical harness, creates
user data, then requires current platform init/install/uninstall to refuse it.
Private state, volumes, credentials, process identities and old user data must
remain unchanged. No migration or cleanup is performed.

The historical successful 0.2.0-to-0.2.1 upgrade remains at commit `511099e`:
run `--upgrade-020` from a checkout of that commit, before running a resettable
platform scenario. The current CLI rejects that flag before resetting any VM.
See [PLATFORM-RENAME.md](PLATFORM-RENAME.md) for scope, local checks and lab gaps.

The documentation below is retained verbatim as historical core-layout guidance
and evidence through 0.2.1; its bundle/filename assumptions do not describe 0.3.0.

---

# Acceptance: dev → bundle → offline prod

Run from the controller (a Linux laptop with Python 3.11+, git, SSH and scp):

```sh
python3 acceptance/acceptance.py --run 2026-10-13-run-24 run
# Separate fresh-snapshot run for the reverse installation order.
python3 acceptance/acceptance.py --run 2026-10-13-run-25 --first-app app2 run
```

**This rolls both configured VMs back to their snapshots and deletes their
current state.** Use only the two disposable lab VMs. Starting a run is
consent to rollback, network isolation, installation and reboot in these VMs.
No root access is needed on the controller. All controller tools use only the
Python standard library. VM-1 uses a separate venv for the HTTP tests.

## One-time setup

1. Create two Oracle Linux 9 VMs on the lab network. Use the same CPU architecture,
   enough disk for the .NET/Python/nginx images and the bundle, SELinux enforcing
   and active firewalld. VM-2 is the hardened production target and must have fapolicyd
   active. VM-1 is the developer machine, matching the laptop in `podman_test`,
   and must have fapolicyd inactive and disabled. That difference is established only
   when `clean-dev` is created, never during an acceptance run.
   VM-1 must have internet. VM-2 needs internet only during this preparation.
2. Install the prerequisites **before the snapshot**, on both VMs:

   ```sh
   sudo dnf install -y podman python3 python3-pyyaml openssl curl git tar gzip nftables firewalld fapolicyd policycoreutils-python-utils
   sudo systemctl enable --now firewalld
   python3 -c 'import yaml, venv'
   podman --version
   test -x /usr/lib/systemd/user-generators/podman-user-generator
   ```

   VM-1 must be able to build rootless and download Python packages. The system Python on
   VM-2 with PyYAML is enough; nothing is installed with pip there. Use Podman with
   user Quadlet and multi-image save (Podman 5.x); the actual versions are recorded in the report.
   No app images may be preloaded to hide gaps in the bundle.
3. Add the laptop's SSH key to the user's authorized_keys and confirm the SSH host keys
   on the laptop. The test uses `StrictHostKeyChecking=yes`. Enable lingering for
   the lab user so that rootless containers and the runtime directory survive SSH:

   ```sh
   sudo loginctl enable-linger "$USER"
   printf '%s ALL=(ALL) NOPASSWD: ALL\n' "$USER" | sudo tee /etc/sudoers.d/90-offline-acceptance
   sudo chmod 0440 /etc/sudoers.d/90-offline-acceptance
   sudo visudo -c
   sudo -n true
   ```

   These are lab permissions, not a production recommendation. The journal should be
   persistent. Check the clock/NTP before the offline test.
4. Create a Proxmox API token user limited to these two VM IDs with
   `VM.Audit`, `VM.PowerMgmt`, `VM.Snapshot.Rollback`, plus audit access to
   task status, HA and firewall settings. The token needs no right to
   change node/datacenter firewalls. Create a token file with mode 0600 outside Git:

   ```text
   PVE_HOST=<DNS name matching the Proxmox certificate>
   PVE_NODE=<node>
   PVE_TOKEN_ID=<user@realm!token>
   PVE_TOKEN_SECRET=<secret value>
   PVE_CA=/absolute/path/pve-root-ca.pem
   ```

   An existing token and CA from `podman_test` can be used. The TLS chain and host name
   are verified; only Python's newer STRICT requirement for Key Usage in the Proxmox root CA
   is relaxed, as in the inspiration repo's client. The token is sent only in an HTTP header.
5. Check that both VMs are clean: no pods, containers, volumes or
   Secrets in either rootless or rootful storage; no
   `/etc/containers/systemd/myproduct.*`; no user `myproduct` or
   `/var/lib/myproduct`. These state requirements are checked after rollback,
   before isolation/installation (an earlier failed run may remain before rollback). Do not put the lab VMs under Proxmox HA.
   Shut the VMs down cleanly, take the snapshot `clean-agent` and start them again. The snapshot
   must contain SSH/sudo, packages and network, but no application state.
   This matches the preparation in `podman_test`'s
   `deploy/scripts/lab/prepare-agent-snapshots.sh`. Do not run that script blindly:
   it has lab-specific VM IDs and overwrites guest state.
   For VM-1 a separate snapshot is created from `clean-agent` with the script below.
   The original snapshot is kept for `podman_test`. No packages,
   trust rules, SELinux or firewall settings are changed.

6. The Proxmox VM firewall must be disabled and the NICs connected in the baseline.
   A snapshot rollback does not necessarily reset external firewall rules.
   Readiness rejects deviations; it does not change node/datacenter rules.
7. Copy `lab.example.env` to
   `~/.config/podman-offline-acceptance/lab.env`, fill in verified values,
   set the directory to 0700 and the file to 0600. Never guess VM IDs or IPs.
   `LAB_CIDR` is the actual lab subnet (/24 or narrower).
   `PROD_HOST` is the app's name, not necessarily the VM's OS host name. The current
   product uses `myproduct-proxy`, which Podman DNS also resolves internally.
   The external HTTP test uses `CONNECT_IP` and needs no change to `/etc/hosts`.

## Create the developer profile once

After filling in the configuration file above, run on the controller:

```sh
mkdir -p -m 700 ~/podman-offline-acceptance-runs/preparations
# Use a new log file name and keep the log.
(umask 077; python3 acceptance/prepare_dev_snapshot.py --create   > ~/podman-offline-acceptance-runs/preparations/clean-dev.log 2>&1)
```

The script stops the VM configured as DEV, rolls it back to
`clean-agent`, starts it, checks the baseline and runs exactly
`sudo systemctl disable --now fapolicyd`. It still checks Enforcing
and active firewalld, shuts the VM down cleanly, creates `clean-dev` and starts
it again with a new profile check. It rejects an existing `clean-dev`, checks
that `clean-agent`'s snapshot configuration is preserved and sends no operations
to PROD. Then update the local `lab.env` to `DEV_SNAPSHOT=clean-dev`;
`PROD_SNAPSHOT=clean-agent` stays.

Readiness requires DEV: fapolicyd inactive/disabled, PROD: fapolicyd active,
and both: SELinux Enforcing and firewalld active. The profiles are recorded before
rollback and checked again from the snapshots after rollback. A wrong profile
stops the run, never an automatic change. Both VMs must therefore be running with
the right profile before readiness.

## Running and evidence

Commit test code and any allowed smoke changes first: readiness requires a
clean checkout. No push is needed: a Git bundle of exactly HEAD is sent to VM-1
and cloned there. Both local commits and offline Git access are therefore supported.
The product's offline bundle uses prepared localhost/ demo images and pulls any
registry names before saving. Dev build and pull are separate steps; the demo
still builds its app images from source in every clean run.

For a private container registry deployment, VM-1's build user must already have a
working `podman login <registry>` and public CA certificate under
`~/.config/containers/certs.d/<registry-host[:port]>/ca.crt` (or the system
`/etc/containers/certs.d` equivalent) in the clean dev profile. Never put an
auth file, password or registry token in lab.env, Git or evidence. The default
demo needs no private registry credentials; real container registry authentication and
repository paths are not tested by the temporary registry scenario below.

The steps run in a fixed order: clean start, isolation, dev, bundle, installation,
checks, life cycle, reboot and upgrade. VM-2 is isolated **before the transfer**, with
a separate nftables filter and an enabled systemd oneshot unit before the network starts.
Only incoming SSH/HTTPS from the lab subnet is allowed, plus established
traffic and Podman's internal DNS. Outgoing traffic outside the lab network is blocked,
and external DNS requests are blocked too, also against the lab's DNS server. The internal
Podman network is allowed. IPv6 gets no external outgoing permission.
Firewalld stays active; opening HTTPS for the lab subnet is a documented
installation requirement. No incoming database ports are opened.

Isolation is proven with a registry curl, a public DNS lookup and a failed pull,
and repeated after reboot. A failed program lookup does not count as network evidence.
The test's evidence pull happens before installation; later journal checks for the product's
pull attempts start only at install. The network isolation is not removed afterwards.

Reports and artifacts are stored in
`~/podman-offline-acceptance-runs/<run-id>/` (0700), outside Git:

- `logs/<step>.log`: time, exact command and any stdin code, full
  output and exit codes. Expected failures in the blocking tests are explicitly marked.
- `record.jsonl`: one final result per step with duration and log path.
- `REPORT.md`: verdict, revision, clean checkout, VERSION, bundle SHA256, VM facts,
  boot IDs and timings. Fields that were not reached are absent.
- `EVIDENCE.md`: the generated report plus excerpts and SHA256 for each full log.
- The source Git bundle and the product bundle/checksum when those steps are reached.

The first failure gives `NOT CLEAN` and stops all following test steps. After a failure only read-only
prod launcher diagnostics, collection of the prod audit and cleanup of transferred secrets run. A Podman `Error:` with
exit 0 also counts as a failure. Run IDs and steps can never be reused. Readiness can
fail before rollback: then no clean-start test has run, and the report says so.
Do not repair VMs or change code during a run. There are no automatic new runs.

The CA certificate and demo passwords are transferred with scp to 0700 directories under
`$XDG_RUNTIME_DIR` on the controller and VM-1. No private signing or CA keys
are moved. Passwords are not logged; known tokens/passwords are also masked in the log writer.
`11-cleanup` removes transferred files, also after a failure. If SSH to VM-1 is down,
the cleanup fails and the verdict cannot be CLEAN PASS; the remote
runtime directory must then be removed when access returns or after a reboot. SIGKILL or power loss
can interrupt the cleanup; keep the run folder and use a new run ID next time.
The product's own Secret volumes on VM-2 stay as evidence after a stop.

## What the test actually requires

The product uses Always, a network Quadlet, name checks and deferred archive writes. The test therefore does not create the product network manually.
It checks every container from all installed component YAML files: ten app containers
in eight pods after app1, app2 and help. The first app is selected by --first-app;
run both app1-first and app2-first as separate clean-snapshot runs. Help alone must
refuse missing core without writing component state. Each subsequent install has
an explicit health wait, with no unknown, missing or duplicate app containers allowed.

The two Todo instances get full HTTPS e2e and independent Alice/Bob markers.
The shared-login step signs in once per direction and proves that the other app
uses that identity session without another password form, keeps app cookies scoped,
and cannot read the first app's database rows. Help is upgraded independently,
then app1 with equal core, then app1 with newer core. All private config/credential
hashes must remain identical; only names and same/changed are logged.
Before/after observations require app2/help PID, StartedAt and RestartCount, their
version markers and their own trust records to be unchanged. App1 is then
uninstalled with data retained: its route returns 404 and app2/help e2e, markers,
health and the shared network must still work.

`09-crash` tests an unexpected
process crash. The step reads PID, start time and restart count from inspect JSON and
sends one `sudo -n kill -KILL <host PID>`. Within 60 seconds it requires Running,
a restart count increased by exactly one, a new PID, a new start time and no StoppedByUser.
Then all containers and `/app1/api/health` through the HTTPS proxy are checked
with the installation's CA before the markers are read.

`podman kill` is not used to simulate a crash: Podman marks it as an
[explicit user stop](https://github.com/containers/podman/blob/v5.8.2/docs/source/markdown/options/restart.md)
and prevents an automatic restart. Run-11 documents the earlier test;
its result and evidence are preserved.
Markers are created for Alice and Bob, checked after start/restart/crash/reboot and
kept in the database for inspection. The HTTP tests do not run JavaScript in a browser.

## Local checks of the test harness

```sh
python3 -m unittest discover -s acceptance -p 'test_*.py'
bash -n acceptance/remote.sh
ruff check acceptance/ dev/smoke-test.py
ruff format --check acceptance/ dev/smoke-test.py
pyright acceptance/ dev/smoke-test.py
```

The 141 local tests stub/simulate failures and cover stop rules, masking of secrets,
cleanup, duplicate run IDs/steps and that incomplete runs never become CLEAN PASS.

## Registry source acceptance

`03-build-images` builds local demo images using their manifest tags;
`03-pull-images` fetches any registry names without a build fallback.
`03-registry-test` starts the pinned `docker.io/library/registry:3.0.0` image
rootless on VM-1, bound only to a randomly allocated 127.0.0.1 port. It uses
a self-signed TLS test certificate and an authority-specific user certs.d entry.
No insecure-registry flag, system CA update, SELinux relabeling or fapolicyd
policy change is made. Private TLS files live in a 0700 runtime directory.
The server, its anonymous storage, the test CA entry and private files are
removed automatically, including after an unexpected test failure.

The test pulls public BusyBox, pushes it to that registry, removes its source
image and all fixture aliases from the local image cache, then bundles its
fully qualified registry name in a separate fixture checkout. It requires
successful manifest and blob GETs in the projected registry access log and
an exact pull/save sequence with zero builds. The log parser validates JSON
objects and complete Combined Log Format access records separately on each
stream. Registry 3.0.0 emits Combined records even when its application logger
uses JSON ([Distribution handler](https://github.com/distribution/distribution/blob/v3.0.0/registry/registry.go#L145),
[Gorilla format](https://github.com/gorilla/handlers/blob/v1.5.2/logging.go#L192)).
Only GET method, an allowlisted manifest/blob path without a query, and status
are projected. Referrers, user agents, headers and arbitrary messages are never
printed. Unknown or malformed lines fail, as does a failing log command or
missing HTTP 200 evidence for either artifact type.

It also runs both dev helpers:
the build helper must do nothing for registry-only manifests, and the pull
helper must fetch the registry image.

Two planned negative cases must fail without save or build fallback: a missing
registry tag with a cached alias, and a stopped registry with a cached valid
image. Each requires bundle exit 1 and the image/login hint. Their public
diagnostics are marked as expected failures, not ignored acceptance failures.
The examples use the BusyBox image downloaded by the positive case.

`05-registry-transfer` copies only the positive fixture bundle and checksum
through the controller. After the real product installation,
`07-registry-offline` verifies outer/inner checksums, loads the archive as
myproduct and proves the exact registry name exists. A temporary container
runs with `--pull=never --network=none` and removes itself; the product's exact
healthy inventory and audit are checked afterwards. VM-2 has no test registry
or its CA/credentials and remains offline. No test container is left behind.

## Prod operator and audit evidence

Prod runs as the lab user with sudo exactly as in the product's [README](../README.md):
temporary unpacking, prepare-host, a release under /var/lib/myproduct, inner
checksums as root and trust of deploy.py only, certificates as myproduct,
per-component config created exclusively with mode 0600,
and install as myproduct. The user's HOME is set with sudo -H, and bash changes the working directory as
the service user before install and Podman. This is needed when the operator's
home is 0700; sudo -H alone keeps the inaccessible working directory. No rootful
product resources may be created. Step 07 checks ownership/mode, SELinux labels,
the user generator's network dependency and that the rootful container storage is empty.
Step 07 uses the same Python heredoc on stdin to sudo python3 as before.
The selinux module is required (policycoreutils-python-utils); its absence gives a clear FAIL.
Policy probes confirm the equivalence; actual types are compared with
selinux.matchpathcon using stat.S_IFMT(os.lstat(path).st_mode) for existing
paths. Only the two explicit policy probes use mode 0. An lstat error gives
FAIL without a fallback lookup; link targets are not followed. Overlay, overlay-layers and overlay-images are ro, while
overlay-containers is container_var_lib_t and volume content container_file_t.
Outside storage, an empty restorecon -n -v -R -e <storage> /var/lib/myproduct is required.
The storage dry run is logged separately and every line must be classified with [the rules and
the run-6 table](SELINUX-DIAGNOSIS.md). Unknown lines give FAIL.
No AVC/USER_AVC/FANOTIFY since the start is allowed. No labels are repaired in
the check steps, and no restorecon without -n, -F or chcon is used there.
The preparation excludes storage from recursive relabeling, also when repeated;
never run restorecon -R or -F on populated storage.
Prepare-host opens HTTPS in firewalld; the nft filter restricts access to the lab subnet.

The CA and passwords are read through sudo as myproduct directly into private files on
the controller, never into a log; then they go with scp to VM-1's private runtime directory.
The life cycle uses systemctl --user -M myproduct@, and Podman as myproduct with
the user's XDG_RUNTIME_DIR. Reboot must work without a login as myproduct.

Once PROD has been rolled back and SSH is available, FANOTIFY,
AVC and USER_AVC are collected at the end, both on success and on failure. The start time is stored as an epoch.
The VM's ausearch expects the date in the locale's %x format and the time as a separate argument:

```sh
start_date=$(LC_ALL=C date -d "@$run_started" +%x)
start_time=$(date -d "@$run_started" +%H:%M:%S)
sudo env LC_ALL=C ausearch --input-logs -m FANOTIFY,AVC,USER_AVC -ts "$start_date" "$start_time" -i </dev/null
```

On the OL9 lab this means MM/DD/YY. A four-digit year, or date and time in
one argument, is rejected; this was checked read-only before a new run.
The whole audit excerpt goes into EVIDENCE.md, including denials that did not stop a
product step. No matches is valid; an unavailable audit gives NOT CLEAN.
The original failure is kept even if the audit collection fails. Old runs and
separate diagnosis logs are never changed.

`09-launch-audit-crash` and `09-launch-audit-hang` collect launcher evidence and
check the audit immediately after their respective tests, before marker checks
and reboot. Any denial stops the run at that point. This preserves evidence
that would otherwise be lost on a VM with a volatile journal, as in run-18.
The final audit also collects these read-only diagnostics after an earlier failure.
No journald configuration, labels, security rules or service state are changed.

Launcher diagnostics read the service user's journal since run start and the
transient healthcheck services' selected state properties: Result, ExecMainPID,
ExecMainCode, ExecMainStatus and related state. ExecStart is printed only when
it is the expected `/usr/bin/podman healthcheck run <container-ID>` command;
other arguments are withheld. Journal output is projected to recognized systemd
execution failures and safe PID, time and unit identifiers. Arbitrary messages,
environments and raw inspect data are never logged. A command or parsing error
fails the diagnostic check, while the final audit is still collected.
An audit record with `exe=systemd`, `comm=(podman)` and no PATH does not by itself
identify the target executable or prove a crun failure.

Historical transient units may have been removed by Podman cleanup. A
`LoadState=not-found` response without ExecStart is recorded as unavailable
execution evidence; systemd's default success/zero fields are not logged as
proof of a successful launch. Loaded units still require every selected property.
Other missing fields or malformed output fail the diagnostic check.

## Persistent state and upgrade

The first installation writes config, generated-certificates and PKI directly into
`/var/lib/myproduct`, outside the releases. Step 07 keeps the CA certificate's
SHA256 fingerprint (DER) and the file hashes for config, certificates, passwords and CA
only in memory for comparison. The evidence shows file names and “same/changed”,
without hash values or file content.

After the life cycle and reboot, step 10 first builds a new help image/content
release in a temporary clone. Only its help bundle is built/transferred. Core and
app processes, versions, protected files, network and other bundles’ trust must
remain unchanged. Verified HTTPS content, e2e and markers gate retirement of the
old help release/trust.

The app1-only regression then increments VERSION in VM-1's working copy and
retains CORE_VERSION. Three scoped bundles are rebuilt, but only app1 is
transferred; app2/help process identity, versions and trust must remain unchanged.
A final temporary clone increments CORE_VERSION and builds/transfers an app1
bundle. Core must change version and restart, while app2/help remain untouched.
The prior trusted app1 release must refuse its older core before image operations,
with all managed files and services preserved. Both apps’ e2e and markers run
after upgrade and after refusal. No configuration initialization or credential
generation occurs during any upgrade. Step 11 collects audit and cleans up
transferred secrets. A failed step stops all later operations.

Checks A–E run again after reboot and upgrade. The hash comparison
covers each component config, generated-certificates and files, plus shared PKI/private, routes and clients. Both the e2e and
marker checks use the original passwords.

### Machine-readable command output

The harness captures stdout and stderr separately. Only stdout is used as JSON,
a runtime path, a boot ID or in the VM checks' string comparisons. Stderr
is logged under its own label, including the OpenSSH warning about the missing
post-quantum key exchange; the warning is named in the report. A non-zero exit
stops the step even if stdout contains valid data. Empty or invalid
machine-readable output also stops it. Empty resource lists and restorecon output
are expected results in the checks that explicitly require them.

The audit has one documented exception: `ausearch` returns 1, empty stdout and
`<no matches>` on stderr when no events exist. Other audit errors stop the step.
SSH polling after rollback/reboot and the explicit isolation probes accept
expected failing statuses. The pull probe inspects only its own stderr for a specific
network error; stdout and stderr are never merged into a machine-readable answer.

The full persistent-state comparison keeps hashes only in controller memory.
Focused lifecycle observations also use private mode-0600 baseline files on the
target, alongside the existing private process/trust snapshots. Logs, report and
evidence contain only file names and
“same/changed” from the comparison. The command reads the files for hashing and
never writes file content. The overview below describes where
command output is parsed; it is documentation, not automatic test evidence.

The pull probe keeps stdout and labels its own stderr with `pull-probe:`.
Exit 124 is accepted as a timeout. Exit 125 requires a specific network error on stderr
(lookup, dial tcp, i/o timeout, connection refused, network is unreachable
or no such host); permission and storage errors give FAIL. A successful pull and
other statuses stop the step. SSH warnings are not relabeled.

After reboot, `09-wait-boot-service` waits up to 240 seconds per installed component for automatic
start. `failed` stops at once; the step never starts or restarts
the service. The final audit uses check mode after a complete run, so that
denials during the last e2e steps also give NOT CLEAN. After an earlier
failure the events are still collected as evidence.

Non-empty stderr from restorecon gives FAIL also with exit 0. The rule for
`CUSTOM_WRITABLE_LAYER` accepts only UpperDir layers from inspect of existing
containers; an image layer with the same label is not accepted.

### Overview of command output parsing

- `acceptance.py`: `persistent_state` reads JSON; `credentials` validates the runtime path;
  `boot_id`, `wait_ssh` and `reboot` validate the boot ID.
- `09-crash` parses inspect JSON into five validated state fields and logs only
  those. The start time is handled as one JSON string, also when it contains spaces.
  `wait_backend` checks the curl exit and the HTTP status from the proxy.
- `remote.sh`: `profile`/`facts` compare getenforce and systemctl; `clean`,
  `check` and `stop` check Podman lists and find output.
- `clone`, `bundle` and `upgrade-bundle` check Git status/diff; the release steps
  read VERSION and `upgrade` checks the trust database.
- `healthy` reads Podman JSON; `check` checks the generator and the filtered journal,
  user ID and install time; `wait-boot-service` reads the systemd state.
- LABELS reads UpperDir from inspect and restorecon lines; `audit_events` reads
  the ausearch result with separate streams.
- Snapshot preparation compares getenforce/systemctl. Proxmox data is HTTP JSON;
  the marker check reads local JSON files and HTTP responses.
- Git revision/status, VERSION and record.jsonl on the controller are local data.

Every recorded stderr line that starts with `WARNING`, `** WARNING` or
`Warning:` is named as a “stderr warning” in the report. The source can be the SSH client
or the remote command; it is not inferred from the text. Known secrets are masked.

Trust updates are checked with a bounded, read-only wait: `--update`
notifies the daemon without waiting for the database to finish. Before installation the
new path is required, and after an upgrade the old path must also be gone.
Database content and hash values are not written to the log.

## Container health and hang test

`healthy()` reads the expected `<pod>-<container>` names from the installed YAML,
rejects missing, extra or duplicate app containers and requires `running`
and `State.Health.Status=healthy`. Infra/service containers and manifest-defined
init containers are excluded. The health check waits up to 150 seconds;
command/parse errors and unhealthy stop at once. `initialDelaySeconds: 90`
covers startup. The status is starting for up to 90 seconds after each start,
and healthy only once the next check succeeds.

`09-hang` follows `09-crash` and the marker check: inspect records PID, start time,
restart count and health. Every host PID from `podman top ... hpid` gets SIGSTOP,
without pause/stop/kill through Podman. Within 300 seconds it requires an observed unhealthy,
exactly one restart with a new PID/start time, StoppedByUser=false and finally healthy.
Then all containers, the HTTPS backend and `09-markers-hang` are checked.
No SIGCONT or repair is used on failure. The same health requirement applies after
reboot and upgrade, and the final audit must still be free of denials.

The hang-test limit is 300 seconds: 3 × (30 s interval + 5 s timeout) + 10 s stop + 90 s start period + 30 s
for the first healthy check is about 235 s; 300 s leaves a scheduling margin.
The temporary stop flag on the original non-running unhealthy process is allowed;
`StoppedByUser` must be false after restart.

The English baseline is supplemented with the previously verified run-16 stop-flag
transition handling; `StoppedByUser` must be false on the restarted process.

The demo generates one additional persistent API-secret file through
GENERATED_SECRETS. Step 07 checks its 0600 mode, its private parent directory,
and delivery through identity envFrom by checking length only. The persistent
file comparison after upgrade includes this file without logging hashes or values.

Generated API-secret delivery compares the source file's bytes with the container
environment in memory; another 32-character value fails. Neither values nor
hashes are logged. Crash and hang checks explicitly project `StoppedByUser`
through a Podman template, because native inspect JSON omits false values.
Missing or invalid projected fields fail rather than defaulting to false.
Smoke-test failure messages withhold response URLs and bodies, including OIDC
callback code/state and form/session tokens. The generated-secrets example also
checks private file modes and reuse after a second prepare/play.

## Component acceptance

The 0.2 source and bundles use core/app1/app2/help with independent units,
configs and databases. The component flow checks both installation orders,
shared sign-in, scoped data/markers, app1-only upgrade and app1 uninstall while
app2/help remain available. Each bundle has its own deploy.py trust file; shared
core is reused on an equal CORE_VERSION. Run-23 proves the previous monolithic
layout only. Component runtime results are recorded in new runs, never inferred
from it. See the root README for fresh installation and retained-data uninstall.

Upgrade-build regressions execute the named remote action with only scoped
app1/app2/help artifacts. The app1 checksum must pass before its image list is
read; a damaged archive stops the action. The monolithic filename is not used.


## Help-only upgrade regression

```sh
python3 acceptance/acceptance.py --run CONFIG-HELP-UNIQUE --help-only run
```

This uses the same two configured disposable snapshots and authorization as a
full run. It installs app1/core then help and verifies health. It builds a newer
help release with a new image tag and `help-release-<version>` content marker,
packages and transfers only that help bundle, then installs on the existing host.
HTTPS must serve the marker. Core/app1 PID, start time and restart count must
remain identical, as must versions, config, credentials, imports, installed YAML,
network ID and other bundles’ trust. App1 e2e and persistent task markers must
pass. Only then does it retire old help trust and delete the old help release.
An unchanged route permits no core restart. Focused product tests separately
require exactly one core restart for a changed route, without a core version
upgrade or app1 restart.

Both full installation orders remain covered and include this help upgrade before
the existing app1-only upgrade and sibling checks. Dev config uses
`config/dev.yaml`; production setup calls the real `init-config` command, edits
core before initializing dependents and retains configs during upgrades.
Harness tests stub guest calls and verify sequencing and failure gates; only a
completed target-machine run proves offline install, TLS, health and trust behavior.


The full flows also build a newer `CORE_VERSION` in an app1 bundle, require a
changed core PID/start time and updated core marker, retain app2/help observations
and private state, and rerun both apps’ e2e and task markers. Reinstalling the prior
trusted app1 release must refuse its older core before image commands or any
persistent mutation, followed by successful e2e. Old own trust is retired only
after those checks. Product tests additionally exercise both app orders with
newer/older core and exact expected service restarts.

Current config/lifecycle results and their exact verification limits are recorded
in [CONFIG-VERIFICATION.md](CONFIG-VERIFICATION.md).


## PostgreSQL runtime verification

Full runs execute `database-runtime` after images are built and before dev startup.
It creates and removes only UUID-scoped disposable resources on the dev VM. Kube
Secrets initialize PostgreSQL and feed the .NET Identity verifier; the verifier
builds and uses `ConnectionStrings__Default` at runtime with Npgsql. Python tests
its file-secret/keyword-parameter interface. Non-standard DB identities and port,
quotes, dollar signs, semicolons, spaces, equals, Unicode and legacy hexadecimal
credentials with trailing LF are checked by real connections; wrong credentials must fail authentication rather
than DNS/network setup. Missing/invalid parameter and empty/invalid password diagnostics must not reveal
credentials. The lifecycle guard is also checked against an actually initialized
disposable volume. Existing fixture password bytes survive GENERATED_SECRETS,
and negative client input is a separate temporary copy.

`database-auth` runs on the offline prod VM after initial installation, after
reboot and after upgrades. Identity must connect through its environment interface.
For both Todo directions, the correct local password must connect before the same
connection with a sibling's secret is required to fail password authentication. Npgsql checks SQLSTATE 28P01; Python
checks either that code or libpq’s exact PostgreSQL FATAL password-authentication
reply (handshake errors may have no SQLSTATE). Neither private diagnostic is
dumped. This tests
credential separation, **not network isolation** between applications. No persistent
password is modified by negative checks. Installed database/client logs are
checked privately for password or complete connection-string disclosure. Inputs remain in memory/stdin, never
argv, full inspect/environment dumps or report output. Existing CRUD/e2e/persistent
hash and volume checks remain in the full run. Failed scenarios stop before later
checks; the original audit and cleanup rules are unchanged.

See the root README for manual DB config additions before upgrading existing
0.2.0 installs. Passwords and database volumes must be restored together. Rotating
a file alone does not change a PostgreSQL role password; rotation is out of scope.

Actual database results and limitations: [DATABASE-VERIFICATION.md](DATABASE-VERIFICATION.md).


## Focused historical 0.2.0 upgrade

```sh
python3 acceptance/acceptance.py --run upgrade-020-20261015 --upgrade-020 run
```

This resets the same two configured disposable lab VMs. It builds genuine old
images/archives from pinned commit `86e8e27`, installs old app1/core and app2,
creates authenticated user markers, then upgrades core/app1 followed by app2 with
only the documented manual config additions. It reuses existing logs, readiness,
transfer, credential, audit and cleanup mechanisms. It does not rerun the full
reboot/crash/hang matrix. Use a new run ID every time.

See [test baseline and run details](TEST-BASELINE.md) for exact checks, revisions,
local results and remaining verification. The local harness now has 148 tests;
passing them is not evidence of a real historical upgrade. That scenario has not
yet been run on the lab VMs.
