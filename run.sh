#!/usr/bin/env bash
# Dev convenience: refresh the data, then serve it.
# Pipeline must finish before the API starts — dbt needs an exclusive
# write lock on worldcup.duckdb that open read connections would block.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-venv/bin/python}"

"$PYTHON" pipeline.py
exec "$PYTHON" -m uvicorn api:app "$@"
