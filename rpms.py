"""Wrap built bundles as RPMs: dist/rpm/<product>-<component>-<version>-1.noarch.rpm.

Backlog 69, phase 1 (unsigned RPMs, product owner 2026-10-26 and 2026-11-01).
Each RPM installs one bundle unchanged under
/var/lib/<product>/releases/<product>-<component>-<version>/, where the target
expects its releases. The version is part of the package name, so versions
install side by side and the running one keeps its release tree. fapolicyd
trusts the files through the RPM database.

An installed release can be erased only by the administrator command
(backlog 69 WP4): the package's %preun refuses an erase unless
/run/<product>/erase-authorization names exactly this package and the live
administrator command that wrote it, and consumes it.

The tools RPM, dist/rpm/<product>-tools-<version>-1.noarch.rpm, carries the
administrator command /usr/sbin/<product>-admin (tools/admin.py) and the
runtime command /usr/bin/<product> (tools/runtime.py), with the host
preparation script and the two deployment modules they import, under
/usr/libexec/<product>-tools/. Its version is tools/VERSION: raise it whenever
one of TOOLS_FILES changes. It has the same erase guard; an upgrade replaces it.

One version has exactly one content: an existing RPM of the same name is
never replaced; it is reused when it wraps the same content (bundle_content,
tools_content) and refused otherwise. Every run writes dist/delivery/ with
exactly its RPMs, the directory to deliver (backlog 85); bundles and RPMs are
environment-neutral, and the target applies its environment file at
deployment.
"""

import hashlib
import json
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
# The authorization (tools/admin.py remove) is root-owned and names exactly
# this package and the live administrator process (PID and start time); the
# guard consumes it, so it is used once and never outlives its command.
GUARD = """\
authorized() {{
    auth=/run/{product}/erase-authorization
    [ ! -L "$auth" ] && [ -f "$auth" ] && [ "$(stat -c %u "$auth")" = 0 ] || return 1
    read -r identity owner started extra < "$auth" || return 1
    [ "$identity" = "%{{name}}-%{{version}}-%{{release}}" ] && [ -z "$extra" ] || return 1
    case "$owner$started" in ''|*[!0-9]*) return 1;; esac
    process=$(cat "/proc/$owner/stat" 2>/dev/null) || return 1
    set -- ${{process##*) }}
    case "$1" in Z|X|x) return 1;; esac
    [ "${{20}}" = "$started" ] || return 1
    rm -f -- "$auth"
}}
if [ "$1" -eq 0 ] && ! authorized; then
    echo "{product}: removing %{{name}} is refused; use: sudo {product}-admin" >&2
    exit 1
fi
"""

# rpmbuild must install the files byte for byte: no shebang rewriting,
# bytecode, stripping or generated dependencies. The payload is zstd level 3
# (product owner, 2026-11-08): OL9's default level 19 takes minutes for a
# release's image archive; level 3 builds many times faster for somewhat
# larger files.
HEADER = """\
%global _binary_payload w3.zstdio
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
Summary: {product} administrator and runtime commands
License: Proprietary
BuildArch: noarch
AutoReqProv: no
Requires: python3, python3-pyyaml, util-linux, rpm, dnf
%description
sudo {product}-admin installs delivered {product} RPMs and prepares the host;
{product}, run by the runtime account, installs the {product} components.
%install
mkdir -p %{{buildroot}}/usr/sbin %{{buildroot}}/usr/bin %{{buildroot}}/usr/libexec
cp -a {tree}/{product}-admin %{{buildroot}}/usr/sbin/{product}-admin
cp -a {tree}/{product} %{{buildroot}}/usr/bin/{product}
cp -a {tree}/{product}-tools %{{buildroot}}/usr/libexec/{product}-tools
%preun
{guard}
%files
%defattr(-,root,root,-)
/usr/sbin/{product}-admin
/usr/bin/{product}
/usr/libexec/{product}-tools
"""
)

# Source files of the tools RPM, below /usr/libexec/<product>-tools/.
TOOLS_FILES = {
    "admin.py": "tools/admin.py",
    "host.py": "tools/host.py",
    "runtime.py": "tools/runtime.py",
    "scripts/prepare-host.sh": "scripts/prepare-host.sh",
    "deployment/__init__.py": "deployment/__init__.py",
    "deployment/arguments.py": "deployment/arguments.py",
    "deployment/output.py": "deployment/output.py",
}

