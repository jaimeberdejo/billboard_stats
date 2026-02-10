"""Build pre-computed statistics tables from raw chart entries.

Handles phantom chart weeks: the billboard.py library returns the first
real chart for any query date before the chart actually started. These
phantom weeks are detected (ALL entries have is_new=true AND weeks_on_chart=1)
and excluded from stats, keeping only the earliest such week per chart type.
"""

import logging

logger = logging.getLogger(__name__)

# Common CTE to identify valid Hot 100 chart weeks (excluding phantoms).
# A phantom week is one where 95%+ of entries have is_new=true AND weeks_on_chart=1.
# (Some phantoms have a few stray entries that don't match perfectly.)
# We keep only the earliest such week (the real first chart).
_VALID_HOT100_WEEKS_CTE = """
    phantom_hot100 AS (
        SELECT e.chart_week_id
        FROM hot100_entries e
        GROUP BY e.chart_week_id
        HAVING COUNT(*) FILTER (WHERE e.is_new = true AND e.weeks_on_chart = 1)
               >= COUNT(*) * 95 / 100
    ),
    first_real_hot100 AS (
        SELECT MIN(cw.id) AS id
        FROM phantom_hot100 ph
        JOIN chart_weeks cw ON ph.chart_week_id = cw.id
        WHERE cw.chart_type = 'hot-100'
    ),
    valid_hot100_weeks AS (
        SELECT cw.id
        FROM chart_weeks cw
        WHERE cw.chart_type = 'hot-100'
          AND (cw.id NOT IN (SELECT chart_week_id FROM phantom_hot100)
               OR cw.id = (SELECT id FROM first_real_hot100))
    )
"""

# Same for Billboard 200
_VALID_B200_WEEKS_CTE = """
    phantom_b200 AS (
        SELECT e.chart_week_id
        FROM b200_entries e
        GROUP BY e.chart_week_id
        HAVING COUNT(*) FILTER (WHERE e.is_new = true AND e.weeks_on_chart = 1)
               >= COUNT(*) * 95 / 100
    ),
    first_real_b200 AS (
        SELECT MIN(cw.id) AS id
        FROM phantom_b200 ph
        JOIN chart_weeks cw ON ph.chart_week_id = cw.id
        WHERE cw.chart_type = 'billboard-200'
    ),
    valid_b200_weeks AS (
        SELECT cw.id
        FROM chart_weeks cw
        WHERE cw.chart_type = 'billboard-200'
          AND (cw.id NOT IN (SELECT chart_week_id FROM phantom_b200)
               OR cw.id = (SELECT id FROM first_real_b200))
    )
"""


def build_all_stats(conn):
    """Populate all stats tables. Call after all chart data is loaded."""
    logger.info("Building song stats...")
    build_song_stats(conn)
    logger.info("Building album stats...")
    build_album_stats(conn)
    logger.info("Building artist stats...")
    build_artist_stats(conn)
    logger.info("Stats build complete.")


