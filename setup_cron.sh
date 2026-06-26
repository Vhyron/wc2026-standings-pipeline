#!/usr/bin/env bash
# Helper: prints the exact crontab line for THIS machine, with correct
# absolute paths resolved automatically. Run it, copy the line it prints,
# then `crontab -e` and paste.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(command -v python3)"
SCRIPT="$PROJECT_DIR/pipeline.py"
LOG="$PROJECT_DIR/pipeline.log"

echo "Add this line to your crontab (run 'crontab -e'):"
echo ""
echo "0 8 * * * $PYTHON $SCRIPT >> $LOG 2>&1"
echo ""
echo "That runs the pipeline daily at 08:00, logging to pipeline.log"
