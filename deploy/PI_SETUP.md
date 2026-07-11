# Deploying on a Raspberry Pi Zero 2 W

Self-hosted serving path: the Pi runs the pipeline daily (systemd timer), keeps the API + dashboard up (systemd service), and Cloudflare Tunnel exposes it over HTTPS. GitHub Actions independently keeps publishing marts to BigQuery — the two paths share code but fail independently.

Coexists with Pi-hole + Unbound: the API uses port 8000, Pi-hole owns 53/80, Unbound owns 5335, and `cloudflared` makes outbound connections only.

## 1. One-time system prep

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git python3-venv

# dbt needs more headroom than the default swap on a 512MB board.
sudo dphys-swapfile swapoff
sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo dphys-swapfile setup && sudo dphys-swapfile swapon
```

## 2. Project

```bash
cd ~
git clone https://github.com/Vhyron/worldcup-analytics-pipeline.git
cd worldcup-analytics-pipeline
python3 -m venv venv
venv/bin/pip install -r requirements.txt   # ARM wheels come from piwheels; takes a while

# First pipeline run by hand, so the DB exists and you see it work.
venv/bin/python pipeline.py
```

Do NOT set `WC_BQ_PROJECT`/`WC_BQ_DATASET` here — BigQuery publishing belongs to GitHub Actions, so the warehouse keeps refreshing even if the Pi is down.

## 3. Services

```bash
sudo cp deploy/worldcup-api.service deploy/worldcup-pipeline.service deploy/worldcup-pipeline.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now worldcup-api.service
sudo systemctl enable --now worldcup-pipeline.timer
```

Check: `http://<pi-ip>:8000` from a browser on your LAN shows the dashboard.

```bash
systemctl status worldcup-api          # API up?
systemctl list-timers worldcup-*       # next pipeline run scheduled?
journalctl -u worldcup-pipeline -n 50  # last pipeline run's log
```

## 4. Cloudflare Tunnel

Prereq: a domain added to a (free) Cloudflare account.

1. Cloudflare dashboard -> Zero Trust -> Networks -> Tunnels -> Create a tunnel (Cloudflared connector). Name it `worldcup`.
2. It shows an install command for Debian arm64 — run it on the Pi. It installs `cloudflared` as a service with the tunnel token baked in.
3. In the tunnel's Public Hostname tab: hostname `worldcup.<yourdomain>`, service `http://localhost:8000`. Save.
4. `https://worldcup.<yourdomain>` now serves the dashboard. HTTPS, no open router ports, home IP never published.

## 5. Notes

- The timer fires at 09:00 in the Pi's local timezone — confirm with `timedatectl` (set it with `sudo timedatectl set-timezone Asia/Manila`).
- The daily dbt build may slow Pi-hole DNS replies for a couple of minutes; `Nice=10` keeps it polite.
- `Persistent=true` on the timer means a Pi that was off at 09:00 runs the pipeline at next boot instead of skipping the day.
- Update the deployment after pushing changes: `cd ~/worldcup-analytics-pipeline && git pull && venv/bin/pip install -r requirements.txt && sudo systemctl restart worldcup-api`
