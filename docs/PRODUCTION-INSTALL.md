# Production installation

For administrators and installers with limited Linux experience. Every
ordinary task is here, in the order you do it, and the commands are short
enough to type from a printed copy. Design explanations are in the
[README](../README.md).

**Status:** RPM delivery, backlog 69 phase 1 (unsigned RPMs). The automated
OL9 lab scenario `--rpm-manual` runs this manual's command blocks literally,
with typed answers, a real SSH login, its stops, an interruption, an upgrade
and the tools repair; it passed on the default and the strict fapolicyd
profile. Mounting a medium is not part of it (the lab copies the delivery to
a directory). The AI
walkthrough is in `acceptance/OPERATOR-REVIEW.md`. A test with a person
following this manual alone is still outstanding (backlog 68).

## Who does what

| Role | Account | Does |
| --- | --- | --- |
| Administrator | your own account, with `sudo` | installs the tools once, then every delivery and the credentials |
| Runtime user | the product's login account, **without** `sudo` | runs the product's one command, `myproduct` |

One person may hold both accounts. Switch between them by logging in (step 5),
never with `su` or `sudo -u`. Messages may also name the **system**,
**security** or **account administrator**: your organisation's people for the
operating system, for SELinux and fapolicyd, and for login accounts. Often
that is the administrator.

## The example used in this manual

Replace these example values with your own wherever they appear. Nothing else
in the commands changes.

| Example | Meaning |
| --- | --- |
| `myproduct` | the product name the supplier gave you |
| `produser` | the runtime user's login account |
| `server1.example.org` | the name users type in the browser; the web certificate is for this name |
| `192.0.2.10` | the server's IP address |
| `8443` | the HTTPS port |
| `/dev/sdb1` | the delivery medium (USB stick or DVD); step 1 shows how to find it |
| `/mnt` | where the delivery is; a directory the delivery was copied to works too |

## Before you begin

The administrator's preflight (step 3) checks all of this and names what is
missing and who fixes it, so you can also start and let it tell you.

- **Server:** Oracle Linux 9 with SELinux `Enforcing`, and `firewalld` and
  `fapolicyd` running.
- **OS packages**, installed from your organisation's OS media or repository:
  `python3`, `python3-pyyaml`, `podman`, `fapolicyd`, `rpm-plugin-fapolicyd`,
  `firewalld`, `policycoreutils`, `policycoreutils-python-utils`,
  `libselinux-utils`, `shadow-utils`, `shadow-utils-subid`, `acl`,
  `util-linux` and `sudo`. Nothing is downloaded during installation.
