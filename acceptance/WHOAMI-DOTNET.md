# .NET and TypeScript demo app through Duende (backlog 71)

Status (2026-10-26): implemented as demo component `app3` and lab verified at
`45fdb17e8d7e6a4df745ee846d925851557d8794`: signed offline bundle installation,
both OIDC variants, trust-chain negative control and session persistence across
user-systemd restarts passed on OL9.8, Podman 5.8.2, rootless, SELinux Enforcing.
Earlier real `kube play` dev evidence is retained separately below. No change
to `deployment/` or the fixed matrix's component counts/install orders/upgrades.

The opt-in `--whoami` scenario added in `f82d107` has not been run in this
lab verification. Testing stopped at the user's request before that update was
pulled; results below do not verify the newer harness.

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

## The six conversion points (earlier dev evidence)

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
- Local logout does not revoke the session: ASP.NET's cookie is
  self-contained, so a copy of it taken before logout stays valid until it
  expires (1 hour here). The session script showed this in dev. app1/app2's
  signed Flask cookie behaves the same way. If the real backend must revoke
  sessions at logout, it needs a server-side ticket store
  (`CookieAuthenticationOptions.SessionStore`) or short lifetimes: **open**.
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

## Earlier dev results

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

## Lab: the `--whoami` acceptance scenario (not yet run)

```sh
python3 acceptance/acceptance.py --run whoami-1 --whoami run
```

A focused scenario like `--identity-only`: it resets both VMs from their
snapshots, isolates PROD from the internet and runs the steps below in order,
stopping at the first failure. It cannot be combined with another focused
scenario, `--status-retry` or `--host-setup`. The fixed matrix is unchanged.

| Steps | Machine | What is checked |
| --- | --- | --- |
| `03-build-images` … `03-dev-down` | DEV | Demo images including app3, dev validate/up, `dev/whoami-smoke-test.py` with a pod restart |
| `04-bundle`, `05-transfer-*` | DEV → PROD | Signed bundles; only platform, identity and app3 are transferred and published |
| `06-prepare-host`, `06-install-*` | PROD | Host preparation, then platform, identity and app3 installed as the runtime account, each checked healthy. app3's demo client pair comes from `generate-certificates.sh`, its chain is copied from `state/PKI/private/ca.crt` (`whoami_trust_chain` in `remote.sh`) |
| `07-check` | PROD | The existing installation checks (units, graphroot, permissions, no rootful containers) |
| `07-whoami-chain-mounts` | PROD | Backlog 70's lab check in the running backend: Podman version and SELinux mode recorded, both `subPath` files equal the environment's CA, more than two entries remain in `/etc/ssl/certs` |
| `08-whoami-e2e` | DEV → PROD | Smoke test through the public origin (variant a) |
| `08-whoami-session-create` … `09-whoami-session-reboot` | DEV and PROD | One saved session (`acceptance/whoami_session.py`) still signed in after `systemctl --user restart myproduct-app3.service` and after a PROD reboot; then local logout |
| `10-whoami-chain-break` | PROD | An unrelated CA in both chain files and a reinstall: sign-in start answers `500` and the backend log names `PartialChain` or `UntrustedRoot` |
| `10-whoami-internal`, `10-whoami-internal-e2e` | PROD, DEV → PROD | Variant b (`IDENTITY_INTERNAL_URL`) with the unrelated CA still mounted: the log names the internal address, the browser is sent to the public authorize endpoint, the smoke test passes |
| `10-whoami-restore`, `10-whoami-restored-e2e`, `10-check-restored` | PROD, DEV → PROD | Empty `IDENTITY_INTERNAL_URL` and the environment's CA restored, public variant logged, smoke test and installation checks pass |
| `10-home-unchanged`, `11-prod-audit` | PROD | No product writes in the login home; no AVC or fapolicyd denials since the run started |

Record the run's verdict, Podman version and SELinux mode here, and anything
that differed from dev. The scenario does not cover upgrade, uninstall or the
other demo apps beside app3.

Before a real run, the PROD steps' shell code was run against the real dev
pods in this container, with `as_product` running commands directly and
`dev/dev.sh up` standing in for the install. `whoami-chain-mounts`,
`whoami-chain-break`, `whoami-internal` and `whoami-restore` passed, and so did
the smoke test in variant b and after the restore. The session script passed
create, check after a pod restart, and logout after `dev/dev.sh down` + `up`.
This exercised the log patterns and the curl output format; it does not
replace the lab run.

Manual equivalent for a host outside the harness, as the runtime account after
the release is published, with `release=/var/lib/myproduct/releases/myproduct-app3-0.1.0`
and `state=/var/lib/myproduct/state`:

```sh
bash "$release/deploy.sh" init-config app3
bash -s -- --root "$state" app3 myproduct-proxy < generate-certificates.sh
install -d -m 0700 "$state/app3/cert"
install -m 0644 "$state/PKI/private/ca.crt" "$state/app3/cert/root.crt"
install -m 0644 "$state/PKI/private/ca.crt" "$state/app3/cert/ca.crt"
bash "$release/deploy.sh" validate && bash "$release/deploy.sh" install
```

