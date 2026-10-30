# Check of the decided component specification

**Conclusion: ready after these corrections.** The revised decisions make the
implementation substantially smaller. No alternative catalog or migration
layer is needed; the remaining corrections are listed below.

Baseline: **`858bb2f`**, superseding the check of `d86b73f`.
[Specification](COMPONENT-SMALL-VARIANT.md), especially new sections 5–6.
**C = Verified in code. E = Verified by execution** as described below.
**A = Assumption/design judgment**, including recommendations and estimates.
No implementation of backlog 77 exists yet.

## Effect of the new assumptions

- **C/A:** Explicit `identity:` removes manifest-based receiver discovery and
  its unresolved placeholder/config context. Existing rendering can resolve
  receiver placeholders later; no new literal-name restriction is needed.
- **C/A:** Generated-single-source-only short references have a known key at
  declaration time. The missing supplied-file ambiguity disappears. Retained
  extra files still require the specified delivered-key check.
- **C/A:** Forbidding handwritten `envFrom` alongside `env/` excludes the
  previously identified collision between generated env and a later-expanded
  API registration Secret. Keep that container on its existing `envFrom`
  path; no additional reservation of API variable names is necessary.
- **C/A:** Fresh installations remove conversion/migration work. They do not
  remove credential retention, normal upgrades or fresh-process retry within
  the new model. Section 6's two ordinary helpers give a clearer implementation
  boundary than inference spread across lifecycle code.

## Problems and minimum corrections

Code paths below are relative to `deployment/`, except where stated.

| ID / severity | What is wrong and evidence | Code location | Minimum correction (A) |
| --- | --- | --- | --- |
| **B1 — Blocker** | **C/E:** Rule 3.2.7 excludes only `POSTGRES_PASSWORD_FILE`. The guard checks every `POSTGRES_PASSWORD*` name. Keeping FILE direct while putting an additional `POSTGRES_PASSWORD` in generated `envFrom` hides a declaration that the direct-env guard refuses. The new no-mixing rule does not prevent this: generated `envFrom` is allowed. | `deploy.py:180–207` | Keep **all `POSTGRES_PASSWORD*` variables** out of `env/`, with the same actionable “keep it in the manifest's env” error. Leave the existing guard unchanged. |
| **B2 — Blocker for the stated equivalence test** | **C/E:** `RENAMED` has another difference besides `manual`: `login-service.accepts` gains `apis: login-service-apis`. Its current manifest does not reference that Secret and fails the existing unused-import check. | `tests/helpers/product_fixture.py:141–155`; `render.py:799–805` | Document this second expected fixture change; add the API Secret reference and update its expected descriptor. Keep R2's single Identity accepting both roles. |
| **M1 — Minor** | **C/E:** Identity without a gateway cannot support `client.yaml`: normalized validation still requires `public_from`. The refusal list omits this case. | `catalog.py:213–217` | Add “client.yaml requires a gateway and a non-gateway client component.” Name the source file and remedy, rather than asking for removed `public_from`. |
| **M2 — Minor** | **C/E:** R3 overstates existing validation: a routes PVC in `spec.volumes` with no container mounting it passes `effective_documents`. A reference is not proof of a mount. | `render.py:729`, `references`; `render.py:760`, `check_links`; `render.py:907`, `check_pod_specs` | State that a focused receiver-mount check is needed in the existing rendering validation: follow Pod volume names to regular/init-container mounts after substitution. Keep the catalog independent of manifests. |
| **M3 — Minor** | **C:** The suggested lowering return values need a specified destination. `effective_documents` returns documents only; later `materialize` reads recipes from config again. Temporary recipes discarded after validation will never produce the Secret. | `render.py:1003,1085`; `deploy.py:401,786` | Carry synthetic recipes in the same transient effective config used for validation and materialization; never persist them into operator config. Permit this plumbing adjustment while keeping one lowering path. |
| **M4 — Minor** | **C:** Section 9 promises every §3.2 refusal before any write/generation/host command, but checking private substituted bytes requires materialization. | `render.py:1085–1125`; `templates.py:153–179` | Apply the early guarantee to declaration checks. Require private-content checks before rendered YAML/registrations are published or services changed. Keep validate free of credential-content reads. |
| **M5 — Minor** | **C:** “Move these variables to env/” is not a valid remedy for every handwritten `envFrom`: Identity's platform-generated registration Secret is not a `SECRET_FILES` source that env recipes can import. | `render.py:1043–1050`; `templates.py:128–135` | Say “use env/ or keep this container's handwritten envFrom.” Explicitly keep the Identity receiver on its existing path; only app3 is required to convert. |

