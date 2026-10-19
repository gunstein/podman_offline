# Optional signing PFX provisioning (backlog 44)

The certificate helper has an explicit signing mode, independent of application
source and demo component names:

```bash
bash dev/generate-certificates.sh --root build/dev \
  --component my-identity --purpose signing --pfx
```

This mode requires Python 3.6+ and OpenSSL. It does not create demo users, change
an application, run Podman, or run automatically from deploy. Existing demo
commands are unchanged; the shipped Identity continues to consume PEM.

## Prepare the password once

The password file must exist before provisioning:

```text
<root>/<component>/credentials/signing/pfx-password
```

It must be a regular file owned by the provisioning user, mode 0600, with one
nonempty line (optional final LF, no CR/NUL, at most 1023 password bytes). The
component, credentials and signing directories must be mode 0700. No default
password is built into the helper. A missing/invalid file fails before writes.

For example, run this interactively from the source root to enter the password
expected by the unchanged application. The exclusive redirect refuses an existing
password file; do not delete that file to make the command work again.

```bash
mkdir -p build/dev/my-identity/credentials/signing
chmod 700 build/dev/my-identity build/dev/my-identity/credentials \
  build/dev/my-identity/credentials/signing
(
  umask 077
  set -o noclobber
  IFS= read -r -s -p 'PFX password expected by the application: ' pfx_password || exit 1
  printf '\n'
  printf '%s\n' "$pfx_password" > build/dev/my-identity/credentials/signing/pfx-password
)
```

Use the application's existing password. One organisation's image hardcodes its
password; the tool neither assumes nor configures that value. In that case no
password is delivered to the container. An application that requires a configurable
password must receive it through its own supported private configuration, not
through a newly invented deploy setting.

## Inputs and precedence

All signing inputs/outputs live under `<root>/<component>/credentials/signing/`:

| Files present | Action |
| --- | --- |
| `signing-cert.pfx` | Verify its password, private key and matching leaf certificate; retain its exact bytes. Any supplied PEM certificate/key must match it. No CA or PEM is generated. |
| `signing-cert.crt` and `signing-cert.key`, no PFX | Verify the pair, then export the PFX. No CA is needed. |
| Neither PFX nor PEM | Use the complete CA at `<root>/PKI/private/ca.crt` and `ca.key`, or create the current development CA there if absent; issue a signing pair and export the PFX. |
| A partial PEM pair without PFX, partial CA needed for issuance, corrupt/mismatched credentials, or wrong password | Fail and retain existing inputs; restore the missing/correct files from backup. Remove an orphan only if confirmed unused after interrupted first issuance, as described below. |

Thus externally supplied files override issuance simply by being present before
the same invocation. A retained PFX can exist alone. If just one optional PEM file
is present alongside it, that file is also checked against the PFX. The helper
accepts unencrypted PEM keys; it never prompts for a PEM/CA key password. Existing
private inputs (PFX/PEM key/CA key) require current-user ownership and mode 0600.
Credential paths and their ancestors must not be symlinks.

New private files are mode 0600. Scratch files, including the decrypted key used
for verification, live in a temporary 0700 directory under the signing directory
and are removed on ordinary success/failure, including handled SIGTERM. A hard-link publish (`os.link`, the
same no-clobber operation as `ln`) atomically refuses any existing destination.
The PFX is verified before publication; an export failure leaves the source
pair available for retry and does not publish an incomplete PFX. Publishing a
new PEM/CA pair is not a multi-file transaction: if interrupted between files,
restore the missing file from backup. If no backup exists and you confirm the
remaining file belongs to an unused, interrupted first issuance, remove only
that orphan and retry. Never remove an in-use signing key or CA to trigger
reissuance; restore a valid pair or perform a separately planned replacement.

Explicit signing invocations use `<root>/.signing-provision.lock` to serialize
provisioning for that environment, including CA creation. A second invocation
fails rather than interfering. After an uncatchable interruption such as SIGKILL,
first confirm no provisioning process remains, inspect/recover any partial pair,
then remove the stale lock directory with `rmdir` before retrying. Remove only
orphan `.pfx-*` scratch directories from that interrupted operation. Do not run
the older demo provisioning commands concurrently with signing provisioning.

PKCS#12 export explicitly uses AES-256-CBC for key/certificate encryption and
SHA-256 for the MAC, rather than OpenSSL-version-dependent defaults; no `-legacy`.
Password values are read by OpenSSL with `file:` and never placed in argv or
printed. OpenSSL errors are captured and replaced with value-free diagnostics.
Exporting the same inputs again produces equivalent, not byte-identical, PFX
bytes because of random salt/IV. Existing PFX bytes are always retained.

## Deliver only the PFX

For `components/my-identity/config.defaults.yaml`, use the individual file as the
source, not the whole signing directory (which also holds private provisioning
inputs):

```yaml
SECRET_FILES:
  my-identity-signing:
    - path: credentials/signing/signing-cert.pfx
```

In the Pod manifest, these are fragments of `spec.volumes` and the consuming
container's `volumeMounts`:

```yaml
volumes:
  - name: signing
    secret:
      secretName: my-identity-signing
      defaultMode: 0400
      items:
        - key: signing-cert.pfx
          path: signing-cert.pfx
```

```yaml
volumeMounts:
  - name: signing
    mountPath: /run/secrets
    readOnly: true
```

