#!/usr/bin/env bash
# Prints the cron line + short setup steps for this machine.
# Doesn't edit the crontab itself -- you paste the line via `crontab -e`.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# cron runs with a bare PATH, so the cron line needs uv's absolute path.
UV="$(command -v uv || true)"
if [ -z "$UV" ]; then
    echo "uv not found on PATH -- install it first:" >&2
    echo "    curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

# cd first so uv finds pyproject.toml/uv.lock; `uv run` syncs .venv as needed.
CRON_LINE="0 8 * * * cd $DIR && $UV run pipeline.py >> $DIR/pipeline.log 2>&1"

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
