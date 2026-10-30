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

## 2026-10-30 independent check: API placeholders and short declarations

**Conclusion: ready after corrections.** The two additions are feasible without
another registration system, but **B3 and B4 below block implementation as
currently specified**. The new Identity mapping changes persistent metadata and
upgrade validation; it cannot be implemented while keeping descriptors and all
post-catalog behavior unchanged. This does not reopen the product owner's
catalog, syntax, hashing or simplicity decisions.

Baseline: **`65af892d0ceab1464e81dec4b67001e29954144d`**, `main`, 2026-10-30.
This section checks the update in [the specification](COMPONENT-SMALL-VARIANT.md)
against that code, not against an implementation of backlog 77.
**C = verified in code; E = verified by execution; A = assumption or judgment.**
Finding numbers continue the earlier report; the earlier findings are historical.
Read first: [AGENTS.md](../AGENTS.md), [review guide](REVIEW_GUIDE.md), and
[backlog 77 and 72](../BACKLOG.md). Relevant contracts: credential retention,
API registrations, declaration-only validation, secret templates, dependency
ordering, durable retry, scoped removal and developer/operator understandability.

### Blocking findings

**B3 — The compiled mapping needs a defined durable and upgrade contract (C/E/A).**
Section 5 requires new Identity descriptor data, but sections 2.3 and 7 still
promise unchanged descriptors, `check_descriptor` and downstream behavior.
`catalog.check_descriptor` accepts exactly `DESCRIPTOR_KEYS`; an executed probe
adding a mapping field is refused. Today `registrations.api_index`,
`registration_stage` and `owner_secrets` read the index from
`STATE/apis/<api>/index`, and `owner_secrets` constructs a hard-coded
`ApiResources__<index>__ApiSecrets__0__Value`. They cannot implement arbitrary
owner variable names by changing only the `api.yaml` reader.

Concrete failure to specify: Identity v2 removes or moves an installed API's
mapping. `deploy.check_dependents` checks version ranges, not mapping coverage.
The old registration still carries its old index. Reusing it unchanged can put
the secret on the wrong resource; simply ignoring it silently disables the API.
Also, `install_component_plan` writes incoming metadata even when a `newer-only`
component is not rendered. A newly compiled mapping must not replace the mapping
used by the running Identity while its YAML remains unchanged.

**Minimum correction (A):** explicitly permit one validated descriptor field
for the Identity container and API-to-variable mapping, carried through bundle
and installed metadata. Define the installed, actually rendered Identity mapping
as authoritative for isolated API installs and owner-Secret rewrites. Before
writes, refuse an Identity release that drops a mapping required by an installed
API; explain that the API must first be uninstalled or upgraded to drop its role.
Permit moving a key when Identity is actually rerendered, rebuilding from retained
values by API ID. On skipped Identity renders retain its effective installed
mapping (or refuse a differing incoming mapping). Check mapping membership on API
install and mapping preservation on Identity upgrade. Specify how the old
registration `index` is removed or made non-authoritative; do not persist two
competing mappings. Fresh-install-only removes old-format migration work, not
ordinary upgrades or interrupted installs in the new format.

**B4 — Identity mapping cardinality and key ownership are under-specified (C/A).**
Section 5 says “API component -> variable name”, allows any variable name, and
limits one secret per API resource, but does not say whether the same API may
appear at two Identity variables or whether two differently spelled variables
may identify the same .NET configuration key. Section 3 only rejects identical
YAML keys. For example, `ApiResources__0__ApiSecrets__0__Value` and
`apiresources__0__apisecrets__0__value` are distinct YAML keys but collide in
.NET configuration. One can contain the placeholder and the other a literal;
omitting the placeholder does not then guarantee a resource without a secret.
The old duplicate-index check cannot validate this new mapping. Injection must
also avoid handing these lines to ordinary `SECRET_TEMPLATES`: Identity has no
local `SECRET_FILES` source for another component's API value.

**Minimum correction (A):** choose a single-valued mapping: exactly one receiving
variable per API in the one Identity container; repeated references in the API's
own containers may consume the same value. Reject duplicate receiving keys using
.NET's case-insensitive comparison, including conflicts with direct manifest
`env` and ordinary generated env keys. Partition Identity API lines before normal
env lowering; only the owner registration Secret supplies them. Either require
canonical `ApiResources__<n>__ApiSecrets__0__Value` keys (smallest Duende-specific
check) or state explicitly which application checks replace this validation when
arbitrary keys are retained. An Identity self-reference must be refused clearly,
rather than discovered as a derived self-dependency. All these checks use public
declarations and belong before generation or host actions.

