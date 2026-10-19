# Secret templates and ConfigMap inline values: verification and lab handoff

Implementation: backlog 41, Identity component 0.4.12 / image 0.2.2 and platform
component 0.4.12 (unchanged stock nginx image).
The operator authorized local implementation before the prerequisite lab probe
on 2026-10-19 and will perform real verification separately. No real Podman,
systemd, SELinux or fapolicyd result is claimed by this report.

## Contracts and implementation

- The retained file is authoritative. Existing credentials are not overwritten;
  templates read the same loaded file Secret bytes used for delivery.
- Recipes accept config string/integer inputs and same-component `SECRET_FILES`
  keys; no recursive/derived references. Public ConfigMap `data` can compose
  string/integer config through the same single-pass callback, with Secret
  references refused. Other manifest fields retain whole-value replacement.
- Declarations, names, references and public inputs validate before generation;
  `validate` never reads credential contents or runs host commands.
- After DB preflight and permitted generation, derived data is composed in memory
  and encoded in the existing 0600 install YAML. No derived source file is added.
- Unsafe input is rejected without values in diagnostics. The character rule is
  deliberately narrower than the Python file-client interface.
- `newer-only` with an equal version still skips rendering. systemd restart uses
  installed YAML; actual config/credential changes need a rendering install.
- `secretKeyRef` env values are accepted as visible to the service user/root.
  Source, YAML, Podman storage and backups are not encrypted by this feature.
- No SELinux/fapolicyd rules or external runtime dependencies are added.

`deployment/templates.py` owns recipe shape, parsing, public/reference checks and
private composition. `config_text()` is the public-only resolver, and
`substitute()` is shared with both private validation and materialization.
`render.configmap_data()` preserves original whole-value semantics and ensures
inserted values are not interpreted recursively. `render.py` supplies names for validation and loaded file
Secret documents during materialization. It integrates links/key checks and the
existing uninstall resource inventory. Only original `SECRET_FILES` may serve as
a database password source. `catalog.py` reserves the new setting from sharing.
`bundle.py` needs no new path handling because templates add no file sources.

Identity now consumes a complete environment value. The PostgreSQL pod keeps its
file interface; app1/app2 keep their Python file readers. Existing installations
must explicitly add the recipe to persistent config before installing the new
Identity manifest. Deploy does not merge new defaults.

## Local evidence

Python 3.12.14 was used. Product tests use runtime stubs, and acceptance-harness
tests prove scenario construction/assertions only. Results are recorded in
backlog 41 after the final run:

| Check | Result |
| --- | --- |
| Product suite with ConfigMap extension | 389 collected: 386 passed, 3 environment-blocked GnuPG tests skipped explicitly in the verification invocation |
| Acceptance harness | 193 passed; host commands stubbed |
| Ruff check and format | Passed |
| Pyright | 0 errors, 0 warnings |
| Host compatibility | Vermin: Python 3.6 for deployment, bundle and new/changed template/retry product tests |
| Shell syntax / whitespace | `bash -n acceptance/remote.sh` and `git diff --check` passed |
| .NET / Podman / systemd / SELinux / fapolicyd | Not run here; lab pending |

The original full product run hit three existing
GnuPG fixture failures: `/tmp` is unavailable here. Redirecting that test directory
to writable scratch also failed at GnuPG key generation. These signing tests are
unrelated to this change and require the normal controller/lab environment.

New coverage includes declaration failures before generation, source keys,
restricted characters and redaction, LF stripping, size limits, deterministic
output, preserved source bytes, generated files, config/password changes, and a
restart failure followed by retry in a fresh interpreter. A minimal worker has
no .NET, Identity, DB, gateway or certificates. The renamed `shop` product must
render renamed template IDs and `secretKeyRef` references without code changes.

ConfigMap extension: product tests cover multiple/public integer placeholders,
multi-line and literal dollar/backslash text, forbidden Secret references, invalid
markers/types and unchanged scopes. Worker install/config-change and missing-key
init cases exercise the real lifecycle. Three harness tests verify demo and `shop`
consumer selection, stale/unrendered/missing values and failure before health
success. Every lab `healthy()` call requires the demo value in its running proxy.

