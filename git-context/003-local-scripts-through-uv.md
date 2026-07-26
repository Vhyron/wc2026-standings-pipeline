# 003 — build: run local scripts through uv

**Commit:** `build: run local scripts through uv`
**Area:** ops / developer experience
**Files:** `run.sh`, `setup_cron.sh`

## What changed

Both scripts stop hardcoding an interpreter path and defer to `uv run`:

```bash
# run.sh — before
PYTHON="${PYTHON:-venv/bin/python}"
"$PYTHON" pipeline.py
exec "$PYTHON" -m uvicorn api:app "$@"

# run.sh — after
uv run pipeline.py
exec uv run uvicorn api:app "$@"
```

`setup_cron.sh` now resolves uv with `command -v uv`, exits with an install hint if it isn't
found, and emits a cron line that `cd`s into the project first:

```
0 8 * * * cd $DIR && $UV run pipeline.py >> $DIR/pipeline.log 2>&1
```

The ordering comment in `run.sh` (pipeline before API, because dbt needs the exclusive DuckDB
write lock) and the macOS Full Disk Access note in `setup_cron.sh` are both preserved.

## Why

**This closes `issues/006`.** Both scripts pointed at `venv/`; the working copy had `.venv/`.
`./run.sh` therefore died instantly on a fresh clone, and `setup_cron.sh` was worse — it
*succeeded*, printing a crontab line referencing an interpreter that didn't exist, so the job it
told you to install would fail silently every night at 08:00. That issue framed the fix as
"pick one of `venv/` or `.venv/` and make everything agree"; adopting uv answers it differently
and better, by removing the choice. uv owns exactly one venv path and creates it on demand, so
there is no longer a convention to get wrong.

**`uv run` also removes the setup step.** It syncs `.venv` from `uv.lock` before running, so a
fresh clone goes straight to `./run.sh` — no "create a venv first" instruction that can drift out
of date, and no `PYTHON=` override needed as a stopgap.

**The cron line needs uv's absolute path** because cron runs with a bare `PATH` that won't
include `/opt/homebrew/bin` (or `~/.local/bin`). That was the original reason the script
hardcoded `$DIR/venv/bin/python`, and it still applies — only the binary changed. The `cd $DIR &&`
prefix is new and necessary: `uv run` discovers the project from the working directory, and
cron starts in `$HOME`.

**Failing loudly when uv is missing** addresses the second half of `issues/006` directly. The old
script's real sin wasn't the wrong path, it was printing a confidently broken cron line; the
guard means it now refuses rather than emitting something that fails at 08:00 with no output
anyone reads.

## Evidence

The generated line resolves to a real binary — the check the old script would have failed:

```
$ bash setup_cron.sh
0 8 * * * cd /Users/vhyron/desktop/worldcup-analytics-pipeline && /opt/homebrew/bin/uv run pipeline.py >> .../pipeline.log 2>&1

$ bash setup_cron.sh | grep -oE '/[^ ]+/uv' | head -1 | xargs ls -l
lrwxr-xr-x /opt/homebrew/bin/uv -> ../Cellar/uv/0.11.8/bin/uv
```

## Alternatives rejected

**Keeping the `PYTHON` override in `run.sh`.** It existed so you could work around the wrong
default (`PYTHON=.venv/bin/python ./run.sh`). With uv owning the venv there is nothing left to
work around, and the variable would just be another way to run against the wrong interpreter.

**Pointing the scripts at `.venv/bin/python` directly.** Would work, but skips the sync — a stale
`.venv` after a `uv.lock` change would run silently against outdated dependencies. `uv run` is
the right call here precisely because these are interactive/scheduled *developer* entry points.
The systemd units make the opposite trade for good reason; see [004].

## Verify

```bash
./run.sh                 # pipeline runs to completion, then uvicorn starts
bash setup_cron.sh | grep -oE '/[^ ]+/uv' | head -1 | xargs ls -l   # path exists
grep -rn "venv" run.sh setup_cron.sh                                # no hits
```

Temporarily shadowing uv (`PATH=/usr/bin bash setup_cron.sh`) should produce the install hint and
a non-zero exit, not a cron line.

[004]: 004-systemd-uv-venv.md
