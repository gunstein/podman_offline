# Backlog 77: the simple catalog and `env/` files (decided specification)

Status: **decided by the product owner on 2026-10-29; not implemented.** This
document replaces the earlier proposal text in this file and is the scope of
backlog 77 for now. Everything else in backlog 77 (example application,
`mounts/`, CA profiles, shared secrets, read-through public values) stays
deferred. The review in [COMPONENT-SMALL-VARIANT-REVIEW.md](COMPONENT-SMALL-VARIANT-REVIEW.md)
found problems in the earlier proposal; section 6 lists how each is handled.
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

The organisation's product:

```yaml
product: myproduct
gateway: platform
components:
  platform:
  myidentity-server:
  myapp:
  myapp2:
```

### 2.2 Fields

| Field | Where | Meaning |
| --- | --- | --- |
| `product` | top level | Unchanged. |
| `gateway` | top level, optional | The ID of the component that is the reverse proxy. |
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

- `G` must be a listed component, and G's manifests must mount a
  PersistentVolumeClaim named `G-routes`. It becomes `accepts.routes: G-routes`.
- Every other component gets `public_from: G` and `G` in `requires`. That is,
  in a product with a gateway, **every** other component takes
  `PUBLIC_ORIGIN`, `HTTPS_PORT` and G's `shares` from the gateway, exactly as
  `public_from` does today (copied at `init-config`, compared at install,
  overlaid in dev).
- A component with `route.conf` gets `routes: G`.
- `G` itself gets no `public_from` (no self-dependency).

If `gateway` is not set: no component may have `route.conf`, and no component
gets `public_from`. A worker-only product works as today.

**R2. Clients receiver.** The component whose manifests mount a
PersistentVolumeClaim named `<its id>-clients` receives clients:
`accepts.clients: <id>-clients`. At most one component may do so. Every
component with `client.yaml` gets `clients: <receiver>` and the receiver in
`requires`.

**R3. API secrets receiver.** The component whose manifests reference a
Secret named `<its id>-apis` (in `envFrom.secretRef`,
`env.valueFrom.secretKeyRef` or a Secret volume) receives API secrets:
`accepts.apis: <id>-apis`. At most one component may do so. Every component
with `api.yaml` gets `apis: <receiver>` and the receiver in `requires`.

**R4. Reserved names.** A PersistentVolumeClaim named `<id>-routes` may only be
the gateway's; `<id>-clients` and the Secret `<id>-apis` mean "receiver" by
R2/R3. Using such a name for anything else is refused.

**R5. `requires`.** The derived dependencies are added to any written
`requires`; a written `requires` that repeats a derived one is fine.

### 2.4 Product shapes dropped on purpose (product-owner decision)

| Dropped | Today | Now |
| --- | --- | --- |
| A component in a product with a gateway that does not take the gateway's public settings | `public_from` simply omitted (example: `manual` in the `RENAMED` test fixture) | Not possible; every component takes them. Unused values in its config are harmless. |
| A component with its own `PUBLIC_ORIGIN` in a product with a gateway | Possible without `public_from` | Not possible; set it once on the gateway. |
| `public_from` pointing at a component that is not the gateway | Allowed by `check_entry` | Not possible. |
| Receiver resources with other names (e.g. `accepts.routes: gateway-includes`) | Any name with the component prefix | Only `<id>-routes`, `<id>-clients`, `<id>-apis`. |

The organisation's product and every shipped demo/acceptance product already
fit the new rules (checked in the review, section 1, and against the shipped
`bundles.yaml`). The `RENAMED` platform-test fixture must change: `manual` now
inherits public settings; its test that asserts no `PUBLIC_ORIGIN` is updated
to the new rule.

### 2.5 Refusals (before anything is written)

Each names the file and the next action, never a value:

- `gateway` names an unlisted component, or the gateway does not mount `G-routes`;
- `route.conf` exists but no `gateway` is set;
- two components would receive clients, or API secrets;
- `client.yaml` or `api.yaml` exists but no component receives it;
- a reserved name used by the wrong component (R4);
- a removed field is present;
- a derived dependency cycle.

### 2.6 `validate` shows what it derived