# /usr/sbin/<product>-admin and /usr/bin/<product>. -E -s keep the
# environment and user site out; -B writes no bytecode next to the RPM's files.
WRAPPER = """\
#!/bin/sh
exec /usr/bin/python3 -E -s -B /usr/libexec/{product}-tools/{script} "$@"
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
        for command, script in (
            (f"{product}-admin", "admin.py"),
            (product, "runtime.py"),
        ):
            (tree / command).write_text(WRAPPER.format(product=product, script=script))
            (tree / command).chmod(0o755)
        (libexec / "scripts/prepare-host.sh").chmod(0o755)
        normalize_modes(tree)
        text = TOOLS_SPEC.format(
            product=product,
            version=version,
            tree=tree,
            guard=GUARD.format(product=product),
        )
        return rpmbuild(work, product + "-tools.spec", text, target)


# Beside each component RPM: bundle_content() of the archive it wraps.
BUNDLE_SUFFIX = ".bundle.sha256"


def bundle_content(archive):
    """SHA256 of what the component's release does, not of the archive's bytes.

    Three parts, each read from the bundle itself:

    - every file of the release (its checksums.sha256 lines): the
      component's manifests and declarations, images/images.txt, and the
      release's own deploy.sh, deployment/, scripts/, quadlet/ and documents,
      which the release runs or ships; except bundle.yaml and
      images/images.tar, which follow;
    - its descriptor (bundle.yaml) with the names of its dependencies but not
      their version ranges: a dependency's new version changes those ranges,
      and an earlier release of this component stays a valid delivery then;
    - its images: image IDs and layer digests from images.tar's manifest.json,
      so the same tag with other content is a change.

    The archive's bytes change with every build (tar and gzip times).
    """
    root = archive.name[: -len("-offline.tar.gz")]
    with tarfile.open(str(archive)) as tar:
        lines = member_bytes(tar, root + "/checksums.sha256").decode("utf-8")
        descriptor = yaml.safe_load(member_bytes(tar, root + "/bundle.yaml"))
        images = image_identity(tar, root + "/images/images.tar")
    files = sorted(
        line
        for line in lines.splitlines()
        if line.split("  ", 1)[-1] not in ("bundle.yaml", "images/images.tar")
    )
    descriptor = dict(descriptor, requires=sorted(descriptor["requires"]))
    content = {"files": files, "descriptor": descriptor, "images": images}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def member_bytes(tar, name):
    member = tar.extractfile(name)
    if member is None:
        raise RpmError(f"{name} is missing from the bundle")
    return member.read()


def image_identity(tar, name):
    """[RepoTags, Config, Layers] of every image in the bundle's docker-archive.

    Read as a stream: manifest.json may follow gigabytes of layers.
    """
    stream = tar.extractfile(name)
    if stream is None:
        raise RpmError(f"{name} is missing from the bundle")
    with tarfile.open(fileobj=stream, mode="r|") as images:
        for member in images:
            if member.name.lstrip("./") == "manifest.json":
                manifest = images.extractfile(member)
                if manifest is not None:
                    return sorted(
                        [
                            sorted(item.get("RepoTags") or []),
                            item["Config"],
                            item["Layers"],
                        ]
                        for item in json.load(manifest)
                    )
    raise RpmError(f"{name} has no manifest.json")


def tools_content():
    """SHA256 of the tools RPM's files and tools/VERSION, as bundle_content for a bundle."""
    digest = hashlib.sha256((ROOT / "tools/VERSION").read_bytes())
    for installed, source in sorted(TOOLS_FILES.items()):
        digest.update(installed.encode() + b"\0" + (ROOT / source).read_bytes())
    return digest.hexdigest()


def built_or_reused(rpm, content, what, build):
    """Build rpm, or reuse it when it wraps the same content; one version, one content.

    content is written beside a new RPM (BUNDLE_SUFFIX). An existing RPM with
    other or unknown content is refused: rebuilding it would give one
    version two contents.
    """
    record = Path(str(rpm) + BUNDLE_SUFFIX)
    if rpm.exists():
        if not record.is_file() or record.read_text(encoding="utf-8") != content + "\n":
            raise RpmError(
                f"{rpm.name} already exists with other content; one version has "
                f"one content, so give {what} a new VERSION instead of rebuilding it"
            )
        log.info(f"[OK] {rpm.relative_to(ROOT)} (built before, same content)")
        return rpm
    rpm = build()
    record.write_text(content + "\n", encoding="utf-8")
    log.info(f"[OK] {rpm.relative_to(ROOT)}")
    return rpm


