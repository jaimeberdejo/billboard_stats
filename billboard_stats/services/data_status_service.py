"""Database health and data status queries."""

from billboard_stats.db.connection import execute_query


_ALLOWED_TABLES = frozenset({
    "chart_weeks", "hot100_entries", "b200_entries",
    "songs", "albums", "artists",
    "song_stats", "album_stats", "artist_stats",
})


def get_table_counts() -> dict:
    """Row counts for all major tables."""
    counts = {}
    for table in sorted(_ALLOWED_TABLES):
        # Safe: table name comes from a hardcoded allowlist.
        rows = execute_query(f"SELECT COUNT(*) AS cnt FROM {table};")
        counts[table] = rows[0]["cnt"] if rows else 0
    return counts


def get_latest_chart_dates() -> dict:
    """Latest chart_date per chart_type."""
    rows = execute_query(
        "SELECT chart_type, MAX(chart_date) AS latest_date "
        "FROM chart_weeks GROUP BY chart_type;"
    )
    return {r["chart_type"]: r["latest_date"] for r in rows}


def get_data_summary() -> dict:
    """Combined summary: counts, latest dates, totals."""
    counts = get_table_counts()
    latest = get_latest_chart_dates()
    return {
        "counts": counts,
        "latest_dates": latest,
        "chart_weeks": counts.get("chart_weeks", 0),
        "songs": counts.get("songs", 0),
        "albums": counts.get("albums", 0),
        "artists": counts.get("artists", 0),
        "hot100_entries": counts.get("hot100_entries", 0),
        "b200_entries": counts.get("b200_entries", 0),
    }
