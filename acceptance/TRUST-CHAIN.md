# CA trust chain for a backend (backlog 70)

Status: implemented as a documented pattern with local regression coverage
(2026-10-26). `subPath` and sign-in through the chain work in dev with Podman
4.9.3 through backlog 71's `app3`; **the lab check on Podman 5.8.2 (OL9,
SELinux Enforcing, rootless) is pending.** No change to
`deployment/`; the pattern is in
[COMPONENTS.md](../docs/COMPONENTS.md#trusting-the-environments-ca-in-a-backend).

## Local evidence

`tests/platform_tests/test_trust_chain.py` uses a synthetic product (component
`billing`, no demo names) through the real `validate` and `prepare`:

- one `SECRET_FILES` source renders one Secret with both keys, and the Pod keeps
  both single-file mounts (`subPath`, `mountPath`, `readOnly`) unchanged;
- a Secret named after the product (`myproduct-ingress-trust-chain`) is refused
  by the component prefix rule before any output is written;
- a missing chain file is named before any output is written;
- `validate` reads no chain file contents.

Manifest validation does not restrict `volumeMounts` keys, so `subPath` passes
unchanged; whether Podman honours it is the lab check below.

## Lab check: `subPath` with a Secret volume (pending)

On a lab VM as an ordinary user, with a local image that has `/etc/ssl/certs`
(for example the proxy's `docker.io/library/nginx:1.28-alpine`):

```sh
podman --version
cat > /tmp/subpath.yaml <<'YAML'
apiVersion: v1
kind: Secret
metadata:
  name: subpath-test
data:
  root.crt: dGVzdC1yb290
  ca.crt: dGVzdC1jYQ==
---
apiVersion: v1
kind: Pod
metadata:
  name: subpath-test
spec:
  restartPolicy: Never
  containers:
  - name: c
    image: docker.io/library/nginx:1.28-alpine
    imagePullPolicy: Never
    command: ["sh", "-c", "cat /etc/ssl/certs/myproduct-root.pem; echo; cat /etc/ssl/certs/myproduct-ca.pem; echo; ls /etc/ssl/certs | wc -l"]
    volumeMounts:
    - {name: v, mountPath: /etc/ssl/certs/myproduct-root.pem, subPath: root.crt, readOnly: true}
    - {name: v, mountPath: /etc/ssl/certs/myproduct-ca.pem, subPath: ca.crt, readOnly: true}
  volumes:
  - name: v
    secret:
      secretName: subpath-test
YAML
podman kube play /tmp/subpath.yaml
podman logs subpath-test-c
podman kube down /tmp/subpath.yaml
```

Pass: the log shows `test-root`, `test-ca` and a file count above 2 (the image's
own certificates are still present). Record the Podman version and the output
here. If `subPath` fails, stop and decide an alternative with the product owner
(backlog 70, task 4).

## Dev evidence through app3 (2026-10-26)

Podman 4.9.3, rootful, in an Ubuntu 24.04 container without SELinux or
systemd; real `podman kube play` of the whole demo. In `app3-whoami-backend`
both files appear at `/etc/ssl/certs/myproduct-{root,ca}.pem` with the dev CA's
bytes, beside the image's own 297 files (299 entries). The .NET backend fetched
discovery, keys, token and userinfo through the public origin and signed in;
with an unrelated CA in both files it failed with `PartialChain`. Details and
commands: [backlog 71 verification](WHOAMI-DOTNET.md). This does not replace
the lab check above (Podman version, SELinux labels on single-file mounts).

## End to end

Dev: passed through backlog 71's app (above). Pending: the lab, and later the
real backend. Only the single-level demo CA is exercised.
