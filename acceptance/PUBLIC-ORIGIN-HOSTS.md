# Public origin and deterministic localhost entries (backlog 76)

Status (2026-10-30): the previous `--no-hosts` implementation passed its
functional loopback checks and all six matrix scenarios (**472/472**), but
three PROD application containers could not resolve localhost. The replacement
below has local regression coverage and **requires a fresh lab test**. Earlier
results remain unchanged below and do not verify this new mechanism.

## Current change

- `quadlet/containers-hosts.conf` sets `[containers] base_hosts_file = "none"`
  and `no_hosts = false`: ask Podman to generate localhost/container entries
  without using the host's file as a base, even if normal config says otherwise.
- `dev/dev.sh` selects that file through `CONTAINERS_CONF_OVERRIDE` only for
  `podman kube play`. It no longer passes `--no-hosts`.
- Quadlet's `[Service] Environment=` selects the copy in the current component's
  immutable release. The internal `@@PODMAN_HOSTS_CONFIG@@` token supplies its
  absolute, systemd-escaped path. Missing/symlinked policy files are refused
  when templates are checked, before generation or host commands.
- Bundles already copy/checksum the complete `quadlet/` directory. No runtime
  dependency, shared mutable hosts config, or normal user/system Podman config
  write is introduced. Component versions advance so immutable bundles and
  `newer-only` installs receive the new units; images are unchanged.