### Minor findings and concrete corrections

| ID | Evidence and consequence | Minimum correction (A) |
| --- | --- | --- |
| **M6 — Implicit credential collision policy** | **C:** `file_group_sources` requires lists today; `generated_secret_paths` detects duplicate generated paths. Neither establishes the resource ID of the implicit API source. An existing long declaration can point to `credentials/api-secret/value`, independently of its ID. | Choose one component-prefixed internal API source ID and reject an explicit resource with that ID or a conflicting declaration for that path. Repeated lowering must reuse its own transient entry, not overwrite user entries. Keep the stipulated credential path. |
| **M7 — Short declarations and config layers** | **C/E:** `<id>: generate` currently fails list validation; expansion to `[{path: credentials/<id>, generate: [value]}]` is accepted. `UniqueKeyLoader` rejects duplicate keys; `merge_config` replaces whole top-level maps. | Expand in the shared effective-config/file-source path before existing consumers, not only in `lower_env`: standalone config, validation, generation and direct Secret mounts also need it. A short and long declaration with the same ID in one map is an error. Across layers retain existing whole-`SECRET_FILES` replacement semantics; do not merge or concatenate silently. Show this in the copied example/diagnostic. |
| **M8 — Identity loading contract is incomplete** | **C:** `apps/identity/Program.cs:69–76` already omits resources with no secret, but currently expects the platform's hash. It counts secrets, without establishing the new raw-value hashing contract. | Require Base64(SHA-256(UTF-8(raw value))) exactly once while constructing the in-memory resource; never persist the hash back over the raw source. Exclude an absent-secret resource from active resources; refuse a present empty/invalid secret without printing it. Test zero, one and two APIs, gaps, removal, restart and successful/failed introspection. |
| **M9 — Stale explanatory text and acceptance coverage** | **C:** Section 9 still describes `api.yaml` presence and says Identity keeps its handwritten registration `envFrom`; sections 3/5 now replace both. Section 10's early-refusal test list names 2.5/3.2 but not the new section 4/5 errors. | Correct those references and include short-declaration, API mapping, collision, isolated-bundle and owner-upgrade refusals in the test list. State that normalized role/dependency equality remains the goal; descriptor equality now has an explicit mapping exception. |
| **M10 — Readiness example needs bounded failure semantics** | **C/A:** The existing app1 manifest has `always` init migration/seed steps; the new `pg_isready` wait is a checklist addition, not verified new behavior. | Show explicit host/port, per-attempt timeout, finite retries and a nonzero final exit. A lower-numbered database manifest orders submission, not readiness. State that `pg_isready` does not prove application credentials or migrations work; the following init step must fail safely and remain idempotent. Test a delayed and an unavailable database in the new example. |

### Lifecycle: what is reusable and what must change

**C/A — authority and storage.** The proposed raw source is
`/var/lib/<product>/state/<api>/credentials/api-secret/value` in production,
relative to the API's persistent `config.yaml`; dev uses its own generated
component config directory under `build/dev`. This follows `layout.select` and
`catalog.state_paths`. Section 4's ordinary short declaration instead uses
`credentials/<id>/value`; these are deliberately different conventions.
`render.generate_secrets` already creates missing 32-character alphanumeric
values with private permissions and preserves existing nonempty regular files.
Reusing it through a transient implicit API source is feasible. Generation
belongs after declaration/database preflight, during prepare/materialization,
never in catalog loading, build or `validate`.

The source file remains authoritative for a rendered API. A private
`STATE/apis/<api>/value` registration represents the value that install publishes
to Identity. With platform hashing removed, that registration holds raw text;
Identity's private rendered YAML contains its Base64-encoded transport form,
not its Duende hash. These are existing delivery copies, not independent secrets.
Do not rebuild Identity from arbitrary current API credential files: an API
skipped by `newer-only` must keep the value it actually runs with.

