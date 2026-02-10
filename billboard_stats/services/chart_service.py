"""Weekly chart snapshot queries."""

from datetime import date
from typing import List

from billboard_stats.db.connection import execute_query
from billboard_stats.etl.stats_builder import _VALID_HOT100_WEEKS_CTE, _VALID_B200_WEEKS_CTE
from billboard_stats.models.schemas import ChartEntry


def get_weekly_chart(chart_date: date, chart_type: str = "hot-100") -> List[ChartEntry]:
    """Full chart for a specific week.

    Args:
        chart_date: The chart publication date.
        chart_type: 'hot-100' or 'billboard-200'.
    """
    if chart_type == "hot-100":
        rows = execute_query(
            f"""
            WITH {_VALID_HOT100_WEEKS_CTE}
            SELECT e.rank, s.title, s.artist_credit, s.image_url,
                   e.peak_pos, e.last_pos, e.weeks_on_chart, e.is_new, e.song_id
            FROM hot100_entries e
            JOIN chart_weeks cw ON e.chart_week_id = cw.id
            JOIN songs s ON e.song_id = s.id
            WHERE cw.chart_date = %s AND cw.chart_type = %s
              AND cw.id IN (SELECT id FROM valid_hot100_weeks)
            ORDER BY e.rank;
            """,
            (chart_date, chart_type),
        )
        return [
            ChartEntry(
                rank=r["rank"], title=r["title"], artist_credit=r["artist_credit"],
                image_url=r["image_url"], peak_pos=r["peak_pos"],
                last_pos=r["last_pos"], weeks_on_chart=r["weeks_on_chart"],
                is_new=r["is_new"], song_id=r["song_id"],
            )
            for r in rows
        ]
    else:
        rows = execute_query(
            f"""
            WITH {_VALID_B200_WEEKS_CTE}
            SELECT e.rank, a.title, a.artist_credit, a.image_url,
                   e.peak_pos, e.last_pos, e.weeks_on_chart, e.is_new, e.album_id
            FROM b200_entries e
            JOIN chart_weeks cw ON e.chart_week_id = cw.id
            JOIN albums a ON e.album_id = a.id
            WHERE cw.chart_date = %s AND cw.chart_type = %s
              AND cw.id IN (SELECT id FROM valid_b200_weeks)
            ORDER BY e.rank;
            """,
            (chart_date, chart_type),
        )
        return [
            ChartEntry(
                rank=r["rank"], title=r["title"], artist_credit=r["artist_credit"],
                image_url=r["image_url"], peak_pos=r["peak_pos"],
                last_pos=r["last_pos"], weeks_on_chart=r["weeks_on_chart"],
                is_new=r["is_new"], album_id=r["album_id"],
            )
            for r in rows
        ]


def get_available_dates(chart_type: str = "hot-100") -> List[date]:
    """All available chart dates for a given chart type, newest first.

    Excludes phantom weeks (duplicate data from before the chart started).
    """
    valid_cte = _VALID_HOT100_WEEKS_CTE if chart_type == "hot-100" else _VALID_B200_WEEKS_CTE
    valid_table = "valid_hot100_weeks" if chart_type == "hot-100" else "valid_b200_weeks"
    rows = execute_query(
        f"""
        WITH {valid_cte}
        SELECT cw.chart_date
        FROM chart_weeks cw
        WHERE cw.chart_type = %s
          AND cw.id IN (SELECT id FROM {valid_table})
        ORDER BY cw.chart_date DESC;
        """,
        (chart_type,),
    )
    return [r["chart_date"] for r in rows]
