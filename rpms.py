"""Wrap built bundles as RPMs: dist/rpm/<product>-<component>-<version>-1.noarch.rpm.

Backlog 69, phase 1 (unsigned RPMs, product owner 2026-10-26 and 2026-11-01).
Each RPM installs one bundle unchanged under
/var/lib/<product>/releases/<product>-<component>-<version>/, where the target
expects its releases. The version is part of the package name, so versions
install side by side and the running one keeps its release tree. fapolicyd
trusts the files through the RPM database.

An installed release can be erased only by the administrator command
(backlog 69 WP2): the package's %preun refuses an erase unless
/run/<product>/erase-authorization names exactly this package. That command
writes the authorization for one package and deletes it afterwards.

The tools RPM, dist/rpm/<product>-tools-<version>-1.noarch.rpm, carries the
administrator command /usr/sbin/<product>-admin (tools/admin.py) with the host
preparation script and the two deployment modules it imports, under
/usr/libexec/<product>-tools/. Its version is tools/VERSION: raise it whenever
one of TOOLS_FILES changes. It has the same erase guard; an upgrade replaces it.

A version is built once: an existing RPM of the same name is never replaced,
because one version has exactly one content.
"""

import hashlib
import logging
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import yaml

from deployment import arguments, catalog, common, output

log = logging.getLogger("deployment.rpms")

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

# %preun of every release RPM. $1 is the number of instances left after the
# transaction: 0 for an erase. Plain sh, so it needs nothing from the product.
GUARD = """\
if [ "$1" -eq 0 ]; then
    auth=/run/{product}/erase-authorization
    if [ -L "$auth" ] || [ ! -f "$auth" ] || [ "$(stat -c %u "$auth")" != 0 ] \\
        || [ "$(cat "$auth")" != "%{{name}}-%{{version}}-%{{release}}" ]; then
        echo "{product}: removing %{{name}} is refused; use: sudo {product}-admin" >&2
        exit 1
    fi
fi
"""

# rpmbuild must install the files byte for byte: no shebang rewriting,
# bytecode, stripping or generated dependencies.
HEADER = """\
%global debug_package %{{nil}}
%global __os_install_post %{{nil}}
%global __brp_mangle_shebangs %{{nil}}
%global _build_id_links none
"""

SPEC = (
    HEADER
    + """\
Name: {name}
Version: {version}
Release: 1
Summary: {product} {component} {version} release
License: Proprietary
BuildArch: noarch
AutoReqProv: no
%description
The {product} release {component} {version}, installed unchanged under
/var/lib/{product}/releases/{name}/.
%install
mkdir -p %{{buildroot}}/var/lib/{product}/releases
cp -a {tree} %{{buildroot}}/var/lib/{product}/releases/{name}
%preun
{guard}
%files
%defattr(-,root,root,-)
/var/lib/{product}/releases/{name}
"""
)

# What the administrator command needs on the host before it can say what is
# missing; dnf names a missing one when the tools are installed.
TOOLS_SPEC = (
    HEADER
    + """\
Name: {product}-tools
Version: {version}
Release: 1
Summary: {product} administrator command
License: Proprietary
BuildArch: noarch
AutoReqProv: no
Requires: python3, python3-pyyaml, util-linux, rpm, dnf
%description
sudo {product}-admin installs delivered {product} RPMs and prepares the host.
%install
mkdir -p %{{buildroot}}/usr/sbin %{{buildroot}}/usr/libexec
cp -a {tree}/{product}-admin %{{buildroot}}/usr/sbin/{product}-admin
cp -a {tree}/{product}-tools %{{buildroot}}/usr/libexec/{product}-tools
%preun
{guard}
%files
%defattr(-,root,root,-)
/usr/sbin/{product}-admin
/usr/libexec/{product}-tools
"""
)

# Source files of the tools RPM, below /usr/libexec/<product>-tools/.
TOOLS_FILES = {
    "admin.py": "tools/admin.py",
    "scripts/prepare-host.sh": "scripts/prepare-host.sh",
    "deployment/__init__.py": "deployment/__init__.py",
    "deployment/arguments.py": "deployment/arguments.py",
    "deployment/output.py": "deployment/output.py",
}

