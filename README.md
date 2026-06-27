# World Cup 2026 Standings Pipeline

A four-layer ELT data pipeline that ingests FIFA World Cup 2026 group-stage results, computes group standings and a top-scorers leaderboard, and exports them to JSON and CSV.

## What it does

Every run, the pipeline:

1. Pulls all World Cup 2026 match data from a public source [openfootball](https://github.com/openfootball/worldcup.json)
2. Stores group-stage matches and goal events in a local SQLite database
3. Computes group standings (points, W/D/L, goal difference) and top scorers
4. Exports the results to JSON and CSV, and prints readable tables to the console

It is idempotent. Each run overwrites the last rather than piling up duplicate or
stale data, so you always end up with one clean, current result.

## Architecture

```
EXTRACT          pull match data from openfootball (public domain, no API key)
   |
LOAD             store group-stage matches + goal events in worldcup.db (SQLite)
   |
TRANSFORM        derive standings (with tiebreakers) and top scorers
   |
SERVE            export to JSON + CSV, print bordered tables to console
   |
ORCHESTRATION    cron triggers a daily run
```

Only the 72 group-stage matches are loaded. The 32 knockout matches in the source (which use placeholder teams like `2A` until groups are decided) are skipped.

## Data source

Match data comes from [openfootball](https://github.com/openfootball/worldcup.json) (`worldcup.json`), a public-domain dataset. It is free to use, requires no API key, and updates roughly once a day.

## Project layout

```
pipeline.py        the full ELT pipeline (single entry point)
setup_cron.sh      prints the cron line + setup steps for this machine
worldcup.db        SQLite database (generated, gitignored)
output/            exported standings/scorers as JSON + CSV (generated, gitignored)
pipeline.log       run log (generated, gitignored)
```

## Running it

```bash
python3 pipeline.py
```

No dependencies, uses only the Python standard library. Produces the console tables and writes four files into `output/`.

## Scheduling

To run automatically once a day at 08:00:

```bash
bash setup_cron.sh        # prints the exact cron line for your machine
crontab -e                # paste the line it printed
crontab -l                # confirm it registered
```

On macOS, grant Full Disk Access to `/usr/sbin/cron` in System Settings > Privacy & Security, or scheduled jobs won't run.

Each run is logged with timestamps to `pipeline.log`.

## Output

**Standings** for each group show position, team, played, won, drawn, lost, goals for and against, goal difference, and points. They are ranked by points, then goal difference, then goals scored.

**Top Scorers** show player, team, and goals.

Both are written as JSON and CSV.

## Known limitations

- Tiebreakers stop at goal difference and goals scored. The later FIFA rules (head-to-head, cards, random draw) need data the source doesn't provide.
- No cards or assists, because no reliable open data source had them for WC2026.
- Not real-time, since the source updates only about once a day.

---

<div align="center"> <sub>Vhyron </div>