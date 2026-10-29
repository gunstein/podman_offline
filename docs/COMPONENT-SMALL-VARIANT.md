# Backlog 77: the simple catalog and `env/` files (decided specification)

Status: **decided by the product owner on 2026-10-29; not implemented.** This
document replaces the earlier proposal text in this file and is the scope of
backlog 77 for now. Everything else in backlog 77 (example application,
`mounts/`, CA profiles, shared secrets, read-through public values) stays
deferred. The review in [COMPONENT-SMALL-VARIANT-REVIEW.md](COMPONENT-SMALL-VARIANT-REVIEW.md)
found problems in the earlier proposal; section 8 lists how each is handled.
Code references describe `main` at `75594c6`.

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
| `identity` | top level, optional | The ID of the component that receives OIDC clients (`client.yaml`) and API secrets (`api.yaml`). |
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
is unchanged.

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

**R2. Identity.** If `identity: I` is set, `I` must be a listed component and
gets `accepts.clients: I-clients` and `accepts.apis: I-apis`. Every component
with `client.yaml` gets `clients: I` and every component with `api.yaml` gets
`apis: I`, each with `I` in `requires`. A component with neither file has no
link to Identity and does not depend on it.

**R3. Fixed receiver names.** The receiving resources are always
`<gateway>-routes` (PVC), `<identity>-clients` (PVC) and `<identity>-apis`
(Secret). The catalog does **not** read manifests: whether the gateway mounts
`<gateway>-routes`, Identity mounts `<identity>-clients` and reads
`<identity>-apis` is checked by the existing manifest/link checks in
`effective_documents`, as for today's `accepts` names.

**R4. Reserved names.** No component other than the gateway may declare a
resource named `<gateway>-routes`, and none other than Identity
`<identity>-clients` or `<identity>-apis`.

**R5. `requires`.** The derived dependencies are added to any written
`requires`; a written `requires` that repeats a derived one is fine.

### 2.4 Product shapes dropped on purpose (product-owner decision)

| Dropped | Today | Now |
| --- | --- | --- |
| A component in a product with a gateway that does not take the gateway's public settings | `public_from` simply omitted (example: `manual` in the `RENAMED` test fixture) | Not possible; every component takes them. Unused values in its config are harmless. |
| A component with its own `PUBLIC_ORIGIN` in a product with a gateway | Possible without `public_from` | Not possible; set it once on the gateway. |
| `public_from` pointing at a component that is not the gateway | Allowed by `check_entry` | Not possible. |
| Receiver resources with other names (e.g. `accepts.routes: gateway-includes`) | Any name with the component prefix | Only `<gateway>-routes`, `<identity>-clients`, `<identity>-apis`. |
| Clients and API secrets received by two different components | Possible (`accepts.clients` and `accepts.apis` on different components) | One `identity` receives both. |

The organisation's product and every shipped demo/acceptance product already
fit the new rules (checked in the review, section 1, and against the shipped
`bundles.yaml`). The `RENAMED` platform-test fixture must change: `manual` now
inherits public settings; its test that asserts no `PUBLIC_ORIGIN` is updated
to the new rule.

### 2.5 Refusals (before anything is written)

Each names the file and the next action, never a value:

- `gateway` or `identity` names an unlisted component;
- `route.conf` exists but no `gateway` is set;
- `client.yaml` or `api.yaml` exists but no `identity` is set;
- a reserved name used by the wrong component (R4);
- a removed field is present;
- a derived dependency cycle.

### 2.6 `validate` shows what it derived

