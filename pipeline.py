import urllib.request
import json
import csv
import os
import sqlite3
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

URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
DB_FILE = "worldcup-2026.db"
OUTPUT_DIR = "output"


class PipelineError(Exception):
    pass
 
 
# --- EXTRACT (once, shared by all loaders) ---

def extract():
    try:
        with urllib.request.urlopen(URL, timeout=15) as response:
            data = json.loads(response.read())
    except urllib.error.URLError as e:
        raise PipelineError(f"extract failed: could not reach source ({e.reason})")
    except json.JSONDecodeError:
        raise PipelineError("extract failed: source returned invalid JSON")

    matches = data.get("matches")
    if not matches:
        raise PipelineError("extract failed: no matches in source data")
    return matches


# --- LOAD ---

def setup_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            match_group TEXT,
            team1       TEXT,
            team2       TEXT,
            score1      INTEGER,
            score2      INTEGER,
            played      INTEGER,
            UNIQUE (match_group, team1, team2)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            match_group TEXT,
            scorer      TEXT,
            team        TEXT,
            minute      TEXT,
            UNIQUE (match_group, scorer, team, minute)
        )
    """)
    conn.commit()


def load_matches(conn, matches):
    loaded = 0
    for m in matches:
        if "group" not in m:
            continue
        if "score" in m:
            score1, score2 = m["score"]["ft"]
            played = 1
        else:
            score1, score2 = None, None
            played = 0

        conn.execute("""
            INSERT OR REPLACE INTO matches
                (match_group, team1, team2, score1, score2, played)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (m["group"], m["team1"], m["team2"], score1, score2, played))
        loaded += 1
    conn.commit()

    if loaded == 0:
        raise PipelineError("load failed: no group-stage matches found")
    return loaded


def load_goals(conn, matches):
    loaded = 0
    for m in matches:
        if "group" not in m:
            continue
        # goals1 belongs to team1, goals2 to team2.
        for side, team in (("goals1", m["team1"]), ("goals2", m["team2"])):
            for g in m.get(side, []):
                conn.execute("""
                    INSERT OR REPLACE INTO goals (match_group, scorer, team, minute)
                    VALUES (?, ?, ?, ?)
                """, (m["group"], g["name"], team, g.get("minute")))
                loaded += 1
    conn.commit()
    return loaded


# --- TRANSFORM: standings ---

def blank_row():
    return {"P": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0, "Pts": 0}


def build_standings(conn):
    groups = {}
    rows = conn.execute("""
        SELECT match_group, team1, team2, score1, score2
        FROM matches WHERE played = 1
    """).fetchall()
 
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
 
def top_scorers(conn, limit=10):
    return conn.execute("""
        SELECT scorer, team, COUNT(*) AS goals
        FROM goals
        GROUP BY scorer, team
        ORDER BY goals DESC, scorer ASC
        LIMIT ?
    """, (limit,)).fetchall()


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
 
    matches = extract()
    log.info("extract: pulled %d matches", len(matches))
 
    conn = sqlite3.connect(DB_FILE)
    try:
        setup_tables(conn)
        n_matches = load_matches(conn, matches)
        n_goals = load_goals(conn, matches)
        log.info("load: %d matches, %d goals", n_matches, n_goals)
 
        standings = build_standings(conn)
        scorers = top_scorers(conn)
        log.info("transform: %d group tables, top scorers ranked", len(standings))
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
