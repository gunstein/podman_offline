"""<product>: install this product's components as the runtime account (backlog 69 WP3).

Phase 1, within the product owner's decisions of 2026-11-01 (BACKLOG.md item
69). The <product>-tools RPM installs this file as
/usr/libexec/<product>-tools/runtime.py; the command is /usr/bin/<product>.
The runtime account runs it in its own login (console or SSH), never root:

    <product> [--environment <environment>] [<component>]
              [--public-origin <url>] [--ip-address <address>]

It uses the releases <product>-admin installed, the newest of each component,
in dependency order, each through its own deploy.sh (no code is shared
across releases):

1. deploy.sh init-layout: the account's bootstrap file.
2. deploy.sh status --json: what is installed and what is pending.
3. A pending component first, then each component not installed in its
   release's version; a completed one is skipped. With <component>, only that
   one, also when it is complete, so a changed config.yaml takes effect.
4. A component without config.yaml gets one from deploy.sh init-config. For
   the gateway the answers (public origin and IP address, asked the first
   time; the port from /etc/<product>/host.conf) are written with it in one
   step, so an interruption before that write asks again.
5. Delivered credentials move from /var/lib/<product>/incoming/<component>/
   to state/<component>/ (the same layout): an identical file is kept, a
   different one stops before anything is copied, and the incoming copy is
   removed once the state copy is verified.
6. deploy.sh install. A failure stops; the next run resumes it first.
7. A warning names each component that is not installed now but has
   delivered files waiting in incoming/ (<product> <component> takes them).
8. deploy.sh status.

With --environment <environment> (backlog 85) the operator's file
/var/lib/<product>/state/<environment>.yaml decides the components: only
those listed are deployed, each with the file's overrides (init-config and
install get --environment). Before anything changes: every listed component
and every dependency of one must have an installed release package in a
compatible version, a dependency must be listed too, a listed component may
not have been uninstalled on purpose (unless named), and every listed
release checks the file (deploy.sh check-environment). Components not
listed are left as they are. Nothing about the environment is remembered:
the file is read again by every run and by every deploy.sh it calls.
"""

import json
import os
import re
import socket
import stat
import sys

import host
import yaml
from host import ToolError, ask, run

from deployment import arguments, output

log = output.log


def check_account(product):
    """The runtime account of the prepared host, in its own login."""
    if os.geteuid() == 0:
        raise ToolError(f"Run {product} as the runtime account, not as root")
    account = host.prepared_account(product)
    if account is None:
        raise ToolError(
            f"This host is not prepared for {product}; the administrator runs "
            f"sudo {product}-admin <delivery directory> first"
        )
    if account.pw_uid != os.geteuid():
        raise ToolError(
            f"{product} runs as {account.pw_name} on this host; log in as {account.pw_name}"
        )
    return account


def releases(product):
    """{component: (package, release directory, descriptor)} of the newest releases."""
    newest = host.newest_releases(host.installed(product))
    if not newest:
        raise ToolError(
            f"No {product} release is installed; the administrator runs "
            f"sudo {product}-admin <delivery directory>"
        )
    result = {}
    for component, package in newest.items():
        path = host.release_path(product, package)
        descriptor = yaml.safe_load((path / "bundle.yaml").read_text())
        result[component] = (package, path, descriptor)
    return result


def install_order(product, found):
    """Components in dependency order; a missing dependency stops.

    Identity (each descriptor names it) comes before every component it does
    not itself depend on: an environment may make any of them an API of
    Identity, whose installed mapping that component's install reads.
    """
    requires = {}
    for component, (_, _, descriptor) in found.items():
        requires[component] = set(descriptor["requires"])
        for dependency in sorted(requires[component] - set(found)):
            raise ToolError(
                f"{component} requires {dependency}, which is not installed; the "
                f"administrator delivers the {product}-{dependency} RPM"
            )
    identities = {descriptor.get("identity") for _, _, descriptor in found.values()}
    identity = next(iter(identities)) if len(identities) == 1 else None
    if identity in found:
        before, pending = set(), [identity]
        while pending:
            for dependency in requires[pending.pop()]:
                if dependency not in before:
                    before.add(dependency)
                    pending.append(dependency)
        for component, needed in requires.items():
            if component != identity and component not in before:
                needed.add(identity)
    order = []
    while len(order) < len(requires):
        ready = sorted(
            component
            for component, needed in requires.items()
            if component not in order and needed <= set(order)
        )
        if not ready:
            raise ToolError(
                "The installed releases require each other; ask the supplier"
            )
        order.append(ready[0])
    return order


