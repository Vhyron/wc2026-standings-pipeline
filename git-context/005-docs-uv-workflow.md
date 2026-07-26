# 005 — docs: document the uv workflow

**Commit:** `docs: document the uv workflow`
**Area:** documentation
**Files:** `README.md`, `deploy/PI_SETUP.md`

## What changed

The same migration described for two audiences — someone cloning the repo, and someone standing
up the Pi.

`README.md`:

- "Running the pipeline" → `uv sync` then `uv run pipeline.py`, replacing
  `pip install -r requirements.txt` + `python3 pipeline.py`.
- "Running the API + dashboard" → `uv run uvicorn api:app`.
- The dependency paragraph now says where dependencies are declared (`pyproject.toml`) and
  pinned (`uv.lock`), and why the lock matters.
- Project layout gains `pyproject.toml`, `uv.lock`, `.python-version` and `git-context/`.

`deploy/PI_SETUP.md`:

- §1 drops `python3-venv` from the apt line and adds the uv installer.
- §2 replaces `python3 -m venv venv` + `venv/bin/pip install -r requirements.txt` with
  `uv sync`; the first manual run becomes `uv run pipeline.py`; the checkpoint becomes
  `.venv/bin/dbt --version`.
- §5 update line becomes `git pull && uv sync && sudo systemctl restart worldcup-api`, with a
  note on why the units call `.venv/bin/...` directly.

## Why

**The old README instruction had a caveat that no longer applies.** It read
"inside a venv if your system python is externally managed" — a hedge that never said *which*
venv or *where*, which is precisely the ambiguity that produced the `venv/` vs `.venv/` split in
`issues/006`. `uv sync` has one answer and needs no caveat.

**Dropping `python3-venv` from the Pi's apt line is the substantive change in §1**, not
housekeeping. It encodes the real shift: the Pi no longer depends on Raspberry Pi OS shipping a
Python new enough for dbt. uv provisions CPython 3.14 itself, so the deployment stops being
coupled to the distro's release cycle — which matters on a board that gets reimaged rarely and
upgraded reluctantly.

**The piwheels note had to change rather than just survive.** It said "ARM wheels come from
piwheels; takes a while", which described pip's index on Raspberry Pi OS. uv doesn't use
piwheels — it pulls manylinux aarch64 wheels straight from PyPI. The warning that it takes a
while on a Zero 2 W is still honest and worth keeping; the explanation behind it isn't, so it's
replaced with the specific reassurance that nothing compiles from source.

**§5 gains a line about `uv sync` being mandatory after `git pull`.** Under pip the equivalent
step was visible in the update command itself. Now that the units invoke `.venv/bin/...`
directly ([004]), skipping the sync leaves the services running happily on stale dependencies
with no error — so the reason is written down where the update command is.

## Evidence

Both documents were previously the only places that told anyone how to install this project, and
both described a workflow that no longer exists after [001]–[004]. The verification grep for the
whole migration is:

```
$ grep -rn "requirements.txt\|pip install\|/venv/" README.md deploy/ .github/ *.sh
(no hits)
```

`issues/` and `git-context/` are excluded from that grep on purpose: both discuss the old setup
as history, which is their job.

## Alternatives rejected

**Splitting README and PI_SETUP into separate commits.** They describe one change for two
audiences; separating them would leave a commit where the project's two install guides
contradict each other.

**Documenting a pip fallback** ("if you don't have uv, `uv export` a requirements.txt"). Rejected
for the same reason [001] deleted `requirements.txt`: a documented second path is a second path
that has to keep working, and nobody would notice when it stopped.

## Verify

```bash
grep -rn "requirements.txt\|pip install\|/venv/" README.md deploy/ .github/ *.sh   # no hits
```

Then follow the README from a clean clone — `uv sync && uv run pipeline.py && uv run uvicorn
api:app` should get you to a working dashboard on `localhost:8000` with no step that isn't
written down. The Pi half is verified by walking §2 on the box itself, ending at
`systemctl status worldcup-api` and the live dashboard.

[001]: 001-adopt-uv-toolchain.md
[004]: 004-systemd-uv-venv.md
