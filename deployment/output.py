"""Operator messages through standard-library logging (backlog 74).

One convention for every command (docs/REVIEW_GUIDE.md, "Operator messages"):

- ``log.info("[OK] ...")`` for a completed step, on stdout;
- ``log.warning("WARNING: ...")`` and ``log.error("ERROR: ...")`` on stderr,
  with the next action in the same message;
- ``log.info("PASS: ...")`` as the last line of a successful command;
- ``log.debug("+ command")`` for each host command, shown with ``--verbose``.

Results and data (the status table, ``--json``, rendered output) stay plain
``print`` on stdout. No message contains a secret value.

The ``deployment`` logger is set up when this module is imported, so callers
that use the lifecycle functions directly (tests, the harness) see the same
text on the same streams. The handlers look up ``sys.stdout``/``sys.stderr``
when they write, so redirected streams receive the messages. Entry points call
``configure`` to choose the level and to start the audit trail.
"""

import logging
import logging.handlers
import os
import sys

log = logging.getLogger("deployment")
# Separate from the terminal messages: one line per operator action, journal only.
audit_log = logging.getLogger("deployment-audit")
SYSLOG = "/dev/log"


class CurrentStream(logging.StreamHandler):
    """Write to the current sys.stdout or sys.stderr, also after a redirect."""

    def __init__(self, name):
        self.name_of_stream = name
        super().__init__()

    @property
    def stream(self):
        return getattr(sys, self.name_of_stream)

    @stream.setter
    def stream(self, value):
        """StreamHandler assigns a stream; the current one is always used."""


class QuietSysLogHandler(logging.handlers.SysLogHandler):
    """A journal that goes away never interrupts or clutters the command."""

    def handleError(self, record):
        pass


def terminal_handlers():
    """INFO and DEBUG to stdout, WARNING and above to stderr."""
    out = CurrentStream("stdout")
    out.addFilter(lambda record: record.levelno < logging.WARNING)
    err = CurrentStream("stderr")
    err.setLevel(logging.WARNING)
    for handler in (out, err):
        handler.setFormatter(logging.Formatter("%(message)s"))
    return [out, err]


def setup():
    """Install the terminal handlers once; repeated imports change nothing."""
    if not log.handlers:
        for handler in terminal_handlers():
            log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
    audit_log.propagate = False
    if not audit_log.handlers:
        audit_log.addHandler(logging.NullHandler())
    audit_log.setLevel(logging.INFO)


def configure(verbose=False, product=None, address=None):
    """Choose the terminal level and (re)start the journal audit trail.

    With product, audit lines go to the local journal with that identifier
    (journalctl -t <product>); address defaults to SYSLOG. Without a reachable
    journal socket (tests, containers) the command still works and audits
    nothing.
    """
    setup()
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    for handler in list(audit_log.handlers):
        audit_log.removeHandler(handler)
        handler.close()
    handler = None
    if product is not None:
        try:
            handler = QuietSysLogHandler(address=address or SYSLOG)
        except OSError:
            handler = None
    if handler is None:
        audit_log.addHandler(logging.NullHandler())
        return
    handler.ident = f"{product}[{os.getpid()}]: "
    handler.setFormatter(logging.Formatter("%(message)s"))
    audit_log.addHandler(handler)


def audit(message):
    """Record one operator action or result in the journal; never a secret value."""
    audit_log.info(message)


setup()
