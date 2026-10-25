# Item 69 implementation plan: signed RPM delivery, one command per role

Status: plan, revision 3.3 (2026-10-25), after AI reviews of revision 1
(`7a9f9cf`), revision 2 (`f05f63b`) and revision 3 (`05fb034`, which cleared
WP0 to start as a bounded investigation), and a first WP0 attempt that
stopped before any probe; WP0 now runs every probe from `clean-agent` without
new snapshots (revision 3.2, `a404e91`). Revision 3.3 declares the WP0
journal/daemon trust observations as an automation adaptation and records
WP0 verification status after the bounded-investigation merge (`3dc304e`).
Not implemented; WP0 is not complete. Work package 0 is an
investigation; statements marked "confirm in WP0" are hypotheses about rpm,
dnf or fapolicyd behaviour, and WP1 starts only when every mandatory probe
passes. Read
[item 69](../BACKLOG.md#69-paper-first-installation-for-closed-networks)
("Chosen direction"), the
[RPM prototype results](../acceptance/RPM-PROTOTYPE.md#results-2026-10-25)
(historical: one manual run, default policy, network on), the
[paper-first lab results](../acceptance/PAPER-FIRST-LAB.md), the
[item 66 plan](INSTALL-SET-PLAN.md), the [review guide](REVIEW_GUIDE.md)
(sections 1, 6 and 7) and the current [production manual](PRODUCTION-INSTALL.md).

## Outcome and scope

Today the administrator pastes a 61-line tool bootstrap and a setup block, and
the runtime user pastes a values block and shell blocks of about 3 700
characters. None of it can be typed from a printed manual.

After this item, on a standalone OL9 server on a restricted network, from one
printed manual:

- **Administrator**, once per new server: about ten short lines with OS tools
  only (copy the key and tools package to a root-only directory, check the
  fingerprint and the package signature against the product key alone, install
  `<product>-tools`). Then, for every delivery: **`sudo <product>-admin /mnt`**.
- **Runtime user**, after a real login (console or SSH): **`<product>`**.
- Console-only use and one person holding both accounts are main flows.

In scope: supplier build of release and tools RPMs, both commands, product-bound
signature verification, immutable versions, preflight, private credential
delivery, retirement with a guard, removal of the `release.py` publication
flow, manual rewrite, harness scenario with a strict fapolicyd profile. Not in
scope: a supplier set manifest (dropped in item 66), rollback/downgrade,
credential generation (45b), encryption at rest (37), compressed image
archives, product uninstallation (tools erase stays refused), migration of
existing lab installations (pre-customer exemption).

## Product-owner decisions (2026-10-25)

| Question | Decision | How this plan applies it |
| --- | --- | --- |
| Signature trust | **Bound to the product's own key.** A valid signature from any other imported RPM key never authorizes this product, also not for the first tools installation or repository delivery. | Every check, including the OS-only bootstrap, verifies the exact package bytes against a keyring that contains only the delivered product key whose primary fingerprint matched the paper (its signing subkeys included). No Key ID comparison anywhere. |
| Immutable versions | **Yes.** One product/component/version has exactly one content; a rebuild needs a new version, also for internal-repository delivery. | Prevented at the source (supplier ledger) and on the documented path (admin refuses); a bypass with plain `dnf` is **detected** before use, which is stated as detection, not prevention. |
| Removal guard | **Yes, also for plain `dnf remove`,** with a conservative stop whenever the state is unclear. No override in the ordinary flow. | Plain `dnf remove`/`rpm -e` of any product package is **always refused**; only `<product>-admin` removes, one authorized package at a time, after a check that does not depend on the user manager. Anything unclear stops. |

## Guarantees of today's `release.py` flow and their replacement

| Today (`scripts/release.py`) | After this item | Kind |
| --- | --- | --- |
| Archive signature against a pinned per-product keyring | RPM signature and digests verified against an isolated product-only keyring on a root-only copy, before dnf (see "Signature verification") | replaced |
| Same version with other content refused before publication | Supplier ledger prevents a second signed content; admin refuses a candidate whose identity differs from the installed one; bypass via plain dnf detected before use (see "Immutable versions") | replaced (prevention on the documented path, detection on bypass) |
| Protected, root-owned release tree and records | RPM-owned files under root-owned `/var/lib/<product>/releases/`; rpmdb is the record; `rpm -V` verifies | replaced |
| Exact-inventory fapolicyd `file` trust and `wait_trust` | rpmdb trust through `rpm-plugin-fapolicyd`; before PASS a bounded poll of `--dump-db` until every installed `deployment/` and tools file appears from `rpmdb` with matching size/digest, then a self-check as the runtime account | replaced |
| `integrity` none/size/sha256 accepted | only profiles verified in WP0 | narrowed |
| Preflight before publication | preflight in `<product>-admin` before release or host changes; bootstrap prerequisites as explicit tools `Requires:` | replaced |
| Journaled retirement that resumes | guarded one-package removal with postcondition checks and a defined repair (see "Retirement") | replaced |
| Stdin tool bootstrap with an independent SHA256 | OS-only paper bootstrap with isolated-keyring verification | replaced |
| Publication lock per product | rpm transaction lock plus one admin run at a time (`/run/<product>-admin.lock`) and the runtime operation lock | replaced |
| Checksums inside bundles | kept; the runtime verifies the release tree against `checksums.sha256` before install | kept |

Given up deliberately: trust records in fapolicyd's `file` database and the
stdin bootstrap.

## Relationship to item 66 (authoritative)

| Item 66 decision | Status under this plan |
| --- | --- |
| Admin side: `release.py setup --all-in-input-dir`, publication as selection | **Superseded:** installation of release RPMs by `<product>-admin` is the selection. |
| "Newest published release" from published records | **Superseded:** newest release whose directory is owned by an installed release RPM with a valid identity; other directories are ignored with a warning. |
| Guard: never older than installed; refuse two versions of one component in one run | **Kept**, applied by `<product>-admin`. |
| Each component's own `deploy.sh` as child process; no imports across releases | **Kept.** |
| Order, compatibility, skip completed, stops (exit 3), no new progress record, pending first | **Kept**, in `<product>`. |
| `--settings` data file | **Kept** as the answer-file format. |
| `--credentials <dir>` mirroring `<component>/credentials/<group>/<file>` | **Replaced** by the incoming directory and the `delivered` declaration. |
| Retirement by explicit administrator `retire` | **Replaced** by `<product>-admin` retirement. |

Where this table says superseded or replaced, this plan wins; there is no
fallback to published records and only one credential format.

## Release interface (minimum for an RPM release)

A release is accepted by the build, the admin command and the runtime command
only if its `bundle.yaml` declares `interface: 2` (new field) and its own
lifecycle code provides: `deploy.sh init-layout`, `init-config <component>
--settings <file>` (atomic, below), `validate`, `install`, `status --json`,
the `delivered` file source, recording of the content identity in installed
metadata, and the operation-lock protocol. Older bundles, including ones that
have `deploy.sh` and `init-layout` but not this interface, are refused before
packaging and before installation, naming the missing interface. Tools declare
the interface versions they support; `Requires: <product>-tools >= n` in each
release RPM and a tested rule that newer tools support every interface they
accept.

## Signature verification

Verification always uses an **isolated keyring** that contains exactly one
primary key, the approved product key whose fingerprint matched the paper, and
its valid signing subkeys; a key file with any additional primary key is
refused before import, and a key database is never reused without being
created fresh in an emptied work directory. It requires **both a valid signature and valid digests**
regardless of host defaults (`_pkgverify_level all`). Unsigned packages,
other keys, tampered headers or payloads fail. The bytes verified are the
bytes installed: packages are first copied to a root-only directory.

Bootstrap, once per new server (OS tools only; exact commands confirm in WP0):

```text
sudo -i
lsblk                                   find the medium, e.g. sdb1
mount /dev/sdb1 /mnt
rm -rf /root/pkg                        start from an empty work directory
mkdir -m 0700 /root/pkg
cd /root/pkg
cp /mnt/RPM-GPG-KEY-myproduct /mnt/myproduct-tools-*.rpm .
gpg --show-keys RPM-GPG-KEY-myproduct   exactly one "pub" line; fingerprint = this page
rpmkeys --dbpath /root/pkg/db --import RPM-GPG-KEY-myproduct
rpmkeys --dbpath /root/pkg/db --define '_pkgverify_level all' -K myproduct-tools-*.rpm
                                        exactly one line, ending: digests signatures OK
rpm --import RPM-GPG-KEY-myproduct
dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 install ./myproduct-tools-*.rpm
exit
```

OS prerequisite before the first line: `gnupg2` (for `gpg`), with `rpm` and
`dnf`, from the OS installation. The delivery contains exactly one tools
package. Any mismatch (more than one `pub` line, another fingerprint, more than
one package line, anything but `digests signatures OK`): stop and contact the
supplier. `/root/pkg` is the procedure's own scratch directory; emptying it on
every run makes the procedure repeatable without mixing old packages or key
databases. The tools apply the same rules (one primary key, fresh private key
database, one package per verified file). The global `rpm --import` is needed so that later dnf
transactions accept product packages; it does not authorize anything by itself
because every product package is checked against the isolated keyring first.

After the bootstrap, `<product>-admin` does the same for every candidate:
copy to a private root-only temporary directory (safe open, regular files
only), verify there against an isolated keyring built from the product key
shipped in the tools RPM (identical to the bootstrap key; the tools refuse if
the globally imported product key differs), then install exactly those files
with `dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1`. A new tools package
is verified by the installed tools the same way.

Internal repository: `<product>-admin --repo <repo-id>` runs
`dnf download --disablerepo='*' --enablerepo=<repo-id>` for the selected
release packages **and** a newer tools package if the releases require it,
into the private directory, then applies the same verification and local
installation. Bootstrap from a repository replaces the `cp` line with two lines: copy the
key file (from the supplier medium or the organisation's kept copy) into the
work directory, and
`dnf download --disablerepo='*' --enablerepo=<repo-id> myproduct-tools`
(needs `dnf-plugins-core`; confirm in WP0).

If isolated product-key verification cannot be established in WP0, WP0 stops.
A signer Key ID comparison is not an automatic replacement.

## Immutable versions

- **Identity of a release package:** name, version, `Release` (always 1), the
  normalised file inventory (path, type, mode, owner, group, size, SHA256),
  the exact scriptlets (the standard guard only) and the
  requires/provides/conflicts set, as read from the RPM header. The release
  content identity used at runtime is the SHA256 of the release's
  `checksums.sha256`, which the build verifies covers every other release file.
- **Prevention at the source:** the supplier build records each released
  identity in a ledger kept with the signing material (outside this
  repository) and refuses to build or sign a second identity for a released
  version. A second signed content for one version therefore never exists in
  the ordinary process.
- **Prevention on the documented path:** `<product>-admin` refuses a candidate
  whose name is installed with another identity, and any `Release` other
  than 1. An identical candidate is skipped, or reinstalled when `rpm -V`
  reports the installed tree damaged.
- **Reference identities:** after the isolated verification and a successful
  install, `<product>-admin` writes the package identity to a root-owned
  record `/var/lib/<product>/identities/<package>.json` (0644, directory 0755,
  written atomically, only by the admin command). A package installed any
  other way has no matching record. Separately, the runtime records the
  release content hash in its installed metadata when it installs a release;
  that links installed state to content, while the root-owned record is the
  reference for the package itself.
- **Detection on a bypass:** a plain `dnf` upgrade of a release package cannot
  be blocked by the installed package (its `%preun` runs after the new files
  are in place; confirm in WP0). `<product>-admin` and `<product>` compare
  each relevant installed package (rpmdb header identity, `rpm -V`, release
  tree against `checksums.sha256`) with its root-owned record **before any
  code of that release runs**, including `init-layout`, and stop on a missing
  record or a mismatch, naming the release; the manual never shows `dnf` for product
  packages after the bootstrap. This is detection after the fact, not the same
  guarantee as refusal before publication; with the ledger it covers only a
  deliberately bypassed process.

## Retirement

**Rule:** plain `dnf remove` or `rpm -e` of any product package is refused.
Only `<product>-admin` removes a release, one package per transaction, when
the check below allows it.

**Check** (`<product> retire-check --json` from the tools RPM), run as the
runtime account: `setpriv --reuid=<uid> --regid=<gid> --clear-groups
--inh-caps=-all --ambient-caps=-all --bounding-set=-all --no-new-privs`, with a
cleared environment (`HOME` from the user database, `USER`, `LOGNAME`,
`PATH=/usr/bin:/bin`, no `XDG_*`). It reads only installed markers, installed
metadata and the pending record; it queries no user unit and does not need
the user manager, so the manager's state is not a source of doubt. Root
reads only its bounded JSON (component names and versions).

| Runtime state for component C | Release C-v removable? |
| --- | --- |
| check failed, timed out, output invalid, lock not obtained within the bound | no: stop, nothing removed |
| no installed markers, metadata or pending record (reported `uninitialized`; the check reads the fixed `/var/lib/<product>/state` and needs no bootstrap file) | yes |
| pending record for C (target version unknown) | no, for every version of C |
| completed or recorded version of C is v | no |
| v newer than the completed version | no (awaiting the runtime user) |
| v older than the completed version, no pending record for C | yes |

Service activity is ignored: a stopped service still protects its release.

**One lock owner for the whole removal:**

1. `<product>-admin` takes `/run/<product>-admin.lock`, then starts the check
   child as the runtime account. The child opens (creating it if missing, as
   the account) `state/.operation.lock`, takes an exclusive `flock` (bounded
   wait), runs the check, sends the JSON **and the open lock descriptor**
   (`SCM_RIGHTS` over a socket pair) to the admin command, then exits. Root
   never resolves the account's path; it only holds the received descriptor.
   The admin command passes that descriptor, inheritable, to the dnf child, so
   the lock lives as long as either the admin command or dnf is alive: a dead
   check child, or an admin command killed after `%preun` approved, does not
   release it while dnf is still erasing.
2. The admin command confirms with the operator, then writes a root-only
   authorization record `/run/<product>/erase-authorization` naming exactly
   one package (name-version-release), the boot ID, its own PID and that
   process's start time (from `/proc/<pid>/stat`), and a random nonce.
3. It runs `dnf --disablerepo='*' remove <that package>` as its own child. The
   package's `%preun` (erase only) allows the erase only if the record names
   exactly this package, the boot ID matches, the recorded PID with the
   recorded start time is alive, is `<product>-admin`, **and is an ancestor of
   the scriptlet's own process**, so a separate `dnf remove` started from
   another terminal while the record exists is refused. Otherwise it fails
   with "use: sudo <product>-admin". `%preun` takes no lock. The record is
   single-use: the admin command deletes it right after dnf returns.
4. The admin command deletes the record, checks the postcondition (package
   absent from rpmdb, its tree absent, every other release package present and
   `rpm -V` clean, its identity record removed), and only then closes the
   lock descriptor.

Runtime operations (`<product>` and each `deploy.sh` it starts) take the same
operation lock: `<product>` takes it and passes the open descriptor to its
children; a child accepts an inherited descriptor only after checking that it
refers to `state/.operation.lock` (same device and inode) and that a
non-blocking exclusive `flock` on it succeeds (it does, because the open file
description already holds it); a direct `deploy.sh` run takes the lock
itself. No environment flag skips the lock.

**Tools package:** its `%preun` allows upgrade and refuses erase (product
uninstallation is a later item), so a plain `dnf remove <product>-tools`,
which would also remove the releases that require it, is refused.
Whether a refused `%preun` keeps every other package of a multi-package
transaction installed, or only its own, is confirmed in WP0; the design does
not rely on it because the admin path removes one package and plain removal
is refused for every product package.

**Interrupted removal:** a repeat of `<product>-admin` finds one of: package
present and intact (check again, remove), package absent and tree absent
(done), package absent but files left (stop: reinstall the same package from
the delivery, then remove again), package present but `rpm -V` failing
(reinstall the identical package, then remove).

## Runtime command (`<product>`)

1. Tools code (no release code yet) verifies the installed releases it may
   use against their root-owned identity records and trees, and selects the
   newest valid release per component; nothing of a failing release runs.
2. `init-layout` from the selected owner release (today's idempotent, atomic
   bootstrap; root never reads it), then take the operation lock and verify
   again under the lock.
3. Item 66 planning over installed releases: order, ranges, pending first,
   skip completed, refuse downgrade.
4. Only for a component that declares public settings, at its first
   configuration: ask for the public origin and IP address. The port is **not**
   asked: it comes from root-owned `/etc/<product>/host.conf` (0644, public),
   set by the administrator; a different value in an answer file stops.
   Suggestions: origin `https://<fully qualified host name>:<port>`; IP
   address the local source address of the route to the default gateway
   (`ip route get`), with no suggestion when there is no default route or
   several candidates. The **chosen** host name, whether suggested, typed or
   from an answer file, is checked against the delivered web certificate
   before install; a mismatch stops with both names.
5. Answers go to the private answer file `state/answers.conf` (item 66
   `--settings` format, 0600) **before** `init-config`; `init-config --settings`
   validates them and publishes the new config atomically with them. A retry
   reuses the saved answers; an existing config with a different value stops
   with the key name.
6. Credentials from the incoming directory (next section), then each
   component's own `validate` and `install`, as item 66.
7. Status table and `PASS`. An upgrade asks nothing unless the new release
   declares a new required setting or credential; then it stops and names it.

Every prompt has an option and an answer-file equivalent; without a terminal a
missing answer stops with exit 3 naming the option. A minimal worker without
gateway, certificate or public origin gets no prompts.

## Private credential delivery

- **Incoming directory:** `/var/lib/<product>/incoming/`, created by host
  preparation next to `state/`, `config/` and `storage/` (account-owned, 0700),
  so it exists before the first runtime run and is outside the component
  namespace. Layout `<component>/<file>`; a flat layout is accepted only when
  every file name is declared by exactly one component, otherwise `<product>`
  stops before copying and names the ambiguous file.
- **SSH:** as the runtime user, `scp -r <component> <runtime user>@<server>:/var/lib/<product>/incoming/`
  from a local folder named after the component; `-r` creates
  `incoming/<component>/`.
- **Console or one person:** `sudo <product>-admin --credentials /mnt` opens
  the source files as root with safe opens (no links, regular files, size
  bound) and passes their bytes to a `setpriv` child running as the runtime
  account (flags as above), which creates missing subdirectories and writes
  the files with 0600, refusing to replace a different file. Root never writes
  into the account's directories itself. Host preparation must have run first.
- **Declaration:** the existing `path` file source gets an optional
  `delivered` list of file names, beside the existing `generate` list. Example
  for the demo identity component:

  ```yaml
  SECRET_FILES:
    identity-signing:
    - path: credentials/identity
      delivered: [identity.crt, identity.key]
    identity-demo-users:
    - path: credentials/users
      delivered: [alice-password, bob-password]
  ```

  The durable target is `<state>/<component>/<path>/<file>`. A name declared
  twice within one component is refused at validation. PFX and password files
  are chosen by declaration, never by extension.
- `<product>` copies each declared, missing file from `incoming/` (0600),
  keeps an identical existing file, stops on a different one, never prints
  contents, and removes the incoming copy once the durable file is verified
  identical. After installation the runtime does not depend on `incoming/`.

## Preflight and bootstrap prerequisites

- **Bootstrap prerequisites** (needed before the tools can diagnose anything):
  explicit tools `Requires:` (`python3`, `python3-pyyaml`, `util-linux`,
  `rpm`, `dnf`). A missing one makes the local, offline dnf transaction fail
  with the package name; the manual says to install it from the OL9
  installation media and repeat the last bootstrap line. Every dnf call uses
  `--disablerepo='*'` or one explicitly enabled repository, so unreachable
  enabled repositories are never contacted.
- **Product preflight** in `<product>-admin`, before any release or host
  change (the key import and tools installation necessarily come before it):
  OS packages by name, SELinux Enforcing, firewalld, fapolicyd profile (next
  section) and `rpm-plugin-fapolicyd`, `subj_cache_size >= 16381`, journald
  `Storage`/`SplitMode`, account exists without sudo, free space for the
  selected packages' installed size plus image load.

## Supported fapolicyd profiles

Only profiles verified in WP0 are supported. Preflight records the effective
rule text (`fapolicyd-cli --list`), `trust`, `integrity`, `permissive`, the RPM
filter configuration and the plugin, and refuses anything outside them, naming
the setting and who acts:

| Profile | Definition |
| --- | --- |
| P1 default | OL9.8 `clean-agent`: `trust = rpmdb,file`, `integrity = none`, default rules (as in `PAPER-FIRST-LAB.md`) |
| P2 strict | P1 with `trust = rpmdb`, `integrity = sha256`, rules 1, 2 and 12 removed (in WP0 created in the running VM after each rollback to `clean-agent`, never snapshotted) |

PASS also requires the trust poll and the runtime self-check. Other policies
are not claimed until verified.

## Manual target (paper)

```text
Administrator, once per new server: the bootstrap lines above.
Administrator, every delivery:
  sudo mount /dev/sdb1 /mnt          (if not mounted; lsblk shows the name)
  sudo myproduct-admin /mnt          asks account and port the first time
  sudo myproduct-admin --credentials /mnt    when credentials come on a medium
Switch to the runtime user:
  at the console: exit, then log in as the runtime user at the login prompt
  over SSH from a laptop: exit, then on the laptop: ssh <runtime user>@<server>
  one person in an SSH session on the server: ssh <runtime user>@localhost
Runtime user:
  myproduct                          asks the address the first time
```

Order on a new server: bootstrap → `myproduct-admin /mnt` (host preparation
creates `incoming/`) → credentials (admin `--credentials` or `scp`) → runtime
login → `myproduct`. The manual also gives the fingerprint, the OS package
list, expected answers and output, unmounting, the tools repair procedure and
a table of stops with remedy and repeat command. One page is the target, not
a limit. The AI walkthrough counts commands, typed characters, account
switches and medium handling for the whole task, including fixing a missing
prerequisite.

## Failure and retry

| Where it stops | Durable state | Next step |
| --- | --- | --- |
| Bootstrap fingerprint or signature check | nothing installed | stop; contact the supplier |
| Missing bootstrap prerequisite | key imported, nothing else | install the named OS package from the OS media; repeat the dnf line |
| Tools damaged (interrupted tools install/upgrade; wrapper or module missing) | rpm may or may not list a tools package, possibly another version | **tools repair**: the bootstrap lines up to the isolated check, then `rpm -q myproduct-tools` decides the last line: not installed → the bootstrap `dnf ... install`; same version as delivered → `dnf ... reinstall`; older than delivered → `dnf ... install` (completes the upgrade); two versions listed (interrupted upgrade) → `dnf ... remove --duplicates`, then `rpm -q` again (the tools `%preun` allows this erase because another instance remains; confirm in WP0 probe C3/R3); newer than delivered → stop, ask the supplier for the current tools package. All with `--disablerepo='*' --setopt=localpkg_gpgcheck=1`; then the same admin command |
| Product preflight | nothing changed after tools | named party fixes it; same command |
| Candidate refused (signature, identity, older version, interface) | nothing installed by this run | supplier delivers a correct package; same command |
| Release install interrupted | some packages installed, one possibly partly | same command: identity and `rpm -V` checks, reinstall a damaged identical package, install the rest |
| Trust poll or self-check fails | releases installed | message names the missing trust or denial; administrator acts; same command |
| Host preparation | postcondition checks as item 65 | same command |
| Runtime stop for input | answers, config and credentials kept | supply the named input; `<product>` |
| Interrupted between answers and config | `state/answers.conf` saved | `<product>` reuses it |
| Component install fails | pending record (item 66) | `<product>` resumes that component first |
| Identity mismatch of an installed release | unchanged | stop; administrator reinstalls the identical package or contacts the supplier |
| Removal interrupted | see "Interrupted removal" | same admin command |

## Work package 0: investigation (decides go/no-go)

WP0 is an investigation in `acceptance/` with existing harness pieces
(`pve.py`, the existing network isolation that keeps administration access,
repositories disabled). Probes use `rpm-prototype/` plus minimal probe
packages; nothing here is a product gate. **Every probe is mandatory; WP1
starts only when all pass. Recording an unsafe result does not satisfy a pass
criterion.** A failing probe stops the work until a new technical solution
within the product-owner decisions passes; any weakening needs a new
product-owner decision before the plan changes.

History: the first attempt (recorded in
[RPM-WP0.md](../acceptance/RPM-WP0.md), historical evidence) created a
separate P2 snapshot on the ZFS-backed PROD disk, which blocked further
rollback to `clean-agent` and stopped WP0 before any probe. That design is
replaced below. The product owner removed that snapshot and restored the lab.

### Lab rules

- **One snapshot only.** Every isolated probe run starts with a rollback to
  `clean-agent`. The controller never creates, deletes or modifies a
  snapshot; its Proxmox calls are limited to an allowlist (read-only `GET`s,
  `status/stop`, `status/shutdown`, `status/start` and
  `snapshot/clean-agent/rollback` for the configured PROD VM only), enforced
  in code and covered by a local test.
- **Snapshot preflight before the first change:** the configured PROD VM is
  not HA-managed, `clean-agent` exists and is the most recent snapshot of
  every PROD disk (so a rollback is possible on ZFS); older snapshots, if
  any, are left untouched. Anything else stops before any VM operation.
- **P2 is created per run in the running VM**, after the rollback: `trust =
  rpmdb`, `integrity = sha256`, the original rules 1, 2 and 12 removed (matched
  by rule text), rules recompiled and fapolicyd restarted. P2 is never
  snapshotted; the next run's rollback discards it.

### Order of one isolated probe run

Each step decides PASS/FAIL automatically and the first failure stops the run.

1. **Rollback and start:** snapshot preflight, rollback to `clean-agent`,
   start, wait for SSH.
2. **Clean baseline check:** OL9.8, SELinux Enforcing, fapolicyd and firewalld
   active; P1 policy exactly as recorded (`trust = rpmdb,file`,
   `integrity = none`, `permissive = 0`, the 14 rules of the recorded
   baseline by text); no `/var/lib/<product>`, no product RPMs, no imported
   product or probe `gpg-pubkey`, no `/root/pkg`, no WP0 artifacts.
3. **Apply and record the profile:** P1 unchanged; P2 as above. Capture the
   effective profile (`fapolicyd-cli --list`, configuration, RPM filter,
   plugin) and check automatically that it equals the profile definition
   (P2: exactly the three rules removed and only `trust`/`integrity` changed).
4. **Isolate the network** with the existing harness isolation and check it;
   repositories disabled.
5. **Transfer inputs** to a probe directory. Expected values used for
   decisions (for example the approved fingerprint) are never transferred
   with the inputs (see probe C).
6. **Run the probe.** Each criterion is a scripted predicate on recorded
   output and state; nothing is judged afterwards by reading logs.
7. **Collect evidence:** FANOTIFY/AVC lines since the probe start, the step
   records and logs. A positive run requires none; a negative run records
   them as expected or unexpected per case.

The unit of isolation is one probe case group on one profile. Positive runs
(A, B, E) never share a run with negative cases (C, F, G, H, and the negative
parts of D); a positive run's audit result is taken only from that run, and
A's "no FANOTIFY/AVC" criterion is never satisfied by evidence from another
run.

### Probes

| Probe | Profiles | Pass criterion |
| --- | --- | --- |
| A. Prototype RPMs installed locally, today's runtime flow over real SSH, non-interactive | P1, P2 | services healthy; release files trusted from rpmdb only; no FANOTIFY/AVC in this positive run |
| B. Root Python from stdin and Python as the account (`prepare-host.sh`) | P2 | both run |
| C. Paper bootstrap on a root-only copy (details below) | P1, P2 | every case in C1–C3 as defined below |
| D. The same isolated check run by tools code on candidates, including repository download | P1 | same results as C1; `dnf download` available or an equivalent recorded |
| E. Immediate execution after install | P1, P2 | trust visible in `--dump-db` within the poll bound; first execution not denied |
| F. Guard: probe release and tools packages with the `%preun` described above | P1, P2 | plain `dnf remove` and `rpm -e` of a release refused; plain `dnf remove` of tools refused and every release still installed and intact; admin-authorized erase of exactly one package succeeds; a record naming another package, another boot, a dead or reused PID refuses; a separate plain `dnf remove` of the authorized package started while the record exists is refused (not an ancestor); user manager stopped does not change the result |
| G. Lock protocol | P1 | the lock blocks a concurrent runtime run (bounded wait, clear message) and does not block the authorized `%preun`; it stays held when the check child exits before `%preun` and when the admin command is killed after `%preun` approved, until dnf ends; inherited descriptor accepted, forged descriptor refused |
| H. Plain `dnf` upgrade of a release package with changed content, and a release installed without the admin command | P1 | the next `<product>-admin` and `<product>` stop on the missing or mismatching identity record before any code of that release runs, including `init-layout` |

Probes D, F, G and H use small, clearly marked probe implementations; a pass
shows that the mechanism works on OL9, not that the later product
implementation does.

### Probe C in detail

**Trusted expected fingerprint.** The approved primary fingerprint comes from
a source outside the delivery: a constant committed with the probe controller
and reviewed against the paper value of the lab key. The controller checks,
before transfer, that the fixture product key has that fingerprint (wrong
fixture → stop). On the VM the constant is part of the probe script sent over
SSH, never a file in the input directory, and it is never computed from the
key file under test.

**One primary key before any import.** Every key file used for authorization,
including the product key with an added signing subkey, is checked before any
import: `gpg --show-keys --with-colons` shows exactly one `pub` record, and
its fingerprint equals the trusted constant. Only then is the isolated
database created and the file imported.

**C1, signature matrix** (one run per profile, after the checks above on the
delivered key): product-signed tools accepted; unsigned, signed by another
imported key, tampered header and tampered payload refused; signed by a
signing subkey of the product key accepted (with the subkey key file, which
passes the one-primary and fingerprint checks); signed by another key's
subkey refused. Each verdict uses the paper's predicate: exactly one output
line ending in `digests signatures OK`, exit status 0.

**C2, stop rules before authorizing import** (one run per profile):

| Case | Expected | Postconditions |
| --- | --- | --- |
| key file with a second primary key | the bootstrap procedure stops at the one-primary check with its stop message | no isolated database was created; global `gpg-pubkey` set unchanged; no tools package installed |
| key file with one primary key whose fingerprint differs from the constant | stop at the fingerprint check | as above |
| leftover `/root/pkg` with an obsolete foreign-signed package and a key database containing the foreign key | the first lines remove and recreate `/root/pkg`; the verification step sees exactly one tools package and a database holding only the product key | the obsolete package and foreign key are absent from the isolated database; the tools package installed is the delivered one |

**Observation (not a pass criterion), recorded separately:** how OL9
`rpmkeys --import` handles the two-primary key file in a disposable
database (which keys appear, exit status, messages). It shows why the
one-primary rule is needed; it never authorizes anything.

**C3, tools repair states** (one isolated run per state and profile). Each
state is produced by deterministic fault injection as root on the disposable
VM, documented as probe setup, not product behaviour. Killing a real
transaction at a chosen point is not deterministic; these runs cover the
listed end states, not every interruption point.

| State | Setup | Expected diagnosis | Repair (paper) | Postconditions |
| --- | --- | --- | --- | --- |
| R1 registered, files missing | install delivered tools, delete the wrapper and one module | `rpm -V` reports missing files; `rpm -q` shows the delivered version | `reinstall` | exactly one tools version, the delivered one; `rpm -V` clean; wrapper runs as root; tools files trusted from rpmdb; no unexpected FANOTIFY/AVC |
| R2 files present, not registered | install delivered tools, then remove only the rpmdb entry (`rpm -e --justdb --noscripts`) | `rpm -q` says not installed while files exist | `install` | as R1 |
| R3 two versions registered (interrupted upgrade) | install an older signed tools fixture, then force-register the delivered version beside it | `rpm -q` lists two versions | the repair line defined for this state (see "Failure and retry"; confirm in WP0) | as R1; the older version absent; no release package removed |
| R4 older version installed cleanly | install an older signed tools fixture | `rpm -q` shows an older version | `install` (upgrade) | as R1 |
| R5 newer version installed than delivered | install a newer signed tools fixture | `rpm -q` shows a newer version | stop: contact the supplier | nothing changed |

R4 is an ordinary upgrade and is listed for completeness; it does not count
as interruption coverage. A first installation never counts as a repair case.

**Paper procedure versus automation.** The probe runs the paper commands
unchanged except for declared automation adaptations, each recorded in the
results: non-interactive confirmation (`dnf -y`), an SSH-delivered input
directory instead of a mounted medium, scripted reading of the output
lines the paper names, and journal/daemon trust observations around each
installing DNF command (next section). A pass shows that the commands and
their stop rules behave as the paper says; it is not a paper-usability result (console typing,
medium handling and reading are left to the AI walkthrough and item 68).

### Trust observation around DNF (automation adaptation)

The paper command lines stay unchanged; the runner adds observations before
and after every DNF `install`/`reinstall`, including the paper repair line.
Details and rationale: [refresh correction](../acceptance/RPM-WP0-TRUST-REFRESH.md);
implementation: `capture_trust_cursor`, `completed_refresh` and `wait_trust`
in `acceptance/rpm_wp0/operations.py`; local tests:
`acceptance/test_rpm_wp0_trust.py`.

1. **Before DNF:** wait for journal-observed idle state of the active
   fapolicyd main process in the current boot: its latest refresh message is
   `Updated`, or startup reached `Starting to listen for events`. This wait
   has its own 30-second bound. The PID is checked again after reading the
   journal; only then is the journal cursor published. A missing or
   unrecognized history, an in-progress refresh at the deadline, a daemon
   that is not active or a changed PID stops before DNF runs.
2. **After DNF:** the trust poll keeps one shared 30-second bound for all
   following observations, separate from the wait in step 1. The E criterion
   ("within the poll bound") refers to this post-install bound.
3. **Dump gate:** after the cursor, the journal must show a new refresh start
   (`It looks like there was an update of the system... Syncing DB.`)
   followed by `Updated`. A lone `Updated`, or only the backend message
   `Updating trust database` before `Updated`, is insufficient; a later start
   invalidates the preceding completion.
4. **Around the dump:** the daemon must be active with the same PID before and
   after; the completed refresh must be the same before and after the
   unchanged `fapolicyd-cli --dump-db`, so a dump overlapping another refresh
   never passes. The trust predicate is unchanged: every inventoried file
   appears from `rpmdb` with exact path, size and SHA256; `src_unknown`, file
   trust and other sources are refused.
5. **Failures:** timeouts, command failures, malformed or missing journal
   records and daemon death/restart stop the run without retry as success.
   Each command is recorded; a timed-out command keeps its partial stdout and
   stderr when available.

**Limitation.** Journal-observed idle state is neither a lock nor a
transaction identifier. A refresh triggered by the runner's own earlier
transaction may still be pending without having logged its start when idle
state is observed; the subsequent start/`Updated` pair can then belong to that
refresh rather than to the DNF command that follows. The observations reduce,
but do not eliminate, concurrent reads by the unregistered CLI reader, and
they do not prove a causal link between one refresh and one particular DNF
transaction. This adaptation is test infrastructure only; it is not a design
for the trust poll of `<product>-admin` (WP2).

### Before the next lab run

- A complete A–H runner, implementing every probe and case above, the lab
  rules and the run order, with one command for the whole matrix and one per
  probe case group.
- Local tests: the Proxmox allowlist and snapshot preflight, the baseline and
  profile checks (P1 exact, P2 derivation and refusal of other differences),
  the probe C predicates and stop rules, the fingerprint source, positive and
  negative run separation, reporting after any failure, and that no step can
  give PASS without its predicate.
- A separate code review of the runner before the product owner authorizes
  the lab run.

### WP0 verification status (2026-10-25)

- The runner is merged (`3dc304e`) as a bounded WP0 investigation. This is
  neither a completed WP0 nor clearance for WP1.
- Selected cases E, A and C3/R4 passed on P1 and P2 at `47b14ca`
  ([report](../acceptance/RPM-WP0-LAB-20261025-SELECTED05.md)). Review later
  found that both R4 cursors were taken during an earlier refresh, so these
  runs do not verify the corrected gate above.
- The corrected gate is locally tested and independently reviewed, but not
  verified in the lab.
- WP0 ends only when the complete A–H matrix passes on the final revision,
  under the lab rules, run order and stop rule above. C3/R1 and C3/R3 are
  particularly relevant because they reinstall identical content.

## Required tests

Product/unit tests with arbitrary names (product `cedar`, components `base`,
`login`, `worker`, account `operator-a`), real bundles, host commands replaced:

| Area | Tests |
| --- | --- |
| Build | release/tools RPMs from real bundles; modes; only `rpmlib` and explicit `Requires`; tools scriptlet is the guard only; `Release: 1`; ledger refuses a second identity; a real old bundle (prototype finding 5) and a bundle with `deploy.sh`/`init-layout` but without `interface: 2` refused |
| Signature | unsigned, unknown key, another imported key, tampered header and payload, subkeys; verification on the private copy; refused before dnf is called (arguments asserted) |
| Immutability | another identity or `Release`; identical skipped; damaged reinstalled; changed installed release detected before any lifecycle step |
| Selection | newest per component; older than installed; two versions in one directory; other products ignored; unowned release directory ignored |
| Preflight | each stop with message, actor and repeat command; no host change after a stop |
| Guard | every row of the check table; record matching rules; one package per transaction; postcondition and every interrupted-removal case; tools erase refused, upgrade allowed |
| Lock | inherited descriptor checks; direct `deploy.sh` takes the lock; bounded wait messages |
| Runtime | item 66 tests through `<product>`; `init-layout` first; fault injection between answer file and config; port from `host.conf`; suggestion rules; certificate check on the chosen name; minimal worker without prompts; no terminal → exit 3 |
| Credentials | `delivered` validation (duplicates, unknown names); incoming layouts and flat ambiguity; identical kept, different refused, links/specials refused on both root read and account write; incoming copy removed after verification; contents never printed |
| Tools repair | interrupted tools upgrade (missing module) repaired by the documented procedure |

Acceptance harness: one scenario using only the manual's commands on P1 and
P2: bootstrap, admin install, credentials through both paths, real SSH login
as the runtime account without sudo, `<product>` with a deliberate missing
credential, an unchanged rerun (no restarts), an interruption continued in a
fresh session, an upgrade, retirement through the admin command, refused plain
`dnf remove` of a release and of tools, a refused foreign-key package, and the
trust and denial checks of the positive runs. A checked mapping from manual
steps to harness commands fails on drift.

Existing gates as in `tests/README.md` (platform/demo suites, harness suite,
Ruff, Pyright, Vermin 3.6, shellcheck, link checks, `git diff --check`).

## Review-guide contracts to rewrite (in WP6, before declaring done)

| Contract | Change |
| --- | --- |
| Production release authentication | RPM signature and digests against an isolated product-only keyring on a root-only copy, also at bootstrap; other imported keys never authorize |
| Host preparation | entry `<product>-admin`; keep the UID/capability boundary, safe file operations, actual postcondition checks and bounded diagnostics; creates `incoming/` |
| Production layout | RPM-owned `releases/`; root-owned `identities/`; `/etc/<product>/host.conf`; `incoming/`; `state/answers.conf`; operation lock; only RPM-owned release trees with a matching identity record are valid |
| Compatibility | release interface 2; immutable versions (prevention and detection as above); offline dnf transactions; tools/interface compatibility; verified fapolicyd profiles only |
| Operator usability | unchanged requirement: one complete manual, separate AI and human verification |

## Work packages

0. Investigation above (lab rules, run order, probes A–H, complete runner,
   local tests and a separate code review before the lab run); results in
   `acceptance/`; plan revised if needed.
1. Supplier build: productise `rpm-prototype/` (release and tools RPMs,
   explicit requirements, guard scriptlets, ledger, interface checks), tests.
2. `<product>-admin`: isolated verification, selection, identity, preflight,
   host preparation (reusing `prepare-host.sh`, adding `incoming/`),
   `host.conf`, trust poll and self-check, credential hand-over, tests.
3. Release interface 2 in the lifecycle code (`init-config --settings`,
   `delivered`, identity in metadata, lock) and `<product>` (item 66
   orchestration, prompts, answers, incoming copy), tests.
4. Retirement: `retire-check`, authorization record, guard scriptlets,
   one-package removal, repair, tests.
5. Manual rewrite (including tools repair) and the AI operator walkthrough
   with full counts.
6. Harness scenario on P1 and P2 with the drift mapping; remove the
   `release.py` flow, its tests and manual sections; rewrite the contracts
   above and item 65/66 references.
7. Item 68 human trial on the closed lab: the printed manual only, short.

## Open points

- Compressed image archives (716 MB installed in the lab): a separate change.
- Key rotation and a delivery signed with a new key.
- The organisation's own PKI or a PFX with the `delivered` source (45a–45c).
- Changing the port after installation.
- Product uninstallation (tools erase).

## Understandability review to complete

- Success: medium → root-only copy → isolated-keyring check → local dnf →
  rpmdb trust poll and self-check → host preparation → credentials into
  `incoming/` → runtime login → `<product>`: `init-layout`, lock, plan,
  answers, each component's own lifecycle → status.
- Update: new release RPM beside the old → `<product>` upgrades that component
  only → next admin run: check as the runtime account under the lock →
  authorization record → one-package removal → postcondition.
- Failure/retry: interruption after the answer file → same command, no prompt;
  component 2 install fails → pending record → fresh login → resumes component
  2 → no restart of component 1; plain `dnf remove` → refused by `%preun` →
  admin path.
