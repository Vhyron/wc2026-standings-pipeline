# 001 — build: replace requirements.txt with pyproject.toml and uv.lock

**Commit:** `build: replace requirements.txt with pyproject.toml and uv.lock`
**Area:** dependencies / toolchain
**Files:** `pyproject.toml`, `.python-version`, `uv.lock`, `requirements.txt` (deleted)

## What changed

Dependency declaration moves from `requirements.txt` (pip, unlocked) to `pyproject.toml` +
`uv.lock` (uv, locked). The interpreter is pinned to Python 3.14 via `.python-version`, and
`requirements.txt` is deleted rather than kept as a generated export — there is now exactly one
source of dependency truth.

The six direct dependencies carry over unchanged. Two lines did **not** carry over:

```python
# both removed:
mashumaro>=3.22; python_version >= "3.14"
google-cloud-bigquery>=3.25   # comment about protobuf 7.x conflicting with dbt-adapters
```

`[tool.uv] package = false` marks this a non-package project: `pipeline.py` and `api.py` are
top-level scripts, not an importable library, so uv installs the dependencies and skips building
the project itself. No build backend is needed.

## Why

Three problems had accumulated under pip.

**No lockfile.** Local, CI, and the Pi each resolved independently against live PyPI, so the
three environments were never provably identical — and nothing would have told us if they
diverged. `uv.lock` pins the full transitive graph, and `uv sync --locked` in CI (see [002]) now
fails loudly rather than silently re-resolving.

**Both pip workarounds had gone stale, and one was actively breaking.** The `mashumaro` override
was added because `dbt-core` capped `mashumaro<3.15` while nothing below 3.15 ran on Python
3.14. `dbt-core` 1.12 now caps `<3.18`, and mashumaro 3.17 supports 3.14 — so the override
became both redundant *and* unsatisfiable: `>=3.22` cannot coexist with dbt's `<3.18`. pip
tolerated the contradiction with a warning; uv's resolver treats it as the hard conflict it is
and refuses to resolve. Removing it is what makes the migration possible, not a side cleanup.

**The venv was broken anyway.** `run.sh` and `setup_cron.sh` pointed at `venv/`, the working copy
had `.venv/`, and that `.venv/` ran Python 3.9.6 — below `dbt-core`'s `>=3.10` floor, so it could
not install this project at all. uv creating and owning a single `.venv/` removes the ambiguity
(the script side of this is [003]).

## Evidence

Every claim below came from PyPI metadata at the time of the commit. Re-run these when the pins
next move:

```bash
# dbt's mashumaro cap, and its actual Python support
curl -s https://pypi.org/pypi/dbt-core/json | python3 -c "
import json,sys; d=json.load(sys.stdin)['info']
print(d['version'], d['requires_python'])
print([r for r in d['requires_dist'] if 'mashumaro' in r or 'protobuf' in r])"
# -> 1.12.0 >=3.10
#    ['mashumaro[msgpack]<3.18,>=3.9', 'protobuf<8.0,>=6.0']

# mashumaro 3.17 is inside that cap AND supports 3.14
curl -s https://pypi.org/pypi/mashumaro/3.17/json | python3 -c "
import json,sys
print([c.split('::')[-1].strip() for c in json.load(sys.stdin)['info']['classifiers']
       if 'Programming Language :: Python ::' in c])"
# -> ['Only', '3.10', '3.11', '3.12', '3.13', '3.14', '3.9']
```

**3.14 is supported end to end**, including on the Pi. `dbt-core`, `dbt-adapters`, `dbt-common`
and `duckdb` all declare 3.14. The compiled dependencies all publish `cp314` **linux aarch64**
wheels, which is what makes the Raspberry Pi deployment viable — `duckdb` 1.5.5
(`manylinux_2_26_aarch64`), `grpcio` 1.83.0, `pydantic-core` 2.47.0. `fastapi`, `uvicorn` and
`google-cloud-bigquery` are pure-Python. Nothing has to build from source on the Pi.

**The protobuf "conflict" was never real.** `dbt-adapters` pins `protobuf<7`, google's chain
(`google-api-core`, `proto-plus`, `googleapis-common-protos`) allows `<8`. The intersection —
protobuf 6.x — is perfectly satisfiable; pip simply failed to backtrack into it and installed
7.x with a warning. uv lands on 6.x without any override:

```
$ uv pip show mashumaro protobuf
mashumaro 3.17
protobuf  6.33.6
```

Confirmed working after `uv sync`: `uv run python -VV` → 3.14.4, `uv run dbt --version` → dbt
1.12.0 / duckdb plugin 1.10.1, and a full `uv run pipeline.py` → 23 tournaments, 1069 matches,
dbt build passed.

## Alternatives rejected

**Python 3.12 instead of 3.14.** The initial instinct, purely to match what CI already ran. It
had no technical basis once the metadata was checked: the only thing that ever made 3.14
awkward was dbt's old mashumaro cap, which upstream has since fixed. Pinning to 3.12 would have
meant carrying a lower version for no reason.

**Core + optional extras** (`[project.optional-dependencies]` with `api` and `bigquery` groups).
Extras only pay off when some environment genuinely installs less. Here CI needs
pipeline+bigquery, the Pi needs all six, and local dev needs all six — so extras would have
bought CI two skipped pure-Python wheels in exchange for `--extra` flags in the workflow,
`run.sh`, both systemd units and the Pi docs, plus a `[tool.uv] conflicts` hazard if the sets
ever diverged. Worth revisiting only if an environment appears that actually needs a slimmer
install.

**Keeping a generated `requirements.txt`** via `uv export`, so the Pi could stay on pip. Rejected
because two sources of truth drift, and uv installs cleanly on the Pi anyway (see [005]).

## Verify

```bash
rm -rf .venv && uv sync
uv lock --check                  # lock is up to date with pyproject.toml
uv run python -VV                # 3.14.x
uv pip show mashumaro protobuf   # mashumaro 3.17.x (< dbt's 3.18 cap), protobuf 6.x (not 7.x)
uv run pipeline.py               # 23 tournaments, 1069 matches, dbt build passed
```

The `protobuf` check is the one worth keeping an eye on: if a future `dbt-adapters` drops its
`<7` pin, 7.x becomes reachable and this line will change legitimately.

[002]: 002-ci-uv-sync-locked.md
[003]: 003-local-scripts-through-uv.md
[005]: 005-docs-uv-workflow.md
