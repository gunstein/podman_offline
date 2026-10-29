# Review of the small component variant

**Recommendation — Assumption (A): proceed with `env/`, the short secret
reference and an adapted checklist, after correcting the issues below. Keep
the explicit catalog ownership and `public_from` for this delivery.** The
smaller proposal avoids the original global-secret and trust changes, but its
catalog inference is not behavior-preserving for all currently supported
products. It is not ready for implementation unchanged. No merge to `main`
is needed to review or revise it on its branch.

Reviewed at `75594c6`, including [the small proposal](COMPONENT-SMALL-VARIANT.md)
and [the referenced design](COMPONENT-ENV-DESIGN.md). Labels: **C = Verified in
code**, **E = Verified by execution** as described below, **A = Assumption**
(recommendation or prediction about the unimplemented proposal).

## 1. Correctness: do the descriptors stay identical?

**E:** A disposable comparison read selected manifests and registration files,
reconstructed candidate descriptor fields, and compared all fields with
`catalog.source_descriptors()`, including dependency ranges. It used the actual
`acceptance/renamed_product.py` generator for the acceptance product. This was
an independent calculation, **not execution of an implemented new compiler**.
It needed two interpretations: scan actual placeholder uses, not mere presence
of config keys, and exempt the routes receiver from inheriting from itself.

| Product | Result under those interpretations |
| --- | --- |
| Shipped demo | Equal. Owners: routes → `platform`; clients/apis → `identity`. Identity requires platform; app1/app2/app3 require both; help requires platform. |
| Acceptance renamed product | Equal. Owners become `gateway` and `login-service`; orders/inventory require both, manual requires gateway. Gateway's `shares: [SHOP_NAME]` is retained. |
| Shipped platform + help only | Equal. Platform accepts routes; help requires/inherits/registers with platform. No clients/apis owner is needed. |
| Bare worker fixture | Equal: no receiver, registration, public owner or dependency. |
| Existing platform-test `RENAMED` fixture | **Different:** `manual.public_from` changes from `None` to `gateway`. Its route currently does not imply shared configuration. |

**C:** The last case already exists in
[product_fixture.py](../tests/helpers/product_fixture.py), `RENAMED.manual`;
`test_renamed_product.py` explicitly asserts that manual's config has no
`PUBLIC_ORIGIN`. Do not confuse this fixture with the different acceptance
generator. Also, platform/gateway uses public placeholders itself: the literal
proposed rule would produce a forbidden self-dependency without the exemption.

## 2. Is receiver inference robust?

**C/E: no, resource use is not sufficient evidence of a receiver.**
[catalog.py](../deployment/catalog.py), `check_entry` (line 196), permits any
accepted resource name with the component prefix. A valid
`accepts.routes: gateway-includes` cannot be recovered by matching
`gateway-routes`. Conversely, a probe with an ordinary mounted `worker-routes`
PVC passed today's manifest validation with `accepts: {}`; the proposed rule
classified it as a route receiver.

**A:** Two genuinely declared owners should still be refused. Two name matches
can instead be a real owner plus an unrelated ordinary volume, making that
refusal a new restriction. A misspelled receiving name can yield “no receiver,”
but when there are no producers it may simply lose the role. A suffix cannot
distinguish a typo from an intentionally ordinary resource. References through
whole-value placeholders also need a defined resolution rule; do not base
compiled ownership on machine-specific dev overrides.

**A:** Keep `accepts` explicit. If later desired, infer producer links from
`route.conf`, `client.yaml` and `api.yaml` to the already declared unique owner.
That is a smaller convenience than inferring both capability and destination.
Print source file/reference and destination in `validate`, not just the inferred
owner; otherwise the report hides why the wrong component was selected.

## 3. Is the `public_from` rule complete?

**C/E: no.** Besides the existing route-only manual counterexample:

- A worker can use its own `PUBLIC_ORIGIN` without any routes receiver. A probe
  passed `effective_documents()` with that layout; the proposed inference would
  refuse it or force inheritance when a receiver exists.
- **C:** `public_from` can name a dependency that does not accept routes.
  `check_entry` does not tie public settings to that role. The new rule removes
  this supported choice, and keeping an explicit `requires` cannot restore it.
- **C:** `config/common.defaults.yaml` supplies public keys to components
  without implying inheritance. Their presence is not proof of use. Similarly,
  a local `SHOP_NAME` does not establish intent to inherit the gateway's value.

**A:** A complete scanning rule would have to cover `env/`, valid manifest
placeholder positions and `SECRET_TEMPLATES`, exclude self-edges and unused
defaults, and distinguish local values from inherited ones. Syntax alone cannot
resolve the last distinction. Keep `public_from` explicit rather than grow
exception rules. This also preserves `init_config`, `shared_keys`,
`check_public_settings` and `dev_settings` semantics.

## 4. Installed state, upgrades, skips and pending work

