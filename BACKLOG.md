# Backlog

Use [the review guide](docs/REVIEW_GUIDE.md) for product contracts, lifecycle
review, evidence levels and the required understandability check. Follow
[AGENTS.md](AGENTS.md) when implementing or reviewing these tasks.

Planned work, not implemented behavior. Each item requires separate implementation
and verification. Item numbers are stable references, not execution priority.
The recommended implementation sequence through item 1 is complete. Remaining
items retain their individual scopes below; agree the next priority separately.

## Current priority (updated 2026-10-23)

Item 64 is the highest-priority next operator deliverable: unblock a fresh
rootless production installation as an existing login user with almost no home
space, keeping product files under a separate `/var/lib/<product>` root.
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
fields ([verification](acceptance/MANIFEST-STRUCTURE.md)). Item 59 is a high-priority follow-up
to standardise Quadlet placeholder syntax and reject invalid templates early.
Item 60 follows with the high-priority rename of the CLI wrapper to `deploy.sh`;
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
   (operator request); `{{NAME}}` image tokens from `config/images.yaml` and
   `{{COMPONENT_VERSION}}`, resolved at build; literal tags in releases;
   refuse equal-version releases with different images. After item 54.
8. [Item 62](#62-reject-misplaced-container-fields-in-manifest-validation): implemented;
   reject valid YAML with container fields at the wrong structural level,
   starting with `spec.env`; after item 54 and before item 59.
9. [Item 59](#59-standardise-quadlet-placeholder-syntax): high priority;
   use `@@UNIT_NAME@@` / `@@PRODUCT_NAME@@` with explicit internal values and
   early validation; after item 54.
10. [Item 60](#60-rename-the-cli-wrapper-to-deploysh): high priority;
   rename `deploy` to `deploy.sh` consistently in source, bundles, callers,
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
18. [Item 39](#39-show-the-installed-components-and-versions-on-the-target):
   `./deploy status` shows each installed component, version and unit state.
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

Open: 64 (urgent, coordinated with 54), 54 (implementation on feature branch; lab matrix pending), 63, 59 and 60 (high priority, in that order after 54), 48, 49, 44, 39, 45b, 45c, 42, 3, 2, 37, 47, 35, 36, 50, 22, 24, 51 and 52 (low priority), 53, 55, 5, 7, 6, and
item 30 steps 3-4.
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

## 64. Support new rootless installations outside the login home

Status: planned; highest-priority operator deliverable, requested 2026-10-23.
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

Suppler testdekningen i `gunstein/podman_offline` før den planlagte refaktoreringen av deploy-koden.

Målet er å etablere en tydelig, testet baseline for eksisterende oppførsel. Dette er en avgrenset testoppgave, ikke selve refaktoreringen.

### 1. Kartlegg eksisterende dekning og kjør baseline

Les dagens kode, tester og verifikasjonsrapporter. Kontroller særlig:

- `tests/`
- `acceptance/`
- `deploy.py`
- `bundle.py`
- Rotkommandoene og bundle-innholdet.

Kjør eksisterende produkt- og acceptance-harness-tester før endringer. Registrer commit og resultater.

Gjenbruk eksisterende fixtures og testverktøy. Ikke dupliser tester som allerede dekker kravene nedenfor.

### 2. Test reell oppgradering fra 0.2.0

Legg til et målrettet acceptance-scenario som oppgraderer en faktisk 0.2.0-installasjon til dagens versjon.

Bruk en identifisert historisk commit for gammel kode og gamle images. Ikke simuler gammel release ved bare å endre `VERSION` i dagens kode.

Scenario:

1. Bygg og installer gammel app1/core og app2.
2. Opprett brukerdata gjennom eksisterende e2e-/markørmekanisme.
3. Registrer eksisterende versjoner, config, credential-filer, databasevolumer og relevante tjenesteobservasjoner.
4. Følg dagens dokumenterte manuelle oppgraderingssteg: legg til nødvendige DB-felter og `GENERATED_SECRETS`-oppføringer i persistent config.
5. Overfør og installer ny app1/core-bundle.
6. Verifiser at app1/core fungerer, og at gammel app2 fortsatt fungerer uten utilsiktede endringer.
7. Oppgrader deretter app2 og verifiser hele installasjonen.

Kontroller spesielt:

- Eksisterende databasepassord beholdes byte-for-byte.
- Databasevolumer beholdes, og eksisterende brukerdata er tilgjengelige.
- Persistent config endres bare gjennom de eksplisitte operatørstegene.
- Ingen credentials regenereres eller databasebrukere endres automatisk.
- App1-oppgraderingen ikke endrer app2s tjeneste, versjon, config eller credentials.
- Innlogging og databaseoperasjoner fungerer etter hvert oppgraderingstrinn.
- Trust for gammel release fjernes først etter vellykket verifikasjon, uten å berøre sibling-bundles.

Test også at manglende nødvendige configtillegg avvises før image-operasjoner og endringer i installert tilstand. Dette kan dekkes av en fokusert lokal test dersom eksisterende dekning er tilstrekkelig.

Hold scenarioet avgrenset. Ikke gjenta hele matrisen av reboot-, crash- og hang-tester hvis disse allerede dekkes separat.

### 3. Lås feiloppførselen under installasjon

Undersøk eksisterende dekning og suppler for:

- Feil under `podman load`.
- Feil eller manglende image ved `podman image exists`.
- Feil ved restart eller `is-active` for en berørt systemd-tjeneste.

Bruk eksisterende komponentinstallasjon som utgangspunkt.

Test relevante observasjoner:

- Persistent config og credentials.
- Importarkiver.
- Route- og OIDC-klientregistreringer.
- Quadlet- og YAML-filer.
- Versjonsmarkører.
- Hvilke tjenester som er forsøkt restartet, og i hvilken rekkefølge.
- At upåvirkede sibling-komponenter beholdes.

Skille mellom feil før og etter at installasjonen begynner å endre tilstand. Ikke anta at installasjon er atomisk eller at rollback allerede finnes.

Ved servicefeil skal testen beskrive den faktiske delvis gjennomførte tilstanden og kontrollere at videre steg stopper, og at versjonsmarkører ikke feilaktig hevder en fullført installasjon.

Bruk konkrete feilscenarioer fremfor tester som bare gjentar interne funksjonskall.

Hvis du finner en eksisterende feil, dokumenter den med en fokusert reproduksjon. Ikke lås en kjent feil som ønsket oppførsel eller gjør urelaterte produktendringer uten å synliggjøre dem.

### 4. Test rotkommandoer fra en annen arbeidsmappe

Legg til integrasjonstester som starter de faktiske wrapper-scriptene fra en arbeidsmappe utenfor checkout/release:

```text
./deploy prepare
./deploy init-config <component>
./deploy install
./deploy uninstall
./build-bundle.sh
```

Bruk absolutt sti til wrapperen i testen.

Test kommandoene i riktig kontekst:

- `prepare` og bundling fra kildekoden.
- `init-config`, `install` og `uninstall` fra en utpakket bundle.

Verifiser at ressursstier og configvalg fungerer uavhengig av callerens arbeidsmappe, og at output ikke utilsiktet skrives dit.

Bruk isolerte midlertidige mapper og eksisterende stubs for Podman/systemd der det er hensiktsmessig. Ikke kjør produksjonskommandoer mot utviklerens virkelige hjem eller containermiljø.

Der realistisk testing krever tjenestebruker, brukerhjem og systemd-runtime, legg kontrollen i det eksisterende autoriserte labscenarioet fremfor å bygge et komplisert nytt mock-rammeverk.

### 5. Avgrensning

Ikke implementer:

- Oppdeling i `deployment/`-pakken.
- Ny CLI-arkitektur.
- Directory trust for fapolicyd.
- Passordrotasjon.
- Automatisk config- eller databasemigrering.
- Ny rollback-mekanisme.

Tester for den kommende pakkestrukturen, `python -B`, bytecode-ekskludering og directory trust hører til refaktoreringsoppgaven.

Behold eksisterende sikkerhetskontroller og testassertions. Ikke svekk dem for å få nye scenarioer til å passere.

### 6. Verifikasjon

Kjør etter endringene:

- Alle produkttester.
- Alle acceptance-harness-tester.
- Relevante ruff-, format-, pyright-, vermin- og shellcheck-kontroller med prosjektets eksisterende oppsett.

Behold Python 3.6-kompatibilitet for host-verktøy og produkttester.

Kjør det nye reelle oppgraderingsscenarioet dersom det etablerte labmiljøet er tilgjengelig og kjøring er autorisert. Ikke reset eller endre andre miljøer.

Skill tydelig mellom lokale tester, harness-tester og faktiske målmaskinkjøringer. Hvis labkjøring ikke er mulig, implementer scenarioet og rapporter at oppgraderingen fortsatt ikke er operasjonelt verifisert.

### 7. Leveranse

Rapporter kort:

1. Baseline-commit og testresultater før endringer.
2. Hvilken dekning som allerede fantes.
3. Nye tester og hvilke konkrete feil de beskytter mot.
4. Historisk og ny revision brukt i upgrade-scenarioet.
5. Testresultater, inkludert faktisk labkjøring.
6. Eventuelle oppdagede produktfeil og verifikasjonshull.
7. Om baseline er tilstrekkelig til å starte refaktoreringen.

Oppdater relevant testdokumentasjon med garantiene og begrensningene.

Foretrekk noen få sterke tester fremfor mange overlappende tester.

## 1. Deploy maintainability refactor

Status: done in 0.4.3 after items 10, 8, 9, 12 and 13; directory trust of each
release's `deployment/` package (add, wait, retire) is verified on the target by
the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS). See [verification](acceptance/DEPLOY-REFACTOR.md).
No existing installation requires migration: this implementation adds no migration,
old-module fallback or compatibility layer. The original task follows.

Refactor the deploy implementation for maintainability without redesigning the architecture or changing behavior.

Goal: a medium-experienced developer with some Python knowledge and little familiarity with this project should be able to understand the install/upgrade/uninstall flow quickly.

Keep the root commands unchanged:

- `./deploy prepare`
- `./deploy install`
- `./deploy uninstall`
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

Keep `./deploy` as the stable entrypoint and run Python with `-B`, e.g. `python3 -B -m deployment`, so trusted release code does not create `.pyc`/`__pycache__`. Preserve invocation from outside the release directory as well.

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

Gi den delte komponenten `core` navnet `platform` i `gunstein/podman_offline`.

Dette er en avgrenset navneendring. Behold arkitektur, funksjonalitet, sikkerhetskontroller og komponentisolasjon. Ikke gjennomfør modulrefaktoreringen samtidig.

### 1. Mål og begrepsbruk

Bruk `platform` om den delte komponenten som inneholder Identity, identitetsdatabasen og HTTPS-proxyen.

App1, app2 og help skal fortsatt ha samme avhengighet til denne komponenten som de i dag har til core.

Omdøpingen skal være konsekvent i aktiv kode, konfigurasjon, manifester, tester og dokumentasjon.

### 2. Kartlegg alle berørte navn før endringer

Undersøk blant annet:

- `components/core/`.
- `CORE_VERSION`.
- Bundle-definisjoner og descriptors.
- Funksjoner, variabler og feilmeldinger.
- Persistent komponentmappe og installed-markør.
- Quadlet-/systemd-navn.
- Pod-, Secret-, PVC- og ConfigMap-navn.
- Hostnames og `DB_HOST`.
- Registrerings- og importarkivnavn.
- Sertifikatgenerering og tilhørende filstier.
- Dev-script, acceptance-script og fixtures.
- README, verifikasjonsrapporter og backlog.

Skill mellom navn som tilhører komponenten, eksterne begreper og historiske referanser. Ikke bruk ukritisk global søk-og-erstatt.

### 3. Ønsket navngivning

Bruk blant annet:

```text
components/platform/
PLATFORM_VERSION

/var/lib/myproduct/platform/config.yaml
/var/lib/myproduct/installed/platform

myproduct-platform.service
myproduct-platform.kube
myproduct-platform.yaml
```

Ressurser med komponentprefikset `core-` skal få `platform-`, eksempelvis:

```text
platform-identity
platform-identity-postgres
platform-identity-data
platform-database-password
platform-routes
platform-clients
```

Oppdater alle referanser til de omdøpte ressursene.

Behold navn som ikke trenger å endres:

- Produktnavnet `myproduct`.
- Det delte nettverket `myproduct`.
- App1/app2/help og deres egne ressurser.
- Offentlige URL-paths som `/identity/`, `/app1/`, `/app2/` og `/help/`.
- Databasebrukere og databasenavn, eksempelvis `identity`.
- OIDC-klient-ID-er og scopes.
- Image-repositorier som ikke inneholder komponentnavnet.

Ikke endre credentials eller sertifikatinnhold bare fordi komponenten får nytt navn.

### 4. Bundle-modell og kommandoer

Bundle-modellen skal bli:

```yaml
app1: [platform, app1]
app2: [platform, app2]
help: [help]
```

Behold de tre eksisterende bundle-typene og deres filnavnmønstre:

```text
myproduct-app1-<version>-offline.tar.gz
myproduct-app2-<version>-offline.tar.gz
myproduct-help-<version>-offline.tar.gz
```

Det skal ikke opprettes en separat platform-bundle.

Behold rotkommandoene. Oppdater komponentargumentene:

```sh
./deploy init-config platform
./deploy uninstall platform
./deploy uninstall platform --delete-data
```

Gamle `core`-argumenter skal ikke utføre utilsiktede operasjoner. Gi en tydelig melding om nytt navn dersom de brukes.

Platform skal fortsatt:

- Installeres sammen med første app.
- Beholdes ved lik platform-versjon, med eksisterende regler for registreringsendringer og restart.
- Oppgraderes ved nyere platform-versjon.
- Avvise nedgradering.
- Ikke kunne avinstalleres mens app1, app2 eller help krever den.

### 5. Eksisterende installasjoner og migrering

Omdøpingen berører persistente ressursnavn. Den må ikke føre til at en eksisterende database erstattes av et nytt tomt volum uten at operatøren forstår det.

Denne oppgaven gir ikke tillatelse til å slette, resette eller migrere eksisterende produksjonsstate automatisk.

Bruk følgende avgrensning:

- Implementer den nye navngivningen for nye installasjoner.
- Ikke implementer automatisk migrering fra `core` til `platform`.
- Oppdag gammel core-layout og avvis operasjoner som ellers kan opprette en parallell platform-installasjon eller påvirke gammel state.
- Feil før generering av nye secrets, image-operasjoner, skriving av installert config/registreringer eller endringer i tjenester.
- Gi en tydelig melding om at gammel installasjon krever en separat migreringsprosedyre eller en eksplisitt ny installasjon.
- Avvis også blandet core/platform-state fremfor å gjette hvilken som er autoritativ.

Kontrollen må ikke bare bruke installed-markøren. Undersøk relevante gamle config-/tjenestefiler og persistente databasevolumer, siden avinstallasjon kan ha beholdt data.

Hold kontrollen konkret og avgrenset til produktets kjente ressurser. Feil ved nødvendige tilstandskontroller skal ikke tolkes som fravær.

Behold gamle filer og volumer urørt ved avvisning. Ikke legg til en automatisk «cleanup»-funksjon.

Dokumenter kompatibilitetsbruddet tydelig. Eksisterende installasjoner skal fortsatt kunne administreres med sin tidligere release.

### 6. Versjonering

Ikke publiser endringen under samme releaseversjon som eksisterende layout.

Oppdater `VERSION` og den nye `PLATFORM_VERSION` i tråd med prosjektets versjoneringspraksis, og forklar at navneendringen påvirker oppgraderingskompatibilitet.

Ikke endre image-tags dersom image-innholdet er uendret. Hvis image-innhold faktisk må endres, bruk nye tags og behold prinsippet om immutable release-tags.

### 7. Tester

Oppdater eksisterende tester til den nye navngivningen uten å svekke assertions.

Verifiser minst:

- Korrekte platform-prefikser og referanser i rendret YAML.
- Initialisering av platform-config.
- App-config arver de riktige felles verdiene fra platform.
- App1 og app2 kan hver være første installerte app.
- Help alene avvises.
- Lik, nyere og eldre `PLATFORM_VERSION` håndteres som før.
- Help-only og app-only upgrade beholder upåvirkede komponenter.
- Databasepassord og databasevolumer er koblet korrekt.
- Platform-uninstall blokkeres når dependenter finnes.
- `--delete-data` bare retter seg mot valgt komponents ressurser.
- Bundle-innhold, image-utvalg og checksums er korrekte.
- Gammel core-layout og blandet layout avvises uten endringer.
- Gamle core-databasevolumer oppdages selv om installed-markøren mangler.
- Feil ved tilstandskontroll gir kontrollert avvisning.

Behold historiske fixtures og historiske release-kilder når de faktisk skal representere gammel kode.

En test som tidligere oppgraderte fra en core-basert release kan ikke bare gis nye navn og fortsatt hevde å teste den historiske oppgraderingen. Behold relevant historisk dekning, men test tydelig avvisning ved denne nye kompatibilitetsgrensen.

### 8. Dokumentasjon og opprydding

Oppdater aktive beskrivelser, kommandoer, filstier og diagrammer til `platform`.

Søk gjennom hele repoet etter relevante forekomster av `core`, `CORE_VERSION` og `core-`.

Forklar bevisst beholdte forekomster, eksempelvis:

- Gammel-layout-deteksjon.
- Historiske fixtures.
- Tidligere verifikasjonsrapporter.
- Dokumenterte migreringsbegrensninger.

Ikke omskriv gamle testresultater eller historisk evidence slik at det ser ut som de ble kjørt med platform-layout.

Oppdater backlog med eventuell fremtidig migreringsoppgave. Ikke bland den inn i modulrefaktoreringen.

### 9. Verifikasjon og rapport

Kjør:

- Alle produkttester.
- Alle acceptance-harness-tester.
- Relevante ruff-, format-, pyright-, vermin- og shellcheck-kontroller.

Behold Python 3.6-kompatibilitet for host-verktøyene.

Kjør relevante nye installasjons- og livssyklusscenarioer i det etablerte labmiljøet dersom dette er tilgjengelig og autorisert. Ikke slett eksisterende state eller reset andre miljøer.

Skill mellom lokale tester, harness-tester og faktiske målmaskinkjøringer.

Rapporter:

1. Hvilke navn og filer som er endret.
2. Hvilke navn som bevisst er beholdt.
3. Hvordan gammel og blandet layout oppdages og avvises.
4. Konsekvensen for eksisterende installasjoner.
5. Versjonsendringer.
6. Testresultater og verifikasjonshull.
7. Arbeid som er utsatt, særlig eventuell migrering.

Foretrekk enkel og konsekvent navngivning fremfor et generisk alias- eller kompatibilitetsrammeverk.

## 9. Extract Identity into a separate component and bundle

Status: done in 0.4.0; verified by the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS), including the Identity upgrade
scenario. Platform and Identity are separate bundles with explicit dependencies. See [Identity verification](acceptance/IDENTITY-SPLIT.md). The original task follows.

Skill Identity ut av `platform` som en egen komponent med en egen separat offline-bundle i `gunstein/podman_offline`.

Dette er en funksjonell oppdeling som skal gjøres før den planlagte modulrefaktoreringen. Ikke gjennomfør modulrefaktoreringen samtidig.

### 1. Undersøk dagens løsning først

Les gjeldende kode, bundle-definisjoner, avhengighetsmodell, tester og dokumentasjon.

Platform er allerede ment som en separat bundle. Ikke ta utgangspunkt i den tidligere modellen hvor app-bundler inkluderte core/platform.

Gjenbruk eksisterende mekanismer for komponenter, bundles, versjoner og avhengigheter. Ikke innfør et parallelt system eller et generisk plugin-rammeverk.

Registrer baseline-commit og kjør eksisterende produkt- og acceptance-harness-tester før endringer.

### 2. Ønsket ansvarsdeling

Etter oppdelingen skal:

| Komponent | Ansvar |
|---|---|
| `platform` | HTTPS-proxy, proxyens TLS-materiale og offentlige ruteregistreringer |
| `identity` | IdentityServer, identitetsdatabase, databasepassord, signeringsmateriale, Data Protection-state, demobrukere og OIDC-klientregistreringer |
| `app1` | App1, egen database og egne credentials |
| `app2` | App2, egen database og egne credentials |
| `help` | Hjelpeinnhold og egen ruteregistrering |

Behold eksisterende eierskap og sikre livssyklusregler for delt nettverk og eventuell felles demo-CA. Ikke slett eller regenerer felles materiale som følge av oppdelingen.

Kartlegg alle eksisterende ressurser og filer før flytting, slik at ingen persistent state blir glemt.

### 3. Separate bundles og eksplisitte avhengigheter

Bruk følgende logiske modell:

| Bundle | Innhold | Avhengigheter |
|---|---|---|
| `platform` | Platform-komponenten | Ingen |
| `identity` | Identity-komponenten | Platform |
| `app1` | App1-komponenten | Platform og identity |
| `app2` | App2-komponenten | Platform og identity |
| `help` | Help-komponenten | Platform |

Hver bundle skal bare inneholde egne komponentressurser og nødvendige images, i tillegg til felles deploy-kode og nødvendige metadata/defaults.

App-bundler skal ikke inkludere eller installere platform/identity automatisk. Identity-bundlen skal ikke inkludere platform.

Manglende avhengighet skal gi en tydelig feil. Ikke forsøk nettverksnedlasting eller automatisk installasjon fra andre release-mapper.

Oppdater eksisterende bundle-bygging slik at alle definerte bundles produseres, inkludert separat identity-bundle, med prosjektets etablerte filnavnmønster.

### 4. Versjoner og kompatibilitet

Identity skal kunne versjoneres og oppgraderes uavhengig av platform og appene.

Bruk eksisterende versjoneringsmodell. Hvis denne bruker separate versjonsfiler, innfør en tilsvarende `IDENTITY_VERSION`. Ikke opprett et nytt versjoneringssystem hvis repoet allerede har en egnet modell.

Avhengigheter skal ha eksplisitte, dokumenterte versjonskrav. Gjenbruk eksisterende syntaks og sammenligningsregler. Hvis slike krav ikke finnes, innfør den minste mekanismen som dekker behovet, og begrunn valget.

Valider:

- At avhengighetene er installert.
- At deres versjoner tilfredsstiller innkommende bundles krav.
- At oppgradering av platform eller identity fortsatt tilfredsstiller kravene til installerte dependenter.

Oppbevar nødvendig avhengighetsmetadata som installert state. Kontrollene skal ikke avhenge av at gamle release-mapper fortsatt finnes.

Ikke anta kompatibilitet bare fordi en versjon er nyere.

Behold eksisterende regler for reinstallasjon og nedgradering der de fortsatt er relevante. Dokumenter eventuelle nødvendige endringer.

Alle avhengighets- og versjonsavvisninger skal skje før secret-generering, image-load, skriving av registreringer/tjenestefiler eller restart.

### 5. Skill ruteregistreringer fra OIDC-klientregistreringer

I dagens samlede løsning kan begge registreringstypene påvirke samme komponent. Etter oppdelingen skal eierskapet være tydelig:

- Platform konsumerer offentlige ruter.
- Identity konsumerer offentlige OIDC-klientregistreringer.
- Appene eier sine private klientnøkler og leverer bare offentlig klientmetadata og sertifikat til identity.
- Identity registrerer sin egen offentlige route hos platform.
- Help registrerer bare en route hos platform.

Behold indeksmekanismen som hindrer at gamle filer i importvolumer holder fjernede ruter eller klienter aktive.

Restartbeslutninger skal være separate:

| Endring | Forventet påvirkning |
|---|---|
| Bare app-route endres | Platform oppdateres/restartes |
| Bare OIDC-klientregistrering endres | Identity oppdateres/restartes |
| Begge endres | Begge berørte komponenter oppdateres/restartes |
| Ingen registrering endres | Ingen unødvendig restart av platform/identity |
| Help-route endres | Platform påvirkes, identity beholdes |
| Identity oppgraderes uten endret offentlig route | Identity påvirkes, platform beholdes |

Appenes containere skal ikke restartes bare fordi platform eller identity restartes. Et kort avbrudd i tilgjengelighet eller innlogging er noe annet enn restart av appene.

Ikke legg til nye registreringskommandoer hvis eksisterende installasjonsflyt kan håndtere dette tydelig.

### 6. Behold den offentlige innloggingskontrakten

Oppdelingen skal ikke samtidig endre:

- `/identity/`.
- Offentlig issuer-URL.
- Appenes klient-ID-er og scopes.
- Redirect-URI-er.
- `/app1/`, `/app2/` og `/help/`.
- Appenes cookie-navn og paths.

Oppdater interne hostnames og upstream-referanser der det er nødvendig.

Platform skal kunne kjøre og betjene help uten at identity er installert. Proxykonfigurasjonen må ikke kreve at en fraværende identity-tjeneste kan DNS-resolves ved oppstart.

Verifiser fortsatt delt innlogging mellom app1 og app2.

### 7. Config, secrets og database

Identity skal få egen komponentconfig og persistent mappe:

```text
components/identity/config.defaults.yaml
/var/lib/myproduct/identity/config.yaml
```

Følg eksisterende configmodell:

- Defaults brukes ved initialisering og dev.
- Produksjon bruker autoritativ persistent komponentconfig.
- Upgrade overskriver ikke eksisterende config.

Identity skal arve relevante felles verdier fra installert platform ved config-initialisering, etter samme etablerte prinsipp som øvrige dependenter.

Flytt identity-spesifikke DB-innstillinger, Secret-/volumdefinisjoner og generated-secret-oppføringer ut av platform.

Behold:

- Én persistent kilde for hvert databasepassord.
- Samsvar mellom PostgreSQL-server og klient.
- Beskyttelse mot å generere nytt passord når database-state allerede finnes.
- Runtime-bygging av `ConnectionStrings__Default`.
- Korrekt escaping og sikker feilhåndtering.
- Eksisterende databasebruker og databasenavn hvis det ikke finnes en nødvendig grunn til å endre dem.

Ikke innfør passordrotasjon, databaseprivilegium-endringer eller schema-migrering i denne oppgaven.

### 8. Eksisterende installasjoner: ikke migrer automatisk

Oppdelingen berører persistent identitetsdatabase, credentials, signeringsnøkler, Data Protection-state og klientregistreringer.

Denne oppgaven gir ikke tillatelse til automatisk flytting, sletting eller reinitialisering av eksisterende installert state.

Implementer ny layout for nye installasjoner. Oppdag eksisterende layout hvor identity fortsatt inngår i platform, og avvis inkompatibel installasjon/oppgradering før endringer.

Kontrollen skal også håndtere:

- Beholdte databasevolumer uten installed-markør.
- Blandet gammel og ny layout.
- Delvis eksisterende credentials eller tjenestefiler.
- Feil ved nødvendige tilstandskontroller.

Ikke bruk eksistensen av platform alene som tegn på gammel layout; platform er også en gyldig selvstendig komponent i den nye modellen.

Gi en tydelig melding om at den gamle layouten krever en separat migreringsprosedyre eller eksplisitt ny installasjon. La eksisterende state være urørt og fortsatt administrerbar med tidligere release.

Ikke lag tom identitetsdatabase eller nye signeringsnøkler som skjult erstatning for gammel state.

Dokumenter kompatibilitetsbruddet og før eventuell migrering som egen backlog-oppgave.

### 9. Avinstallasjon

Avhengigheter skal styre avinstallasjon:

- Identity kan ikke fjernes mens installerte apper krever den.
- Help skal ikke blokkere avinstallasjon av identity.
- Platform kan ikke fjernes mens identity, app1, app2 eller help krever den.

Når en app fjernes:

- Fjern dens route fra platform.
- Fjern dens offentlige OIDC-klientregistrering fra identity.
- Oppdater/restart bare de berørte tjenestene.
- Behold andre komponenters registreringer, tjenester og data.

Når identity fjernes uten dependenter:

- Fjern dens route fra platform.
- Behold platform og eventuell help.
- Behold identity-data som standard.

`--delete-data` skal bare slette valgt komponents egne data. Delt nettverk, felles CA og andre komponenters credentials skal ikke slettes.

### 10. Dev og bundling

Dev skal bruke samme komponentdeling og registreringsmodell som produksjon, selv om dev-helperen starter hele demosystemet samlet.

Oppdater image-bygging, image-utvalg og bundling etter behov.

Behold:

- Manifestdrevet image-utvalg.
- `imagePullPolicy: Never`.
- Ekskludering av privat state og bytecode.
- Checksums for alle leverte filer.
- Eksisterende fapolicyd- og SELinux-modell.

Identity-bundlen skal kunne transporteres og oppgraderes alene uten at platform- eller app-bundler må overføres på nytt.

Ikke endre immutable image-tags uten å bygge tilsvarende nye images.

### 11. Tester

Oppdater eksisterende tester uten å svekke sikkerhets- eller isolasjonskontroller. Legg til fokuserte tester for:

#### Installasjon og avhengigheter

- Platform kan installeres alene.
- Platform og help fungerer uten identity.
- Identity uten platform avvises før endringer.
- App uten identity avvises før endringer.
- Begge apprekkefølger fungerer etter platform og identity.
- Manglende og inkompatible avhengigheter gir tydelige feil.
- Oppgradering som bryter installerte dependenters versjonskrav avvises.

#### Registreringer og restart

- Bare route-endring påvirker platform.
- Bare klientendring påvirker identity.
- Begge endringer påvirker begge.
- Uendrede registreringer gir ingen unødvendig restart.
- Fjernede ruter/klienter er ikke aktive gjennom gamle importfiler.

#### Selvstendig identity-upgrade

Legg til et reelt acceptance-scenario som:

1. Installerer platform, identity og begge apper.
2. Oppretter brukerdata og verifiserer innlogging.
3. Bygger og overfører bare en nyere identity-bundle.
4. Installerer denne.
5. Verifiserer at ny identity-versjon og nytt image faktisk kjører.
6. Verifiserer innlogging og appenes databaseoperasjoner.
7. Verifiserer at identity-data og eksisterende credentials er beholdt.
8. Verifiserer at platform og appenes versjoner, tjenesteprosesser og konfigurasjon er uendret når registreringene ikke er endret.

Bruk en observerbar endring eller image-identitet som bevis; en oppdatert versjonsmarkør alene er ikke tilstrekkelig.

#### Avinstallasjon og gammel state

- Identity-avinstallasjon blokkeres av apper, men ikke help.
- Platform-avinstallasjon blokkeres av dependenter.
- Data beholdes som standard.
- Eksplisitt sletting er avgrenset til riktig komponent.
- Gammel samlet platform/identity-layout og blandet layout avvises uten endringer.

Behold relevant eksisterende dekning for help-only upgrade, app-only upgrade, offline installasjon, reboot og persistens. Tilpass forventningene til separate bundles.

### 12. Dokumentasjon

Oppdater README og relevant arkitektur-/testdokumentasjon slik at det er enkelt å forstå:

- Hva hver komponent eier.
- Hva hver bundle inneholder.
- Installasjonsrekkefølgen.
- Hvordan avhengigheter og versjonskrav kontrolleres.
- Hvem som konsumerer ruter og OIDC-klienter.
- Hvilke endringer som restarter hvilke tjenester.
- Hvordan identity oppgraderes alene.
- Hvilken state som er persistent.
- Hvorfor gammel samlet layout ikke oppgraderes automatisk.

Oppdater aktive kommandoeksempler og fjern foreldede antakelser om at app-bundler inneholder platform.

Ikke omskriv historiske verifikasjonsrapporter som om de ble kjørt med den nye arkitekturen.

### 13. Verifikasjon og leveranse

Kjør:

- Alle produkttester.
- Alle acceptance-harness-tester.
- Relevante ruff-, format-, pyright-, vermin- og shellcheck-kontroller.

Behold Python 3.6-kompatibilitet for host-verktøyene.

Kjør relevante faktiske acceptance-scenarioer i etablert labmiljø dersom dette er tilgjengelig og autorisert. Ikke reset eller endre andre miljøer.

Skill tydelig mellom lokale tester, harness-tester og målmaskinkjøringer. Hvis labkjøring ikke kan utføres, rapporter hvilke garantier som fortsatt er uverifisert.

Rapporter:

1. Ny komponent- og bundle-struktur.
2. Ressurser og state som har fått ny eier.
3. Avhengighets- og versjonsmodellen.
4. Restartreglene for ruter og klienter.
5. Konsekvensen for eksisterende installasjoner.
6. Testresultater og verifikasjonshull.
7. Utsatt arbeid, særlig migrering og modulrefaktorering.

Hold funksjonell oppdeling og senere modulrefaktorering adskilt. Foretrekk eksplisitte, enkle regler fremfor generelle abstraksjoner.


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

Erstatt katalognavnet `generated-certificates/` med `credentials/` for komponentenes passord, sesjonsnøkler, private nøkler og sertifikater i `gunstein/podman_offline`.

Navnet `generated-certificates` beskriver innholdet feil: mappen inneholder også databasepassord og sesjonsnøkler, og materialet kan være både generert og eksternt levert.

Dette er en avgrenset opprydding av filstier. Ikke kombiner den med modulrefaktorering, passordrotasjon eller andre arkitekturendringer.

### 1. Ingen migrering eller bakoverkompatibilitet

Det finnes ingen eksisterende installasjoner som skal oppgraderes.

Implementer bare den nye layouten:

- Ikke lag migreringskode.
- Ikke lag fallback til `generated-certificates/`.
- Ikke legg til aliaser eller kompatibilitetsgrener.
- Ikke lag en flytteprosedyre for gammel state.
- Bruk fersk, isolert state i testene.

Sletting av andre eksisterende filer, credentials eller databasevolumer inngår ikke i oppgaven.

Historiske verifikasjonsrapporter og evidence skal beholdes uendret.

### 2. Undersøk gjeldende kode

Ta utgangspunkt i faktisk repo-status, inkludert eventuell gjennomført omdøping fra core til platform og utskilling av identity.

Kartlegg aktive referanser til `generated-certificates`, blant annet i:

- Komponentenes config-defaults.
- `GENERATED_SECRETS`, `SECRET_FILES` og `VOLUME_FILES`.
- Sertifikatscript og andre generatorer.
- OIDC-klientdescriptors og offentlig sertifikatregistrering.
- Database-preflight.
- Dev-script og smoke-tester.
- Acceptance-script og persistensobservasjoner.
- Bundle-beskyttelse mot private filer.
- README, PKI-dokumentasjon og eksempler.

### 3. Ny standardstruktur

Bruk `credentials/` under hver komponents state-mappe.

For app1 kan strukturen være:
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

Dev bruker tilsvarende:
```
build/dev/app1/credentials/
```

Oppdater config, eksempelvis:
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

Bruk samme prinsipp for øvrige komponenter.

Behold eksisterende undermapper og filnavn når de fortsatt er meningsfulle. Ikke utvid oppgaven til en generell reorganisering av credentials.

Felles PKI/CA-state utenfor komponentenes `generated-certificates/` skal ikke flyttes som en bieffekt.

### 4. Behold eksisterende funksjonalitet

Dette er en endring av host-side filstier. Behold:

- Secret-navn og keys.
- PVC-/volumnavn.
- Pod- og tjenestenavn.
- Containerens mount-paths, eksempelvis `/run/secrets/database/password` og `/certificates`.
- Databasebrukere og databasenavn.
- OIDC-klient-ID-er, scopes og offentlige URL-er.
- Runtime-mekanismen for connection strings.
- Config-precedence og autoritativ persistent produksjonsconfig.

Oppdater alle host-side referanser, også sertifikatstier i `client.yaml` eller tilsvarende descriptors.

Unngå endringer i applikasjonskode og images når containergrensesnittet er uendret.

### 5. Behold genererings- og sikkerhetsreglene

Databasepassord og sesjonsnøkler skal fortsatt genereres gjennom eksisterende `GENERATED_SECRETS`.

Sertifikatscriptet skal skrive sitt materiale til de nye stiene. Ikke flytt databasepassordgenerering tilbake til sertifikatscriptet.

Behold eksisterende garantier:

- Manglende hemmeligheter opprettes bare når dette er tillatt.
- Eksisterende gyldige filer beholdes byte-for-byte ved restart/redeploy.
- Tomme eller ugyldige filer gir feil.
- Manglende databasepassord med eksisterende databasevolum avvises.
- Private fil- og katalogrettigheter beholdes.
- Symlink-escape og utrygge output-stier avvises.
- Credentials og komplette connection strings eksponeres ikke i logger.

Disse kontrollene gjelder vanlig drift av den nye layouten. Det skal ikke innføres egne kontroller eller fallback-regler for gammel layout.

### 6. Dev, bundling og acceptance

Oppdater alle helper-script som leser, genererer, overfører eller sammenligner credentials.

Nye dev- og produksjonsinstallasjoner skal bruke samme layout under sine respektive komponentmapper.

Bundle-beskyttelsen skal fortsatt hindre at credentials følger med offline-arkivene, inkludert kopiering gjennom symlink-aliaser.

Behold kontrollene som følger deklarerte secret-filer. Ikke erstatt dem med bare et enkelt navnefilter for mappen `credentials`.

Behold checksum-garantier, offline-egenskaper og eksisterende SELinux-/fapolicyd-kontroller.

### 7. Tester

Oppdater eksisterende tester og legg bare til fokuserte regresjoner der dekning mangler.

Verifiser:

- Defaults og config-initialisering bruker `credentials/`.
- Genererte filer havner på riktige stier i dev og produksjon.
- Sertifikatscriptet bruker de nye stiene.
- OIDC-klientregistrering finner riktig offentlig sertifikat.
- Server og klient fortsatt bruker samme databasepassord.
- Restart/redeploy beholder credentials byte-for-byte.
- Database-preflight fortsatt avviser manglende passord når volumet finnes.
- Secret-/PVC-navn og container-mounts er uendret.
- Private filer og symlink-aliaser ikke havner i bundles.
- Smoke- og acceptance-script bruker de nye plasseringene.

Ikke legg til migreringstester eller tester som krever støtte for gamle configstier.

### 8. Dokumentasjon og opprydding

Dokumenter rollene tydelig:

- `credentials/` inneholder passord, nøkler og sertifikater.
- `GENERATED_SECRETS` angir hvilke filer som genereres.
- `SECRET_FILES` og `VOLUME_FILES` angir hvordan filene leveres til containerne.

Søk gjennom hele repoet etter `generated-certificates`. Oppdater aktive referanser i kode, config, tester, eksempler og operatørdokumentasjon.

Behold historiske rapporter og eventuelle fixtures som eksplisitt representerer en historisk release. Forklar gjenværende forekomster i sluttrapporten.

Ikke marker tidligere labresultater som verifikasjon av denne endringen.

### 9. Verifikasjon og leveranse

Kjør:

- Alle produkttester.
- Alle acceptance-harness-tester.
- Relevante ruff-, format-, pyright-, vermin- og shellcheck-kontroller med prosjektets eksisterende oppsett.

Behold Python 3.6-kompatibilitet for host-verktøyene.

Kjør relevante ferske installasjons-/e2e-scenarioer i etablert labmiljø dersom dette er tilgjengelig og autorisert. Ikke reset andre miljøer.

Skill tydelig mellom lokale tester, harness-tester og faktisk container-/målmaskinverifikasjon. Oppgi hva som ikke kunne kjøres.

Rapporter kort:

1. Hvilke stier og filer som er endret.
2. Eventuelle bevisst beholdte historiske referanser.
3. Testresultater og verifikasjonshull.
4. Bekreftelse på at det ikke er innført migreringskode eller fallback til gammel layout.

Foretrekk en enkel, konsekvent navneendring fremfor nye abstraksjoner.

## 13. Retry-safe install and uninstall

Status: done in 0.4.2. Failure injection is verified in fresh local processes
(`tests/test_retry.py`); on real hosts the normal lifecycle is verified by
the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS), but no failure is injected there. See [retry verification](acceptance/RETRY-SAFETY.md).
This is a bounded correctness fix for retrying failed operations, not a transaction
framework or module refactor. The full agent message follows, with Markdown
formatting adjusted for this document.

Implementer trygg gjentakelse etter feil i installasjon og avinstallasjon i gunstein/podman_offline.

Oppgaven gjelder to konkrete feil i deploy.py:

1. Et nytt installasjonsforsøk kan hoppe over nødvendige omstarter av Identity/platform etter et mislykket forsøk.
2. En avinstallasjon kan bli stående halvferdig, samtidig som neste forsøk avvises fordi installasjonsmarkøren allerede er slettet.

Dette er en avgrenset feilretting. Ikke gjennomfør den planlagte modulrefaktoreringen, endre komponentarkitekturen eller innfør et generelt transaksjonsrammeverk.

### 1. Les og forstå eksisterende flyt

Les først:

- install_components()
- install_component_plan()
- write_registrations()
- registration_stage()
- component_imports()
- uninstall()
- relevante tester for installasjonsfeil, komponenter og Identity

Funksjonsnavnene kan ha endret seg. Finn tilsvarende kode i gjeldende branch.

Komponentmodellen er:

- platform eier proxy og ruteregistreringer.
- identity eier IdentityServer og klientregistreringer.
- app1 og app2 avhenger av platform og identity.
- help avhenger av platform.

Ruteregistreringer og klientregistreringer skal fortsatt behandles separat. En route-endring skal normalt påvirke platform, mens en klientendring skal påvirke identity.

### 2. Feilen ved installasjon

Dagens flyt skriver registreringer før alle nødvendige tjenester er restartet.

Et eksempel:

1. App1 har en ny route og klientregistrering.
2. Installer skriver begge registreringene til persistent state.
3. Restart av app1 feiler.
4. Installer avslutter før Identity og platform er restartet.
5. Operatøren kjører samme installasjon på nytt.
6. Registreringsfilene har allerede riktig innhold og regnes som uendret.
7. Identity og platform blir derfor ikke restartet.

Det andre forsøket kan rapportere suksess selv om de kjørende tjenestene ikke har tatt i bruk registreringene.

En tilsvarende feil kan oppstå dersom skriving av importarkiver eller restart av en av registreringseierne feiler.

Krav: Et nytt installasjonsforsøk må fullføre nødvendig arbeid fra forrige forsøk. Det er ikke tilstrekkelig å sammenligne nye registreringer med filene som allerede ligger på disk.

### 3. Løsning for installasjon

Velg en enkel, eksplisitt mekanisme for å huske ufullført arbeid mellom prosesskjøringer.

En liten persistent pending-fil er et mulig valg. Den kan for eksempel angi at registreringene til identity og/eller platform ennå ikke er bekreftet tatt i bruk.

Det konkrete filnavnet og formatet kan tilpasses eksisterende kode. Følg disse reglene:

- Registrer nødvendig arbeid før endringer som ellers kan gjøre at behovet blir glemt.
- Pending-state skal overleve at installer avslutter eller prosessen avbrytes.
- Ved neste forsøk skal pending-state leses og kombineres med eventuelle nye endringer.
- Nødvendige importarkiver må skrives på nytt dersom forrige forsøk ikke fullførte dette.
- Berørte tjenester må restartes og kontrolleres med eksisterende suksesskriterier.
- Fjern bare pending-state for arbeid som faktisk er fullført.
- Hvis en restart eller kontroll feiler, skal ufullført arbeid fortsatt være registrert.
- Et nytt forsøk med identiske registreringsfiler må fortsatt utføre pending arbeid.

Pending-state skal inneholde bare nødvendig metadata, aldri passord, private nøkler eller komplette konfigurasjoner.

Bruk eksisterende mønstre for private filrettigheter og trygg filskriving. Ikke følg symlinker til vilkårlige steder. Ugyldig pending-state skal gi en tydelig feil, ikke ignoreres.

Ikke løs problemet ved å restarte alle tjenester på hver installasjon.

Bevar normal oppførsel:

- Uendrede registreringer uten pending arbeid skal ikke restarte Identity/platform.
- Bare route-endring skal normalt restarte platform.
- Bare klientendring skal normalt restarte identity.
- Begge endringer skal restarte begge.
- Sibling-applikasjoner skal ikke restartes som en bivirkning.

Hvis du velger en annen løsning enn pending-state, må den dekke de samme feiltilfellene og forklares tydelig.

### 4. Feilen ved avinstallasjon

Dagens avinstallasjon sletter blant annet installasjonsmarkøren før hele operasjonen er fullført.

Et eksempel:

1. App1 stoppes.
2. Quadlet/YAML og registreringer slettes.
3. Installasjonsmarkøren slettes.
4. Restart av Identity eller platform feiler.
5. Operatøren kjører uninstall på nytt.
6. Installer avviser forsøket fordi app1 ikke lenger regnes som installert.

Med --delete-data kan også volumfjerning feile etter at installasjonsmarkøren er borte.

Krav: Operatøren skal kunne gjenta avinstallasjonen og fullføre den uten manuell rekonstruksjon av markører, YAML eller registreringer.

### 5. Løsning for avinstallasjon

Gjør avinstallasjonen mulig å fortsette etter delvis gjennomføring.

Ikke løs dette bare ved å flytte sletting av installasjonsmarkøren til slutten. Tidligere slettet YAML eller andre filer kan fortsatt være nødvendige for å vite hva som gjenstår.

Før destruktive steg må nødvendig informasjon være validert og bevart slik at neste kjøring vet:

- hvilken komponent som avinstalleres
- om operasjonen inkluderer --delete-data
- hvilke tjenester som skal stoppes eller oppdateres
- hvilke registreringseiere som må oppdateres
- hvilke konkrete volumer som eventuelt skal slettes

Bruk en liten, eksplisitt tilstand for pågående avinstallasjon dersom det er nødvendig. Ikke lag en generell operasjonsmotor.

Følg disse kravene:

- Avhengighetskontroller skal fortsatt kjøres før avinstallasjonen starter.
- En komponent med pågående avinstallasjon må ikke behandles som en frisk, tilgjengelig avhengighet for nye installasjoner.
- Gjentatt sletting av filer som allerede er fjernet av samme operasjon skal være trygg.
- Manglende volum ved retry kan regnes som allerede slettet.
- Feil ved kontroll av et volum skal fortsatt være en feil; det må ikke tolkes som at volumet mangler.
- Volumlisten skal komme fra validert, komponentavgrenset informasjon.
- Ikke utvid sletting til andre komponenters volumer eller state.
- Oppdatering av registreringer og nødvendige omstarter må kunne gjentas.
- Marker operasjonen som fullført først når alle nødvendige steg har lykkes.
- Rydd opp i pending-state etter fullført operasjon.

Bevar forskjellen mellom:

- uninstall: behold data, config og credentials.
- uninstall --delete-data: slett bare den valgte komponentens relevante data og state.

Et retry må ikke utilsiktet endre en avinstallasjon uten datasletting til en avinstallasjon med datasletting. Definer og dokumenter hvordan avvikende flagg håndteres. Den enkleste løsningen er å kreve samme valg som da operasjonen startet og gi en tydelig feil ved avvik.

### 6. Samspill mellom installasjon og avinstallasjon

Definer enkel og tydelig oppførsel dersom en ny kommando møter en ufullført operasjon.

For eksempel:

- install må ikke ignorere en pågående avinstallasjon av samme komponent.
- uninstall må ikke slette eller overse pending registreringsarbeid på en måte som etterlater feil runtime-state.
- En operasjon må ikke fjerne pending arbeid som tilhører en annen operasjon.

Det er akseptabelt å avvise en konflikt med en tydelig melding om hvilken kommando operatøren må kjøre for å fullføre først.

Ikke innfør automatisk rollback eller automatiske reparasjoner av ukjent state.

### 7. Tester for installasjon

Bruk eksisterende testoppsett og feilinjeksjon. Legg minst til følgende scenarioer:

#### A. App-restart feiler etter registreringsskriving

1. Installer en app med endret route og klientregistrering.
2. La app-restart feile etter at registreringene er skrevet.
3. Verifiser at installasjonen feiler.
4. Kjør samme installasjon igjen uten feilen.
5. Verifiser at nødvendige importarkiver oppdateres og både Identity og platform restartes.
6. Verifiser at pending-state fjernes etter suksess.

#### B. En registreringseier feiler

1. La restart eller etterfølgende kontroll av Identity/platform feile.
2. Kjør installasjonen igjen.
3. Verifiser at ufullført arbeid utføres, selv om registreringsfilene er identiske.

#### C. Importarkivskriving feiler

1. La skriving av et nødvendig importarkiv feile etter at registreringer er skrevet.
2. Kjør installasjonen igjen.
3. Verifiser at importarkivet faktisk oppdateres før operasjonen regnes som fullført.

#### D. Normal installasjon er fortsatt avgrenset

Verifiser fortsatt de fire kombinasjonene:

- ingen registreringsendring
- bare route-endring
- bare klientendring
- begge endringer

Uten pending arbeid skal ingen ekstra fellestjenester restartes.

### 8. Tester for avinstallasjon

Legg minst til følgende scenarioer:

#### A. Restart av registreringseier feiler

1. Start avinstallasjon av en installert app.
2. La restart av Identity eller platform feile.
3. Kjør avinstallasjonen igjen.
4. Verifiser at den fullføres selv om noen filer allerede er slettet.
5. Verifiser at registreringene er fjernet fra de oppdaterte importarkivene.
6. Verifiser at pending-state ryddes opp.

#### B. Volumsletting feiler

1. Start uninstall --delete-data med flere komponentvolumer.
2. La sletting av et senere volum feile etter at et tidligere volum er fjernet.
3. Kjør samme kommando igjen.
4. Verifiser at allerede slettede volumer håndteres og resterende arbeid fullføres.
5. Verifiser at andre komponenters state er uendret.

#### C. Avinstallasjon uten datasletting

Et mislykket forsøk og retry skal bevare bytes i config og credentials samt databasevolumer.

#### D. Konflikter og ugyldig state

Test:

- retry med avvikende valg for --delete-data
- installasjon mens samme komponent har pågående avinstallasjon
- ny installasjon som krever en komponent med pågående avinstallasjon
- ugyldig eller symlinket pending-state

Retry-testene må representere en ny prosesskjøring: løsningen skal ikke være avhengig av variabler fra første forsøk. Bruk samme persistente testkatalog, men nullstill midlertidig tilstand mellom forsøkene.

### 9. Avgrensning og kompatibilitet

Bevar:

- eksisterende rotkommandoer
- Python 3.6-kompatibilitet for deploy-koden
- bundle-avhengigheter og versjonsregler
- checksums og offline installasjon
- eksisterende secret-generering og credential-stier
- SELinux- og fapolicyd-kontroller
- komponentisolasjon og persistente data

Ikke:

- flytt deploy til en Python-pakke som del av denne oppgaven
- legg til passordrotasjon
- regenerer credentials ved retry
- innfør ny migreringslogikk
- endre normale tjenesteomstarter utover det feilrettingen krever
- legg pending-state i release-katalogen eller offline-bundlen

### 10. Dokumentasjon, sjekker og rapport

Dokumenter kort hvordan operatøren gjentar en mislykket installasjon eller avinstallasjon, og hvordan eventuelle konflikter rapporteres.

Kjør:

- produkttestene
- acceptance-harness-testene
- ruff
- formatkontroll
- pyright
- vermin
- shellcheck

Legg bare til nye reelle acceptance-scenarioer dersom de gir nødvendig dekning utover målrettede feilinjeksjonstester. Ikke påstå at stubbet testing beviser faktisk Podman/systemd-oppførsel.

Rapporter:

1. Årsaken til de to feilene.
2. Hvordan ufullført arbeid lagres og fullføres ved retry.
3. Hvilke filer som er endret.
4. Hvilke nye feilscenarioer testene dekker.
5. Faktiske testresultater og sjekker som ikke kunne kjøres.
6. Eventuelle begrensninger.

Foretrekk små, tydelige funksjoner og eksplisitte steg. Målet er at en middels erfaren Python-utvikler enkelt skal kunne forstå hvorfor et nytt forsøk er trygt.

## 14. Tighten app credential delivery and remove unused API secret

Status: done in 0.4.4; delivery and modes are checked on the target
(`08-credentials`) by the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS); see
[credential delivery](acceptance/CREDENTIAL-DELIVERY.md). The original agent message follows.

