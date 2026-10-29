# Public origin from containers despite host `/etc/hosts` (backlog 76)

Status: implemented with local regression coverage (2026-10-29). **No real
Podman/systemd run of this change yet**; the lab check below is required before
the behaviour is called verified.

## Change

- `dev/dev.sh` runs `podman kube play --replace --no-hosts`.
- `quadlet/template.kube` adds `PodmanArgs=--no-hosts` to every installed unit.
- Pod `spec.hostAliases` is refused by the shared Pod shape guard
  (`render.pod_specs`): validate, prepare, install and bundle building.
- `dev/generate-certificates.sh platform <host>` (and therefore
  `dev/demo-credentials.sh`) refuses a retained web certificate that does not
  cover `<host>` and says to remove `web.crt`/`web.key`; it still never
  rotates a certificate by itself.
- Documentation: [COMPONENTS.md](../docs/COMPONENTS.md#reaching-the-public-origin-from-a-container)
  and the trust-chain `openssl -CAfile` check.

## Local evidence

`tests/platform_tests/test_public_origin_hosts.py`:

- the rendered shipped Quadlet template has `PodmanArgs=--no-hosts` in `[Kube]`;
- the single `podman kube play` line in `dev/dev.sh` has `--no-hosts`;
- `hostAliases` fails `validate` (exit 1, value not printed), `prepare` and
  `bundle.build()` with no host command and no file change.

`tests/platform_tests/test_certificates.py`
(`test_web_certificate_for_an_earlier_host_name_is_reported`): a certificate
issued for `old.example.test` is refused for `new.example.test` without any
write, accepted for its own name and `localhost`, and re-issued for the new
name from the retained CA after the two files are removed.

These are unit/fixture results with mocked Podman. They do not show that Podman
accepts `--no-hosts` for `kube play`/Quadlet or that the proxy name resolves.

## Origin of the change (operator-run, not a lab result)

On a developer VDI (2026-10-29, Podman version not recorded) the host maps its
own name, used in `PUBLIC_ORIGIN`, to `127.0.0.1`. In the backend container the
name resolved to `127.0.0.1` and `openssl s_client` got `Connection refused`;
the backend rejected tokens with `IDX10204`. With `--no-hosts` added by hand to
`dev/dev.sh`, the name appeared in the network's aardvark-dns file with the
proxy's internal address, the TLS connection succeeded (with item 70's chain
and a re-issued web certificate) and sign-in plus GraphQL worked.

## Lab recipe

