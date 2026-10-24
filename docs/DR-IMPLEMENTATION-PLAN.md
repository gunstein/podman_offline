# Optional disaster recovery: implementation brief and analysis

Prepared 2026-10-18 for [backlog item 24](../BACKLOG.md#24-optional-disaster-recovery-dr-adapted-from-podman_test).
Status: proposed implementation plan, not implemented or runtime-verified.

## 1. Instruction to the implementing agent

Implement optional disaster recovery for this general-purpose offline deployment
product. Preserve the straightforward single-host installation. Organisations
must be able to install without DR, enable it later while retaining their data
and credentials, and deliberately return to single-host operation.

Read [AGENTS.md](../AGENTS.md), [REVIEW_GUIDE.md](REVIEW_GUIDE.md),
[ARCHITECTURE.md](../ARCHITECTURE.md), [COMPONENTS.md](COMPONENTS.md), item 24,
this entire plan, and the source references in section 14 before changing code.
Refresh both repositories and record the actual revisions; inspect differences
from this analysis rather than assuming the working trees still match it.

This document is the requested planning deliverable. It does not itself authorise
implementation. Item 24 requires an agreed plan. A subsequent user instruction
to implement this plan is that agreement; do not ask for the same approval again.
Create an isolated `feature/dr` branch from the agreed current baseline. Follow
item 24's draft-PR workflow when implementation is authorised. Do not merge or
declare the feature complete before the verification gates below are met.

Use small reviewable commits. Finish the runtime feasibility gate in section 10
before building the rest of the system. Report a material departure from the
agreed architecture or scope; resolve ordinary implementation choices yourself.
Do not turn this task into an unrelated deployment rewrite.

## 2. Product decisions and scope

### Decisions

- One repository; a separate optional operations archive and command. Ordinary
  component bundles carry no operations code. No plugins, dynamic loading,
  framework of providers, git submodule, or runtime dependency on `podman_test`.
- Operations code may import a compatible local `deployment` package. The reverse
  import is forbidden and tested. Keep one authoritative component model.
- A component's recovery capability is product data. Enabling that capability
  for a particular installation is a separate, explicit operator action.
- Use PostgreSQL's established physical replication and backup tools. The first
  supported database major is 17, matching the current demo. Verify the exact
  image/tools used; do not claim support for every image called PostgreSQL.
- One active host and one database-only standby, asynchronous replication over
  TLS, manually initiated and fencing-gated failover. No automatic election,
  witness, active/active, automatic failback, or zero-data-loss claim.
- Start with one protected group per service-user home. Its component and
  dependency set is explicit. Arbitrary names and independent component versions
  are supported within the documented resource/storage contracts.
- Backup/restore is usable without a standby and enabled explicitly. Do not
  silently add a nightly timer to every single-host installation.
- Offline means no internet access at runtime. Replication and SSH need private
  connectivity between hosts. Disconnected-site/manual-media replication is
  outside the first delivery.

### Required first completed delivery

After-install enablement, preflight/status, PostgreSQL replication, credential
and configuration provisioning, complete-group promotion, application recovery,
base backup and isolated PITR, backup history on the surviving host, standby
rebuild/reseed, controlled compatible upgrades, and safe DR disablement.

Intermediate commits may demonstrate a smaller slice. Do not label a slice with
no surviving backup history or no supported maintenance path as completed DR.

Defer other databases, arbitrary writable-file replication, tablespaces/external
WAL directories, PostgreSQL major upgrades, automated credential rotation,
multiple protection groups/standbys, transparent session continuity, and generic
hypervisor APIs. Unsupported state must be refused, never silently omitted.

## 3. Analysis of the existing code

### Baselines and evidence

| Repository | Analysed revision | Evidence |
| --- | --- | --- |
| `gunstein/podman_offline`, `main` | `29a628b637685692ae5a9fc174cca57742a9b428` | Source inspection; no new runtime verification |
| `gunstein/podman_test`, `feature/platform` | `517119764927b9bb4532ee42980fde75f18f6988` | Source inspection plus 511 selected local tests passed on Python 3.12 |
| Reference historical lab run | `c11ed00db80769cc1f9e88fd1657f04a4c95e7e8` | Repository report records 124 passing steps on two VMs; not current target-product evidence |

The reference's 171 `deploy/dr/tests` tests and 340 selected root tests covered
DR/backup, controller commands, transport and boundaries. Jinja2 was initially
missing from the analysis environment, preventing fixture construction; after
installing the test/build dependency in an isolated scratch directory the tests
passed. This does not introduce Jinja2 as a target dependency or verify Python 3.6.
No current Podman/systemd/SELinux/fapolicyd lab run was performed for this plan.

Publication update: this document was rebased onto `f8a9258`, which adds the
declared product name (item 27). Follow the current Product name contract in
`REVIEW_GUIDE.md`: derive product-owned unit/network/archive names from the
catalog helpers or descriptor, preserve `check_same_product`, and keep image
names/public origins independent. This update does not change the analysis
baseline or claim a fresh runtime review of those intervening changes.

### Reuse map

| Reference source under `podman_test` | Reuse | Required adaptation |
| --- | --- | --- |
| `deploy/dr/app_ops/transport.py`, `inventory.py` | Transport, bounded commands, pinned SSH keys, role/host validation | Python 3.6 APIs, local paths, strict inventory schema; never expose secret command output |
| `deploy/dr/scripts/app_dr.py` | Whole-group checks, lock, durable decision, promotion refusal rules | Component/database bindings, state location, per-component release set |
| `deploy/dr/app_dr_host/replication.py` | Status, WAL positions, replication authentication, bootstrap and reseed checks | Actual Pod/container/PVC names, PGDATA, SQL user, ports, units and file credentials |
| `deploy/dr/app_dr_host/replication_tls.py` | Verified TLS, expiry and renewal checks | File-based credentials, paths and explicit CA policy |
| `deploy/dr/app_dr_host/transfer.py` | Validate the complete transfer before mutation; refuse credential mismatches | Replace Podman-secret export/import with secure file delivery |
| `deploy/dr/scripts/app_backup.py`, `deploy/installer/app_installer/backup.py` | Base backup verification, retention, isolated recovery containers | Standby backups, archive survival, PGDATA, optional activation and scoped state |
| `deploy/dr/app_dr_host/promoted.py`, `app_ops/failover.py` | Ordered recovery, checking before opening traffic, explicit failure stages | Replace Keycloak and fixed nginx checks with declared component checks; use current registration lifecycle |
| `tests/test_dr_boundary.py`, DR tests, runbooks | Safety expectations and scenarios | Assert this product's names, bindings, metadata, offline layout and failure boundaries |
| QEMU/Proxmox quarantine tooling | Optional lab/runbook reference | Do not make a particular hypervisor or Guest Agent privilege change a product requirement |

Some small algorithms can survive unchanged, but no complete package is assumed
drop-in compatible. The reference DR group is already derived from its `Platform`
model, including optional apps; it is not simply a fixed three-database list.
Its model nevertheless derives resource names and database roles by convention
and treats Keycloak specially. Do not copy that model into `deployment`.

### Concrete integration differences

1. **Runtime granularity.** `write_component_units_and_imports()` creates one
   service for the complete component YAML. The reference has separate database
   and application services. App1's init container and Identity's startup both
   write SQL; neither may start against an unpromoted standby.
2. **PGDATA.** Current demo manifests mount `/var/lib/postgresql/data` but set
   `PGDATA=/var/lib/postgresql/data/pgdata`. Reference bootstrap/promote/recovery
   helpers often assume the mount root is PGDATA. Copying these commands is unsafe.
3. **Credentials.** This product owns persistent files and renders Secret YAML;
   the reference uses Podman secret objects. New standby credentials must match
   the data being restored; ordinary missing-password safeguards must remain.
4. **Release identity.** This product has a bundle, version and dependency range
   per component. Reference `readiness()` expects one product revision and image
   archive list. It checks archive presence, not a complete ongoing integrity
   attestation. Readiness here must cover the selected release set and checksums.
5. **Package context.** `deployment.common.ROOT` derives from the imported package
   and `HOME` from the service account. Importing one arbitrary component bundle
   and silently reusing its globals for other releases is incorrect.
6. **Compatibility.** The reference uses dataclasses and APIs such as
   `shlex.join`, `capture_output=True`, and `unlink(missing_ok=True)`. Preserve
   Python 3.6 with stdlib/PyYAML on targets; do not vendor another runtime.
7. **Maintenance.** `install` regenerates runtime and may restart registration
   owners. A separate DR command cannot safely patch generated YAML if the next
   ordinary install overwrites it. Ownership and upgrade rules are necessary.
8. **State beyond SQL.** Credentials, authoritative config, registration inputs,
   and `identity-protection` are needed or need an explicit loss policy. Raw
   Podman storage-directory copying is not a valid solution.
9. **Lab topology.** The existing acceptance harness has DEV and PROD roles;
   DEV intentionally has fapolicyd disabled. Two production-like DR hosts require
   a distinct DR scenario/configuration, not relabelling an unchanged DEV run.

### Reference limitations to fix or state explicitly

- Backlog D2 in the reference is still planned: backup/WAL history is local to
  the primary; a standby skips nightly backup. Do not inherit this limitation.
- The configured RPO target is informational. Zero received-but-unreplayed WAL
  does not establish zero unreceived WAL or prove a time-based loss bound.
- Promotion is not an atomic cross-database transaction. A group does not by
  itself guarantee application consistency across independently committed stores.
- Fencing remains an external action. A typed confirmation and unreachable TCP
  port are not proof that the original host cannot serve writes elsewhere.
- Failed SSH/timeouts do not prove a remote mutation stopped. Reconcile actual
  host state under the host lock before retrying.
- The reference has no complete DR deactivation command. Design one here.

## 4. Proposed component and installation contracts

Use an optional, versioned `recovery` declaration in the component descriptor,
compiled from `bundles.yaml`, bundled in `bundle.yaml`, and persisted in installed
metadata. Its absence means **not assessed for recovery**, not stateless and not
DR-enabled. Validate it through the existing pure validation path. A worker with
no declaration must still deploy normally without the operations package.

The following is a proposed schema to freeze during the feasibility step, not
configuration currently accepted by the program:

```yaml
product: example-product
components:
  orders:
    requires: [gateway, login-service]
    recovery:
      schema: 1
      postgres:
        - id: main
          pod: orders-postgres
          container: db
      volumes:
        orders-data: postgres/main
      checks:
        - path: /orders/health
          status: 200
```

The `pod`/`container` selectors identify effective manifest resources. Derive and
validate PVC, data mount, PGDATA, image, port and credential source from those
same effective documents. Do not introduce independent copies of all DB settings
in inventory YAML. Unsupported/ambiguous bindings fail before mutation. Infer
runtime container names through verified Podman information, not a demo naming
formula. Validate all resolved paths are within the intended data mount.

Every persistent resource must have a recovery classification:

| Classification | Behaviour |
| --- | --- |
| PostgreSQL binding | Replicate and back up the whole selected PostgreSQL instance; not an arbitrary SQL database subset |
| Derived configuration/import | Rebuild from complete authoritative component/config/registration inputs |
| Static supplied files/credentials | Provision securely; include in the private recovery inventory and backup |
| Explicitly disposable | May be recreated on recovery; document consequences and test them |
| Unsupported mutable data | Refuse activation until a supported strategy exists |

Cross-check these declarations against PVCs, hostPath mounts and the existing
`SECRET_FILES`/`VOLUME_FILES` model. Unknown persistent mounts are not disposable.
Declarations for derived imports must agree with actual registration owners.
Do not add arbitrary shell hooks as an escape hatch for unsupported state.

For the demo, propose `identity-protection` as explicitly disposable on disaster
recovery, with loss of existing Identity cookies/antiforgery flows and required
fresh login. Confirm this through the actual application/browser tests; do not
generalise this choice to other applications' Data Protection keys. Signing keys,
client private keys, database passwords and demo-user input files remain required.
Never delete the original host's keys merely to prepare a standby. On recovery
use a deliberately empty target volume with documented ownership rather than
silently reusing an unrelated/stale key ring. Session continuity is not promised.

Data Protection automatically rotates keys; a one-time key-ring copy is not a
continuous protection strategy. If the product requires preserved protected
payloads rather than disposable login state, this v1 policy is insufficient and
activation must fail until that storage strategy is implemented.

The group includes the transitive dependency and registration-owner closure.
Reject omitted required components, incompatible versions and dependencies on
unprotected state. Keep unrelated components outside the group. A stateless
component still needs its release and configuration staged for recovery.

Example installation inventory, also proposed:

```yaml
schema: 1
group: business
user: appsvc
hosts:
  site-a: {role: primary, address: 192.0.2.10}
  site-b: {role: standby, address: 192.0.2.11}
components: [gateway, login-service, orders]
replication_ports:
  login-service/main: 15432
  orders/main: 15433
policy:
  rpo_target_seconds: 30
  backup_keep_days: 7
```

Host identity, host-key trust and fencing identity must be verified separately;
these sample values grant no access. Inventory contains no passwords or key bytes.
Use explicit site-local public access/DNS procedures and the existing public
origin/issuer contract. The sample RPO is a requested objective, not a guarantee.

Persist an immutable generation record: group/host identities, component
descriptors and versions, bundle and image identities, relevant config and
recovery-input generation, resource bindings, operations/deployment compatibility,
and completion state. Keep private material and fingerprints of low-entropy
credentials out of public metadata and logs. Store secrets separately with
private permissions. Refer to complete verified generations, not mutable tags.

Older supported non-DR descriptors without `recovery` remain readable as
unassessed. Adding DR may require a normal upgrade to an engine that implements
the new contracts. Test that upgrade with retained data. This is not a request
to restore obsolete 0.1.x layouts or add broad migration machinery.

Old bundle executables do not acquire the new ownership guard just because a
marker exists on the host. Require compatible engine code in every executable
bundle used with a managed installation; retire obsolete trusted releases where
the host trust policy permits. Running a retained pre-guard installer against
managed state is unsupported and cannot be made safe by a new Python check it
does not contain. Explain this limitation rather than claiming all historical
installer binaries are automatically blocked.

## 5. Runtime ownership: preferred bounded design

Keep ordinary non-DR runtime unchanged. When an operator enables DR, the
operations package owns the protected group's runtime until disablement. It
derives database-only and application units from the same validated component
documents. This is a runtime split, not mandatory new component bundles.

Place the ownership check and local serialization in the deployment package as
a small data-only contract. It must not import or execute DR. On a managed
component, ordinary mutating commands refuse before side effects and name the
operations workflow to use. `validate` remains read-only and must not acquire a
write lock or inspect secret bytes. Management status and desired declarations
must remain inspectable without the operations package.

The guard applies also when an apparently unrelated component operation would
mutate/restart a managed registration owner. Never restart a protected owner
through a side path. Before enabling DR, existing pending install/uninstall work
must be finished or explicitly resolved; do not clear it as setup.

Use one service-home mutation lock for deployment and operations, with separate
durable records for their own work. Locks are released on process exit; ownership
and incomplete transitions survive. An internal operations-owned lifecycle path
may invoke shared functions under the same lock and validated ownership record.
Do not expose a general `--ignore-dr` bypass, use an environment-variable bypass,
or repeatedly remove the ownership marker around ordinary install commands.
This is coordination against mistakes, not a security boundary against the same
Unix account deliberately editing its own files.

### Ownership transition

1. Read and validate the entire proposed group, source state and both hosts.
2. Stage/check all releases, configs, credentials and candidate units outside
   systemd generator search paths. Persist intent before changing live runtime.
3. Enter the ownership transition and stop affected ordinary component units.
4. Retire their source Quadlets from generator search paths, reload, and verify
   that a reboot cannot start both old and new units. Retain recoverable source
   configuration and release identities, not an untracked patch of generated YAML.
5. Publish operations-owned database and application units on primary, retaining
   the same data bindings. On standby publish database-only units. Validate the
   selected Pods' resource closure and do not accidentally include app init Pods.
6. Verify database roles, primary application health and standby replication;
   write completion only after checks succeed.

On failure, default to a recorded incomplete transition with safe stopped
applications, not automatic data rollback. Define and test recovery for every
cut point, including a reboot after only some unit files were published.

DB and application containers sharing one inseparable Pod are unsupported for
this first DR implementation; refuse clearly. The ordinary installer may still
support such a component without DR. Independent database Pods inside the same
component, as in the current demo, are the supported starting point.

Transformations are narrow PostgreSQL operations: explicit replication endpoint,
backup mount and necessary configuration. No generic YAML patch language.
Feed transformed documents through the existing validation/materialization
checks before runtime writes. Do not maintain a second implementation of
credentials, imports, registrations, dependency checks or uninstall inventory.
Primary install/upgrade through operations must retain the established owner
pending/acknowledgement ordering and selected-component isolation contracts.

The first prototype must identify the minimal shared prepare/apply functions
needed to avoid copying `install_component_plan()`. DR owns the alternate unit
layout; ordinary deployment keeps its current writer. Use explicit arguments,
not monkey-patched `common.ROOT`, callbacks scattered throughout the installer,
or a new transaction framework. If a materially broader refactor is required,
report its evidence and revised design before expanding the implementation.

## 6. Distribution, local package context and offline compatibility

Suggested ownership layout (module names may be simplified during implementation):

- `operations/`: CLI, inventory, SSH transport, host adapter, replication,
  recovery, backup and operation records. Keep ordinary control flow visible.
- `deployment/`: existing component engine plus only the narrow declaration,
  lifecycle reuse and ownership/locking support justified above.
- A separate operations archive builder; ordinary `bundle.py` does not include
  `operations/`. Never add operations code under a recursively copied component
  `scripts/` directory accidentally.
- `docs/runbooks/` and focused product/harness tests. Hypervisor-specific lab
  helpers stay under acceptance tooling.

Version the operations protocol and required deployment capabilities. Check
compatibility before staging mutations. Keep engine versions separate from app
component versions. Pin the selected release set, reject incompatible engine
mixes, and test at least two independently versioned component bundles.

For local component work, use a release-specific worker process importing that
release's compatible `deployment` package, or explicitly pass a release context
through a small shared interface proven in the prototype. Never let Python's
module cache select the first bundle for all components. Package this worker
and its dependencies offline and verify it from outside the checkout.

Provision every needed image, helper, executable and document before an incident.
Use checksums for distribution integrity; do not describe them as authenticity
unless an actual signing/trust mechanism is implemented. Check archives before
activation and recovery; scheduled readiness must report the verification state
and detect missing/changed release inputs. Retain exact trusted code generations
needed by incomplete operations. Retire fapolicyd trust entries only after no
unit or pending operation references them. Preserve SELinux enforcing and rootless
volume ownership; do not copy the reference's different trust paths blindly.

Failover runs locally on the surviving host without primary, original checkout,
internet, controller, package repository or online CA. No pip/venv on targets.
Privileged host setup is explicit; ordinary database/runtime work is rootless.
Do not require broad passwordless sudo or enable Guest Agent execution by default.

## 7. Data, credentials and backup

### Provisioning and continued readiness

Stage persistent configuration, all selected private file sources and public
registration inputs as one verified recovery generation. Include inherited
settings and CA trust. Reconstruct derived imports using existing code; do not
copy all service-home state or duplicate another host's pending-operation record.
Do not record standby as an ordinary fully installed active component just to
bypass dependency checks; its prepared generation and role are operations state.

Check file type, paths, permissions, complete membership and existing values
before transfer writes. Refuse traversal, symlinks escaping declared roots and
conflicting existing credentials. Use protected stdin/SSH and private staging;
never argv passwords or secret-bearing stdout/stderr in operation logs. Partial
transfer is resumable by verified generation and atomic publication, not assumed
to be transactional across hosts. Failed transfer must not mark standby ready.

Activation takes existing credentials; it must not generate new app/database
identities on standby. Replication-only credentials are new, explicitly owned
operations resources. General credential rotation is deferred: drift or changed
inputs invalidate readiness and require a documented reconciliation; do not
overwrite mismatches under a misleading `sync` command. Declare direct edits
during active operations unsupported and detect them where practical. Never
promise immediate detection of arbitrary administrator edits.

### PostgreSQL and network

Validate source instance identity, version/image compatibility, PGDATA, available
space, role permissions, WAL settings and topology before bootstrap. Physical
replication covers the whole instance. Reject external tablespaces/WAL paths in
v1 rather than copying an incomplete instance. Validate actual runtime bindings
agree with the prepared manifests; do not treat command failure as absence.

Use dedicated least-privilege replication credentials, TLS verification of the
expected peer, explicitly assigned host ports and rules restricted to the peer.
No open port or new timer for installations never enabled. Record original and
owned settings so disablement can remove only what operations introduced.
Bound WAL retention and monitor slot invalidation, archive failure and free disk;
retention bounds can require standby reseeding after a long outage.

Bootstrap creates only fresh owned destination storage. A failed base backup or
existing slot is not permission to delete/reuse arbitrary resources. Record the
instance system identifier, slot ownership and destination before creation;
reconcile exact state on retry. Promotion/reseed must compare these bindings,
not just resource names.

### Backup history that survives one host loss

Preferred v1 design: each DR host maintains full verified base backups and a
local WAL archive, with standby archiving enabled using `archive_mode=always`.
This requires explicit setup and a fresh real test: it is not implemented in
the reference. Enable backup before the first disaster, not only after promotion.
Backups remain optional for a standalone non-DR installation.

Use `pg_basebackup` with the required WAL included and `pg_verifybackup`; publish
the completed-backup marker only after verification. Preserve the full WAL chain
needed by every retained backup, including timeline history and active restores.
Do not prune based only on timestamps or the oldest filename. Preserve older
usable generations across reseed; do not delete archives because replication
was reset. Record gaps and the earliest/latest tested recovery coverage.

Validate standby backup prerequisites including `full_page_writes` on primary,
replication access on standby, and adequate WAL senders. Promotion during a
standby backup may invalidate that backup: fail it, do not publish completion,
and prioritise safe failover. Make backup/pruning and destructive recovery
coordinate explicitly. WAL archival must be idempotent, detect conflicting
existing contents and only report success after durable publication.

Retain the matching protected config/credential generations alongside database
backup metadata. Database files alone are not a complete product recovery set.
Recoverability across app/schema versions must name the compatible release set;
do not start today's app automatically against an older restored schema.

PITR first restores into a distinct owned volume/container with no application
network or published port, paused/read-only for inspection. Replacement of live
data is a separate explicitly confirmed operation; the first implementation may
provide a tested operator runbook for that step. Test named-point and timestamp
recovery, timeline changes and recovery from the surviving host's history while
the original primary is unavailable.

For multiple stores, document that group promotion and equal restore timestamps
do not create distributed transaction consistency. Application-level coordination
requirements must be declared; do not promise consistency beyond the tested app.

## 8. Operation and failure contracts

Suggested commands below are requirements for the new CLI, not existing commands.
Use one consistent `./ops` wrapper running Python with `-B`.

| Operation | Required contract and retry behaviour |
| --- | --- |
| `validate` | Pure declaration/release-set validation; no secret-byte reads, host commands or persistent writes |
| `preflight` | Read-only runtime/network inspection; unlike the reference, does not silently stage tools; missing provisioned tools are a prerequisite failure |
| `enable` | Explicit staging and ownership transition; validates existing install, protects retained data and records partial work |
| `bootstrap-standby` | Fresh owned storage only; reconcile incomplete copies/slots before retry; no overwrite of unexplained existing data |
| `status` / `check` | Role, streaming, replay/receive positions, archive/backup/credential readiness, disk, expiry and release coverage; never changes role |
| `failover` | Local to surviving host, exact fencing and target confirmation; group preflight, durable promotion intent, sequential promotion, app recovery and health checks |
| `rebuild-standby` | Explicit fenced old-host identity and destructive confirmation; validate entire group before deletion; never force-remove in-use/unowned volumes |
| `reseed-standby` | Requires proof of a read-only database-only standby; never a shortcut to erase a writable primary |
| `upgrade` | Coordinated compatible component release-set change with durable progress; keeps/revalidates replica and recovery inputs |
| `disable` | Controlled detach to one writable host; stops/disarms standby, removes owned slots/endpoints/timers, restores ordinary deployment ownership |
| `backup configure/create/status` | Explicit standalone or DR backup setup and verified generation; independent of promotion history |
| `restore verify` | Isolated recovery only; report selected backup, target and result without touching live data |

For each mutating operation implement a short state table: preconditions, durable
intent, each irreversible boundary, success criteria, retry reconciliation and
operator recovery. Retain the reference's refusal of blind partial-promotion
retry. A completed promotion may be followed by retry of app recovery; a partial
promotion needs explicit inspection of every database before a recovery decision.
No automatic rollback of committed data, schema migration or role changes.

Use host-side locks and group operation identities, not controller memory alone.
A lock file only serializes local execution; it is not distributed fencing.
On uncertain remote results, query actual role/resources/records and verify
generation before continuing. Never interpret SSH timeout as permission to repeat
deletion. At every step distinguish `prepared`, `replicating`, `promoting`,
`active`, `degraded`, `disabling` and incomplete operations; do not mark ready on
successful process exit alone. These labels need not become a generic state engine.

Fencing procedures must prevent the former primary serving writers and prevent
automatic restart. Include the returning-old-primary case. Leave provider-specific
fencing to a documented operator procedure in v1; confirmations attest to that
procedure, not a network check's ability to establish physical isolation.

Report replication measurements with their observation time. Separate receive
lag, replay lag and time since last observation; an idle database's old last
transaction timestamp is not by itself evidence of lag. If primary is lost,
state that unreceived transactions cannot generally be counted from standby
alone. A stricter measured RPO requires an explicit measurement method and real
link tests, not relabelling the configured target as an achieved result.

### Compatible upgrades

In v1, use planned maintenance and the ops command for protected components.
Before touching primary, stage/verify all recovery inputs on standby and record
the pending release generation on both. Refuse normal deploy/uninstall changes to
managed resources, including owner restart side effects. Check app dependency
ranges and actual DB/image compatibility; PostgreSQL major upgrades are refused.
Do not execute migrations on read-only standby. Any migrations run on primary
must become available through replication before readiness is restored.

A primary crash during upgrade must not start a guessed app/schema combination
on standby. The pending generation blocks ordinary failover completion until its
specific recovery procedure establishes which version is usable. Define that
procedure and test an interrupted upgrade. If migrations are irreversible, state
that rollback is not provided. Membership changes use a documented coordinated
reconfiguration (or disable/change/re-enable in v1), never source omission alone.

### Disablement and deletion are different

Safe disablement requires control of both hosts, or independently established
fencing of an unreachable former participant. Disarm old units against reboot;
preserve the current primary's data/config/credentials and restore its ordinary
component units before releasing the management guard. Remove only owned
replication slots/users/endpoints and timers after their users have stopped.
Retain ownership if the transition is incomplete. A missing peer prevents a
claim of fully cleaned-up DR until its cleanup is recorded later.

Retain backup history and standby data by default, with no orphaned writers or
timers. Provide a separately confirmed purge/export procedure for owned retained
resources. If standalone backup remains enabled, its retained archive and timer
are explicit backup ownership, not orphaned DR. Do not meet a cleanup requirement
by silently deleting the only recovery history. Re-enable must detect retained
state and reconcile it explicitly rather than overwriting it.

## 9. Expected changes to the deployment core

| Area | Bounded purpose |
| --- | --- |
| `catalog.py` and descriptor readers/writers | Optional recovery metadata and capability/schema compatibility; no parallel `Platform` model |
| Existing validation functions | Recovery resource bindings and coverage; normal manifests without recovery still valid |
| `bundle.py` | Carry declarations as data; existing bundle isolation/checksum/private-file contracts retained |
| Lifecycle entrypoints | Data-only ownership guard and serialization, including affected registration owners |
| Existing prepare/apply functions | Minimal explicit reuse boundary for operations-owned runtime; keep validation-before-effects ordering |
| Tests and docs | Boundary, retained-data enable/disable/upgrade and no-DR regressions |

No planned change to rootless Podman, YAML workload format, normal component
catalog usage, ordinary CLI commands, image supply model or Python minimum.
Do not automatically expand backlog 7 to every PostgreSQL layout; support and
test the existing layout plus its PGDATA subdirectory first. Keep backlog 2's
credential rotation separate. Backlog 3's backup/recovery use case stays usable
without standby even if implemented by this operations package.

## 10. Delivery sequence and gates

### A. Runtime feasibility and design freeze

Produce a small executable prototype/test fixture, not a second production
installer. On a renamed external-image component with separate DB/app Pods:

- Render the effective documents and identify the exact PostgreSQL binding.
- Derive database-only standby and active serving units from those documents.
- Prove safe transition from the existing combined unit, with retained data,
  including restart/reboot and failure after retiring the original unit.
- Prove only one PostgreSQL process can mount/write the instance's data at a time.
- Demonstrate app init SQL never runs before promotion and that normal deployment
  cannot overwrite/restart the managed runtime through registration side effects.
- Show the small shared lifecycle API, per-release import context and proposed
  schema in a diff. Check that transformed docs pass existing safety validation.

Gate: a real rootless Podman/systemd check on an isolated host. Without runtime
access, deliver runnable steps and mark this gate blocked; source/mocks alone do
not settle runtime feasibility. Do not expand into the whole implementation on
an unproven ownership scheme. Record the measured change scope. If the bounded
design works, freeze the schema and local API in this document and proceed.

### B. Declarations, package and ownership

Implement recovery metadata, group closure, private generation records, optional
operations packaging, compatible local worker and ownership/lock contract.
Add no-DR artifact/import checks, read-only validation tests, old-supported-
descriptor handling, and worker/no-gateway fixtures. Gate: all existing tests
still pass, ordinary bundles contain no ops code, isolated ops entrypoints work.

### C. Backup as a standalone optional feature

Port base backup, verification and isolated recovery against actual PGDATA.
Record credential/config/release generations. Enable archiving explicitly,
verify retention and deletion scope. No dependence on DR promotion records.
Gate: retain data across configuration/restart; demonstrate isolated restore
with before/after rows and no changes in the live database.

### D. Enablement and replication

Implement the ownership transition, protected input transfer, TLS, fresh
bootstrap, monitoring and standalone-to-DR path. Configure and verify standby
base backup/WAL history. Gate: retained primary data/credentials, primary serving,
standby database-only, all streams verified, two independently usable histories.

### E. Fenced group failover

Port durable promotion logic and app recovery. Integrate registration rebuild,
correct public origin, certificates and declared checks. Exercise partial
promotion refusal, local execution with primary/controller absent, and fresh
login. Gate: real functional access after failover plus isolated PITR from the
surviving host's pre-failure history.

### F. Rebuild, upgrades and disablement

Implement quarantined old-host rebuild, ordinary standby reseed, compatible
upgrades, credential-drift refusal and safe detach/purge separation. Gate:
fresh-process and reboot failure recovery; scoped deletion; original non-DR
workflow restored after disablement; re-enable preserves intended data.

### G. Product acceptance and documentation

Complete the renamed product and current demo two-host scenarios, runbooks,
quality checks and understandability review. Record results against one exact
revision. Only then mark item 24 complete and the draft PR ready. Report any
remaining limitations rather than carrying forward a historical green verdict.

## 11. Verification requirements

### Product tests

Test decisions and actual command arguments/state boundaries, not just method
calls or return values. Use new processes for retries and failure injection:

- No recovery declaration; no ops installed; minimal worker without gateway,
  login, certificates or database. Same normal install/retry/uninstall behaviour.
- Renamed product, external images, two independently versioned components,
  configurable PGDATA/PVC/Secret bindings, multiple declared DB Pods in a group.
- Missing/unclassified persistent state, unsupported DB layout, mixed-engine
  versions, stale recovery generation and incomplete dependency closure refused.
- Wrong host/machine identity, reachable old primary, wrong confirmation,
  read-write standby, unknown/lagging WAL and split-group refusal.
- Fail before/after journal writes, each promotion, credential publication,
  ownership transition, image load, unit writes, owner restart and completion.
- Partial bootstrap and orphan slot; expired TLS; broken archive; disk pressure;
  invalid slot; ambiguous SSH timeout; lock contention with normal deploy.
- Upgrade during replication and failure during schema change; failover blocked
  from selecting an unverified release generation; old archives retained.
- Every deletion uses recorded owned resources; inspect failure is not absence;
  unrelated components/data/registrations and original credentials are preserved.
- Disable with healthy peer, missing peer, interrupted detach, retained backups,
  explicit purge, and later re-enable.
- Malicious/invalid transfer paths and archive members, secret-bearing command
  failures/timeouts and log redaction; no secrets in release/operations bundles.

Run the documented existing checks and extend their scopes to new code:

```sh
python3 -B -m unittest discover -s tests
python3 -B -m unittest discover -s acceptance -p 'test_*.py'
ruff check deployment/ operations/ bundle.py tests/ acceptance/ dev/smoke-test.py
ruff format --check deployment/ operations/ bundle.py tests/ acceptance/ dev/smoke-test.py
pyright deployment/ operations/ bundle.py tests/ acceptance/ dev/smoke-test.py
vermin -t=3.6- deployment/ operations/ bundle.py tests/
shellcheck deploy.sh build-bundle.sh dev/*.sh scripts/*.sh acceptance/remote.sh examples/run.sh PKI/generate.sh
git diff --check
```

Add new Python/shell entrypoints to these checks. If names differ from the
proposal, update commands. Actually import/run the packaged target code on the
supported Python/PyYAML combination; static compatibility analysis is not enough.
Do not apply the target Python floor to newer-Python controller-only acceptance
code unnecessarily. No new CI platform is required merely to satisfy this list.

### Real acceptance harness

Reuse current recording/first-failure/evidence conventions. Add a separate DR lab
configuration with build/controller, primary and standby roles. Both runtime
hosts must satisfy production hardening. A build/controller can be a separate
machine or an explicitly provisioned lab role; do not mutate the existing DEV
snapshot assumptions silently. Never reset unrelated machines.

Implement the following proposed runnable interface (not available today), or
update this plan and the runbook with the final exact equivalent before use:

```sh
python3 -B acceptance/dr_acceptance.py --config /absolute/path/dr-lab.env --run dr-YYYYMMDD-HHMMSS run
python3 -B acceptance/dr_acceptance.py --config /absolute/path/dr-lab.env --run dr-YYYYMMDD-HHMMSS report
```

The runbook must list exact commands and prerequisites for every numbered stage:

1. Ordinary offline installation; create data and capture private credential
   comparison evidence without exposing bytes. Prove no DR ports/timers/code.
2. Enable DR on that retained installation; verify TLS replication, readonly
   standby and absent app/init execution there. Reboot both roles in turn.
3. Create verified backups/WAL history on both; create before/after markers.
4. Isolate/fence primary using the lab infrastructure. Confirm it cannot auto-
   restart. Make primary and the external controller unavailable to recovery.
5. Fail over locally on standby; verify all group roles, API writes, dependency
   services, real browser login, unchanged public issuer and intended key policy.
6. Restore pre-failure data into isolated containers using only surviving history;
   check before row present/after row absent and live data unchanged. Repeat for
   named point, timestamp and a timeline change; cover each protected database.
7. Bring old primary back quarantined; prove it does not start as writable;
   rebuild, verify new replication direction and marker propagation.
8. Lose/invalidate a slot and reseed the standby; primary continues to serve.
9. Perform a compatible app upgrade and an interrupted upgrade recovery;
   independently versioned sibling remains correct. Inject credential drift.
10. Disable DR with data/history retained; ordinary install works; then re-enable.
11. Repeat core coverage with renamed components/external images and verify
    non-DR/minimal-worker regression. Report measured failover duration, observed
    loss/positions and backup coverage separately from configured RPO/RTO goals.

Exercise representative failure paths under real Podman as well as mocks.
Report product tests, harness tests and runtime runs separately. Record version,
checksums, host/image facts, commands and redacted evidence. A passing report
must not imply cross-database transaction consistency or guaranteed zero loss.

## 12. Understandability and review checklist

Trace a successful enable/failover and a failure/retry from authoritative YAML
through effective manifests, resource bindings, protected input generation,
runtime ownership, durable operations record and completion. Name the functions
that decide versus execute work. A moderately experienced Python developer must
be able to explain the order and resource ownership without discovering hidden
imports, mutable globals or filename conventions.

Check explicitly: declaration generality; isolated offline delivery; retained
credentials; correct DB binding; pending-operation durability; scoped deletion;
Python 3.6; SELinux/fapolicyd; read-only validation; declared product naming and
single-product service-home isolation; and the no-DR boundary.
Preserve the reference's safety properties while reducing its product-specific
assumptions. Passing tests alone is not a GREEN understandability result.

## 13. Required handoff from the implementation agent

- Agreed schema and runtime ownership decisions, including the feasibility result.
- List of core changes and why each is needed; reused/adapted reference modules.
- Complete operations/recovery runbooks, supported limitations and compatibility
  matrix; backup-only and post-install enablement instructions.
- Exact tests run and results, separate runtime evidence and unexecuted gates.
- Failure/retry and deletion-scope review plus understandability verdict.
- Updated architecture/components documentation, backlog and review-guide gaps.
  Do not mark a planned design or a reference repo's acceptance as implemented here.

## 14. Sources and technical follow-up basis

Repository findings above are source analysis, not external best-practice claims.
Pinned reference sources:

- [Reference DR tree](https://github.com/gunstein/podman_test/tree/517119764927b9bb4532ee42980fde75f18f6988/deploy/dr)
- [Reference component model](https://github.com/gunstein/podman_test/blob/5171197/deploy/installer/app_installer/apps.py)
- [Reference boundary tests](https://github.com/gunstein/podman_test/blob/5171197/tests/test_dr_boundary.py)
- [Reference operations distribution tests](https://github.com/gunstein/podman_test/blob/5171197/tests/test_operations_distribution.py)
- [Reference backup-history gap D2](https://github.com/gunstein/podman_test/blob/5171197/docs/BACKLOG.md)
- [Historical acceptance report and its limits](https://github.com/gunstein/podman_test/blob/5171197/docs/history/ACCEPTANCE-c11ed00.md)
- [Reference runbooks](https://github.com/gunstein/podman_test/tree/5171197/docs/runbooks)

Primary documentation consulted 2026-10-18:

- [PostgreSQL 17 pg_basebackup](https://www.postgresql.org/docs/17/app-pgbasebackup.html):
  physical backup is instance-wide; standby backups are supported with specific
  prerequisites, and a promotion during such a backup can invalidate the attempt.
- [PostgreSQL 17 WAL configuration](https://www.postgresql.org/docs/17/runtime-config-wal.html):
  `archive_mode=always` enables archiving during recovery/standby. Enabling it is
  a startup setting; archive success must reflect actual successful storage.
- [ASP.NET Core Data Protection key management](https://learn.microsoft.com/en-us/aspnet/core/security/data-protection/implementation/key-management?view=aspnetcore-8.0):
  automatic key rolling means a bootstrap-only copy is not a continuing key-ring
  replication mechanism. This plan's disposable-demo-session policy is a design
  proposal and still requires application-level verification.

Remaining implementation evidence gates are explicit: safe runtime ownership
transition, standby backup/retention across promotion and reseed, demo fresh-login
behaviour with disposable protection keys, interrupted upgrades, and packaged
Python 3.6 compatibility. These require executable tests, particularly the lab;
additional prose analysis cannot substitute for them.