Rett credential-håndteringen i `gunstein/podman_offline` med en liten, målrettet endring.
Behold dagens komponentarkitektur og offline installasjonsmodell.

### 1. Bakgrunn og bekreftede observasjoner

App1 og app2 deklarerer `credentials/todo/session-key` i `GENERATED_SECRETS`.
Hele `credentials/todo/`, inkludert session key og privat klientnøkkel, leveres i dag
gjennom `VOLUME_FILES` til appens signing-PVC og monteres skrivebeskyttet på
`/certificates` i backend. Frontend får ikke denne mounten.

`deployment/render.py: generate_secrets()` oppretter originalfilen med modus `0600`.
`write_file_archives()` oppretter selve arkivet med `0600`, men `normalize()` setter
vanlige filer inne i arkivet til `0644`. Dette er lokalt reprodusert med en syntetisk
session key. Faktiske rettigheter etter Podman-import er ikke verifisert her.
PVC-bruk alene er ikke et bekreftet sikkerhetshull; vurder tilgang og livssyklus,
ikke bare navnet på YAML-ressursen.

Identity deklarerer også `credentials/app/ApiResources__0__ApiSecrets__0__Value` og
leverer den via `identity-api-secrets` og `envFrom`. Gjennomgangen fant ingen bruk
av verdien i dagens Identity-kode. Bekreft dette før den fjernes.

