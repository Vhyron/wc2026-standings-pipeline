import os
import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "worldcup.duckdb")
DASHBOARD = os.path.join(BASE_DIR, "dashboard.html")

app = FastAPI(
    title="World Cup Analytics API",
    description="Standings, scorers, and historical analytics for every FIFA World Cup (1930-2026).",
    version="1.0.0",
)


def query(sql, params=()):
    # A fresh read-only connection per request: cheap for a local file, and
    # never holds a lock that would block the pipeline's daily write.
    try:
        conn = duckdb.connect(DB_FILE, read_only=True)
    except duckdb.Error:
        raise HTTPException(503, "database not available — run the pipeline first")
    try:
        cursor = conn.execute(sql, params)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(DASHBOARD)


@app.get("/api/tournaments")
def tournaments():
    return query("SELECT year, name FROM stg_tournaments ORDER BY year")


@app.get("/api/tournaments/{year}/standings")
def standings(year: int):
    rows = query("""
        SELECT match_group AS "group", position, team, played, won, drawn, lost,
               goals_for, goals_against, goal_difference, points
        FROM standings
        WHERE year = ?
        ORDER BY match_group, position
    """, (year,))
    if not rows:
        raise HTTPException(404, f"no group-stage standings for {year}")
    return rows


@app.get("/api/tournaments/{year}/scorers")
def scorers(year: int, limit: int = 10):
    rows = query("""
        SELECT scorer_rank AS "rank", player, team, goals
        FROM top_scorers
        WHERE year = ? AND scorer_rank <= ?
        ORDER BY scorer_rank
    """, (year, limit))
    if not rows:
        raise HTTPException(404, f"no scorer data for {year}")
    return rows


@app.get("/api/analytics/scoring-trends")
def scoring_trends():
    return query("SELECT * FROM scoring_trends ORDER BY year")


@app.get("/api/analytics/upsets")
def upsets(limit: int = 25):
    return query("""
        SELECT year, round, match_date, winner, loser, score, decided_by,
               winner_group_points, loser_group_points, points_gap
        FROM knockout_upsets
        ORDER BY points_gap DESC, year
        LIMIT ?
    """, (limit,))


@app.get("/api/analytics/team-records")
def team_records(limit: int = 50):
    return query("""
        SELECT team, tournaments, first_year, last_year, played, won, drawn, lost,
               goals_for, goals_against, win_rate
        FROM team_records
        ORDER BY won DESC, played DESC
        LIMIT ?
    """, (limit,))