The understandability review traced successful install and failed restart/retry:
`validate_component` -> `check_templates` -> database preflight -> `materialize`
-> file Secret documents -> `templates.documents` -> existing publication and
restart -> completion marker. No additional durable state is needed; retry
recomputes derived values from retained config/passwords. ConfigMap success and
failure were traced through the same `configmap_data()` helper at initialization
and effective-document validation, before any generated output. Source strings
remain distinct from already replaced values to prevent recursive expansion.
Existing file-write
atomicity and credential rotation are not expanded in this task.

## Disposable runtime probe

After building the current demo images, as the rootless DEV lab user:

```sh
python3 acceptance/secret_templates_test.py
python3 acceptance/database_test.py
```

The first command uses hand-written kube input independent of the product
renderer. It checks initial env/file delivery and changed values with
`kube play --replace`, then initial Quadlet start and unit restart. The running
process checks its mounted file equals its env value, and the controller checks
that inspect contains the expected env value without printing it. Logs/journal
must not contain any probe value. Only UUID-scoped probe pods/Secret/volume/unit
and private temporary YAML are created and cleaned up; cleanup failures fail.

To run the exact same probe under the hardened PROD service account after its
images have been installed, transfer this probe file as lab input and pass it to
Python on stdin (no script trust entry is needed). From a lab user's shell on
PROD, assuming the file is in the current directory:

```sh
product=myproduct  # product: in the tested bundles.yaml
sudo -n -H -u "$product" bash -c '
  cd "$HOME" || exit
  export XDG_RUNTIME_DIR="/run/user/$(id -u)"
  exec python3 - --image localhost/demo-todo-backend:0.2.2
' < secret_templates_test.py
```

`--image` uses an already installed Python-capable image and avoids source-tree
imports. This works offline. Record Podman version, SELinux/fapolicyd state and
the probe result alongside the matrix results. A failed env/replacement probe is
a blocker for deploying this feature; do not infer success from unit tests.

## Six-scenario matrix

Run from a clean committed controller checkout with the configured disposable
lab VMs. These existing commands reset those VMs to their configured snapshots.
Use unique run IDs. The default config path remains
`~/.config/podman-offline-acceptance/lab.env`.

```sh
python3 acceptance/acceptance.py --run templates-app1 --first-app app1 run
python3 acceptance/acceptance.py --run templates-app2 --first-app app2 run
python3 acceptance/acceptance.py --run templates-help --help-only run
python3 acceptance/acceptance.py --run templates-platform --platform-help-only run
python3 acceptance/acceptance.py --run templates-identity --identity-only run
python3 acceptance/acceptance.py --run templates-shop --renamed-product run
```

All six scenarios run the shared `healthy()` check, which verifies the public
`PUBLIC_ENDPOINT` ConfigMap value against hostname/port inputs and `printenv`
in the proxy container; renamed products are found by their ConfigMap reference.
A missing sample or an incorrectly rendered/runtime value fails the check.

`database-runtime` starts with the disposable env/file/restart probe, and renamed
runs also execute it. Installed `database-auth` checks correct credentials and
wrong sibling credentials, private container/journal diagnostics, ConfigMap
safety and mode 0600 YAML. Deploy output is captured and checked before being
published into acceptance evidence.

The focused Identity scenario first builds the genuine pinned in-app builder
from `932c7f3a647a84fb5388144bc822f895cc40d959`, component 0.4.11. It reads those files
from the transferred local Git history without fetching. It then builds current
HEAD with a new health marker, explicitly adds only the template recipe to the
old persistent config, and follows the ordinary upgrade path. Existing config
settings, password/key bytes, DB/protection volume identities and sibling state
must be preserved. Installed `--database-check`, login, users/CRUD, markers and
new image/content must pass before the old release trust is retired. Disposable
new-image Identity checks are omitted while this scenario is intentionally
running the old image; the upgraded installed image is checked afterwards.

## Pending real evidence

- Direct and Quadlet probe on rootless Podman 5.8.2, including hardened PROD.
- Six CLEAN PASS matrix results, including pinned in-app -> template Identity.
- .NET image compilation/runtime, actual mounts/modes, SELinux and fapolicyd.
- Actual Python 3.6 execution (static compatibility check is not runtime proof).
- The three existing GnuPG product tests in an environment supporting gpg-agent.
