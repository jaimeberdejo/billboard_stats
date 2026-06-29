"""Weekly chart snapshot queries."""

from datetime import date
from typing import List

from billboard_stats.db.connection import execute_query
from billboard_stats.etl.stats_builder import valid_weeks_cte
from billboard_stats.models.schemas import ChartEntry


def get_weekly_chart(chart_date: date, chart_type: str = "hot-100") -> List[ChartEntry]:
    """Full chart for a specific week.

    Args:
        chart_date: The chart publication date.
        chart_type: 'hot-100' or 'billboard-200' (a chart SLUG, resolved to a
            chart_id; NOT the dropped chart-type discriminator column).
    """
    if chart_type == "hot-100":
        rows = execute_query(
            f"""
            WITH {valid_weeks_cte('valid_weeks')}
            SELECT e.rank, s.title, s.artist_credit, s.image_url,
                   e.peak_pos, e.last_pos, e.weeks_on_chart, e.is_new, e.song_id
            FROM chart_entries e
            JOIN chart_weeks cw ON e.chart_week_id = cw.id
            JOIN songs s ON e.song_id = s.id
            WHERE e.chart_id = (SELECT chart_id FROM bound_valid_weeks)
              AND cw.chart_date = %s
              AND cw.id IN (SELECT id FROM valid_weeks)
            ORDER BY e.rank;
            """,
            (_chart_id("hot-100"), chart_date),
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
            WITH {valid_weeks_cte('valid_weeks')}
            SELECT e.rank, a.title, a.artist_credit, a.image_url,
                   e.peak_pos, e.last_pos, e.weeks_on_chart, e.is_new, e.album_id
            FROM chart_entries e
            JOIN chart_weeks cw ON e.chart_week_id = cw.id
            JOIN albums a ON e.album_id = a.id
            WHERE e.chart_id = (SELECT chart_id FROM bound_valid_weeks)
              AND cw.chart_date = %s
              AND cw.id IN (SELECT id FROM valid_weeks)
            ORDER BY e.rank;
            """,
            (_chart_id("billboard-200"), chart_date),
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

    ``chart_type`` is a chart SLUG (resolved to a chart_id and bound into the
    parametric ``valid_weeks_cte``), NOT the dropped chart-type discriminator
    column.
    """
    rows = execute_query(
        f"""
        WITH {valid_weeks_cte('valid_weeks')}
        SELECT cw.chart_date
        FROM chart_weeks cw
        WHERE cw.chart_id = (SELECT chart_id FROM bound_valid_weeks)
          AND cw.id IN (SELECT id FROM valid_weeks)
        ORDER BY cw.chart_date DESC;
        """,
        (_chart_id(chart_type),),
    )
    return [r["chart_date"] for r in rows]


def _chart_id(slug: str) -> int:
    """Resolve a chart slug to its registry chart_id (an int).

    The parametric ``valid_weeks_cte`` binds a ``%s::int`` chart_id, so each query
    resolves its slug to an int first (Pitfall 1).
    """
    rows = execute_query("SELECT id FROM charts WHERE slug = %s;", (slug,))
    if not rows or rows[0]["id"] is None:
        raise ValueError(f"No chart registered for slug {slug!r}")
    return rows[0]["id"]
