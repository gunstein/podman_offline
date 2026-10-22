# Generated Secret values in init containers (backlog 61)

The operator reported an empty `APP_CONNECTIONSTRING` in an external Grate
migration image. This does not establish a renderer or Podman defect. No product
workaround has been added: focused product tests preserve the init-container
reference and produce the expected Secret bytes. The private image, entrypoint,
configuration and host version still need operator-side verification.

## Run the disposable offline scenario

Use the current checkout as a rootless user with a working user systemd manager,
Quadlet, Python 3/PyYAML on the host, tar/disk space for one image archive, and an
already available image with `python` on PATH and its standard library. The probe
needs no database, app source, private image, registry or new SELinux/fapolicyd
rules. Its default image is the already built demo backend; closed networks can
specify another image explicitly:

```sh
python3 -B acceptance/init_secret_test.py --image localhost/my-python-probe:available
```

This scenario targets the project's existing rootless OL9/Podman 5.8.2/systemd
Quadlet baseline. Other versions must be recorded and tested; their compatibility
is not established by unit tests. It explicitly uses
`io.podman.annotations.init.container.type: always`, an exited init container with
exit code zero, and a running ordinary container as a control. It does not claim
coverage of init type `once` or the organisation's Grate entrypoint.

Record `git rev-parse HEAD`, the command, printed Podman/systemd versions and the
host policy (`getenforce` and `systemctl is-active fapolicyd`) with each real run.
Record pass/fail output only; do not attach manifests, credentials, full inspect
output or connection strings. Run from a complete checkout; this new scenario
copies the current product code to a disposable fixture. Unlike the older
standalone Secret probe, it is not intended to be transferred as one file to PROD.

The scenario:

1. Creates a UUID-scoped minimal product with arbitrary component/resource names,
   a retained synthetic password, a full `SECRET_TEMPLATES` connection string and
   an init `env.valueFrom.secretKeyRef`. No `apps/` tree is involved.
2. Uses real `deploy prepare` with a component dev override, then `kube play`.
   Changes the public host input, rerenders and replaces the pod, retaining the
   password byte-for-byte.
3. Builds a real offline archive using a temporary localhost image alias, unpacks
   it elsewhere and deletes the entire source fixture. The copied release's own
   validation/materialization functions render from a separate persistent config.
   This exercises the production rendering path, not the full production installer;
   product tests separately exercise init-config/install from a relocated release.
4. Starts a disposable Quadlet, then changes persistent public config, rerenders
   and restarts it. A bare restart without rerendering does not apply config edits.
5. Requires both init and control processes to see a non-empty exact expected
   value. An independent test-only Secret supplies expected bytes; a SHA-256
   expectation embedded in the probe command is computed separately for each
   render, so stale env and stale mounted bytes cannot pass together. The hash
   carries no reusable credential; plaintext private values remain in Secrets.
   Each process logs only a public, fresh execution token or `PROBE-FAIL`.
6. Requires the init's own fresh log token and zero exit, not just inspect's env
   or the control's health. Missing/skipped/stale init, mismatch, nonzero exit or
   timeout fails. Nonrecursive rendering and generic empty-value policy are unchanged.

Only this run's temporary directory, pod, Secret-backed volumes, Quadlet and image
alias are removed, also after failure. Cleanup errors fail the run. It never
resets a database or removes original images, retained operator credentials or
unrelated pods/volumes. Diagnostics from subprocesses are captured and withheld.
The normal `database-runtime` and renamed-product lab flows invoke the probe;
no VM reset is performed by this standalone command.

## Diagnose the operator's container without displaying secrets

First keep the failing container for diagnosis and note the actual Podman version.
Use the exact YAML passed to Podman (`build/install.yaml` in dev, installed
`~/.config/containers/systemd/<product>-<component>.yaml` in production), and the
actual init-container name. Run this locally as its rootless owner, replacing the
four public identifiers below. It reports only presence, length and equality;
it captures inspect output privately and never prints raw diagnostics.

```sh
python3 - /path/to/install.yaml sts-migrations connection-string actual-init-container <<'PY'
import base64
import json
import subprocess
import sys
import yaml

try:
    path, secret_name, key, container = sys.argv[1:]
    with open(path) as stream:
        docs = list(yaml.safe_load_all(stream))
    secret = next((d for d in docs if d and d.get('kind') == 'Secret'
                   and d.get('metadata', {}).get('name') == secret_name), None)
    data = (secret or {}).get('data', {})
    expected = base64.b64decode(data[key], validate=True).decode() if key in data else None
    print('rendered key present:', expected is not None)
    print('rendered key length:', len(expected) if expected is not None else 0)
    refs = [e.get('valueFrom', {}).get('secretKeyRef')
            for d in docs if d and d.get('kind') == 'Pod'
            for c in d.get('spec', {}).get('initContainers', [])
            for e in c.get('env', []) if e.get('name') == 'APP_CONNECTIONSTRING']
    print('matching init reference:', any(r and r.get('name') == secret_name
          and r.get('key') == key for r in refs))
    result = subprocess.run(['podman', 'inspect', container], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, universal_newlines=True, timeout=30)
    if result.returncode:
        raise RuntimeError('inspect unavailable')
    row = json.loads(result.stdout)[0]
    values = [e.split('=', 1)[1] for e in row.get('Config', {}).get('Env', [])
              if e.startswith('APP_CONNECTIONSTRING=')]
    actual = values[0] if len(values) == 1 else None
    print('container env present:', actual is not None)
    print('container env length:', len(actual) if actual is not None else 0)
    print('container env matches nonempty rendered value:', bool(expected) and actual == expected)
    print('init exited successfully:', row.get('State', {}).get('Status') == 'exited'
          and row.get('State', {}).get('ExitCode') == 0)
except Exception:
    raise SystemExit('Diagnostic failed; private details withheld') from None
PY
```

