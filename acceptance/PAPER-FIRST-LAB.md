# Paper-first installation: lab probes (backlog 69)

Status: lab recipe, **run on 2026-10-25** on `todo-standby` (OL9.8); results at
the end. The recipe below includes the corrections made during that run. It answers the four questions
in [backlog 69](../BACKLOG.md#69-paper-first-installation-for-closed-networks)
before a design is chosen. These are manual probes, not product tests and not
part of the acceptance harness. Record the results at the end of this file.

Use a **disposable** OL9 PROD VM at the `clean-agent` snapshot (SELinux
Enforcing, fapolicyd active, firewalld active) and revert it afterwards. The
probes create a test account, a test RPM key and test files; nothing here touches
a product installation.

Throughout: run as the administrator account (`admin` below) unless a step says
otherwise. Copy each command's output, and after each part run:

```sh
sudo ausearch -m FANOTIFY,AVC -ts recent 2>&1 | tail -n 20
```

## 0. Baseline facts

```sh
cat /etc/oracle-release
rpm -q fapolicyd rpm dnf systemd
getenforce
systemctl is-active fapolicyd
sudo grep -E '^(integrity|trust|permissive)' /etc/fapolicyd/fapolicyd.conf
sudo grep -rh '%languages=' /etc/fapolicyd/rules.d/ | tr ',' '\n' | grep -E 'shell|python'
sudo fapolicyd-cli --list | grep -n languages
```

Record whether `text/x-shellscript` is in `%languages`; that decides whether
fapolicyd treats an untrusted shell script like an untrusted Python file.

## 1. Is an untrusted shell script on delivery media allowed to run?

Create test files where a delivery would put them:

```sh
mkdir -p /var/tmp/p69
printf '#!/bin/bash\necho hello-from-untrusted-shell\n' > /var/tmp/p69/setup.sh
printf 'echo hello-from-untrusted-noshebang\n' > /var/tmp/p69/plain.sh
printf 'print("hello-from-untrusted-python")\n' > /var/tmp/p69/probe.py
printf '#!/usr/bin/python3\nimport sys\nprint("hello-from-untrusted-python-shebang")\n' > /var/tmp/p69/probe2.py
chmod 0755 /var/tmp/p69/setup.sh
```

fapolicyd decides the file type from the content, not the name. Check what it
sees (`probe.py` without a shebang is plain text; `probe2.py` is Python):

```sh
sudo fapolicyd-cli --ftype /var/tmp/p69/probe.py
sudo fapolicyd-cli --ftype /var/tmp/p69/probe2.py
sudo fapolicyd-cli --ftype /var/tmp/p69/setup.sh
```

Run each line separately and record output and exit code (`echo $?`):

```sh
bash /var/tmp/p69/setup.sh
sudo bash /var/tmp/p69/setup.sh
/var/tmp/p69/setup.sh
sudo /var/tmp/p69/setup.sh
bash /var/tmp/p69/plain.sh
sha256sum /var/tmp/p69/setup.sh
python3 /var/tmp/p69/probe.py
sudo python3 /var/tmp/p69/probe.py
sha256sum /var/tmp/p69/probe.py
python3 /var/tmp/p69/probe2.py
sha256sum /var/tmp/p69/probe2.py
sudo python3 /var/tmp/p69/probe2.py
bash < /var/tmp/p69/setup.sh
```

Optional, closer to real media: copy `setup.sh` to a USB stick, mount it
(`sudo mount /dev/sdX1 /mnt`) and repeat the first four lines with `/mnt/setup.sh`.
Real DVD/USB mounts may add `noexec`; record `findmnt /mnt`.

Then the audit check above. Expected from the item 54 lab finding: Python is
denied even for `sha256sum`; shell is the open question.

## 2. Is a tool installed from an RPM trusted?

### 2a. Build a small signed test RPM (on the laptop, not the server)

Needs Podman and network on the machine that builds (in the 2026-10-25 run it was
the server itself, which still had network access at `clean-agent`). Creates `p69-hello-unsigned.rpm`,
`p69-hello-signed.rpm` and the public key `RPM-GPG-KEY-p69` in `~/p69`:

```sh
mkdir -p ~/p69 && cd ~/p69
podman run --rm -v "$PWD":/out:Z docker.io/library/oraclelinux:9 bash -c '
set -e
dnf -y -q install rpm-build rpm-sign gnupg2
mkdir -p ~/rpmbuild/SPECS
cat > ~/rpmbuild/SPECS/p69-hello.spec <<EOF
Name: p69-hello
Version: 1.0
Release: 1
Summary: Lab probe for backlog 69
License: none
BuildArch: noarch
%description
Lab probe.
%install
mkdir -p %{buildroot}/usr/local/sbin %{buildroot}/usr/local/libexec/p69
printf "#!/bin/bash\necho hello-from-rpm-shell\n" > %{buildroot}/usr/local/sbin/p69-hello
printf "#!/usr/bin/python3\nimport sys\nprint(\"hello-from-rpm-python\")\n" > %{buildroot}/usr/local/libexec/p69/hello.py
chmod 0755 %{buildroot}/usr/local/sbin/p69-hello
%files
/usr/local/sbin/p69-hello
/usr/local/libexec/p69/hello.py
EOF
rpmbuild -bb --quiet ~/rpmbuild/SPECS/p69-hello.spec
cp ~/rpmbuild/RPMS/noarch/p69-hello-1.0-1.noarch.rpm /out/p69-hello-unsigned.rpm
gpg --batch --pinentry-mode loopback --passphrase "" \
    --quick-gen-key "p69 lab key <p69@lab.invalid>" rsa3072 sign never
gpg --armor --export p69@lab.invalid > /out/RPM-GPG-KEY-p69
cp /out/p69-hello-unsigned.rpm /tmp/p69-hello-signed.rpm
rpm --define "_gpg_name p69@lab.invalid" --addsign /tmp/p69-hello-signed.rpm
cp /tmp/p69-hello-signed.rpm /out/
gpg --with-fingerprint --show-keys /out/RPM-GPG-KEY-p69
'
ls -l ~/p69
scp ~/p69/* admin@<prod>:/var/tmp/p69/
```

Write down the key fingerprint printed at the end: in a real delivery it would
be the value on paper.

### 2b. Install and run on the server

```sh
cd /var/tmp/p69
gpg --with-fingerprint --show-keys RPM-GPG-KEY-p69
rpm -K p69-hello-signed.rpm
sudo rpm --import RPM-GPG-KEY-p69
rpm -K p69-hello-signed.rpm
sudo dnf --disablerepo='*' install -y ./p69-hello-signed.rpm
sudo fapolicyd-cli --ftype /usr/local/libexec/p69/hello.py
p69-hello
sudo p69-hello
python3 /usr/local/libexec/p69/hello.py
sha256sum /usr/local/libexec/p69/hello.py
sudo fapolicyd-cli --dump-db | grep -c p69
```

Record whether the RPM-installed shell and Python files run and can be read
without extra rules, under the baseline `integrity` value from part 0. Then the
audit check.

## 3. How is a local RPM's signature checked, and what does the operator see?

Continue in `/var/tmp/p69`. Each line separately; record output and exit code:

```sh
sudo dnf config-manager --dump | grep -E '^(gpgcheck|localpkg_gpgcheck)'
rpm -K p69-hello-unsigned.rpm
sudo dnf remove -y p69-hello
sudo dnf --disablerepo='*' install -y ./p69-hello-unsigned.rpm
sudo dnf remove -y p69-hello
sudo dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 install -y ./p69-hello-unsigned.rpm
cp p69-hello-signed.rpm tampered.rpm
printf 'X' | dd of=tampered.rpm bs=1 seek=$(( $(stat -c %s tampered.rpm) - 200 )) conv=notrunc
rpm -K tampered.rpm
sudo dnf --disablerepo='*' install -y ./tampered.rpm
sudo dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 install -y ./tampered.rpm
```

Questions to answer: does `dnf install ./file.rpm` install an unsigned or
tampered local file by default; does `localpkg_gpgcheck=1` refuse it; is the
`rpm -K` output short and clear enough to be checked from a printed manual?
Does `dnf` work offline with `--disablerepo='*'`, and what happens without it?

## 4. Can one person switch roles without logging out?

Persistent journal first (as `setup` would do on a fresh host), then a test
account without sudo:

```sh
sudo mkdir -p /var/log/journal
sudo systemd-tmpfiles --create --prefix /var/log/journal
sudo journalctl --flush
sudo useradd -m -s /bin/bash p69user
sudo passwd p69user
sudo loginctl enable-linger p69user
sudo -l -U p69user
```

A command that switches user must be run **alone**; wait for the new prompt
before typing the next line. Pasting a block after it runs the rest as the new
user (this happened in the first attempt of 4a).

The checks used in each variant, typed one at a time in the new session:

```sh
echo "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"
loginctl session-status | head -n 5
systemctl --user status --no-pager | head -n 3
systemd-run --user --unit p69-probe /bin/echo hello-user-journal
journalctl --user -u p69-probe --no-pager
id
```

### 4a. `sudo -iu p69user` (expected to be insufficient)

Run `sudo -iu p69user`, then the checks, then `exit`.

### 4b. `ssh p69user@localhost` and `machinectl shell`

Run `ssh p69user@localhost` (password login; answer `yes` to the host key),
then the checks, then `exit`. `sudo machinectl shell p69user@` needs the
`systemd-container` package; record `rpm -q systemd-container`.

### 4c. Real console login (reference)

At the VM console (not a laptop terminal): log in as `p69user`, run the checks
except `systemd-run`, then `exit`. Expect `TTY: tty1` and no `Remote` line.

## Cleanup

Revert the VM to its snapshot. If that is not possible:

```sh
sudo dnf remove -y p69-hello
sudo rpm -e $(rpm -q gpg-pubkey --qf '%{NAME}-%{VERSION}-%{RELEASE} %{SUMMARY}\n' | awk '/p69/ {print $1}')
sudo loginctl disable-linger p69user
sudo userdel -r p69user
rm -rf /var/tmp/p69
```

## Results (2026-10-25)

Operator-run on PROD `todo-standby` at `clean-agent`, guided step by step;
outputs were shared in the conversation. Administrator `gunstein` (UID 1000),
test account `p69user` (UID 1001, no sudo: `sudo -l -U` reported "not allowed").

### Baseline (part 0)

OL9.8, SELinux Enforcing, fapolicyd-1.4.5-1.1.el9_8 active, rpm-4.16.1.3-40.el9,
dnf-4.14.0-34.0.1.el9_8, systemd-252-67.0.2.el9_8.4. `permissive = 0`,
`trust = rpmdb,file`, `integrity = none`. `%languages` contains Python but **not**
`text/x-shellscript`. Effective rules (`fapolicyd-cli --list`, first match wins):

```text
1. allow perm=any uid=0 : dir=/var/tmp/
2. allow perm=any uid=0 trust=1 : all
3. allow perm=open exe=/usr/bin/rpm : all
4. allow perm=open exe=/usr/bin/python3.9 comm=dnf : all
5. deny_audit perm=any pattern=ld_so : all
6. deny_audit perm=any all : ftype=application/x-bad-elf
7. allow perm=open all : ftype=application/x-sharedlib trust=1
8. deny_audit perm=open all : ftype=application/x-sharedlib
9. allow perm=execute all : trust=1
10. allow perm=open all : ftype=%languages trust=1
11. deny_audit perm=any all : ftype=%languages
12. allow perm=any all : ftype=text/x-shellscript
13. deny_audit perm=execute all : all
14. allow perm=open all : all
```

### Part 1: untrusted scripts

| Command | Result |
| --- | --- |
| `bash setup.sh`, `sudo bash setup.sh`, `./setup.sh`, `sudo ./setup.sh`, `bash < setup.sh`, `bash plain.sh`, `sha256sum setup.sh` | all ran (rule 12, or 1/2 for root) |
| `fapolicyd-cli --ftype` | `probe.py` (no shebang) `text/plain`; `probe2.py` `text/x-python`; `setup.sh` `text/x-shellscript` |
| `python3 probe.py`, `sha256sum probe.py` (no shebang, plain text) | ran (rule 14) |
| `python3 probe2.py`, `sha256sum probe2.py` as UID 1000 | **denied**, `Operation not permitted`; FANOTIFY `fan_info=B` (rule 11), `obj_trust=0` |
| `sudo python3 probe2.py` | ran (rule 1 or 2) |

### Part 2: RPM-installed files

The test RPM was built and signed in an `oraclelinux:9` container on the server
(fingerprint `4B54 004E B465 CB16 2BB6  7A4D 5760 70CC A1C8 6E70`; the displayed
fingerprint matched). `rpm -K` before import: `digests SIGNATURES NOT OK`; after
`rpm --import`: `digests signatures OK`. `dnf --disablerepo='*' install
./p69-hello-signed.rpm` worked offline. `/usr/local/libexec/p69/hello.py` is
`text/x-python`, yet `python3 hello.py` and `sha256sum hello.py` ran as UID 1000
and `p69-hello` ran: RPM-installed files are trusted through `rpmdb` with no
extra rule. No new FANOTIFY/AVC events.

### Part 3: local RPM signature checks

| Check | Result |
| --- | --- |
| Defaults (`dnf config-manager --dump`) | `gpgcheck = 1`, `localpkg_gpgcheck = 0` |
| `rpm -K` unsigned | `digests OK` (no "signatures"; easy to mistake for success) |
| `dnf install ./unsigned.rpm` (defaults) | **installed without warning** |
| `dnf install --setopt=localpkg_gpgcheck=1 ./unsigned.rpm` | refused: `Package ... is not signed`, `Error: GPG check FAILED` |
| `rpm -K` tampered (header byte) | `error: ... region trailer: BAD` |
| `dnf install ./tampered.rpm`, with or without the option | refused: `Can not load RPM file` |

A tampered payload byte (not only the header) was not tested.

### Part 4: role switch for one person

| Variant | Session | `systemctl --user` | `journalctl --user` |
| --- | --- | --- | --- |
| `sudo -iu p69user` | none (showed the admin's session) | `Failed to connect to bus: No medium found` | no entries |
| `sudo machinectl shell p69user@` | not available: `systemd-container` not installed | – | – |
| `ssh p69user@localhost` | own session, `Remote: ::1`, `XDG_RUNTIME_DIR=/run/user/1001` | `State: running` | shows `hello-user-journal`, also in a later session |
| Console login (tty1) | own session, `TTY: tty1` | `State: running` | shows the entry (reported by the operator) |

### Answers

| Question | Answer |
| --- | --- |
| 1. Untrusted `bash setup.sh` from delivery media | **Allowed** for everyone by the default policy (rule 12); root may also run untrusted Python (rules 1/2). Only non-root opening of untrusted Python (and other `%languages`) is denied. fapolicyd therefore does not protect a delivered shell script; authenticity must come from a signature check. Stricter local policies may differ. |
| 2. RPM-installed shell/Python trusted without extra rules | **Yes**, through `trust = rpmdb`, with `integrity = none`. |
| 3. Local RPM signature | `dnf` does **not** check local files by default (`localpkg_gpgcheck = 0`); with the option it refuses unsigned files clearly. `rpm -K` must show the words `signatures OK`; `digests OK` alone means unsigned. Tampered headers are refused either way. |
| 4. One person switching roles | `sudo -iu` is insufficient; `machinectl` needs an extra package; **`ssh <runtime>@localhost`** and a console login both give a real session with working `systemctl --user` and user journal. |

Paper-manual lessons from the run: a user-switch command must stand alone; long
pasted blocks were split and partly run in the wrong session.
