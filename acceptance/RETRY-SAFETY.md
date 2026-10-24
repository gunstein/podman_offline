# Install/uninstall retry safety — 0.4.2

Baseline: `d53afe4d57c2b45374bd5bfe061af3b6096d3b96`. Before this change,
207 product tests and 158 acceptance-harness tests passed with Python 3.12.14 /
PyYAML 6.0.3. Historical reports remain unchanged.

## Current completion follow-up (backlog 39)

The historical evidence below predates the status command. The current
`/var/lib/<product>/state/pending-operation.json` also represents the selected
install attempt, even without registration owners. `begin_install` saves it after
image verification and before installed metadata/registrations/service files
change. `owners=[]` means owner work is confirmed, not that install is complete.
The previous completed version stays in `installed/<id>` during failed work.
Only `install_component_plan`, after healthy restarts and the durable completion
marker write, clears the whole install operation. Uninstall retains its existing
separate final acknowledgement after its scoped removal steps.

Fresh-process regressions cover same-version daemon-reload failure, last-owner
acknowledgement followed by marker failure, and read-only status/retry. An opt-in
lab probe is implemented but not run; see [current evidence and commands](STATUS.md).
The counts and host evidence in the original report below are historical.

## Cause and fix

Installation previously used only registration file differences to decide shared
restarts. Those files were written before service restarts. A failed app restart,
shared restart/check or import write left files that compared equal on retry even
though Identity/platform had not consumed them.

`HOME/pending-operation.json` now records the selected component and unfinished
registration owners before registration writes. Retries merge recorded owners
with new differences, rebuild necessary imports and restart/check only required
owners. Each owner is acknowledged only after its existing `systemctl --user
is-active --quiet` check succeeds. A new invocation cannot lose work merely
because registration files now compare equal. Incoming client metadata is staged
from its descriptor even when its preceding write left an incomplete directory.

Uninstall previously removed YAML and the installed marker before all owner
restarts and optional volume removals succeeded. A retry either lacked its volume
inventory or was refused as not installed.

Before stopping/deleting anything, uninstall now validates and saves the component,
original deletion choice, exact component-prefixed volume names, affected owners
and a stop checkpoint. The service name is derived from the validated component.
A successful stop is recorded before removing YAML/Quadlet files, so a retry does
not try to stop an already unloaded unit. File removals and retained-data cleanup
are idempotent. Owner imports/restarts/checks are acknowledged separately. Volume
absence means already removed; inspection errors still fail. The installed and
dependency markers and operation record are removed only after required work.
The saved inventory permits retries without the original YAML or marker.

The JSON record contains no credentials, configuration values or registration
payloads. It is written as mode 0600 from creation, flushed/fsynced, atomically
replaced and followed by parent-directory fsync. Symlinks in its path are refused.
Strict operation/field/type/owner/component/volume validation rejects malformed
state; uninstall also checks its removal paths before acting. State is in the
service user's persistent home, outside release directories and offline bundles.

## Operator behavior

Use the same component's verified/trusted bundle and repeat the failed command:

```sh
./deploy install
./deploy uninstall
./deploy uninstall --delete-data
```

Choose the original command; the two uninstall choices are not interchangeable.
An opposite `--delete-data` choice is refused before changes. A pending operation
blocks other component lifecycle commands and config initialization; the error
names the recorded component and command to finish. In particular, an uninstalling
Identity/platform cannot be used as an available dependency, and uninstall cannot
discard pending installation registrations. No command clears another operation's
work. Do not manually remove/edit the record to bypass a conflict.

Unchanged registrations without pending work restart neither shared service;
route-only changes affect platform, client-only changes affect Identity, both
affect both. Sibling apps do not restart as a side effect. Ordinary uninstall
retains config/credentials/data; explicit deletion affects only its saved own
resources. Existing dependency/version checks, credential generation, container
interfaces, offline checksums, SELinux and fapolicyd flows remain unchanged.

## Files and verification

Changed runtime code: `deploy.py`. Release metadata advances to 0.4.2 in VERSION,
PLATFORM_VERSION and IDENTITY_VERSION; image tags/application code are unchanged.
Tests add `tests/test_retry.py` and `tests/retry_driver.py`; the existing Identity
import fixture moves into shared ComponentFixture in `tests/test_components.py`
and is inherited by `tests/test_identity.py`. README, tests/README, BACKLOG and this
report document behavior and evidence. No new lab scenario is needed to inject
these targeted failure boundaries.

Final local checks: 220 product tests and 158 acceptance-harness tests passed
with Python 3.12.14 / PyYAML 6.0.3. Ruff lint/format, pyright, vermin (Python 3.6
minimum), shellcheck and `git diff --check` passed.

The 13 new product tests use genuinely distinct interpreter processes for every
initial invocation/retry. They retain the same files, real tar archives and
simulated volume inventory between attempts. Coverage includes:

- App restart failure and abrupt process exit after registration writes.
- Identity/platform restart and subsequent active-check failures; only unfinished
  owners repeat, and imports precede restart.
- Import write failure with identical persistent registrations on retry.
- Combining old pending route work with a new client change.
- Partial public client writes, regenerated from the incoming descriptor.
- Uninstall owner failure with YAML already gone, retained config/credential bytes,
  no volume operations and removed registrations excluded by rebuilt indexes.
- Uninstall import failure, followed by successful owner restarts.
- Completion cleanup failure after markers, YAML, volumes and own data are gone;
  the saved plan still permits another fresh-process retry.
- Later-volume deletion failure after an earlier volume was removed, safe absence
  handling on retry and unchanged sibling/Identity volume inventory and state.
- Mismatched deletion flags, install/uninstall conflicts and unavailable pending
  dependencies, without discarding the original record.
- Invalid/nonprivate/symlinked pending state and out-of-component volume names.
- Volume inspection errors retained as errors with unfinished work still pending.

Existing normal route/client four-combination coverage, lifecycle, dependencies,
secret preservation, archive, Python and acceptance-harness checks also pass.

## Limits

Podman/systemd and environment checks are stubbed in failure tests. Fresh Python
processes and real filesystem/import operations do not establish actual target
service behavior, Podman volume semantics, target permissions, SELinux/fapolicyd
integration or machine power-loss recovery. No real VM/container acceptance run
was performed. Python 3.6 is checked statically; no Python 3.6 runtime or second
PyYAML version was available. Real lab verification remains separate, using the
existing fresh-install/lifecycle commands in acceptance/README.md.

Run one deploy lifecycle command at a time. The record is not a process lock,
general transaction engine or automatic rollback. Unknown partial operations
from an earlier installer without retry metadata are not automatically repaired.
Malformed records require diagnosis rather than guessed recovery. Process death
while creating the private temporary journal file can leave an unreferenced
`.pending-*` metadata file; the canonical operation record remains authoritative.
No migration, credential rotation or module refactor is included.
