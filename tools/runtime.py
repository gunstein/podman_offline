"""<product>: install this product's components as the runtime account (backlog 69 WP3).

Phase 1, within the product owner's decisions of 2026-11-01 (BACKLOG.md item
69). The <product>-tools RPM installs this file as
/usr/libexec/<product>-tools/runtime.py; the command is /usr/bin/<product>.
The runtime account runs it in its own login (console or SSH), never root:

    <product> [<component>] [--public-origin <url>] [--ip-address <address>]

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
7. deploy.sh status.
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
    """Components in dependency order; a missing dependency stops."""
    requires = {}
    for component, (_, _, descriptor) in found.items():
        requires[component] = set(descriptor["requires"])
        for dependency in sorted(requires[component] - set(found)):
            raise ToolError(
                f"{component} requires {dependency}, which is not installed; the "
                f"administrator delivers the {product}-{dependency} RPM"
            )
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


def selected(report, order, versions, component):
    """The components to install now: pending first, then incomplete ones."""
    if component:
        return [component]
    pending = report["pending"]
    targets = (
        [pending["component"]] if pending and pending["component"] in order else []
    )
    current = {item["name"]: item for item in report["components"]}
    for name in order:
        item = current.get(name)
        if name in targets:
            continue
        if item and item["complete"] and item["version"] == versions[name]:
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


def install(product, args):
    check_account(product)
    found = releases(product)
    order = install_order(product, found)
    if args.component and args.component not in found:
        raise ToolError(
            f"No {product} release of {args.component} is installed; installed: "
            + ", ".join(order)
        )
    first = found[order[0]][1]
    deployed(first, "init-layout")
    versions = {name: found[name][0].version for name in order}
    targets = selected(status_report(first), order, versions, args.component)
    for component in targets:
        package, path, descriptor = found[component]
        config = host.LIB / product / "state" / component / "config.yaml"
        if not config.exists():
            settings = []
            if "routes" in descriptor["accepts"]:
                settings = gateway_answers(product, args)
            command = ["init-config", component]
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
        deployed(path, "install")
        log.info(f"[OK] {component} {package.version} installed")
    if deploy(found[order[-1]][1], "status").returncode != 0:
        raise ToolError(
            f"status reports an incomplete or inactive component; run {product} again, "
            "or see the troubleshooting section of the manual"
        )


def parser(product):
    result = arguments.Parser(
        prog=product,
        usage=(
            f"{product} [<component>] [--public-origin <url>] [--ip-address <address>] "
            "[--verbose]"
        ),
        description=(
            f"Install the installed {product} releases as the runtime account, in "
            "dependency order; with <component>, install that one again with its "
            "current config. Repeat the same command after a stop."
        ),
        allow_abbrev=False,
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
            parser(product), sys.argv[1:] if command_line is None else command_line
        )
    except arguments.UsageError as error:
        return error.code
    output.configure(verbose=args.verbose, product=product)
    action = " ".join([product] + ([args.component] if args.component else []))
    output.audit(action + ": started")
    try:
        install(product, args)
    except (ToolError, OSError, yaml.YAMLError) as error:
        log.error(f"ERROR: {error}")
        output.audit(action + ": failed")
        return 1
    output.audit(action + ": completed")
    log.info(f"PASS: {product} completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
