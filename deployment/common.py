"""Shared release paths, name rules and errors; no lifecycle actions.

The component model is declared in YAML and read by catalog.py.
"""

import os
import pwd
import re
from pathlib import Path

HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
MANIFESTS = ROOT / "manifests"
CONFIG = ROOT / "config.yaml"  # Standalone manifest fixtures only.

# A product declares its name in bundles.yaml (product:); it prefixes units,
# the shared network and archives. Standalone manifest fixtures have no
# catalog, so they use this explicit name.
STANDALONE_PRODUCT = "myproduct"

# quadlet/template.kube and template.network; {product} and {name} are filled in.
QUADLET_TEMPLATE = ROOT / "quadlet" / "template.kube"
QUADLET_DIR = HOME / ".config/containers/systemd"
QUADLET_TARGET = QUADLET_DIR / (STANDALONE_PRODUCT + ".kube")
QUADLET_YAML = QUADLET_DIR / (STANDALONE_PRODUCT + ".yaml")
SERVICE = STANDALONE_PRODUCT + ".service"

SECRET_FILES = "SECRET_FILES"
VOLUME_FILES = "VOLUME_FILES"

# Tar archives for VOLUME_FILES. Podman imports them into the volumes on every
# start, so they must stay in the service user's home directory.
FILES_DIR = HOME / "files"
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
