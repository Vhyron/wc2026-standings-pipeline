# Deploying on a Raspberry Pi Zero 2 W

Self-hosted serving path: the Pi runs the pipeline daily (systemd timer), keeps the API + dashboard up (systemd service), and Cloudflare Tunnel exposes it over HTTPS. GitHub Actions independently keeps publishing marts to BigQuery — the two paths share code but fail independently.

This Pi is dedicated solely to this project — no Pi-hole/Unbound running alongside it.

## 1. One-time system prep

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git

# uv manages both the dependencies and the Python interpreter, so there's no
# need for the system python to be a supported version.
curl -LsSf https://astral.sh/uv/install.sh | sh   # lands at ~/.local/bin/uv

# dbt needs more headroom than the default swap on a 512MB board.
# (Plain swapfile — works on any Raspberry Pi OS; Trixie+ has no dphys-swapfile.)
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Checkpoint: free -h shows Swap: 1.0Gi.

## 2. Project

```bash
cd ~
git clone https://github.com/Vhyron/worldcup-analytics-pipeline.git
cd worldcup-analytics-pipeline
uv sync   # downloads Python 3.14 + arm64 wheels into .venv; takes a while on a Zero 2 W

# First pipeline run by hand, so the DB exists and you see it work.
uv run pipeline.py
```
same log lines — load: 23 tournaments, 1069 matches, transform: dbt build passed, Pipeline finished.

Checkpoint: .venv/bin/dbt --version prints versions without errors.

Everything installs from prebuilt aarch64 wheels — duckdb, grpcio and pydantic-core all ship
cp314 manylinux aarch64 builds — so nothing compiles from source on the Pi.

Do NOT set `WC_BQ_PROJECT`/`WC_BQ_DATASET` here — BigQuery publishing belongs to GitHub Actions, so the warehouse keeps refreshing even if the Pi is down.

## 3. Services

```bash
sudo cp deploy/worldcup-api.service deploy/worldcup-pipeline.service deploy/worldcup-pipeline.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now worldcup-api.service
sudo systemctl enable --now worldcup-pipeline.timer
```

Checkpoints:
```bash
systemctl status worldcup-api          # API up?
systemctl list-timers worldcup-*       # next pipeline run scheduled?
```
And http://<pi-ip>:8000 works from your Mac — systemd owns it. Reboot test if you want the full proof: sudo reboot, wait a minute, dashboard's back by itself.

## 4. Cloudflare Tunnel

Prereq: a domain added to a (free) Cloudflare account.

1. Cloudflare dashboard -> Zero Trust -> Networks -> Tunnels -> Create a tunnel (Cloudflared connector). Name it `worldcup`.
2. It shows an install command for Debian arm64 — run it on the Pi. It installs `cloudflared` as a service with the tunnel token baked in.
3. In the tunnel's Public Hostname tab: hostname `worldcup.<yourdomain>`, service `http://localhost:8000`. Save.
4. `https://worldcup.<yourdomain>` now serves the dashboard. HTTPS, no open router ports, home IP never published.

## 5. Notes

- The timer fires at 09:00 in the Pi's local timezone — confirm with `timedatectl` (set it with `sudo timedatectl set-timezone Asia/Manila`).
- `Nice=10` on the pipeline service keeps the daily dbt build from hogging CPU over the API.
- `Persistent=true` on the timer means a Pi that was off at 09:00 runs the pipeline at next boot instead of skipping the day.
- Update the deployment after pushing changes: `cd ~/worldcup-analytics-pipeline && git pull && uv sync && sudo systemctl restart worldcup-api`
- The systemd units call `.venv/bin/...` directly rather than `uv run`, so nothing resolves
  dependencies or touches the network while a service is starting. `uv sync` at deploy time is
  what keeps that venv current — don't skip it after a `git pull`.