`generate-certificates.sh` is copied from DEV; it is not in the bundles. If the
proxy certificate came from a supplier, copy the supplier's issuing chain
instead of the demo CA.

## Completed lab verification (2026-10-26)

Every result in this section tested commit
`45fdb17e8d7e6a4df745ee846d925851557d8794` on branch
`claude/sweet-fermat-08ibq2`. DEV VM 107 and PROD VM 108 are the configured,
authorized disposable lab VMs. Both ran Oracle Linux Server 9.8, Podman 5.8.2,
SELinux Enforcing. App3 ran rootless on PROD as `myproduct-ops` (UID 1001),
through `myproduct-app3.service` and Quadlet. These are new lab results, not
reuse of the earlier rootful Podman 4.9.3 dev evidence.

### Six conversion points: lab outcome

| # | Point | Lab status at `45fdb17` | Evidence and limits |
| --- | --- | --- | --- |
| 1 | Callback path | **Confirmed** | Both variants passed the public HTTPS `/app3/auth/callback` redirect and actual `form_post` callback through nginx/Duende. No protocol change. Duende post-logout redirect remains open; only local logout is tested. |
| 2 | Forwarded headers | **Confirmed** | Smoke asserted the HTTPS redirect URI and completed sign-in behind the real proxy. The dev-only middleware-removal negative control was not repeated in the lab. |
| 3 | Data Protection keys | **Confirmed** | The same authenticated cookie and claims API worked after `systemctl --user restart myproduct-app3.service` in both variants, including (b) with unrelated CA. App3 reboot and same-cookie survival across install were not tested. |
| 4 | CA trust chain | **Confirmed** | Rootless Secret `subPath` probe passed first; both actual app3 mounts matched the environment CA, retained 299 CA-store entries and had SELinux `container_file_t:s0` labels. Unrelated CA in both files caused HTTP 500 plus user-journal `PartialChain`; restoration recovered sign-in. Only a single-level demo CA was tested. |
| 5 | `private_key_jwt` | **Confirmed** | Real Duende sign-in and claims API passed using the bundled .NET handler and runtime client certificate in both variants; no assertions, tokens or private keys were printed. |
| 6 | TypeScript build | **Confirmed** | DEV built both app3 images, including successful NuGet restore, `npm ci` and `tsc`; the signed app3 bundle carried both images. PROD remained network-isolated for installation and served the compiled frontend checked by smoke. |

### Installation steps 1–6 and controls from the `45fdb17` recipe

1. **Confirmed:** the normal matrix's DEV image build/pull and bundle build
   produced `myproduct-app3-0.1.0-offline.tar.gz`, its checksum and signature.
   The app3 archive was transferred separately and published with the existing
   protected-release helper and the run's pinned signing key. Signature,
   immutable publication and fapolicyd trust checks passed.
2. **Confirmed:** with platform and Identity already installed by the normal
   matrix, the runtime user ran `init-config app3`, the supplied demo certificate
   recipe on stdin, both CA copies, `validate` and `install`. App3's two
   containers, Identity and platform were healthy. No files under `deployment/`
   were changed. This used the harness's runtime-user invocation with its
   configured XDG paths; it was not an unassisted human/real-SSH operator trial.
3. **Confirmed:** the smoke test ran as the runtime user on PROD with
   `PUBLIC_ORIGIN=https://myproduct-proxy:8443`, `CONNECT_IP=192.168.0.108`,
   the PROD CA and Identity password directory, and exactly
   `SMOKE_RESTART_COMMAND='systemctl --user restart myproduct-app3.service'`.
   It produced the four lines below. **Changed lab prerequisite:** PROD lacked
   `requests`; public Python dependencies were transferred from DEV in a zip,
   and the unchanged smoke source was supplied on stdin (compatible with
   fapolicyd). No PROD package download was used. An initial invocation with
   loopback failed readiness because the proxy binds the PROD IP; correcting
   `CONNECT_IP` resolved this test-invocation error.
