#!/usr/bin/env bash
# Build the demo app images and pull PostgreSQL with the local manifest names.
set -euo pipefail
cd "$(dirname "$0")/.."
# The app list and tag must follow the manifests; the bundle finds images automatically.
for app in identity todo-backend todo-frontend help proxy; do
    podman build -t "localhost/myproduct-$app:0.1.0" -f "apps/$app/Containerfile" "apps/$app"
done
podman pull docker.io/library/postgres:17.11
podman tag docker.io/library/postgres:17.11 localhost/myproduct-postgres:17.11
