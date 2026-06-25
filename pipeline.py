import urllib.request
import json
import sqlite3
import sys

URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
DB_FILE = "worldcup-2026.db"


# --- EXTRACT ---

def extract():
    try:
        with urllib.request.urlopen(URL, timeout=15) as response:
            data = json.loads(response.read())
    except urllib.error.URLError as e:
        # Network down, DNS fail, timeout: stop cleanly, don't touch the db.
        raise PipelineError(f"extract failed: could not reach source ({e.reason})")
    except json.JSONDecodeError:
        raise PipelineError("extract failed: source returned invalid JSON")

    matches = data.get("matches")
    if not matches:
        raise PipelineError("extract failed: no matches in source data")

    return matches


# --- LOAD ---

def load(conn, matches):
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


# --- TRANSFORM ---

def blank_row():
    return {"P": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0, "Pts": 0}


def transform(conn):
    groups = {}
    rows = conn.execute("""
        SELECT match_group, team1, team2, score1, score2
        FROM matches WHERE played = 1
    """).fetchall()

    for group, team1, team2, s1, s2 in rows:
        table = groups.setdefault(group, {})
        t1 = table.setdefault(team1, blank_row())
        t2 = table.setdefault(team2, blank_row())

        t1["P"] += 1
        t2["P"] += 1
        t1["GF"] += s1; t1["GA"] += s2
        t2["GF"] += s2; t2["GA"] += s1

        if s1 > s2:
            t1["W"] += 1; t1["Pts"] += 3
            t2["L"] += 1
        elif s2 > s1:
            t2["W"] += 1; t2["Pts"] += 3
            t1["L"] += 1
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


def show(standings):
    for group in sorted(standings):
        print(f"\n{group}")
        print(f"  {'Team':<22}{'P':>3}{'W':>3}{'D':>3}{'L':>3}{'GF':>4}{'GA':>4}{'GD':>4}{'Pts':>5}")
        for team, s in rank(standings[group]):
            gd = s["GF"] - s["GA"]
            print(f"  {team:<22}{s['P']:>3}{s['W']:>3}{s['D']:>3}{s['L']:>3}"
                  f"{s['GF']:>4}{s['GA']:>4}{gd:>+4}{s['Pts']:>5}")


# --- ORCHESTRATION OF THE RUN (the run flow itself) ---

class PipelineError(Exception):
    pass


def run():
    print("Starting pipeline...")

    matches = extract()
    print(f"  extract: pulled {len(matches)} matches")

    # One connection for the whole run; closed even if a later step fails.
    conn = sqlite3.connect(DB_FILE)
    try:
        loaded = load(conn, matches)
        print(f"  load: stored {loaded} group-stage matches")

        standings = transform(conn)
        print(f"  transform: built {len(standings)} group tables")
    finally:
        conn.close()

    show(standings)
    print("\nPipeline finished.")


if __name__ == "__main__":
    try:
        run()
    except PipelineError as e:
        # Expected, handled failures: clear message, non-zero exit for cron.
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
