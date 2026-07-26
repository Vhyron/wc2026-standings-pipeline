#!/usr/bin/env bash
# Dev convenience: refresh the data, then serve it.
# Pipeline must finish before the API starts — dbt needs an exclusive
# write lock on worldcup.duckdb that open read connections would block.
set -euo pipefail
cd "$(dirname "$0")"

# uv syncs .venv from uv.lock before each command, so a fresh clone works
# with no setup step.
uv run pipeline.py
exec uv run uvicorn api:app "$@"