Interpret the checks in order:

- Missing/empty rendered key: check the recipe, selected config layer and retained
  source file locally. Dev uses common/component defaults, global dev and component
  dev overrides; top-level maps are replaced. Production uses persistent config,
  not changed release defaults. Do not regenerate/delete retained passwords.
- Wrong reference: correct `secretKeyRef.name` and `.key` in the init declaration.
- Rendered value non-empty but created env absent/different: check the selected
  manifest, component and stale container. Rerender and use the supported
  replacement/install flow; merely restarting an old container does not apply new
  YAML. Run the disposable probe on that exact host version before attributing
  the difference to Podman.
- Matching inspect env but Grate still misses `--connstring`: inspect does not
  prove the executed process consumed it. Review the actual image entrypoint and
  effective `command`/`args` privately. Kubernetes `command` replaces ENTRYPOINT;
  argument arrays do not perform shell `$APP_CONNECTIONSTRING` expansion.
  Confirm that the entrypoint reads the expected environment name and forwards
  its value as the option's argument. If a shell is available, temporarily add
  `test -n "$APP_CONNECTIONSTRING" || exit 17` immediately before the existing
  migration invocation; never use `set -x`, `env`, or echo the value. Preserve the
  original migration command and do not run it again against a real database
  merely to diagnose variable presence. The synthetic probe checks the process
  environment without running migrations.

A passing probe narrows the problem to the private configuration/image/entrypoint;
it does not prove that private migration works. Capture the actual manifest
reference, input presence/length, host version and entrypoint behavior before
proposing a product fix.

## Evidence and understandability

Local product tests cover exact generated bytes, unchanged init references and
`always` annotation, wrong/missing key/Secret refusal before generation,
side-effect-free validation, dev override precedence, retained password bytes,
0600 YAML, and isolated production init-config/install/retry using retained config.
Harness tests exercise the probe's actual Python check and reject missing, empty,
wrong and stale values (including equally stale env/file), failed/skipped init and
timeout despite a healthy control. A stubbed host flow runs real prepare, bundle,
relocation and release rendering; it proves orchestration, not Podman delivery.

Success: dev settings or persistent config -> `validate_component` ->
`render.materialize` -> generated Secret and preserved init reference -> private
runtime YAML -> kube/Quadlet -> init's exact nonempty process assertion -> fresh
success token and zero exit -> control assertion. Failure: a mismatched init value
exits 17 or lacks its new token; `verify` refuses completion even if the control
runs. Cleanup attempts the owned resources and retry starts a fresh isolated run;
no new product retry state is introduced. Production install retry remains covered
by existing lifecycle tests and the new retained-config init fixture.

Real Podman/systemd/SELinux/fapolicyd verification for item 61 is **pending**.
The old item 41 lab results cover its ordinary-container probe only. Record new
runtime results here after executing the new scenario; Python 3.6 execution and
the organisation's private image remain separate verification gaps.


### Local verification (2026-10-22)

Baseline `735b39d` plus the implementation delivered in this change, Python 3.12.14:

| Check | Result |
| --- | --- |
| `PYTHONPATH=tests python3 -B -m unittest platform_tests.test_secret_templates -q` | 30 passed, also in a freshly exported platform-only copy without apps/demo sources |
| `python3 -B tests/run.py platform --isolate` | 384 run: 380 passed; three gpg-agent fixture failures and one unavailable `/proc/self/fd/0` host-delivery check |
| `python3 -B -m unittest discover -s acceptance -p 'test_*.py'` | 230 passed, including eight new init-probe harness tests |
| Ruff lint/format, changed Python files | Passed; existing tests config/ignore conventions retained |
| Pyright, changed Python files | 0 errors, 0 warnings |
| Vermin, new runtime probe and modified product tests | Minimum Python 3.6; acceptance-harness tests use the existing modern unittest syntax |
| `bash -n acceptance/remote.sh`; `git diff --check`; new documentation links | Passed |
| Real Podman, user systemd, SELinux/fapolicyd | Not available; not run |

The platform failures are in unchanged prerequisite-dependent signing/host tests;
no exclusions or production policy changes were made to produce a green suite.
Static compatibility does not replace Python 3.6 execution. The understandability
trace above covers authoritative inputs, pure validation, private rendering,
process assertions, failure cleanup and retained-state retry without new product
state or a second Secret renderer.
