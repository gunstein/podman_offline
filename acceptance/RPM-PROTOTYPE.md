# RPM delivery prototype (backlog 69)

Status: lab prototype, 2026-10-25; **built and run once on the lab** (results
at the end; network on, default fapolicyd policy). It tests whether
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

Use bundles from an existing acceptance run whose bundles match the manual
(they ship `deploy.sh`, `init-layout` and `status`, from 2026-10-24 on), for
example:

```sh
find ~/podman-offline-acceptance-runs/host65-20261024-144821-app1 -name '*-offline.tar.gz'
```

Older bundles (for example `main-20261023-1731-app1`, which ships `deploy`
without `init-layout`) package and install, but the runtime user's steps then
fail at `init-layout`. The build script does not detect this.

Build RPMs for the first installation and one upgrade:

```sh
rpm-prototype/build-rpms.sh <path>/myproduct-platform-0.4.12-offline.tar.gz \
    <path>/myproduct-identity-0.4.12-offline.tar.gz \
    <path>/myproduct-platform-0.4.13-offline.tar.gz
ls -l dist/rpm
podman run --rm -v "$PWD/dist/rpm":/r:ro,Z docker.io/library/oraclelinux:9 bash -c 'rpm -qpR /r/*.rpm'
```

The last line checks that no RPM has generated dependencies (only `rpmlib(...)`
lines); it runs in the build image because a non-RPM laptop has no `rpm`.
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
sudo fapolicyd-cli --dump-db | grep /var/lib/myproduct/releases | awk '{print $1}' | sort | uniq -c
sudo ausearch -m FANOTIFY,AVC -ts boot 2>&1 | tail -n 20
```

`--dump-db` lists every trusted file with its source, including rpmdb entries,
so release files do appear. Expected: a single `rpmdb` line and no `file` line
(trust comes from the RPM database, nothing was enrolled with
`fapolicyd-cli --file add`).

## 5. Upgrade and retire

Administrator: `rpm -K ./myproduct-platform-0.4.13-*.rpm`, then
`sudo dnf --disablerepo='*' install ./myproduct-platform-0.4.13-*.rpm`. Both
platform versions are now installed. Runtime user: `validate` and `install` from
the 0.4.13 release. After checks, administrator:
`sudo dnf remove myproduct-platform-0.4.12`.

## 6. Optional: strict fapolicyd profile

Repeat on a VM with `trust = rpmdb`, `integrity = sha256` and rules 1, 2 and 12
removed (see backlog 69, "Policy variation").

## Results (2026-10-25)

Operator-run by the product owner, guided step by step; outputs were shared in
the conversation. This is one manual lab run, not an automated or repeated
verification.

| Item | Value |
| --- | --- |
| Prototype commit | `61e2711` (branch `claude/friendly-mendel-8u3bqs`); `prepare-host.sh` in host-tools came from this checkout |
| Bundles (run 2) | platform 0.4.12, identity 0.4.12, platform 0.4.13 from `host65-20261024-144821-app1` (bundles built at `2d36d71`, that run CLEAN PASS) |
| Build | laptop (Ubuntu), rootless Podman, `oraclelinux:9`; new lab key, fingerprint `4255 84C8 3A44 FFC9 F7E5  E1A4 E202 1B0C C1DD 70E3` (kept for run 2) |
| PROD | `todo-standby` (OL9.8) at `clean-agent`, SELinux Enforcing, fapolicyd-1.4.5 with `rpm-plugin-fapolicyd`, `trust = rpmdb,file`, `integrity = none`, default rules |
| `subj_cache_size` | **4099 left unchanged** (operator's choice, to see the prototype on the default; the product requires 16381) |
| Network | **on** throughout (console work was too slow); transfer by `scp` to `/var/tmp/myproduct-upload`; USB/DVD and offline not tested |
| Accounts | administrator `gunstein` (sudo); runtime `drift` (UID 1001, created with `useradd -m`/`passwd`, no sudo, no extra groups), logged in with `ssh drift@192.168.0.108` from the laptop |

### Run 1: old bundles (stopped)

With the bundles from `main-20261023-1731-app1` the build, signatures, `dnf`
install and `myproduct-host-setup` all passed as in run 2, but the runtime
user's first step failed: `deploy.sh: No such file or directory`. Those bundles
predate the `deploy.sh` rename (`88f3110`), `init-layout` and `status`, and ship
an older manual. The VM was reverted to `clean-agent` and the RPMs rebuilt from
the `host65` bundles (same key). Section 1 now names a matching run.

### Build (laptop)

| Check | Expected | Actual |
| --- | --- | --- |
| `build-rpms.sh` | four RPMs, key, fingerprint | as expected; only `warning: Could not set GPG_TTY` (once per signature, harmless); no rpmbuild errors (`%files`, shared `/var/lib/myproduct` ownership, 220 MB identity payload, `w3T.zstdio` all fine) |
| `ls -l dist/rpm` | 5 files | host-tools 14 kB, platform 23.7 MB each, identity 230.6 MB, key 1.3 kB |
| `rpm -qpR` | only `rpmlib(...)` | 4 × (`CompressedFileNames`, `FileDigests`, `PayloadFilesHavePrefix`, `PayloadIsZstd`); run in the build image (no `rpm` on the laptop) |

### Administrator (server)

| Command | Expected | Actual |
| --- | --- | --- |
| `gpg --show-keys` | fingerprint as on paper | matched (`425584C8...C1DD70E3`, printed without spaces) |
| `sudo rpm --import`, `rpm -K *.rpm` | `digests signatures OK` × 4 | as expected |
| `sudo dnf --disablerepo='*' install` (3 files) | 3 packages, no dependencies | 3 from `@commandline`, no dependencies, no repository metadata; 243 MB, 716 MB installed (image archives stored uncompressed) |
| `sudo myproduct-host-setup` (answers `drift`, Enter) | `PASS: host ready for myproduct` | as expected, including the `subj_cache_size is 4099` warning, persistent journal enabled, firewall `success` × 2, both releases listed |
| `rpm -qa 'myproduct*'` | 3 packages | as expected |
| `--dump-db` release entries by source | rpmdb only | `57 rpmdb`, no `file` (the recipe's original "expected 0" for `grep -c` was wrong and is corrected above) |
| `sudo ausearch -m FANOTIFY,AVC -ts boot` | no denials | `<no matches>` (after install, and again after upgrade and removal) |

### Runtime user (`docs/PRODUCTION-INSTALL.md` steps 4–8, pasted)

| Step | Expected | Actual |
| --- | --- | --- |
| `id`, `systemctl --user is-system-running`, `ls -l /var/lib/myproduct` | own session, no groups; root `releases` 0755, own 0700 dirs | as expected |
| init-layout | `[OK] Bootstrap ready` | as expected: the runtime user's Python from RPM-installed files ran under fapolicyd without rules or `file` trust |
| gateway-config | config created, settings saved | as expected |
| credentials-transfer (laptop) | 7 files | first attempt stopped at `runtime: unbound variable` (values block not run on the laptop; nothing copied); repeat copied 7 files with two password prompts |
| gateway-credentials, gateway-install | healthy service | `podman load` from the RPM release, `1 containers running and healthy`, no `203/EXEC` despite cache 4099 |
| gateway-check | `204` | `204` |
| identity-config, identity-install | both healthy | database password generated, both images loaded, identity 2 containers healthy, platform restarted healthy |
| identity-check | `200` | `200` |
| status block, identity `is-active`/journal | complete/active, journal readable | `platform 0.4.12` and `identity 0.4.12` `active installed`, `Pending: none`; journal JSON readable without sudo. Platform logs two `PRIORITY 3` lines per liveness probe: nginx `[notice] signal 17 (SIGCHLD)` / `unknown process ... exited with code 0` on stderr (noise, unrelated to RPM) |

### Upgrade and retire

| Command | Expected | Actual |
| --- | --- | --- |
| `rpm -K`, `sudo dnf ... install ./myproduct-platform-0.4.13-*.rpm` | `Installing:` (not `Upgrading`) | as expected; `rpm -qa` shows 0.4.12 and 0.4.13 |
| runtime user: validate/install from 0.4.13 (one pasted block, also checking retention) | healthy, config and key kept | `1 containers running and healthy`, `config-retained` (sha256 of `config.yaml`), `key-retained` (`cmp`), status `platform 0.4.13` / `identity 0.4.12` active, `Pending: none`, `livez 204` |
| `sudo dnf --disablerepo='*' remove -y myproduct-platform-0.4.12` | removed, services active | `Complete!`; `systemctl --user -M drift@ is-active` both `active` |

### Fixes and deviations

- `rpm-prototype/` code: **no changes**. Recipe corrections in this file only:
  matching bundle run, `rpm -qpR` in the build image, `--dump-db` expectation.
- Deviations from the recipe/manual: network on; `subj_cache_size` 4099; manual
  step 3 not repeated for the upgrade (the RPM replaces publication);
  retirement by `dnf remove` instead of `release.py retire`; the upgrade and
  retirement checks were pasted as one block each to save time.

### Findings

1. **fapolicyd:** with the default policy, RPM delivery works end to end with
   no rule change and no `file` trust: root and the runtime user run the
   packaged shell and Python, Podman reads the image archives. The strict
   profile (section 6) was **not** tested.
2. **Signature gate:** `dnf install ./x.rpm` does not check signatures
   (`localpkg_gpgcheck = 0`, see [PAPER-FIRST-LAB.md](PAPER-FIRST-LAB.md));
   `rpm -K` is the only gate in this recipe. A design should enforce it
   (`--setopt=localpkg_gpgcheck=1` or a local repository with `gpgcheck=1`).
3. **`dnf remove` has no guard:** it would equally remove the release a running
   service uses; `release.py retire` has no RPM equivalent here.
4. **Missing preflight:** host-setup only warns about `subj_cache_size`; with
   4099 no `203/EXEC` occurred in this one run, which does not show it is safe.
5. **Bundle/manual drift is not detected** by the build (run 1).
6. `prepare-host.sh` still ends with "create ~/.myproduct/myproduct.env",
   which contradicts the manual's `init-layout`; `init-config identity` says
   "edit config" although nothing needs editing.

### Paper-manual assessment

Administrator, run 2: 11 commands (2 on the laptop, 9 on the server) for the
first installation and 3 for upgrade/retire, each one line; the longest is the
`dnf install` line (about 130 characters, with `'*'` and globs); host-setup
asked two questions. Comparing the fingerprint worked (the paper groups it in
fours, gpg prints it in one block). This replaces the manual's tool bootstrap,
transfer and setup blocks (about 3 800 characters) and is typeable from paper.

Runtime user: **not typeable from paper.** Steps 4–7 on the server are about
77 lines and 3 670 characters (values block 569, gateway-config 603 with an
embedded Python program, gateway-credentials 549, identity-config 1 098 with
`case` and loops, two `curl --resolve ... sed -E` checks of about 200 each),
plus the credential transfer on the laptop (11 lines) and the values block
again on every machine and session. The product owner objected at the values
block ("we cannot have it like that"); the run continued by pasting. Hard
points: remembering the values block per session and machine (one failure),
what "change the version in the values block" means, and the length of the
whole session. With RPMs the release paths are fixed, so a packaged command
on `PATH` (for example `myproduct init-config platform` asking for origin and
port, `myproduct add-credentials`, `myproduct install platform` including the
health check) could reduce the runtime user's part to about eight short
commands; that is design work for backlog 69/66, not part of this prototype.

Process: the guided manual session was long and is not
repeatable often. Once a design is chosen, build, install, upgrade, retire and
the fapolicyd checks (also under the strict profile) belong in the acceptance
harness; manual sessions should be reserved for paper typeability and the
human trial (item 68).

### Not tested

Offline network, USB/DVD media, console-only work, the strict fapolicyd
profile (section 6), `subj_cache_size = 16381`, reboot (manual step 8 boot
check), identity upgrade, interruption/retry, and a tampered or unsigned RPM
with this prototype.
