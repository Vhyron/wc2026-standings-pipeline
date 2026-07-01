import urllib.request
import json
import csv
import os
import duckdb
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
    # Raw payloads are kept verbatim so downstream transforms (dbt staging)
    # can always be rebuilt from what the source actually said.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_payloads (
            year       INTEGER PRIMARY KEY,
            fetched_at TIMESTAMP,
            payload    JSON
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            year INTEGER PRIMARY KEY,
            name TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            year        INTEGER,
            match_id    INTEGER,
            round       TEXT,
            stage       TEXT,
            match_group TEXT,
            match_date  DATE,
            team1       TEXT,
            team2       TEXT,
            score1_ft   INTEGER,
            score2_ft   INTEGER,
            score1_et   INTEGER,
            score2_et   INTEGER,
            score1_p    INTEGER,
            score2_p    INTEGER,
            played      INTEGER,
            PRIMARY KEY (year, match_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            year     INTEGER,
            match_id INTEGER,
            ordinal  INTEGER,
            team     TEXT,
            scorer   TEXT,
            minute   TEXT,
            penalty  BOOLEAN,
            owngoal  BOOLEAN,
            PRIMARY KEY (year, match_id, ordinal)
        )
    """)


def load_tournament(conn, year, data):
    """Replace one tournament's rows wholesale. Delete-then-insert keeps the
    run idempotent without upsert bookkeeping on composite keys."""
    conn.execute("BEGIN")
    for table in ("raw_payloads", "tournaments", "matches", "goals"):
        conn.execute(f"DELETE FROM {table} WHERE year = ?", (year,))

    conn.execute(
        "INSERT INTO raw_payloads VALUES (?, now(), ?)",
        (year, json.dumps(data, ensure_ascii=False)),
    )
    conn.execute(
        "INSERT INTO tournaments VALUES (?, ?)",
        (year, data.get("name", f"World Cup {year}")),
    )

    n_matches = n_goals = 0
    for pos, m in enumerate(data["matches"], 1):
        match_id = m.get("num", pos)
        score = m.get("score", {})
        ft = score.get("ft", (None, None))
        et = score.get("et", (None, None))
        p = score.get("p", (None, None))
        conn.execute("""
            INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (year, match_id, m.get("round"),
              "group" if "group" in m else "knockout", m.get("group"),
              m.get("date"), m["team1"], m["team2"],
              ft[0], ft[1], et[0], et[1], p[0], p[1],
              1 if "score" in m else 0))
        n_matches += 1

        ordinal = 0
        # goals1 belongs to team1, goals2 to team2.
        for side, team in (("goals1", m["team1"]), ("goals2", m["team2"])):
            for g in m.get(side, []):
                ordinal += 1
                conn.execute(
                    "INSERT INTO goals VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (year, match_id, ordinal, team, g["name"],
                     str(g.get("minute") or ""),
                     bool(g.get("penalty")), bool(g.get("owngoal"))),
                )
                n_goals += 1
    conn.execute("COMMIT")

    if n_matches == 0:
        raise PipelineError(f"load failed for {year}: no matches loaded")
    return n_matches, n_goals


# --- TRANSFORM: standings ---

def blank_row():
    return {"P": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0, "Pts": 0}


def build_standings(conn, year):
    groups = {}
    rows = conn.execute("""
        SELECT match_group, team1, team2, score1_ft, score2_ft
        FROM matches
        WHERE year = ? AND stage = 'group' AND played = 1
    """, (year,)).fetchall()

    for group, team1, team2, s1, s2 in rows:
        table = groups.setdefault(group, {})
        t1 = table.setdefault(team1, blank_row())
        t2 = table.setdefault(team2, blank_row())

        t1["P"] += 1; t2["P"] += 1
        t1["GF"] += s1; t1["GA"] += s2
        t2["GF"] += s2; t2["GA"] += s1

        if s1 > s2:
            t1["W"] += 1; t1["Pts"] += 3; t2["L"] += 1
        elif s2 > s1:
            t2["W"] += 1; t2["Pts"] += 3; t1["L"] += 1
        else:
            t1["D"] += 1; t1["Pts"] += 1
            t2["D"] += 1; t2["Pts"] += 1
    return groups


