# Protected releases (backlog 54)

Implementation on branch `feature/protected-releases`, based on `a37f4e4`.
Backlog 64 moved the protected anchor from `/opt/<product>` to the root-owned
installation root `/var/lib/<product>` (releases in `releases/`, keyring and
lock beside it); `/opt` below describes the item 54 implementation as reviewed.
See [production layout verification](PRODUCTION-LAYOUT.md).
Real OL9/SELinux/fapolicyd verification of this change is **pending**. Earlier
CLEAN PASS for host preparation or Secret delivery does not verify this boundary.

## Authority and bootstrap

The trusted administrator authenticates a reviewed `scripts/release.py` through
an independent administrative channel. The README provisions a compressed
root-owned helper at `/usr/local/libexec/podman-offline-release.py.gz`, verifies
that protected copy against an independently delivered SHA256 digest and streams
its decompressed bytes into Python stdin. Parent ownership/modes/ACLs and links
are checked administratively before provisioning. This avoids opening a raw
untrusted Python file, including for bootstrap hashing; no new allow rule or
self-enrollment is involved. An organisation-signed OS package is an alternative.

Merely extracting a helper from an unverified incoming archive cannot bootstrap
authentication. Helper updates repeat the separate reviewed admin procedure.
A separately authenticated public key from the trusted operator, rather than the
service account, is checked against the independently authenticated
`--key-sha256` on the protected copied bytes and pinned at
`/opt/<product>/keyring.gpg`; a different existing
key is refused. Rotation is a separate administrator operation. Publication uses
only that pinned product key; `--keyring` is accepted only by `provision-key`.
Production signatures are mandatory; unsigned archives remain development-only.

In the lab, the controller sends its reviewed source over authenticated SSH;
Bash's builtin printf streams code to `sudo python3 -I -B -` through a real pipe. Isolated mode excludes caller
CWD, PYTHONPATH and user site modules from privileged imports; the regression
also plants hostile yaml/argparse modules and verifies they are ignored.
The root interpreter opens no untrusted target Python file. A regression compiles
the actual generated source and checks stdin's FIFO type, including the large
embedded helper. The shared helper imports only host-installed PyYAML and Python
standard-library modules, never the incoming release's deployment package.

## Before the first customer installation

Existing dev/lab hosts may be discarded. Prefer a fresh host. If reusing a lab
host, an administrator must remove the obsolete `trust.d/<product>-<component>`
files, reload fapolicyd, verify no `/var/lib/<product>/releases` entries remain in
the live database, then remove that old tree. Preserve unrelated trust and
persistent state. Publication does not scan, migrate or repair old layouts.
After the first real customer installation, incompatible changes must include
migration and verification preserving customer data and credentials.

## Protected flow

`scripts/release.py` owns root release operations; deploy still owns the existing
service-user lifecycle and pending-operation record. There is no engine migration,
old-layout fallback or second deployment transaction model.

1. `product_lock` validates `/opt` and its complete root-controlled ancestor chain,
   creates/refuses the product anchor and serializes operations with a bounded
   flock wait. Root-owned, nonwritable modes, no ACLs, links or unexpected objects
   are required. Existing unsafe paths are refused, never recursively repaired.
2. `publish` copies regular archive/signature inputs without following their final
   symlinks into new root-only staging under `/opt/<product>`. It checks that exact
   snapshot with gpgv and the independently pinned root-owned keyring. Swapping
   caller paths afterwards cannot change the bytes extracted.
3. `extract` first validates every member: one requested root, safe relative names,
   explicit directory parents, no duplicates, links, sparse/special files,
   privileged/writable modes or unsupported metadata. It copies file bytes itself,
   establishes root ownership and 0755 directories/0644 or 0755 files, hashes bytes
   directly while copying (without reopening untrusted Python), and checks
   VERSION, descriptor product/component/version and exact checksum inventory.
