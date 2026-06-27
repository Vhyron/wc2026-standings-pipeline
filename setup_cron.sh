#!/usr/bin/env bash
# Prints the cron line + short setup steps for this machine.
# Doesn't edit the crontab itself -- you paste the line via `crontab -e`.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Use the project venv so duckdb is importable under cron's bare environment.
PYTHON="$DIR/venv/bin/python"
CRON_LINE="0 8 * * * $PYTHON $DIR/pipeline.py >> $DIR/pipeline.log 2>&1"

echo ""
echo "Cron line (daily 08:00):"
echo "    $CRON_LINE"
echo ""
echo "Install it:"
echo "  1. crontab -e        open the crontab"
echo "  2. paste the line    (vim: press i, paste, Esc, type :wq, Enter)"
echo "  3. crontab -l        confirm it's there"
echo ""
echo "macOS: also grant Full Disk Access to /usr/sbin/cron in"
echo "System Settings > Privacy & Security > Full Disk Access, or the job won't run."
echo ""