def deploy(path, *command, capture=False):
    """Run one release's own deploy.sh; its messages go to the terminal."""
    return run(
        ["bash", str(path / "deploy.sh"), *command], check=False, capture=capture
    )


def deployed(path, *command):
    """deploy.sh that must succeed; its own ERROR line explains a failure."""
    if deploy(path, *command).returncode != 0:
        raise ToolError(
            f"deploy.sh {command[0]} stopped; fix what it names, then run the same "
            "command again"
        )


def status_report(path):
    result = deploy(path, "status", "--json", capture=True)
    try:
        return json.loads(result.stdout)
    except ValueError:
        detail = (result.stderr or "").strip().splitlines()
        raise ToolError(
            "deploy.sh status failed" + (": " + detail[-1] if detail else "")
        ) from None


def uninstalled(state):
    """Components the runtime user removed with deploy.sh uninstall (backlog 85).

    Read from state/uninstalled/ itself, the one record deploy.sh uninstall
    writes, not from a status report: the report comes from one release,
    which may be older than the record and not know it. Links and other
    files are refused, as deployment.catalog.uninstalled_components does.
    """
    directory = state / "uninstalled"
    if directory.is_symlink():
        raise ToolError(f"Refuse symlinked uninstall records: {directory}")
    if not directory.exists():
        return []
    names = []
    for record in sorted(directory.iterdir()):
        if record.name.startswith("."):
            continue  # An interrupted atomic write leaves only a temporary file.
        if (
            not host.ID.fullmatch(record.name)
            or record.is_symlink()
            or not record.is_file()
        ):
            raise ToolError(f"Invalid uninstall record {record}")
        names.append(record.name)
    return names


def selected(report, order, versions, component, product, removed):
    """The components to install now: pending first, then incomplete ones.

    removed (uninstalled()) stays out until <product> <component> installs it
    again. An unfinished uninstall is finished, never reinstalled.
    """
    pending = report["pending"]
    if pending and pending["operation"] == "uninstall":
        raise ToolError(
            f"The uninstall of {pending['component']} is unfinished; run the same "
            "./deploy.sh uninstall command in its release again (with --delete-data "
            'if you gave it), see "Remove a component" in the manual'
        )
    if component:
        return [component]
    targets = (
        [pending["component"]] if pending and pending["component"] in order else []
    )
    current = {item["name"]: item for item in report["components"]}
    for name in order:
        item = current.get(name)
        if name in targets:
            continue
        if name in removed and not item:
            log.info(
                f"[OK] {name} was uninstalled; run {product} {name} to install it again"
            )
        elif item and item["complete"] and item["version"] == versions[name]:
            log.info(f"[OK] {name} {item['version']} is installed")
        else:
            targets.append(name)
    return targets


def suggested_address():
    """The local address of the default route, or None without a clear one."""
    try:
        result = run(["ip", "-4", "-o", "route", "get", "192.0.2.1"], check=False)
    except OSError:
        return None
    match = re.search(r"\bsrc (\S+)", result.stdout or "")
    return match.group(1) if result.returncode == 0 and match else None


def gateway_answers(product, args):
    """Settings for the gateway's new config: asked, or from the options."""
    port = host.configured_port(product)
    if port is None:
        raise ToolError(
            f"{host.host_conf(product)} is missing; the administrator runs "
            f"sudo {product}-admin <delivery directory>"
        )
    origin = args.public_origin or ask(
        "Public address (https://<host name>:<port>)",
        f"https://{socket.getfqdn()}:{port}",
        "--public-origin",
    )
    address = args.ip_address or ask(
        "IP address the server listens on", suggested_address(), "--ip-address"
    )
    return [f"PUBLIC_ORIGIN={origin}", f"HTTPS_PORT={port}", f"IP_ADDRESS={address}"]


def credential_files(top):
    """{relative path: path} of the regular files below top; links refused."""
    files = {}
    for directory, names, filenames in os.walk(str(top)):
        for name in names + filenames:
            path = os.path.join(directory, name)
            info = os.lstat(path)
            if name.endswith(".partial"):
                # Left by an interrupted sudo <product>-admin --credentials.
                raise ToolError(
                    f"{path} is an interrupted copy; the administrator runs "
                    "--credentials again"
                )
            if stat.S_ISREG(info.st_mode):
                files[os.path.relpath(path, str(top))] = path
            elif not stat.S_ISDIR(info.st_mode):
                raise ToolError(f"{path} is a link or special file; remove it")
    return files


