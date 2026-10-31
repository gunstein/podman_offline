"""Root command parsing and concise error reporting.

argparse with one subcommand per command (backlog 73). Newer tools call older
releases' deploy.sh, so the accepted forms are a release interface: validate,
prepare, install, init-layout, uninstall [<component>] [--delete-data],
init-config <component> and status [--json]. Usage errors exit 2 on stderr,
--help exits 0 on stdout, failures exit 1. Operator messages follow
deployment/output.py.
"""

import argparse
import subprocess
import sys

import yaml

from . import catalog, common, deploy, status, validation
from .arguments import Once, Parser, UsageError, parse
from .output import audit, configure, log

USAGE = (
    "./deploy.sh validate|prepare|install|uninstall [<component>] "
    "[--delete-data] | init-layout | init-config <component> | status [--json]"
)
# Commands that change the target; each start and result goes to the journal.
AUDITED = ("init-layout", "init-config", "install", "uninstall")


def component_id(value):
    """Lowercase letters, digits and inner hyphens; the bundle decides the rest."""
    if not common.ID.fullmatch(value):
        raise argparse.ArgumentTypeError(f"invalid component ID {value!r}")
    return value


def parser():
    """One parser per command, each declaring only its own arguments."""
    root = Parser(prog="./deploy.sh", usage=USAGE, allow_abbrev=False)
    verbose = Parser(add_help=False, allow_abbrev=False)
    # SUPPRESS keeps a --verbose given before the command.
    verbose.add_argument(
        "--verbose",
        action=Once,
        default=argparse.SUPPRESS,
        help="also show each host command (+ command)",
    )
    root.add_argument("--verbose", action=Once, default=False, help=argparse.SUPPRESS)
    commands = root.add_subparsers(dest="command", metavar="<command>")
    commands.required = True  # Python 3.6 has no required= argument here.

    def command(name, help_text, usage):
        return commands.add_parser(
            name,
            help=help_text,
            usage=usage,
            parents=[verbose],
            allow_abbrev=False,
        )

    command("validate", "check declarations without writing", "./deploy.sh validate")
    command(
        "prepare", "render dev YAML from the source checkout", "./deploy.sh prepare"
    )
    command("install", "install this bundle's component", "./deploy.sh install")
    command(
        "init-layout",
        "create the runtime account's bootstrap file",
        "./deploy.sh init-layout",
    )
    remove = command(
        "uninstall",
        "uninstall this bundle's component",
        "./deploy.sh uninstall [<component>] [--delete-data]",
    )
    remove.add_argument("component", nargs="?", type=component_id)
    remove.add_argument(
        "--delete-data",
        action=Once,
        default=False,
        help="also delete the component's volumes and state",
    )
    init = command(
        "init-config",
        "create the component's persistent config",
        "./deploy.sh init-config <component>",
    )
    init.add_argument("component", type=component_id)
    show = command("status", "show installed components", "./deploy.sh status [--json]")
    show.add_argument("--json", action=Once, default=False, help="machine output")
    return root


def audit_subject(command, args):
    """Name the command, component and executing bundle's version; never config.

    The bundle version is labelled as such: an uninstall may run from another
    release's bundle than the installed one (run() adds what it removed).
    """
    subject = command
    try:
        descriptor = deploy.bundle_descriptor()
        name = getattr(args, "component", None) or descriptor["name"]
        subject += f" {name} (bundle {descriptor['version']})"
    except (OSError, common.DeployError, yaml.YAMLError):
        if getattr(args, "component", None):
            subject += " " + args.component
    if getattr(args, "delete_data", False):
        subject += " --delete-data"
    return subject


def journal_product():
    """The product named by this release or checkout; None writes no journal lines."""
    try:
        return catalog.product_name(common.ROOT)
    except (OSError, common.DeployError, yaml.YAMLError):
        return None


def run(args):
    """Run one parsed command; return (exit code, result note for the journal)."""
    note = ""
    try:
        if args.command == "status":
            return status.status(json_output=args.json), note
        if args.command == "init-config":
            deploy.init_config(args.component)
        elif args.command == "uninstall":
            removed = deploy.uninstall(args.component, args.delete_data)
            if removed:
                note = f"; removed installed version {removed}"
        else:
            {
                "prepare": deploy.prepare,
                "install": deploy.install,
                "init-layout": deploy.init_layout,
                "validate": validation.validate,
            }[args.command]()
    except subprocess.CalledProcessError as error:
        log.error(f"ERROR: {error}")
        if args.command == "install":
            service = catalog.unit_name(deploy.bundle_descriptor()["name"]) + ".service"
            log.error(
                f"Troubleshoot: journalctl --user -u {service} and "
                "/usr/lib/systemd/user-generators/podman-user-generator --dryrun"
            )
        return 1, note
    except (OSError, common.DeployError, yaml.YAMLError) as error:
        log.error(f"ERROR: {error}")
        return 1, note
    log.info(f"PASS: ./deploy.sh {args.command} completed")
    return 0, note


def main(arguments=None):
    """Parse the command line, run the command and return its exit code."""
    try:
        args = parse(
            parser(),
            sys.argv[1:] if arguments is None else arguments,
            flags=("--verbose", "--delete-data", "--json"),
        )
    except UsageError as error:
        return error.code
    audited = args.command in AUDITED
    configure(verbose=args.verbose, product=journal_product() if audited else None)
    if not audited:
        return run(args)[0]
    subject = audit_subject(args.command, args)
    audit(f"{subject}: started")
    code, note = run(args)
    result = "completed" + note if code == 0 else f"failed (exit {code})"
    audit(f"{subject}: {result}")
    return code
