# 002 — ci: install dependencies with uv sync --locked

**Commit:** `ci: install dependencies with uv sync --locked`
**Area:** CI
**Files:** `.github/workflows/pipeline.yml`

## What changed

The daily workflow installs with uv instead of pip:

```yaml
# before
- uses: actions/setup-python@v6
  with:
    python-version: "3.12"
- name: Install dependencies
  run: pip install -r requirements.txt
...
- name: Run pipeline
  run: python pipeline.py

# after
- uses: astral-sh/setup-uv@v6
  with:
    enable-cache: true
- name: Install dependencies
  run: uv sync --locked
...
- name: Run pipeline
  run: uv run python pipeline.py
```

The GCP credentials step and the `WC_BQ_PROJECT`/`WC_BQ_DATASET`/`GOOGLE_APPLICATION_CREDENTIALS`
env block are untouched — the BigQuery publish path behaves exactly as before.

## Why

**`--locked` is the whole point of committing `uv.lock`.** Without it, a stale lock would be
quietly re-resolved and CI would keep passing while testing a dependency set nobody had
reviewed — which is the pre-migration behaviour this work exists to end. With it, a `pyproject.toml`
change that wasn't accompanied by a `uv lock` fails the run immediately, loudly, and in the one
place that always executes.

**The hardcoded `python-version: "3.12"` had to go**, not just because [001] moved the project to
3.14, but because a version pinned in the workflow is a second source of truth that can silently
disagree with `.python-version`. `uv sync` reads `.python-version` and downloads the interpreter
if the runner lacks it, so the local machine, CI, and the Pi now all derive the interpreter from
the same tracked file.

**`enable-cache: true`** caches `~/.cache/uv` between runs. This is safe precisely *because* the
lock is authoritative: the cache can only serve artifacts the lock already names, so it changes
run time, never the resolved result.

## Evidence

CI is the only environment that runs the pipeline against live openfootball data on a schedule
(daily, 01:00 UTC), and it treats a zero exit code as success — so an install-layer regression
here is invisible until the dashboard or the BigQuery tables go stale. That is why the install
step is the one that should fail loudly rather than adapt.

Locally, the equivalent of the CI install path was confirmed green before this commit:

```
$ uv sync --locked && uv run python pipeline.py
load: 23 tournaments, 1069 matches (raw payloads)
transform: dbt build passed (staging -> intermediate -> marts + tests)
Pipeline finished.
```

## Alternatives rejected

**`uv sync --frozen`.** Installs from the lock without checking it against `pyproject.toml` at
all. Faster, but it would hide exactly the drift `--locked` is there to catch.

**`setup-uv` with an explicit `python-version` input.** Would reintroduce the second source of
truth that removing the `setup-python` pin was meant to eliminate.

**Keeping `actions/setup-python` alongside uv.** Redundant — uv provisions the interpreter
itself, and having both invites the two to disagree about which Python the run actually used.

## Verify

Can't be checked locally; the workflow has `workflow_dispatch`, so after merging, trigger
`worldcup-workflow` from the Actions tab and confirm the run is green.

Two failure modes worth recognising in the log:

- *"the lockfile is not up-to-date with the project"* at the install step — someone edited
  `pyproject.toml` without running `uv lock`. Working as intended.
- The run picking a Python other than 3.14 — means `.python-version` isn't being honoured and
  something reintroduced an explicit version pin.

[001]: 001-adopt-uv-toolchain.md
