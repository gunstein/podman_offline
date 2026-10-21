# Component-specific dev configuration (backlog 56)

Implemented on 2026-10-21. Local product/harness verification is separate from
real Podman/systemd evidence; no real lab run of this change has been performed.
Existing installations may be discarded, as explicitly agreed by the operator.
No migration or compatibility layer was added. Item 57 remains unimplemented.

## Behavior and contracts

Source dev config has four optional layers, from lowest to highest priority:

1. `config/common.defaults.yaml`
2. `components/<id>/config.defaults.yaml`
3. `config/dev.yaml`
4. `components/<id>/config.dev.yaml`

All use `render.merge_config`: later top-level values replace whole earlier
values. Maps/lists are not recursively merged. `public_from` owner values are
still applied last. A dependent's component dev file that declares an owner's
shared key is refused, naming the key, file and owner without printing values.
The global dev layer retains its existing owner-wins behavior (backlog 58).

Production `init-config` never reads the dev layers; later validation and install
continue to read only authoritative persistent config. Tests deliberately place
malformed dev files into an unpacked release and exercise all three operations.
Actual bundle archives exclude component dev overrides and referenced external
local inputs. The bundle guard also reads the new layer so private/generated
sources declared only there cannot enter the archive through an alias.
The existing allowlist still includes a component's entire `files/` tree.

Relative sources retain their config-directory base (`build/dev/<id>/` in dev).
This change neither introduces portable component-file references nor collects
local input files for bundling. Ordinary credentials, database-volume guards,
sibling resource isolation and Python 3.6 compatibility remain in force.

## Dev config readers and consumers

The implementation review searched `deployment/`, `dev/` and `bundle.py` for
`config/dev.yaml`, `config.dev.yaml`, `component_defaults(` and `dev_settings(`:

| Reader/consumer | Responsibility |
| --- | --- |
| `render.component_defaults` / `merge_config` | Only effective layer assembly and merge implementation |
| `deploy.check_dev_shared_settings` | Reads the dependent's component dev layer to refuse shared keys before merging; does not merge |
| `deploy.dev_settings` | Catalog order, shared-key check and owner inheritance |
| `validation.validate_catalog` | Uses `dev_settings`, then shared read-only validation |
| `deploy.prepare_components` / `check_dev_components` | Same settings, manifest/DB checks, then dev output/materialization |
| `dev/dev.sh up` | Delegates to `./deploy prepare`; has no config reader of its own |
| `dev/demo-credentials.sh` (`DEMO_HOST`) | Uses `dev_settings` and preflight before provisioning |
| `bundle.generated_secret_guard` | Inspects all declaration layers independently, relative to dev state, protecting private inputs even if a later map replaces them |
| `deploy.init_config` | Calls `component_defaults` without dev mode; never reads the new layer |

`dev/build-images.sh` and `dev/pull-images.sh` read manifest images, not effective
dev settings. The acceptance renamed-product generator copies/renames the tracked
component dev declarations; it does not create another merge implementation.

## Local verification

- Focused config, file guard and bundle tests: 49 passed.
- Demo product suite: `python3 -B tests/run.py demo` — 64 passed.
- Acceptance harness: `python3 -B -m unittest discover -s acceptance -p 'test_*.py'`
  — 200 passed. Podman/systemd are stubbed.
- Isolated platform suite: 354 executed; 351 passed and three signing tests
  failed their environment prerequisite. The short-TMPDIR rerun had the same
  result. A direct `gpg-agent` probe confirmed `can't create socket: Operation
  not permitted`; this environment does not permit the required agent socket.
- Ruff lint/formatting, ShellCheck, `bash -n acceptance/remote.sh`, relative
  documentation links and `git diff --check` passed.
- Vermin reports minimum Python 3.6; this is static analysis, not execution on
  Python 3.6.
- Pyright: 0 errors; one environment warning for missing `requests` source in
  the existing smoke-test module.

Both isolated runs executed 354 tests: 351 passed; three signing tests failed
their prerequisite. The rerun used a shorter TMPDIR as tests/README.md advises;
that did not resolve the socket permission restriction confirmed by the probe.
Signing verification therefore remains blocked here; the platform suite is not
reported as wholly passing. The rerun command was:

```sh
TMPDIR=/workspace/scratch/0780781d7ca6/t python3 -B tests/run.py platform --isolate
```

An initial harness run started before the new files were staged and failed the
tracked-file inventory check; after staging, the complete 200-test run passed.
These environment/setup failures are not represented as successful runs.

## Understandability review

Successful dev flow: `dev_settings` reads the catalog in dependency order,
`check_dev_shared_settings` rejects conflicting local declarations,
`component_defaults` selects layers and `merge_config` produces effective values.
Validate uses these values without writes or host commands. Prepare passes them
through the existing manifest and database checks before writing
`build/dev/<id>/config.yaml`, retaining valid credentials, and materializing the
same values. The generated config is an output, never a merge input.

Failure/retry: an invalid local YAML/shared-key declaration stops both validate
and prepare before output, generation or host commands. A changed dev layer with
a missing password and an existing database volume is still refused before
writes. Restoring the original password permits a new prepare and retains its
bytes. The existing credential files remain authoritative; no new retry state
or transaction mechanism is introduced. Production pending-operation behavior
is unchanged.

Layer selection now uses an ordinary list plus an explicit dev-only extension.
One small check names the owner-inheritance rule; no second config model, merge
algorithm or framework was added. The public marker and fixed app names exist
only in demo declarations and the acceptance harness, not generic deployment
code. The affected ownership, validation and failure order are explicit.

## Real runtime checks still required

After committing this work, use the documented disposable lab prerequisites in
[README.md](README.md). These commands are provided, not executed here:

```sh
python3 acceptance/acceptance.py --run component-dev-app1-first --first-app app1 run
python3 acceptance/acceptance.py --run component-dev-app2-first --first-app app2 run
python3 acceptance/acceptance.py --run component-dev-shop --renamed-product run
```

DEV dev-up checks app1/orders renders and exposes `component-dev` in its actual
backend; app2/inventory has no marker, including an empty environment value.
PROD health checks require `defaults` in app1/orders and no marker in its sibling
when installed. Wrong rendered/runtime values, missing coverage and command
failures stop the step; only the single public key is inspected, and runtime
stdout/stderr are not included in failures. Help/owner-only installs require no
app marker. Existing persistence, restart, upgrade and sibling checks still run.
No claim is made about actual Podman, systemd, SELinux or fapolicyd results.
