#!/bin/bash
# Pure Python: the tests of the parts that need no Calendar library, and the syntax of the scripts.
set -euo pipefail
cd /project/apps/ical-sync
for f in ical_sync.py ical-sync ical-sync-gui; do
    python3 -I -c "import ast,sys; ast.parse(open('$f').read())"
done
python3 -I tests/test_ical_sync.py > /tmp/ical-sync-test.log || { cat /tmp/ical-sync-test.log; exit 1; }
echo "ical-sync: syntax ok, $(grep -c '^ok' /tmp/ical-sync-test.log) tests passed"
