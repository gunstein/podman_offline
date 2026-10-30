# Component environment files: phase 0 design (backlog 77)

Status: **decisions in section 7 signed off by the product owner
(2026-10-29); the developer walkthrough in section 8 was dropped by the
product owner the same day; phase 1 is next; not implemented.** Phase 0 of [backlog 77](../BACKLOG.md#77-make-a-component-intuitive-to-write-env-files-mounts-and-shared-secrets),
after the [component model analysis](COMPONENT-MODEL-ANALYSIS.md). Code
references describe `main` at `00d34e4`. Nothing here changes current
behaviour until phase 1 is implemented and verified.

Phase 0 fixes the details phase 1 needs:

1. the `env/<container>.yaml` file and its rules;
2. the short secret reference `@@secret:<id>@@`;
3. what `validate` reports and how errors read;
4. a draft example component for the organisation's architecture;
5. a one-page conversion checklist;
6. the decisions to sign off and the walkthrough that gates phase 1.

## 1. Principles applied

From backlog 77: one fact in one place, where a developer would look; the
platform derives the rest and says what it derived; ambiguity is refused; a
simplification never removes an existing safety check; recipes ship with the
release and the operator owns values.

The test for every rule below: could a developer who has not read this
document guess it correctly from the files and the messages?

## 2. `env/<container>.yaml`

### Location and target

```text
components/<component>/env/<container>.yaml
```

- `<container>` is the `name` of a container in the component's Pods, regular
  or init container. The file sets that container's environment.
- The name must occur **exactly once** across the component's Pods. A file
  without a matching container, or a container name used in two Pods, is
  refused before anything is written (rename the container). No qualified
  `<pod>/<container>` form in phase 1; add it only if a real case needs it.
- Only `*.yaml` directly under `env/`; subdirectories, other extensions,
  symlinks and special files are refused.

### Format

A flat map from variable name to value. Nothing else.

```yaml
# components/orders/env/api.yaml
ASPNETCORE_HTTP_PORTS: 5000
Authentication__Authority: '@@PUBLIC_ORIGIN@@/identity'
ConnectionStrings__Default: 'Host=orders-postgres;Database=orders;Username=orders;Password=@@secret:orders-database-password@@'
```

- **Variable names** follow the existing Secret/ConfigMap key rule
  (`common.SECRET_KEY`: letters, digits, `-`, `.`, `_`) and must not start with
  a digit. A name containing `:` is refused with the hint "use `__` for
  .NET sections (`Authentication__Authority`)", because compose files often use
  `Authentication:Authority`.
- **Values** are strings or integers. Integers are written in decimal.
  `true`/`false`, floats, null, lists and maps are refused with "quote the
  value" (YAML turns `yes`, `on`, `1.0` and `~` into other types silently).
- Duplicate keys are refused with their line (the existing `UniqueKeyLoader`).
- An empty file is refused (delete it instead).

### Placeholders

The same grammar as today (`deployment/templates.py`): one non-recursive pass,
`@@` outside a placeholder is refused.

| Form | Meaning |
| --- | --- |
| `@@NAME@@` | A config value (`PUBLIC_ORIGIN`, `DB_HOST`, ...) from the usual layers. Must be text or an integer. |
| `@@secret:<id>/<key>@@` | A key of this component's `SECRET_FILES.<id>` (today's form). |
| `@@secret:<id>@@` | Short form: the only key of `SECRET_FILES.<id>` (section 3). |

No other forms in phase 1 (no `provided:`, no `shared:`; see backlog 77).

### What the platform makes of it

For a file `env/api.yaml` in component `orders`:

| Lines | Delivered as | Generated resource |
| --- | --- | --- |
| Without a secret reference | ConfigMap data, composed like today's inline ConfigMap values | `orders-api-env` (ConfigMap) |
| With a secret reference | Secret data, composed like today's `SECRET_TEMPLATES` | `orders-api-env` (Secret) |

- A line with any secret reference is private as a whole. A line without one
  is public. The platform does not guess whether a literal is a password: a
  literal password written as plain text is public. The checklist says so.
- The container gets `envFrom` entries for the generated ConfigMap and/or
  Secret, appended after its hand-written entries. Only the resources that
  exist are referenced (no empty Secret for a public-only file).
- Generated names are `<component>-<container>-env`. They fall under the
  component prefix rule; a hand-written resource or a `SECRET_FILES`,
  `VOLUME_FILES` or `SECRET_TEMPLATES` ID with the same name is refused, naming
  both.
- The generated ConfigMap and Secret are ordinary resources in the rendered
  YAML: uninstall removes them like any other, and the install YAML stays 0600.

### Conflicts (always refused, never resolved silently)

- The same variable in `env/<container>.yaml` and in that container's
  hand-written `env`: refused, naming both places.
