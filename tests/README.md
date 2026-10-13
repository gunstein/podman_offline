# Unit tests

`test_deploy.py` and `test_bundle.py` use only the standard library
and PyYAML. `test_certificates.py` also uses bash and OpenSSL when they exist,
with all key material in a temporary directory. All paths point into `TemporaryDirectory`; Podman/systemd calls and the user check
are stubbed. No network, Podman, systemd or root is required. The bundle tests write
and read real tar archives and verify every SHA-256 line, but stub the image save.

```sh
python3 -m unittest discover -s tests
.venv54/bin/python -m unittest discover -s tests
ruff check deploy.py bundle.py tests/
ruff format --check deploy.py bundle.py tests/
pyright deploy.py bundle.py tests/
vermin -t=3.6- deploy.py bundle.py tests/
```

For PyYAML 5.4.1, use a Python version it can be built on (tested with 3.11):

```sh
python3.11 -m venv .venv54
.venv54/bin/pip install setuptools wheel 'cython<3'
.venv54/bin/pip install --no-build-isolation pyyaml==5.4.1
```

Lint/type/vermin are development tools, not new runtime dependencies.
The tests use Python 3.6-compatible syntax and standard library APIs.

## Images from the manifests

101 tests pass with PyYAML 6.0.3 (Python 3.14.4) and 5.4.1 (Python 3.11.17).
The image tests cover Pod/Deployment, init containers, several files/documents,
flow maps, duplicates, full names and expected validation errors. The bundle tests
check one sorted multi-image save, the name list, tar content and checksums.
The installer tests check the render/load/exists order, rendered names,
a missing archive/image and that existing Quadlet files are kept on check failures.
The prepare tests still run entirely without Podman calls.

A real save/load was verified on 2026-10-12 with **Podman 5.7.0, rootless**.
Three existing names were saved with `podman save -m -o images.tar ...` and loaded
with `podman load -i images.tar` into an empty, temporary VFS image store
(`--root`, `--runroot`, `--storage-driver vfs`). All three
`podman image exists` checks returned 0. `podman images` after the load showed:

```text
docker.io/library/nginx:1.28-alpine dc73b49f5124
localhost/offline-example:1 30ecbe150909
docker.io/library/busybox:1.37.0 30ecbe150909
```

Full names and tags were preserved, including two names for the same image ID.
The test store was removed afterwards. This was a separate save/load test with small
test images; the full product bundle and the prod Quadlet installation were not run
as part of that change.

The regression tests cover name collisions between Secret/PVC/ConfigMap,
validation without writing archives, keeping old archives on load/exists failures,
the network Quadlet and rejection of duplicate manifest keys during the build.
Real systemd, reboot and upgrade are checked by the [acceptance test](../acceptance/README.md).

## Rootless prod

The install tests reject root before rendering/commands, check the user-database-based
Quadlet/archive paths, systemctl --user in the right order, the runtime fallback and
the error for a missing runtime directory, plus file permissions. No product files
are written to the system instance's Quadlet directory. The bundle test includes prepare-host.
The acceptance harness's local tests also check that the sudo commands change
the working directory before install/Podman, without root, Podman or network.

Persistent config is tested separately from the release config: install uses the home from the user database, prepare
uses the repo root, and relative secret/volume paths follow the config directory.
The certificate tests check --root, the default root, file modes, the host name
and that a repeated generation is rejected without changing any files.

The prod paths are tested with a mock of pwd.getpwuid, also with a wrong HOME. Install
rejects a mismatch before rendering and commands; an absent HOME uses pw_dir.

The host script tests check the required port, rejection of an old equivalence,
the idempotent rule and that recursive restorecon always excludes storage.
The runtime tests reject every XDG_RUNTIME_DIR value other than /run/user/<euid>.
The bundle test includes the two prod scripts and excludes the dev/ directory.

Manifest errors are tested with the file path and image errors with the container name. A separate
test renders the real product manifests with the example config and dummy files,
without Podman, and checks resources and image names.

`test_health.py` requires one exec liveness probe in every real app manifest,
with initialDelay 90, period 30, timeout 5 and failureThreshold 3. Init containers
have no probe. The backend's /livez and its authentication guard are tested in isolation, without
importing the app, a database or the app's dependencies.

Manifest validation tests cover defined and missing ConfigMaps in all three
reference forms, pod-local mounts, and required Never pull policies on ordinary
and init containers. Nested Deployment pod specs use the same validation.

Generated-secret tests verify exclusive creation, 32 alphanumeric characters,
0600/0700 modes, reuse by prepare and install, empty-file errors, path confinement
including symlinks, concurrent creation and output without secret values.
