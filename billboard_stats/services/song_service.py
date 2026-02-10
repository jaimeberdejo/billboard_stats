"""Song chart runs, stats, and search queries."""

from typing import List, Optional

from billboard_stats.db.connection import execute_query
from billboard_stats.etl.stats_builder import _VALID_HOT100_WEEKS_CTE
from billboard_stats.models.schemas import (
    Artist,
    ChartRunEntry,
    Song,
    SongStats,
    SongWithStats,
)


def get_song(song_id: int) -> Optional[SongWithStats]:
    """Return a song with its stats and associated artists."""
    rows = execute_query(
        "SELECT id, title, artist_credit, image_url FROM songs WHERE id = %s;",
        (song_id,),
    )
    if not rows:
        return None

    song = Song(**rows[0])

    stats_rows = execute_query(
        "SELECT * FROM song_stats WHERE song_id = %s;",
        (song_id,),
    )
    stats = SongStats(**stats_rows[0]) if stats_rows else None

    artist_rows = execute_query(
        """
        SELECT a.id, a.name, a.image_url
        FROM song_artists sa
        JOIN artists a ON sa.artist_id = a.id
        WHERE sa.song_id = %s
        ORDER BY sa.role, a.name;
        """,
        (song_id,),
    )
    artists = [Artist(**r) for r in artist_rows]

    return SongWithStats(song=song, stats=stats, artists=artists)


def get_chart_run(song_id: int) -> List[ChartRunEntry]:
    """Full weekly position history for a song (excludes phantom weeks)."""
    rows = execute_query(
        f"""
        WITH {_VALID_HOT100_WEEKS_CTE}
        SELECT cw.chart_date, e.rank, e.last_pos, e.is_new,
               e.peak_pos, e.weeks_on_chart
        FROM hot100_entries e
        JOIN chart_weeks cw ON e.chart_week_id = cw.id
        WHERE e.song_id = %s
          AND cw.id IN (SELECT id FROM valid_hot100_weeks)
        ORDER BY cw.chart_date;
        """,
        (song_id,),
    )
    return [ChartRunEntry(**r) for r in rows]


def get_song_stats(song_id: int) -> Optional[SongStats]:
    """Pre-computed stats for a song."""
    rows = execute_query(
        "SELECT * FROM song_stats WHERE song_id = %s;",
        (song_id,),
    )
    return SongStats(**rows[0]) if rows else None


def search_songs(query: str, limit: int = 20) -> List[SongWithStats]:
    """Fuzzy search songs by title."""
    rows = execute_query(
        """
        SELECT s.id, s.title, s.artist_credit, s.image_url,
               ss.total_weeks, ss.peak_position, ss.weeks_at_number_one,
               ss.debut_date,
               similarity(s.title, %s) AS sim
        FROM songs s
        LEFT JOIN song_stats ss ON s.id = ss.song_id
        WHERE s.title %% %s
        ORDER BY sim DESC
        LIMIT %s;
        """,
        (query, query, limit),
    )
    results = []
    for r in rows:
        song = Song(id=r["id"], title=r["title"],
                     artist_credit=r["artist_credit"], image_url=r["image_url"])
        stats = None
        if r["total_weeks"] is not None:
            stats = SongStats(
                song_id=r["id"], total_weeks=r["total_weeks"],
                peak_position=r["peak_position"],
                weeks_at_number_one=r["weeks_at_number_one"],
                debut_date=r["debut_date"],
            )
        results.append(SongWithStats(song=song, stats=stats))
    return results
