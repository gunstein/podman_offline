# App credential delivery (0.4.4)

Backlog item 14 replaces app1/app2's private signing-PVC imports with the existing
`SECRET_FILES` mechanism. There are no application/image changes. VERSION and
IDENTITY_VERSION are 0.4.4; unchanged PLATFORM_VERSION remains 0.4.3.

## Change and reason

Previously `credentials/todo/` (session-key, todo-client.key, todo-client.crt,
ca.crt) was archived by `VOLUME_FILES`. Source files and the archive were private,
but ordinary archive members were normalized to `0644`. Their actual imported
runtime permissions had not been verified. PVC delivery alone was not evidence
of an exploitable access path.

The same source files now form Secret `app1-signing` / `app2-signing`. Explicit
items keep the filenames and `/certificates` container interface unchanged.
The backend alone mounts them read-only; `defaultMode: 256` requests `0400` for
every file, including the public certificates. The current backend image uses
container UID/GID 0. Database password generation and delivery are unchanged.
Public route/client PVC imports keep their existing modes and behavior.

Identity does not read the generated API-secret configuration value: Program.cs
constructs API scopes and certificate-authenticated clients directly. Its unused
generation, Secret and envFrom reference, and empty app credential-directory
creation have been removed. API scopes, client authentication, token signing,
database users/passwords and demo users remain unchanged.

No migration, fallback, compatibility adapter, password rotation or automatic
deletion of retained credential files/volumes was added. Config remains
authoritative; the installer never rewrites persistent config to new defaults.
This change uses freshly initialized current configs, then preserves their
bytes and private files during ordinary repeat installs/upgrades/retries.
Historical task messages and verification reports retain their original claims.

## Local verification

Executed on 2026-10-16 with Python 3.12.14 / PyYAML 6.0.3:

| Check | Result |
| --- | --- |
| Product tests | 229 passed |
| Acceptance-harness tests | 162 passed |
| Ruff lint / format | passed, 53 Python files formatted |
| Pyright | 0 errors, 0 warnings |
| Vermin, host tooling and product tests | minimum Python 3.6 |
| ShellCheck, all documented shell entry points | passed |
| git diff --check | passed |

Python 3.6 compatibility was checked statically; no Python 3.6 interpreter or
second PyYAML version was available. No real acceptance/VM result is claimed.

Local product tests exercise actual component defaults/manifests and verify:

- Exact Secret bytes, independent app session keys, mode settings, selected
  file keys, backend-only read-only mount and the unchanged database interface.
- No private app import archive or signing-PVC is generated; public imports are
  unchanged. Rendered production YAML retains `0600` permissions.
- A failed app upgrade followed by install in a fresh interpreter retains
  config, database password, session key, client key and sibling state.
- Failed uninstall followed by retry preserves state without --delete-data;
  explicit deletion removes only the selected component's declared database
  and Secret-backed volumes and state, retaining sibling volumes/files.
- Identity defaults no longer generate/deliver the unused API-secret; the
  certificate script does not create its directory. Other Identity mechanisms
  remain present. Existing bundle/alias protections still run.

The acceptance helper's old unused-API-secret comparison is replaced by an app
credential probe. Harness tests execute its comparison logic and container probe
with synthetic files/transport: mismatching bytes, broad modes, wrong ownership,
failed exec, writable/non-readable mounts, frontend credential mounts and a
credential import archive are rejected without logging content or digests.
Stubbed host/container transport does not prove Podman/systemd behavior.

## Target verification still required

Podman is not installed in this workspace; no VM reset or container run was
performed. Upstream Podman v5.8.2 source was reviewed: `VolumeFromSecret()` reads
defaultMode and selected items, and kube play's volume setup applies the mode
with `f.Chmod`. It creates/reuses local volumes for Secrets; this is not an
encryption or memory-only storage guarantee. Reference:
[secret volume parsing](https://github.com/podman-container-tools/podman/blob/v5.8.2/pkg/specgen/generate/kube/volume.go)
and [kube play volume setup](https://github.com/podman-container-tools/podman/blob/v5.8.2/pkg/domain/infra/abi/play.go).

The existing fresh lab matrix now checks actual source/file hashes, UID/GID 0,
mode `0400`, read-only open behavior and absent frontend credential mounts at
the normal production check. Existing e2e covers login/client authentication,
signed sessions, markers and restart/upgrade persistence; uninstall steps and
sibling observations remain in the matrix. Run these only when the disposable
lab VM resets are authorized:

```sh
python3 acceptance/acceptance.py --run credentials-app1-first --first-app app1 run
python3 acceptance/acceptance.py --run credentials-app2-first --first-app app2 run
```

Both runs reset the configured disposable VMs. Real SELinux/fapolicyd behavior,
Podman file permissions/ownership, persisted sessions and volume cleanup remain
unverified until fresh runs pass. Rendered YAML and runtime copies remain
sensitive even though they use a resource named Secret. No concurrent lifecycle
commands are supported, as before this task.