### 2. Kartlegg før endring

Les `AGENTS.md` dersom den finnes, README, ARCHITECTURE og relevante tester.
Følg de faktiske filene gjennom:

- `components/app1/config.defaults.yaml` og tilsvarende for app2/identity.
- Komponentenes manifester og `scripts/generate-certificates.sh`.
- `deployment/render.py`: generering, filgrupper, Secret/PVC og importarkiver.
- `deployment/deploy.py`: installasjon, retry og avinstallasjon.
- `apps/todo-backend/app.py` og `apps/identity/Program.cs`.

Session key brukes som Flask `SECRET_KEY` til sesjonscookies. Den private
klientnøkkelen brukes til `private_key_jwt` mot Identity. Dette er forskjellige
hemmeligheter med forskjellige oppgaver; ingen av dem skal leveres til frontend.

### 3. Stram inn levering og rettigheter

Foretrekk å levere session key og privat klientnøkkel gjennom eksisterende
`SECRET_FILES`, som for databasepassord og Identitys signeringsnøkkel. Avklar at
valgt løsning støttes av målversjonen av Podman og eksisterende `.kube`-flyt.
En liten credential-gruppe per app er tilstrekkelig; ikke innfør et nytt rammeverk.

- Behold persistente originalfiler og samme bytes gjennom normale oppgraderinger,
  gjentatt installasjon og retry. Ikke regenerer eller roter nøkler ved flyttingen.