def rank(table):
    # Points, then goal difference, then goals scored.
    return sorted(
        table.items(),
        key=lambda kv: (kv[1]["Pts"], kv[1]["GF"] - kv[1]["GA"], kv[1]["GF"]),
        reverse=True,
    )


# --- TRANSFORM: top scorers ---

def top_scorers(conn, year, limit=10):
    # Own goals credit no scorer.
    return conn.execute("""
        SELECT scorer, team, COUNT(*) AS goals
        FROM goals
        WHERE year = ? AND NOT owngoal
        GROUP BY scorer, team
        ORDER BY goals DESC, scorer ASC
        LIMIT ?
    """, (year, limit)).fetchall()


# --- SERVE: export to JSON + CSV ---

def standings_to_records(standings):
    records = []
    for group in sorted(standings):
        for pos, (team, s) in enumerate(rank(standings[group]), 1):
            records.append({
                "group": group, "position": pos, "team": team,
                "played": s["P"], "won": s["W"], "drawn": s["D"], "lost": s["L"],
                "goals_for": s["GF"], "goals_against": s["GA"],
                "goal_difference": s["GF"] - s["GA"], "points": s["Pts"],
            })
    return records


def scorers_to_records(scorers):
    return [{"rank": i, "player": name, "team": team, "goals": goals}
            for i, (name, team, goals) in enumerate(scorers, 1)]


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


def serve(standings, scorers):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    standings_records = standings_to_records(standings)
    scorers_records = scorers_to_records(scorers)
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


def show_standings(standings):
    header = f"{'Team':<22}{'P':>3}{'W':>3}{'D':>3}{'L':>3}{'GF':>4}{'GA':>4}{'GD':>4}{'Pts':>5}"
    for group in sorted(standings):
        print()
        _line()
        _row(group)
        _line()
        _row(header)
        _line()
        for team, s in rank(standings[group]):
            gd = s["GF"] - s["GA"]
            _row(f"{team:<22}{s['P']:>3}{s['W']:>3}{s['D']:>3}{s['L']:>3}"
                 f"{s['GF']:>4}{s['GA']:>4}{gd:>+4}{s['Pts']:>5}")
        _line()


def show_scorers(scorers):
    header = f"{'Rk':>3}  {'Player':<22}{'Team':<18}{'G':>3}"
    print()
    _line()
    _row("TOP SCORERS")
    _line()
    _row(header)
    _line()
    for i, (scorer, team, goals) in enumerate(scorers, 1):
        _row(f"{i:>3}  {scorer:<22}{team:<18}{goals:>3}")
    _line()


# --- RUN FLOW ---

def run():
    log.info("Starting pipeline...")

    conn = duckdb.connect(DB_FILE)
    try:
        setup_tables(conn)
        total_matches = total_goals = 0
        for year in YEARS:
            data = extract(year)
            n_matches, n_goals = load_tournament(conn, year, data)
            total_matches += n_matches
            total_goals += n_goals
        log.info("load: %d tournaments, %d matches, %d goals",
                 len(YEARS), total_matches, total_goals)

        standings = build_standings(conn, CURRENT_YEAR)
        scorers = top_scorers(conn, CURRENT_YEAR)
        log.info("transform: %d group tables, top scorers ranked (%d)",
                 len(standings), CURRENT_YEAR)
    finally:
        conn.close()

    n_standings, n_scorers = serve(standings, scorers)
    log.info("serve: exported %d standings + %d scorers to %s/", n_standings, n_scorers, OUTPUT_DIR)

    show_standings(standings)
    show_scorers(scorers)
    log.info("Pipeline finished.")
    print()


if __name__ == "__main__":
    try:
        run()
    except PipelineError as e:
        log.error("%s", e)
        sys.exit(1)