**C:** Identical descriptors really would allow the existing runtime flow to
remain: `install_component_plan` records the attempt, publishes metadata and
registration changes, updates YAML/imports, restarts and acknowledges owners,
then completes the marker. After an owner failure, pending work survives;
`replace_owner_secrets` rebuilds the accepted Secret and acknowledgement follows
restart/health success. `api_updates` retains the installed value for a skipped
`newer-only` API, and `install_checks` refuses a non-rendering retry of another
pending version. No new transaction mechanism is required for source shorthand.

**A:** That compatibility is conditional, not established by retaining field
names. Changed inferred owners/dependencies change upgrade, uninstall and retry
checks. Source-only field restrictions must not be applied to compiled
descriptors or old installed metadata: keep `check_descriptor` and its older
field defaults. Infer once at build time, never again from an isolated installed
bundle that lacks sibling manifests.

**C/E: conversion to `env/` has a separate persistent-config problem.**
`init_config` retains existing config. If conversion replaces an old
`SECRET_TEMPLATES` output with a newly named generated Secret, the old recipe
remains in that config. A probe using `effective_documents()` reproduced the
“not used by any manifest” refusal for the retained old recipe. Specify an
explicit config-conversion procedure, or limit the first conversion to fresh
dev/lab state; do not promise transparent old-release upgrades merely because
their descriptors match. Bump versions when converting `newer-only` components.

## 5. What is lost, and understandability

**A:** A shorter catalog loses the visible ownership/dependency overview and
turns resource suffixes into behavioral declarations. Renaming a mount can
then change installation order, shared-value validation and restart targets.
This trades writing less YAML for understanding more hidden rules.

**C:** The existing model already permits only one owner per role, so choosing
between two simultaneous Identity owners is **not** a capability being lost.
What is lost is arbitrary accepted resource naming, ordinary use of matching
suffixes, route-only components without inheritance, and independent public
configuration owners.

**A — understandability outcome:** `env/` is a useful, local simplification;
inferred ownership is less understandable for maintenance than the declarations
it removes. Keep the compiler path explicit and diagnostic provenance visible.
The checklist must point to a real existing component or a complete inline
example: its current “copy the example component” instruction depends on the
new `orders` application that this variant excludes. No human usability result
is claimed.

## 6. Scope, estimate and the smaller alternative

**C/E: fix these concrete issues inherited from the phase-0 design first:**

1. **Mixed env files cannot use one resource name for both kinds.** Design
   lines 87–88 give ConfigMap and Secret the same `orders-api-env` name.
   `render.check_links` (line 760) rejects this across kinds; a direct probe
   reproduced the refusal. Use distinct names such as `-env` and `-env-secret`;
   keep the collision guard.
2. **Existing guards do not follow `envFrom`.**
   `registrations.check_client_identity` (line 242) reads direct `env` values;
   moving `APP_ID` into a ConfigMap produced its “manifests set APP_ID to
   nothing” error. `deploy.postgres_binding` (line 180) likewise rejected moving
   `POSTGRES_PASSWORD_FILE` into `envFrom`. Preserve these explicit manifest
   entries initially, or budget a shared resolution change; lowering into
   ordinary resources does not by itself preserve these checks.
3. **One generated filename is not necessarily one delivered key.**
   `render.secret_keys` includes existing directory entries. A source with
   `generate: [password]` and an additional retained file exposed two keys in
   the probe. Resolve the short form against actual delivered key names before
   publication, without reading secret contents during validation.

**C:** Renamed acceptance work also goes beyond removing catalog-field rewrites:
`renamed_product.generate` does not copy `env/`, and `rename_defaults` rewrites
only long secret references. Both forms and new files need coverage.

**A:** The listed estimates total 6.5–7.5 working days. That is an optimistic
budget, not a reliable commitment for the whole proposal: inference decisions,
retained-config conversion and these validation interactions remain unresolved,
and lab failures can require another iteration. **The smallest useful delivery
is `env/` with distinct resource names, the checked short reference, and a
corrected checklist, retaining today's catalog.** Keep PostgreSQL/OIDC guard
inputs explicit for that delivery. Reassess optional producer-link shorthand
only after seeing whether catalog editing still causes significant problems.

**E — verification in this review:** 75 existing product/unit tests passed
(`PYTHONPATH=tests python3 -B -m unittest platform_tests.test_catalog
platform_tests.test_api_registrations platform_tests.test_retry
platform_tests.test_secret_templates`); 17 acceptance-harness tests passed
(`python3 -B -m unittest discover -s acceptance -p 'test_renamed.py'`). The
disposable comparisons/probes above exercised existing Python functions and
fixtures on Python 3.12.14. No new implementation, real Podman/systemd, full
acceptance matrix, Python 3.6 or human trial was run. These results establish
the current baseline and counterexamples, not acceptance of the proposed model.
