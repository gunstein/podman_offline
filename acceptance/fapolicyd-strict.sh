#!/usr/bin/env bash
# P2 creation only: derive the authorized stricter policy from clean-agent.
set -euo pipefail
test ! -e /var/lib/myproduct
test -z "$(rpm -qa 'myproduct*')"
test "$(getenforce)" = Enforcing
fapolicyd-cli --list > /root/wp0-rules-before.txt
# Match the effective rule text rather than deleting numbered source lines.
python3 - <<'PY'
from pathlib import Path
import re
rules = Path('/root/wp0-rules-before.txt').read_text().splitlines()
remove = {'allow perm=any uid=0 : dir=/var/tmp/',
          'allow perm=any uid=0 trust=1 : all',
          'allow perm=any all : ftype=text/x-shellscript'}
actual = {re.sub(r'^\d+\.\s*', '', line).strip() for line in rules}
if not remove <= actual:
    raise SystemExit('FAIL: clean-agent rules differ from the authorized P1 baseline')
found = []
for path in Path('/etc/fapolicyd/rules.d').glob('*.rules'):
    lines = path.read_text().splitlines(keepends=True)
    kept = []
    for line in lines:
        if line.strip() in remove:
            found.append(line.strip())
        else:
            kept.append(line)
    if kept != lines:
        path.write_text(''.join(kept))
if set(found) != remove or len(found) != 3:
    raise SystemExit('FAIL: expected exactly the three authorized source rules')
path = Path('/etc/fapolicyd/fapolicyd.conf')
text = path.read_text()
for name, value in [('trust', 'rpmdb'), ('integrity', 'sha256')]:
    text, count = re.subn(r'(?m)^' + name + r'\s*=.*$', name + ' = ' + value, text)
    if count != 1:
        raise SystemExit('FAIL: expected one active ' + name + ' setting')
path.write_text(text)
PY
fagenrules --load
systemctl restart fapolicyd
systemctl is-active fapolicyd
test ! -e /var/lib/myproduct
test -z "$(rpm -qa 'myproduct*')"
