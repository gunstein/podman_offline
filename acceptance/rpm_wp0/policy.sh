#!/usr/bin/env bash
# Read-only effective policy evidence. Run as root on the disposable PROD VM.
set -euo pipefail
test "$(getenforce)" = Enforcing
systemctl is-active fapolicyd firewalld
cat /etc/oracle-release
rpm -q rpm dnf gnupg2 fapolicyd rpm-plugin-fapolicyd
rpm -q dnf-plugins-core || test "$?" = 1
echo '=== Effective rules ==='
fapolicyd-cli --list
echo '=== fapolicyd.conf ==='
cat /etc/fapolicyd/fapolicyd.conf
echo '=== RPM filters ==='
find /etc/fapolicyd -maxdepth 1 -name '*filter*' -type f -exec cat {} +
echo '=== RPM plugin configuration ==='
rpm --eval '%{__transaction_fapolicyd}'