def build_song_stats(conn):
    """Populate song_stats from hot100_entries, excluding phantom weeks."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM song_stats;")
        cur.execute(f"""
            WITH {_VALID_HOT100_WEEKS_CTE}
            INSERT INTO song_stats (
                song_id, total_weeks, peak_position, weeks_at_peak,
                weeks_at_number_one, debut_date, last_date, debut_position
            )
            SELECT
                e.song_id,
                COUNT(*) AS total_weeks,
                MIN(e.rank) AS peak_position,
                0 AS weeks_at_peak,
                COUNT(*) FILTER (WHERE e.rank = 1) AS weeks_at_number_one,
                MIN(cw.chart_date) AS debut_date,
                MAX(cw.chart_date) AS last_date,
                NULL AS debut_position
            FROM hot100_entries e
            JOIN chart_weeks cw ON e.chart_week_id = cw.id
            WHERE e.chart_week_id IN (SELECT id FROM valid_hot100_weeks)
            GROUP BY e.song_id;
        """)

        # Update weeks_at_peak
        cur.execute(f"""
            WITH {_VALID_HOT100_WEEKS_CTE}
            UPDATE song_stats ss
            SET weeks_at_peak = sub.cnt
            FROM (
                SELECT e.song_id, COUNT(*) AS cnt
                FROM hot100_entries e
                JOIN song_stats s ON e.song_id = s.song_id AND e.rank = s.peak_position
                WHERE e.chart_week_id IN (SELECT id FROM valid_hot100_weeks)
                GROUP BY e.song_id
            ) sub
            WHERE ss.song_id = sub.song_id;
        """)

        # Update debut_position
        cur.execute(f"""
            WITH {_VALID_HOT100_WEEKS_CTE}
            UPDATE song_stats ss
            SET debut_position = sub.rank
            FROM (
                SELECT DISTINCT ON (e.song_id) e.song_id, e.rank
                FROM hot100_entries e
                JOIN chart_weeks cw ON e.chart_week_id = cw.id
                WHERE e.chart_week_id IN (SELECT id FROM valid_hot100_weeks)
                ORDER BY e.song_id, cw.chart_date
            ) sub
            WHERE ss.song_id = sub.song_id;
        """)

    conn.commit()


def build_album_stats(conn):
    """Populate album_stats from b200_entries, excluding phantom weeks."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM album_stats;")
        cur.execute(f"""
            WITH {_VALID_B200_WEEKS_CTE}
            INSERT INTO album_stats (
                album_id, total_weeks, peak_position, weeks_at_peak,
                weeks_at_number_one, debut_date, last_date, debut_position
            )
            SELECT
                e.album_id,
                COUNT(*) AS total_weeks,
                MIN(e.rank) AS peak_position,
                0 AS weeks_at_peak,
                COUNT(*) FILTER (WHERE e.rank = 1) AS weeks_at_number_one,
                MIN(cw.chart_date) AS debut_date,
                MAX(cw.chart_date) AS last_date,
                NULL AS debut_position
            FROM b200_entries e
            JOIN chart_weeks cw ON e.chart_week_id = cw.id
            WHERE e.chart_week_id IN (SELECT id FROM valid_b200_weeks)
            GROUP BY e.album_id;
        """)

        cur.execute(f"""
            WITH {_VALID_B200_WEEKS_CTE}
            UPDATE album_stats ss
            SET weeks_at_peak = sub.cnt
            FROM (
                SELECT e.album_id, COUNT(*) AS cnt
                FROM b200_entries e
                JOIN album_stats s ON e.album_id = s.album_id AND e.rank = s.peak_position
                WHERE e.chart_week_id IN (SELECT id FROM valid_b200_weeks)
                GROUP BY e.album_id
            ) sub
            WHERE ss.album_id = sub.album_id;
        """)

        cur.execute(f"""
            WITH {_VALID_B200_WEEKS_CTE}
            UPDATE album_stats ss
            SET debut_position = sub.rank
            FROM (
                SELECT DISTINCT ON (e.album_id) e.album_id, e.rank
                FROM b200_entries e
                JOIN chart_weeks cw ON e.chart_week_id = cw.id
                WHERE e.chart_week_id IN (SELECT id FROM valid_b200_weeks)
                ORDER BY e.album_id, cw.chart_date
            ) sub
            WHERE ss.album_id = sub.album_id;
        """)

    conn.commit()