def read_bytes(path):
    """Read without following a link or opening a device."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ToolError(f"{path} is not a regular file; inspect it")
        return stream.read()


def move_credentials(product, component):
    """Step 5: incoming/<component>/ to state/<component>/, never printing contents."""
    incoming = host.LIB / product / "incoming" / component
    state = host.LIB / product / "state" / component
    if not incoming.is_dir() or incoming.is_symlink():
        return
    files = credential_files(incoming)
    different = []
    for relative, source in sorted(files.items()):
        target = state / relative
        if target.is_symlink() or (
            target.exists() and read_bytes(str(target)) != read_bytes(source)
        ):
            different.append(relative)
    if different:
        raise ToolError(
            f"{', '.join(different)} in {incoming} differ from the files in {state}; "
            "nothing was copied. Remove the wrong copy, then run the same command again"
        )
    for relative, source in sorted(files.items()):
        target = state / relative
        data = read_bytes(source)
        if not target.exists():
            for parent in reversed(target.relative_to(state).parents):
                directory = state / parent
                if not directory.exists():
                    directory.mkdir(mode=0o700)
            partial = target.with_name(target.name + ".partial")
            if partial.is_symlink() or partial.exists():
                partial.unlink()
            descriptor = os.open(
                str(partial),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(str(partial), str(target))
        if read_bytes(str(target)) != data:
            raise ToolError(
                f"{target} could not be verified; run the same command again"
            )
        os.unlink(source)
    for directory, _, _ in sorted(os.walk(str(incoming)), reverse=True):
        os.rmdir(directory)
    if files:
        log.info(
            f"[OK] {component}: {len(files)} delivered credential file(s) in {state}"
        )


def environment_components(product, name):
    """components: of state/<name>.yaml; each listed release checks the rest.

    Only the list is read here, to know which releases to use; the file's
    structure and overrides are the releases' to check (check-environment).
    """
    path = host.LIB / product / "state" / (name + ".yaml")
    if not host.ENVIRONMENT.fullmatch(name):
        raise ToolError(
            f"--environment {name!r}: use lowercase letters, digits and inner hyphens"
        )
    if path.is_symlink() or not path.is_file():
        raise ToolError(
            f"Missing {path}; place the environment file there as {product}'s "
            'runtime user, see "Place the environment file" in the manual'
        )
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        raise ToolError(f"{path} is not valid YAML; correct it and run again") from None
    components = document.get("components") if isinstance(document, dict) else None
    if (
        not isinstance(components, list)
        or not components
        or not all(isinstance(c, str) and host.ID.fullmatch(c) for c in components)
        or len(set(components)) != len(components)
    ):
        raise ToolError(
            f"{path}: components: must list the components of this installation, "
            "each once"
        )
    return path, components


def compatible(version, requirement):
    """version within requirement's inclusive min and exclusive before."""
    key = host.version_key
    return key(requirement["min"]) <= key(version) < key(requirement["before"])


def environment_releases(product, args, found):
    """The listed components' releases, checked before anything changes."""
    path, components = environment_components(product, args.environment)
    missing = sorted(name for name in components if name not in found)
    problems = []
    for name in components:
        if name not in found:
            continue
        for dependency, requirement in sorted(found[name][2]["requires"].items()):
            if dependency not in components:
                raise ToolError(
                    f"{path}: {name} requires {dependency}; add {dependency} to "
                    "components:, then run the same command again"
                )
            if dependency in found and not compatible(
                found[dependency][0].version, requirement
            ):
                problems.append(
                    f"{name} needs {dependency} {requirement['min']} or newer before "
                    f"{requirement['before']}, installed: {found[dependency][0].version}"
                )
    if missing or problems:
        named = ["no release package of " + ", ".join(missing)] if missing else []
        raise ToolError(
            "; ".join(named + problems)
            + f". Nothing was changed. The administrator installs the {product} "
            f"release packages (sudo {product}-admin <delivery directory>); then run "
            "the same command again"
        )
    if args.component and args.component not in components:
        raise ToolError(f"{args.component} is not in components: of {path}")
    removed = uninstalled(host.LIB / product / "state")
    for name in components:
        if name in removed and name != args.component:
            raise ToolError(
                f"{name} was uninstalled but is in components: of {path}; remove it "
                f"there, or run {product} --environment {args.environment} {name} to "
                "install it again"
            )
    return {name: found[name] for name in components}


