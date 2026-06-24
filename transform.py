import sqlite3

DB_FILE = "worldcup.db"


def blank_row():
    return {"P": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0, "Pts": 0}


def build_standings(conn):
    # group -> team -> stats
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
    # Points first, then goal difference, then goals scored.
    return sorted(
        table.items(),
        key=lambda kv: (kv[1]["Pts"], kv[1]["GF"] - kv[1]["GA"], kv[1]["GF"]),
        reverse=True,
    )


conn = sqlite3.connect(DB_FILE)
standings = build_standings(conn)
conn.close()

for group in sorted(standings):
    print(f"\n{group}")
    print(f"  {'Team':<16}{'P':>3}{'W':>3}{'D':>3}{'L':>3}{'GF':>4}{'GA':>4}{'GD':>4}{'Pts':>5}")
    for team, s in rank(standings[group]):
        gd = s["GF"] - s["GA"]
        print(f"  {team:<16}{s['P']:>3}{s['W']:>3}{s['D']:>3}{s['L']:>3}"
              f"{s['GF']:>4}{s['GA']:>4}{gd:>+4}{s['Pts']:>5}")
