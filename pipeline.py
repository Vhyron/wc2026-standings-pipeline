import urllib.request
import json
import csv
import os
import duckdb
import subprocess
import sys
import logging

# Log to both the console and a file, each line timestamped.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Every World Cup in the openfootball archive (no tournaments in 1942/1946).
YEARS = [1930, 1934, 1938, 1950, 1954, 1958, 1962, 1966, 1970, 1974, 1978,
         1982, 1986, 1990, 1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022, 2026]
CURRENT_YEAR = 2026  # tournament the dashboard exports track

URL_TEMPLATE = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/{year}/worldcup.json"
DB_FILE = os.path.join(BASE_DIR, "worldcup.duckdb")
DBT_DIR = os.path.join(BASE_DIR, "dbt")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


class PipelineError(Exception):
    pass


# --- EXTRACT ---

def extract(year):
    url = URL_TEMPLATE.format(year=year)
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.loads(response.read())
    except urllib.error.URLError as e:
        raise PipelineError(f"extract failed for {year}: could not reach source ({e.reason})")
    except json.JSONDecodeError:
        raise PipelineError(f"extract failed for {year}: source returned invalid JSON")

    if not data.get("matches"):
        raise PipelineError(f"extract failed for {year}: no matches in source data")
    return data


# --- LOAD ---

def setup_tables(conn):
    # The load layer stores only the verbatim source payloads; everything
    # else is derived from them by the dbt models in dbt/models/.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_payloads (
            year       INTEGER PRIMARY KEY,
            fetched_at TIMESTAMP,
            payload    JSON
        )
    """)


def load_raw(conn, year, data):
    conn.execute("BEGIN")
    conn.execute("DELETE FROM raw_payloads WHERE year = ?", (year,))
    conn.execute(
        "INSERT INTO raw_payloads VALUES (?, now(), ?)",
        (year, json.dumps(data, ensure_ascii=False)),
    )
    conn.execute("COMMIT")
    return len(data["matches"])


# --- TRANSFORM: dbt builds staging -> intermediate -> marts, with tests ---

def transform():
    # dbt runs as a subprocess (same interpreter) rather than in-process:
    # it releases its DuckDB write lock on exit and can't hijack our logging.
    cmd = [
        sys.executable, "-c", "from dbt.cli.main import cli; cli()",
        "build",
        "--project-dir", DBT_DIR,
        "--profiles-dir", DBT_DIR,
        "--log-level", "warn",
    ]
    result = subprocess.run(cmd, env={**os.environ, "WC_DB_PATH": DB_FILE})
    if result.returncode != 0:
        raise PipelineError(f"transform failed: dbt build exited with code {result.returncode}")


# --- SERVE: export marts to JSON + CSV ---

def fetch_standings(conn, year):
    rows = conn.execute("""
        SELECT match_group, position, team, played, won, drawn, lost,
               goals_for, goals_against, goal_difference, points
        FROM standings
        WHERE year = ?
        ORDER BY match_group, position
    """, (year,)).fetchall()
    keys = ["group", "position", "team", "played", "won", "drawn", "lost",
            "goals_for", "goals_against", "goal_difference", "points"]
    return [dict(zip(keys, r)) for r in rows]


def fetch_scorers(conn, year, limit=10):
    rows = conn.execute("""
        SELECT scorer_rank, player, team, goals
        FROM top_scorers
        WHERE year = ? AND scorer_rank <= ?
        ORDER BY scorer_rank
    """, (year, limit)).fetchall()
    keys = ["rank", "player", "team", "goals"]
    return [dict(zip(keys, r)) for r in rows]


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def write_csv(path, records):
    if not records:
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)


def serve(standings_records, scorers_records):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    write_json(f"{OUTPUT_DIR}/standings.json", standings_records)
    write_csv(f"{OUTPUT_DIR}/standings.csv", standings_records)
    write_json(f"{OUTPUT_DIR}/scorers.json", scorers_records)
    write_csv(f"{OUTPUT_DIR}/scorers.csv", scorers_records)
    return len(standings_records), len(scorers_records)


# --- DISPLAY ---

WIDTH = 51


def _line():
    print(f"+{'-' * (WIDTH + 2)}+")


def _row(text):
    print(f"| {text:<{WIDTH}} |")


def show_standings(records):
    header = f"{'Team':<22}{'P':>3}{'W':>3}{'D':>3}{'L':>3}{'GF':>4}{'GA':>4}{'GD':>4}{'Pts':>5}"
    current_group = None
    for r in records:
        if r["group"] != current_group:
            current_group = r["group"]
            print()
            _line()
            _row(current_group)
            _line()
            _row(header)
            _line()
        _row(f"{r['team']:<22}{r['played']:>3}{r['won']:>3}{r['drawn']:>3}{r['lost']:>3}"
             f"{r['goals_for']:>4}{r['goals_against']:>4}{r['goal_difference']:>+4}{r['points']:>5}")
    if records:
        _line()


def show_scorers(records):
    header = f"{'Rk':>3}  {'Player':<22}{'Team':<18}{'G':>3}"
    print()
    _line()
    _row("TOP SCORERS")
    _line()
    _row(header)
    _line()
    for r in records:
        _row(f"{r['rank']:>3}  {r['player']:<22}{r['team']:<18}{r['goals']:>3}")
    _line()


# --- RUN FLOW ---

def run():
    log.info("Starting pipeline...")

    conn = duckdb.connect(DB_FILE)
    try:
        setup_tables(conn)
        total_matches = 0
        for year in YEARS:
            data = extract(year)
            total_matches += load_raw(conn, year, data)
        log.info("load: %d tournaments, %d matches (raw payloads)", len(YEARS), total_matches)
    finally:
        conn.close()  # dbt needs the write lock

    transform()
    log.info("transform: dbt build passed (staging -> intermediate -> marts + tests)")

    conn = duckdb.connect(DB_FILE, read_only=True)
    try:
        standings_records = fetch_standings(conn, CURRENT_YEAR)
        scorers_records = fetch_scorers(conn, CURRENT_YEAR)
    finally:
        conn.close()

    n_standings, n_scorers = serve(standings_records, scorers_records)
    log.info("serve: exported %d standings + %d scorers to %s/", n_standings, n_scorers, OUTPUT_DIR)

    show_standings(standings_records)
    show_scorers(scorers_records)
    log.info("Pipeline finished.")
    print()


if __name__ == "__main__":
    try:
        run()
    except PipelineError as e:
        log.error("%s", e)
        sys.exit(1)