```text
[OK] gateway: platform (routes PVC platform-routes); clients: identity (PVC identity-clients); apis: identity (Secret identity-apis)
[OK] app3: public settings and routes from platform; client.yaml, api.yaml -> identity; requires platform, identity
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
6. Refused as conflicts: a variable also set in the container's hand-written
   `env`; a variable also present in a hand-written `envFrom` source of that
   container (checked when its keys are known, at the latest before YAML is
   published).
7. **Variables the platform checks must stay in the manifest's `env`**, because
   those checks read `env` only: the names in `client.yaml` `environment:`
   (for example `APP_ID`, `BASE_PATH`; `registrations.check_client_identity`)
   and `POSTGRES_PASSWORD_FILE` (`deploy.postgres_binding`). Such a variable in
   `env/` is refused with "keep it in the manifest's env".
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

- Means "the only key of `SECRET_FILES.<id>`". The long form
  `@@secret:<id>/<key>@@` keeps working.
- `<id>` not declared in this component's `SECRET_FILES`: refused, naming file
  and variable.
- At validation (no secret contents read): the declaration must give one key
  (one `generate` name, or one `path` that is a single file).
- At materialization, before anything is published: the **delivered** keys
  must be exactly one. A retained directory with an extra file makes two keys
  (`render.secret_keys` lists existing entries) and is refused with "has N
  keys; use `@@secret:<id>/<key>@@`".
- Accepted in `env/` and in `SECRET_TEMPLATES`.

## 5. Checklist

Add a short "Converting a service" checklist to `docs/COMPONENTS.md`, taken
from [phase 0 design, section 6](COMPONENT-ENV-DESIGN.md#6-conversion-checklist-draft-one-page),
adapted: the catalog lines follow section 2 here; the example to copy is
**app3** (converted to `env/` in this delivery, with `APP_ID`/`BASE_PATH` kept in
its manifest per rule 3.2.7), not the deferred `orders` application.

## 6. The review's findings and how they are handled

| Review finding | Handling |
| --- | --- |
| Inference changes the `RENAMED` fixture's `manual` | Accepted product change (2.4); test updated. |
| Gateway would depend on itself | R1: no `public_from` for the gateway. |
| Resource suffix is not proof of a receiver; arbitrary accepted names | Names reserved (R4); other names dropped (2.4). |
| Worker with its own `PUBLIC_ORIGIN`; `public_from` to a non-gateway | Dropped on purpose (2.4). |
| Scanning placeholders to decide `public_from` is incomplete | Not used: every non-gateway component inherits (R1). |
| Do not infer from isolated installed bundles | Inference only when loading the source catalog; descriptors and `check_descriptor` unchanged. |
| ConfigMap and Secret with the same name | Different names (3.2.4). |
| Client and PostgreSQL checks do not follow `envFrom` | Those variables stay in the manifest (3.2.7). |
| One `generate` name is not always one delivered key | Checked again on delivered keys (section 4). |
| Retained config keeps old `SECRET_TEMPLATES` after conversion | Conversion is for fresh dev/lab installations only; existing lab installations are reset (no customer installation exists). Bump the version of converted `newer-only` components. |
| `acceptance/renamed_product.py` rewrites removed fields, copies no `env/`, renames only long references | Update it: write the new catalog form, copy `env/`, rename short references too. |
| Checklist pointed at the deferred `orders` example | Points at app3 (section 5). |

## 7. Work, tests and verification

| Part | Estimate |
| --- | --- |
| Catalog: new fields, rules R1–R5, refusals, `validate` lines; tests | 2 days |
| `env/` and short reference; tests | 2–3 days |
| Convert demo `bundles.yaml`, app3 to `env/`, fixtures, `renamed_product.py` | 1 day |
| `docs/COMPONENTS.md`, README, review-guide contracts, checklist | half a day |
| Lab: fixed matrix (6 scenarios) and `--whoami` | 1 day, mostly machine time |

Tests must show, for the demo, the acceptance renamed product, platform+help
and a worker-only product: the normalized catalog from the new form equals the
one from today's explicit form (except the documented `manual` change); every
refusal in 2.5 and 3.2 happens before any write, generation or host command,
and no message contains a value. Real Podman/systemd evidence comes only from
the lab run.