- Sørg for eksplisitte restriktive rettigheter for hemmelige filer i containeren,
  for eksempel `0400` eller `0600`, med eierskap som passer prosessen som leser dem.
  Verifiser at Podman faktisk anvender feltene; ikke anta Kubernetes-oppførsel.
- Behold skrivebeskyttet mount og tilgang bare i backend. Behold eksisterende
  filstier i containeren hvis dette gir den enkleste og tydeligste løsningen.
- Offentlige sertifikater kan følge samme beskyttede gruppe når det forenkler
  mounten; ikke skap ekstra abstraksjoner bare for å skille offentlige filer.
- Session key og privat klientnøkkel skal ikke samtidig bli liggende i et aktivt
  generert `VOLUME_FILES`-arkiv etter endringen.
- Ikke sett alle generelle importfiler til `0600` uten å vurdere offentlige
  payloads, katalogtilgang og containernes UID/GID. Dersom hemmeligheter fortsatt
  må leveres gjennom importarkiv, begrunn valget og bevar restriktive rettigheter.
- Bevar avinstallasjonens skille mellom å beholde state og eksplisitt
  `--delete-data`. Sletting skal fortsatt være avgrenset til valgt komponent.

En Secret gir ikke automatisk kryptering eller minnebasert lagring i Podman.
Renderet YAML med base64-kodede secrets er sensitiv. Beskytt YAML, originalfiler,
eventuelle arkiver og runtime-kopier, og unngå verdier i logger og testutskrifter.

