# .NET and TypeScript demo app through Duende (backlog 71)

Status (2026-10-26): implemented as demo component `app3`. Verified end to end
with real `podman kube play` in dev, in both the public HTTPS variant (a) and
the internal variant (b). **Lab installation from bundles (OL9, Podman 5.8.2,
SELinux Enforcing, rootless, Quadlet/systemd) is pending.** No change to
`deployment/`.

## What was added

| Path | Content |
| --- | --- |
| `apps/whoami-backend/` | ASP.NET Core 8 BFF (`Program.cs`): cookie session, OpenID Connect handler, `GET /auth/login`, `GET /auth/me`, `POST /auth/logout`, `GET /api/claims`, `GET /livez` |
| `apps/whoami-frontend/` | TypeScript page (`src/app.ts`), built with `tsc` in a Node stage, served by nginx |
| `components/app3/` | `VERSION` 0.1.0, defaults, ConfigMap, Data Protection PVC, Pod `app3-whoami`, `route.conf` (`/app3/`), `client.yaml` (client ID `app3`) |
| `bundles.yaml` | `app3: requires [platform, identity], public_from/routes: platform, clients: identity` |
| `dev/generate-certificates.sh` | Demo recipe `app3`: client pair `credentials/client/client.{key,crt}` (clientAuth) |
| `dev/demo-credentials.sh` | Also runs `app3`, then copies the dev CA to `build/dev/app3/cert/{root,ca}.crt` (backlog 70) |
| `dev/whoami-smoke-test.py` | End-to-end check through the proxy (below) |

Images: `localhost/demo-whoami-backend:0.1.0` and
`localhost/demo-whoami-frontend:0.1.0`, built by `dev/build-images.sh` like the
other demo images. No database, seed data or init containers.

## The six conversion points

| # | Point | Result | What the real backend needs |
| --- | --- | --- | --- |
| 1 | Callback path | **Confirmed, configuration only.** `UsePathBase(BASE_PATH)` plus `CallbackPath = "/auth/callback"` gives `redirect_uri = PUBLIC_ORIGIN + BASE_PATH + /auth/callback`, the client protocol's URI; `/signin-oidc` is not used and the protocol is unchanged. **Changed detail:** ASP.NET's default `response_mode=form_post` makes Duende answer with a form that the browser POSTs to the callback (the Python apps use the query mode); the route passes the POST, Duende accepts it. | Set `CallbackPath` (and the path base) as above; route `<base>/auth/` to the backend. |
| 2 | Forwarded headers | **Confirmed.** `ForwardedHeaders.XForwardedProto` with `KnownNetworks`/`KnownProxies` cleared, before authentication; the route sets `X-Forwarded-Proto https` and `Host $http_host`. Negative control: the same image without `UseForwardedHeaders()` produced `redirect_uri=http://myproduct-proxy:8443/app3/auth/callback`. | The same middleware; nginx already sends the headers. |
| 3 | Data Protection keys | **Confirmed.** Keys in PVC `app3-protection` at `/data/protection` (`PersistKeysToFileSystem`, `SetApplicationName`). The signed-in session survived `podman pod restart app3-whoami` and `dev/dev.sh down` + `up`. Negative control: deleting the key files and restarting turned the same cookie into `401`. Keys are stored unencrypted, as Identity's (backlog 37). | A PVC for the key ring; it is kept on uninstall without `--delete-data`. |
| 4 | CA trust chain | **Confirmed in dev.** Backlog 70's pattern: Secret `app3-ingress-trust-chain` from `cert/`, two `subPath` mounts to `/etc/ssl/certs/myproduct-{root,ca}.pem`. The image's own 297 CA files stayed (299 entries). .NET trusted the proxy for discovery, JWKS, token and userinfo. Negative control: an unrelated CA in both files made `/app3/auth/login` return `500` with `IDX20803 ... The SSL connection could not be established` and `AuthenticationException: ... errors in the certificate chain: PartialChain` in the backend log; restoring the CA fixed it. | Backlog 70's declaration and mounts, CA copied from the environment. |
| 5 | `private_key_jwt` | **Confirmed.** `OnAuthorizationCodeReceived` adds an RS256 client assertion (`iss = sub = client ID`, `aud` = the token endpoint from discovery, `jti`, 1 minute lifetime) signed with `X509SigningCredentials` from the client pair; Duende accepted it in both variants. | The same event handler; the client certificate is registered through `client.yaml`. |
| 6 | TypeScript build | **Confirmed.** Two stages: `node:22-alpine` runs `npm ci` (TypeScript 5.9.3 pinned in `package-lock.json`) and `tsc`; the runtime is `nginx:1.28-alpine` with `index.html` and the compiled `app.js` only. The build needs `registry.npmjs.org` on the build machine; `./build-bundle.sh app3` saved both images in one 114 MB archive, so installation is offline. | A lockfile; network only at build time. |

