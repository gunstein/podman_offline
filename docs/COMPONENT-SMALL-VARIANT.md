# Backlog 77: the simple catalog and `env/` files (decided specification)

Status: **decided by the product owner on 2026-10-29; not implemented.** This
document replaces the earlier proposal text in this file and is the scope of
backlog 77 for now. Everything else in backlog 77 (example application,
`mounts/`, CA profiles, shared secrets, read-through public values) stays
deferred. The review in [COMPONENT-SMALL-VARIANT-REVIEW.md](COMPONENT-SMALL-VARIANT-REVIEW.md)
found problems in the earlier proposal; section 8 lists how each is handled.
The [check of this specification](COMPONENT-SMALL-VARIANT-CHECK.md) found two
blocking and five minor points; they are corrected here (section 8).
**Update 2026-10-30:** API secrets are written as `@@api-secret:<component>@@`
on both sides instead of `api.yaml` (section 5), and a short
`<id>: generate` declaration is added (section 4). The
[second check](COMPONENT-SMALL-VARIANT-CHECK.md#2026-10-30-independent-check-api-placeholders-and-short-declarations)
(baseline `65af892`) found two blocking (B3, B4) and five minor points
(M6–M10); they are corrected here (section 9). Code references describe `main`
at `75594c6` unless a section names another revision.

## 1. Why, in one paragraph

Everything works today. The problem is that writing a component is too hard:
`bundles.yaml` repeats the same facts on every component (`requires`,
`public_from`, `routes`, `clients`, `apis`, `accepts`), and a container's
environment is spread over a hand-written ConfigMap, `SECRET_TEMPLATES` and
`envFrom` lines. The product owner requires the result to be obvious to a
developer who does not read documentation. **Simplicity is the requirement;
where the earlier designs kept rare product shapes working at the cost of
simplicity, this specification drops those shapes on purpose** (section 2.4).

## 2. The catalog (`bundles.yaml`)

### 2.1 What it looks like

```yaml
product: myproduct
gateway: platform
identity: identity
components:
  platform:
    upgrade: newer-only
  identity:
    upgrade: newer-only
  app1:
  app2:
  app3:
  help:
```

The organisation's product, including a later component `reports` that does
not use Identity:

```yaml
product: myproduct
gateway: platform
identity: myidentity-server
components:
  platform:
  myidentity-server:
  myapp:
  myapp2:
  reports:
```

### 2.2 Fields

| Field | Where | Meaning |
| --- | --- | --- |
| `product` | top level | Unchanged. |
| `gateway` | top level, optional | The ID of the component that is the reverse proxy. |
| `identity` | top level, optional | The ID of the component that receives OIDC clients (`client.yaml`) and API secrets (`@@api-secret:...@@`, section 5). |
| `components` | top level | The list of components. An empty entry is fine. |
| `upgrade` | per component, optional | Unchanged (`always` or `newer-only`). |
| `shares` | on the gateway only, optional | Unchanged meaning: extra config names every other component takes from the gateway. |
| `requires` | per component, optional | Only for dependencies the rules below do not already create. |

**Removed:** `public_from`, `routes`, `clients`, `apis`, `accepts`. Writing any
of them is an error whose message explains the rule that replaced it. There is
only one way to write a catalog. (Allowed before the first customer
installation; see the review guide.)

### 2.3 Rules the platform applies

Applied once, when the **source** catalog is loaded (`catalog.load_catalog`).
The result is the same normalized entry dict the code uses today
(`requires`, `public_from`, `routes`, `clients`, `apis`, `accepts`, `shares`,
`upgrade`), so everything after loading, including bundle descriptors,
installed state, upgrades, `newer-only`, registrations, restarts and retries,
is unchanged. **One exception:** Identity's descriptor gains the API-secret
mapping of section 5 (5.2).

**R1. The gateway.** If `gateway: G` is set:

- `G` must be a listed component. It gets `accepts.routes: G-routes`; that its
  manifests mount that PVC is checked later by the existing link checks (R3).
- Every other component gets `public_from: G` and `G` in `requires`. That is,
  in a product with a gateway, **every** other component takes
  `PUBLIC_ORIGIN`, `HTTPS_PORT` and G's `shares` from the gateway, exactly as
  `public_from` does today (copied at `init-config`, compared at install,
  overlaid in dev).
- A component with `route.conf` gets `routes: G`.
- `G` itself gets no `public_from` (no self-dependency).

If `gateway` is not set: no component may have `route.conf`, and no component
gets `public_from`. A worker-only product works as today.

**R2. Identity.** If `identity: I` is set, `I` must be a listed component. It
gets `accepts.clients: I-clients` **only if at least one component has
`client.yaml`**, and `accepts.apis: I-apis` **only if at least one component
is an API** (its `env/` files use `@@api-secret:<its own id>@@`, section 5), so
an Identity that uses neither registration needs no unused volume or Secret.
Every component with `client.yaml` gets `clients: I` and every API gets
`apis: I`, each with `I` in `requires`. A component with neither has no link to
Identity and does not depend on it. To decide this, the catalog function looks
at file existence and at the `env/` files' `@@api-secret:` placeholders; it
still never parses manifests.

**R3. Fixed receiver names.** The receiving resources are always
`<gateway>-routes` (PVC), `<identity>-clients` (PVC) and `<identity>-apis`
(Secret; internal, injected by the platform, never written by anyone, see
section 5). The catalog does **not** read manifests. Rendering validation
(`effective_documents`) checks that the receiver uses them: the existing link
checks refuse an accepted resource no manifest references, and a **new focused
check** follows each receiving PVC from Pod `spec.volumes` to a regular or init
container `volumeMounts` entry (after placeholder substitution), because a
volume that is declared but not mounted passes today's checks.

**R4. Reserved names.** No component other than the gateway may declare a
resource named `<gateway>-routes`, and none other than Identity
`<identity>-clients` or `<identity>-apis`.

**R5. `requires`.** Written `requires` keep their order; missing derived
dependencies (gateway, then Identity) are appended; repeats are removed.
Catalog order of unrelated components is unchanged. "No link to Identity" in R2
means no *derived* dependency; a written `requires` still applies.

**R6. `shares`** is allowed only on the gateway's entry.

### 2.4 Product shapes dropped on purpose (product-owner decision)

| Dropped | Today | Now |
| --- | --- | --- |
| A component in a product with a gateway that does not take the gateway's public settings | `public_from` simply omitted (example: `manual` in the `RENAMED` test fixture) | Not possible; every component takes them. Unused values in its config are harmless. |
| A component with its own `PUBLIC_ORIGIN` in a product with a gateway | Possible without `public_from` | Not possible; set it once on the gateway. |
| `public_from` pointing at a component that is not the gateway | Allowed by `check_entry` | Not possible. |
| Receiver resources with other names (e.g. `accepts.routes: gateway-includes`) | Any name with the component prefix | Only `<gateway>-routes`, `<identity>-clients`, `<identity>-apis`. |
| Clients and API secrets received by two different components | Possible (`accepts.clients` and `accepts.apis` on different components) | One `identity` receives both. |
| `api.yaml` with `index`, `secret`, `hash` | Item 72's declaration | Replaced by `@@api-secret:<component>@@` on both sides (section 5). |
| Platform-side hashing (`hash: sha256`) | Item 72 could hash for Identity | Removed: both sides get the same value; Identity hashes it itself. The demo Identity is changed accordingly. |

The organisation's product and every shipped demo/acceptance product already
fit the new rules (checked in the review, section 1, and against the shipped
`bundles.yaml`). The `RENAMED` platform-test fixture must change: `manual` now
inherits public settings; its test that asserts no `PUBLIC_ORIGIN` is updated
to the new rule.

### 2.5 Refusals (before anything is written)

Each names the file and the next action, never a value:

- `gateway` or `identity` names an unlisted component;
- `route.conf` exists but no `gateway` is set;
- `client.yaml` exists, or an `@@api-secret:` placeholder is used, but no
  `identity` is set;
- an `api.yaml` file exists (replaced by `@@api-secret:`; the message says how);
- `client.yaml` exists but no `gateway` is set, or on the gateway itself (a
  client needs the gateway's public origin for its redirect URI; today's
  normalized check "clients needs public_from" stays);
- `shares` on a component other than the gateway;
- a reserved name used by the wrong component (R4);
- a removed field is present;
- a derived dependency cycle.

### 2.6 `validate` shows what it derived

```text
[OK] gateway: platform (routes PVC platform-routes); identity: identity (clients PVC identity-clients)
[OK] app3: public settings and routes from platform; client.yaml -> identity; API secret -> identity; requires platform, identity
[OK] reports: public settings from platform; requires platform
```

## 3. Environment files: `env/<container>.yaml`

From the signed-off [phase 0 design, section 2](COMPONENT-ENV-DESIGN.md#2-envcontaineryaml),
with the review's corrections.

### 3.1 What it looks like

```yaml
# components/myapp/env/backend.yaml
ASPNETCORE_HTTP_PORTS: 5000
Authentication__Authority: '@@PUBLIC_ORIGIN@@/myidentity-server'
Cors__default__origin__0: '@@PUBLIC_ORIGIN@@'
ConnectionStrings__Default: 'Host=myapp-postgres;Database=myapp;Username=myapp;Password=@@secret:myapp-database-password@@'
```

### 3.2 Rules

1. `<container>` is the name of one container (regular or init) in the
   component's Pods. It must exist and be unique in the component.
2. The file is a flat map. Keys: letters, digits, `-`, `.`, `_`, not starting
   with a digit; `:` is refused with "use `__`". Values: strings or integers
   only; booleans, floats, null, lists and maps are refused with "quote it".
   Duplicate keys refused, also when they differ only in case (5.7). Empty
   file refused.
3. Placeholders: `@@NAME@@` (a config value, as today),
   `@@secret:<id>/<key>@@` and its short form `@@secret:<id>@@` (section 4),
   and `@@api-secret:<component>@@` (section 5).
4. Lines without a secret reference go into a generated **ConfigMap**
   `<component>-<container>-env`. Lines with one go into a generated **Secret**
   `<component>-<container>-env-secret`. Different names are required: the
   renderer refuses a ConfigMap and a Secret with the same name
   (`render.check_links`).
5. The platform appends `envFrom` entries for the generated resources to the
   container. Generated names that collide with any other resource or
   declaration are refused. The synthetic `SECRET_TEMPLATES` entries live only
   in the **transient effective config** that validation and materialization
   both use (`effective_documents` and `materialize` read recipes from that
   config); they are never written to the operator's `config.yaml`. Lowering
   must be safe to run more than once on the same input.
6. **A container with an `env/` file has no hand-written `envFrom`.** Its
   manifest `env` may keep only single named entries, and a variable may not be
   in both places (checked immediately, no secret keys needed). Mixing is
   refused with "use env/<container>.yaml or keep this container's hand-written
   envFrom, not both". Identity no longer needs a hand-written `envFrom` for
   API secrets: the platform injects them (section 5).
7. **Variables the platform checks must stay in the manifest's `env`**, because
   those checks read `env` only: the names in `client.yaml` `environment:`
   (for example `APP_ID`, `BASE_PATH`; `registrations.check_client_identity`)
   and **every `POSTGRES_PASSWORD*` variable** (`POSTGRES_PASSWORD`,
   `POSTGRES_PASSWORD_FILE`; `deploy.postgres_binding` inspects all of them).
   Such a variable in `env/` is refused with "keep it in the manifest's env". The same `env` list
   is where a `secretKeyRef` goes for a secret that does not fit rule 8.
8. Value rules are today's `SECRET_TEMPLATES` rules (trailing LF stripped from
   secret sources; no surrounding whitespace, `;`, quotes, control characters
   or `@@` in substituted values), applied to **both** public and secret lines
   of `env/` files (`templates.check_text`; today's `config_text` for ordinary
   ConfigMaps does not check substituted public values, and stays as it is). A
   secret that does not fit must use `secretKeyRef` in the manifest.
9. `bundle.py` ships `env/` (add it to the copied component entries); it is
   then in `checksums.sha256` and signed.
10. Implementation: lower `env/` into a synthetic ConfigMap document, a
    synthetic `SECRET_TEMPLATES` entry and `envFrom` entries **inside
    `render.effective_documents`, before** the existing checks, so all of
    them run unchanged.

`validate` prints one line per file, without values:

```text
[OK] myapp/backend: env/backend.yaml -> 3 settings (ConfigMap myapp-backend-env), 1 secret (Secret myapp-backend-env-secret: myapp-database-password)
```

## 4. Short secret declaration and reference

A secret generated by the platform can be declared in one line:

```yaml
# config.defaults.yaml
SECRET_FILES:
  myapp-database-password: generate
```

This means one generated value (32 letters and digits, as today), stored at
`credentials/<id>/value` in the component's config folder, Secret key `value`.
A container that mounts the Secret sees the file `value` (for example
`POSTGRES_PASSWORD_FILE: /run/secrets/db/value`). The long form
(`- path: ...` with `generate: [<name>]`, or a supplied file without
`generate`) stays for several files, chosen file names and supplied secrets.
Examples and the checklist show the database case complete, so nobody has to
guess the `value` file name.

The short reference:

- `@@secret:<id>@@` means "the generated value of `SECRET_FILES.<id>`". Allowed
  **only** for `<id>: generate` or a declaration with exactly one source and
  exactly one `generate` name; the key is known from the declaration without
  reading files. Supplied
  secrets (no `generate`) and multi-key sources use the long form
  `@@secret:<id>/<key>@@`, which keeps working.
- `<id>` not declared in this component's `SECRET_FILES`, or declared without
  a single `generate` name: refused, naming file and variable.
- The short form is expanded to the long form before the existing recipe
  checks run. At materialization, before anything is published, a safety check
  confirms the delivered keys are exactly that one (`render.secret_keys` also
  lists unexpected files in a retained directory).
- Accepted in `env/` and in `SECRET_TEMPLATES`.

Where the short declaration is expanded (check M7): once, in the shared
effective-config path, to `[{path: credentials/<id>, generate: [value]}]`
before any consumer (validation, standalone config, generation, Secret mounts,
`env/` lowering). A short and a long declaration with the same ID in one file
is already a duplicate key and stays refused. Config layers keep today's
behavior: a layer's `SECRET_FILES` replaces the whole map, nothing is merged.

## 5. API secrets: `@@api-secret:<component>@@`

An API backend and Identity must hold the same secret. Both sides write the
same placeholder; that is the whole declaration:

```yaml
# components/myidentity-server/env/identity.yaml
ApiResources__0__Name: myapp
ApiResources__0__Scopes__0: myapp
ApiResources__0__ApiSecrets__0__Value: '@@api-secret:myapp@@'
ApiResources__1__Name: myapp2
ApiResources__1__Scopes__0: myapp2
ApiResources__1__ApiSecrets__0__Value: '@@api-secret:myapp2@@'

# components/myapp/env/backend.yaml
Authentication__ApiSecret: '@@api-secret:myapp@@'
```

Rules:

1. A component is an **API** when one of its own `env/` files uses
   `@@api-secret:<its own id>@@`. It may not use another component's API secret.
2. Identity's `env/` files may use `@@api-secret:<component>@@` for any API
   component, on a line named exactly `ApiResources__<n>__ApiSecrets__0__Value`
   (Identity is always Duende; section 6). `<n>` is where Identity receives the
   value; the index lives only there, next to the name and scopes. The API
   resource name is free; the placeholder is the link. **Exactly one line per
   API**, each `<n>` used by one API only, all in one Identity container.
   Identity may not reference itself.
3. **One value, unchanged on both sides.** The platform generates it once (32
   letters and digits) when the API is first installed or prepared and keeps it
   byte for byte at `credentials/api-secret/value` in the API component's config
   folder. Internally this is a generated `SECRET_FILES` source with the
   reserved ID `<component>-api-secret`; an explicit declaration with that ID
   or that path is refused (check M6). To reuse an existing value, the operator
   manual's procedure writes it there before the first install (service
   account, mode 0600, no trailing newline, not through shell history). There
   is no hash setting: Identity hashes the value itself when it loads it.
