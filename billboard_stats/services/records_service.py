"""Global records, rankings, and leaderboard queries."""

from typing import List, Optional

from billboard_stats.db.connection import execute_query
from billboard_stats.etl.stats_builder import _VALID_HOT100_WEEKS_CTE, _VALID_B200_WEEKS_CTE
from billboard_stats.models.schemas import RecordEntry


def most_weeks_at_number_one(chart: str = "hot-100", limit: int = 25) -> List[RecordEntry]:
    """Songs or albums with the most weeks at #1."""
    if chart == "hot-100":
        rows = execute_query(
            """
            SELECT s.title, s.artist_credit, ss.weeks_at_number_one AS value, s.id AS song_id
            FROM song_stats ss
            JOIN songs s ON ss.song_id = s.id
            WHERE ss.weeks_at_number_one > 0
            ORDER BY ss.weeks_at_number_one DESC, s.title
            LIMIT %s;
            """,
            (limit,),
        )
        return [
            RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                        value=r["value"], song_id=r["song_id"])
            for i, r in enumerate(rows)
        ]
    else:
        rows = execute_query(
            """
            SELECT a.title, a.artist_credit, als.weeks_at_number_one AS value, a.id AS album_id
            FROM album_stats als
            JOIN albums a ON als.album_id = a.id
            WHERE als.weeks_at_number_one > 0
            ORDER BY als.weeks_at_number_one DESC, a.title
            LIMIT %s;
            """,
            (limit,),
        )
        return [
            RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                        value=r["value"], album_id=r["album_id"])
            for i, r in enumerate(rows)
        ]


def longest_chart_runs(chart: str = "hot-100", limit: int = 25) -> List[RecordEntry]:
    """Songs or albums with the most total weeks on chart."""
    if chart == "hot-100":
        rows = execute_query(
            """
            SELECT s.title, s.artist_credit, ss.total_weeks AS value, s.id AS song_id
            FROM song_stats ss
            JOIN songs s ON ss.song_id = s.id
            ORDER BY ss.total_weeks DESC, s.title
            LIMIT %s;
            """,
            (limit,),
        )
        return [
            RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                        value=r["value"], song_id=r["song_id"])
            for i, r in enumerate(rows)
        ]
    else:
        rows = execute_query(
            """
            SELECT a.title, a.artist_credit, als.total_weeks AS value, a.id AS album_id
            FROM album_stats als
            JOIN albums a ON als.album_id = a.id
            ORDER BY als.total_weeks DESC, a.title
            LIMIT %s;
            """,
            (limit,),
        )
        return [
            RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                        value=r["value"], album_id=r["album_id"])
            for i, r in enumerate(rows)
        ]


def most_entries_by_artist(chart: str = "hot-100", limit: int = 25) -> List[RecordEntry]:
    """Artists with the most distinct entries on a chart."""
    if chart == "hot-100":
        rows = execute_query(
            """
            SELECT a.name AS title, a.name AS artist_credit,
                   ast.total_hot100_songs AS value, a.id AS artist_id
            FROM artist_stats ast
            JOIN artists a ON ast.artist_id = a.id
            WHERE ast.total_hot100_songs > 0
            ORDER BY ast.total_hot100_songs DESC, a.name
            LIMIT %s;
            """,
            (limit,),
        )
    else:
        rows = execute_query(
            """
            SELECT a.name AS title, a.name AS artist_credit,
                   ast.total_b200_albums AS value, a.id AS artist_id
            FROM artist_stats ast
            JOIN artists a ON ast.artist_id = a.id
            WHERE ast.total_b200_albums > 0
            ORDER BY ast.total_b200_albums DESC, a.name
            LIMIT %s;
            """,
            (limit,),
        )
    return [
        RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                    value=r["value"], artist_id=r["artist_id"])
        for i, r in enumerate(rows)
    ]


def most_simultaneous_entries(chart: str = "hot-100", limit: int = 25) -> List[RecordEntry]:
    """Artists with the most songs on the chart in the same week.

    Returns one row per artist per week where they hit their personal max,
    so an artist can appear multiple times if they tied their own record.
    """
    if chart != "hot-100":
        return []  # Only tracked for Hot 100

    rows = execute_query(
        f"""
        WITH {_VALID_HOT100_WEEKS_CTE},
        artist_week_counts AS (
            SELECT sa.artist_id, e.chart_week_id, COUNT(*) AS cnt
            FROM hot100_entries e
            JOIN song_artists sa ON e.song_id = sa.song_id
            WHERE e.chart_week_id IN (SELECT id FROM valid_hot100_weeks)
            GROUP BY sa.artist_id, e.chart_week_id
        ),
        artist_max AS (
            SELECT artist_id, MAX(cnt) AS max_cnt
            FROM artist_week_counts
            GROUP BY artist_id
        )
        SELECT a.name AS title, a.name AS artist_credit,
               awc.cnt AS value, a.id AS artist_id, cw.chart_date
        FROM artist_week_counts awc
        JOIN artist_max am ON awc.artist_id = am.artist_id AND awc.cnt = am.max_cnt
        JOIN artists a ON awc.artist_id = a.id
        JOIN chart_weeks cw ON awc.chart_week_id = cw.id
        ORDER BY awc.cnt DESC, a.name, cw.chart_date
        LIMIT %s;
        """,
        (limit,),
    )
    return [
        RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                    value=r["value"], artist_id=r["artist_id"],
                    chart_date=r["chart_date"])
        for i, r in enumerate(rows)
    ]