### 4. Fjern ubrukt API-secret

Hvis kartleggingen bekrefter at API-secret-en er ubrukt, fjern dens generering,
Secret-deklarasjon, `envFrom`-referanse og eventuelle unødvendige katalogopprettelser.
Oppdater relevante tester og dokumentasjon. Ikke fjern legitime API-scopes,
klientsertifikatautentisering, databasepassord eller Identitys tokensignering.
Ingen automatisk sletting av ukjente eksisterende credential-filer.

### 5. Tester og dokumentasjon

Legg til målrettede tester som verifiserer:

- Riktig leveringsmåte, mount, eierskap/rettighetsinnstillinger og uendrede
  credential-bytes. Undersøk faktisk generert YAML og eventuelle arkivmedlemmer.
- Separate nøkler for app1 og app2 og ingen credential-mount i frontend.
- Ingen duplisert privat nøkkel/session key i appens genererte importarkiv.
- Installasjon, upgrade og retry beholder nøklene, samt fortsatt trygg og avgrenset
  avinstallasjon med og uten datasletting.
- Ubrukt API-secret genereres eller refereres ikke lenger.
- Private filer og bytecode følger fortsatt ikke med i offline-bundles.

Oppdater README og relevant test-/arkitekturdokumentasjon med faktisk filflyt og
skillet mellom en hemmelig verdi og YAML-typen `Secret`. Brukerens diagramskisser
er foreløpig til diskusjon; ikke legg dem inn uten egen avtale.

