#!/usr/bin/env bash
# Build manifest localhost/ demo images; registry images are handled by pull-images.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
images=$(python3 - <<'BUILD_IMAGES'
import sys
import yaml
import bundle

try:
    print("\n".join(bundle.manifest_images()))
except (OSError, bundle.BundleError, yaml.YAMLError) as error:
    print("ERROR: " + str(error), file=sys.stderr)
    raise SystemExit(1)
BUILD_IMAGES
)
while IFS= read -r image; do
    case "$image" in
        localhost/demo-postgres:*)
            source="docker.io/library/postgres:${image##*:}"
            podman pull --policy=always "$source"
            podman tag "$source" "$image";;
        localhost/demo-*:* )
            app=${image#localhost/demo-}
            app=${app%:*}
            [[ $app =~ ^[a-z0-9-]+$ && -f apps/$app/Containerfile ]] || {
                echo "ERROR: no demo build recipe for $image; prepare it with podman build" >&2; exit 1;
            }
            podman build -t "$image" -f "apps/$app/Containerfile" "apps/$app";;
        localhost/*)
            echo "ERROR: no demo build recipe for $image; prepare it with podman build" >&2; exit 1;;
        *) printf 'Registry image %s: use dev/pull-images.sh\n' "$image";;
    esac
done <<< "$images"
