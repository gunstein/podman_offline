#!/usr/bin/env bash
# Render the Mermaid sequence diagrams in ARCHITECTURE.md to docs/diagrams/*.png,
# for viewers without Mermaid support. Needs Node (npx) and a Chromium; set
# CHROMIUM to its path when Puppeteer should not download one.
set -euo pipefail

cd "$(dirname "$0")/.."
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
if [[ -n ${CHROMIUM:-} ]]; then
    printf '{"executablePath":"%s","args":["--no-sandbox"]}' "$CHROMIUM" > "$work/puppeteer.json"
    export PUPPETEER_SKIP_DOWNLOAD=1
else
    echo '{}' > "$work/puppeteer.json"
fi
for pair in "deploy-install:### \`./deploy.sh install\` from an unpacked bundle" \
    "build-bundle:### \`./build-bundle.sh\` in the source checkout"; do
    name=${pair%%:*}
    heading=${pair#*:}
    awk -v heading="$heading" '$0 == heading {f=1} f && /^```mermaid/ {m=1; next} m && /^```/ {exit} m' \
        ARCHITECTURE.md > "$work/$name.mmd"
    [[ -s $work/$name.mmd ]] || { echo "ERROR: no diagram under: $heading" >&2; exit 1; }
    npx -y @mermaid-js/mermaid-cli@11.4.2 -p "$work/puppeteer.json" \
        -i "$work/$name.mmd" -o "docs/diagrams/$name.png" -w 1600 -s 2 -b white >/dev/null
    echo "[OK] docs/diagrams/$name.png"
done