4. **Under the hood this is item 72's mechanism**, with the declaration moved:
   the API's install registers the value (private registration, pending state,
   restart of the API first, then Identity, removal on uninstall, `newer-only`
   retention); the Identity side is rebuilt as one platform-rendered Secret
   `<identity>-apis` with the key `ApiResources__<n>__ApiSecrets__0__Value`
   per installed API, exactly the key `registrations.owner_secrets` builds
   today. Identity's `@@api-secret` lines are taken out before ordinary `env/`
   lowering and never become `SECRET_TEMPLATES` recipes; only `<identity>-apis`
   supplies them. The platform injects `<identity>-apis` into that Identity
   container; nobody writes its name, and no component, Identity included, may
   declare it. `api.yaml`, `index`, `secret` and `hash` disappear.
5. **Where the mapping lives (check B3).** When Identity is built, the mapping
   `{API component: <n>}` is read from its `env/` files and stored as one
   validated field of Identity's descriptor (`check_descriptor` accepts it for
   Identity only), carried into the bundle and Identity's installed metadata.
   The mapping of the **installed, actually rendered** Identity is the only
   authority. The registration keeps only the API's value, keyed by API ID; the
   registration's `index` file is dropped, so there are never two mappings.
   - API install: its ID must be in the installed mapping, otherwise refused
     before anything is written.
   - Identity upgrade that is rendered: refused before anything is written if
     the new mapping drops an installed API ("uninstall myapp first, or keep
     its line"). Moving an API to another `<n>` is fine: `<identity>-apis` is
     rebuilt from the retained values by API ID.
   - Identity skipped by `newer-only`: its installed mapping stays; an incoming
     Identity bundle with a different mapping is refused ("raise Identity's
     version"), so the mapping never changes under a running Identity.
   - Pending operations: the existing pending-operation gate also covers the
     mapping, so a retry sees the mapping it started with.
6. **Lines for APIs that are not installed yet are left out** of Identity's
   environment until the API is installed (Identity is installed first). The
   API resource's name and scopes stay; the missing secret makes it inactive.
7. **Keys are compared the way .NET reads them** (check B4): in every
   container, `env/` keys and manifest `env` names must be unique ignoring
   case, so `ApiResources__0__...` and `apiresources__0__...` cannot both
   exist.
8. Refused, naming files and the next action, before anything is written or
   generated (declaration checks; source `validate`, `prepare` and isolated
   install share them):
   - an API uses `@@api-secret:` but Identity's `env/` files have no line for it
     ("add `ApiResources__<n>__ApiSecrets__0__Value: '@@api-secret:myapp@@'` to
     components/myidentity-server/env/<container>.yaml");
   - Identity references `@@api-secret:X@@` but X is not a listed component, or
     X never uses its own `@@api-secret:X@@` (checked in the source catalog);
   - at an isolated install: the API is not in the installed Identity's
     compiled mapping ("install the Identity release that lists myapp first");
   - `@@api-secret:` lines in more than one Identity container, or in a component
     that is neither the API itself nor Identity;
   - in Identity: a line not named `ApiResources__<n>__ApiSecrets__0__Value`,
     two lines for one API, one `<n>` for two APIs, or a reference to Identity
     itself;
   - two keys in one container that differ only in case;
   - an Identity release that drops an installed API, or a differing mapping
     on a skipped `newer-only` Identity (5.5);
   - an `@@api-secret:` placeholder used outside a whole env value is allowed
     only in the API's own files (composition like any secret); in Identity's
     files it must be the whole value.
9. `validate` shows the link and the rules a reader cannot see in the files,
   without values:

   ```text
   [OK] api-secret myapp: generated at myapp credentials/api-secret/value; myapp/backend Authentication__ApiSecret; myidentity-server/identity ApiResources__0__ApiSecrets__0__Value; install myidentity-server first
   ```

Requirements on the Identity code (not platform rules; in the checklist and
shown in the demo Identity, check M8):

- Hash each API secret exactly once while building the in-memory resource:
  Base64(SHA-256(UTF-8(raw value))), as Duende expects. Never write the hash
  back anywhere.
- An API resource without a secret is left out of the active resources (the
  API is not installed yet). A present but empty secret stops startup with a
  message that does not print it.

Requirement on the API code: its health check must not depend on a
successful introspection with Identity, because the API restarts before
Identity during rotation.

Limits: one API secret per component, one secret per API resource
(`ApiSecrets__0`); rotation needs a render of the API (a skipped `newer-only`
version keeps its value) and restarts the API and then Identity (short
interruption, no overlap of old and new secrets).

## 6. Assumptions that keep it simple (product-owner decision)

1. **Fresh installations only.** No customer installation exists. The old
   catalog fields are removed outright: no dual format, no transition period,
   no conversion of retained `config.yaml`. Dev and lab installations are set
   up again.
2. **Gateway and Identity are named, not detected.** The catalog reads
   `bundles.yaml`, checks whether `route.conf` and `client.yaml` exist, and looks
   for `@@api-secret:` placeholders in `env/` files. It never parses manifests.
3. **No mixing in a container**: `env/` or hand-written `envFrom`, not both
   (rule 3.2.6).
4. **Short reference only for generated single-key secrets** (section 4).
5. **Identity hashes API secrets itself** and tolerates a missing one
   (section 5).
6. **Identity is Duende.** API secret lines therefore have Duende's fixed
   name `ApiResources__<n>__ApiSecrets__0__Value`; that is checked instead of
   trusting arbitrary variable names.

## 7. How the code must be structured

To keep the Python as easy to follow as today (see backlog 75):

1. **One catalog function** (for example `catalog.derive_entries(document,
   component_files)`) turns the new `bundles.yaml` plus "which of `route.conf`,
   `client.yaml` exist and which `@@api-secret:` placeholders the `env/` files
   use, per component" into exactly today's
   normalized entry dicts. Pure: no writes, no host commands, no manifest
   parsing; tested on its own. `load_catalog` calls it; everything after is
   unchanged. `catalog_document` (used by `product_name`) accepts the new
   top-level keys `gateway` and `identity`. Normalized `check_entry`,
   `check_owners`, cycle checks and `source_descriptors` stay as they are.
2. **One `env/` function** (for example `render.lower_env(component_dir,
   documents, config)`) returns the synthetic ConfigMap documents, the synthetic
   `SECRET_TEMPLATES` entries and the `envFrom` additions. `effective_documents`
   calls it once, before its existing checks. No new modes, flags or second
   validation path.
3. **API secrets reuse item 72's registration code**: replace reading
   `api.yaml` (index, secret, hash) with the API's own generated value and
   the installed Identity's mapping `{API: <n>}` (5.5), looked up when the owner
   Secret is assembled; the owner-Secret rebuild, pending state and restart
   order stay. No second registration mechanism, no synthetic `api.yaml`, no
   index copies.
4. **Delete what the new form makes unnecessary**: parsing and cross-checks of
   the removed catalog fields in source catalogs, `api.yaml`, the registration
   `index` file and hashing. `check_descriptor` stays, with the one added
   Identity mapping field (5.5).
5. **Comments explain why** (for example why checked variables stay in `env`),
   matching the existing style; no generic framework.

## 8. Checklist

Add a short "Converting a service" checklist to `docs/COMPONENTS.md`, taken
from [phase 0 design, section 6](COMPONENT-ENV-DESIGN.md#6-conversion-checklist-draft-one-page),
adapted: the catalog follows section 2 here; the example to copy is
**app3** (converted to `env/` in this delivery, with `APP_ID`/`BASE_PATH` kept in
its manifest per rule 3.2.7), not the deferred `orders` application. Add:

- API secrets: `@@api-secret:<component>@@` on both sides, the Identity line
  named `ApiResources__<n>__ApiSecrets__0__Value`; the Identity and API code
  requirements of section 5. A complete, minimal Identity/API example with
  short comments and the actual Identity loading code.
- Init containers that need the database: a first init container that waits
  with `pg_isready` (same image as the database; explicit `-h` and `-p`, a
  per-attempt timeout, a finite number of retries and a nonzero exit when the
  database never answers; one folded `command` line), the Pod annotation
  `io.podman.annotations.init.container.type: always`, and idempotent init
  steps that fail safely. A lower-numbered database manifest only orders
  submission, not readiness, and `pg_isready` does not prove that credentials
  or migrations work. Show the complete YAML (check M10).

## 9. The review's findings and how they are handled

| Review finding | Handling |
| --- | --- |
| Inference changes the `RENAMED` fixture's `manual` | Accepted product change (2.4); test updated. |
| Check B1: only `POSTGRES_PASSWORD_FILE` was kept out of `env/` | Every `POSTGRES_PASSWORD*` variable stays in the manifest (3.2.7). |
| Check B2: `RENAMED`'s `login-service` also gains `accepts.apis` | Resolved by R2's condition: no `RENAMED` component uses `@@api-secret:`, so no `accepts.apis` is derived and the fixture's manifests stay unchanged. Only `manual`'s `public_from` changes. |
| Check M1: `client.yaml` without a gateway | Refused with a file-specific message (2.5). |
| Check M2: a declared but unmounted receiving PVC passes | New focused mount check (R3). |
| Check M3: where synthetic recipes live | Transient effective config only (3.2.5). |
| Check M4: private-content checks cannot run before generation | Declaration checks run before any write; private-content checks before any YAML/registration is published or a service changes (section 10). |
| Check M5: "move to env/" is not always possible | Message changed. Identity's API-secret `envFrom` is now injected by the platform (3.2.6, 5.4). |
| Gateway would depend on itself | R1: no `public_from` for the gateway. |
| Resource suffix is not proof of a receiver; arbitrary accepted names | Receivers are named (`gateway`, `identity`), not detected; fixed resource names (R3/R4). |
| Worker with its own `PUBLIC_ORIGIN`; `public_from` to a non-gateway | Dropped on purpose (2.4). |
| Scanning placeholders to decide `public_from` is incomplete | Not used: every non-gateway component inherits (R1). |
| Do not infer from isolated installed bundles | Inference only when loading the source catalog; descriptors and `check_descriptor` unchanged except Identity's mapping field (5.5). |
| ConfigMap and Secret with the same name | Different names (3.2.4). |
| Client and PostgreSQL checks do not follow `envFrom` | Those variables stay in the manifest (3.2.7). |
| One `generate` name is not always one delivered key | Short form only for single-`generate` secrets, plus a delivered-key safety check (section 4). |
| Retained config keeps old `SECRET_TEMPLATES` after conversion | Conversion is for fresh dev/lab installations only; existing lab installations are reset (no customer installation exists). Bump the version of converted `newer-only` components. |
| `acceptance/renamed_product.py` rewrites removed fields, copies no `env/`, renames only long references | Update it: write the new catalog form, copy `env/`, rename short references too. |
| Checklist pointed at the deferred `orders` example | Points at app3 (section 8). |
| (Product owner, 2026-10-30) `api.yaml` and the `-apis` name were hidden rules | `@@api-secret:` on both sides; `<identity>-apis` injected by the platform (section 5). Checked in the second check. |
| Check B3: the compiled mapping's storage, upgrade and `newer-only` | One descriptor field on Identity; the installed rendered mapping is the only authority; registration `index` dropped; refusals for a dropped API and a differing skipped mapping (5.5). |
| Check B4: mapping cardinality and case-insensitive keys | Fixed Duende key name, one line per API, unique `<n>`, no self-reference (5.2); keys unique ignoring case (5.7); Identity's lines bypass ordinary recipes (5.4). |
| Check M6: implicit API source collides with user declarations | Reserved ID `<component>-api-secret` and path refused in explicit declarations (5.3). |
| Check M7: where the short declaration is expanded; config layers | Once in the shared effective-config path; whole-map layer replacement kept (section 4). |
| Check M8: Identity loading contract | Exact hash, inactive when absent, refuse empty without printing; tests listed in section 10 (section 5). |
| Check M9: stale text and test list | Section 9 rows and section 10's test list corrected. |
| Check M10: readiness example | Bounded `pg_isready` wait with nonzero exit and its limits (section 8). |
| Check: operator preload and API health checks | Preload through the operator manual's procedure (5.3); API health check without introspection (section 5). |

## 10. Work, tests and verification

| Part | Estimate |
| --- | --- |
| Catalog: `gateway`/`identity`, rules R1–R6, refusals, receiver mount check, `validate` lines; tests | 1.5–2 days |
| `env/`, short declaration and reference; tests | 2 days |
| API secrets: `@@api-secret:`, Identity descriptor mapping and its upgrade rules, injection into Identity, item 72 registration rewired, demo Identity hashes itself; tests | 2.5–3 days |
| Convert demo `bundles.yaml`, app3 to `env/`, fixtures, `renamed_product.py` | 1 day |
| `docs/COMPONENTS.md`, README, review-guide contracts, checklist | half a day |
| Lab: fixed matrix (6 scenarios) and `--whoami` (covers API secret, rotation, uninstall) | 1 day, mostly machine time |

Total about 1.5–2 weeks of implementation, **2–3 weeks including review and
lab fixes** (second check: 8–8.5 working days; the descriptor/installed-state
rules and their failure tests are the uncertainty, not parsing). Tests must show, for the demo, the acceptance renamed
product, platform+help, a product with a component that does not use Identity,
and a worker-only product: the normalized catalog from the new form equals the
one from today's explicit form (except the documented `RENAMED` `manual` change);
every **declaration** refusal in 2.5, 3.2, section 4 and 5.8 happens before any
write, generation or host command, including short-declaration errors, API
mapping and case collisions, an API absent from the installed Identity
mapping (isolated bundle) and a dropped or differing mapping on Identity
upgrade; the demo Identity is tested with zero, one and two APIs, a gap in
`<n>`, removal, restart and successful and failed introspection; focused
lifecycle cases cover a moved `<n>`, a skipped `newer-only` Identity, two APIs
and API-before-Identity refusal (the fixed matrix does not); checks that need private substituted bytes run
before any rendered YAML or registration is published or a service changes,
and `validate` never reads credential contents; no message contains a value.
Real Podman/systemd evidence comes only from the lab run.
