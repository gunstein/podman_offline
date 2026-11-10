"""What <product>-admin and <product> both read from the host (backlog 69).

The installed releases come from the RPM database; the runtime account is the
owner of /var/lib/<product>/state (prepare-host.sh creates it); the HTTPS port
is /etc/<product>/host.conf (written by <product>-admin). Nothing here is
stored twice.
"""

import os
import pwd
import re
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

import yaml

from deployment import output

log = output.log

TOOLS = Path(__file__).resolve().parent
# Host paths; tests point them at temporary directories.
LIB = Path("/var/lib")
ETC = Path("/etc")
# Where a release RPM installs its tree (rpms.py); release RPMs are recognised by it.
RELEASE_PATH = "/var/lib/{product}/releases/{name}"

ID = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
# An environment file's name, state/<name>.yaml: deployment.common.PRODUCT's rule.
ENVIRONMENT = re.compile(r"[a-z]([a-z0-9-]{0,30}[a-z0-9])?")

# One RPM file or installed package of this product. component is "" for the
# tools package; file is a private copy of a delivered RPM, or None.
Package = namedtuple("Package", "name version component file")
QUERY = "%{NAME} %{VERSION} %{FILENAMES}\n"


class ToolError(Exception):
    """Error shown as a single ERROR line without a traceback."""


def run(command, check=True, capture=True, stdin=None):
    """Run a host command in the C locale; return the CompletedProcess."""
    log.debug("+ " + " ".join(command))
    pipe = subprocess.PIPE if capture else None
    result = subprocess.run(
        command,
        input=stdin,
        stdout=pipe,
        stderr=pipe,
        universal_newlines=True,  # noqa: UP021 - text= needs Python 3.7
        env=dict(os.environ, LC_ALL="C"),
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        raise ToolError(
            f"{command[0]} {command[1]} failed (exit {result.returncode})"
            + (": " + detail[-1] if detail else "")
        )
    return result


def product_name():
    """The product the tools RPM was built for (bundle.yaml beside this file)."""
    return yaml.safe_load((TOOLS / "bundle.yaml").read_text())["product"]


def version_key(version):
    return tuple(int(part) for part in version.split("."))


def ask(question, default, option):
    """Ask on the terminal; without one, name the option that gives the value."""
    if not sys.stdin.isatty():
        raise ToolError(f"Give {option}; there is no terminal to ask")
    prompt = f"{question} [{default}]: " if default else f"{question}: "
    answer = input(prompt).strip() or default
    if not answer:
        raise ToolError(f"No answer; run again and answer, or give {option}")
    return answer


def host_conf(product):
    return ETC / product / "host.conf"


def configured_port(product):
    """The HTTPS port from host.conf, or None before the first preparation."""
    path = host_conf(product)
    if not path.exists():
        return None
    match = re.search(r"^HTTPS_PORT=([0-9]+)$", path.read_text(), re.MULTILINE)
    if not match:
        raise ToolError(f"{path} has no HTTPS_PORT line; inspect it")
    return int(match.group(1))


def prepared_account(product):
    """The runtime account of a prepared host: the owner of state/, else None."""
    state = LIB / product / "state"
    if not state.is_dir() or state.is_symlink():
        return None
    return pwd.getpwuid(state.lstat().st_uid)


def component_of(product, name, version, first_file):
    """'' for the tools package, the component for a release, None otherwise."""
    if name == product + "-tools":
        return ""
    prefix, suffix = product + "-", "-" + version
    if not (
        VERSION.fullmatch(version) and name.startswith(prefix) and name.endswith(suffix)
    ):
        return None
    component = name[len(prefix) : -len(suffix)]
    if ID.fullmatch(component) and first_file == RELEASE_PATH.format(
        product=product, name=name
    ):
        return component
    return None


def installed(product):
    """This product's installed packages, from the RPM database."""
    packages = []
    for line in run(["rpm", "-qa", "--queryformat", QUERY]).stdout.splitlines():
        name, version, first_file = (line.split(" ", 2) + ["", ""])[:3]
        component = component_of(product, name, version, first_file)
        if component is not None:
            packages.append(Package(name, version, component, None))
    return packages


def newest_releases(packages):
    """{component: package} with the newest installed release of each component."""
    newest = {}
    for package in packages:
        current = newest.get(package.component)
        if package.component and (
            current is None
            or version_key(package.version) > version_key(current.version)
        ):
            newest[package.component] = package
    return newest


def release_path(product, package):
    return LIB / product / "releases" / package.name