# /usr/sbin/<product>-admin. -E -s keep the environment and user site out;
# -B writes no bytecode next to the RPM's files.
WRAPPER = """\
#!/bin/sh
exec /usr/bin/python3 -E -s -B /usr/libexec/{product}-tools/admin.py "$@"
"""


class RpmError(Exception):
    """Error shown as a single ERROR line without a traceback."""


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unpack(archive, target):
    """Extract a bundle archive; return its one release directory.

    The archive holds only regular files and directories under one top
    directory (bundle.py writes it so); anything else is refused.
    """
    with tarfile.open(str(archive)) as tar:
        members = tar.getmembers()
        tops = {Path(member.name).parts[0] for member in members}
        if len(tops) != 1 or any(
            not (member.isreg() or member.isdir())
            or member.name.startswith("/")
            or ".." in Path(member.name).parts
            for member in members
        ):
            raise RpmError(f"{archive.name}: unexpected archive layout")
        # The checks above stand in for an extraction filter on Python 3.6;
        # newer Pythons also apply the "data" filter. Modes are kept: the
        # executable bit decides 0755 or 0644 (normalize_modes).
        for member in members:
            if hasattr(tarfile, "data_filter"):
                tar.extract(member, str(target), filter="data")
            else:
                tar.extract(member, str(target))
    return target / tops.pop()


def check_release(release, product, component, version):
    """The release matches its name, bundle.yaml and checksums.sha256."""
    descriptor = yaml.safe_load((release / "bundle.yaml").read_text())
    if (descriptor["product"], descriptor["name"], descriptor["version"]) != (
        product,
        component,
        version,
    ):
        raise RpmError(f"{release.name}: bundle.yaml names another release")
    listed = {}
    for line in (release / "checksums.sha256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        listed[name] = digest
    files = {
        str(path.relative_to(release))
        for path in release.rglob("*")
        if path.is_file() and path.name != "checksums.sha256"
    }
    if set(listed) != files or any(
        sha256(release / name) != digest for name, digest in listed.items()
    ):
        raise RpmError(f"{release.name}: files do not match checksums.sha256")


def normalize_modes(release):
    """Directories and executables 0755, other files 0644, as installed releases."""
    for path in [release] + sorted(release.rglob("*")):
        mode = path.stat().st_mode
        executable = stat.S_ISDIR(mode) or mode & 0o111
        path.chmod(0o755 if executable else 0o644)


def refuse_existing(target, what):
    if target.exists():
        raise RpmError(
            f"{target.name} already exists; one version has one content, so "
            f"give {what} a new VERSION instead of rebuilding it"
        )


def rpmbuild(work, spec_name, text, target):
    """Build the spec text in work; copy the one RPM to target."""
    spec = work / spec_name
    spec.write_text(text)
    log.debug("+ rpmbuild -bb " + spec.name)
    subprocess.run(
        [
            "rpmbuild",
            "-bb",
            "--quiet",
            "--define",
            f"_topdir {work}/rpmbuild",
            str(spec),
        ],
        check=True,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(work / "rpmbuild/RPMS/noarch" / target.name), str(target))
    return target


def build_rpm(archive, product, component, version, out):
    """Build one release RPM from a bundle archive into out; return its path."""
    name = f"{product}-{component}-{version}"
    target = out / f"{name}-{version}-1.noarch.rpm"
    refuse_existing(target, component)
    with tempfile.TemporaryDirectory(prefix="rpm-") as directory:
        work = Path(directory)
        release = unpack(archive, work / "tree")
        if release.name != name:
            raise RpmError(f"{archive.name}: top directory is not {name}")
        check_release(release, product, component, version)
        normalize_modes(release)
        text = SPEC.format(
            name=name,
            version=version,
            product=product,
            component=component,
            tree=release,
            guard=GUARD.format(product=product),
        )
        return rpmbuild(work, name + ".spec", text, target)


def build_tools(product, out):
    """Build the tools RPM from TOOLS_FILES and tools/VERSION; return its path."""
    version = (ROOT / "tools/VERSION").read_text().strip()
    catalog.version_number(version)
    target = out / f"{product}-tools-{version}-1.noarch.rpm"
    refuse_existing(target, "tools (tools/VERSION)")
    with tempfile.TemporaryDirectory(prefix="rpm-") as directory:
        work = Path(directory)
        tree = work / "tree"
        libexec = tree / f"{product}-tools"
        for installed, source in TOOLS_FILES.items():
            (libexec / installed).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(ROOT / source), str(libexec / installed))
        # admin.py and prepare-host.sh read the product name here.
        (libexec / "bundle.yaml").write_text(yaml.safe_dump({"product": product}))
        (tree / f"{product}-admin").write_text(WRAPPER.format(product=product))
        (tree / f"{product}-admin").chmod(0o755)
        (libexec / "scripts/prepare-host.sh").chmod(0o755)
        normalize_modes(tree)
        text = TOOLS_SPEC.format(
            product=product,
            version=version,
            tree=tree,
            guard=GUARD.format(product=product),
        )
        return rpmbuild(work, product + "-tools.spec", text, target)


