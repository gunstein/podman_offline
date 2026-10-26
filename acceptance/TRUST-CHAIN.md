# CA trust chain for a backend (backlog 70)

Status: implemented and lab verified (2026-10-26) at
`45fdb17e8d7e6a4df745ee846d925851557d8794`. Rootless Podman 5.8.2 on OL9.8
with SELinux Enforcing passed the Secret `subPath` check and app3's public
HTTPS sign-in/negative control. No change to `deployment/`; the pattern is in
[COMPONENTS.md](../docs/COMPONENTS.md#trusting-the-environments-ca-in-a-backend).
Earlier Podman 4.9.3 results below remain separate dev evidence.

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

## Lab check: `subPath` with a Secret volume

The newer acceptance scenario `--whoami` (not run in this verification;
step `07-whoami-chain-mounts`) implements this
check in the installed app3 backend under the real layout, SELinux and
fapolicyd, and its final audit step rejects any AVC denial. The standalone
recipe below isolates the Podman behaviour if that step fails.

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

## Completed lab verification (2026-10-26)

Tested commit: `45fdb17e8d7e6a4df745ee846d925851557d8794`, branch
`claude/sweet-fermat-08ibq2`. The recipe above ran **before the matrix or app3
installation**, on authorized DEV VM 107 (`192.168.0.102`), as ordinary user
`gunstein` (UID 1000), rootless, Oracle Linux Server 9.8. Actual output:

```text
podman version 5.8.2
Enforcing
test-root
test-ca
299
```

**Confirmed:** both single-file mounts work and the image's other CA entries
remain visible. Container exit status was 0. Its process label was
`system_u:system_r:container_t:s0:c137,c477`, and its mount label was
`system_u:object_r:container_file_t:s0:c137,c477`. The image was already local
and `imagePullPolicy: Never` was retained. The only recipe adaptations were a
unique `/tmp/subpath-45fdb17-lab.yaml` filename (the original path already
existed), a two-second wait before reading the exited container's logs, and
exit/label inspection. `kube down` removed the test pod and Secret; no existing
pod, Secret or environment was reset for this probe.

**Confirmed end to end:** app3 installed from its signed offline bundle on PROD
VM 108 (`192.168.0.108`) as runtime user `myproduct-ops` (UID 1001), Podman
5.8.2, OL9.8, SELinux Enforcing, Quadlet/user systemd. Both mounted files were
byte-compared with that environment's CA, without displaying certificate data;
`/etc/ssl/certs` contained 299 entries. Unlike dev, real SELinux labels were
present on both files:

```text
unconfined_u:object_r:container_file_t:s0
```

The backend process had `container_t` with an MCS category pair; its
`MountLabel` had `container_file_t` with the same pair. The actual Secret files
had the shared `s0` label above, not that category pair. Reading the files and
.NET HTTPS trust both worked under Enforcing; no manual relabel was needed.

An unrelated CA in **both** files, followed by install, produced HTTP 500 at
`/app3/auth/login`. Bounded user-journal excerpt:

```text
The remote certificate is invalid because of errors in the certificate chain: PartialChain
```

The matrix baseline initially lacked a readable persistent user journal. The
existing `scripts/release.py` `prepare_persistent_journal()` helper was run as
root on this disposable PROD VM; after reinstall, the runtime user's
`journalctl --user -u myproduct-app3.service` supplied the excerpt. This was a
lab prerequisite repair, not a deployment change or a pass for the unmodified
baseline's journal access. Restoring the environment CA and reinstalling
restored all four smoke PASS lines. Internal variant (b) also passed with the
unrelated CA; the correct CA and public-HTTPS config were restored afterward.
See [all six conversion points and lab results](WHOAMI-DOTNET.md#completed-lab-verification-2026-10-26).

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

Dev and lab: passed through backlog 71's app (separate evidence above).
Open: the organisation's real backend and a root plus issuing-CA chain. Only
the single-level demo CA is exercised; no app3 reboot was tested.
