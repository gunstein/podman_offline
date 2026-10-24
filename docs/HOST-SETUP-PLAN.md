# Item 65 implementation plan: host setup and operator guide

Status: implemented on `feature/65-host-setup`, 2026-10-24; current-change real
OL9 and unassisted human verification remain outstanding. See
[implementation/evidence](../acceptance/HOST-SETUP.md). This plan records the
constraints; current operator commands live in the production manual.
Read [item 65](../BACKLOG.md#65-one-command-host-preparation-and-a-short-operator-guide),
the [review guide](REVIEW_GUIDE.md), and the
[manual installation report](../acceptance/PRODUCTION-LAYOUT.md#manual-run-as-produser-over-ssh-2026-10-23)
before implementing. This document resolves the choices left open in the item.

## Outcome and scope

After the administrator has installed the independently authenticated release
tool, one command pins the product key, publishes the explicitly selected signed
bundles, establishes persistent journaling on a supported host, and prepares the
existing runtime account. It prints what completed and the runtime account's
next command. The operator must not reconstruct this sequence from several docs.

There are still two roles: the administrator prepares the host and releases;
the runtime account logs in itself and initializes config, supplies credentials,
validates and installs each component. Item 65 does not run those lifecycle
commands as root or impersonate the operator to create the home bootstrap file.

Item 66 owns the install-set manifest, dependency ordering and one-command
runtime installation of multiple components. Item 65 supplies the focused manual-matched setup and initial real-SSH path.
Item 67 extends it through full logout/reboot/upgrade/retirement verification;
that complete operator verification remains outstanding. Do not claim a sudo-u
substitute covers it. No automatic
account creation, package installation, network access, key rotation, retirement,
legacy migration or new certificate-tool packaging belongs in 65.

## Decisions

| Question | Decision |
| --- | --- |
| Administrator entry point | Add `setup` to the existing independently authenticated `scripts/release.py`. Keep it a single-file stdin tool, compatible with Python 3.6. No additional privileged Python import from the transfer directory or an incoming bundle. |
| Existing host code | Call the selected protected release's `scripts/prepare-host.sh` after publication and trust verification. Preserve its privilege drop and descriptor-based directory operations. |
| Initial tool trust | A separate, explicit bootstrap installs and verifies the compressed tool before its first execution. Consolidate and test that procedure; the tool cannot authenticate its own first execution. |
| Bundle selection | Repeated explicit `--release COMPONENT@VERSION`; no glob, directory discovery or implicit latest version. Require an explicit `--host-release` among those selections. |
| Journal | For effective `Storage=auto` or `persistent` and `SplitMode=uid`, safely create the persistent journal directory if absent, apply systemd's tmpfiles policy, and flush. Refuse an explicit incompatible policy; do not rewrite it or add privileged groups. |
| OS/security baseline | Check OL9, packages, SELinux Enforcing, active enforcing fapolicyd, active firewalld and adequate subject cache. Report concrete remedies; do not install packages, tune security settings or restart fapolicyd automatically. |
| Retry | Recheck actual durable state on every invocation. Reuse immutable release records, pinned key and existing host state. No new setup completion flag or second pending-operation protocol. |

This deliberately refines the original item's wrapper suggestion: extending the
already authenticated tool avoids shipping a second bootstrap executable and
another independently delivered tool digest. The initial authenticated tool
installation remains a visible prerequisite, not a self-verification claim.

## Operator interface

Implemented administrator syntax (substitute delivered versions/digest):

```sh
gzip -dc /usr/local/libexec/podman-offline-release.py.gz | sudo python3 -I -B - setup \
    --product myproduct --user produser --port 8443 \
    --input-dir /var/tmp/myproduct-upload \
    --keyring /var/tmp/myproduct-upload/bundle-signing.gpg \
    --key-sha256 <independently-obtained-key-sha256> \
    --release platform@0.4.12 --release identity@0.4.12 \
    --host-release platform@0.4.12
```

The guide must substitute the versions actually delivered; these historical
versions illustrate syntax only. The input directory can be administrator-owned
and need not be copied into another root-only transfer directory. Treat every
input as untrusted until the existing snapshot/signature checks succeed.

For each explicit release derive exactly
`<product>-<component>-<version>-offline.tar.gz` and its `.asc` from `--input-dir`.
Use `identity()` to validate identifiers. Reject duplicate component selections,
two versions of one component, missing inputs, unsafe IDs, an unselected host
release, and arguments belonging to other operations. Paths are arguments, never
shell fragments. `.sha256` files may still be delivered for transport diagnostics;
they are not required by `setup` and never authorize a release. The authenticated
archive's internal checksum inventory remains mandatory.

Publication has no runtime dependency order: publish in the explicit command-line
order and run host preparation once, after all selected releases are ready.
`--host-release` explicitly chooses which authenticated host script runs as root;
it need not be named `platform` or have a gateway role. Different component
versions may carry different host scripts; do not require identical scripts or
silently choose the highest version. Missing runtime dependencies are still
checked by normal install, and runtime ordering remains item 66.

Exit 0 means all selected releases and host postconditions were verified.
Argument errors use argparse's exit 2; operational failures return 1. Errors name
the step and a bounded public identifier/path, never arbitrary command output,
config values or credentials. Print `PASS` after each completed step and one
final `PASS: host setup`; a failure must not print the final success line.

The final report lists release paths, account, port and journal change, then the
exact `deploy.sh init-layout` command for the runtime account. This small explicit
command was added during implementation to replace manual shell file creation.
It validates the prepared root, syncs a private temporary file and atomically
publishes the bootstrap without replacement, or
preserves a matching existing file, and refuses conflicting/linked files; root must neither read nor create that file.
Do not imply that the product services have been installed or started.

## Trusted tool bootstrap

Keep compressed `release.py.gz` from a separately reviewed source commit and an
independently authenticated SHA256 as the only new-host tool inputs. A digest
beside the uploaded file is not independent authentication. Do not extract the
bootstrap helper from a candidate application bundle.

Replace the scattered README steps with one canonical, copyable bootstrap
procedure in `docs/PRODUCTION-INSTALL.md`, in the operator's execution sequence.
Use a standard-library-only Python snippet passed literally on stdin to
`sudo python3 -I -B -`; it must not
import or execute the candidate helper. Its algorithm is fixed:

1. Validate the fixed `/usr/local/libexec` target and protected ancestors,
   rejecting links, ACL write grants, foreign ownership and unsafe modes. Create
   a missing final directory only beneath a validated protected parent. Reject
   an unsafe existing helper instead of repairing it.
2. Copy the regular candidate compressed file through an opened descriptor into
   an exclusive root-owned temporary file in that protected directory. Do not
   run gzip or Python on the candidate yet.
3. Hash that exact copy and compare with the supplied independent digest. On
   mismatch discard only this temporary file and leave any previous helper
   untouched. A concurrent change to the upload must never change executed bytes.
4. Set 0644, fsync, atomically replace the protected target and fsync its parent.
   Execute only after successful completion, using the setup command above.

Keep the snippet in a single fenced block in that document, with tests extracting
and executing those exact bytes. It is bootstrap code, not a second release
engine. The production guide already ships via `bundle.py:RELEASE_DOCS`; check
the complete procedure inside an unpacked bundle. A reviewed OS package remains an alternative way to
provision the tool, not a new package-building task. Updating the helper repeats
independent authentication; `setup` never updates itself from the input directory.
The operator must not need to understand or edit the snippet's internals. Review
its size and command burden under the operator checklist; if it prevents a simple
manual, simplify the trusted delivery/bootstrap workflow rather than adding
explanations. Any such design revision must preserve independent authentication
and be reflected in this plan before implementation is declared complete.

## Execution order and persistence

Implement a small named `setup_host(args)` coordinator in `scripts/release.py`.
Suggested helpers describe responsibilities, not a new framework:
`setup_request`, `check_host_prerequisites`, `provision_key`,
`prepare_persistent_journal`, `verify_host_setup`. Extract the existing
`provision-key` body into `provision_key` and reuse it from both operations.
Keep existing commands' behavior and error handling unchanged.

1. **Read-only preflight.** Parse all inputs and inspect the host, selected input
   files, existing key hash, protected anchors and existing host conflicts.
   Run this before `product_lock()` because that function creates directories.
   Collect independent actionable baseline errors; do not continue into mutation
   when any remain. Recheck relevant ownership/state after taking the lock.
2. **Key provisioning.** Hold the existing product lock for the entire setup.
   Call `provision_key` using snapshot/digest comparison. An identical pinned key
   is accepted; a different key is an error, not rotation.
3. **Selected release preparation.** Call existing `publish()` then `enroll()`
   per release under that lock. Do not recursively invoke `main()` or reacquire
   the product lock. Each publication verifies a private snapshot, validates the
   archive and immutable inventory, and waits for exact trust. A later failure
   may leave earlier authenticated releases ready; this is not batch rollback.
4. **Host script authorization.** Revalidate the selected host release with
   `published()` and require `scripts/prepare-host.sh` in its authenticated
   inventory. Never source/import its Python package to decide root work.
   Refuse a missing or modified script before journal/host changes.
5. **Journal.** Apply the supported persistent-journal procedure below.
6. **Existing host preparation.** Run a fixed Bash executable with the protected
   script path, `--port` and `--user` as an argument list, without `shell=True`.
   Use a controlled execution environment for privileged child commands, excluding
   caller overrides such as `BASH_ENV`, `ENV`, `PYTHONPATH` and an untrusted PATH.
   Preserve the script's existing UID/GID/capability drop for descendant work.
7. **Postconditions.** Check linger, manager XDG values, the owned product
   layout, the configured runtime/permanent firewall port and persistent journal
   availability. Report success only after these checks. Do not query application
   status or mark any component installed.

Release helper ownership/ACL/link protection stays authoritative; do not add a
weaker parallel implementation. Preflight may inspect root-owned host settings
and product anchors, but must never execute a candidate host script. The script's
detailed subordinate-ID, SELinux and descendant-directory checks therefore run
after authentication, immediately before their existing side effects. Do not
claim every possible host failure is detectable before publication. Keep the
small coordinator preflight checks consistent with the existing script, and
retain the script's checks at its own mutation boundaries.

`state/pending-operation.json` belongs to the runtime lifecycle and is never
opened or modified by `setup`. Host completion is derived from real
postconditions, not stdout from an earlier invocation. Serialize setup with
existing publication/retirement through the product lock. As today, operators
must not run host preparation concurrently with runtime lifecycle commands;
do not add a cross-account transaction protocol in this item.

## Preflight policy and journal behavior

| Check | Required behavior |
| --- | --- |
| Host | OL9; required packaged commands/imports available; SELinux Enforcing; fapolicyd active with `permissive=0`; supported integrity policy; firewalld active. No hidden download or enable/disable of security services. |
| Packages | Report missing capabilities and their documented OL9 packages, including PyYAML, gpgv, ACL/SELinux utilities and existing host-script dependencies. PyYAML is needed before the helper imports; the bootstrap guide names this prerequisite explicitly. |
| Subject cache | Require one unambiguous effective `subj_cache_size >= 16381`. A low/ambiguous value stops setup with the config path, required value and restart instruction. Retain the old direct host script's warning behavior unless a shared check can preserve its existing contract. |
| Account | Existing ordinary non-root login account, suitable for OL9 per-user journaling; no privileged groups or sudo grants. Preserve home, shell, groups, UID/GID and existing subordinate IDs. Check effective sudo policy as root, not just membership in wheel. |
| Sudo inspection | Use a controlled locale and `sudo -n -l -U ACCOUNT`. A command/policy lookup error is not proof of no grants. Accept only an explicitly recognized denial on supported OL9; reject grants and ambiguous results. Test denial, restricted grants, password-required grants, lookup failures and group-derived grants. Never edit sudoers. |
| Existing product | Reject old service-home layout, foreign-owned state roots, a different product for this account, conflicting drop-in or SELinux equivalence; do not migrate or recursively repair. |
| Space | Check writable capacity under `/var/lib`, `/var/tmp` and `/var/log`, grouping checks when paths share a filesystem. Report required/free bytes and state that application data/image expansion still needs administrator sizing. Never call a compressed-size estimate proof of sufficient installation space. |

Space checking is two-stage: before mutation require room for the selected
compressed inputs plus a documented 1 GiB reserve on the publication filesystem.
After signature verification and before extraction, use validated tar member
sizes to require room for the uncompressed release plus that reserve; do not
duplicate or weaken `extract()`'s archive validation. Account for already
allocated snapshots and previously published releases. Use `images/images.tar`
size, when present, for the `/var/tmp` load lower bound plus reserve. A minimal
fixture with no image archive must not acquire a demo dependency. Require at
least 1 GiB free on the journal filesystem; these are setup lower bounds, not
resource quotas or a guarantee against later ENOSPC. Recheck capacity immediately
before each allocation stage and report partial progress honestly. For shared
filesystems calculate the peak concurrently needed bytes for that stage, keeping
one reserve per filesystem rather than checking each path against the same free
bytes independently. The extra size preflight belongs to `setup`; reuse the
archive member validation without imposing this new reserve on existing commands.

For journals, read the effective main/drop-in settings using systemd's ordering;
do not grep only `/etc/systemd/journald.conf`. Support the OL9 default
`Storage=auto`, `SplitMode=uid` and already-persistent configurations. Validate
the protected journal parent and reject a linked/unsafe journal directory before
invoking systemd utilities. Create a missing directory, then run
`systemd-tmpfiles --create --prefix /var/log/journal` and `journalctl --flush`.
Preserve existing journal files, ACL policy and retention settings; no recursive
chown/chmod, journal deletion, privileged group additions or unconditional
journald restart. Check persistence actually became available after flushing.

Explicit `Storage=volatile`, `Storage=none` or `SplitMode=none` stops in preflight
with the setting and source file. Do not overwrite an organization's policy.
Document that enabling persistence affects the whole host and uses `/var/log`.
Account checks must reject system/dynamic/nobody UIDs that do not receive normal
per-user journals. For the supported standard OL9 boundaries reject UIDs below
1000 and the reserved 61184..65535 range; do not impose useradd's usual 60000
allocation ceiling on existing directory-service accounts. Test 999, 1000, 60000,
61184, 65519, 65534 and an ordinary higher UID. Nonstandard systemd UID-boundary
builds are outside the OL9 baseline and must not be guessed from `UID_MIN` alone.
Directory existence alone does not prove that `journalctl --user` works:
real service-log access after SSH login remains a required lab/manual check.

The journal choice follows the documented
[systemd storage and user-splitting rules](https://www.freedesktop.org/software/systemd/man/252/journald.conf.html)
and [persistent-directory/flush procedure](https://freedesktop.org/software/systemd/man/latest/systemd-journald.html).
The account distinction follows systemd's
[UID ranges](https://systemd.io/UIDS-GIDS/), not account-name conventions.
Verify commands against the supported OL9 installation; do not introduce APIs
from newer systemd versions merely because current upstream docs list them.

## Failure and retry acceptance table

| Failure boundary | Durable state allowed | Required behavior in a new process |
| --- | --- | --- |
| Tool digest/preflight | No setup changes; previous tool retained on digest mismatch | Correct input/baseline, repeat the same documented procedure. |
| Key pinning | Product anchor/lock and possibly the matching pinned key | Reauthenticate input and retained key; refuse a different key. |
| Second bundle signature, extraction or publication | First authenticated release may be published/trusted; no host script executed | Revalidate the first immutable release; prepare the remaining release. Never trust/execute the rejected input. |
| Publication succeeded, trust failed/timed out | Authenticated release and possibly scoped trust records | `enroll()` rechecks records/live trust; do not republish conflicting bytes or skip the wait. |
| Journal creation or flush | Existing releases plus possibly a journal directory | Recheck policy, apply tmpfiles and flush again; do not infer success from directory existence. |
| Host directory/drop-in/manager/firewall step | Existing host-script partial state | Rerun its idempotent checks; verify live manager values even when the drop-in already exists. Retain account mappings, storage labels and all data. |
| Final report/postcondition failure | Host might already be prepared | Recheck actual postconditions; no new completion marker to clear and no service install to redo. |

No automatic rollback or deletion of previous authenticated releases, host
settings, config, credentials, data or trust for other components. Temporary
cleanup removes only paths created and owned by that invocation. Test a real
process interruption as well as exceptions: abandoned private staging must not
become executable/trusted input or trigger broad cleanup. Existing crash-staging
disk cleanup can remain a documented administrator action; no scavenger in 65.

## Implementation work packages and files

1. **Bootstrap and request contract:** canonical tested bootstrap block and
   short instructions in the one manual; `scripts/release.py` parser, pure selection
   validation, extracted `provision_key`. Preserve every existing CLI operation.
2. **Coordinator and host policy:** preflight, guarded journal setup, calls to
   existing publication/trust/host operations, postconditions and diagnostics.
   Keep side effects explicit; do not create a plugin system or generic engine.
3. **Product regressions:** extend `tests/platform_tests/test_release.py` and
   `test_prepare_host.py`; place coordinator tests in `test_host_setup.py` if that
   keeps fixtures clear. Shared fixtures go under `tests/helpers`, not imported
   test classes. `tests/run.py` already exports the complete `scripts` directory.
4. **Acceptance wiring:** add opt-in `--host-setup` to
   `acceptance/acceptance.py`, the setup path in `acceptance/remote.sh`, and tests
   in `acceptance/test_acceptance.py`/`test_prepare_host.py`. Preserve existing
   security probes; do not replace them with a success-string assertion. Share
   the documented command blocks or test an explicit manual-step mapping, and
   connect to 67's real SSH path for runtime actions.
5. **Operator docs:** rewrite `docs/PRODUCTION-INSTALL.md`, consolidate README
   bootstrap instructions, update bundle doc inclusion/link tests and the
   architecture/review-guide/backlog status to match implemented behavior.
   Add `acceptance/HOST-SETUP.md` with actual evidence and outstanding checks.

Each work package must leave the existing release commands and isolated suite
usable. Implement on the working branch without overwriting other work. Commit,
push, PR and merge are separate user instructions, not part of this plan.

## Required regression evidence

Product/unit coverage must drive real files, archives and orchestration, with
only host commands replaced. Use arbitrary product/component/account names
(`cedar`, `worker`, `operator-a`), no gateway/Identity/database/certificate role,
and no shipped demo tree. Include a second independently versioned component.

- Verify selection, exact argument lists and command order. Unselected files,
  even valid signed archives, must not be opened or installed. Check conflicting
  versions, wrong product, missing signature and missing host script.
- Reuse real signing fixtures for at least one valid and invalid signature
  path. A mock gpgv accepting everything is insufficient. Assert that no uploaded
  code or protected host script runs before authentication/trust succeeds.
- Exercise bootstrap digest mismatch and upload replacement, unsafe target
  ancestors, symlink/hardlink/FIFO targets and preservation of the previous
  helper. Only the authenticated protected copy may be executed.
- Drive the failure/retry table through fresh processes and the same persistent
  fixture. Inject failures through test doubles outside production flags. Assert
  files/ownership/modes/retained bytes and trace command calls, not just messages.
- Cover effective journal defaults/drop-in precedence, explicit conflicts,
  already-persistent state, flush failure, unsafe paths and retry after mkdir.
  Test no chmod/chown recursion and no extra groups/security-policy changes.
- Preserve and rerun existing release hostile-input, retirement, exact-trust,
  host privilege-drop, SELinux exclusion and same-product-account regressions.
  Existing runtime install/status/pending behavior must remain unchanged.

Harness coverage must verify option propagation, selected release/host-script
identity, artifact delivery, manual-command mapping, failure reporting and
assertions. `--host-setup` executes the manual's authenticated tool bootstrap and
coordinator, rather than first running the old prepare path or executing helper
source supplied directly by the controller. The lab may supply the explicitly
documented OS/account baseline, reset VMs, deliver artifacts and provision a
lab-only SSH key. Every operator action after that starting state must use the
manual's commands, account and order. Missing prerequisites exercise the manual's
diagnosis, remedy and continuation; no hidden harness repair.

Do not independently create product directories, journals, pinned keys, manager
drop-ins or the runtime bootstrap file. Run runtime steps through real SSH without
sudo or environment injection, using 67's shared path. Cover first execution,
an unchanged successful rerun and continuation after interruption in a new
process/session; tests must detect when the harness bypasses a documented entry
point or drifts from its steps. Until that path is implemented and run, report a
gap, not a passing substitute. Never remove production journals: the empty-journal
baseline is allowed only on explicitly reset disposable lab VMs. Incompatible
scenario combinations must fail before reset.

Add a controlled interruption/retry probe at the publication-to-host boundary;
inject from controller-supplied test code, never by editing a protected release,
weakening fapolicyd or adding a production fault-injection option. Check that
retry retains publication/key identity and reaches real host postconditions.

Run these existing local gates after implementation:

```sh
python3 -B tests/run.py platform --isolate
python3 -B tests/run.py demo
python3 -B -m unittest discover -s acceptance -p 'test_*.py'
```

Also run relevant focused tests and the current Ruff, Pyright, Vermin and shell
checks from [tests/README.md](../tests/README.md#deployment-package-043), plus
operator-document link checks in source and unpacked bundles and
`git diff --check`. Report pre-existing lint separately; do not fix unrelated
findings. Exercise bootstrap/guest code with the same static compatibility checks.

Implemented focused lab commands (not executed for this change):

```sh
python3 acceptance/acceptance.py --run host65-normal --first-app app1 --host-setup run
python3 acceptance/acceptance.py --run host65-renamed --renamed-product --host-setup run
python3 acceptance/acceptance.py --run host65-minimal --platform-help-only --host-setup run
```

Use unique run names and run sequentially on the authorized disposable lab.
These commands reset VMs; the implementation agent must document them, not run
them without a separate lab instruction. Real OL9 SELinux/fapolicyd checks are
required before declaring the privileged boundary verified. The full existing
six-scenario matrix should also be rerun before release because the shared
release helper changes. None of today's matrix results verifies future 65 code.

## Guide and completion criteria

Use one coherent `myproduct` example with `platform` and `identity`, independent
versions, account `produser`, and an explicit substitution table. The main guide
has a short path: obtain trusted delivery -> administrator bootstrap/setup ->
runtime SSH/bootstrap -> per-component config/credentials/validate/install ->
health/log checks -> upgrade. Label machine, account, required access, command
and expected result at every step. The laptop is only for trusted artifact
preparation/transfer and SSH. Keep bootstrap, prerequisite remedies, selected
credential-path steps, ordinary diagnosis and recovery in this one manual.
Only design detail and advanced topics belong in linked references.

Keep PEM delivery and PFX provisioning visibly separate. Do not pretend the demo
certificate helper ships in bundles or expand 45b. Validate actual endpoints:
demo `/livez` returns 204 and `/identity/.well-known/openid-configuration` returns
200; `/identity/` is not a success probe. Distinguish release publication from
runtime installation and retain explicit retirement after successful upgrade.
Every common error needs a non-sensitive diagnosis, corrective action and exact
next command; classify which commands can safely be repeated after interruption.

Implementation is reviewable when the CLI, guide, focused regressions, harness
scenario and documentation gates are complete. Apply the separate mandatory
[operator review](REVIEW_GUIDE.md#7-mandatory-operator-and-procedure-understanding-review):
record a literal AI walkthrough using only the stated prerequisites, with missing
steps, hidden assumptions, unclear terms and excessive Linux knowledge flagged.
Count commands, manual edits and account switches per task, and assess tool/flow
simplification if the guide remains complicated. The
[current baseline](../acceptance/OPERATOR-REVIEW.md) has findings; rerun the AI
review on the implemented procedure rather than claiming this plan passes it.

Customer readiness additionally requires a person with limited Linux experience
to follow that same manual on a fresh test host without oral assistance,
including real SSH without sudo, nonempty user-service
logs, correct XDG paths, reboot startup before login, upgrade/config retention
and retirement. Record elapsed time, errors, stopping points, command/edit counts
and explanations needed. This human trial is outstanding. An assisted trial
needs a new unassisted run after fixes; it is not a usability pass. Report AI,
human and automated outcomes independently: green acceptance does not establish
that the manual is simple. Item 67 automates the execution path, not the human
assessment; pending 67 must not be reported as covered by a sudo-u harness path.

Understandability review must trace both:

- **Success:** independent digest -> protected tool -> explicit selections ->
  `provision_key` -> `publish`/`enroll` -> journal -> authenticated host script ->
  postconditions. Name each authority and write boundary; account config and
  runtime pending state are not part of root setup.
- **Failure/retry:** first publication ready, later trust/host step fails -> new
  process authenticates/rechecks durable state -> completes missing work ->
  verifies live postconditions. Explain why neither stdout nor an existing
  directory is a completion receipt.

Planning review outcome: the current trust, host privilege separation, product
identity, offline and retry contracts have been traced to their owning code.
The final implementation review and actual local results are recorded in the
linked implementation/evidence report. Neither this plan nor those local tests
establish current-change real-host or human usability verification.