def build(selected=(), tools=False):
    """Build the selected RPMs into dist/rpm/; return their paths.

    selected names catalog components, each built from its bundle in dist/
    (./build-bundle.sh first, matching its .sha256 file); tools adds the tools
    RPM. Without either, every catalog component and the tools.
    """
    if shutil.which("rpmbuild") is None:
        raise RpmError("rpmbuild is missing; install the rpm-build package")
    descriptors = catalog.source_descriptors(ROOT)
    unknown = sorted(set(selected) - set(descriptors))
    if unknown:
        raise RpmError("Unknown component " + ", ".join(unknown) + "; see bundles.yaml")
    everything = not selected and not tools
    built = []
    for component, descriptor in descriptors.items():
        if not everything and component not in selected:
            continue
        product, version = descriptor["product"], descriptor["version"]
        archive = DIST / f"{product}-{component}-{version}-offline.tar.gz"
        checksum = Path(str(archive) + ".sha256")
        if not archive.is_file() or not checksum.is_file():
            raise RpmError(f"Missing {archive.name}; run ./build-bundle.sh {component}")
        if checksum.read_text().split()[0] != sha256(archive):
            raise RpmError(f"{archive.name} does not match its .sha256 file")
        built.append(build_rpm(archive, product, component, version, DIST / "rpm"))
        log.info(f"[OK] {built[-1].relative_to(ROOT)}")
    if everything or tools:
        built.append(build_tools(catalog.product_name(ROOT), DIST / "rpm"))
        log.info(f"[OK] {built[-1].relative_to(ROOT)}")
    return built


def parser():
    result = arguments.Parser(
        prog="./build-rpms.sh",
        usage="./build-rpms.sh [<component> ...] [--tools] [--verbose]",
        description=(
            "Wrap built bundles as RPMs and build the tools RPM; without "
            "components or --tools, every catalog component and the tools."
        ),
        allow_abbrev=False,
    )
    result.add_argument(
        "--tools",
        action=arguments.Once,
        default=False,
        help="build the tools RPM (the administrator command)",
    )
    result.add_argument(
        "--verbose", action=arguments.Once, default=False, help="also show each command"
    )
    result.add_argument("components", nargs="*", metavar="<component>")
    return result


def main(command_line=None):
    try:
        args = arguments.parse(
            parser(), sys.argv[1:] if command_line is None else command_line
        )
    except arguments.UsageError as error:
        return error.code
    output.configure(verbose=args.verbose)
    try:
        build(args.components, args.tools)
    except (
        OSError,
        RpmError,
        common.DeployError,
        yaml.YAMLError,
        subprocess.CalledProcessError,
    ) as error:
        log.error(f"ERROR: {error}")
        return 1
    log.info("PASS: ./build-rpms.sh completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
