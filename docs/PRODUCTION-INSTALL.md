# Production installation

For administrators and installers with limited Linux experience. All required
steps are here, in execution order. Design explanations are in [README](../README.md).
**Status:** the item 65 implementation passed the focused OL9 scenarios and full
regression matrix at `2d36d71`. This English translation is a later documentation
change. Unassisted human testing remains outstanding. The verification report
is `acceptance/HOST-SETUP.md` in the source repository.

## Before you begin

You need an Oracle Linux 9 server with SELinux Enforcing, active fapolicyd and
firewalld. Your organisation's administrator provides an existing login account,
`produser`, without sudo access or membership in wheel, adm or systemd-journal.
Its home and shell are retained. Python 3, python3-pyyaml, Podman, gnupg2,
fapolicyd, firewalld, policycoreutils-python-utils, acl, util-linux, shadow-utils
and sudo must be installed from your organisation's approved offline repository.
`setup` checks the commands and names the package if something is missing.
No command downloads packages.

**Two accounts:** The administrator uses sudo to prepare the host, publish
releases and retire releases. The runtime user logs in directly over SSH and
never uses sudo. Product files go under `/var/lib/myproduct`; only
`~/.myproduct/myproduct.env` is created in the home directory. SSH keys belong
to the ordinary login setup.

Obtain the following delivery from the supplier before changing the server:

- This manual from a trusted source, `release.py.gz`, `bundle-signing.gpg`, the
  selected `<product>-<component>-<version>-offline.tar.gz` files and their `.asc`
  files. Signatures are mandatory; `.sha256` files may accompany them to check
  transfer integrity.
- **Two SHA256 values through a separate authenticated channel:** one for
  `release.py.gz` and one for `bundle-signing.gpg`. A checksum file next to the
  upload is not sufficient.
- For the platform and identity example: `web.crt`, `web.key`, `identity.crt`,
  `identity.key`, `alice-password`, `bob-password` and the public `ca.crt`.
  The web certificate must cover the hostname in `public_origin`. Deliver these
  files privately to the runtime user. The two password files belong to demo
  users; your organisation's components need their own delivery list. The PFX
  variant instead needs `signing-cert.pfx` and the private, single-line
  `pfx-password` file.

Ask the administrator to prepare the server/account if these prerequisites are
missing. Do not generate credentials from dev or use an unsigned archive as a
shortcut. For the supplier: create `release.py.gz` using
`gzip -n -c scripts/release.py > release.py.gz` from the separately reviewed
source commit that the tool is intended to represent. Do not produce the tool
from an unverified bundle.

### Values to replace once

Copy the following block into the terminal on each machine and in each new
login session where you follow these steps. Replace **only the values between
single quotes**, using the table. These are public settings; never put passwords
or private keys in this block. Do not include single quotes or line breaks in a
value. Take versions from the delivery filenames; they need not match.

| Value | Meaning |
| --- | --- |
| `server`, `admin`, `runtime` | Server address and the two login accounts |
| `product` | Supplier's product name; `myproduct` in this example |
| `gateway`, `login_component` | Component names; `platform` and `identity` in this example |
| `gateway_version`, `login_version` | Versions in the delivery, not an assumed latest version |
| `old_gateway_version` | Previously installed gateway version, used only for retirement after upgrade |
| `port`, `public_origin`, `bind_ip` | HTTPS port and server address that the service will use |
| `upload` | Upload directory on the server, outside the home directory |
| `credentials` | Runtime user's private delivery directory on the server |
| `helper_sha256`, `key_sha256` | Replace the text with the two independently received 64-character values |
| `credential_format` | `pem` for the demo; `pfx` only for a delivered component declaring `credentials/signing/signing-cert.pfx` |
| `discovery_path` | Supplier's actual discovery path, as in this example |
| `with_identity` | `yes` for this example; `no` for gateway only, without Identity or a database |