Other findings:

- The demo Identity issues no `name` claim, neither in the ID token nor from
  userinfo (its default profile service sees only access-token claims). The app
  shows `sub`, as app1/app2 do. A real Duende configuration has its own profile
  service; this is not a conversion risk.
- The client protocol has no post-logout redirect URI, so logout is local
  (`POST /auth/logout` with antiforgery token and `Origin` check). If the real
  backend signs out at Duende, `client.yaml` and Identity need a post-logout URI:
  **open**.
- `podman kube play` pods do not inherit the host's proxy variables; a plain
  `podman run` does (`--http-proxy`), which matters only for manual tests.

## Public HTTPS versus internal calls

| | (a) Public HTTPS (default, as Kubernetes) | (b) Internal |
| --- | --- | --- |
| Config | `IDENTITY_INTERNAL_URL: ''` | `IDENTITY_INTERNAL_URL: http://identity-server:8080/identity` |
| Discovery, JWKS, token, userinfo | `https://<public origin>/identity/...` through nginx | `http://identity-server:8080/identity/...` on the Podman network |
| Browser authorize | public, from discovery | public, **overridden by the app** |
| Issuer / `ValidIssuer` | public | public (Identity sets `IssuerUri`) |
| Trust chain | required | not used (passed with an unrelated CA mounted) |
| App code beyond (a) | none | `MetadataAddress`, `RequireHttpsMetadata = false`, and `ProtocolMessage.IssuerAddress` in `OnRedirectToIdentityProvider` |
| Dev result | pass | pass, including restart |

Duende does **not** publish split endpoints: it builds every endpoint from the
request's host, so the internally fetched discovery document names
`http://identity-server:8080/identity/connect/authorize` (and the token, JWKS
and end-session endpoints) while `issuer` stays public. Without the override
the browser would be sent to the internal host. A real backend using (b) must
also override `end_session_endpoint` if it signs out at Duende. The client
assertion's audience then is the internal token endpoint, which Duende accepted.

Security review points for (b): the authorization code, PKCE verifier, client
assertion, ID/access tokens and userinfo travel unencrypted between containers
on the product network; `RequireHttpsMetadata = false` must stay limited to
this internal address; the backend depends on another component's Pod name
(`identity-server`) and port. Variant (a) keeps all OIDC traffic on TLS and
needs no endpoint overrides. **Recommendation:** convert the real backend with
(a), as the backlog item already directs, unless the security review accepts
plaintext traffic on the Podman network.

## How to repeat in dev

On a machine with network access to the image and package registries:

```sh
./dev/build-images.sh && ./dev/pull-images.sh
cp config/dev.yaml.example config/dev.yaml && chmod 600 config/dev.yaml
./dev/demo-credentials.sh && ./deploy.sh validate && ./dev/dev.sh up
python3 -m venv .venv-app && .venv-app/bin/pip install -r apps/todo-backend/requirements.txt
SMOKE_RESTART_COMMAND='podman pod restart app3-whoami' .venv-app/bin/python dev/whoami-smoke-test.py
```

Expected: four `PASS` lines (HTTPS, routes, compiled frontend, anonymous `401`
and the https callback URI; sign-in through Duende and the claims API; session
after restart; CSRF/origin checks and local logout).

Variant (b): write `IDENTITY_INTERNAL_URL: http://identity-server:8080/identity`
to `components/app3/config.dev.yaml` (not committed), `./dev/dev.sh up`, run the
smoke test; the backend log names the internal address. Remove the file and
run `./dev/dev.sh up` again to return to (a).

Trust-chain negative control: copy an unrelated CA certificate over
`build/dev/app3/cert/root.crt` and `ca.crt`, `./dev/dev.sh up`, request
`/app3/auth/login` (expect `500` and `PartialChain` or `UntrustedRoot` in
`podman logs app3-whoami-backend`), then rerun `./dev/demo-credentials.sh` and
`./dev/dev.sh up`.