Kjør repoets dokumenterte produkttester, acceptance-harness-tester, ruff,
formatkontroll, pyright, vermin og shellcheck. Behold Python 3.6-kompatibilitet
for host-verktøyene. Oppdater berørte image-/releaseversjoner etter repoets
konvensjoner dersom endringen krever nye images; ikke gjenbruk en uforanderlig tag.

Beskriv eller utvid målrettet labverifikasjon av reelle filmoduser, lesetilgang,
innlogging, sesjoner etter restart/upgrade, klientautentisering og avinstallasjon.
Ikke start destruktive VM-/snapshot-kjøringer uten eksplisitt autorisasjon.
Skill mellom lokale tester, statisk vurdering og faktisk Podman-verifikasjon.

### 6. Avgrensning og leveranse

Ingen eksisterende installasjoner trenger migrering fra gamle layouts. Ikke bygg
migreringskode, fallback, automatisk nøkkelrotasjon eller en ny secret manager.
Normale oppgraderinger i den støttede modellen skal fortsatt bevare private filer
og data. Ikke redesign Flask-/OIDC-autentiseringen eller tilpass demoen til en
hypotetisk C#/GraphQL-applikasjon som del av denne oppgaven.

Rapporter valgt løsning, konkrete endringer, testresultater og hva som gjenstår i
lab. Forklar hvilke sikkerhetsegenskaper som faktisk er forbedret, uten å påstå at
et bytte fra PVC til Secret alene gir kryptering eller en ny isolasjonsgrense.

## 15. Remove obsolete legacy layout refusal checks

Status: done in 0.4.5; fresh installs without the removed checks are verified by
the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS); see [layout cleanup](acceptance/LEGACY-CHECK-CLEANUP.md). The original
agent message follows. No existing installations require migration.

Melding til agenten:

Fjern kontrollene som bare oppdager og avviser historisk core-layout eller
kombinert platform/Identity-layout i `gunstein/podman_offline`.
`core-identity-data` i `deployment/deploy.py` er ett konkret eksempel; dagens
Identity-volum heter `identity-data`. Det gamle navnet brukes til avvisning,
ikke som et aktivt databasevolum.

- Kartlegg `reject_legacy_layout()`, `reject_combined_platform()`,
  `legacy_volume_exists()` og tilsvarende kontroller i sertifikat-/dev-script,
  tester og aktive acceptance-scenarioer. Ta utgangspunkt i siste repo-status.
- Fjern avvisningskontrollene, tilhørende kall og feiltekster om separate
  migreringsprosedyrer. Ikke bare erstatt gamle volumnavn med nye navn i disse
  kontrollene; dagens volumer skal ikke avvises som historisk state.
- Oppdater tester og aktiv operatørdokumentasjon slik at de beskriver dagens
  støttede layout. Behold historiske rapporter, evidence og fixtures som
  eksplisitt representerer gamle releaser; forklar gjenværende gamle navn.