<!-- operator: values -->
```sh
server='192.168.0.108'
admin='gunstein'
runtime='produser'
product='myproduct'
gateway='platform'
login_component='identity'
gateway_version='0.4.12'
old_gateway_version='0.4.11'
login_version='0.4.12'
port='8443'
public_origin='https://myproduct-proxy:8443'
bind_ip='192.168.0.108'
upload='/var/tmp/myproduct-upload'
credentials='/var/tmp/myproduct-credentials'
helper_sha256='REPLACE_WITH_INDEPENDENT_TOOL_SHA256'
key_sha256='REPLACE_WITH_INDEPENDENT_KEY_SHA256'
with_identity='yes'
credential_format='pem'
discovery_path='/identity/.well-known/openid-configuration'
```

## 1. Transfer the delivery

**Machine:** laptop. **User:** administrator's login account. Run the values
block, then log in to the server:

<!-- operator: admin-login -->
```sh
ssh "$admin@$server"
```

**Expected:** the server's shell prompt. Run the values block in this new session too.

**Machine:** server. **User:** administrator, without sudo for this step. Run
the values block first. Create a private directory owned by your account;
an additional copy into a root-only directory is not required.

<!-- operator: upload-directory -->
```sh
install -d -m 0700 "$upload"
```

**Machine:** laptop. **User:** administrator. Run the values block here too,
and work from the directory containing the public delivery. Private credential
files are transferred later using the runtime account.

<!-- operator: transfer -->
```sh
(
set -eu
scp release.py.gz bundle-signing.gpg "$product-$gateway-$gateway_version-offline.tar.gz" "$product-$gateway-$gateway_version-offline.tar.gz.asc" "$admin@$server:$upload/"
if [ "$with_identity" = yes ]; then
  scp "$product-$login_component-$login_version-offline.tar.gz" "$product-$login_component-$login_version-offline.tar.gz.asc" "$admin@$server:$upload/"
fi
)
```

**Expected:** scp completes without errors. If a file is missing, obtain it from
the supplier, repeat the same transfer, then continue with step 2.

## 2. Install the trusted tool

**Machine:** server. **User:** administrator with sudo. Run the values block
after a new login. Copy the entire block. It checks the independent checksum
against a protected copy before the tool can run. An older copy is retained on
failure. Do not edit the Python code. You can repeat this step with the same delivery.

<!-- operator: tool-bootstrap -->
```sh
sudo python3 -I -B - "$upload/release.py.gz" "$helper_sha256" <<'PY'
import errno, hashlib, os, stat, sys, tempfile
from pathlib import Path

def protected(path, directory):
    info = path.lstat()
    if info.st_uid != 0 or info.st_mode & 0o022 or not (
        stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    ):
        raise ValueError('Unsafe protected path; ask administrator to inspect: ' + str(path))
    for key in ('system.posix_acl_access', 'system.posix_acl_default'):
        try:
            os.getxattr(str(path), key, follow_symlinks=False)
        except OSError as error:
            if error.errno not in (errno.ENODATA, errno.ENOTSUP):
                raise
        else:
            raise ValueError('ACL on protected path; ask administrator to inspect: ' + str(path))

source, expected = sys.argv[1:]
target = Path('/usr/local/libexec/podman-offline-release.py.gz')
if os.geteuid() != 0 or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
    raise SystemExit('ERROR: administrator access and independent SHA256 required; repeat bootstrap with correct inputs')
temporary = None
try:
    for parent in reversed((target.parent,) + tuple(target.parent.parents)):
        if not os.path.lexists(str(parent)):
            parent.mkdir(mode=0o755)
        protected(parent, True)
    if os.path.lexists(str(target)):
        protected(target, False)
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as incoming:
        if not stat.S_ISREG(os.fstat(incoming.fileno()).st_mode):
            raise ValueError('Helper upload must be a regular file')
        with tempfile.NamedTemporaryFile(dir=str(target.parent), prefix='.bootstrap-', delete=False) as out:
            temporary = Path(out.name)
            value = hashlib.sha256()
            for block in iter(lambda: incoming.read(1024 * 1024), b''):
                value.update(block)
                out.write(block)
            if value.hexdigest() != expected:
                raise ValueError('Helper SHA256 mismatch; obtain correct file/digest, then repeat bootstrap')
            out.flush()
            os.fchmod(out.fileno(), 0o644)
            os.fsync(out.fileno())
    os.replace(str(temporary), str(target))
    fd = os.open(str(target.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    print('PASS: authenticated release tool installed; continue with setup')
except (OSError, ValueError) as error:
    if isinstance(error, ValueError):
        raise SystemExit('ERROR: ' + str(error)) from None
    raise SystemExit('ERROR: bootstrap I/O failure; administrator must inspect upload/target permissions and space, then repeat bootstrap') from None
finally:
    if temporary is not None and temporary.exists():
        temporary.unlink()
PY
```

