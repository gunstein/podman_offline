# Paper-first installation: lab probes (backlog 69)

Status: lab recipe, 2026-10-25; **not run yet**. It answers the four questions
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
chmod 0755 /var/tmp/p69/setup.sh
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
bash < /var/tmp/p69/setup.sh
```

Optional, closer to real media: copy `setup.sh` to a USB stick, mount it
(`sudo mount /dev/sdX1 /mnt`) and repeat the first four lines with `/mnt/setup.sh`.
Real DVD/USB mounts may add `noexec`; record `findmnt /mnt`.

Then the audit check above. Expected from the item 54 lab finding: Python is
denied even for `sha256sum`; shell is the open question.

## 2. Is a tool installed from an RPM trusted?

### 2a. Build a small signed test RPM (on the laptop, not the server)

Needs Podman and network on the laptop. Creates `p69-hello-unsigned.rpm`,
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
printf "print(\"hello-from-rpm-python\")\n" > %{buildroot}/usr/local/libexec/p69/hello.py
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
sudo rpm --import RPM-GPG-KEY-p69
rpm -K p69-hello-signed.rpm
sudo dnf --disablerepo='*' install -y ./p69-hello-signed.rpm
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
dnf --dump-main-config 2>/dev/null | grep -E '^(gpgcheck|localpkg_gpgcheck)' || sudo dnf config-manager --dump | grep -E 'gpgcheck'
rpm -K p69-hello-unsigned.rpm
sudo dnf --disablerepo='*' install -y ./p69-hello-unsigned.rpm
sudo dnf remove -y p69-hello
sudo dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 install -y ./p69-hello-unsigned.rpm
cp p69-hello-signed.rpm tampered.rpm
printf 'X' | dd of=tampered.rpm bs=1 seek=$(( $(stat -c %s tampered.rpm) - 200 )) conv=notrunc
rpm -K tampered.rpm
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

### 4a. `sudo -iu` (expected to be insufficient)

```sh
sudo -iu p69user
echo "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"
systemctl --user status --no-pager | head -n 3
exit
```

### 4b. `machinectl shell`

```sh
sudo machinectl shell p69user@
echo "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"
loginctl session-status | head -n 5
systemctl --user status --no-pager | head -n 3
systemd-run --user --unit p69-probe /bin/echo hello-user-journal
sleep 2
journalctl --user -u p69-probe --no-pager
id
exit
```

### 4c. Real console login (reference)

At the VM console: log out, log in as `p69user`, then the same five checks as
in 4b. Record whether `machinectl shell` behaves like the console login.

Note: `machinectl` is in `systemd-container`; record `rpm -q systemd-container`
if the command is missing.

## Cleanup

Revert the VM to its snapshot. If that is not possible:

```sh
sudo dnf remove -y p69-hello
sudo rpm -e $(rpm -q gpg-pubkey --qf '%{NAME}-%{VERSION}-%{RELEASE} %{SUMMARY}\n' | awk '/p69/ {print $1}')
sudo loginctl disable-linger p69user
sudo userdel -r p69user
rm -rf /var/tmp/p69
```

## Results

Not run yet. For each part record: date, VM and snapshot, `rpm -q` versions,
the exact commands that differed from this recipe, outputs and exit codes, and
the FANOTIFY/AVC lines. Then answer:

| Question | Answer |
| --- | --- |
| 1. Untrusted `bash setup.sh` from delivery media | pending |
| 2. RPM-installed shell/Python trusted without extra rules | pending |
| 3. Local RPM signature: default `dnf` behavior, `localpkg_gpgcheck`, `rpm -K` clarity | pending |
| 4. `machinectl shell` equivalent to a real login for `systemctl --user`/`journalctl --user` | pending |
