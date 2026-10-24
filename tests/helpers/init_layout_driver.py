"""Fresh-process bootstrap interruption; only paths/ownership are fixtures."""

import os
import signal
import sys
from pathlib import Path

from deployment import common, layout

root = Path(sys.argv[1])
mode = sys.argv[2]
common.HOME = root / "home/operator-account"
layout.ANCHOR = root / "var-lib"
layout.TRUSTED_TOP = root
layout.ROOT_UID = os.geteuid()
real_open = os.open
real_fsync = os.fsync
real_publish = layout.publish_bootstrap


def opened(path, flags, *args, **kwargs):
    fd = real_open(path, flags, *args, **kwargs)
    if mode == "created" and flags & os.O_CREAT:
        os.kill(os.getpid(), signal.SIGKILL)
    return fd


def synced(fd):
    real_fsync(fd)
    if mode == "synced":
        os.kill(os.getpid(), signal.SIGKILL)


def published(directory, temporary, name):
    real_publish(directory, temporary, name)
    if mode == "published":
        os.kill(os.getpid(), signal.SIGKILL)


layout.os.open = opened
layout.os.fsync = synced
layout.publish_bootstrap = published
layout.initialize("orders")
