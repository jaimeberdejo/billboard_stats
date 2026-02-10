"""Artist profile, career stats, and chart history queries."""

from typing import List, Optional

from billboard_stats.db.connection import execute_query
from billboard_stats.etl.stats_builder import _VALID_HOT100_WEEKS_CTE, _VALID_B200_WEEKS_CTE
from billboard_stats.models.schemas import (
    Album,
    AlbumStats,
    AlbumWithStats,
    Artist,
    ArtistProfile,
    ArtistStats,
    ChartRunEntry,
    Song,
    SongStats,
    SongWithStats,
)


def get_artist_profile(artist_id: int) -> Optional[ArtistProfile]:
    """Return artist info + career stats."""
    rows = execute_query(
        "SELECT id, name, image_url FROM artists WHERE id = %s;",
        (artist_id,),
    )
    if not rows:
        return None

    artist = Artist(**rows[0])

    stats_rows = execute_query(
        "SELECT * FROM artist_stats WHERE artist_id = %s;",
        (artist_id,),
    )
    stats = ArtistStats(**stats_rows[0]) if stats_rows else None

    return ArtistProfile(artist=artist, stats=stats)


def get_artist_songs(artist_id: int) -> List[SongWithStats]:
    """All songs for an artist, with stats, ordered by debut date."""
    rows = execute_query(
        """
        SELECT s.id, s.title, s.artist_credit, s.image_url,
               ss.total_weeks, ss.peak_position, ss.weeks_at_peak,
               ss.weeks_at_number_one, ss.debut_date, ss.last_date, ss.debut_position
        FROM song_artists sa
        JOIN songs s ON sa.song_id = s.id
        LEFT JOIN song_stats ss ON s.id = ss.song_id
        WHERE sa.artist_id = %s
        ORDER BY ss.debut_date;
        """,
        (artist_id,),
    )
    results = []
    for row in rows:
        song = Song(id=row["id"], title=row["title"],
                     artist_credit=row["artist_credit"], image_url=row["image_url"])
        stats = None
        if row["total_weeks"] is not None:
            stats = SongStats(
                song_id=row["id"], total_weeks=row["total_weeks"],
                peak_position=row["peak_position"], weeks_at_peak=row["weeks_at_peak"],
                weeks_at_number_one=row["weeks_at_number_one"],
                debut_date=row["debut_date"], last_date=row["last_date"],
                debut_position=row["debut_position"],
            )
        results.append(SongWithStats(song=song, stats=stats))
    return results


def get_artist_albums(artist_id: int) -> List[AlbumWithStats]:
    """All albums for an artist, with stats, ordered by debut date."""
    rows = execute_query(
        """
        SELECT a.id, a.title, a.artist_credit, a.image_url,
               als.total_weeks, als.peak_position, als.weeks_at_peak,
               als.weeks_at_number_one, als.debut_date, als.last_date, als.debut_position
        FROM album_artists aa
        JOIN albums a ON aa.album_id = a.id
        LEFT JOIN album_stats als ON a.id = als.album_id
        WHERE aa.artist_id = %s
        ORDER BY als.debut_date;
        """,
        (artist_id,),
    )
    results = []
    for row in rows:
        album = Album(id=row["id"], title=row["title"],
                       artist_credit=row["artist_credit"], image_url=row["image_url"])
        stats = None
        if row["total_weeks"] is not None:
            stats = AlbumStats(
                album_id=row["id"], total_weeks=row["total_weeks"],
                peak_position=row["peak_position"], weeks_at_peak=row["weeks_at_peak"],
                weeks_at_number_one=row["weeks_at_number_one"],
                debut_date=row["debut_date"], last_date=row["last_date"],
                debut_position=row["debut_position"],
            )
        results.append(AlbumWithStats(album=album, stats=stats))
    return results


def search_artists(query: str, limit: int = 20) -> List[Artist]:
    """Fuzzy search artists by name using trigram similarity."""
    rows = execute_query(
        """
        SELECT id, name, image_url,
               similarity(name, %s) AS sim
        FROM artists
        WHERE name %% %s
        ORDER BY sim DESC
        LIMIT %s;
        """,
        (query, query, limit),
    )
    return [Artist(id=r["id"], name=r["name"], image_url=r["image_url"]) for r in rows]


def get_artist_timeline(artist_id: int) -> List[ChartRunEntry]:
    """Chronological chart appearances across both charts (excludes phantom weeks)."""
    rows = execute_query(
        f"""
        WITH {_VALID_HOT100_WEEKS_CTE},
        {_VALID_B200_WEEKS_CTE}
        SELECT cw.chart_date, e.rank, e.last_pos, e.is_new
        FROM hot100_entries e
        JOIN chart_weeks cw ON e.chart_week_id = cw.id
        JOIN song_artists sa ON e.song_id = sa.song_id
        WHERE sa.artist_id = %s
          AND cw.id IN (SELECT id FROM valid_hot100_weeks)
        UNION ALL
        SELECT cw.chart_date, e.rank, e.last_pos, e.is_new
        FROM b200_entries e
        JOIN chart_weeks cw ON e.chart_week_id = cw.id
        JOIN album_artists aa ON e.album_id = aa.album_id
        WHERE aa.artist_id = %s
          AND cw.id IN (SELECT id FROM valid_b200_weeks)
        ORDER BY chart_date;
        """,
        (artist_id, artist_id),
    )
    return [ChartRunEntry(**r) for r in rows]
