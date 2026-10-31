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
| Authoritative production config | Explicit `init-config` creates persistent config; subsequent production operations use it and never write it. Its values win; a top-level setting or a `SECRET_FILES`/`VOLUME_FILES`/`SECRET_TEMPLATES` ID it lacks comes from the release's `config.defaults.yaml` (`catalog.operator_config`), and install/validate print those names. Automatic init-config is not existing functionality. There are no customer installations, so no code migrates or detects earlier formats or layouts. |
| Component dev config | Source dev merges the component defaults and the developer's untracked `config/dev.yaml` in that order, replacing whole top-level values. The gateway's `PUBLIC_ORIGIN`/`HTTPS_PORT` remain authoritative; another component's defaults may not declare them. Validate, prepare and dev credential tooling share this flow. `config/dev.yaml` never initializes production config and never ships in bundles; generated dev config is output only. There is no shared defaults file and no per-component dev file. |
| Bundled file references | `component_file` selects public immutable content under the current component's `files/` in the selected source/release, with explicit component context. Keep logical references in persistent config; reject traversal, symlinks throughout selected trees, special files, generation and database password use before delivery. Validation reads no source bytes. Ordinary `path` semantics and private-source guards remain; imported volumes overwrite matching files and retain unlisted ones. |
| Credential retention | Generate missing secrets only when allowed; preserve valid existing credentials byte-for-byte. Do not expose credentials or complete connection strings in logs. Secret-template values are recomputed from retained sources, never independently persisted. |
| Production release authentication | Signed archive plus independently provisioned pinned product keyring are mandatory before protected publication, trust or execution. Unsigned builds are development-only; checksums alone never authorize production installation. **Temporary exception (product owner, 2026-10-26):** phase 1 of [backlog 69](../BACKLOG.md#phasing-decision-product-owner-2026-10-26) delivers unsigned RPMs installed with `dnf`; this contract remains the target and returns with phase 2. Review phase 1 changes for the interim protections listed there and for anything that would make phase 2 harder. |
| Signing provisioning | Validate public CA subject/lifetimes before writes; share CA creation across modes and retain complete existing CA/credentials when settings change. Refuse an explicit CA subject that differs from the retained CA, and explain that CA lifetime applies only to new CAs. Explicit signing PFX provisioning is separate from deploy/validate, supports arbitrary component IDs and works via stdin offline. Retain external PFX/PEM before issuance; read the private password file without exposing its value. Publish private files without clobbering existing credentials; deliver only the declared PFX, never provisioning keys/passwords implicitly. |
| Secret templates | Only `SECRET_TEMPLATES` composes config and same-component file Secrets. Validate declarations before generation and read no secret bytes during validate. Reject unsafe input without values in errors; output only Opaque Secrets in existing 0600 install YAML, never plain env values or ConfigMaps. |
| ConfigMap inline values | Compose only ConfigMap `data` using public string/integer config; refuse Secret references and recursive expansion without printing values. Keep whole-value behavior elsewhere and preserve shell/nginx dollar syntax. Init, validate and lifecycle share declaration checks; the lab checks the actual consuming container, including renamed products. |
| API secret registrations | A component is an API when identity's `ENVIRONMENT` line `ApiResources__<n>__ApiSecrets__0__Value` names one of its secrets as the whole value `@@secret:<id>/<key>@@`; the owner is the listed component whose ID begins the secret ID (Secret IDs carry their component prefix). Only that identity line may name another component's secret. The API declares the secret in its own `SECRET_FILES` (staging refuses a missing declaration or key before any write) and both sides receive it byte for byte, without hashing. One line per API, one `<n>` per API, one container; the catalog compiles `{API: {index, secret}}` into Identity's descriptor (`api_secrets`) and refuses foreign use, duplicate lines, unowned secrets and a removed `api.yaml`, before any write. The platform injects `envFrom` `<identity>-apis` and renders it with the lines of installed APIs only. The installed, rendered Identity's mapping is authoritative: install refuses an API it does not list and an Identity release that drops an installed API. The private registration `apis/<id>/value` is written after generation; staging and validate never read values. Changes, removal and uninstall rebuild only `<identity>-apis` (atomic YAML replacement, added if missing) and restart the API first, then Identity; values never appear in output or errors. Identity code hashes once and leaves an absent secret inactive. [Contract](COMPONENTS.md#api-secrets). Backlog 72 lab evidence (`fd99d31`, `0ece0c1`) is historical for the earlier `api.yaml` form; the first backlog 77 form (`@@api-secret:`) was lab-verified by the c77 runs (`0459e5a`, renamed on `6210670`; [evidence](../acceptance/RESULTS.md)); the current declared-secret form is lab-verified by the c77b runs (`318d394`); manual API secret rotation on PROD is not automated. |
| Database safety | Missing password plus existing database volume is refused. Inspection failure is not evidence of absence. Server and client receive the same password. |
| Retry | Durable pending work survives a new process and is acknowledged only after required work succeeds. |
| Isolation | Operate on the selected component's resources/state; preserve sibling data and registrations and avoid sibling app restarts. |
| Compatibility | Preserve host Python 3.6, checksums, offline delivery, version/dependency rules, SELinux and fapolicyd behavior. |
| Operator usability | An administrator/installer with limited Linux experience can complete ordinary tasks quickly and correctly using one manual, without oral help or internal architecture knowledge. Apply the separate [operator review](#7-mandatory-operator-and-procedure-understanding-review), including distinct AI and human evidence. Green automated acceptance alone does not establish usability. |
| Host preparation | `release.py setup` composes preflight, explicit authenticated publication, guarded persistent journaling and the existing host script; `deploy.sh init-layout` syncs a private temporary file and atomically publishes the runtime bootstrap without replacing an existing file. Host failures retain bounded phase/reason/action diagnostics; the manual itself owns fail-stop shell behavior, without stronger harness shell options. [Current implementation/evidence](../acceptance/HOST-SETUP.md); real OL9 verification passed at `2d36d71`; human verification remains item 68. Trust the root-controlled `/var/lib` anchor; root creates only the root-owned `/var/lib/<product>` and the account's `state/`, `config/`, `storage/` directly beneath it, refusing links and foreign owners before chown/chmod. Descendant directory/lock creation and both relabel operations run as a non-root numeric account UID/GID without supplementary groups or capabilities, with no privilege acquisition or root retry. Reject managed links/foreign-owned objects; preserve lock bytes, existing subordinate IDs, the account's home/shell and populated storage labels. Current-change OL9 Enforcing/fapolicyd verification is required before declaring this boundary verified. |
| Production layout | An existing login account (any name) runs one product. Its home holds only `~/.<product>/<product>.env`, read by `layout.select()` as private data (no execution, unknown keys ignored, values never logged). Everything else is under `/var/lib/<product>`: root-only `releases/`, the account's `state/`, `config/` (`XDG_CONFIG_HOME`) and `storage/` (`XDG_DATA_HOME`). The user manager gets the same two values from a root-owned `user@<uid>` drop-in, and lifecycle commands refuse a mismatch. Root never reads the bootstrap file. Source dev and bundle building never select production paths. No migration of the earlier service-home layout. |
| CLI entry point | Source and new offline releases expose only executable `deploy.sh`, which changes to its own directory and execs `python3 -B -m deployment` with unchanged arguments and exit status. The Python module remains `deployment.deploy`; callers, checksums and trust inventory use the wrapper filename. No old-name alias is shipped. [Verification](../acceptance/RESULTS.md). `deployment/cli.py` parses with argparse subcommands (backlog 73) through `deployment/arguments.py`, shared with `bundle.py`: one parser per command with only its own arguments, `allow_abbrev=False`, flags repeated anywhere on the line and the `--` separator refused, per-command `--help` (exit 0, stdout), `Usage:`/`ERROR:` prefixes. The accepted forms are a release interface (newer tools call older releases): `validate`, `prepare`, `install`, `init-layout`, `uninstall [<component>] [--delete-data]` in either order, `init-config <component>`, `status [--json]`, plus `--verbose`. Usage errors exit 2 with the `Usage:` line and `ERROR:` on stderr; failures exit 1. New command lines use the same pattern; no third-party CLI library. |
| Operator messages | One convention (backlog 74), through `deployment/output.py` (standard-library `logging`, format `%(message)s`): `[OK]` for a completed step and a final `PASS:` line on stdout; `WARNING:`/`ERROR:` on stderr with the next action in the same message; `+ command` host lines at `DEBUG` (`--verbose`). Data (status table, `--json`, rendered output) stays `print` on stdout. Handlers resolve `sys.stdout`/`sys.stderr` when writing. State-changing commands (`init-layout`, `init-config`, `install`, `uninstall`, `prepare-host.sh`) write a start and a result line to the journal (`journalctl -t <product>`; one syslog datagram per line from `output.JournalHandler`, `logger` in shell); the line names the executing bundle's version and, for uninstall, the removed installed version; a missing or refusing journal never stops or clutters a command. No secret value, connection string or config content in any handler. Parsed markers are an interface: `HOST-PHASE:` (prepare-host.sh to release.py) and the harness's `[OK] validated <component>;` and `PASS:` lines; change them only together with their readers. `scripts/release.py` is outside this convention (item 69 WP6 removes it). |
| Quadlet templates | `@@UNIT_NAME@@` and `@@PRODUCT_NAME@@` resolve only from internal unit/catalog names; `@@PODMAN_HOSTS_CONFIG@@` resolves only to the current release's regular `quadlet/containers-hosts.conf`, with systemd Environment path escaping. All use one nonrecursive pass; arbitrary config/Secret access and obsolete `{name}`/`{product}` are refused. Preserve literal braces, shell `${...}`, systemd specifiers and rendered bytes. Validate both templates before host queries or persistent changes, including standalone and repeated same-version installs. [Verification](../acceptance/RESULTS.md). |
| Installed status | `./deploy.sh status [--json]` reads the selected product's installed markers/descriptors and pending record under `STATE`, never config/credentials or incoming release versions. Query only bounded user-unit states; preserve all files and pending work. Show missing/mismatched markers or a pending attempt for the component as incomplete, including same-version reinstalls with an active old service. Retain the completed version; persist the attempt after image verification and before installed metadata or service files change, and clear it only after the completion marker is durable, even without registration owners. Return 1 for empty, pending, incomplete or non-active state. [Verification](../acceptance/RESULTS.md). |
| Validation | `./deploy.sh validate` and the lifecycle share one validation (`validate_component`, staging, `install_checks`, `install_preconditions`); the command writes nothing, reads no credential contents and runs no host command. Container-only fields listed in [README](../README.md) are refused directly under Pod `spec` through the shared `render.pod_specs` shape check, including bundle image discovery. This is a focused guard, not full schema validation. A new declaration check belongs in one of those functions, never inline in `install_component_plan`; a validate-only check names where the lifecycle does the same. |
| Product name | `product:` in `bundles.yaml` is the only source of the installation's names. Code builds unit, network, Quadlet, temporary-directory and archive names from `catalog.product_name()` / `catalog.unit_name()` (or the descriptor's `product`), never from a literal; `common.STANDALONE_PRODUCT` is only for standalone fixtures. It names the installation root `/var/lib/<product>` and the bootstrap file; the runtime account is passed explicitly (`prepare-host.sh --user`) and need not match it (the harness uses `<product>-ops`). One account runs one product (`check_same_product`, one drop-in per account). Image names come from the manifests (the demo's are neutral `localhost/demo-*`) and `PUBLIC_ORIGIN` from config; neither is derived from the product name. |
| Catalog | `bundles.yaml` names `gateway:` and `identity:`; `components` is a plain list of IDs; dependencies come only from the gateway and identity rules (no `requires`). `catalog.derive_entries` derives the normalized `public_from`, `routes`, `clients`, `apis`, `accepts` and `api_secrets` from those names, `route.conf`, `client.yaml` and identity's `ENVIRONMENT` API secret lines, never from manifests; descriptors keep the normalized form. The earlier map form with per-component fields (`requires`, `upgrade`, `shares`, ...) is refused with their replacement rule; descriptors still write `upgrade: always` and `shares: []` for older readers (`catalog.OLDER_READER_KEYS`) and drop them on read; `validate` prints the derived lines. A received registration volume must be mounted by a container (`render.check_imported_mounted`). [Contract](COMPONENTS.md#the-catalog-bundlesyaml). |
| Component config | Each component has one `config.defaults.yaml`. Its top part (settings, `SECRET_FILES`, `VOLUME_FILES`) is what `init-config` copies to the operator's `config.yaml`; `ENVIRONMENT` (container -> variables) belongs to the release, is read only from the release's file (`environment.read`) and is dropped by `render.merge_config`; the operator's or a dev file's `ENVIRONMENT` is refused. Values are read as written text (`environment.TextLoader`). Each container lowers to the ConfigMap `<component>-<container>-env`, a transient `SECRET_TEMPLATES` recipe for the Secret `<component>-<container>-env-secret`, and appended `envFrom` (`deployment/environment.py`, from `render.effective_config` and `render.effective_documents`). Refused before writes: unknown/ambiguous container, hand-written `envFrom` in the same container, a variable also in manifest `env` (case-insensitive), `:` keys, lists/maps, unknown placeholders, undeclared or foreign secrets, `POSTGRES_PASSWORD*`, `@@CLIENT_ID@@`/`@@CLIENT_BASE_PATH@@` without `client.yaml` (they come only from it and cannot be config), unsafe values, recipe collisions and a leftover `env/` directory. Secrets have one form: a declared `SECRET_FILES` source with its path and `@@secret:<id>/<key>@@`. Recipes are never written to `config.yaml`. [Contract](COMPONENTS.md#one-config-file-per-component-configdefaultsyaml). |
| Public settings | `PUBLIC_ORIGIN` and `HTTPS_PORT` are set only in the gateway's `config.yaml`. Every other component (normalized `public_from`) reads them from there at init-config (validation only), validate, install and registration staging (`catalog.with_gateway_settings`), and in dev from the gateway's effective dev config; its own `config.yaml` or `config.defaults.yaml` may not set them. No other setting is shared. Errors name the setting, the file and the gateway, never values. Every install renders again, so changing the gateway's values takes effect by reinstalling the components. Reserved names (`PUBLIC_HOSTNAME`, `SECRET_FILES`, `VOLUME_FILES`, `SECRET_TEMPLATES`, `ENVIRONMENT`) are documented in docs/COMPONENTS.md, "Reserved configuration names". |
| Public origin from containers | Containers reach the public origin through the proxy's host name in the product network; `IP_ADDRESS` only publishes the host port. Dev `kube play` and Quadlet's Service environment select the source/release-local `quadlet/containers-hosts.conf` via `CONTAINERS_CONF_OVERRIDE`: `base_hosts_file = "none"`, `no_hosts = false`. Podman must generate localhost/container entries while excluding host `/etc/hosts` lines, without editing normal user/system configuration. `spec.hostAliases` remains refused to protect network DNS authority. Certificate tooling refuses a retained web certificate for a different requested name. The prior `--no-hosts` implementation passed 472/472 matrix steps and functional loopback checks, but three PROD images could not resolve localhost. The replacement passed focused whoami 46/46 and normal 125/125 at `e99c6be`, plus operator-reported manual DEV/PROD localhost/loopback checks. Dev restarts use `dev/dev.sh restart <pod>...`, which selects the same override; a plain `podman pod restart`/`start` without it is not covered by the pass. [Contract](COMPONENTS.md#reaching-the-public-origin-from-a-container), [evidence and retest](../acceptance/RESULTS.md). |

Before the first real customer installation, existing dev/lab installations may
be discarded; no migration code, aliases or old-layout fallback are required for
the current changes (including items 20, 21, 54 and 64). After the first real customer
installation, incompatible changes must provide a migration and verification
procedure that preserves customer data and credentials. This temporary exemption
must not become a permanent no-migration policy. Older backlog exemptions apply
only to the pre-customer phase. This does not remove normal restart/redeploy/retry or data-retention requirements within
the supported model.

Evidence: `acceptance/RESULTS.md` holds only the latest real results for the
current code; each run replaces its row. Older reports and results live in the
git history and never count as verification of newer code.

### Known gaps

Open gaps only; a resolved gap is removed (its history is in git).

| Gap | Owner |
| --- | --- |
| PostgreSQL data mount and explicit Secret items mapping restrict supported layouts | Backlog 7 |
| Demo apps connect to PostgreSQL as the image's superuser | Backlog 35 |
| Demo containers run as container root without `securityContext` or resource limits | Backlog 36 |
| Accepted exposure: Secret-derived env values are visible to the service user/root in runtime inspection and process environments; use file mounts when the app supports them | Backlog 41; [contract](COMPONENTS.md#secret-templates) |
| Credentials are not encrypted at rest (sources, rendered YAML, Secret volumes, Identity keys) | Backlog 37 |
| Root release authentication/trust must remain protected from service-user modification | Backlog 54 implementation uses protected publication (now under `/var/lib/<product>/releases`, backlog 64) and shared exact-inventory trust; six-scenario [OL9 matrix](../acceptance/RESULTS.md) CLEAN PASS on `5b8ab69`; Python 3.6 and non-baseline integrity outstanding |
| Production installation as an existing login account with product files outside the home | Backlog 64 implemented; full automated [OL9 matrix](../acceptance/RESULTS.md) CLEAN PASS on `5b8ab69`; manual ssh run without sudo worked after adding a persistent journal, but the guide is not verified literally; host setup/manual and a focused real-SSH scenario are implemented under 65 with local tests, real OL9 verification passed at `2d36d71`, human verification remains item 68; install sets and complete reboot/upgrade SSH flow remain 66–67 |
| One self-contained procedure usable without Linux expertise or oral assistance | Backlog 65–67; [AI operator review](../acceptance/OPERATOR-REVIEW.md) finds gaps in the current manual. Unassisted human trial remains outstanding; earlier assisted installation and automated matrix results do not close this gap. |
| A host `/etc/hosts` line mapping the public host name to loopback is copied into containers, so backends cannot reach the public origin (`IDX10204`) | Backlog 76: original public-origin/loopback checks and 472/472 matrix steps passed, but PROD localhost failed in three images. Dev/Quadlet now select the bundled `base_hosts_file = "none"` policy through `CONTAINERS_CONF_OVERRIDE`; requested lab scope complete at `e99c6be`: focused 46/46, normal 125/125 and operator-reported DEV/PROD localhost/loopback checks. Direct DEV Podman restart requires the explicit override (the first attempt failed without it); `dev/dev.sh restart` supplies it, and the whoami smoke steps use it. [Evidence and retest](../acceptance/RESULTS.md) |

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
| API secret | API's `SECRET_FILES` + identity's `ApiResources__<n>__ApiSecrets__0__Value` line -> catalog mapping in Identity's descriptor -> staged membership and declaration check -> generation -> private registration -> `<identity>-apis` (owner render or YAML rewrite) -> API then Identity restart -> acknowledgement |
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
| AI operator walkthrough | Missing instructions, assumptions and comprehension barriers found by following the manual literally; neither runtime verification nor proof of human usability |
| Unassisted human trial | Observed ability of a person in the target audience to complete the tested tasks with that manual/version; record time, mistakes, stops and explanations needed, without generalizing beyond the trial |

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
Record real runs only in `acceptance/RESULTS.md`, replacing the earlier row.

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

## 7. Mandatory operator and procedure-understanding review

This is a separate assessment in addition to code review, the developer-facing
understandability review in section 6, and automated acceptance tests. The target
operator is a human administrator or installer with limited Linux experience,
not a developer who knows the implementation. Ordinary setup, installation,
checks, upgrade and recovery should be quick and correct using **one simple
manual**, without oral assistance or knowledge of the internal architecture.

Apply this review to changes affecting operator commands, prerequisites,
diagnostics, recovery or instructions, including documentation-only changes.
For other changes state why operator impact is not applicable. Keep separate
outcomes for the AI walkthrough and human trial; never treat one as the other.

### Procedure checklist

- Every step states machine, user, required access, command and expected result.
  Make account/machine switches explicit, including a fresh SSH session.
- Commands can be copied directly after a single, clearly explained substitution
  step. Collect replacement values in one place and use one consistent example;
  do not assume remembered shell variables, functions or working directories.
- Check prerequisites before changes. Explain exactly how to remedy a missing
  prerequisite, who does it and which command resumes the procedure. Identify
  checks that necessarily happen later and the partial state they can leave.
- Put all ordinary task instructions and necessary credential-path choices in
  the one manual, in execution order. The operator must not assemble a sequence
  from other documents. Linked documents may explain design and advanced topics.
- Errors explain what failed, the operator's next action and the next command
  to run, with its machine/user context. An internal exception name or a generic
  instruction to inspect configuration is not enough.
- Explain recovery after interruption and which commands are safe to repeat,
  which preserve existing work, and which must not be repeated blindly.
- Common diagnosis must not require displaying or sharing passwords, private
  keys, tokens, complete connection strings or unfiltered potentially sensitive
  logs. Give bounded safe diagnostics and say what can be shared.
- Ordinary tasks require few commands and account switches. Record command and
  manual-edit counts per task. If the manual becomes complicated, assess and
  document whether the tool or workflow needs simplification; adding more prose
  or hiding many manual steps in a large pasted script is not sufficient alone.

### Paper manual and closed networks

Assume the operator may follow a **printed** manual in a closed lab, possibly
at a console only, and may hold both the administrator and runtime accounts.
Ordinary steps must be typeable without copy/paste: short commands, prompts
with defaults instead of long option lists, digests and fingerprints compared
rather than typed, and account switches by a real login, not `su -` or
`sudo -iu`. Record typed characters as well as commands per task. A procedure
that only works by pasting large blocks has a finding (backlog 69).

### Two separately documented assessments

1. **AI walkthrough:** start only from the manual's stated prerequisites and
   follow the commands in order, including success and interruption/retry paths.
   Do not fill gaps from source code, architectural knowledge or earlier chat.
   Record the first blocker and any downstream conditional findings: missing
   steps, hidden assumptions, ambiguous terms and Linux knowledge beyond the
   audience. Identify the manual revision, tasks, step references, findings and
   remedies, and distinguish static reasoning from commands actually executed.
2. **Human trial:** a person with limited Linux experience uses the same manual
   on a fresh disposable test host without oral assistance. Record the tested
   revision, declared starting state, relevant experience, tasks, elapsed time
   (separating machine waits where possible), errors, stopping points and every
   requested/received explanation. Record actual command/edit counts. If help is
   supplied, mark that task assisted, fix the procedure and repeat the affected
   task unassisted. If no qualifying trial took place, explicitly report
   **outstanding verification**, with the intended tasks and starting state.

Store both assessments with the change's acceptance evidence and link them from
the relevant backlog item. Use pass, findings or not performed per assessment;
do not infer a human pass from an AI pass, an assisted demonstration or green
automated tests. A human pass is scoped to its tested tasks/manual/host. Do not
declare the operator flow customer-ready while required human verification is
outstanding or unresolved findings prevent unassisted completion.

### Same procedure in manual and acceptance harness

For backlog 65–67, automated acceptance must execute the same preparation command
and operator flow as the manual. Use shared command blocks or a checked mapping
from manual step IDs to executable harness commands, with tests that fail on
drift; a comment saying the flows are equivalent is not a gate. Cover initial
execution, repeated execution and continuation after interruption, plus real
SSH login as the runtime account without sudo or manually injected login/XDG
environment. The first-run path must include the documented tool bootstrap.

The harness may reset disposable VMs, deliver test artifacts and provision a
lab-only SSH key. Its declared starting state may supply documented OS/account
prerequisites. It must not independently create product directories, pin keys,
populate journal/drop-in/bootstrap state or call lower-level preparation helpers
to bypass manual steps. If a prerequisite is absent, test the same diagnosis,
documented remedy and continuation rather than silently repairing it in the
harness. Keep fault injection outside protected release code and retain trust
rules. Record test infrastructure separately from the operator's procedure.

These tests establish execution and retry behavior for the documented path.
They do not establish that a human finds the manual understandable or quick.

## Delivery and maintenance

For each change report: relevant contracts, findings/fixes, meaningful regression
evidence, code-understandability outcome, separate AI operator and human-trial
outcomes (or justified non-applicability), and remaining gaps. Mark non-applicable
areas briefly rather than inventing work. Do not fix unrelated backlog items as
incidental scope expansion. Documentation-only work needs consistency/link checks
and git diff --check, not runtime tests merely to satisfy this template.

When closing a known gap, update its status/reference here and in the backlog,
linking to actual verification where available. Keep contracts here as the shared
source; backlog items add task-specific requirements instead of copying this
guide wholesale. Update tests and existing CI gates as implementations land.
