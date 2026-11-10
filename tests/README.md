# Platform and demo test groups (backlog 43)

Use the standard-library unittest runner through these explicit entry points:

```sh
python3 -B tests/run.py platform
python3 -B tests/run.py demo
python3 -B tests/run.py all
python3 -B tests/run.py platform --isolate
```

`platform_tests/` exercises deployment, bundles, validation, templates, retry,
database safety and external images with synthetic declarations in `fixtures/`.
It does not read `apps/` or the shipped demo component declarations.
The synthetic `fixtures/catalog` keeps `platform`, `identity`, `app1`, `app2`
and `help` as fixture IDs; that separation alone does not prove arbitrary names.
The renamed-product and minimal-worker fixtures provide that additional evidence.
`demo_tests/` contains application-source assertions, shipped manifests, demo
builds, demo credential recipes and their integration assumptions. Organisations
using other images run their own integration tests in addition to the platform
group. `helpers/` contains reusable fixtures without test methods or imports from
test modules. Historical module names in the coverage notes below refer to files
now located in one of these groups; mixed modules were split.

The offline runtime prerequisites are Python 3.6+, PyYAML, bash, standard host
utilities, OpenSSL, gpg/gpgv/gpgconf and a writable temporary directory supporting
gpg-agent sockets (set a short `TMPDIR` if needed). Missing prerequisites fail
clearly; tests do not silently disappear or skip because demo files are absent.
The temporary directory must also allow execution: tests run wrappers, Podman/
OpenSSL stubs and copied `deploy.sh` scripts from it. On hosts where `/tmp` is
mounted `noexec`, this shows up as `PermissionError`, a failing OpenSSL wrapper
test or a wrong-error failure in the failures example, not as a prerequisite
message. Use an executable directory instead:

```sh
mkdir -p ~/t && TMPDIR=~/t python3 -B tests/run.py platform
```

Run the suite from one consistent copy of a single commit. A copy that mixes
older `deployment/` files with newer tests can fail in confusing ways.
A venv, network, Podman, systemd and root are not required. Ruff, pyright, vermin
and ShellCheck are contributor checks, not offline runtime prerequisites.

To transfer a self-contained platform suite to an offline organisation:

```sh
python3 -B tests/run.py platform --export /path/to/new/platform-suite
# Transfer that whole directory, with executable permissions preserved.
cd /path/to/new/platform-suite
python3 -B tests/run.py platform
```

The export contains the runner, platform tests/helpers/declarative fixtures,
`deployment/`, bundle/entry-point scripts, the production manual (its bootstrap
block is executable regression input), Quadlet/examples and the three dev
helpers tested by the platform group. Its root catalog/components/version files
come from synthetic fixtures. It contains neither `apps/`, `demo_tests/` nor the
shipped demo component tree. `--isolate` builds and runs the same copy temporarily;
`--list` prints exact test IDs for inventory comparison. Export refuses an
existing destination. The renamed-product generator uses tracked files: stage
new helpers before running its regression tests. Acceptance's `03-unit` step (normal scenario) runs
`all`; acceptance-harness tests remain a separate command below and do not prove
real Podman/systemd behaviour. No hosted CI is added.

## Contributor checks

Run from the repository root with the contributor tools installed separately:

```sh
ruff check deployment tests acceptance tools rpms.py
ruff format --check deployment tests tools rpms.py
pyright deployment/ bundle.py rpms.py tools/ tests/ acceptance/ dev/smoke-test.py
vermin -t=3.6- deployment/ bundle.py rpms.py tools/ tests/ acceptance/prepare_host_test.py
shellcheck deploy.sh build-bundle.sh dev/*.sh scripts/*.sh acceptance/remote.sh
```

Report existing lint findings separately from regressions in a change. These
checks do not add runtime dependencies or establish real container behavior.

## Acceptance-harness tests

```sh
cd acceptance
python3 -B -m unittest discover -s . -p 'test_*.py'
```

These local tests exercise scenario wiring, checks and failure reporting with
simulated guest commands. Real Podman/systemd runs are separate: see
[the acceptance instructions](../acceptance/README.md) and
[latest lab results](../acceptance/RESULTS.md). Older evidence remains in Git
history and is not verification of later code.

## Coverage and maintenance

Use `python3 -B tests/run.py all --list` for the current inventory rather than a
stored test count. Focused tests can be run with, for example:

```sh
PYTHONPATH=tests python3 -B -m unittest platform_tests.test_mounts
```

The platform suite covers config precedence and initialization, declarative
catalogs, renamed/minimal products, bundles and signatures, credential retention,
ENVIRONMENT and MOUNTS, environment overrides (`test_environment_overrides.py`,
backlog 84) and the components of an environment
(`test_environment_components.py`, backlog 85), source/key validation, database preflight, installed
status, scoped install/uninstall and fresh-process retry. Backlog 69's RPM
delivery has `test_rpms.py` and `test_admin.py` (real `rpmbuild`/`rpm -qp` with a
fake host; skipped without `rpmbuild`) and `test_runtime.py` (the runtime
command against a fake `deploy.sh`). Demo tests additionally
check application behavior and the shipped declarations. Keep assertions about
expected paths, resource names and bytes independent of production helpers.

A supported executable temporary directory and working GPG agent are required
for the bundle signature tests, and `rpmbuild` for the RPM and administrator
tests (skipped without it). Journal tests also need Unix sockets. Report
sandbox restrictions explicitly rather than treating blocked tests as passes. Real rootless, SELinux and fapolicyd behavior belongs to the
lab, not mocked local tests.

For new behavior, follow [the review guide](../docs/REVIEW_GUIDE.md), including
failure/retry coverage and the distinction between product tests, harness tests
and real runtime evidence. Test descriptions for removed product formats must
not become examples of current configuration.
