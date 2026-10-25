# Item 69 implementation plan: signed RPM delivery, one command per role

Status: plan, revision 2 (2026-10-25), after an AI review of revision 1
(`7a9f9cf`) and three product-owner decisions; not implemented. Work package 0
is an investigation whose results may change the decisions marked "to be
confirmed in WP0". Read
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

- **Administrator**, once per new server: mount the medium, check the key
  fingerprint and the tools package's signer against the paper, import the
  key, install `<product>-tools`. Then, for every delivery: mount the medium
  and run **`sudo <product>-admin /mnt`**.
- **Runtime user**, after a real login (console or SSH): **`<product>`**.
- Console-only use and one person holding both accounts are main flows.

In scope: supplier build of release and tools RPMs, both commands, product-bound
signature verification, immutable versions, preflight, private credential
delivery, retirement with an in-use guard, removal of the `release.py`
publication flow, manual rewrite, harness scenario with a strict fapolicyd
profile. Not in scope: a supplier set manifest (dropped in item 66),
rollback/downgrade, credential generation (45b), encryption at rest (37),
compressed image archives (see open points), migration of existing lab
installations (pre-customer exemption).

## Product-owner decisions (2026-10-25)

| Question | Decision |
| --- | --- |
| Signature trust | **Bound to the product's own key.** A valid signature from any other imported RPM key never authorizes this product, also not for the first tools installation or repository delivery. |
| Immutable versions | **Yes.** One product/component/version has exactly one content; a rebuild needs a new version, also for internal-repository delivery. |
| Removal guard | **Yes, also for plain `dnf remove`,** with a conservative stop whenever the runtime state is unclear (user manager down, unreadable state, several packages at once). No override in the ordinary flow. |

## Guarantees of today's `release.py` flow and their replacement

| Today (`scripts/release.py`) | After this item | Kind |
| --- | --- | --- |
| Archive signature against a pinned per-product keyring | RPM signature verified against the pinned product key in an isolated keyring before dnf runs (see "Signature verification") | replaced |
| Immutable published release; same version with other content refused (`publish`) | Release field fixed to 1; admin refuses a package whose name is installed with other file digests; runtime refuses an installed release whose content identity differs from the one recorded at install (see "Immutable versions") | replaced |
| Protected, root-owned release tree and records | RPM-owned files under root-owned `/var/lib/<product>/releases/`; rpmdb is the record; `rpm -V` can verify | replaced |
| Exact-inventory fapolicyd `file` trust and `wait_trust` | rpmdb trust through `rpm-plugin-fapolicyd`; before PASS the admin command polls `--dump-db` (bounded) until every installed `deployment/` and tools file appears from `rpmdb` with matching size/digest, then runs a self-check as the runtime account | replaced |
| `integrity` none/size/sha256 accepted | only profiles verified in WP0 are accepted (see "Supported fapolicyd profiles") | narrowed |
| Preflight before publication (OS, packages, space, cache) | preflight in `<product>-admin` before release or host changes; bootstrap prerequisites as explicit tools `Requires:` | replaced |
| Journaled retirement that resumes after interruption | `dnf remove` of one package per transaction, guard first, postcondition checked in rpmdb and on disk; a repeat continues | replaced |
| Stdin tool bootstrap with an independent SHA256 | one-time OS-tool check of key fingerprint and tools signer on paper | replaced |
| Publication lock per product | rpm's transaction lock; one admin run at a time (lock file under `/run/<product>-admin.lock`) | replaced |
| Checksums inside bundles | kept: the build verifies them; the runtime verifies the release tree against `checksums.sha256` before install | kept |

Given up deliberately: per-product trust records in fapolicyd's `file`
database and the stdin bootstrap. Nothing else is given up without a
replacement above.

## Relationship to item 66 (authoritative)

