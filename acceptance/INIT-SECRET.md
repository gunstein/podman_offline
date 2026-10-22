# Generated Secret values in init containers (backlog 61)

The operator reported an empty `APP_CONNECTIONSTRING` in an external Grate
migration image. This does not establish a renderer or Podman defect. No product
workaround has been added: focused product tests preserve the init-container
reference and produce the expected Secret bytes. The private image, entrypoint,
configuration and host version still need operator-side verification.

## Run the disposable offline scenario

Use the current checkout as a rootless user with a working user systemd manager,
Quadlet, Python 3/PyYAML on the host, tar/disk space for one image archive, and an
already available image with `python` on PATH and its standard library. The home
filesystem needs room for the image archive, compressed bundle and extracted
release simultaneously. The private disposable directory is created under the
rootless user's home, not the usually small `XDG_RUNTIME_DIR` tmpfs. The probe
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
unrelated pods/volumes. Raw subprocess output and argv are captured and withheld.
The probe prints fixed START/PASS/FAIL phase labels for bundle relocation, release
rendering, Quadlet registration/start, process verification and cleanup. Failures
report numeric command exit status, timeout or OS errno without private values.
Cleanup failures are reported separately and cannot replace the primary failure;
a cleanup failure on its own still fails the probe.
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

Real Podman/Quadlet verification for item 61 **passed** in the normal and renamed
lab runs at `52f28e4`; see [completed verification below](#completed-real-lab-verification-2026-10-22).
The old item 41 lab results cover its ordinary-container probe only. Python 3.6
execution and the organisation's private image remain separate verification gaps.

The following local and failed-run entries retain their original results and
then-current limitations. The completed runs below supersede their pending status.


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

### Partial lab evidence and diagnostic correction (2026-10-22)

Run `init-secret-app1-20261022-170953` at `ecceaac` passed the ordinary Secret
probe (direct kube play and Quadlet, including updates) and both generated-Secret
init/control direct kube play checks. It failed before the first relocated
Quadlet PASS. The old catch-all message discarded the failing operation, so this
log does not establish the runtime cause. The tarfile warning alone does not
establish extraction failure either. This change repairs failure reporting and
preserves the original error when cleanup also fails; it does not claim to fix
an unobserved Podman or renderer defect. At that point a new lab run was required to identify
or rule out the remaining failure; the subsequent records below resolve it. No production policy or Secret semantics
were changed.

Verification of this diagnostic correction: all 233 acceptance-harness tests
passed, including real prepare/bundle/relocated-render orchestration with a
stubbed host and three new failure-reporting regressions. Ruff lint/format and
`git diff --check` passed. Understandability review traced successful phase
completion and primary failure followed by failed cleanup: fixed phase labels
identify the boundary, raw output stays private, owned cleanup continues and
an incomplete cleanup cannot yield success. Product code is unchanged; real
Podman/systemd verification was pending at that point; see the completed runs below.

### Runtime-directory space fix (2026-10-22)

The follow-up run `init-secret-fix-20261022-173957` at `1eb713f` isolated the
failure to bundle relocation: `OS error errno=28` (ENOSPC). Direct init/control
checks and owned cleanup passed. The fixture incorrectly stored the source,
image archive, compressed bundle and extracted release in `XDG_RUNTIME_DIR`.
Move that private temporary tree under the user's home; keep `XDG_RUNTIME_DIR`
for rootless Podman/systemd. The full-flow regression now uses distinct home and
runtime paths, exercises real bundling and release rendering, requires the
runtime directory to remain empty and verifies cleanup of the home fixture.
This fixes the test's storage location; it does not relax process assertions or
change production Secret behavior. Both lab reruns below subsequently passed.

### Completed real lab verification (2026-10-22)

Both runs below report **CLEAN PASS** from a clean checkout of
`52f28e47e51c62f25e2c81d281c0837b2395d110`:

| Run | Scenario | Init-probe evidence |
| --- | --- | --- |
| `init-secret-space-20261022-175002` | Normal app1-first lifecycle | `logs/03-database-runtime.log` |
| `init-secret-renamed-20261022-181444` | Renamed product | `logs/03-renamed-generate.log` |

Reports and full logs are retained outside Git at
`~/podman-offline-acceptance-runs/<run>/REPORT.md`, `EVIDENCE.md` and the log
paths above. The report revision metadata and probe PASS lines were independently
read when recording these results; no private manifests or credentials are copied
into Git.
Both logs contain PASS for generated-Secret init/control initial kube play,
replacement, relocated-release Quadlet initial start, rerender/restart and
complete owned-resource cleanup. These are actual process assertions, not just
successful rendering or ordinary-container health. The reports also record
successful remaining lifecycle steps and the final PROD audit.

The recorded baseline is Oracle Linux 9.8, Podman 5.8.2, systemd 252 and PyYAML
5.4.1. SELinux was Enforcing on DEV and PROD. The init probe ran on DEV, where
fapolicyd was inactive; PROD lifecycle/audit ran with fapolicyd active. Therefore
these runs establish the init probe's Podman/Quadlet behavior, but do not establish
that this disposable probe itself runs under active fapolicyd.

This closes item 61's synthetic generated-Secret delivery verification gap and
supersedes the two earlier failed attempts. It does not verify the organisation's
private Grate image/entrypoint, other Podman versions or init type `once`.
These results predate item 62's structural-validation changes and must not be
reported as a real runtime run of that later branch change. No tests were rerun
when recording this documentation correction.
