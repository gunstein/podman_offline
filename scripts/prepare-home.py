#!/usr/bin/env python3
"""Prepare rootless directories through held descriptors, as the service user."""

import os
import stat
import sys

DIRECTORIES = (
    ".local",
    ".local/share",
    ".local/share/containers",
    ".local/share/containers/storage",
    ".config",
    ".config/cni",
    ".config/cni/net.d",
    ".config/containers",
    ".config/containers/systemd",
)
LOCK = ".config/cni/net.d/cni.lock"
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def owned_directory(descriptor, path):
    """Never repair an object owned by a different account."""
    if os.fstat(descriptor).st_uid != os.geteuid():
        raise ValueError("Inspect directory owned by another user: " + path)


def check_lock(parent, path):
    """Inspect without following links or waiting on a planted FIFO."""
    info = os.stat("cni.lock", dir_fd=parent, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError("Inspect unsafe CNI lock: " + path)


def open_directories(home, descriptors, create):
    """Check all existing managed paths first; only then create missing ones."""
    for relative in DIRECTORIES:
        parent, name = os.path.split(relative)
        if parent not in descriptors:
            continue
        path = os.path.join(home, relative)
        if create:
            try:
                os.mkdir(name, mode=0o700, dir_fd=descriptors[parent])
            except FileExistsError:
                pass
        try:
            descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=descriptors[parent])
        except FileNotFoundError:
            if not create:
                continue
            raise
        descriptors[relative] = descriptor
        owned_directory(descriptor, path)


def prepare(home):
    """Create the known tree and lock without truncation or pathname chmod."""
    descriptors = {}
    try:
        descriptors[""] = os.open(home, DIRECTORY_FLAGS)
        owned_directory(descriptors[""], home)
        open_directories(home, descriptors, create=False)
        parent = os.path.dirname(LOCK)
        if parent in descriptors:
            try:
                check_lock(descriptors[parent], os.path.join(home, LOCK))
            except FileNotFoundError:
                pass
        # Reopen from the held home after preflight. O_NOFOLLOW still applies
        # if a service process replaces a checked path during preparation.
        for relative in list(descriptors):
            if relative:
                os.close(descriptors.pop(relative))
        open_directories(home, descriptors, create=True)
        for descriptor in descriptors.values():
            os.fchmod(descriptor, 0o700)
        try:
            descriptor = os.open(
                "cni.lock",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=descriptors[parent],
            )
        except FileExistsError:
            # Another process may have created it since preflight. Never unlink,
            # truncate or chmod the existing object, even in this race.
            check_lock(descriptors[parent], os.path.join(home, LOCK))
        else:
            os.close(descriptor)
    finally:
        for descriptor in descriptors.values():
            os.close(descriptor)


def main():
    if len(sys.argv) != 2 or os.geteuid() == 0:
        raise SystemExit(
            "ERROR: prepare-home requires a non-root service user and home"
        )
    try:
        prepare(sys.argv[1])
    except (OSError, ValueError) as error:
        # File paths and OS errors are useful; no application file is read.
        raise SystemExit(
            "ERROR: Unsafe or inaccessible service home; inspect it: " + str(error)
        )


if __name__ == "__main__":
    main()
