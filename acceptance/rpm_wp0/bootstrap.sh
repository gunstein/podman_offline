#!/usr/bin/env bash
# Probe C: OS-only paper bootstrap; no product implementation is supplied here.
# Expected negative checks belong only to C, never to the positive run A.
set -euo pipefail
export LC_ALL=C
input=/var/tmp/wp0-input
fail() { echo "FAIL: C/$1"; exit 1; }
pass() { echo "PASS: C/$1"; }

# Literal paper commands, with the existing prototype's package/key names and
# the SCP delivery directory substituted for mounted media. Empty it every run.
rm -rf /root/pkg
mkdir -m 0700 /root/pkg
cd /root/pkg
cp "$input/RPM-GPG-KEY-myproduct" "$input"/myproduct-host-tools-*.rpm .
gpg --show-keys RPM-GPG-KEY-myproduct
fingerprint=$(gpg --batch --with-colons --show-keys RPM-GPG-KEY-myproduct | \
    awk -F: '$1=="fpr" {print $10; exit}')
test "$fingerprint" = "$(cat "$input/product-fingerprint")" || fail fingerprint
rpmkeys --dbpath /root/pkg/db --import RPM-GPG-KEY-myproduct

verify() {
    local result status=0
    result=$(rpmkeys --dbpath /root/pkg/db --define '_pkgverify_level all' -K "$1" 2>&1) || status=$?
    printf '%s\n' "$result"
    [[ $status == 0 && $(wc -l <<< "$result") == 1 && $result == *': digests signatures OK' ]]
}
verify myproduct-host-tools-*.rpm || fail product-signed
pass product-signed
rpm --import RPM-GPG-KEY-myproduct
dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 install -y ./myproduct-host-tools-*.rpm
rpm -V myproduct-host-tools
pass repair-not-installed

# A foreign key is deliberately imported globally: it must never authorize
# this product in the isolated database.
rpm --import "$input/foreign.asc"
for kind in unsigned foreign tampered-header tampered-payload; do
    cp "$input/$kind.rpm" "/root/pkg/$kind.rpm"
    if verify "/root/pkg/$kind.rpm"; then fail "accepted-$kind"; fi
    pass "refused-$kind"
done

# The approved product primary, with a signing subkey added in a disposable
# GNUPGHOME, still has exactly the fingerprint compared above. Use a fresh DB.
rm -rf /root/pkg/db
rpmkeys --dbpath /root/pkg/db --import "$input/product-subkey.asc"
cp "$input/product-subkey.rpm" .
verify /root/pkg/product-subkey.rpm || fail product-subkey
pass product-subkey
cp "$input/foreign-subkey.rpm" .
if verify /root/pkg/foreign-subkey.rpm; then fail accepted-foreign-subkey; fi
pass refused-foreign-subkey

# The paper's stop condition is exactly one pub line, not a Key ID match.
output=$(gpg --show-keys "$input/two-primary.asc")
printf '%s\n' "$output"
test "$(grep -c '^pub ' <<< "$output")" = 2 || fail two-primary-fixture
pass two-primary-stop-before-import

# Leftovers must be removed by the first paper command, including an old
# foreign-key DB and an obsolete package, before any glob can select them.
cp "$input/foreign.rpm" /root/pkg/obsolete.rpm
rpmkeys --dbpath /root/pkg/db --import "$input/foreign.asc"
rm -rf /root/pkg
mkdir -m 0700 /root/pkg
cd /root/pkg
cp "$input/RPM-GPG-KEY-myproduct" "$input"/myproduct-host-tools-*.rpm .
test ! -e obsolete.rpm && test ! -e db || fail leftovers
rpmkeys --dbpath /root/pkg/db --import RPM-GPG-KEY-myproduct
verify myproduct-host-tools-*.rpm || fail clean-repeat
pass leftovers-cleaned

# Tools repair, same delivered version. Damage only a packaged public module;
# rpm -V must observe it and reinstall must restore the package exactly.
rm /usr/libexec/myproduct-host-tools/scripts/prepare-host.sh
if rpm -V myproduct-host-tools; then fail damage-not-detected; fi
dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 reinstall -y ./myproduct-host-tools-*.rpm
rpm -V myproduct-host-tools
pass repair-same-version

# Establish a deliberately older prototype tools state, then use the paper's
# upgrade branch. This fixture is not a supported product migration.
dnf --disablerepo='*' remove -y myproduct-host-tools
cp "$input/older.rpm" .
verify /root/pkg/older.rpm || fail older-fixture-signature
dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 install -y ./older.rpm
test "$(rpm -q myproduct-host-tools --qf '%{VERSION}')" = 0.1 || fail older-fixture
dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 install -y ./myproduct-host-tools-*.rpm
rpm -V myproduct-host-tools
test "$(rpm -q myproduct-host-tools --qf '%{VERSION}')" = 0.202610250832 || fail repair-older-version
pass repair-older-version
pass complete
