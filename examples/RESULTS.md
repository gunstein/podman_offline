# Test results, 2026-10-12

Environment: Podman **5.7.0**, **rootless** (`podman info` reported `true`),
BusyBox **1.37.0**, tagged locally as `localhost/offline-example:1`.
No rootful installation, systemd operations or reboot were performed.

| Run | Result |
| --- | --- |
| `./examples/run.sh basic` | Exit 0: environment, HTTP response and the exact loopback port binding matched |
| `./examples/run.sh secrets` | Exit 0: SHA-256 matched also with `items`; the same file name, top-level renaming and leaving out unselected keys worked |
| `./examples/run.sh volumes` | Exit 0: content, owners/permissions, app data after down/play and overwriting from a new archive matched |
| `./examples/run.sh init-containers` | Exit 0: the main container observed `first`, then `second` |
| `./examples/run.sh manifest-defined` | Exit 0: PVC and Secret/stringData/secretKeyRef worked |
| `./examples/run.sh failures` | Exit 0: all four expected prepare errors were checked; no YAML/archives were written |

**Deviation from a completely clean Podman run:** On `kube down` Podman wrote
`rootless netns: kill network process: permission denied` under an
`Error: stopping container ... network` message. Podman still returned 0.
This happened in the five positive examples, also between the volume test's two plays.
All functional checks passed. After the run, separate listings showed none
of the tests' containers, pods, secrets or volumes. The network process's
life cycle is not verified beyond this, and the cause has not been determined.
The deviation must be investigated if it repeats on the target VM.

The first version of the runner left Secret mount volumes behind. The runner was fixed
to remove these named volumes as well, the first test volumes were removed,
and all six examples were run again with the results in the table.
The apps' PID 1 handles SIGTERM to avoid an unnecessary ten-second stop timeout.

Follow-up with `secret.items`: the example keeps one mount without `items`, uses
an explicit `key: binary.bin` / `path: binary.bin` for the binary file and has a third
Secret that selects only `message.txt` under the name `renamed.txt`. The file hashes matched,
and both the original file name and the left-out key `second.txt` were missing
in the filtered mount. The extended test returned 0 on rootless Podman 5.7.0.

A trial with `items.path: nested/renamed.txt` **failed** with exit 125:
`name "nested/renamed.txt" must not contain path separator`. Subdirectories in
`items.path` are therefore not supported in this trial. It is a Podman limitation;
`deploy prepare` rendered the manifest without errors. The normal example run
therefore uses top-level renaming. Both runs cleaned up their own resources;
the successful run still had the network deviation described above.

## Unit tests and quality checks

- 51 new tests: 42 deploy tests and 9 bundle tests, with further variants
  in `subTest`.
- Python 3.14.4 / PyYAML 6.0.3: all 51 pass.
- Python 3.11.17 / PyYAML 5.4.1 (`.venv54`): all 51 pass.
- Ruff 0.17.0: lint and format checks clean.
- Pyright 1.1.414: 0 errors and 0 warnings.
- Vermin 1.8.0: minimum Python 3.6, target `3.6-` accepted.
- `bash -n examples/run.sh`: accepted.

The 21 original tests mentioned and several original files did not exist in the workspace.
They could therefore not be read or run. New tests are in separate files;
no original tests were replaced. The tests on 5.4.1/6.x and the static
compatibility check are not the same as an actual run on Python 3.6.

## The Python code and open observations

During this example run, `deploy.py` and `bundle.py` were unchanged. None of the implemented tests or
Podman examples revealed a Python bug that needed fixing, so there is
no bug-fix commit.

The following limitations were observed by reading, without changing existing
behavior:

- The link check validates Secret/PVC names, not whether `secretKeyRef.key` exists
  or the full Kubernetes/Podman schema. The real examples complement this.
- File archives are written only after successful validation, but writing several
  archives is not an atomic transaction, for example on disk errors.
- A volume import overwrites uploaded files at the next play. This is intended
  behavior; app data that must be kept should have other file names or its own volume.

Production start-up and an actual reboot must be checked manually with the
[VM checklist](VM-CHECKLIST.md) and a complete bundle.

Later, the image handling was changed to structural YAML reading and one shared
image archive. The current build and installation flow is described in the
[README](../README.md#offline-bundle-and-rootless-quadlet).
