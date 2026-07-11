# World Cup Analytics Pipeline

An ELT analytics pipeline over every FIFA World Cup (1930–2026). It ingests full tournament history into DuckDB, models it with dbt into tested staging/intermediate/mart layers, and serves standings, scorers, and historical analytics through a FastAPI backend, a web dashboard, and BigQuery.

## What it does

Every run, the pipeline:

1. Pulls match data for every World Cup (1930–2026) from a public source [openfootball](https://github.com/openfootball/worldcup.json)
2. Stores the verbatim JSON payloads in a local DuckDB database (the raw layer)
3. Runs dbt to build standings, top scorers, and analytics marts for all 23 tournaments, with data tests
4. Publishes the marts to BigQuery (when configured); a FastAPI backend serves them to the dashboard and any other consumer

It is idempotent. Each run overwrites the last rather than piling up duplicate or stale data, so you always end up with one clean, current result.

## Architecture

```
EXTRACT          pull each tournament's JSON from openfootball (public domain, no API key)
   |
LOAD             store verbatim raw payloads in worldcup.duckdb (DuckDB)
   |
TRANSFORM        dbt builds staging -> intermediate -> marts, with data tests
   |
SERVE            publish marts to BigQuery; FastAPI serves them live to the dashboard
   |
ORCHESTRATION    GitHub Actions runs the pipeline daily (local cron optional for dev)
```

The pipeline is multi-target: DuckDB is the local analytical store and the transform engine; BigQuery receives a copy of the finished marts for cloud
consumers. This is one pipeline with two destinations, not a backup scheme — the source of truth is openfootball and everything is reproducible from it. The BigQuery publish only runs when `WC_BQ_PROJECT` and `WC_BQ_DATASET` are set, so local runs stay local.

The transform layer is a dbt project in `dbt/`:

```
staging          stg_matches, stg_goals, stg_tournaments — parse + type the raw JSON
intermediate     int_team_match_results — one row per team per played match
                 int_match_outcomes — one row per match with the decided winner
                 (extra time and penalties included, not just full time)
marts            standings, top_scorers — per tournament, with era-correct points
                 (2 per win before 1994, 3 since)
                 scoring_trends — goals/match, draw rate, ET/penalty counts per tournament
                 knockout_upsets — knockout wins by the team with the worse group record
                 team_records — all-time W/D/L and goals per team
```

Example — query the analytics marts directly:

```sql
-- how scoring has changed across eras
SELECT year, goals_per_match, draw_rate FROM scoring_trends;

-- biggest knockout upsets ever (by group-stage points gap)
SELECT year, round, winner, loser, score, points_gap
FROM knockout_upsets ORDER BY points_gap DESC LIMIT 10;
```

Every model run also runs data tests (unique keys, not-null columns, accepted values, referential integrity between goals and matches). The pipeline fails if a test fails. To run the transforms alone:

```bash
dbt build --project-dir dbt --profiles-dir dbt
```

All 23 tournaments (1930–2026, none in 1942/1946) are loaded — 1,069 matches, both group stage and knockout. Each tournament is replaced wholesale on every run (delete-then-insert), so runs stay idempotent. The raw JSON payloads are also kept in the database, so downstream transforms can always be rebuilt from exactly what the source said.

## Data source

Match data comes from [openfootball](https://github.com/openfootball/worldcup.json) (`worldcup.json`), a public-domain dataset. It is free to use, requires no API key, and updates roughly once a day.

## Project layout

```
pipeline.py        the ELT pipeline (single entry point; calls dbt for transforms)
api.py             FastAPI backend serving marts from DuckDB (also hosts the dashboard)
dbt/               dbt project: staging -> intermediate -> marts models + tests
deploy/            systemd units + walkthrough for self-hosting on a Raspberry Pi
.github/workflows/ daily pipeline run on GitHub Actions (+ optional BigQuery publish)
dashboard.html     the web dashboard (reads the API)
setup_cron.sh      prints the cron line + setup steps for this machine
worldcup.duckdb    DuckDB database (generated, gitignored)
pipeline.log       run log (generated, gitignored)
```

## Running the pipeline

```bash
pip install -r requirements.txt   # inside a venv if your system python is externally managed
python3 pipeline.py
```

Dependencies: DuckDB (local analytical store), dbt-duckdb (transform layer), FastAPI + uvicorn (API), google-cloud-bigquery (optional cloud publish). Paths are anchored to the script's own location, so it behaves the same run by hand, by cron, or in CI.

## Running the API + dashboard

```bash
uvicorn api:app
```

Then open `http://localhost:8000` — the API serves the dashboard at the root. Run the pipeline first so the database has data. Interactive API docs at `http://localhost:8000/docs`.

Endpoints:

```
/api/tournaments                        all 23 tournaments
/api/tournaments/{year}/standings       group-stage standings for one tournament
/api/tournaments/{year}/scorers         scorer leaderboard (404 for gap years)
/api/analytics/scoring-trends           goals/match, draw rate, ET/pens per tournament
/api/analytics/upsets                   knockout upsets ranked by points gap
/api/analytics/team-records             all-time per-team records
```

The dashboard has a light and dark theme toggle and JSON/CSV export buttons (built client-side from the loaded data).

## Scheduling

`.github/workflows/pipeline.yml` runs the pipeline daily at 06:00 UTC (after openfootball's roughly daily update) and on demand from the Actions tab.

To enable the BigQuery publish in CI, configure the repo once:

1. Create a GCP project and a BigQuery dataset (the free sandbox tier works — no billing account needed)
2. Create a service account with the *BigQuery Data Editor* and *BigQuery Job User* roles, and download a JSON key
3. In the repo settings, add the key as the secret `GCP_SA_KEY`, and add `WC_BQ_PROJECT` and `WC_BQ_DATASET` as Actions variables

Without those, CI still runs — it just skips the cloud publish.

## Self-hosted deployment

The API + dashboard run on a Raspberry Pi Zero 2 W behind a Cloudflare Tunnel: a systemd timer runs the pipeline nightly, a systemd service keeps uvicorn up, and the tunnel exposes it over HTTPS with no open router ports. GitHub Actions stays the independent owner of the BigQuery path, so either half can fail without taking down the other. Full walkthrough in [deploy/PI_SETUP.md](deploy/PI_SETUP.md).

For local development, cron can run the same pipeline daily:

```bash
bash setup_cron.sh        # prints the exact cron line for your machine
crontab -e                # paste the line it printed
crontab -l                # confirm it registered
```

On macOS, grant Full Disk Access to `/usr/sbin/cron` in System Settings > Privacy & Security, or scheduled jobs won't run.

Each run is logged with timestamps to `pipeline.log`.

## Known limitations

- Tiebreakers stop at goal difference and goals scored. The later FIFA rules (head-to-head, cards, random draw) need data the source doesn't provide.
- Goal-scorer events are only complete for 1930–1950 and 2014–2026; the source has few or none for 1954–2010. Match results are complete for all tournaments.
- No cards or assists, because no reliable open data source provides them.
- Not real-time, since the source updates only about once a day.

##
<div align="center"> <sub>Vhyron </div>