Revision 2 (2026-10-29), after the first run stopped in part 2: with
`--no-hosts` Podman creates no `/etc/hosts`, so an image without its own file
(`mcr.microsoft.com/dotnet/aspnet:8.0`) has none at all. That is the intended
result (no host line reaches the container), not a failure. Step 3 now accepts
a missing file, the `localhost` checks are recorded observations instead of stop
conditions, and part 2 first records whether this Podman offers
`--hosts-file=none` (a generated `/etc/hosts` with `localhost` but without the
host's lines), which may be a better choice than `--no-hosts`.

**Continuing after the first run:** only documentation changed after
`5f4b499`, so part 1's CLEAN PASS (`hosts76-whoami-5f4b499`) still covers the
code. Start again at part 2, from its beginning, in that run's DEV checkout;
PROD still has that run's installation for part 3. If either VM was reset
since, run part 1 again first.

Four parts, in this order. Part 1 is the existing automated scenario; parts 2
and 3 are manual and add the host loopback line that no scenario sets; part 4
repeats the fixed matrix because every installed unit now carries
`--no-hosts`. Stop at the first failure and record it.

Values used below come from `~/.config/podman-offline-acceptance/lab.env` on the
controller: `SSH_USER`, `DEV_IP`, `PROD_IP`, `PROD_HOST`, `HTTPS_PORT`. The
product is `myproduct`, its runtime account `myproduct-ops`.

### Part 1: whoami scenario (controller)

From a clean checkout of the commit under test on the controller:

```sh
git rev-parse --short HEAD                # record it; must contain backlog 76
run=hosts76-whoami-$(git rev-parse --short HEAD)
python3 acceptance/acceptance.py --run "$run" --whoami run
```

Pass: `CLEAN PASS`, all steps. This shows that DEV `dev/dev.sh up` and the PROD
Quadlet units start with `--no-hosts` and that app3 signs in through the public
origin (`03-dev-whoami-e2e`, `08-whoami-e2e`), restarts and survives a reboot.
It does **not** yet set a loopback line in `/etc/hosts`.

### Part 2: DEV with the public name mapped to loopback (DEV VM)

The run leaves its source checkout, images and smoke environment on DEV. Log
in to DEV as `SSH_USER`:

```sh
run=<run ID from part 1>
cd ~/podman-offline-acceptance/$run/src
host=myproduct-proxy                      # config/dev.yaml: PUBLIC_ORIGIN host
podman --version; getenforce

# 1. Map the public name to loopback on the host, as on a developer VDI.
sudo sh -c "printf '127.0.0.1 %s\n' '$host' >> /etc/hosts"
getent hosts "$host"                      # expect 127.0.0.1 (host view)

# 2. Negative control: without --no-hosts a container would get that line.
proxy_image=$(python3 -B -c 'import yaml; d=[x for x in yaml.safe_load_all(open("components/platform/manifests/80-proxy.yaml")) if x and x["kind"]=="Pod"][0]; print(d["spec"]["containers"][0]["image"])')
podman network exists myproduct || podman network create myproduct
podman run --rm --pull=never --network myproduct --entrypoint getent "$proxy_image" hosts "$host"   # expect 127.0.0.1

# 2b. Record the hosts options this Podman offers (decision input, not a pass/fail step).
podman kube play --help | grep -iE -- '--(no-hosts|hosts-file)' || echo 'kube play: no hosts options listed'
podman run --help | grep -iE -- '--hosts-file' || echo 'run: no --hosts-file'
podman run --rm --pull=never --network myproduct --hosts-file=none --entrypoint cat "$proxy_image" /etc/hosts \
  || echo 'run --hosts-file=none not usable'
# Wanted: localhost present, no "127.0.0.1 $host" line from the host.

# 3. Start dev the normal way (dev/dev.sh passes --no-hosts).
./dev/dev.sh up
podman exec app3-whoami-backend sh -c "if [ -e /etc/hosts ]; then grep -c '$host' /etc/hosts || true; else echo 'no /etc/hosts'; fi"
                                                                               # expect 0 or 'no /etc/hosts'
podman exec app3-whoami-backend getent hosts "$host"                           # expect the proxy address below
podman inspect platform-proxy-nginx --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
# Observation (record, do not stop): does each container resolve "localhost"?
for c in $(podman ps --format '{{.Names}}'); do
  printf '%s hosts-file=%s localhost=' "$c" "$(podman exec "$c" sh -c '[ -e /etc/hosts ] && echo yes || echo no' 2>/dev/null || echo ?)"
  podman exec "$c" sh -c 'command -v getent >/dev/null || { echo NO-GETENT; exit 0; }; getent hosts localhost || echo NO-LOCALHOST' 2>/dev/null || echo NO-SHELL
done

# 4. Sign-in through the public origin while the host maps it to loopback.
SMOKE_RESTART_COMMAND='podman pod restart app3-whoami' .venv-smoke/bin/python dev/whoami-smoke-test.py

# 5. hostAliases conflict (records Podman's behaviour behind the refusal).
cat > /tmp/hostaliases-test.yaml <<'EOF'
apiVersion: v1
kind: Pod
metadata: {name: hostaliases-test}
spec:
  hostAliases: [{ip: 192.0.2.10, hostnames: [alias.example.test]}]
  containers:
  - {name: c, image: PROXY_IMAGE, imagePullPolicy: Never, command: [sleep, "30"]}
EOF
sed -i "s|PROXY_IMAGE|$proxy_image|" /tmp/hostaliases-test.yaml
podman kube play --no-hosts /tmp/hostaliases-test.yaml; echo "exit=$?"
podman kube down /tmp/hostaliases-test.yaml 2>/dev/null; rm -f /tmp/hostaliases-test.yaml

# 6. Restore.
./dev/dev.sh down
sudo sed -i "/^127\.0\.0\.1 $host\$/d" /etc/hosts
getent hosts "$host" || echo 'restored: no host entry'
```

Pass: step 2 shows `127.0.0.1` (the line would have reached a container);
step 3 shows `0` or `no /etc/hosts` for the backend and the name resolves to
the proxy's address; step 4 prints its `PASS` lines. Record, without stopping:
step 2b's output, the `localhost` line for every container (an address,
`NO-LOCALHOST`, `NO-GETENT` or `NO-SHELL`) and step 5's exit status and message.
A container that cannot resolve `localhost` is a finding for the
`--hosts-file` decision, not a failure of this run.