4. **Confirmed, with a journal prerequisite repair:** unrelated CA in both
   `cert/` files plus install gave HTTP 500 at `/app3/auth/login`. Initially
   `journalctl --user` could not open a journal: the matrix baseline had no
   persistent user journal. Running the existing guarded
   `scripts/release.py` `prepare_persistent_journal()` helper as root, then
   reinstalling, made the runtime journal readable and confirmed `PartialChain`.
   [Bounded excerpt and SELinux details](TRUST-CHAIN.md#completed-lab-verification-2026-10-26).
   Restoring the correct CA and installing again restored all four smoke PASS
   lines. This repair does not retrospectively verify the baseline journal.
5. **Confirmed:** setting `IDENTITY_INTERNAL_URL` to
   `http://identity-server:8080/identity`, installing and running smoke produced
   four PASS lines; replacing both CA files with the unrelated CA, reinstalling
   and repeating smoke also produced four PASS lines. Both mounted files were
   checked against the unrelated CA. Actual internal discovery advertised
   internal authorize/token/JWKS/userinfo URLs and the public issuer, confirming
   the browser authorize override is still needed. Finally the correct CA and
   empty config value were restored, install was repeated, and public HTTPS
   smoke again produced four PASS lines. The temporary unrelated CA was removed.
6. **Confirmed:** runtime/version/SELinux facts and differences are recorded
   here and in the trust-chain report. Session survival across a user-service
   restart passed in every successful smoke run. **Open:** app3 reboot persistence; the
   normal matrix's successful reboot did not include app3 and is not evidence
   for it.

Each successful smoke invocation produced:

```text
PASS: HTTPS, routes, compiled frontend, anonymous 401, https callback URI
PASS: alice signed in through Duende (PKCE, private_key_jwt); claims API
PASS: the session cookie still works after restarting the app
PASS: CSRF and origin checks; local logout
```

### Separate test and matrix evidence

- **Product/unit:** DEV `python3 -B tests/run.py all`: 559 tests passed in
  108.107 seconds. Source/assertion coverage is separate from the runtime checks.
- **Acceptance harness:** controller
  `python3 -B -m unittest discover -s acceptance -p 'test_*.py'`:
  341 tests passed in 9.434 seconds.
- **Real matrix:** normal `app3-45fdb17-normal`: **CLEAN PASS**, including
  offline installation, sign-in, restart/recovery, reboot, upgrades, scoped
  uninstall and final PROD audit. `dev-up` accepted app3, and all six bundles
  built; app3 remained outside the fixed PROD matrix.
- **Real renamed matrix:** `app3-45fdb17-renamed`: **STOPPED at user request; incomplete, not CLEAN.**
  Eighteen completed steps passed with no recorded failure, through
  `05-transfer-login-service`; the controller was stopped during the next
  bundle transfer. Renamed PROD installation/lifecycle and final audit were
  not reached. No complete runner verdict was generated. The generated catalog/component tree and five-bundle list were checked:
  app3 is absent; only gateway, login-service, orders, inventory and manual
  appear in the retained bundle list.
- Controller evidence is retained under
  `~/podman-offline-acceptance-runs/app3-45fdb17-normal/{REPORT,EVIDENCE}.md`.
  The interrupted renamed run retains `record.jsonl` and step logs under
  `~/podman-offline-acceptance-runs/app3-45fdb17-renamed/`; it has no final report.
  These are local lab artifacts, not repository-relative links. The normal run
  completed before the separate app3 test; app3 was restored before the renamed
  scenario reset the same authorized VMs. No unrelated environment was reset.

### Understandability and operator review

Documentation review traced declared CA files through Secret mounts, runtime
trust failure, reinstall/restoration, and the persistent Data Protection volume
through a service restart. The report distinguishes source tests, harness tests,
real matrix evidence and app3 evidence, and records the two lab prerequisite
issues rather than hiding them. No implementation/control-flow change required
a code understandability redesign. The lab result identifies the correct
`CONNECT_IP` choice. AI procedure assessment: **findings** (offline smoke
prerequisite and baseline user-journal availability, remedied for this run as
above). Human operator assessment: **not performed**; this developer acceptance
exercise does not establish unassisted operator usability.

## Acceptance harness and matrix

`app3` is in the catalog but not in the fixed acceptance matrix, as the backlog
item states. In the fixed scenarios DEV builds its images, validates it
(`dev-up` expects `app3` in the validated list) and starts it with the other
dev pods; no fixed scenario installs it on PROD, and `current-bundles.txt`
lists six bundles while those scenarios transfer their fixed sets. The renamed
product (`acceptance/renamed_product.py`) leaves `app3` out, so its
five-component expectations are unchanged. Only the opt-in `--whoami`
scenario above installs `app3`. `acceptance/test_whoami.py` covers its step
order, flag rules, the chain copy and the PROD steps' pass and fail paths with
stubbed commands.

## Gaps

- The organisation's real backend is not covered by the app3 lab result.
- App3 reboot persistence, same-cookie persistence across install, and the
  dev-only forwarded-header/key-deletion negative controls were not lab-tested.
- The renamed matrix was stopped at user request during transfer; its PROD
  lifecycle and final audit remain unverified.
- The newer `f82d107` `--whoami` harness and its added tests were not run here.
  Test counts above apply only to `45fdb17`.
- Only the single-level demo CA is exercised; a root plus issuing CA is not.
- Post-logout redirect through Duende (open, point 1 findings).
- App3 remains outside the fixed PROD matrix; adding its counts, install orders
  and upgrade coverage is a separate follow-up. No human operator trial occurred.
- The unmodified matrix baseline lacks persistent user-journal access; this run
  repaired it with the existing host-setup helper for the app3 negative control.