## 1. Equal normalized catalog

**E:** A disposable script calculated the new rules using named gateway/Identity
and file presence only, then compared entries, dependency order and compiled
`source_descriptors` with today's functions. Existing `check_entry` and
`check_owners` checked the derived entries.

| Product | Result |
| --- | --- |
| Shipped demo | Equal. |
| Actual acceptance renamed-product generator output | Equal. |
| Platform + help | Equal; no Identity required. |
| Gateway-free `WORKER` fixture | Equal. |
| Demo plus a new `reports` without client/API files | Equal; reports requires only platform. |
| Platform-test `RENAMED` | `manual.public_from: None → gateway`, **plus** the new accepted API Secret (B2). |

**E:** Adding that Secret reference to a temporary copy of the fixture makes
its existing rendering validation pass. Repeated written/derived demo
requirements also match after stable deduplication. **A:** Preserve written
order, then append missing gateway/Identity dependencies; keep existing catalog
order for unrelated components. R2's “no dependency” means no *inferred*
Identity dependency; explicit `requires` still applies.

## 2. Completeness

**C/A:** Keep normalized `check_entry`, `check_owners`, dependency/cycle checks
and `source_descriptors` version-range compilation. Remove only source-field
parsing made obsolete by the new form. Enforce gateway-only `shares` at source
loading, and update `catalog_document` too: `product_name` uses its top-level
schema check. Prefix validation plus disjoint component IDs supports R4.
M1 completes the missing source refusal. No new dependency representation is
needed.

## 3. Receiver references

**E:** Existing `effective_documents` resolves placeholder PVC and Secret names
in init containers with the new named owner's imports. Thus placeholder forms
no longer complicate catalog derivation. Supported manifest kinds remain Pod,
ConfigMap, PVC and Secret; no Deployment/List support is implied. M2 is the
remaining distinction between a linked resource and an actually mounted one.

## 4. `env/` and short references

**C/A:** Lowering before existing checks is feasible with M3's transient config
flow. Keep checked OIDC variables direct; extend the PostgreSQL exclusion as
B1 specifies. Reject handwritten `envFrom` before adding generated entries,
and make repeated validation safe.

**C/E:** Public `templates.config_text` accepts a semicolon-containing
substitution that `check_text` rejects. Apply §3.2.8's check explicitly for
public env substitutions; do not tighten unrelated existing ConfigMaps.
Generated short references can expand to the declaration's sole key before
existing recipe validation; check the delivered key set again at materialization.
Shipping `env/` requires the stated bundle copy/guard/checksum and renamed-tool
updates.

## 5. State and lifecycle

**C/A:** Source normalization can preserve descriptor formats, `check_descriptor`
and `LATER_KEYS`. Fresh dev/lab recreation replaces old-config conversion;
normal lifecycle behavior must still remain intact. Success continues through
materialization, durable pending work, registration/YAML publication, restart,
health check, acknowledgement and completion. An owner restart failure leaves
pending work for retry; a non-rendered `newer-only` API retains its installed
registration. No redesign of this state machine follows from the new assumptions.

## 6. Scope and understandability

**A:** The new estimate adds up to **six working days**, slightly more than a
five-day week. About 1–1.5 weeks is plausible for someone familiar with the code,
with little contingency. The likely overrun is carrying env recipes consistently
through validate/prepare/install and then resolving lab failures, rather than
catalog derivation or migration.

**A — understandability:** the two helpers and explicit data flow are a better
basis for maintenance. One successful operation and one retry can retain the
existing lifecycle explanation. This is a specification assessment, not a pass
for unwritten Python or an unassisted human trial. No operator procedure was
changed or executed in this review.

**Evidence:** The new named-owner comparisons and focused rendering/guard probes
ran on `858bb2f` under Python 3.12.14, using temporary fixtures and existing
functions. Before the documentation-only update, **75 product/unit tests**
passed (`test_catalog`, `test_api_registrations`, `test_retry`,
`test_secret_templates`, via `PYTHONPATH=tests python3 -B -m unittest` with
`platform_tests.` module prefixes); **17 acceptance-harness tests** passed
(`python3 -B -m unittest discover -s acceptance -p 'test_renamed.py'`). The code
and tests did not change between these baselines. No real Podman/systemd,
Python 3.6, full lab matrix or future implementation was executed. Historical
lab results provide no evidence for this change.
