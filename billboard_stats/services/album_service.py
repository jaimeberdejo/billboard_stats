"""Album chart runs, stats, and search queries."""

from typing import List, Optional

from billboard_stats.db.connection import execute_query
from billboard_stats.etl.stats_builder import _VALID_B200_WEEKS_CTE
from billboard_stats.models.schemas import (
    Album,
    AlbumStats,
    AlbumWithStats,
    Artist,
    ChartRunEntry,
)


def get_album(album_id: int) -> Optional[AlbumWithStats]:
    """Return an album with its stats and associated artists."""
    rows = execute_query(
        "SELECT id, title, artist_credit, image_url FROM albums WHERE id = %s;",
        (album_id,),
    )
    if not rows:
        return None

    album = Album(**rows[0])

    stats_rows = execute_query(
        "SELECT * FROM album_stats WHERE album_id = %s;",
        (album_id,),
    )
    stats = AlbumStats(**stats_rows[0]) if stats_rows else None

    artist_rows = execute_query(
        """
        SELECT a.id, a.name, a.image_url
        FROM album_artists aa
        JOIN artists a ON aa.artist_id = a.id
        WHERE aa.album_id = %s
        ORDER BY aa.role, a.name;
        """,
        (album_id,),
    )
    artists = [Artist(**r) for r in artist_rows]

    return AlbumWithStats(album=album, stats=stats, artists=artists)


def get_chart_run(album_id: int) -> List[ChartRunEntry]:
    """Full weekly position history for an album (excludes phantom weeks)."""
    rows = execute_query(
        f"""
        WITH {_VALID_B200_WEEKS_CTE}
        SELECT cw.chart_date, e.rank, e.last_pos, e.is_new,
               e.peak_pos, e.weeks_on_chart
        FROM b200_entries e
        JOIN chart_weeks cw ON e.chart_week_id = cw.id
        WHERE e.album_id = %s
          AND cw.id IN (SELECT id FROM valid_b200_weeks)
        ORDER BY cw.chart_date;
        """,
        (album_id,),
    )
    return [ChartRunEntry(**r) for r in rows]


def get_album_stats(album_id: int) -> Optional[AlbumStats]:
    """Pre-computed stats for an album."""
    rows = execute_query(
        "SELECT * FROM album_stats WHERE album_id = %s;",
        (album_id,),
    )
    return AlbumStats(**rows[0]) if rows else None


def search_albums(query: str, limit: int = 20) -> List[AlbumWithStats]:
    """Fuzzy search albums by title."""
    rows = execute_query(
        """
        SELECT a.id, a.title, a.artist_credit, a.image_url,
               als.total_weeks, als.peak_position, als.weeks_at_number_one,
               als.debut_date,
               similarity(a.title, %s) AS sim
        FROM albums a
        LEFT JOIN album_stats als ON a.id = als.album_id
        WHERE a.title %% %s
        ORDER BY sim DESC
        LIMIT %s;
        """,
        (query, query, limit),
    )
    results = []
    for r in rows:
        album = Album(id=r["id"], title=r["title"],
                       artist_credit=r["artist_credit"], image_url=r["image_url"])
        stats = None
        if r["total_weeks"] is not None:
            stats = AlbumStats(
                album_id=r["id"], total_weeks=r["total_weeks"],
                peak_position=r["peak_position"],
                weeks_at_number_one=r["weeks_at_number_one"],
                debut_date=r["debut_date"],
            )
        results.append(AlbumWithStats(album=album, stats=stats))
    return results