- `spec.hostAliases` remains refused to protect public-origin network DNS,
  rather than because of the old flag conflict. Certificate-name checks are
  unchanged. [Configuration contract](../docs/COMPONENTS.md#reaching-the-public-origin-from-a-container).

Podman's [configuration documentation](https://github.com/containers/common/blob/main/docs/containers.conf.5.md#environment-variables)
explains the last-loaded override. This is design support, not lab evidence
for the Podman/Quadlet combination used here.

## Local regression scope

`test_public_origin_hosts.py` executes the actual dev script with a recorded
Podman stub, checking command-scoped override selection and retention of the
caller's config. It builds/installs a relocated external-image bundle after
removing the source, checks the bundled/checksummed policy and installed
Environment path, refuses missing/symlinked policy before effects, and tests
literal path escaping. The existing hostAliases validation/bundle guard still
refuses values before writes. `test_quadlet_templates.py` covers the relocated
unit lifecycle for both upgrade policies. These tests do not simulate Podman's
hosts-file generation; the real checks below are still required.

## Current short lab recipe: localhost correction

Use a clean commit containing this replacement, and record `git rev-parse
HEAD`. **Do not reuse the old DEV/PROD installation for the new code.** The
product owner requested the localhost and host-loopback checks, preferably
with one normal fixed-matrix run; the earlier six-scenario matrix remains
historical evidence for `--no-hosts`.

Use the controller's private `lab.env` for `SSH_USER`, DEV/PROD addresses,
`PROD_HOST` and `HTTPS_PORT`; never print its contents. Reset only its configured
disposable VMs. Record command exits and safe output. Stop at the first failed
functional check, always completing hosts restoration. Do not repair code or
config during verification. No secret values, private files, complete
connection strings, redirect query parameters or unfiltered journals belong
in the result. `NO-SHELL` from infra/service containers is an observation;
`NO-LOCALHOST` from an application container is a failure of this correction.

### 1. Fresh focused setup (controller)

This builds the bundles and installs platform, Identity and app3 with the new
policy, providing the DEV checkout and smoke environment for the next checks:

```sh
git rev-parse HEAD
test -z "$(git status --porcelain)"
run=hosts76-localhost-whoami-$(git rev-parse --short HEAD)
python3 acceptance/acceptance.py --run "$run" --whoami run
```

Require CLEAN PASS. Record the exact commit and step counts. This exercises
ordinary sign-in but does not set the host loopback entry.

### 2. DEV localhost and host-loopback check (DEV as SSH_USER)

Replace the run placeholder below with step 1's ID. The subshell always stops
dev and removes its temporary hosts entry, including after a failed check.

```sh
(
  set -euo pipefail
  run=<run-ID-from-step-1>
  cd ~/podman-offline-acceptance/$run/src
  host=myproduct-proxy
  restore() {
    result=$?
    trap - EXIT
    ./dev/dev.sh down || result=1
    sudo sed -i "/^127\.0\.0\.1 $host\$/d" /etc/hosts || result=1
    if grep -q "^127\.0\.0\.1 $host\$" /etc/hosts; then
      echo 'FAIL: temporary host entry remains'; result=1
    else
      echo 'restored: no host entry'
    fi
    exit "$result"
  }
  trap restore EXIT
  podman --version; getenforce
  sudo sh -c "printf '127.0.0.1 %s\n' '$host' >> /etc/hosts"
  getent hosts "$host"                      # expect 127.0.0.1
  ./dev/dev.sh up

  for c in identity-postgres-db identity-server-app app3-whoami-backend; do
    printf '%s ' "$c"
    podman exec "$c" sh -c 'test -f /etc/hosts && grep -E "^(127\.0\.0\.1|::1)[[:space:]]+localhost([[:space:]]|$)" /etc/hosts && getent hosts localhost'
  done
  count=$(podman exec app3-whoami-backend sh -c 'grep -F -c "$1" /etc/hosts || true' sh "$host")
  printf 'backend public-name hosts entries: %s\n' "$count"
  test "$count" = 0
  resolved=$(podman exec app3-whoami-backend getent hosts "$host")
  proxy=$(podman inspect platform-proxy-nginx --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
  printf 'backend: %s\nproxy: %s\n' "$resolved" "$proxy"
  test -n "$proxy"
  test "${resolved%%[[:space:]]*}" = "$proxy"
  SMOKE_RESTART_COMMAND='podman pod restart app3-whoami' .venv-smoke/bin/python dev/whoami-smoke-test.py
)
```

Require localhost entries in a real `/etc/hosts`, successful localhost lookup,
zero public-name entries, proxy address equality and all smoke PASS lines.
Record any other application/infra observations separately if collected;
infra images without a shell/getent cannot supply resolution evidence.

### 3. Installed PROD localhost and host-loopback check (PROD as SSH_USER)

Fill in the two public values from `lab.env`. These are lab helpers, not a
new customer operator procedure. Only the declared public override path and
filtered unit facts are printed; do not dump the full service environment.

```sh
(
  set -euo pipefail
  host=<PROD_HOST>; port=<HTTPS_PORT>
  ops() { sudo -n -H -u myproduct-ops env XDG_RUNTIME_DIR="/run/user/$(id -u myproduct-ops)" \
          XDG_CONFIG_HOME=/var/lib/myproduct/config XDG_DATA_HOME=/var/lib/myproduct/storage \
          bash -c 'cd "$HOME" || exit; exec "$@"' bash "$@"; }
  units() { ops systemctl --user "$@"; }
  restore() {
    result=$?
    trap - EXIT
    sudo sed -i "/^127\.0\.0\.1 $host\$/d" /etc/hosts || result=1
    units restart myproduct-platform.service myproduct-identity.service myproduct-app3.service || result=1
    if grep -q "^127\.0\.0\.1 $host\$" /etc/hosts; then
      echo 'FAIL: temporary host entry remains'; result=1
    else
      echo 'restored: no host entry'
    fi
    exit "$result"
  }
  podman --version; getenforce
  for u in platform identity app3; do
    start=$(units show --property=ExecStart --value myproduct-$u.service)
    if printf '%s\n' "$start" | grep -q -- '--no-hosts'; then
      echo 'FAIL: obsolete --no-hosts option'; exit 1
    fi
    env_text=$(units show --property=Environment --value myproduct-$u.service)
    printf '%s ' "$u"
    printf '%s\n' "$env_text" | grep -o 'CONTAINERS_CONF_OVERRIDE=[^ ]*'
  done
  trap restore EXIT
  sudo sh -c "printf '127.0.0.1 %s\n' '$host' >> /etc/hosts"
  units restart myproduct-platform.service myproduct-identity.service myproduct-app3.service
  sleep 20
  units is-active myproduct-platform.service myproduct-identity.service myproduct-app3.service

  for c in identity-postgres-db identity-server-app app3-whoami-backend; do
    printf '%s ' "$c"
    ops podman exec "$c" sh -c 'test -f /etc/hosts && grep -E "^(127\.0\.0\.1|::1)[[:space:]]+localhost([[:space:]]|$)" /etc/hosts && getent hosts localhost'
  done
  count=$(ops podman exec app3-whoami-backend sh -c 'grep -F -c "$1" /etc/hosts || true' sh "$host")
  printf 'backend public-name hosts entries: %s\n' "$count"
  test "$count" = 0
  resolved=$(ops podman exec app3-whoami-backend getent hosts "$host")
  proxy=$(ops podman inspect platform-proxy-nginx --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
  printf 'backend: %s\nproxy: %s\n' "$resolved" "$proxy"
  test -n "$proxy"
  test "${resolved%%[[:space:]]*}" = "$proxy"

  login=$(ops curl --noproxy '*' --cacert /var/lib/myproduct/state/PKI/private/ca.crt \
    --resolve "$host:$port:<PROD_IP>" --silent --show-error --max-time 30 \
    --output /dev/null --write-out '%{http_code} %{redirect_url}\n' \
    "https://$host:$port/app3/auth/login")
  status=${login%% *}; destination=${login#* }; destination=${destination%%\?*}
  printf '%s %s [query withheld]\n' "$status" "$destination"
  test "$status" = 302
  test "$destination" = "https://$host:$port/identity/connect/authorize"
  unset login
)
```

Require a release-local override path for each unit, no `--no-hosts` start
flag, all services active, all three former failures resolving localhost from
generated files, zero inherited public-name entries, matching proxy address,
302 to the public authorize endpoint and successful restoration. In particular,
**do not accept another NO-LOCALHOST as an informational pass**.

### 4. Recommended normal regression (controller)

After manual restoration, one normal scenario checks the changed unit path and
offline bundle through lifecycle/upgrade/reboot. It resets the disposable VMs:

```sh
rev=$(git rev-parse --short HEAD)
python3 acceptance/acceptance.py --run "hosts76-localhost-normal-$rev" run
```

Require CLEAN PASS. Do not call the earlier 472/472 run verification of this
new configuration. Record unit/product tests, isolated harness tests and real
manual/harness-driven runtime results separately, with exact commits, modes,
OS/Podman versions, localhost/hosts-file/DNS outputs, sign-in and restoration.
Keep earlier result sections unchanged and record failures before repairs.

## Historical evidence: previous --no-hosts implementation

The following sections report the original implementation, including its
recipe failures and the PROD localhost findings. They remain historical
results; no pass below closes the retest for the replacement above.

## Lab verification (2026-10-29): stopped in part 2

Tested commit: `5f4b499f7cc0c9123fdc6f4078031d5cfa24d371`, from a clean
`main` checkout. The controller's private `lab.env` was present; SSH as its
`SSH_USER` (`gunstein`) and `sudo -n true` succeeded on both configured lab VMs
before execution. Only the configured disposable VMs were reset by part 1.

**Overall: incomplete; stopped at the first unexpected result, part 2,
step 3 (the backend `/etc/hosts` grep).** No command was retried, no recipe,
code or configuration was repaired, and parts 3 and 4 were not started.
The required DEV restoration completed successfully.

### Environment recorded by this run

| Host | VM | OS | Podman | systemd | SELinux | fapolicyd |
| --- | --- | --- | --- | --- | --- | --- |
| DEV | 107 / 192.168.0.102 | Oracle Linux 9.8 | 5.8.2 | 252 | Enforcing | inactive / disabled |
| PROD | 108 / 192.168.0.108 | Oracle Linux 9.8 | 5.8.2 | 252 | Enforcing | active / enabled |

Lab values: `PROD_HOST=myproduct-proxy`, `HTTPS_PORT=8443`. No credentials,
private-file contents, authentication redirect parameters or raw journals are
included in this report.

### Harness runs: parts 1 and 4

| Part | Run ID | Result | Passed / recorded steps |
| --- | --- | --- | ---: |
| 1 | `hosts76-whoami-5f4b499` | **CLEAN PASS** | **46/46** |
| 4 | Fixed matrix (normal, app2-first, Identity-only, help-only, platform/help, renamed) | **NOT RUN**, due to the part 2 stop | 0 recorded; no runs created |

Part 1 ran the specified command:

```sh
python3 acceptance/acceptance.py --run hosts76-whoami-5f4b499 --whoami run
```

The run started at 2026-10-29 16:53 UTC. Image builds, DEV startup and whoami
smoke, signed bundle installation on PROD, subPath checks, PROD whoami smoke,
log safety, session persistence over service restart and reboot, trust-chain
negative control, internal variant, restoration, final checks,
`11-prod-audit` and cleanup all passed. This run did not set a host loopback
line; it does not establish the manual loopback results requested below.

Original harness artifacts remain at
`~/podman-offline-acceptance-runs/hosts76-whoami-5f4b499/REPORT.md`,
`record.jsonl` and `EVIDENCE.md` on the controller. Older lab results are not
used as evidence here. No separate product/unit suite or isolated
acceptance-harness unittest suite was run for this verification.

### Manual checks: part 2 (DEV)

The source checkout was the one left by part 1:
`~/podman-offline-acceptance/hosts76-whoami-5f4b499/src`.
The recipe's `host=myproduct-proxy` was used unchanged.

| Recipe step | Result | Recorded output / observation |
| --- | --- | --- |
| 1. Add host loopback line and resolve on DEV | PASS | `getent hosts "$host"`: `127.0.0.1 myproduct-proxy` (exit 0). |
| 2. Negative control without `--no-hosts` | PASS | `podman run ... --entrypoint getent "$proxy_image" hosts "$host"`: `127.0.0.1 myproduct-proxy myproduct-proxy` (exit 0); image `docker.io/library/nginx:1.28-alpine`. |
| 3. Normal DEV startup | Startup passed | `./dev/dev.sh up` exited 0 with the host line present. |
| 3. Backend hosts-file check | **STOP: expected count missing** | Empty stdout; stderr `grep: /etc/hosts: No such file or directory`; enclosing shell exit 0 because of the recipe's `|| true`. Expected stdout was `0`. |
| 3. Backend DNS/proxy address comparison | NOT RUN | Stopped before the two address commands; no proxy address comparison recorded. |
| 3. All-container localhost loop | NOT RUN | Neither a localhost pass nor a `NO-LOCALHOST` observation is available. |
| 4. Sign-in/restart smoke with the host loopback line | NOT RUN | No manual-loopback sign-in result; part 1's smoke is separate evidence. |
| 5. Raw Podman hostAliases test | NOT RUN | No exit status or Podman message exists for this test; no hostAliases manifest/pod was created. |
| 6. Restore | PASS | DEV down, loopback-line removal and confirmation all exited 0; details below. |

Of the five numbered verification steps (1–5), steps 1 and 2 fully passed;
step 3 stopped partway through, and steps 4–5 were not run. Restore step 6
is recorded separately and is not counted as a passed verification step.

The first unexpected command, exactly as executed with the recipe's host
variable, was:

```sh
podman exec app3-whoami-backend sh -c "grep -c '$host' /etc/hosts || true"
```

Bounded output:

```text
stdout: <empty>
stderr: grep: /etc/hosts: No such file or directory
enclosing command exit: 0
expected stdout: 0
```

The backend had no `/etc/hosts` file, rather than an existing file with zero
matching lines. Therefore the shell exit alone was not accepted as a pass.
This establishes a mismatch with the recipe's expected observation; it does
not establish whether backend DNS or localhost resolution would pass. No
alternative command or workaround was attempted.

All shipped restoration commands were executed after the stop:

```sh
./dev/dev.sh down
sudo sed -i "/^127\.0\.0\.1 $host\$/d" /etc/hosts
getent hosts "$host" || echo 'restored: no host entry'
```

Each command exited 0. Confirmation printed:

```text
restored: no host entry
```

### Manual checks: part 3 (PROD) and remaining limits

Part 3 was **NOT RUN**. PROD's `/etc/hosts` was not modified manually, so no
PROD hosts-file restoration was needed. No manual unit grep counts, backend
addresses, localhost results or `302` sign-in-start result were collected.
The raw hostAliases behavior, manual loopback sign-in on either host, and the
six fixed matrix scenarios remain unverified at this commit. No
`NO-LOCALHOST` was observed because that loop was not reached; this is not a
localhost pass.

Only this dated evidence section was added. `BACKLOG.md`,
`docs/REVIEW_GUIDE.md`, the recipe above and implementation code are unchanged.
The result awaits product-owner review; no verification status is promoted.

## Part 2, Revision 2 verification (2026-10-29)

**Part 2 PASS**, including restoration. Only part 2 of Revision 2 was run.
The controller used clean `main` at
`d2ca3dc52e865607dccb186d969fb2ac92bb39e2`. The required command

```sh
git diff --stat 5f4b499 HEAD -- . ':(exclude)*.md'
```

produced no output before execution. The existing DEV source checkout at
`~/podman-offline-acceptance/hosts76-whoami-5f4b499/src` was confirmed present;
no VM was reset and part 1 was not rerun. Part 1 is explicitly reused from
`hosts76-whoami-5f4b499` (**CLEAN PASS, 46/46**) because non-Markdown code is
unchanged from `5f4b499`. This manual run is new real-DEV evidence for the
revised recipe, not a new harness run or an isolated unit/harness-test result.

DEV: **Oracle Linux 9.8, Podman 5.8.2, SELinux Enforcing**. Commands ran as
`gunstein` on configured DEV VM 107 (`192.168.0.102`), using sudo only where
the recipe requires it. The public name was `myproduct-proxy`.

### Result by recipe step

| Step | Result | Observation |
| --- | --- | --- |
| 1. Host loopback mapping | PASS | Host lookup returned `127.0.0.1 myproduct-proxy`. |
| 2. Negative control | PASS | A container without `--no-hosts` returned `127.0.0.1 myproduct-proxy myproduct-proxy`. Image: `docker.io/library/nginx:1.28-alpine`. |
| 2b. Hosts options and alternative | OBSERVED | All three enclosing commands exited 0; their complete stdout is reproduced unchanged below. |
| 3. Normal DEV startup / public-name resolution | PASS | `./dev/dev.sh up` exited 0. Backend check printed `no /etc/hosts`; backend DNS returned `10.89.0.24 myproduct-proxy.dns.podman`, matching proxy inspect address `10.89.0.24`. |
| 3. Localhost loop | OBSERVED | All 12 application containers resolved `localhost` to `::1`; all 9 infra containers reported `hosts-file=?` and `NO-SHELL`. No `NO-LOCALHOST` or `NO-GETENT` result. Full per-container output below. |
| 4. Sign-in and app restart | PASS | Smoke exited 0 with all six PASS lines, including Duende sign-in, introspection and the same session after app restart. |
| 5. hostAliases conflict | OBSERVED | Raw `podman kube play --no-hosts` exited **125** with `Error: HostAliases in yaml file will not work with --no-hosts`. The enclosing `...; echo "exit=$?"` command exited 0. Manifest cleanup completed. |
| 6. Restore | PASS | DEV down, loopback-line removal and confirmation all exited 0. Confirmation: `restored: no host entry`. |

No operational step failed and none was retried. Step 2b, localhost results
and the raw hostAliases conflict were observations as specified, rather than
stop conditions. No code, recipe or persistent product configuration was
changed to obtain these results.

### Complete step 2b output (unchanged)

The recipe filters the two help outputs; the following are the complete
outputs of those exact commands, including original spacing. No stderr was
emitted by these three Podman observation commands.

`podman kube play --help | grep -iE -- '--(no-hosts|hosts-file)' || echo 'kube play: no hosts options listed'`:

```text
      --no-hosts                      Do not create /etc/hosts within the pod's containers, instead use the version from the image
```

`podman run --help | grep -iE -- '--hosts-file' || echo 'run: no --hosts-file'`:

```text
      --hosts-file string                        Base file to create the /etc/hosts file inside the container, or one of the special values. ("image"|"none")
```

`podman run --rm --pull=never --network myproduct --hosts-file=none --entrypoint cat "$proxy_image" /etc/hosts` (with the recipe's fallback):

```text
127.0.0.1	localhost
::1	localhost
169.254.1.2	host.containers.internal host.docker.internal
10.89.0.23	869e178e7961 practical_raman
```

The `kube play` help lists `--no-hosts` and does **not** list
`--hosts-file`; `run` help lists `--hosts-file`. No unlisted kube-play option
was attempted. In the separate `run --hosts-file=none` observation, the file
contains `127.0.0.1 localhost` and `::1 localhost`, plus generated internal and
container entries. It does not contain `127.0.0.1 myproduct-proxy` or any other
`myproduct-proxy` entry. This is decision input for the product owner; the
implementation remains `--no-hosts`.

### Localhost and hosts-file observations for every container

The following is the complete output of the recipe's observation loop. A
`?`/`NO-SHELL` on an infra container means the shell-based file/resolution
probe could not run; it is not proof that the file is absent or localhost
resolution is broken there. Containers reporting `hosts-file=no` still
resolved `localhost` in this run.

```text
275d7c7d2888-infra hosts-file=? localhost=NO-SHELL
platform-proxy-nginx hosts-file=yes localhost=::1               localhost  localhost
cfa2804e89ea-infra hosts-file=? localhost=NO-SHELL
identity-postgres-db hosts-file=no localhost=::1             localhost
e481adffc279-infra hosts-file=? localhost=NO-SHELL
identity-server-app hosts-file=no localhost=::1             localhost
10aa54d0289e-infra hosts-file=? localhost=NO-SHELL
app1-postgres-db hosts-file=no localhost=::1             localhost
47066fa3bf5d-infra hosts-file=? localhost=NO-SHELL
app1-todo-backend hosts-file=no localhost=::1             localhost
app1-todo-frontend hosts-file=yes localhost=::1               localhost  localhost
52fa6c84797b-infra hosts-file=? localhost=NO-SHELL
app2-postgres-db hosts-file=no localhost=::1             localhost
63cf83e8ad21-infra hosts-file=? localhost=NO-SHELL
app2-todo-backend hosts-file=no localhost=::1             localhost
app2-todo-frontend hosts-file=yes localhost=::1               localhost  localhost
bd1867ce3796-infra hosts-file=? localhost=NO-SHELL
app3-whoami-backend hosts-file=no localhost=::1             localhost
app3-whoami-frontend hosts-file=yes localhost=::1               localhost  localhost
33a863fc00ee-infra hosts-file=? localhost=NO-SHELL
help-web-web hosts-file=yes localhost=::1               localhost  localhost
```

### Sign-in/restart smoke and hostAliases

With the host loopback line still present, the exact recipe smoke command
exited 0:

```text
PASS: HTTPS, routes, compiled frontend, anonymous 401, https callback URI
PASS: alice signed in through Duende (PKCE, private_key_jwt); claims API
PASS: Identity accepts app3's registered API secret (introspection)
PASS: the session cookie still works after restarting the app
PASS: CSRF and origin checks; local logout
PASS: an OIDC error response is refused without echoing its text
```

For the raw hostAliases probe, Podman stderr was:

```text
Error: HostAliases in yaml file will not work with --no-hosts
```

The recipe's exit-status output was:

```text
exit=125
```

The subsequent `podman kube down ...; rm -f /tmp/hostaliases-test.yaml`
cleanup command exited 0.

### Restoration, scope and remaining verification

Step 6 completed all three prescribed commands. Its final output was:

```text
restored: no host entry
```

DEV pods were stopped and the temporary host loopback entry removed. No PROD
commands or changes were performed. **Parts 3 and 4 were intentionally not
run**, as requested: the product owner first decides whether to retain
`--no-hosts` or change mechanism based on these part-2 observations. The
installed-PROD loopback check and fixed matrix therefore remain outstanding.

No separate product/unit tests or acceptance-harness unittests were run in
this round; part 1's existing real-runtime evidence is reused only under the
explicit unchanged-code condition above. This report does not claim runtime
verification of `--hosts-file=none` through kube play or Quadlet, or empirical
understandability/operator-trial verification. Earlier result sections are
unchanged; neither `BACKLOG.md` nor `docs/REVIEW_GUIDE.md` was edited.

## Remaining verification attempt (2026-10-29): stopped in part 3

Controller revision: `00d34e454d234c776e8bdd6c013b82264f2232ed`, a clean
`main` checkout at execution start. Fetch confirmed that this was also the
current remote main. The non-Markdown diff against `5f4b499` was empty.
Part 1 remains the explicit reused run `hosts76-whoami-5f4b499`
(**CLEAN PASS, 46/46**); the Revision 2 part-2 results above are unchanged.
Neither was rerun. This attempt started at part 3 on the existing PROD
installation, after confirming sudo access and that app3's installed marker
still existed. No VM was reset.

**Stopped at the first failure: part 3, step 1.** The recipe's `units cat`
command failed before any unit contents could be checked. No workaround,
alternative inspection command, recipe fix, code change or retry was made.
Part 4 was not started.

PROD (configured VM 108, `192.168.0.108`): **Oracle Linux 9.8, Podman 5.8.2,
SELinux Enforcing**. The SSH account was `gunstein`.

### Manual PROD result

The helper was used exactly as supplied in Revision 2:

```sh
units() { sudo -n systemctl --user -M myproduct-ops@ "$@"; }
```

The failed recipe command was:

```sh
for u in platform identity app3; do printf '%s ' "$u"; units cat myproduct-$u.service | grep -c -- '--no-hosts'; done
```

Complete stdout:

```text
platform 0
identity 0
app3 0
```

Complete application stderr (SSH transport warnings excluded):

```text
Cannot remotely cat units.
Cannot remotely cat units.
Cannot remotely cat units.
```

The enclosing command exited **1**. The expected output was `1` for each
unit. Here `systemctl cat` rejected the remote-machine access form and supplied
no unit text to `grep`; the zero counts therefore **do not establish that
`--no-hosts` is absent**. No generated service command line was obtained.

| Part 3 check | Result |
| --- | --- |
| Step 1: generated-unit `--no-hosts` counts | **FAIL**, inspection command rejected; 0/1 attempted numbered checks passed. |
| Step 2: host loopback mapping and service recreation | NOT RUN. |
| Step 3: backend hosts file, proxy address and localhost observations | NOT RUN. |
| Public-origin sign-in start (`302`) | NOT RUN. |
| Restore | NOT NEEDED: the failure preceded the hosts-file append and service restart. No PROD host entry was added and no services were changed. |

### Harness runs, scope and gaps

No new harness run was created. All six part-4 scenarios (normal, app2-first,
Identity-only, help-only, platform/help and renamed) are **NOT RUN**, with zero
recorded steps in this attempt, because execution stopped at the part-3
failure. No product/unit or isolated acceptance-harness tests were run.

The successful DEV loopback/sign-in and localhost observations from part 2
remain available, but this attempt adds no PROD loopback, localhost, sign-in
or fixed-matrix verification. The full backlog 76 lab scope is still
incomplete. Only this evidence section was appended; the recipe, earlier
results, `BACKLOG.md`, `docs/REVIEW_GUIDE.md` and implementation code were not
changed. The unsupported inspection command is reported for review rather than
silently bypassed.

## Completed PROD check and fixed matrix (recorded 2026-10-30)

The corrected part-3 procedure and all six part-4 scenarios have now been
executed. **Part 3's required functional checks passed, with three
`NO-LOCALHOST` observations retained as findings. Part 4 finished CLEAN PASS
in all six scenarios, 472/472 steps**, including all final audits and cleanup.
This updates the earlier incomplete attempts without changing their reports.
No tests or VM operations were rerun while recording these results.

### Revisions and evidence scope

- The corrected Revision 3 recipe was committed as
  `84eabd639fc6191b06dac60c061ac4d0a8feef86` and used for the new PROD check on
  2026-10-29. Part 1's existing installation was retained for that check.
- The operator then ran all six matrix scenarios on 2026-10-29,
  19:26–21:46 UTC, at **`d5e5d70e24188f8dd4df5676c82d29cebcf1b20b`**,
  after merging the latest remote documentation. Local `REPORT.md` metadata
  and `record.jsonl` files confirm that exact revision and each verdict.
- `git diff --stat 5f4b499 HEAD -- . ':(exclude)*.md'` was empty before the
  PROD continuation; the same code comparison is empty for `d5e5d70`.
  Thus part 1 is explicitly reused from `hosts76-whoami-5f4b499`
  (**CLEAN PASS, 46/46**), and the Revision 2 DEV manual observations above
  remain applicable to this unchanged implementation. They were not rerun or
  relabelled as new results.
- DEV and PROD metadata for every matrix run report **Oracle Linux 9.8,
  Podman 5.8.2, systemd 252 and SELinux Enforcing**. PROD had fapolicyd
  active/enabled; DEV had it inactive/disabled. The manual PROD check also
  reported Podman 5.8.2 and Enforcing.

### Manual real-host verification: part 3

The original failed `systemctl --user -M ... cat` attempt remains recorded
above. Revision 3 executes commands directly as `myproduct-ops` with its XDG
runtime/config/data paths and its own home as the working directory.
It checks the effective `ExecStart` property, rather than counting the whole
unit: full unit text contains both retained `PodmanArgs` and the generated
`ExecStart`. Failed property reads stop before flag counting. These are recipe
corrections; no product code or deployment configuration was changed.

| Check | Result | Output / observation |
| --- | --- | --- |
| Effective `ExecStart` contains `--no-hosts` | PASS | `platform 1`, `identity 1`, `app3 1`; inspection exit 0. |
| Add PROD host loopback line and recreate services | PASS | Append/restart commands exited 0; platform, Identity and app3 each reported `active`. |
| Backend `/etc/hosts` | PASS | `no /etc/hosts`, accepted by Revision 3. |
| Backend public-name lookup | PASS | `10.89.0.12 myproduct-proxy.dns.podman`. |
| Proxy inspect address | PASS | `10.89.0.12`, matching the backend lookup rather than the host's loopback entry. |
| Localhost loop | OBSERVED | Three application containers reported `NO-LOCALHOST`; two resolved to `::1`; seven service/infra containers reported `NO-SHELL`. See complete output below. |
| Public-origin sign-in start | PASS | `302 https://myproduct-proxy:8443/identity/connect/authorize`; redirect query withheld. |
| Restore | PASS | Host-line removal and the prescribed platform/Identity/app3 restart both exited 0. No temporary PROD hosts entry was intentionally retained. |

Complete localhost observation output:

```text
505487900842-service localhost=NO-SHELL
0cc37bc73d5d-infra localhost=NO-SHELL
app3-whoami-backend localhost=NO-LOCALHOST
app3-whoami-frontend localhost=::1               localhost  localhost
cd4cad9917e5-service localhost=NO-SHELL
2f6b7191c337-infra localhost=NO-SHELL
identity-postgres-db localhost=NO-LOCALHOST
e88e0b00f993-infra localhost=NO-SHELL
identity-server-app localhost=NO-LOCALHOST
cc4a03a3ecab-service localhost=NO-SHELL
3b71c950755e-infra localhost=NO-SHELL
platform-proxy-nginx localhost=::1               localhost  localhost
```

The three `NO-LOCALHOST` observations are `app3-whoami-backend`,
`identity-postgres-db` and `identity-server-app`. In contrast, all 12 DEV
application containers resolved localhost in the earlier part-2 check.
That DEV/PROD difference is a real finding, despite successful public-name DNS,
sign-in and the matrix. A `NO-SHELL` result means the probe could not execute;
it does not establish hostname behavior in that container. No workaround,
image/hosts-file adjustment or resolver configuration change was applied.

The login result stored for reporting is:

```text
302 https://myproduct-proxy:8443/identity/connect/authorize [query withheld]
```

### Real harness-driven verification: part 4

| Run ID | Scenario | Result | Passed / total steps |
| --- | --- | --- | ---: |
| `hosts76-normal-d5e5d70` | Normal, app1 first | **CLEAN PASS** | 125/125 |
| `hosts76-app2-d5e5d70` | App2 first | **CLEAN PASS** | 125/125 |
| `hosts76-identity-d5e5d70` | Identity-only baseline/upgrade | **CLEAN PASS** | 66/66 |
| `hosts76-help-d5e5d70` | Help only | **CLEAN PASS** | 60/60 |
| `hosts76-platform-help-d5e5d70` | Platform/help without Identity on PROD | **CLEAN PASS** | 39/39 |
| `hosts76-renamed-d5e5d70` | Renamed product | **CLEAN PASS** | 57/57 |

The normal and app2-first runs exercised stop/start, restart, crash/hang
recovery, reboot/offline operation, independent help/app/platform/Identity
upgrades, downgrade refusal, data/sibling preservation, and scoped uninstall.
The other scenarios covered the pinned historical Identity baseline and
upgrade, isolated help upgrade, platform/help without Identity on PROD, and
the renamed product's registration removal and retained-bundle uninstall.
All six final `11-prod-audit` steps and cleanup steps passed. App3 remains
outside the fixed PROD matrix; the focused/manual checks above supply its
runtime evidence.

### Product/unit tests and acceptance-harness tests

The `03-unit` logs show **590 tests, OK** in each of normal, app2-first,
Identity-only, help-only and platform/help. The renamed scenario has no
separate `03-unit` step. All six image-build steps passed. These results come
from the operator's completed runs, not new test executions while editing this
report.

No isolated acceptance-harness unittest command was run or supplied in this
batch; no new harness-unittest pass is claimed. A CLEAN acceptance scenario
is real runtime evidence and is kept separate from that test category.

### Artifact fingerprints and remaining findings

Original harness files remain under
`~/podman-offline-acceptance-runs/<run-id>/`. The following fingerprints link
this summary to the local records without copying secrets or unfiltered logs.

| Run ID | SHA-256 of record.jsonl | SHA-256 of final audit log |
| --- | --- | --- |
| `hosts76-normal-d5e5d70` | `832f5d36be0743e739ffd1fb8899c25233a644c6e0b75207daa63b6b6ac9bae7` | `f8620c0c03de7922057b2ab341d22b1697f18a3ec8bde3e2a2e632ee858f1314` |
| `hosts76-app2-d5e5d70` | `d25e853c8bfd544bfd48109cd71667b366a30980ecd7879eb1cde8da1f49fb8a` | `9e5c07d8b0b418bef4c003288f947c3a15a0a77c7e31420ff904ffd060138790` |
| `hosts76-identity-d5e5d70` | `0f3d8af1ffe79bfbc9272f7f4b06d5413d982a019cf0b5a13c91b9eac3265fea` | `05735dae9b4b7eea54baafa8a39e5f9e3756d9550a6d19bdca1251af9bc64880` |
| `hosts76-help-d5e5d70` | `8e396c57b058394f8bd3af8c8838d95ffc2b027acea14c3aac798c1424f97def` | `5a68ac10b9755b8a172afdc42962a61165205be9aed1191decaa8b7ddd18f051` |
| `hosts76-platform-help-d5e5d70` | `99a31eb59758762cccf74a0fd1480a80a0e0f2f6c7c33df01861745c655b1d5c` | `06f7cf18a9158d7a25002c66cbcb6009cfd8699988f08aa1333ff332ca853661` |
| `hosts76-renamed-d5e5d70` | `53e34e4ec2239053fefe2cedb68ebc82eff18213e62b3393a4ad270fe3e30736` | `79ba30bbea18b3ceec5ccc642173761949c74433cb7b9ed26de2980d148fad35` |

The required functional PROD loopback checks and all fixed-matrix runs are now
recorded; the former inspection-command blocker is resolved. This does **not**
make the three PROD localhost findings disappear or select a different hosts
mechanism. Part 2 found `--hosts-file` in `podman run` help but not kube-play
help; use of that alternative through kube play/Quadlet is still unverified.
The product owner must assess the localhost findings before treating the
behavior as unconditionally acceptable. An automated loopback acceptance
step is not added by this evidence-only update.

Only this report was changed while recording the results. `BACKLOG.md`,
`docs/REVIEW_GUIDE.md`, earlier result sections and implementation code are
unchanged; no backlog status is promoted. The relevant checked contracts are
host-line isolation, public-origin routing through network DNS, effective
Quadlet start flags, credential-safe output and restoration, plus the
lifecycle/isolation checks actually exercised by the matrix. No implementation
refactor or new understandability assessment is claimed; no unassisted human
operator trial occurred.

## Localhost correction prepared (2026-10-30): new lab test required

The product owner accepted the recorded matrix/functional results and requested
a correction for the three PROD localhost failures. The implementation now
uses the source/release-local `quadlet/containers-hosts.conf` override described
at the top of this report. It removes `--no-hosts`, sets `base_hosts_file =
"none"` and `no_hosts = false`, and leaves the normal user's config files
untouched. The policy is selected only on dev `kube play` and in the installed
service environment; each unit points inside its own immutable release.
This is a code change: **none of the earlier lab passes verify it**.

### Local checks for this correction

- `python3 -B tests/run.py all`: **592 tests, OK**.
- `python3 -B tests/run.py platform --isolate`: **520 tests, OK**, without
  application source or shipped demo declarations.
- `python3 -B -m unittest discover -s acceptance -p 'test_*.py'`:
  **358 tests, OK**. This is harness-unit evidence, not runtime evidence.
- Focused hosts-policy / Quadlet tests: **13 tests, OK**, including actual dev
  shell execution with recorded Podman, a relocated/checksummed bundle,
  untouched caller config, early policy refusal and literal path escaping.
- Scoped Ruff lint/format and ShellCheck (`dev/dev.sh`) passed. Vermin reports
  minimum Python **3.6**. Scoped Pyright reports **0 errors**, with 7 PyYAML
  source-resolution warnings in this tool environment.
- The repository-wide Ruff invocation still reports 12 existing issues in
  unchanged `acceptance/init_secret_test.py`, `acceptance/test_init_secret.py`
  and `tests/platform_tests/test_secret_templates.py`. Its broad format check
  reports one unchanged file, `acceptance/test_acceptance.py`. These baseline
  issues were not repaired as part of the hosts fix; changed Python files and
  the deployment package pass their scoped lint/format checks. The full listed
  ShellCheck set and Python-3.6 Vermin check passed.

The initial sandboxed full-suite attempts could not create the existing GPG
and fake journal Unix sockets; normal local test permissions resolved those
infrastructure failures. The tracked-file renamed generator also requires the
new public policy file in its inventory; after staging that file, the harness
suite passed. The first default multiprocessing Vermin invocation was blocked
by the sandbox's socket restriction; its single-process run passed. No lab VM
or real Podman/systemd verification was performed for this correction.

### Contracts and understandability review

1. The catalog still owns product/component names and versions. The public
   policy lives in `quadlet/`, is copied/checksummed with the existing bundle
   content, and supplies no component-config or credential values.
2. `quadlet_text` resolves only the fixed internal policy path, refuses a
   missing/symlinked file and control characters, and escapes quotes,
   backslashes and systemd percent specifiers. Existing shared template checks
   reach it before generation/host calls; validate reads no secret bytes.
3. Dev scopes the environment assignment to its existing start command. The
   template renderer only computes text; existing lifecycle writers publish
   units. No new mutable shared config, transaction layer or process-global
   production setting was introduced.
4. Image validation, pending/registration publication, unit writes,
   restart/health, acknowledgement and completion order are unchanged. The
   new Environment path is generated alongside the already-validated unit.
5. Existing durable metadata/pending state still controls retry. The inspected
   failure path is a missing policy during template checks: no generated
   credentials, live writes or host calls occur; restoring the bundled public
   file permits a fresh attempt. Relocation before install selects the new
   release path, not a path back into a deleted source checkout.
6. The policy has no demo names. Synthetic external-image/renamed fixtures
   exercise it; the lab checks use the known demo names only to reproduce the
   three observed failures. hostAliases refusal remains the explicit
   public-origin DNS contract and no longer claims an obsolete flag conflict.

Outcome: one internal path token and one small public file carry the policy;
there is no component-object hierarchy or extra mutable configuration model.
All six component patch versions advance so immutable delivery and
`newer-only` updates select new unit files. This review establishes code-flow
clarity, not empirical human understandability.

The shorter recipe above was statically walked through: explicit controller,
DEV/PROD accounts and fresh starting state; runtime helper cwd/XDG; read-only
unit-property checks; secret-safe redirect output; hosts restoration on shell
exit; and failure conditions for the affected localhost probes. This is an AI
procedure assessment only; its new commands were syntax-checked but not run on
the lab hosts. An unassisted human operator trial was not performed, and no
customer-readiness claim is made.

Next: run the fresh focused setup, DEV and PROD localhost/loopback/sign-in
checks with restoration, then preferably one normal matrix scenario. Record
the exact new commit and generated-policy paths/contents. Keep the historical
472/472 result scoped to the old mechanism. Backlog 76 remains open until this
new behavior is verified on real Podman/Quadlet.
