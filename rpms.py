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

from deployment import arguments, catalog, common, environment, output

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


def build(selected=(), tools=False, environment_name=None):
    """Build the selected RPMs into dist/rpm/; return their paths.

    selected names catalog components, each built from its bundle in dist/
    (./build-bundle.sh first, matching its .sha256 file); tools adds the tools
    RPM. Without either, every catalog component and the tools.
    environment_name takes the bundles of that build environment from
    dist/<name>/ and writes dist/<name>/rpm/ (./build-bundle.sh --environment):
    only its components (backlog 85), and only archives its
    current-bundles.txt names, so an archive an earlier, larger set left in
    dist/<name>/ is never wrapped; dist/<name>/delivery/ then holds exactly
    the current delivery (write_delivery).
    """
    if shutil.which("rpmbuild") is None:
        raise RpmError("rpmbuild is missing; install the rpm-build package")
    dist, option, env_overrides, current = DIST, "", None, None
    if environment_name is not None:
        env_overrides = environment.read_environment_file(ROOT, environment_name)
        dist, option = DIST / environment_name, f"--environment {environment_name} "
        current = current_bundles(dist, option)
    descriptors = catalog.source_descriptors(ROOT, env_overrides)
    unknown = sorted(set(selected) - set(descriptors))
    if unknown and env_overrides and env_overrides.selected is not None:
        raise RpmError(
            ", ".join(unknown) + f" is not in {env_overrides.path} components:"
        )
    if unknown:
        raise RpmError("Unknown component " + ", ".join(unknown) + "; see bundles.yaml")
    if current is not None:
        check_current_bundles(current, descriptors, dist, option)
    everything = not selected and not tools
    built = []
    for component, descriptor in descriptors.items():
        if not everything and component not in selected:
            continue
        product, version = descriptor["product"], descriptor["version"]
        archive = dist / f"{product}-{component}-{version}-offline.tar.gz"
        checksum = Path(str(archive) + ".sha256")
        if not archive.is_file() or not checksum.is_file():
            raise RpmError(
                f"Missing {archive.relative_to(ROOT)}; run ./build-bundle.sh "
                f"{option}{component}"
            )
        if checksum.read_text().split()[0] != sha256(archive):
            raise RpmError(f"{archive.name} does not match its .sha256 file")
        built.append(build_rpm(archive, product, component, version, dist / "rpm"))
        # Which bundle content this RPM wraps, so write_delivery can tell a
        # reused RPM from one of an earlier bundle with the same version.
        Path(str(built[-1]) + BUNDLE_SUFFIX).write_text(
            bundle_content(archive) + "\n", encoding="utf-8"
        )
        log.info(f"[OK] {built[-1].relative_to(ROOT)}")
    if everything or tools:
        built.append(build_tools(catalog.product_name(ROOT), dist / "rpm"))
        log.info(f"[OK] {built[-1].relative_to(ROOT)}")
    if environment_name is not None:
        write_delivery(dist, descriptors, option)
    return built


# Beside each component RPM: bundle_content() of the archive it wraps.
BUNDLE_SUFFIX = ".bundle.sha256"


def bundle_content(archive):
    """SHA256 of the component's own content in a bundle: its declarations and images.

    Taken from the bundle's checksums.sha256 lines for components/<id>/ (the
    manifests and config.defaults.yaml with its environment's overrides) and
    images/images.txt. Not the archive's bytes, which change with every build
    (tar and gzip times), and not bundle.yaml or the shared tools code: a
    dependency's new version changes the ranges in bundle.yaml, and an
    earlier release of this component stays a valid delivery then.
    """
    root = archive.name[: -len("-offline.tar.gz")]
    with tarfile.open(str(archive)) as tar:
        member = tar.extractfile(root + "/checksums.sha256")
        if member is None:
            raise RpmError(f"{archive.name} has no checksums.sha256")
        lines = member.read().decode("utf-8").splitlines()
    own = sorted(
        line
        for line in lines
        if line.split("  ", 1)[-1].startswith("components/")
        or line.endswith("  images/images.txt")
    )
    return hashlib.sha256("\n".join(own).encode("utf-8")).hexdigest()


