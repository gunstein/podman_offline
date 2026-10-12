#!/usr/bin/env bash
# Bygg demoens app-images og hent PostgreSQL med lokale manifestnavn.
set -euo pipefail
cd "$(dirname "$0")/.."
for app in identity todo-backend todo-frontend help proxy; do
    podman build -t "localhost/myproduct-$app:0.1.0" -f "apps/$app/Containerfile" "apps/$app"
done
podman pull docker.io/library/postgres:17.11
podman tag docker.io/library/postgres:17.11 localhost/myproduct-postgres:17.11
