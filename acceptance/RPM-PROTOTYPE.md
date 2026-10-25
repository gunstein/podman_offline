# RPM delivery prototype (backlog 69)

Status: lab prototype, 2026-10-25; **not built or run yet**. It tests whether
signed RPMs make the closed-network, paper-manual installation simple and
robust against fapolicyd policy differences, before a design for
[backlog 69](../BACKLOG.md#69-paper-first-installation-for-closed-networks) is
chosen. It is not a product feature: nothing in `deployment/`, `scripts/` or
the bundles changes, and the existing `release.py` flow stays the supported one.

## What the prototype does

`rpm-prototype/build-rpms.sh` takes built offline bundles and, in an Oracle
Linux 9 container, writes `dist/rpm/`:

| File | Content |
| --- | --- |
| `<product>-<component>-<version>-<version>-1.noarch.rpm` (package name `<product>-<component>-<version>`) | the bundle's release tree, installed unchanged at `/var/lib/<product>/releases/<product>-<component>-<version>/`; the version is part of the package name so old and new versions install side by side |
| `<product>-host-tools-<v>-1.noarch.rpm` | `/usr/sbin/<product>-host-setup` and a copy of `scripts/prepare-host.sh` |
| `RPM-GPG-KEY-<product>` | public half of a lab-only signing key kept in `~/.podman-offline-rpm-gnupg` |

Before packaging it checks each archive's `.sha256` (when present), the inner
`checksums.sha256`, the archive layout and `bundle.yaml`, rejects links and
special files, and sets the modes `release.py` publishes (0755 directories,
0755/0644 files). rpmbuild's automatic processing (shebang rewriting, bytecode,
stripping, generated dependencies) is disabled so files are installed byte for
byte.

`<product>-host-setup` (run with sudo) asks for the runtime account and port if
not given, checks that the account exists, is an ordinary UID and has no sudo,
enables the persistent journal when journald policy allows it, then runs the
packaged `prepare-host.sh`. Safe to run again.

Release trust comes from the RPM database (`trust = rpmdb`), so there is no
`fapolicyd-cli --file add`, no stdin bootstrap and no `release.py` on the
server. The runtime flow (`deploy.sh init-layout`, config, credentials,
`validate`, `install`) is unchanged.

Not covered compared with `release.py setup`: product key pinning per product
(replaced by the RPM key), immutable release records and exact-trust waits,
the OS/package/space/subject-cache preflight (prepare-host.sh still warns about
the cache), and `retire` (replaced by `dnf remove`).

## 1. Build (machine with Podman and network)

Use bundles from an existing acceptance run, for example:

```sh
find ~/podman-offline-acceptance-runs/main-20261023-1731-app1 -name '*-offline.tar.gz'
```

Build RPMs for the first installation and one upgrade:

```sh
rpm-prototype/build-rpms.sh <path>/myproduct-platform-0.4.12-offline.tar.gz \
    <path>/myproduct-identity-0.4.12-offline.tar.gz \
    <path>/myproduct-platform-0.4.13-offline.tar.gz
ls -l dist/rpm
```

Write the printed key fingerprint on the paper manual. Copy `dist/rpm/` to a USB
stick, or to the server with `scp`.

## 2. Install on the server (administrator, paper manual)

Use a fresh disposable PROD VM at `clean-agent`. Take it off the network if the
test is meant to be fully offline. Create the runtime account first (`drift`
below): `sudo useradd -m drift`, `sudo passwd drift`.

Type one line at a time:

```sh
sudo mount /dev/sdb1 /mnt
cd /mnt
gpg --show-keys RPM-GPG-KEY-myproduct
sudo rpm --import RPM-GPG-KEY-myproduct
rpm -K *.rpm
sudo dnf --disablerepo='*' install ./myproduct-host-tools-*.rpm ./myproduct-platform-0.4.12-*.rpm ./myproduct-identity-0.4.12-*.rpm
sudo myproduct-host-setup
```

Expected: the fingerprint matches the paper; every `rpm -K` line ends with
`digests signatures OK` (`digests OK` alone means unsigned); `dnf` installs
three packages; `myproduct-host-setup` asks for `drift` and the port, then ends
with `PASS: host ready for myproduct`.

## 3. Runtime user

Log in as `drift` at the console, or `ssh drift@localhost` from the
administrator session. Then follow `docs/PRODUCTION-INSTALL.md` from step 4
(`deploy.sh init-layout`), using the release paths under
`/var/lib/myproduct/releases/`.

## 4. Checks

As `drift`: `deploy.sh status`, `systemctl --user status myproduct-platform`,
`journalctl --user -u myproduct-identity -n 5`, the HTTPS checks from the manual.
As administrator:

```sh
rpm -qa 'myproduct*'
sudo fapolicyd-cli --dump-db | grep -c /var/lib/myproduct/releases
sudo ausearch -m FANOTIFY,AVC -ts boot 2>&1 | tail -n 20
```

The `--dump-db` count shows whether any release file was added to the `file`
trust database (expected 0: trust comes from rpmdb).

## 5. Upgrade and retire

Administrator: `rpm -K ./myproduct-platform-0.4.13-*.rpm`, then
`sudo dnf --disablerepo='*' install ./myproduct-platform-0.4.13-*.rpm`. Both
platform versions are now installed. Runtime user: `validate` and `install` from
the 0.4.13 release. After checks, administrator:
`sudo dnf remove myproduct-platform-0.4.12`.

## 6. Optional: strict fapolicyd profile

Repeat on a VM with `trust = rpmdb`, `integrity = sha256` and rules 1, 2 and 12
removed (see backlog 69, "Policy variation").

## Results

Not run yet. Record: commit, bundle versions, VM state, whether the network was
off, the exact commands that differed, outputs of each expected line, the
FANOTIFY/AVC lines, and how the paper-manual steps felt to type.