4. `inventory` records every file's size/hash/mode and every directory, including
   empty ones. Protected `.release.json` binds this inventory to the signed
   archive digest. Stored device/inode/mtime bindings reject later changes,
   including same-size writes and removed/recreated entries, without reopening
   untrusted payloads. Authenticated VERSION/descriptor/checksums are read from
   the archive stream, with a 16 MiB limit on each metadata file. Never manually
   copy/chmod/modify a published release; those operations invalidate bindings.
   SELinux relabeling is supported: ctime/xattrs are excluded, so `restorecon`,
   `fixfiles` and autorelabel do not invalidate provenance. Root is trusted; a root
   writer changing bytes and restoring mtime is outside this service-user boundary.
   Atomic same-filesystem rename publishes the whole tree;
   fsyncs make file/inventory/directory publication durable. Same archive/identity
   repeats safely; any different archive or changed final inventory is refused.
5. `scoped_trust` atomically writes only authenticated deployment records in
   `/etc/fapolicyd/trust.d/podman-offline-<product>.<component>` using its documented three-column
   format. It verifies any retained older entries against their protected
   provenance, preserves them, rejects foreign/duplicate/mismatched entries and
   stages outside trust.d so reloads cannot read partial text. The dot separator
   cannot occur in product/component IDs, so distinct products cannot collide
   through ambiguous hyphen concatenation. `enroll` then
   updates the daemon. This avoids the untrusted-Python open problem of rehashing
   unpacked source with `--file add`; identical records merge idempotently without
   accepting duplicate-add errors. `wait_trust` compares exact paths, sizes and
   SHA256 values, rejects duplicates/extras and uses bounded reads/polling. An
   enrolled path alone or a syntactically plausible digest is insufficient.
6. Service-user init-config/validate/install/retry/upgrade/uninstall use readable,
   nonwritable release inputs and retain private state under `/var/lib/<product>`.
   `sudoedit -u <product>` edits that service-owned config. Old release/trust stays
   until install, health, persistent-state/sibling and application checks pass.
7. `withdraw` removes only a verified package's scoped trust after uninstall,
   retaining its release files. `retire` revalidates both protected trees, withdraws
   only the selected old package's trust, waits for exact new trust and old-entry disappearance,
   then atomically moves that old tree to `.retired-<release>` with a protected
   `.retirement-<release>.json` journal before deleting it. A failed wait preserves
   old files. Interrupted deletion resumes only from that matching protected
   journal and checks remaining objects against the recorded inventory; unrelated
   or orphaned trees are refused. The journal is removed only after cleanup.

A relabel leaves release inventory and old retained trust usable; the safety probe
sets `tmp_t` on one deployment file with `chcon`, requires the label to change,
then runs `restorecon -R` and verifies restoration of the original label before
repeat publication and subsequent trust/lifecycle checks. Restoration is attempted
also when the change assertion fails. Metadata-only unit tests use a real user xattr to exercise the ctime
change; they do not establish SELinux behavior on OL9. Unexpected ownership,
permissions, ACLs or changed payload metadata still fail. Diagnostics identify
the operation, protected path or probe phase and subprocess exit status without
printing external stderr, credential contents or complete configuration.

A process interrupted before publication leaves only an ignored root-only
`.staging-*` directory; a new call starts fresh, never executes/reuses it. An
administrator may remove stale staging while no helper process runs. After
publication, the inventory is the retry boundary and enrollment can resume.
Publication never overwrites an existing release. Locks coordinate trusted
helper processes; service users cannot rename the parent or replace ancestors.

The protected layout supports the existing `integrity = none` policy after
enrollment. `size` is not protection against same-size replacement; `sha256` is
supplementary. The helper reports/refuses unsupported or ambiguous settings and
never changes global integrity policy. Stronger settings need their own startup
and upgrade verification. No fapolicyd/SELinux allow rules are added.

The registry-offline archive is a data-only fixture: an unprivileged operator
checks its outer checksum, verifies every inner checksum directly from the
compressed archive streams, extracts only the two `images/` data files and streams
image data to rootless Podman. Neither root nor the operator reopens extracted
Python for checksums; no Python payload is extracted or enrolled for this fixture. Historical removed legacy scenarios
retain their pinned layouts; they are not current deployment paths.