def install(product, args):
    check_account(product)
    found = releases(product)
    option = []
    if args.environment:
        found = environment_releases(product, args, found)
        option = ["--environment", args.environment]
    order = install_order(product, found)
    if args.component and args.component not in found:
        raise ToolError(
            f"No {product} release of {args.component} is installed; installed: "
            + ", ".join(order)
        )
    first = found[order[0]][1]
    deployed(first, "init-layout")
    if args.environment:
        # Every listed release checks the file before the first change.
        for component in order:
            deployed(found[component][1], "check-environment", args.environment)
    versions = {name: found[name][0].version for name in order}
    removed = uninstalled(host.LIB / product / "state")
    report = status_report(first)
    pending = report["pending"]
    if args.environment and pending and pending["component"] not in order:
        raise ToolError(
            f"The {pending['operation']} of {pending['component']} is unfinished, and "
            f"{pending['component']} is not in this environment; finish it first"
        )
    targets = selected(report, order, versions, args.component, product, removed)
    for component in targets:
        package, path, descriptor = found[component]
        config = host.LIB / product / "state" / component / "config.yaml"
        if not config.exists():
            settings = []
            if "routes" in descriptor["accepts"]:
                settings = gateway_answers(product, args)
            command = ["init-config", component] + option
            for setting in settings:
                command += ["--set", setting]
            deployed(path, *command)
        elif "routes" in descriptor["accepts"] and (
            args.public_origin or args.ip_address
        ):
            log.warning(
                f"WARNING: {config} exists; --public-origin and --ip-address apply only "
                f"to a new config. Edit it, then run {product} {component}"
            )
        move_credentials(product, component)
        deployed(path, "install", *option)
        log.info(f"[OK] {component} {package.version} installed")
    # Delivered credentials are taken only by an install of their component;
    # say so instead of leaving them unused without a word.
    for component in order:
        incoming = host.LIB / product / "incoming" / component
        if component not in targets and incoming.is_dir() and any(incoming.iterdir()):
            log.warning(
                f"WARNING: {incoming} holds delivered files that {component} does not "
                f"use yet; run {product} {component} to install it with them"
            )
    if deploy(found[order[-1]][1], "status").returncode != 0:
        raise ToolError(
            f"status reports an incomplete or inactive component; run {product} again, "
            'or see "If a command stops" in the manual'
        )


def parser(product):
    result = arguments.Parser(
        prog=product,
        usage=(
            f"{product} [--environment <environment>] [<component>] "
            "[--public-origin <url>] [--ip-address <address>] [--verbose]"
        ),
        description=(
            f"Install the installed {product} releases as the runtime account, in "
            "dependency order; with --environment, the components and overrides of "
            f"/var/lib/{product}/state/<environment>.yaml; with <component>, install "
            "that one again with its current config. Repeat the same command after a "
            "stop."
        ),
        allow_abbrev=False,
    )
    result.add_argument(
        "--environment",
        metavar="<environment>",
        help=f"deploy the environment file /var/lib/{product}/state/<environment>.yaml",
    )
    result.add_argument("component", nargs="?", metavar="<component>")
    result.add_argument(
        "--public-origin",
        metavar="<url>",
        help="the gateway's public address, asked if missing",
    )
    result.add_argument(
        "--ip-address",
        metavar="<address>",
        help="the address to listen on, asked if missing",
    )
    result.add_argument(
        "--verbose", action=arguments.Once, default=False, help="also show each command"
    )
    return result


def main(command_line=None):
    product = host.product_name()
    try:
        args = arguments.parse(
            parser(product),
            sys.argv[1:] if command_line is None else command_line,
            flags=("--environment",),
        )
    except arguments.UsageError as error:
        return error.code
    output.configure(verbose=args.verbose, product=product)
    action = " ".join(
        [product]
        + (["--environment", args.environment] if args.environment else [])
        + ([args.component] if args.component else [])
    )
    output.audit(action + ": started")
    try:
        install(product, args)
    except (ToolError, OSError, yaml.YAMLError) as error:
        log.error(f"ERROR: {error}")
        output.audit(action + ": failed")
        return 1
    except KeyboardInterrupt:
        # Ctrl+C: finished work is kept, so the same command continues.
        log.error("ERROR: Interrupted; run the same command again to continue")
        output.audit(action + ": interrupted")
        return 130
    output.audit(action + ": completed")
    log.info(f"PASS: {product} completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