**Expected:** `PASS: authenticated release tool installed`.
For a SHA256 mismatch, obtain the correct tool/values through the trusted channel,
update the values block and repeat step 2. For ownership/ACL errors, the
administrator must inspect the named system path; do not run recursive chmod/chown.

## 3. Prepare the server and selected releases

**Machine:** server. **User:** administrator with sudo. Copy the entire block.
Only the components explicitly selected here are processed. Other files in the
directory are ignored.

<!-- operator: setup -->
```sh
(
set -euo pipefail
set -- --release "$gateway@$gateway_version"
if [ "$with_identity" = yes ]; then
  set -- "$@" --release "$login_component@$login_version"
fi
gzip -dc /usr/local/libexec/podman-offline-release.py.gz | sudo python3 -I -B - setup \
  --product "$product" --user "$runtime" --port "$port" \
  --input-dir "$upload" --keyring "$upload/bundle-signing.gpg" --key-sha256 "$key_sha256" \
  "$@" --host-release "$gateway@$gateway_version"
)
```

**Expected:** `PASS: setup preflight`, one `PASS: release ready` per component,
and finally `PASS: host setup`. The tool prints the next command for the runtime
user. This publishes the releases and prepares the host; applications are not
yet installed. No installation receipt is created on their behalf.

The command checks the OS, packages, account, sudo policy, security services,
key, journal policy and space before product changes. Archive contents and
extracted size can only be validated after signature verification. Failure in
a later bundle can therefore leave earlier verified releases in place, but does
not run the host script. Space checks are lower bounds with 1 GiB reserved per
filesystem; the administrator must also size storage for images and databases.
On standard OL9, `/var/log/journal` is created and journald is flushed to disk.
This makes the **entire host's** journal persistent and requires space under
`/var/log`. Explicit conflicting journal policy is not overwritten. The runtime
user receives no additional group memberships.

### If preflight stops

**Same server and administrator account.** Follow the named error, then repeat
all of step 3. For a missing command, install the named package from your
organisation's offline repository. For a sudo grant, use an account without
grants; do not give the product sudo access. For a `Storage`/`SplitMode` conflict,
the system administrator must first approve persistent journaling with
`Storage=auto` or `persistent` and `SplitMode=uid`; do not bypass policy with groups.

For standard OL9 with an undersized fapolicyd cache, check that the setting
exists and apply this exact remedy. It changes cache size, not trust rules.
If the first command fails, stop and ask the system administrator to prepare
the baseline.

<!-- operator: cache-remedy -->
```sh
if sudo grep -Eq '^[[:space:]]*subj_cache_size[[:space:]]*=' /etc/fapolicyd/fapolicyd.conf; then
  sudo sed -i -E 's/^[[:space:]]*subj_cache_size[[:space:]]*=.*/subj_cache_size = 16381/' /etc/fapolicyd/fapolicyd.conf &&
  sudo systemctl restart fapolicyd
else
  printf 'STOP: subj_cache_size is missing; ask the system administrator to prepare the OL9 baseline before repeating step 3.\n' >&2
  false
fi
```

