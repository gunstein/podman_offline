# Backlog 77: the small variant (proposal for review)

Status: **proposal, 2026-10-29; not decided, not implemented.** Written after
the product owner found the full backlog 77 plan
([phases 1–5](../BACKLOG.md#77-make-a-component-intuitive-to-write-env-files-mounts-and-shared-secrets),
[phase 0 design](COMPONENT-ENV-DESIGN.md)) far too large for what is a
convenience, not a missing capability: everything the organisation needs works
today. Code references describe `main` at `b068151`.

## Goal

Make the two files a developer edits most, `bundles.yaml` and a container's
environment, obvious to write, without changing how installation, secrets,
registrations, restarts or retries work underneath. Nothing else from
backlog 77 is in scope.

## 1. `bundles.yaml` becomes a list

Today (demo):

```yaml
product: myproduct
components:
  platform:
    upgrade: newer-only
    accepts:
      routes: platform-routes
  identity:
    requires: [platform]
    upgrade: newer-only
    public_from: platform
    routes: platform
    accepts:
      clients: identity-clients
      apis: identity-apis
  app1:
    requires: [platform, identity]
    public_from: platform
    routes: platform
    clients: identity
  # app2, app3, help similar
```

Proposed:

```yaml
product: myproduct
components:
  platform: {upgrade: newer-only}
  identity: {upgrade: newer-only}
  app1:
  app2:
  app3:
  help:
```

Derived instead of written (the rules already hold today: at most one
component may accept each role):

| Today written | Derived from |
| --- | --- |
| `accepts: {routes: <id>-routes}` | the component whose manifests mount the PVC `<its id>-routes` (platform mounts `platform-routes`) |
| `accepts: {clients: <id>-clients}` | the component whose manifests mount the PVC `<its id>-clients` |
| `accepts: {apis: <id>-apis}` | the component whose manifests read the Secret `<its id>-apis` |
| `routes: <owner>` | the component has `route.conf` |
| `clients: <owner>` | the component has `client.yaml` |
| `apis: <owner>` | the component has `api.yaml` |
| `public_from: <owner>` | the component has `route.conf` or `client.yaml`, or its config/manifests use `PUBLIC_ORIGIN`, `HTTPS_PORT`, `PUBLIC_HOSTNAME` or a name the routes receiver lists in `shares`; the owner is the routes receiver |
| `requires` for those owners | the edges above |

Still written when needed: `upgrade`, `shares` (on the routes receiver), and
`requires` for dependencies not implied by files.

Refused before anything is written, with the file and the next action:
two components that would receive the same role; a `route.conf`, `client.yaml`
or `api.yaml` with no receiver; a component needing public settings with no
routes receiver; a derived cycle; any of the removed fields still present (one
way only; allowed before the first customer installation).

`validate` prints what it derived:

```text
[OK] receivers: routes -> platform (PVC platform-routes), clients -> identity (PVC identity-clients), apis -> identity (Secret identity-apis)
[OK] app3: route.conf -> platform (public settings from platform); client.yaml, api.yaml -> identity
```

Underneath nothing changes: the derived values are compiled into the same
bundle descriptors (`requires`, `public_from`, `routes`, `clients`, `apis`,
`accepts`) that the lifecycle reads today. Public values are still copied at
`init-config` and compared at install; item 72 works as before.

## 2. `env/<container>.yaml`

As specified in the signed-off
[phase 0 design, section 2](COMPONENT-ENV-DESIGN.md#2-envcontaineryaml): one flat
file of variables per container; lines without a secret become a generated
ConfigMap, lines with a secret a generated Secret, both injected into that
container; conflicts with hand-written `env`/`envFrom` refused; the existing
value rules; shipped in the bundle; lowered inside `effective_documents` so all
existing checks still run.

## 3. Short secret reference

`@@secret:<id>@@` for a `SECRET_FILES` source with exactly one key; the long form
stays ([design, section 3](COMPONENT-ENV-DESIGN.md#3-short-secret-reference-secretid)).

## 4. Conversion checklist

The one-page checklist from the
[phase 0 design, section 6](COMPONENT-ENV-DESIGN.md#6-conversion-checklist-draft-one-page),
moved into `docs/COMPONENTS.md`, with the example adapted to the list catalog.

## Not in the small variant

No new example application, no `mounts/`, no gateway field, no read-through of
public values, no CA profiles, no change to item 72's mechanism, no
`@@provided:`/`@@shared:`. They stay deferred in backlog 77.

## Work and verification

| Part | Estimate |
| --- | --- |
| Catalog derivation (receivers from manifests, edges from files, descriptor compilation, `validate` report) with tests | about 2 days |
| `env/` and the short reference with tests | 2–3 days |
| Demo conversion: `bundles.yaml`, a few components to `env/`, fixtures, `acceptance/renamed_product.py` (it rewrites `public_from`, `routes`, `clients`, `apis`, `accepts`) | about 1 day |
| Docs and checklist | about half a day |
| Lab: fixed matrix and `--whoami` | about 1 day, mostly machine time |

Total about 1–1.5 weeks. Contracts affected: "Declarative components",
"Shared settings" and "Registrations" in the review guide (how they are
declared, not how they behave); the gateway-free worker product stays
supported.

## Questions for the review

1. Is deriving receivers from the manifests (`<id>-routes`, `<id>-clients`,
   `<id>-apis`) robust, and does it keep the renamed product and the
   gateway-free/worker products working?
2. Is deriving `public_from` from `route.conf`/`client.yaml`/placeholder use
   complete and unambiguous, including `shares`?
3. Do the derived values really compile to identical descriptors, so that
   installed state, upgrades from releases built with today's catalog and
   `newer-only` behave exactly as now?
4. Is anything lost by removing the explicit fields (for example reviewability,
   or a case that today needs an explicit owner that is not the single
   receiver)?
5. Is the estimate realistic, and is there an even smaller variant with most of
   the value?