- Ikke innfør migrering, fallback, aliaser, kompatibilitetsgrener, automatisk
  opprydding eller sletting/flytting av gamle filer eller volumer. Oppgavene 4
  og 11 skal ikke implementeres; de er historiske forslag som er erstattet av
  presiseringen om at ingen eksisterende installasjoner trenger migrering.
- Behold normal oppgradering og retry i dagens komponentmodell: config,
  credentials og data skal fortsatt bevares. Behold database-preflight,
  avhengighets-/versjonskontroller, pending-state-validering, komponentisolasjon,
  sikre filstier/rettigheter og bundle-beskyttelse.

Kjør produkttester, acceptance-harness-tester og repoets relevante ruff-, format-,
pyright-, vermin- og shellcheck-kontroller samt `git diff --check`. Behold Python
3.6-kompatibilitet for host-verktøyene. Rapporter hva som er fjernet, hvilke
historiske referanser som er beholdt, testresultater og eventuelle labhull.

## 16. Combine secret generation and file delivery declarations

Status: done in 0.4.6 after item 14; source-level generate is supported
for both delivery groups and verified (examples `03-example-*` and generated
database passwords) by the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS). See [file sources](acceptance/FILE-SOURCES.md) for
verification and remaining lab work. The original agent message follows.

Melding til agenten:

Forenkle config-modellen i `gunstein/podman_offline` slik at eventuell generering
deklareres sammen med filene som leveres gjennom `SECRET_FILES` eller
`VOLUME_FILES`. Fjern behovet for en separat `GENERATED_SECRETS`-liste og dobbelt
vedlikehold av samme filsti. Målet er at en middels erfaren utvikler enkelt skal
forstå både hvor en fil kommer fra og hvordan den leveres til containeren.

Et mulig format, som et utgangspunkt for vurdering, er:

```yaml
SECRET_FILES:
  app2-database-password:
    directory: credentials/database
    generate:
    - password
  identity-signing:
    directory: credentials/identity
```

Her er `generate` relativt til den deklarerte katalogen og angir bare filer som
skal opprettes hvis de mangler. Uten `generate` brukes eksisterende filer.
Støtt samme prinsipp for `VOLUME_FILES`, siden genererte sesjonsnøkler i dagens
modell leveres gjennom volumer. Undersøk om formatet bør bruke en liste med
filkilder fremfor én `directory`, slik at nødvendig støtte for flere kildefiler
og kataloger ikke forsvinner. Velg én enkel og konsekvent modell; ikke innfør et
generelt generator-/pluginrammeverk eller to parallelle config-formater.

- Les gjeldende defaults, config-validering, generering, rendering, database-
  preflight, bundling, dev-/sertifikatscript og tester før formatet bestemmes.
- Behold dagens genereringsregler og tidspunkt: bare eksplisitt deklarerte
  manglende filer opprettes der dette er tillatt. Eksisterende gyldige filer
  beholdes byte-for-byte; tomme/ugyldige filer gir feil. Manglende databasepassord
  med eksisterende databasevolum skal fortsatt avvises før generering.
- Sertifikater og private signeringsnøkler skal fortsatt forberedes separat.
  Den nye deklarasjonen skal ikke gjøre deploy til en sertifikatutsteder.
- Behold credential-stier, Secret-navn og keys, volum-/PVC-navn, container-mounts,
  passordformat/-lengde, config-precedence og autoritativ persistent config.
  Behold sikre filstier, symlink-kontroller og private fil-/katalogrettigheter.
- Bundle-beskyttelsen må fortsatt følge deklarerte private filer, inkludert
  symlink-aliaser, og ikke bare filtrere på katalog- eller filnavn. Credentials
  og komplette connection strings skal ikke eksponeres i logger eller bundles.
- Oppdater alle aktive configs, eksempler, hjelpere, tester og dokumentasjon til
  den nye deklarasjonen. Behold historiske rapporter og eksplisitte historiske
  release-fixtures. Ingen eksisterende installasjoner trenger config-migrering:
  ikke lag migreringskode, fallback, aliaser eller støtte for gammelt format.

Legg til målrettet dekning av genererte og eksternt leverte filer, begge
leveringsmåter, ugyldige deklarasjoner/stier, config-initialisering, database-
preflight, byte-bevaring ved restart/redeploy/retry og bundle-beskyttelse.
Behold config, credentials og data ved normale oppgraderinger i den nye modellen.
Ikke kombiner med passordrotasjon, endret komponentarkitektur eller bred
modulrefaktorering.

Kjør produkttester, acceptance-harness-tester og relevante ruff-, format-,
pyright-, vermin- og shellcheck-kontroller samt `git diff --check`. Behold Python
3.6-kompatibilitet for host-verktøyene. Rapporter valgt format, endrede filer,
testresultater og hva som eventuelt gjenstår å verifisere i lab.

## 17. Use an init container for database preparation in one demo app

Status: done in 0.4.8. App1 uses a real schema-preparation init container;
app2 retains backend initialization. Verified by the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS) (database
authentication steps; the renamed `orders` init container exits 0). Local checks and remaining real target
verification are documented in [app1 init verification](acceptance/APP1-INIT.md).
The original agent message follows.

Melding til agenten:

La én av appene i `gunstein/podman_offline` bruke `initContainers` til reell
databaseklargjøring før backend starter. Velg og begrunn en egnet app ut fra
gjeldende kode og manifests, fortrinnsvis app1 eller app2. Dagens Todo-backend
oppretter tabellen i oppstartskoden, mens Identity klargjør brukertabellen selv.
Flytt et konkret, nødvendig klargjøringssteg til init-containeren; ikke legg til
en symbolsk init-container som bare kjører `echo` eller en ventekommando.

- Undersøk Podman/Quadlet-oppstarten og hvor PostgreSQL kjører før løsningen
  velges. En init-container må ikke vente på en ordinær databasecontainer i
  samme pod som først starter etter init-containeren. Dokumenter hvordan
  databasen faktisk blir tilgjengelig før klargjøringssteget kjører.
- Backend skal starte først etter vellykket init. Databaseventing skal være
  tidsbegrenset, og init-feil skal gi en tydelig feil uten å eksponere passord
  eller komplette connection strings. Bruk appens eksisterende credential-
  mekanisme og samme databasepassord som databasen og backend.
- Klargjøringen skal være idempotent: fersk installasjon oppretter nødvendig
  skjema; restart, redeploy og retry bevarer eksisterende databaseinnhold og
  credentials. Ikke innfør passordrotasjon, destruktive resets, migrering fra
  historiske layouts eller et generelt database-migreringsrammeverk.
- Behold den andre appens virkemåte. Appene deler backend-kilde/image i dagens
  modell; unngå utilsiktet å kreve init-klargjøring også i appen som ikke endres.
  Behold isolasjon fra platform, identity og sibling-appens data og tjenester.
- Oppdater nødvendig appkode, manifests, dev-flyt, bundling, tester og README.
  Offline-bundlen skal inneholde alle nødvendige images; ingen nedlasting av
  kode eller pakker ved init. Følg repoets regler for nye image-/releaseversjoner.

Legg til målrettede tester for oppstartsrekkefølge, init-feil, tidsavbrudd og
gjentatt klargjøring uten datatap. Kjør produkttester, acceptance-harness-tester
og relevante lint-, format-, type-, kompatibilitets- og shellkontroller samt
`git diff --check`. Behold Python 3.6-kompatibilitet for host-verktøyene.
Beskriv nødvendig labverifikasjon av faktisk Podman-oppførsel, inkludert fersk
installasjon og restart med beholdte data. Ikke påstå at stubbede tester beviser
reell init-container-rekkefølge. Rapporter valgt app, konkret flyt, endrede filer,
testresultater og verifikasjonshull.

## 18. Move proxy configuration out of apps and use stock nginx from YAML

Status: done in 0.4.7 with the revised scope: existing app image building
is unchanged, standard nginx is configured through platform YAML. Verified by
the full lab matrix (latest `b34-*` on `77b27cd`, CLEAN PASS) (HTTPS e2e through the proxy). See
[proxy verification](acceptance/NGINX-YAML.md) for checks and remaining lab work.
The original revised agent message follows.

Melding til agenten:

Fjern den egendefinerte proxyen fra `apps/` i `gunstein/podman_offline`. Platform
skal referere et versjonert standard nginx-image direkte, og alt som trengs for
proxyens konfigurasjon/oppstart skal deklareres i manifest-YAML under platform.
Det skal ikke lenger bygges et eget proxy-image.

Image-byggingen for de øvrige appene skal være som i dag. Ikke flytt byggelogikk
til Python og ikke refaktorer `dev/build-images.sh`, `dev/pull-images.sh` eller
bundle-verktøyet som del av denne oppgaven. Behold eksisterende
komponentarkitektur, CLI og offline installasjonsmodell.

### 1. Les eksisterende flyt

Les `AGENTS.md` dersom den finnes, README, ARCHITECTURE, BACKLOG og relevante
tester. Undersøk minst `dev/build-images.sh`, `dev/pull-images.sh`,
`bundle.py: manifest_images()` / image-validering / arkivering,
`apps/*/Containerfile`, `apps/proxy/default.conf`, `15-resolver.envsh`,
platform-manifestene, ruteregistreringene og image-/registry-acceptance-hjelperne.
Funksjonsnavn og filer kan ha endret seg; bruk faktisk gjeldende repo-status.

### 2. Behold eksisterende image-bygging

- Behold `dev/build-images.sh` og dagens oppskrifter/build contexts/tags for
  øvrige app-images. Ikke lag en ny Python-fil eller wrapper for image-bygging.
- Behold manifestdrevet image-discovery, skille mellom lokale demo-builds og
  registry-pull, PostgreSQLs gjeldende upstream-pull/lokale tag, feilkoder og
  validering. Ikke legg til fallback-bygging ved pull-feil.
- Det eneste tilsiktede utslaget i image-flyten er at proxyen blir et vanlig
  registry-image: den hentes av eksisterende pull-flyt og bygges ikke lokalt.
  Tilpass bare hjelpere som konkret avhenger av det gamle proxy-imaget.

### 3. Proxy uten eget image-bygg

- Erstatt `localhost/myproduct-proxy:...` med et fullt kvalifisert, eksplisitt
  versjonert standard nginx-image i platform-manifestet. Ikke bruk `latest`.
  Undersøk dagens baseimage og unngå en unødvendig nginx-versjonsendring.
