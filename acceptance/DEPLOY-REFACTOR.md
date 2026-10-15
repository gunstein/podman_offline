# Deploy package refactor — 0.4.3

Baseline: `034f8b0eb58136d9cf5390335a96f20b3e4bdc6e`. Before changes, 220 product
tests and 158 acceptance-harness tests passed on Python 3.12.14 / PyYAML 6.0.3.
Existing historical reports and pinned upgrade fixtures retain their evidence.

## Structure and behavior

The root deploy.py is replaced by `deployment/__init__.py`, `__main__.py`, cli.py,
common.py, render.py and deploy.py. Root `./deploy` changes to the release and
runs `python3 -B -m deployment`; `./build-bundle.sh` remains stable and uses `-B`.
Both source and unpacked bundles work from an unrelated caller directory.

CLI handling lives in cli.py; common.py contains paths, errors and fixed component
contracts; render.py owns config/YAML/secrets/manifests/import archives; deploy.py
owns DB/host preflight, initialization, dependencies/versions, registrations,
retry state and service lifecycle. COMPONENTS derives from the existing fixed
dependency graph rather than duplicating its names. The bundle selections remain
in bundles.yaml, with generated contracts validated against that same graph.

The first move was mechanical and passed all 220 baseline product tests before
readability changes. An AST comparison, ignoring module qualification, docstrings
and helper renames, confirmed unchanged original function bodies except prepare
and install_component_plan, before the later scoped CLI hint update and removal
of the duplicate pending-owner map. Pending owners use the unchanged fixed
dependency graph, which has exactly the same allowed sets as that old map.
Those two functions delegate to explicit steps at
their original boundaries. `materialize_and_render` names the existing creation
of missing generated secrets and optional imports; validation timing is unchanged.
Standalone fixture support is isolated in named prepare/install helpers.

The install plan now reads as network check → materialize manifests → load/verify
images → persist/apply registration work → write services/imports → restart/check
services → record installed contracts. Existing safety/failure semantics are
retained, including generated secrets before image loading and possible committed
files before restart failures. All fresh-process retry tests still run the real
lifecycle in separate interpreters with only host transport stubbed.

The CLI failure hint now names the selected component service rather than the
standalone `myproduct.service`; its focused regression covers that diagnostic.
Standalone hints retain their own service name.

No component architecture, credential paths, private bytes, version comparison
rules, container interfaces, immutable image tags or application code changed.
Release metadata advances to 0.4.3. No migration, old-module fallback, compatibility
branch or automatic repair of older installs was introduced. Existing historical
core/combined-layout refusal checks remain mechanically moved behavior; pinned
old-release fixtures are not converted to the new package.

## Required trust change

Active README, VM checklist, remote acceptance lifecycle and trust tests use only
`<release>/deployment/` recursively, in the existing per-bundle trust file.
The root wrapper/config/credentials/whole release are not added. The helper
reads the expected package files and requires all individual trust records;
it handles delayed updates, nested/space-containing paths, malformed/duplicate
records, missing files and complete old-prefix removal. Old package trust is
removed only after the existing successful verification gates, retaining other
bundles' entries. Sibling observations validate exact per-file package trust and
continue comparing processes, state, network and versions.

No new allow, crun, memfd or SELinux policy changes were made. Upstream documents
recursive directory add/delete; actual installed fapolicyd behavior remains a lab
gate, not a claim established by stubbed tests. Historical legacy-install code,
old helpers and test fixtures retain their old single-file trust references.
The new active command path has no fallback to that layout.

## Tests and files

Final local results: 224 product tests and 160 acceptance-harness tests pass with
Python 3.12.14 / PyYAML 6.0.3. Ruff lint/format, pyright, vermin (minimum Python
3.6), shellcheck and `git diff --check` pass. Python 3.6 was checked statically;
no Python 3.6 runtime or second PyYAML version was available.

Product tests retain validation/image failure boundaries, independent bundles,
all four route/client restart combinations, scoped uninstall/data retention,
generated-secret security, checksums and all 13 fresh-process retry scenarios.
Tests import/patch the owning module and common path context rather than the old
monolithic namespace. A focused regression executes the real dev preflight heredoc against fresh defaults
and checks that it imports the package, probes the three DB volumes and writes
no state. The help-alone probe is checked to execute the Bash wrapper, not pass
it to Python. New archive regressions inspect real package members,
exclude nested bytecode and the removed root module, and reject package symlink
aliases to declared secrets. The wrapper regression unsets the bytecode environment
flag, runs source/unpacked prepare/init/install/uninstall and confirms no cache
files appear. Thus it checks the actual `-B` entrypoint behavior.

Two new harness tests require complete recursive package trust and exact sibling
package inventories, rejecting missing, duplicate, stale or unexpected records.
Existing trust cleanup sequencing and failure-stop tests remain in place, adapted
to the new wrapper/package paths. Historical upgrade tests remain unchanged.

Runtime/build files changed: the new deployment package, root deploy wrapper,
build-bundle.sh, bundle.py, dev/dev.sh and examples/run.sh. Acceptance database and
registry helpers now import/copy the package; remote.sh uses package trust and
the wrapper. Relevant product/harness fixtures and imports are adapted. README,
ARCHITECTURE.md, VM checklist, test/acceptance READMEs, release version files and
BACKLOG document the resulting structure and verification.

## Target verification and limits

No real Podman/systemd/SELinux/fapolicyd/VM acceptance run was performed here.
Local Python/subprocess/filesystem tests do not prove directory trust, offline
startup, target access rules, service health, shared login, DB operations or reboot
persistence on the target. Use fresh disposable lab snapshots from a clean commit:

```sh
python3 acceptance/acceptance.py --run package-app1-first --first-app app1 run
python3 acceptance/acceptance.py --run package-app2-first --first-app app2 run
python3 acceptance/acceptance.py --run package-help --platform-help-only run
```

Each command resets both configured lab VMs. The normal matrix includes app,
help, platform and Identity upgrades, old-package trust retirement, retained data,
reboot and unchanged sibling observations. Real directory trust remains explicitly
unverified until those runs pass. No additional VM scenario is necessary for the
mechanical module move beyond the adapted matrix and focused local checks.

Source review identified one existing acceptance-helper limitation, left unchanged:
`prepare_release()` adds trust only when first creating the release directory.
If extraction succeeds but trust registration fails, retrying against that
existing directory only waits for missing trust; it does not re-add it. The
README's explicit add/update/wait steps provide the manual recovery path. A
separate helper retry fix should address this; it is outside the module move and
the deploy lifecycle pending-operation mechanism.

No unrelated behavior fixes were included. The existing no-concurrent-lifecycle
limitation and unknown-state recovery boundary remain as documented in
RETRY-SAFETY.md. Migration, password rotation and deferred backlog work remain
outside this refactor.
