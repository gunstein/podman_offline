"""Root command parsing and concise error reporting."""

import subprocess
import sys

import yaml

from . import common, deploy


def main():
    """Run the chosen deploy command and return an exit code for expected errors."""
    commands = {
        "prepare": deploy.prepare,
        "install": deploy.install,
        "uninstall": deploy.uninstall,
        "init-config": deploy.init_config,
        "validate": deploy.validate,
    }
    args = sys.argv[1:]
    removing = bool(args and args[0] == "uninstall")
    # Component arguments are checked against the bundle's own descriptor later.
    names = [arg for arg in args[1:] if arg != "--delete-data"]
    valid_remove = (
        removing
        and len(names) <= 1
        and args[1:].count("--delete-data") <= 1
        and all(common.ID.fullmatch(name) for name in names)
    )
    initializing = bool(
        args
        and args[0] == "init-config"
        and len(args) == 2
        and common.ID.fullmatch(args[1])
    )
    if (
        not args
        or args[0] not in commands
        or (
            not valid_remove
            and not initializing
            and (len(args) != 1 or args[0] == "init-config")
        )
    ):
        print(
            "Usage: ./deploy validate|prepare|install|uninstall [<component>] [--delete-data] | init-config <component>"
        )
        return 2

    try:
        if initializing:
            deploy.init_config(args[1])
        elif removing:
            deploy.uninstall(names[0] if names else None, "--delete-data" in args[1:])
        else:
            commands[args[0]]()
    except subprocess.CalledProcessError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        if args[0] == "install":
            service = (
                "myproduct-" + deploy.bundle_descriptor()["name"] + ".service"
                if (common.ROOT / "bundle.yaml").is_file()
                else common.SERVICE
            )
            print(
                f"Troubleshoot: journalctl --user -u {service} and "
                "/usr/lib/systemd/user-generators/podman-user-generator --dryrun",
                file=sys.stderr,
            )
        return 1
    except (OSError, common.DeployError, yaml.YAMLError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0
