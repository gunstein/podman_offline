# Configuration and component lifecycle verification — 2026-10-14

The configuration roles, initialization workflow, merge rules, relative paths and
manual upgrades are documented in [README](../README.md#configuration-and-initialization).
No production state migration or general module/configuration framework was added.

## Local product and integration tests

164 tests passed with both PyYAML 6.0.3 on Python 3.14.4 and PyYAML 5.4.1 on
Python 3.11.17. All original product tests remain in the suite.

```sh
python3 -m unittest discover -s tests
.venv54/bin/python -m unittest discover -s tests
```

The new tests cover layer precedence and whole-map/list replacement, duplicate
keys and safe invalid-YAML errors, incomplete layers, dev output versus inputs,
retained credentials/data, complete private initialization without copying or
creating secrets, existing/empty/invalid config preservation, symlink rejection,
core common-value inheritance, missing installed core config, shared-value
mismatches, authoritative production config and changed defaults, required keys,
materialized relative paths, source/bundle versus standalone config paths,
selected bundle contents, and generated-secret aliases in every new config source.

Lifecycle tests cover unchanged/changed help registration with exact expected
restart sets, both missing-core app cases, equal-core file retention even when
incoming core manifests change, required keys when core is actually upgraded,
newer-core sibling preservation in both app orders, and older-core refusal with
all managed files and command calls checked.

Import archives normalize timestamps alongside the existing ownership/mode
normalization. A regression requires identical archive bytes after timestamp-only
changes and different bytes after content changes; core import checksums remain
part of persistent-state comparisons.

## Acceptance harness tests

139 controller/guest-harness tests passed:

```sh
python3 -m unittest discover -s acceptance
```

These stub external operations. They prove sequencing, scoped transfers, strict
observations, failure gates and trust retirement ordering; they do not prove
actual offline deployment. Full flows retain both app installation orders,
help-alone refusal, app1-only upgrade and retained-data uninstall, and add a real
help image/content upgrade plus newer/older core scenarios. `--help-only` adds
the focused app1/core → help → help-only-upgrade target flow.

## Static checks

Ruff 0.17.0 check/format, pyright 1.1.414, vermin 1.8.0 and ShellCheck 0.11.0
passed using the existing project scopes. Vermin reports a minimum of Python 3.6
for deploy.py, bundle.py and product tests. Python 3.6 itself was not executed.
ShellCheck covered all tracked shell scripts and the deploy wrapper.

## Target-machine runs

Runs used only the two configured disposable lab VMs. The harness checked lab
profiles before rollback and preserved all audit, isolation, SELinux and fapolicyd
requirements. Code was sent from detached verification snapshots; the working
branch and historical evidence were not rewritten.

| Run | Revision | Result |
| --- | --- | --- |
| `2026-10-14-config-help-01` | `93d3e10` | Readiness stopped on temporary-worktree index setup; no VM changes |
| `2026-10-14-config-help-02` | `93d3e10` | CLEAN PASS: app1/core → help → help-only upgrade |
| `2026-10-14-config-app1-01` | `2b6b46e` | Stopped at newer-core persistent comparison: import archive timestamp noise |
| `2026-10-14-config-app2-01` | `996ab21` | CLEAN PASS: full app2-first flow, help/app1/core upgrades and older-core refusal |
| `2026-10-14-config-app1-02` | `aca77b2` | CLEAN PASS: full app1-first flow, help/app1/core upgrades and older-core refusal |

Evidence and full step logs are stored outside Git under
`~/podman-offline-acceptance-runs/<run>/`. Failed evidence was retained unchanged.
The archive mismatch was fixed in code by timestamp normalization, without
excluding imports from comparisons or relaxing checks.

The focused help run verified a new help version/image tag and HTTPS content,
unchanged core/app1 processes (PID/start/restart count), versions, private state,
network identity and other bundle trust, retained task data and successful app1
e2e. It transferred only the new help bundle for the upgrade. New help trust worked;
old help trust/release were removed only after verification, followed by another
sibling check. Audit was clean.

Both clean full runs additionally verified both-app e2e and shared login, reboot,
crash/hang recovery with clean audit, app1-only upgrade, newer core with updated
marker and explicit process restart, unchanged sibling config/credentials/data
and import checksums, older-core refusal before image operations with all managed
files and service identities unchanged, successful e2e after refusal, and retained-data
uninstall with working app2/help and shared networking. The app1-first run used
the final deploy/bundle code, including the local materialized-config alias guard.

Changed help-route behavior is covered by focused product tests, rather than a
separate target-machine route-change run. HTTP acceptance does not execute browser
JavaScript. Complete existing persistent component config remains usable; operators
must explicitly add newly required keys or restore missing authoritative core config
from a private backup. No automatic production config rewrite/migration was added.

## Deliberately outside this change

General module refactoring, generic configuration frameworks, per-component dev
overrides, automatic state migration, image digest policy changes and trust/SELinux
policy changes were not introduced. Standalone fixture deployment remains supported
and was exercised by the target examples/registry tests. Legacy root config names
in that explicit fixture support and old external evidence are intentional.
