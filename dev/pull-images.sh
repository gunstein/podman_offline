#!/usr/bin/env bash
# Pull manifest registry images without building or replacing localhost/ images.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PULL_IMAGES'
import sys
import yaml
import bundle

try:
    bundle.pull_images(bundle.manifest_images())
except (OSError, bundle.BundleError, yaml.YAMLError) as error:
    print("ERROR: " + str(error), file=sys.stderr)
    raise SystemExit(1)
PULL_IMAGES
