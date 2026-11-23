"""Notice every open below a forbidden directory (backlog 88).

A consumer's install must not open its producer's raw key. The guard wraps
open functions (builtins.open, io.open, os.open) and resolves each name as
the kernel would, including a name relative to a dir_fd.
"""

import os


def guard(original, forbidden, violation):
    """Wrap original so that opening a path below forbidden calls violation(path)."""
    forbidden = os.path.realpath(forbidden)

    def checked(file, *args, **kwargs):
        if not isinstance(file, int):
            name = os.fsdecode(file)
            directory = kwargs.get("dir_fd")
            if directory is not None and not os.path.isabs(name):
                name = os.path.join(os.readlink(f"/proc/self/fd/{directory}"), name)
            path = os.path.realpath(name)
            if path == forbidden or path.startswith(forbidden + os.sep):
                violation(path)
        return original(file, *args, **kwargs)

    return checked
