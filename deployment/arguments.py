"""argparse conventions shared by deploy.sh and build-bundle.sh (backlog 73).

Usage lines start with "Usage:" and errors with "ERROR:" on stderr, as the
message convention (deployment/output.py) asks; usage errors exit 2 and --help
exits 0. argparse never exits the process: parse raises UsageError with the
exit code, so callers return it like any other result.
"""

import argparse
import sys


class UsageError(Exception):
    """argparse asked to exit; code is the exit status (2 usage, 0 help)."""

    def __init__(self, code=2):
        super().__init__(code)
        self.code = code


class Parser(argparse.ArgumentParser):
    """argparse with the convention's "Usage:" and "ERROR:" prefixes."""

    def format_usage(self):
        return "U" + super().format_usage()[1:]  # argparse writes "usage: ".

    def format_help(self):
        return "U" + super().format_help()[1:]

    def error(self, message):
        sys.stderr.write(self.format_usage())
        sys.stderr.write(f"ERROR: {message}\n")
        raise UsageError(2)

    def exit(self, status=0, message=None):
        if message:
            sys.stderr.write(message)
        raise UsageError(status)


class Once(argparse.Action):
    """A flag that may be given once; a repeat in one parser is a usage error."""

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, False):
            parser.error(f"{option_string} given more than once")
        setattr(namespace, self.dest, True)


def parse(parser, arguments, flags=()):
    """Parse the whole command line, refusing what argparse would let through.

    A flag a subcommand and its parent both accept is counted over the whole
    line, since subparsers fill a separate namespace. The "--" separator is
    refused: no accepted form needs it, and component IDs never start with "-".
    """
    for flag in flags:
        if list(arguments).count(flag) > 1:
            parser.error(f"{flag} given more than once")
    if "--" in arguments:
        parser.error("the -- separator is not accepted")
    return parser.parse_args(list(arguments))
