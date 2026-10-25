#!/usr/bin/env bash
# Read-only evidence only; do not repair a failed probe.
set -euo pipefail
status=0
ausearch -m FANOTIFY,AVC -ts boot --raw > /root/wp0-audit.txt 2>&1 || status=$?
cat /root/wp0-audit.txt
if [[ $status != 0 && $status != 1 ]]; then exit "$status"; fi