def build_artist_stats(conn):
    """Populate artist_stats with cross-chart career statistics, excluding phantom weeks."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM artist_stats;")

        cur.execute("""
            INSERT INTO artist_stats (artist_id)
            SELECT id FROM artists;
        """)

        # Hot 100 song counts (not affected by phantoms — counts distinct songs)
        cur.execute("""
            UPDATE artist_stats ast
            SET total_hot100_songs = sub.cnt
            FROM (
                SELECT sa.artist_id, COUNT(DISTINCT sa.song_id) AS cnt
                FROM song_artists sa
                GROUP BY sa.artist_id
            ) sub
            WHERE ast.artist_id = sub.artist_id;
        """)

        # Billboard 200 album counts
        cur.execute("""
            UPDATE artist_stats ast
            SET total_b200_albums = sub.cnt
            FROM (
                SELECT aa.artist_id, COUNT(DISTINCT aa.album_id) AS cnt
                FROM album_artists aa
                GROUP BY aa.artist_id
            ) sub
            WHERE ast.artist_id = sub.artist_id;
        """)

        # Hot 100 total weeks & number ones & best peak (filtered)
        cur.execute(f"""
            WITH {_VALID_HOT100_WEEKS_CTE}
            UPDATE artist_stats ast
            SET total_hot100_weeks = sub.total_weeks,
                hot100_number_ones = sub.num_ones,
                best_hot100_peak = sub.best_peak
            FROM (
                SELECT
                    sa.artist_id,
                    COUNT(*) AS total_weeks,
                    COUNT(DISTINCT e.song_id) FILTER (WHERE e.rank = 1) AS num_ones,
                    MIN(e.rank) AS best_peak
                FROM song_artists sa
                JOIN hot100_entries e ON sa.song_id = e.song_id
                WHERE e.chart_week_id IN (SELECT id FROM valid_hot100_weeks)
                GROUP BY sa.artist_id
            ) sub
            WHERE ast.artist_id = sub.artist_id;
        """)

        # Billboard 200 total weeks & number ones & best peak (filtered)
        cur.execute(f"""
            WITH {_VALID_B200_WEEKS_CTE}
            UPDATE artist_stats ast
            SET total_b200_weeks = sub.total_weeks,
                b200_number_ones = sub.num_ones,
                best_b200_peak = sub.best_peak
            FROM (
                SELECT
                    aa.artist_id,
                    COUNT(*) AS total_weeks,
                    COUNT(DISTINCT e.album_id) FILTER (WHERE e.rank = 1) AS num_ones,
                    MIN(e.rank) AS best_peak
                FROM album_artists aa
                JOIN b200_entries e ON aa.album_id = e.album_id
                WHERE e.chart_week_id IN (SELECT id FROM valid_b200_weeks)
                GROUP BY aa.artist_id
            ) sub
            WHERE ast.artist_id = sub.artist_id;
        """)

        # First and latest chart dates (filtered, union of both charts)
        cur.execute(f"""
            WITH {_VALID_HOT100_WEEKS_CTE},
            {_VALID_B200_WEEKS_CTE}
            UPDATE artist_stats ast
            SET first_chart_date = sub.first_date,
                latest_chart_date = sub.latest_date
            FROM (
                SELECT
                    artist_id,
                    MIN(chart_date) AS first_date,
                    MAX(chart_date) AS latest_date
                FROM (
                    SELECT sa.artist_id, cw.chart_date
                    FROM song_artists sa
                    JOIN hot100_entries e ON sa.song_id = e.song_id
                    JOIN chart_weeks cw ON e.chart_week_id = cw.id
                    WHERE e.chart_week_id IN (SELECT id FROM valid_hot100_weeks)
                    UNION ALL
                    SELECT aa.artist_id, cw.chart_date
                    FROM album_artists aa
                    JOIN b200_entries e ON aa.album_id = e.album_id
                    JOIN chart_weeks cw ON e.chart_week_id = cw.id
                    WHERE e.chart_week_id IN (SELECT id FROM valid_b200_weeks)
                ) combined
                GROUP BY artist_id
            ) sub
            WHERE ast.artist_id = sub.artist_id;
        """)

        # Max simultaneous Hot 100 entries (filtered)
        cur.execute(f"""
            WITH {_VALID_HOT100_WEEKS_CTE}
            UPDATE artist_stats ast
            SET max_simultaneous_hot100 = sub.max_sim
            FROM (
                SELECT
                    sa.artist_id,
                    MAX(week_count) AS max_sim
                FROM (
                    SELECT sa2.artist_id, e.chart_week_id, COUNT(*) AS week_count
                    FROM song_artists sa2
                    JOIN hot100_entries e ON sa2.song_id = e.song_id
                    WHERE e.chart_week_id IN (SELECT id FROM valid_hot100_weeks)
                    GROUP BY sa2.artist_id, e.chart_week_id
                ) sa
                GROUP BY sa.artist_id
            ) sub
            WHERE ast.artist_id = sub.artist_id;
        """)

    conn.commit()