## Current local evidence

Focused regression coverage uses real archives, file hashes and inventories;
signature/trust commands are stubbed in unit tests, not represented as daemon or
OpenPGP evidence. Cases include rewritten package plus checksum list, unlisted
files, immutable-version conflicts, hostile archive types/names, identity
mismatch, signature refusal before extraction, replacement of the original
input after snapshot verification, publication failure/retry, concurrent locking,
ACL/mode/link refusal and exact live size/hash/unique-path matching. Retirement
failure preserves old files and siblings. Production component_file inputs,
retained config, retry and upgrade are exercised against write-denied release
paths; standalone fixture validation/install is checked separately.

Harness regressions exercise actual shell wrappers and shared trust logic,
authenticated-controller pipe delivery and retirement ordering after e2e. The
renamed generator carries generic helper code unchanged. Actual test totals and
host-dependent failures are recorded after the final local checks below.

## Required real lab matrix

From a committed clean checkout of this branch on the controller, using the
existing disposable VM configuration:

```sh
python3 acceptance/acceptance.py --run release54-app1 --first-app app1 run
python3 acceptance/acceptance.py --run release54-app2 --first-app app2 run
python3 acceptance/acceptance.py --run release54-help --help-only run
python3 acceptance/acceptance.py --run release54-identity --identity-only run
python3 acceptance/acceptance.py --run release54-platform-help --platform-help-only run
python3 acceptance/acceptance.py --run release54-renamed --renamed-product run
```

Each command resets both configured lab VMs; use a new run ID on every retry.
Every scenario runs `07-release-safety` after installation, using its actual
platform/gateway release. The controller-provided probe runs replacement,
checksum rewrite, extra-file, ancestor-rename and symlink attempts under a
separate numeric service UID/GID without supplementary groups or privilege
acquisition. It also tries to replace the private snapshot immediately before
and after signature verification, rejects a corrupt archive with the real
original signature without changing trust, rechecks the full published inventory
and validates through the enrolled file-based launcher as the service user.

The negative probes request denied DAC writes, not execution of untrusted
payloads. They do not suppress audit records; unexpected AVC/FANOTIFY denials
still fail the existing audit gate. Runtime facts include exact RPM versions,
SELinux mode and fapolicyd state. Protected files/ancestors must remain unchanged;
the release-safety probe permits only SELinux relabel metadata updates within
the selected protected release. There are no permitted outside-target writes or
policy changes. This does not
claim that the service user cannot execute arbitrary code through other routes.

Record revision, all six CLEAN PASS reports and their EVIDENCE.md paths here.
Full lab execution, actual Python 3.6 and a non-baseline integrity strategy remain
outstanding. No historical run closes this task.

## Understandability review

Authoritative input: the signed protected archive snapshot. Durable release:
root-owned final tree plus generated inventory, never the incoming checksum file
on a writable extraction. Validation precedes extraction/publication, then trust
precedes service-user deployment. Root publication/trust and service lifecycle
remain separate, with explicit functions and files rather than hidden mode flags.

Success trace: product lock -> verified snapshot -> validated inventory -> atomic
publication -> enroll -> exact live trust -> service init/validate/install ->
health/e2e -> scoped retirement. Failure trace: failed enrollment leaves the
protected published inventory; a fresh call verifies the incoming archive and
existing full inventory again, then resumes enrollment. Install/e2e failure keeps
old release/trust. Retirement failure before confirmation preserves old files; an atomic
retirement journal permits retry after partial deletion without treating a
partial tree as a new authenticated release.
The helper contains no demo component list; platform/help and renamed scenarios
use the same operations. Separate-UID enforcement and actual policy remain lab
requirements, not conclusions from mocked command results.

