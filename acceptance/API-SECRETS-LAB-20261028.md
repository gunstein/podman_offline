# API secret lab evidence (2026-10-28)

Tested source: `fd99d319658391ca6eca1f0f9020137d627d8738` on `claude/compassionate-gauss-8pyugq`.

This is a sanitized supplement to [the lab report](WHOAMI-DOTNET.md#backlog-72-api-secret-lab-verification-2026-10-28). Full private artifacts remain under `~/podman-offline-acceptance-runs/<run-id>/`; raw logs, secrets and sessions are not committed.

| Run ID | Result | Steps | SHA-256 of record.jsonl |
| --- | --- | ---: | --- |
| `api72-fd99d31-build` | NOT CLEAN (unsupported DEV Python 3.9 harness suite) | 6/7 | `d0f5411d0beef64edfb2807c6b0d2f9724101ceb4d53d82852a1ad7a20b561ec` |
| `whoami-fd99d31` | CLEAN PASS | 46/46 | `cdf67f85aee8a877c90b88fbef81ff78b0764ebc2bbcb1332781d25fb8647af4` |
| `api72-fd99d31-lifecycle` | CLEAN PASS | 10/10 | `ce38b32fb13debaa82baa5cf08d97d15a02d5374df2c2adc96722d2b6fe409eb` |
| `normal-fd99d31` | CLEAN PASS | 125/125 | `c60286fdddcb95a80d982603f8884b3a5c62e733d7f7afdf8c10f8bb89ac579f` |
| `api72-fd99d31-uninstall` | CLEAN PASS | 13/13 | `c6f5de32d75c547f72de647a77d548abc54eb251c3ef694d297a2596c45d07ab` |

The separate controller harness command passed 358 tests on Python 3.14.4. Its captured output SHA-256 is `3a6a90e7df2f00f5cdabf845a091f7820c61b9b5bb9c3d3233566b3ad3bb1b5a`.

## Stored and running values

The source file is `/var/lib/myproduct/state/app3/credentials/api/value`. Expected registration bytes were calculated as `base64.b64encode(hashlib.sha256(raw).digest())`. `state/apis/app3/value` and the base64-decoded owner YAML key both matched those bytes. Neither value was printed.

The exact `podman exec <container> printenv <key> | sha256sum` pipelines were run with `pipefail` inside the runtime account. `printenv` adds one newline: environment pipeline hashes were compared with the expected source bytes **plus that newline**, and the captured bytes were also checked for exact equality. Identity holds the Base64(SHA-256) form; app3 holds the raw value. Their hashes are therefore intentionally different.

| SHA-256 comparison | Initial focused install | After single-install rotation |
| --- | --- | --- |
| Raw source file | `dd608cccbed74370f56eec90383b68510394cca6e0323f9f7dc37380527c67c3` | `e2dc7c756e917395daa8fea493160681a8418166c924cfbe336d5e9e702ab1c0` |
| Registered Base64(SHA-256) bytes | `f37ff8aa12205b116a15dcce433eb3f0a97d9b0a6d8724772c85916ad3087170` | `406e124912a99e39aeb0200a6b9f9ba39923a7e4253ad8ccf00c98ae1c073900` |
| Owner YAML key, base64-decoded | `f37ff8aa12205b116a15dcce433eb3f0a97d9b0a6d8724772c85916ad3087170` | `406e124912a99e39aeb0200a6b9f9ba39923a7e4253ad8ccf00c98ae1c073900` |
| Identity printenv (equals expected + newline) | `1c9aeebbc4721a2173506c0f1a5bed61cf87e0f2987a8e9b4b38b05049a3e6a5` | `08e9127e8357ef8b156cdcb9962293cfef920e69208bfb1b5a40a0d29cafa73f` |
| App3 printenv (equals raw + newline) | `e2a845067ae4c0b51025976ad791265b8109350c152550b3360c37c9641cc523` | `a69f3ad1e7715a0db4a5d1820c7395b3d9a30ef41f4fc8fb4931142f84ba853e` |

`state/apis` and `state/apis/app3` were 0700; `index` and `value` were 0600. Index bytes were exactly `0`. All comparisons were repeated after rotation and after restoring the newline control.

## Rotation with other applications present

The post-normal probe checked service invocation IDs for all `myproduct-*.service` units before/after one app3 install. Only app3 and Identity changed. It also checked these systemd monotonic microsecond timestamps:

| Event | Timestamp |
| --- | ---: |
| App3 main process started | 675432434 |
| App3 became active | 675432475 |
| Identity main process started | 688117285 |
| Identity became active | 688117321 |

App3 was active before Identity started; app2, help and platform retained their invocation IDs. A fresh signed-in introspection check passed after rotation.

## Refusal and uninstall evidence

For the trailing-newline control, the probe retained the valid bytes privately, appended one newline, and called the shipped app3 `./deploy.sh install` once. Exit 1 and the phrase `trailing newline` were required; the source bytes were required absent from captured output. Before/after snapshots compared paths, modes, mtimes and file SHA-256s for `state/apis`, the owner YAML, `pending-operation.json` (including absence) and the Quadlet/user-unit directories; all matched. Service invocation IDs also matched. The valid bytes were restored in `finally`; checksums matched again.

The final supplemental probe installed the original signed app3 0.1.1 bundle after the normal run, without resetting either VM. App3 uninstall removed its API registration and the owner key; Identity restarted; app2/help invocation IDs were unchanged. App2 completed the real sign-in and CRUD/CSRF smoke afterwards. Filtered `podman logs identity-server-app` confirmed the inactive-API line both before install and after uninstall.

The earlier read-only journal evidence probe failed (`journalctl --user` exit 1, zero records). Diagnosis independently found an empty `dict` Secret with zero keys and active Identity; `podman logs` then supplied one matching inactive-API record. This was a change of evidence source, not a rerun or repair of the failed journal check. The official normal run and its strict final audit both passed unchanged.

## Selected private-log fingerprints

| Run / step | SHA-256 |
| --- | --- |
| `api72-fd99d31-build/03-build-images` | `37d3eb70d2cdcf265fe4f664561406828f6d41c54dea98351bb152f7b819b4ee` |
| `api72-fd99d31-build/04-product-tests` | `9444a3c858755ca726e1e06ebe6697056a119ca8588dc92a0b3949e8202a871d` |
| `api72-fd99d31-build/05-harness-tests` | `3010b985145e6ccdea41d897fa7c8442a9d2592e4b611dc96275bb88de666e08` |
| `whoami-fd99d31/08-whoami-e2e` | `2b2dff0925ccf498040ca093185fcbbadab3f9abf3b95d8c4074c20f77326188` |
| `whoami-fd99d31/11-prod-audit` | `5e8cd7101030afc6f3df56f26cbf1e9c98f36abc7ca2edb34acd46b21fa35648` |
| `api72-fd99d31-lifecycle/06-rotate-once` | `a0c044b908d3fa092e3a53a6feb90fdbfb1be8bc2360d65e76dad6a0192d49e2` |
| `api72-fd99d31-lifecycle/08-trailing-newline-refusal` | `439b2ed2f6e9563c34df3e67a46a35e6082363ea10eaa1b800dc1aed1c2696c8` |
| `normal-fd99d31/11-prod-audit` | `1dac4a675d326bbe578e470ebbdf99ece950249bbad50623691a9ae0b767d76e` |
| `api72-fd99d31-uninstall/07-rotate-with-siblings` | `cad0e228caf847106184d506c6ba27812bfb94caee4ff8ab59ec56b026f18604` |
| `api72-fd99d31-uninstall/08-uninstall-app3` | `64cfc8207726b3abee46379b751a1cf98644e8062af33e40e10f298ad9ffe027` |
| `api72-fd99d31-uninstall/09-survivor-app2-signin` | `655ff9f41a74abc42bf7ddf7a13f78406810529a92873a0cd03e1effff2e9d82` |
