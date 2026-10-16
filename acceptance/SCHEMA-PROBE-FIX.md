# Schema init probe compatibility — 2026-10-16

Baseline: `df9aad4e0d50cb88fb14b625db1a8505f691c3f0` (app/help 0.4.8,
platform/Identity 0.4.7). The original failed acceptance evidence is preserved at
`~/podman-offline-acceptance-runs/20261016-173010-app1-first/`.

## Failure and scoped fix

The original run stopped at `03-database-runtime` with Podman exit 125. The
generic error attributed all kube operations to Identity/PostgreSQL and withheld
the underlying stderr. A separate disposable reproduction established that
PostgreSQL and the Identity connection check succeeded; `schema-init.yaml` failed
before its pod could start:

```text
Error: couldn't get object kind: error converting YAML to JSON:
yaml: line 12: did not find expected '-' indicator
```

The fixture's multiline Python command triggered the failure during Podman's
YAML conversion. The source document loaded with PyYAML. Serializing the input
as JSON still failed: Podman 5.8.2 decodes and re-marshals individual documents
before inspecting their kinds. See `splitMultiDocYAML()` / `getKubeKind()` in
[the versioned Podman source](https://github.com/containers/podman/blob/v5.8.2/pkg/domain/infra/abi/play.go).
This is a finding about this concrete fixture, not a claim that Podman rejects
all multiline commands.

`init_schema_check()` now assembles its small static verification program as
readable individual statements, joined into one command line. It still verifies
schema readiness, asserts an initially empty table, inserts and commits a row,
then reruns the real app1 init command and requires the same retained row. The
replay performs no insert. Successful checks explicitly commit and close their
connection. No credential value is included in the command.

`podman()` errors now name the kube action and fixture basename, rather than
guessing the client type. Raw stdout/stderr, credentials, connection strings and
environment dumps remain withheld. This makes a failed schema probe distinguishable
from the Identity check without exposing private diagnostics.

No production manifest, image, application code, config model, generated-secret
policy, deploy lifecycle, trust rule or generic YAML renderer changes. The probe
still uses the shipped app1 init declaration and its existing Secret, DB parameters,
network and volume. Only UUID-scoped disposable test resources are created/deleted.

## Local verification

- 253 product tests passed with Python 3.11 / PyYAML 5.4.1.
- 163 acceptance-harness tests passed.
- Ruff check/format, pyright, vermin (host/product minimum Python 3.6), ShellCheck
  and `git diff --check` passed.
- The construction/replay regression requires newline-free compilable commands,
  explicit commit/close, initial insertion and no insertion on replay. It retains
  checks of the actual init image/command, DB parameters, Secret mounts, unchanged
  input and failure cleanup.
- A new diagnostic regression requires the kube action/fixture in failures and
  verifies that private subprocess output is not exposed.

## Target verification

A focused run on the existing authorized Oracle Linux 9.8 dev VM, rootless
Podman **5.8.2**, passed all three credential cases (special characters, Unicode
and legacy hexadecimal/trailing LF). It verified real PostgreSQL initialization,
Identity environment and Python file-secret connections, authentication refusal,
missing-password/retained-volume protection, actual app1 init/replay with retained
rows, and cleanup of the disposable resources.

Focused output: `~/podman-offline-acceptance-runs/diagnostics/20261016-schema-probe-fixed-01.log`.
This was not a full offline installation or systemd/security acceptance run.

The new full app1-first run uses clean detached snapshot
`2bbd10b366c0b27c013fcbf06d4eaffc3de5dd31` (baseline plus the two changed Python
files), under `~/podman-offline-acceptance-runs/20261016-schema-probe-app1-01/`.
It finished with **CLEAN PASS: all 117 steps passed**. The repaired database step,
dev/e2e/registry/examples, bundle checksums, real offline installation, database
authentication, shared login, data markers, stop/start/restart, crash/hang, reboot,
help/app1/platform/Identity-only upgrades, older-platform refusal, sibling
preservation, retained-data uninstall and survivor checks all passed. Final audit
reported no FANOTIFY/AVC events; cleanup passed. All 117 log SHA256 values match
the evidence. The production VM retained SELinux Enforcing, active fapolicyd and
firewalld with the existing offline isolation and directory-trust model.

Read `REPORT.md`, `EVIDENCE.md` and `record.jsonl` in that run folder for the exact
revision, artifacts, steps and timings. The report records SSH post-quantum-key-
exchange and pip root-user/version warnings; these were not test failures.

## Understandability review and limits

The affected flow is `run()` → `init_schema_check()` → the actual declared init
container → the fixed verification command → pod removal → replay on the same DB.
DB parameters and Secret references come from the disposable client's manifest;
schema preparation comes from the app1 declaration. The statement list exposes
the row assertion, insert and commit boundaries. Failure raises before replay,
the existing `finally` removes the probe pod, and the outer cleanup removes only
its disposable resources. There is no installed retry record to change here.

Credential retention, scoped cleanup, unchanged application interfaces and bounded
diagnostics were the relevant reviewed contracts. Understandability review found
no additional lifecycle abstraction necessary. Unrelated component/preflight gaps
remain owned by the existing backlog and review guide.

Other Podman versions and an actual Python 3.6 runtime are unverified. The
app2-first and focused platform/help-only scenarios were not rerun for this fix.
The focused run does not replace the full run's offline/systemd/security evidence;
conversely, the full happy-path run does not establish every injected init failure
or arbitrary manifest shape. Historical reports remain unchanged.
