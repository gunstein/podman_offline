# Quadlet placeholder syntax (backlog 59)

Implemented on `fix/59-quadlet-placeholders` (2026-10-23). This is a consistency
and early-validation change; it does not diagnose a runtime unit-generation bug.

## Contract and implementation

Both shipped templates now use `@@UNIT_NAME@@` / `@@PRODUCT_NAME@@`.
`deploy.quadlet_text(suffix, product, name)` reuses `templates.substitute` with
an internal-only resolver. It supports repeated/inline tokens in a single,
nonrecursive pass. No config object or credential source enters the resolver.
Unknown config names, Secret references, malformed or unresolved markers, invalid
UTF-8 and obsolete `{name}` / `{product}` are refused with template-path context.
Shell `${name}`, `${product}`, other `${...}`, literal braces and systemd `%`
specifiers are retained. A template need not use every allowed marker.

`check_quadlet_templates(component)` obtains the product from the catalog or
compiled bundle descriptor and the unit from `catalog.unit_name`. Standalone
uses `common.STANDALONE_PRODUCT` for both. Config settings named `UNIT_NAME` or
`PRODUCT_NAME` do not change these values. No aliases, external dependencies,
network schema or alternative template engine were added. YAML typed replacement,
ConfigMap composition and Secret policies are unchanged.

## Validation and lifecycle review

- Source/standalone validate and prepare reach the pure check through
  `validate_component` before manifest preflight, generation, output or host calls.
- Bundle validate calls `service_user` (read-only identity/layout selection), then
  `install_checks`, which checks both templates even when an equal-version
  `newer-only` operation will skip rendering.
- Bundle install selects the account/layout and runs `install_checks` before
  `production_environment` queries the user manager. The latter retains its own
  identity/runtime checks. Invalid templates therefore stop before even this
  read-only systemd query, not merely before Podman image loading.
- Standalone install similarly selects the account/layout and checks both
  templates before `production_environment`, retaining the checked text for writes.
- Valid installs keep the existing staging, materialization, image import, unit
  writes, shared-network comparison, owner restart, pending-state acknowledgement
  and completion-marker ordering. Component unit writes use the same renderer.
  Source dev and bundle building do not select production paths.

Successful flow: descriptor/catalog names -> shared token parser with internal
resolver -> existing manifest/host checks -> materialization -> unchanged unit
names and YAML/network references. Failed template flow: the pure check raises,
leaving credentials, rendered files, installed metadata, pending state, shared
network and siblings intact. Fixing the template permits the normal repeat using
retained state. No new durable state or transaction layer was introduced.

The affected source and diff were reviewed separately from test results. The
understandability review passed: internal name authority, accepted tokens, early
validation, side effects and retry ownership remain explicit. Two fixture changes
follow the affected lifecycle: standalone examples now copy the required templates,
and the fresh-process retry driver stubs the newly explicit identity/layout call
alongside its existing environment stub. Real layout guards remain tested by the
existing layout/wrapper tests.

## Regression evidence

`tests/platform_tests/test_quadlet_templates.py` adds eight focused tests covering:

- Exact inline/repeated rendering and literal braces, shell expressions and
  systemd specifiers; optional/absent markers and nonrecursive refusal.
- Both template paths, unknown/config/Secret tokens, malformed/obsolete/mixed
  syntax, invalid UTF-8 and diagnostics without full template contents.
- Standalone output and refusal before host queries, materialization or mutations.
- Source validate/prepare and first bundle install before generated password writes.
- A renamed `cedar` product with separate `processor` and `observer` components,
  no `apps/`, real offline bundles relocated after deleting their source, exact
  shipped unit/network bytes, unit permissions and config names unable to override
  internal names.
- Both ordinary and equal-version `newer-only` repeat installs: validate/install
  agree on errors, no host query runs, the complete fixture inventory remains
  unchanged, and repair/retry retains shared-network inode/bytes and sibling state.

Existing validation, wrapper, bundle, renamed-product and fresh-process retry
regressions provide the broader lifecycle coverage.

Current-change local checks:

| Evidence | Result |
| --- | --- |
| Focused product tests (Quadlet, deploy, validate, components, validation ordering) | 151 passed |
| `python3 -B tests/run.py platform --isolate` | 441 passed |
| `python3 -B tests/run.py demo` | 66 passed |
| `python3 -B -m unittest discover -s acceptance -p 'test_*.py'` | 243 passed; stubbed runtime transport |
| Ruff for changed Python files and documented format/Pyright/Vermin checks | Passed; Vermin minimum Python 3.6 |
| `bash -n examples/run.sh` | Passed |
| ShellCheck | Not run: executable unavailable in this environment |
| Relative documentation links and `git diff --check` | Passed; 182 local link targets checked |

Full-tree Ruff still reports 12 pre-existing findings in
`acceptance/init_secret_test.py`, `acceptance/test_init_secret.py` and
`tests/platform_tests/test_secret_templates.py`. This gate is not green; changed
Python files pass Ruff.

The initial isolated run failed because the retry driver still bypassed only
`production_environment`, leaving the newly explicit `service_user` call to read
an absent production bootstrap. The driver was updated to preserve its existing
fixture identity/layout boundary; tests were not excluded.

## Runtime verification gap

No real Podman/systemd/SELinux/fapolicyd run was performed for this change.
The previous manual production installation and historical lab matrices do not
verify the new templates or renderer. Python 3.6 was checked statically; no Python
3.6 interpreter was run. For current-change runtime evidence, use a clean committed
checkout and the existing app1-first and renamed-product lab scenarios from
[acceptance instructions](README.md), with unique run IDs. They reset the configured
disposable VMs and cover real template consumption, repeated installation, upgrade
and shared networking; they have not been run here.