def biggest_debuts(chart: str = "hot-100", limit: int = 25) -> List[RecordEntry]:
    """Highest debut positions (lowest number = best)."""
    if chart == "hot-100":
        rows = execute_query(
            """
            SELECT s.title, s.artist_credit, ss.debut_position AS value, s.id AS song_id
            FROM song_stats ss
            JOIN songs s ON ss.song_id = s.id
            WHERE ss.debut_position IS NOT NULL
            ORDER BY ss.debut_position ASC, ss.total_weeks DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return [
            RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                        value=r["value"], song_id=r["song_id"])
            for i, r in enumerate(rows)
        ]
    else:
        rows = execute_query(
            """
            SELECT a.title, a.artist_credit, als.debut_position AS value, a.id AS album_id
            FROM album_stats als
            JOIN albums a ON als.album_id = a.id
            WHERE als.debut_position IS NOT NULL
            ORDER BY als.debut_position ASC, als.total_weeks DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return [
            RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                        value=r["value"], album_id=r["album_id"])
            for i, r in enumerate(rows)
        ]


def fastest_to_number_one(chart: str = "hot-100", limit: int = 25) -> List[RecordEntry]:
    """Songs/albums that reached #1 in the fewest weeks from debut."""
    if chart == "hot-100":
        rows = execute_query(
            """
            SELECT s.title, s.artist_credit, calc.weeks_to_one AS value, s.id AS song_id
            FROM (
                SELECT e.song_id,
                       MIN(cw.chart_date) FILTER (WHERE e.rank = 1) AS first_no1_date,
                       MIN(cw.chart_date) AS debut_date
                FROM hot100_entries e
                JOIN chart_weeks cw ON e.chart_week_id = cw.id
                GROUP BY e.song_id
                HAVING MIN(e.rank) = 1
            ) sub
            JOIN songs s ON sub.song_id = s.id
            CROSS JOIN LATERAL (
                SELECT ((sub.first_no1_date - sub.debut_date) / 7 + 1) AS weeks_to_one
            ) calc
            WHERE calc.weeks_to_one IS NOT NULL
            ORDER BY calc.weeks_to_one ASC, s.title
            LIMIT %s;
            """,
            (limit,),
        )
        return [
            RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                        value=r["value"], song_id=r["song_id"])
            for i, r in enumerate(rows)
        ]
    else:
        rows = execute_query(
            """
            SELECT a.title, a.artist_credit, calc.weeks_to_one AS value, a.id AS album_id
            FROM (
                SELECT e.album_id,
                       MIN(cw.chart_date) FILTER (WHERE e.rank = 1) AS first_no1_date,
                       MIN(cw.chart_date) AS debut_date
                FROM b200_entries e
                JOIN chart_weeks cw ON e.chart_week_id = cw.id
                GROUP BY e.album_id
                HAVING MIN(e.rank) = 1
            ) sub
            JOIN albums a ON sub.album_id = a.id
            CROSS JOIN LATERAL (
                SELECT ((sub.first_no1_date - sub.debut_date) / 7 + 1) AS weeks_to_one
            ) calc
            WHERE calc.weeks_to_one IS NOT NULL
            ORDER BY calc.weeks_to_one ASC, a.title
            LIMIT %s;
            """,
            (limit,),
        )
        return [
            RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                        value=r["value"], album_id=r["album_id"])
            for i, r in enumerate(rows)
        ]


def most_number_one_songs_by_artist(chart: str = "hot-100", limit: int = 25) -> List[RecordEntry]:
    """Artists with the most distinct #1 songs (Hot 100 only)."""
    if chart != "hot-100":
        return []
    rows = execute_query(
        """
        SELECT a.name AS title, a.name AS artist_credit,
               COUNT(DISTINCT ss.song_id) AS value, a.id AS artist_id
        FROM song_stats ss
        JOIN song_artists sa ON ss.song_id = sa.song_id
        JOIN artists a ON sa.artist_id = a.id
        WHERE ss.weeks_at_number_one > 0
        GROUP BY a.id, a.name
        ORDER BY value DESC, a.name
        LIMIT %s;
        """,
        (limit,),
    )
    return [
        RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                    value=r["value"], artist_id=r["artist_id"])
        for i, r in enumerate(rows)
    ]


