#!/usr/bin/env bash
# Runs inside the Oracle Linux 9 build container started by build-rpms.sh.
# /in: bundle archives and helper scripts (read-only); /out: RPMs and key;
# /key: the lab GnuPG home with the signing key.
set -euo pipefail
die() { echo "ERROR: $*" >&2; exit 1; }

dnf -y -q install rpm-build rpm-sign gnupg2 python3-pyyaml >/dev/null
export GNUPGHOME=/key
key_uid="podman-offline lab RPM key <rpm-lab@podman-offline.invalid>"
if ! gpg --list-secret-keys "$key_uid" >/dev/null 2>&1; then
    gpg --batch --pinentry-mode loopback --passphrase "" \
        --quick-gen-key "$key_uid" rsa3072 sign never
fi

top=$(mktemp -d)
product=
built=()

# Write a spec with rpmbuild's automatic processing disabled: the release must
# be installed byte for byte (no shebang rewriting, bytecode, stripping or
# generated dependencies).
write_spec() { # spec name version summary
    cat > "$1" <<EOF
%global debug_package %{nil}
%global __os_install_post %{nil}
%global __brp_mangle_shebangs %{nil}
%global _build_id_links none
%global _binary_payload w3T.zstdio
Name: $2
Version: $3
Release: 1
Summary: $4
License: Proprietary
BuildArch: noarch
AutoReqProv: no
%description
$4. Lab prototype for backlog 69.
EOF
}

for archive in /in/*-offline.tar.gz; do
    [[ -e $archive ]] || die "no bundle archives given"
    work=$(mktemp -d -p "$top")
    tar -xzf "$archive" -C "$work" --no-same-owner --no-same-permissions
    entries=("$work"/*)
    [[ ${#entries[@]} == 1 && -d ${entries[0]} ]] || die "$(basename "$archive"): expected one top directory"
    release=${entries[0]}
    name=$(basename "$release")
    [[ -z $(find "$release" ! -type f ! -type d) ]] || die "$name: links or special files"
    (cd "$release" && sha256sum -c --quiet checksums.sha256) || die "$name: inner checksums do not match"
    read -r bundle_product component version < <(python3 -I -c '
import sys, yaml
data = yaml.safe_load(open(sys.argv[1]))
print(data["product"], data["name"], data["version"])
' "$release/bundle.yaml")
    [[ $name == "$bundle_product-$component-$version" ]] || die "$name: name does not match bundle.yaml"
    [[ -z $product || $product == "$bundle_product" ]] || die "bundles of more than one product: $product, $bundle_product"
    product=$bundle_product
    # The same modes as scripts/release.py publishes.
    find "$release" -type d -exec chmod 0755 {} +
    find "$release" -type f -perm /111 -exec chmod 0755 {} +
    find "$release" -type f ! -perm /111 -exec chmod 0644 {} +

    spec=$top/$name.spec
    write_spec "$spec" "$name" "$version" "$product $component $version release"
    cat >> "$spec" <<EOF
%install
mkdir -p %{buildroot}/var/lib/$product/releases
cp -a $release %{buildroot}/var/lib/$product/releases/$name
%files
%dir %attr(0755,root,root) /var/lib/$product
%dir %attr(0755,root,root) /var/lib/$product/releases
%defattr(-,root,root,-)
/var/lib/$product/releases/$name
EOF
    rpmbuild -bb --quiet --define "_topdir $top/rpmbuild" "$spec"
    built+=("$name")
done

# The host setup command and the host script it calls, with a minimal
# bundle.yaml so prepare-host.sh finds the product name next to itself.
tools=$top/tools
mkdir -p "$tools/scripts"
sed "s/@PRODUCT@/$product/g" /in/host-setup.sh > "$tools/host-setup"
cp /in/prepare-host.sh "$tools/scripts/prepare-host.sh"
printf 'product: %s\n' "$product" > "$tools/bundle.yaml"
spec=$top/$product-host-tools.spec
write_spec "$spec" "$product-host-tools" "$TOOLS_VERSION" "$product host setup command"
cat >> "$spec" <<EOF
%install
mkdir -p %{buildroot}/usr/sbin %{buildroot}/usr/libexec/$product-host-tools/scripts
install -m 0755 $tools/host-setup %{buildroot}/usr/sbin/$product-host-setup
install -m 0755 $tools/scripts/prepare-host.sh %{buildroot}/usr/libexec/$product-host-tools/scripts/prepare-host.sh
install -m 0644 $tools/bundle.yaml %{buildroot}/usr/libexec/$product-host-tools/bundle.yaml
%files
%defattr(-,root,root,-)
/usr/sbin/$product-host-setup
/usr/libexec/$product-host-tools
EOF
rpmbuild -bb --quiet --define "_topdir $top/rpmbuild" "$spec"

for rpm in "$top"/rpmbuild/RPMS/noarch/*.rpm; do
    rpm --define "_gpg_name $key_uid" --addsign "$rpm" >/dev/null
    cp "$rpm" /out/
done
gpg --armor --export "$key_uid" > "/out/RPM-GPG-KEY-$product"
echo "Built: ${built[*]} $product-host-tools"
echo "Key fingerprint (write it on the paper manual):"
gpg --with-fingerprint --show-keys "/out/RPM-GPG-KEY-$product" | sed -n 2p