| Event | Current code evidence (C/E where executed) and required new behavior (A) |
| --- | --- |
| First Identity install | `owner_secrets` can render an empty Secret; the demo already filters resources lacking secrets. Under the proposal only placeholder-bearing secret lines are omitted. Name/scopes and other ordinary env lines remain. Identity must have its own dependencies/config prepared first. |
| API attempted before Identity | **E:** `check_dependencies_installed` refuses with “Install the separate accounts bundle before installing orders” in a renamed probe. R2 preserves that dependency. There is no deferred pre-Identity API install queue; install Identity first. |
| API installed after Identity | Validate membership against installed mapping, generate/retain the API source, stage the raw registration, render API output, publish pending work and registration, rewrite the installed owner's Secret, restart/check API, then restart/check Identity. In dev, `api_updates` already generates API values before the owner is materialized, despite dependency render order. |
| API upgrade/rotation | Existing `api_updates` and registration comparison preserve an unrendered `newer-only` API's registration. A rendered API uses its retained or explicitly replaced source. Changing bytes restarts API before Identity; unchanged registration alone adds no owner restart. Rotation requires a render, not merely editing a file and retrying a skipped version. |
| Identity upgrade | Rebuild all mapped, registered values from installed registration state using the incoming mapping only when rendering. Check retained APIs first; apply B3 for skipped renders and removed/moved mappings. No sibling API restart is needed for a pure owner mapping change. |
| API uninstall or role removal | Existing uninstall records pending owners before stopping/deleting, removes `apis/<api>`, rewrites the owner's Secret and restarts/checks the owner. Normal uninstall retains credentials; `--delete-data` removes the selected component state/data. Name/scopes remain in Identity; the missing secret makes the resource inactive. A later reinstall can reuse retained bytes. |

**C/E — success and interruption.** `begin_install` records the attempted version
before installed metadata/unit publication. `apply_registration_updates` records
changed owners before registration writes/deletions. `replace_owner_secrets`
atomically replaces installed YAML; `restart_component_services` uses reversed
dependency order and acknowledges each owner only after restart and health
checks. The completion marker precedes `clear_pending`. Executed existing tests
cover interrupted owner-YAML replacement, retained old YAML, pending owner work,
retry and refusal of a skipped retry for another attempted version. These tests
invoke retry in the test process with retained disk state; they are not a new
process-kill or real systemd test. The new mapping must be durable before a retry
needs it, and the same pending-operation gate must prevent an intervening owner
operation from changing the mapping underneath an API retry.

**A — health ordering constraint:** an API's startup/health check must not require
successful introspection with its new secret before Identity's restart. The
existing API-first order otherwise stalls rotation. Keep health checks local;
exercise the brief authentication interruption in acceptance. No overlap or
zero-downtime guarantee is introduced.

### Syntax, refusals and confidentiality

**C/E:** `templates.tokens` currently accepts `@@NAME@@` and
`@@secret:orders-password/value@@`, and rejects both new forms as unknown/nested
placeholders. The grammars can be disjoint: uppercase config names, `secret:`
with an optional single key separator, and `api-secret:` with a validated
component ID. Extend one tokenizer/normalizer; never use repeated text
replacement or let a secret's contents introduce tokens. Ordinary short secrets
expand to their known generated key before recipe checks. API-owned references
can lower to the implicit local source; Identity references go to registration
mapping, not local secret lookup. They remain forbidden in ordinary public
ConfigMap data and outside the specified contexts.

**C/A:** `check_text` constrains substituted bytes, not placeholder syntax. New
prefixes do not require weakening it. Generated alphanumeric values fit it.
Retained API values must continue to reject trailing newline, whitespace,
quotes, semicolon, controls and `@@` before publication; do not let recipe LF
stripping create a mismatch between the API and its registration. Short-secret
key-set checks must include unexpected retained files. Values needed for these
checks cannot be read by `validate` and generation may already have occurred;
“every error before any write” is only achievable for declaration errors.

**C/A:** R4 reserves resources, not token names. Existing prefix checks and
`effective_documents`' imported-Secret collision guard remain useful. In
particular, Identity itself may not declare `<identity>-apis` either: R4's
wrong-component prohibition must not be interpreted as permission for Identity
to override that platform-generated Secret. Apply generated-resource collision
checks after placeholder substitution and before injection.