def write_delivery(dist, descriptors, option):
    """dist/<environment>/delivery/: exactly the RPMs of the current delivery.

    The administrator command installs every product RPM of the directory it
    is given, so the supplier delivers this one, not dist/<environment>/rpm/,
    which keeps every RPM ever built (one version has one content). It is
    written again by every --environment run: the selected components' RPMs
    in their current versions and the current tools RPM. A missing one, or a
    component RPM built from another archive than the current one (same
    version, other content), leaves no delivery directory at all. The
    directory is filled beside it and renamed only when complete, so a
    failed copy never leaves a smaller delivery that looks intended.
    """
    product = catalog.product_name(ROOT)
    tools = (ROOT / "tools/VERSION").read_text().strip()
    wanted = {
        name: f"{descriptor['product']}-{name}-{descriptor['version']}-"
        f"{descriptor['version']}-1.noarch.rpm"
        for name, descriptor in descriptors.items()
    }
    wanted["--tools"] = f"{product}-tools-{tools}-1.noarch.rpm"
    delivery, partial = dist / "delivery", dist / ".delivery-partial"
    shutil.rmtree(str(delivery), ignore_errors=True)
    shutil.rmtree(str(partial), ignore_errors=True)
    missing = [
        name for name, rpm in wanted.items() if not (dist / "rpm" / rpm).is_file()
    ]
    if missing:
        raise RpmError(
            f"{delivery.relative_to(ROOT)} not written: no RPM yet for "
            + ", ".join(missing)
            + f"; run ./build-rpms.sh {option}"
            + " ".join(missing)
        )
    for name, descriptor in descriptors.items():
        rpm = dist / "rpm" / wanted[name]
        archive = dist / (
            f"{descriptor['product']}-{name}-{descriptor['version']}-offline.tar.gz"
        )
        wrapped = Path(str(rpm) + BUNDLE_SUFFIX)
        current = bundle_content(archive) + "\n"
        if not wrapped.is_file() or wrapped.read_text(encoding="utf-8") != current:
            raise RpmError(
                f"{delivery.relative_to(ROOT)} not written: {rpm.name} wraps another "
                f"{archive.name} than the current one; one version has one content, "
                f"so give {name} a new VERSION and build it again"
            )
    try:
        partial.mkdir()
        for rpm in wanted.values():
            shutil.copy2(str(dist / "rpm" / rpm), str(partial / rpm))
        partial.rename(delivery)
    finally:
        shutil.rmtree(str(partial), ignore_errors=True)
    log.info(f"[OK] {delivery.relative_to(ROOT)}: deliver this directory")


def current_bundles(dist, option):
    """The archive names of dist/<environment>/current-bundles.txt."""
    path = dist / "current-bundles.txt"
    if not path.is_file():
        raise RpmError(
            f"Missing {path.relative_to(ROOT)}; run ./build-bundle.sh {option.strip()}"
        )
    return path.read_text(encoding="utf-8").split()


def check_current_bundles(current, descriptors, dist, option):
    """The list names exactly the environment's components in their versions."""
    expected = {
        f"{descriptor['product']}-{name}-{descriptor['version']}-offline.tar.gz"
        for name, descriptor in descriptors.items()
    }
    listed = set(current)
    if listed != expected:
        stale = sorted(listed - expected) or sorted(expected - listed)
        raise RpmError(
            f"{(dist / 'current-bundles.txt').relative_to(ROOT)} does not match "
            f"the environment's components ({', '.join(stale)}); run "
            f"./build-bundle.sh {option.strip()}"
        )


def parser():
    result = arguments.Parser(
        prog="./build-rpms.sh",
        usage=(
            "./build-rpms.sh [--environment <name>] [<component> ...] [--tools] "
            "[--verbose]"
        ),
        description=(
            "Wrap built bundles as RPMs and build the tools RPM; without "
            "components or --tools, every catalog component (or every component "
            "of the --environment) and the tools. With --environment, "
            "dist/<name>/delivery/ holds exactly the RPMs to deliver."
        ),
        allow_abbrev=False,
    )
    result.add_argument(
        "--environment",
        metavar="<name>",
        help="wrap the bundles of dist/<name>/ (./build-bundle.sh --environment "
        "<name>) into dist/<name>/rpm/",
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
            parser(),
            sys.argv[1:] if command_line is None else command_line,
            flags=("--environment",),
        )
    except arguments.UsageError as error:
        return error.code
    output.configure(verbose=args.verbose)
    try:
        build(args.components, args.tools, args.environment)
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