The direct trust-file format and policy constraint follow upstream documentation:
[fapolicyd.trust(5)](https://github.com/linux-application-whitelisting/fapolicyd/blob/main/doc/fapolicyd.trust.5)
and [upstream policy description](https://github.com/linux-application-whitelisting/fapolicyd#policies).
No allow rule or daemon shutdown is used to work around untrusted language opens.

## Final local checks (2026-10-22)

| Check | Actual result |
| --- | --- |
| Focused release, component-file lifecycle and standalone command tests | 50 passed; includes 17 new protected-release tests |
| Acceptance-harness discovery | 234 passed |
| `python3 -B tests/run.py platform --isolate` | 403 run: 399 passed, three unchanged gpg-agent signing fixture failures, one unchanged `/proc/self/fd/0` delivery-test error |
| Scoped Ruff lint/format on affected Python; Bash syntax on affected shell | Scoped checks passed; the documented full Ruff command was not verified (see correction below). Shellcheck unavailable |
| Pyright on affected Python | 0 errors, 0 warnings |
| Vermin on helper/probe and affected runtime-compatible product tests | Static minimum 3.5, compatible with required 3.6; actual 3.6 interpreter not run |
| Relative documentation links and `git diff --check` | Passed |
| Current-change OL9 separate-UID/SELinux/fapolicyd matrix | Not available here; all six runs pending |

The focused checks were rerun after the final payload-mode/fsync adjustment.
No tests were silently skipped or policy weakened to make the suite green.
The signing failures require working gpg-agent generation; they are not evidence
that actual gpgv verification passed locally. Signature-before-extraction order
and rejection are exercised with injected command failures; the real signature
and daemon path must pass in the lab. Understandability review of the final
success/retry/retirement flow is recorded above; no independent review is claimed.


## Review follow-up checks (2026-10-23)

Production signatures are now mandatory; publication uses only the pinned product
keyring, while `--keyring` selects input only for `provision-key`. The harness action
`publish-release` names its authentication/publication/enrollment effects explicitly.
The README and review guide record the temporary pre-customer migration exemption
and the required removal of old service-writable trust before reusing a lab host.

| Check | Actual result |
| --- | --- |
| Release regressions plus script-inventory test with `scripts/__pycache__` present | 21 passed (20 release tests) |
| Acceptance-harness discovery, including a run without `-B` | 237 passed |
| `python3 -B tests/run.py platform --isolate` | 410 run: 406 passed, three gpg-agent signing fixture failures and one `/proc/self/fd/0` delivery-test error, as in the previous local environment |
| Scoped Ruff lint/format; Bash syntax; Pyright on helper/probe/new tests | Scoped Ruff checks passed, not the documented full Ruff gate (see correction below); Bash/Pyright passed, 0 errors, 0 warnings |
| Vermin on helper/probe/release tests | Minimum 3.5, compatible with required 3.6; actual 3.6 not run |
| Current-change OL9/Podman/systemd/SELinux/fapolicyd matrix | Still pending; no current-change real-runtime result claimed |

The relabel regression sets a real user xattr on the published tree, confirms
ctime changed, then repeats publication, retains old scoped trust, waits for new
trust and retires the relabeled old release. Signature/key tests reject missing
signatures and caller-selected publication keys; commands remain mocked in these
unit tests. Diagnostic regressions preserve phase/path/exit or errno while
withholding injected credential values and captured subprocess output. The lab
probe now runs real `restorecon -R` before repeat authentication and deployment.

Understandability recheck: authority remains the signed snapshot and pinned key;
ctime is deliberately excluded to permit SELinux relabeling, with root trusted.
Successful relabel/repeat/upgrade/retire uses the same protected inventory and
existing retirement journal. Failure reports now name the operation/path or probe
phase without private stderr. No recovery mode, alternate key choice or unsigned
production branch was added. Customer-data migration becomes mandatory after the
first real customer installation, rather than adding a compatibility framework
for disposable pre-customer hosts. Lab verification is still required for closure.


## Lint correction and stronger probes (2026-10-23)

The earlier Ruff claims above referred to selected rules with command-line ignores
and formatting with an explicit target version. They did **not** establish that
the documented full Ruff commands passed. Review found real issues in the new
files. The host helper and probe now use the existing Python 3.6 `UP021`/`UP022`
file exemptions, explicit `check=False` with status handling, and narrow annotated
exceptions for authenticated controller exec and sanitized catch-all reporting.
Their formatting now passes the command documented in tests/README.md without
command-line overrides; host code remains compatible with Python 3.6.

Current actual checks:

- `ruff check deployment/ bundle.py scripts/release.py tests/ acceptance/ dev/smoke-test.py`:
  no findings in the item 54 files; 12 existing findings remain in unchanged
  `acceptance/init_secret_test.py` (8), `acceptance/test_init_secret.py` (3) and
  `tests/platform_tests/test_secret_templates.py` (1). This full lint gate is **not green**.
- `ruff format --check deployment/ bundle.py scripts/release.py tests/ acceptance/ dev/smoke-test.py`:
  all 134 files already formatted.
- Release unit tests: 21 passed. Harness discovery: 239 passed. These are
  distinct from real runtime evidence. Pyright on the helper/probe and affected
  tests reports 0 errors, 0 warnings; Vermin reports minimum Python 3.5 for the
  helper/probe (compatible with required 3.6, not an actual 3.6 runtime test).

The relabel probe now requires an actual temporary label change and restores it
in a finally block; it rejects a no-op chcon and an ineffective restorecon. The
bad-signature probe accepts only a typed command failure naming `gpgv` with a
signature/key rejection status (1 or 2); unrelated publication/lock errors,
other commands, launch failures and unexpected successful verification fail the
probe. Unit tests cover these negative cases and the typed command status.

Understandability recheck: the temporary label belongs to one selected public
release file, is restored before service-user execution, and changes no policy
rules. Publication still verifies before extraction, and retirement/retry keep
the same ownership boundaries. Failure classification now identifies the command
without exposing private stdout/stderr. No generic recovery flow was added.

The operator reports all 410 platform tests and 237 harness tests passed at
`7bb05dd`. That is verification of the previous revision, not current-change OL9
coverage. The strengthened chcon/restorecon and gpgv paths have not run on OL9
here; start with `--platform-help-only`, then run all six matrix scenarios before
closing item 54.


## First supplied OL9 run: registry fixture blocked (2026-10-23)

The operator supplied evidence for `release54-20261023-055311-app1`, revision
`7bb05dd`, on OL9.8 with SELinux Enforcing, fapolicyd 1.4.5 active, Podman 5.8.2,
systemd 252 and host Python 3.9.25. All five component installations/health checks,
host-path safety and `07-release-safety` passed. This verifies only that revision's
probe; it predates the forced chcon/restorecon and typed gpgv refinements.

The run is **NOT CLEAN**: `07-registry-offline` failed because fapolicyd denied
`sha256sum` opening the extracted, untrusted `scripts/release.py`, even as the
unprivileged operator. Outer archive checksum passed. Removing root authority
from that inner checksum operation was insufficient. Later lifecycle, upgrade
and retirement steps were not tested; the full matrix remains outstanding.

The fixture now verifies the complete inner file inventory and hashes from the
compressed tar streams via controller-supplied stdin code, then extracts only
`images/images.tar` and `images/images.txt`. It never opens an extracted Python
file, never enrolls fixture code, and preserves the offline registry-name/load/run
checks and audit gate. This changes only the lab data fixture; production signed
publication and trust remain in the protected helper.

The regression runs the actual shell action with real tar/checksum commands and
stubbed Podman/health/audit calls. A valid archive containing untrusted Python
passes without extracting that Python; modified Python, an unlisted file or a
missing image fail before Podman loading even when the outer archive checksum is
recomputed. Real fapolicyd verification of this fix still requires a new lab run.


Local follow-up checks: 240 acceptance-harness tests passed; Ruff lint/format on
the changed Python, Bash syntax, Pyright (0 errors/0 warnings) and `git diff
--check` passed. Success/rejection flow was rechecked: full archive inventory
before image extraction/loading, no fixture Python execution, unchanged service
user and production trust boundary. These checks do not claim an OL9 rerun.
