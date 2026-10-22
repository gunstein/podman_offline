# Protected releases (backlog 54)

Implementation on branch `feature/protected-releases`, based on `a37f4e4`.
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
key is refused. Rotation is a separate administrator operation.

In the lab, the controller sends its reviewed source over authenticated SSH;
Bash's builtin printf streams code to `sudo python3 -I -B -` through a real pipe. Isolated mode excludes caller
CWD, PYTHONPATH and user site modules from privileged imports; the regression
also plants hostile yaml/argparse modules and verifies they are ignored.
The root interpreter opens no untrusted target Python file. A regression compiles
the actual generated source and checks stdin's FIFO type, including the large
embedded helper. The shared helper imports only host-installed PyYAML and Python
standard-library modules, never the incoming release's deployment package.

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
   archive digest. Stored device/inode/ctime/mtime bindings reject later changes,
   including same-size writes and removed/recreated entries, without reopening
   untrusted payloads. Authenticated VERSION/descriptor/checksums are read from
   the archive stream, with a 16 MiB limit on each metadata file. Never manually
   copy/chmod/relabel a published release; those operations invalidate bindings.
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
checks/extracts it and streams image data to rootless Podman. Root no longer
checksums its operator-writable extraction. Historical removed legacy scenarios
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
there are no permitted outside-target writes or policy changes. This does not
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
| Ruff lint/format on affected Python; Bash syntax on affected shell | Passed (existing lint exceptions retained; shellcheck unavailable) |
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
