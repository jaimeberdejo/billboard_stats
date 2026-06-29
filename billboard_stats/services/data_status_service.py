"""Database health and data status queries."""

from billboard_stats.db.connection import execute_query


_ALLOWED_TABLES = frozenset({
    "chart_weeks", "chart_entries",
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
    """Latest non-future Saturday chart_date per chart (keyed by chart slug).

    Reads the chart identity from the ``charts`` registry via ``chart_weeks.chart_id``
    (the dropped chart-type discriminator column is gone). The returned keys are
    chart slugs (``'hot-100'`` / ``'billboard-200'`` / ...), unchanged from before.
    """
    rows = execute_query(
        "SELECT c.slug AS chart_type, MAX(cw.chart_date) AS latest_date "
        "FROM chart_weeks cw "
        "JOIN charts c ON cw.chart_id = c.id "
        "WHERE cw.chart_date <= CURRENT_DATE "
        "AND EXTRACT(DOW FROM cw.chart_date) = 6 "
        "GROUP BY c.slug;"
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
        "chart_entries": counts.get("chart_entries", 0),
    }