def most_number_one_albums_by_artist(chart: str = "hot-100", limit: int = 25) -> List[RecordEntry]:
    """Artists with the most distinct #1 albums (Billboard 200 only)."""
    if chart != "billboard-200":
        return []
    rows = execute_query(
        """
        SELECT a.name AS title, a.name AS artist_credit,
               COUNT(DISTINCT als.album_id) AS value, a.id AS artist_id
        FROM album_stats als
        JOIN album_artists aa ON als.album_id = aa.album_id
        JOIN artists a ON aa.artist_id = a.id
        WHERE als.weeks_at_number_one > 0
        GROUP BY a.id, a.name
        ORDER BY value DESC, a.name
        LIMIT %s;
        """,
        (limit,),
    )
    return [
        RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                    value=r["value"], artist_id=r["artist_id"])
        for i, r in enumerate(rows)
    ]


# ---------------------------------------------------------------------------
# Drill-down functions (return items for a specific artist)
# ---------------------------------------------------------------------------

def drilldown_number_one_songs(artist_id: int, chart: str = "hot-100") -> List[RecordEntry]:
    """Songs by this artist that reached #1, with weeks at #1."""
    if chart != "hot-100":
        return []
    rows = execute_query(
        """
        SELECT s.title, s.artist_credit, ss.weeks_at_number_one AS value, s.id AS song_id
        FROM song_stats ss
        JOIN songs s ON ss.song_id = s.id
        JOIN song_artists sa ON s.id = sa.song_id
        WHERE sa.artist_id = %s AND ss.weeks_at_number_one > 0
        ORDER BY ss.weeks_at_number_one DESC, s.title;
        """,
        (artist_id,),
    )
    return [
        RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                    value=r["value"], song_id=r["song_id"])
        for i, r in enumerate(rows)
    ]


def drilldown_number_one_albums(artist_id: int, chart: str = "hot-100") -> List[RecordEntry]:
    """Albums by this artist that reached #1, with weeks at #1."""
    if chart != "billboard-200":
        return []
    rows = execute_query(
        """
        SELECT a.title, a.artist_credit, als.weeks_at_number_one AS value, a.id AS album_id
        FROM album_stats als
        JOIN albums a ON als.album_id = a.id
        JOIN album_artists aa ON a.id = aa.album_id
        WHERE aa.artist_id = %s AND als.weeks_at_number_one > 0
        ORDER BY als.weeks_at_number_one DESC, a.title;
        """,
        (artist_id,),
    )
    return [
        RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                    value=r["value"], album_id=r["album_id"])
        for i, r in enumerate(rows)
    ]


def drilldown_artist_entries(artist_id: int, chart: str = "hot-100") -> List[RecordEntry]:
    """All songs (hot-100) or albums (b200) by this artist, with total weeks."""
    if chart == "hot-100":
        rows = execute_query(
            """
            SELECT s.title, s.artist_credit, ss.total_weeks AS value, s.id AS song_id
            FROM song_stats ss
            JOIN songs s ON ss.song_id = s.id
            JOIN song_artists sa ON s.id = sa.song_id
            WHERE sa.artist_id = %s
            ORDER BY ss.total_weeks DESC, s.title;
            """,
            (artist_id,),
        )
        return [
            RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                        value=r["value"], song_id=r["song_id"])
            for i, r in enumerate(rows)
        ]
    else:
        rows = execute_query(
            """
            SELECT a.title, a.artist_credit, als.total_weeks AS value, a.id AS album_id
            FROM album_stats als
            JOIN albums a ON als.album_id = a.id
            JOIN album_artists aa ON a.id = aa.album_id
            WHERE aa.artist_id = %s
            ORDER BY als.total_weeks DESC, a.title;
            """,
            (artist_id,),
        )
        return [
            RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                        value=r["value"], album_id=r["album_id"])
            for i, r in enumerate(rows)
        ]


def drilldown_simultaneous_entries(artist_id: int, chart: str = "hot-100",
                                   chart_date=None) -> List[RecordEntry]:
    """Songs on chart for this artist on a specific week, with position as value."""
    if chart != "hot-100" or chart_date is None:
        return []
    rows = execute_query(
        """
        SELECT s.title, s.artist_credit, e.rank AS value, s.id AS song_id
        FROM hot100_entries e
        JOIN songs s ON e.song_id = s.id
        JOIN song_artists sa ON s.id = sa.song_id
        JOIN chart_weeks cw ON e.chart_week_id = cw.id
        WHERE sa.artist_id = %s AND cw.chart_date = %s AND cw.chart_type = 'hot-100'
        ORDER BY e.rank ASC;
        """,
        (artist_id, chart_date),
    )
    return [
        RecordEntry(rank=i + 1, title=r["title"], artist_credit=r["artist_credit"],
                    value=r["value"], song_id=r["song_id"])
        for i, r in enumerate(rows)
    ]


