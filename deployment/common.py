"""Shared release paths, name rules and errors; no lifecycle actions.

The component model is declared in YAML and read by catalog.py.
"""

import os
import pwd
import re
from pathlib import Path

# The account's registered home: its identity and the bootstrap file only.
HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"

# quadlet/template.kube and template.network; @@PRODUCT_NAME@@ and @@UNIT_NAME@@ are filled in.
QUADLET_TEMPLATE = ROOT / "quadlet" / "template.kube"

# Production paths under the installation root. layout.select() assigns them
# for production commands only; source dev and bundle building never do.
# STATE holds component config/credentials, installed metadata and markers,
# registrations and the pending-operation record.
STATE: Path = None  # type: ignore[assignment]
QUADLET_DIR: Path = None  # type: ignore[assignment]
# Tar archives for VOLUME_FILES. Podman imports them into the volumes on every
# start, so they stay in the persistent state directory.
FILES_DIR: Path = None  # type: ignore[assignment]

SECRET_FILES = "SECRET_FILES"
SECRET_TEMPLATES = "SECRET_TEMPLATES"
# Each container's environment; only in the release's config.defaults.yaml.
ENVIRONMENT = "ENVIRONMENT"
# Files mounted into each container; only in the release's config.defaults.yaml.
MOUNTS = "MOUNTS"
VOLUME_FILES = "VOLUME_FILES"

IMPORT_SOURCE = "volume.podman.io/import-source"

ID = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
# The product name is also the default service user, so it follows the
# portable Linux user name rule: a letter first, at most 32 characters.
PRODUCT = re.compile(r"^[a-z]([a-z0-9-]{0,30}[a-z0-9])?$")
SECRET_KEY = re.compile(r"^[-._a-zA-Z0-9]+$")
# Podman rejects secrets over 512,000 bytes (the whole Secret document).
MAX_SECRET_SIZE = 500000

PH = re.compile(r"^@@([A-Z0-9_]+)@@$")
MAX_PORT = 65535


class DeployError(Exception):
    """Error shown as a single ERROR line without a traceback."""