**A — required negative cases:** misspelled/unlisted component; listed non-API;
missing Identity; absent receiving mapping; foreign API use; duplicate mapping;
self-reference; duplicate YAML declaration; short/long resource or path collision;
and API absent from installed Identity mapping must all fail using public inputs
before persistent writes, generation or host commands. Include file, variable
or resource name and a concrete repair, never the env value or whole YAML line.
Use a sanitized YAML error boundary such as `config_layer`, not raw arbitrary
parser diagnostics. Existing tests cover the old API format's secret-safe errors;
they cannot certify these new errors. Public mapping checks should not be added
only to a late `api_updates` call: source validate/prepare and isolated install
must share them.

### Identity feasibility and understandability

**C/A:** The two-line link is easier to discover than `api.yaml`, and raw values
on both sides can support Duende. The [Duende ApiResource reference](https://docs.duendesoftware.com/identityserver/reference/models/api-resource/)
identifies `Name` as the introspection identity and `ApiSecrets` as its credential.
The backend must use that resource name for introspection; a free resource name
is not automatically the component ID. The existing platform's
`api_registration(hash: sha256)` is an executable reference for the requested
Base64 SHA-256 calculation. Moving that calculation into the application is
small, but the new C# binding/hash behavior was not executed in this review.

**A — developer understandability: findings.** A reader can infer that matching
`@@api-secret:myapp@@` tokens share a value. From the files alone they cannot infer
its storage path, generation/retention rules, Identity hashing, omitted-secret
behavior, Identity-first installation, `newer-only` rotation limits, or that
`generate` mounts a file named `value`. Section 4 promises a complete database
example, which addresses the last point. Supply an equally complete, minimal
Identity/API example with short adjacent comments and actual Identity loading
code. Extend value-free `validate` output to show generated source path, receiving
container/key and install prerequisite; the current link-only output does not
explain those rules. This is clarification at the point of use, not a second
configuration format or a long manual developers must reconstruct.

**A — operator review:** static findings only. The spec's instruction to preload
with `printf '%s'` is not yet a complete operator procedure: it omits account,
absolute path, private permissions and safe input that avoids shell history.
The eventual single manual must provide that procedure, explain retention and
Identity-first order, and give a safe rotation/retry command for `newer-only`.
No new operator command sequence was executed; no unassisted human trial took
place. Operator usability remains unverified, not implicitly passed by unit tests.

### Scope, simpler implementation and evidence

**A:** The table totals **8–8.5 working days**. About **1.5–2 weeks remains a
plausible implementation target for a maintainer**, after the corrections above,
with little contingency; budget **2–3 weeks including review and lab fixes** if
this is a delivery commitment. Descriptor/installed-state semantics and new
failure tests are the uncertainty, not parsing the two prefixes. The fixed
matrix alone does not exercise mapping moves/removal, skipped-owner metadata,
two APIs, duplicate destinations or API-first refusal. Add focused cases rather
than treating historical backlog-72 lab results as evidence for the new form.

**A — simplest variant with the same author experience:** normalize short
`SECRET_FILES` entries once; lower API-owned tokens to one implicit generated
file source; compile one owner mapping keyed by API ID; retain raw registration
values keyed by that same ID. Resolve destination names only when assembling
the owner Secret. Reuse existing pending/restart/uninstall machinery. Avoid a
second registry, synthetic on-disk `api.yaml`, mutable index copies and a generic
cross-component secret framework. This requires the explicit small descriptor
change in B3, not an additional user-facing declaration.

**Executed evidence (E), Python 3.12.14:**

- `PYTHONPATH=tests python3 -B -m unittest platform_tests.test_api_registrations platform_tests.test_retry platform_tests.test_secret_templates platform_tests.test_catalog`: **75 passed**.
- `PYTHONPATH=tests python3 -B -m unittest platform_tests.test_config demo_tests.test_identity_demo`: **15 passed**.
- Disposable existing-function probes: new token refusal versus existing token
  acceptance; short declaration refusal versus expanded-list acceptance;
  descriptor extension refusal; API-first dependency refusal; duplicate-key
  loading through both YAML/config readers without echoing a sentinel value.
  These are current-code observations, not tests of future lowering.

No acceptance-harness suite, real Podman/systemd/Duende run, .NET compilation,
Python 3.6 run, new-format implementation, or full lab matrix was performed.
Only this report file is changed. Relative Markdown targets and anchors in this
report and `git diff --check` are checked before committing.
