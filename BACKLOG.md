# Backlog

Use [the review guide](docs/REVIEW_GUIDE.md) for product contracts, lifecycle
review, evidence levels and the required understandability check. Follow
[AGENTS.md](AGENTS.md) when implementing or reviewing these tasks.

Planned work, not implemented behavior. Each item requires separate implementation
and verification. Item numbers are stable references, not execution priority.
The recommended implementation sequence through item 1 is complete. Remaining
items retain their individual scopes below; agree the next priority separately.

## Current priority (updated 2026-10-30)

[Item 76](#76-reach-the-public-origin-from-containers-when-the-host-maps-it-to-loopback)
**has completed its requested lab scope** at `e99c6be` (2026-10-30).
The replacement uses the bundled `base_hosts_file = "none"` / `no_hosts =
false` override without editing user config: focused whoami **46/46** and
normal **125/125**, both CLEAN PASS, plus operator-reported DEV/PROD
localhost, host-loopback, sign-in and restoration checks. The normal run's
product suite passed **592 tests**. DEV direct restart must select the same
hosts-policy override as startup; the first manual attempt failed without it.
The earlier six-scenario 472/472 matrix belongs to the old `--no-hosts`
implementation. [Results, failed attempt and scope](acceptance/PUBLIC-ORIGIN-HOSTS.md#localhost-correction-lab-results-2026-10-30).

[Item 77](#77-make-a-component-intuitive-to-write-env-files-mounts-and-shared-secrets)
makes components intuitive for developers who do not read documentation.
Direction decided on 2026-10-29 after an [independent analysis](docs/COMPONENT-MODEL-ANALYSIS.md):
phase 1 is `env/<container>.yaml` with short, declared secret references and a
working example component for the organisation's SPA/.NET architecture, on top
of today's lifecycle. Phase 0's design ([COMPONENT-ENV-DESIGN.md](docs/COMPONENT-ENV-DESIGN.md)) is signed off and the walkthrough dropped; phase 1 can follow item 76's completed requested lab scope.

[Item 72](#72-register-api-resource-secrets-with-identity) was requested by
the product owner on 2026-10-28 while converting the organisation's
.NET backend: an API backend and Identity must hold the same API resource
secret. **Its requested lab scope is complete** at `fd99d31` (2026-10-28):
`whoami-fd99d31` passed all 46 steps and `normal-fd99d31` all 125 steps,
including their final audits. Real Duende introspection, private registration
modes/checksums, one-install rotation, trailing-newline refusal, empty Identity
Secret and uninstall with app2 sign-in passed. The five remaining fixed scenarios
subsequently passed at `0ece0c1` (347/347 steps), including the corrected Identity
baseline and renamed product; [matrix evidence](acceptance/API-SECRETS-MATRIX-20261029.md).
Optional API-secret interruption/retry remains untested. [Lab results and remaining gaps](acceptance/WHOAMI-DOTNET.md#backlog-72-api-secret-lab-verification-2026-10-28).

[Item 71](#71-add-a-net-and-typescript-demo-app-that-signs-in-through-duende)
**has completed its lab scope**: run `whoami-7b32621` at
`7b326213ea40466319eff3dd9a54fd23f95fedcb` finished **CLEAN PASS**, all 46 steps,
including `11-prod-audit` with the shared journal-reader fix. The six conversion
points, issuer/log review rules and one saved session across service restart
and PROD reboot passed. [Complete lab evidence](acceptance/WHOAMI-DOTNET.md#complete-audit-fix-lab-run-2026-10-27).
[Item 70](#70-provision-a-components-ca-trust-chain-from-the-environments-pki)
remains verified; the focused run repeated its subPath and trust-chain controls.
The renamed regression at `43dd0dd` remains **CLEAN PASS**. The optional normal
scenario was skipped at `7b32621`; no fixed-matrix verification of the shared
audit fix is claimed for that commit. Historical `45fdb17` and `43dd0dd` reports
remain unchanged. Work outside item 71's completed lab scope includes the real
backend, two-level CA, Duende post-logout redirect, session revocation, and app3
integration into the fixed matrix.

Item 64 is the highest-priority next operator deliverable: unblock a fresh
rootless production installation as an existing login user with almost no home
space, keeping product files under a separate `/var/lib/<product>` root.
Implementation and local regressions are delivered on
`claude/friendly-mendel-8u3bqs` (built on the item 54 branch); merged to `main`;
the full OL9 matrix passed CLEAN on `5b8ab69`. A manual install as `produser`
over ssh without sudo worked on 2026-10-23 after adding a persistent journal,
but needed extensive help: the operator found host preparation incomprehensible
([verification](acceptance/PRODUCTION-LAYOUT.md#manual-run-as-produser-over-ssh-2026-10-23)).
Next: item 65 (one-command host preparation and a short guide), then 66
(install sets) and 67 (ssh acceptance scenario).
Coordinate with item 54's protected release/trust work; integrate that security
boundary before real installation, rather than implementing a second release
helper or publishing service-writable trusted code. Item 64 precedes the other
open feature work and includes a short, verified production installation guide.

Item 61 is done: local tests and both normal/renamed real lab runs passed at
`52f28e4` (2026-10-22). No renderer defect is established;
the private migration image/entrypoint still needs operator-side diagnosis.
See [the runnable probe and safe diagnostics](acceptance/INIT-SECRET.md).

Items 56 and 57 are done: implemented with local tests and a clean real lab
matrix (`t10`, `cda22e7`). They followed the operator's 2026-10-21 order:
component-specific dev overrides, then portable references to bundled component
files. They unblock the organisation's migration/seed setup without leaking
component-specific declarations into global dev config. Item 46 is done: implemented with local regressions and
a clean real lab matrix (`t11`, `3a54714`; [verification](acceptance/PREPARE-HOST.md)). It prevents privileged host-home
operations through service-user-controlled paths. Items 33 and 34
from the earlier best-practice review are done. Item 44 remains the leading
runtime-verification priority for the organisation's PFX-based Identity image.
Item 54 follows item 46 for release trust and supplies the security boundary
for urgent item 64; implementation is on `feature/protected-releases`, with
review and the full OL9 matrix still pending. Item 63 (operator request) then
parameterises image versions through build-time `config/images.yaml`.
Item 62 is implemented with local regression coverage for misplaced container
fields ([verification](acceptance/MANIFEST-STRUCTURE.md)). Item 59 is implemented
with local regression coverage and the 2026-10-24 CLEAN PASS lab matrix:
consistent Quadlet markers and early validation
([verification](acceptance/QUADLET-TEMPLATES.md)).
Item 60 is implemented and lab-verified in that matrix: the CLI wrapper is `deploy.sh`
([verification](acceptance/CLI-WRAPPER.md));
items 48/49 then cover proxy ingress trust and logging; item 50 is
lower-priority production hardening. Item 42 remains before item 3; implementation and
verification statuses are recorded below.
The order for an offline production deployment of an organisation's own apps:

1. [Item 64](#64-support-new-rootless-installations-outside-the-login-home):
   highest priority for the operator's next production test; existing arbitrary
   user, small home bootstrap file, all product state/storage under a separate
   installation root. New installations only; coordinate release safety with 54.
2. [Item 61](#61-verify-secret-derived-environment-values-in-init-containers):
   done; local tests and real generated-Secret init-process delivery passed in
   normal and renamed lab runs at `52f28e4`.
3. [Item 56](#56-add-component-specific-dev-configuration-overrides): high priority;
   done; lab matrix `t10` clean at `cda22e7`. Isolate each component's dev
   settings in its own optional `config.dev.yaml`.
4. [Item 57](#57-add-portable-references-to-bundled-component-files): high priority;
   done; lab matrix `t10` clean at `cda22e7`. Use one explicit file reference
   in source/dev and an isolated offline release,
   without hand-editing release paths. Separate from the override-layer change.
5. [Item 46](#46-prevent-root-host-preparation-from-following-service-user-symlinks):
   done; lab matrix `t11` clean at `3a54714`. Protect the
   root/service-user boundary on repeated host preparation; high priority,
   conditional on an attacker controlling the service account.
6. [Item 54](#54-keep-root-release-verification-and-trust-off-service-writable-paths):
   keep root checksum, fapolicyd trust and config edits off release/data paths
   the service user can replace; after item 46.
7. [Item 63](#63-parameterise-image-versions-with-build-time-variables): high priority
   (operator request); `@@NAME@@` in image references (versions and the
   registry, e.g. Artifactory) from `config/images.yaml` and
   `@@COMPONENT_VERSION@@`, resolved at build; literal tags in releases;
   refuse equal-version releases with different images. After item 54.
8. [Item 62](#62-reject-misplaced-container-fields-in-manifest-validation): implemented;
   reject valid YAML with container fields at the wrong structural level,
   starting with `spec.env`; after item 54 and before item 59.
9. [Item 59](#59-standardise-quadlet-placeholder-syntax): implemented;
   use `@@UNIT_NAME@@` / `@@PRODUCT_NAME@@` with explicit internal values and
   early validation; after item 54.
10. [Item 60](#60-rename-the-cli-wrapper-to-deploysh): implemented;
   use `deploy.sh` consistently in source, bundles, callers,
   tests and documentation; after item 59.
11. [Item 48](#48-validate-public-hosts-and-proxy-header-trust):
   reject unexpected hosts and prevent client-supplied forwarded headers from
   controlling Identity's request host; before wider production exposure.
12. [Item 49](#49-define-safe-proxy-logging-for-authentication-and-api-requests):
   verify and address sensitive URL parameters in access/error logs, including
   upstream failures; preserve useful operational diagnostics.
13. [Item 44](#44-generate-optional-pfx-signing-credentials-in-dev-and-production):
   opt-in PFX generation from retained or own-PKI signing credentials in dev and
   production, external files taking precedence; unblocks the organisation's
   Identity image.
14. [Item 41](#41-build-secret-and-configmap-values-from-templates-at-install-time): Secret
   values (connection strings) and ConfigMap values built from several
   placeholders at install time (done; six-scenario matrix CLEAN PASS 2026-10-19).
15. [Item 43](#43-separate-reusable-platform-tests-from-demo-application-tests):
   a platform test suite that runs without the demo apps, so an organisation
   using only external images can verify the platform it deploys. Before item
   40, whose fixture changes it then only has to make once (done; lab-verified
   with `t6-*` on `b3f3cf1`).
16. [Item 45a](#45-production-pki-from-the-certificate-provisioning-tool):
   configurable production CA name and lifetimes in the certificate script
   (small; after item 44; done, lab-verified with `t6-*`). 45b (delivery to
   targets) and 45c (renewal and expiry, after item 39) are planned separately.
17. [Item 38](#38-sign-bundles-so-the-target-can-authenticate-them): signed
   bundles, beside the existing checksums (done; verified in every lab run 2026-10-19).
18. [Item 39](#39-show-the-installed-components-and-versions-on-the-target): implemented
   locally; `./deploy.sh status [--json]` shows installed versions, unit states and
   pending work ([verification](acceptance/STATUS.md)).
19. [Item 40](#40-one-version-file-per-component-in-its-own-directory): one
   `components/<id>/VERSION` per component; the root version files go.
   Done; lab-verified with `t6-*` on `b3f3cf1`.
20. [Item 42](#42-explain-client-registration-and-import-volumes-in-the-architecture-diagrams):
   documentation of client registration and import volumes; before item 3,
   which refers to its list of durable registration state.
21. [Item 3](#3-database-backup-and-credential-recovery-procedures): tested
   backup and recovery of databases and credentials.
22. [Item 2](#2-postgresql-password-rotation): PostgreSQL password rotation.
23. [Item 37](#37-document-and-protect-credential-copies-at-rest): credential
   copies at rest and Identity key protection (with items 2 and 3).
24. [Item 47](#47-refuse-unsafe-permissions-on-retained-generated-secrets):
   reject unsafe retained generated-secret permissions; low-priority hardening,
   coordinated with item 37 rather than blocking the status command or lab run.
25. [Item 35](#35-run-demo-apps-with-a-database-role-that-is-not-a-superuser):
   a database role that is not a superuser (a pattern for products too).
26. [Item 36](#36-harden-the-demo-application-containers): container hardening
   with secret file modes.
27. [Item 50](#50-define-configurable-production-proxy-limits-and-security-headers):
   lower-priority production hardening: bounded request rates/connections and
   compatible response-header policy, with explicit proxy/application ownership.
28. [Item 22](#22-one-scoped-mutation-testing-round-for-the-riskiest-deployment-decisions):
   one mutation-testing round before the larger DR change.
29. [Item 24](#24-optional-disaster-recovery-dr-adapted-from-podman_test):
   optional DR, after 2, 3 and 37; on its own branch.
30. [Item 51](#51-add-an-optional-grafana-and-loki-logging-demo): low-priority
   demo extension with PostgreSQL logs, maintained collection and a basic
   Grafana view; full SQL logging is opt-in. Does not block DR or core work.
31. [Item 52](#52-add-optional-prometheus-metrics-after-the-logging-demo):
   low-priority follow-up to item 51: container/pod CPU and memory plus backend
   request rates, latency and errors; GraphQL details require app instrumentation.
32. [Item 53](#53-upgrade-app1-with-an-actually-changed-application-image):
   focused acceptance coverage of an app1-only release with a rebuilt application
   image; schedule with acceptance improvements, independently of observability.
33. [Item 55](#55-add-an-explicit-component-scoped-dev-reset): explicit
   `dev/dev.sh reset <component> --delete-data` and `reset --all --delete-data`
   for disposable dev data; whole-dev mode removes local dev Secrets and volumes
   for a fresh start. Not automatic database recovery or a production blocker.
34. When needed: item 5 (verification gaps: a real Python 3.6 run, new Podman
   versions), item 7 (other PostgreSQL layouts), item 6 (unchanged .NET images,
   scope decision first) and item 30 steps 3-4.

## Status overview (2026-10-19)

Done and verified on real VMs (rootless Podman 5.8.2, fapolicyd, SELinux
Enforcing): items 1, 8, 9, 12, 14–21, 23, 25–29, 31–34, 38, 40, 41, 43, 45a. Their behaviour is
exercised by every run of the six-scenario acceptance matrix (demo with app1 or
app2 first, help only, Identity upgrade, platform with help, renamed product
`shop`); the latest matrix, `t6-*` on `b3f3cf1` (2026-10-19), was CLEAN PASS in
all six scenarios on a single commit. Item 30 (faster
runs) is done up to its optional steps 3-4.

Partly verified: item 10 (the test baseline runs in every lab run as
`03-unit`; the historical 0.2.0 upgrade lives in item 5) and item 13 (normal
lifecycle on real hosts; failure injection only in fresh local processes).

Update 2026-10-21: items 56 and 57 are implemented and locally tested; real runtime
checks are pending ([56](acceptance/COMPONENT-DEV.md),
[57](acceptance/COMPONENT-FILES.md)). Platform signing tests are blocked by the
local environment's GPG socket restriction; see the verification reports.

Update for item 46 (2026-10-22): done; lab matrix `t11` clean at `3a54714` after three lab
fixes ([verification](acceptance/PREPARE-HOST.md)).

Update for item 61 (2026-10-22): done; normal and renamed lab runs at `52f28e4`
both CLEAN PASS ([evidence and scope](acceptance/INIT-SECRET.md#completed-real-lab-verification-2026-10-22)).

Items 70 and 71 are removed from the open list for their documented lab scope.
Item 71's complete `whoami-7b32621` run passed all 46 steps, including the shared
audit fix and final audit. [Evidence and remaining work outside that scope](acceptance/WHOAMI-DOTNET.md#complete-audit-fix-lab-run-2026-10-27).

Item 72 is removed from the open list for its requested lab scope at `fd99d31`;
[the report](acceptance/WHOAMI-DOTNET.md#backlog-72-api-secret-lab-verification-2026-10-28) records the unsupported DEV harness interpreter and untested extensions.

Item 76 is removed from the open list for its requested lab scope at `e99c6be`;
DEV restart requires the explicit hosts-policy environment described in its report.

Open: 77 (phase 0 signed off; item 76's requested lab scope complete), 64 (urgent; on main, OL9 matrix clean, manual run worked with help; usability via 65), 65 (implemented; lab passed), 69, 66 and 67 (high priority, in that order; 69 settles paper-first requirements before 66's commands), 68 (human verification before customer readiness), 54 (on main, OL9 matrix clean; Python 3.6 and integrity strategy pending), 63 (high priority, after 54; 59 and 60 implemented locally), 48, 49, 44, 45b, 45c, 42, 3, 2, 37, 47, 35, 36, 50, 22, 24, 51 and 52 (low priority), 53, 55, 5, 7, 6, and
item 30 steps 3-4.
Also open, priority not assigned: [75](#75-make-python-lifecycle-code-easier-to-follow-diagnose-and-change)
(Python lifecycle understandability; coordinate with 69 and 73–74).

Earlier per-item verification reports stay linked from each item:
[credential paths](acceptance/CREDENTIAL-PATHS.md),
[retry](acceptance/RETRY-SAFETY.md),
[deploy refactor](acceptance/DEPLOY-REFACTOR.md),
[credential delivery](acceptance/CREDENTIAL-DELIVERY.md),
[layout cleanup](acceptance/LEGACY-CHECK-CLEANUP.md),
[file sources](acceptance/FILE-SOURCES.md),
[proxy](acceptance/NGINX-YAML.md), [app1 init](acceptance/APP1-INIT.md),
[declarative components](acceptance/DECLARATIVE-COMPONENTS.md),
[Identity](acceptance/IDENTITY-SPLIT.md) and
[platform](acceptance/PLATFORM-RENAME.md).

Item 15 removes historical layout refusal checks; the earlier task descriptions
and reports retain their original scope and are not current requirements.

The full agent task descriptions for items 8, 9 and 10 are preserved below, with
heading levels adjusted for this document. The later clarification in item 9
supersedes item 8's bundled-platform assumptions: platform is to be a separate
bundle with explicit dependencies, and app bundles must not embed it. Do not
reintroduce the older bundle model while renaming. Inspect the actual repository
baseline before implementation; these tasks are not claims of completed work.

The refactor must preserve the behavior and naming established by items 8 and 9;
its original core terminology below is historical scope, not an instruction to
restore core or merge Identity back into platform.

## 77. Make a component intuitive to write: env files, mounts and shared secrets

Status: **planned; direction decided 2026-10-29; phase 0 design
([COMPONENT-ENV-DESIGN.md](docs/COMPONENT-ENV-DESIGN.md)) signed off by the
product owner on 2026-10-29; the developer walkthrough was dropped by the
product owner the same day; item 76 is complete; the specification's second
independent check (2026-10-30, two blocking and five minor findings) is
corrected in the specification. Implemented 2026-10-30 with product/unit and
harness tests ([change, evidence and lab check](acceptance/COMPONENT-MODEL-77.md)).
The first implementation is verified on real Podman/systemd 2026-10-30: six
scenarios CLEAN PASS on `0459e5a`; `--renamed-product` CLEAN PASS on `6210670`
after a harness fix. The product owner's later changes below (2026-10-30 and
2026-10-31) have product/unit and harness tests; their lab run is outstanding.**

**Decision (product owner, 2026-10-30, after review of the first
implementation):** config must be in as few files as possible and easy to
understand, and no name or path may appear that no file states. Hence one
config file per component (`ENVIRONMENT` in `config.defaults.yaml` instead of
`env/` files), one secret form (declared `SECRET_FILES` source with its path,
`@@secret:<id>/<key>@@`; the short forms are dropped) and API secrets declared
by the API and named on Identity's line (instead of `@@api-secret:`).
Implemented the same day ([change](acceptance/COMPONENT-MODEL-77.md)).

**Decision (product owner, 2026-10-31):** `upgrade:` and `shares:` are removed.
Every install renders the component again and only a downgrade is refused
(restarting platform or Identity on a same-version reinstall is acceptable).
`PUBLIC_ORIGIN` and `HTTPS_PORT` are set only in the gateway's `config.yaml`
and read from there; other components hold no copies.
`config/common.defaults.yaml` is gone from the demo (its values are platform's
defaults). Implemented the same day ([change](acceptance/COMPONENT-MODEL-77.md)).
Also on 2026-10-31: `requires` is removed and `components` is a plain list of
IDs; only what is needed now is implemented, and an explicit dependency
between two applications can be added back when a product needs it.

**Simplification candidates (assessment 2026-10-30, not decided):** each
config type was checked for whether it can go.

| Config | Assessment |
| --- | --- |
| `bundles.yaml` `product`, `gateway`, `identity`, component list | Keep: each is one decision no file can derive. |
| `upgrade:` | Removed 2026-10-31: refuse downgrades, every install re-applies config. |
| `requires:` | Removed 2026-10-31: not needed now; `components` is a plain list. |
| `shares:` and copied `PUBLIC_ORIGIN`/`HTTPS_PORT` | Removed 2026-10-31: the two public settings are read from the gateway's `config.yaml`. |
| Hand-written settings ConfigMaps (app1, app2, platform `10-configmap.yaml`) | Can go: move to `ENVIRONMENT`, so settings have one form. No decision needed. |
| `SECRET_TEMPLATES` | Can leave the authoring model: no component writes it any more; `ENVIRONMENT` covers environment variables. The remaining case is a templated secret *file* (for example `bootstrap.sql`). Needs a decision whether that case is needed. |
| `config/common.defaults.yaml` | Removed from the demo 2026-10-31; the optional layer stays in code for products that want it. |
| `components/<id>/config.dev.yaml` | Probably can go: only app1 uses it (demo layer marker, dev SQL sample); `config/dev.yaml` stays for machine-specific values. |
| `client.yaml` `environment:` plus `APP_ID`/`BASE_PATH` in the manifest | The same id and path are written twice and compared. Can be written once: `ENVIRONMENT` lines `APP_ID: '@@CLIENT_ID@@'`, `BASE_PATH: '@@CLIENT_BASE_PATH@@'` filled from `client.yaml`, without the compare. |
| `route.conf`, `client.yaml` (id, path, scopes, certificate), `VERSION`, `files/`, manifests | Keep: each holds facts nothing else has. |
| Operator `config.yaml`, credentials | Keep: one file per component with only settings and secret sources. |
| Registration volume names `<gateway>-routes`, `<identity>-clients` in manifests | A naming rule; the error names the exact volume. Writing them elsewhere would add config. |

**Scope decided 2026-10-29 (replaces phases 1–5 for now):** the simple catalog
(`gateway:` and `identity:` plus a plain component list; routes, public
settings, receivers and their dependencies derived from files, without
reading manifests), API secrets written as `@@api-secret:<component>@@` on
both sides instead of item 72's `api.yaml` (same mechanism underneath; the
installed Identity's descriptor holds the API-to-index mapping), `env/<container>.yaml`,
the short `<id>: generate` declaration and secret reference
and a checklist, specified in [COMPONENT-SMALL-VARIANT.md](docs/COMPONENT-SMALL-VARIANT.md)
after an [independent review](docs/COMPONENT-SMALL-VARIANT-REVIEW.md). The
product owner deliberately drops three rarely used product shapes (that
specification, section 2.4). Everything else in this item stays deferred. Requested by the product owner after converting the
organisation's .NET/TypeScript solution in dev. The first draft was reviewed by
an independent analysis; the decisions, corrections and revised phases below
replace that draft's proposal. "Today" describes the code at `5f4b499`.

Independent assessment: [Component model analysis](docs/COMPONENT-MODEL-ANALYSIS.md).

### Why simplicity is a requirement here

The people who write and change components are application developers and
integrators converting existing Kubernetes/docker-compose solutions, not the
platform's authors and not AI agents. They do not read documentation first;
they copy something that looks right, change names and expect it to work. A
model is only good enough if such a person can **guess** where a setting goes,
what a line does and why something failed, from the files alone.

This matters for concrete reasons:

- **Errors surface late and far from the cause.** In the dev conversion every
  mistake showed up as a browser or token error (CSP, 404, `invalid
  redirect_uri`, `IDX10204`), never at the line that caused it. Each one took a
  long guided diagnosis. A model with fewer places and fewer coupled values
  produces fewer such errors.
- **Values that must agree in several places drift.** The conversion met
  `PUBLIC_ORIGIN` versus hand-built `DNS_HOST.DNS_DOMAIN` URLs without the port,
  an API resource whose name (ConfigMap) and secret (Secret template) must
  share an index, the same API secret copied into two components, and a web
  certificate for an older name. Every duplicated fact is a future outage.
- **The platform is only adopted if conversion is cheap.** If converting one
  backend needs an expert session, teams will not move further applications.
- **Simple models are easier to verify.** Fewer mechanisms mean fewer
  lifecycle paths to test, review and keep correct (see the review guide's
  understandability rules).
- **Operators mostly do not see this**: they never edit `bundles.yaml`,
  manifests or templates. They do see supplied secrets and restarts, so every
  such step must stay explicit in the manual and in install-set messages.

Rule for this item and its follow-ups: **one fact in one place, written where a
developer would look for it, with the platform deriving everything else and
explaining what it derived.** Prefer conventions over repeated declarations,
keep the one declaration that carries a decision (who owns a secret, how it is
obtained), and refuse ambiguity loudly instead of guessing silently.
Simplicity must not remove a safety check: the analysis showed that several
shortcuts in the first draft would have bypassed existing protections.

### What a component author handles today

For the organisation's `myapp` (backend + frontend + database) behind the
proxy, signing in through their Duende (`myidentity-server`):

| Concern | Where it is written today |
| --- | --- |
| Membership, order, dependencies | `bundles.yaml`: entry, `requires` |
| Same public address as the proxy | `bundles.yaml`: `public_from: platform`; owner's `shares` |
| Proxy routes | `route.conf` **and** `bundles.yaml`: `routes: platform`; owner `accepts.routes` |
| Public environment values | hand-written ConfigMap manifest with `@@NAME@@`, plus `configMapRef`/`env` in the Pod |
| Values for placeholders | `config.defaults.yaml`, `config.dev.yaml`, `config/dev.yaml`, production `config.yaml` |
| Secret environment values | `SECRET_TEMPLATES` in `config.defaults.yaml`, plus `secretRef` in the Pod |
| Secret sources | `SECRET_FILES` (path, `generate`), files under the config folder |
| Templated files (e.g. `bootstrap.sql`) | inline text in `SECRET_TEMPLATES` plus a Secret volume and `volumeMount` |
| API secret shared with Identity | `SECRET_FILES` + `SECRET_TEMPLATES` + `api.yaml` (`index`, `secret`, `hash`) + `bundles.yaml` `apis:` + owner `accepts.apis` + owner `envFrom` (item 72) |
| Identity's API resource names | Identity's ConfigMap, at the same index as `api.yaml` |
| Trusting the environment's CA | `SECRET_FILES` + Secret volume + two `subPath` mounts + copying `ca.crt` (item 70) |
| Pods, images, volumes | Pod/PVC manifests |

Observed in the dev conversion (2026-10-28/29, operator-run, not lab results):
each issue above needed a long guided diagnosis; none was a platform defect
except the `/etc/hosts` gap addressed by item 76.

The table shows the organisation's full multi-container case, not the minimum
for every component. Several rows have simpler existing alternatives (direct
`env.value`, `secretKeyRef` without a recipe, `component_file`); see the
analysis, section 2, for the row-by-row corrections.

### Decisions (product owner, 2026-10-29)

Taken after the [independent analysis](docs/COMPONENT-MODEL-ANALYSIS.md), which
found real errors in the first draft of this item (corrected below). The
product owner follows the recommendations recorded here:

1. **First goal:** make environment and file wiring simple to write while
   keeping today's lifecycle underneath (ownership, retention, registrations,
   pending/retry). Success means a developer can copy the example component and
   adapt it without reading the full component manual.
2. **Recipes belong to the release, values to the operator.** `env/` and
   `mounts/` ship with the component and change only with a new release; the
   operator owns the values in `config.yaml`. Persistent config is never
   silently re-merged.
3. **Secrets are declared once, referenced briefly.** The source and its policy
   (generated, or supplied by the operator) are declared in one place; `env/`
   and `mounts/` refer to it by a short name; an unknown name is refused before
   anything is written. A reference never creates a secret by itself.
4. **Ambiguity is refused, never resolved silently:** duplicate container
   targets, the same variable from two sources (generated and hand-written),
   the same mount path twice, and conflicts with hand-written YAML.
5. **The example proves the organisation's real architecture:** a TypeScript
   SPA doing OIDC/PKCE in the browser, a .NET backend validating bearer tokens
   (JwtBearer) and serving GraphQL over HTTP and WebSocket, `route.conf` with
   the needed `rewrite`, and runtime frontend configuration.
6. **The gateway is optional in the platform but used automatically when
   present.** Products with a proxy (all web products) get routes and public
   values from it without per-component lines; a worker-only product stays
   supported.
7. **API secrets keep item 72's contract** (API owns the secret, installed
   membership, per-API `hash`, staged registration, restart order). Only its
   authoring may be simplified later (for example moving `api.yaml` into the
   catalog or deriving it); general product-wide shared secrets are deferred
   until a concrete non-API need exists.
8. **CA trust becomes an explicit, tested opt-in profile per image/runtime**,
   not automatic injection into every container.

### Corrections to the first draft (from the analysis)

- Empty catalog entries already work (`catalog.load_catalog` turns `null` into
  `{}`); there is nothing to remove.
- A mandatory gateway would remove a supported product shape (worker without
  gateway); hence decision 6.
- The PostgreSQL example was unsafe: the platform's database preflight only
  understands `POSTGRES_PASSWORD_FILE` with a Secret mount (`deploy.postgres_binding`),
  which is what lets it refuse a new password against an existing volume. The
  database container keeps that binding; `env/` must not carry its password
  until a replacement resolver is designed and tested.
- The Identity example needs the hashed value for configuration-bound Duende
  resources (as the demo uses) and the scopes. Which form an organisation's
  Identity needs stays a per-API `hash` choice (item 72).
- `@@shared:` as written let a typo silently create a new secret and could not
  tell Identity whether an API is installed or uninstalled; hence decisions 3
  and 7.
- Two PEM files in `/etc/ssl/certs` are not a universal trust interface (.NET,
  Node and Java read different locations); hence decision 8.
- Value rules are not uniform today: templates strip a trailing newline,
  item 72 refuses it, direct file delivery is byte for byte. The new syntax
  must state its exact-byte behaviour.
- `bundle.py` copies a fixed set of component entries; `env/` and `mounts/` must
  be shipped, covered by the authenticated inventory and path-checked.
- Operators are affected after all: supplied secrets, their file locations and
  any update that restarts several components must appear in the manual and in
  item 66's stop/resume messages.
- Setting environment variables on a static-file container does not change
  already built JavaScript. The SPA needs a runtime configuration contract (for
  example an entrypoint that writes `config.json` from the environment), and the
  example must prove it in a browser. The organisation's images already consume
  these variables in Kubernetes; the example must show how.
- The "about six concepts" estimate is withdrawn. The analysis counts roughly the
  same number of concepts with a different granularity; the useful measure is
  how many places hold one fact and how many values must agree, and finally the
  human trial.

### Revised model, first delivery

```text
components/myapp/
  manifests/                       Pods, PVCs (as today)
  route.conf                       proxy locations (as today)
  config.defaults.yaml             values and secret declarations (as today)
  env/backend.yaml                 environment of container "backend"
  env/frontend.yaml                environment of container "frontend"
  mounts/frontend/usr/share/nginx/html/config.json
                                   file at that path in container "frontend"
```

`mounts/` is used because `files/` already holds `component_file` sources.

```yaml
# config.defaults.yaml: declared once (existing SECRET_FILES, policy on the declaration)
SECRET_FILES:
  myapp-database-password:
  - path: credentials/database
    generate: [password]
  myapp-export-key:
  - path: credentials/export          # supplied by the operator; no generate

# env/backend.yaml: short reference to a declared, single-key source
Authentication__Authority: '@@PUBLIC_ORIGIN@@/myidentity-server'
Cors__default__origin__0: '@@PUBLIC_ORIGIN@@'
ConnectionStrings__Default: 'Host=myapp-postgres;Database=myapp;Username=myapp;Password=@@secret:myapp-database-password@@'
```

- `@@secret:<id>@@` is a short form of today's `@@secret:<id>/<key>@@` for a
  source with exactly one key; the long form stays valid. An undeclared `<id>`
  is refused. (Exact syntax to be confirmed in phase 0.)
- `env/<container>.yaml`: values without a secret reference go to a generated
  ConfigMap, values with one to a generated private Secret; both are injected
  into the container of that name (regular or init). Unmatched files, a
  container name used in more than one Pod, and keys also set by hand-written
  `env`/`envFrom` are refused, naming the file and key.
- `mounts/<container>/<path>`: read-only single-file mounts (`subPath`), private
  if the text contains a secret reference. Text only, with size limits; binary
  files, directories and PFX keep `SECRET_FILES`/`VOLUME_FILES`/`component_file`.
- Both lower into the existing validated structures (`effective_documents`
  before database preflight), so existing checks keep applying. One renderer,
  not two.
- `validate` reports the wiring by name (`myapp/backend: 3 settings, 1 secret
  (myapp-database-password)`) and never prints values.
- `SECRET_TEMPLATES` stays as the internal representation and an escape hatch;
  it is no longer the recommended way to write environment or file recipes.

### Revised phases

| Phase | Deliverable | Gate before the next phase |
| --- | --- | --- |
| 0 | Confirm syntax (short `@@secret:<id>@@`, conflict rules, exact-byte rules), write the example component design for the organisation's architecture: [design](docs/COMPONENT-ENV-DESIGN.md), including two demo gaps found (no public SPA client in the demo Identity, SPA runtime config) | Product-owner sign-off of its section 7 (done 2026-10-29); the developer walkthrough was dropped by the product owner |
| 1 | `env/<container>.yaml` with `@@NAME@@` and short/long secret references; bundling and inventory; wiring report; **working example component** (SPA + .NET JwtBearer + GraphQL/WebSocket + `route.conf` + runtime frontend config) | Unit/fixture tests (targets, init containers, conflicts, private classification, no secret reads in `validate`, refusal before side effects, isolated bundle); real OL9 env delivery; **human trial with the example** |
| 2 | `mounts/<container>/<path>` for text files | Podman 5.8.2 ConfigMap/Secret `subPath` tests: non-root UID, SELinux Enforcing, replaced/shortened/removed/renamed files (a reused Podman volume keeps old unlisted files), public-to-private transitions; uninstall without PVC loss |
| 3 | Gateway convenience: when a gateway exists, derive routes and public values; drop `routes:`/`public_from` lines where derivable; keep copied public values and their checks until propagation is designed | Gateway-free and renamed fixtures; custom shared names; cycles; dev overrides; isolated releases |
| 4 | Opt-in CA trust profiles for named images/runtimes (starting with .NET on Linux) | Real application TLS: right chain, missing trust, wrong CA, hostname mismatch, two-level chain, renewal |
| 5 | Simpler authoring for item 72 (catalog entry or derivation instead of `api.yaml`), same contract | Item 72's affected scenarios rerun; general shared secrets only if a concrete need appears, with the analysis's revision/membership requirements |

Phase 1 gives the largest simplification for the least risk; the example is
part of phase 1, not the end.

### Deferred, with the reason

- **Product-wide `@@shared:` secrets:** need ownership, installed membership,
  typo protection, consistent revisions across consumers, rotation with retry
  and cleanup (analysis sections 4–6). Item 72 covers the known API case.
- **Reading gateway values at render instead of copying:** changes production
  config authority and needs a propagation design for installed dependents,
  including `newer-only` and pinned releases.
- **Database password via `env/`:** needs a replacement for
  `deploy.postgres_binding` that keeps the existing-volume refusal.

### Risks still open

From the analysis, kept as requirements for phases 1–2: deterministic generated
names that cannot collide; YAML scalar conversion (quote booleans/numbers);
no secret in parser errors, wiring reports or temporary public YAML; mount
cleanup in reused volumes; file ownership for non-root images; size limits per
file and per resource; descriptor/metadata compatibility for new fields;
interplay with items 66 (stop for supplied secrets, resume) and 69 (package and
authenticate the new files, no secret creation in package scripts).

### Verification

- Unit/fixture tests per phase, including refusal before side effects and no
  secret values in output.
- Acceptance: the fixed matrix and `--whoami` after converting the demo; focused
  negative cases the matrix does not cover.
- Real Podman/systemd checks named in each phase gate.
- **Human trial (required):** a developer who has not seen this discussion
  converts a small .NET/TypeScript service using only the example component
  and checklist. Record time, edits, stops, questions and every error message
  they could not act on; repeat with today's model for comparison. The item is
  not done until the trial shows fewer stops and no help needed for the common
  case. The analysis's code-understandability check (one successful and one
  interrupted operation traced by a Python developer) applies as well.

## 76. Reach the public origin from containers when the host maps it to loopback

Status: **requested lab scope complete** (2026-10-30), tested at
`e99c6be9406f5441fa21ac17ec9db73e813c306c`. Runs
`hosts76-localhost-whoami-e99c6be-20261030T151555Z` and
`hosts76-localhost-normal-e99c6be-20261030T151555Z` finished **CLEAN PASS,
46/46 and 125/125** including audits/cleanup. The normal run passed 592
product tests. Both hosts ran Oracle Linux 9.8, Podman 5.8.2 and SELinux
Enforcing. The operator reported passing DEV/PROD generated-hosts localhost,
public-name DNS/loopback, sign-in and restoration checks.

The earlier `--no-hosts` finding (three PROD containers unable to resolve
localhost) was addressed by the replacement below. The first replacement
manual DEV attempt failed after a direct Podman restart without its override;
filtered logs showed discovery connection refusal and HTTP 500. The corrected
run explicitly propagated the override to the smoke/restart process and
passed. A plain Podman restart without that policy is not covered by the pass.
The original six-scenario 472/472 matrix at `d5e5d70` remains historical,
not verification of this replacement.

The product-owner-approved direction is now `quadlet/containers-hosts.conf`:
`[containers] base_hosts_file = "none"` and `no_hosts = false`, selected by
`CONTAINERS_CONF_OVERRIDE` only on dev `kube play` and through the installed
Quadlet Service environment. Each unit references the immutable copy inside
its own release, with no system/user `containers.conf` writes. The new
internal `@@PODMAN_HOSTS_CONFIG@@` token supplies that path without exposing
component config. `--no-hosts` is removed. The `hostAliases` guard remains a
public-origin DNS policy; its error no longer claims a flag conflict.

All six component patch versions advance because their immutable bundles
include the changed deployment/template/policy files: platform 0.4.13,
identity 0.4.14, app1/app2/help 0.4.12, app3 0.1.2. This also makes the
`newer-only` platform/Identity render the new unit on upgrade. Images and
fixed matrix counts/install orders are unchanged.

[The report and corrected short lab recipe](acceptance/PUBLIC-ORIGIN-HOSTS.md)
retain all earlier attempts and distinguish inspected harness artifacts from
operator-reported manual results. Direct DEV stop/start/restart commands must
select the same `CONTAINERS_CONF_OVERRIDE` as `dev.sh up`; production service
restarts inherit it from the installed unit. Follow-up (2026-10-30): to remove
that hidden rule, `dev/dev.sh restart <pod>...` selects the policy for
`podman pod restart`; README, the whoami smoke documentation and the harness
`dev-whoami-e2e` step use it, with a stubbed-Podman regression test. Dev
scripts are not in bundles, so no component version changes. Harness run
`hosts76-devrestart-whoami-15e1cd6`: CLEAN PASS 46/46, including the real dev
restart (without a host loopback line). No implementation change was
made between the failed and successful manual runs. An automated host-loopback
acceptance step, broader runtime/version coverage and component work remain
separate follow-ups; the other five fixed scenarios were not rerun for this
replacement.

### How containers reach the public origin today

A backend that signs in through Duende calls it server to server through the
public origin, as in Kubernetes (items 70 and 71). Inside the product network
the name resolves to the proxy because of this chain:

1. `PUBLIC_ORIGIN` gives the derived `PUBLIC_HOSTNAME`.
2. `components/platform/manifests/80-proxy.yaml` sets the proxy Pod's
   `hostname: '@@PUBLIC_HOSTNAME@@'`.
3. Podman registers that host name in the product network's DNS
   (aardvark-dns); the name appears in
   `$XDG_RUNTIME_DIR/containers/networks/aardvark-dns/<network>` next to the
   proxy's internal address.
4. Other containers resolve the public host name to the proxy's internal
   address and connect to nginx on `HTTPS_PORT` inside the network.
   `IP_ADDRESS`/`hostIP` affects only the published host port.

This chain is documented in `docs/COMPONENTS.md`; the manual loopback checks
assert DNS/proxy equality. A dedicated automated host-loopback step remains
a follow-up.

### Problem

By default Podman builds each container's `/etc/hosts` from the host's file
(`base_hosts_file`), and `/etc/hosts` is read before DNS. The developer VDI
maps its own name to loopback (`127.0.0.1 <public host name>`) and the operator
cannot edit that file. Every container then resolves the public origin to its
own loopback, the backend cannot fetch the discovery document, and JwtBearer has
no expected issuer: `IDX10204`, `WWW-Authenticate: ... The issuer '...' is
invalid`, with no `IDX20803`. The symptom points at issuer configuration, not at
name resolution, so it took a long diagnosis. The lab matrix never met it: the
lab maps the public name to the VM's real address and tests from DEV with
`CONNECT_IP`, without a loopback line on the installation host.

Observed on the VDI on 2026-10-29 (operator-run, Podman version not recorded;
not a lab result):

- In the backend container the public name resolved to `127.0.0.1` and
  `openssl s_client` got `Connection refused`.
- With `--no-hosts` added locally to `podman kube play` in `dev/dev.sh`, the
  name resolved through aardvark-dns, the TLS connection to the proxy succeeded
  and, after the trust chain (item 70) and a matching web certificate, the
  backend accepted tokens. The browser on the VDI still used the host's
  loopback line and `IP_ADDRESS: 127.0.0.1`.

Two follow-up traps met in the same session:

- `dev/generate-certificates.sh` keeps an existing web certificate, so after a
  `PUBLIC_ORIGIN` change the proxy still presents the old name (`openssl`
  `num=62: hostname mismatch`) until `web.crt`/`web.key` are removed and issued
  again.
- `openssl s_client` inside a container does not use trust-chain files mounted
  under `/etc/ssl/certs` by name (it needs the bundle or hashed names), so it
  reports `num=20` although .NET trusts the chain; test with `-CAfile`.

### Tasks

1. Choose the mechanism so that a host `/etc/hosts` entry for the public name
   never reaches the containers, while localhost is generated independently
   of the host's DNS, in dev and production alike. The original `--no-hosts`
   passed public-origin checks but failed localhost in three PROD images.
   Verify the replacement override on Podman 5.8.2 and generated Quadlet
   services, including inherited settings, the override's installed path,
   generated localhost entries and exclusion of the host loopback mapping.
   Do not change normal user/system Podman configuration.
2. Document the chain above in COMPONENTS.md next to the trust chain recipe:
   containers reach the public origin through the proxy's host name in the
   product network; `IP_ADDRESS` only publishes the host port.
3. Warn in `validate`/`prepare` when the web certificate does not cover
   `PUBLIC_HOSTNAME`, and document re-issuing it after a `PUBLIC_ORIGIN` change
   (or let the dev credential tooling re-issue a certificate whose name no
   longer matches).
4. Add the `openssl ... -CAfile` check and the `IDX10204` symptom to the
   trust-chain troubleshooting text.

### Verification

- Unit/fixture tests: the rendered dev command and the Quadlet unit carry the
  chosen option; the certificate-name warning.
- Acceptance: on the installation host, add `127.0.0.1 <public host name>` to
  `/etc/hosts`, install, and show from a backend container that the name
  resolves to the proxy's internal address and that app3's public-HTTPS sign-in
  passes; remove the line afterwards. Run in dev and in the production layout.
- Report Podman version, SELinux mode and whether any shipped component
  changed behaviour without host entries.

## 72. Register API resource secrets with Identity

Status: implemented; requested lab scope completed at `fd99d31` (2026-10-28).
Focused whoami **CLEAN PASS (46/46)** and normal matrix **CLEAN PASS (125/125)**;
supplemental real rotation, newline refusal and uninstall checks passed.
Images compiled and 572 product tests passed. All 358 harness tests passed on
the supported controller; the attempted DEV Python 3.9 run failed (34 errors,
4 failures), as recorded in the report. Requested by the product owner while
converting the organisation's .NET backend; direction and open decisions were
settled on 2026-10-28. [Lab evidence, scope and gaps](acceptance/WHOAMI-DOTNET.md#backlog-72-api-secret-lab-verification-2026-10-28).

Remaining matrix on `main` (`58240ea`, code as `fd99d31`): `m72-identity`
(`--identity-only`) was **NOT CLEAN** at `03-dev-up`, a harness defect, not a
product defect. `acceptance/identity_template_baseline.py` restored Identity
0.4.11's files but kept the current catalog, where Identity accepts `apis` and
app3 registers one, so `validate` refused the unused `identity-apis`. Such a
catalog never existed: 0.4.11 accepted no API registrations. The baseline now
also drops `accepts.apis`, every `apis` role and their `api.yaml`, so the
scenario models the real old release and then exercises the upgrade to an
Identity that accepts `apis`. Reproduced and fixed locally on a clone with the
pinned baseline (`validate` and `prepare` pass); harness regression in
`test_secret_templates.py`. The five remaining scenarios subsequently passed
on 2026-10-28 at `0ece0c1`: `m72c-identity` 66/66, `m72c-renamed` 57/57,
`m72c-app2` 125/125, `m72c-help` 60/60 and `m72c-platform-help` 39/39,
all **CLEAN PASS**, including final audits. [Results recorded 2026-10-29](acceptance/API-SECRETS-MATRIX-20261029.md).
The earlier failed run is not relabelled; no normal app1-first or focused whoami
rerun at this commit is claimed.

### Problem

The organisation's Duende Identity defines one API resource per API backend and
reads each secret from its environment, for example
`ApiResources__0__ApiSecrets__0__Value` and
`ApiResources__1__ApiSecrets__0__Value` (a second application). Each API
backend receives the same value as `Authentication__ApiSecret`. In the original
Kubernetes installation one Secret (`appSecrets`) feeds both sides, so the two
values cannot drift.

Here a secret belongs to one component:

- Secret IDs must start with the component ID, so one declaration cannot serve
  Identity and an API component.
- `SECRET_FILES`/`SECRET_TEMPLATES` cannot be shared, and the config layers
  replace whole top-level values, so `config/common.defaults.yaml` is no place
  for a shared declaration either. Secret values never live in config anyway,
  only the files they are read from.

The only way today is for the operator to put the same value into a file under
each component and keep them equal by hand. Nothing checks that they match; a
mismatch shows only as an authentication failure at runtime. A missing secret
went unnoticed in the dev conversion because neither side reported it as a
configuration error. (That conversion also met `IDX10204`, a missing expected
issuer; whether the missing API secret caused it is not established.)

### Goal

One source of truth per API secret: the API component delivers or generates its
secret, Identity receives every registered API secret, and a mismatch or a
missing secret is refused before anything is written, in dev and production.

### Chosen direction (2026-10-28)

Keep it as simple as possible: **the API component owns its secret and the
platform copies it to Identity.** No product-wide secrets and no manual copies.
It reuses two existing mechanisms: per-component secrets and registrations like
`clients` ([COMPONENTS.md](docs/COMPONENTS.md#registrations-routes-oidc-clients-and-api-secrets)).

```text
myapp (owner of the secret)          identity (receives it)
SECRET_FILES: myapp-api-secret  -->  Secret identity-apis
  generate: [value]                    ApiResources__0__ApiSecrets__0__Value
        |                                     | envFrom
        v                                     v
Authentication__ApiSecret            Duende reads ApiResources__0__...
(always the same value)
```

What the product writes:

1. In the API component, with existing features: declare and generate the
   secret, and give it to the backend.

   ```yaml
   # components/myapp/config.defaults.yaml
   SECRET_FILES:
     myapp-api-secret:
     - path: credentials/api-secret
       generate: [value]
   SECRET_TEMPLATES:
     myapp-authentication:
       Authentication__ApiSecret: '@@secret:myapp-api-secret/value@@'
   ```

2. New: a small `api.yaml` in the API component.

   ```yaml
   index: 0                        # position in Identity's ApiResources list
   secret: myapp-api-secret/value  # this component's own secret
   ```

3. New: the registration role in `bundles.yaml`, like `clients`:
   `apis: identity` on the API component and `apis` in Identity's `accepts`.
4. In Identity's manifest: `envFrom: [{secretRef: {name: identity-apis}}]`.

What the platform does, in dev `prepare` and production install alike:

- Reads `api.yaml` from every component registered with `apis: <owner>` and
  renders the owner Secret `<owner>-apis` with one key per API,
  `ApiResources__<index>__ApiSecrets__0__Value`, holding the API component's
  own file value.
- Refuses before writing anything when `api.yaml` is missing or present without
  the role, the referenced secret is not declared by that component, two APIs
  use the same `index`, no component accepts `apis`, or `<owner>-apis`
  collides with a resource the owner declares itself.
- Rebuilds the owner Secret from the current registrations on every change, so
  a removed API does not stay active; a changed or removed API secret restarts
  the API component first and then the owner, as for clients.

`index` is explicit because the organisation's Identity most likely keeps names
and scopes in `appsettings.json`; the environment value must hit the same list
position. An order chosen by the platform (for example alphabetical) could put
a secret on the wrong API.

### Decisions (product owner, 2026-10-28)

1. The hash is chosen per API: `api.yaml` requires `hash: sha256` (the owner
   receives Base64(SHA-256), the form Duende compares for secrets from
   configuration) or `hash: none` (the value unchanged).
2. Only an explicit `index`; names and scopes stay in the owner's own
   configuration. The platform renders no `ApiResources__<index>__Name`.
3. Both: synthetic fixtures cover the role, and the demo gains a real API.

### Implementation (2026-10-28)

Contract: [COMPONENTS.md](docs/COMPONENTS.md#api-secrets) and the review
guide's "API secret registrations".

- `deployment/catalog.py`: role `apis` (`api.yaml`), `accepts.apis` names a
  Secret; descriptors without `apis` (older bundles/metadata) read as `None`.
- `deployment/registrations.py`: staging checks `api.yaml`, the declared
  secret/key and unique indexes before writes; `api_updates` builds the private
  `apis/<id>/` (`index`, `value`) after generation; `owner_secrets` renders
  the owner Secret.
- `deployment/deploy.py`: dev prepare and install render the owner Secret; an
  owner outside the install has only that Secret rewritten in its installed
  YAML, then restarts after the API; uninstall removes the registration.
- Demo: app3 generates `app3-api-secret`, receives it as
  `Authentication__ApiSecret` and registers index 0 with `hash: sha256`;
  Identity names `ApiResources__0__Name: app3-api` (scope `app3`), reads
  `identity-apis` and activates only APIs with a registered secret; app3's
  `/api/secret-check` asks Duende's introspection endpoint whether the secret
  is accepted, and `dev/whoami-smoke-test.py` requires it. Images
  `demo-identity:0.2.3` and `demo-whoami-backend:0.1.1`; identity 0.4.13 and
  app3 0.1.1.

Review of `19805ee` requested changes; fixed in the follow-up commit:

1. P1: the owner YAML rewrite truncated the file in place. Now published
   atomically (`write_install_record`); a missing Secret is added; an
   unreadable YAML names a recovery that works with the pending record.
2. P1: a retry with an older `newer-only` bundle skipped rendering and
   restarted the owner with the newer registration. The install record now
   names its version; `install_checks` refuses a non-rendering retry of another
   version. A rendering release may still finish it (existing contract).
3. P2: staging (and so `validate`) read whole registrations including values.
   Registrations are now `apis/<id>/index` and `apis/<id>/value`; staging reads
   only `index`, values are read when the owner Secret is rendered.
4. P2: the registration stripped a trailing newline that direct delivery
   keeps. Now the bytes are used as stored and text that consumers would see
   differently is refused before any write.

Local verification: platform tests (`test_api_registrations.py`, 11 tests,
each new regression checked against its reintroduced defect) and demo tests
pass; the shipped demo validates and prepares with an
`identity-apis` value equal to Base64(SHA-256) of app3's generated secret
(Podman stubbed). This remains local evidence. New lab verification at
`fd99d31` built both images and passed the focused scenario, one-install
rotation/refusal, normal matrix with an empty `identity-apis` Secret, and app3
uninstall with app2 sign-in. See the [dated report](acceptance/WHOAMI-DOTNET.md#backlog-72-api-secret-lab-verification-2026-10-28)
and [sanitized checksums](acceptance/API-SECRETS-LAB-20261028.md).
The renamed startup/lifecycle regression is now verified by `m72c-renamed` at
`0ece0c1`; [scope and remaining limits](acceptance/API-SECRETS-MATRIX-20261029.md).
Remaining extensions: interrupted API owner-restart retry, real `hash: none` /
multiple-API deployments and the organisation's backend. No claim is made for
those paths from these lab results.

### Constraints

- Secrets stay in private files/Secrets: never in ConfigMaps, logs, command
  output or bundles; `validate` reads no secret contents.
- Works for production `init-config`/install and for dev, through the same
  validation flow; dev layers never initialize production config.
- Rotation and uninstall: replacing or removing an API's secret updates the
  owner's registrations; uninstalling the API removes its resource.
- Keep the existing per-component secret rules; no product-wide shared secret
  mechanism.

### Verification

- Unit/fixture tests: registration rendered for the owner, matching values on
  both sides, missing source, missing owner and duplicate `index` refused
  before output, removed
  registration not kept, restart order, no secret contents in output.
- Acceptance: an API component signs in through Identity with a registered
  secret in a real Podman run; a changed secret takes effect on both sides
  after one install.
- Update COMPONENTS.md and the review guide's contracts.

### Before this change

Operators used one file per component with the same value and compared
checksums, never the values:

```bash
podman exec <identity-container> printenv ApiResources__0__ApiSecrets__0__Value | sha256sum
podman exec <api-container> printenv Authentication__ApiSecret | sha256sum
```

## 73. Parse command lines with argparse subcommands

Status: implemented with local tests (2026-10-28); no real Podman/systemd run
yet. Split out of item 69, where the product owner asked for it on 2026-10-26
as part of WP2/WP3.

Delivered: `deployment/cli.py` uses argparse subcommands (one parser per
command, `allow_abbrev=False`, repeated flags refused, per-command `--help`)
and accepts exactly the earlier forms plus `--verbose`; `bundle.py` parses
`[<component> ...] [--verbose]` the same way. Decision on the usage stream:
usage errors now go to stderr (with the `Usage:` line and `ERROR:`), and
`--help` exits 0 on stdout instead of 2; the two wrapper tests and one CLI test
that read usage on stdout changed with it. Tests: `test_cli_output.py`.

Review of `731b97f` (2026-10-29), fixed in the follow-up commit: a repeated
`--verbose` before and after the command passed (subparsers have their own
namespace), `build-bundle.sh` accepted repeats and printed lowercase
`usage:`/`error:`, and `uninstall --` or `init-config -- app1` were accepted
where the old parser refused them. `deployment/arguments.py` now holds the
shared parser (`Usage:`/`ERROR:`), counts repeated flags over the whole line
and refuses `--`; both commands use it.

Implementation remains owned here; [item 75](#75-make-python-lifecycle-code-easier-to-follow-diagnose-and-change)
reuses the resulting parser and does not commission a parallel CLI rewrite.

### Problem

`deploy.sh` (`deployment/cli.py`) parses `sys.argv` by hand: one compound
validity expression decides which forms of `validate`, `prepare`, `install`,
`uninstall [<component>] [--delete-data]`, `init-layout`,
`init-config <component>` and `status [--json]` are accepted. It works for
today's few options but is hard to extend, gives no per-command `--help`, and
every new option (item 66's `install-set`, WP3's `init-config --settings`)
would grow the same condition. `scripts/release.py` uses one flat `argparse`
parser whose options are shared by every operation and checked afterwards
("setup arguments are only accepted for setup").

### Task

Use standard-library `argparse` with subcommands (`add_subparsers`, one parser
per command declaring only its own arguments, `allow_abbrev=False`) for
`deploy.sh`, and for every new command line from its first version: item 66's
install-set entry point and item 69's `<product>-admin` and `<product>`
commands. No third-party CLI library (offline hosts, fapolicyd, Python 3.6).

### Constraints

- Release interface: newer tools call older releases' `deploy.sh`, and the
  manual, the harness and the tests use its current forms. Keep accepting
  exactly those forms with the same meaning.
- Keep the exit codes (2 usage, 1 failure, 3 needs input where defined) and the
  usage and error messages and streams that tests, the harness and the manual
  rely on, or change them together with those consumers. argparse writes usage
  errors to stderr where `cli.py` prints its usage line to stdout today: decide
  once and update the consumers in the same change.
- Component arguments keep their current check (`common.ID`, then the bundle's
  own descriptor); argparse does not validate component names against a list.
- Prompts with defaults for paper operation (item 69) are a separate layer on
  top of parsing: ask only when an option is missing and stdin is a terminal;
  otherwise fail as today.
- `scripts/release.py` is not converted: item 69's WP6 removes that flow.

### Verification

Parser tests per command: every accepted form, unknown and misplaced options,
refused abbreviations, a missing or extra component, `--help` per command and
the exit codes. Existing CLI tests and the acceptance harness pass unchanged
(or are changed together with a deliberate message change). Python 3.6
compatibility (vermin). Update README's command section and the review guide's
"CLI entry point" contract.

## 74. One operator message convention and Python logging

Status: implemented with local tests (2026-10-28); the journal lines are not
yet verified on a real host. Split out of item 69, where the product owner
asked for it on 2026-10-26 as part of WP2/WP3.

Delivered: `deployment/output.py` (standard-library `logging`, `%(message)s`,
INFO to stdout and WARNING/ERROR to stderr through handlers that follow the
current streams, `--verbose` for DEBUG); every operator `print` in
`deployment/` and `bundle.py` goes through it, data stays `print`. Convention
chosen: the existing `[OK]`, a final `PASS: ./deploy.sh <command> completed`,
`WARNING:`/`ERROR:` on stderr; `bundle.py`'s `[WARN]` became `WARNING:` on
stderr. `+ command` lines are DEBUG, so they are hidden without `--verbose`;
the harness's platform-downgrade check, which proves no image operation by
their absence, now asks the old release's `install --help` and passes
`--verbose` only where it exists (older releases print them unconditionally).
Journal: `init-layout`, `init-config`, `install` and `uninstall` write a start
and a result line (one syslog datagram per line, identifier `<product>[pid]`),
naming the executing bundle's version and, for uninstall, the removed
installed version; `prepare-host.sh` does the same with `logger`; neither stops
a command without a journal.

Review of `731b97f` (2026-10-29), fixed in the follow-up commit: on Python
3.6 a failed `SysLogHandler` connection could leave a handler without a
socket, so a later `configure()` or interpreter exit raised; the
`SysLogHandler` is replaced by `output.JournalHandler`, which opens and closes
one datagram socket per line and keeps no state. The downgrade probe passed
`--verbose` to releases that refuse it. The uninstall line named the bundle's
version instead of the removed one. `HOST-PHASE:` and the
harness's `[OK] validated`/`PASS:` lines are documented as parsed interfaces
in the review guide. Outstanding: `journalctl -t <product>` on a real OL9 host
after install and uninstall (the per-user journal must be persistent, item 64),
and a run under a real Python 3.6 (not available where the fix was made).

[Item 75](#75-make-python-lifecycle-code-easier-to-follow-diagnose-and-change) owns
additional lifecycle decision/phase DEBUG context after this infrastructure is
integrated; handlers, streams, audit policy and existing review fixes stay here.

### Problem

Operator output is `print` in Python (about 24 calls in `deployment/`, 5 in
`bundle.py`, 14 in `scripts/release.py`) and `printf`/`echo` in shell, with no
documented convention and no Python `logging`. Prefixes vary (`[OK]`, `PASS:`,
`INFO:`, `START:`, `ERROR:`, `WARNING:`, `HOST-PHASE:`, `+ command`), stdout and
stderr are mixed without a rule, `release.py` parses `HOST-PHASE:` from
`prepare-host.sh`, many assertions in the tests and the acceptance harness match
these strings, and nothing records afterwards what the administrator or runtime
account did, which matters on closed networks.

### Task

- One convention, written into the review guide: completed steps `OK:` (or the
  existing `[OK]`, chosen once), `WARNING:`/`ERROR:` on stderr with the next
  action in the same message, a final `PASS:` line, no secret values. Results
  and data (the `status` table, `--json`, rendered output) stay plain `print`
  on stdout.
- Python: standard-library `logging` (Python 3.6, no extra packages) configured
  once in each command's entry point (`deployment/cli.py`, `bundle.py`), format
  `%(message)s` so visible text is unchanged; `INFO` to stdout,
  `WARNING`/`ERROR` to stderr (two handlers, since the default handler writes
  everything to stderr). `--verbose` (item 73) enables `DEBUG`, which carries
  today's `+ command` lines.
- Audit trail: one line per operator action and result to the journal via
  `logging.handlers.SysLogHandler` (`/dev/log`), identifier `<product>`, so
  support can ask for `journalctl -t <product>`. Shell scripts use
  `logger -t <product>` for the same; their terminal output stays `printf`.
  Without `/dev/log` (tests, containers) the command still works.
- Markers that other code parses (`HOST-PHASE:`, `PASS:`) become a documented,
  tested interface or are replaced by exit codes or `--json`.

### Constraints

- Keep existing messages and streams that tests, the harness and the manual
  rely on, or change them together with those consumers.
- Never log secret values, complete connection strings or config contents,
  also not at `DEBUG` or in the journal (credential-retention contract).
- Not in scope: `scripts/release.py` (removed in item 69's WP6) and
  application/container logs (already in journald through systemd and Podman).

### Verification

Tests for format and stream per message class, `--verbose`, the syslog handler
(with a fake socket), absence of secret values in every handler, and logging
reset between tests (configuration is global). Existing tests and the
acceptance harness pass unchanged. A real Podman/systemd run checks
`journalctl -t <product>` after install and uninstall. Update the review guide
with the convention and README where it shows output.

## 75. Make Python lifecycle code easier to follow, diagnose and change

Status: **planned; not implemented**, requested 2026-10-29.
Static analysis is recorded below; implementation remains future work.
This entry does not implement a refactor or establish a functional defect.
It follows the completed [item 1](#1-deploy-maintainability-refactor), rather
than reopening that package extraction. No new priority over agreed operator
work is implied; select a small first slice with the product owner.

### Audience, outcome and preserved strengths

The reader is an ordinary developer with some Python experience who already
understands Podman, Kubernetes-like manifests and this project's configuration
model. Maintenance difficulty must be addressed in the Python, not attributed
to missing Podman training. Make it reasonably easy to find a behavior, follow
its control/data flow, distinguish checks from effects, locate a failure,
correct it without changing unrelated paths, and place an extension in one
clear home with a bounded set of related edits.

Retain ordinary functions, standard-library dependencies, the catalog/render/
registrations/lifecycle/CLI/status module boundaries, declarative dict lookups,
named install stages, shared validation, and host-independent lifecycle fixtures.
This is incremental code and testability work, not a rewrite, a new deployment
engine, a framework, or documentation as a substitute for clearer code. A large
developer guide and an organised trial with a new developer are deferred.

### Checked revision and coordination

The initial analysis inspected `120d4eb` and the in-flight 73–74 work at
`5bb5e26`. Before delivery, fetched and integrated latest `main`,
`870e85225557da63062dc06801a9fccb161899fe`, and rechecked the affected code
and updated review-guide contracts on 2026-10-29. This is the primary checked revision below. It includes
both `731b97f` (the product owner's review base) and its review fixes in
`5bb5e26`; the earlier `120d4eb` main did not. These are static observations,
not new test results. Reconfirm the base and ongoing work before each slice.

- [73](#73-parse-command-lines-with-argparse-subcommands) and
  [74](#74-one-operator-message-convention-and-python-logging) are now integrated
  on the checked main: argparse, `deployment/arguments.py`,
  `deployment/output.py`, `--verbose` command diagnostics, agreed terminal
  streams and a separate journal audit logger already exist. The earlier
  no-verbose observation applied only to `120d4eb` and is superseded. The
  original observation about command-focused verbose output remains relevant:
  `deploy.run` emits DEBUG command lines, while lifecycle decisions still lack
  comparable phase context. Do not commission parsing, logging handlers,
  operator/audit conventions or the review fixes in 73–74 again. Reuse their
  integrated interfaces; this item adds only justified lifecycle diagnostics.
- [69](#69-paper-first-installation-for-closed-networks),
  [66](#66-install-sets-several-signed-bundles-through-one-entry-point) and
  [RPM plan](docs/RPM-DELIVERY-PLAN.md) own new command boundaries, release
  selection, operation locking, RPM layout/authentication and replacement of
  `scripts/release.py`. Do not refactor that retiring publication tool here,
  redesign its replacement, or create a competing runtime entry point/context.
  Agree ownership before changing a shared lifecycle/path interface; defer
  larger path changes where the selected RPM work is actively changing it.
- Existing `install_checks`, `install_preconditions`, write/restart helpers,
  `uninstall_plan`, atomic owner-YAML publication, pending records and shared
  validation are already present. Do not propose creating these from scratch,
  re-extracting the package, or making all work pure before secret generation.

### Current observations, maintenance assessment and candidate actions

The evidence below is at the checked main revision. Line numbers identify
starting points, not stable interfaces. Maintenance assessments are review
judgments; proposed actions require justification and tests before coding.

| Area | Observed code/dependency | Maintenance assessment | Candidate action, not an implemented fix |
| --- | --- | --- | --- |
| A. Production dependencies | `layout.select` (`deployment/layout.py:308`) assigns `common.STATE`, `FILES_DIR`, `QUADLET_DIR`, `QUADLET_TARGET`, `QUADLET_YAML` and updates the process's XDG environment. `service_user` establishes this; `catalog.component_paths`, pending functions and lifecycle functions then read it implicitly. `DeployFixture.setUp` patches a dictionary of paths and `layout.select`; the fresh-process retry driver patches another subset. | A caller must know earlier initialisation and the selected product. Debugging crosses both the operation and its environment setup; test patching shows concrete coupling. This is not evidence that repeated commands currently fail. | Later, choose a coherent production-path boundary and pass a small explicit path value from the command boundary to its consumers. Assess `ROOT`/release identity and child-process environment separately. Keep stable constants, regex rules and account identity as constants unless a real variable dependency requires otherwise. |
| B. Boundary data | `install_checks` returns a five-position tuple; `known` overlays the incoming descriptor on installed descriptors. `checked` maps component to `(effective config, effective documents)`; `rendered` maps component to `(YAML text, import volumes)`. `registration_stage` returns `(imports, updates, removals)`. `imports` is both volume-to-path-list and, for APIs, an ordered `[staged API directory, persistent API directory]`; after `api_updates`, update bytes include private registered values. | Shape, validation state, source/installed/effective meaning and privacy must be reconstructed from producers and consumers. Positional API inputs hide why two directories are required. Rendered YAML contains Secret data and is sensitive despite base64 encoding. | Name these distinctions at the producer/consumer boundaries; consider small Python 3.6-compatible named results for checked components, staged registration results and materialized manifests where that reduces unpacking ambiguity. Keep dicts for natural lookup and YAML; do not wrap every document in a parallel model. |
| C. Effect names | `install_component_plan` (`deployment/deploy.py:984`) materializes/generates secrets, loads images, persists pending/metadata/registrations, writes units/imports, restarts services, writes the marker and clears pending. `materialize_component_manifests` explicitly permits secret generation; `registration_stage` writes temporary files. | "plan" suggests calculation, although the function executes. Staging and materialization are also not pure checks. Existing docstrings help, but names should not require reading the entire body to discover critical effects. | Rename the executor to describe execution (for example `apply_component_install`, subject to review), update callers, and make short contracts distinguish read/check, calculation, generation/temporary staging, persistent publication, host commands, health and acknowledgement/completion. Do not invent a plan object merely to justify its old name. |
| D. Interleaved responsibilities | `registration_stage` (`deployment/registrations.py:31`) retains non-selected registrations, validates incoming role declarations, records removals, stages route/client bytes, defers API values and builds aggregate indexes/imports. `uninstall` (`deployment/deploy.py:1201`) resumes a durable record, stops/removes resources, rebuilds/restarts owners, optionally deletes data and finalizes. `uninstall_plan` already validates a first attempt and captures volumes/owners before YAML deletion. | Changing one role or failure boundary requires tracking several independent branches and the durability order. Length alone is not the problem. | First consider three cohesive staging steps: retain existing registrations, stage selected declarations/removals, build/check derived indexes/import inputs. Keep role-specific cases explicit. Separately consider owner-refresh and optional data-removal extraction in uninstall, leaving its stop/persist/delete/rebuild/acknowledge/finalize order visible at the top level. Accept an extraction only if it reduces simultaneous concepts rather than adding forwarding calls. |
| E. Diagnosis | On main `deploy.run` (`deployment/deploy.py:516`) emits command lines at DEBUG; `install_needed`, pending-owner selection and render-skip decisions have no comparable phase trace. CLI catches expected subprocess/OS/deploy/YAML errors; it does not catch all programming exceptions. The integrated 74 implementation already separates terminal diagnostics from journal action/result audit. | A failed host command is easier to identify than the preceding decision that selected it or skipped rendering. This is a diagnostic limitation, not proof of wrong decisions. | Through the existing logger, add only useful DEBUG boundaries: operation/component, render/skip reason, resumed pending operation/version, remaining owner IDs, and phase reached. Preserve useful existing causes and narrow expected-error handling; do not wrap all exceptions in "install failed". |

For A, a later slice must first list the exact changing globals and consumers
it replaces. Establish checked paths/process settings at the command boundary;
use explicit inputs for the selected core functions, and configure child
command environment explicitly where needed. A small immutable path record may
help, but must not contain logger/catalog/secrets/services or the whole app.
Do not retain two mutable sources of truth: migrate a bounded call chain and
its fixtures together, with one authoritative selection. Keep an adapter only
at an explicit boundary with no independent mutable copy. Preserve source dev,
bundle install and standalone contexts; test independent roots and repeated
operations in the same process where this dependency is changed. Global-path
work is not a prerequisite for the smaller staging/naming improvements.

For B, describe whether each field holds public metadata, effective config,
paths, documents or finished bytes, and whether it can contain sensitive data.
Use names such as installed descriptors versus effective descriptors rather
than indiscriminately renaming every local variable. Choose a plain record or
simple class only where named fields help; type hints should explain rather
than create a complex type system. Never log a record/config/document with
`repr`, formatting, `vars` or automatic object dumps; consider suppressing a
sensitive record's automatic representation. No new serialized schema, bundle
metadata, registration format or pending format follows from an internal type.

For E, use allowlisted scalar context (operation, component, owner IDs,
version, phase, finite reason), not config, paths read from arbitrary secrets,
connection strings, exception-object dumps or whole plans. Keep operator text,
DEBUG diagnostics, machine-readable output and journal action/result audit
separate. Add no log line without a concrete debugging question it answers;
logging every helper is not the task. Context added to expected failures must
identify operation/phase/component while preserving the underlying cause.
Coordinate any visible message/stream changes with 74 and its consumers.

### Extension placement analysis (F)

No new feature is requested by these examples. Record the actual affected
implementation/caller/test sites in each slice; a lower line count is not a
success measure and a numeric edit budget is not a universal requirement.

| Representative change | Current authoritative home and consumers | Proposed boundary to protect |
| --- | --- | --- |
| A new manifest declaration rule | `render.effective_documents` and its checks, through `deploy.validate_component`; called by `check_manifests` in prepare/install and by `validation.validate_catalog`, `validate_bundle`, `validate_standalone`. `test_secret_keys.test_missing_key_is_found_by_every_path_before_writes` is an existing cross-path example. A bundle/installed-state rule instead belongs in `install_checks`; it need not run in a source-only context. | One rule implementation in the appropriate shared check plus focused fixtures for relevant contexts; do not copy it into each CLI mode or `validation.py`. Keep validation-only source checks and later workload-volume inspection explicitly distinct. |
| A new install decision | `install_checks` / `install_needed` decide against the descriptor, installed markers, config and pending version; `install_components` selects `checked`, then the executor consumes it. `validation.validate_bundle` also calls `install_checks` / `install_preconditions`. | A named decision result with an explicit reason and render eligibility, if justified; the executor acts on it and diagnostics describe it. Declaration-only decisions remain shared with validate; decisions requiring generated bytes or host queries stay at their necessary later boundary. No duplicate decision in CLI, validation and execution. |
| Change how a registration updates its owner | `registration_stage` / `api_updates` create inputs; `apply_registration_updates` persists owner work before mutations; `write_changed_owner_imports` and uninstall's owner loop publish imports and `replace_owner_secrets`; `restart_component_services` / uninstall restart and acknowledge. | Consider one cohesive owner-publication helper reused at those two publication sites, while each caller retains visible restart/health/acknowledgement ordering. Keep API Secret and route/client-volume differences explicit. Do not introduce a plugin/role registry or merge whole install/uninstall paths behind boolean flags. |

Concrete current fan-out: `install_checks` has two direct consumers,
`install_components` and `validation.validate_bundle`; changing its result
requires reviewing both, rather than patching only the executor. Registration
staging has six call sites across `deploy.py` and `validation.py` (dev prepare,
install, uninstall planning, uninstall owner refresh, catalog validate, bundle
validate). An owner-publication change has two orchestration sites (install's
`write_changed_owner_imports` and uninstall's owner loop), already sharing
`replace_owner_secrets`. These are review surfaces, not a demand to edit every
caller. A new shared declaration predicate normally needs one implementation
plus tests for its consumers, not six copies. Record actual changes per slice.

The first row does not claim all rules fit one universal validator. Preserve
necessary dev/source, installed-bundle and standalone differences visibly,
without forcing them through one function with accumulating mode flags.

### Staged delivery and dependencies

1. Recheck main and relevant in-flight 69/73/74 changes; choose **registration
   staging plus the install executor name/data boundary** as the proposed
   first slice, or justify a smaller alternative. Trace a successful operation
   and an interrupted retry before editing. Inventory existing tests and
   agree which behavior/effect boundaries the slice touches.
2. Fix the misleading executor name and clarify selected boundary results and
   data names. Keep behavior, serialization and side-effect timing unchanged.
   Do not turn this into a wholesale renaming/type-annotation exercise.
3. Extract only the cohesive interleaved responsibilities justified above,
   keeping orchestration order apparent. Review staging first; uninstall is a
   separate later slice, not an automatic addition to the first patch.
4. Add bounded diagnostic context through the integrated 74 logger. Reassess
   its current diagnostics first: missing lifecycle decision context is this
   item's scope; parser/audit follow-ups remain with 73–74. Do not introduce a
   second logger or reconfigure handlers in lifecycle helpers.
5. Reassess remaining global dependencies with concrete caller/test evidence.
   A later small explicit-path migration may be warranted; do not make moving
   every global/module a condition for landing earlier useful improvements.

Each slice must explain what dependencies/branches a maintainer no longer has
to reconstruct, what complexity deliberately remains, and why the changed
call graph is simpler. Reject extraction that only shortens a file or adds
one-line forwarding layers. Keep functional fixes in separate patches/items
where practical; record newly discovered defects separately with reproductions.
Do not quietly alter retry/validation semantics as part of this structural task.

### Preserved contracts

Follow [the complete review guide](docs/REVIEW_GUIDE.md), especially sections
1–6. Preserve Python 3.6, standard/offline dependencies, CLI forms, exit codes
and agreed message/data streams (including status JSON). Preserve declaration
checks before relevant writes and workload commands: validate reads no
credential contents, generates no secrets and runs no workload commands; its
existing temporary staging is not permission for persistent writes.

Keep private modes, credential retention, secret-safe diagnostics, installed
metadata and all registration/pending on-disk formats unchanged. Preserve the
actual install sequence: declaration checks and environment checks -> temporary
staging/checks -> materialization (which may generate retained credentials) ->
image load/verification -> pending record -> installed metadata -> changed-owner
work durably recorded -> registration publication/removal -> unit/import and
owner-YAML publication -> component/owner restart and health -> acknowledgement
-> completed marker -> clear pending. Do not move generation earlier or imply
rollback of already performed writes. The temporary stage may check API indexes
before secret bytes exist; API value validation happens after generation and
before pending/live registration publication.

Keep a fresh process able to resume every partial attempt, including after
registration deletion or loss of installed YAML. Ordinary uninstall retains
config/credentials/data; `--delete-data` removes only the selected component's
recorded volumes and state. Preserve unaffected component data/config/services,
owner restart eligibility/order and pending conflict/version guards. Path
clarification must not weaken user-manager/XDG agreement, symlink/ownership
checks, SELinux/fapolicyd boundaries, isolated bundles or source-dev separation.

### Current success and interrupted-operation traces

For a component bundle, `cli.main` parses/configures logging and audit, then
`cli.run` dispatches `deploy.install` to
`install_components`: `service_user`/`layout.select` establish paths;
`install_checks` decides render eligibility; environment checks and temporary
`registration_stage` precede checked manifests and `install_component_plan`.
That executor materializes, verifies images, calls `begin_install`, publishes
metadata and registration work, writes units/owner imports, restarts/checks
services, writes the marker and clears pending. The API owns its source secret;
registrations own derived per-component records; the owner's installed YAML
holds the rendered Secret; the pending record owns unfinished owner work.

For failure during owner YAML replacement, `write_install_record` keeps the old
file when replacement fails; registration changes and pending owners can
already exist. A later process must reconstruct the same operation from
installed metadata and `pending-operation.json`, rebuild the owner's Secret,
restart/check it and acknowledge only after success, then mark completion.
`install_checks` also guards a non-rendering retry against a different pending
version. This is a static trace of the intended existing code and test
assertions, not new process-retry evidence (see the API test limitation below).
In uninstall, the stored plan retains volumes/owners after YAML removal; it
must remain the source for retry instead of rediscovering deleted information.

### Existing coverage, specific gaps and verification plan

This inventory is **inspection**, not a claim that tests ran for this entry.
Read test bodies and fixtures before adding cases; do not replace behavior
assertions with checks for proposed internal names or function counts.

| Boundary | Existing coverage inspected | Remaining work for an affected slice |
| --- | --- | --- |
| Validation before effects / rendered bytes | `test_validation_order.py` checks prepare/install/standalone ordering, registration refusal before workload commands, archive checks before generation, and exact bytes installed from the single materialization. `test_validate.py`, `test_secret_keys.py`, `test_manifest_structure.py` and `test_api_registrations.py` cover shared declaration/credential-read refusals. | Reuse these guards. Add only a demonstrated missing path, with a malformed synthetic input and before/after files/host-call assertions, not a second string copy of the implementation. |
| Pending, registration/import writes, restart/health and completion | `test_retry.py` uses `helpers/retry_lifecycle.py` / `retry_driver.py`: each attempt starts `sys.executable -B`, checks distinct PIDs and retains actual files/archives. It covers partial client writes, owner import failure, restart/active/health failure, metadata/marker replacement interruption, completion cleanup, pending conflicts and owner acknowledgement ordering. `test_install_failures.py` protects image-failure state and old markers after service failure; `test_health_wait.py` covers the wait itself. | Do not commission an entirely new retry framework. Inventory explicit injection at pending-record replacement/fsync and acknowledgement persistence before claiming all durability boundaries are covered; the inspected record-failure matrix targets installed metadata/markers, not every `save_pending` boundary. Add focused fresh-process cases only where absent and touched. |
| Registration removal / uninstall | `test_registration_removal.py` checks exact removals/restarts, a component omitted from source not being removed, and interruption after deletion with a fresh-process continuation. `test_retry.py` covers uninstall after YAML removal, owner/import failure, partial `--delete-data`, mounted ConfigMap deletion, removed marker/data, conflicting flags and volume-inspection errors. | Preserve separate retention/deletion cases and actual sibling snapshots; extend only for extracted behavior not already protected. |
| API owner YAML update | `test_api_registrations.py::test_interrupted_owner_rewrite_keeps_the_old_yaml_and_retry_finishes` verifies atomic replacement, retained old YAML, pending owners and successful retry. Despite its "fresh process" comment, the retry calls `self.quiet(deploy.install)` in the same interpreter, after resetting the subprocess mock. This is not a real process restart. | Add an API owner-YAML publication failure followed by a genuinely fresh-process attempt using the existing driver/fixtures; assert owner Secret bytes, restart order, pending/completion, modes and sibling retention. Correct the misleading test comment when that test is changed. This coverage finding is not a demonstrated product retry bug and does not rewrite historical lab reports. |
| Paths / global initialisation | `DeployFixture` patches paths/layout/environment; retry transport patches a separate path subset. `test_layout.py` covers production selection, XDG agreement, refusing unsafe bootstrap/root state, and source-dev ignoring production layout; bootstrap interruption has fresh-process coverage. | If paths become explicit, retain those guards and add independent-root/repeated-operation isolation without recreating conflicting global and explicit states. Avoid tests tied to a particular context class name. |

For implementation, run the repository's existing product groups
(`python3 -B tests/run.py all`, plus `platform --isolate` for a generic lifecycle
slice), and applicable established static/Python 3.6 checks from the test/CI
instructions. Separately run
`python3 -B -m unittest discover -s acceptance -p 'test_*.py'` for harness wiring.
Test assertions must check observable outputs,
private-file access/modes, durable bytes and host effects, not the new helper
names. Add safe sentinel coverage for any new diagnostic's handlers/streams;
`test_cli_output.py` already covers parser forms, verbose command visibility,
terminal stream routing, secret-safe lifecycle audit and unreachable journal
sockets (including a fresh interpreter); extend it for new decision context
only where coverage is missing, rather than rebuilding 73–74 infrastructure. Test unexpected programming exceptions
remain diagnosable instead of being converted into generic success/failure text.

Select real Podman/systemd verification according to the actual slice: normal
and renamed lifecycle for changed staging/owner publication; include declaration
removal and unchanged siblings, and a minimal external-image worker fixture for
generic assumptions. For install/uninstall/paths, exercise restart, reboot,
upgrade/skip, retention and `--delete-data` on configured disposable lab VMs,
plus a controlled relevant failure and retry in a fresh process. For API-owner
or API path changes, include focused `--whoami` with registration/introspection
and rotation/removal, and the owner-publication/restart interruption missed by
ordinary happy-path smoke. If diagnostics change, check the agreed terminal
streams/status JSON and relevant journal audit on a real host without exposing
values. Never reset unrelated environments. Record exact tested revisions,
commands, results and gaps separately for product/unit, harness and real
runtime. Historical green lab runs cannot verify a future refactor.

### Understandability acceptance gate

Green tests and shorter files are insufficient. The final review of each slice
must answer the review guide's six questions and trace one success and one
interrupted operation/retry, naming state ownership and functions. Show that:

- The command entry and principal operation sequence are easy to find.
- Names and placement reveal important effects; temporary staging/generation,
  persistent publication and host commands are distinguishable from checks.
- Central inputs/results reveal shape, validation stage, origin and sensitivity
  without a long producer/consumer hunt; named results serve actual readers.
- Required paths/process settings and any remaining initialisation order are
  visible; no competing implicit/explicit source can drift.
- A new declaration rule has one identifiable authoritative home and can be
  exercised across relevant flows without copying the rule.
- Safe diagnostic context identifies the relevant component/phase/reason while
  preserving useful failure causes and existing machine-readable interfaces.
- The retry can be explained from files left by the first process, including
  owner work and completion; unrelated components remain untouched.
- The new call graph reduces hidden relationships rather than multiplying
  helpers. Document intentional complexity (three roles, source versus bundle,
  generation-dependent checks, existing durable protocol) and why it remains.

Record this as a code-review assessment, not empirical proof of human
comprehension. The larger developer guide/new-developer trial are deferred.
No operator commands/prerequisites are changed by this planning entry, so the
section 7 AI operator walkthrough and human trial are not performed here. If
implementation changes such procedures, apply section 7 then; green code tests
are not a human/operator usability result.

## 64. Support new rootless installations outside the login home

Status: implemented with local regressions on `claude/friendly-mendel-8u3bqs`
(2026-10-23), built on the unmerged item 54 branch; merged to `main`; full OL9
matrix CLEAN PASS on `5b8ab69`; manual ssh run without sudo worked 2026-10-23
with extensive help and found the missing persistent-journal prerequisite (now
in the guide). Not ready for the operator: the guide is not verified literally
and host preparation is too hard (items 65–67); small `/home` still untested. Requested 2026-10-23.

Delivered: `deployment/layout.py` (bootstrap file `~/.<product>/<product>.env`
with required `INSTALL_ROOT=/var/lib/<product>`, read as data; root/ancestor and
account-directory checks; refusal of product Quadlets in the login home);
`common.STATE` separate from the identity `common.HOME`; `prepare-host.sh --user`
for an existing account with a `user@<uid>` drop-in setting
`XDG_CONFIG_HOME=/var/lib/<product>/config` and `XDG_DATA_HOME=/var/lib/<product>/storage`;
user manager agreement check before lifecycle commands; `release.py` anchor moved
to `/var/lib/<product>`; the harness runs as `<product>-ops` with a read-only
home and checks unit sources, graphroot and home inventory after reboot; the
Norwegian [operator guide](docs/PRODUCTION-INSTALL.md) ships in every component
bundle. Open: the manual checks listed in the verification report; item 54 must be reviewed/merged first or together.
The operator needs to test an offline production installation immediately after
implementation. Scope is **new installations only**: no migration of an old
home-based installation, images, volumes or users. Ordinary upgrades, retries,
restarts and retention within the new layout remain required.

Deliver the implementation and a short, precise production installation guide.
The [operator-flow draft](docs/PRODUCTION-INSTALL.md) records the agreed target;
it is explicitly not a runnable recipe for the current bundles. Replace its
planned status with actual tested commands when implemented.

### Operator requirements and scope

- Run rootless as an existing non-root login account. Its real name, UID/GID and
  home can vary and need not match the product. `produser` and product `sms` are
  examples only. Keep the account's registered home, shell and login working;
  do not require `nologin`, rename the account, move its home or spoof `HOME`.
- The home has almost no free space. For product `sms`, the sole intended
  persistent product file there is `~/.sms/sms.env`, containing installation
  settings. All other product-persistent files belong under `/var/lib/sms`:
  releases, component config and credentials, rendered YAML, installed metadata,
  pending operations, route/client registrations, import archives, Podman
  configuration, images, volumes and product caches. Generalise from the catalog
  product name; do not hardcode `sms`, `produser` or `/home/<user>` in core code.
- System-owned `/etc` configuration, system journal and transient
  `/run/user/<uid>` are deliberate exceptions, not hidden relocations into the
  login home. Keep per-UID runtime semantics. Document archive staging and image
  import temporary-space requirements; no home-sized archive copies or caches.
- Administrator/sudo may prepare the host and protected release/trust boundary.
  Starting/stopping services, inspecting health/logs and ordinary product
  operations after publication must work as the selected account without sudo.
  Do not promise completely unprivileged publication of new executable releases:
  protected release installation and fapolicyd enrollment remain administrator
  operations unless an explicit safe delegation is implemented separately.
- Preserve dev behavior: `build/dev`, existing dev override precedence,
  `dev/dev.sh up/down`, image helpers and bundle creation must not start reading
  production `sms.env` or silently switch to production Podman storage. No need
  for application or manifest edits just to relocate host storage.

### Detailed instructions for the implementation agent

1. Read [AGENTS.md](AGENTS.md), [the review guide](docs/REVIEW_GUIDE.md),
   [architecture](ARCHITECTURE.md), [component contracts](docs/COMPONENTS.md),
   [tests](tests/README.md) and [acceptance](acceptance/README.md), plus items 46,
   54, 56, 57 and 60. Inspect current main and any ongoing item 54 work before
   selecting helpers/layout; the task text does not prove those fixes are merged.
   Trace `common.HOME`, `FILES_DIR`, `QUADLET_DIR`, `catalog.component_paths`,
   metadata, registrations and pending-state paths through init-config, validate,
   install, retry, upgrade and uninstall. Trace all shell/acceptance paths too.
2. Introduce one explicit production path model separating actual user home,
   release inputs, installation/state root, Podman storage/config and runtime.
   Keep common.HOME's identity meaning if retained; do not globally substitute
   `/var/lib/...` for the user's home. Derive consumer paths consistently instead
   of scattering new environment lookups or fallback chains. Use small functions
   and existing lifecycle boundaries, not a plugin or configuration framework.
3. Define a minimal, documented bootstrap format at
   `~/.<product>/<product>.env` (the sms example is `~/.sms/sms.env`). Find the
   actual user/home through account identity, and the product through the release
   descriptor. Specify supported fields, precedence, quoting, missing-file and
   unknown-key behavior, and how existing application settings in this file are
   treated. Read data, not shell code: no `eval`, shell `source`, substitutions
   or execution. Bootstrap fields select paths; they do not implicitly replace
   authoritative component config or forward secrets to all containers. Keep
   secret values out of diagnostics and redact invalid input. Require private
   ownership/modes and safely handle symlinks. Do not ship this file in bundles.
4. Use `/var/lib/<product>` as the target layout's root-owned anchor. A proposed
   layout is protected `releases/`, user-private `state/`, Podman `storage/` and
   `config/`; map all other durable outputs explicitly. The service user may
   manage its designated data directories but must not rename/replace the root
   anchor or protected release entries. Validate ancestors and ACL/mode exposure.
   Coordinate with item 54: reuse its verifier/publisher and update its layout
   assumptions if needed; keep final trusted release bytes and ancestors
   protected before and after verification. Never fix this with recursive chown
   of the whole installation tree or a root-owned directory inside a replaceable
   user-owned parent. Root must not source or blindly follow paths in sms.env;
   privileged destinations must come from explicit validated administrator input
   or protected configuration. Validate agreement with user bootstrap settings.
5. Adapt host preparation to an explicitly selected existing login account.
   Preserve its home, shell, contents and existing non-overlapping subordinate
   ID ranges; verify required mappings instead of overwriting them. Preserve
   item 46's non-root filesystem operations and race/symlink protections while
   preparing the new data locations. Support rootless linger, correct SELinux
   labels/equivalences and scoped fapolicyd trust. Do not disable enforcement,
   broaden executable trust to data, globally chown mapped volume contents or
   recursively relabel already populated container storage.
6. Configure Podman and the user systemd manager so CLI deployment, image load,
   kube/Quadlet services, interactive diagnostics and unattended reboot use the
   same storage and config. Work out Quadlet discovery before generation: merely
   adding `EnvironmentFile=` to a generated service or exporting variables in an
   interactive shell cannot establish the generator's environment. Verify the
   supported Podman/systemd versions and choose a small persistent integration.
   Preserve `/run/user/<uid>`; no fake HOME or persistent runtime directory.
   Avoid global shell exports that redirect dev or unrelated user workloads.
   Provide an explicit supported way to run production `podman` diagnostics if
   they require scoped configuration. Retain the one-product-per-account
   contract; general multi-product account support is not part of this item.
7. New-layout creation must refuse conflicting existing state or a changed root
   instead of silently creating a second installation, switching storage or
   migrating data. Cover restart and fresh-process retry on the same new layout.
   Keep credentials and DB volumes on ordinary uninstall; scoped delete-data
   must never remove the user home, shared anchor, protected releases, another
   product or unrelated containers. Preserve side-effect-free validate: no
   Podman/systemd commands, writes or reads of credential contents. Loading
   public bootstrap path settings is distinct from reading Secret source bytes.
8. Update bundles and host/deploy helpers as needed so a release operates offline
   without source checkout, sibling source directories or apps. Source dev and
   bundle building ignore installed production bootstrap settings. Preserve
   component_file resolution against the selected read-only release; ordinary
   path sources resolve against the new persistent component-config directory.
   Never copy local sms.env, credentials or production state into a bundle.
   Coordinate CLI spelling with item 60 instead of introducing another alias.

### Tests and real acceptance requirements

- Use synthetic products and a runtime user whose name differs from the product,
  with an actual home outside the install root and ordinary login shell. Include
  a renamed-product case. Test root derivation, malformed/missing bootstrap,
  permission/symlink failures, retained config, Secret templates, component files,
  installed metadata, registration updates, retry and scoped uninstall. Do not
  write tests that merely repeat the implementation's derived path strings.
- Test that command-like env values cannot execute, invalid inputs fail before
  side effects, root helpers cannot be redirected through user-controlled
  bootstrap/ancestors, and private content is absent from logs and artifacts.
- Add a real OL9 scenario with Enforcing SELinux and active fapolicyd, separate
  administrator and runtime identities, an effectively unwritable or tightly
  constrained login home after bootstrap, and sufficient space under /var/lib.
  Check actual Podman graphroot/volume paths and home file inventory. Distinguish
  unrelated OS/login files from product writes; no large files or product
  config/Quadlets may silently appear in the old home layout.
- Exercise protected bundle publication, first install in dependency order,
  actual init-container Secret/migration-probe delivery, HTTPS health, component
  upgrade retaining data, failed operation/retry, stop/start, logout and reboot
  without interactive login. Confirm that generated Quadlets are discovered and
  services use the intended storage after reboot, not only during install.
  Runtime operations must not rely on cached sudo credentials.
- Use real separate-UID checks for release write/replace denial, and verify that
  no unexpected SELinux AVC/fapolicyd denial is needed to make the normal flow
  work. Keep bounded waits and cleanup confined to disposable test resources.
- Run the appropriate platform/demo suites, platform --isolate, acceptance-harness
  tests and required static checks. Include a dev regression with a production
  env file present and an isolated bundle export; neither may inherit production
  paths/settings. Record commit and exact commands, separating unit, harness and
  real runtime evidence. If OL9 execution is unavailable, mark it pending and do
  not label the new deployment model ready for the operator.

### Required short production installation guide

Finish [docs/PRODUCTION-INSTALL.md](docs/PRODUCTION-INSTALL.md) as a short
Norwegian operator guide with concrete copy/paste commands, linked prominently
from README and included or explicitly delivered with the offline release.
Keep deep design/verification details in linked documents, not in the operator
flow. Use one coherent example with product sms and a different, replaceable
runtime username; never assume all component versions are equal. It must show:

1. Prerequisites, actual-user/root paths, required disk space and transfer of the
   right archives/checksums/signatures. Explicit signed-policy versus approved
   unsigned test flow; never run privileged code from an unverified archive.
2. Administrator host preparation for the existing account, bounded ownership
   and labels, port 8443, UID mapping/linger and protected release publication
   plus exact fapolicyd trust verification. State which steps repeat per release.
3. The exact minimal sms.env content and its permissions; no manual HOME change
   or terminal-only environment required. Show actual config/credential paths.
4. Rootless platform init-config, config edits, TLS provisioning, validate and
   install; then STS and dependencies with signing-PFX, DB credentials and the
   production migration/seed selection. Do not copy the entire dev credentials
   directory or ship dev overrides. Respect component-specific secret names.
5. Rootless status/log/Podman commands, local and external HTTPS checks, restart,
   logout/reboot verification and a few safe diagnostics for wrong paths/storage,
   permissions, missing credentials or fapolicyd trust. Show the execution user
   and success condition for each step; fail clearly instead of continuing.

Run the guide's commands as an acceptance scenario on a fresh host. Keep
README, architecture, review contracts, current helper usage and this backlog
status consistent with the final implementation. Complete the understandability
review by tracing one successful install and one failure/retry, explaining path
ownership, bootstrap loading and systemd startup. No automatic legacy migration,
application refactoring or unrelated backlog cleanup belongs in this task.

## 65. One-command host preparation and a short operator guide

Status: implemented on `feature/65-host-setup` with local regression coverage
(2026-10-24). The first real OL9 run at `8559a2a` stopped in preflight: sudo
reported explicit denial with exit 0, which setup incorrectly rejected. The
follow-up fix has regression coverage. All nine scenarios in lab series
`host65-20261024-144821-*` passed at `2d36d71`; unassisted human
verification remains outstanding under item 68. Review follow-up fixes literal manual
fail-stop behavior, interruption-safe bootstrap publication and bounded host
phase/error diagnostics, with regression coverage and a revised AI operator
assessment.
[Implementation, evidence and lab commands](acceptance/HOST-SETUP.md). Read the
[implementation plan](docs/HOST-SETUP-PLAN.md) before starting: it fixes the CLI,
bootstrap trust, journal policy, scope against 66/67, failure/retry behavior and
test gates. The focused `--host-setup` scenario uses the manual blocks and real
runtime SSH without sudo. `deploy.sh init-layout` replaces manual bootstrap-file
creation. The complete reboot/upgrade SSH path remains item 67. Found in the manual backlog 64 run
([report](acceptance/PRODUCTION-LAYOUT.md#manual-run-as-produser-over-ssh-2026-10-23)).
The operator's verdict: "Host preparation must be simpler. I did not
understand what was happening." (translated from Norwegian) Installation worked only with step-by-step help.

Today the administrator reconstructs the order from the guide, README and the
PFX guide: fapolicyd cache, persistent journal, transfer area, checksums,
independent key/tool hashes, protected copy of the release tool,
`provision-key`, `prepare` per release, `prepare-host.sh`, later `retire`.

Deliver one administrator entry point (`setup` in the existing independently
authenticated `scripts/release.py`, calling the protected `prepare-host.sh`;
no second release helper) that takes product, existing
runtime account, HTTPS port, the trusted public key with its independent SHA256,
the transfer directory, explicit release selections and a selected host-script
release, and then:

- checks every prerequisite first and names the exact fix (OL9, SELinux
  Enforcing, fapolicyd and `subj_cache_size`, firewalld, packages, account
  exists and has no sudo, space under `/var/lib` and `/var/tmp`);
- establishes the persistent journal for supported `auto`/`persistent` plus
  `SplitMode=uid` policy, without extra groups; refuses explicit incompatible
  policy rather than overwriting it. Document the host-wide change;
- uses the separately installed/authenticated release tool and pins the key
  once; consolidate and test the initial tool bootstrap procedure;
- runs the existing `prepare` for the selected bundles and the existing host
  preparation once. Publication follows explicit selection order; dependency
  ordering for runtime installation belongs to item 66;
- is safe to rerun after interruption and says which step completed;
- ends with a short report and the exact next command for the runtime account.

Keep the trust boundaries: authenticate before any privileged execution of
archive code, keep the runtime account without sudo, no wildcard or shell
expansion inside root-only directories, no hidden network access.

Rewrite `docs/PRODUCTION-INSTALL.md` around it: each step names machine,
account, one command and the expected output; one example product that matches
the demo (or a clear substitution table); PEM and PFX credential paths shown
separately; HTTPS checks against endpoints the component answers. Move design
detail to linked documents; keep every required action, including tool bootstrap
and the selected credential path, in the one manual.

Apply the [mandatory operator review](docs/REVIEW_GUIDE.md#7-mandatory-operator-and-procedure-understanding-review).
For 65, the AI walkthrough must cover transfer/tool authentication, prerequisite
failure and remedy, initial setup, identical rerun and interrupted setup retry,
then handoff to real SSH login as the non-sudo runtime account. Each step states
machine, user, access, copyable command and expected result. Count commands,
manual edits and account switches; simplify the tool if these make setup hard.
Errors must give a safe diagnosis, corrective action and exact continuation.

The acceptance path must execute the manual's bootstrap and `setup` command,
including first run, repeat and interruption/retry, with a checked mapping to
manual steps. No controller-provided helper execution, direct `prepare-host.sh`
call, journal setup or product/bootstrap-file creation may substitute for those
operator steps. Runtime steps use real SSH without sudo; coordinate this shared
path with 67, and mark its absence as a verification gap until implemented.
Preserve the existing hostile-input/security probes as additional tests.

Record a separate fresh-host trial by a person with limited Linux experience,
without oral help: time, errors, stops and explanations needed. Human verification
is outstanding; the assisted 2026-10-23 run does not qualify. The current
[AI assessment](acceptance/OPERATOR-REVIEW.md) has findings; repeat it on the final
manual. Automated success alone does not make 65 customer-ready.

## 68. Human operator trial on a fresh VM

Status: outstanding verification (2026-10-24). Required before declaring the
operator flow customer-ready; does not block merging the implementation of 65.
Coordinate with items 65–67 and repeat affected tasks when their manual changes.

A person with limited Linux experience must follow the English
[production manual](docs/PRODUCTION-INSTALL.md) on a fresh disposable VM at its
declared OS/account baseline, without oral help or internal architecture
knowledge. Supply only the documented delivery, substitution worksheet and
manual. An observer records events without coaching or silently repairing state.

Use a printed manual without copy/paste (backlog 69), with a console-only variant and one person holding both accounts. In item 69's phase 1 (unsigned RPMs) the trial has no key or fingerprint steps; repeat the affected tasks when phase 2 adds signing. Cover transfer and trusted tool bootstrap, prerequisite diagnosis/remedy, first
setup, repeated setup and continuation after an interruption, then real SSH login
as the runtime user without sudo, configuration/credential delivery, installation,
status and safe journal access. Include install sets and reboot/upgrade/retire
when items 66–67 provide those procedures. Record unsupported tasks as pending.

Record code/manual revision, VM starting state, relevant participant experience,
elapsed and active time, machine waits, commands, edits, account switches, errors,
stopping points and every requested explanation. Do not record sensitive values.
If assistance is needed, mark the task assisted, fix the manual or workflow and
repeat the affected task without help. Assess whether the tool needs simplifying
rather than merely adding more instructions.

Store the result in [the operator assessment](acceptance/OPERATOR-REVIEW.md),
following the [mandatory review criteria](docs/REVIEW_GUIDE.md#7-mandatory-operator-and-procedure-understanding-review).
Keep AI walkthrough, automated acceptance and human outcomes separate. The
assisted 2026-10-23 trial and green automated lab runs do not satisfy this item.
Completion requires an unassisted pass for each claimed task, with remaining
scope and usability findings explicitly recorded.

## 70. Provision a component's CA trust chain from the environment's PKI

Status: **implemented and lab verified** (2026-10-26) at `45fdb17`:
[documented pattern](docs/COMPONENTS.md#trusting-the-environments-ca-in-a-backend),
regression coverage and real rootless Podman 5.8.2/OL9.8 `subPath` with SELinux
Enforcing passed. App3 signed-bundle sign-in, unrelated-CA HTTP 500 plus
user-journal `PartialChain`, and restoration passed. Actual single-file SELinux
labels were recorded; persistent user journaling needed the existing host-setup
helper on the matrix baseline. [Lab evidence](acceptance/TRUST-CHAIN.md#completed-lab-verification-2026-10-26).
Only the single-level demo CA/app3 is covered; the organisation's backend and a
root plus issuing CA remain unverified.
The `43dd0dd` focused lab run repeated subPath, public HTTPS, wrong-CA failure
and restoration successfully (2026-10-27); its later audit-format failure does
not invalidate those checks. [Current lab evidence](acceptance/TRUST-CHAIN.md#lab-verification-at-43dd0dd-2026-10-27).
High priority, requested by the product owner.
This work unblocks converting the organisation's backend that signs in through
Duende and calls it over HTTPS through the platform proxy. Kept small on 2026-10-26: copy
steps, documentation and a `subPath` check, no new script mode. Independent of
items 66/69; item 71 uses it.

### Background

In the original Kubernetes installation the backend (not the frontend) mounts a
public CA chain from the Secret `<product>-ingress-trust-chain` as two single
files with `subPath`: `/etc/ssl/certs/<product>-root.pem` and
`/etc/ssl/certs/<product>-ca.pem`. The backend is the OIDC client: it calls
Duende server to server (discovery, JWKS, token exchange with
`private_key_jwt`) through the public HTTPS origin, so it must trust the CA that
issued the proxy certificate. .NET on Linux reads every file in
`/etc/ssl/certs`, so the two extra files extend the image's trust store without
hiding its own CAs. The chain contains only public certificates; it signs
nothing (Duende signs tokens with its own signing key).

Today `dev/generate-certificates.sh` creates one self-signed CA per root
(`<root>/PKI/private/ca.crt`): `build/dev` in dev, the runtime state
(`/var/lib/<product>/state`) in the lab, where the runtime user runs it on
stdin. That CA directly signs the web, Identity and client certificates, so in
dev and the lab it is both the root and the only issuing CA. The script has no
way to deliver this CA to a new component's own files. `dev/demo-credentials.sh`
calls the script for the shipped demo only, in dev only.

### Task (kept small, product owner 2026-10-26)

Follow the original Kubernetes setup (public HTTPS plus the chain); whether the
backend could call Duende internally instead is tested in item 71, not decided
here. No new code in `dev/generate-certificates.sh` for now.

1. Dev: in the dev provisioning for the organisation's components (outside
   generic `dev/dev.sh`), after the environment's CA exists, copy it into the
   component's files:
   `install -d -m 0700 build/dev/<id>/cert`, then
   `install -m 0644 build/dev/PKI/private/ca.crt build/dev/<id>/cert/root.crt`
   and the same to `ca.crt`. The demo PKI has one level, so the root is also
   the only issuing CA.
2. Lab and manual: the same two copies as the runtime user after `init-config`,
   from `/var/lib/<product>/state/PKI/private/ca.crt` to
   `/var/lib/<product>/state/<id>/cert/`; add them to the harness if the
   component is in a scenario. Always the environment's own CA, never the
   source checkout's.
3. Component pattern, documented in `docs/COMPONENTS.md`:
   `SECRET_FILES: <component>-ingress-trust-chain: [{path: cert}]` (the Secret
   name must start with the component ID; `<product>-...` is refused), and in
   the backend container two `volumeMounts` of one `secret` volume with
   `subPath: root.crt` / `subPath: ca.crt` to
   `/etc/ssl/certs/<product>-root.pem` and `/etc/ssl/certs/<product>-ca.pem`,
   `readOnly: true`, with matching `items`.
4. Verify before relying on it: `podman kube play` (5.8.2 on OL9) supports
   `subPath` for a Secret volume and keeps the image's other files in
   `/etc/ssl/certs`; manifest validation accepts `subPath`. If `subPath` does
   not work, stop and decide an alternative with the product owner.

### Tests and verification

- A product test that a component with this declaration and these mounts
  validates and renders the Secret with both keys.
- The `subPath` check above on a lab host, recorded with the Podman version.
- End to end in dev and the lab through item 71's app (and later the real
  backend): sign-in through Duende with the chain; record that only the
  single-level demo CA is exercised.

### Later, only if needed

A `--component ID --purpose trust-chain` mode in `dev/generate-certificates.sh`
(copy with the script's retain/conflict/link rules and script tests), if the
manual copies turn out to drift or to be error-prone. Out of scope: a two-level
demo PKI (root plus issuing CA) and customer CA delivery (backlog 45a/45b).

## 71. Add a .NET and TypeScript demo app that signs in through Duende

Status: **complete for the documented lab scope** (2026-10-27). Run
`whoami-7b32621` tested `7b326213ea40466319eff3dd9a54fd23f95fedcb` and finished
**CLEAN PASS, 46/46 steps**, including the final PROD audit with `5f30331`'s
shared journal-reader fix. No parser relaxation, step retry, interruption or
manual prerequisite repair was needed. The six conversion points, explicit
issuer pin's image-build checks, protocol-error log rule, both OIDC variants,
wrong-CA negative control and restoration passed on rootless OL9.8/Podman 5.8.2,
SELinux Enforcing and Quadlet/user systemd. One saved session survived service
restart and PROD reboot. [Complete lab evidence](acceptance/WHOAMI-DOTNET.md#complete-audit-fix-lab-run-2026-10-27).

The earlier NOT CLEAN `43dd0dd` run and interrupted fix run remain unchanged
historical evidence. Renamed regression at `43dd0dd` was CLEAN PASS. The optional
normal scenario was skipped at `7b32621`, so the shared audit fix is not claimed
verified through a fixed-matrix run at that commit. No change to `deployment/`
or fixed-matrix component sets. Recommendation remains variant (a). The real
backend, two-level CA, post-logout redirect and session revocation remain outside
this completed lab scope; app3 fixed-matrix integration is a separate follow-up.
High priority, requested by the product owner to de-risk converting the
organisation's .NET backend. Exercises item 70.

### Why

The demo apps cover Duende only from the server side: Identity is C# with
Duende, but app1/app2 use a Python (Flask/Authlib) BFF and a plain JavaScript
frontend without a build step. The organisation's solution has a C# backend
and a TypeScript frontend. The risky parts of converting it are untested here:

1. ASP.NET's OpenID Connect handler behind the platform proxy: its default
   callback `/signin-oidc` versus the client protocol's `/auth/callback`
   (configure the app, or record that the protocol must change).
2. Forwarded headers: without `X-Forwarded-Proto` handling the app builds
   `http` redirect URIs behind nginx.
3. ASP.NET Data Protection keys: kept in a persistent volume, so sign-in
   cookies survive restarts and reinstalls.
4. The CA trust chain from item 70: the backend calls Duende over the public
   HTTPS origin and trusts the proxy certificate only through
   `/etc/ssl/certs/<product>-root.pem` and `-ca.pem` mounted with `subPath`.
5. `private_key_jwt` client authentication from .NET with the component's
   client certificate, as the existing apps use.
6. A TypeScript frontend built in a multi-stage image (Node at build time,
   static files served by nginx at run time), fully offline at install.

### Scope

A minimal "whoami" app, for example component `app3`: the user signs in through
the existing Identity; the TypeScript page shows the user's name and calls one
protected backend API that returns the signed-in user's claims. No database,
no seed data, no init containers.

- `apps/<name>-backend` (ASP.NET Core, .NET 8 like Identity) and
  `apps/<name>-frontend` (TypeScript), each with a Containerfile; images built
  and pulled by the existing dev scripts and bundled offline like the others.
- Component `components/<id>/`: `VERSION`, `config.defaults.yaml`, manifests,
  `route.conf` and `client.yaml`; catalog entry with `requires: [platform,
  identity]`, `public_from`, `routes` and `clients` like app2.
- Secrets/volumes: the trust chain (item 70), the client key pair, a session or
  Data Protection volume; nothing generic added for this app.
- Dev provisioning of its certificates through `generate-certificates.sh`
  (client pair and item 70's trust-chain mode), outside generic `dev/dev.sh`.
  As implemented: the client pair by a demo recipe in
  `generate-certificates.sh`, the chain by item 70's copy commands in
  `dev/demo-credentials.sh` (item 70 deferred a trust-chain mode).

### Verification

- Dev: `deploy.sh validate`, `dev.sh up`, sign-in end to end, claims API,
  restart keeps the session (Data Protection), redirect URIs use https.
- Lab: manual installation from bundles as the runtime user; same checks; the
  backend reaches Duende only through the trust chain (remove it once to see the
  expected certificate error, then restore).
- Not part of the fixed acceptance matrix at first; add it there (container
  counts, install orders, e2e, upgrade) in a follow-up if it proves useful.
- Record each of the six points above as confirmed, changed or open, so the
  conversion of the real backend can reuse the answers.
- **Public HTTPS versus internal calls (product owner, 2026-10-26).** Run the
  app in two variants and record the configuration each needs:
  (a) as the original Kubernetes setup: discovery, JWKS and token endpoint
  through the public HTTPS origin, trusting the proxy certificate through
  item 70's chain;
  (b) internal: discovery/JWKS/token from Duende on the Podman network over
  HTTP (`MetadataAddress`, `RequireHttpsMetadata = false`), while the issuer
  stays the public origin (`ValidIssuer`) and the browser is still sent to the
  public authorize and end-session endpoints, without the chain.
  For (b) record whether Duende publishes split endpoints or the app must
  override them, and any security review concern about unencrypted traffic
  between containers. The result decides which variant the real backend uses;
  until then the conversion follows (a).

## 69. Paper-first installation for closed networks

Status: requirement and investigation (2026-10-25), lab questions answered and
an RPM prototype run the same day (see below); **direction chosen by the
product owner on 2026-10-25: signed RPM delivery with one command per role**
(see "Chosen direction"); **phased on 2026-10-26: unsigned RPMs first, signing
deferred, not dropped** (see "Phasing decision"); high priority. It
applies to items 65 (implemented for pasted commands), 66 (planned) and 68
(human trial), and must be settled before 66's operator-facing commands are
fixed.

Status 2026-10-27: the WP0 investigation matrix passed (all 24 case/profile
runs at `3222efb`, 2026-10-25,
[report](acceptance/RPM-WP0-LAB-20261025-FULL.md)). Nothing is implemented.
WP1 waits for the product owner's go/no-go and the two open phase 1 decisions
under "Phasing decision"; both are still open.

Many customers install in a closed server lab, often from a **printed manual**,
sometimes with **only a console** (bundles on DVD or USB, no SSH), and the
administrator and the runtime user are often **the same person** using two
accounts. Whatever the scenario, installation must be easy. The current manual
assumes copy and paste: a ~60-line Python block for the tool bootstrap, a long
multi-line `setup` command, a variable "values block" and 64-character digests.
None of this can be typed reliably from paper.

### Scenarios to support

| Dimension | Variants |
| --- | --- |
| Bundle delivery | one DVD per bundle, possibly at different times; many bundles on a USB stick; a lab network share; `scp` from a laptop |
| Server access | console only; SSH from a laptop in the closed network |
| Manual | printed; PDF on another machine without copy/paste; copy/paste (not the default assumption) |
| Tool provisioning | organisation has an internal package repository; it does not; only supplier media |
| Security baseline | SELinux Enforcing and fapolicyd as today; possibly stricter local rules |
| Task | first installation; adding a component later; updating one app; a new server |
| People | separate administrator and runtime user; one person with both accounts |
| Credentials | files from the supplier; the organisation's PKI; PEM or PFX |

### Requirements for the manual and the tools

1. Every command can be typed from paper without error: short, few options, no
   pipes, line continuations, quoting or long paths in the ordinary flow.
2. Tools ask for missing values with a suggested default (runtime account, port,
   public address, which found bundles to publish) and accept the same values
   as options for automation and tests.
3. Sensible defaults: product from the bundles, bundles from the current or
   mounted directory, port 8443.
4. The operator compares, never types, digests and key fingerprints: tools print
   them in groups of four characters and ask for confirmation.
5. The same flow for every delivery medium: mount or copy, then one command.
6. One command per role, repeated after a stop or interruption until it reports
   success.
7. Errors in one or two lines: what is wrong and what to do now; no tracebacks,
   no reference to another document for ordinary remedies.
8. Account switches that work at a console: log out and log in as the runtime
   user (a real login session). `su -` and `sudo -iu` do not start the user's
   systemd session and must not appear in the manual.
9. A measurable limit on commands and typed characters per task, checked in the
   AI walkthrough and the human trial (item 68).

### Questions to answer in the lab before choosing a design

Recipe and results: [PAPER-FIRST-LAB.md](acceptance/PAPER-FIRST-LAB.md), run on
2026-10-25 on OL9.8 with the default fapolicyd policy. Findings:

- Untrusted shell scripts run for everyone (rule `allow perm=any all :
  ftype=text/x-shellscript`), and root may run untrusted Python. Only non-root
  opening of untrusted Python is denied. fapolicyd does not protect a delivered
  `setup.sh`; authenticity must come from a signature check.
- RPM-installed files are trusted through `trust = rpmdb` without extra rules.
- `dnf install ./file.rpm` does not check signatures by default
  (`localpkg_gpgcheck = 0`); `rpm -K` prints `digests OK` for an unsigned file,
  so the manual must require the words `signatures OK` or the host must enable
  `localpkg_gpgcheck`.
- `sudo -iu` gives no user session; `machinectl` needs `systemd-container`
  (not installed); `ssh <runtime>@localhost` and a console login both give a
  real session with working `systemctl --user` and user journal.

The questions below are answered there; they are kept for reference.

**Policy variation (product owner, 2026-10-25).** The lab host has the default,
permissive OL9 policy. Customers may have stricter fapolicyd settings, and the
design must not depend on rules that a site can remove, nor ask a site to relax
its policy. Variants to support or refuse clearly:

| Setting | Lab default | Stricter variant | Affects |
| --- | --- | --- | --- |
| Rule 12 (shell scripts allowed for all) | present | removed | any delivered script run from media |
| Rules 1/2 (root may open/run anything) | present | removed | root running untrusted Python/scripts |
| `trust` | `rpmdb,file` | `rpmdb` only | today's release publication, which enrolls releases in the `file` trust database for the runtime user's Python |
| `integrity` | `none` | `sha256` or `ima` | today's release helper accepts `none`, `size` and `sha256` (`scripts/release.py`); runtime verification of the others is outstanding |
| Mount options | default | `noexec` on `/var/tmp` or media | executing from upload/media |

Design principles: build only on `trust = rpmdb` and on no other permissive
rule; detect the actual policy in preflight and name what is missing and who
must act, never change it; document one explicit supported policy range and
refuse anything outside it before changes. Add a lab profile with
`trust = rpmdb`, `integrity = sha256` and rules 1, 2 and 12 removed, and repeat
the recipe there before choosing a design; RPM delivery is the only option
expected to work under every variant.

**RPM prototype (2026-10-25).** At the product owner's request a lab prototype
wraps built bundles as signed, side-by-side-versioned RPMs plus a
`<product>-host-setup` command: [RPM-PROTOTYPE.md](acceptance/RPM-PROTOTYPE.md)
(`rpm-prototype/`). Run once on the lab on 2026-10-25 (network on, default
policy): install, upgrade and `dnf remove` worked with trust from rpmdb only
and no FANOTIFY/AVC denials; the administrator's part was typeable from
paper, the runtime user's part was not (see the results). Strict profile not
tested. No product code changes; no automated regression coverage.

- Does the default OL9 fapolicyd policy deny `bash setup.sh` for an untrusted
  shell script on DVD/USB or in the upload directory? (For Python this was
  observed in the item 54 lab runs; for shell it is not verified.)
- Is a tool installed from an RPM trusted and runnable under the default policy
  and the `integrity = none` baseline, without extra rules?
- How does OL9 verify the signature of a local RPM file (`rpm -K`, `dnf install
  ./file.rpm` with `localpkg_gpgcheck`), and what does the operator see?
- Does `sudo machinectl shell <runtime>@` give the runtime user a real session
  (user manager, `XDG_RUNTIME_DIR`, `journalctl --user`) so one person can
  switch roles without logging out at the console?

### Chosen direction (product owner, 2026-10-25)

Decided after the [RPM prototype run](acceptance/RPM-PROTOTYPE.md#results-2026-10-25),
which showed that RPM delivery works with the default fapolicyd policy (trust
from rpmdb only, no denials) and makes the administrator's part typeable from
paper, but leaves the runtime user's part (about 3 700 characters of pasted
shell) unchanged. The product owner also stated that long guided sessions on
the closed lab are not feasible.

- **Delivery:** every release and the administrator tool are signed RPMs.
  The main scenario is a **standalone server on a very restricted network**
  without a package repository. A delivery is a directory of files (RPMs,
  public key) that may arrive on USB, DVD, a network
  share or by `scp`; nothing is executed from it, so `noexec` mounts do not
  matter, and an incomplete copy fails the signature/checksum checks before
  changes. An organisation's internal package repository must keep working
  with the same RPMs but is not a separate feature.
- **Administrator:** on a new server, once, with OS tools only (supplier code
  must not run before the key is checked): compare `gpg --show-keys` with the
  fingerprint on paper, verify the tools package against that key alone, and
  install it.
  Trust stays bound to the product's own key (product owner, 2026-10-25): a
  signature from another imported RPM key never authorizes this product. After that, every installation, upgrade and
  retirement is **one command**, `sudo <product>-admin [delivery directory]`:
  it verifies and installs what is new, prepares the host (asking for the
  account and port the first time), retires old releases only when they are
  not needed (plain `dnf remove` of product packages is refused), and says
  what the runtime user does next.
- **Runtime user:** logs in directly (console or SSH), then **one command**,
  `<product>`: it detects the state, asks only for missing values with
  defaults (public address; the port comes from the administrator), takes
  credentials from a private incoming directory, installs the delivered
  releases in dependency order, runs the health checks and prints status. A
  repeat continues after interruption; an upgrade asks nothing unless a new
  release needs a new setting or credential. No values
  block and no shell blocks in the manual.
- **Preflight stops** before changes for anything the host must already have
  (OS packages from the OS media, by name; `subj_cache_size`; journald), and
  says who acts.
- **`release.py` flow:** phased out before the first customer installation;
  one supported flow, one manual.
- **Verification:** the acceptance harness runs exactly the paper commands
  (review guide section 7), including the strict fapolicyd profile above,
  first installation, upgrade, retirement and interruption/retry. Manual lab
  sessions are limited to one short paper/human trial (item 68).

### Phasing decision (product owner, 2026-10-26)

For now the bundles are delivered as RPMs **without signatures**: the RPMs are
placed in a fixed location on the server and installed with `dnf`. Signing must
be supported later, possibly in about two years. **Signing and every challenge
that comes with it are deferred, not removed.** Nothing in "Chosen direction",
the plan or the WP0 evidence about signatures is deleted or weakened in text; it
becomes phase 2.

- **Phase 1 (now):** unsigned release and tools RPMs, installed with `dnf` from
  the fixed location; trust in fapolicyd from the RPM database (WP0 probes A,
  B, E: unaffected by signing); host preparation, runtime command, retirement,
  lock and repair as planned where they do not depend on signatures.
- **Phase 2 (deferred, unchanged scope):** product-key-bound signature
  verification, the paper fingerprint and key bootstrap, isolated keyring
  checks, signature predicates in the manual, and the WP0 signature evidence
  (probes C1, C2 and the signature part of D). Rerun those probes when phase 2
  starts; the 2026-10-25 evidence is historical by then.
- **Phase 1 must not make phase 2 harder:** keep package names, file layout and
  versions as planned; keep the build able to sign (`rpm --addsign` stays in the
  pipeline, just not required); keep a clear place in the administrator flow
  where the signature check will go; do not bake "no signature" assumptions into
  code or file formats; anything that turns signature checking off (for example
  `gpgcheck=0` in a repository file) is one explicit, documented setting.
- **Temporary security exception, documented in the review guide:** without
  signatures, whoever can place an RPM in the fixed location and get the
  administrator to install it gets code run as root and trusted by fapolicyd.
  Interim protection: a root-owned location, delivery on trusted media, release
  RPMs with no scriptlets that change the host. The exception ends with phase 2.
- **`release.py`:** stays until phase 1 replaces it; its signed flow is not
  carried into phase 1 and returns as phase 2 design, not as code to keep.
- **Installing RPMs requires root (2026-10-26).** `dnf install`, `dnf upgrade`,
  `dnf remove` and `rpm -i/-e` write the RPM database and system directories and
  refuse to run without superuser privileges; an ordinary account can only
  query (`rpm -q`, `rpm -qi`, `rpm -ql`, `dnf list installed`, `dnf info`).
  Installing, upgrading and removing product RPMs is therefore always an
  **administrator** task with sudo; the runtime user never installs packages and
  keeps no sudo. Workarounds that would let the runtime user install (a sudoers
  rule for `dnf`, polkit/PackageKit `pkcon install-local`) conflict with the
  no-sudo requirement and are not used. The manual's prerequisites must say
  that someone with root access is needed for every delivery; if the person on
  site has no sudo, nothing can be installed. To confirm on a lab host as an
  ordinary user: `dnf install -y /tmp/missing.rpm` must report the superuser
  error, and `sudo -l` must show `not allowed` for the runtime account.
- **Open decisions for phase 1:** (1) the fixed location: a local repository
  (`repodata/` plus a `.repo` file, `dnf install <name>`) or a plain directory
  (`dnf install /path/*.rpm`); (2) whether the administrator installs with
  plain `sudo dnf` or through the administrator command (either way it is the
  administrator, see above). (2) decides whether WP0 probes F (removal guard)
  and H (stop on a release installed outside the administrator command) remain
  phase 1 requirements. Consequences, to inform the decisions (not decided):
  - (1) Local repository: shorter commands from paper (`dnf install <name>`)
    and one explicit, documented signature-check setting in the `.repo` file,
    as the phase rules ask; but the build must produce `repodata/` and the
    administrator must place a `.repo` file once. Plain directory: no
    repository metadata and nothing to place, but longer commands with a path
    and glob, and the signature-check setting goes on each command line
    (`--setopt`) or into `dnf.conf`.
  - (2) Administrator command: one command per role (requirement 6), and the
    retirement guard, selection checks and trust poll stay in one place, so F
    and H remain phase 1 requirements. Plain `sudo dnf`: fewer tools to build
    in phase 1, but the administrator types dnf options and file names, and
    the 2026-10-25 decision "a conservative guard also for plain `dnf remove`"
    must then hold through package scriptlets alone (F); H would not apply.
  - Both choices keep phase 2 possible; neither changes package names, file
    layout or versions.

Implementation plan: [RPM-DELIVERY-PLAN.md](docs/RPM-DELIVERY-PLAN.md),
revision 3.3; the WP0 matrix passed at `3222efb` after an earlier attempt that
stopped before any probe ([report](acceptance/RPM-WP0.md)); not implemented. Product-owner
decisions recorded there: trust bound to the product key, immutable versions,
and a conservative guard also for plain `dnf remove`. Work package 0 is an
investigation with explicit go/no-go criteria.

Open points for the design: how answers are given non-interactively for the
harness; dependency order and version selection when several releases are
installed; the retirement guard; how credentials of the organisation's PKI or
PFX fit the credential-folder prompt; package naming for side-by-side versions
(no automatic `dnf upgrade`); disk space (images are stored uncompressed);
supplier signing key management; console-only and one-person use; whether the
strict profile holds.

### Design options considered before the decision

- Trusted tool delivery: a signed RPM installed once (`rpm --import` with a
  fingerprint compared against paper, `rpm -K`, `dnf install`), so the
  per-delivery command is `sudo <product>-setup`; or a short verified copy into
  a protected path; the current stdin bootstrap stays only for automation.
- An interactive `setup` front end over the existing authenticated `release.py`
  operations, with the same trust boundaries.
- Runtime `install-set` (item 66) with prompts or default locations for settings
  and credentials instead of options.
- Larger and not decided: shipping the bundles themselves as RPMs so `rpm` and
  fapolicyd's RPM trust replace parts of the custom publication; assess image
  size, upgrade and retention before considering it.

Deliverables: lab findings for the questions above, a chosen design recorded in
a plan document, then changes to 65/66 and a printed-manual human trial under
item 68 (console-only and SSH variants, one person with both accounts).

### Command-line parsing and operator logging

Split out on 2026-10-28 into
[item 73](#73-parse-command-lines-with-argparse-subcommands) (argparse
subcommands) and [item 74](#74-one-operator-message-convention-and-python-logging)
(message convention and Python `logging`), so they can be done before the RPM
work. The new `<product>-admin` and `<product>` commands of WP2/WP3 use both
from their first version.
[Item 75](#75-make-python-lifecycle-code-easier-to-follow-diagnose-and-change) is
limited to incremental lifecycle readability/testability; coordinate any shared
path interfaces with this RPM work rather than redesigning either command flow.

## 66. Install sets: several signed bundles through one entry point

Status: planned, high priority (2026-10-23), after item 65. Implementation
plan: [INSTALL-SET-PLAN.md](docs/INSTALL-SET-PLAN.md), revised 2026-10-24 with
the product owner: no supplier set manifest (bundles arrive one per DVD or many
per USB stick); `install-set` installs the newest published version of every
published component; publication is the selection; no rollback (needs a
database restore, backlog 3). Where the text below says manifest, the plan
supersedes it. Requested by the
operator after the manual backlog 64 run: put e.g. platform, identity and app1
in one directory and have one `install.sh` install them all.

Shape to investigate: an install set directory with an explicit manifest
(product, components, versions) and the signed bundles with `.asc`/`.sha256`.
Bundles stay separate component releases (each has its own `bundle.yaml`,
`VERSION`, `deploy.sh` and modules), so never unpack them on top of each other.
The administrator part authenticates and publishes every listed bundle (item
65); the runtime account then runs one command that, in declared dependency
order, runs `init-config` where needed, stops for required operator edits or
credentials with a clear message, and runs `validate`/`install` per component.

Contracts: install only what the manifest lists (not every archive that happens
to be present); keep independent component versions; keep existing config and
credentials; offline only; a rerun after interruption continues without
restarting finished components needlessly; the runtime account needs no sudo.
Coordinate with item 60 (CLI name) and the per-component lifecycle; do not add a
second deployment engine. New command-line options follow
[item 73](#73-parse-command-lines-with-argparse-subcommands) (argparse subcommands, no hand-written `sys.argv`
conditions). Tests: dependency order, partial failure and retry,
manifest/bundle mismatch, and a real OL9 run.

Apply the [mandatory operator review](docs/REVIEW_GUIDE.md#7-mandatory-operator-and-procedure-understanding-review)
to the complete multi-bundle task. One manual must show how to supply/select the
install set, run 65's administrator preparation, log in through SSH without sudo,
provide required public config/credentials, and invoke the runtime installation
command. Give exact continuation commands when it stops for input or fails after
one component. Do not make the operator infer dependency order, choose internal
helpers or display sensitive values to diagnose a stop.

The automated scenario must use those same public commands and manual steps for
first installation, unchanged rerun and partial-failure continuation in a fresh
SSH session, asserting retained config/credentials and no unnecessary restart of
completed components. No harness loop over lower-level component commands may
stand in for the documented install-set entry point. Reuse 65/67's preparation
and SSH path, with drift tests for the manual-command mapping.

Document an AI walkthrough and a separate unassisted human trial of the whole
install set, including command/edit counts, elapsed time, errors, stops and
explanations requested. Both assessments of the future install-set procedure
remain outstanding; existing per-component tests/manual runs do not prove them.
The [current operator baseline](acceptance/OPERATOR-REVIEW.md) records the gaps.

## 67. Acceptance scenario with a real ssh login as the runtime account

Status: planned, high priority (2026-10-23). Item 65 now supplies a focused
manual-matched setup/initial-install SSH path; this item must extend it through
logout/reboot/upgrade/retirement and retention assertions. Its real lab execution
and human usability evidence are still pending. The ordinary automated matrix runs runtime
commands through the administrator's `sudo -u`; it passed while a real login
could not read its user journal on a fresh host (manual backlog 64 run).

Add a harness scenario that creates a runtime account without sudo (and asserts
`sudo -l -U` denies it), installs a lab-only ssh key for it, and runs every
runtime step over `ssh <account>@prod` without setting `XDG_*` or other login
environment: bootstrap file, `init-config`, credentials, `validate`/`install`,
`systemctl --user`, `journalctl --user` (must show the service's entries),
HTTPS including the identity discovery endpoint, logout, reboot before login,
a fresh login with the same checks, upgrade with state comparison and `retire`.
Start from a host without `/var/log/journal` so the journal contract chosen in
item 65 is verified. Do not grant `systemd-journal`/`adm` or sudo to make it
pass. Drive the commands from `docs/PRODUCTION-INSTALL.md` or a tested explicit
mapping from its step IDs; fail harness tests when command, account, prerequisites
or order drift. Remove the lab key in cleanup.

Exercise the exact manual bootstrap/preparation command from 65 and the runtime
flow from 66 when available. Cover first execution on a fresh host, successful
repeat, and interrupted preparation/installation followed by a new SSH session
and the documented continuation command. Do not pre-create journals, product
directories, pinned keys, manager drop-ins or the runtime bootstrap file through
private harness logic. VM reset, artifact delivery and the disposable SSH key
are test infrastructure; any supplied OS/account baseline must match the stated
manual prerequisites. Missing prerequisites must exercise documented diagnosis
and remedy, not an invisible harness fix.

Apply the [mandatory operator review](docs/REVIEW_GUIDE.md#7-mandatory-operator-and-procedure-understanding-review)
separately from harness/code review. Record an AI literal walkthrough of the
tested manual and a separate limited-Linux-experience human trial on a fresh
host, without oral help. Record time, errors, stops, command/edit counts and
explanations needed; assisted tasks require a new unassisted trial after fixes.
The human trial is outstanding, and the [current AI baseline](acceptance/OPERATOR-REVIEW.md)
has findings. A green SSH acceptance scenario proves execution of that path,
not that the manual is easy to understand; report these outcomes separately.

## 61. Verify Secret-derived environment values in init containers

Status: done, 2026-10-22; local product/harness tests and real Podman/Quadlet
verification passed. Runs `init-secret-space-20261022-175002` (normal app1) and
`init-secret-renamed-20261022-181444` (renamed product) both CLEAN PASS at `52f28e4`.
See [the recorded evidence and limits](acceptance/INIT-SECRET.md#completed-real-lab-verification-2026-10-22).
Requested after an operator encountered a failing migration init container.
No confirmed renderer or Podman defect; no speculative product workaround added.

Implementation/evidence: [INIT-SECRET.md](acceptance/INIT-SECRET.md).
`acceptance/init_secret_test.py` renders a minimal component with retained
synthetic password and dev overrides, tests init/control processes through direct
replacement, builds/relocates an offline bundle, removes its source and rerenders
from persistent config through the release modules for Quadlet start/restart.
Each execution requires exact nonempty values, an independent expected-value
check, a fresh init success token and zero init exit. Host commands are bounded,
diagnostics withheld and cleanup UUID-scoped. Both normal and renamed lab flows
invoke it. Product tests also exercise production init-config/install/retry.

Local evidence on baseline `735b39d` plus this working change: 30 focused product
tests and 230 acceptance-harness tests pass (including eight new probe tests).
`platform --isolate` ran 384 tests: 380 passed, three signing tests failed because
gpg-agent key generation is unavailable, and one unchanged host-delivery test
failed because `/proc/self/fd/0` is unavailable in this environment. No tests were
silently excluded. Static checks and the understandability review are recorded
in the verification document. Historical item 41 lab runs do not verify this new
init path. The original task and acceptance criteria follow.

### Operator report and coverage gap

The organisation's external Duende Identity migration image runs Grate and
reports `Required argument missing for option: --connstring`. The operator
confirmed that the image expects `APP_CONNECTIONSTRING`. Its manifest uses:

```yaml
env:
  - name: APP_CONNECTIONSTRING
    valueFrom:
      secretKeyRef:
        name: sts-migrations
        key: connection-string
```

Inspection of the created migration container reports that the variable exists
but is empty. The rendered Secret's content has not yet been checked, and the
organisation's Podman version, effective configuration and image entrypoint
have not been captured. Do not infer a database, seeding, Grate or Podman bug
from this observation alone. Do not require the operator's private image,
credentials or full connection string to build the regression scenario.

At the reviewed baseline (`7c3ce53`), product tests cover Secret-template
composition and key validation. `acceptance/secret_templates_test.py` checks
Secret env/file delivery and replacement through real kube play and Quadlet,
but uses a regular container and hand-written Secrets. The .NET connection
probe in `acceptance/database_test.py` also uses a regular container. Neither
proves the complete generated-Secret-to-init-container flow. Historical green
lab runs for item 41 remain valid evidence for their existing scope, not for
this missing case. Tests of the harness use mocked host commands and cannot
establish actual runtime delivery.

### Detailed instructions for the implementation agent

1. Read [AGENTS.md](AGENTS.md), [the review guide](docs/REVIEW_GUIDE.md),
   [test instructions](tests/README.md), [acceptance instructions](acceptance/README.md),
   [Secret-template verification](acceptance/SECRET-TEMPLATES.md) and items 33,
   41, 56 and 57. Recheck the current code and coverage before implementation.
   Trace effective config through `deployment/templates.py`, `render.py`,
   dev prepare and production install to the actual Podman input. Check
   `initContainers` handling, Secret ordering/key selection, top-level config
   replacement and container recreation. Verify actual process environment;
   runtime inspection alone is not sufficient evidence of delivery.
2. Build a minimal declarative fixture with arbitrary component/resource names,
   a retained synthetic password file and `SECRET_TEMPLATES` composing a full
   connection string. Render through the real product code. Use an already
   available probe image whose process can inspect its environment, without
   depending on `apps/`, Duende, Grate, a registry connection or a database.
   Support an explicit image argument for closed-network reproduction; document
   the image's required interpreter and command. Keep ordinary-container coverage
   as a control and extend existing helpers rather than creating a second harness.
3. Add focused product tests for generated Secret bytes and the preserved
   `env.valueFrom.secretKeyRef` in an init container. Cover wrong/missing keys
   and declarations under the existing validation contract. Exercise component
   dev overrides and production retained config where relevant to the report.
   Do not introduce a blanket ban on empty generic Secret values without a
   separately justified contract change; this connection-string probe must
   explicitly reject empty or missing values.
4. Add a real runtime scenario for the full chain: effective config and retained
   password -> rendered Secret -> `secretKeyRef` -> init process environment.
   Require exact equality with an independently constructed expected value and
   require a non-empty value. Comparing env only with a mounted file is not
   enough: both could contain the same stale or empty value. A main container
   may confirm successful init completion, but its own env success must never
   substitute for the init process assertion. Record failures even when an init
   container has already exited; bound waits and handle the supported init type
   explicitly, including the operator's `always` annotation.
5. Exercise initial direct `podman kube play`, rerendered replacement, initial
   Quadlet start and the supported rerender/restart lifecycle. Change a public
   recipe input for the second expected value while retaining the password;
   require the init container to execute again and receive the new value.
   This tests stale-value detection without implementing database password
   rotation. Include an isolated offline release using persistent config so a
   source-only render test cannot mask a production delivery difference. Keep
   this focused; do not duplicate the entire lab matrix unnecessarily.
6. Add harness regressions showing that missing, empty, wrong and stale init
   values, non-zero init exit and timeout cause failure. Confirm that a healthy
   main container cannot hide a failed/skipped init assertion. Wire the real
   scenario into existing relevant lab flows, including renamed resources.
   Keep product tests runnable via `platform --isolate` without demo sources.
7. If reproduction identifies a product defect, fix it in the responsible
   existing path and add a regression that fails before the fix. If it is a
   configuration, entrypoint or supported-version issue, document the evidence
   and precise correction instead of adding speculative deploy workarounds.
   A passing synthetic probe does not prove the organisation's private image
   works; state what operator-side checks remain. Never print secrets, full
   connection strings, unfiltered inspect output or raw subprocess diagnostics.
   Failure messages should identify the stage/resource/key, not private values.
8. Give the operator a short offline diagnostic procedure to distinguish a
   missing/empty rendered key, wrong reference, stale container and init-process
   consumption failure using presence/length or pass/fail checks. Document exact
   commands, prerequisite image, supported host versions, cleanup and expected
   outcomes. Use disposable names and clean only test-owned pods, volumes,
   Secrets, units and temporary files, including on failure. Never reset the
   operator's database, delete retained credentials or require weaker host policy.

### Acceptance criteria and evidence

- The full generated-Secret-to-init-process path passes with exact, non-empty
  values on initial deployment and after the supported update/restart flow,
  through both direct Podman and Quadlet; the failure cases above are enforced.
- Validation remains side-effect-free and does not read credential contents;
  private data stays in the existing Secret/0600 manifest path, not plain env
  literals, ConfigMaps, command arguments, logs or evidence artifacts.
- Run relevant product tests, `python3 -B tests/run.py platform --isolate` and
  `python3 -B -m unittest discover -s acceptance -p 'test_*.py'`, plus the
  repository's required checks appropriate to changed code. Report failures
  and unavailable prerequisites rather than silently excluding tests.
- Record actual commit, Podman/systemd versions, host policy and commands for
  real runs. Distinguish unit/product, acceptance-harness and real runtime
  results. If the lab is unavailable, deliver the runnable scenario and leave
  runtime verification explicitly pending; mocks or older matrix results do
  not close this gap.
- Complete the understandability review with one successful flow and one
  failed-init/retry flow. Update the relevant coverage documentation and this
  item's status with evidence, preserving historical verification scope.

## 10. Supplement test coverage before structural changes

Status: implemented at `511099e`; the test baseline runs in every lab run
(`03-unit`). The historical 0.2.0 upgrade lab run was never done and is tracked
in item 5. Item 8 proceeded with explicit user authorization.
See [test baseline and lab command](acceptance/TEST-BASELINE.md) for coverage,
results and the retained 0.2.0 upgrade gate. The original task is preserved below.
This task includes the retained 0.2.0 upgrade scenario already tracked in item 5;
implement it once and cross-reference its evidence rather than duplicating it.

Supplement test coverage in `gunstein/podman_offline` before the planned deploy-code refactor.

The goal is to establish a clear, tested baseline for existing behaviour. This is a bounded testing task, not the refactor itself.

### 1. Map existing coverage and run the baseline

Read the current code, tests and verification reports. In particular, check:

- `tests/`
- `acceptance/`
- `deploy.py`
- `bundle.py`
- Root commands and bundle contents.

Run existing product and acceptance-harness tests before changes. Record the commit and results.

Reuse existing fixtures and test tools. Do not duplicate tests already covering the requirements below.

### 2. Test a real upgrade from 0.2.0

Add a focused acceptance scenario upgrading an actual 0.2.0 installation to the current version.

Use an identified historical commit for old code and images. Do not simulate an old release by changing only `VERSION` in current code.

Scenario:

1. Build and install old app1/core and app2.
2. Create user data through the existing e2e/marker mechanism.
3. Record existing versions, config, credential files, database volumes and relevant service observations.
4. Follow the currently documented manual upgrade steps: add required DB fields and `GENERATED_SECRETS` entries to persistent config.
5. Transfer and install the new app1/core bundle.
6. Verify that app1/core works and old app2 still works without unintended changes.
7. Then upgrade app2 and verify the entire installation.

In particular, check:

- Existing database passwords are retained byte-for-byte.
- Database volumes are retained and existing user data remains available.
- Persistent config changes only through explicit operator steps.
- No credentials are regenerated or database users changed automatically.
- The app1 upgrade does not change app2's service, version, config or credentials.
- Login and database operations work after each upgrade stage.
- Trust for the old release is removed only after successful verification, without affecting sibling bundles.

Also test that missing required config additions are rejected before image operations or installed-state changes. A focused local test may cover this if existing coverage is sufficient.

Keep the scenario bounded. Do not repeat the entire reboot, crash and hang matrix if those cases are already covered separately.

### 3. Establish installation failure behaviour

Review existing coverage and supplement it for:

- Failure during `podman load`.
- Failure or a missing image during `podman image exists`.
- Failure during restart or `is-active` for an affected systemd service.

Use existing component installation as the starting point.

Test relevant observations:

- Persistent config and credentials.
- Import archives.
- Route and OIDC client registrations.
- Quadlet and YAML files.
- Version markers.
- Which services were targeted for restart, and in which order.
- Preservation of unaffected sibling components.

Distinguish failures before and after installation begins changing state. Do not assume installation is atomic or rollback already exists.

For a service failure, describe the actual partial state and check that later steps stop and version markers do not falsely claim a completed installation.

Use concrete failure scenarios rather than tests that merely repeat internal function calls.

If you find an existing bug, document it with a focused reproduction. Do not lock in a known bug as desired behaviour or make unrelated product changes without identifying them.

### 4. Test root commands from another working directory

Add integration tests launching the actual wrapper scripts from a working directory outside the checkout/release:

```text
./deploy.sh prepare
./deploy.sh init-config <component>
./deploy.sh install
./deploy.sh uninstall
./build-bundle.sh
```

Use the wrapper's absolute path in the test.

Test commands in the appropriate context:

- `prepare` and bundling from source.
- `init-config`, `install` and `uninstall` from an unpacked bundle.

Verify that resource paths and config selection work independently of the caller's working directory, and that output is not accidentally written there.

Use isolated temporary directories and existing Podman/systemd stubs where appropriate. Do not run production commands against the developer's actual home or container environment.

Where realistic testing requires a service account, user home and systemd runtime, put the check in the existing authorised lab scenario rather than building a complicated new mock framework.

### 5. Scope

Do not implement:

- Extraction into the `deployment/` package.
- A new CLI architecture.
- Directory trust for fapolicyd.
- Password rotation.
- Automatic config or database migration.
- A new rollback mechanism.

Tests for the future package structure, `python -B`, bytecode exclusion and directory trust belong to the refactoring task.

Retain existing security checks and test assertions. Do not weaken them to make new scenarios pass.

### 6. Verification

After changes, run:

- All product tests.
- All acceptance-harness tests.
- Relevant ruff, format, pyright, vermin and shellcheck checks using the project's existing setup.

Retain Python 3.6 compatibility for host tools and product tests.

Run the new real upgrade scenario if the established lab is available and execution is authorised. Do not reset or change other environments.

Clearly distinguish local tests, harness tests and actual target-host runs. If a lab run is unavailable, implement the scenario and report that the upgrade remains operationally unverified.

### 7. Delivery

Briefly report:

1. Baseline commit and test results before changes.
2. Coverage that already existed.
3. New tests and the concrete failures they guard against.
4. Historical and new revisions used in the upgrade scenario.
5. Test results, including actual lab execution.
6. Any product bugs found and verification gaps.
7. Whether the baseline is sufficient to begin refactoring.

Update relevant test documentation with guarantees and limitations.

Prefer a few strong tests over many overlapping tests.

## 1. Deploy maintainability refactor

Status: done in 0.4.3 after items 10, 8, 9, 12 and 13; directory trust of each
release's `deployment/` package (add, wait, retire) is verified on the target by
the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS). See [verification](acceptance/DEPLOY-REFACTOR.md).
Further lifecycle readability work is planned separately in
[item 75](#75-make-python-lifecycle-code-easier-to-follow-diagnose-and-change);
this completed package extraction and its historical evidence remain unchanged.
No existing installation requires migration: this implementation adds no migration,
old-module fallback or compatibility layer. The original task follows.

Refactor the deploy implementation for maintainability without redesigning the architecture or changing behavior.

Goal: a medium-experienced developer with some Python knowledge and little familiarity with this project should be able to understand the install/upgrade/uninstall flow quickly.

Keep the root commands unchanged:

- `./deploy.sh prepare`
- `./deploy.sh install`
- `./deploy.sh uninstall`
- `./build-bundle.sh`

Move deploy internals into a small Python package, roughly:

```text
deployment/
  __init__.py
  __main__.py
  cli.py
  deploy.py
  render.py
```

Keep `./deploy.sh` as the stable entrypoint and run Python with `-B`, e.g. `python3 -B -m deployment`, so trusted release code does not create `.pyc`/`__pycache__`. Preserve invocation from outside the release directory as well.

Responsibilities:

- `render.py`: config/YAML loading, placeholders, generated-secret helpers, SECRET_FILES/VOLUME_FILES, Secret/PVC generation, manifest validation/rendering.
- `deploy.py`: production environment, component/bundle selection, VERSION/CORE_VERSION logic, registrations/routes/OIDC clients, image load/verify, Quadlet/systemd, install/uninstall lifecycle.
- `cli.py`: argument handling and error reporting.
- `__main__.py`: minimal delegation to the CLI.
- Do not introduce unnecessary classes or framework abstractions.

Important simplifications:

- Make the main install flow easy to read: determine plan → stage registrations → render → load/verify images → apply registrations → write Quadlet/YAML → restart affected services → write version markers.
- The main install function should read as that lifecycle sequence. Helper names should make persistent writes and service restarts obvious.
- Avoid surprising side effects in `render()` where practical; make persistent generated-secret creation explicit.
- Split `registration_stage()` if that improves readability.
- Reduce duplicated component truth between `bundles.yaml` and hardcoded Python where this can be done simply, but do not build a generic plugin system.
- Keep standalone manifest support used by examples/tests, but isolate it from the main component lifecycle. Do not remove supported examples as part of this refactor.

Behavior preservation:

- Preserve existing prepare/install/upgrade/uninstall behavior, including component isolation, core version rules, restart decisions, persistent state retention and explicit data deletion.
- Preserve validation order and failure semantics, including which persistent files may have changed when an operation fails.
- Explicit generated-secret creation must not happen earlier than today.
- Treat the lifecycle sequence above as a readability goal, not permission to reorder safety checks.
- Do not silently fix unrelated bugs. Report discovered issues separately.

fapolicyd:

- Support multiple Python files using directory trust.
- Trust only `<release>/deployment/` recursively with the existing per-bundle trust file.
- On upgrade, remove the old release’s `deployment/` trust entry after the new release has been verified successfully.
- Do not trust the whole release and do not add new allow/crun/memfd rules.
- Keep SELinux/fapolicyd hardening unchanged.
- Update trust verification and cleanup to match the directory-based approach.

Bundling:

- Keep `bundle.py` mostly as-is.
- Include `deployment/` in offline bundles.
- Never include `.pyc`, `__pycache__`, generated secrets or private state.
- Keep all checksum guarantees.
- Ensure imports and resource paths work both from the source checkout and from an unpacked offline bundle.

Tests/docs:

- Adapt existing tests; preserve Python 3.6 compatibility.
- Run product tests, acceptance-framework tests, ruff, format check, pyright, vermin and shellcheck.
- Add focused regressions for the root entrypoint, package contents in bundles, no bytecode files, unchanged prepare/install/uninstall behavior, and directory-based fapolicyd trust/upgrade cleanup.
- Check that failed validation or image verification preserves existing deployed state as before.
- Update README/trust instructions and stale monolithic service names.
- Add a short `ARCHITECTURE.md` explaining module responsibilities, the lifecycle flow, shared core versus independent components, and persistent state versus disposable release files.
- Report acceptance-framework tests separately from actual target-host acceptance runs. If no lab is available, state explicitly that directory trust remains unverified on the target.
- If a required check cannot run, report the reason rather than treating it as passed.

Prefer a mechanical move with passing tests first, followed by focused readability improvements. Prefer simpler code over more generic code.

Do the refactor, run the checks, and report:

1. New structure.
2. What moved where.
3. Any intentional or discovered behavior differences, including the required fapolicyd trust change.
4. Test and static-check results, clearly distinguishing local checks from target-host verification.
5. Anything intentionally left for later, including unrelated issues discovered during the work.

## 2. PostgreSQL password rotation

Status: planned; separate from the deploy refactor.

- Define an explicit operator-controlled procedure coordinating the database role
  password, persistent secret file and running clients for core/app1/app2.
- Use the existing ownership, file paths, Secret keys and volume mapping in
  [README.md](README.md#postgresql-configuration-and-credentials).
- After an explicit password change, re-render Secret templates and recreate
  client containers; changing a source file or restarting systemd alone is not
  database-role rotation. Preserve the `newer-only` render policy.
- Define failure handling and verification before selecting a mechanism. Verify
  authentication after rotation and retention of database data.
- Keep session keys, demo-user passwords, OIDC keys and certificates outside this
  database-specific procedure. Never rotate implicitly during install or upgrade.

## 3. Database backup and credential recovery procedures

Status: planned; separate from password rotation.

- Document and exercise coordinated backup/restore of database volumes and their
  persistent password files, including private permissions.
- Define an explicit recovery procedure for missing credentials or a mismatched
  database password, with operator prerequisites and authentication checks.
- Preserve refusal to generate a replacement password when database state exists.
  Do not delete/reinitialize volumes or assume that changing the secret file
  changes the PostgreSQL role password.
- Keep credentials and connection strings out of logs and acceptance evidence.

## 4. Migration from retained monolithic 0.1.x installations

Status: superseded by the clarification in item 15: no existing installations
require migration. The original proposal below is retained as history, not
planned implementation work.

- Inventory old services, config, credentials and database volumes before defining
  a migration to core/app1/app2/help.
- Define backup, identity/data mapping, service transition and recovery steps.
- Verify retained application data and credentials on a real migration fixture.
- Do not add automatic migration or destructive cleanup to normal upgrades.

## 5. Close documented runtime verification gaps

Status: planned verification work; current evidence remains unchanged.
The retained 0.2.0 upgrade scenario below is implemented as part of item 10;
run the [focused lab scenario](acceptance/TEST-BASELINE.md#run-the-historical-upgrade-in-the-lab)
and cross-reference its evidence here rather than implementing it again.

- Run a full retained 0.2.0 → 0.2.1 upgrade with the documented manual DB config
  additions, verifying existing credentials, volumes and sibling state.
  Prioritize this before upgrading an important retained installation. Start with
  the old release's real config, initialized database volumes and credentials;
  apply only the documented manual additions, then install the new images and
  verify authentication, CRUD, persistent data and unaffected siblings. Existing
  legacy-password fixtures do not replace this end-to-end upgrade scenario.
- Verify supported Podman versions beyond the currently tested 5.8.2 before
  claiming runtime coverage for them.
- Verify localized PostgreSQL authentication diagnostics, preserving the distinction
  between authentication refusal and DNS/network failures.
- Run host tooling on an actual Python 3.6 interpreter if a suitable environment
  is available; current Python 3.6 compatibility evidence is static.
- Report local/harness checks separately from actual target-machine results.

Source and existing evidence: [DATABASE-VERIFICATION.md](acceptance/DATABASE-VERIFICATION.md#limits-and-deferred-work).

## 6. Runtime connection strings for existing .NET images

Status: superseded by item 41's accepted Secret-template delivery for unchanged
images reading a complete connection string. Identity 0.2.2 demonstrates
`secretKeyRef`, replacing the in-app builder. A launcher or derived image is no
longer required. The earlier prohibition on connection strings in private YAML
is explicitly replaced: existing 0600 Secret YAML is the accepted storage path,
and env inspection by service user/root is an accepted exposure. Runtime lab
verification remains outstanding under item 41. File-consuming applications can
continue using Secret mounts without environment copies.

## 7. PostgreSQL preflight manifest compatibility

Status: follow up when adding another PostgreSQL image or mount layout.

- Document and test the current assumptions in `database_preflight()`, including
  the `/var/lib/postgresql/data` mount and explicit Secret `items` mapping.
- Before supporting a different layout, ensure the guard identifies its actual
  password source and persistent database volume. Unsupported layouts must fail
  clearly before secret generation or persistent changes.
- Add focused regressions for each newly supported layout. Keep database-state
  checks in the lifecycle layer and avoid a generic PostgreSQL framework.
- Since 0.4.10 a container that mounts `/var/lib/postgresql/data` counts as a
  database container even without any `POSTGRES_PASSWORD*` variable, so
  `PGPASSWORD`, `envFrom` and missing password settings are refused there.

Review source for items 6–7 and the expanded upgrade scenario: static code review
of `improvements-0-2` through `87f4e98`. These are follow-up requirements and
verification gaps, not evidence of completed runtime support.

## 8. Rename core to platform

Status: done in 0.3.0; the separate platform bundle, its upgrade and the
downgrade refusal (`10-platform-*`) are verified by the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS).
The user explicitly selected a separate platform bundle for this step. Platform
still contains Identity until item 9. The original task below is retained;
[PLATFORM-RENAME.md](acceptance/PLATFORM-RENAME.md) describes the delivered model,
compatibility boundary and checks. The later separate-bundle clarification takes
precedence over the original embedded-platform assumptions in this task.

Rename the shared `core` component to `platform` in `gunstein/podman_offline`.

This is a bounded rename. Retain architecture, functionality, security checks and component isolation. Do not perform the module refactor at the same time.

### 1. Goal and terminology

Use `platform` for the shared component containing Identity, the identity database and the HTTPS proxy.

App1, app2 and help must retain the same dependency on this component that they currently have on core.

Apply the rename consistently across active code, config, manifests, tests and documentation.

### 2. Inventory affected names before changes

Inspect at least:

- `components/core/`.
- `CORE_VERSION`.
- Bundle definitions and descriptors.
- Functions, variables and error messages.
- Persistent component directory and installed marker.
- Quadlet/systemd names.
- Pod, Secret, PVC and ConfigMap names.
- Hostnames and `DB_HOST`.
- Registration and import archive names.
- Certificate generation and associated paths.
- Dev scripts, acceptance scripts and fixtures.
- README, verification reports and backlog.

Distinguish component-owned names, external concepts and historical references. Do not apply an indiscriminate global replacement.

### 3. Intended names

Use names including:

```text
components/platform/
PLATFORM_VERSION

/var/lib/myproduct/platform/config.yaml
/var/lib/myproduct/installed/platform

myproduct-platform.service
myproduct-platform.kube
myproduct-platform.yaml
```

Resources with the `core-` component prefix become `platform-`, for example:

```text
platform-identity
platform-identity-postgres
platform-identity-data
platform-database-password
platform-routes
platform-clients
```

Update every reference to renamed resources.

Retain names that do not need to change:

- Product name `myproduct`.
- Shared network `myproduct`.
- App1/app2/help and their own resources.
- Public URL paths such as `/identity/`, `/app1/`, `/app2/` and `/help/`.
- Database users and database names, for example `identity`.
- OIDC client IDs and scopes.
- Image repositories not containing the component name.

Do not change credentials or certificate contents merely because the component is renamed.

### 4. Bundle model and commands

The bundle model becomes:

```yaml
app1: [platform, app1]
app2: [platform, app2]
help: [help]
```

Retain the three existing bundle types and filename patterns:

```text
myproduct-app1-<version>-offline.tar.gz
myproduct-app2-<version>-offline.tar.gz
myproduct-help-<version>-offline.tar.gz
```

Do not create a separate platform bundle.

Retain root commands. Update component arguments:

```sh
./deploy.sh init-config platform
./deploy.sh uninstall platform
./deploy.sh uninstall platform --delete-data
```

Old `core` arguments must not perform unintended operations. Give a clear message about the new name if they are used.

Platform must still:

- Be installed with the first app.
- Be retained at equal platform version, using existing registration-change and restart rules.
- Be upgraded for a newer platform version.
- Reject downgrades.
- Refuse uninstallation while app1, app2 or help requires it.

### 5. Existing installations and migration

The rename affects persistent resource names. It must not silently replace an existing database with a new empty volume.

This task does not authorise automatic deletion, reset or migration of existing production state.

Use these boundaries:

- Implement the new naming for new installations.
- Do not implement automatic migration from `core` to `platform`.
- Detect old core layout and reject operations that could create a parallel platform installation or affect old state.
- Fail before new secret generation, image operations, installed config/registration writes or service changes.
- Clearly explain that the old installation requires a separate migration procedure or an explicit fresh installation.
- Also reject mixed core/platform state rather than guessing which is authoritative.

Do not rely only on the installed marker. Inspect relevant old config/service files and persistent database volumes, because uninstall may have retained data.

Keep the check concrete and bounded to known product resources. Failure of a required state check must not be treated as absence.

Leave old files and volumes untouched on rejection. Do not add automatic cleanup.

Clearly document the compatibility break. Existing installations must remain manageable with their previous release.

### 6. Versioning

Do not publish the change under the same release version as the existing layout.

Update `VERSION` and the new `PLATFORM_VERSION` according to project conventions, and explain the effect on upgrade compatibility.

Do not change image tags if image content is unchanged. If image content must change, use new tags and retain immutable release tags.

### 7. Tests

Update existing tests to the new naming without weakening assertions.

Verify at least:

- Correct platform prefixes and references in rendered YAML.
- Platform config initialisation.
- App config inherits the correct shared values from platform.
- App1 and app2 can each be the first installed app.
- Help alone is rejected.
- Equal, newer and older `PLATFORM_VERSION` are handled as before.
- Help-only and app-only upgrades retain unaffected components.
- Database passwords and volumes are linked correctly.
- Platform uninstall is blocked when dependents exist.
- `--delete-data` targets only the selected component's resources.
- Bundle contents, image selection and checksums are correct.
- Old core layout and mixed layout are rejected without changes.
- Old core database volumes are detected even without an installed marker.
- State-check failures produce controlled rejection.

Retain historical fixtures and release sources when they are intended to represent old code.

A test that previously upgraded from a core-based release cannot merely be renamed and still claim to test the historical upgrade. Retain relevant historical coverage, but explicitly test rejection at this new compatibility boundary.

### 8. Documentation and cleanup

Update active descriptions, commands, paths and diagrams to `platform`.

Search the entire repository for relevant occurrences of `core`, `CORE_VERSION` and `core-`.

Explain deliberately retained occurrences, such as:

- Old-layout detection.
- Historical fixtures.
- Earlier verification reports.
- Documented migration restrictions.

Do not rewrite old test results or historical evidence to suggest they ran with the platform layout.

Update the backlog with any future migration task. Keep it separate from the module refactor.

### 9. Verification and report

Run:

- All product tests.
- All acceptance-harness tests.
- Relevant ruff, format, pyright, vermin and shellcheck checks.

Retain Python 3.6 compatibility for host tools.

Run relevant fresh-installation and lifecycle scenarios in the established lab if available and authorised. Do not delete existing state or reset other environments.

Distinguish local tests, harness tests and actual target-host runs.

Report:

1. Names and files changed.
2. Names deliberately retained.
3. How old and mixed layouts are detected and rejected.
4. Consequences for existing installations.
5. Version changes.
6. Test results and verification gaps.
7. Deferred work, particularly any migration.

Prefer simple, consistent naming over a generic alias or compatibility framework.

## 9. Extract Identity into a separate component and bundle

Status: done in 0.4.0; verified by the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS), including the Identity upgrade
scenario. Platform and Identity are separate bundles with explicit dependencies. See [Identity verification](acceptance/IDENTITY-SPLIT.md). The original task follows.

Extract Identity from `platform` into its own component and separate offline bundle in `gunstein/podman_offline`.

This functional split precedes the planned module refactor. Do not perform the module refactor at the same time.

### 1. Inspect the current solution first

Read current code, bundle definitions, dependency model, tests and documentation.

Platform is already intended as a separate bundle. Do not start from the earlier model where app bundles included core/platform.

Reuse existing component, bundle, version and dependency mechanisms. Do not introduce a parallel system or generic plugin framework.

Record the baseline commit and run existing product and acceptance-harness tests before changes.

### 2. Intended ownership

After the split:

| Component | Responsibility |
|---|---|
| `platform` | HTTPS proxy, proxy TLS material and public route registrations |
| `identity` | IdentityServer, identity database, database password, signing material, Data Protection state, demo users and OIDC client registrations |
| `app1` | App1, its database and its credentials |
| `app2` | App2, its database and its credentials |
| `help` | Help content and its route registration |

Retain existing ownership and safe lifecycle rules for the shared network and any shared demo CA. Do not delete or regenerate shared material as a result of the split.

Inventory all existing resources and files before moving them so no persistent state is overlooked.

### 3. Separate bundles and explicit dependencies

Use this logical model:

| Bundle | Contents | Dependencies |
|---|---|---|
| `platform` | Platform component | None |
| `identity` | Identity component | Platform |
| `app1` | App1 component | Platform and identity |
| `app2` | App2 component | Platform and identity |
| `help` | Help component | Platform |

Each bundle contains only its own component resources and required images, plus shared deploy code and necessary metadata/defaults.

App bundles must not include or automatically install platform/identity. The Identity bundle must not include platform.

A missing dependency must produce a clear error. Do not attempt network downloads or automatic installation from other release directories.

Update existing bundle building to produce all defined bundles, including separate identity, with the project's established filename pattern.

### 4. Versions and compatibility

Identity must support versioning and upgrading independently of platform and apps.

Use the existing versioning model. If it uses separate version files, introduce a corresponding `IDENTITY_VERSION`. Do not create a new versioning system if a suitable model already exists.

Dependencies must have explicit, documented version requirements. Reuse existing syntax and comparison rules. If no such requirements exist, introduce the smallest adequate mechanism and justify it.

Validate:

- Dependencies are installed.
- Their versions satisfy the incoming bundle's requirements.
- Platform or identity upgrades still satisfy installed dependents' requirements.

Retain required dependency metadata as installed state. Checks must not rely on old release directories still being present.

Do not assume compatibility merely because a version is newer.

Retain existing reinstall and downgrade rules where relevant. Document necessary changes.

All dependency/version rejections must precede secret generation, image loading, registration/service-file writes and restarts.

### 5. Separate route registrations from OIDC client registrations

In the current combined solution both registration types can affect one component. After the split, ownership must be explicit:

- Platform consumes public routes.
- Identity consumes public OIDC client registrations.
- Apps own private client keys and deliver only public client metadata and certificates to identity.
- Identity registers its own public route with platform.
- Help registers only a route with platform.

Retain the index mechanism preventing old import-volume files from keeping removed routes or clients active.

Restart decisions must be separate:

| Change | Expected effect |
|---|---|
| Only app route changes | Platform updated/restarted |
| Only OIDC client registration changes | Identity updated/restarted |
| Both change | Both affected components updated/restarted |
| No registration changes | No unnecessary platform/identity restart |
| Help route changes | Platform affected, identity retained |
| Identity upgraded without changing its public route | Identity affected, platform retained |

App containers must not restart merely because platform or identity restarts. A brief availability or login interruption differs from restarting the apps.

Do not add registration commands if the existing installation flow can handle this clearly.

### 6. Retain the public login contract

The split must not also change:

- `/identity/`.
- Public issuer URL.
- App client IDs and scopes.
- Redirect URIs.
- `/app1/`, `/app2/` and `/help/`.
- App cookie names and paths.

Update internal hostnames and upstream references where necessary.

Platform must run and serve help without identity installed. Proxy configuration must not require DNS resolution of an absent identity service at startup.

Verify shared login between app1 and app2 remains functional.

### 7. Config, secrets and database

Identity gets its own component config and persistent directory:

```text
components/identity/config.defaults.yaml
/var/lib/myproduct/identity/config.yaml
```

Follow the existing config model:

- Defaults are used for initialisation and dev.
- Production uses authoritative persistent component config.
- Upgrade does not overwrite existing config.

Identity must inherit relevant shared values from installed platform during config initialisation, using the established approach for other dependents.

Move identity-specific DB settings, Secret/volume definitions and generated-secret entries out of platform.

Retain:

- One persistent source for each database password.
- Agreement between PostgreSQL server and client.
- Protection against generating a new password when database state already exists.
- Runtime construction of `ConnectionStrings__Default`.
- Correct escaping and safe error handling.
- Existing database user and database name unless there is a necessary reason to change them.

Do not introduce password rotation, database-privilege changes or schema migration in this task.

### 8. Existing installations: no automatic migration

The split affects the persistent identity database, credentials, signing keys, Data Protection state and client registrations.

This task does not authorise automatic relocation, deletion or reinitialisation of existing installed state.

Implement the new layout for new installations. Detect existing layout where identity remains inside platform and reject incompatible install/upgrade before changes.

The check must also handle:

- Retained database volumes without an installed marker.
- Mixed old and new layout.
- Partially existing credentials or service files.
- Failure of required state checks.

Do not treat platform's presence alone as proof of old layout; platform is also a valid standalone component in the new model.

Explain clearly that old layout requires a separate migration procedure or explicit fresh installation. Leave existing state untouched and manageable with its previous release.

Do not silently replace old state with an empty identity database or new signing keys.

Document the compatibility break and track any migration as a separate backlog task.

### 9. Uninstall

Dependencies must control uninstall:

- Identity cannot be removed while installed apps require it.
- Help must not block identity uninstall.
- Platform cannot be removed while identity, app1, app2 or help requires it.

When removing an app:

- Remove its route from platform.
- Remove its public OIDC client registration from identity.
- Update/restart only affected services.
- Retain other components' registrations, services and data.

When removing identity without dependents:

- Remove its route from platform.
- Retain platform and any help component.
- Retain identity data by default.

`--delete-data` must delete only the selected component's own data. Do not delete the shared network, shared CA or other components' credentials.

### 10. Dev and bundling

Dev must use the same component split and registration model as production, even if the dev helper starts the entire demo system together.

Update image building, image selection and bundling as necessary.

Retain:

- Manifest-driven image selection.
- `imagePullPolicy: Never`.
- Exclusion of private state and bytecode.
- Checksums for all delivered files.
- Existing fapolicyd and SELinux model.

The Identity bundle must be transportable and upgradeable alone without retransferring platform or app bundles.

Do not change immutable image tags without building corresponding new images.

### 11. Tests

Update existing tests without weakening security or isolation checks. Add focused tests for:

#### Installation and dependencies

- Platform installs alone.
- Platform and help work without identity.
- Identity without platform is rejected before changes.
- An app without identity is rejected before changes.
- Both app orders work after platform and identity.
- Missing/incompatible dependencies produce clear errors.
- Upgrades breaking installed dependents' version requirements are rejected.

#### Registrations and restart

- Route-only changes affect platform.
- Client-only changes affect identity.
- Both changes affect both.
- Unchanged registrations cause no unnecessary restart.
- Removed routes/clients are not kept active through old import files.

#### Independent identity upgrade

Add a real acceptance scenario that:

1. Installs platform, identity and both apps.
2. Creates user data and verifies login.
3. Builds and transfers only a newer identity bundle.
4. Installs it.
5. Verifies the new identity version and image are actually running.
6. Verifies login and app database operations.
7. Verifies retention of identity data and existing credentials.
8. Verifies platform/app versions, service processes and configuration remain unchanged when registrations are unchanged.

Use an observable change or image identity as evidence; an updated version marker alone is insufficient.

#### Uninstall and old state

- Identity uninstall is blocked by apps, but not help.
- Platform uninstall is blocked by dependents.
- Data is retained by default.
- Explicit deletion is limited to the correct component.
- Old combined platform/identity layout and mixed layout are rejected without changes.

Retain relevant existing coverage for help-only upgrade, app-only upgrade, offline installation, reboot and persistence. Adapt expectations to separate bundles.

### 12. Documentation

Update README and relevant architecture/test documentation to make it easy to understand:

- What each component owns.
- What each bundle contains.
- Installation order.
- How dependencies and version requirements are checked.
- Who consumes routes and OIDC clients.
- Which changes restart which services.
- How identity is upgraded alone.
- Which state is persistent.
- Why old combined layout is not upgraded automatically.

Update active command examples and remove obsolete assumptions that app bundles include platform.

Do not rewrite historical verification reports as if they ran against the new architecture.

### 13. Verification and delivery

Run:

- All product tests.
- All acceptance-harness tests.
- Relevant ruff, format, pyright, vermin and shellcheck checks.

Retain Python 3.6 compatibility for host tools.

Run relevant actual acceptance scenarios in the established lab if available and authorised. Do not reset or change other environments.

Clearly distinguish local tests, harness tests and target-host execution. If lab execution is unavailable, report which guarantees remain unverified.

Report:

1. New component and bundle structure.
2. Resources and state with a new owner.
3. Dependency and version model.
4. Restart rules for routes and clients.
5. Consequences for existing installations.
6. Test results and verification gaps.
7. Deferred work, particularly migration and module refactoring.

Keep the functional split and later module refactor separate. Prefer explicit, simple rules over general abstractions.

## 11. Plan an explicit retained core-to-platform migration

Status: superseded by the clarification in item 15: no existing installations
require migration. The original proposal below is retained as history, not
planned implementation work.

0.3.0 deliberately refuses retained or mixed core/platform state. Design and
review a separate procedure before migrating an important 0.2.x installation.
Inventory config, all credentials/certificates and CA, database and Data
Protection volumes, public registrations/imports, versions/dependencies,
Quadlet/systemd files and trust. Specify backups/restoration, volume identity/data
retention, explicit operator steps, verification and failure recovery. Preserve
password bytes and existing keys; never create an unnoticed empty replacement
database. Test against real historical releases and representative retained data.
Do not implement automatic rename, cleanup, resets or migration as part of item 1.
Include both retained core 0.2.x and combined platform/Identity 0.3.x sources.
Target the separate platform/Identity layout of 0.4.0; neither old layout is
automatically migrated. Coordinate backups, ownership and explicit transitions
with item 9 before implementing a procedure.

## 12. Rename component credential paths

Status: done in 0.4.1; fresh installs with these paths are verified by
the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS). See
[credential-path verification](acceptance/CREDENTIAL-PATHS.md). The deploy
refactor (item 1) is implemented; see its verification report.
This task uses fresh state only and requires no migration or backward compatibility.
The full agent message follows, with heading levels adjusted for this document.

Replace `generated-certificates/` with `credentials/` for component passwords, session keys, private keys and certificates in `gunstein/podman_offline`.

The name `generated-certificates` misrepresents the contents: the directory also contains database passwords and session keys, and material may be generated or externally supplied.

This is a bounded path cleanup. Do not combine it with module refactoring, password rotation or other architecture changes.

### 1. No migration or backward compatibility

There are no existing installations to upgrade.

Implement only the new layout:

- No migration code.
- No fallback to `generated-certificates/`.
- No aliases or compatibility branches.
- No procedure for moving old state.
- Use fresh isolated state in tests.

Deleting other existing files, credentials or database volumes is outside scope.

Keep historical verification reports and evidence unchanged.

### 2. Inspect current code

Start from actual repository state, including any completed core-to-platform rename and identity split.

Inventory active `generated-certificates` references, including:

- Component config defaults.
- `GENERATED_SECRETS`, `SECRET_FILES` and `VOLUME_FILES`.
- Certificate scripts and other generators.
- OIDC client descriptors and public certificate registration.
- Database preflight.
- Dev scripts and smoke tests.
- Acceptance scripts and persistence observations.
- Bundle protection against private files.
- README, PKI documentation and examples.

### 3. New default structure

Use `credentials/` under each component's state directory.

For app1, the structure could be:
```
/var/lib/myproduct/app1/
├── config.yaml
└── credentials/
    ├── database/
    │   └── password
    └── todo/
        ├── session-key
        ├── todo-client.key
        ├── todo-client.crt
        └── ca.crt
```

Dev uses the equivalent:
```
build/dev/app1/credentials/
```

Update config, for example:
```
GENERATED_SECRETS:
- credentials/todo/session-key
- credentials/database/password

SECRET_FILES:
  app1-database-password:
  - credentials/database

VOLUME_FILES:
  app1-signing:
  - credentials/todo
```

Apply the same principle to other components.

Retain existing subdirectories and filenames where still meaningful. Do not expand this into general credential reorganisation.

Shared PKI/CA state outside component `generated-certificates/` directories must not move as a side effect.

### 4. Retain existing functionality

This changes host-side paths. Retain:

- Secret names and keys.
- PVC/volume names.
- Pod and service names.
- Container mount paths, for example `/run/secrets/database/password` and `/certificates`.
- Database users and database names.
- OIDC client IDs, scopes and public URLs.
- Runtime connection-string mechanism.
- Config precedence and authoritative persistent production config.

Update all host-side references, including certificate paths in `client.yaml` or equivalent descriptors.

Avoid application-code and image changes when the container interface is unchanged.

### 5. Retain generation and security rules

Database passwords and session keys must still be generated through existing `GENERATED_SECRETS`.

The certificate script must write material to the new paths. Do not move database-password generation back into that script.

Retain existing guarantees:

- Missing secrets are created only when allowed.
- Existing valid files are retained byte-for-byte on restart/redeploy.
- Empty or invalid files produce errors.
- A missing database password with an existing database volume is rejected.
- Private file and directory permissions are retained.
- Symlink escape and unsafe output paths are rejected.
- Credentials and complete connection strings are not exposed in logs.

These checks apply to normal operation of the new layout. Do not introduce separate checks or fallback rules for old layout.

### 6. Dev, bundling and acceptance

Update all helper scripts that read, generate, transfer or compare credentials.

New dev and production installations must use the same layout under their respective component directories.

Bundle protection must still prevent credentials from entering offline archives, including copies through symlink aliases.

Retain checks following declared secret files. Do not replace them with a simple directory-name filter for `credentials`.

Retain checksum guarantees, offline properties and existing SELinux/fapolicyd checks.

### 7. Tests

Update existing tests and add only focused regressions where coverage is missing.

Verify:

- Defaults and config initialisation use `credentials/`.
- Generated files use the correct dev and production paths.
- The certificate script uses the new paths.
- OIDC client registration finds the correct public certificate.
- Server and client still use the same database password.
- Restart/redeploy retains credentials byte-for-byte.
- Database preflight still rejects missing passwords when the volume exists.
- Secret/PVC names and container mounts are unchanged.
- Private files and symlink aliases do not enter bundles.
- Smoke and acceptance scripts use the new locations.

Do not add migration tests or tests requiring old config paths.

### 8. Documentation and cleanup

Clearly document the roles:

- `credentials/` contains passwords, keys and certificates.
- `GENERATED_SECRETS` specifies generated files.
- `SECRET_FILES` and `VOLUME_FILES` specify delivery to containers.

Search the entire repository for `generated-certificates`. Update active references in code, config, tests, examples and operator documentation.

Retain historical reports and fixtures explicitly representing a historical release. Explain remaining occurrences in the final report.

Do not present earlier lab results as verification of this change.

### 9. Verification and delivery

Run:

- All product tests.
- All acceptance-harness tests.
- Relevant ruff, format, pyright, vermin and shellcheck checks with the existing project setup.

Retain Python 3.6 compatibility for host tools.

Run relevant fresh-install/e2e scenarios in the established lab if available and authorised. Do not reset other environments.

Clearly distinguish local tests, harness tests and actual container/target verification. State what could not be run.

Briefly report:

1. Paths and files changed.
2. Deliberately retained historical references.
3. Test results and verification gaps.
4. Confirmation that no migration code or fallback to old layout was introduced.

Prefer a simple, consistent rename over new abstractions.

## 13. Retry-safe install and uninstall

Status: done in 0.4.2. Failure injection is verified in fresh local processes
(`tests/test_retry.py`); on real hosts the normal lifecycle is verified by
the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS), but no failure is injected there. See [retry verification](acceptance/RETRY-SAFETY.md).
This is a bounded correctness fix for retrying failed operations, not a transaction
framework or module refactor. The full agent message follows, with Markdown
formatting adjusted for this document.

Implement safe retries after installation and uninstallation failures in gunstein/podman_offline.

This task addresses two concrete deploy.py bugs:

1. A retry can skip required Identity/platform restarts after a failed installation.
2. Uninstall can remain incomplete while the next attempt is rejected because the installation marker has already been deleted.

This is a bounded correctness fix. Do not perform the planned module refactor, change component architecture or introduce a general transaction framework.

### 1. Read and understand the existing flow

First read:

- install_components()
- install_component_plan()
- write_registrations()
- registration_stage()
- component_imports()
- uninstall()
- Relevant installation-failure, component and Identity tests.

Function names may have changed. Find the equivalent current-branch code.

The component model is:

- platform owns the proxy and route registrations.
- identity owns IdentityServer and client registrations.
- app1 and app2 depend on platform and identity.
- help depends on platform.

Route and client registrations must remain separate. A route change normally affects platform, while a client change affects identity.

### 2. Installation bug

The current flow writes registrations before all necessary services have restarted.

For example:

1. App1 has a new route and client registration.
2. The installer writes both registrations to persistent state.
3. App1 restart fails.
4. The installer exits before Identity and platform restart.
5. The operator repeats the same installation.
6. Registration files already contain the intended content and are considered unchanged.
7. Identity and platform therefore do not restart.

The second attempt can report success even though running services have not applied the registrations.

A similar failure can occur if writing import archives or restarting a registration owner fails.

Requirement: a retry must complete required work from the previous attempt. Comparing new registrations with files already on disk is insufficient.

### 3. Installation solution

Choose a simple, explicit mechanism to remember incomplete work between processes.

A small persistent pending file is one option. It could record that identity and/or platform registrations have not yet been confirmed applied.

Adapt the filename and format to existing code. Follow these rules:

- Record required work before changes that could hide its necessity.
- Pending state must survive installer exit or process interruption.
- On retry, read pending state and combine it with new changes.
- Rewrite required import archives if the previous attempt did not complete them.
- Restart affected services and check them against existing success criteria.
- Remove pending state only for work actually completed.
- If restart or validation fails, unfinished work must remain recorded.
- A retry with identical registration files must still perform pending work.

Pending state contains only required metadata, never passwords, private keys or complete configurations.

Use existing private-permission and safe-write patterns. Do not follow symlinks to arbitrary locations. Invalid pending state must produce a clear error, not be ignored.

Do not solve this by restarting all services on every install.

Preserve normal behaviour:

- Unchanged registrations without pending work do not restart Identity/platform.
- Route-only changes normally restart platform.
- Client-only changes normally restart identity.
- Both changes restart both.
- Sibling apps must not restart as a side effect.

If choosing an alternative to pending state, cover the same failure cases and explain it clearly.

### 4. Uninstall bug

Current uninstall deletes the installation marker, among other things, before the entire operation completes.

For example:

1. App1 stops.
2. Quadlet/YAML and registrations are deleted.
3. The installation marker is deleted.
4. Identity or platform restart fails.
5. The operator retries uninstall.
6. The installer rejects the attempt because app1 is no longer considered installed.

With --delete-data, volume removal can also fail after the installation marker is gone.

Requirement: the operator can repeat and complete uninstall without manually reconstructing markers, YAML or registrations.

### 5. Uninstall solution

Make partially completed uninstall resumable.

Do not solve this only by moving marker deletion to the end. Previously deleted YAML or other files may still be needed to determine remaining work.

Before destructive steps, validate and retain enough information for the next run to know:

- Which component is being uninstalled.
- Whether --delete-data is included.
- Which services must stop or update.
- Which registration owners must update.
- Which specific volumes, if any, must be deleted.

Use small, explicit state for ongoing uninstall if needed. Do not build a general operation engine.

Follow these requirements:

- Run dependency checks before uninstall starts.
- A component undergoing uninstall must not count as a healthy available dependency for new installations.
- Repeated deletion of files already removed by the same operation must be safe.
- A missing volume on retry can count as already deleted.
- A volume-inspection error remains an error; do not interpret it as absence.
- The volume list must come from validated component-scoped information.
- Do not expand deletion to other components' volumes or state.
- Registration updates and required restarts must be repeatable.
- Mark completion only after every required step succeeds.
- Clean up pending state after completion.

Preserve the distinction between:

- uninstall: retain data, config and credentials.
- uninstall --delete-data: delete only the selected component's relevant data and state.

A retry must not accidentally change a retaining uninstall into a data-deleting uninstall. Define and document handling of conflicting flags. The simplest solution is to require the original selection and clearly reject a mismatch.

### 6. Interaction between installation and uninstallation

Define simple, clear behaviour when a new command encounters unfinished work.

For example:

- install must not ignore an ongoing uninstall of the same component.
- uninstall must not delete or ignore pending registration work in a way that leaves incorrect runtime state.
- An operation must not remove another operation's pending work.

It is acceptable to reject a conflict with a clear message naming the command the operator must complete first.

Do not introduce automatic rollback or automatic repair of unknown state.

### 7. Installation tests

Use existing test infrastructure and fault injection. Add at least these scenarios:

#### A. App restart fails after registration writes

1. Install an app with changed route and client registration.
2. Fail app restart after registration writes.
3. Verify installation fails.
4. Repeat installation without the fault.
5. Verify required import archives update and both Identity and platform restart.
6. Verify pending state is removed after success.

#### B. A registration owner fails

1. Fail Identity/platform restart or its subsequent check.
2. Repeat installation.
3. Verify unfinished work runs even with identical registration files.

#### C. Import archive write fails

1. Fail a required import archive write after registration writes.
2. Repeat installation.
3. Verify the import archive actually updates before completion is acknowledged.

#### D. Normal installation remains scoped

Continue checking all four combinations:

- No registration change.
- Route-only change.
- Client-only change.
- Both changes.

Without pending work, no additional shared services should restart.

### 8. Uninstall tests

Add at least these scenarios:

#### A. Registration-owner restart fails

1. Begin uninstalling an installed app.
2. Fail Identity or platform restart.
3. Repeat uninstall.
4. Verify completion even though some files are already deleted.
5. Verify registrations are removed from updated import archives.
6. Verify pending-state cleanup.

#### B. Volume deletion fails

1. Begin uninstall --delete-data with several component volumes.
2. Fail deletion of a later volume after an earlier volume is removed.
3. Repeat the same command.
4. Verify already deleted volumes are handled and remaining work completes.
5. Verify other components' state is unchanged.

#### C. Uninstall without data deletion

A failed attempt and retry must preserve config/credential bytes and database volumes.

#### D. Conflicts and invalid state

Test:

- Retry with a conflicting --delete-data selection.
- Installation while the same component is being uninstalled.
- A new installation depending on a component being uninstalled.
- Invalid or symlinked pending state.

Retry tests must represent a new process: the solution must not depend on variables from the first attempt. Use the same persistent test directory but reset temporary state between attempts.

### 9. Scope and compatibility

Preserve:

- Existing root commands.
- Python 3.6 compatibility for deploy code.
- Bundle dependencies and version rules.
- Checksums and offline installation.
- Existing secret generation and credential paths.
- SELinux and fapolicyd checks.
- Component isolation and persistent data.

Do not:

- Move deploy into a Python package as part of this task.
- Add password rotation.
- Regenerate credentials on retry.
- Introduce migration logic.
- Change normal service restarts beyond what the fix requires.
- Put pending state in the release directory or offline bundle.

### 10. Documentation, checks and report

Briefly document how the operator retries failed install/uninstall and how conflicts are reported.

Run:

- Product tests.
- Acceptance-harness tests.
- ruff.
- Format checks.
- pyright.
- vermin.
- shellcheck.

Add real acceptance scenarios only where they provide necessary coverage beyond focused fault-injection tests. Do not claim stubbed tests prove actual Podman/systemd behaviour.

Report:

1. Causes of the two bugs.
2. How unfinished work is stored and completed on retry.
3. Files changed.
4. New failure scenarios covered by tests.
5. Actual test results and checks that could not run.
6. Limitations.

Prefer small, clear functions and explicit steps. A moderately experienced Python developer should readily understand why retry is safe.

## 14. Tighten app credential delivery and remove unused API secret

Status: done in 0.4.4; delivery and modes are checked on the target
(`08-credentials`) by the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS); see
[credential delivery](acceptance/CREDENTIAL-DELIVERY.md). The original agent message follows.

Fix credential handling in `gunstein/podman_offline` with a small, focused change.
Retain current component architecture and the offline installation model.

### 1. Background and confirmed observations

App1 and app2 declare `credentials/todo/session-key` in `GENERATED_SECRETS`.
The entire `credentials/todo/` directory, including the session key and private
client key, currently travels through `VOLUME_FILES` to the app's signing PVC
and is mounted read-only at `/certificates` in the backend. The frontend does
not receive this mount.

`deployment/render.py: generate_secrets()` creates the original file with `0600`.
`write_file_archives()` creates the archive itself with `0600`, but `normalize()`
sets ordinary archive members to `0644`. This was reproduced locally with a
synthetic session key. Actual permissions after Podman import are unverified here.
Using a PVC alone is not a confirmed vulnerability; assess access and lifecycle,
not just the YAML resource's name.

Identity also declares `credentials/app/ApiResources__0__ApiSecrets__0__Value`
and delivers it through `identity-api-secrets` and `envFrom`. Review found no
use of the value in current Identity code. Confirm that before removing it.

### 2. Inventory before changes

Read `AGENTS.md` if present, README, ARCHITECTURE and relevant tests.
Trace actual files through:

- `components/app1/config.defaults.yaml` and app2/identity equivalents.
- Component manifests and `scripts/generate-certificates.sh`.
- `deployment/render.py`: generation, file groups, Secret/PVC and import archives.
- `deployment/deploy.py`: install, retry and uninstall.
- `apps/todo-backend/app.py` and `apps/identity/Program.cs`.

The session key is Flask's `SECRET_KEY` for session cookies. The private client
key is used for `private_key_jwt` against Identity. These are distinct secrets
with distinct purposes; neither belongs in the frontend.

### 3. Tighten delivery and permissions

Prefer delivering the session key and private client key through existing
`SECRET_FILES`, as with database passwords and Identity's signing key. Confirm
support in the target Podman version and existing `.kube` flow. A small credential
group per app is sufficient; do not introduce a new framework.

- Retain persistent originals and identical bytes through normal upgrades,
  repeated installation and retry. Do not regenerate or rotate keys during relocation.
- Set explicit restrictive permissions for secret files in containers, such as
  `0400` or `0600`, with ownership appropriate to the reader process. Verify
  Podman actually applies the fields; do not assume Kubernetes behaviour.
- Retain read-only mounting and backend-only access. Keep existing container
  paths if that gives the simplest, clearest solution.
- Public certificates may share the protected group when that simplifies the
  mount; do not add abstractions merely to separate public files.
- The session key and private client key must not also remain in an active
  generated `VOLUME_FILES` archive after the change.
- Do not set every general import file to `0600` without considering public
  payloads, directory access and container UID/GID. If secrets still require
  archive delivery, justify it and retain restrictive permissions.
- Preserve uninstall's distinction between retention and explicit `--delete-data`.
  Deletion remains limited to the selected component.

A Secret does not automatically provide encryption or memory-only storage in
Podman. Rendered YAML containing base64 secrets is sensitive. Protect YAML,
original files, any archives and runtime copies, and keep values out of logs
and test output.

### 4. Remove the unused API secret

If investigation confirms the API secret is unused, remove its generation,
Secret declaration, `envFrom` reference and unnecessary directory creation.
Update relevant tests and documentation. Do not remove legitimate API scopes,
client-certificate authentication, database passwords or Identity token signing.
Do not automatically delete unknown existing credential files.

### 5. Tests and documentation

Add focused tests verifying:

- Correct delivery, mount, ownership/permissions and unchanged credential bytes.
  Inspect actual generated YAML and any archive members.
- Separate app1/app2 keys and no credential mount in the frontend.
- No duplicated private key/session key in the app's generated import archive.
- Install, upgrade and retry retain keys; uninstall remains safe and scoped
  with and without data deletion.
- The unused API secret is no longer generated or referenced.
- Private files and bytecode remain excluded from offline bundles.

Update README and relevant test/architecture documentation with the actual file
flow and the distinction between a secret value and YAML type `Secret`. The
user's diagram sketches are still under discussion; do not add them without agreement.

Run documented product tests, acceptance-harness tests, ruff, format checks,
pyright, vermin and shellcheck. Retain Python 3.6 compatibility for host tools.
Update affected image/release versions following repository conventions if new
images are required; do not reuse an immutable tag.

Describe or extend focused lab verification of real file modes, read access,
login, sessions after restart/upgrade, client authentication and uninstall.
Do not start destructive VM/snapshot runs without explicit authorisation.
Distinguish local tests, static assessment and actual Podman verification.

### 6. Scope and delivery

No existing installations need migration from old layouts. Do not build migration
code, fallback, automatic key rotation or a new secret manager. Normal upgrades
within the supported model must still retain private files and data. Do not
redesign Flask/OIDC authentication or adapt the demo to a hypothetical C#/GraphQL
application as part of this task.

Report the chosen solution, concrete changes, test results and remaining lab
work. Explain which security properties actually improved without claiming that
switching from PVC to Secret alone provides encryption or a new isolation boundary.

## 15. Remove obsolete legacy layout refusal checks

Status: done in 0.4.5; fresh installs without the removed checks are verified by
the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS); see [layout cleanup](acceptance/LEGACY-CHECK-CLEANUP.md). The original
agent message follows. No existing installations require migration.

Message to the agent:

Remove checks that only detect and reject historical core layout or combined
platform/Identity layout in `gunstein/podman_offline`. `core-identity-data` in
`deployment/deploy.py` is one example; today's Identity volume is `identity-data`.
The old name is used for rejection, not as an active database volume.

- Inventory `reject_legacy_layout()`, `reject_combined_platform()`,
  `legacy_volume_exists()` and equivalent checks in certificate/dev scripts,
  tests and active acceptance scenarios. Start from current repository state.
- Remove rejection checks, their calls and errors about separate migration
  procedures. Do not merely replace old volume names with new names in these
  checks; current volumes must not be rejected as historical state.
- Update tests and active operator documentation to describe the supported
  layout. Retain historical reports, evidence and fixtures explicitly representing
  old releases; explain remaining old names.
- Do not introduce migration, fallback, aliases, compatibility branches, automatic
  cleanup or deletion/movement of old files or volumes. Do not implement items 4
  and 11; those historical proposals were superseded by the clarification that
  no existing installations need migration.
- Retain normal upgrade and retry in the current component model: config,
  credentials and data must still be retained. Keep database preflight,
  dependency/version checks, pending-state validation, component isolation,
  safe paths/permissions and bundle protection.

Run product tests, acceptance-harness tests and relevant ruff, format, pyright,
vermin and shellcheck checks, plus `git diff --check`. Retain Python 3.6
compatibility for host tools. Report removals, retained historical references,
test results and any lab gaps.

## 16. Combine secret generation and file delivery declarations

Status: done in 0.4.6 after item 14; source-level generate is supported
for both delivery groups and verified (examples `03-example-*` and generated
database passwords) by the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS). See [file sources](acceptance/FILE-SOURCES.md) for
verification and remaining lab work. The original agent message follows.

Message to the agent:

Simplify config in `gunstein/podman_offline` so optional generation is declared
alongside files delivered through `SECRET_FILES` or `VOLUME_FILES`. Remove the
need for a separate `GENERATED_SECRETS` list and duplicate path maintenance.
A moderately experienced developer should readily understand both where a file
comes from and how it reaches the container.

One possible format to assess is:

```yaml
SECRET_FILES:
  app2-database-password:
    directory: credentials/database
    generate:
    - password
  identity-signing:
    directory: credentials/identity
```

Here `generate` is relative to the declared directory and names only files to
create when missing. Without `generate`, use existing files. Support the same
principle for `VOLUME_FILES`, because current generated session keys use volumes.
Consider whether a list of file sources is needed instead of one `directory`,
so required support for multiple files/directories is retained. Choose one
simple, consistent model; do not introduce a general generator/plugin framework
or two parallel config formats.

- Read current defaults, config validation, generation, rendering, database
  preflight, bundling, dev/certificate scripts and tests before choosing the format.
- Retain current generation rules and timing: create only explicitly declared
  missing files where allowed. Retain valid files byte-for-byte; reject empty or
  invalid files. Reject missing database passwords with existing volumes before generation.
- Certificates and private signing keys remain separately prepared. The new
  declaration must not turn deploy into a certificate issuer.
- Retain credential paths, Secret names/keys, volume/PVC names, container mounts,
  password format/length, config precedence and authoritative persistent config.
  Keep safe paths, symlink checks and private file/directory permissions.
- Bundle protection must still follow declared private files, including symlink
  aliases, rather than filtering only by names. Credentials and complete
  connection strings must not appear in logs or bundles.
- Update all active configs, examples, helpers, tests and documentation. Retain
  historical reports and explicit historical-release fixtures. No existing
  installation needs config migration: no migration code, fallback, aliases or
  old-format support.

Add focused coverage for generated and externally supplied files, both delivery
methods, invalid declarations/paths, config initialisation, database preflight,
byte retention on restart/redeploy/retry and bundle protection. Retain config,
credentials and data during normal upgrades in the new model. Do not combine
this with password rotation, component architecture changes or broad module refactoring.

Run product tests, acceptance-harness tests, relevant ruff, format, pyright,
vermin and shellcheck checks, and `git diff --check`. Retain Python 3.6 compatibility
for host tools. Report the chosen format, changed files, test results and any
remaining lab verification.

## 17. Use an init container for database preparation in one demo app

Status: done in 0.4.8. App1 uses a real schema-preparation init container;
app2 retains backend initialization. Verified by the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS) (database
authentication steps; the renamed `orders` init container exits 0). Local checks and remaining real target
verification are documented in [app1 init verification](acceptance/APP1-INIT.md).
The original agent message follows.

Message to the agent:

Use `initContainers` in one app in `gunstein/podman_offline` for actual database
preparation before backend startup. Choose and justify a suitable app from
current code/manifests, preferably app1 or app2. The current Todo backend creates
its table during startup; Identity prepares its own user table. Move a concrete,
necessary preparation step into the init container; do not add a symbolic init
container running only `echo` or a wait command.

- Inspect Podman/Quadlet startup and PostgreSQL placement before choosing the
  solution. An init container must not wait for an ordinary database container
  in the same pod that starts only after init completes. Document how the
  database becomes available before preparation runs.
- Start the backend only after successful init. Database waiting must be bounded,
  and init failure must give a clear error without passwords or complete connection
  strings. Use the app's existing credential mechanism and the same database
  password as the database and backend.
- Preparation must be idempotent: fresh install creates required schema;
  restart, redeploy and retry retain database contents and credentials. No
  password rotation, destructive resets, historical-layout migration or general
  database migration framework.
- Retain the other app's behaviour. Apps currently share backend source/image;
  avoid accidentally requiring init preparation in the unchanged app. Retain
  isolation from platform, identity and sibling-app data/services.
- Update required app code, manifests, dev flow, bundling, tests and README.
  The offline bundle must contain all required images; no code/package downloads
  during init. Follow repository rules for new image/release versions.

Add focused tests for startup order, init failure, timeout and repeated
preparation without data loss. Run product tests, acceptance-harness tests,
relevant lint, format, type, compatibility and shell checks, and `git diff --check`.
Retain Python 3.6 compatibility for host tools. Describe required lab verification
of actual Podman behaviour, including fresh installation and restart with retained
data. Do not claim stubbed tests prove real init-container ordering. Report the
chosen app, concrete flow, changed files, test results and verification gaps.

## 18. Move proxy configuration out of apps and use stock nginx from YAML

Status: done in 0.4.7 with the revised scope: existing app image building
is unchanged, standard nginx is configured through platform YAML. Verified by
the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS) (HTTPS e2e through the proxy). See
[proxy verification](acceptance/NGINX-YAML.md) for checks and remaining lab work.
The original revised agent message follows.

Message to the agent:

Remove the custom proxy from `apps/` in `gunstein/podman_offline`. Platform must
reference a versioned stock nginx image directly, with all proxy configuration
and startup requirements declared in platform manifest YAML. Stop building a
separate proxy image.

Image building for other apps stays as it is. Do not move build logic into
Python or refactor `dev/build-images.sh`, `dev/pull-images.sh` or bundle tooling
as part of this task. Retain component architecture, CLI and offline installation.

### 1. Read the existing flow

Read `AGENTS.md` if present, README, ARCHITECTURE, BACKLOG and relevant tests.
Inspect at least `dev/build-images.sh`, `dev/pull-images.sh`,
`bundle.py: manifest_images()` / image validation / archiving,
`apps/*/Containerfile`, `apps/proxy/default.conf`, `15-resolver.envsh`, platform
manifests, route registrations and image/registry acceptance helpers. Functions
and files may have changed; use actual current repository state.

### 2. Retain existing image building

- Keep `dev/build-images.sh` and current recipes/build contexts/tags for other
  app images. Do not add a Python file or wrapper for image building.
- Retain manifest-driven image discovery, the distinction between local demo
  builds and registry pulls, PostgreSQL's upstream pull/local tag, exit codes
  and validation. No fallback building after a pull failure.
- The only intended image-flow change is that the proxy becomes an ordinary
  registry image: existing pull flow fetches it rather than building locally.
  Adapt only helpers concretely depending on the old proxy image.

### 3. Proxy without a custom image build

- Replace `localhost/myproduct-proxy:...` with a fully qualified, explicitly
  versioned stock nginx image in the platform manifest. Do not use `latest`.
  Inspect the current base image and avoid an unnecessary nginx version change.
- Move required nginx config, templates and any small startup code into YAML,
  such as ConfigMap data and explicit command/args or the image's supported
  entrypoint mechanism. No new image, proxy Containerfile or separate proxy
  config/script files in `apps/proxy/` should be required. Remove those files
  once active dependencies are replaced.
- Retain runtime DNS from container `/etc/resolv.conf` and dynamic component
  name resolution. Platform must start without apps/Identity, and routes must
  work as services appear or restart with new addresses.
- Retain HTTPS_PORT, TLS files, restrictions, `/livez`, unknown-route 404 and
  `/routes/installed.conf`. Do not hardcode app/Identity routes in base proxy
  config. Keep TLS/route mounts, readOnly, hostname, hostIP/port and healthcheck.
- Respect the renderer's whole-value `@@...@@` contract. If nginx templating
  occurs at startup, restrict substitution so nginx variables in config/routes
  are not unintentionally replaced. Do not make a general deploy-renderer change
  to solve proxy templating.
- Verify shell/tool support, ConfigMap mounts, modes and startup order for the
  selected image and Podman version. Do not write to read-only mounts; run nginx
  as the main process with correct signal handling.

### 4. Offline operation, tests and documentation

Discover the nginx image from the manifest, fetch it on the build machine through
the pull flow, archive it in the platform bundle and load/verify it before install.
Retain `imagePullPolicy: Never` on the target, checksums, image-name validation
and bundle isolation. Production must not fetch images/packages from the network.
Update dev/acceptance helpers still expecting a custom proxy build or files under
`apps/proxy`. Do not change historical reports or pinned fixtures.

Retain current image-build and pull-failure tests. Add focused coverage that
nginx is discovered and pulled through existing flow instead of built, and
other app builds retain their tags/contexts. Verify rendered proxy YAML, runtime
templating/DNS, retained nginx variables, offline image inclusion and unchanged
TLS/route mounts. Update tests previously reading `apps/proxy/default.conf`
without weakening component separation or dynamic-registration checks.

Run product tests, acceptance-harness tests, ruff, format checks, pyright, vermin,
shellcheck and `git diff --check` with repository configuration. Update relevant
release versions according to conventions without changing unchanged app images/tags.
Document unchanged app building, how stock nginx is fetched and how YAML configures
the proxy. Describe required lab verification of HTTPS, login, platform/help
without Identity, app addition, DNS after restart, health and offline installation.
Do not reset labs without authorisation or claim stubbed tests prove actual
nginx/Podman behaviour.

No config/credential migration, old-proxy-layout fallback, password rotation,
new component model or broad deploy refactor. Retain persistent config/credential
bytes, database data, retry and SELinux/fapolicyd checks. Report changed files,
chosen YAML/entrypoint solution, actual test results and verification gaps.

## 19. Remove branches whose changes are already in main

Status: done. On 2026-10-17 `git ls-remote --heads origin` listed only `main`;
`fix/atomic-install-records` and `improvements-0-2` no longer exist on the remote.
Their content was confirmed in `main` on 2026-10-16 as described below. Who deleted
them is not recorded here. No source, release version or `main` history changed.

Message to the agent:

Clean up `fix/atomic-install-records` and `improvements-0-2` in
`gunstein/podman_offline`. Retain `main`.

On 16 October 2026, verification found `improvements-0-2` included in `main`
history. The three commits on `fix/atomic-install-records` were combined into
`c1e26e2369c94350aae36ead018fc5f82117ffc0` on `main`, with identical contents in
the three affected files. That branch therefore needs no additional merge.

Fetch current remote state before deleting and verify neither branch has new
changes missing from `main`. For atomic-install-records, account for the combined
commit: absence of shared commit IDs alone does not imply missing content. If
new work is missing from `main`, report it and retain the affected branch.

Delete only the two named remote branches once their content is confirmed
preserved. Clean up corresponding local branches and stale remote references
without losing local changes. Do not change source code, release versions or
`main` history, and do not create a merge merely to mark branches as merged.
Report deleted branches and how their content was checked.

## 20. Make components and bundles declarative instead of hardcoding demo names

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: done in 0.4.9 (merged from `feature/declarative-components`); local
product and harness tests pass, and the lab runs (demo and
`--renamed-product`) were CLEAN PASS on `8e62153`. See
[verification](acceptance/DECLARATIVE-COMPONENTS.md) and
[components](docs/COMPONENTS.md). The original task follows.
This addresses custom installations failing when a component is renamed, for
example from `identity` to `my-identity`. Component IDs currently reject `_`;
retain the existing lowercase/digit/hyphen rule and explain it clearly.

### Analysis of the current implementation

The current component model is fixed in `deployment/common.py` through
`DEPENDENCIES`, `COMPONENTS` and `VERSION_FILES`. `bundles.yaml` is validated
against that model rather than defining it. Changing a directory or the YAML
alone therefore cannot define a new component.

Name-dependent behavior also exists in:

- `deployment/deploy.py`: config initialization and platform config inheritance;
  dev preparation; bundle selection and dependency/version checks; registration
  staging; allowed client directories; fixed import IDs; registration owner
  restarts; pending-state validation; install markers; uninstall dependents and
  registration-owner updates.
- `deployment/render.py`: compulsory PUBLIC_ORIGIN/HTTPS_PORT for every component
  and deriving PUBLIC_HOSTNAME only for the literal platform name.
- `deployment/cli.py`: fixed component validation and the special platform
  argument to uninstall.
- `bundle.py`: component admission, version-file selection, dependencies and
  generated bundle descriptors.
- `dev/dev.sh`: three named databases, a named platform config and five named
  components passed to the certificate script.
- `scripts/generate-certificates.sh`: demo component names, certificate paths,
  signing material and demo users. This is application-specific provisioning,
  not a requirement every deployment should inherit.

Image delivery is already mostly independent of app sources: `bundle.py` and
production deploy do not need `apps/`; registry images are discovered from YAML.
`dev/build-images.sh` is a demo build helper with an explicit naming convention.
Demo source code, OIDC routes and smoke tests may legitimately name demo apps.
They must not determine which components the general deployment tools accept.

The most sensitive part is lifecycle metadata across isolated offline bundles.
The source catalog is unavailable on the target, and another component's release
may have been removed. Reverse dependencies, registration ownership and pending
work must remain understandable from validated bundled/installed metadata.
Replacing constants with a source-file lookup everywhere would not solve this.

### Review findings explicitly included in item 20

The subsequent Python review confirmed that this task must also cover:

- Bundle validation/version sources must come from declarations, not
  `common.COMPONENTS`, `DEPENDENCIES` or `VERSION_FILES`. The initial image
  discovery/validation in `bundle.build()` must use the selected catalog too;
  an unselected directory with an invalid image must not block a selected build.
- Registration owners, owner import IDs, allowed client directories, restart
  order and config inheritance must not depend on demo component names.
- A component without a public endpoint must not require PUBLIC_ORIGIN or
  HTTPS_PORT. Deriving PUBLIC_HOSTNAME must not depend on the name `platform`.
- Document and test the OIDC contract explicitly: currently client ID equals
  component ID, base_path equals `/` plus that ID, and scopes equal
  `[openid, profile, component ID]`. Separate configurable application identity
  from deployment identity where the existing application protocol supports it;
  otherwise validate and document that protocol constraint explicitly. Never
  silently overwrite a supplied descriptor with inferred demo values. Supporting
  arbitrary new OIDC protocols is outside scope.

Add targeted regression tests for these cases alongside the required renamed-app
unit and acceptance scenarios below. Item 21 separately handles preflight/render
ordering, resource-kind validation and registration removal. Item 7 owns broader
PostgreSQL mount-layout support; do not expand either task into that work.

### Message to the implementing agent

Make component selection and lifecycle behavior in `gunstein/podman_offline`
declarative. A user must be able to define their own components under
`components/` and in `bundles.yaml`, use externally built images and run dev,
build bundles and install them offline without editing Python or shell code to
add/rename components. Treat the shipped five components as one demo product
configuration, not a built-in platform model.

Read the current repository and any AGENTS.md first. Inspect the files and
functions identified above, the dependency/retry/registration tests, config
precedence, certificate preparation and existing image/bundle helpers. Work from
the actual branch; recent changes include Secret source-level generation,
standard nginx from YAML and app1 database init. Preserve these behaviors.

### 1. Define one authoritative source model

Choose a small, explicit YAML schema. `bundles.yaml` selects the components to
package/run, and their directories provide defaults/manifests. Put component
metadata in that YAML or in one referenced descriptor per component; do not
maintain duplicate independent graphs in Python and YAML.

The model must express, where relevant:

- Component ID and selection, dependency IDs and compatible version rules.
- Release version source and the existing install/upgrade behavior (including
  unchanged-version shared-component handling), without inferring behavior from
  an ID or from the existence of a particular version filename.
- Route and OIDC-client registration owners and their destination VOLUME_FILES
  resource IDs. Route changes and client changes remain different operations.
- Any explicit config inheritance/equality contract, such as a component taking
  PUBLIC_ORIGIN and HTTPS_PORT from its declared gateway dependency.

Use one component per bundle as today, with bundle/component IDs matching, unless
inspection reveals a concrete requirement otherwise. Multi-component bundles,
new plugin systems and arbitrary executable hooks are outside this task.

Keep metadata declarative and validate it before writes, credential generation,
image operations or service changes. Reject duplicate YAML keys, invalid IDs,
unknown dependencies, self-dependencies, cycles, conflicting owners, missing
selected directories/files, unsafe paths and inconsistent resource ownership.
Version-file paths must remain confined to the source/release; reject traversal
and symlink escape. Report the filename/component and expected declaration, not
an unhandled FileNotFoundError.

Define the directory-selection rule explicitly: selected catalog entries require
matching component directories; unselected directories must not be installed or
built implicitly. A bare directory must not silently invent missing dependency
or ownership metadata. Topologically order selected components, with a stable
order for unrelated nodes. Preserve manifest order within each component.

Keep component IDs restricted to the existing safe naming rules. Explain that
`my-identity` is valid and `my_identity` is not; do not silently rewrite names.
Do not introduce a renamed default component list as a fallback.

### Declarative addition and removal of services

Adding a service must require only a new directory under `components/` containing
its supported YAML manifests, defaults/metadata, and an update to `bundles.yaml`.
Use existing version sources or declare version data in YAML; do not require a
new Python constant, shell case, handwritten service inventory or new per-service
version file. Existing images and externally supplied credentials may still need
normal preparation. This requirement concerns service discovery and lifecycle,
not automatic application image building or certificate issuance.

Removing a service from the source product must require only removing its catalog
entry, updating affected YAML dependencies/roles, and removing its component
directory. Dev output, discovered images and new bundles must then exclude it,
including after a previous prepare/build in the same working directory. Stale
rendered artifacts or distributions must not make removed services part of the
current generated product; clearly distinguish retained historical archives from
current build outputs. An entry whose selected directory is missing is an error,
not an implicit removal. A still-declared dependency on the removed service must
fail clearly before side effects.

Removing source declarations does not authorize uninstalling an already-installed
production service or deleting data. Preserve installed dependency/registration
metadata; removal on a target uses explicit uninstall with its existing data
retention and dependency rules. Ensure that offline uninstall remains available
from the service's previously built bundle even when its source directory/catalog
entry no longer exists. Do not silently prune installed components absent from a
new source catalog. Document how to stop removed dev services through the normal
dev lifecycle without deleting their persistent data or unrelated containers.

Add unit/product tests that add and then remove a custom service by changing only
component files and `bundles.yaml`, with no edits to generic Python/shell code.
Cover fresh and repeated prepare/build, stale-output exclusion, dangling dependency
errors, unaffected siblings and preservation of installed production state.
Extend runnable acceptance coverage to add/start/use the service, stop it through
the normal dev lifecycle, remove its source definition and rebuild/restart the
remaining dev product; verify it is absent from the new product and siblings
still work. Also verify explicit scoped offline uninstall using its retained
bundle after source removal, with ordinary uninstall preserving data. Report
actual runtime execution separately from harness/unit results.

### 2. Support isolated production bundles and installed metadata

Compile the required validated metadata into `bundle.yaml` (or a minimal bundled
catalog). An unpacked bundle must support init-config/install/uninstall without
source `bundles.yaml`, sibling source directories, `apps/`, or the original
checkout. Its own payload remains component-scoped.

Persist enough public metadata to discover installed dependents and registration
owners independently of the incoming source catalog and retained release files.
Read installed metadata with the same strictness as current dependency records;
do not infer installed components from arbitrary home directories. Keep the
existing atomic ordering: dependency/ownership metadata is durable before the
installation completion marker makes a component available.

Preserve version range checks, missing/incompatible dependency refusal, reverse
upgrade checks, downgrade refusal and uninstall dependency guards. A component
with pending uninstall is not an available dependency. Adding a component to a
new source catalog must not hide an already-installed dependent or erase its
registrations because it is absent from that source checkout.

Define how conflicting owner/config metadata is rejected. Do not let a newly
supplied descriptor silently reassign another installed component's registrations
or state. Keep bundle checksums and validation of untrusted paths/names.

### 3. Resolve registration behavior through declarations

Replace literal platform/identity owner selection and fixed `platform-routes` /
`identity-clients` import IDs with validated metadata. Existing nginx route and
Identity client formats can remain supported protocols; their component IDs
must be arbitrary. No change to demo application protocols is required.

The existing demo may retain its component names, resources, URLs and OIDC IDs.
A renamed test product must be expressed through YAML/config/application
inputs, with no edits to generic deploy code. Retain strict public descriptor
validation, public-certificate handling and protection against importing private
keys. Keep existing client URL/scope conventions where needed; do not turn this
into an arbitrary OIDC integration framework.

Remove the app1/app2-only client-directory allowlist. Validate registered clients
against authoritative installed/pending metadata and their public descriptors.
Continue rebuilding the current route/client indexes so removed entries do not
remain active due to stale imported files.

Restart only affected owners. No change means no owner restart; route-only means
route owner; client-only means client owner; both means both. Never restart
sibling applications as a side effect. Order restarts by declared dependencies,
not a literal pair of owner names. No declaration of routes or OIDC must mean
no requirement for either service.

### 4. Generalize config, dev and CLI

Remove the unconditional requirement to load platform config during every
installation. A standalone worker or service with no gateway, Identity, database
or public URL must work with only its own required manifest placeholders/config.
Validate shared URL/port rules only for components declaring that contract.
Handle derived values such as PUBLIC_HOSTNAME through the relevant declared
behavior or validated config, rather than a test of the component's name.
Preserve common/component/dev precedence and authoritative persistent production
config. Keep init-config an explicit operation; do not implement automatic
init-config as part of this task.

Run manifest-driven database preflight for selected components before any secret
creation. A component without PostgreSQL needs no database settings. Keep the
current PostgreSQL layout checks and lost-password/existing-volume refusal;
broader database image/layout support remains backlog item 7.

`dev/dev.sh up/down` and `./deploy.sh prepare` must use the catalog and dependency
order, including the real app1 database-before-init order. Generic dev startup
must work with a missing/empty `apps/` and externally prepared credentials/images.
It must not invoke demo certificate/user generation for arbitrary components.

Separate demo provisioning explicitly: the existing certificate/demo-user logic
may remain in a clearly identified demo helper with an explicit documented call.
Do not rename or rotate existing demo credential files merely to achieve this.
Keep a simple documented command sequence for starting the shipped demo. Do not
introduce implicit arbitrary script execution from YAML as a shortcut.

Generalize CLI component arguments from validated bundle/catalog metadata.
Retain the existing root commands and `--delete-data`. A production bundle must
still refuse operations on another component. Document generic syntax and remove
special treatment of a literal platform argument.

### 5. Keep image building independent

Continue discovering ordinary and init-container images from manifests.
A selected set of registry-image components must build offline bundles and run
dev without an `apps/` directory. Build/pull/image discovery must use the same
selected component set as prepare, not all stray directories under components/.

Keep the current demo image build helper or clearly label it as demo-specific.
Do not add a Python image-builder refactor or automatic build fallback. Local
images must be explicitly prepared; external registry images use existing pull
and offline save/load behavior. Do not fetch code/packages/images on targets.

### 6. Preserve retries, isolation and safety

Adapt pending-state validation to declared/installed component IDs and owners.
Retain durable registration work recorded before writes, regenerated import
archives, owner checks and acknowledgement only after success. A retry must work
in a fresh process even when files already match or the source release is gone.

Uninstall must retain its validated component-scoped volume plan, including
mounted ConfigMaps, after deleting YAML. Keep flag-conflict refusal, missing
volume handling versus inspection errors, dependency guards and private atomic
state writes. No operation may clear another operation's pending work.

Preserve current credentials, generated-file byte retention, resource prefixes,
Secret/PVC names, container mounts, data isolation, symlink/path protections,
logging hygiene, SELinux/fapolicyd checks and offline checksum guarantees. Reject
invalid declarations before destructive side effects.

There are no existing installations requiring an upgrade to this metadata
schema. Implement only the new source/bundle/installed metadata layout. Do not
add migration code, legacy aliases, old-schema fallbacks or automatic state moves.
Use fresh isolated state in tests, then exercise normal restart/redeploy/retry
within that new model. Keep historical evidence and pinned release fixtures.

### 7. Required verification

Keep the existing demo regression suite and add focused tests demonstrating:

1. A fully renamed product, for example `gateway`, `login-service`, `orders` and
   `manual`, with renamed resources and separate route/client owners, operates
   without changing Python/shell source. No former component directory exists.
2. A minimal component such as `worker`, with no dependencies, PUBLIC_ORIGIN,
   HTTPS_PORT, database, registration provider, certificates or apps directory,
   supports prepare, bundle, init-config, install and uninstall.
3. Adding a valid new catalog entry/directory requires no code edits. Unselected
   directories are excluded from images, dev output and bundles.
4. Dependency order is deterministic; missing nodes/cycles/duplicate IDs/unsafe
   paths/ambiguous roles fail before writes or host commands. Error messages
   explain the actual declaration error.
5. Offline bundles work from another directory with no source catalog/sibling
   releases. Installed reverse dependencies and version contracts remain enforced
   even if the incoming bundle's source did not contain those dependents.
6. Renamed clients survive another component's install/upgrade/uninstall;
   route-only/client-only/both/no-change restart sets remain exact.
7. Registration write, import write and owner restart/check failures are retried
   in fresh processes with the new IDs. Partial uninstall/data deletion resumes
   after rendered YAML removal and preserves unrelated state.
8. The original demo still passes credential, database, init-container, nginx,
   image/build, checksum, config precedence, isolation and wrapper tests.
9. Registry-only dev/bundling requires no apps directory or demo provisioning;
   the explicitly selected demo bootstrap still provisions its original layout.

Renaming coverage is mandatory at both levels:

- Unit/product tests must rename application components as well as the gateway
  and Identity components. Use at least two renamed apps (for example `orders`
  and `inventory`) to verify selection, dependencies, rendering, client/route
  registration, exact restart sets, retries and isolation from the sibling app.
  Change only declarative configuration/component fixtures, never generic
  Python/shell code. Do not merely test renaming Identity.
- Add executable real acceptance scenarios to the existing harness for this
  renamed product. From fresh isolated state, exercise dev startup and the
  offline production lifecycle: bundle creation, explicit init-config,
  dependency-ordered install, access through the proxy, OIDC login and database
  CRUD for both renamed apps, restart/redeploy with persisted data, and
  component-scoped uninstall. Verify app init-container behavior where declared.
  Run the offline target portion without source checkout or original component
  directories. Application images may be reused with declarative runtime inputs;
  the scenario must not require code patches to accept the new component IDs.
- Include harness tests for scenario wiring, assertions and failure reporting.
  These complement but do not replace real Podman/systemd acceptance runs.

Implement these acceptance scenarios even if the execution environment cannot
run them. Document the exact commands, prerequisites and expected assertions so
an operator can run them later. Report unit/product results, harness results and
real acceptance results separately; unavailable lab access means runtime
verification is outstanding, not that acceptance coverage may be omitted.
Renaming here means defining a fresh installation with different component IDs,
not migrating an existing installation's names or state.

Run all product and acceptance-harness tests, ruff, format, pyright, vermin,
shellcheck and git diff --check with the project's existing setup. Keep host
Python 3.6 compatibility. Adapt generic acceptance inventory/packaging as needed
and retain existing demo login/CRUD scenarios alongside the renamed-app scenarios.

If authorized lab access is available, verify fresh installs and lifecycle for
both the shipped demo and a renamed/minimal fixture. Otherwise give exact
remaining lab scenarios. Do not reset other environments, claim stubbed tests
prove Podman/systemd behavior, or count historical runs as current evidence.

### Architecture boundary and complexity check

Moving the component model from Python constants into declarations is the scoped
architecture change in this task. Keep the current module structure as the
starting point; a wider architectural rewrite is not required by these findings.
Organize the flow around three explicit responsibilities:

1. Read and validate one authoritative component model from YAML.
2. Plan dependencies, registration changes and required service restarts using
   that validated model, without performing those actions.
3. Execute the plan through the existing lifecycle functions, preserving durable
   pending work and retry guarantees when an action fails.

Use small functions and explicit data within the existing modules where practical.
These responsibilities do not require new layers, a plugin system, a class
hierarchy, a generic operation engine or a transaction framework. Introduce a
small helper module only when it gives a concrete readability benefit and explain
that choice; do not reorganize the package merely to mirror these three steps.

If implementation starts accumulating many mode flags, parallel representations
of the same model, or special cases, pause implementation to reassess and simplify
the design before continuing. Do not conceal growing complexity with additional
abstractions. The understandability review must assess these warning signs and
justify any remaining complexity before the task can be marked complete.

### Mandatory understandability review

Before marking this task complete, perform and report an explicit
understandability review of the final diff, separate from automated checks.
A moderately experienced Python developer must be able to follow the normal
flow and failure/retry paths without reconstructing hidden conventions.

- Trace one successful operation and one failure/retry from CLI entry to durable
  state and service actions. Explain which function owns each step and why its
  ordering is safe.
- Identify the single source of truth for each decision. Avoid duplicate models,
  hidden defaults, name-based special cases and unnecessary indirection.
- Prefer small named functions, explicit data and ordinary control flow. Do not
  introduce a plugin system, operation engine or class hierarchy for these fixes.
- Check that validation, planning and side effects are visibly separated, with
  clear state ownership and completion conditions. Comments should explain why
  an ordering or constraint matters, rather than repeat the code.
- Simplify confusing paths before delivery. Report remaining complexity and its
  concrete justification, plus any simplifications made during this review.
  Passing tests alone does not satisfy this completion requirement.

### 8. Documentation and delivery

Document the final YAML schema, selection rules, dependency/version contracts,
optional registration/config roles, installed metadata, explicit demo bootstrap
and a complete example of adding a custom component using an external image.
Explain the source catalog versus compiled bundle metadata versus installed
metadata; distinguish component IDs, image names, resource names and public URLs.

Search active generic code for the former component names and explain every
remaining match. Names are acceptable in demo configuration/application code,
explicit demo provisioning/smoke tests, tests and historical evidence; they must
not restrict the generic tool's supported components. Do not replace literals
with indirect demo-specific conditionals or silently default to the demo graph.

Report the original coupling, selected schema and rationale, changed files,
verified custom/demo scenarios, test results, runtime gaps and confirmation that
no migration/fallback was added. Apply repository release version rules.
Favor small explicit functions and one validated metadata model over a generic
plugin framework or large object hierarchy.


## 21. Fix manifest validation gaps and removal of obsolete registrations

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: done in 0.4.10 (merged from `feature/manifest-validation`); local checks
green, and all six lab scenarios were CLEAN PASS on `5ee9748`. The independent
review's follow-up changed install order, database detection and image checks;
app1-first, identity-only and renamed-product were CLEAN PASS on `a688c30`. See
[verification](acceptance/MANIFEST-VALIDATION.md). Original findings: four,
reproduced in isolated Python checks.

### Message to the implementing agent

Fix the following four concrete issues in `gunstein/podman_offline`. Read the
current branch, AGENTS.md if present, and relevant product/harness tests first.
Item 20 may have changed the component model before this task starts: use the
actual declarations and lifecycle implementation, not a historical hardcoded
graph. Keep this work separate from general component/schema refactoring.

### 1. Validate the effective database manifest

`deployment/deploy.py: database_preflight()` currently reads raw YAML. A PVC
reference `claimName: "@@DB_VOLUME@@"` results in the literal command
`podman volume exists @@DB_VOLUME@@`, rather than checking the configured volume.
This was reproduced with a mocked subprocess; the actual Podman response to that
invalid name has not been measured. Do not claim this reproduction proves real
Podman would report the volume absent.

Resolve supported whole-value placeholders using the authoritative effective
config before database inspection. Apply the same resolved manifest values that
will be rendered and installed. Do not call the side-effecting renderer just to
obtain them. Validate resolved names, bindings and required values before host
commands or generation. Missing/invalid placeholders must fail clearly.

Test both literal and configured PVC names, Secret references and password-file
paths supported by the existing layout. Assert the actual name passed to Podman.
With a missing password and the resolved volume present, fail without creating a
password or changing runtime state. Cover absent volume and inspection errors
separately: only the documented absent-volume result allows generation. Preserve
existing password bytes and normal config precedence. Broader PostgreSQL images,
PGDATA layouts and mount support belong to item 7, not this fix.

### 2. Make supported resource kinds consistent across the lifecycle

Current database preflight and component resource-name checks recognize top-level
Pod documents, while image discovery and some render checks traverse nested pod
specs. A Deployment containing the same database spec therefore bypasses
preflight; a Deployment named for another component also passes the current
component-name check. Both behaviors were reproduced without running containers.
Uninstall also extracts mounted ConfigMaps only from top-level Pods.

Establish and document the resource kinds the tool actually supports. Either
handle a kind consistently in preflight, rendering, component isolation, image
collection and uninstall planning, or reject it clearly before side effects.
Do not add broad Kubernetes support as part of this task. Prefer explicit
rejection where support cannot be justified by existing product requirements and
Podman behavior. Account for wrapper/list documents so they cannot bypass checks.
Reuse a small explicit traversal/validation helper if useful; avoid a new generic
resource framework. Check names after substitution and preserve scoped volume
ownership checks.

Test identical relevant container specs under each supported wrapper. For
unsupported kinds assert an actionable error before generation, Podman calls,
registration changes or service changes. Cover foreign resource names, database
checks, init-container validation, image discovery and mounted ConfigMap cleanup
as applicable. Preserve existing supported fixtures or explicitly update their
contract; do not silently accept documents only part of the lifecycle understands.

### 3. Remove registrations omitted by a new release

`registration_stage()` copies installed routes/clients before applying incoming
files. If an installed app's new release removes `route.conf`, the old route is
still imported and no change is recorded. The old-route case was reproduced;
client.yaml follows the same retention logic and needs its own regression test.

For the component being installed/upgraded, treat the incoming release's declared
registration set as authoritative. If its previous route or client is absent in
the new release, stage removal, rebuild the public indexes/imports and restart
only the affected registration owner. Preserve all sibling registrations.
Absence for a component not selected by this operation must never mean removal.

Extend the existing explicit registration change/pending mechanism to represent
removals safely. Record required owner work durably before deletion can hide the
change. After any failed import write or owner restart/check, retry in a new
process must rebuild the required imports and finish owner work even though the
old registration has already disappeared. Do not add a transaction framework,
rollback, or untracked deletion shortcuts. Preserve private path/symlink checks.

Test route-only removal, client-only removal, both removals and unchanged inputs;
assert exact owner restarts, updated indexes, retained sibling entries and no
sibling app restart. Inject failures after deletion and during archive writing
and owner restart/check. Retry with the same persistent directory in a fresh
process, and verify pending state is removed only after success. Test ordinary
uninstall still works with registrations already removed by an earlier upgrade.

### 4. Validate manifests before generating secrets

`materialize_and_render()` currently calls generate_secrets before checking pod
mounts and final resource links. A manifest referencing an undefined volume was
rejected, but its declared generated password had already been created.

Separate side-effect-free structural/config validation from materialization.
Resolve placeholders and validate supported kinds, resource names, duplicate
resources, volume mounts, offline image policies and declared Secret/PVC/ConfigMap
links before generating files or writing import archives/output. Validate what
can be determined from declarations first; checks requiring generated file bytes
may follow generation. Do not promise transactionality for arbitrary filesystem
failures or implement rollback that deletes existing credentials.

Add tests for invalid mounts, missing references, duplicate resources, invalid
policies and unresolved placeholders. Snapshot fresh state and existing config/
credential bytes and assert those validation failures produce no new secrets,
archives, output YAML, registration changes or host actions. Retain positive
coverage for valid generation, file-content validation and byte-preserving
restart/redeploy. Keep database-preflight before secret generation.

### Mandatory understandability review

Before marking this task complete, perform and report an explicit
understandability review of the final diff, separate from automated checks.
A moderately experienced Python developer must be able to follow the normal
flow and failure/retry paths without reconstructing hidden conventions.

- Trace one successful operation and one failure/retry from CLI entry to durable
  state and service actions. Explain which function owns each step and why its
  ordering is safe.
- Identify the single source of truth for each decision. Avoid duplicate models,
  hidden defaults, name-based special cases and unnecessary indirection.
- Prefer small named functions, explicit data and ordinary control flow. Do not
  introduce a plugin system, operation engine or class hierarchy for these fixes.
- Check that validation, planning and side effects are visibly separated, with
  clear state ownership and completion conditions. Comments should explain why
  an ordering or constraint matters, rather than repeat the code.
- Simplify confusing paths before delivery. Report remaining complexity and its
  concrete justification, plus any simplifications made during this review.
  Passing tests alone does not satisfy this completion requirement.

### 5. Review findings added after item 20 (2026-10-17)

An independent review of item 20 at `c00865f` reproduced §1–§4 with renamed
components (`orders-data` behind `@@DB_VOLUME@@`, a `Deployment` named
`gateway-stolen` installed from the `orders` bundle, an `inventory` release
without its route leaving `/stock` active, and a password generated before an
undefined mount was rejected). It also found:

- **F2:** `database_preflight` recognizes PostgreSQL only through
  `POSTGRES_PASSWORD_FILE` in top-level Pod `containers`. A container using
  `POSTGRES_PASSWORD` (for example through `secretKeyRef`) skips the check, so a
  lost password with an existing volume generates a new one silently. Refuse,
  before generation, every `POSTGRES_PASSWORD*` form other than the supported
  layout, with the file and container named; broader layouts stay item 7.
- **Root cause and suggested shape:** six places walk manifests with their own
  idea of the resource kinds (placeholder collection, references, pod-spec
  checks, image discovery, database preflight, the uninstall ConfigMap plan),
  and `materialize_and_render` renders twice per install. One pure function
  returning the effective, placeholder-replaced documents, plus one `pod_specs()`
  helper with an explicit list of supported kinds, used by all of them before
  `generate_secrets`, addresses §1, §2, §4 and F2 together. Extracting
  `uninstall_plan()` and one shared restart-and-acknowledge helper would make
  the lifecycle easier to follow. No wider architecture change is needed.

### Implementation plan (2026-10-17, revised after review)

Status of the plan: carried out in five commits. Deviation: imported
registration volumes are validated by name from the descriptor's `accepts`,
so staging stays where it was in install (after the preflight, before
generation); dev validates every component before writing its configs.

**Starting point.** Six places walk manifests with their own idea of resource
kinds: `check_component_names`, `database_preflight` and uninstall look only at
top-level `kind: Pod`; `check_pod_spec`, `find_images` and `references` search
for `spec`/`containers` at any depth. That mismatch is the root cause of §2 and
F2 and part of §1. `materialize_and_render` mixes validation with side effects,
derives `PUBLIC_HOSTNAME` internally, runs twice per install (and twice in
`install_standalone`) and calls `generate_secrets` before mounts and links are
checked (§4). `registration_stage` copies every installed registration,
including those of the component being upgraded (§3).

**Resource-kind contract.** Supported: `Pod`, `ConfigMap`,
`PersistentVolumeClaim`, `Secret`, which are the kinds the demo uses and
`podman kube play` handles well. Everything else (`Deployment`, `List`, an
unknown `kind`, a non-map document) is rejected with file and kind named before
any side effect, and already at `./build-bundle.sh`. No broader Kubernetes
support. `references()` stays recursive on purpose: a link is a link wherever
it appears in a supported document.

**Validation order, the same on every path.** Install, `prepare` (dev),
`prepare_standalone` and `install_standalone` all follow:

1. effective config (`render.effective_config`: merged config plus derived
   `PUBLIC_HOSTNAME`; the authoritative effective config §1 asks for);
2. effective documents (`render.effective_documents(config, manifests,
   component)`: placeholders replaced, kinds, names, pull policy, mounts; pure);
3. registration staging in a temporary directory (no live writes) when the
   path has registrations;
4. links and duplicates (`check_links`) once imports are known;
5. database preflight on the effective documents (the first host command,
   `podman volume exists`);
6. `generate_secrets`, then checks that need generated bytes (file-group
   content, empty/invalid password file), then output and archives.

A validation failure in 1–4 therefore causes no host command, generation or
write. In install, staging moves before preflight; staging writes only to its
temporary directory.

**Five steps, one commit each, tests green after every step:**

1. **One manifest model (§2).** `render.check_kinds(documents, source)` with
   `SUPPORTED_KINDS`, and `render.pod_specs(documents)` yielding
   `(document, spec)` for Pods. Use them in `check_pod_spec`, `find_images`,
   `check_component_names`, database preflight, the uninstall plan and
   `bundle.manifest_images`; drop the any-depth search. Tests: the same
   container spec is accepted in a Pod and rejected in a Deployment/List
   before Podman calls, generation or writes, including at build; a
   `Deployment` named `gateway-stolen` is rejected.
2. **Validation before side effects, one render (§4).** Add
   `effective_config` and `effective_documents` (above) and make
   `materialize_and_render` a thin sequence of steps 4 and 6. Render once per
   component: return the rendered text together with the volumes to archive,
   so `write_component_units_and_imports` and `install_standalone` only write.
   Apply the validation order to all four paths. Tests: invalid mount, missing
   reference, duplicates, wrong pull policy, unreplaced placeholder on each
   path, each with no new secrets, archives, YAML or host commands and
   existing config/credential bytes unchanged.
3. **Database preflight on the effective manifest (§1, F2).**
   `database_preflight` takes the effective documents and uses `pod_specs`,
   so Podman receives the configured volume name, not `@@DB_VOLUME@@`. Split
   the ~110-line function into small named helpers (find the PostgreSQL
   binding, find the password file, check the volume). F2: refuse every
   `POSTGRES_PASSWORD*` form other than the supported `POSTGRES_PASSWORD_FILE`
   layout, including `secretKeyRef`, in `containers` and `initContainers`,
   naming file and container; other layouts stay item 7. Tests on the install,
   dev and standalone paths: literal and configured volume names with the
   exact Podman argument; absent volume (exit 1) allows generation; existing
   volume (exit 0) and inspection errors (other exit, `OSError`) refuse
   without generating; existing password bytes preserved.
4. **Registrations removed by a new release (§3).** In `registration_stage`
   the release files are authoritative for the selected components: their
   installed route/client is never copied, whatever their declared roles.
   A dropped role is returned as a separate set,
   `removals = {"routes/<id>.conf", "clients/<id>"}`, rather than `None`
   values in `updates` (a client is a directory, `updates` is per file).
   `registration_changes` counts an existing removal target as a change for
   its owner; pending owners are saved with `save_pending` before
   `write_registrations` deletes, with the same symlink checks, using the
   existing pending mechanism and no transaction logic. Retry in a fresh
   process rebuilds indexes without the deleted entry and restarts the
   pending owners. Absence for an unselected component never means removal.
   Clean-up: extract `uninstall_plan(component, output)` and one shared
   `restart_and_acknowledge(owner, state)` used by install and uninstall.
   Tests: route-only, client-only, both and unchanged; exact owner restarts,
   siblings kept and not restarted; failures injected after deletion, during
   archive writing and during restart, then retry in a fresh process;
   uninstall after an upgrade already removed the route.
5. **Acceptance, docs and version.** Extend the existing `--renamed-product`
   scenario instead of adding one with its own VM reset: at the end, generate
   an inventory release with a higher version and without `route.conf`,
   `client.yaml` and the catalog's `routes`/`clients`, install it, and check
   that `/stock` returns 404, the inventory client is gone and orders still
   works. Update `docs/COMPONENTS.md` (supported kinds), `ARCHITECTURE.md`
   (sequence diagram: validation order) and `docs/REVIEW_GUIDE.md`. Bump the
   product version per the repository's rules. Write
   `acceptance/MANIFEST-VALIDATION.md` with the mandatory understandability
   review.

**Trade-offs.** Rejecting `Deployment` is simpler than supporting it, and no
existing requirement needs it. No classes or frameworks: a few small functions,
fewer lines overall as six traversals become one. Validation that needs
generated bytes still runs after generation; document that explicitly.

**Delivery.** Branch `feature/manifest-validation`, five commits, one PR (as
for item 20), reviewable commit by commit. Step 2 is the largest and riskiest;
if smaller reviews are preferred, split into two PRs after step 2 (model and
validation; then preflight, removal and acceptance).

### Scope, verification and delivery

- Preserve Python 3.6 support for host tools, existing commands, authoritative
  persistent config, credentials, checksum/offline guarantees, retry behavior,
  SELinux/fapolicyd handling and component isolation.
- No migration, legacy fallback, credential rotation or general architecture
  refactor. Use fresh isolated fixtures; retain historical evidence unchanged.
- Run product tests, acceptance-harness tests, ruff, format checks, pyright,
  vermin, shellcheck and git diff --check using the repository setup.
- Add a focused runnable acceptance regression for registration removal on
  upgrade: verify the removed route/client is no longer active, while a sibling
  remains usable. Reuse existing lab setup and avoid duplicating item 20's full
  renamed-product suite. Keep failure injection tests as the primary coverage
  for precise retry boundaries and preflight command selection.
- Run relevant real Podman/systemd scenarios only in an available authorized
  isolated environment; never reset unrelated installations. If unavailable,
  implement/document the scenario and exact operator commands and report it as
  unexecuted. Stubbed tests do not prove actual runtime behavior.

Report each root cause, chosen resource-kind contract, changed files, regression
coverage, actual checks/results and remaining runtime gaps. Explain how removal
work survives retry and which validation necessarily requires generated bytes.
Apply the repository's release/version rules when implementing the fixes.

## 22. One scoped mutation-testing round for the riskiest deployment decisions

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its section on
assessing evidence, including the tests themselves.

Status: planned, narrowed on 2026-10-17. One bounded round, not a permanent
tool or gate. Do after items 29 and 31.

### Background

The suites pass, but passing tests do not show that they would detect a wrong
decision. The independent review of item 21 found tests that could not fail
(four tests patched a function install never calls) and a retry test that
accepted any owner set. Code and tests were largely written by the same
agent, so they may share blind spots. Mutation testing finds such gaps
systematically: it changes the code in small ways (a `<` becomes `<=`, a
condition is negated, a call is removed) and reports which changes no test
detects.

A full run is not worth it here: about 3000 lines of product code and an
80-second suite give thousands of mutants and hours of run time, many
survivors are uninteresting (message text), and a permanent threshold adds
maintenance for a moderately experienced developer. Mutation results say
nothing about real Podman, systemd or fapolicyd; the lab runs do.

### Scope

Only these decisions, where an undetected change does the most harm:

- `registrations.registration_stage` and `registrations.registration_changes`
  (which registrations are removed, which owners restart)
- the pending record in `registrations.py`: `save_pending`, `load_pending`,
  `check_pending`, `acknowledge_owner`, `apply_registration_updates`
- `deploy.database_preflight` and `deploy.postgres_binding`
- `deploy.uninstall_plan`
- catalog validation in `catalog.load_catalog`, `catalog.role_owners` and
  `catalog.dependency_order`

Exclude everything else, including demo applications, the acceptance harness,
rendering helpers and logging or message text.

### Task

1. Pick one maintained Python mutation tool that can restrict mutation to the
   functions above and run only the tests that cover each mutant (for example
   mutmut or cosmic-ray). Give the reason. Install it only for this round, in
   a virtual environment or with `pipx run`; do not add it to the product or
   to the bundles. Host Python 3.6 compatibility is unchanged.
2. Use the existing product tests as the kill criterion. Stay offline, with no
   Podman, systemd or network calls; keep the existing stubs. Target a run of
   at most about an hour.
3. Classify each survivor: missing test, equivalent mutant (one-line
   justification) or code that can be simplified.
4. Add focused regression tests for the survivors that matter. Assert the
   exact arguments and state transitions, not just the exit status. Do not
   change production behavior only to kill a mutant; simplifying dead or
   redundant code is allowed when the review guide's contracts hold.
5. Document one command in `tests/README.md` that reruns the round before a
   large change to these functions. No automatic gate or threshold.

### Verification and delivery

Run the product tests, acceptance-harness tests, ruff, format, pyright, vermin,
shellcheck and `git diff --check` as usual. Report the tool and version, the
command, mutants killed and surviving per function before and after, the
tests added, the remaining survivors with their classification, and the run
time.

## 23. Explicit side-effect-free validation command for YAML, secrets, volumes and placeholders

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: done on `main` (plan below, approved 2026-10-17), revised after
an independent review of `4023c6d`; the full lab matrix (`val-app1-first`,
`val-app2-first`, `val-help-only`, `val-identity`, `val-platform-help`,
`val-renamed`) was CLEAN PASS on `9dc0381`. `./deploy validate` in the source checkout, an unpacked bundle and a
standalone fixture; the lab runs it on DEV before `dev up` (demo and renamed
product) and on PROD before every install and upgrade. Item 21 already moved the checks ahead of secret generation;
this item adds the explicit command and reuses that validation instead of a
second implementation.

### What exists today

The checks exist, but only as steps inside `prepare`/`install`, and partly after
side effects:

- `render.validate_component_config` requires every whole-value `@@NAME@@`
  placeholder in a component's manifests to exist in its config before writes.
  `render.replace` and the final `Unreplaced @@...@@` check catch the rest
  during rendering.
- `render.check_links` rejects a Secret/PVC/ConfigMap that a manifest uses but
  nothing defines, an id in `SECRET_FILES`/`VOLUME_FILES` that no manifest uses,
  and names defined twice. `render.check_pod_spec` rejects mounts of undefined
  pod volumes and a missing `imagePullPolicy: Never`.
- These run inside `materialize_and_render`, after `generate_secrets` and while
  reading the source files, so a failed check can leave a newly generated secret
  behind (item 21 §4). There is no command that only validates, and no check
  that reports every problem at once.

### Message to the implementing agent

Add one explicit validation command that a developer or operator runs before
`prepare`, `build-bundle.sh` or `install`, for example `./deploy.sh validate`.

1. Scope: in the source checkout, validate every catalog component with its dev
   config layers (common, component, optional `config/dev.yaml`). In an
   unpacked bundle, validate the bundle's component against the persistent
   config, as install would. Standalone manifest fixtures keep their explicit
   `config.yaml`.
2. Checks, using the existing functions rather than a parallel implementation:
   YAML syntax and duplicate keys; supported resource kinds; component name
   prefixes; every `secretName`, `claimName`, ConfigMap name, `secretKeyRef`,
   `secretRef`, `configMapRef` and `configMapKeyRef` has a matching
   `SECRET_FILES`/`VOLUME_FILES` id, import volume or manifest resource; every
   config id is used; every `@@NAME@@` has a config value of the right type,
   including init containers; pod mounts and pull policy; Secret `items` keys
   that can be determined from declared file names or `generate` entries.
3. No side effects: no secret generation, no reads of private file contents
   beyond existence and type, no archives, no rendered output, no Podman or
   systemd calls, and no network. Missing declared source files are reported as
   such; `generate` entries count as present.
4. Report all findings in one run, each with file, document/container and the
   expected declaration, then exit non-zero. Never print config values or
   secret contents. Exit zero with a short summary when everything passes.
5. Make `prepare`, `install` and `bundle.py` call the same validation first, so
   the command and the lifecycle cannot disagree.

### Tests and delivery

Add focused tests for each finding type (missing Secret/PVC id, unused id,
undefined ConfigMap, missing and wrongly typed placeholder, placeholder only in
an init container, undefined mount, duplicate resource name) and assert that a
failing validation creates no files and runs no commands. Validate the shipped
demo and the renamed/minimal fixtures from item 20. Run product tests,
acceptance-harness tests, ruff, format, pyright, vermin, shellcheck and
`git diff --check`. Document the command in README and the review guide.

### Plan (2026-10-17)

**Command.** `./deploy.sh validate`, the same wrapper as `prepare` and `install`.
It decides the mode as those commands do:

| Where | What is validated | Config |
| --- | --- | --- |
| Source checkout (`bundles.yaml`) | every catalog component | dev layers, as `prepare` (`deploy.dev_settings`) |
| Unpacked component bundle (`bundle.yaml`) | the bundle's component and its registrations against the installed set | the persistent `config.yaml`, as `install` |
| Standalone fixture | `manifests/` | the fixture's `config.yaml` |

In the bundle mode it runs as the service user (it reads the service home),
but it needs no runtime directory and changes nothing.

**One pure function.** Split today's `deploy.check_manifests` into:

- `validate_component(config, config_path, manifests, component, imported)`:
  pure. It runs `effective_config` and `effective_documents` (kinds, names,
  placeholders, pull policy, mounts, links, duplicates), `find_images` (fully
  qualified literals), the static PostgreSQL layout check (`postgres_binding`
  and `database_password_path`, which read no host state), and a new
  `check_file_sources` that reports a declared `path` that is missing, or a
  directory under `SECRET_FILES`, unless `generate` creates it. It only checks
  existence and type, never contents.
- `check_manifests`: `validate_component`, then `database_preflight`'s host
  query (`podman volume exists`), unchanged for install and prepare.

Registrations are validated by `registration_stage` in a temporary directory,
as install and dev prepare already do (client descriptors, certificates, role
files, owners). Install's descriptor checks (pending record, owners, ID
prefixes, dependency ranges, `public_from`) are factored into one function that
both `install_components` and `validate` call, so the two cannot disagree.

**Reporting.** The existing checks stop at their first error. Rewriting every
check to collect all errors would be a parallel implementation, so `validate`
reports the first finding per component and continues with the next
component; fixing and rerunning shows the next finding. Each line names the
component and keeps today's messages (file, document, container, expected
declaration). It never prints config values or secret contents. Exit 1 on any
finding, otherwise exit 0 with a summary:
`OK: validated platform, identity, app1, app2, help; nothing written, no host
commands`.

**No side effects.** No secret generation, no rendered YAML, no archives, no
Podman, systemd or network calls, and nothing written outside a temporary
directory that is removed. Tests assert an unchanged tree and no subprocess
calls for every finding type.

**Lifecycle uses the same code.** Dev `prepare` (`check_dev_components`),
install and both standalone paths call `validate_component` through
`check_manifests`. `build-bundle.sh` is unchanged: it validates the catalog,
kinds and images, but not dev config, which is developer-local.

**Out of scope.** Secret `items` keys checked against declared file names
(keys are known only from file names or `generate`; correction 2026-10-18: a
wrong key does *not* fail at materialize, it passes every check and fails only
when the pod starts; now item 33); F8 from item 25 (application
identity across `client.yaml`, environment and route), which can be added later
as an optional check; and a machine-readable output format.

**Tests.** One test per finding type listed above plus: missing and wrongly
typed source paths, an invalid `client.yaml`, an unknown dependency range in
the bundle mode, prefix-ambiguous IDs, and a passing run of the shipped demo
and the renamed product. Each failure test asserts exit 1, the component in
the message, no files changed and no commands. A test asserts that `prepare`
and `validate` report the same message for the same broken manifest.

**Docs.** README (developer workflow: run `./deploy.sh validate` before
`dev/dev.sh up` and `build-bundle.sh`; operator workflow: before `install`),
`docs/COMPONENTS.md` (adding and removing a component), ARCHITECTURE
(validation order) and the review guide.

**Lab.** No new acceptance step is needed for correctness, but a cheap one is
useful: `03-validate` on DEV before `03-dev-up`, and `06-validate-<id>` on PROD
before each install, both expecting exit 0 and no changes.

### Review follow-up (2026-10-17)

An independent review of `4023c6d` found the command free of side effects but
claims 3 and 4 not fully true. Each finding was checked against the code and
fixed:

| # | Finding | Fix |
| --- | --- | --- |
| 1 | `validate_component` decided about a missing password, so install reported "declare generate" before asking Podman, instead of "existing volume …; restore from backup". | `validate_component` checks only the layout; install's preflight is unchanged. The command names both remedies, since it cannot query the volume. |
| 2 | Install checked the shared network, the image archive and image names in `install_component_plan`; validate missed the network, components without images and non-rendered (`newer-only`) releases. | `deploy.install_preconditions()` is shared by install and validate. |
| 3 | `generate: ["bad name"]` or `["sub/key"]` under `SECRET_FILES` passed validate, and install generated the file before refusing it. | `generated_secret_paths` requires one valid Secret file name, before generation. |
| 4 | Malformed fields (`volumeMounts: 5`, `env: 5`, `metadata: x`) and invalid UTF-8 escaped as tracebacks and stopped the run. | Typed field checks (`check_lists`, metadata) and UTF-8 errors are `DeployError`s. |
| 5 | Validate required the runtime directory (linger). | `deploy.service_user()` (root and HOME only); staging uses the default temporary directory. |
| 6 | "Reads no private contents" was too strong. | Docs: reads no credential contents; config, metadata, public registrations and certificates are read. |
| 7, 8 | Tree snapshots compared names only; no test ran the same bundle state through install and validate. | Snapshots compare bytes, type and mode; `BundleAgreementTests`. |

The command moved to `deployment/validation.py`; deploy.py keeps the shared
checks. The suggested split of registration and pending code is item 32.

## 24. Optional disaster recovery (DR), adapted from podman_test

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: planned; large. Requested 2026-10-17. Requires a separate analysis and
an agreed plan before any implementation. Analysis and a proposed agent plan
were prepared on 2026-10-18: [DR implementation plan](docs/DR-IMPLEMENTATION-PLAN.md).
Read that document in full; it adds the code reuse analysis, runtime ownership
design, declaration proposals, failure/retry contracts, delivery gates and
acceptance scenarios. It is not implementation approval or runtime evidence.
Once agreed, its detailed delivery sequence supersedes the outline below.
Builds on items 20 (declarative components) and 21; recheck the current baseline.
Coordinate with items 2 (password rotation), 3 (backup and credential recovery)
and 7 (PostgreSQL layouts). Backup/recovery must remain usable without standby,
even if its implementation is delivered by this optional operations package.

### Source of the existing implementation

`gunstein/podman_test`, branch `feature/platform` (checked 2026-10-17 at
`5171197`), has a working DR design with a clean acceptance record:

- `deploy/dr/app_ops`: `python3 -m app_ops`, one command per DR operation, run
  from a controller over plain SSH (`BatchMode=yes`, pinned host keys,
  `sudo -n`), driven by a small YAML inventory of `primary`/`standby` hosts.
- `deploy/dr/app_dr_host`: building blocks staged on each host: streaming
  replication and its TLS, secret export/import between hosts, standby reseed,
  promoted application deploy and pair checks.
- `deploy/dr/scripts/app_dr.py` (fencing-gated promotion) and `app_backup.py`
  (physical base backup, WAL archive and point-in-time restore into disposable
  containers), plus systemd timers for a scheduled DR check and nightly backup.
- Commands such as `preflight-standby`, `bootstrap-standby`,
  `replication-status`, `failover --confirm-primary-fenced ...
  --confirm-promotion ...`, `deploy-promoted-application`, `configure-backup`
  and `rebuild-standby --confirm-fenced ... --confirm-reseed ...`.
- Boundaries: DR imports the single-host installer, never the reverse
  (`tests/test_dr_boundary.py`); every operation acts on one complete group of
  replicated databases and refuses a partial group; destructive steps need
  explicit confirmations; runbooks in `docs/runbooks/`.

### Differences to resolve in podman_offline

- The reference already derives its replicated group from its declared
  `Platform`/apps model, but has its own naming, database and Identity conventions.
  Here components and databases must follow this product's model (item 20),
  without copying a second `Platform` model. The replicated set must come from declarations,
  for example an optional per-component DR declaration, and be recorded in
  installed metadata so the target knows it without the source checkout.
- Each component is a separate offline bundle with its own version and
  dependency checks; podman_test promotes one product bundle.
- Credentials here are files delivered as kube Secret YAML from component
  config directories, not `podman secret` objects; secret transfer to a
  standby must keep the credential-retention and logging contracts.
- Host constraints: Python 3.6 with PyYAML, no Jinja2, rootless user systemd,
  SELinux, fapolicyd trust per bundle, strictly offline targets.
- Existing safety guards must stay intact: database preflight, retry/pending
  state, scoped uninstall and `--delete-data`.

### DR must be optional

A single-host installation without DR must keep working exactly as today,
with no new requirement, service, timer, port or package. DR is enabled
explicitly, for example as a separate operations bundle and explicit
commands. Component bundles must not depend on DR code, and the deploy
package must never import DR code (add a boundary test). Disabling DR or
never enabling it must not leave active replication resources or orphaned
timers behind. Enablement after ordinary installation must retain existing data
and credentials. Disablement must restore ordinary deployment ownership and
remove owned replication slots/endpoints and DR timers, while retaining backup
history and standby data by default. Retained resources must be inventoried;
purging them requires a separate explicit destructive operation. A separately
enabled backup feature may retain its own archive and timer. Do not silently
delete recovery history to satisfy cleanup; see the plan's disablement contract.

### Phase 1: analysis and plan (deliver before implementing)

1. Read podman_test `feature/platform`: `deploy/dr/`, the installer's
   `backup.py`, `docs/runbooks/`, `docs/manual-recipes/03-DR-TWO-VM.md`,
   `04-BACKUP-PITR.md` and the acceptance record. List what can be reused
   unchanged, what must be adapted and what does not apply.
2. Propose a scope for the first delivery, for example: replication of
   declared PostgreSQL components to one standby, fencing-gated promotion,
   backup/PITR, and standby rebuild, with the rest deferred.
3. Propose the declaration schema, installed metadata, the operations
   package layout, the inventory format and the command list.
4. Describe the failure and retry model of every destructive step, and how
   each of the guide's contracts is preserved.
5. Plan the tests: unit tests with stubbed transport, harness tests, and the
   real two-VM acceptance scenarios with exact commands.
6. Get the user's approval of the plan before phase 2.

### Phase 2: implementation

- Develop on a separate branch, for example `feature/dr`, branched from
  `main` after item 20 has been merged.
- Deliver in reviewable steps that each keep the tests green: declarations
  and metadata, then replication, then promotion and fencing, then
  backup/PITR, then standby rebuild.
- Use a pull request to `main`. Open it as a draft early so the plan, the
  phased commits and the CI results are reviewed in one place; mark it ready
  only when the agreed scope, the tests and the real two-VM acceptance are
  complete. A pull request fits here because the change is large, touches
  safety-critical paths and needs review before it reaches `main`.

### Verification and delivery

Run product tests, acceptance-harness tests, ruff, format, pyright, vermin,
shellcheck and `git diff --check`. Add runnable real two-VM acceptance
scenarios (replication, fenced failover, promoted application access,
backup/PITR restore and standby rebuild) and document them even if no lab is
available; report unexecuted runtime scenarios as outstanding. Never count
podman_test's acceptance results as evidence for this repository.

## 25. Smaller follow-ups from the item 20 review

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md).

Status: done on `main` (2026-10-18); the full lab matrix on `2528769` (`b26-app1-first`, `b26-app2-first`,
`b26-help-only`, `b26-identity`, `b26-platform-help`, `b26-renamed`) was CLEAN
PASS.

- F7: uninstall of a component with metadata but no marker now says it is an
  unfinished first install and that `./deploy.sh install` from its bundle finishes
  it (the only recovery: units may be partly written). Fresh-process
  regression `test_unfinished_first_install_names_the_retry_for_uninstall`.
- F8: `client.yaml` may declare `environment: {id: <VAR>, base_path: <VAR>}`;
  `validate`, `prepare` and `install` (via `deploy.validate_component`) require
  `route.conf` to have a location for `base_path` and, when declared, the named
  variables to carry the `client.yaml` values. The demo apps declare
  `APP_ID`/`BASE_PATH`; the tools learn no variable name. `ClientIdentityTests`.
- F10: the demo certificate script moved to `dev/generate-certificates.sh`;
  product bundles ship only `scripts/prepare-host.sh`. The harness copies the
  script to the target and runs it on stdin; the README demo procedure does the
  same.

Original findings:

- **F7, unfinished first install:** when a first install fails after its
  metadata is written but without pending owner work (for example at the
  component's own restart), `metadata/<id>.json` exists without
  `installed/<id>`. A retry of the same bundle completes it, but `uninstall`
  refuses with "not installed". Either let uninstall clean up such an
  unfinished install with its usual data rules, or document the retry as the
  only recovery and say so in the error. Add a fresh-process regression.
- **F8, application identity in three places:** `client.yaml` (`id`,
  `base_path`), the app's `APP_ID`/`BASE_PATH` environment and the route's
  `location` must agree, but nothing checks it; a mismatch shows up only as an
  OIDC failure. The generic tool must not learn the demo's environment names.
  Consider an optional check in the validation command of item 23 for products
  that declare which variables carry these values.
- **F10, demo provisioning in every bundle:** `bundle.py` copies the whole
  `scripts/` directory, so `scripts/generate-certificates.sh` ships in every
  product's bundles. Decide whether demo provisioning belongs in bundles at
  all, for example by shipping only `prepare-host.sh` and moving the demo
  script next to `dev/demo-credentials.sh`, and update the acceptance harness
  that runs it on the target.

## 26. Make reserved configuration names and shared settings visible

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: done on `main` in 0.4.11 (2026-10-18); the full lab matrix on `2528769` (`b26-app1-first`, `b26-app2-first`,
`b26-help-only`, `b26-identity`, `b26-platform-help`, `b26-renamed`) was CLEAN
PASS; `07-init-check`
confirmed that login-service, orders, inventory and manual inherited gateway's
`SHOP_NAME` on PROD.

- Reserved names are documented once in docs/COMPONENTS.md ("Reserved
  configuration names"), linked from README; `deploy.PUBLIC_KEYS` and
  `catalog.UNSHAREABLE` point there.
- `shares: [NAME, ...]` on the owner (catalog, compiled into `bundle.yaml` and
  installed metadata). `public_from` dependents inherit those names with
  `PUBLIC_ORIGIN`/`HTTPS_PORT` at `init-config` and in dev; install and
  validate compare them (`deploy.shared_keys`, `check_public_settings`). The
  owner's config must define them (`check_own_shares`); an owner upgrade that
  drops a name installed dependents take is refused before writes
  (`check_kept_shares`). Names follow the placeholder rule; `PUBLIC_HOSTNAME`,
  `SECRET_FILES` and `VOLUME_FILES` are refused.
- Deviation, deliberate: a descriptor without `shares` is read as `[]`, so a
  product installed from a 0.4.10-with-product-name bundle can still upgrade.
  Every other field stays strict.
- Tests: `SharedSettingTests` (dev and init-config inheritance, mismatch
  refused without values, unshared names free, owner must define its shares,
  owner upgrade dropping a share), catalog name tests; the renamed product's
  gateway shares `SHOP_NAME`, checked in dev and on PROD (`07-init-check`).

### Problem

All configuration values are written the same way in the same YAML files, but
some names have behavior built into the tools and others do not. Nothing in the
configuration shows which is which:

| Name | What the tools do with it |
| --- | --- |
| `PUBLIC_ORIGIN` | Validated as an HTTPS origin; copied from the `public_from` dependency at `init-config` and in dev; install refuses a mismatch; used for OIDC redirect URIs |
| `HTTPS_PORT` | Validated as a port 1-65535; inherited and compared like `PUBLIC_ORIGIN` |
| `PUBLIC_HOSTNAME` | Always derived from `PUBLIC_ORIGIN`; setting it is an error |
| `SECRET_FILES`, `VOLUME_FILES` | File-source declarations, not placeholder values |
| Any other name, e.g. `PUBLIC_MY_SETTING` | Only replaces `@@NAME@@`; each component keeps its own copy, nothing is inherited or compared, whatever its prefix |

So `PUBLIC_MY_SETTING` in `config/common.defaults.yaml` looks like
`PUBLIC_ORIGIN` but behaves differently: in production every component gets its
own copy at `init-config`, and a later edit in one component is neither
propagated nor detected. A product has no declarative way to share its own
value the way the gateway shares `PUBLIC_ORIGIN`.

Renaming the reserved names is not the goal: the tools must know what
`PUBLIC_ORIGIN` means to validate it, derive the hostname and build redirect
URIs, and a configurable name would only move the constant. The goal is that
the difference is visible and that products can share their own values.

### Message to the implementing agent

1. **Document the reserved names in one place.** Add a "Reserved configuration
   names" section to `docs/COMPONENTS.md` with the table above and the reason
   each is reserved. Link it from README's configuration section. Keep
   `deploy.PUBLIC_KEYS` and the documentation consistent, and say in a code
   comment where the documentation lives.
2. **Declare shared settings in the catalog.** Add one optional field on the
   component that owns the values, for example:

   ```yaml
   gateway:
     shares: [PUBLIC_MY_SETTING]
   ```

   A component with `public_from: gateway` then inherits and is compared on
   `PUBLIC_ORIGIN`, `HTTPS_PORT` and every name in the owner's `shares`, at
   `init-config`, in dev prepare and at install, exactly as `PUBLIC_ORIGIN` is
   today. `PUBLIC_ORIGIN` and `HTTPS_PORT` are always shared and keep their
   extra validation; listing them in `shares` is allowed but changes nothing.
   Validate names with the existing placeholder name rule and refuse reserved
   names that cannot be shared (`PUBLIC_HOSTNAME`, `SECRET_FILES`,
   `VOLUME_FILES`).
3. **Keep it offline and strict.** Compile `shares` into `bundle.yaml` and
   installed metadata, so a dependent's install compares against the owner's
   installed declaration without the source checkout. An owner upgrade that
   removes a shared name still used by an installed dependent must fail
   clearly before writes. Read installed metadata with the existing strictness;
   no migration or fallback (no installations of the old schema exist).
4. **Errors name the setting, both files and the declaring component**, never
   the values.

### Tests and delivery

Test inheritance at `init-config` and in dev, refusal of a mismatch at install
for a shared custom name, no comparison for unshared names, invalid and reserved
names in `shares`, an owner upgrade dropping a used name, and the renamed
product sharing a value from `gateway`. Run product tests, acceptance-harness
tests, ruff, format, pyright, vermin, shellcheck and `git diff --check`. Update
the review guide's contracts, `docs/COMPONENTS.md` and the release version.

## 27. Declare the product name instead of hardcoding `myproduct`

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: done on `main` (2026-10-18), prioritized by the operator. The full lab
matrix on `8806016` (after the review fixes below) was CLEAN PASS:
`pn-app1-first`, `pn-app2-first`, `pn-help-only`, `pn-identity`,
`pn-platform-help` and `pn-renamed`, the last one installed as product `shop`
(service user, units, archives); fapolicyd showed 0 early evictions in every
run. `product:` in `bundles.yaml` (required, Linux user name rule) is
compiled into `bundle.yaml` and installed metadata. `catalog.product_name()` /
`unit_name()` name units, Quadlet files, the network, temporary directories and
archives; the Quadlet files are filled from `quadlet/template.kube` and
`template.network`. `prepare-host.sh` defaults the service user and
`/var/lib/<user>` to the bundle's product, with `--user` to override (point 4:
explicit, printed and documented rather than silent). Install, uninstall and
validate refuse a bundle of another product than the installed components
(`check_same_product`). Standalone fixtures keep `common.STANDALONE_PRODUCT`
(`myproduct`). `dev/dev.sh` reads the name for its network. The harness takes
the name as `remote.sh`'s 13th argument; `--renamed-product` now runs as
product `shop` (service user, units, archives). The demo images are renamed
to the neutral `localhost/demo-*` (manifests, `dev/build-images.sh`, harness), so
no installed name keeps `myproduct` after a rename; image names stay a
manifest choice, not derived from the product. `PUBLIC_ORIGIN` is
configuration. Tests: `ProductNameTests` (every installed name follows `hubbabubba`;
another product refused before any write), catalog and prepare-host argument
tests.

### Review follow-up (2026-10-18)

An independent review of `8629614..f8a9258` (items 27, 28, 32) confirmed the
move of item 32 and the docstring of item 28 and found:

| # | Finding | Fix |
| --- | --- | --- |
| 1 | The pending record had no product. After a last uninstall failed at `clear_pending`, its metadata was gone, so another product's bundle with the same component ID resumed and cleared the record. | The record stores `product`; `check_pending` refuses another product before anything else. `test_unfinished_last_uninstall_stays_with_its_product`. |
| 2 | `prepare-host.sh` read `product:` with `sed`, so a valid name that YAML quotes (`'on'`, `'null'`) became an invalid user name. | It parses `bundle.yaml` with PyYAML; tests serialize the descriptor as bundle.py does. Repeated `--port`/`--user` are refused. |
| 3 | Metadata from before product names was reported as "Invalid installed metadata". | A specific message names the format break and the remedies; README documents it. |
| 4 | ARCHITECTURE still named `deploy.registration_stage()`. | Fixed; COMPONENTS says `product:` is required; README's claim narrowed; the demo CA is `Demo Development CA`. |

The wrong-product test now also runs `validate` and compares file bytes.

### Problem

`myproduct` is the product name, not a component ID, and it predates item 20.
The code builds names from it in `deployment/` and `bundle.py`:
`myproduct-<id>.service`, the shared `myproduct.network`, Quadlet file names,
temporary-directory prefixes and archive names
(`myproduct-<id>-<version>-offline.tar.gz`). It is also fixed in `quadlet/`,
in `scripts/prepare-host.sh` (the `myproduct` service user and
`/var/lib/myproduct`), in the dev network and in the acceptance harness.

### Message to the implementing agent

1. Declare the product name once in `bundles.yaml`, for example
   `product: shop`, validated with the component ID rule. Compile it into every
   bundle descriptor and installed metadata, so the target needs no source.
2. Use it everywhere the code builds unit, network, Quadlet, temporary
   directory and archive names. Keep the standalone example mode working with
   an explicit name.
3. All components installed under one service user must share one product
   name; refuse a bundle with another name before any write.
4. Keep the host account and home (`prepare-host.sh`) as a separate, explicit
   setting rather than deriving them silently. Document both.
5. No migration of existing installations (none use another name); keep
   the demo name `myproduct`. Update the dev scripts and the acceptance harness
   to read the name instead of repeating it, and add a run with a different
   product name to the renamed-product scenario.

Run product tests, acceptance-harness tests, ruff, format, pyright, vermin,
shellcheck and `git diff --check`; report real acceptance runs separately.

## 28. Clarify the `install_standalone` docstring

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md).

Status: done on `main` (2026-10-18). The docstring names when install uses it,
its inputs, the six steps, what it does not touch and its failures; README's
standalone sentence points to it. No behaviour change.

### Problem

`deployment/deploy.py` `install_standalone()` says only "Install a standalone
rootless manifest fixture using the persistent config." It does not say when it
is used instead of the component install (a release without `components/`), or
what it does, in this order (as of 0.4.10):

1. `production_environment()`; requires the service user's `~/config.yaml`
   (`common.HOME / "config.yaml"`, not `~/.config/...`), else "Missing ...".
2. `check_manifests()`: validates the effective `manifests/` (kinds,
   placeholders, pull policy, mounts, links), then the database preflight.
3. `render.materialize()`: generates allowed missing secrets and renders the
   YAML once, returning it with the import volumes; no files are written yet.
4. Requires `images/images.tar`, runs `podman load` and `podman image exists`
   for every image.
5. Only then writes the import archives to `files/`, so a failed image check
   never leaves new imports beside old YAML.
6. Writes the Quadlet `.yaml`, `.kube` and `.network`, then `daemon-reload`,
   `restart` and `is-active` for the single service, and `podman ps`.

Before 0.4.10 it rendered twice (without, then with archives) and ran the
database preflight only when the config existed.

### Task

Rewrite the docstring so a developer with some Python experience can tell from
it alone what the function is for, its inputs (`~/config.yaml`, `manifests/`,
`images/images.tar`), the order above, what it does not do (no catalog,
metadata, registrations, pending record or markers) and its failure cases. No behaviour change. Keep README's
standalone paragraph consistent.

## 29. fapolicyd denies systemd's Podman launch just after a trust update

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: fix on `main`; earlier lab runs had 0 early evictions with the documented
cache size. A later counter observation remains to monitor (below).
`acceptance/fapolicyd-reload-probe.sh` reproduces
the sequence on the PROD VM (trust add/delete, `fapolicyd-cli --update`, wait
0–15 s, restart a user unit) and reports failed restarts per delay, the
effective rules, `fapolicyd.conf`, fapolicyd's journal and every FANOTIFY/AVC
denial. Found in the item 20 acceptance run `decl-app1-first-2` (revision
`8e62153`, 2026-10-17).

First probe result (PROD after `speed-app1-first`, 10 rounds): 0 of 50
restarts failed at 0, 2, 5, 10 or 15 s after an update, and there were no
FANOTIFY/AVC events. A reload takes about one second with the trust database
at 2 % capacity. fapolicyd 1.4.5; the effective rule 5 is
`deny_audit perm=any pattern=ld_so : all`, so the original denial was the
ld.so pattern detector, not a missing trust entry: the subject (systemd's
freshly forked child) was judged to start through the dynamic loader. That
points to fapolicyd losing track of the new process (for example subject
cache evictions or a full event queue under load, as during `podman load`
right before the restart) rather than to the reload itself.

State report on the same VM (`fapolicyd-cli --check-status`, since the run's
reboot, no denials): subject cache 4099 slots, 83 % in use, 3556 evictions and
**6 early subject cache evictions**; maximum queue depth 6 of 800. Early
evictions of starting processes are what can make the ld.so pattern rule
misfire, so the cache is too small for this host, and the queue is not the
cause.

Remedy (on `main`): the README documents `subj_cache_size = 16381` as a host
prerequisite (a cache size, not a rule change); `prepare-host.sh` warns when
it is smaller but does not edit fapolicyd's configuration; the lab's
prepare-host step applies the documented setting and restarts fapolicyd; and
`11-prod-audit` records the cache and queue figures. No retry was added to
deploy: rerunning `./deploy.sh install` already completes pending owner work.

Confirmed in `fapo-app1-first` on `2589710` (CLEAN PASS, no FANOTIFY/AVC
events): with `subj_cache_size = 16381` the report showed 0 early evictions
(was 6), 19 % of slots in use (was 83 %), 444 evictions (was 3556) and a
maximum queue depth of 5. The audit's figures were empty in that run because
the CLI read the script's stdin; fixed by redirecting it from `/dev/null`.
The `val-*` runs on `9dc0381` still had no figures: a clean run calls
`audit-check`, and the block ran only for `audit`. It now runs for every PROD
audit action (test: `test_clean_prod_audit_check_reports_fapolicyd_cache`).
Confirmed in `fapo-stats-app1-first` on `8629614` (CLEAN PASS): cache size
16381, 0 early evictions, 19 % of slots in use, 453 evictions, maximum queue
depth 7.

Follow-up observation, 2026-10-24: `status39-20261024-070515-renamed` on
`137a2da` ended CLEAN PASS with no FANOTIFY/AVC events, but its final audit
reported 6 early subject cache evictions at cache size 16381 (3559 slots in use,
805 total evictions, maximum queue depth 14/800). The other five final matrix
audits reported zero early evictions. This does not diagnose a new failure or
justify changing policy/cache settings during evidence recording; retain it for
monitoring and investigation if launch failures recur. The cache size is not a
guarantee of zero evictions. [Run provenance and limits](acceptance/STATUS.md#completed-real-lab-verification-2026-10-24).

### Observation

Step `10-identity-install` (Identity 0.4.9 → 0.4.10) failed at
`systemctl --user restart myproduct-identity.service`. The release had been
added to the trust file, `fapolicyd-cli --update` had run and `wait_trust`
had confirmed every package file in the live database; validation,
`podman load` and the image checks had passed. About ten seconds after the
update, systemd's child for the unit was denied:

```text
syscall=execve exit=EPERM comm=(podman) exe=/usr/lib/systemd/systemd
FANOTIFY resp=deny fan_info=5 subj_trust=unknown obj_trust=yes
Failed at step EXEC spawning /usr/bin/podman: Operation not permitted (203/EXEC)
```

`/usr/bin/podman` is trusted (`obj_trust=yes`); the subject, a freshly forked
systemd process of the `myproduct` user manager, was not (`subj_trust=unknown`).
It was the only denial in the run. The same step passed in `decl-app2-first-2`
on the same revision, as did every other install, stop/start/restart, crash,
hang, reboot and upgrade restart in both runs. Earlier launcher denials
(`exe=systemd`, `comm=(podman)`, run-18) led to the `09-launch-audit-*` steps;
their cause was not established.

### Why it matters

The documented operator procedure does the same thing: add the release's trust,
`fapolicyd-cli --update`, then `./deploy.sh install`, which restarts services. If
the denial is a window after a trust database reload, real installs and
upgrades can fail intermittently with 203/EXEC.

### Task

1. Reproduce: repeat trust add/update followed immediately by a user-unit
   restart on the lab PROD VM, and record how often and for how long after the
   update the denial occurs. Inspect the effective rule 5 (`fapolicyd-cli
   --list`), fapolicyd's version and its subject-trust handling for processes
   forked by `systemd --user` during a database reload.
2. Decide from evidence, not by weakening policy: candidates are waiting for a
   reliable "reload finished" condition before the restart, ordering the trust
   update earlier in the operator procedure, or one bounded, logged retry of a
   restart that fails with 203/EXEC and a matching denial. Never add trust
   rules, disable fapolicyd, or retry other failures.
3. If deploy code changes, keep the pending-owner semantics: a restart that
   still fails leaves the pending record for a later retry.
4. Add a focused acceptance check that installs right after a trust update and
   requires no FANOTIFY/AVC events; rerun `decl-app1-first`.

Run product tests, acceptance-harness tests, ruff, format, pyright, vermin,
shellcheck and `git diff --check`; report real acceptance runs separately.

## 30. Make the acceptance runs much faster

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: step 1 done in 0.4.10, on the operator's decision (2026-10-17): every
liveness probe now uses initialDelaySeconds 10, periodSeconds 10, timeoutSeconds
5 and failureThreshold 6 (was 90/30/5/3), without a startupProbe. Measured on
`a688c30`: each health wait about 11 s (was 92), the hang test 100 s (was 199),
app1-first 25 min (was 44), identity-only 14 min (was 22), renamed 20 min
(was 32). Step 2 done on `main`: bundles are written with gzip level 6
instead of 9 (measured locally on 3 GB of binaries: 150 s instead of 484 s,
archives 0.6 % larger), and `./build-bundle.sh <component>` builds only the
named bundles; the app1 upgrade and the inventory release without registrations
now build only that bundle. Measured in `speed-app1-first` on `bbce76d`
(CLEAN PASS): `04-bundle` 107 s (was 263), `10-build-upgrade` 32 s (was 269),
`10-identity-build` 43 s (was 94); transfer 52 s (was 47). app1-first now takes
about 17 min (44 min before step 1, 25 min after it). Steps 3–4 are optional;
weigh them against the rule that each clean run builds from source.
Raised by the operator on 2026-10-17: the item 21 matrix (six scenarios) took
several hours, which is far too long.

### Where the time goes

Measured from the step tables of the item 20 runs on `8e62153`:

| Run | Total | Health waits (85–115 s steps) | Bundle builds (~263 s each) | Everything else |
| --- | ---: | ---: | ---: | ---: |
| `decl-app1-first-3` | 44 min | 15 steps, 24 min | 2 builds, 9 min | 11 min, including the 200 s hang test |
| `decl-renamed-4` | 27 min | 9 steps, 14 min | 2 builds, 9 min | 4 min |
| `decl-help-2` | 12 min | 2 steps, 3 min | 1 build, 4 min | 4 min |

1. **Health waits are more than half of every run.** Every container has
   `initialDelaySeconds: 90` and `periodSeconds: 30`, so after any install,
   start, restart, reboot or upgrade, `healthy` cannot pass in less than about
   90 seconds, even when everything is up in five. The hang test (200 s) is
   also derived from these numbers.
2. **Bundle builds take about 4.5 minutes each.** `build-bundle.sh` builds all
   five bundles, and `bundle.py` writes them with `tarfile` `w:gz`, which is
   single-threaded gzip at level 9. The upgrade steps rebuild every bundle to
   change one.
3. **The six scenarios repeat the same work.** Each one resets both VMs and
   rebuilds images, runs the unit suite and builds bundles from the same
   revision.

### Task

Measure first, on the lab VMs, then change in this order. Stop once the full
matrix is comfortably under an hour.

1. **Health timing (product decision, largest gain).** Check on Podman 5.8.2
   what `kube play` does with `startupProbe` and with a shorter
   `initialDelaySeconds`: when the status becomes `healthy`, and how a hung
   container is detected. Then propose one of these to the operator, with
   measured times:
   - a `startupProbe` with a short period and a generous total budget (slow
     first starts such as Identity and PostgreSQL initialization keep their
     time), plus a liveness probe without a long initial delay
   - or a shorter `initialDelaySeconds` and period

   This changes the documented product contract (README "Health checks and
   acceptance", `tests/test_health.py`, the VM checklist and the hang-test
   limit), so it needs the operator's approval before it changes.
2. **Bundle builds.** Time `podman save` against compression separately. Then
   consider a lower gzip level or a faster compressor available on the build
   host, and building only the changed component in the upgrade steps. The
   archive format and checksums must stay the same for the target.
3. **Repeated work across scenarios.** Consider a matrix mode that builds
   images, the unit suite and bundles once per revision and reuses them,
   checked by hash, in each scenario. This conflicts with the current rule
   that every clean run builds from source, so weigh it last and keep single
   scenarios unchanged.
4. Record before and after times per scenario in the acceptance README, and
   keep every check that exists today. Speed must not come from dropping
   evidence.

## 31. Refuse component IDs that are prefixes of each other

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: done on `main`. `catalog.check_id_prefixes` refuses the pair in
`bundles.yaml` and, on install, among the installed components and the
incoming bundle, before any write or host command; documented in
[components](docs/COMPONENTS.md#component-ids). An existing installation with
such a pair cannot install either component again until one is renamed;
none is known. Found by the independent review of item 21 (`c92897d`); it
predates that change.

### Observation

Resource names are checked only for the prefix `<component>-`. With components
`orders` and `orders-data`, the name `orders-data-db` passes the check for both,
so the two components can declare the same Podman volume or Secret, and
`uninstall --delete-data` of one can delete the other's data. Reproduced with
`render.check_component_names`.

### Task

1. Refuse, in the catalog (`catalog.load_catalog`) and for installed metadata,
   any component ID that equals another ID followed by `-` and more characters.
   Report both IDs and say how to rename.
2. Check whether existing installations could already hold such a pair; if so,
   refuse the install of the second with the same message, before any write.
3. Add catalog and install regressions. No lab run is needed beyond the usual
   matrix when this ships.

## 32. Move registration and pending-record code out of deploy.py

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its
mandatory understandability review.

Status: done on `main` (2026-10-18), without behaviour change.
`deployment/registrations.py` holds staging, client registrations, comparison,
writing, `apply_registration_updates` and the pending record (`pending_path`
through `acknowledge_owner`); it imports catalog, common and render, never
deploy. `component_paths`, which staging needs, moved to `catalog.py` beside
`metadata_path`. deploy.py (about 1030 lines) calls both modules by name, so
tests and `tests/retry_driver.py` patch them there. ARCHITECTURE's module table
and install sequence diagram (PNG re-rendered) show the new module.

`deployment/deploy.py` holds about 1400 lines. The registration and pending
code (about 400 lines: `registration_stage`, `client_registration`,
`registered_client_id`, `write_registrations`, `registration_changes`,
`component_imports` and `pending_path` through `acknowledge_owner`) is used by
install and uninstall but does not depend on them. Move it to
`deployment/registrations.py` with a one-way import from deploy.py, without
changing behavior. Tests and `tests/retry_driver.py` patch these functions on
the `deploy` module, so update those references in the same change. Run the
full product and harness suites; no lab run is needed for a pure move, but the
next scheduled matrix covers it.

## 33. Refuse Secret item keys that no source provides

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: done on `main` (2026-10-18); the full lab matrix on `77b27cd` (`b34-app1-first`, `b34-app2-first`,
`b34-help-only`, `b34-identity`, `b34-platform-help`, `b34-renamed`) was CLEAN
PASS. `render.secret_keys`
decides each Secret's keys from file names, `generate` names and inline
`data`/`stringData` (no contents read; a missing source stays unknown and is
reported by the source check). `render.check_secret_keys` refuses a missing
`secret.items[].key` or `secretKeyRef.key` (optional references skipped). It
runs at the start of `materialize`, before generation (so dev `prepare` and
`install` refuse before writes, after the database preflight), and in
`validate`'s source checks in the same order. Tests: tests/test_secret_keys.py,
including one product refused identically by validate, prepare and install;
demo test fixtures now write the key files the demo pods select.

Found by the best-practice review at `689156b` (finding 2, CONFIRMED by
reproduction).

### Problem

`render.check_links` (around `deployment/render.py:559`) checks that a Secret a
manifest mounts or references exists, but not that the keys it selects exist.
A volume `secret: {secretName: app1-todo-files, items: [{key: nonexistent-key,
path: ...}]}`, or an `env.valueFrom.secretKeyRef.key`, naming a key that no
source provides passes `validate`, the file-source checks and `materialize`.
It fails only when Podman starts the pod. Item 21's text claimed the opposite;
that claim is corrected there.

### Task

1. Decide each Secret's keys from declarations, before any side effect and
   without reading credential contents: the file names of a `SECRET_FILES`
   source (a directory's entries or the file itself), `generate` names, and the
   `data`/`stringData` keys of an inline Secret manifest.
2. Refuse a `volumes[].secret.items[].key`, `secretKeyRef.key` (env) or other
   explicit key reference to a key the Secret does not provide. The error names
   the manifest, the pod/container, the Secret and the key, and lists the keys
   that exist (names only).
3. Run it where the other link checks run, so `validate`, `prepare` and
   `install` agree. Keys of a `SECRET_FILES` directory that is still missing
   at validate time follow the existing missing-source rule.
4. Regression tests: missing item key, missing `secretKeyRef` key, generated
   key present, inline Secret key, and a directory source; plus a demo manifest
   check. Update docs/COMPONENTS.md or README where Secret references are
   described.

## 34. Wait for healthy containers after install and upgrade

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: done on `main` (2026-10-18); the full lab matrix on `77b27cd` (`b34-app1-first`, `b34-app2-first`,
`b34-help-only`, `b34-identity`, `b34-platform-help`, `b34-renamed`) was CLEAN
PASS; the app1 install log shows
`[OK] myproduct-app1.service: 3 containers running and healthy` and the same
for the restarted owners identity and platform. `deployment/health.py`
waits after every `restart_service` (component, install owners and uninstall
owners) and after the standalone restart: every app container of the unit's
installed YAML (`<pod>-<container>`, init containers excluded) must be running
and healthy, or running without a health check, within 150 s. `unhealthy` fails
at once; the timeout lists each container with its last state (`missing`,
`exited`, `running/starting`). Only `podman container inspect` State is read.
Because the wait is part of `restart_service`, an owner is acknowledged and the
completion marker written only after health, so retries behave as for a failed
restart. `validate` and dev `prepare` make no Podman calls. Tests:
tests/test_health_wait.py; fresh-process `test_unhealthy_owner_stays_pending_and_the_retry_finishes`
and `test_unhealthy_first_install_writes_no_marker_and_the_retry_finishes`. The
harness keeps its stricter whole-installation `healthy` step.

Found by the best-practice review at `689156b` (finding 5).

### Problem

`deploy.restart_service` runs `systemctl --user restart` and `is-active`. An
active unit does not prove that the pod's containers are running, let alone
healthy: a crash loop or a failing health check still reports success, and
`./deploy.sh install` prints OK. The acceptance harness has its own health wait
(`healthy` in acceptance/remote.sh and the README helper); the product does not.

### Task

1. After the component's own restart (and each restarted owner), wait until
   every container of that component's installed YAML is running and, where it
   has a health check, healthy. Use `podman inspect` state only; print no
   environment or inspect content beyond names and states.
2. Bounded wait (for example 150 s, as the harness), then fail with the
   component, the container and its last state, plus the journal hint cli.py
   already prints. The failure must keep the retry contract: the pending owner
   record and completion marker behave exactly as for a failed restart today
   (the marker is written only after the component is healthy).
3. Decide and document whether `uninstall` restarts of owners also wait.
4. Keep `./deploy.sh validate` and dev `prepare` free of Podman calls.
5. Tests: healthy, starting then healthy, unhealthy, exited, missing container
   and timeout; a fresh-process retry after an unhealthy first install. Update
   README (what install guarantees), ARCHITECTURE's sequence diagram and the
   harness where its own wait becomes redundant (keep its stricter checks).

## 35. Run demo apps with a database role that is not a superuser

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md).

Status: planned. Found by the best-practice review at `689156b` (finding 1,
CONFIRMED). Matters if the demo apps or their manifests are used in production.

The official PostgreSQL image creates `POSTGRES_USER` as a superuser, and the
demo backends (app1, app2, Identity) connect with that same user
(`components/*/manifests/40-postgres.yaml`, `60-todo.yaml`). A compromised web
application thus has administrator rights in its database instance.

Separate administration and migration from normal operation: the init/schema
step uses the superuser; the application gets its own role with only the
rights it needs and its own password (a second generated secret). Adapt the
database preflight, which today assumes one password shared by server and
client, and item 7 (PostgreSQL layouts). Document the pattern for products in
docs/COMPONENTS.md. Lab run required (fresh install and upgrade with retained
volumes, which must keep working: existing databases need the role created by
an idempotent init step).

## 36. Harden the demo application containers

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md).

Status: planned. Found by the best-practice review at `689156b` (finding 3).

`apps/todo-backend/Containerfile` and `apps/identity/Containerfile` set no
`USER`; the manifests set no `securityContext` and no CPU/memory limits.
Rootless Podman already means container root is not host root, but the apps can
be confined further: a non-root container user, `allowPrivilegeEscalation:
false`, dropped capabilities, `readOnlyRootFilesystem` where the app allows it
(with explicit writable mounts), and realistic resource limits.

Do it together with the secret file modes: signing keys and other mounted
secrets are 0400 for container UID 0 today, so changing the user alone breaks
startup. Use only fields Podman 5.8.2 `kube play` supports (for example
`runAsUser`, `capabilities`, `readOnlyRootFilesystem`; not `runAsNonRoot`,
`fsGroup`, `readinessProbe`, `startupProbe`), and add manifest validation for
fields Podman would silently ignore if that proves necessary. Lab run required.

## 37. Document and protect credential copies at rest

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md).

Status: planned. Found by the best-practice review at `689156b` (finding 4,
a deliberate limitation today). Coordinate with items 2, 3 and 24.

Private files are written 0600 from the first byte and existing credentials are
kept, but nothing is encrypted at rest: source credentials, the rendered YAML
(base64 Secrets, not encryption) and Podman's Secret volumes all hold the
values, and removed keys can remain in volumes. `SECRET_TEMPLATES` adds composed
values to the same YAML/Podman stores; there is no separate derived credential
file to back up. Config recipes plus original passwords reconstruct them. An
item 44 PFX is another copy of a signing key at rest; its password does not
protect against anyone who can read both the PFX and the password file. The
organisation's Identity image has the PFX password hardcoded as "password", so
the PFX encryption gives no real protection there; file modes, Secret delivery
and backups protect the key. A production CA key on the target (item 45) is
another copy of key material that needs the same care. Identity stores Data
Protection keys with `PersistKeysToFileSystem` (apps/identity/Program.cs)
without key encryption.

Document every copy of each credential (where, who can read it, how it is
backed up, rotated and removed), and offer an encrypted backup procedure and an
explicit at-rest protection choice for the Identity keys (for example a
certificate) that an organisation can apply offline. No online secret service
is required.

## 38. Sign bundles so the target can authenticate them

Policy update (item 54, 2026-10-23): production publication/installation now
requires a detached signature verified against the independently pinned product
keyring. Unsigned builds remain available for development only. This supersedes
the original optional-production-signature policy below.

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md).

Status: done and lab-verified (2026-10-19): every run of the `t3-*`/`t5-*`
matrix signed its bundles on DEV and PROD verified each with `gpgv` (Good
signature) before the checksum and unpacking. With
`BUNDLE_SIGNING_KEY` set, `bundle.sign` writes `<archive>.asc` (gpg detached,
armored) after the checksum; without it the build warns and writes none, and a
stale `.asc` is always removed. The README documents exporting the public key
once, delivering it separately, and `gpgv --keyring ./bundle-signing.gpg`
before the checksum and unpacking (never a script from the unverified
archive). The harness signs every DEV build with a per-run lab key and verifies
with `gpgv` on PROD in `prepare_release`; readiness requires gpg and gpgv.
Tests: tests/test_signing.py (real gpg/gpgv: valid, tampered, unsigned, unknown
key) and the harness prepare-release sequence.

`bundle.py` writes `.sha256` files and `checksums.sha256` inside each release.
They detect corruption, but anyone who can replace the archive can replace its
checksum too, so they do not prove who built it. Add an optional detached
signature per archive (for example OpenPGP or minisign, with a key the
organisation controls on the build machine), a documented verification step on
the offline target before `prepare-host.sh` and unpacking, and harness support
for a lab key. Keep unsigned builds possible for development; the README states
which one an operator has.

## 39. Show the installed components and versions on the target

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: implemented with local product and harness checks (2026-10-24), on
`feature/39-component-status`, based on CLI rename commit `88f3110`.
`./deploy.sh status [--json]` reports installed versions and unit states in
recorded dependency order, incomplete installs/upgrades/reinstalls and pending work;
it reads `/var/lib/<product>/state` without config/credential reads or writes.
Review follow-up: the existing pending record now covers the full install attempt,
including same-version reinstalls without owners, until the completion-marker
write succeeds. Fresh-process install/failure/status/retry regression coverage
preserves the previous completed version and the `newer-only` skip policy.
The fix is committed as `bd0cc77`. The coverage follow-up demonstrates the test
failing against `b46d548` and adds an opt-in `--status-retry` acceptance probe,
including actual container consumption after retry. The 2026-10-24 six-scenario
matrix is CLEAN PASS, including the probe in all five applicable scenarios.
[Verification and understandability review](acceptance/STATUS.md).
Current-change real Podman/systemd verification is recorded with exact revisions,
477 verified step logs and the non-blocking fapolicyd counter observation in that
report. Python 3.6 runtime and the separate 65–67 operator work remain outstanding.
The original request (2026-10-19) and task follow.

### Problem

The target already records everything: `installed/<id>` holds the completed
version, `metadata/<id>.json` the installed descriptor (product, version,
dependencies, roles), and `pending-operation.json` unfinished work. But there is
no command that shows it; an operator has to read private files in the service
home by hand, for example
`sudo -u <user> sh -c 'cd /var/lib/<user>/installed && grep -H . *'`.

### Task

1. Add `./deploy.sh status`, run as the service user from any unpacked bundle of
   the product (the bundle only supplies the code; status reads the installation's
   `state/` directory). Output, one line per installed component in dependency order:
   component, installed version, unit name and `systemctl --user is-active`
   state; then the product name and any pending operation (operation,
   component, owners). Show an unfinished first install (metadata without
   marker) explicitly.
2. Read-only: no writes, no pending record, no Podman calls beyond reading
   unit state; it must work while another component's install is pending and
   when a unit is failed. Refuse a bundle of another product the same way
   install does, or print the installed product and say the bundle differs.
3. Optional `--json` with the same fields for collection by other tools.
4. Exit 0 when everything listed is installed and active, non-zero otherwise,
   so scripts can use it as a check.
5. Tests: several components with different versions, an unfinished install,
   a pending operation, a failed unit, an empty home; the harness runs it on
   PROD after installs and checks the versions it expects. Document it in
   README (operations) and COMPONENTS (installed state).

## 40. One version file per component in its own directory

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: done and lab-verified: six-scenario matrix `t6-*` CLEAN PASS on `b3f3cf1` (2026-10-19; Oracle Linux 9.8, rootless Podman 5.8.2, SELinux Enforcing, fapolicyd on PROD). Earlier status: implemented on main
on 2026-10-19; independent review's ordinary and isolated platform runs green. Component-local version files replace source root
version files and the catalog override. Build descriptors and installed metadata
keep their existing format. Acceptance upgrade builders and renamed products
use the selected component's version. Local verification is recorded below;
the full real Podman/systemd lab matrix remains required.

Verification (2026-10-19): 64 demo tests and 196 acceptance-harness tests
passed. The focused catalog/bundle/wrapper set passed 42 tests; the final
component/layout set passed 29 tests in a fresh offline export without demo
files. A new regression checks independent component versions with no root
VERSION; coverage also refuses missing/invalid/escaping version files and the
removed catalog field. Renamed-generator coverage checks every copied version.
Independent review reported on 2026-10-19 supersedes the earlier local
verification gaps: both `tests/run.py platform` and `platform --isolate` ran
347 tests successfully. Demo ran 64 tests successfully (one proxy test skipped
when GNU envsubst was absent); `all --list` had 411 unique tests and no
duplicates. Acceptance-harness tests, Pyright, bash syntax and diff checks
passed. The review found two Ruff DTZ007 errors, corrected in the follow-up
by making parsed OpenSSL GMT dates explicitly UTC. These are review-provided
results for the reviewed main revision, not a full-suite run of the subsequent
CA-option/recovery-message changes. Real lab, .NET and Python 3.6 remain unverified.

Ruff lint/format, scoped Pyright, ShellCheck, bash syntax, diff checks and static
Python 3.6 compatibility passed. Real Python 3.6 and the lab matrix were not run.
Understandability review: source_descriptors reads and validates the component
version before build side effects, then the existing descriptor flow carries it
into bundle and installed metadata. A missing version stops before publication;
a corrected file can be retried without changing installed state. No new
migration, lifecycle branch or credential behavior is introduced.

### Problem

Versions live in root files chosen by `version_file:` in `bundles.yaml`
(default `VERSION`): the demo apps share `VERSION`, platform and Identity use
`PLATFORM_VERSION` and `IDENTITY_VERSION`, and the renamed product adds
`INVENTORY_VERSION`. In a real product every component has its own version, so
the root would collect one file per component, far from the component's code,
and two teams releasing different components touch the same directory.

### Task

1. Make `components/<id>/VERSION` (one `major.minor.patch`) the only source of a
   catalog component's version. Remove `version_file` from the catalog schema;
   a missing or invalid file is refused with a message naming the file.
   Components that should share a version simply hold the same number.
2. Remove the root `VERSION`, `PLATFORM_VERSION` and `IDENTITY_VERSION` from the
   product repository. A standalone manifest fixture (no `bundles.yaml`) keeps
   its root `VERSION` unchanged; each built bundle keeps its informational
   `VERSION` file with that component's version.
3. Update the acceptance harness: upgrade, help, platform and Identity release
   builds bump the component's own file instead of a root file; the renamed
   product generator writes `components/<id>/VERSION` (no `INVENTORY_VERSION`);
   version reads in acceptance.py and remote.sh follow.
4. Update tests, README, docs/COMPONENTS.md and bundles.yaml comments. No
   migration is needed: installed metadata already holds each component's own
   version, and the change affects only the source checkout.
5. Run the full lab matrix (the upgrade scenarios change).

## 41. Build Secret and ConfigMap values from templates at install time

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: done and lab-verified (2026-10-19); see the final result below.
Earlier status: Secret-template delivery is on `main`; the ConfigMap inline extension
(section 2b, added in `b6bf75c`) is now implemented with a shared regex
substitution callback, public-only resolver, demo value and runtime assertions
for all six scenarios. Real lab verification remains pending for both parts. On
2026-10-19 the operator explicitly authorized implementation before the lab
probe and will run it in the evening. No lab result is claimed. Local evidence
and runnable lab commands are recorded in [Secret template verification](acceptance/SECRET-TEMPLATES.md).
The initial lab probe requirement below is deferred by that operator decision.

Local verification (2026-10-19, Python 3.12.14): 379 product tests collected,
376 passed and 3 existing GnuPG tests explicitly skipped after the ordinary run
failed in their environment setup (`/tmp` absent; redirected GnuPG key generation
also unavailable). All 190 acceptance-harness tests passed. Ruff check/format,
Pyright (0 errors/warnings), `bash -n acceptance/remote.sh` and `git diff --check`
passed. Vermin reports Python 3.6 for `deployment/`, `bundle.py` and the new/changed
template/retry product tests; no actual Python 3.6 or .NET/Podman execution here.
Templates, Identity integration, the disposable env/file/replace/Quadlet probe,
redaction/mode checks, and pinned 0.4.11 -> template Identity upgrade are ready.
The six-scenario CLEAN PASS requirement remains outstanding, not waived.

ConfigMap extension verification (2026-10-19): 389 product tests collected,
386 passed and the same 3 environment-blocked GnuPG tests skipped. All 193
acceptance-harness tests passed. Targeted reruns cover preserved regex/backslash
input and invalid ConfigMap metadata during initialization. Ruff check/format,
Pyright (0 errors/warnings), static Python 3.6 compatibility, shell syntax and
whitespace checks pass. `replace()` remains unchanged; Secret and ConfigMap text
use `templates.substitute()` with separate source policies. Platform 0.4.12 adds
`PUBLIC_ENDPOINT`; every lab health check verifies it inside its actual consumer,
including the renamed gateway. The lab matrix remains unexecuted here.

Review finding 1 fixed (2026-10-19): declared operator-supplied Secret sources
may be absent at init-config; unknown groups/known missing keys still fail early.
Three new regressions failed before the fix and pass after it. The 395-test
product run had 392 passes and 3 existing GnuPG setup errors (`/tmp` absent).
The acceptance harness passed 193/193 on rerun; its first run had one renamed
credential-fixture failure. Ruff/Pyright/static Python 3.6/shell/diff gates checked.
Real Podman/systemd, the lab probe and six-scenario CLEAN PASS remain outstanding.

Review finding 2 checked (2026-10-19): `render.with_derived` centralizes
PUBLIC_HOSTNAME derivation. Template checks deliberately remain before init
writes and in effective_documents for standalone prepare/install/validate,
with an explanation and standalone regression. Final verification: 396 product
tests, 393 passed and 3 GnuPG setup errors (`/tmp` absent); all 26 template tests
and all 193 acceptance-harness tests passed. Ruff check/format, Pyright (0
errors/warnings), shell/diff checks and static deployment Python 3.6 passed;
Python 3.6 was not executed. Understandability and Secret templates/Validation/
Credential retention contracts were reviewed. Real Podman/systemd, the lab
probe and six-scenario CLEAN PASS remain outstanding; item 41 is not complete.

Lab run `templates-app1` on `603d626` (2026-10-19) was NOT CLEAN at
`03-example-failures`: `examples/failures/partial-placeholder` used an inline
placeholder in ConfigMap data, which item 41 now supports, so `prepare`
succeeded. The case now uses a container env value, which stays refused, and
`ExampleFailureTests` runs `examples/run.sh failures` in the product suite (it
needs no Podman). The `templates-identity` run stopped in `00-readiness` without
a message before touching the VMs (consistent with an interrupted run); the
other scenarios were not reported. The six-scenario matrix must be rerun.

Lab run `t2-app1` on `b9612b5` passed through `07-check` (build, signing and
`gpgv`, Secret env/file/restart probe, Identity connection string, install,
health, inline `PUBLIC_ENDPOINT`, SELinux/fapolicyd) and failed at
`07-database-auth`. A read-only diagnosis on PROD showed every check passing
except the new Identity journal check: `journalctl --user` as the service user
(UID 995) exits 1 with insufficient permissions. Root now reads the service
user's journal by `_UID` since run start, requires records and rejects any
password without printing content; a harness test covers it. Matrix rerun pending.

Matrix `t3-*` on `7f23775` (2026-10-19, Oracle Linux 9.8, rootless Podman 5.8.2,
SELinux Enforcing, fapolicyd on PROD): app1, app2, help and platform CLEAN PASS.
Identity NOT CLEAN at `04-bundle`: the pinned 0.4.11 baseline left uncommitted
files in the DEV clone, so the clean-checkout check refused the build; `shop`
was not run. The baseline is now a local commit in the disposable clone and the
upgrade builder checks out the tested revision explicitly. Identity and `shop`
must be rerun; item 41 is not complete until they are CLEAN PASS.

Run `t4-identity` on `f5ae8d6` built and installed the 0.4.11 baseline, upgraded
to the template build and passed `identity-after` (password, keys and volumes
unchanged, new image and content running), then stopped at
`10-identity-persistent`: the controller compared `identity/config.yaml` to its
pre-upgrade hash although the scenario adds `SECRET_TEMPLATES` to it on purpose.
That step now allows exactly this file to change (verified on PROD by the
explicit addition and `identity-after`); every other file and the CA must stay
identical. Identity and `shop` must be rerun.

Final lab result (2026-10-19, Oracle Linux 9.8, rootless Podman 5.8.2, systemd
252, SELinux Enforcing, fapolicyd active on PROD): six-scenario matrix CLEAN
PASS. `t3-app1`, `t3-app2`, `t3-help` and `t3-platform` ran on `7f23775`;
`t5-identity` and `t5-shop` on `2c0ed76`. The commits in between change only
the acceptance harness (Identity baseline commit, upgrade builds checking out
the tested revision, the allowed Identity config change), not product code.
The runs cover the disposable env/file/`kube play --replace`/Quadlet probe
(probe checks 1-4 of section 1, as the DEV lab user), Identity's complete
connection string (exit 0/2/1), the inline `PUBLIC_ENDPOINT` in its consumers,
database/journal/ConfigMap/0600 checks, the pinned 0.4.11 in-app -> template
Identity upgrade with unchanged password, keys and volumes, and the renamed
product `shop`. Not covered: the probe under the hardened PROD account (manual
command in [Secret template verification](acceptance/SECRET-TEMPLATES.md)), an
Identity start with an invalid connection-string value such as `Port=abc`,
and actual Python 3.6 execution. A full matrix on a single commit followed:
`t6-*` on `b3f3cf1`, CLEAN PASS in all six scenarios.

### Background and decision

The organisation's real .NET apps read one complete `ConnectionStrings__Default`
(password included) from the environment. They cannot change the app code and
cannot build derived images, so neither Identity's in-app
`DatabaseEnvironment.cs` nor item 6's launcher is available to them. Today they
build the string by hand at install time; deploy should do it for them.

This deliberately changes item 6's rule "do not render credentials into YAML or
write connection strings to disk". It is accepted because the rendered install
YAML already holds every Secret (base64, mode 0600, owned by the service user),
so a composed value is the same exposure class. Rules that stay:

- a credential never goes into a ConfigMap, a plain `env: value:`, a log, an
  error message, `validate` output or any file other than the existing 0600
  install YAML;
- the password file stays the only source of truth: the template is rendered
  from it on every install and upgrade and is never stored or edited separately.

Accepted, documented risk: an env value is visible to the service user and root
through `podman inspect`, `/proc/<pid>/environ` and child processes. A Secret
mounted as a file (supported by the same templates) avoids that for apps that
can read files.

### Agent task

#### 1. Probe Podman first (lab, before building)

`env[].valueFrom.secretKeyRef` is validated today (`render.check_secret_keys`)
but no shipped manifest uses it. On a lab VM (rootless Podman 5.8.2, SELinux,
fapolicyd), with a hand-written kube YAML holding a `Secret` document and a pod
that reads it, verify and record:

1. `podman kube play` and the Quadlet `.kube` unit both set the env value from
   `secretKeyRef` correctly;
2. a changed Secret value reaches the container after the normal upgrade path
   (`kube play --replace` through the unit restart);
3. whether `podman inspect` shows the value (expected: yes; document it);
4. the same Secret also works as a mounted file through `volumes[].secret.items`.

If 1 or 2 fails, stop and report before writing code.

#### 2. Config format

```yaml
# components/<id>/config.defaults.yaml or the operator's config.yaml
SECRET_TEMPLATES:
  identity-database:
    ConnectionStrings__Default: "Host=@@DB_HOST@@;Port=@@DB_PORT@@;Database=@@DB_NAME@@;Username=@@DB_USER@@;Password=@@secret:identity-database-password/password@@"
```

- The ID follows the same naming, length and component-prefix rules as
  `SECRET_FILES` IDs (`check_component_config_names`). It must not collide with a
  `SECRET_FILES` or `VOLUME_FILES` ID. Keys match `common.SECRET_KEY`.
- A value is a string. Within `SECRET_TEMPLATES`, the allowed placeholders are:
  - `@@NAME@@` is an effective config value of the same component, shared
    settings included. Only strings and integers are allowed; a missing key, a
    list, a dict, a boolean or null is refused.
  - `@@secret:<id>/<file>@@` is the content of `<file>` in this component's
    `SECRET_FILES.<id>`, generated files included. Strip trailing LF exactly like
    postgres `file_env` and `DatabaseEnvironment.cs` (`TrimEnd('\n')`).
- No templates inside templates and no nested placeholders. Text left over that
  still looks like `@@...@@` is refused.
- Outside ConfigMap `data`, placeholders in manifests stay whole-value only
  (`common.PH`); the existing
  "Unreplaced @@...@@" check must keep working.
- **Characters.** The template does not know the connection-string syntax, so
  deploy does not escape. Every substituted value (config or secret) that
  contains `;`, `"`, `'`, a control character, or leading/trailing whitespace is
  refused. The message names the template, the key and the source
  (`SECRET_FILES.identity-database-password/password`), never the value.
  Generated passwords (letters and digits) always pass. Document this, and how to
  replace an operator-supplied password that fails.
- An unknown placeholder, a missing group or file, or an empty secret file gives
  a `DeployError` naming the template and key, without the value.

#### 2b. Inline placeholders in ConfigMap data

The same engine also fills ConfigMap `data` values, so non-secret strings can be
built from several config values:

```yaml
data:
  DB_HOST: "@@DB_HOST@@"                      # whole value, as today
  API_URL: "http://@@API_HOST@@:@@API_PORT@@" # new: inline
```

- **Scope.** Inline placeholders are allowed only in ConfigMap `data` values,
  multi-line file content included, and in `SECRET_TEMPLATES`. Everywhere else
  in manifests (env `value:`, images, names, volumes) placeholders stay
  whole-value only, and the existing "Unreplaced @@...@@" check applies.
- **Allowed placeholders.** Only `@@NAME@@` is allowed in ConfigMaps.
  `@@secret:...@@` in a ConfigMap is refused with a message that points to
  `SECRET_TEMPLATES`, so a credential can never reach a ConfigMap.
- **Value types.** A whole-value placeholder keeps today's behaviour (the
  value's type, then the existing `str()` of ConfigMap data). With inline text
  the result is always a string. Only strings and integers may be inserted; a
  list, dict, boolean or null is refused.
- **No escape syntax.** A literal `@@` in ConfigMap content stays refused, as
  it is today; nobody has needed one.
- **Demo and acceptance.** Add one inline value to a demo ConfigMap that an app
  really reads or that the harness checks inside the running container (for
  example `podman exec ... printenv`). Check it in all six scenarios, the
  renamed product `shop` included.

#### 3. Rendering and validation

- **Static checks (no secret contents read).** Schema, IDs, placeholder syntax,
  config keys exist, referenced secret groups and files are declared (existing
  or `generate:`). These run in `validate_component_config` / `validation.check_sources`
  and `./deploy.sh validate`, like `check_file_sources` today.
- **Content checks and rendering.** In `render.materialize`, after
  `generate_secrets` and `load_file_group(SECRET_FILES)`, render each template
  into an `Opaque` Secret document beside `secret_documents()`, with the same
  size limit.
- **Validation.** `declared_volume_names` / `effective_documents` count template
  IDs as declared Secrets, so `check_links` accepts `secretName`/`secretKeyRef`
  to them. `secret_keys()` includes template keys, so `check_secret_keys`
  catches a wrong key.
- **Upgrades.** A changed password or config value changes the rendered YAML and
  must follow the existing upgrade/restart path; prove it with a test.
- Nothing is printed and nothing new is written.
- **Implementation.** Write one small substitution function using the
  standard library, `re.sub` with a replacement callback. Share it between
  `SECRET_TEMPLATES` and ConfigMap data, and leave `replace()`'s whole-value
  path as it is.
  - Do not use `string.Template`: its `$NAME` syntax collides with the nginx
    `${...}` templates in ConfigMaps, and bending it to `@@` means overriding
    its regex.
  - Do not add Jinja2: it is a new offline dependency for Python 3.6 hosts and
    has far more features than needed.
  - The callback raises `DeployError` naming the placeholder (never a value).
- A new module (`deployment/templates.py` or similar) is fine if `render.py`
  grows too much; remember `git add` (the renamed-product generator uses
  `git ls-files`).

#### 4. Use it in the demo: Identity

Identity becomes the reference for "the app reads a ready connection string",
which is how the organisation's own apps work:

- `components/identity/config.defaults.yaml`: add `SECRET_TEMPLATES.identity-database`
  with `ConnectionStrings__Default` (`Timeout=5;Include Error Detail=false`,
  matching today's builder settings).
- `components/identity/manifests/50-identity.yaml`: set `ConnectionStrings__Default`
  from `secretKeyRef`. Remove `DB_*` env and the `password` volume from
  identity-server. The postgres pod keeps its password file unchanged.
- `apps/identity`: remove `DatabaseEnvironment.cs`. `Program.cs` reads
  `ConnectionStrings__Default`; if it is empty it prints "Missing
  ConnectionStrings__Default" and exits 1. `--database-check` keeps exit codes
  0/2/3 and its messages. Bump the Identity image and component version.
- app1/app2 (Python) are unchanged and keep showing the file-secret pattern.
  Document both patterns and when to use which.

#### 5. Tests

- **Unit tests** (`tests/test_secret_templates.py`):
  - rendering and LF stripping;
  - integer config values;
  - unknown, list, bool and missing placeholders;
  - missing group or file;
  - each refused character;
  - ID collisions;
  - `secretKeyRef` key checks;
  - size limit;
  - `validate` reads no secret contents;
  - a changed password changes the rendered YAML;
  - every error message is free of the secret value (assert the value string is
    absent);
  - ConfigMap inline values: several placeholders in one value, multi-line file
    content, a whole value keeping today's behaviour, `@@secret:...@@` refused
    in a ConfigMap, and an inline placeholder outside ConfigMap data still
    refused.
- **`acceptance/database_test.py`:** pass `ConnectionStrings__Default` to the
  Identity image directly. Keep the correct password, wrong password (exit 2)
  and missing value (exit 1) cases. Remove the `DB_*` permutations that no
  longer apply.
- **`acceptance/remote.sh`.** Keep the `--database-check` check (around line
  1379). Add:
  - no ConfigMap in the rendered YAML contains the database password;
  - the password is absent from `./deploy.sh` output and from the user journal of
    the Identity units;
  - the rendered YAML is still mode 0600.
- **Identity upgrade scenario** (old in-app build to the template build): the
  password file is byte-for-byte unchanged, the same database and users work,
  and login passes.
- **All six scenarios** must pass, the renamed product `shop` included
  (template IDs follow component IDs, not the product name).

#### 6. Documentation

- **docs/COMPONENTS.md:** a "Secret templates" section with the example, the
  character rule, env vs mounted file, and the accepted exposure.
- **README:** the config reference.
- **docs/REVIEW_GUIDE.md:**
  - update the "Credential retention" contract;
  - add a "Secret templates" row;
  - add an accepted gap: env values visible to the service user and root.
- **ARCHITECTURE.md:** the "Manifest values" flow; re-render diagrams if changed.
- **BACKLOG:**
  - item 6: Identity no longer demonstrates an in-app builder, and templates
    cover unchanged images that read a complete string;
  - item 37: template Secrets are one more copy at rest;
  - item 2: rotation must re-render templates.

#### Out of scope

- Docker Compose; the organisation's compose setup is not touched.
- Format-specific escaping (Npgsql quoting); inline placeholders outside
  ConfigMap data and `SECRET_TEMPLATES`; an escape syntax for a literal `@@`.

#### Done when

`ruff`, `pyright` and the unit tests are clean; the Podman probe results are in
this item; the six-scenario lab matrix is CLEAN PASS and recorded here. Work on
`main`, as agreed for this repository.

## 42. Explain client registration and import volumes in the architecture diagrams

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: planned; requested by the operator on 2026-10-19. Documentation only.

### Problem

The install sequence diagram in ARCHITECTURE.md shows registration staging,
materialization, import archives and owner restarts, but does not explain how
an application's client.yaml becomes files in Identity's /clients mount. It is
also unclear why identity-clients needs no VOLUME_FILES entry in config.defaults.yaml.

### Task

1. Add a focused sequence diagram and supporting text in ARCHITECTURE.md for
   public client registration delivery. Keep the main install diagram readable;
   link it to this detail rather than expanding every internal call there.
2. Trace client.yaml and the public certificate through client_registration(),
   registration_stage() (client.json, client.crt and installed.json),
   component_imports(), materialize()/volume_claims() and write_file_archives().
   Explain the PVC import annotation and Podman's import of the archive when
   Quadlet starts the service, ending with Identity reading /clients at startup.
3. Show that bundles.yaml accepts.clients selects the volume name, using
   identity-clients as an example, not a hardcoded platform requirement. Explain
   how this differs from an ordinary data PVC and operator-declared VOLUME_FILES.
4. Cover an app install/update while Identity is already installed:
   write_changed_owner_imports() rebuilds the owner's archive and
   restart_component_services() restarts the affected owner when registration
   data changes. Distinguish durable host registrations from temporary staging,
   import archives and the container mount; private client keys stay with apps.
5. Check every arrow against current code, validate Mermaid syntax and any
   rendered diagram artifacts using the existing documentation workflow, and
   run git diff --check. Do not change runtime code or configuration contracts.
6. Cover the failure, retry and removal path, as the route/client trace in
   docs/REVIEW_GUIDE.md section 3 requires (declaration -> planned change ->
   pending state -> persistent registration -> import -> owner restart/check ->
   acknowledgement). Show that registration_changes() decides the owners and
   save_pending() records pending-operation.json before registrations and import
   archives are written; what a new process does after a failed Identity restart
   or health check; and that removing client.yaml (backlog 21) rebuilds the
   owner's archive and restarts it.
7. Routes use the same mechanism: accepts.routes (platform-routes) receives
   route.conf from components with routes:. State this in one or two sentences,
   or mark it explicitly out of scope, so clients do not read as a special case.
8. Name the actual durable locations below the service user's home: persistent
   registrations, import archives in FILES_DIR and the pending record. Say which
   of them are rebuilt from registrations and which an operator must keep, so
   item 3 (backup and recovery) can refer to this text.
9. Runtime claims need evidence. deployment/common.py says Podman imports the
   archives "on every start"; cite existing lab evidence for that and for the
   annotation's behaviour on an existing volume, or mark the statement as
   unverified. Do not describe Podman behaviour that no evidence covers.
10. dev/render-diagrams.sh renders a fixed list of diagrams selected by
    ARCHITECTURE.md headings. Add the new diagram to that list, commit its PNG in
    docs/diagrams/ and link it beside the existing install/build images. If
    rendering is not possible in the agent's environment, say so and leave the
    exact command; do not commit a stale or hand-made image.

Done when a reader can follow the source declarations to the running Identity
container and explain who builds the files, who imports the volume and why no
config.defaults.yaml entry is needed. This task does not establish new runtime
verification evidence or close the outstanding lab work in other items.

## 43. Separate reusable platform tests from demo application tests

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: done and lab-verified: six-scenario matrix `t6-*` CLEAN PASS on `b3f3cf1` (2026-10-19; Oracle Linux 9.8, rootless Podman 5.8.2, SELinux Enforcing, fapolicyd on PROD); `03-unit` ran
`tests/run.py all` on DEV. Earlier status: implemented on main (2026-10-19). `tests/run.py` provides platform,
demo and all groups plus isolated/offline export. Helpers no longer import test
modules, and platform declarations are synthetic, independent of shipped apps
and components. All 403 original declared test methods remain: prior discovery
executed seven imported inherited methods twice (410 executions). Current
inventory is 347 platform + 64 demo = 411 unique tests, including the item 40
version regression. Acceptance's `03-unit` uses the all group; a renamed-product
harness regression compares the complete platform inventory. The synthetic
fixture catalog keeps historical demo IDs; renamed-product and minimal-worker
fixtures provide the arbitrary-name/no-demo evidence.
Independent review reported on 2026-10-19: platform and isolated platform both
347 tests OK; demo 64 tests OK (one envsubst-dependent proxy skip); inventory
411 unique IDs, no duplicates; acceptance harness OK. Pyright, bash syntax and
diff checks passed; two Ruff DTZ007 findings are fixed in the follow-up. Earlier
local GPG setup failures no longer block the reviewed revision. These review
results do not cover later changes or real Podman/systemd, .NET or Python 3.6.

### Problem

tests/ mixes generic deployment tests with tests reading demo application source
and shipped component declarations. For example, test_credential_delivery.py,
test_health.py, test_database.py and test_init_database.py read files under apps/.
The acceptance harness also tests the demo's builds and scenarios. The minimal
worker fixture demonstrates a deployment without apps/, but does not establish
that the platform test suite can run without the demo files.

### Task

1. Inventory test dependencies, including module imports, inherited fixtures,
   shared helpers and source-file reads. Split mixed modules where necessary;
   do not classify a whole module solely from its filename or Secret names.
2. Establish explicit platform and demo test groups using the existing unittest
   conventions, with a documented command for each and one command for all tests.
   Keep reusable fixture helpers independent of demo test modules and files.
   Choose the smallest practical directory/module change; no new test framework.
3. Platform tests must run from a self-contained copy with no apps/ and with the
   shipped demo component tree replaced by declarative test fixtures. Exercise
   the real platform code with external image references and mocked host actions;
   do not silently skip tests when demo files are absent. Retain generic database,
   Secret/template, validation, lifecycle, retry and isolation coverage.
4. Keep application-source assertions, demo build tests and demo integration
   scenarios in the demo group. Retain their coverage in the full repository
   suite. Separate acceptance-harness tests from real Podman/systemd runs in
   commands and reporting; classify harness tests by actual dependencies.
5. Update CI and acceptance test-baseline commands, tests/README.md and relevant
   contributor instructions for the chosen layout. Audit imports and subprocess
   invocations so discovery runs every intended test exactly once and existing
   renamed-product generation still includes all tracked helpers.
6. Document the minimal files and dependencies an organisation should transfer
   to run platform tests offline, without venv being required. Distinguish these
   tests from organisation-specific integration tests of its own images/manifests.

### Known dependencies at `e419a2a`

Recheck with grep when starting; this list is a starting point, not a complete
inventory.

- Eight test modules read apps/: test_bundle, test_credential_delivery,
  test_database, test_health, test_images, test_init_database,
  test_product_changes and test_renamed_product.
- Eighteen test files read the shipped bundles.yaml or components/<demo id>,
  including the shared fixtures catalog_fixture.py and product_fixture.py.
  Replacing the shipped catalog with declarative fixtures is the main work.
- Fifteen modules import from other test modules. product_fixture.py imports
  DeployFixture from test_deploy.py, so a shared fixture lives in a test module.
  Move shared fixtures into helper modules first; a helper must not import a test
  module, and discovery must not run inherited tests twice.
- Item 41's tests are mixed: SecretTemplateTests, the worker lifecycle and the
  ConfigMap tests are platform tests; Identity connection-string coverage is demo.

### Additional requirements

- There is no hosted CI (no .github/workflows). The gates are the commands in
  tests/README.md and the unit step in acceptance/remote.sh (`unit`, run as
  `03-unit` in every lab run). Update those; do not add a hosted CI workflow as
  part of this item.
- acceptance/renamed_product.py copies tracked files (`git ls-files`) and
  rewrites names for the renamed product `shop`. After moving or splitting test
  files, check that the renamed copy still contains and runs the intended
  groups, with the same test counts as the original checkout.
- List the platform suite's runtime requirements: Python 3.6+ and PyYAML (the
  host already needs them), gpg/gpgv and a writable temporary directory for the
  signing tests. A missing requirement fails with a clear message naming it; it
  is never a silent skip. ruff and pyright are contributor checks, not
  requirements on the offline target.
- Coordinate with item 40 (per-component VERSION files): fixtures reading the
  root IDENTITY_VERSION/PLATFORM_VERSION change there too. Item 43 comes first
  in the agreed priority: keep the root files in the new fixtures, and item 40
  then updates them, without supporting both layouts.

### Verification and boundaries

Run the platform suite in isolation without demo files, the demo group in the
complete checkout, and the combined suite; account for test counts so moving
tests cannot hide lost coverage. Run the existing lint/type checks and preserve
host Python 3.6 compatibility. This is test organisation work, not a deploy
runtime refactor or a redesign of the acceptance lab. Report unit/product,
acceptance-harness and actual runtime evidence separately.

Done when an organisation using only external images can run a meaningful,
documented platform suite without apps/ or demo component files, while the full
repository still verifies all demo-specific behaviour.

## 44. Generate optional PFX signing credentials in dev and production

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: implemented (2026-10-19). Matrix `t6-*` on `b3f3cf1` was CLEAN PASS,
but no acceptance step runs the signing/PFX mode; it shows only that the shared
CA path and the demo recipes still work. Verification of the signing mode on a
lab host, of the organisation's external Duende image and of its mount path is
still pending. Do not close this
item until that evidence is recorded. The missing /run/secrets/signing-cert.pfx
reported by the operator motivated the explicit signing mode; the shipped demo
keeps PEM and its existing commands.

`dev/generate-certificates.sh --root DIR --component ID --purpose signing --pfx`
now provisions any valid component ID without demo users or manual directory
moves. The same standalone/stdin invocation supports dev and production roots.
Private password-file validation precedes writes; external PFX/PEM wins over
issuance; exports are verified in private scratch and hard-linked without
clobbering existing files. Only an explicitly declared PFX is delivered through
existing Secrets. No deployment/ code, image, bundle schema or CA renewal is
changed. The helper embeds Python 3.6-compatible code to keep stdin execution
self-contained; existing PEM/CA recipes remain separate for backward compatibility.
See [PFX credentials](docs/PFX-CREDENTIALS.md) for input names, password creation,
Secret/mount examples, failure recovery and the runnable external-image check.

Understandability review: password/path/mode checks -> per-root lock ->
provision (existing PFX, PEM, or issuance) -> verify_pfx -> publish. On an export
failure, temporary files and the lock are removed, existing PEM/password remain,
and retry reuses them. Uncatchable interruptions can leave a stale lock or
partial PEM pair; recovery is explicit, never automatic key replacement.
Deployment still loads a single binary source -> Opaque Secret in 0600 YAML ->
explicit secret.items mapping. Actual UID/HOME/mount and .NET loading remain
organisation-specific runtime checks, not established by local tests.

Local verification (2026-10-19, Python 3.12.14/OpenSSL 3.0.13): final full
product rerun collected 410 tests: 407 passed, 3 GnuPG tests explicitly skipped
only in the invocation after the ordinary run confirmed missing `/tmp` setup
errors. The ordinary run also had two failures in unchanged retry tests; both
passed separately and in the final full rerun (cause not established). After the
last SIGTERM-cleanup change, all 43 certificate/template tests passed, including
16 certificate tests with real OpenSSL. All 195 acceptance-harness tests passed.
Ruff check/format, Pyright (0 errors/warnings), ShellCheck, shell syntax, relative
Markdown links and diff checks pass. Extracted embedded Python was included in
lint/type/static Python 3.6 gates; Python 3.6 was not executed. Real .NET,
Podman/systemd, service-user mount access, SELinux/fapolicyd and OpenSSL 1.1.1
remain unverified for this change; historical lab results are not reused.

### Analysis and recommended scope

Baseline before implementation: dev/generate-certificates.sh issued PEM .crt/.key
pairs, preserves existing complete pairs, refuses partial pairs, and sets umask
077. Its component mode accepts fixed demo names; Identity's branch also creates
demo user passwords. It did not export PKCS#12/PFX. The shipped Identity reads
PEM, so its successful operation does not verify an external PFX-consuming image.
SECRET_FILES can already deliver a PFX as ordinary binary file data; no new
Secret type, renderer, template syntax or deploy lifecycle is needed.

Recommended: add a small, explicit opt-in PFX export to the dev provisioning
helper, reusing retained PEM material. Do not switch the demo to PFX or require
PFX for all Identity servers/apps. This belongs to development credential
provisioning; production continues to accept externally supplied certificates.
Do not add automatic certificate issuance to prepare/install or validation.

Not yet confirmed: the external application's PFX password setting, its required
password policy, UID/file access and exact mount configuration. The reported
file path establishes only that the file is missing; it does not establish that
the resulting certificate or password will be accepted. Resolve these inputs
before implementing the application-specific example. Do not infer them from
the demo's Program.cs or add changes to the external C# image as a prerequisite.

### Task

1. Add an opt-in export step after successful signing PEM issuance/reuse. Use
   OpenSSL's PKCS#12 export and verify compatibility with supported developer
   OpenSSL versions and the consuming .NET runtime. Keep existing invocations,
   PEM paths and certificate identities unchanged when PFX is not requested.
2. Accept an explicit private password-file input; do not put the password in a
   command-line argument, source file or logs. Prefer this bounded file interface
   over an additional interactive/configuration system. Document how the same
   password is supplied through existing Secret delivery to the application's
   actual configuration setting. No silent password generation/change or fallback
   to an empty password; make any supported empty-password mode an explicit,
   separately justified development choice.
3. Support the target component/output path explicitly so my-identity can receive
   signing-cert.pfx directly without generating in identity/ and copying files.
   Keep issuance purpose separate from the chosen component name; do not add a
   hardcoded my-identity branch or rename the demo globally. Choose the smallest
   backward-compatible CLI extension, with validated paths, not a new general
   certificate configuration framework. PFX export must not implicitly create
   demo users for an external application.
4. Preserve existing credentials byte-for-byte on repeated runs. Produce new PFX
   files with mode 0600 under private directories (0700), and prevent publishing
   partially written exports or overwriting an existing output. Verify an
   existing PFX can be opened with the supplied password and corresponds to the
   source certificate/key before reporting success; refuse empty, corrupt,
   mismatched or symlinked outputs safely. Never regenerate signing keys or
   replace an existing PFX/password automatically to repair an error. A missing
   PFX may be regenerated from the retained PEM pair and password; concurrent
   invocations/failure cleanup must preserve existing files.
5. Document a complete example: generation, SECRET_FILES source, explicit
   secret.items key/path, password delivery and a mount that exposes
   /run/secrets/signing-cert.pfx. Check existing /run/secrets mounts so the new
   mount does not hide other credentials. Avoid delivering extra PEM private
   keys or the CA private key when only PFX is needed. Document that PFX passwords
   do not replace host file protection or remove at-rest credential copies.
6. Keep the original dev CA/certificate workflow, offline operation, and host
   Python compatibility intact. No changes to generic deployment modules,
   Duende configuration models, rotation, automatic trust installation or
   production PKI integration belong in this task.

### Operator decisions (2026-10-19)

These decisions replace the dev-only scope and the open password question above.

- **Dev and production.** Production usually issues credentials from the
  organisation's own PKI in the same way as dev; an external certificate must be
  able to override that, though rarely. The same invocation works in both.
  Production keeps using the current script until item 45 makes it a supported
  production tool.
- **Precedence (external files always win).** In the component's
  `credentials/signing/`, the script takes the first case that applies:
  1. `signing-cert.pfx` exists (external or earlier): keep it unchanged; verify
     only that it opens with the password and contains a private key, and, when
     a PEM key/certificate is also present, that they match.
  2. Only a PEM key and certificate exist (external or earlier): export the PFX
     from them.
  3. Nothing exists: issue a key and certificate from the configured CA, then
     export the PFX.
  Overriding means placing files before running the same command; there is no
  separate mode or flag for it.
- **Password.** The organisation's image has the PFX password hardcoded as
  "password" and cannot be changed. The password is read from
  `credentials/signing/pfx-password` (outside git, mode 0600, retained like other
  credentials) in both dev (`build/dev/<component>/`) and production
  (`/var/lib/<product>/<component>/`). It is created once per machine as part of
  credential provisioning. It is not stored in `config/dev.yaml` or any config
  file, and the script has no built-in default password. Missing or invalid
  password files fail clearly.
- **No password delivery to the container.** The application already knows the
  password, so only the PFX is mounted; no `secretKeyRef` or extra Secret file.
- **Delivery.** `SECRET_FILES` in `components/<id>/config.defaults.yaml` points to
  `credentials/signing/...` relative to the component directory, so the same
  entry works in dev and production.
- **Mount path, still to confirm.** The operator believes a subdirectory such as
  `/run/secrets/signing/signing-cert.pfx` is configurable. Confirm whether the
  application's PFX path is also hardcoded. If it is, mount a Secret volume with
  only that key at `/run/secrets`, verify in the lab that nothing else is needed
  there and that host `mounts.conf` entries do not conflict.
- Document that the hardcoded password gives no real protection (item 37).

### Operator findings (2026-10-20)

From the organisation's old docker-compose test file for `identity-server`:

- The only secret is `signing-cert` (host file `./cert/signing-cert-for-test-pfx`)
  with `target: signing-cert.pfx`, so the application reads
  `/run/secrets/signing-cert.pfx`. No other secret has to share `/run/secrets`.
  Whether the path is hardcoded or only a default is still unknown; the compose
  file sets no path in `environment`.
- The secret has `uid: '999'`, `gid: '999'`, `mode: 0400` and the service has no
  `user:`, so the image runs as a non-root container user (expected 999).
- Decision: the requirement is that it works and is secure enough, not a copy
  of compose. Keep the application's non-root user and mount the PFX-only Secret
  at `/run/secrets` with `defaultMode: 0444`. `kube play` has no per-file owner
  or `fsGroup` for Secret volumes, so the earlier `0400` (container root) example
  would be unreadable for UID 999. `0444` is readable only inside this single-app
  container; host protection (service user's private storage) is unchanged, and
  the hardcoded password already makes host file access the real boundary. Do not
  use `runAsUser: 0`. [docs/PFX-CREDENTIALS.md](docs/PFX-CREDENTIALS.md) is updated.
- Lab evidence still required: `id` in the container shows the non-root user,
  `stat` of the mounted file shows its owner/mode, the host `mounts.conf` does not
  conflict, and the application starts, loads the key and issues a real token.
  Readability alone is not proof. Until then the mode choice is unverified.

### Review additions (2026-10-19)

Decisions and facts from the review of this item; they refine the task above.

- **Export command.** Use `openssl pkcs12 -export ... -passout file:<path>
  -keypbe AES-256-CBC -certpbe AES-256-CBC -macalg sha256`. OpenSSL 1.1.1 and
  3.x have different defaults (3DES/RC2 versus AES/PBKDF2); explicit algorithms
  give the same format on every supported developer host. Do not use `-legacy`.
  `file:` keeps the password out of argv and reads only the first line, so the
  password file must hold a single line; refuse anything else. Checked locally
  with OpenSSL 3.0.13: the certificate fingerprint inside the PFX matched the
  PEM, a wrong password gave exit 1 and `umask 077` produced mode 0600.
- **Re-export is not byte-identical.** Exporting the same key and password
  twice gives different bytes (random salt and IV). "Byte-for-byte" retention
  applies to an existing PFX; a regenerated PFX is only equivalent. It changes
  the rendered YAML, so it reaches the container through the normal upgrade
  path; an equal `newer-only` version does not apply it. Document this.
- **Verifying an existing PFX.** Open it with `-passin file:`, compare the
  certificate's SHA-256 fingerprint with the PEM certificate, and compare the
  public key with the PEM key (`openssl pkey -pubout`). Any mismatch, wrong
  password or unreadable file refuses without changing files.
- **Atomic, no-clobber publish.** Write the export to a temporary file in the
  target directory, publish it with `ln` (fails if the target exists) and remove
  the temporary file; a `trap` removes it on failure. Do not use `mv`, which
  overwrites, or rely on `mv -n`, whose behaviour differs between versions.
- **Purpose versus component name.** `generate-certificates.sh` accepts only
  `platform|identity|app1|app2|help`, and the purpose (signing, web, client)
  follows the name. `acceptance/remote.sh` (`demo_credentials`) works around this
  for the renamed product by moving directories. Add the explicit component and
  purpose without changing that workaround in this item; note a possible
  simplification in the backlog. Validate the component name with the deploy ID
  rule (`common.ID`) so it cannot form an unexpected path. `dev/demo-credentials.sh`
  keeps its demo list; the organisation's component calls the script directly.
- **Stdin execution on targets.** The script also runs as the product user via
  `bash -s -- --root DIR ... < generate-certificates.sh` in the lab and on
  targets. Password and PFX paths are relative to `--root` and must not depend
  on the source checkout.
- **No silent skips.** `tests/test_certificates.py` uses `skipUnless(openssl)`.
  Item 43 requires a missing requirement to fail clearly. Treat OpenSSL as a
  required tool for these tests, at least in the lab's `03-unit` step, and do
  not add new tests that skip silently.
- **.NET verification.** Verify with the organisation's image that the app
  loads the PFX with its private key and the supplied password, as the app's
  UID, from a read-only mount, with the container's actual `HOME` (.NET may try
  to write key material; relates to item 36). Record this under pending real
  evidence; it cannot be verified in this repository.

### Tests and completion

Extend tests/test_certificates.py using the existing isolated fixtures and real
OpenSSL where available: opt-in export, default PEM behavior unchanged, target
component/output name independent of identity, PFX certificate/private-key
readability, password-file handling, repeat-run byte retention, permissions,
missing/partial inputs, incorrect password, corrupt/mismatched existing output,
symlink refusal, interrupted export and redacted diagnostics. Add focused
Secret-delivery coverage for binary PFX and the declared file mapping if existing
coverage does not already establish it; do not add application names to generic
platform assertions. Update the relevant dev/PKI instructions and harness tests
only where their invocations change. Coordinate test placement with item 43.

Run the applicable product and harness gates and inspect the end-to-end flow.
Provide a runnable dev verification for the external app (or a clearly scoped
PFX-loading container fixture) checking the exact mount and password consumption;
record actual runtime results separately from certificate/unit tests. The user
must verify their external Identity image, which is not available in this repo.
Done when one documented provisioning invocation places a valid, retained PFX
at the configured component path and the unchanged application can consume it
through existing Secrets, without manual copying or exposed passwords.

## 45. Production PKI from the certificate provisioning tool

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its relevant
contracts and mandatory understandability review alongside this task message.

Status: planned; requested by the operator on 2026-10-19 and split into 45a,
45b and 45c the same day. Production usually issues certificates from the
organisation's own PKI in the same way as dev, with external certificates as a
rare override (item 44's precedence rules). Each part is a separate task with
its own verification; do them in order.

### Problem

`dev/generate-certificates.sh` is a demo tool: the CA is "Demo Development CA",
certificates last 365 days, the script is not in bundles, and README/ARCHITECTURE
state that organisations bring their own certificates. The lab runs it on PROD
only as demo provisioning (`demo_credentials` in `acceptance/remote.sh`).

### 45a. Configurable production CA (small; after item 44)

Status: done and lab-verified: six-scenario matrix `t6-*` CLEAN PASS on `b3f3cf1` (2026-10-19; Oracle Linux 9.8, rootless Podman 5.8.2, SELinux Enforcing, fapolicyd on PROD). The demo recipes in every
scenario create and reuse the CA through the shared `ensure_ca()` path with
default settings; explicit CA options are covered by product tests only.
Earlier status: implemented on main (2026-10-19).
Prefix options `--ca-subject`, `--ca-days` and `--cert-days` are checked before
writes. All modes share `ensure_ca()` in the stdin-compatible embedded tool;
existing CA/credentials remain authoritative when settings change. Five new
real-OpenSSL regressions cover settings/retention/invalid input and relative roots
across explicit signing and both demo recipes. The 16 existing certificate tests
and all five new tests have passed locally with OpenSSL 3.0.13. Python 3.6 and
OpenSSL 1.1.1 execution, real Duende/Podman/systemd, delivery (45b) and renewal
(45c) remain unverified or separate work; old lab runs are not evidence here.

Review follow-up (2026-10-19): explicit --ca-subject conflicting with a retained
CA is refused before new credentials, including repeated PFX calls and demo
modes. Omitted subject keeps reuse; explicit --ca-days reports that it affects
only new CAs. Partial-pair messages now distinguish backup restoration from
confirmed unused orphans after interrupted first issuance; no automatic deletion.
Independent review's green product/harness runs apply to the reviewed revision;
focused verification of this follow-up is recorded separately below.

Follow-up verification (2026-10-19): all 21 platform/demo certificate tests
passed together with real local OpenSSL after the final fixes. They cover
subject mismatch through stdin and the demo entry point, same-subject reuse,
omitted-subject reuse, CA-days notice, private-file retention and partial-pair
recovery messages. The documented Ruff lint/format commands, explicit DTZ007
check, scoped Pyright (zero errors/warnings), ShellCheck, bash syntax, diff
check and static Python 3.6 compatibility passed. Full product/harness suites
were not rerun for this follow-up; independent review's earlier green runs
are recorded under items 40/43. No lab, .NET, Python 3.6 or OpenSSL 1.1.1 run.

Understandability follow-up: check_retained_ca_subject owns the public DN
comparison and runs in the existing preflight before writes. ensure_ca repeats
the subject check before using a CA; provision/publish keep credential ownership
and no-clobber semantics. Mismatch fails without new credentials; retry with
the retained subject or without the option reuses existing material. The larger
embedded-tool/demo issuance consolidation is explicitly assigned to 45b.

Already true and to be kept: the CA lives in `<root>/PKI/private/`, and `--root`
differs per environment (`build/dev` in dev, `/var/lib/<product>` on targets), so
dev and production already have separate CAs. An existing complete CA is kept
and a partial one is refused. Demo component names select issued certificates
only (item 44), not the CA.

1. Make the CA subject and lifetime configurable. Today `/CN=Demo Development CA`
   and `-days 3650` are duplicated across provisioning modes; consolidate
   CA creation while preserving standalone/stdin execution. Keep the current
   values as the demo default.
2. Make the issued certificate lifetime configurable (currently hardcoded `-days 365`
   across provisioning modes).
3. Validate values before any file is written (subject syntax, positive integer
   days); invalid values fail without creating or changing files.
4. Tests in `tests/platform_tests/test_certificates.py` and
   `tests/demo_tests/test_certificates_demo.py` with real OpenSSL: the configured
   subject and lifetimes are used for a new CA and certificates; an existing CA
   is never modified or recreated when settings change; invalid values write
   nothing; existing invocations without settings behave as before.
5. Document where the CA key lives (mode 0600, `PKI/private/`), that it must be
   backed up and protected (items 3 and 37), and that new settings apply only to
   CAs created afterwards. Replacing an existing CA means reissuing every
   certificate and distributing the new CA; that is a separate operation and
   not part of 45a.

Keep the current stdin delivery; no deploy, bundle or lab-scenario changes.

### 45b. Delivery to targets (medium)

1. Deliver the tool in a supported way, for example signed inside the platform
   bundle (item 38) or as a signed tool archive, that works with fapolicyd and
   offline execution; no network or package installs.
2. Update the lab to use the delivered tool instead of copying the script, and
   remove the renamed-product directory workaround in `demo_credentials` if the
   tool supports arbitrary component names (item 44).
3. Keep demo provisioning available for the shipped demo without making demo
   names part of the production tool.

4. Resolve the understandability finding from the 2026-10-19 review: when the
   tool is delivered in a bundle, extract the embedded Python into a dedicated
   module and route demo leaf issuance through the same issuance function.
   Preserve supported offline execution and document how standalone/stdin
   delivery is replaced or retained. Avoid three independent issuance paths;
   do not expand the production tool with hardcoded demo names.

### 45c. Renewal and expiry (medium; after item 39)

1. Renew issued certificates before expiry without silently replacing keys or
   the CA; define when renewal is allowed and how consumers (nginx, Identity,
   app clients) pick up the new certificate through the normal upgrade/restart
   path.
2. Report certificate expiry in `./deploy.sh status` (item 39).
3. Test expiry and renewal with short-lived fixtures, and verify on PROD in the
   lab. Plan it well before the first production certificates expire.

### Out of scope

An online CA, ACME, HSM integration, replacing an existing CA, and rotation of
database passwords (item 2).

Done when (all three parts): production installs can issue, retain, renew and
back up their certificates from a documented per-environment CA with the same
tool, external certificates still override it, and the lab verifies the flow on
PROD.


## 46. Prevent root host preparation from following service-user symlinks

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply its
credential-retention, isolation and compatibility contracts and understandability
review to the privileged host-setup boundary.

Status: done. Implemented on 2026-10-21 from `5f720d1`, with local filesystem and
shell regressions. Separate-UID OL9 Enforcing/fapolicyd verification passed in
lab matrix `t11` clean at `3a54714` (all six scenarios), after lab fixes in
`aafede6`, `a82be32` and `8cebe9f`. See
[implementation, understandability review and verification](acceptance/PREPARE-HOST.md).
Found in the quick Python/Bash security scan of main at
`b3f3cf161999ab83be5d596d4ce222bf81712c7d` on 2026-10-19. A historical sandbox
probe with a separate UID confirmed the ownership takeover on 2026-10-21
(see review additions below); that is not proof of the current fix.

Implementation: `as_service_user` drops numeric UID/GID, supplementary groups and
all capability sets, enables no-new-privileges and wraps both relabel commands.
The Python helper is embedded in `prepare-host.sh` as a here-document and is
passed on stdin under that boundary. A shipped `.py` file would be denied by
fapolicyd before release trust (lab run `h46b-platform`). The helper checks
existing managed paths before creating directories through no-follow directory
descriptors, changes modes through those descriptors and creates the CNI lock
exclusively. Existing locks are never replaced/truncated, including at a
creation race. A failure stops before linger/firewall; there is no root repair.
The `/var/lib` anchor, final home entry, service identity and existing ID ranges
are checked. No compatibility/migration layer was added.

The automatic acceptance flow now runs a disposable separate-account proof on
DEV and planted-link/full-repeat checks after installation on PROD, including
the renamed product. Local harness tests do not replace these real runs. The
earlier task/review text below records the analysis; the shipped mechanism uses
descriptor-based Python preparation instead of GNU `install` and injects races
at descriptor open/chmod boundaries. SELinux probes inject replacement at the
relabel command boundary; they do not instrument an internal libselinux walk.
Review follow-up: the ordinary PROD probe explicitly selects the transferred
`help` bundle, including platform/help-only runs. Shared link-fixture cleanup
covers partial setup failure after rename, retains unexpected replacements and
reports the original backup. Regression coverage includes both findings; the
acceptance harness now has 218 passing tests. The real-host gate later passed (lab matrix `t11` at `3a54714`).

### Finding and evidence

`scripts/prepare-host.sh` runs as root and permits repeated preparation of an
existing service account. Its directory loop runs `install -d -m 0700 -o "$user"`
under that account's writable home (`.local`, `.config` and descendants), without
rejecting symlink components. The subsequent CNI lock creation and SELinux
operations must also be included in the path review.

A compromised service account can prepare a symlink before an administrator
reruns the trusted helper. Privileged directory operations can then follow it
outside the intended tree, potentially handing ownership of a host directory
to the service account. This is a conditional local privilege-escalation risk,
not evidence of unauthenticated remote exploitation.

An isolated probe using the same `install -d` operation confirmed that a symlink
under a synthetic service home redirected a 0755-to-0700 permission change to a
sibling directory. Cross-user ownership change/full privilege escalation was
not reproduced: the sandbox rejected the attempted alternate numeric UID.
Only disposable synthetic paths were used; no production paths were modified.

### Task and verification

1. Trace every privileged write, ownership/mode change and labeling operation
   involving the service home. Refuse symlinks in the affected path components
   before touching their targets, including dangling links and the CNI lock.
   Preserve valid existing rootless storage, user identity and subordinate IDs.
2. Address check/use replacement races as well as static symlinks: a path check
   followed by a root command on a still service-writable pathname is not a
   sufficient boundary. Select a bounded, understandable approach that prevents
   traversal/replacement across privileged operations; document its assumptions.
   Do not recursively chown existing application data or alter targets outside
   the intended service tree as a repair step.
3. Add regressions for a valid fresh setup and repeat, symlinked `.config`,
   `.local`, nested directories and CNI lock. Assert the outside target's
   ownership, mode and contents remain unchanged on refusal, and that later
   privileged commands do not run. Use disposable targets, never real system
   directories. Include a controlled replacement-race regression for the chosen
   mechanism; command stubs alone do not prove filesystem safety.
4. Run relevant product and harness tests plus existing static checks. Verify
   real repeat preparation with separate root/service identities, SELinux and
   fapolicyd in a disposable lab before calling the boundary verified. Keep
   sandbox probes and real-host results separate; update the operator recipe.

### Review additions (2026-10-19)

5. Preferred mechanism: create the service-home directories and the CNI lock as
   the service user (for example `runuser -u "$user" -- install -d -m 0700 ...`
   or `setpriv` with the user's UID/GID and cleared groups), so a symlink can at
   most redirect writes to places the service user may already write. Keep root
   only for operations that need it: `useradd`, subordinate IDs, `semanage`,
   `restorecon`, linger and firewall. A root `openat`/`O_NOFOLLOW` walk from a
   root-held directory descriptor is the alternative if a step must stay root;
   choose one approach and document why it closes the check/use race.
6. Verify `restorecon` semantics on Oracle Linux 9 before relying on it under a
   service-writable tree: whether `-R` follows a symlinked final or intermediate
   component, and what the `-e` exclusion does when `storage` is replaced by a
   link. Relabeling a host path outside the home through a planted link is in
   scope for this item even if ownership is unchanged.
7. State the boundary precisely: `/var/lib/<user>` itself is created by root in
   root-owned `/var/lib` and cannot be replaced by the service user; everything
   beneath it can. The existing home-owner check is kept but is not a symlink
   check for descendants.
8. Malicious lab step on PROD after a normal installation: as the service user
   replace `.config/cni` with a symlink to a disposable root-owned directory, and
   separately plant a dangling symlink at `.config/cni/net.d/cni.lock`; rerun
   `prepare-host.sh` as root. Require refusal (or a service-user-confined effect)
   with the target's owner, mode, SELinux label and contents unchanged. Then
   restore the home and confirm a normal repeat preparation keeps storage,
   container/volume IDs and labels.
9. Operator guidance in README: when a repeat preparation is expected (port
   change, recovery after a failed preparation) and that it must not be rerun
   before inspecting the home if the service account is suspected compromised.

### Review additions (2026-10-21)

Re-checked against main at `ba662ab`: `scripts/prepare-host.sh` is unchanged
since the finding. These points refine the plan above; where they differ, these
win.

10. **Sandbox evidence (not a real-host result).** Disposable paths under
    `/var/tmp`, a disposable system user `probe46`, no SELinux:
    - As root, today's `install -d -m 0700 -o "$user"` on a planted
      `.config -> <outside dir>` changed the root-owned 0755 outside directory to
      `probe46` 0700. Cross-user ownership takeover is therefore reproduced, not
      only the mode change from the first probe. With `/etc/systemd/system` or
      `/etc/profile.d` as the target, this is a root escalation path.
    - The same command run as the service user
      (`setpriv --reuid --regid --clear-groups`) failed with
      `Operation not permitted`, and the outside directory stayed root 0755.
    - CNI lock: a dangling symlink as the final component is not followed. GNU
      `install` unlinks the destination before creating it, so the link was
      replaced by a regular file in the home. A symlinked intermediate directory
      (`net.d -> <outside dir>`) did redirect: root created a `probe46`-owned
      `cni.lock` in the root-owned outside directory. The lab step in point 8
      should therefore plant both a final-component and an intermediate link, and
      expect the final-component case to stay inside the home.
    - A fresh and a repeated preparation run entirely as the service user created
      the same tree, owners and modes as today.
11. **Mechanism: run every operation below `$service_home` as the service user.**
    Introduce one small helper, for example
    `as_service_user() { setpriv --reuid="$user" --regid="$group" --clear-groups -- "$@"; }`,
    and use it for the directory loop and the CNI lock. `--clear-groups` keeps
    root's supplementary groups from being inherited. The intended boundary is
    that pathname replacement cannot confer authority beyond the service user;
    verify the effective authority as required in point 18. `setpriv`
    (util-linux) is preferred over `runuser`
    because it does not open a PAM session; check that it is present in the
    command preflight. Both are RPM-installed, so fapolicyd trusts them.
    Verify that the helper retains the expected SELinux context and that
    pre-created directories get the same labels as today; the OL9 probe is the
    acceptance gate for this assumption. Keep the pre-creation itself. It exists
    so that Podman does not create these directories and the lock with a runtime type (see the comments
    in the script); removing it would reintroduce that labeling defect.
12. **Intended behavior change on repeat.** Root's `install -d` today silently
    repairs the owner and mode of existing subdirectories. As the service user it
    cannot take ownership: an existing directory owned by another user fails
    with `Operation not permitted`, as the probe showed. Turn that into an
    explicit refusal that names the path and tells the operator to inspect it.
    Never `chown` it as a repair (point 2). Document this in the README recipe
    (point 9).
13. **`restorecon` is the remaining root path operation; resolve it first.**
    The remaining operations that take paths are `stat`/`chmod` on
    `$service_home` itself (safe: root owns `/var/lib`, point 7) and the two
    `restorecon` calls. Expected semantics, to be confirmed on Oracle Linux 9
    with a short probe before implementation (point 6):
    - `restorecon -R` walks with `FTS_PHYSICAL`, so links below the starting
      directory are relabeled as links, not followed. The starting directory is
      `$service_home`, which the user cannot replace.
    - For an explicit path, `restorecon` resolves the parent components with
      `realpath` and does not follow the final component. In
      `restorecon "$container_home/storage"`, a symlinked `.local`, `share` or
      `containers` would therefore relabel a host path outside the home, with
      the default label for that host path.
    - It is unknown whether `selinux_restorecon` uses full pathnames during the
      recursive walk (`FTS_NOCHDIR`). If it does, swapping a directory for a link
      during the walk could apply a home/container label to an outside file.
      This is the replacement race in point 2 for labels.

    Preferred resolution to verify: run both `restorecon` calls through the same
    `as_service_user` helper. Do not treat a changed UID or a retained SELinux
    domain alone as proof of safe relabeling: verify the effective credentials,
    capabilities and actual policy behavior. Probe on OL9:
    1. that it relabels a normal home, including the storage directory itself,
       as today;
    2. that nothing outside `storage` is owned by subordinate IDs, since
       relabeling such a file as the service user would fail;
    3. that a planted `.local` link and a mid-walk replacement leave the outside
       target's label unchanged.

    If any of these fail, do not fall back to a component check followed by
    ordinary root `restorecon` on the checked pathname. Even a check using
    `O_NOFOLLOW`/`openat` leaves a replacement race when the later operation
    resolves that pathname again. A root alternative must keep the actual
    operation bound to safely opened objects throughout traversal and relabeling,
    with its own race regression. If no bounded mechanism is verified, leave
    this part explicitly blocked; documenting the race does not close item 46.
14. **Test placement.** The 8 tests in `tests/platform_tests/test_prepare_host.py`
    use stubs and run without root. Keep them, and add a static stub test: with
    `setpriv` and `install` stubbed, every command whose argument is under
    `$service_home` must run through the helper, and no root `install`,
    `chown`, `chmod` (except on the home) or `restorecon` may remain on such a
    path. That is the regression for the mechanism.

    The filesystem proof needs root and a second UID, which `tests/run.py`
    (`03-unit`, no sudo) does not have. Add a disposable root probe in the style
    of `acceptance/database_test.py`, for example
    `acceptance/prepare_host_test.py`, run with `sudo -n` on DEV as an `03-*`
    step. It creates a temporary system user and a temporary home under
    `/var/tmp`, executes the real directory/lock block from the script (extract
    it into a function to make this possible), and removes both afterwards.

    Cases:
    - fresh setup and repeat;
    - `.config` link;
    - `.local` link;
    - nested `.config/cni` link;
    - intermediate `net.d` link;
    - final-component dangling lock link;
    - a root-owned existing subdirectory (refusal).

    For each refusal, assert the outside target's owner, mode and contents are
    unchanged and that the later steps did not run.

    Replacement-race regression: a PATH shim for `install` that, as the service
    user, swaps the next directory for a link to the outside target and then
    executes the real binary. It must leave the target unchanged. This makes the
    race deterministic without timing loops. It must run on Python 3.6 and stay
    within the 03 step's time budget.
15. **Lab acceptance.** Add the malicious step from point 8 as a PROD step after
    the normal installation (before `07-persistent-before`, or as a separate
    focused scenario if it would disturb the persistent comparison). Afterwards
    the existing restart, reboot, persistent-state and upgrade steps serve as the
    normal-repeat check. Compare the outside target's SELinux label with
    `stat -c %C` before and after.
16. **Review guide.** Add items 46 and 54 to the known-gap table in
    `docs/REVIEW_GUIDE.md` now. Mark 46 resolved there only with lab evidence
    from the current change.

### Implementation clarifications (2026-10-21)

These clarify the acceptance boundary after review at `16b2566`; they do not
represent new runtime evidence.

17. **Separate layout checks from the security boundary.** Reject pre-existing
    links in the managed directory chain and at the CNI lock, including dangling
    links, with a clear path-only diagnostic. This is a layout check for those
    paths, not a blanket ban on links in application data. Point 10 describes
    the current GNU `install` behavior, not a requirement to silently replace a
    planted lock link. A link introduced after the check must still be harmless
    to protected outside targets because the operation lacks elevated authority.
    Running as the service user limits authority; it does not by itself confine
    access to the home. Do not claim that all outside paths are inaccessible.
18. **Verify the helper's authority, not just its command line.** In the
    separate-UID probe, record real/effective/saved UID and GID, supplementary
    groups, effective/permitted/ambient capabilities and SELinux context inside
    the helper. Require no root identity, inherited privileged groups or
    capabilities that bypass the intended boundary. For relabeling, test both
    a root-owned non-writable outside target and a disposable root-owned target
    writable by the service user; unchanged ownership alone does not demonstrate
    unchanged labeling. A failure in directory, lock or label preparation must
    stop before linger/firewall and must never trigger a root repair/retry.
19. **Preserve retry behavior without promising rollback.** A failed preparation
    may leave earlier valid setup steps in place; a new invocation must succeed
    after the operator removes the unsafe condition. Test that an existing
    regular CNI lock is not replaced or truncated, including a lock appearing
    between the existence check and creation. On normal repeat, verify the
    storage exclusion and retained container/volume identities as well as
    ownership and labels. Keep all adversarial fixtures disposable and cleanup
    independent of attacker-controlled symlink targets.

Related, but owned by item 54 and out of scope here: the README's
`sudoedit "/var/lib/$product_name/$bundle/config.yaml"`, and root `sha256sum` and
`fapolicyd-cli` on the service-writable release tree. Prefer `sudoedit -u
"$product_name"` there. Do not change these in item 46.

### Done when

No root operation in `prepare-host.sh` follows a symlink or can be redirected
through a service-replaceable path; regressions for static links and the
replacement race pass; the malicious lab step and a normal repeat preparation are
green on real hosts with SELinux Enforcing and fapolicyd. Out of scope: root
operations on unpacked release trees (item 54), credential copies at rest
(item 37) and retained secret permissions (item 47).

## 47. Refuse unsafe permissions on retained generated secrets

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply credential
retention and validation-before-side-effects; coordinate with item 37.

Status: planned; low-priority hardening. Found by the same 2026-10-19 scan at
`b3f3cf1`. Separate from encryption at rest and backup implementation.

### Finding and evidence

`deployment/render.py:generate_secrets` accepts an existing declared generated
file when it is regular and nonempty, then skips the private-mode creation path.
An isolated call retained a synthetic password with mode 0644 beneath a 0755
credential directory. New generated files already use 0600 and new credential
directories use 0700; this finding concerns retained/restored material only.

This is not proof of disclosure in the normal production layout: the service
home's 0700 blocks other local users. Exposure depends on the complete ancestor
permissions and becomes relevant when credentials are restored or staged under
more accessible directories. Do not report 0644 alone as demonstrated disclosure.

### Task and verification

1. Define and enforce an explicit permission/ownership policy for existing
   files declared with `generate`. At minimum refuse group/other access to
   retained generated secrets; specify accepted private modes and ownership.
   Assess ancestor access and document which checks apply to dev, standalone
   fixtures and production. Preserve bytes and valid existing credentials.
2. Fail with a safe, actionable message before install side effects; do not
   regenerate or rotate the secret, print its contents, or silently repair
   ownership. Keep declaration-only `validate` free of credential-content reads
   and host commands; document where permission checks occur in the lifecycle.
3. Add focused tests for safe reuse, 0644/group-readable retained files, the
   selected ownership policy and restored credential directories. Confirm
   refusal preserves bytes and performs no Podman/systemd calls. Include the
   existing-file branch after a competing create where relevant.
4. Keep public certificates and ordinary non-generated VOLUME_FILES outside a
   blanket private-secret policy. This item adds no backup engine or encryption
   dependency. Run focused product tests and the relevant existing checks.


## 48. Validate public hosts and proxy-header trust

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve declarative
components, independent images, shared public settings, offline delivery and
credential-retention contracts; complete the understandability review.

Status: planned; medium severity, high implementation priority after item 46.
Found in the reverse-proxy security assessment of main at `593de60` on
2026-10-19. Static configuration/source evidence; no demonstrated authentication
bypass or end-to-end exploit. Must be addressed before wider production exposure.

### Finding

The sole server in `components/platform/manifests/20-proxy-config.yaml` has
`server_name _`, which does not reject unexpected Host headers. The shipped
Identity and Todo backend routes pass `$http_host` upstream. Identity's route
sets X-Forwarded-Proto and X-Forwarded-For, but does not clear/replace a supplied
X-Forwarded-Host. Nginx normally forwards other request headers unchanged.

`apps/identity/Program.cs` enables XForwardedHost and clears KnownNetworks and
KnownProxies without an allowed-host restriction. A supplied X-Forwarded-Host
can therefore influence the request host used by the demo middleware. IssuerUri
is pinned to PUBLIC_ORIGIN, but that alone is not proof that every generated URL
or redirect is safe. A private shared container network and absence of host
ports on backend pods do not establish that nginx is their only possible caller.
The organisation's external Identity image has not been inspected or tested.

### Task and verification

1. Derive the permitted public authority from the existing PUBLIC_ORIGIN model;
   reject unexpected Host values before proxying. Merely replacing `_` with a
   configured server_name does not reject requests handled by the default server.
   Define handling of ports, supported IP/IPv6 origins and missing/malformed Host
   without hardcoding demo names. Keep the loopback health probe functional with
   an intentional Host policy; do not add an unrestricted backend bypass.
2. Define the minimal forwarded-header contract for each hop. Clear or replace
   client-controlled X-Forwarded-Host, X-Forwarded-Proto, X-Forwarded-For and other
   forwarded metadata actually consumed by supported apps. Audit all shipped
   routes and the custom-route documentation. Preserve legitimate authentication
   headers, cookies and external-app compatibility.
3. Implement header rules in each relevant location or a shared include used
   there: nginx does not inherit server-level proxy_set_header directives when
   a location declares its own. Add a regression for this inheritance trap.
4. Align the demo Identity middleware with that contract: consume only required
   forwarded fields, restrict accepted hosts and avoid unrestricted proxy trust
   justified solely by private networking. Choose a rootless-compatible trust
   mechanism; do not hardcode transient pod IPs. Document external applications'
   responsibilities and the limits of a shared network/origin trust boundary.
5. Add focused config tests and actual nginx/backend lab probes using synthetic
   Host and forwarded-header values. Check legitimate OIDC discovery/login,
   callback and generated URL authorities; unexpected Host rejection; spoofed
   X-Forwarded-Host and client-IP handling; renamed product; and health checks.
   Verify the real app contract without claiming an unseen external image is
   covered. Current five proxy tests exercise rendering/startup, not this boundary.
6. Run relevant product/harness and static checks. Keep current TLS versions,
   read-only mounts, credential privacy and scoped component lifecycle unchanged.

References:
- [nginx request processing](https://nginx.org/en/docs/http/request_processing.html)
- [nginx proxy header handling and inheritance](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header)
- [ASP.NET Core forwarded headers and allowed hosts](https://learn.microsoft.com/en-us/aspnet/core/host-and-deploy/proxy-load-balancer?view=aspnetcore-8.0)

## 49. Define safe proxy logging for authentication and API requests

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Coordinate with
credential retention and item 37; this is logging protection, not backup work.

Status: planned; medium severity, after item 48. Identified by the 2026-10-19
reverse-proxy assessment at `593de60`. No actual credential leak was reproduced
in the product's nginx container; verify the deployed image/configuration first.

### Finding

Shipped Identity/auth routes disable access_log, which reduces normal-path
exposure. Other routes inherit the image's access-log configuration and have no
explicit safe log format. Nginx's standard combined access format includes the
request line and Referer. Its HTTP error-log context can include the request
line and upstream URL independently of access_log. An upstream failure during a
callback can therefore expose sensitive query parameters despite access_log off.
This does not establish that reusable tokens/passwords have actually leaked or
that logged authorization codes are redeemable without PKCE/client credentials.

### Task and verification

1. Inspect the actual supported stock nginx image's nginx -T output, access/error
   formats and stdout/stderr/journal routing. Reproduce with synthetic markers
   only: normal callback, upstream unavailable/timeout, malformed request and
   API query/Referer cases. Never put real codes, tokens or passwords in evidence.
2. Define useful access logging that excludes sensitive query/Referer fields by
   default, retaining safe path/status/timing information where appropriate.
   Keep the public proxy generic across arbitrary component routes.
3. Handle error logs separately: changing log_format or access_log does not
   sanitize error_log. Choose a practical policy supported by the pinned nginx
   version and delivery model; do not indiscriminately disable all error logging.
   If residual sensitive error context cannot be removed without losing required
   diagnostics, document it and bound log access, retention and export. Do not
   claim unconditional secret-free logs while that exposure remains.
4. Add actual nginx regression scenarios checking synthetic marker presence or
   absence against the chosen policy, including failure paths and inherited
   location configuration. Confirm safe diagnostics remain available. Run the
   relevant product/harness checks and document unexecuted runtime scenarios.

References:
- [nginx access-log formats](https://nginx.org/en/docs/http/ngx_http_log_module.html#log_format)
- [nginx development guide: HTTP error-log request context](https://nginx.org/en/docs/dev/development_guide.html)

## 50. Define configurable production proxy limits and security headers

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve independent
external applications and keep product policy declarative. Coordinate container
user/capability/filesystem hardening with item 36 instead of duplicating it here.

Status: planned; lower-priority production hardening, alongside item 36. Found
in the 2026-10-19 assessment at `593de60`; exposure depends on the real bind
address and surrounding controls. The shipped default binds only 127.0.0.1.

### Scope and boundaries

- The shipped proxy has no configured limit_req or limit_conn policy. The demo
  Identity login has no implemented account lockout/throttling. This is not a
  finding about the organisation's external Identity image. Determine which
  controls that application already provides before duplicating them.
- The proxy has no common HSTS, Referrer-Policy or nosniff policy; the Todo
  backend sets nosniff itself, but the static frontends do not. Existing
  application/framework response headers still need runtime inspection.
- Retain the good defaults: TLS 1.2/1.3, 16k request-body limit, no implicit public
  backend ports, read-only route/config/TLS mounts and private TLS-key delivery.
  Absence of custom timeout directives does not mean nginx has no default timeouts.

### Task and verification

1. Define optional production request/connection limits, especially for login
   and token endpoints. Account for legitimate OIDC flows, clients sharing an IP,
   correct client-IP trust from item 48, and load-test/health traffic. Keep
   per-account brute-force defenses and lockout under the application's control;
   rate limiting alone is not an authentication security guarantee. Avoid a
   hardcoded Identity component/path dependency in generic deployment code.
2. Provide a documented compatible response-header baseline: nosniff and an
   appropriate Referrer-Policy; configurable HSTS for production HTTPS after
   trust/deployment validation. Do not force HSTS preload or includeSubDomains
   onto dev hosts or unrelated services. Evaluate CSP/frame protection per app;
   a blanket policy must not silently break OIDC frames, inline scripts or
   supported external applications. Check nginx header inheritance and error
   responses, not just the successful root page.
3. Add focused configuration tests and runnable lab checks for intended 429
   behavior, legitimate login/client traffic, spoof-resistant limiting, headers
   on representative success/error responses and unchanged health checks. Test
   renamed components and document defaults, overrides and ownership of each
   control. Real limits must be chosen from the product's exposure/load needs.
4. No new WAF, online service, custom proxy image or mandatory security framework
   is required. Run relevant product/harness/static checks and report actual
   nginx/.NET verification separately from template assertions.


## 51. Add an optional Grafana and Loki logging demo

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve declarative
components, independent images, isolated offline bundles, credential retention,
scoped lifecycle and compatibility. Coordinate log privacy with items 37 and 49.

Status: planned; low priority, requested on 2026-10-19. Medium-sized demo
extension, not a prerequisite for core deployment, backup or DR. This task is
planning only; no Grafana/Loki integration or rootless collection is verified.

### First delivery

Add optional self-hosted Grafana OSS and Loki OSS, with a maintained collector
(for example Grafana Alloy), to demonstrate searchable PostgreSQL logs. Start
with errors and slow queries; make full statement logging an explicit diagnostic
choice. Keep ordinary deployment fully usable without the logging components.
Application-wide instrumentation, OIDC login, advanced dashboards, metrics and
traces are separate later scope, not prerequisites for this delivery. Item 52
is the planned metrics follow-up and reuses this Grafana instance.

### Task

1. First prove a minimal collection path from the actual rootless Podman setup:
   determine the log driver, journal/file locations, permissions and restart
   behavior. Compare service-user journal ingestion with a suitably scoped file
   path before choosing the collector configuration. Do not require a rootful
   daemon, expose a writable container-engine socket, or grant access to unrelated
   host/users' logs. Record any required narrowly scoped host preparation.
2. Use existing component/catalog/bundle declarations, stock version-pinned OSS
   images, persistent volumes and config/Secret delivery. Provision Loki as a
   Grafana data source and one useful saved view/dashboard automatically.
   Aim to leave generic deployment Python/Bash unchanged; justify any concrete
   platform gap rather than embedding Grafana/Loki names in deploy code.
3. Define PostgreSQL logging modes declaratively. Default to errors and a
   documented slow-query threshold; provide opt-in full statement logging for
   demo/troubleshooting. Explain that statement logging does not record result
   sets or guarantee an audit trail of every attempted statement. Preserve
   database data/passwords when changing logging settings.
4. Keep SQL text and parameter values out of Loki labels. Use bounded labels
   such as component/database, with SQL in log content or structured metadata.
   Avoid user IDs, request IDs and arbitrary query text as indexed stream labels.
   Document that SQL literals/bind values can disclose personal data or secrets;
   parameter-log suppression does not redact literals written into SQL text.
   Use synthetic data for examples and test evidence. Logging failures must not
   become a prerequisite for the application's database operations.
5. Configure Grafana authentication through existing private credential handling;
   do not enable anonymous public log access or use committed/default passwords.
   Keep Loki ingestion/query endpoints internal unless explicitly secured.
   Integrate the UI with the reverse-proxy contract from item 48; define the
   supported base path or host route and verify it in the browser. OIDC is not
   required in this first delivery.
6. Bound retention/disk use in both local source logs and Loki. Define rotation,
   collector checkpoints, persistence, behavior when Loki is unavailable and
   recovery after restart, plus scoped uninstall/data-retention behavior. Do not
   claim exactly-once/lossless delivery without evidence. Keep database volumes
   and unrelated component state untouched during cleanup.
7. Package all required images, configuration and any required plugins for
   offline installation; prefer built-in functionality without extra plugins.
   Select the OSS editions and record their licences/distribution requirements.
   Ensure operation does not require Grafana Cloud, online plugin downloads or
   update/usage-reporting connectivity. Do not add new host Python dependencies.

### Verification and delivery

Add appropriate product/config tests and runnable real Podman/systemd acceptance
checks: install without logging; enable it; emit synthetic error, slow and opt-in
full-SQL events; find them through Loki/Grafana with correct source labels; check
authentication; restart collector/Loki; verify persistence and bounded retention;
uninstall logging without touching application/database data. Verify the offline
bundle and rootless/SELinux/fapolicyd permissions rather than relying on a Docker
quickstart. Report template/unit, harness and real-runtime evidence separately.
Run relevant existing static checks and complete the understandability review.
Document setup, logging modes, resource requirements, privacy limits and the
optional nature of the demo. Do not introduce a general observability framework.


## 52. Add optional Prometheus metrics after the logging demo

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve declarative
components, independent external images, offline delivery, scoped lifecycle and
rootless/SELinux/fapolicyd compatibility. Build on item 51's optional Grafana UI.

Status: planned; low priority, requested on 2026-10-19. Schedule immediately
following item 51 in the observability work, without blocking core deployment,
backup or DR. No exporter, application instrumentation or real metric collection
has been verified in this repository.

### Scope

Use Prometheus OSS for numeric time series, Loki for logs and the same Grafana
instance for visualization. Demonstrate CPU/memory per container and aggregated
by pod/component, plus backend HTTP request count/rate, duration and errors.
Provide an explicit extension path for GraphQL-specific operation/error metrics.
No Grafana Cloud or paid product is required; record licences for the selected
stock images and exporter. Distributed tracing and a general observability
framework are out of scope.

### Task

1. Prove a collection path on the supported rootless Podman/cgroup setup using a
   maintained Podman exporter (evaluate containers/prometheus-podman-exporter)
   or another narrow source. Verify actual CPU/memory availability, permissions,
   container identity and restart behavior before selecting the delivery model.
   Prefer collection without a container-engine socket where supported. A
   read-only bind mount of a Podman socket does not make its API read-only;
   assess the privileges of the actual interface. Do not enable a rootful daemon,
   privileged collector or access to other service accounts as a shortcut.
2. Add optional declarative Prometheus/exporter components and persistent storage
   using the existing bundle/config model. Reuse Grafana and provision the data
   source plus a small dashboard. Keep scrape/query endpoints internal or
   explicitly authenticated, bound retention/disk usage and support fully
   offline image/config delivery. Avoid new host Python dependencies or hardcoded
   component lists in generic deployment code; justify any needed host integration.
3. Display container CPU rate and memory bytes with stable pod/component labels.
   Define CPU percentage denominators, memory semantics and aggregation clearly;
   handle multiple containers and the infra container without double-counting.
   Do not sum percentages with incompatible denominators or show missing metrics
   as healthy zeroes. Document which measurements are unavailable on a host.
4. Export HTTP metrics from a representative backend using supported application
   instrumentation (for .NET, evaluate built-in HTTP meters/OpenTelemetry), or
   explicit proxy metrics if appropriate. Show requests per second, cumulative
   count, latency and HTTP error rates. Adding Prometheus alone does not
   instrument apps; document exactly what external images must expose and how
   scraping/authentication is configured. Avoid counting the same hop twice.
5. Distinguish HTTP requests to a GraphQL endpoint from GraphQL operation counts
   and execution errors. HTTP 200 does not imply GraphQL success; batching and
   subscriptions also need explicit counting semantics if supported. For detailed
   GraphQL metrics, document/instrument the actual framework or use a focused
   representative fixture; do not add an unrelated GraphQL API to the Todo demo.
   Bound any operation-name labels; never label metrics with raw queries,
   variables, user/request IDs, tokens or other unbounded/sensitive input.
6. Make instrumentation and collection optional. Missing telemetry must not
   prevent application startup, database operations or ordinary install/uninstall.
   Preserve existing data/credentials and item 51's log behavior. Document counter
   resets and sampling gaps; operational monitoring is not an exact billing or
   security-audit ledger.

### Verification and delivery

Add focused product/config tests and runnable lab checks: metrics-disabled
installation; enable collection; apply controlled CPU/memory load and locate the
correct container/pod series; emit synthetic requests and inspect counts/rates,
latency and error classifications; exercise GraphQL HTTP-200 execution errors
where that integration is implemented; restart apps/exporter/Prometheus and
verify identity, reset handling and persistence; uninstall metrics without
removing app data or breaking logging. Verify rootless permissions and actual
Podman/systemd/SELinux/fapolicyd behavior, not only dashboard JSON. Run relevant
harness/static checks, complete the understandability review and report unit,
harness and real-runtime evidence separately. Document integration steps,
resource cost and the remaining external-app instrumentation requirements.


## 53. Upgrade app1 with an actually changed application image

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve isolated
offline bundles, independent images, credential retention, database safety and
scoped lifecycle.

Status: planned; requested on 2026-10-19. A focused extension of the existing
acceptance flow. After item 57, the app1 upgrade changes `components/app1/VERSION`
and reference SQL in an isolated checkout (`acceptance/seed_upgrade.py`), then
rebuilds its bundle using unchanged application images. Extend that builder and
its exact changed-file check when implementing this item. Help and Identity have
separate upgrade scenarios with changed content/code and rebuilt images; they
provide an existing pattern to reuse, but do not prove this app1 path.

### Task

1. Extend the existing app1 upgrade in both full acceptance scenarios (app1-first
   and app2-first), rather than adding another complete VM installation. In an
   isolated build checkout, make a small deterministic change to an observable
   app1 backend response, build a new image with a distinct release tag, update
   the relevant manifest image references and bump `components/app1/VERSION`.
   Do not overwrite published image tags or modify the operator's checkout.
2. Build and transfer only the app1 offline bundle and its required verification
   files to the already installed PROD host. Include the new image in the
   archive; do not preload it on PROD or transfer sibling bundles as a shortcut.
   Keep network image pulls disabled. Reuse the established help/Identity build
   helpers where that keeps the flow simple and avoids duplicate shell logic.
3. After installation, assert both the new backend response through the existing
   public route and the running backend's expected image ID. Bundle version and
   health alone are insufficient evidence that the new application is running.
4. Retain existing E2E and persistence assertions: previously created application
   data remains readable, config/credentials/certificates remain unchanged and
   app1 stays functional. Keep route/client declarations unchanged in this
   scenario, so platform, Identity, app2 and help must retain their running
   processes, versions, state, trust entries and shared network identity using
   the existing sibling checks. App1 itself is expected to restart.
5. Add focused harness regression coverage for the changed-image build/transfer
   wiring and assertions. Demonstrate that the checks reject an old backend
   response or wrong running image; avoid assertions that only repeat a new tag
   string. Update acceptance documentation and keep added build time modest.

### Verification and delivery

Run relevant acceptance-harness and static checks, then the real app1-first and
app2-first scenarios on supported rootless Podman/systemd with SELinux and
fapolicyd. Report harness results separately from real-runtime results; until
those lab runs pass, record the scenario as implemented but unverified. This
item covers a compatible application-image upgrade, not database schema
migration, zero-downtime deployment or automatic rollback. Complete the
understandability review of build, transfer, install and observable evidence.

## 54. Keep root release verification and trust off service-writable paths

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Apply the
signed-bundle, isolation and fapolicyd contracts to the operator's privileged
release steps; coordinate with items 38 and 46.

Status: implementation delivered on branch `feature/protected-releases`, based on
`a37f4e4`; implementation and local regressions delivered, merged to `main` with
item 64; six-scenario OL9 matrix CLEAN PASS on `5b8ab69`. Open: actual Python 3.6
and a non-baseline integrity strategy.
Coordinated with urgent item 64; not marked resolved. Found in the item 46 review on 2026-10-19. Analysis updated on
2026-10-22 against `07f8d56`: three local reproductions confirm gaps in release
verification/trust wiring. That analysis predates this implementation;
current-change real-host verification remains pending.

Implementation: shared `scripts/release.py` authenticates a protected snapshot,
strictly validates/extracts archives and publishes immutable root-owned releases
under `/opt/<product>/releases`, with protected provenance and exact live
size/SHA256 trust checks. README and the harness share this helper; independently
authenticated bootstrap, service-user config editing, scoped retirement after
health/e2e, resumable retirement cleanup and separate-UID lab probes are documented in
[PROTECTED-RELEASES.md](acceptance/PROTECTED-RELEASES.md). No old-layout migration
or global integrity-policy changes are included. Current dev/lab installations
may be discarded; after the first real customer installation, incompatible
changes require an explicit migration preserving customer data and credentials.
Initial local results (2026-10-22): 50 focused and
234 harness tests passed; isolated platform suite ran 403 tests with 399 passes,
three unchanged gpg-agent fixture failures and one unchanged `/proc/self/fd/0`
error. Static checks and understandability review passed; real OL9 matrix remains
required before resolution. The original analysis and task
below remain the review baseline, not claims of current runtime verification.

Review follow-up (2026-10-23): mandatory production signatures and pinned-key-only
publication; SELinux relabel-compatible device/inode/mtime bindings (ctime excluded);
explicit removal of obsolete service-writable release trust on disposable hosts;
cache-tolerant script inventory test; step-scoped sanitized diagnostics and
`publish-release` harness naming. Migration after the first customer is a future requirement,
not a compatibility framework to implement before the first customer installation.
Follow-up checks: 21 focused tests and 237 harness tests passed (also without
`-B`); isolated platform suite ran 410 tests, with 406 passes and the same three
gpg-agent fixture failures plus one `/proc/self/fd/0` error in this environment.
Scoped Ruff plus Bash/Pyright/Vermin checks passed; the full documented Ruff gate
was not green (correction below). See the dated verification report for
regression scope and understandability recheck. Current-change lab verification
remains pending.

Lint correction and probe hardening (2026-10-23): previous Ruff claims used a
limited rule selection/target version, not the documented full commands. Item 54
files now pass those lint/format settings; full lint still reports 12 findings in
three unchanged item 61 Secret test files. Full formatting passes (134 files).
The lab probe now forces tmp_t on one deployment file and verifies restoration;
the negative signature probe requires a typed gpgv rejection, never any generic
ReleaseError. Current-change lab coverage is still pending. The operator reports
410/410 platform and 237/237 harness passes at `7bb05dd`. Current follow-up
checks: 21 release and 239 harness tests passed; Pyright 0 errors/0 warnings and
Vermin Python 3.6 compatibility passed. Real OL9 verification remains pending.

First supplied real run (2026-10-23): `release54-20261023-055311-app1`
at `7bb05dd` passed component installation/health and the then-current release
safety probe, but was NOT CLEAN at `07-registry-offline`: fapolicyd denied the
unprivileged checksum reader access to extracted `scripts/release.py`. The data
fixture now checks the full inventory from compressed tar streams and extracts
only image data. Regression checks modified/unlisted/missing payload refusal
before Podman loading; current lab rerun and full matrix remain required. See
[the dated verification report](acceptance/PROTECTED-RELEASES.md) for exact scope.

Coordination (2026-10-23): [item 64](#64-support-new-rootless-installations-outside-the-login-home)
requires an existing login user and product files under a separate root-owned
`/var/lib/<product>` anchor. Reconcile the final release path with that item;
preserve this item's protected publication/trust boundary and shared helper.
Do not assume product name equals user name or that the installation root is
also the registered user home.

### Problem

The README operator recipe unpacks a release as the service user into
`/var/lib/<product>/releases`, then runs privileged steps on that
service-writable tree: `sudo ... sha256sum -c checksums.sha256` and
`sudo fapolicyd-cli --file add "$release/deployment/"`. A compromised service
account can replace files between the checksum and the trust step (check/use
race), so root may trust content that was never verified. A race is not required:
the account can also change the package and its local checksum list before the
operator starts. Signing the original archive does not authenticate an existing,
service-writable extraction of it.

`prepare_release()` in `acceptance/remote.sh` verifies the incoming archive but
skips extraction when the release directory already exists. Root then reads
that directory's own `checksums.sha256` and registers all files in `deployment/`.
`sha256sum -c` does not reject additional files absent from the list. The current
`wait_trust` derives its expected file set from the live directory and checks
paths and record syntax, without comparing size/hash with authenticated content.

With fapolicyd `integrity = none`, the trust decision has no content-integrity
check. Files must therefore remain protected after enrollment as well as before
it. `sudoedit` of `config.yaml` currently targets root in the README despite the
config living in the service-owned data directory; use service-user authority.
These findings establish a broken verification/trust boundary, not proof of
direct root code execution.

### Analysis and local evidence (2026-10-22)

The actual `prepare_release` and `wait_trust` shell functions were exercised
with disposable files outside the checkout. Hashing, file enumeration and the
archive were real. The signature step was simulated by checking a fixed digest
of the original archive; fapolicyd enrollment/database output and sudo identity
changes were simulated. This tests binding to the authenticated input, not
OpenPGP, separate-UID enforcement or the real daemon.

| Reproduction | Observed result |
| --- | --- |
| Replace a package file and rewrite the extracted checksum list before invoking `prepare_release` | Exit 0; the changed file was passed to simulated trust enrollment while the original archive remained unchanged |
| Add `deployment/extra.py`, absent from both the original archive and its checksum list | Exit 0; the extra file was included in simulated trust enrollment |
| Supply a live trust record with the expected path but arbitrary size and a syntactically valid unrelated hash | `wait_trust` returned success |

Nine existing harness tests for trust waiting, release retry, README parity,
upgrade ordering and retention of old trust on failure passed. Those tests do
not cover the three gaps above. No new real Podman/systemd/SELinux/fapolicyd run
was performed for this analysis; item 46's successful lab matrix does not verify
item 54.

Another boundary to include: the harness's `prepare-host` action checks only
the archive checksum before extracting and running its script as root. Unlike
the README recipe, it does not call `gpgv` there. Require signature verification
before the first privileged execution of bundle code, not only later in
`prepare_release`. Review other archive consumers such as `unpack` and the
separate registry fixture according to whether they execute code or import data.

### Chosen direction and scope

Use a final root-owned release tree outside the service home, for example
`/opt/<product>/releases/<product>-<component>-<version>/`. The service user may
read/traverse it but must not modify files, add entries or replace any ancestor.
Config, credentials, installed metadata, import archives, Quadlets and Podman
storage remain service-owned under `/var/lib/<product>` and its runtime directory.

Root ownership of a `releases` directory under the service-owned home is not
enough: the service user can rename that directory entry and replace it because
it controls the parent. Check the entire trusted anchor chain. A protected
verification copy alone is also insufficient if trust or execution still uses
a different, service-writable final copy. Do not recursively chown an existing
service-owned release tree as the repair mechanism.

The existing production code already separates these paths: `common.ROOT`
locates release inputs, `catalog.component_paths` locates persistent output,
and `install_components` stages under `XDG_RUNTIME_DIR`. The wrapper uses
`python3 -B`. This suggests limited deploy-engine changes, but read-only release
operation must be tested for init-config, validate, install, retry, upgrade and
uninstall, including `component_file` inputs and standalone fixtures. Dev
`prepare` deliberately writes source build output and keeps its existing role.

Prefer one small shared release helper used by the operator recipe and the
acceptance harness. It should own staging, verification, publication and trust
ordering explicitly. Keep the existing deploy lifecycle and pending-operation
model; a second generic transaction framework is unnecessary. Existing
dev/lab installations may currently be discarded: no migration, old-layout
aliases or compatibility layer is required before the first real customer installation. Normal repeated operations and data retention still apply.

### Task

1. Trace every root operation on release and data paths in the README recipe,
   `acceptance/remote.sh` and any helper, and classify which paths the service
   user can write or replace.
2. Implement the protected final layout above, with service-readable files and
   no service write permission through modes or ACLs. Validate product/component
   identifiers, version and all ancestor directories before privileged writes.
   Keep private persistent state out of the release and out of fapolicyd trust.
3. Stage the archive in a fresh protected area, then verify that exact snapshot
   against a separately provisioned trusted keyring. Do not verify one pathname
   and later extract a replaceable copy. Verify the signature before unpacking
   or executing archive-provided setup code. Document how the release helper
   itself is initially obtained and authenticated; an unverified helper cannot
   establish its own trust. Preserve item 46's fapolicyd lesson: opening a new
   untrusted Python helper file can fail before enrollment. Keep bootstrap
   execution compatible with the actual OL9 policy and Python 3.6.
4. Validate archive members before extraction: expected single top directory,
   relative confined paths, no duplicate/ambiguous destinations, symbolic or hard
   links, devices, FIFOs or other special files. Reject unsafe names and metadata;
   establish explicit ownership/modes rather than accepting service-writable or
   privileged modes from the tar. Extract into a new empty protected directory,
   never over an existing release. Validate descriptor identity against the
   requested product/component/version and require an exact authenticated file
   inventory, including refusal of unlisted extra files.
5. Publish the complete verified tree at its final path before enrolling that
   path. Publication must not overwrite an existing release or expose a partial
   extraction. Retain protected provenance sufficient to distinguish the exact
   authenticated archive and file set. A repeated call for the same content may
   resume trust setup; the same product/component/version with different content
   must fail. Refuse unexpected existing ownership/content rather than silently
   repairing it. Define behavior for concurrent publication and interrupted
   staging/publication/trust updates; preserve a previously usable release.
6. Trust only the verified `deployment/` inventory. Update `wait_trust` to compare
   expected paths, sizes and hashes with the authenticated inventory, not a
   service-controlled directory listing. Preserve bounded polling, scoped trust
   files, duplicate-add diagnostics and explicit failures. Confirm OL9 handling
   of initial/intermediate/final symlinks and special files; the helper's own
   checks and protected paths must make safety independent of CLI traversal
   behavior.
7. Document the integrity policy explicitly. `size` is not protection against
   deliberate same-size replacement. `sha256` is additional content verification,
   not a substitute for verifying the bytes before enrollment or protecting the
   final release. Decide whether the protected layout supports the existing
   `none` baseline or requires `sha256`; test any stronger setting with startup,
   upgrades and `wait_trust`. Do not silently change global host policy. Warn or
   refuse settings incompatible with the documented design.
8. Use `sudoedit -u "$product_name"` consistently for service-owned config,
   including the README's missing-config-key recovery instructions. Run deploy
   and ordinary data operations as the service user. Keep root release retirement
   scoped to validated protected paths; update old-release deletion, trust removal,
   final host removal and all harness release-path assumptions. Retain old trust
   and release files until install, health and required application checks pass;
   preserve sibling releases, trust and persistent data.
9. Add regressions for the three reproductions, signature failure before host
   setup, archive/link/special-file rejection, protected ancestors and final
   ownership/modes, immutable-version conflicts, exact live trust records and
   interrupted/repeated operations. Verify the production lifecycle against a
   service-readable but nonwritable release. Include renamed products and the
   platform/help-only scenario without assuming app1 is present.
10. Add separate-UID malicious OL9 lab probes: attempt replacement before/after
    verification and after enrollment, addition of unlisted files, ancestor
    replacement and symlink insertion. Require protected writes to fail, no
    unauthenticated trust enrollment and no execution of substituted package
    content through the tested file-based launch path. Do not generalize this to
    a claim that a service user cannot execute arbitrary code at all. Record
    exact package versions, SELinux/fapolicyd settings and outside-target state;
    handle expected negative-probe audit evidence explicitly without broadly
    suppressing unrelated denials. Run the full six-scenario acceptance matrix.

### Sources and remaining host questions

- [Upstream fapolicyd integrity documentation](https://github.com/linux-application-whitelisting/fapolicyd/blob/main/README.md):
  size checking is intended for accidental overwrites; SHA256 compares content
  with the stored digest. Neither authenticates an attacker-controlled initial
  enrollment.
- [fapolicyd release notes](https://github.com/linux-application-whitelisting/fapolicyd/releases):
  version 1.4.5 explicitly mentions reporting skipped symlinks. Do not assume all
  symlinks are followed; test the installed OL9 build and path positions above.
- [GNU tar security guidance](https://www.gnu.org/software/tar/manual/html_section/Security.html):
  use a new empty extraction directory protected from untrusted modification.

Understandability review: the authoritative input should be the authenticated
archive snapshot; the protected published release is its durable representation.
The shared helper decides and performs privileged release/trust work, while deploy
owns service-user configuration and lifecycle state. On success, publish, enroll,
wait and deploy in that order. After failure, discard incomplete private staging
or resume an already verified identical release; never reinterpret a writable
directory as verified just because it exists. Validate this flow in tests and
document the remaining real-host assumptions before declaring completion.

### Done when

No root verification, trust or config-edit step operates on a path the service
user can replace. Authenticated content, the complete published file set and
live trust records agree, and the service user cannot change the final release
or its ancestors. Bootstrap signature verification, failure/retry behavior and
retirement are covered by the shared helper and consistent operator instructions.
Regressions and malicious lab probes pass with SELinux Enforcing and fapolicyd;
normal install, retry, upgrade and uninstall preserve credentials, data and
sibling isolation in the six-scenario matrix. Update the review guide and record
current-change lab evidence before marking this item resolved.


## 55. Add an explicit component-scoped dev reset

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve database
safety, declarative component names, scoped lifecycle, credential retention and
offline/rootless operation. Coordinate recovery documentation with item 3.

Status: planned; requested on 2026-10-20 after a real dev startup was refused
because `sts-db-data` existed while its database password file was missing.
Manual removal of that disposable volume allowed startup. The reset command
below is proposed functionality, not implemented behavior.

Scope update 2026-10-22: the operator also requests one simple way to delete all
Secrets and volumes of the dev installation. Add the explicit whole-dev mode
below alongside the component mode; no reset command exists yet.

### Why

An existing database volume may contain valuable data. Generating a replacement
password file does not change the database's initialized password. Consequently,
ordinary `dev/dev.sh up` must continue to refuse a missing-password/existing-volume
combination, with recovery guidance; it must never silently delete or reinitialize
the database. For disposable dev installations, provide an explicit alternative
to manually discovering containers, volumes and retained credential copies.

### Proposed command and task

```sh
./dev/dev.sh reset sts --delete-data
```

1. Require a catalog component ID and `--delete-data`; `sts` is an example, not
   a special case. Limit the command to a source checkout's dev installation and
   current rootless user. Do not operate on production state or require `apps/`,
   network access, sudo or new host Python dependencies.
2. Resolve the selected component's actual resources from effective declarations
   and the last rendered dev state. Show what will be stopped/deleted, explicitly
   warn that database data is lost and require confirmation before destruction.
   Refuse unknown components, ambiguous ownership, shared/external volumes and
   unsafe paths before destructive actions. Do not infer ownership solely from
   a component-name prefix or accept arbitrary volume/path deletion arguments.
3. Stop/remove only the selected component's containers/pods, then remove its
   exclusively owned dev data volumes, including the database and relevant
   retained Secret/import copies. Define the cleanup set explicitly so a later
   prepare cannot reuse stale rendered credentials accidentally. Preserve
   operator config, source manifests, external credential files, TLS/signing
   certificates and CA material. Retain valid generated source passwords by
   default; allow the normal generation path when a password is absent and its
   database volume has actually been removed. Never print secret contents.
4. Keep siblings, their data/credentials, shared network and shared owners intact.
   Do not run aggregate `kube down` on `build/install.yaml` as a component reset.
   Report resources still in use or other inspection/deletion failures without
   forced removal of unrelated containers. Make partial cleanup safely repeatable;
   inspection failure is not evidence that a resource is absent.
5. Reset performs cleanup only and explains how to start again with the existing
   `./dev/dev.sh up`. Document that this existing startup command applies the
   whole dev catalog; reset itself must not restart siblings. Keep normal `up`
   and `down` data-retention behavior unchanged.

### Whole-dev reset: all development Secrets and volumes

Also implement:

```sh
./dev/dev.sh reset --all --delete-data
```

This is an explicit fresh start of this checkout's dev installation, including
new passwords. The component mode above keeps its narrower retention contract;
its preservation of generated passwords/certificates is not the contract of
`--all`. Make the distinction clear in help, preview, confirmation and docs.

- Require `--all` and `--delete-data`; reject a component combined with `--all`.
  Show a read-only plan with exact owned pods, volumes, Podman Secrets and local
  credential paths, never their contents. Require explicit confirmation that all
  listed dev database contents and dev credentials will be lost. Cancel/no input
  must leave everything unchanged.
- Stop/remove all pods and containers of this dev product, then remove all their
  exclusively owned declared dev volumes, including database, import and
  Secret-backed copies where present. Remove matching Podman Secret objects too,
  so startup cannot consume a stale retained value. Never use global prune,
  `podman volume rm --all`, `podman secret rm --all` or ownership inferred only
  from a name prefix. Refuse resources still used by unrelated containers.
- Remove local dev Secret source files under `build/dev/`, including generated
  passwords/session keys and local dev TLS/signing/PFX credentials. Include the
  dev-only CA/private material under `build/dev/PKI` when present. Preserve source
  manifests, config defaults, global/component dev overrides, application files
  and unrelated non-secret input files. Do not simply delete the entire `build/`
  directory: it may contain manually supplied component files and other outputs.
- Do not delete or follow Secret sources outside the managed dev tree. Report
  those external inputs as retained and explain that any desired replacement is
  an explicit operator action. Preserve production state, root/source PKI,
  external organisation certificates, original images and the shared network.
  A secret copied into the managed dev tree is disposable in this mode, even if
  originally provided by the operator; list it clearly before confirmation.
- Invalidate/rebuild the affected generated dev config, rendered YAML and import
  artifacts so no secret survives in an old generated output that can be replayed
  accidentally. Keep the last successful resource inventory or a cleanup record
  until cleanup completes; it must support a retry after partial deletion.
  Coordinate with the retained state needed by component reset instead of adding
  separate competing ownership models.
- Resolve ownership from effective declarations and the last rendered dev state,
  covering removed/renamed components where the old inventory identifies them.
  Refuse ambiguous or external ownership before deletion. Reset must not depend
  on reading Secret contents, generating replacement secrets or passing ordinary
  startup's missing-password/existing-volume guard; that is exactly the broken
  state it must help clean up. Validate paths and symlinks without following them
  outside the dev tree.
- Cleanup is safely repeatable: absent owned resources are acceptable, inspection
  errors are not absence, and deletion failure stops success reporting while
  preserving enough inventory to resume. Preflight the full plan before mutation.
- Reset itself does not start apps or generate credentials. Explain the next steps:
  generated `generate:` sources are recreated by normal prepare/up; externally
  supplied Secrets/PFX/password inputs must be reprovisioned first. The shipped
  demo can use `./dev/demo-credentials.sh` before `./dev/dev.sh up`, but generic
  products must not implicitly invoke demo provisioning. Confirm that full reset
  followed by provisioning/start produces a new database with matching new
  client/server passwords and recomposed `SECRET_TEMPLATES` values.

### Verification and delivery

Add focused platform tests with arbitrary component IDs and no `apps/`: explicit
flag/confirmation requirements, invalid/shared resource refusal before deletion,
correct scoped commands, valid retained password preservation, missing-password
recovery, partial-failure retry and unchanged siblings/certificates/config. Add a
runnable real Podman check that reproduces the missing-password guard, resets a
disposable component, starts again and verifies database initialization and
sibling data/process retention across reset. Keep unit/harness and actual runtime
evidence separate. Document the command, irreversible data loss and the backup
recovery alternative; complete the understandability review of resource ownership
and deletion order. For `--all`, add positive and negative coverage for the complete cleanup set,
new generated passwords after reinitialization, dev certificate/CA disposal,
preserved external credentials/non-secret files/config/images/other products,
confirmation/cancellation, stale Secret copies, invalid startup state and partial
cleanup retry. Provide a focused real Podman fresh-start scenario using synthetic
resources and no private organisation image. No new general recovery framework
is required.


## 56. Add component-specific dev configuration overrides

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve declarative
components, authoritative production config, shared settings, credential retention,
side-effect-free validation and host Python 3.6 compatibility. Coordinate with
item 57, but keep the two changes independently reviewable.

Status: done. Implemented on 2026-10-21; real Podman/systemd verification
passed in lab matrix `t10` at `cda22e7` ([COMPONENT-DEV.md](acceptance/COMPONENT-DEV.md)).
The optional component dev layer, shared-key refusal, private-source bundle guard,
demo marker, renamed-product handling and runtime acceptance assertions are in
place. Local verification and the understandability review are recorded in
[acceptance/COMPONENT-DEV.md](acceptance/COMPONENT-DEV.md). Historical analysis
below describes the implementation baseline; it is not a claim of lab results.

Operator clarification (2026-10-21), applying to items 56 and 57: existing
installations may be discarded. Start verification with a fresh installation and
newly initialized config; do not add migration code, compatibility fallbacks or
manual config-transition steps for installations predating these features.
Preservation and upgrade checks within the new model still apply, including
item 57's newer-bundle test with unchanged persistent config.

### Problem and intended behavior

`config/dev.yaml` applies to every component. Placing Identity-specific
`VOLUME_FILES`, `SECRET_FILES` or `SECRET_TEMPLATES` there contaminates other
components' effective settings and can violate component resource-name rules.
Whole-map replacement also discards declarations inherited from defaults. The
organisation needs local SQL paths and dev-only seeding choices for its Identity
migration init-container, independently of unrelated components and production.

### Task

1. Read optional `components/<id>/config.dev.yaml` only in source dev mode, with
   precedence from lowest to highest: `config/common.defaults.yaml`, component
   `config.defaults.yaml`, global `config/dev.yaml`, component `config.dev.yaml`.
   Retain the existing authoritative inheritance/checks for `public_from` and
   shared settings; a local override must not silently bypass those contracts.
2. Use the existing top-level merge and validation rules. Do not introduce deep
   merge: maps/lists, including complete file/Secret mappings, replace the earlier
   value. Document this with an example that retains all required declarations.
   Missing optional files keep current behavior; invalid YAML/duplicate keys fail
   through the same readable, value-safe diagnostics as existing config layers.
3. Apply the same effective dev config in validate, prepare/dev startup and
   relevant source tooling that already reads dev settings (for example file
   guards/build helpers). Trace those consumers explicitly; avoid a second merge
   implementation with different precedence. Preserve generated credentials and
   database-volume guards when overrides change.
4. Never read this layer during production init-config, validate or install, and
   never package the override file or collect external local files merely because
   it references them. The component's existing `files/` packaging rule still
   applies: non-secret demo files there ship even when only dev config selects
   them (see item 57). Keep generated `build/dev/<id>/config.yaml` an output, not
   an additional input layer.
5. Document the file, precedence, whole-map replacement and a renamed component
   example. Relative file sources still resolve against `build/dev/<id>/` under
   today's rules, not against the new override file. Clearly distinguish this
   task from item 57; adding a layer alone does not make paths portable.

### Review additions (2026-10-21)

Code facts and decisions from the review; they refine the task above.

- **Current code.** `render.component_defaults()` builds the layer list and
  `merge_config()` applies the `public_from` shared settings (`overrides`) after
  all layers. `deploy.dev_settings()` is the dev caller; `init_config()` is the
  production caller and must never read the new layer. `bundle.py` copies an
  allowlist per component (`manifests`, `config.defaults.yaml`, `route.conf`,
  `client.yaml`, `files`), so `config.dev.yaml` is not packaged today; prove it.
  README still says dev overrides apply to all components with no per-component
  override; update it.
- **Tracked file, no secrets.** `components/<id>/config.dev.yaml` is committed
  (shared dev settings). The acceptance harness requires a clean committed
  checkout, so the demo override must be tracked. It must never contain secret
  values; secrets stay in `credentials/` files. `config/dev.yaml` stays local
  and ignored.
- **Local override consequence.** With the chosen precedence, the tracked
  component dev file wins over the developer's ignored `config/dev.yaml`.
  Document that a developer cannot change a key supplied there through the global
  file; a machine-specific adjustment requires editing the tracked component
  file. Avoid committing machine-specific absolute paths in shared examples;
  use item 57's portable references for shipped files. Keep the specified order
  and do not silently introduce another local layer.
- **Shared settings are not silently ignored.** A `public_from` dependent must not
  set a shared key (`PUBLIC_ORIGIN`, `HTTPS_PORT`, the owner's `shares`) in its
  `config.dev.yaml`: the owner's value is applied afterwards, so the local value
  would vanish. Refuse it naming key, file and owner, never values. The owner may
  set its own shared keys there; dependents inherit them as today. If
  `config/dev.yaml` already has the same silent-ignore behavior, record it in the
  backlog rather than widening this item.
- **Bundle guard.** `bundle.generated_secret_guard()` reads `config/dev.yaml` with
  base `build/dev/<id>`; add `components/<id>/config.dev.yaml` with the same
  base, so a generated secret declared only there cannot be bundled. List every
  reader of dev config (grep) in the report; one merge implementation only.
- **Demo usage (app1).** Add a small, observable, non-secret value, for example a
  `DEMO_CONFIG_LAYER` key in the `app1-settings` ConfigMap from a placeholder with
  value `defaults` in `config.defaults.yaml` and `component-dev` in
  `components/app1/config.dev.yaml`. It must not change application behavior or
  existing E2E assertions; app2 must not receive it.
- **Acceptance.** DEV after dev-up: the running app1 container shows
  `component-dev` (podman exec printenv for that key only, never the full
  environment); app2 does not have the key. PROD after install: app1 shows
  `defaults`. Add stubbed harness regressions including a wrong-layer value
  reported as failure.
- **Additional tests.** Component dev beats global dev; a map replaces rather than
  merges; shared-key refusal for a dependent and owner-to-dependent inheritance;
  production init-config/validate/install ignore a hand-copied file of that name;
  a real bundle archive excludes it; the guard refuses a generated secret declared
  only in it. Update `tests/run.py --export` fixtures if needed and run
  `python3 -B tests/run.py platform --isolate`.

### Verification and delivery

Add focused platform tests for all precedence levels, absent/invalid files,
unchanged authoritative shared settings, two arbitrary component IDs with
independent file mappings, no `apps/`, validate/prepare agreement and preservation
of production config. Check real bundle contents exclude the dev override file.
Update offline export/fixtures and test instructions as necessary; run relevant
platform/isolation/static checks. Complete the understandability review of config
ownership and precedence; report any real-runtime verification separately.


## 57. Add portable references to bundled component files

Review baseline: [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md). Preserve isolated
offline bundles, authoritative production config, scoped file access, credential
retention, read-only validation and Python 3.6 compatibility. High-priority
follow-up to item 56; a separate feature, not an implicit part of its merge rules.

Status: done. Implemented on 2026-10-21; real Podman/systemd/SELinux/fapolicyd
verification passed in lab matrix `t10` at `cda22e7`
([COMPONENT-FILES.md](acceptance/COMPONENT-FILES.md)). `component_file` resolves public inputs in the selected component/release,
with shared validation/materialization, logical retained config and existing
private-source guards. The app1 demo and isolated SQL upgrade/failure-retry
acceptance checks are implemented. See [verification and understandability
review](acceptance/COMPONENT-FILES.md) for actual results and lab evidence.
The review notes below describe the baseline and implementation requirements.

Review follow-up (2026-10-21): the demo seed runs each SQL file with
`--single-transaction`, so a failed file rolls back entirely while completed files
stay committed; the real failure/retry probe now requires the failing file's
earlier row to be absent. The `sts` README example uses a relative dev path under
`build/dev/sts/` instead of a machine-specific path in a tracked file, and the docs
recommend an explicit file list or history table for real migrations instead of
executing every imported file.

The operator clarification in item 56 applies: no transition from pre-feature
installations is required. Test upgrades between releases of the new model.

### Problem and intended behavior

An SQL source under `components/<id>/files/` currently needs a dev path such as
`../../../components/<id>/files/permissions/9000_CreateUsers.sql`, resolved from
`build/dev/<id>/`. Production resolves ordinary relative paths from the persistent
component config directory instead; the file lives under an unpacked release.
Operators must hand-edit production release paths, which can become stale after
an upgrade or relocation. The same logical declaration should select the current
component's shipped file in both source dev and an unpacked offline bundle.

### Task

1. Define and document a small explicit source syntax for referencing a path
   under the selected component's `files/`. Choose the exact syntax during
   implementation; examples in the task are conceptual, not supported settings.
   Support non-generated sources in `VOLUME_FILES` and `SECRET_FILES` using a
   shared resolver, with their existing type/size rules. Do not introduce general
   shell/environment expansion, templating of arbitrary paths or app-specific SQL
   logic. Never execute referenced files as part of resolving them.
2. Resolve the reference against `components/<id>/files/` in the active source
   checkout or selected unpacked bundle. Carry that explicit context through
   config, validation and materialization; do not infer it from the caller's cwd,
   require `apps/`, use sibling release directories or depend on original build
   paths. Preserve ordinary relative, absolute and tilde path semantics.
3. Keep logical references in initialized persistent config instead of converting
   them to a versioned release's absolute paths. Later installs with that retained
   config must read files from the selected new bundle, including changed SQL,
   without rewriting operator config. Missing files must fail clearly; never
   fall back silently to an old release or source checkout. A newly published
   default still must not overwrite an existing authoritative config.
4. Reject absolute/traversing component-file references and symlink escapes,
   cross-component access and unsupported file types. Component-file sources are
   immutable inputs, never generation targets: refuse `generate` for this source
   kind before writes. Avoid exposing secret values in errors. Real secret inputs
   should remain external/generated credentials; do not commit or bundle passwords
   just because the file-reference mechanism can deliver a Secret.
5. Keep file delivery through the existing Secret/import-archive/PVC mechanisms,
   including init-container consumers and existing retention/uninstall behavior.
   Do not bind-mount build-machine paths into production containers. Confirm that
   current-release content actually reaches imported volumes after upgrade rather
   than merely asserting archive paths. Document existing stale/unlisted-file
   behavior and dev-seed inclusion explicitly; no automatic prod seeding toggle
   or new SQL runner is part of this task.
6. Document source/default config examples and relocated offline install/upgrade
   commands, including how it combines with item 56. Update relevant contracts,
   diagram text and tests only where affected; no general file-routing framework.

### Review additions (2026-10-21)

Code facts and decisions from the review; they refine the task above.

- **Current code.** `render.resolve_path(value, base_dir)` resolves relative paths
  from `build/dev/<id>/` in dev and the persistent config directory in production;
  the release is `common.ROOT`. It is used by `render.load_file_group`,
  `render.check_file_sources`, `render.secret_keys`,
  `deploy.database_password_path` and `bundle.generated_secret_guard` (which reads
  `entry["path"]` directly). All must use one shared resolver for the new kind.
  `file_group_sources` validates entry shape. VOLUME_FILES archives are written
  under `HOME/files` at install; Podman imports them at every start, overwriting
  matching files and keeping unlisted ones (README).
- **Recommended syntax.** A separate key, not a path prefix, so it cannot be
  mistaken for an ordinary relative path and `path` semantics stay unchanged:

  ```yaml
  VOLUME_FILES:
    app1-seed:
    - component_file: sql/010-reference.sql
  ```

  An entry has exactly one of `path` or `component_file`; `generate` with
  `component_file` is refused before writes. Confirm or justify another choice.
- **Selected release.** The base is `common.ROOT/components/<current component>/files/`:
  the source checkout in dev, the unpacked bundle running `./deploy.sh` in production,
  for validate and install alike. No release path is stored in config. Refuse the
  reference when there is no component context (standalone fixtures), and as a
  database password source or any generated credential.
- **Bundle guard and Secret delivery.** `bundle.generated_secret_guard()` currently
  excludes all declared `SECRET_FILES` sources from bundles, even without
  `generate`. Merely using the new resolver there would therefore reject an
  intentional bundled source. Define `component_file` in `SECRET_FILES` as an
  explicit declaration of shipped, non-secret content delivered through a Secret;
  it does not make the bundle a safe place for credentials. Permit this source
  kind without weakening the guard for ordinary private paths, generated files,
  credential directories or aliases. Test both successful archive inclusion and
  continued refusal when a file is also protected by a private declaration.
- **Recursive source checks.** If a component-file reference selects a directory,
  inspect all descendants, not only its root. `write_file_archives()` currently
  uses `dereference=True`, so an unchecked nested symlink could copy data outside
  the component. Reject symlinks and unsupported special files throughout the
  selected tree before generation or archive writes, using the same checks for
  validate and materialization. Cover a deeply nested escaping link, a symlinked
  ancestor and a special file without reading its contents. Preserve existing
  ordinary `path` semantics; apply the new confinement rules to `component_file`.
- **Dev selection versus bundle contents.** `bundle.py` copies the whole component
  `files/` tree. Consequently `files/sql-dev/900-dev-sample.sql` is included in the
  production bundle, even though production config does not select it for
  delivery or execution. Document and test that distinction; only harmless demo
  content belongs there. Excluding `config.dev.yaml` does not exclude files it
  references under `files/`, and these items add no selective packaging mechanism.
- **Sensitive dev-only seed data stays outside `files/`.** Because every file under
  `files/` ships, dev seed content that must not reach production (test users,
  test passwords, personal or customer-like data) belongs outside the component's
  `files/`, referenced with an ordinary `path` from `config.dev.yaml` (relative
  to `build/dev/<id>/` as today, or a local credential path). For the
  organisation's `sts` migration init container, the shipped migrations use
  `component_file` while such dev seeds use `path`. Document this rule with that
  example in README/docs/COMPONENTS.md, and add a test showing that a dev-only
  `path` source is neither packaged nor needed by production validate/install.
  Secret test passwords still belong in `credentials/`, never in tracked files.
- **Stale files.** Because Podman keeps unlisted files in an imported volume, a file
  removed from a later release still exists there. The demo makes every SQL file
  idempotent; document the limitation for the organisation's own migrations. No
  migration framework.
- **Demo usage (app1).** `components/app1/files/sql/010-reference.sql` creates a
  marker table (for example `demo_seed(name text primary key, value text)`) and
  upserts `reference` with a value identifying the release content;
  `files/sql-dev/900-dev-sample.sql` upserts `dev-sample`. `config.defaults.yaml`
  maps only the reference file to `VOLUME_FILES.app1-seed`; the item 56
  `config.dev.yaml` repeats it and adds the dev file (whole-map replacement). A new
  init container `seed-database`, after `prepare-database`, uses the already
  bundled `localhost/demo-postgres` image (official postgres with `psql`), mounts
  the PVC read-only and the existing database password Secret, and runs an
  explicit sorted list of `*.sql` files with `ON_ERROR_STOP`. The password goes
  from the mounted file into `PGPASSWORD` inside the container and is never
  printed. No new image or app rebuild; todo data, probes and app2 unchanged;
  update demo inventory counts intentionally.
- **SQL failure and retry.** The app1 pod already declares init-container type
  `always`; seeding must tolerate restart and repeated installation. Add a focused
  runnable Podman check that fails a SQL step after an earlier step succeeds,
  verifies startup is not reported as successful, then retries with corrected
  input and verifies no lost Todo data or duplicate seed rows. Add harness
  regressions for false success and report actual runtime execution separately.
  `ON_ERROR_STOP` stops processing but does not roll back earlier committed
  statements: use idempotent demo SQL and explain its transaction boundaries,
  without promising automatic migration rollback or adding a migration engine.
- **Acceptance.** DEV after dev-up: `demo_seed` has `reference` and `dev-sample`
  (query in the app1 postgres container, print only these rows). PROD after
  install: `reference` present, `dev-sample` absent. App1 upgrade in both app1-first
  and app2-first: build the new bundle with a changed reference value in an
  isolated build checkout (as the help/Identity builders do, never the operator's
  checkout). The `upgrade-bundle` step in `acceptance/remote.sh` currently requires
  that only `components/app1/VERSION` changed; require exactly VERSION plus that
  SQL file. After upgrade `reference` has the new value, the existing
  `persistent_state` check proves unchanged config, todo data stays readable and
  sibling checks pass. Coordinate with item 53, which changes the same step. The
  renamed `shop` scenario must carry component files and references and assert
  the same rows. Harness regressions reject the old value after upgrade, a
  `dev-sample` row on PROD and a missing `reference` row.
- **Additional tests.** Refuse absolute, `..`, empty, symlinked file or `files/`
  directory, cross-component, `path` plus `component_file`, `generate`, database
  password use and missing component context; SECRET_FILES use keeps key/size rules
  without printing values; the bundle guard handles entries without `path`; a
  relocated unpacked bundle with the source checkout removed resolves the same
  declaration; init-config keeps the logical reference and a newer bundle with
  changed bytes and unchanged config delivers the new bytes.

### Verification and delivery

Use renamed/minimal components without `apps/` to test identical declarations in
source dev and an unpacked relocated bundle with the original checkout removed.
Exercise config initialization, read-only validation, materialization and a new
bundle version with changed file bytes while persistent config is unchanged.
Cover missing sources, path/symlink escapes, generation refusal, ordinary paths,
Secret redaction and preservation of credentials, config and sibling state.
Add runnable real Podman acceptance coverage that reads an imported SQL/marker
file in an init-container before and after the selected-component upgrade. No
actual organisation SQL, passwords or Duende image is needed for the generic
fixture. Run relevant platform/isolation, harness and static checks; distinguish
these from real lab results. Complete the understandability review of reference
resolution, config persistence and release selection.


## 58. Clarify global dev overrides of owner-shared settings

Status: done (documentation only), 2026-10-21. No code change.

`deploy.dev_settings()` applies a `public_from` owner's effective shared values
after merging a dependent's layers. The owner's effective values already include
the global `config/dev.yaml`, which applies to every component. A global shared
key therefore reaches the owner and every dependent with the same value; nothing
is lost. The only difference arises when the owner's own `config.dev.yaml` sets
the key: that more specific value wins for the owner and all dependents alike.
This keeps proxy, Identity and apps consistent, matches production (`init-config`
inherits shared values from the owner) and is covered by item 56's
`test_owner_dev_settings_reach_dependents`.

Refusing global shared keys would break ordinary use: `config/dev.yaml.example`
sets `PUBLIC_ORIGIN` and `HTTPS_PORT` globally. The precedence is now documented
in README, docs/COMPONENTS.md and acceptance/COMPONENT-DEV.md, and the
REVIEW_GUIDE known gap is marked resolved.


## 59. Standardise Quadlet placeholder syntax

Status: implemented with local product/harness regression checks (2026-10-23).
`@@UNIT_NAME@@` / `@@PRODUCT_NAME@@` use the existing single-pass parser with
an internal-only resolver; both templates are checked before host queries,
generation or writes, including standalone and equal-version `newer-only`.
[Verification and understandability review](acceptance/QUADLET-TEMPLATES.md).
Real Podman/systemd verification passed in the 2026-10-24 six-scenario matrix;
see [run provenance and limits](acceptance/STATUS.md#completed-real-lab-verification-2026-10-24).
The original analysis and task follow.

### Analysis and decision

The Quadlet templates currently use `{name}` and `{product}`, while the YAML,
ConfigMap and Secret templates use `@@...@@`. The Quadlet spelling is a project
convention implemented by two literal replacements in `deploy.quadlet_text()`;
it is not syntax required by Podman or systemd. There is no technical need for
two placeholder spellings. Literal replacement also leaves misspelled markers
in the output without reporting the template error.

Standardise Quadlet on `@@UNIT_NAME@@` and `@@PRODUCT_NAME@@`. Keep the distinct
sources and rendering rules: these are internally calculated unit/product names,
not user configuration keys. Sharing marker syntax does not mean exposing the
YAML config or Secret resolvers to Quadlet, or changing YAML type preservation.

### Implementation brief for the AI agent

Read [AGENTS.md](AGENTS.md) and [the review guide](docs/REVIEW_GUIDE.md), then trace
both component and standalone flows before editing. Inspect:

- `quadlet/template.kube` and `quadlet/template.network`;
- `deployment/deploy.py`: `quadlet_text()`, `check_shared_network()`,
  `write_component_units_and_imports()` and `install_standalone()`;
- `deployment/common.py`, `deployment/catalog.py` and `deployment/validation.py`
  for template paths, authoritative names and read-only validation;
- `deployment/templates.py` and `deployment/render.py` for existing token parsing
  and the deliberately different config/Secret/YAML rendering contracts;
- the Quadlet fixtures in `tests/helpers/`, plus relevant validation, deployment,
  renamed-product, retry and bundle tests in `tests/platform_tests/`.

Implement the following contract:

1. Change the shipped `.kube` template to use these values, preserving its other
   directives:

   ```ini
   [Unit]
   Description=@@UNIT_NAME@@

   [Kube]
   Yaml=@@UNIT_NAME@@.yaml
   Network=@@PRODUCT_NAME@@.network
   ```

   The `.network` template becomes:

   ```ini
   [Network]
   NetworkName=@@PRODUCT_NAME@@
   ```

2. Resolve only these two names from explicit internal arguments. Product name
   comes from the existing catalog contract (`product:` in the source/compiled
   descriptor); unit name uses the existing component naming contract. Standalone
   fixtures retain `common.STANDALONE_PRODUCT`. Do not derive names from demo
   component IDs, environment variables, arbitrary config values or secrets.
   Do not introduce `UNIT_NAME` / `PRODUCT_NAME` as configurable settings.

3. Render text in one nonrecursive pass, supporting inline and repeated tokens.
   Reject unknown names, malformed `@@...@@` syntax and unresolved markers with
   a useful template-path/token diagnostic. Explicitly reject the obsolete
   `{name}` and `{product}` markers rather than silently accepting a mixed
   template. Preserve unrelated literal braces, shell `${...}` expressions and
   systemd `%` specifiers; do not ban every brace expression. Errors must not dump
   whole templates or configuration/Secret contents. Do not require every allowed
   marker to occur in every template.

4. Use the same pure rendering/validation logic for read-only `deploy validate`
   and install. Check both required templates for the selected operation during
   early preflight, including standalone mode, before image import, generated
   credentials, unit writes or host commands. Trace the existing ordering:
   validating `.kube` only in `write_component_units_and_imports()` is too late.
   Keep validation side-effect free and avoid a second parser with different
   acceptance rules. Respect component isolation and existing lifecycle checks.

5. Preserve generated unit/network names, YAML references, permissions, service
   directives and shared-network comparison/retry behavior. For equivalent valid
   template content, rendering must produce the same bytes as before. Renamed
   products and standalone fixtures must work without special demo assumptions.
   New source templates and the renderer must travel together in offline bundles.

6. Update affected test fixtures, comments, docstrings and current documentation.
   Explain that the marker syntax is shared but the allowed values depend on the
   template context. Historical backlog descriptions may remain historical.
   Existing installations can be discarded: no migration, dual-syntax fallback
   or compatibility aliases are required. Normal retry and retained-data contracts
   still apply to installations made with the new code.

Keep this small. Reuse a suitable existing tokenizer/substitution helper with a
Quadlet-specific resolver if that keeps the code clearer; do not reuse a resolver
that grants arbitrary config or Secret access. Do not add Jinja, another external
dependency, a generic template framework or unrelated deployment refactoring.
Retain Python 3.6 and offline operation. Do not change YAML typed substitution,
ConfigMap inline composition or Secret template policies.

### Verification and acceptance criteria

Add focused regression coverage for:

- Both templates, repeated/inline tokens and exact expected rendered output.
- A renamed product with a distinct component ID: the full unit name is used
  once, while the shared network uses only the product name; also standalone.
- Unknown, malformed and obsolete markers, config/Secret references being refused,
  and unrelated braces/shell expressions/systemd specifiers being preserved.
  Config values must not override the two internally supplied names.
- Identical rejection through read-only validation and install, with assertions
  that invalid templates cause no host commands or installation mutations.
- Repeated install/shared-network comparisons and sibling resource preservation.
- Current templates and renderer in an unpacked relocated offline bundle, using
  a minimal/renamed fixture without `apps/` or access to the original checkout.

Run the relevant platform, isolation and acceptance-harness checks using existing
repository conventions, plus `git diff --check`. Reuse existing bundle/retry tests
where they already prove the contract instead of duplicating the implementation
in tests. If real Podman/systemd verification is performed, report it separately
from unit/harness results; otherwise state that gap explicitly. Historical lab
results are not evidence for this change.

Complete an understandability review: a reader should be able to trace where the
two values originate, which tokens are allowed, when validation runs, what can
have changed when an error occurs, and why retry still works. Delivery is complete
when the templates, shared validation, fixtures and current documentation agree,
the relevant checks pass, and any runtime verification gaps are recorded.


## 60. Rename the CLI wrapper to deploy.sh

Status: implemented with local product and harness regression checks (2026-10-24).
`./deploy.sh` is the sole current wrapper in source, bundles, callers, usage and
current documentation; no old-name alias is shipped. Based on item 59 commit
`6c9a461`, on branch `fix/60-deploy-sh`.
[Verification and understandability review](acceptance/CLI-WRAPPER.md).
Real Podman/systemd verification passed in the 2026-10-24 six-scenario matrix;
see [run provenance and limits](acceptance/STATUS.md#completed-real-lab-verification-2026-10-24).
The original rename brief follows.

### Analysis and implementation brief

The current `deploy` is a small Bash wrapper: it changes to its own directory and
executes `python3 -B -m deployment`, forwarding all arguments. Renaming the wrapper
is straightforward; the work is making every caller and delivered bundle agree.
The suffix is a usability/naming decision, not a change of interpreter or CLI
behavior.

Read [AGENTS.md](AGENTS.md) and [the review guide](docs/REVIEW_GUIDE.md). Implement
this as a focused rename:

1. Rename the root executable `deploy` to `deploy.sh`, preserving its executable
   bit, Bash shebang, directory handling, argument forwarding and exit behavior.
   Keep the Python package `deployment` and its modules, including `deploy.py`,
   named as they are. Subcommands and arguments remain the same.
2. Find all executable-path references, including shell/Python callers, bundle
   file lists, checksums, executable permissions, host-preparation/trust handling,
   dev tooling, acceptance scripts, CI and test fixtures. Update active references
   to the new filename. Inspect each match; do not globally replace the word
   `deploy`, Python identifiers or conceptual uses of deployment terminology.
3. Update current README/docs, help and error messages, command examples and
   instructions emitted by scripts. Update active instructions in planned backlog
   items (including item 59) where they refer to the executable. Preserve historical
   verification reports and pinned historical fixtures as historical evidence.
4. New bundles must include executable `deploy.sh`, with checksum/trust handling
   matching the new path. Verify that an unpacked, relocated offline bundle works
   without its source checkout. Keep Python 3.6 and the existing offline dependency
   contract; no new runtime dependencies or installation steps are needed.
5. Existing installations can be discarded. Make `deploy.sh` the sole current
   entry point; no `deploy` alias, compatibility wrapper or migration is required.
   Preserve ordinary install, retry and retained-data behavior in new installations.

### Verification and completion

Adapt existing wrapper, bundle and acceptance-harness tests. Cover invocation from
another working directory, argument forwarding and exit status, executable mode,
help/validation and a relocated bundle using the new path. Exercise relevant
existing lifecycle tests through the renamed wrapper instead of adding duplicate
business-logic tests. Include a minimal/renamed product fixture without `apps/`
where appropriate, so verification is not limited to the demo checkout.

Search for remaining old executable references and explain intentional historical
matches. Run relevant platform/isolation and harness checks, documentation/link
checks and `git diff --check`. Report exact results and any real Podman/systemd
verification gap separately. Complete the understandability check by tracing the
public command through the wrapper to Python in both source and bundle, including
an error exit. Done means the source, release contents, callers, help, tests and
current documentation all agree on `./deploy.sh`.


## 62. Reject misplaced container fields in manifest validation

Status: implemented with local product regression coverage (2026-10-22).
Shared `render.pod_specs` rejects nineteen container-only fields directly under
Pod `spec`; validate, prepare, install and bundle building use the guard with
source-file context, including equal-version `newer-only` repeat installs after
review follow-up. Exact scope, checks and limitations:
[MANIFEST-STRUCTURE.md](acceptance/MANIFEST-STRUCTURE.md).
This closes the confirmed structural validation gap, distinct from item 61's
completed runtime verification. The original finding and task follow.

### Finding and reproduction

The operator placed `env` beside `initContainers` under a Pod's `spec`, instead
of inside the selected init-container object:

```yaml
spec:
  initContainers:
  - name: migration
    image: localhost/probe:1
    imagePullPolicy: Never
  containers:
  - name: main
    image: localhost/probe:1
    imagePullPolicy: Never
  env:                         # Wrong: belongs to a container, not Pod spec.
  - name: APP_CONNECTIONSTRING
    valueFrom:
      secretKeyRef:
        name: worker-settings
        key: connection
```

This is syntactically valid YAML, but `spec.env` is not a valid Pod field.
The operator observed empty/missing init environment variables. After correcting
the indentation, inspect showed the expected environment; the remaining migration
failure is separate and is not diagnosed by this finding.

A read-only synthetic reproduction at `7063f57` confirmed that
`render.effective_documents()` accepts the wrong structure above with a declared
`worker-settings` Secret template. `check_pod_specs()` checks selected supported
properties, but does not reject this misplaced field. Recursive reference scanning
can still count its Secret reference as used; a successful reference check is not
proof that the field belongs to a container or will be consumed by Podman.

### Implementation brief for the AI agent

Read [AGENTS.md](AGENTS.md), [the review guide](docs/REVIEW_GUIDE.md) and item 61.
Trace `render.effective_documents()`, `check_pod_specs()`, `pod_specs()`,
`containers()` and `references()` in `deployment/render.py`, then
`deploy.validate_component()` and its callers in `deployment/validation.py` and
`deployment/deploy.py`. Inspect bundle manifest validation too.

- Add structural validation that rejects misplaced container fields. At minimum,
  reject `env`, `envFrom`, `command`, `args`, `image`, `imagePullPolicy` and
  `volumeMounts` directly under Pod `spec`, with regression coverage for the
  operator's `spec.env` case. Assess other common misplaced fields and document
  the exact enforced scope; do not call a small guard complete schema validation.
- Put the check in the shared declaration-validation path used by validate,
  prepare and install, before credential generation, output writes or host
  commands. Reuse the same check for bundle building where applicable; do not
  add a validate-only rule or a late install-only check.
- Report the source manifest and field path, and explain the correct location.
  For example: `pod.yaml: spec.env is not allowed here; place env under
  spec.containers[] or spec.initContainers[]`. Do not print field values,
  passwords, connection strings or whole YAML documents. Carry source context
  explicitly where needed instead of relying on a generic filename in errors.
- Reject the error rather than silently moving fields into a container: a Pod
  may have several ordinary/init containers, so the intended recipient is unknown.
  Preserve valid `env` on each individual container and support both ordinary YAML
  sequence indentation styles. The problem is object structure, not an exact
  number of spaces or where the sequence dash is aligned.
- Keep Python 3.6, offline operation and supported Podman annotations/fields.
  Choose a small maintainable structural guard unless broader schema validation
  has a clear justified scope. Do not require a Kubernetes cluster, network schema
  downloads or a new mandatory external CLI. Do not apply a recursive keyword ban:
  ConfigMap `data`, Secret key maps and annotation values may legitimately contain
  words such as `env`, `image` or `command`.
- Review existing schema/shape checks before extending them. Avoid duplicate
  allowlists or independent validation engines. A broader strict field allowlist
  must be tied to documented supported structures and must not accidentally reject
  otherwise supported manifests. Do not expand supported resource kinds or add
  unrelated lifecycle/Secret behavior while addressing this gap.

### Regression coverage and completion

Use synthetic renamed/minimal components without `apps/`. Prove that misplaced
`spec.env` is rejected even when its Secret and key exist and the reference would
otherwise pass. Cover the other guarded fields, correct placement in ordinary and
init containers, multiple Secret-based env entries in the same init container,
and valid arbitrary keys in ConfigMaps/Secrets/annotations.

Exercise the public validate command and prepare/install paths, including an
unpacked relocated component bundle with retained production config. Assert that
refusal preserves config, credentials, existing rendered output and sibling state,
reads no credential contents during validate, and causes no Podman/systemd call.
Adapt relevant existing tests rather than building another harness. Cover bundle
build refusal before image operations if the shared check applies there.

Run relevant product tests, `python3 -B tests/run.py platform --isolate`, acceptance
harness tests if changed, and appropriate static checks plus `git diff --check`.
Report environment-blocked checks and real runtime verification separately.
Complete an understandability review of source context -> structural check ->
semantic checks -> materialization, including the error path before side effects.
Update current validation documentation and this item's status with the actual
scope and evidence. Success means this concrete YAML mistake fails clearly at
validation; it does not establish the cause of the remaining private Grate failure.

## 63. Parameterise image versions with build-time variables

Status: planned, high priority (2026-10-22, extended 2026-10-27). Requested by
the operator: image versions must be controlled by parameters, not edited
inside each manifest. Decision (operator, 2026-10-22): one shared variables file
`config/images.yaml`, placeholders only in container image references, resolved
at bundle build and in dev; plus a built-in `COMPONENT_VERSION` for images that
follow their component's release. Production keeps receiving fixed literal
tags.

Product owner, 2026-10-27:
- **Registry too, not only versions.** The organisation pulls images through
  Artifactory; when its address changes, it must change in one place. A
  variable can therefore hold the registry host and path, not only a tag, and
  the demo uses one (see "Demo adoption").
- **Optional per image.** Not every image uses the registry or any variable;
  some are written as plain literal references and must keep working.
- **`@@NAME@@`, not `{{NAME}}`.** Use the repository's existing placeholder
  spelling. `@@` already depends on where it stands (whole config values,
  inline ConfigMap and Secret-template text, `@@secret:…@@`, Quadlet
  `@@UNIT_NAME@@`); an `image` field becomes one more such place, read from
  `config/images.yaml` at build time. The rules under "Target behaviour" keep
  the two sources of `@@` values apart.

### Why image versions must not live in component config

Analysis on `a37f4e4`:

- `config/common.defaults.yaml` and `components/<id>/config.defaults.yaml` are
  copied into the authoritative production config by `init-config`. Later
  defaults are never merged into it (review-guide contract "Authoritative
  production config"). An image version there would keep the old image after an
  upgrade, or let an operator select an image the offline bundle does not
  contain.
- The bundle must know its images at build time. `bundle.build_release` calls
  `manifest_images(directory / "manifests")` on the source manifests and saves
  exactly those images in `images/images.tar` and `images/images.txt`.
  `render.find_images` deliberately rejects `@@` placeholders in `image:`
  ("placeholders are not supported").
- `@@NAME@@` elsewhere in a manifest (`common.PH`, resolved by
  `render.replace` from config at render time) means "comes from installation
  config". Inside an `image` field it is rejected today, so no existing
  manifest uses it there; giving it the build-time meaning in that one field
  breaks nothing. A reviewer must still be able to tell the two apart, hence
  the name rules below (target behaviour 2).

### Current image flow (all places that read source manifests for images)

- `bundle.manifest_images()` is used by `build_release`, `dev/build-images.sh`
  and `dev/pull-images.sh`. It parses source manifests through
  `render.load_yaml_all` and `render.find_images`.
- `bundle.build_release` copies `components/<id>/manifests` verbatim into the
  release with `shutil.copytree`.
- `render.py` around line 186 loads source component manifests for dev and
  validate. Rendered output (`deploy.py` near line 982, `health.py`) must not be
  token-resolved again.
- `deploy.load_and_verify_images` and the code near `deploy.py:854` load the
  release's `components/<id>/manifests` at install and check that every image
  exists after `podman load`.
- `dev/build-images.sh` maps `localhost/demo-postgres:<tag>` to
  `docker.io/library/postgres:<tag>` and builds other `localhost/demo-<app>`
  images from `apps/<app>/Containerfile`. It works on resolved names.
- `install_needed` (`deploy.py`): with `upgrade: newer-only` an equal installed
  version is kept. Installed metadata is the compiled descriptor
  (`deploy.py:830`) and records no images. A changed variable, for example
  `POSTGRES_VER`, without a `VERSION` bump would therefore be silently ignored
  on an existing installation. This is the main correctness risk of the
  feature.
- The acceptance harness hard-codes tags. `remote.sh` help and identity upgrade
  builders regex-replace `localhost/demo-help:X.Y.Z` and
  `localhost/demo-identity:X.Y.Z` in manifests (with a count==1 check) and build
  the new tag. Literal tags also appear in `tests/demo_tests/test_images_demo.py`,
  `test_bundle_demo.py`, `test_proxy.py`, `acceptance/test_identity.py`,
  `acceptance/test_components.py`, `acceptance/renamed_product.py` (keeps image
  names), README, ARCHITECTURE and acceptance documents.

### Target behaviour

1. `config/images.yaml` (optional; absent means no variables) is a flat mapping:
   ```yaml
   REGISTRY: artifactory.example.com/docker-remote
   POSTGRES_VER: '17.11'
   NGINX_VER: 1.28-alpine
   TODO_BACKEND_VER: 0.2.2
   TODO_FRONTEND_VER: 0.2.0
   ```
   Keys match `^[A-Z][A-Z0-9_]*$`. Values must be nonempty YAML strings. Reject
   numbers (`17.11` parses as a float) with a message telling the author to
   quote them. `COMPONENT_VERSION` is reserved. The file is build input. It
   never enters component or production config and is not merged by
   `merge_config`.
2. Placeholders are optional, per image reference. A literal reference
   (`image: docker.io/library/nginx:1.28-alpine`) stays valid, needs no
   variable and is copied unchanged; one manifest and one Pod may mix literal
   and templated references, and a manifest without `@@` in its `image` fields
   needs no change. Where wanted, manifests may use `@@NAME@@` inside a
   container or initContainer `image` string, in any part of it and more than
   once: registry host and path, name or tag. Examples:
   `image: localhost/demo-postgres:@@POSTGRES_VER@@`,
   `image: '@@REGISTRY@@/library/nginx:@@NGINX_VER@@'` (quoted: YAML would
   otherwise read a leading `@` as reserved). No nesting, defaults or
   expressions. Rules that keep the two `@@` sources apart, checked before any
   write:
   - In an `image` field, `@@NAME@@` comes only from `config/images.yaml` (or
     `COMPONENT_VERSION`); a name not defined there is an error, never a
     fallback to installation config.
   - Outside `image` fields, `@@NAME@@` keeps today's meaning (installation
     config). A name defined in `config/images.yaml` used outside an `image`
     field is an error naming file and field, so a build-time value cannot be
     mistaken for an installation setting.
   - A name may not be both an image variable and a key in common or component
     config defaults (or a reserved configuration name); refuse the build and
     name both files.
   - The resolved reference must be a valid image reference: no URL scheme
     (`https://` is refused with a hint to give only host and path), no
     whitespace or `@@` left, registry host with an optional port. Variable
     values are public (they end up in the release); never treat them as
     credentials.
3. `@@COMPONENT_VERSION@@` resolves to the owning component's
   `components/<id>/VERSION`. It requires component context; the standalone
   `manifests/` fixture has no component and must reject it clearly.
4. Resolution happens in one shared function used by every source-manifest
   reader listed above: bundle image discovery, bundle release copy, dev,
   validate, build-images and pull-images. Unknown names fail with file,
   component, container and variable name. Only names appear in messages, never
   unrelated file contents.
5. The release contains resolved literal manifests. `bundle.build_release` writes
   the resolved text instead of copying verbatim, before checksums are computed.
   `images.txt` must equal the images found in the shipped manifests. Production
   install, validate, upgrade and health then need no knowledge of the variables,
   and `render.find_images` keeps rejecting any unresolved `@@` in a release's
   `image` fields.
   Do not ship `config/images.yaml` in bundles.
6. Equal version, different images: record the resolved, sorted image list in
   the compiled descriptor (`bundle.yaml`), which installed metadata already
   stores. When `install_needed` would keep an equal installed version but the
   recorded images differ, refuse with a clear message to bump the component's
   `VERSION`; do not reinstall silently. Metadata from before this change has no
   image list. Treat that as "unknown" and allow the normal equal-version
   behaviour; existing lab installations may be discarded, so no migration
   layer is needed. Check `catalog.check_descriptor` and descriptor comparisons
   (`check_kept_shares`, sibling checks) so the new field does not break them.
7. A variable defined but unused by any selected manifest prints a warning at
   bundle build. That catches typos and leftovers without blocking.

### Demo adoption

Convert the demo so the templated forms and literal references are all
exercised; not every image is converted:
- help and identity: `@@COMPONENT_VERSION@@`. Their images are built per
  component.
- todo-backend and todo-frontend: `TODO_BACKEND_VER` and `TODO_FRONTEND_VER`.
  app1 and app2 share these images and may have different component versions.
- postgres in app1, app2 and identity: `POSTGRES_VER`.
- platform nginx: `REGISTRY` and `NGINX_VER`
  (`@@REGISTRY@@/library/nginx:@@NGINX_VER@@`, demo value `docker.io`), so the
  registry form is exercised; changing `REGISTRY` alone must change the pulled,
  bundled and installed image name. `dev/pull-images.sh` and
  `dev/build-images.sh` work on resolved names; check that the
  `localhost/demo-postgres` source mapping still holds.
- app3's whoami images stay literal (`localhost/demo-whoami-backend:0.1.0` and
  `localhost/demo-whoami-frontend:0.1.0`): a release must ship them unchanged,
  and the bundle's image list, `images.txt` and descriptor images must include
  them exactly as written.

This changes the demo's help and identity tags to the component version (for
example `localhost/demo-identity:0.4.12`). Update the harness accordingly:
- The help and identity upgrade builders in `remote.sh` should set only `VERSION`
  (plus content and marker changes) and build the image tagged with the new
  version. Remove the manifest regex replacement and its count check.
- `seed_upgrade.py` bumps app1 `VERSION` only. Its image must stay unchanged
  because todo images use variables. Assert that.
- `renamed_product.py` must carry `config/images.yaml` into the generated
  product (it copies Git-tracked files; verify) and keep image names unchanged.

### Detailed instructions for the implementation agent

1. Read [AGENTS.md](AGENTS.md), [the review guide](docs/REVIEW_GUIDE.md),
   `docs/COMPONENTS.md`, [tests/README.md](tests/README.md) and
   [acceptance/README.md](acceptance/README.md), and items 20, 21, 41, 56 and
   57. Re-check the code paths above on the current baseline before changing
   anything; line numbers will drift.
2. Implement one loader and resolver, for example a small function next to
   `render.load_yaml_all`. It should take the component (or none), parse the
   YAML, find tokens only in `image` fields of `pod_specs`/containers/
   initContainers, and reject tokens elsewhere. Keep YAML loading safe
   (`yaml.safe_load_all`) and Python 3.6 compatible on the target; the release
   never resolves.
3. For the release copy, prefer substituting resolved values into the original
   text after the parsed check has proved that every token sits in an image
   field. That preserves comments and formatting. Re-parse the written release
   manifest and require that `find_images` equals the bundle's image list.
4. Wire the resolver into `bundle.manifest_images`, `build_release`, the dev and
   validate source paths and both dev image scripts. Make sure renders of
   generated output and release manifests do not resolve a second time.
5. Implement the equal-version image guard (target behaviour 6), with a
   message naming the component and telling the operator to bump `VERSION`.
   Never print config or credential data.
6. Convert the demo and harness as described, keeping existing upgrade, sibling
   and persistent-state assertions.
7. Documentation:
   - `docs/COMPONENTS.md`: a new "Image versions" section.
   - README build and upgrade sections: how to change an image, and that a
     changed image needs a `VERSION` bump.
   - `docs/REVIEW_GUIDE.md`: a contract row "Image references", covering
     build-time only, literal in release, equal-version guard.
   - `ARCHITECTURE.md`: replace hard-coded tag references where they describe
     current behaviour.

### Tests

- Platform/product (generic, runnable with `platform --isolate`, no demo):
  - resolution in image fields, including a registry variable with a path
    and several variables in one reference;
  - literal references unchanged, alone and mixed with templated ones in the
    same Pod, and a product without `config/images.yaml` whose manifests
    have no image placeholders;
  - `COMPONENT_VERSION`;
  - an image variable name used outside an image field; a config name used
    in an image field; a name defined both as image variable and in config
    defaults;
  - a registry value with a URL scheme or whitespace;
  - unknown variable;
  - token outside image (env value, name, command, annotation);
  - non-string value;
  - reserved name;
  - missing file with and without tokens;
  - standalone fixture rejecting `COMPONENT_VERSION`;
  - nested or malformed tokens;
  - unused-variable warning;
  - release manifests contain no tokens and match `images.txt` and descriptor
    images;
  - comments preserved;
  - equal-version different-images refusal;
  - old metadata without images accepted.
- Demo tests: updated expected images, now resolved from `config/images.yaml`.
- Harness tests: upgrade builders no longer edit manifests. The identity and help
  builds tag `COMPONENT_VERSION`, and `seed_upgrade` keeps the todo image.
- Real lab: this touches every bundle and the upgrade flows. Run the full
  six-scenario matrix (app1, app2, help, platform, identity, shop) and record
  the run IDs and commit. Product, harness and real-runtime results must be
  reported separately.

### Acceptance criteria

- Changing a value in `config/images.yaml` (or a component `VERSION` for
  `COMPONENT_VERSION` images) changes the built, bundled, installed and running
  image tags, with no manifest edits. Changing the registry variable changes
  every image that uses it, in one place, and no literal image.
- Literal image references keep working unchanged; using placeholders is a
  choice per image, never a requirement.
- Production config never contains image versions. Releases contain only
  literal, fully qualified images.
- An equal-version release with different images is refused with guidance and
  never silently ignored.
- All existing contracts and lab scenarios stay green. The understandability
  review covers one normal build and upgrade flow and one failure flow (unknown
  variable or equal-version refusal).

Out of scope: operator overrides of image versions in production config,
registry credentials, automatic `VERSION` bumps and image pruning.

Open question (product owner, not decided): the Artifactory address may also be
needed outside manifests, for example in the `FROM` lines of the demo
Containerfiles (`docker.io/…`, `mcr.microsoft.com/…`) and in package sources
used while building images (NuGet, npm, pip). `config/images.yaml` covers only
manifest image references; the build side would need build arguments or
registry mirrors and is a separate decision.
