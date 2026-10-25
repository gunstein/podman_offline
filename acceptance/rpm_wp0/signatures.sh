#!/usr/bin/env bash
# WP0 fixture build, inside the disposable OL9 container only.
set -euo pipefail
dnf -y -q install rpm-build rpm-sign gnupg2 createrepo_c >/dev/null
export GNUPGHOME=/key
python3 -B /support/fixtures.py
