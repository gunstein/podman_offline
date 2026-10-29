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

## Lab check (required)

On the DEV VM, as an ordinary user, with the demo including app3:

```sh
host=myproduct-proxy        # the host name in the effective dev PUBLIC_ORIGIN
podman --version
sudo sh -c "printf '127.0.0.1 %s\n' '$host' >> /etc/hosts"     # lab admin
./dev/demo-credentials.sh && ./dev/dev.sh up
podman exec app3-whoami-backend sh -c "grep -c '$host' /etc/hosts || true"   # expect 0
podman exec app3-whoami-backend getent hosts "$host"             # expect the proxy's address
podman inspect platform-proxy-nginx --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
for c in $(podman ps --format '{{.Names}}'); do printf '%s ' "$c"; podman exec "$c" getent hosts localhost || echo NO-LOCALHOST; done
SMOKE_RESTART_COMMAND='podman pod restart app3-whoami' .venv-app/bin/python dev/whoami-smoke-test.py
sudo sed -i "/^127\.0\.0\.1 $host\$/d" /etc/hosts                # restore
```

Pass: no host line in the container, the name resolves to the proxy's address,
every container still resolves `localhost`, and the whoami smoke test passes
while the host maps the name to loopback.

On PROD after installing the platform and app3 releases, as the runtime user:

```sh
systemctl --user cat myproduct-platform.service | grep -c -- --no-hosts   # expect >= 1
```

Repeat the hosts-line part of the DEV check against the installed units and
run the installed public-HTTPS smoke. Also record whether `podman kube play
--no-hosts` with a Pod that declares `hostAliases` fails (the refusal assumes
it conflicts, as `--no-hosts` does with `--add-host` for `podman run`).

Record Podman version, SELinux mode, the outputs above and any shipped component
that behaved differently without host entries.