| Item 66 decision | Status under this plan |
| --- | --- |
| Admin side: `release.py setup --all-in-input-dir`, publication as selection | **Superseded:** installation of release RPMs by `<product>-admin` is the selection. |
| "Newest published release" from published records | **Superseded:** newest release whose RPM is installed, verified by `rpm -q` ownership of the release directory and its recorded content identity; directories not owned by an installed release RPM are ignored with a warning. |
| Guard: never older than installed; refuse two versions of one component in one run | **Kept**, applied by `<product>-admin` to the packages it would install. |
| Each component's own `deploy.sh` as child process; no imports across releases | **Kept.** |
| Order, compatibility, skip completed, stops (exit 3), no new progress record, pending first | **Kept**, in the runtime command `<product>`. |
| `--settings` data file | **Kept** as the answer-file format; the prompts write the same file (see "Runtime command"). |
| `--credentials <dir>` mirroring `<component>/credentials/<group>/<file>` | **Replaced** by the credential inbox with `<component>/<file>` (flat only when unambiguous), mapped by component declarations. |
| Retirement by explicit administrator `retire` | **Replaced** by `<product>-admin` retirement with the guard. |

The item 66 plan keeps its runtime algorithm and tests; where this table says
superseded or replaced, this plan wins. One credential format, one selection
rule and one source of installed releases; no fallback to published records.

## Signature verification

Bootstrap, once per new server, OS tools only, before any supplier code runs:

1. `gpg --show-keys /mnt/RPM-GPG-KEY-<product>`: the fingerprint must equal
   the one printed in the manual (printed in gpg's format, without spaces).
2. `rpm -qpi /mnt/<product>-tools-*.rpm`: the `Signature` line shows `Key ID`
   with 16 hexadecimal characters; they must equal the last 16 characters of
   that fingerprint (printed separately in the manual). Nothing from the
   package runs during this query. To be confirmed in WP0 on OL9.8.
3. `sudo rpm --import /mnt/RPM-GPG-KEY-<product>`.
4. `sudo dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 install /mnt/<product>-tools-*.rpm`
   (signature verified against the imported keys; step 2 bound it to the
   product key).

The tools RPM has no scriptlets (build test), so even a wrong package that
passed a careless step 2 cannot run code at install time; it runs only when
the administrator starts it. The manual says to stop at any mismatch in 1 or 2.

After the bootstrap, `<product>-admin` verifies every candidate package
**before** dnf sees it: `rpmkeys --dbpath <private temporary dir> --import`
of the product key shipped in the tools RPM, then `rpmkeys --dbpath ... -K`
of the package, so only the product key can make it pass (isolated keyring;
to be confirmed in WP0). It then installs exactly the verified files with
`dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1`. A candidate signed with
any other key, unsigned or damaged is refused before any change, naming the
file. A new tools package is verified by the installed tools the same way.

Internal repository: `<product>-admin --repo <repo-id>` downloads the selected
packages with `dnf download --repo <repo-id>` into a private temporary
directory, then applies the same verification and local installation, so the
repository's own `gpgcheck` setting does not matter. Bootstrap from a
repository uses `dnf download <product>-tools` and the same steps 2–4 on the
downloaded file (`dnf download` needs `dnf-plugins-core`; to be confirmed in
WP0).

## Immutable versions

- Build: release RPMs always have `Release: 1`. The supplier build refuses to
  build a version listed in the supplier's release ledger with a different
  content identity (ledger kept with the supplier's signing material, outside
  this repository; format in WP1).
- Content identity: SHA256 of the release's `checksums.sha256`, which the
  build verifies covers every other file of the release.
- Admin: a candidate whose package name is installed is refused unless its
  file digests equal the installed package's (`rpm -q --dump` versus the
  candidate's header); an identical candidate is skipped, or reinstalled when
  `rpm -V` reports the installed tree damaged; a candidate with another
  `Release` is refused.
- Runtime: install records the content identity in the installed metadata;
  a later run that finds the installed version's release with another identity,
  or a release tree that fails `checksums.sha256`, stops before changes. This
  also catches a plain `dnf` upgrade that bypassed the admin command.

## Retirement guard

The check runs **as the runtime account**, never by root parsing its state:
`setpriv` to the numeric UID/GID, `--clear-groups`, no inheritable or
bounding-set capabilities (as `prepare-host.sh`), with a cleared environment
(`HOME` from the user database, `USER`, `LOGNAME`, `PATH=/usr/bin:/bin`, no
`XDG_*`). It runs `<product> retire-check --json` from the tools RPM, which
reads only markers, installed metadata and the pending record, queries no
user unit and needs no running user manager. Root reads only its bounded
JSON result (component names and versions). Runtime operations take an
exclusive lock (`state/.operation.lock`, new); `retire-check` takes the same
lock and, when called by `<product>-admin`, holds it until the removal has
finished.

| Runtime state for component C (as reported) | Release C-v removable? |
| --- | --- |
| check failed, timed out, invalid output, lock busy | no: stop, nothing removed |
| bootstrap file missing and no product state under `/var/lib/<product>/state` (reported `uninitialized`) | yes |
| pending record for C (target version unknown) | no, for every version of C |
| completed version of C is v, or recorded version is v | no |
| v newer than the completed version | no (awaiting the runtime user) |
| v older than the completed version, no pending record for C | yes |

Service activity is ignored: a stopped service still protects its release.

Two entry points, one check:

- `<product>-admin` offers removal of releases the table allows, asks for
  confirmation and removes **one package per dnf transaction**, then checks in
  rpmdb and on disk that exactly that package and its tree are gone and every
  other release is intact. A repeat continues.
- Each release RPM's `%preun` (erase only, not upgrade) runs the same check
  for its own component/version and fails when the table says no, printing the
  reason and `sudo <product>-admin`. `Requires(preun): <product>-tools` keeps
  the check available until release packages are erased. A failed `%preun`
  only keeps that package; other packages in the same transaction may still be
  removed, so the admin path never removes several at once, and the manual
  never shows `dnf remove`. Behaviour with several packages, a removed manager
  and the strict profile is to be confirmed in WP0; if `%preun` cannot refuse
  reliably, the fallback is the admin path only, with plain `dnf remove`
  documented as unsupported (product-owner decision needed then).

## Runtime command (`<product>`)

1. `init-layout` (today's idempotent, atomic bootstrap; root never reads it).
2. Take the operation lock; verify release trees and content identities.
3. Item 66 planning over installed releases (table above): order, ranges,
   pending first, skip completed, refuse downgrade.
4. First configuration of a component that declares public settings (only
   then): ask for public origin and IP address; the port is **not** asked: it
   comes from root-owned `/etc/<product>/host.conf` (0644), set by the
   administrator, and a different value in an answer file stops. Suggestions:
   origin `https://<fully qualified host name>:<port>`; IP address the local
   source address of the route to the default gateway (`ip route get`), and no
   suggestion when there is no default route or several candidates. The
   suggested host name is validated against the delivered web certificate
   before install; a mismatch stops with both names.
5. Answers are written to the runtime account's private answer file
   (`state/answers.conf`, item 66 `--settings` format, 0600) **before**
   `init-config`; `init-config --settings` (new lifecycle option) validates the
   answers and publishes the new config atomically with them, never a default
   config first. A retry reuses the saved answers and asks nothing; an
   existing config with a different value stops with the key name.
6. Credentials from the inbox (next section), then each component's own
   `validate` and `install`, as item 66.
7. Status table and `PASS`. An upgrade asks nothing unless the new release
   declares a new required setting or credential; then it stops and names it.

Every prompt has an option and an answer-file equivalent; without a terminal a
missing answer stops with exit 3 naming the option. A minimal worker without
gateway, certificate or public origin gets no prompts.

## Private credential delivery

- Inbox: `/var/lib/<product>/state/credentials-inbox/` (runtime-owned, 0700),
  created by `init-layout`'s companion step in `<product>`, with
  `<component>/<file>` subfolders; a flat inbox is accepted only when every
  file name is declared by exactly one component, otherwise it stops before
  copying and names the ambiguous file.
- SSH delivery: `scp` into the inbox as the runtime user.
- Console or one person: `sudo <product>-admin --credentials /mnt2` reads the
  files as root and hands them to a `setpriv` child running as the runtime
  account, which writes them into the inbox (0600, no links, refuses
  overwriting a different file); root never writes into the account's
  directories itself.
- Model extension (WP3): a file source kind `delivered: <file name>` in the
  existing file-group model (`render.file_group_sources`), next to `path`,
  `component_file` and `generate`, so each component declares which delivered
  names it accepts and where they go; validation, bundling and conflict checks
  reuse that model. PFX and password files are chosen by declaration, never by
  file extension. The manual's shell mapping disappears.

## Preflight and bootstrap prerequisites

- Bootstrap prerequisites (needed before any diagnosis is possible) are the
  tools RPM's explicit `Requires:` (`python3`, `python3-pyyaml`, `util-linux`,
  `rpm`, `dnf`); a missing one makes the local, offline dnf transaction fail
  with the package name, and the manual says to install it from the OL9
  installation media. Every dnf call uses `--disablerepo='*'` (local) or one
  named `--repo` (internal repository), so unreachable enabled repositories
  are never contacted.
- Product preflight in `<product>-admin` runs before any release or host
  change (key import and tools installation necessarily come before it):
  OS packages by name, SELinux Enforcing, firewalld, fapolicyd profile (next
  section) and `rpm-plugin-fapolicyd`, `subj_cache_size >= 16381`, journald
  `Storage`/`SplitMode`, account exists without sudo, free space for the
  selected packages' installed size plus image load.

## Supported fapolicyd profiles

Only profiles verified in WP0 are supported; preflight records the effective
rule text (`fapolicyd-cli --list`), `trust`, `integrity`, `permissive`, the
RPM filter configuration and the plugin, and refuses anything outside them,
naming the setting and who acts:

| Profile | Definition |
| --- | --- |
| P1 default | OL9.8 `clean-agent`: `trust = rpmdb,file`, `integrity = none`, default rules (as in `PAPER-FIRST-LAB.md`) |
| P2 strict | P1 with `trust = rpmdb`, `integrity = sha256`, rules 1, 2 and 12 removed |

Beyond the static check, PASS requires the trust poll and the runtime
self-check from the guarantees table. Stricter or different policies are not
claimed until verified.

## Manual target (paper)

```text
Administrator, once per new server (console or SSH):
  lsblk                                         find the medium, e.g. sdb1
  sudo mount /dev/sdb1 /mnt
  gpg --show-keys /mnt/RPM-GPG-KEY-myproduct    fingerprint = this page
  rpm -qpi /mnt/myproduct-tools-*.rpm           Key ID = this page
  sudo rpm --import /mnt/RPM-GPG-KEY-myproduct
  sudo dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 install /mnt/myproduct-tools-*.rpm
Administrator, every delivery:
  sudo mount /dev/sdb1 /mnt                     (if not mounted)
  sudo myproduct-admin /mnt                     asks account and port the first time
  sudo myproduct-admin --credentials /mnt       only for credentials on a medium
Switch to the runtime user (one person): exit, then log in as the runtime
  user at the console, or: ssh <runtime user>@localhost
Runtime user:
  myproduct                                     asks address the first time
```

The manual also gives the fingerprint and Key ID, the OS package list, the
expected answers and output, `scp` delivery of credentials for SSH users,
unmounting, and a table of stops with the remedy and the command to repeat.
One page is the target, not a limit: required steps stay in the manual. The AI
walkthrough counts commands, typed characters, account switches and medium
handling for the whole task, including fixing a missing prerequisite.

## Failure and retry

| Where it stops | Durable state | Next step |
| --- | --- | --- |
| Bootstrap step 1 or 2 mismatch | nothing installed | stop; contact the supplier |
| Missing bootstrap prerequisite | key imported, nothing else | install the named OS package from the OS media; repeat step 4 |
| Product preflight | tools installed, nothing else changed | named party fixes it; same command |
| Candidate refused (signature, immutability, older version) | nothing installed by this run | supplier delivers a correct package; same command |
| dnf install interrupted | some packages installed; an interrupted package may be partly installed (no atomicity is assumed) | same command: `rpm -V` on installed release and tools packages, reinstalls a damaged one with identical content, installs the rest; the runtime also refuses a release tree failing `checksums.sha256` |
| Trust poll or self-check fails | releases installed | the message names the missing trust or denial; administrator acts; same command |
| Host preparation | postcondition checks as item 65 | same command |
| Runtime stop for input | answers, config and credentials kept | supply the named input; `<product>` |
| Interrupted between answers and config | `state/answers.conf` saved | `<product>` reuses it; no prompt, no conflict |
| Component install fails | pending record (item 66) | `<product>` resumes that component first |
| Retirement refused or interrupted | releases intact or the one package removed | runtime user finishes; administrator repeats |

## Work package 0: investigation (decides go/no-go)

Investigation scripts in `acceptance/` using the existing harness pieces
(`pve.py` snapshots, existing network isolation that keeps administration
access, repositories disabled). `clean-agent` is kept unchanged; P2 is a new,
product-free snapshot made from it, with its effective policy recorded. Probes
use the existing `rpm-prototype/` plus minimal probe packages; nothing here
is a product gate.

| Probe | Profiles | Pass criterion |
| --- | --- | --- |
| A. Prototype RPMs installed locally and today's runtime flow run non-interactively over real SSH | P1, P2 | both services healthy; release files trusted from rpmdb only; no FANOTIFY/AVC in this positive run |
| B. Root Python from stdin and as the account (`prepare-host.sh` lines 24 and 239) | P2 | runs; if denied, the denial is recorded and the design changes there |
| C. Package with the product name signed by another imported key | P1 | `localpkg_gpgcheck=1` accepts it (confirms the review finding); `rpmkeys --dbpath` isolated check refuses it |
| D. `rpm -qpi` shows a 16-character Key ID before import | P1 | yes, readable from paper |
| E. Minimal release package with `%preun` running a `setpriv` check as the runtime UID | P1, P2 | refuses erase with a readable message; erase allowed when the check allows; behaviour recorded with two packages in one transaction, with `Requires(preun)` on a tools package removed in the same transaction, and with the user manager stopped |
| F. Execution immediately after `dnf install` | P1, P2 | trust visible in `--dump-db` within the poll bound; first execution not denied |
| G. `dnf download` available on `clean-agent` | P1 | `dnf-plugins-core` present, or documented alternative |
| H. Tampered payload byte in a signed RPM | P1 | refused by the isolated check and by dnf |

Negative probes (C, E, H) may produce denials or errors on purpose; they are
recorded separately from the positive runs. Decisions after WP0:

- A and B pass on P1 and P2, C and E behave as expected: continue with WP1.
- E fails: remove the `%preun` part; ask the product owner to accept the
  admin-only guard.
- C's isolated check fails: use the signer Key ID from the package header
  compared with the pinned key, with valid signature from dnf, and record why.
- A or B fails on P2: support P1 only, refuse P2 in preflight, and bring the
  finding to the product owner before WP1.

## Required tests

Product/unit tests with arbitrary names (product `cedar`, components `base`,
`login`, `worker`, account `operator-a`), real bundles, host commands replaced:

| Area | Tests |
| --- | --- |
| Build | release/tools RPMs from real bundles; modes; only `rpmlib` and explicit `Requires`; tools RPM has no scriptlets; `Release: 1`; ledger refuses a changed version; a real old bundle without `deploy.sh`/`init-layout` (prototype finding 5) refused |
| Signature | unsigned, unknown key, another imported key, tampered payload, wrong-key tools package; refused before dnf is called (arguments asserted) |
| Immutability | same name with other digests or `Release`; changed release tree or content identity at runtime |
| Selection | newest per component; older than installed; two versions in one directory; other products ignored |
| Preflight | each stop with message, actor and repeat command, including small cache, missing plugin or package, unsupported policy; no host change after a stop |
| Guard | every row of the guard table; active and stopped service; manager down; lock busy; one package per transaction; postcondition check; `%preun` erase versus upgrade |
| Runtime | item 66 tests through `<product>`; `init-layout` first; answers boundary with fault injection between answer file and config; port from `host.conf`; suggestion rules (no route, several); certificate name check; minimal worker without prompts; no terminal → exit 3 |
| Credentials | inbox layout, flat ambiguity, declared names only, identical kept, different refused, links/specials refused, contents never printed; admin hand-over runs as the account |

Acceptance harness: one scenario using only the manual's commands on P1 and
P2: bootstrap, admin install, real SSH login as the runtime account without
sudo, `<product>` with a deliberate missing credential, an unchanged rerun
(no restarts), an interruption continued in a fresh session, an upgrade, a
retirement through the admin command, a refused plain `dnf remove`, a refused
foreign-key package, and the trust/denial checks of the positive runs. A
checked mapping from manual steps to harness commands fails on drift.

Existing gates as in `tests/README.md` (platform/demo suites, harness suite,
Ruff, Pyright, Vermin 3.6, shellcheck, link checks, `git diff --check`).

## Review-guide contracts to rewrite (in WP6, before declaring done)

| Contract | Change |
| --- | --- |
| Production release authentication | RPM signature with the pinned product key in an isolated keyring; one-time paper bootstrap of key and tools signer; other imported keys never authorize |
| Host preparation | entry `<product>-admin`; keep the UID/capability boundary, safe file operations, actual postcondition checks and bounded diagnostics |
| Production layout | RPM-owned `releases/`; `host.conf`; answer file and credential inbox under `state/`; operation lock; only RPM-owned release trees are valid |
| Compatibility | immutable versions and content identity; offline dnf transactions; tools/release compatibility (`Requires: <product>-tools >= n`, newer tools support every release they accept, tested); verified fapolicyd profiles only |
| Operator usability | unchanged requirement: one complete manual, separate AI and human verification |

## Work packages

0. Investigation above; results recorded in `acceptance/`; decisions revisited.
1. Supplier build: productise `rpm-prototype/` (release and tools RPMs,
   explicit requirements, no tools scriptlets, ledger, bundle checks), tests.
2. `<product>-admin`: bootstrap-safe verification, selection, immutability,
   preflight, host preparation (reusing `prepare-host.sh`), `host.conf`, trust
   poll and self-check, credential hand-over, tests.
3. `<product>`: item 66 orchestration in the tools RPM, `init-layout` first,
   operation lock, answers boundary (`init-config --settings`), port and
   suggestions, credential inbox and the `delivered` file source, tests.
4. Retirement: `retire-check`, admin removal, `%preun`, tests.
5. Manual rewrite and the AI operator walkthrough with full counts.
6. Harness scenario on P1 and P2 with the drift mapping; remove the
   `release.py` flow, its tests and manual sections; rewrite the contracts
   above and item 65/66 references.
7. Item 68 human trial on the closed lab: the printed manual only, short.

## Open points

- Compressed image archives to reduce disk use (716 MB installed in the lab):
  a separate change with its own file name, checksum and space rules; not part
  of the first RPM delivery.
- Key rotation and a delivery signed with a new key.
- How the organisation's own PKI or a PFX fits the `delivered` source (45a–45c).
- Changing the port after installation (administrator flow, then reinstall).

## Understandability review to complete

- Success: medium → paper bootstrap → isolated-keyring check → local dnf →
  rpmdb trust poll and self-check → host preparation → runtime login →
  `<product>`: `init-layout`, lock, plan, answers, each component's own
  lifecycle → status.
- Update: new release RPM beside the old → `<product>` upgrades that component
  only → next admin run: guard as the runtime account → one-package removal.
- Failure/retry: interruption after the answer file → same command, no prompt;
  component 2 install fails → pending record → fresh login → resumes component 2
  → no restart of component 1; refused `%preun` → package kept → admin path.