## Results of this change

Real Podman run (2026-10-26): Podman 4.9.3, rootful, inside an Ubuntu 24.04
container without SELinux, systemd or Quadlet. This is dev evidence, not the
lab. All nine dev pods started; `dev/whoami-smoke-test.py` passed in (a) and
(b) with the restart check; app2's `dev/smoke-test.py` still passed; the
negative controls for points 2, 3 and 4 behaved as described above. The
backend compiles without warnings, and `dotnet list package --vulnerable
--include-transitive` reports none.

Automated tests: `tests/demo_tests/test_whoami_demo.py` (client pair issued
once by the environment's CA with clientAuth; paths shared by `client.yaml`,
`SECRET_FILES`, demo provisioning, mounts and `Program.cs`; callback, forwarded
headers, assertion type and ports; two-stage frontend with pinned TypeScript)
and the existing demo tests updated for six components. The acceptance harness
tolerates `app3` (see below).

## Lab: installation from bundles (pending)

Starting state: a lab host with platform and identity installed as the runtime
user by the current procedure, the demo CA in
`/var/lib/myproduct/state/PKI/private/ca.crt` (as the harness provisions it)
and the `app3` release published like the others.

1. DEV: `./dev/build-images.sh && ./dev/pull-images.sh && ./build-bundle.sh app3`;
   transfer `dist/myproduct-app3-0.1.0-offline.tar.gz` with its `.sha256`
   (and `.asc` when signed) and publish it as for the other components.
2. PROD, runtime user, with `release=/var/lib/myproduct/releases/myproduct-app3-0.1.0`
   and `state=/var/lib/myproduct/state`:

   ```sh
   bash "$release/deploy.sh" init-config app3
   bash -s -- --root "$state" app3 myproduct-proxy < generate-certificates.sh
   install -d -m 0700 "$state/app3/cert"
   install -m 0644 "$state/PKI/private/ca.crt" "$state/app3/cert/root.crt"
   install -m 0644 "$state/PKI/private/ca.crt" "$state/app3/cert/ca.crt"
   bash "$release/deploy.sh" validate && bash "$release/deploy.sh" install
   ```

   `generate-certificates.sh` is copied from DEV as the harness does; it is not
   in the bundles. If the proxy certificate came from a supplier, copy the
   supplier's issuing chain instead of the demo CA.
3. Run `dev/whoami-smoke-test.py` as for app1/app2, with `PUBLIC_ORIGIN`,
   `CONNECT_IP`, `SMOKE_CA_FILE`,
   `SMOKE_PASSWORD_DIR=/var/lib/myproduct/state/identity/credentials/users` and
   `SMOKE_RESTART_COMMAND='systemctl --user restart myproduct-app3.service'`.
4. Trust chain: replace both `cert/` files with an unrelated CA, `install`
   again, expect `500` at `/app3/auth/login` and `PartialChain`/`UntrustedRoot`
   in `journalctl --user -u myproduct-app3.service`; restore and `install`.
5. Variant (b): set `IDENTITY_INTERNAL_URL` in `$state/app3/config.yaml`,
   `install`, repeat 3; restore the empty value and `install`.
6. Record here the Podman version, SELinux mode, results and anything that
   differed from dev, including whether `subPath` works with SELinux labels.

## Acceptance harness and matrix

`app3` is in the catalog but not in the fixed acceptance matrix, as the backlog
item states. On DEV the harness builds its images, validates it (`dev-up`
expects `app3` in the validated list) and starts it with the other dev pods;
no scenario installs it on PROD, and `current-bundles.txt` lists six bundles
while the scenarios transfer their fixed sets. The renamed product
(`acceptance/renamed_product.py`) leaves `app3` out, so its five-component
expectations are unchanged. Adding `app3` to the matrix (container counts,
install orders, e2e, upgrade) is a follow-up if it proves useful.

## Gaps

- Lab verification above, including Podman 5.8.2 `subPath` under SELinux
  ([trust chain](TRUST-CHAIN.md)).
- Only the single-level demo CA is exercised; a root plus issuing CA is not.
- Post-logout redirect through Duende (open, point 1 findings).
- Operator impact: none for the shipped procedure; `app3` is a developer demo
  and not part of the production manual, so no AI or human operator review applies.
