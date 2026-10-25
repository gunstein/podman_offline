#!/usr/bin/env bash
# Disposable WP0 signature fixtures; not a supplier build implementation.
set -euo pipefail
dnf -y -q install rpm-build rpm-sign gnupg2 >/dev/null
export GNUPGHOME=/key
product=$(gpg --batch --with-colons --list-keys | awk -F: '$1=="fpr" {print $10; exit}')
gpg --batch --armor --export "$product" > /out/product-primary.asc
mkdir -p /tmp/wp0-build
cat > /tmp/wp0-build/older.spec <<'SPEC'
Name: myproduct-host-tools
Version: 0.1
Release: 1
Summary: WP0 older tools repair fixture, not product code
License: none
BuildArch: noarch
AutoReqProv: no
%description
Minimal older-version fixture for the WP0 bootstrap repair probe only.
%install
mkdir -p %{buildroot}/usr/libexec/myproduct-host-tools
echo 'WP0 older tools fixture' > %{buildroot}/usr/libexec/myproduct-host-tools/wp0-older
%files
/usr/libexec/myproduct-host-tools
SPEC
rpmbuild -bb --quiet --define '_topdir /tmp/wp0-build' /tmp/wp0-build/older.spec
cp /tmp/wp0-build/RPMS/noarch/*.rpm /out/older.rpm
rpm --define "_gpg_name $product!" --addsign /out/older.rpm
original=(/out/myproduct-host-tools-*.rpm)
cp "${original[0]}" /out/unsigned.rpm
rpm --delsign /out/unsigned.rpm

# Extend only the disposable copy. The approved primary fingerprint is unchanged.
gpg --batch --pinentry-mode loopback --passphrase '' \
    --quick-add-key "$product" rsa2048 sign never
product_subkey=$(gpg --batch --with-colons --list-keys "$product" | \
    awk -F: '$1=="sub" {next_fpr=1; next} next_fpr && $1=="fpr" {print $10; exit}')
gpg --batch --armor --export "$product" > /out/product-subkey.asc
cp /out/unsigned.rpm /out/product-subkey.rpm
rpm --define "_gpg_name $product_subkey!" --addsign /out/product-subkey.rpm

gpg --batch --pinentry-mode loopback --passphrase '' \
    --quick-gen-key 'WP0 foreign key <foreign@wp0.invalid>' rsa2048 sign never
foreign=$(gpg --batch --with-colons --list-keys foreign@wp0.invalid | \
    awk -F: '$1=="fpr" {print $10; exit}')
gpg --batch --pinentry-mode loopback --passphrase '' \
    --quick-add-key "$foreign" rsa2048 sign never
foreign_subkey=$(gpg --batch --with-colons --list-keys "$foreign" | \
    awk -F: '$1=="sub" {next_fpr=1; next} next_fpr && $1=="fpr" {print $10; exit}')
gpg --batch --armor --export "$foreign" > /out/foreign.asc
cat /out/product-subkey.asc /out/foreign.asc > /out/two-primary.asc
for kind in foreign foreign-subkey; do
    signer=$foreign
    [[ $kind != foreign-subkey ]] || signer="$foreign_subkey!"
    cp /out/unsigned.rpm "/out/$kind.rpm"
    rpm --define "_gpg_name $signer" --addsign "/out/$kind.rpm"
done

# Flip bytes in the main header and compressed payload, respectively. Keep
# the signature header unchanged so these exercise distinct digest failures.
python3 - "${original[0]}" <<'PY'
import pathlib
import struct
import sys
data = bytearray(pathlib.Path(sys.argv[1]).read_bytes())
def end_header(offset):
    count, size = struct.unpack_from('>II', data, offset + 8)
    return offset + 16 + count * 16 + size
header = (end_header(96) + 7) & ~7
payload = end_header(header)
for name, offset in [('tampered-header', payload - 20),
                     ('tampered-payload', len(data) - 100)]:
    changed = data.copy()
    changed[offset] ^= 1
    pathlib.Path('/out/' + name + '.rpm').write_bytes(changed)
PY
printf '%s\n' "$product" > /out/product-fingerprint
echo 'PASS: WP0 signature fixtures built outside the repository'
