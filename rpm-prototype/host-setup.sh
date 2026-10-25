#!/usr/bin/env bash
# @PRODUCT@-host-setup: prepare this host for @PRODUCT@ (backlog 69 lab prototype).
#
# Installed from the signed @PRODUCT@-host-tools RPM, so fapolicyd trusts it.
# Checks the runtime account, enables the persistent journal when the host's
# journald policy allows it, then runs the product's prepare-host.sh. Asks for
# values that are not given as options. Safe to run again.
set -euo pipefail
product=@PRODUCT@
tools=/usr/libexec/@PRODUCT@-host-tools
die() { echo "ERROR: $*" >&2; exit 1; }
usage="Usage: sudo $product-host-setup [--user ACCOUNT] [--port PORT]"

[[ $EUID == 0 ]] || die "run it as administrator: sudo $product-host-setup"
user=
port=
while [[ $# -gt 0 ]]; do
    case $1 in
        --user) [[ $# -ge 2 ]] || die "$usage"; user=$2; shift 2;;
        --port) [[ $# -ge 2 ]] || die "$usage"; port=$2; shift 2;;
        *) die "$usage";;
    esac
done
if [[ -z $user ]]; then
    read -r -p "Runtime account (existing login account without sudo): " user
fi
if [[ -z $port ]]; then
    read -r -p "HTTPS port [8443]: " port
    port=${port:-8443}
fi

echo "Checking account $user"
getent passwd "$user" >/dev/null \
    || die "account $user does not exist; create it with your normal procedure, then run $product-host-setup again"
uid=$(id -u "$user")
[[ $uid -ge 1000 && $uid -lt 61184 ]] \
    || die "account $user has UID $uid; use an ordinary login account (UID 1000-61183)"
policy=$(LC_ALL=C sudo -n -l -U "$user" 2>&1) || true
[[ $policy == *"is not allowed to run sudo"* ]] \
    || die "account $user has sudo rights, or the sudo policy could not be read; use an account without sudo"
echo "OK: $user is an ordinary account without sudo"

echo "Checking the journal"
settings=$(systemd-analyze cat-config systemd/journald.conf)
storage=$(sed -n 's/^[[:space:]]*Storage[[:space:]]*=[[:space:]]*//p' <<< "$settings" | tail -n 1)
split=$(sed -n 's/^[[:space:]]*SplitMode[[:space:]]*=[[:space:]]*//p' <<< "$settings" | tail -n 1)
case ${storage:-auto} in
    auto|persistent) ;;
    *) die "journald has Storage=$storage; ask the system administrator to allow persistent journals (Storage=auto or persistent)";;
esac
[[ ${split:-uid} == uid ]] \
    || die "journald has SplitMode=$split; ask the system administrator to use SplitMode=uid"
if [[ ! -d /var/log/journal ]]; then
    mkdir -m 0755 /var/log/journal
    echo "OK: persistent journal enabled for the whole host (uses space in /var/log)"
fi
systemd-tmpfiles --create --prefix /var/log/journal
journalctl --flush
echo "OK: journal"

echo "Preparing the host"
bash "$tools/scripts/prepare-host.sh" --port "$port" --user "$user"

echo
echo "PASS: host ready for $product"
echo "Installed releases:"
ls -1 "/var/lib/$product/releases"
echo "Next: log in as $user (at the console, or: ssh $user@localhost) and follow the manual."