- The same variable in `env/` and a key of a hand-written `envFrom`
  ConfigMap/Secret of that container: refused when the keys are known. For a
  supplied `SECRET_FILES` source whose keys are only known once the operator
  has provided the files, the check runs at materialization, before any YAML is
  published.
- A container with `env/` and a hand-written `envFrom` pointing at the
  generated name: refused (the platform adds it).

### Exact-byte rules for secret values

One rule for everything in `env/`, identical to today's `SECRET_TEMPLATES`
(`templates.documents` / `check_text`):

- the source file is read as UTF-8; one or more trailing LF bytes are removed
  (as PostgreSQL's `file_env` does); an empty result is refused;
- a substituted value (secret or config) must not have leading/trailing
  whitespace, `;`, `"`, `'`, control characters or `@@`;
- the text around placeholders is free.

Generated secrets always satisfy these rules. A supplied secret that does not
(for example a password containing `;`) must use the existing escape hatch: a
`secretKeyRef` or a Secret volume in the manifest, which delivers the file byte
for byte. The error message says so. Item 72's API secret already refuses a
trailing newline, so API values agree on both sides.

### Dev and production

- `env/` ships with the component and changes only with a new release. It is
  not a config layer: no `env.dev/`, no per-environment variants. Values that
  differ per environment come from `@@NAME@@` and the usual config layers
  (`config/dev.yaml`, component `config.dev.yaml`, production `config.yaml`).
- Dev `prepare`, `validate`, bundle build and production `install` all read the
  same files through the same function.

### Bundling

`bundle.py` copies `env/` with the other component entries (today `manifests`,
`config.defaults.yaml`, `route.conf`, `client.yaml`, `api.yaml`, `files`). It
is then covered by `checksums.sha256` and the signature like every other
bundle file. The private-source guard applies.

### Where it plugs in (for implementers)

`env/` is **lowered** into existing structures before the existing checks run,
inside `render.effective_documents`:

1. read and check the files (format, names, targets, conflicts that need no
   secret keys);
2. add one synthetic ConfigMap document per container (data composed by
   `templates.config_text`) and one synthetic `SECRET_TEMPLATES` entry per
   container (composed by `templates.documents`);
3. append the `envFrom` references to the target container;
4. continue with the unchanged checks: names, kinds, links, secret keys,
   database preflight.

One renderer; no second path. Validation reads no secret contents, as today.

## 3. Short secret reference `@@secret:<id>@@`

- `<id>` must be declared in this component's `SECRET_FILES`. An unknown `<id>`
  is refused with the file, variable and "declare `SECRET_FILES.<id>` in
  config.defaults.yaml or correct the name". A reference never creates a
  secret.
- The short form is allowed only when the declaration has **exactly one key**:
  a single source whose `generate` lists one name, or a single `path` source
  that is one file (its file name is the key). Otherwise it is refused with "has
  N keys; use `@@secret:<id>/<key>@@`". For a supplied source that does not exist
  yet, the key count is checked at materialization, before writes.
- The long form `@@secret:<id>/<key>@@` keeps working everywhere it works today.
- Phase 1 also accepts the short form in `SECRET_TEMPLATES`, so there is one
  grammar.

Typical declarations:

```yaml
# components/orders/config.defaults.yaml
SECRET_FILES:
  orders-database-password:         # generated once, kept byte for byte
  - path: credentials/database
    generate: [password]
  orders-export-key:                # supplied by the operator; install stops until it exists
  - path: credentials/export-key
```

## 4. What `validate` shows and how errors read

On success, one line per container with an `env/` file and no values:

```text
[OK] orders/api: env/api.yaml -> 3 settings (ConfigMap orders-api-env), 1 secret (Secret orders-api-env: orders-database-password)
[OK] orders/web: env/web.yaml -> 2 settings (ConfigMap orders-web-env)
```

Errors name the file, the variable and the next action, never a value:

```text
ERROR: components/orders/env/api.yaml: ConnectionStrings__Default references secret orders-db-password, which is not declared; declare SECRET_FILES.orders-db-password in config.defaults.yaml or correct the name
ERROR: components/orders/env/api.yaml: no container named api in the orders Pods (found: db, web, backend)
ERROR: components/orders/env/api.yaml: Authentication:Authority contains ':'; write Authentication__Authority
ERROR: components/orders/env/api.yaml: Logging__Enabled is a boolean; quote it ('true')
ERROR: components/orders/env/api.yaml: ConnectionStrings__Default is also set in manifests/20-app.yaml (container api, env); keep one
```

## 5. Draft example component (organisation architecture)

Goal: a copyable component that proves the organisation's architecture end to
end. Component ID `orders` in the demo catalog. Phase 1 builds and verifies it;
this is the target shape.

### What it contains

| Part | Content |
| --- | --- |
| `orders-postgres` Pod, container `db` | PostgreSQL with `POSTGRES_PASSWORD_FILE` and a Secret mount (unchanged contract; the database preflight follows this binding) |
| `orders-app` Pod, container `api` | .NET 8 minimal API: JwtBearer (`Authority` from `PUBLIC_ORIGIN`, audience `orders-api`), GraphQL over HTTP at `/graphql` and WebSocket on the same path, CORS for the public origin |
| `orders-app` Pod, container `web` | nginx serving a TypeScript SPA that signs in in the browser (authorization code + PKCE) and calls `/api/orders/graphql` with the access token |
| `route.conf` | `/orders/` to `web`; `/api/orders/` to `api` with `rewrite` to `/graphql` paths and WebSocket headers |
| API secret | item 72: `orders-api-secret` generated, `api.yaml` registers it with Identity |
| CA trust | item 70's two `subPath` files in container `api` (until a phase 4 profile exists) |

### Files

```yaml
# bundles.yaml (entry; phase 3 may derive most lines)
  orders:
    requires: [platform, identity]
    public_from: platform
    routes: platform
    clients: identity
    apis: identity
```

```yaml
# components/orders/config.defaults.yaml
SECRET_FILES:
  orders-database-password:
  - path: credentials/database
    generate: [password]
  orders-api-secret:
  - path: credentials/api
    generate: [value]
  orders-ingress-trust-chain:
  - path: cert
```

```yaml
# components/orders/env/api.yaml
ASPNETCORE_HTTP_PORTS: 5000
Authentication__Authority: '@@PUBLIC_ORIGIN@@/identity'
Authentication__Audience: orders-api
Cors__Origins__0: '@@PUBLIC_ORIGIN@@'
ConnectionStrings__Default: 'Host=orders-postgres;Port=5432;Database=orders;Username=orders;Password=@@secret:orders-database-password@@'
Authentication__ApiSecret: '@@secret:orders-api-secret@@'
```

```yaml
# components/orders/env/web.yaml
# Read by the image's entrypoint, which writes /config.json for the SPA at start.
OIDC_AUTHORITY: '@@PUBLIC_ORIGIN@@/identity'
OIDC_CLIENT_ID: orders-web
OIDC_REDIRECT_URI: '@@PUBLIC_ORIGIN@@/orders/auth/callback'
API_URL: /api/orders/graphql
```

`API_URL` is relative on purpose: the SPA and the API share one origin, so no
scheme, host or port is rebuilt; the WebSocket URL is derived in the browser
from `location` (`wss://` + `location.host` + `/api/orders/graphql`). This avoids
the missing-port mistakes from the conversion.

```nginx
# components/orders/route.conf
location = /orders { return 308 /orders/; }
location /orders/ {
    set $orders_web orders-app:8080;
    rewrite ^/orders/(.*)$ /$1 break;
    proxy_pass http://$orders_web;
}
location /api/orders/ {
    set $orders_api orders-app:5000;
    rewrite ^/api/orders/(.*)$ /$1 break;      # /api/orders/graphql -> /graphql
    proxy_pass http://$orders_api;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

```yaml
# components/orders/api.yaml (item 72)
index: 1                       # after app3 at 0 in identity-settings
secret: orders-api-secret/value
hash: sha256                   # the demo Identity binds API resources from configuration
```

The demo Identity's `identity-settings` gains `ApiResources__1__Name: orders-api`
and `ApiResources__1__Scopes__0: orders`.

### What the example must prove (phase 1 acceptance)

- Browser: sign-in through Identity, token in the SPA, GraphQL query over HTTP
  and a subscription over WebSocket through the proxy, CSP `connect-src 'self'`
  satisfied.
- Backend: JwtBearer accepts the token (issuer from discovery through the
  public origin, item 70 trust, item 76 name resolution); a token for another
  audience is refused (negative control).
- `validate` shows the wiring lines above; `install` on PROD; restart and reboot.

### Gaps the example exposes in the demo (decide before phase 1)

1. **Public SPA client.** The demo Identity only loads confidential clients
   with a certificate (`LoadClient` in `apps/identity/Program.cs`: certificate
   required, `private_key_jwt`). A browser client needs a public client with
   PKCE, no secret, and the SPA's redirect URI. Options: extend the demo's
   `client.yaml` with `public: true` (demo code only), or let the example skip
   the platform's client registration and configure Duende directly. The
   organisation's own Duende configures its clients itself.
2. **SPA runtime configuration.** An env var on nginx does not change built
   JavaScript. The example image needs an entrypoint script (official nginx
   images run executable `/docker-entrypoint.d/*.sh`) that writes `config.json`
   from the environment. The organisation's images already read these variables
   in Kubernetes; the checklist asks them to confirm how.
3. **Size of the example.** Three containers and a database are heavier than
   app3. The alternative is to extend app3 instead of adding `orders`; the
   SPA-in-browser architecture differs from app3's BFF, so a separate component
   is recommended.

## 6. Conversion checklist (draft, one page)

For moving one service from Kubernetes or docker-compose. Each line names the
trap seen in the conversion.

1. **Copy the example component** and rename `orders` everywhere (directory,
   Pod and resource names start with the component ID).
2. **Public address:** build every URL from `@@PUBLIC_ORIGIN@@` (it includes
   the port). Never compose host, domain and port yourself
   (`DNS_HOST.DNS_DOMAIN` lost `:8443`). Prefer relative URLs in the SPA.
3. **Routes:** one `location` per public path in `route.conf`. The proxy sends
   the full path; if the service listens elsewhere (`/graphql`), add a
   `rewrite`. Find the service's real path first (`MapGraphQL`, `UsePathBase`).
   WebSocket needs the `Upgrade`/`Connection` headers.
4. **Environment:** one `env/<container>.yaml` per container. .NET sections
   use `__`, not `:`. Quote `true`/`false`.
5. **Secrets:** declare in `SECRET_FILES` (with `generate` when the platform may
   create them), refer with `@@secret:<id>@@`. Never write a password as plain
   text in `env/`. Database containers keep `POSTGRES_PASSWORD_FILE`.
6. **Identity:** the backend's `Authority` is `@@PUBLIC_ORIGIN@@/<identity path>`
   without a trailing slash; register redirect URIs with the same origin and
   port; API secrets through `api.yaml` (item 72) with the `hash` your Identity
   expects.
7. **Certificates:** the backend trusts the environment's CA (item 70 mounts).
   After changing `PUBLIC_ORIGIN` in dev, issue a new web certificate (the
   tooling refuses the old one and says how).
8. **Name resolution:** do not map the public name to `127.0.0.1` for
   containers; pods start with `--no-hosts` (item 76). Use `127.0.0.1`, not
   `localhost`, in health checks.
9. **Databases initialised by scripts** run only on an empty volume; a changed
   origin does not update existing rows.
10. **Check:** `./deploy.sh validate` and read the wiring lines, then
    `./dev/dev.sh up`. Test sign-in in a private browser window.

## 7. Decisions (signed off 2026-10-29)

The product owner approved all ten recommendations below unchanged.

| # | Decision | Recommendation |
| --- | --- | --- |
| 1 | File location and target: `env/<container>.yaml`, container name unique in the component | Yes |
| 2 | Values: strings and integers only; `:` in names refused with a hint | Yes |
| 3 | Short `@@secret:<id>@@` only for single-key sources; long form kept; short form also in `SECRET_TEMPLATES` | Yes |
| 4 | Conflicts with hand-written `env`/`envFrom` refused | Yes |
| 5 | One value rule = today's `SECRET_TEMPLATES` rule; byte-exact cases use `secretKeyRef` | Yes |
| 6 | Generated names `<component>-<container>-env` | Yes |
| 7 | Example component `orders` (separate from app3) with the architecture above | Yes |
| 8 | Public SPA client: extend the demo `client.yaml` with `public: true` (demo-only Identity code) | Yes, as part of phase 1's example work |
| 9 | SPA runtime config through an nginx entrypoint script writing `config.json` | Yes |
| 10 | Health checks in examples use `127.0.0.1` | Yes. Item 76's part 2 lab run found `localhost` resolving to `::1` first in every demo container; a service listening on IPv4 only would not answer `localhost` |

## 8. Developer walkthrough (dropped 2026-10-29)

The product owner decided not to run this walkthrough before phase 1. It is
kept as a reference for the human trial in phase 1's verification. Without it,
misreadings of the example are found only after implementation.

Show a developer who has not seen this work only the example files (section 5)
and the checklist (section 6), not this document. Ask, and record the answers
without correcting them:

1. Which container gets `env/api.yaml`, and what happens to
   `ConnectionStrings__Default`?
2. Where does `orders-database-password` come from, and who creates it?
3. You need a new setting `Feature__Export: true` for the API. What do you
   write, and where?
4. The GraphQL call returns 404 through the proxy. Where do you look first?
5. You move to another machine with a different address. What do you change?
6. What does `@@secret:orders-api-secret@@` mean, and why is there also an
   `api.yaml`?

Pass: correct answers to at least five without help, and every wrong guess
recorded as a change to the files, names or messages before phase 1.

## 9. Not in phase 1

`mounts/` (phase 2), gateway-derived routes and public values (phase 3), CA
profiles (phase 4), simpler authoring for item 72 (phase 5), `@@provided:`,
`@@shared:`, database passwords through `env/` (deferred in backlog 77).
