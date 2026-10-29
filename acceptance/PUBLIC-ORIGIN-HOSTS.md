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

# 3. Start dev the normal way (dev/dev.sh passes --no-hosts).
./dev/dev.sh up
podman exec app3-whoami-backend sh -c "grep -c '$host' /etc/hosts || true"    # expect 0
podman exec app3-whoami-backend getent hosts "$host"                           # expect the proxy address below
podman inspect platform-proxy-nginx --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
for c in $(podman ps --format '{{.Names}}'); do printf '%s ' "$c"; podman exec "$c" getent hosts localhost || echo NO-LOCALHOST; done

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
step 3 shows no line in the backend's `/etc/hosts`, the name resolves to the
proxy's address and every container resolves `localhost`; step 4 prints its
`PASS` lines. Step 5 is informational: record the exit status and message.

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
ops podman exec app3-whoami-backend sh -c "grep -c '$host' /etc/hosts || true"   # expect 0
ops podman exec app3-whoami-backend getent hosts "$host"                          # expect the proxy address below
ops podman inspect platform-proxy-nginx --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
for c in $(ops podman ps --format '{{.Names}}'); do printf '%s ' "$c"; ops podman exec "$c" getent hosts localhost || echo NO-LOCALHOST; done
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

Pass: `1` for each unit in step 1, all units active, no line and the proxy's
address in step 3, every container resolves `localhost`, and `302` to the
authorize endpoint while the line was present. Part 1's next run
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