- Flytt nødvendig nginx-konfigurasjon, template og eventuell liten oppstartskode
  inn i YAML, for eksempel ConfigMap-data og eksplisitt command/args eller det
  valgte imagets støttede entrypoint-mekanisme. Det skal ikke kreves et nytt
  image, proxy-Containerfile eller separate proxy-konfigurasjons-/scriptfiler i
  `apps/proxy/`. Fjern disse når aktive avhengigheter er erstattet.
- Behold runtime DNS fra containerens `/etc/resolv.conf` og dynamisk oppslag av
  komponentnavn. Platform må kunne starte uten appene/Identity, og routes skal
  fungere når tjenester kommer til eller restartes med nye adresser.
- Behold HTTPS_PORT, TLS-filer, begrensninger, `/livez`, ukjent-route 404 og
  `/routes/installed.conf`. Ikke hardkod app-/Identity-ruter i proxyens grunnconfig.
  Behold TLS-mount, rutemount, readOnly, hostname, hostIP/port og healthcheck.
- Respekter rendererens eksisterende hele-verdi-`@@...@@`-kontrakt. Hvis nginx-
  templating skjer ved containeroppstart, begrens variabelsubstitusjon slik at
  nginx-variabler i konfigurasjon/ruter ikke utilsiktet erstattes. Ikke innfør en
  generell endring av deploy-rendereren for å løse proxy-templating.
- Verifiser nødvendig shell/verktøystøtte, ConfigMap-mounts, filmoduser og
  oppstartsrekkefølge for faktisk valgt image og Podman-versjon. Ikke skriv til
  skrivebeskyttede mounts; kjør nginx som hovedprosess med korrekt signalhåndtering.

### 4. Offline, tester og dokumentasjon

Det nye nginx-imaget skal oppdages fra manifestet, hentes på byggemaskinen via
pull-flyten, arkiveres med platform-bundlen og lastes/verifiseres før installasjon.
Behold `imagePullPolicy: Never` på målmaskinen, checksums, image-navnvalidering og
isolasjon mellom bundles. Produksjon skal ikke hente images eller pakker fra nett.
Oppdater dev-/acceptance-hjelpere som fortsatt forventer egen proxy-build eller
filene under `apps/proxy`. Ikke endre historiske rapporter eller pinned fixtures.

Behold testene for dagens image-bygging og pull-feil. Legg til målrettet dekning
av at nginx ikke bygges, men oppdages og hentes gjennom eksisterende pull-flyt,
og at øvrige app-builds bruker samme tags og contexts som før. Verifiser renderet
proxy-YAML, runtime-templating/DNS, bevarte
nginx-variabler, image-inkludering i offline-bundle og uendrede TLS-/rutemounts.
Oppdater tester som tidligere leste `apps/proxy/default.conf`, uten å svekke
kontrollene for separate komponenter og dynamiske ruteregistreringer.

Kjør produkttester, acceptance-harness-tester, ruff, formatkontroll, pyright,
vermin, shellcheck og `git diff --check` med repoets oppsett. Oppdater relevante
releaseversjoner etter repoets regler, uten å endre uendrede app-images/tags.
Dokumenter at app-byggingen er uendret, og hvordan standard nginx hentes og
proxyen konfigureres fra YAML. Beskriv nødvendig
labverifikasjon av HTTPS, innlogging, platform/help uten Identity, app-tillegg,
DNS etter restart, helse og offline installasjon. Ikke reset labmiljøer uten
autorisasjon og ikke påstå at stubbede tester beviser faktisk nginx/Podman-atferd.

Ingen config-/credential-migrering, fallback for gammel proxy-layout,
passordrotasjon, ny komponentmodell eller bred deploy-refaktorering. Behold
persistente config-/credential-bytes, databasedata, retry og SELinux-/fapolicyd-
kontroller. Rapporter endrede filer, valgt YAML-/entrypoint-løsning, faktiske
testresultater og verifikasjonshull.

## 19. Remove branches whose changes are already in main

Status: done. On 2026-10-17 `git ls-remote --heads origin` listed only `main`;
`fix/atomic-install-records` and `improvements-0-2` no longer exist on the remote.
Their content was confirmed in `main` on 2026-10-16 as described below. Who deleted
them is not recorded here. No source, release version or `main` history changed.

Melding til agenten:

Rydd opp i de to branchene `fix/atomic-install-records` og `improvements-0-2`
i `gunstein/podman_offline`. Behold `main`.

Ved kontroll 16. oktober 2026 var `improvements-0-2` inkludert i historikken til
`main`. De tre commitene på `fix/atomic-install-records` var samlet i commit
`c1e26e2369c94350aae36ead018fc5f82117ffc0` på `main`, med identisk innhold i de
tre berørte filene. Den branchen trenger derfor ingen ekstra merge.

Hent oppdatert remote-status før sletting og kontroller at ingen av branchene
har fått nye endringer som mangler i `main`. For atomic-install-records må
kontrollen ta høyde for at endringene er samlet i én commit; manglende felles
commit-ID alene betyr ikke at innholdet mangler. Hvis nytt arbeid mangler i
`main`, rapporter dette og behold den aktuelle branchen.

Slett bare de to navngitte remote-branchene når innholdet er bekreftet ivaretatt.
Rydd eventuelle tilsvarende lokale brancher og foreldede remote-referanser uten
å miste lokale endringer. Ikke endre kildekode, releaseversjoner eller historikk
på `main`, og ikke opprett en ny merge bare for å markere branchene som merget.
Rapporter hvilke brancher som ble slettet og hvordan innholdet ble kontrollert.

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

`dev/dev.sh up/down` and `./deploy prepare` must use the catalog and dependency
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
`prepare`, `build-bundle.sh` or `install`, for example `./deploy validate`.

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

**Command.** `./deploy validate`, the same wrapper as `prepare` and `install`.
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

**Docs.** README (developer workflow: run `./deploy validate` before
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
  unfinished first install and that `./deploy install` from its bundle finishes
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

Status: done on `main` (0 early evictions in the lab with the documented cache size). `acceptance/fapolicyd-reload-probe.sh` reproduces
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
deploy: rerunning `./deploy install` already completes pending owner work.

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
`fapolicyd-cli --update`, then `./deploy install`, which restarts services. If
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
`./deploy install` prints OK. The acceptance harness has its own health wait
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
4. Keep `./deploy validate` and dev `prepare` free of Podman calls.
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

Status: planned; requested by the operator on 2026-10-19. In a real product
every component can have a different version, and operators must be able to
see on the target which versions are installed.

### Problem

The target already records everything: `installed/<id>` holds the completed
version, `metadata/<id>.json` the installed descriptor (product, version,
dependencies, roles), and `pending-operation.json` unfinished work. But there is
no command that shows it; an operator has to read private files in the service
home by hand, for example
`sudo -u <user> sh -c 'cd /var/lib/<user>/installed && grep -H . *'`.

### Task

1. Add `./deploy status`, run as the service user from any unpacked bundle of
   the product (the bundle only supplies the code; status reads the service
   home). Output, one line per installed component in dependency order:
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
  and `./deploy validate`, like `check_file_sources` today.
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
  - the password is absent from `./deploy` output and from the user journal of
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
2. Report certificate expiry in `./deploy status` (item 39).
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
`a37f4e4`; implementation and local regressions delivered, full current-change
OL9 matrix pending.
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
  the source checkout in dev, the unpacked bundle running `./deploy` in production,
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

Status: planned, high priority (2026-10-22). Schedule after item 54 and before
items 48/49. This is a consistency and validation improvement, not evidence that
the current valid templates generate incorrect units.

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

Status: planned, high priority (2026-10-22). Schedule after item 59 and before
items 48/49. Requested because several users expect the shell script to have a
`.sh` suffix. The canonical command becomes `./deploy.sh` in source and releases.

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

Status: planned, high priority (2026-10-22). Requested by the operator: image
versions must be controlled by parameters, not edited inside each manifest.
Decision (operator, 2026-10-22): one shared variables file `config/images.yaml`,
`{{NAME}}` tokens only in container image references, resolved at bundle build
and in dev; plus a built-in `{{COMPONENT_VERSION}}` for images that follow their
component's release. Production keeps receiving fixed literal tags.

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
- `@@NAME@@` (`common.PH`, whole-value only, resolved by `render.replace` from
  config at render time) means "comes from installation config". Build-time
  image values need a different, visibly distinct syntax so a reviewer can tell
  that they are fixed in the release.

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
   POSTGRES_VER: '17.11'
   NGINX_VER: 1.28-alpine
   TODO_BACKEND_VER: 0.2.2
   TODO_FRONTEND_VER: 0.2.0
   ```
   Keys match `^[A-Z][A-Z0-9_]*$`. Values must be YAML strings. Reject numbers
   (`17.11` parses as a float) with a message telling the author to quote them.
   `COMPONENT_VERSION` is reserved. The file is build input. It never enters
   component or production config and is not merged by `merge_config`.
2. Manifests may use `{{NAME}}` only inside a container or initContainer
   `image` string, in any part of it (registry, name or tag). Example:
   `image: localhost/demo-postgres:{{POSTGRES_VER}}`. No nesting, defaults or
   expressions. `{{` anywhere else in a manifest is an error that names the file
   and field.
3. `{{COMPONENT_VERSION}}` resolves to the owning component's
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
   and `render.find_images` keeps rejecting any unresolved `{{`/`@@` in a release.
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

Convert the demo so both forms are exercised:
- help and identity: `{{COMPONENT_VERSION}}`. Their images are built per
  component.
- todo-backend and todo-frontend: `TODO_BACKEND_VER` and `TODO_FRONTEND_VER`.
  app1 and app2 share these images and may have different component versions.
- postgres in app1, app2 and identity: `POSTGRES_VER`.
- platform nginx: `NGINX_VER`.

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
  - resolution in image fields;
  - `COMPONENT_VERSION`;
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
  image tags, with no manifest edits.
- Production config never contains image versions. Releases contain only
  literal, fully qualified images.
- An equal-version release with different images is refused with guidance and
  never silently ignored.
- All existing contracts and lab scenarios stay green. The understandability
  review covers one normal build and upgrade flow and one failure flow (unknown
  variable or equal-version refusal).

Out of scope: operator overrides of image versions in production config,
registry credentials, automatic `VERSION` bumps and image pruning.