**Expected:** no errors. Then repeat step 3. For another preflight failure,
follow its stated remedy; do not use the cache remedy as a general repair.

## 4. Log in as the runtime user

**Machine:** laptop. **User:** runtime login account, without sudo.

<!-- operator: login -->
```sh
ssh "$runtime@$server"
```

**Machine:** server, in the new SSH session. **User:** runtime user without sudo.
Run the values block again, then create the product's settings file:

<!-- operator: init-layout -->
```sh
bash "/var/lib/$product/releases/$product-$gateway-$gateway_version/deploy.sh" init-layout
```

**Expected:** `[OK] Bootstrap ready` or `[OK] Existing bootstrap retained`.
You can repeat this step; existing valid settings are retained. For a conflict,
ask the administrator to check the product/account association, then continue
with the same command. Do not delete or overwrite an existing settings file.
After interruption, run the same `init-layout` command again as the runtime user.
An unfinished temporary file is not used and does not block the next attempt.

## 5. Configuration and private credentials

**Machine:** server. **User:** runtime user without sudo. Initialise the gateway:

<!-- operator: gateway-config -->
```sh
(
set -eu
bash "/var/lib/$product/releases/$product-$gateway-$gateway_version/deploy.sh" init-config "$gateway"
python3 - "$product" "$gateway" "$public_origin" "$port" "$bind_ip" <<'PY'
from pathlib import Path
import sys, yaml
product, component, origin, port, address = sys.argv[1:]
p = Path('/var/lib') / product / 'state' / component / 'config.yaml'
v = yaml.safe_load(p.read_text())
v.update(PUBLIC_ORIGIN=origin, HTTPS_PORT=int(port), IP_ADDRESS=address)
p.write_text(yaml.safe_dump(v))
print('OK: public gateway settings saved; continue with credentials')
PY
install -d -m 0700 "$credentials"
)
```

**Expected:** init-config reports that config was created or retained, followed
by `OK: public gateway settings saved`. Settings come from the values block.
This is an explicit editing step: during ordinary retry/upgrade, do not repeat
the editing step with old values.
The block stops at the first failure. If `init-config` fails, existing config
is not edited. Correct the reported cause, check the values block and repeat
this block as the runtime user on the server before continuing.

**Machine:** laptop. **User:** runtime login account. Work from the directory
containing the supplier's private files. Run the values block on the laptop first.

<!-- operator: credentials-transfer -->
```sh
(
set -eu
scp web.crt web.key ca.crt "$runtime@$server:$credentials/"
if [ "$with_identity" = yes ]; then
  case "$credential_format" in
    pem) scp identity.crt identity.key alice-password bob-password "$runtime@$server:$credentials/";;
    pfx) scp signing-cert.pfx pfx-password "$runtime@$server:$credentials/";;
    *) printf 'STOP: credential_format must be pem or pfx from the supplier values list.\n' >&2; false;;
  esac
fi
)
```

**Expected:** no scp errors. Never use chat, terminal output or Git to send these
files. Private files must be owned by the runtime user with mode 0600.
On the **server as the runtime user**, install only the gateway files:

<!-- operator: gateway-credentials -->
```sh
(
set -e
install -d -m 0700 "/var/lib/$product/state/$gateway/credentials/web"
for name in web.crt web.key; do
  destination="/var/lib/$product/state/$gateway/credentials/web/$name"
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    test ! -L "$destination" && cmp -s "$credentials/$name" "$destination" || { printf 'STOP: credential conflict for %s; retain the file and contact the credential provider, then repeat this step.\n' "$name" >&2; exit 1; }
  else
    install -m 0600 "$credentials/$name" "$destination" || exit 1
  fi
done
)
```

**Expected:** no errors; identical existing files are retained. For a conflict,
stop and ask the credential provider to confirm the correct set. Do not overwrite
retained keys.

## 6. Install and check the gateway

**Machine:** server. **User:** runtime user without sudo.