### Part 3: installed PROD with the public name mapped to loopback (PROD VM)

The run leaves platform, identity and app3 installed on PROD. Log in to PROD as
`SSH_USER`; the helpers run commands as the runtime account the same way the
harness does:

```sh
host=<PROD_HOST>; port=<HTTPS_PORT>
ops() { sudo -n -H -u myproduct-ops env XDG_RUNTIME_DIR=/run/user/$(id -u myproduct-ops) \
        XDG_CONFIG_HOME=/var/lib/myproduct/config XDG_DATA_HOME=/var/lib/myproduct/storage "$@"; }
units() { sudo -n systemctl --user -M myproduct-ops@ "$@"; }
podman --version; getenforce

# 1. The generated units run kube play with --no-hosts.
for u in platform identity app3; do printf '%s ' "$u"; units cat myproduct-$u.service | grep -c -- '--no-hosts'; done

# 2. Map the public name to loopback and recreate the containers.
sudo sh -c "printf '127.0.0.1 %s\n' '$host' >> /etc/hosts"
units restart myproduct-platform.service myproduct-identity.service myproduct-app3.service
sleep 20; units is-active myproduct-platform.service myproduct-identity.service myproduct-app3.service

# 3. The backend sees the proxy, not the host's line.
ops podman exec app3-whoami-backend sh -c "if [ -e /etc/hosts ]; then grep -c '$host' /etc/hosts || true; else echo 'no /etc/hosts'; fi"
                                                                               # expect 0 or 'no /etc/hosts'
ops podman exec app3-whoami-backend getent hosts "$host"                          # expect the proxy address below
ops podman inspect platform-proxy-nginx --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
# Observation (record, do not stop), as in part 2.
for c in $(ops podman ps --format '{{.Names}}'); do
  printf '%s localhost=' "$c"
  ops podman exec "$c" sh -c 'command -v getent >/dev/null || { echo NO-GETENT; exit 0; }; getent hosts localhost || echo NO-LOCALHOST' 2>/dev/null || echo NO-SHELL
done
```

Still on PROD, while the line is present, start a sign-in the way the harness
does (`whoami_login` in `remote.sh`). The backend needs the discovery document
to answer, so `302` to the authorize endpoint means it reached Duende through
the public origin; `500` was the chain-break result:

```sh
ops curl --noproxy '*' --cacert /var/lib/myproduct/state/PKI/private/ca.crt \
  --resolve "$host:$port:<PROD_IP>" --silent --show-error --max-time 30 \
  --output /dev/null --write-out '%{http_code} %{redirect_url}\n' \
  "https://$host:$port/app3/auth/login"        # expect 302 .../identity/connect/authorize?...
```

Then on PROD restore and confirm:

```sh
sudo sed -i "/^127\.0\.0\.1 $host\$/d" /etc/hosts
units restart myproduct-platform.service myproduct-identity.service myproduct-app3.service
```

Pass: `1` for each unit in step 1, all units active, `0` or `no /etc/hosts`
and the proxy's address in step 3, and `302` to the authorize endpoint while
the line was present. Record the `localhost` observations as in part 2. Part 1's next run
resets both VMs from their snapshots.

### Part 4: fixed matrix (controller)

```sh
rev=$(git rev-parse --short HEAD)
python3 acceptance/acceptance.py --run hosts76-normal-$rev run
python3 acceptance/acceptance.py --run hosts76-app2-$rev --first-app app2 run
python3 acceptance/acceptance.py --run hosts76-identity-$rev --identity-only run
python3 acceptance/acceptance.py --run hosts76-help-$rev --help-only run
python3 acceptance/acceptance.py --run hosts76-platform-help-$rev --platform-help-only run
python3 acceptance/acceptance.py --run hosts76-renamed-$rev --renamed-product run
```

Pass: `CLEAN PASS` in all six. If time is short, run `normal` first; the other
five follow before item 76 is called verified. These runs also give the first
real-host evidence for items 73 and 74 at this commit.

### Record

Add a dated result section here with: tested commit, run IDs and verdicts,
Podman version, SELinux mode, the outputs of parts 2 and 3 (addresses may be
shortened, no credentials), the hostAliases result, and any shipped component
that behaved differently without host entries. Update item 76's status and the
review guide's gap row only from these results.

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
