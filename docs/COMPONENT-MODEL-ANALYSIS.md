# Component model analysis: backlog 77

Date: 2026-10-29. Reviewed repository baseline: `bfa9a41`.
Scope: an independent assessment of the proposal, not an implementation plan
approved by the product owner. Read alongside [item 77](../BACKLOG.md#77-make-a-component-intuitive-to-write-env-files-mounts-and-shared-secrets),
[the review guide](REVIEW_GUIDE.md) and [the component contract](COMPONENTS.md).

Evidence labels used throughout:

- **Verified in code (C):** observed in the repository at the stated baseline.
  External source inspections explicitly name their repository and version.
  This label does not mean that the behavior has been exercised on Podman.
- **Verified by execution (E):** exercised during this analysis; the method and
  limitations are recorded below.
- **Assumption (A):** a design judgment, proposed behavior, predicted failure,
  or runtime question that still needs verification. Supporting documentation
  is identified where relevant. A usability prediction is not a human trial.

## 1. Summary and recommendation

**Assumption (A): approve the direction, not the proposal as one package.**
Putting environment settings beside the container and text files at recognizable
mount paths can remove substantial repetitive YAML. Begin with those authoring
conventions and a working example. Preserve the existing ownership, registration,
retention and retry semantics underneath them. Defer product-wide secret storage,
automatic dependent updates and universal CA injection until their contracts
have been decided and separately verified.

**Verified in code (C): the proposal combines presentation changes with new
deployment semantics.** `env/` can generate existing manifest structures, but
shared secrets cross the current component boundary. Reading gateway values at
render time changes persistent-config authority. Removing API registrations
removes installed-membership information used by Identity. Making a gateway
mandatory removes a supported product shape. These are not consequences that
follow automatically from moving settings into clearer files.

**Assumption (A): the three largest risks, in priority order, are:**

1. **Inconsistent credentials after partial rotation.** A new product-wide value
   can reach Identity while an API skipped by `newer-only` still uses its old
   value. The present pending record is not a transaction for arbitrary shared
   inputs and all their consumers.
2. **Losing API membership and ownership.** Identity's reference to a shared
   secret can generate it before the API is installed and retain it after the
   API is removed. Sharing bytes does not replace item 72's registration model.
3. **Promising trust that a mount does not establish.** Two PEM files at a fixed
   path cannot provide a universal contract for .NET, Node, Java and arbitrary
   unchanged images. A failed connection could still look like the original
   authentication problem, despite apparently correct component files.

**Assumption (A): understandability outcome: promising authoring surface;
not ready for approval as specified.** A developer can guess the purpose of
`env/backend.yaml` and `mounts/postgres/.../bootstrap.sql`. They cannot infer
from those paths when a shared value is created, which release supplies a
consumer's recipe, whether reinstall rotates anything, or how an interrupted
update is finished. The predicted concept reduction is much smaller than the
proposal's “about six” suggests. Only the required human trial can establish
that developers succeed without reading the full documentation.

### Evidence obtained for this analysis

**Verified by execution (E): 64 focused product/fixture tests passed on Python
3.12.14**, using this command from the repository root:

```sh
PYTHONPATH=tests python3 -B -m unittest \
  platform_tests.test_api_registrations \
  platform_tests.test_registration_removal \
  platform_tests.test_secret_templates \
  platform_tests.test_trust_chain \
  platform_tests.test_component_files \
  platform_tests.test_public_origin_hosts
```

**Verified by execution (E): three disposable Python probes also passed.**
They called `catalog.load_catalog()` with `components: {worker: null}` and no
gateway; called `deploy.postgres_binding()` on the fixture PostgreSQL Pod with
`POSTGRES_PASSWORD` instead of `POSTGRES_PASSWORD_FILE`; and used
`ProductFixture.write_product()` / `build_and_unpack()` with added
`env/main.yaml` and `mounts/main/etc/example.conf`. Respectively, the catalog was
accepted, the password layout was refused, and both new directories were absent
from the built bundle. The last probe uses the fixture's mocked host commands.
No credentials or rendered secret values were printed.

**Verified by execution (E): verification boundaries.** These are product/unit
and fixture runs with Podman/systemd calls replaced, not acceptance-harness or
real-runtime runs. The acceptance harness was not rerun. No Podman executable
was available here; there was no real Podman/systemd, OL9, SELinux, .NET compile,
TLS connection, Python 3.6 execution or human trial for this analysis. No part
of the proposed model has been executed. Historical lab reports are discussed
only as evidence for their original versions and scenarios.

## 2. Corrections to item 77

### Every row of “What a component author handles today”

All observations in this table are **Verified in code (C)** at `bfa9a41`.
The table describes the organization's multi-container example; it must not be
presented as the minimum required for every component.

| Concern in item 77 | Corrected description and source |
| --- | --- |
| Membership, order, dependencies | Membership and explicit `requires` are correct. Dependency order is derived; authors do not separately maintain an installation sequence. Compiled version ranges come from component `VERSION` files. See [catalog.py](../deployment/catalog.py), `load_catalog`, `dependency_order`, `source_descriptors` (lines 147, 310, 366). |
| Same public address as proxy | `public_from` identifies a dependency. `PUBLIC_ORIGIN` and `HTTPS_PORT` are inherited without an explicit `shares` entry; `shares` adds other public names. Production `init-config` copies them once and later install checks equality. Dev overlays the owner's effective values. See [deploy.py](../deployment/deploy.py), `init_config`, `shared_keys`, `check_public_settings`, `dev_settings` (21, 71, 87, 329). |
| Proxy routes | Correct: `route.conf`, `routes` and the receiving owner's `accepts.routes` identify a delivery contract. The owner also needs a consuming mount. The accepted name is an import volume; it is not merely a label saying “this is nginx.” See [registrations.py](../deployment/registrations.py), `registration_stage` (31), and the platform manifests. |
| Public environment values | A ConfigMap with `envFrom.configMapRef` is one supported pattern, not compulsory. Direct `env.value` supports whole-value config placeholders; `env.valueFrom.configMapKeyRef` can select keys. Inline public substitution is specifically supported in ConfigMap `data`. See [render.py](../deployment/render.py), `replace`, `configmap_data`, `check_links`. |
| Values for placeholders | Add `config/common.defaults.yaml`. Dev precedence is common defaults, component defaults, global dev, component dev, then inherited owner values; maps are replaced at the top level. Production reads the explicitly initialized persistent file, not an automatic merge with each new release's defaults. See `render.component_defaults` (139), `merge_config` (130), `load_config` (125), and `deploy.init_config`. |
| Secret environment values | `SECRET_TEMPLATES` is needed for composition or renamed keys, not for every secret environment variable. A file Secret can be selected directly through `secretKeyRef`, or consumed through `envFrom.secretRef` when its keys already match. The proposed simplification should not count the recipe as mandatory in both cases. See `render.check_links`; [app3's Pod](../components/app3/manifests/60-whoami.yaml) uses a selected key from a composed Secret. |
| Secret sources | `SECRET_FILES` supports supplied external files/directories and optional generation. External `path` is not confined to the config folder; generated paths are confined there. `component_file` is a distinct immutable, public release-file source, forbidden for generated material and database passwords. `VOLUME_FILES` can also declare generated file sources. See `render.file_group_sources` (272), `generated_secret_paths` (316), `resolve_file_source`, and `deploy.database_password_path` (251). |
| Templated files | Secret-bearing text can use `SECRET_TEMPLATES` plus Secret mounts. Public templated text can already be ConfigMap `data` plus a mount. Literal public release files can use `component_file`; larger/directory delivery uses the existing file-import mechanism. These cases are not all secret recipes. See `render.configmap_data`, `templates.documents`, and [component file tests](../tests/platform_tests/test_component_files.py). |
| API secret shared with Identity | The row mostly describes item 72, but a `SECRET_TEMPLATES` recipe is optional if the API can consume its file Secret directly. `api.yaml` chooses explicit index and hash; `apis` targets the owner; `accepts.apis` names a **Secret**, unlike route/client import volumes. Registration already eliminates manual copying of the secret value. See `registrations.api_registration` (418), `api_updates` (465), `owner_secrets` (506). |
| Identity API resource names | Correct for this demo: names **and scopes** live in [identity-settings](../components/identity/manifests/10-configmap.yaml), indexed to match `api.yaml`. The platform never emits `ApiResources__<index>__Name`. This is an explicit product-owner decision in item 72, not an accidental omission. The API resource name need not equal the component ID: the demo uses `app3-api` and scope `app3`. |
| Trusting the environment's CA | Correct for item 70's selected .NET layout: external CA material, a Secret and two read-only `subPath` mounts. Provisioning tools prepare the component's copy. This is not a general trust mechanism required by every image, nor proof that every application's TLS stack reads these paths. See [trust-chain tests](../tests/platform_tests/test_trust_chain.py), app3 manifests, and item 70. |
| Pods, images, volumes | Correct but incomplete: resource prefixes, supported kinds, container field placement, fully qualified image references, `imagePullPolicy: Never`, component `VERSION`, and PostgreSQL password/PVC binding are enforced contracts too. The proposed model retains most of them. See `render.check_component_names` (928), `check_pod_specs` (907), `find_images` (1128), and `deploy.postgres_binding` (180). |

### Additional material corrections

**Verified in code and by execution (C, E): empty entries already work.**
`catalog.load_catalog`, lines 157–158, converts a YAML null entry to `{}`.
There is no `{}` requirement to remove. The same probe accepted a minimal
worker without a gateway. A mandatory gateway would remove functionality, not
relax an existing restriction.

**Verified in code (C): the examples contain a PostgreSQL contract conflict.**
`deploy.postgres_binding`, lines 180–249, accepts only the declared
`POSTGRES_PASSWORD_FILE` layout and follows its Secret mount to the retained
source file and data PVC. The proposed `POSTGRES_PASSWORD` delivered through
`envFrom` does not satisfy that guard. In the normal data-mounted layout it is
refused; the validator also does not generally discover database credentials
hidden inside arbitrary `envFrom` sources. A new binding resolver or an explicit
limitation is required. Do not delete the guard to make the example pass.

**Verified in code (C), with an assumption about unchanged external Duende
configuration (A): the Identity example uses the wrong form for this demo.**
It shows `@@shared:myapp-api@@`, although it defines a separate SHA-256 form.
The current [Identity code](../apps/identity/Program.cs), lines 65–74, binds
`ApiResource[]` directly; item 72 supplies Base64(SHA-256) and no custom
plaintext-secret validator is registered. The example should show the hashed
form for this configuration and include scopes. Duende's
[secret authentication documentation](https://docs.duendesoftware.com/identityserver/tokens/client-authentication/)
also distinguishes the cleartext credential held by the caller from the hash
stored by Identity. Do not assume an organization's unchanged Identity image
binds the same section or uses the same secret validator.

**Verified in code (C): “existing value rules stay” is inaccurate.**
`templates.documents`, lines 153–191, strips trailing LF characters before
validating substituted secret text. `api_registration` deliberately refuses
them so the direct file, composed API environment and registered hash agree.
Direct file delivery can carry binary data and characters forbidden in a text
recipe. Public values interpolated by the recipe engine are also checked.
Choose and document exact-byte behavior for the new syntax; do not describe
uniform newline refusal as the current behavior of every delivery path.

**Verified in code (C): bundle payload handling must change.**
[bundle.py](../bundle.py), lines 260–281, copies a named set of component entries;
`env/` and `mounts/` are absent. The runtime layout can remain recognizable, but
“RPM payload layout unchanged” does not remove the need to ship these inputs,
include them in authenticated inventories, and apply private-source exclusion
and path validation. New descriptor fields also affect old metadata readers.

**Assumption (A): replace “operators are not affected either way.”**
Supplied-file locations, credential backup/rotation, shared cleanup, pending
work, and gateway-triggered restarts affect operators even if they never edit a
manifest. “Changing them re-renders dependents” followed by “or an explicit
operator step” is an unresolved behavior choice and conflicts with the promise
of no added operator steps. Item 66 must report and resume it.

**Assumption (A): do not equate fewer files with fixing every conversion
failure.** CSP, rewrite paths, SPA configuration, configured authority sections,
issuer values, DNS and certificate validity remain different contracts. A more
intuitive model can prevent some mismatches; it cannot infer arbitrary
application configuration or prove authentication from successful rendering.

## 3. Simplicity assessment

### A reproducible concept inventory

**Assumption (A): the following counting rule is an analytical aid, not a
measured cognitive score.** Count each semicolon-separated topic once for an
author handling the full example, including its maintenance. Related syntax
within a topic is grouped consistently. Familiar Podman/YAML topics are shown
on both sides, since the proposal still requires them. Optional features do
not become prerequisites for a minimal component merely by appearing here.

| Topic | Current model: concepts | Proposed common path: concepts |
| --- | --- | --- |
| Component basics | Membership/naming; `VERSION`; Pod/container model; images; persistent volumes **(5)** | Same five **(5)** |
| Dependency policy | `requires`/version ranges; `newer-only` **(2)** | Same two, even when some edges are derived **(2)** |
| Public address and routes | `public_from`; `shares`; `route.conf`; route owner/delivery binding **(4)** | Gateway; `route.conf`; inferred edges; render-time inheritance and propagation **(4)** |
| Values | Config-layer precedence; persistent initialization; public placeholder substitution **(3)** | Same three, with changed authority for inherited values **(3)** |
| Environment delivery | Public ConfigMap wiring; private Secret wiring **(2)** | Container-name targeting; automatic public/private split **(2)** |
| File delivery | Secret volume/key/`subPath` wiring; volume imports; immutable `component_file` **(3)** | `mounts/` path mapping; volume imports; immutable `component_file` **(3)** |
| Secret inputs and composition | File sources; generation declaration; composition recipe **(3)** | Local generated reference; supplied reference; shared reference; shared hash reference **(4)** |
| Identity | API registration index/hash; owner resource name/scope **(2)** | Owner index/name/scope; shared-secret installed-membership rule **(2)** |
| Trust | Explicit CA delivery contract **(1)** | Automatic trust contract and exceptions **(1)** |
| Recovery | Retention/deletion/retry boundary **(1)** | Cross-consumer rotation/deletion/retry boundary **(1)** |
| **Total** | **26** | **27** |

**Assumption (A): retaining all three old secret-input/composition topics as a
second advanced authoring choice raises the proposal's inventory to 30.**
Conversely, an author who does not use databases, Identity or shared inputs
does not need this whole inventory. The exact totals depend on granularity;
the robust conclusion is that five placeholder forms plus targeting, ownership,
overrides and lifecycle rules are not six concepts. The genuine gain is fewer
manual delivery links and better locality, not removal of all these semantics.

### Walk through the examples without prior knowledge

The predicted misunderstandings and suggested remedies in this table are
**Assumptions (A)**. References to current behavior are supported above.

| Example | Likely wrong guess | Concrete simplification or correction |
| --- | --- | --- |
| Catalog with empty entries | Order in the file controls startup; naming a gateway tells the platform where its nginx includes are mounted. | Display derived dependency and delivery targets. Keep an explicit receiver contract unless the platform owns a fixed gateway implementation. Leave gateway optional for workers. |
| `env/backend.yaml` | The filename is a Pod name; any container named `backend` is acceptable; an existing `env` entry is overridden. | Match exact container names, including init containers; refuse unmatched files and conflicting variables. Report both Pod and container. Offer a qualified target only if duplicate-name use cases justify it, rather than silently applying to several Pods. |
| `@@secret:db-password@@` | It reads a secret already supplied by an operator, or changing its name rotates the database safely. | Put generation/provision policy at the source declaration. A reference should resolve an existing declared source; an undeclared name should be an error, not create a new credential. |
| `@@provided:export-api-key@@` | “Provided” is public configuration, or the tool knows the external service's credential. | Describe it as an externally supplied secret. Show its protected destination and a safe provisioning instruction without a real value in the command, logs or shell history. Preserve raw-file delivery for passwords that cannot be interpolated safely. |
| Backend plus PostgreSQL | Giving both the same environment value changes the stored database password too. | Preserve `POSTGRES_PASSWORD_FILE` and the existing-volume guard until a replacement resolver is tested. Rotation of a database account is a database operation, not just a file replacement and restart. |
| `@@shared:myapp-api@@` | A spelling mistake is caught, the API owns this secret, and Identity sees it only while the API is installed. | Prefer an explicit owner/export and checked consumer reference. Reuse API registration membership. Do not make every reference an implicit declaration with generation privileges. |
| Identity's indexed API values | The name automatically creates a scope, plaintext is correct, and changing indexes is harmless. | Supply name, scope and hashed credential together in the example; preserve explicit index validation and installed membership. Do not infer resource name or scope from the component name. |
| Frontend variables | Setting an environment variable modifies already-built JavaScript served by nginx. | Provide a real runtime configuration file/entrypoint contract consumed by the SPA. The example must prove this with the browser; setting the nginx process environment alone is insufficient. |
| GraphQL and WebSocket URLs | Appending `/graphql` matches every proxy rewrite; rebuilding `wss://host:port` is equivalent to using the canonical origin. | Include and exercise the exact matching route/rewrite. Avoid duplicating scheme/host/port construction in the default example; use an application-supported relative endpoint or one explicitly derived endpoint. |
| SQL mount | Editing the mounted script updates an existing database; public URL interpolation escapes SQL. | Retain the empty-database warning. Fail unsupported substitutions without printing data; no general SQL escaping is promised. Use migrations for existing rows and roles. |
| Automatic CA mounts | Successful mount means every TLS client trusts the CA, including the user's browser. | Make trust support image/runtime-specific and visible. Browser trust remains outside the container. Include a negative-control TLS test. |

**Verified in code (C): app3 is not already the requested generic SPA example.**
Its frontend container has no such environment delivery in
[60-whoami.yaml](../components/app3/manifests/60-whoami.yaml); its backend handles
the demo sign-in flow. Reusing it as a starting point does not establish that
an unchanged TypeScript SPA doing OIDC in the browser reads these variables.

### Fewer placeholder forms and one common authoring path

**Assumption (A): retain two reference forms initially:** public `@@NAME@@` and
the existing `@@secret:<Secret ID>/<key>@@`. Keep generation versus external
provisioning on the source declaration. This separates “what this value uses”
from “how the credential is obtained,” and a typo becomes a missing-source
error. The current grammar is more verbose, but it does not require learning
three new storage namespaces and an additional hash namespace.

**Assumption (A): if short local names are important, use one declared local
alias table rather than five kinds of implicit reference.** A named credential
can declare `generate` or `external` once; all consumers then use the same
reference form. This is an alternative to evaluate with users, not an additional
layer to add alongside all the proposal's forms. Keep hash policy on the API
registration initially. A future general transform needs an explicit allowlist,
not a growing family of `shared-sha256`, `shared-sha512`, etc.

**Assumption (A): keep `SECRET_FILES` and `VOLUME_FILES` as explicit advanced
file-delivery facilities, with one implementation.** Binary PFX, supplied PEM
bundles, directories and immutable bundled files still need them. Make `env/`
and `mounts/` the normal locations for text recipes; do not also teach inline
`SECRET_TEMPLATES` as an equally recommended way to write those same recipes.
It can remain an internal representation or a documented escape hatch where
necessary. Refuse duplicate outputs across the two surfaces. Before the first
customer, obsolete source syntax may be removed by decision; maintaining two
independent renderers is not needed for compatibility.

## 4. Feasibility

### Generated environment resources and container targeting

**Verified in code (C): this is feasible as compilation to existing resources.**
`render.containers` handles regular and init containers; `effective_documents`
already checks names, resource duplication and references. The new files must
be read and their generated declarations included **before** those checks and
the database preflight. Appending them after validation would bypass existing
safety rules. [Podman v5.8.2's kube generator](https://github.com/containers/podman/blob/v5.8.2/pkg/specgen/generate/kube/kube.go),
`envVarsFrom`, reads ConfigMaps and Secrets into container environment values.
This external source was inspected at that tag, not inferred from current
Podman documentation.

**Assumption (A): specify the following before implementing injection:**

- One exact target, with unmatched files and duplicate container names reported
  by source path and Pod. Include init containers and sidecars in validation.
- Deterministic resource names, collision checks against authored resources,
  and a reserved namespace that cannot collide with component IDs or state
  directories. Concatenating component/container names without checking
  ambiguity is insufficient.
- No silent precedence between generated keys, authored `env`, authored
  `envFrom`, and existing registration Secrets. Either reject overlap or define
  one clearly explained rule and resolve it before database validation.
- A string conversion rule for YAML scalars, duplicate-key refusal, and no
  recursive expansion. Quote ambiguous booleans, numbers and `@@` expressions.
- Provenance from each generated key back to source file, key and target. The
  explanation must never contain resolved secret values or connection strings.

**Assumption (A): useful refusals identify the edit, not just the generated
resource.** For example: `components/myapp/env/backend.yaml: variable
ConnectionStrings__Default references undeclared secret myapp-database/password;
declare its source or correct the reference`. An ambiguous target should name
both Pods and the container; a mount conflict should name both source paths.
These messages can be constructed without secret contents. A successful wiring
report should likewise describe names and destinations, not resolved values.

**Assumption (A): secret classification is propagation, not secret detection.**
A recipe containing a secret reference must produce only private output; a
file containing one such reference must be private in its entirety. A literal
password, or a password incorrectly placed in ordinary public config, will not
be discovered by this rule. The example and validation messages must make that
boundary clear. Do not put resolved private text into temporary public YAML,
bundle metadata, error excerpts or a debug rendering report.

### Single-file mounts: supported primitive, unproved general contract

**Verified in code (C, external Podman v5.8.2 source):**
`kube.go` constructs named volumes with `SubPath` for both ConfigMap and Secret
sources. [volume.go](https://github.com/containers/podman/blob/v5.8.2/pkg/specgen/generate/kube/volume.go)
maps keys/items to files and honors a volume `defaultMode`.
[play.go](https://github.com/containers/podman/blob/v5.8.2/pkg/domain/infra/abi/play.go),
lines 776–829, creates or reuses named volumes, applies the mount label, writes
items and chmods them using that default. This inspected path does not apply
individual `items[].mode` values. The population loop also does not remove
old, unlisted files from a reused volume. Do not promise Kubernetes projection
or cleanup semantics merely because the input resembles Kubernetes YAML.

**Assumption (A): use explicit read-only single-file delivery, with a bounded
text-file scope first.** Flatten generated resource keys and map them to safe
paths; reject symlinks, traversal, special files, duplicate targets, parent/child
mount conflicts and collisions with existing mounts. Define what happens when
an image already has a file or symlink at the target. Changing classification
from public to private must not leave the prior public copy in a reused volume.
Renames, removed files and uninstall require a deliberate cleanup policy that
does not delete application PVC data.

**Assumption (A): ownership and modes require real tests.** Rootless user
namespaces and non-root image users make “0600” neither automatically readable
nor a substitute for the right owner. The source inspection above is not proof
that arbitrary `runAsUser`, `runAsGroup` or `fsGroup` choices work as intended.
Use separate generated resources when different file modes are required; do
not rely on ignored per-item modes. Preserve executable requirements for scripts
only through an explicit policy. Test OL9 with SELinux enforcing, the actual
non-root UIDs, read-only root filesystems and existing destination directories.

**Verified in code (C): current Secret output is bounded.**
`common.MAX_SECRET_SIZE` is 500,000 and generated Secret documents are checked
against it; base64 and YAML overhead reduce usable input size. There is not an
equivalent general generated-ConfigMap policy for the proposed directory tree.

**Assumption (A): set per-file and aggregate limits before writes.** Do not
claim that a Kubernetes API server's usual size limit is Podman's measured
limit. Large files, binary files and whole writable directories should keep an
explicit advanced delivery path. Test shortened replacements and removed keys
against the exact target runtime, not just successful first creation.

### Reading gateway values instead of copying them

**Verified in code (C): reading the owner's effective config is already done
in dev; production deliberately has a different persistence contract.**
`dev_settings` supplies owner values during merge. Production `init_config`
copies them, and `check_public_settings` subsequently compares them. A bundle
has installed owner metadata and config available, so reading selected public
values does not inherently require the gateway's source tree.

**Assumption (A): eliminating copies is feasible; automatic propagation is a
separate feature.** Read only an explicit public export allowlist, not arbitrary
gateway configuration or secret declarations. Define how custom `shares` names
create dependencies, and what happens when a dependent still has copied values
or a dev override. An unresolved public token must not make the gateway depend
on itself. Compile inferred dependency versions into the bundle and check cycles.

**Assumption (A): a gateway edit cannot automatically rerender arbitrary
installed consumers with today's retained state.** Their `install.yaml` contains
resolved values, not every original recipe. Current owner-Secret replacement
targets one named generated document; it is not a general rerender mechanism.
The gateway's isolated bundle does not contain sibling source files. A future
propagation operation must use pinned installed releases or persisted validated
bindings, define which are authoritative, and preserve them from release
retirement. Reading the latest published consumer recipe would accidentally
upgrade software while supposedly changing only public settings.

### Shared secret generation, storage and updates

**Verified in code (C): the reusable pieces exist, but not the proposed global
mechanism.** `render.generate_secrets` uses exclusive creation, private files,
and retained nonempty sources; it is component-scoped. `registrations` stages
API indexes separately from private values, and writes pending owner work
before changing live registrations. `replace_owner_secrets` atomically replaces
the one accepted Secret in the installed owner's private YAML. These pieces
do not identify arbitrary consumers of a product-wide secret.

**Assumption (A): product-wide sharing needs all of the following, not just a
new placeholder resolver:** an authoritative declaration/owner; a stable
private storage namespace; installed consumer metadata; generation policy;
one consistent value revision per operation; protected staging and atomic
publication; mutation serialization; a restart/dependency policy; durable
pending work for each affected consumer; and retention/cleanup rules. Names and
public dependency facts can be validated without reading the values. Content
validation must remain in materialization and must not echo input.

**Assumption (A): prefer immutable candidate revisions for rotation rather
than repeatedly overwriting the sole live source.** Record the intended revision
and affected installed consumers before publishing changes to active consumers.
A retry must reuse that revision and the same recipes, including after the
operator edits the input again. Do not mark a consumer complete before its
restart and health check. This is a requirements sketch, not approval to add a
generic transaction framework. Evaluate whether the narrow API registration
mechanism already meets the actual use case at much lower cost.

### Automatic CA trust

**Verified in code (C): the current platform delivers certificate bytes;
item 70's component declares where its chosen image reads them.** Nothing in
`render.materialize` identifies an image's TLS library or installs certificates
into arbitrary trust stores. A successful Secret/subPath render does not prove
a successful application TLS request.

**Assumption (A), supported by primary runtime documentation:**
[.NET on Linux](https://learn.microsoft.com/en-us/dotnet/standard/security/cross-platform-cryptography)
uses OpenSSL locations and environment configuration;
[Node](https://nodejs.org/api/cli.html#node_extra_ca_certsfile) offers an explicit
extra-CA file read at process startup, subject to documented exceptions; and
[Java JSSE](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html)
uses configured/default trust stores. Two files under `/etc/ssl/certs` are not
a universal interface among them. Exact image behavior remains unverified here.

**Assumption (A): offer an explicit, tested trust profile, not universal
injection.** The profile must name the target container/runtime, input CA bundle,
mount locations and any required environment setting. Unsupported images retain
manual mounts. Avoid changing an image's entrypoint or running trust-store update
commands as an implicit prerequisite; arbitrary images may be non-root, minimal,
read-only or lack those tools. Augment intended trust rather than inadvertently
replace its existing public roots. Treat adding a trust anchor as a security
decision even though the certificate is public.

**Assumption (A): prove CA behavior with the application's TLS client.**
Test a correct chain, missing trust, wrong CA, hostname mismatch, intermediate
chain and rotation. Confirm browser-side SPA trust separately. Item 76's
name-resolution fix and reachable proxy routing must work first; mounting a CA
cannot repair DNS resolving to container loopback, a refused TCP connection,
or a wrong authority configuration section. Do not disable verification as a
fallback.

## 5. Contracts and lifecycle

### Review-guide contract changes

The current requirements below are **Verified in code (C)** and in the review
guide. The disposition of the proposal is an **Assumption (A)** requiring an
explicit product decision, not a silent guide rewrite.

| Contract / guide section | Effect of proposal | Recommended disposition |
| --- | --- | --- |
| Declarative components; §2 minimal worker without gateway | Mandatory gateway excludes a supported variation. | Keep gateway optional; use a web-product convention. |
| Shared settings and dev overrides | Read-through replaces production copying/equality checks and may reject previously valid overrides differently. | Decide authoritative keys, edit behavior and propagation explicitly. |
| Config authority / explicit `init-config` | Moving recipes from persistent defaults to release `env/` and `mounts/` makes them release-controlled. | Separate operator values from release recipes deliberately; never silently re-merge operator config. |
| Secret templates / private output | New references, input namespaces, classification and file reading expand the contract. | One parser/render pipeline, declarative checks before generation, private composition, no values in messages. |
| Credential retention / database safety | Shared generation and the PostgreSQL environment example do not preserve the current ownership/binding rules. | Keep retained bytes and database preflight; define rotation as a separate operation. |
| API registrations / registration owners | Shared values omit explicit installed membership, receiver and API-owned hash policy. | Preserve item 72 until a replacement proves all those behaviors. |
| Scope and restart isolation | Gateway changes/shared rotation may update several installed components and override skip expectations. | Explicitly define affected consumers; unrelated components must remain untouched. |
| Pending operation / version guard | Current record names the initiating component, attempted version and unfinished owners, not arbitrary input revisions and consumer recipes. | Extend only after the precise cross-component operation is specified. |
| Bundle independence / immutable public sources | New files must ship; rerender cannot depend on a source checkout or arbitrary newer sibling release. | Retain authenticated, pinned inputs; preserve `component_file` confinement. |
| Offline runtime / Python 3.6 | No inherent need for a new dependency, downloads or online secret service. | Preserve both; execute new paths on 3.6, not just a syntax scanner. |
| §6 readable implementation; §7 understandability | Inference can hide control flow even while reducing YAML. | Keep clear lowering/validation/materialization boundaries and explain derived wiring. Require both code walkthrough and human trial. |

**Verified in code (C): metadata compatibility is explicit, not automatic.**
`catalog.LATER_KEYS` supplies omitted `shares` and `apis` defaults, and descriptor
validation checks the allowed key set, including the pre-product metadata
shape. Adding gateway, export or consumer fields changes those readers and
compiled bundle descriptors. Older release tools cannot be assumed to interpret
new state merely because newer tools can read old state.

**Assumption (A): choose a supported rollout boundary.** The pre-customer rule
permits a deliberate source/state reset instead of a migration, but does not
permit losing retries or retained credentials within the newly supported
model. If old and new component releases will coexist, define their tool/state
compatibility and refusal behavior before staged rollout. Coordinate that
choice with item 66's use of independently delivered release tools.

### Trace the three relevant flows (§3)

**Verified in code (C): configuration today.** Defaults and optional dev layers
produce effective values; production explicitly initializes a retained config.
Owner-shared values are copied/compared as described above. Validated manifests
are materialized into private install YAML. Restart consumes that YAML. A
release default changing does not overwrite the operator's persistent config.

**Assumption (A): configuration with the proposal.** Parse shipped `env/` and
`mounts/`; resolve declared public inputs from local persistent config and the
gateway; validate generated resources and links; publish YAML; restart and
acknowledge. If gateway changes propagate, snapshot the public input revision
and consumer set before updates. An interrupted propagation must not reread a
different gateway configuration halfway through and call that one completed
operation. Define behavior for existing database rows initialized from old URLs.

**Verified in code (C): secrets today.** Source declarations and keys validate
before generation; database preflight inspects the effective PVC/password
binding. Materialization generates missing permitted files, reads retained
sources, composes private Secrets and renders YAML. API registration reads the
same API-owned file and produces its selected hash. Ordinary uninstall retains
component config/credentials; `--delete-data` can remove component data. There
is no global shared-secret garbage collector.

**Assumption (A): secrets with the proposal.** A reference must resolve both its
source identity and its policy without reading bytes during `validate`.
Generation and content checks follow all declaration checks. Shared consumers
must receive one recorded value revision, with private intermediate files and
no value-bearing logging. Removal of a reference releases a consumer, not
necessarily the source. Missing retained credentials for existing data must
still refuse regeneration. A name change is not an automatic safe rotation.

**Verified in code (C): registrations today.** `registration_stage` builds
public route/client inputs and API indexes in temporary staging. API values
are generated/read later by `api_updates`. An install records its attempt,
publishes metadata, records changed owners, publishes registrations and YAML,
then restarts the selected component before its owners. Each successful owner
restart/health check is acknowledged; the completed version marker is written
before pending state is cleared. Uninstall persists its plan before removal
and rebuilds affected owners. See `install_component_plan` (984),
`restart_component_services` (901), `uninstall` (1201), and
`registrations.apply_registration_updates` (626).

**Assumption (A): route inference can preserve this trace; generic sharing
cannot replace it unaided.** A route file can compile to the same explicit
registration and owner contract. An Identity shared reference carries no
equivalent event saying “API installed,” “release dropped registration” or
“API uninstalled.” Keep a membership record even if its authoring syntax changes.

### Successful operation and interrupted-operation requirements

**Verified in code (C): today's successful first API install** checks
declarations and state, materializes its credential/YAML, stages the API value,
loads/verifies images, writes pending/metadata/registrations, writes selected and
owner output, restarts the API then affected owners, writes the marker and clears
pending work. Generation can precede the pending install record; retries retain
the already generated local credential. This is convergence, not rollback.

**Assumption (A): the proposed equivalent must be specified at each boundary.**
The following is an acceptance checklist for a future design, not a claim that
the present record already implements it:

| Failure boundary | Required fresh-process retry behavior |
| --- | --- |
| After validation, before generation | No live state changed. Revalidate the same selected release and declared targets; no secret contents read by `validate`. |
| During first generation or candidate storage | Reuse a complete, private credential; refuse corrupt/empty partial state. Never invent a replacement for a retained database credential. |
| After recording a rotation plan, before consumer publication | Recover the chosen value revision, consumers, release recipes and ordering from durable state. Do not select new consumers from a changed source catalog. |
| After updating registration/shared state, before one consumer's YAML | Pending state still identifies the missing consumer update. Reconstruct from the recorded revision, not newly edited input. |
| After one atomic YAML publication, before the next | Readers see complete individual files; retry completes the remaining set. Atomic files alone do not make the set atomic. |
| After a service restart fails | Preserve unfinished consumer work and actionable diagnostics. A successful earlier consumer may already use the new value; do not claim rollback or zero downtime. |
| After health success, before acknowledgement | Repeating the unacknowledged work must be safe. Database init scripts and migrations must not be rerun as a generic recovery strategy. |
| After acknowledgement, before completion marker/cleanup | Resume only the work allowed by the recorded operation and complete markers before clearing pending state. |
| During uninstall or final shared-source cleanup | Resume removal without regenerating the removed source, losing another consumer's credential, or forgetting required owner updates. |

### Upgrade, removal and skip-policy cases

| Case | Current behavior: **Verified in code (C)** | Proposal requirement / risk: **Assumption (A)** |
| --- | --- | --- |
| First API install | API owns/generates its source; its registration activates the configured owner entry. | Identity-first `@@shared:...@@` must not activate an absent API merely by generating the value. |
| API secret rotation | Rendered API and owner registration are updated together in the scoped install; API restarts before owner. | Arbitrary shared consumers need an explicit convergence order and failure policy. Accept temporary mismatch or design an application-supported overlap protocol; restart order alone does not give uninterrupted authentication. |
| Release drops `apis` | Staging returns a removal and the accepted owner Secret is rebuilt. | A retained shared reference in Identity otherwise keeps the credential active. Define an equivalent removal signal. |
| API uninstall | Private registration is removed and owner rebuilt; ordinary uninstall retains source credentials. | Remove membership independently from source retention. Do not wait for Identity to drop its reference before deactivating the API. |
| Owner reinstall | Owner rebuilds its accepted Secret from installed registrations. | Use installed API membership and applied revisions, not every API mentioned in the owner's latest file. |
| `newer-only`, not rendered | `api_updates` retains the installed registration; it does not reread a changed source value for that API. | Either retain its old revision everywhere that must match it, or define an explicit configuration update that overrides skip policy. Silently advancing only Identity is unsafe. |
| Interrupted install, different attempted version | A non-rendering retry against another pending version is refused. | Bind shared retries to input revisions and consumer release versions too; component version alone is insufficient. |
| Gateway public-value change | Current comparison detects disagreement during dependent install; no generic automatic fan-out. | Decide coordinated propagation versus explicit scoped installs, with source retention and pending semantics for either. |
| Shared reference removed / last consumer uninstalled | No product-wide shared store exists. | Count installed references, distinguish active membership from stored recipes, retain by default, and make destructive deletion explicit. Define whether other installed consumers block `--delete-data`. |

**Assumption (A): do not describe generic secret rotation as updating databases.**
The platform cannot infer a SQL role change, external API-key activation, old/new
credential overlap or application cache behavior from two references to the
same name. These are separate application contracts. Item 77 should not absorb
the unrelated database-rotation backlog merely to make a broad claim true.

### Consequences for items 72, 70, 76, 66 and 69

**Verified in code (C): item 72 remains necessary in the recommended first
phases.** Its API-owned secret, explicit index, per-API `sha256 | none`, no
generated `Name`, staged membership, skip behavior and pending owner restart
remain the contract. `env/` may simplify delivery into the API without changing
who owns the credential. Removing the registration mechanism would require the
product owner to supersede those decisions, including per-API hash ownership.

**Assumption (A): retain item 72's existing evidence as historical and rerun
the affected scenarios after any conversion.** A same-looking generated Secret
does not establish first install, rotation, drop-role, uninstall, owner reinstall,
empty-owner and renamed-product behavior. A new sharing model additionally
needs fresh-process boundary failures and real interrupted rotation. Existing
lab results do not certify that new model.

**Verified in code (C): item 70 is a usable explicit delivery pattern, not a
universal automatic trust implementation.** Keep its known layout available.
Its reports cover named versions/images; the two-level CA and organization-image
gaps must not be silently closed by invoking item 77.

**Assumption (A): new automatic profiles require new item 70 runtime evidence.**
Repeat positive and negative controls on each supported image/runtime profile,
including production initialization, renewal and consumer restart. Retain the
old reports unchanged. Item 76's public-origin DNS/hosts behavior is a separate
prerequisite; its new runtime evidence must also stand on its own.

**Assumption (A): coordinate items 66 and 69 without merging their scopes.**
Install-set ordering can consume compiled inferred edges, but it must also
surface missing supplied credentials and a pending cross-consumer operation.
Published releases are not installed membership. RPM delivery must package and
authenticate the new authoring files; it must not create runtime secrets in a
root package script. If a future propagation operation needs old consumer
recipes, release retirement must preserve the exact required version. Avoid
runtime reads of build-machine source trees and new internet dependencies.

## 6. Risks and alternatives

### Assessment of listed and missing risks

**Assumption (A): the listed risks are relevant but understate the following
failure modes.** The priority expresses design impact, not a defect claimed in
the unimplemented feature.

| Priority | Risk and concrete scenario | Proposed response |
| --- | --- | --- |
| High | `shared:myapp-ap1` is a typo that generates a new value successfully; the API and Identity disagree. | Require declared ownership/exports; unknown references fail before writes. A wiring report alone is not validation of intent. |
| High | Identity starts first and generates credentials for every listed API, including absent ones; uninstalling an API leaves it configured. | Preserve installed membership separately from secret storage and recipe references. |
| High | A retained database PVC is combined with a newly generated password after the new env representation bypasses the old binding analysis. | Resolve the effective password-to-source/PVC binding before generation; keep refusal on uncertainty. |
| High | Gateway update or shared rotation rerenders a consumer from the wrong release, or only updates half the set before failure. | Pin recipes and input revisions, define scope and skip policy, persist remaining work before publication. |
| High | Automatic trust works for the demo but silently fails for an organization's Java/Node/custom .NET image. | Supported explicit profiles and application-level negative tests; no universal promise. |
| Medium | Renaming/removing a public mounted file leaves its previous content in a reused Podman volume; later the file becomes secret. | Test replacement/removal and classification transitions; explicit generated-volume cleanup without touching application PVCs. |
| Medium | A generated env key conflicts with authored env/envFrom, or a name joins two components' generated resources. | Refuse ambiguous targeting, duplicate outputs and conflicting keys before side effects. |
| Medium | YAML errors, template excerpts, debug output or a suggested provisioning command expose a credential/connection string. | Preserve location/key-only diagnostics; sanitize parser errors; never print a resolved value or real secret-bearing shell command. |
| Medium | A broad shared namespace grants a newly added component credentials it did not previously receive. | Explicit exports/consumers are useful even under one supplier. Record whether this is policy or a hard security boundary; one shared runtime account is not strong component isolation. |
| Medium | Inferring clients after deleting `accepts` leaves no definition of which component “can receive clients,” or where to mount their import. | Preserve the capability/delivery declaration; do not inspect image names or assume every Duende image implements the demo protocol. |
| Medium | “Values only” overrides cannot express a dev-only sidecar or an external credential in production versus a generated one in dev. | Define the supported common case and explicit advanced path. Do not invent ad hoc per-file fallback/merge rules. |
| Medium | A `mounts/` file contains arbitrary `@@` text, SQL quoting, executable content, or an image-owned symlink. | Single-pass bounded text templating, literal/binary escape path and clear path/mode validation. Avoid a general expression language. |

### Compare realistic alternatives

All evaluations in this comparison are **Assumptions (A)**.

| Model | Authoring benefit | Lifecycle cost | Assessment |
| --- | --- | --- | --- |
| Item 77 as written | Few manual ConfigMap/Secret links; short credential references; central public settings. | New global secret ownership, propagation, cleanup and retry semantics; replacement of API registrations; universal trust problem. | Too much coupled change for the first phase. |
| **Thin conventions over current contracts** | `env/` and text `mounts/` remove wiring; reuse two existing reference forms and existing source declarations. Optional gateway shorthand may compile to the existing explicit contract. | Existing ownership, API membership and pending behavior remain; validation and bundle packaging expand. Recipe authority still needs an explicit decision. | **Recommended first delivery.** Smaller benefit than a completely implicit model, but a substantially smaller correctness problem. |
| Product-wide secrets with explicit exports | A component declares a source once and selected consumers reference its export; typos and accidental sharing can be refused. | Still needs multi-consumer revisions, propagation, cleanup and retry, but ownership and direction are explicit. | Prefer to anonymous product-wide generation if non-API sharing proves necessary; defer until a concrete use case requires it. |

**Assumption (A): a concrete first-step example can retain familiar source
policy while removing environment wiring:**

```yaml
# config.defaults.yaml: existing source declaration
SECRET_FILES:
  myapp-database-password:
    - path: credentials/database
      generate: [password]

# env/backend.yaml: proposed new location, existing reference grammar
Authentication__Authority: '@@PUBLIC_ORIGIN@@/myidentity-server'
ConnectionStrings__Default: 'Host=myapp-postgres;Database=myapp;Username=myapp;Password=@@secret:myapp-database-password/password@@'
```

**Assumption (A): in that first delivery, PostgreSQL keeps its explicit
`POSTGRES_PASSWORD_FILE` binding and item 72 keeps `api.yaml`.** This consciously
leaves some verbose YAML until its replacement can preserve the safety checks.
It does not require special-casing the demo names in generic Python. Existing
ConfigMap/Secret recipes and new file locations should lower into the same
validated structures rather than fork the install path.

**Assumption (A): implementation understandability should be tested with one
successful and one interrupted operation.** A moderately experienced Python
developer should locate input discovery, reference validation, private
materialization, registration publication and pending acknowledgement without
following a plugin registry or generic dependency engine. Ask them to add one
environment key, find a conflicting mount, and write a failing test for a skipped
API whose source changed. Generated diagnostics should explain source-to-target
links while preserving secret boundaries. This is a code-maintainability gate
in addition to the component-author trial, not a substitute for it.

## 7. Recommended phases

Each phase and gate below is an **Assumption (A)** until approved and verified.
Do not start with a mandatory gateway or leave the example until the end.

| Phase | Deliverable | Required evidence before proceeding |
| --- | --- | --- |
| 0: decisions and example | Correct the example semantics, choose source/recipe authority and conflicts, and prepare a copyable component design. Preserve an external-image and a no-gateway example. | Product-owner answers below; initial developer walkthrough. Finish the separately scoped item 76 runtime check rather than claim trust fixes it. |
| 1: environment convenience | Add `env/<container>.yaml` with public and existing secret references; lower into the current renderer. Bundle it correctly. Keep API registration, file-source policy and retry behavior. | Unit fixtures for targets, init containers, conflicts, private classification, no-content validation and pre-side-effect refusal; isolated bundle rendering; actual image env delivery on OL9; converted example and human trial. **Most simplification for least risk.** |
| 2: bounded text mounts | Add read-only single-file text mounts, clear limits, modes and provenance; keep binary/directory escape hatches. | ConfigMap and Secret subPath tests on Podman 5.8.2, non-root UID, SELinux, shortened/replaced/removed files, rename and private/public transitions; retry and uninstall without PVC loss. |
| 3: optional gateway convenience | Infer route/public dependencies only when an explicit receiver/export contract is available. Consider read-through separately from automatic propagation. | Gateway-free and renamed fixtures; custom public exports, cycles and overrides; isolated releases; chosen gateway-change behavior under failure and `newer-only`. |
| 4: supported CA profiles | Provide convenient opt-in configuration for proven image/runtime profiles and retain manual delivery. | Positive/negative TLS controls using real application clients, two-level chain, renewal, unchanged external images and independent item 76 DNS/routing proof. |
| 5: only if required, general sharing | Evaluate explicit exports against the actual non-API need. Replace item 72 only if its full ownership/membership contract is intentionally superseded. | Consumer-revision design, source retention/retirement, durable failure matrix, real rotation/retry, cleanup, install sets and package delivery. Repeat item 72's affected scenarios and the human trial. |

**Assumption (A): verification must remain separated.** Product/unit tests prove
parsing, compiled links and recorded lifecycle decisions. Acceptance-harness
tests prove the harness still invokes and checks the intended behavior. Only
real Podman/systemd runs prove volume, permission, restart, TLS and application
behavior on the target. For every implemented phase, run the affected fixed
matrix and whoami scenario, plus focused negative/failure cases that the matrix
does not contain. “Matrix green” alone does not prove a newly introduced branch
of behavior or human understandability.

## 8. Questions for the product owner

These are unresolved product choices, therefore **Assumptions (A)** rather
than implementation facts. Questions 1–5 must be answered before phase 1;
the remainder gate the later features.

1. **What is the first success criterion?** Approve reducing env/file wiring
   while preserving today's lifecycle, or require the global model immediately?
   Recommendation: the former, measured by a developer copying the example
   without consulting the full component manual.
2. **Who owns recipes after installation?** May shipped `env/` and `mounts/`
   change with a component release while operators own only input values?
   Recommendation: yes, explicitly; persistent config is not silently replaced.
3. **How are credentials declared?** Keep generation/external policy at one
   source declaration with one secret-reference form, or allow every short
   reference to declare and generate a source? Recommendation: declared sources,
   with unknown references refused.
4. **How should ambiguity be handled?** Approve refusal of duplicate targets,
   env keys and mount paths, including conflicts with authored YAML?
   Recommendation: yes; do not silently override. Keep the advanced path for
   layouts the simple convention does not cover.
5. **Which real application contract must the example prove?** Browser-side
   OIDC/PKCE SPA plus GraphQL, or app3's existing backend sign-in arrangement?
   Recommendation: demonstrate the organization's requested SPA architecture,
   including runtime frontend config, exact routes and API authentication, and
   recruit an independent developer for the required trial.
6. **Must every product have a gateway?** Recommendation: no. A web-product
   default can be obvious without excluding an offline worker product.
7. **What does changing a shared input do to `newer-only` consumers?** Which
   command updates them, what downtime is acceptable, and does a config-only
   update override the skip policy? This must precede automatic propagation.
8. **Does API installation continue to control activation in Identity?** If
   yes, retain membership independent of shared storage. If no, explicitly
   supersede item 72's install/uninstall, API ownership and per-API hash decisions.
9. **Who may publish/read a shared secret, and when may it be destroyed?**
   Recommendation: named ownership and declared consumers; retain by default;
   explicit destructive cleanup with safeguards for installed users and data.
10. **Which images are supported for convenient CA trust?** Recommendation:
    named, tested profiles with explicit use; no claim that all application
    containers support one filesystem convention.
11. **Can later propagation retain exact installed consumer releases?** This
    affects items 66/69 and release retirement. Recommendation: choose pinned
    authenticated recipes or a defined persisted binding format before writing
    the first cross-consumer update implementation.