<!-- operator: gateway-install -->
```sh
bash "/var/lib/$product/releases/$product-$gateway-$gateway_version/deploy.sh" validate &&
bash "/var/lib/$product/releases/$product-$gateway-$gateway_version/deploy.sh" install
```

**Expected:** validated, followed by a healthy service and containers reported Up.
For a failure, follow "Upgrade and failure/interruption" below and repeat the
same block. After success:

<!-- operator: gateway-check -->
```sh
curl --cacert "$credentials/ca.crt" --resolve "$(printf '%s' "$public_origin" | sed -E 's@https://([^:/]+).*@\1@'):$port:$bind_ip" -sS -o /dev/null -w '%{http_code}\n' "$public_origin/livez"
```

**Expected:** `204`. Do not bypass certificate verification with curl's `-k`.
If `with_identity=no`, skip to step 8. The gateway alone needs no Identity,
database or demo users.

## 7. Install identity when selected

**Machine:** server. **User:** runtime user without sudo. The gateway must
already be installed. The supplier selects the credential variant in the values block:

| Variant | Private delivery | Destination under the component's `credentials/` |
| --- | --- | --- |
| `pem` (demo) | `identity.crt`, `identity.key`, `alice-password`, `bob-password` | Certificate/key in `identity/`, demo passwords in `users/` |
| `pfx` (separately supplied Identity) | `signing-cert.pfx`, `pfx-password` | Both in `signing/`; the component's supplied config must already declare the PFX reference |

The password file contains one nonempty line. Never put passwords in command-line
arguments. The supplier must clarify whether the application needs the password
as a separate Secret; provisioning files are never delivered implicitly. Do not
change the demo's PEM config by guessing PFX settings. Copy the same block for
either variant:

<!-- operator: identity-config -->
```sh
(
set -e
bash "/var/lib/$product/releases/$product-$login_component-$login_version/deploy.sh" init-config "$login_component"
case "$credential_format" in
  pem) names='identity.crt identity.key alice-password bob-password';;
  pfx) names='signing-cert.pfx pfx-password';;
  *) printf 'STOP: credential_format must be pem or pfx from the supplier values list.\n' >&2; exit 1;;
esac
for name in $names; do
  case "$name" in
    signing-cert.pfx|pfx-password) group=signing;;
    *-password) group=users;;
    identity.*) group=identity;;
    *) group=signing;;
  esac
  install -d -m 0700 "/var/lib/$product/state/$login_component/credentials/$group"
  destination="/var/lib/$product/state/$login_component/credentials/$group/$name"
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    test ! -L "$destination" && cmp -s "$credentials/$name" "$destination" || { printf 'STOP: credential conflict for %s; retain the file and contact the credential provider, then repeat this step.\n' "$name" >&2; exit 1; }
  else
    install -m 0600 "$credentials/$name" "$destination" || exit 1
  fi
done
)
```

**Expected:** initialised or retained config, no copy errors. Files are retained
on repeat. Install generates a database password if declared; an existing
password is retained. Install:

<!-- operator: identity-install -->
```sh
bash "/var/lib/$product/releases/$product-$login_component-$login_version/deploy.sh" validate &&
bash "/var/lib/$product/releases/$product-$login_component-$login_version/deploy.sh" install
```

**Expected:** both services healthy. Check with:

<!-- operator: identity-check -->
```sh
curl --cacert "$credentials/ca.crt" --resolve "$(printf '%s' "$public_origin" | sed -E 's@https://([^:/]+).*@\1@'):$port:$bind_ip" -sS -o /dev/null -w '%{http_code}\n' "$public_origin$discovery_path"
```

**Expected:** `200`. The demo's `/identity/` is not a valid success check
(it returns 404). The supplier must provide the actual endpoint for its component.
Issuing/converting your own certificates is an advanced supplier task, described
in [PFX design and provisioning](PFX-CREDENTIALS.md). `generate-certificates.sh`
is not included in the bundles; external PEM/PFX delivery above does not need it.