- **fapolicyd setting:** `subj_cache_size = 16381` or more in
  `/etc/fapolicyd/fapolicyd.conf` (the security administrator; see "If a
  command stops"). This is the size of fapolicyd's cache of running
  processes; with a smaller cache fapolicyd can deny Podman when a service
  starts. It changes no rule.
- **Runtime user:** an ordinary login account (UID 1000 or higher, a login
  shell), with no `sudo` rights and not a member of `wheel`, `adm` or
  `systemd-journal`. Create it with your organisation's normal procedure; its
  user knows how to log in (password or SSH key).
- **Someone with `sudo`** for every delivery. The runtime user never installs
  packages.
- **The delivery** from the supplier, on a medium or copied to the server:
  - `myproduct-tools-<version>-1.noarch.rpm` (the commands),
  - one `myproduct-<component>-<version>-<version>-1.noarch.rpm` per component,
    already built by the supplier for your environment (you select nothing),
  - the credentials (certificates, keys, passwords), in folders named
    `<component>/credentials/...`, for example
    `platform/credentials/web/web.crt` and `platform/credentials/web/web.key`.
    The supplier tells you which files each component needs; you do not
    rename or move them.

**Security in phase 1:** the RPMs are not signed yet. Whoever can change a
delivery can run code on the server as administrator. Accept deliveries only
on media from the supplier that stayed in trusted hands.

## 1. Mount the delivery

**Server, administrator.** Insert the medium, then list the disks:

<!-- operator: find-medium -->
```sh
lsblk
```

**Expected:** a list of disks. The medium is the one you just inserted, for
example `sdb1` (USB, size of the stick) or `sr0` (DVD). Mount it read-only:

<!-- operator: mount -->
```sh
sudo mount -o ro /dev/sdb1 /mnt
ls /mnt
```

If `mount` says the medium is already mounted, continue when `ls /mnt` shows
the delivery.
**Expected:** the RPM files and the component folders with credentials. If
the delivery was copied to the server instead (for example with `scp`), use
that directory wherever this manual says `/mnt`.

## 2. Install the tools (once per server)

**Server, administrator.**

<!-- operator: tools -->
```sh
sudo dnf --disablerepo='*' --setopt=localpkg_gpgcheck=0 install /mnt/myproduct-tools-*.rpm
```

Answer `y` when dnf asks. **Expected:** `Complete!`. If dnf names a missing
package, install that package from the OS media and repeat this command.
`--setopt=localpkg_gpgcheck=0` is needed because phase 1 RPMs are unsigned.
Later deliveries update the tools by themselves in step 3.

## 3. Install the delivery (every delivery)

**Server, administrator.**

<!-- operator: admin -->
```sh
sudo myproduct-admin /mnt
```

The first time it asks two questions; later it asks nothing:

```text
Runtime account (an existing login account without sudo): produser
HTTPS port [8443]:
```

Press Enter to accept a value in brackets. Installing large releases can take
several minutes. **Expected:** lines starting with
`[OK]`, among them `[OK] preflight`, `[OK] installed myproduct-...` for each
new component and `[OK] produser can run ...`, and finally:

```text
[OK] next: log in as produser (at the console, or ssh produser@<server>) and run myproduct
PASS: myproduct-admin completed
```

If it prints `Preflight stopped before any change:`, nothing was changed.
Each line below it names what is missing and who fixes it; when that is done,
run the same command again.

The command also removes old releases that the runtime user no longer uses,
and says so (`[OK] removed ...`). An older release that is still in use is
listed as `kept`; that is normal.

## 4. Deliver the credentials

**Server, administrator**, when the delivery contains credentials (the first
installation, and when the supplier sends new ones):

<!-- operator: credentials -->
```sh
sudo myproduct-admin --credentials /mnt
```

**Expected:** one `[OK] incoming/...` line per file, then
`[OK] credentials are in /var/lib/myproduct/incoming for produser` and
`PASS: myproduct-admin completed`. The files are copied for the runtime user;
their contents are never shown. A repeat says `is already there`. The
runtime user's next installation of that component takes them (step 6); for
a component that is already installed, that is `myproduct <component>`.

Then remove the medium:

<!-- operator: umount -->
```sh
sudo umount /mnt
```

**Alternative without a medium:** the runtime user copies the credential
folders from a laptop, one `scp -r` per component folder, run in the laptop
folder that holds the delivered component folders, for example:

<!-- operator: credentials-scp -->
```sh
scp -r platform produser@server1.example.org:/var/lib/myproduct/incoming/
```

## 5. Log in as the runtime user

Log out of the administrator account (`exit`), then log in as `produser`:

- **at the console:** at the login prompt;
- **from a laptop:** `ssh produser@server1.example.org`.

Do not use `su` or `sudo` to become the runtime user.

## 6. Install the components

**Server, runtime user.**

<!-- operator: runtime -->
```sh
myproduct
```

The first time it asks two questions:

```text
Public address (https://<host name>:<port>) [https://server1.example.org:8443]:
IP address the server listens on [192.0.2.10]:
```

The public address is what users type in the browser; it must match the web
certificate. Press Enter to accept a suggestion. **Expected:** the
installation of each component, with `[OK] <component> <version> installed`,
then a status table in which every component is `active` and `installed`,
`Pending: none`, and finally `PASS: myproduct completed`. The first
installation takes a few minutes.

Open `https://server1.example.org:8443/` in a browser on a computer that
trusts your organisation's certificates to check it from the user's side.

## 7. Everyday tasks

| Task | Who | What to do |
| --- | --- | --- |
| Check the status | runtime user | `myproduct`. When nothing is new it installs nothing, restarts nothing and shows the status table. |
| After a reboot | nobody | The services start by themselves. Check with `myproduct` as the runtime user. |
| New delivery (upgrade) | administrator, then runtime user | Steps 1 and 3, and 4 if it contains credentials; without credentials, still remove the medium (`sudo umount /mnt`). Then steps 5 and 6. Settings, credentials and data are kept, and nothing is asked again. |
| Remove old releases | administrator | Nothing extra: step 3 removes them once the runtime user has installed the newer version. To do it right after an upgrade, repeat step 3. |
| Change a setting | runtime user | Edit `/var/lib/myproduct/state/<component>/config.yaml` (for example with `vi`), then `myproduct <component>`. After changing the gateway's public address, run `myproduct <component>` for every component, the gateway first. The HTTPS port cannot be changed after installation. |

## If a command stops

Every command in this manual can be repeated. After an interruption (power
loss, a closed session, Ctrl+C) or after fixing the cause, run **the same
command again**; finished work is kept and not done twice.

The message starts with `ERROR:` and says what to do. The common ones:

| Message (beginning) | Who | What to do, then repeat the same command |
| --- | --- | --- |
| `Interrupted; run the same command again to continue` (after Ctrl+C) | you | Run the same command again. |
| dnf: `nothing provides ...` (step 2) | administrator | Install the named OS package from the OS media. |
| `Preflight stopped before any change:` | the person named in each line | Fix each line. |
| `- Account produser does not exist` | account administrator | Create the account. |
| `- Set subj_cache_size = 16381 ...` | security administrator | `sudo vi /etc/fapolicyd/fapolicyd.conf`, set the line `subj_cache_size = 16381`, save, then `sudo systemctl restart fapolicyd`. |
| `... is older than the installed ...` | supplier | Deliver the current version or a newer one. |
| `... is installed with other content ...` | supplier | Deliver a new version; one version always has one content. |
| `produser cannot run ...; fapolicyd must trust ...` | security administrator | Check that `rpm-plugin-fapolicyd` is installed and fapolicyd trusts the RPM database. |
| `Host preparation stopped` | administrator | The lines above it say what failed. |
| `... already exist with other content; nothing was copied` (step 4) | credential provider | Confirm which file is right. If the delivered file is right, the runtime user removes the old one, for example `rm /var/lib/myproduct/incoming/platform/credentials/web/web.key`. |
| `No <component>/credentials/ directory in /mnt` (step 4) | supplier | The medium has no credentials in the layout under "Before you begin". |
| `This host is not prepared for myproduct` | administrator | Step 3 first. |
| `myproduct runs as produser on this host`, or `Run myproduct as the runtime account, not as root` | you | Log in as the runtime user (step 5). |
| `... differ from the files in /var/lib/myproduct/state/...` (step 6) | credential provider | A newly delivered credential differs from the one in use. Nothing was copied. Confirm which is right; the runtime user removes the wrong copy in `/var/lib/myproduct/incoming/...`. |
| `status reports an incomplete or inactive component` (step 6) | runtime user | Run `myproduct` again a minute later; a service may still be starting. If it stays, ask for help (see below). |
| `deploy.sh ... stopped; fix what it names` (step 6) | runtime user | The `ERROR:` line above it names the cause. The next `myproduct` resumes the unfinished component first. |
| `WARNING: older releases kept ...` | administrator | Normal before the runtime user's first `myproduct`; a later step 3 removes them. If it repeats afterwards, ask for help with the reason it names; the releases are kept. |
| `WARNING: ... holds delivered files that <component> does not use yet` | runtime user | Run the command it names, `myproduct <component>`. |
| `... is left after removing ...` or `... has no installed release package` | administrator, supplier | Files that no package owns remain in a release folder; every later step 3 stops here until it is resolved. Ask the supplier before deleting anything. |

### Repair the tools

Only when `sudo myproduct-admin` itself does not start (for example
`command not found`, or a Python error instead of `ERROR:`). With the
delivery mounted (step 1):

<!-- operator: tools-version -->
```sh
rpm -q myproduct-tools
```

| It prints | Then |
| --- | --- |
| `package myproduct-tools is not installed` | step 2 |
| the same version as the file in `/mnt` | the command below |
| an older version than the file in `/mnt` | step 2 |
| two lines, or a newer version than the file in `/mnt` | stop; ask the supplier |

<!-- operator: tools-reinstall -->
```sh
sudo dnf --disablerepo='*' --setopt=localpkg_gpgcheck=0 reinstall /mnt/myproduct-tools-*.rpm
```

Answer `y`. Then repeat step 3.

## Asking for help

Send the step number, the command and the `[OK]`, `WARNING:` and `ERROR:`
lines it printed; they never contain passwords or keys. The administrator can
add the product's start and result lines:

<!-- operator: help-journal -->
```sh
sudo journalctl -t myproduct -n 30 --no-pager
```

Do not send `config.yaml`, credential files, the output of `podman inspect`
or a complete journal.