def build(selected=(), tools=False):
    """Build or reuse the selected RPMs and write dist/delivery/ with exactly them.

    selected names catalog components, each from its bundle in dist/
    (./build-bundle.sh first, matching its .sha256 file); tools alone is
    only the tools RPM. Without either, every catalog component. Every run
    with components includes the tools RPM. dist/rpm/ keeps every RPM ever
    built; dist/delivery/ (write_delivery) holds this run's RPMs and nothing
    else, and is the directory to deliver; a refused run leaves none.
    """
    # Removed first: after a refused run there is no delivery that looks current.
    shutil.rmtree(str(DIST / "delivery"), ignore_errors=True)
    if shutil.which("rpmbuild") is None:
        raise RpmError("rpmbuild is missing; install the rpm-build package")
    descriptors = catalog.source_descriptors(ROOT)
    unknown = sorted(set(selected) - set(descriptors))
    if unknown:
        raise RpmError("Unknown component " + ", ".join(unknown) + "; see bundles.yaml")
    chosen = [
        name for name in descriptors if (not selected and not tools) or name in selected
    ]
    built = []
    for component in chosen:
        product, version = (
            descriptors[component]["product"],
            descriptors[component]["version"],
        )
        archive = DIST / f"{product}-{component}-{version}-offline.tar.gz"
        checksum = Path(str(archive) + ".sha256")
        if not archive.is_file() or not checksum.is_file():
            raise RpmError(f"Missing {archive.name}; run ./build-bundle.sh {component}")
        if checksum.read_text().split()[0] != sha256(archive):
            raise RpmError(f"{archive.name} does not match its .sha256 file")
        rpm = DIST / "rpm" / f"{product}-{component}-{version}-{version}-1.noarch.rpm"
        built.append(
            built_or_reused(
                rpm,
                bundle_content(archive),
                component,
                lambda a=archive, c=component, v=version, p=product: build_rpm(
                    a, p, c, v, DIST / "rpm"
                ),
            )
        )
    product = catalog.product_name(ROOT)
    version = (ROOT / "tools/VERSION").read_text().strip()
    built.append(
        built_or_reused(
            DIST / "rpm" / f"{product}-tools-{version}-1.noarch.rpm",
            tools_content(),
            "tools (tools/VERSION)",
            lambda: build_tools(product, DIST / "rpm"),
        )
    )
    write_delivery(built)
    return built


def write_delivery(rpms):
    """dist/delivery/: exactly the RPMs of this run, published only when complete.

    The administrator command installs every product RPM of the directory it
    is given, so the supplier delivers this one, never dist/rpm/, which keeps
    every RPM ever built. It is filled beside it and renamed when complete,
    so a failed copy never leaves a smaller delivery that looks intended.
    """
    delivery, partial = DIST / "delivery", DIST / ".delivery-partial"
    shutil.rmtree(str(delivery), ignore_errors=True)
    shutil.rmtree(str(partial), ignore_errors=True)
    try:
        partial.mkdir(parents=True)
        for rpm in rpms:
            shutil.copy2(str(rpm), str(partial / rpm.name))
        partial.rename(delivery)
    finally:
        shutil.rmtree(str(partial), ignore_errors=True)
    log.info(f"[OK] {delivery.relative_to(ROOT)}: deliver this directory")


def parser():
    result = arguments.Parser(
        prog="./build-rpms.sh",
        usage="./build-rpms.sh [<component> ...] [--tools] [--verbose]",
        description=(
            "Wrap built bundles as RPMs and build the tools RPM; without "
            "components or --tools, every catalog component and the tools. "
            "dist/delivery/ then holds exactly this run's RPMs: deliver it."
        ),
        allow_abbrev=False,
    )
    result.add_argument(
        "--tools",
        action=arguments.Once,
        default=False,
        help="build the tools RPM (the administrator and runtime commands)",
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
