# 004 — deploy: point systemd units at the uv-managed .venv

**Commit:** `deploy: point systemd units at the uv-managed .venv`
**Area:** deployment (Raspberry Pi)
**Files:** `deploy/worldcup-api.service`, `deploy/worldcup-pipeline.service`

## What changed

Both `ExecStart=` lines move from the hand-built `venv/` to the uv-created `.venv/`:

```ini
# worldcup-api.service
-ExecStart=/home/pi/worldcup-analytics-pipeline/venv/bin/uvicorn api:app --host 0.0.0.0 --port 8000
+ExecStart=/home/pi/worldcup-analytics-pipeline/.venv/bin/uvicorn api:app --host 0.0.0.0 --port 8000

# worldcup-pipeline.service
-ExecStart=/home/pi/worldcup-analytics-pipeline/venv/bin/python pipeline.py
+ExecStart=/home/pi/worldcup-analytics-pipeline/.venv/bin/python pipeline.py
```

One character each. `User=`, `WorkingDirectory=`, `Restart=`, `Nice=10` and the timer are all
unchanged.

## Why

`venv/` no longer exists anywhere — `uv sync` creates `.venv/`, and that is now the only venv
path in the project ([003] removed the other references). Without this change both units would
fail on the next deploy with a bare `status=203/EXEC`, which is a genuinely unhelpful error to
debug at 09:00 on a headless box.

**Why not `uv run` in `ExecStart=`, given that's what [003] just did to the shell scripts?**
Because these two contexts want opposite things.

`uv run` re-checks the lock before every invocation, and will reach out to the network if
anything needs fetching. That's exactly right for a developer running `./run.sh`, where picking
up a dependency change automatically is the point. It is wrong for `worldcup-api.service`, which
has `Restart=always` and must come back up unattended after a reboot or a crash — putting a
resolution step (and potentially a network round-trip, on a Pi Zero 2 W whose network may not be
up yet) inside the restart path turns a dependency hiccup into an outage of the live dashboard.

Splitting it — `uv sync` at deploy time, plain venv binaries at run time — means the runtime path
touches nothing but the filesystem. The venv is a normal PEP 405 virtualenv, so its `bin/`
entry points work standalone with no uv involvement at all.

## Evidence

`Restart=always` plus `RestartSec=5` on the API service means systemd will retry indefinitely; a
failure mode that depends on the network resolves into a restart loop rather than a clean stop,
which is the worst shape for something fronted by a Cloudflare Tunnel. The pipeline unit is
`Type=oneshot` on a `Persistent=true` timer, so a Pi that was off at 09:00 runs it at next boot —
also a moment when the network is least reliable.

These are edits to a template checked into the repo; they take effect on the Pi only after the
units are recopied and reloaded, which is why [005] updates the deploy instructions in the same
breath.

## Alternatives rejected

**`ExecStart=/home/pi/.local/bin/uv run ...`** — the symmetric-with-`run.sh` option, rejected per
the reasoning above.

**`ExecStartPre=` running `uv sync`.** Keeps the venv fresh on every start while leaving the main
command on venv binaries. Still drags resolution and the network into the boot path, just one
line higher up, and additionally makes a failed sync block a service that would otherwise have
started fine on its existing venv.

**Keeping the name `venv/` by having uv target it** (`UV_PROJECT_ENVIRONMENT=venv`). Preserves
these two files untouched, at the cost of fighting uv's default everywhere else forever.

## Verify

On the Pi, after `git pull && uv sync`:

```bash
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart worldcup-api
systemctl status worldcup-api            # active (running), not 203/EXEC
systemctl list-timers worldcup-*         # next run scheduled
curl -sI http://localhost:8000/ | head -1   # 200
```

Then the real proof, since the point of this unit is unattended recovery: `sudo reboot`, wait a
minute, and confirm the dashboard is back without anyone touching it.

In the repo, `grep -rn "venv" deploy/` should show only `.venv` spellings.

[003]: 003-local-scripts-through-uv.md
[005]: 005-docs-uv-workflow.md