## 8. Operations, fresh login and reboot

**Machine:** server. **User:** runtime user without sudo. Run the values block
again after each new login. All paths are absolute; no remembered shell functions
or manual XDG exports are needed.

<!-- operator: status -->
```sh
(
set -eu
bash "/var/lib/$product/releases/$product-$gateway-$gateway_version/deploy.sh" status
systemctl --user is-active "$product-$gateway.service"
journalctl --user -u "$product-$gateway.service" -b -n 10 --no-pager --output=json --output-fields=__REALTIME_TIMESTAMP,_SYSTEMD_USER_UNIT,USER_UNIT,PRIORITY
)
```

**Expected:** status shows complete/active with no pending work, is-active shows
`active`, and the journal contains JSON entries with timestamps and unit names.
This demonstrates read access without printing message contents (`MESSAGE`).
Do not share raw journal text containing passwords, tokens or connection strings;
see the safe error-reporting instructions below.

Log out as the runtime user (`exit`). The **administrator on the server with sudo**
runs `sudo reboot`. After boot, the administrator logs in again and runs the values
block and the check below **before the runtime user logs in**:

<!-- operator: boot-check -->
```sh
set -- "$product-$gateway.service"
if [ "$with_identity" = yes ]; then set -- "$@" "$product-$login_component.service"; fi
sudo systemctl --user -M "$runtime@" is-active "$@"
```

**Expected:** `active` for each selected service. Then log in again as the runtime
user using step 4, run the values block and step 8. Expect the same status and
readable journal without sudo.

## 9. Upgrade and failure/interruption

For an upgrade, the administrator transfers the new delivery (step 1), changes
only the delivered versions in the values block and runs step 3. Updating the
tool requires new independent verification in step 2. The runtime user logs in,
uses the new versions in the values block and runs validate/install in steps 6/7.
Skip editing and credential copying; existing config, keys and data are retained.

Once functional checks pass, the administrator can retire an old release. Copy
the block on the **server as administrator with sudo** after setting
`old_gateway_version` to the version that was actually replaced:

```sh
(
set -euo pipefail
gzip -dc /usr/local/libexec/podman-offline-release.py.gz | sudo python3 -I -B - retire \
  --product "$product" --component "$gateway" --version "$gateway_version" --old-version "$old_gateway_version"
)
```

**Expected:** `PASS: protected release retire`. Old releases are never deleted
as automatic failure cleanup.

| Event | Action and command to continue |
| --- | --- |
| Interrupted tool bootstrap | Administrator repeats step 2 with the same trusted SHA256. The old tool copy is retained on failure. |
| Interrupted setup, signature/trust failure | Administrator corrects the named file/baseline error and repeats all of step 3. Previously approved releases are retained; an invalid signature never authorises code. |
| Setup stops after journal/drop-in changes | Administrator repeats step 3. It checks the actual manager/journal/firewall, not just file existence. |
| New SSH session | Run the values block again. `init-layout` can be repeated and retains a valid file. |
| Install fails | Runtime user runs status from step 8; the component should be incomplete/pending. Correct the named config/credential error using the delivery's public fields/filenames, then repeat the same validate/install block. Do not edit the pending record. |
| Existing credentials differ | Stop copying, retain the files and ask the credential provider to confirm the set. Repeat the credential step only when the delivery is correct. No secret values need to be shared. |
| Missing journal or manager environment | Administrator repeats step 3. Do not add the runtime user to privileged groups or export XDG manually. |
| Unexpected error without a concrete remedy | Stop. Send only the step name, public component/version and fixed error message; do not dump config, environment, inspect or journal. The supplier must provide a safe remedy and next command before you continue. |

Steps 2, 3, init-layout, init-config and identical credential copying can be repeated.
An install attempt can safely be completed with the same command and retained
settings; `upgrade: always` may restart the selected service on repeat. Do not
repeat config editing with old values or retire a different version.
Run only one setup/install/upgrade/retire operation at a time.
