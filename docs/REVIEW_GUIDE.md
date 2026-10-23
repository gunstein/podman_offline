# Product contracts and review guide

This is the shared review baseline for implementation agents and human reviewers.
Read it with [ARCHITECTURE.md](../ARCHITECTURE.md), [README.md](../README.md), the
[test instructions](../tests/README.md), [acceptance instructions](../acceptance/README.md)
and the relevant [backlog item](../BACKLOG.md). Review the product contract and
complete affected lifecycle, not just the changed lines or passing demo tests.

## 1. Product contracts

These are requirements, not a claim that every requirement is implemented today.
The known gaps below explicitly identify outstanding work.

| Contract | Required behavior |
| --- | --- |
| Component versions | Each catalog component reads only `components/<id>/VERSION` (`major.minor.patch`); no catalog override or root source version. Bundles retain their informational root `VERSION` and compiled descriptors; standalone fixtures keep root `VERSION`. |
| Declarative components | Selected YAML declarations and component files define components, dependencies and roles; adding, renaming or removing components requires only component files and catalog YAML, with no generic Python/shell edits. |
| Independent images | Externally built images work without application source in `apps/`; demo builds and demo credential provisioning are explicit. |
| Isolated offline bundles | An unpacked bundle works without the original checkout or sibling source/release directories; target installation does not fetch dependencies or images. |
| Authoritative production config | Explicit `init-config` creates persistent config; subsequent production operations use it. Automatic init-config is not existing functionality. |
| Component dev config | Source dev merges optional common defaults, component defaults, global dev and component dev in that order, replacing whole top-level values. Owner-shared settings remain authoritative; a dependent's component dev file may not declare them. Validate, prepare and dev credential tooling share this flow. Dev layers never initialize production config and never ship in bundles; generated dev config is output only. |
| Bundled file references | `component_file` selects public immutable content under the current component's `files/` in the selected source/release, with explicit component context. Keep logical references in persistent config; reject traversal, symlinks throughout selected trees, special files, generation and database password use before delivery. Validation reads no source bytes. Ordinary `path` semantics and private-source guards remain; imported volumes overwrite matching files and retain unlisted ones. |
| Credential retention | Generate missing secrets only when allowed; preserve valid existing credentials byte-for-byte. Do not expose credentials or complete connection strings in logs. Secret-template values are recomputed from retained sources, never independently persisted. |
| Production release authentication | Signed archive plus independently provisioned pinned product keyring are mandatory before protected publication, trust or execution. Unsigned builds are development-only; checksums alone never authorize production installation. |
| Signing provisioning | Validate public CA subject/lifetimes before writes; share CA creation across modes and retain complete existing CA/credentials when settings change. Refuse an explicit CA subject that differs from the retained CA, and explain that CA lifetime applies only to new CAs. Explicit signing PFX provisioning is separate from deploy/validate, supports arbitrary component IDs and works via stdin offline. Retain external PFX/PEM before issuance; read the private password file without exposing its value. Publish private files without clobbering existing credentials; deliver only the declared PFX, never provisioning keys/passwords implicitly. |
| Secret templates | Only `SECRET_TEMPLATES` composes config and same-component file Secrets. Validate declarations before generation and read no secret bytes during validate. Reject unsafe input without values in errors; output only Opaque Secrets in existing 0600 install YAML, never plain env values or ConfigMaps. |
| ConfigMap inline values | Compose only ConfigMap `data` using public string/integer config; refuse Secret references and recursive expansion without printing values. Keep whole-value behavior elsewhere and preserve shell/nginx dollar syntax. Init, validate and lifecycle share declaration checks; the lab checks the actual consuming container, including renamed products. |
| Database safety | Missing password plus existing database volume is refused. Inspection failure is not evidence of absence. Server and client receive the same password. |
| Retry | Durable pending work survives a new process and is acknowledged only after required work succeeds. |
| Isolation | Operate on the selected component's resources/state; preserve sibling data and registrations and avoid sibling app restarts. |
| Compatibility | Preserve host Python 3.6, checksums, offline delivery, version/dependency rules, SELinux and fapolicyd behavior. |
| Host preparation | Trust the root-controlled `/var/lib` anchor; root creates only the root-owned `/var/lib/<product>` and the account's `state/`, `config/`, `storage/` directly beneath it, refusing links and foreign owners before chown/chmod. Descendant directory/lock creation and both relabel operations run as a non-root numeric account UID/GID without supplementary groups or capabilities, with no privilege acquisition or root retry. Reject managed links/foreign-owned objects; preserve lock bytes, existing subordinate IDs, the account's home/shell and populated storage labels. Current-change OL9 Enforcing/fapolicyd verification is required before declaring this boundary verified. |
| Production layout | An existing login account (any name) runs one product. Its home holds only `~/.<product>/<product>.env`, read by `layout.select()` as private data (no execution, unknown keys ignored, values never logged). Everything else is under `/var/lib/<product>`: root-only `releases/`, the account's `state/`, `config/` (`XDG_CONFIG_HOME`) and `storage/` (`XDG_DATA_HOME`). The user manager gets the same two values from a root-owned `user@<uid>` drop-in, and lifecycle commands refuse a mismatch. Root never reads the bootstrap file. Source dev and bundle building never select production paths. No migration of the earlier service-home layout. |
| Validation | `./deploy validate` and the lifecycle share one validation (`validate_component`, staging, `install_checks`, `install_preconditions`); the command writes nothing, reads no credential contents and runs no host command. Container-only fields listed in [README](../README.md) are refused directly under Pod `spec` through the shared `render.pod_specs` shape check, including bundle image discovery. This is a focused guard, not full schema validation. A new declaration check belongs in one of those functions, never inline in `install_component_plan`; a validate-only check names where the lifecycle does the same. |
| Product name | `product:` in `bundles.yaml` is the only source of the installation's names. Code builds unit, network, Quadlet, temporary-directory and archive names from `catalog.product_name()` / `catalog.unit_name()` (or the descriptor's `product`), never from a literal; `common.STANDALONE_PRODUCT` is only for standalone fixtures. It names the installation root `/var/lib/<product>` and the bootstrap file; the runtime account is passed explicitly (`prepare-host.sh --user`) and need not match it (the harness uses `<product>-ops`). One account runs one product (`check_same_product`, one drop-in per account). Image names come from the manifests (the demo's are neutral `localhost/demo-*`) and `PUBLIC_ORIGIN` from config; neither is derived from the product name. |
| Shared settings | A `public_from` dependent takes `PUBLIC_ORIGIN`, `HTTPS_PORT` and the owner's `shares` at `init-config` and in dev, and install/validate compare them (`deploy.shared_keys`, `check_public_settings`); errors name the setting, both files and the owner, never values. `shares` is compiled into descriptors; an owner upgrade may not drop a name an installed dependent takes (`check_kept_shares`). Reserved names (`PUBLIC_HOSTNAME`, `SECRET_FILES`, `VOLUME_FILES`, `SECRET_TEMPLATES`) cannot be shared; their documentation is docs/COMPONENTS.md, "Reserved configuration names". |

Before the first real customer installation, existing dev/lab installations may
be discarded; no migration code, aliases or old-layout fallback are required for
the current changes (including items 20, 21, 54 and 64). After the first real customer
installation, incompatible changes must provide a migration and verification
procedure that preserves customer data and credentials. This temporary exemption
must not become a permanent no-migration policy. Older backlog exemptions apply
only to the pre-customer phase. This does not remove normal restart/redeploy/retry or data-retention requirements within
the supported model. Historical evidence and pinned historical fixtures remain
unchanged and must not be represented as current verification.

### Known gaps at the review baseline

Baseline: source reviewed at `1d3e3b7` (2026-10-16). Recheck actual code when using
this list; update entries with implementation/test evidence when resolved.

| Gap | Owner |
| --- | --- |
| ~~Fixed component graph, version sources, registration owners, client allowlist, restart order and config inheritance~~ | Resolved by backlog 20 in 0.4.9; [verification](../acceptance/DECLARATIVE-COMPONENTS.md), lab runs clean |
| ~~Mandatory public origin/port for every component; hostname derivation tied to `platform`~~ | Resolved by backlog 20 in 0.4.9 |
| ~~Initial image validation includes unselected component directories; generic dev still has demo dependencies~~ | Resolved by backlog 20 in 0.4.9 |
| ~~OIDC client ID/path/scopes coupled to component ID; contract needs explicit validation/documentation~~ | Resolved by backlog 20 in 0.4.9; contract in [components](COMPONENTS.md) |
| ~~Database preflight uses raw placeholders rather than effective manifest values~~ | Resolved by backlog 21 in 0.4.10; [verification](../acceptance/MANIFEST-VALIDATION.md), lab runs clean after review follow-up |
| ~~Resource kinds receive inconsistent lifecycle checks: Deployment can bypass Pod checks~~ | Resolved by backlog 21 in 0.4.10: unsupported kinds are refused |
| ~~Removing route/client declarations from a release does not remove prior registrations~~ | Resolved by backlog 21 in 0.4.10 |
| ~~Some invalid manifests create generated secrets before validation rejects them~~ | Resolved by backlog 21 in 0.4.10 |
| ~~Container fields such as `spec.env` pass declaration/reference validation at the wrong structural level~~ | Resolved by backlog 62: shared Pod shape guard; [scope and verification](../acceptance/MANIFEST-STRUCTURE.md) |
| PostgreSQL data mount and explicit Secret items mapping restrict supported layouts | Backlog 7 |
| ~~Secret `items[].key` / `secretKeyRef.key` naming a key no source provides passes validation and fails only at pod start~~ | Resolved by backlog 33: `render.check_secret_keys` in materialize and validate |
| ~~`install` reports success once units are active; containers are not required to be running or healthy~~ | Resolved by backlog 34: `health.wait_healthy` after every restart |
| Demo apps connect to PostgreSQL as the image's superuser | Backlog 35 |
| Demo containers run as container root without `securityContext` or resource limits | Backlog 36 |
| Accepted exposure: Secret-derived env values are visible to the service user/root in runtime inspection and process environments; use file mounts when the app supports them | Backlog 41; [contract](COMPONENTS.md#secret-templates) |
| ~~Generated-Secret delivery to an init process, including replacement and Quadlet rerender/restart, lacks real runtime evidence~~ | Resolved by backlog 61: normal and renamed lab runs CLEAN PASS at `52f28e4`; [evidence and scope](../acceptance/INIT-SECRET.md#completed-real-lab-verification-2026-10-22) |
| Credentials are not encrypted at rest (sources, rendered YAML, Secret volumes, Identity keys) | Backlog 37 |
| ~~Global dev values on a `public_from` dependent can be silently replaced by owner inheritance~~ | Resolved by backlog 58: analysis showed owner and dependents always receive the same effective value; the precedence is documented, no code change |
| ~~Root `prepare-host.sh` follows service-writable home paths for ownership, mode and relabel operations~~ | Resolved by backlog 46: service-user-only, descriptor-based preparation; lab matrix `t11` clean at `3a54714` ([verification](../acceptance/PREPARE-HOST.md)) |
| Root release authentication/trust must remain protected from service-user modification | Backlog 54 implementation uses protected publication (now under `/var/lib/<product>/releases`, backlog 64) and shared exact-inventory trust; six-scenario [OL9 matrix](../acceptance/PROTECTED-RELEASES.md) CLEAN PASS on `5b8ab69`; Python 3.6 and non-baseline integrity outstanding |
| Production installation as an existing login account with product files outside the home | Backlog 64 implemented; full automated [OL9 matrix](../acceptance/PRODUCTION-LAYOUT.md) CLEAN PASS on `5b8ab69`; manual ssh run without sudo worked after adding a persistent journal, but the guide is not verified literally; simpler host preparation, install sets and an ssh harness scenario are backlog 65–67 |
| ~~Bundles carry checksums but no signature~~ | Backlog 38 added `.asc` (gpg); backlog 54 requires signature verification with the pinned key before protected production publication. Unsigned builds remain development-only |

External image support does not by itself demonstrate arbitrary component support.
The baseline review ran 66 existing database/config/bundle/Identity tests
successfully while isolated reproductions still exposed four gaps: literal PVC
placeholder inspection, Deployment bypass, retained route and secret generation
before mount validation. Client removal follows the same retention code but needs
its own regression. Subprocesses were mocked; these are not real runtime results.

## 2. Challenge demo assumptions

For component-model changes, verify both a renamed product (for example gateway,
login-service, orders, inventory and manual) and a minimal worker with no gateway,
Identity, public URL, database, certificates or apps directory. Use declarative
configuration and application inputs, not patches to generic deployment code.
Other changes should use the relevant focused cases, not automatically run every
possible scenario.

| Variation | Expected result |
| --- | --- |
| Add/rename a selected component | No Python component-list edit; validate safe IDs rather than silently rewriting them. |
| Exclude a component | No implicit render/build/install or image validation of that directory. |
| Remove a service definition | Remove its component directory/catalog entry and adjust YAML dependents; repeated builds exclude stale outputs. Installed production state remains until explicit uninstall. |
| Invalid image in an unselected directory | Selected build is unaffected. |
| Gateway/help only | No Identity or app-database requirement. |
| Empty/missing apps directory with external images | No implicit demo build or provisioning. |
| Configured PVC or Secret binding | Same effective values in validation, preflight and runtime. |
| Alternative resource kind/wrapper | Consistent supported lifecycle or clear rejection before side effects. |

Distinguish component IDs, image names, resource names, public URLs and OIDC
client IDs. Explain deliberate protocol constraints; do not infer generic support
from fixtures that repeat demo names. For supported Podman behavior, consult the
project's supported-version evidence and verify runtime where necessary.

## 3. Trace information across the lifecycle

| Information | Trace to review |
| --- | --- |
| Component/dependencies | Source declarations -> bundled metadata -> install checks -> durable installed metadata -> upgrade/uninstall checks |
| Manifest values | Effective config -> placeholder replacement -> validation/preflight -> rendered YAML -> runtime |
| Database password | Declared source -> existing-volume check -> allowed generation -> Secret -> server and client |
| Route/client | Declaration -> planned change -> pending state -> persistent registration -> import -> owner restart/check -> acknowledgement |
| Volumes | Validated resources -> installed YAML -> durable uninstall plan -> scoped deletion |
| Images | Selected manifests including init-containers -> registry pull/local availability -> archive -> offline load -> availability check |

For each trace, identify the authoritative source, validation point, derived
representations, persistence boundary and deletion behavior. Check that all
consumers use the same effective values. Installed dependency/owner information
must remain usable without the original source catalog or sibling release.

## 4. Review removal and failure paths

- The selected release's registration set is authoritative for that component.
  Removing a route/client must update active indexes/imports; omission of an
  unrelated component from the source catalog must not delete its registrations.
- Persist required owner work before writes/deletions can hide its necessity.
  Retry in a fresh process with the same persistent state, including after
  import-write, service-restart and subsequent-check failures.
- Reject invalid declarations before side effects whenever validation does not
  require generated bytes. Do not promise rollback of arbitrary I/O failures or
  delete existing credentials as cleanup.
- Preserve config, credentials and database volumes on ordinary uninstall.
  With --delete-data, remove only the selected component's relevant state/data.
- Preserve a validated uninstall plan after rendered YAML is removed; already
  deleted volumes may be absent on retry, but inspection errors still fail.
- Refuse conflicting retry flags/operations clearly. Never acknowledge or remove
  another operation's pending work.

| Registration change | Extra owner restarts |
| --- | --- |
| None, with no pending work | None |
| Route only, including removal | Route owner |
| Client only, including removal | Client owner |
| Both | Both owners |
| Pending work from a prior failure | Owners with unfinished work |

These are additional registration-owner actions, not a claim that the selected
application never restarts. Sibling applications must not restart as a side effect.

## 5. Assess evidence, including the tests themselves

Review shared assumptions between tests and implementation. A mock accepting any
volume name does not verify that the correct volume was inspected. Tests repeating
only shipped component names cannot demonstrate configurable names. Assert the
arguments and state transitions relevant to the contract, not just exit status.

| Evidence | What it establishes |
| --- | --- |
| Unit/product tests | Validation, planning, command arguments, file changes and injected failure/retry behavior |
| Acceptance-harness tests | Scenario wiring, assertions and failure reporting |
| Real acceptance runs | Actual Podman/systemd, mounts, init-containers, proxy, OIDC, database and persistence behavior |

Run `python3 -B tests/run.py platform --isolate` for platform coverage without
application source or shipped component declarations; `demo` covers shipped apps
and `all` runs both groups. See tests/README.md for offline prerequisites.

Use fresh isolated fixtures, and fresh processes for retry coverage. Add focused
regressions for fixed defects. Component-model work also requires runnable real
acceptance scenarios for renamed apps, not just renamed fixture strings. Implement
and document scenarios even if the current agent cannot run the lab. Record exact
commands/prerequisites and mark unexecuted scenarios as outstanding. Never reset
unrelated environments.

Use existing project test and CI conventions for appropriate automated gates.
State which checks actually ran, with results and scope. Do not claim green CI,
real container verification or new enforcement merely because a guide was added.
Keep historical lab evidence clearly separate from current results.

## 6. Mandatory understandability review

For implementation work, explicitly review the final affected flow separately
from automated checks. A moderately experienced Python developer should be able
to answer these questions without reconstructing hidden conventions:

1. Where does the authoritative component/config model come from, and what
   metadata is derived for bundles and installed state?
2. What is validated before writes, generation or host actions? Which checks
   necessarily require generated bytes?
3. Which functions decide the work, and which perform side effects?
4. Why is their order safe, and when is completion recorded?
5. What durable state lets a new process resume after each failure boundary?
6. Which behavior is explicitly demo/application-specific, and why?

Trace one successful operation and one failure/retry relevant to the change,
naming functions and state ownership. Prefer small named functions, explicit data
and ordinary control flow. Comments should explain why constraints/order matter.
Keep the current module structure as a starting point. A small helper can be
justified by readability; a plugin system, class hierarchy or generic transaction
engine is not required by the current findings.

If many mode flags, parallel models or indirect special cases accumulate, reassess
and simplify before continuing. Report simplifications and justify remaining
complexity. Passing tests alone does not complete this review.

## Delivery and maintenance

For each change report: relevant contracts, findings/fixes, meaningful regression
evidence, understandability outcome, and remaining gaps. Mark non-applicable
areas briefly rather than inventing work. Do not fix unrelated backlog items as
incidental scope expansion. Documentation-only work needs consistency/link checks
and git diff --check, not runtime tests merely to satisfy this template.

When closing a known gap, update its status/reference here and in the backlog,
linking to actual verification where available. Keep contracts here as the shared
source; backlog items add task-specific requirements instead of copying this
guide wholesale. Update tests and existing CI gates as implementations land.
