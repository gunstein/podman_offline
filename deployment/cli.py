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
from .output import audit, configure, log

USAGE = (
    "./deploy.sh validate|prepare|install|uninstall [<component>] "
    "[--delete-data] | init-layout | init-config <component> | status [--json]"
)
# Commands that change the target; each start and result goes to the journal.
AUDITED = ("init-layout", "init-config", "install", "uninstall")


class UsageError(Exception):
    """Raised instead of argparse's own exit, so main returns the code."""


class Parser(argparse.ArgumentParser):
    """Keep the historical "Usage:" line and never exit from inside main."""

    def format_usage(self):
        return "Usage: " + (self.usage or USAGE) + "\n"

    def format_help(self):
        return self.format_usage() + super().format_help().split("\n", 1)[1]

    def error(self, message):
        sys.stderr.write(self.format_usage())
        sys.stderr.write(f"ERROR: {message}\n")
        raise UsageError()

    def exit(self, status=0, message=None):
        if message:
            sys.stderr.write(message)
        raise UsageError(status)


class Once(argparse.Action):
    """A flag that may be given once; a repeat is a usage error."""

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, False):
            parser.error(f"{option_string} given more than once")
        setattr(namespace, self.dest, True)


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
    """Name the command, component and version for the journal; never config."""
    subject = command
    try:
        descriptor = deploy.bundle_descriptor()
        name = getattr(args, "component", None) or descriptor["name"]
        subject += f" {name} {descriptor['version']}"
    except (OSError, common.DeployError, yaml.YAMLError):
        if getattr(args, "component", None):
            subject += " " + args.component
    if getattr(args, "delete_data", False):
        subject += " --delete-data"
    return subject


def journal_product():
    """The product named by this release; a standalone fixture uses its default."""
    try:
        return catalog.product_name(common.ROOT)
    except (OSError, common.DeployError, yaml.YAMLError):
        return common.STANDALONE_PRODUCT


def run(args):
    """Run one parsed command; return 1 for an expected failure."""
    try:
        if args.command == "status":
            return status.status(json_output=args.json)
        if args.command == "init-config":
            deploy.init_config(args.component)
        elif args.command == "uninstall":
            deploy.uninstall(args.component, args.delete_data)
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
            service = (
                catalog.unit_name(deploy.bundle_descriptor()["name"]) + ".service"
                if (common.ROOT / "bundle.yaml").is_file()
                else common.SERVICE
            )
            log.error(
                f"Troubleshoot: journalctl --user -u {service} and "
                "/usr/lib/systemd/user-generators/podman-user-generator --dryrun"
            )
        return 1
    except (OSError, common.DeployError, yaml.YAMLError) as error:
        log.error(f"ERROR: {error}")
        return 1
    log.info(f"PASS: ./deploy.sh {args.command} completed")
    return 0


def main(arguments=None):
    """Parse the command line, run the command and return its exit code."""
    try:
        args = parser().parse_args(sys.argv[1:] if arguments is None else arguments)
    except UsageError as error:
        return error.args[0] if error.args else 2
    audited = args.command in AUDITED
    configure(verbose=args.verbose, product=journal_product() if audited else None)
    if not audited:
        return run(args)
    subject = audit_subject(args.command, args)
    audit(f"{subject}: started")
    code = run(args)
    audit(
        f"{subject}: {'completed' if code == 0 else 'failed (exit ' + str(code) + ')'}"
    )
    return code
