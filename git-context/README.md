# Commit context

Reasoning behind the commits in this repo. Commit messages are deliberately kept to a single
summary line; the *why* — the problem being solved, the evidence, and the alternatives that lost
— lives here, one self-contained file per commit.

Each context file lands in the same commit as the change it describes, so the two can't drift
apart. Entries are keyed by number and commit subject rather than SHA: a commit's SHA isn't
knowable until after it exists, and backfilling one would mean rewriting history.

| # | Commit | Area | Files |
|---|--------|------|-------|
| [001](001-adopt-uv-toolchain.md) | `build: replace requirements.txt with pyproject.toml and uv.lock` | dependencies / toolchain | `pyproject.toml`, `.python-version`, `uv.lock`, `requirements.txt` (deleted) |
