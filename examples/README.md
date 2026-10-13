# Podman examples

Run from the repo root. Python 3.6+, PyYAML, Bash, Podman and `sha256sum`
must be available; `basic` also needs `curl`. Run as a normal user for rootless.
The examples use `prepare`, not the prod installation or systemd.

## Setup on a machine with network

```sh
podman pull docker.io/library/busybox:1.37.0
podman tag docker.io/library/busybox:1.37.0 localhost/offline-example:1
podman image exists localhost/offline-example:1
```

To use an Artifactory mirror, replace the source with its fully qualified BusyBox
image and tag that image as `localhost/offline-example:1`. Log in as the dev user
and configure its registry CA before pulling; keep TLS verification enabled.
The acceptance test seeds a temporary TLS registry on VM-1, proves a fresh
download from it, and uses that downloaded image for these examples.

All containers, including the init containers, use this local name and
`imagePullPolicy: Never`. Podman may also need its infra/pause image
on the first run, depending on version and local configuration. Do the first
trial run while the machine has network. The examples do not change the product's manifests.
To move the test image to a machine without network you can use `podman save` and
`podman load`; this is separate from the product bundle.

## Running

```sh
./examples/run.sh basic
./examples/run.sh secrets
./examples/run.sh volumes
./examples/run.sh init-containers
./examples/run.sh manifest-defined
./examples/run.sh failures
```

`basic` uses HTTP on `127.0.0.1:18080`. Override it when needed:

```sh
EXAMPLE_PORT=18081 ./examples/run.sh basic
```

| Example | Checks |
| --- | --- |
| [basic](basic/README.md) | ConfigMap/envFrom, types in placeholders, HTTP and port binding |
| [secrets](secrets/README.md) | Several ids, binary bytes, SHA-256 and selection/renaming with `items` |
| [volumes](volumes/README.md) | File trees, owners/permissions, persistence and a new import |
| [init-containers](init-containers/README.md) | Two init containers in order before the app |
| [manifest-defined](manifest-defined/README.md) | Manifest-defined PVC and Secret/stringData/secretKeyRef |
| [failures](failures/README.md) | Four expected validation errors, without Podman |

The script copies `deploy`, `deploy.py`, the example's
config, manifests and any files to a private, temporary directory.
There the marker `example-run` is replaced with a unique name, and `POD_NAME` is added
to the config. The originals are not changed. Binary data and the large negative
test file are generated only in the temporary area; no keys or certificates are needed.

Then `./deploy prepare`, `podman kube play --replace` and explicit
checks with `podman exec` and possibly `curl` run. Failures give a non-zero exit.
The exit trap runs `podman kube down` and removes only this run's PVC volumes,
Secret volumes and any remaining Secrets. The volume test keeps the volume
between its two runs and removes it only at the final cleanup.
The test image is kept for the next run. SIGKILL or a power loss can interrupt the trap.

See the [test results](RESULTS.md) and the [manual VM checklist](VM-CHECKLIST.md).
Podman support varies between versions; run the examples on the same version
as in the target network. The fields are described in
[Podman's kube play documentation](https://docs.podman.io/en/v5.7.0/markdown/podman-kube-play.1.html).