def custom_query(
    rank_by: str,
    rank_by_param: int,
    chart: str,
    limit: int,
    peak_min: Optional[int] = None,
    peak_max: Optional[int] = None,
    weeks_min: Optional[int] = None,
    debut_pos_min: Optional[int] = None,
    debut_pos_max: Optional[int] = None,
    artist_names: Optional[List[str]] = None,
) -> List[RecordEntry]:
    """Flexible record query builder.

    rank_by: "weeks_at_position" | "weeks_in_top_n" | "total_weeks" | "weeks_at_number_one"
    rank_by_param: position number (used by weeks_at_position and weeks_in_top_n)
    artist_names: optional list of substrings to match on artist_credit (OR logic)
    """
    is_hot100 = chart == "hot-100"
    entry_table = "hot100_entries" if is_hot100 else "b200_entries"
    item_table = "songs" if is_hot100 else "albums"
    stats_table = "song_stats" if is_hot100 else "album_stats"
    id_col = "song_id" if is_hot100 else "album_id"

    params: list = []

    # Build filter clauses (applied against stats table aliased as 'st'
    # and item table aliased as 'i')
    filter_clauses = []
    if artist_names:
        artist_clause = " OR ".join(["i.artist_credit ILIKE %s"] * len(artist_names))
        filter_clauses.append(f"({artist_clause})")
        params.extend(f"%{name}%" for name in artist_names)
    if peak_min is not None:
        filter_clauses.append("st.peak_position >= %s")
        params.append(peak_min)
    if peak_max is not None:
        filter_clauses.append("st.peak_position <= %s")
        params.append(peak_max)
    if weeks_min is not None:
        filter_clauses.append("st.total_weeks >= %s")
        params.append(weeks_min)
    if debut_pos_min is not None:
        filter_clauses.append("st.debut_position >= %s")
        params.append(debut_pos_min)
    if debut_pos_max is not None:
        filter_clauses.append("st.debut_position <= %s")
        params.append(debut_pos_max)

    filter_sql = (" AND " + " AND ".join(filter_clauses)) if filter_clauses else ""

    if rank_by in ("total_weeks", "weeks_at_number_one"):
        # Query directly from stats table
        value_col = "total_weeks" if rank_by == "total_weeks" else "weeks_at_number_one"
        having_clause = ""
        if rank_by == "weeks_at_number_one":
            having_clause = f"AND st.{value_col} > 0"
        sql = f"""
            SELECT i.title, i.artist_credit, st.{value_col} AS value, i.id AS {id_col}
            FROM {stats_table} st
            JOIN {item_table} i ON st.{id_col} = i.id
            WHERE 1=1 {having_clause} {filter_sql}
            ORDER BY st.{value_col} DESC, i.title
            LIMIT %s;
        """
        params.append(limit)
    else:
        # Query from raw entry table (exclude phantom weeks)
        if rank_by == "weeks_at_position":
            rank_filter = "e.rank = %s"
        else:  # weeks_in_top_n
            rank_filter = "e.rank <= %s"

        valid_weeks_cte = _VALID_HOT100_WEEKS_CTE if is_hot100 else _VALID_B200_WEEKS_CTE
        valid_weeks_table = "valid_hot100_weeks" if is_hot100 else "valid_b200_weeks"

        sql = f"""
            WITH {valid_weeks_cte}
            SELECT i.title, i.artist_credit, COUNT(*) AS value, i.id AS {id_col}
            FROM {entry_table} e
            JOIN {item_table} i ON e.{id_col} = i.id
            JOIN {stats_table} st ON st.{id_col} = i.id
            WHERE e.chart_week_id IN (SELECT id FROM {valid_weeks_table})
              AND {rank_filter} {filter_sql}
            GROUP BY i.id, i.title, i.artist_credit
            ORDER BY value DESC, i.title
            LIMIT %s;
        """
        params = [rank_by_param] + params
        params.append(limit)

    rows = execute_query(sql, tuple(params))
    id_key = "song_id" if is_hot100 else "album_id"
    return [
        RecordEntry(
            rank=i + 1,
            title=r["title"],
            artist_credit=r["artist_credit"],
            value=r["value"],
            **{id_key: r[id_col]},
        )
        for i, r in enumerate(rows)
    ]
