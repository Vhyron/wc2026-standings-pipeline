import urllib.request
import json
import sqlite3

URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
DB_FILE = "worldcup2026.db"


def fetch_matches():
    with urllib.request.urlopen(URL) as response:
        data = json.loads(response.read())
    return data["matches"]


def setup_database(conn):
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
    conn.commit()


def load_matches(conn, matches):
    loaded = 0
    for m in matches:
        # Only group-stage matches have a "group" key. Skip knockouts.
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
    return loaded


conn = sqlite3.connect(DB_FILE)
setup_database(conn)

matches = fetch_matches()
loaded = load_matches(conn, matches)

total = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
played = conn.execute("SELECT COUNT(*) FROM matches WHERE played = 1").fetchone()[0]
print(f"Stored {total} group-stage matches ({played} played, {total - played} upcoming)")

print("-" * 50)
print("Sample from the database (Group A):")
rows = conn.execute("""
    SELECT team1, team2, score1, score2, played
    FROM matches WHERE match_group = 'Group A'
""").fetchall()

for team1, team2, s1, s2, played in rows:
    result = f"{s1}-{s2}" if played else "upcoming"
    print(f"  {team1} vs {team2}: {result}")

conn.close()