```text
[OK] gateway: platform (routes PVC platform-routes); identity: identity (clients PVC identity-clients, apis Secret identity-apis)
[OK] app3: public settings and routes from platform; client.yaml, api.yaml -> identity; requires platform, identity
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
   Duplicate keys refused. Empty file refused.
3. Placeholders as today (`@@NAME@@`, `@@secret:<id>/<key>@@`) plus the short
   form (section 4).
4. Lines without a secret reference go into a generated **ConfigMap**
   `<component>-<container>-env`. Lines with one go into a generated **Secret**
   `<component>-<container>-env-secret`. Different names are required: the
   renderer refuses a ConfigMap and a Secret with the same name
   (`render.check_links`).
5. The platform appends `envFrom` entries for the generated resources to the
   container. Generated names that collide with any other resource or
   declaration are refused.
6. **A container with an `env/` file has no hand-written `envFrom`.** Its
   manifest `env` may keep only single named entries, and a variable may not be
   in both places (checked immediately, no secret keys needed). Mixing
   `env/` with hand-written `envFrom` is refused with "move these variables to
   env/<container>.yaml".
7. **Variables the platform checks must stay in the manifest's `env`**, because
   those checks read `env` only: the names in `client.yaml` `environment:`
   (for example `APP_ID`, `BASE_PATH`; `registrations.check_client_identity`)
   and `POSTGRES_PASSWORD_FILE` (`deploy.postgres_binding`). Such a variable in
   `env/` is refused with "keep it in the manifest's env". The same `env` list
   is where a `secretKeyRef` goes for a secret that does not fit rule 8.
8. Value rules are today's `SECRET_TEMPLATES` rules (trailing LF stripped from
   secret sources; no surrounding whitespace, `;`, quotes, control characters
   or `@@` in substituted values). A secret that does not fit must use
   `secretKeyRef` in the manifest.
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

## 4. Short secret reference `@@secret:<id>@@`

- Means "the generated value of `SECRET_FILES.<id>`". Allowed **only** for a
  declaration with exactly one source and exactly one `generate` name; the key
  is that name, known from the declaration without reading files. Supplied
  secrets (no `generate`) and multi-key sources use the long form
  `@@secret:<id>/<key>@@`, which keeps working.
- `<id>` not declared in this component's `SECRET_FILES`, or declared without
  a single `generate` name: refused, naming file and variable.
- At materialization, before anything is published, a safety check confirms
  the delivered keys are exactly that one (`render.secret_keys` also lists
  unexpected files in a retained directory).
- Accepted in `env/` and in `SECRET_TEMPLATES`.

## 5. Assumptions that keep it simple (product-owner decision)

1. **Fresh installations only.** No customer installation exists. The old
   catalog fields are removed outright: no dual format, no transition period,
   no conversion of retained `config.yaml`. Dev and lab installations are set
   up again.
2. **Gateway and Identity are named, not detected.** The catalog reads only
   `bundles.yaml` and checks whether `route.conf`, `client.yaml` and
   `api.yaml` exist. It never parses manifests.
3. **No mixing in a container**: `env/` or hand-written `envFrom`, not both
   (rule 3.2.6).
4. **Short reference only for generated single-key secrets** (section 4).

## 6. How the code must be structured

To keep the Python as easy to follow as today (see backlog 75):

1. **One catalog function** (for example `catalog.derive_entries(document,
   component_files)`) turns the new `bundles.yaml` plus "which of `route.conf`,
   `client.yaml`, `api.yaml` exist per component" into exactly today's
   normalized entry dicts. Pure: no writes, no host commands, no manifest
   parsing; tested on its own. `load_catalog` calls it; everything after is
   unchanged.
2. **One `env/` function** (for example `render.lower_env(component_dir,
   documents, config)`) returns the synthetic ConfigMap documents, the synthetic
   `SECRET_TEMPLATES` entries and the `envFrom` additions. `effective_documents`
   calls it once, before its existing checks. No new modes, flags or second
   validation path.
3. **Delete what the new form makes unnecessary**: parsing and cross-checks of
   the removed catalog fields in source catalogs (keep `check_descriptor` and
   its defaults for compiled descriptors and installed metadata unchanged).
4. **Comments explain why** (for example why checked variables stay in `env`),
   matching the existing style; no generic framework.

## 7. Checklist

Add a short "Converting a service" checklist to `docs/COMPONENTS.md`, taken
from [phase 0 design, section 6](COMPONENT-ENV-DESIGN.md#6-conversion-checklist-draft-one-page),
adapted: the catalog follows section 2 here; the example to copy is
**app3** (converted to `env/` in this delivery, with `APP_ID`/`BASE_PATH` kept in
its manifest per rule 3.2.7), not the deferred `orders` application.

## 8. The review's findings and how they are handled

| Review finding | Handling |
| --- | --- |
| Inference changes the `RENAMED` fixture's `manual` | Accepted product change (2.4); test updated. |
| Gateway would depend on itself | R1: no `public_from` for the gateway. |
| Resource suffix is not proof of a receiver; arbitrary accepted names | Receivers are named (`gateway`, `identity`), not detected; fixed resource names (R3/R4). |
| Worker with its own `PUBLIC_ORIGIN`; `public_from` to a non-gateway | Dropped on purpose (2.4). |
| Scanning placeholders to decide `public_from` is incomplete | Not used: every non-gateway component inherits (R1). |
| Do not infer from isolated installed bundles | Inference only when loading the source catalog; descriptors and `check_descriptor` unchanged. |
| ConfigMap and Secret with the same name | Different names (3.2.4). |
| Client and PostgreSQL checks do not follow `envFrom` | Those variables stay in the manifest (3.2.7). |
| One `generate` name is not always one delivered key | Short form only for single-`generate` secrets, plus a delivered-key safety check (section 4). |
| Retained config keeps old `SECRET_TEMPLATES` after conversion | Conversion is for fresh dev/lab installations only; existing lab installations are reset (no customer installation exists). Bump the version of converted `newer-only` components. |
| `acceptance/renamed_product.py` rewrites removed fields, copies no `env/`, renames only long references | Update it: write the new catalog form, copy `env/`, rename short references too. |
| Checklist pointed at the deferred `orders` example | Points at app3 (section 5). |

## 9. Work, tests and verification

| Part | Estimate |
| --- | --- |
| Catalog: `gateway`/`identity`, rules R1–R5, refusals, `validate` lines; tests | 1.5 days |
| `env/` and short reference; tests | 2 days |
| Convert demo `bundles.yaml`, app3 to `env/`, fixtures, `renamed_product.py` | 1 day |
| `docs/COMPONENTS.md`, README, review-guide contracts, checklist | half a day |
| Lab: fixed matrix (6 scenarios) and `--whoami` | 1 day, mostly machine time |

Total about one week. Tests must show, for the demo, the acceptance renamed
product, platform+help, a product with a component that does not use Identity,
and a worker-only product: the normalized catalog from the new form equals the
one from today's explicit form (except the documented `manual` change); every
refusal in 2.5 and 3.2 happens before any write, generation or host command,
and no message contains a value. Real Podman/systemd evidence comes only from
the lab run.