This exposes `/run/secrets/signing-cert.pfx`, matching the reported application
path. Check all other mounts and the host's `mounts.conf` before mounting over
`/run/secrets`; it must not hide required credentials. If the app supports a path
under `/run/secrets/signing/`, prefer mounting there and configure that path in
the app. Choose file ownership/mode for the actual application UID: mode 0400
above assumes the container-root consumer used by the current demo. Do not
change the image/user solely to make an unreadable mount appear to work.

The CA key, PEM key and password file are not declared or delivered. PFX remains
private key material even when password-protected. A known/hardcoded password
gives no meaningful confidentiality; protect sources, rendered 0600 install
YAML and container storage, and back up authoritative credentials (items 3/37).

## Dev, production and runtime verification

Dev provisioning uses `--root build/dev`; relative SECRET_FILES paths then resolve
under `build/dev/<component>/`. Run `./deploy validate` and `./dev/dev.sh up` after
images and all other credentials are present.

Production uses the same relative layout under `/var/lib/<product>/<component>/`.
Replace `myproduct` below with the product name. After `init-config`, prepare
the password/external material there as the service
user, then the current explicit stdin delivery works without a checkout:

```bash
# Run as the product service user, with the script supplied on stdin:
bash -s -- --root /var/lib/myproduct --component my-identity --purpose signing --pfx \
  < /path/to/generate-certificates.sh
```

Dev and production must use separate roots and CAs. This is still the current
provisioning helper: configurable production CA identity/lifetimes (45a), signed
tool delivery/fapolicyd integration (45b), and renewal/expiry (45c) remain separate
work. New issuance currently uses the existing development CA defaults. An
external PFX/PEM needs no access to the CA key.

For the organisation's external Identity image, record a new real verification:

1. Use its actual configured/hardcoded PFX path and password. Confirm no other
   credential mount or `mounts.conf` entry is hidden by the Secret mount.
2. Start with `./dev/dev.sh up` (or the ordinary production install), then use
   `podman ps --all --pod` to identify the actual application container. Check
   `podman exec <container> id`, and, if its image has a shell,
   `podman exec <container> sh -c 'test -r /run/secrets/signing-cert.pfx'`.
   Do not print certificate/password contents or the full environment.
3. Verify application startup, signing-key loading and a real token issuance;
   file readability alone does not prove that .NET loaded a private key. Use the
   application's normal UID, read-only mount and actual HOME, including its
   normal .NET key-storage behavior. Do not substitute a root exec for this.
4. Repeat provisioning, restart/redeploy, and verify the PFX hash stays unchanged
   and the app still issues tokens. Also test the same flow with an externally
   supplied PFX, and wrong-password refusal without replacing existing files.
5. Capture versions/commit and redacted evidence, separately for dev and PROD.

A missing PFX can be re-exported from retained PEM/password, but the new bytes
must be delivered through the ordinary render/upgrade path. An equal-version
`newer-only` install skips rendering; a plain restart uses installed YAML.

Local certificate tests verify OpenSSL operations and retention; platform tests
verify binary Secret delivery and file mapping. They do not prove the external
.NET image, supported OpenSSL 1.1.1 runtime, Podman permissions, SELinux/fapolicyd
or systemd behavior. These runtime checks are pending until actually run.

OpenSSL references: [1.1.1 pkcs12](https://docs.openssl.org/1.1.1/man1/pkcs12/),
[3.x pkcs12](https://docs.openssl.org/3.3/man1/openssl-pkcs12/).

## CA subject and certificate lifetimes (backlog 45a)

Set public issuance settings before the component arguments, for example:

```sh
bash dev/generate-certificates.sh --root /var/lib/myproduct \
  --ca-subject '/C=NO/O=Example Organisation/CN=Production CA' \
  --ca-days 3650 --cert-days 365 \
  --component my-identity --purpose signing --pfx
```

The same prefix options work with the full-demo and named-demo recipes and stdin
execution. Defaults remain `/CN=Demo Development CA`, 3650 CA days and 365 leaf
days. Days must be positive decimal integers within the supported date range.
Subject syntax is `/ATTRIBUTE=value` (UTF-8), using CN, C, ST, L, O, OU,
emailAddress, serialNumber, DC or UID. C is two uppercase letters; values must
be nonempty without leading/trailing whitespace, controls, slash, backslash or
plus. This deliberately small DN syntax does not support escaped separators or
multi-valued RDNs. Invalid settings fail before any directory/file write.

All modes use the same CA creation/reuse implementation. Existing complete
CA and valid PFX/PEM files are retained byte for byte. Explicit `--ca-subject`
must match the retained CA subject (ordered DN fields); a mismatch fails before
new credentials, even if the requested component already has a PFX. Omit the
option to reuse the existing CA without asserting its subject. Explicit
`--ca-days` reports that it applies only to newly created CAs. Changing flags
does not renew certificates or replace the CA; a new component uses the retained
CA and the requested new leaf lifetime.
The full-demo recipe still refuses an existing PKI, as before.

Keep a separate `--root` for each environment. Back up and protect the CA pair in
`<root>/PKI/private/` (directory 0700, CA key 0600), together with the retained
component credentials and their private passwords, outside disposable releases.
Restore complete matching pairs; a partial CA is refused. Loss of the CA key
prevents further issuance from that CA. Replacing it requires reissuing all
certificates and distributing the new trust anchor; replacement, expiry/renewal
and signed offline tool delivery are separate operations (45b/45c, backlog 3/37).
