# World Cup 2026 Standings Pipeline

A four-layer ELT data pipeline that ingests FIFA World Cup 2026 group-stage results, computes group standings and a top-scorers leaderboard, and serves them as JSON, CSV, and a web dashboard.

## What it does

Every run, the pipeline:

1. Pulls match data for every World Cup (1930–2026) from a public source [openfootball](https://github.com/openfootball/worldcup.json)
2. Stores raw payloads, matches (group stage and knockout), and goal events in a local DuckDB database
3. Computes 2026 group standings (points, W/D/L, goal difference) and top scorers
4. Exports the results to JSON and CSV, and prints readable tables to the console

It is idempotent. Each run overwrites the last rather than piling up duplicate or
stale data, so you always end up with one clean, current result.

## Architecture

```
EXTRACT          pull each tournament's JSON from openfootball (public domain, no API key)
   |
LOAD             store raw payloads + matches + goal events in worldcup.duckdb (DuckDB)
   |
TRANSFORM        derive 2026 standings (with tiebreakers) and top scorers
   |
SERVE            export to JSON + CSV, print console bordered tables, feed the dashboard
   |
ORCHESTRATION    cron triggers a daily run
```

All 23 tournaments (1930–2026, none in 1942/1946) are loaded — about 1,100 matches, both group stage and knockout. Each tournament is replaced wholesale on every run (delete-then-insert), so runs stay idempotent. The raw JSON payloads are also kept in the database, so downstream transforms can always be rebuilt from exactly what the source said.

## Data source

Match data comes from [openfootball](https://github.com/openfootball/worldcup.json) (`worldcup.json`), a public-domain dataset. It is free to use, requires no API key, and updates roughly once a day.

## Project layout

```
pipeline.py        the full ELT pipeline (single entry point)
dashboard.html     the web dashboard (reads the exported JSON)
setup_cron.sh      prints the cron line + setup steps for this machine
worldcup.duckdb    DuckDB database (generated, gitignored)
output/            exported standings/scorers as JSON + CSV (generated, gitignored)
pipeline.log       run log (generated, gitignored)
```

## Running the pipeline

```bash
pip install -r requirements.txt   # inside a venv if your system python is externally managed
python3 pipeline.py
```

The only dependency is DuckDB, the local analytical store; everything else is the Python standard library. Produces the console tables and writes four files into `output/`. Paths are anchored to the script's own location, so it writes to the same place whether run by hand or by cron.

## Running the dashboard
 
`dashboard.html` is a single file with no build step or dependencies. It fetches the JSON from `output/`, so it must be served over HTTP (opening via `file://` will not work).
 
```bash
python3 -m http.server 8000
```
 
Then open `http://localhost:8000/dashboard.html`. Any static server works, including the VS Code Live Server extension. Run the pipeline first so `output/` has data. The dashboard has a light and dark theme toggle and JSON/CSV export buttons.

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
- Goal-scorer events are only complete for 1930–1950 and 2014–2026; the source has few or none for 1954–2010. Match results are complete for all tournaments.
- No cards or assists, because no reliable open data source had them for WC2026.
- Not real-time, since the source updates only about once a day.

##
<div align="center"> <sub>Vhyron </div>