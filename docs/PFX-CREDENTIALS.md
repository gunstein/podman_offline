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

## Complete provisioning for a product with its own Identity image

One environment needs the proxy TLS pair and the Identity signing PFX, both
issued from the same CA under `<root>/PKI/private/`. The first issuing command
creates that CA, so it carries the CA settings; later commands reuse it. Use a
separate root, and therefore a separate CA, per environment. Replace
`my-identity` with the Identity component ID from `bundles.yaml` and the host
names with real ones. The details of each step are in the sections below.

Dev, from the source root (`--root build/dev`):

```bash
id=my-identity
root=build/dev
# 1. Password file, once: an empty private file you then edit by hand.
d="$root/$id/credentials/signing"
mkdir -p "$d"
chmod 700 "$root/$id" "$root/$id/credentials" "$d"
test -e "$d/pfx-password" || install -m 0600 /dev/null "$d/pfx-password"
vi "$d/pfx-password"   # the password the application expects, on one line
# 2. Proxy TLS pair; this first command creates the CA.
bash dev/generate-certificates.sh --root "$root" \
  --ca-subject '/C=NO/O=Example Organisation/CN=Dev CA' --ca-days 3650 --cert-days 365 \
  platform dev-host.example.test
# 3. Identity signing PFX from the same CA.
bash dev/generate-certificates.sh --root "$root" --cert-days 365 \
  --component "$id" --purpose signing --pfx
```

Production, on the target after `init-config` for each component, as the service
user with the helper copied from the source checkout and supplied on stdin
(the bundles do not contain it):

```bash
product=myproduct
id=my-identity
root=/var/lib/$product
as_product() { sudo -n -H -u "$product" "$@"; }
# 1. Password file, once: an empty private file owned by the service user,
#    then edited by hand with sudoedit.
d="$root/$id/credentials/signing"
as_product mkdir -p "$d"
as_product chmod 700 "$root/$id" "$root/$id/credentials" "$d"
as_product test -e "$d/pfx-password" || as_product install -m 0600 /dev/null "$d/pfx-password"
sudoedit -u "$product" "$d/pfx-password"   # the expected password, on one line
# 2. Proxy TLS pair; this first command creates the production CA.
as_product bash -s -- --root "$root" \
  --ca-subject '/C=NO/O=Example Organisation/CN=Production CA' --ca-days 3650 --cert-days 365 \
  platform public-host.example.test < generate-certificates.sh
# 3. Identity signing PFX from the same CA.
as_product bash -s -- --root "$root" --cert-days 365 \
  --component "$id" --purpose signing --pfx < generate-certificates.sh
```

- External files win: place `signing-cert.pfx` (or the `.crt`/`.key` pair) in
  `credentials/signing/` before step 3, or `web.crt`/`web.key` in
  `platform/credentials/web/` before step 2, and they are retained or exported
  instead of issued. Step 1 is still required for a supplied PFX.
- Commands can be repeated; existing files are retained and nothing is renewed
  (item 45c). `--ca-subject` applies when the CA is created; afterwards it must
  match the retained CA or be omitted.
- `platform <host>` is the retained demo TLS recipe. It writes
  `platform/credentials/web/` with the host, `localhost` and `127.0.0.1` as
  names, so it fits a platform component with the ID `platform`. The signing
  mode accepts any component ID.
- Back up `PKI/private/`, the password file and the component credentials.
- Then run `./deploy validate` and install as usual. Delivery of the PFX is
  described in [Deliver only the PFX](#deliver-only-the-pfx).

Checked locally (2026-10-20, OpenSSL 3, one disposable root): the dev sequence
with a scripted password created one CA with the requested subject, the web pair
and a PFX whose certificate that CA issued, all files mode 0600; repeating steps
2 and 3 kept every file. The hand-edited password file (empty 0600 file, then
one line written) was checked the same way, including refusal of an empty file.
The production commands (sudo, `sudoedit -u`, service user, stdin from a target
copy) have not been run; record them with the item 44 lab check.

## Prepare the password once

The password file must exist before provisioning:

```text
<root>/<component>/credentials/signing/pfx-password
```

It must be a regular file owned by the provisioning user, mode 0600, with one
nonempty line (optional final LF, no CR/NUL, at most 1023 password bytes). The
component, credentials and signing directories must be mode 0700. No default
password is built into the helper. A missing/invalid file fails before writes.

The file is an ordinary private text file that you create once and fill in by
hand; the helper never prompts for the password, and later runs only read it.
Create it empty with mode 0600 and edit it, as in step 1 of
[Complete provisioning](#complete-provisioning-for-a-product-with-its-own-identity-image).
The `test -e` guard keeps an existing file: `install` would otherwise replace it
with an empty one. Write the password on a single line and save. Do not create
the file with a Windows editor (CR line endings are refused). Copying it from a
secure source with `install -m 0600 <source> <path>` is equivalent. An empty or
otherwise invalid file fails clearly before any write, so a forgotten edit is
reported, not silently accepted. Keep the file in backups with the other
credentials.

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
      defaultMode: 0444
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

This exposes `/run/secrets/signing-cert.pfx`, the path the organisation's old
docker-compose test setup used (`target: signing-cert.pfx`, its only secret for
`identity-server`). Check all other mounts and the host's `mounts.conf` before
mounting over `/run/secrets`; it must not hide required credentials. If the app
supports a path under `/run/secrets/signing/`, prefer mounting there and
configure that path in the app.

Mode `0444` is deliberate. The organisation's image runs as a non-root container
user (the compose file gave the secret `uid: '999'`, `gid: '999'`, `mode: 0400`),
and `kube play` offers no per-file owner or `fsGroup` for a Secret volume, so a
`0400` file owned by container root would be unreadable and the app would fail to
load its key. `0444` makes the file readable only inside this one container,
where the application is the only process; on the host the Secret data stays in
the service user's private storage, and the hardcoded PFX password means host
file access is the real protection anyway. Keep the application's own non-root
user; do not set `runAsUser: 0` to make a mount readable. The demo's `0400` for a
container-root consumer remains valid for that demo only.

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
the password/external material there as the service user (commands in
[Complete provisioning](#complete-provisioning-for-a-product-with-its-own-identity-image)),
then the current explicit stdin delivery works without a checkout:

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
   Record `podman exec <container> stat -c '%u:%g %a' /run/secrets/signing-cert.pfx`
   and confirm `id` shows the image's non-root user (expected 999), not 0.
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
