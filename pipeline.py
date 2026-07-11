import urllib.request
import json
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

URL_TEMPLATE = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/{year}/worldcup.json"
DB_FILE = os.path.join(BASE_DIR, "worldcup.duckdb")
DBT_DIR = os.path.join(BASE_DIR, "dbt")


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


# --- SERVE: publish marts to BigQuery (optional cloud target) ---

# Multi-target serving: DuckDB stays the local store and transform engine;
# BigQuery receives a copy of the finished marts for cloud consumers.
BQ_TABLES = ["standings", "top_scorers", "scoring_trends", "knockout_upsets", "team_records"]


def publish_bigquery(conn):
    project = os.environ.get("WC_BQ_PROJECT")
    dataset = os.environ.get("WC_BQ_DATASET")
    if not project or not dataset:
        return None  # cloud target not configured; local-only run

    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE", autodetect=True)

    total_rows = 0
    for table in BQ_TABLES:
        cursor = conn.execute(f"SELECT * FROM {table}")
        columns = [d[0] for d in cursor.description]
        rows = [
            {col: (val.isoformat() if hasattr(val, "isoformat") else val)
             for col, val in zip(columns, row)}
            for row in cursor.fetchall()
        ]
        try:
            client.load_table_from_json(rows, f"{project}.{dataset}.{table}", job_config=job_config).result()
        except Exception as e:
            raise PipelineError(f"publish failed for {dataset}.{table}: {e}")
        total_rows += len(rows)
    return total_rows


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
        published = publish_bigquery(conn)
    finally:
        conn.close()

    if published is None:
        log.info("serve: marts ready in DuckDB (BigQuery target not configured, skipped)")
    else:
        log.info("serve: marts ready in DuckDB, %d rows published across %d marts to BigQuery",
                 published, len(BQ_TABLES))
    log.info("Pipeline finished.")


if __name__ == "__main__":
    try:
        run()
    except PipelineError as e:
        log.error("%s", e)
        sys.exit(1)
