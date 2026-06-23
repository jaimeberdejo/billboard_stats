"""Build pre-computed statistics tables from raw chart entries.

Handles phantom chart weeks: the billboard.py library returns the first
real chart for any query date before the chart actually started. These
phantom weeks are detected (ALL entries have is_new=true AND weeks_on_chart=1)
and excluded from stats, keeping only the earliest such week per chart type.

Two phantom-filter paths coexist here (Phase 9):

* The v1.0 path (``_VALID_HOT100_WEEKS_CTE`` / ``_VALID_B200_WEEKS_CTE`` +
  ``build_artist_stats``) hardcodes the phantom rule once per chart_type over the
  bifurcated ``hot100_entries`` / ``b200_entries`` tables. It is KEPT UNCHANGED
  for compatibility -- the unchanged v1.0 frontend still reads ``artist_stats``.
  Phase 15 retires it, not this module.
* The generalized path (``valid_weeks_cte`` + ``build_artist_chart_stats``)
  expresses the SAME phantom rule as ONE parametric CTE keyed by ``chart_id`` over
  the polymorphic ``chart_entries`` table, feeding the ``artist_chart_stats``
  rollup (one ROW per artist x chart). Adding a chart adds rows, never columns.
"""

from __future__ import annotations

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


def valid_weeks_cte(name: str = "valid_weeks") -> str:
    """Return the SQL body of a parametric valid-weeks CTE keyed by ``chart_id``.

    This is the SINGLE parametric source the new multi-chart rollup path uses
    (success criterion #5). It encodes the SAME phantom-week rule the two v1.0
    literal CTEs (``_VALID_HOT100_WEEKS_CTE`` / ``_VALID_B200_WEEKS_CTE``) encode
    -- a week is phantom when >= 95% of THAT CHART's ``chart_entries`` rows for the
    week have ``is_new = true AND weeks_on_chart = 1`` -- but keyed by a
    ``chart_id`` bind parameter over the polymorphic ``chart_entries`` table
    instead of a hardcoded ``chart_type`` literal. The earliest phantom week is
    kept as the real first chart; all later phantoms are excluded.

    The returned text is a CTE *body* (no leading ``WITH``) producing a relation
    ``<name>`` with a single ``id`` column = the valid ``chart_week_id`` values.
    The ``chart_id`` is bound ONCE via a single ``%s`` placeholder in a leading
    ``bound_<name>`` sub-CTE and referenced everywhere as
    ``(SELECT chart_id FROM bound_<name>)`` -- so the whole CTE takes EXACTLY ONE
    bind parameter (the chart_id). There is exactly ONE such CTE for ALL charts --
    no sixth hardcoded copy.

    Args:
        name: The CTE relation name to emit (default ``valid_weeks``).

    Returns:
        SQL text for use as ``WITH <body> SELECT ...`` (or chained after other
        CTEs with a leading comma). Bind a single ``chart_id`` param.
    """
    return f"""
    bound_{name} AS (
        SELECT %s::int AS chart_id
    ),
    phantom_{name} AS (
        SELECT e.chart_week_id
        FROM chart_entries e
        WHERE e.chart_id = (SELECT chart_id FROM bound_{name})
        GROUP BY e.chart_week_id
        HAVING COUNT(*) FILTER (WHERE e.is_new = true AND e.weeks_on_chart = 1)
               >= COUNT(*) * 95 / 100
    ),
    first_real_{name} AS (
        SELECT cw.id
        FROM phantom_{name} ph
        JOIN chart_weeks cw ON ph.chart_week_id = cw.id
        ORDER BY cw.chart_date, cw.id
        LIMIT 1
    ),
    {name} AS (
        SELECT DISTINCT e.chart_week_id AS id
        FROM chart_entries e
        WHERE e.chart_id = (SELECT chart_id FROM bound_{name})
          AND (e.chart_week_id NOT IN (SELECT chart_week_id FROM phantom_{name})
               OR e.chart_week_id = (SELECT id FROM first_real_{name}))
    )
"""


# Maps a chart's entity_kind to the join that resolves a chart_entries row to the
# artist(s) it rolls up to, plus the entity-id column used for distinct counts.
# The generalized rollup branches on these so the artist-entity chart path is
# present now (drops in for free when Artist 100 is ingested in Phase 11).
_ENTITY_ROLLUP = {
    "song": {
        "join": "JOIN song_artists ja ON ja.song_id = e.song_id",
        "join2": "JOIN song_artists ja2 ON ja2.song_id = e2.song_id",
        "artist_id": "ja.artist_id",
        "artist_id2": "ja2.artist_id",
        "entity_id": "e.song_id",
    },
    "album": {
        "join": "JOIN album_artists ja ON ja.album_id = e.album_id",
        "join2": "JOIN album_artists ja2 ON ja2.album_id = e2.album_id",
        "artist_id": "ja.artist_id",
        "artist_id2": "ja2.artist_id",
        "entity_id": "e.album_id",
    },
    # Artist-entity charts (e.g. Artist 100) carry artist_id directly on the
    # chart_entries row -- no join table needed.
    "artist": {
        "join": "",
        "join2": "",
        "artist_id": "e.artist_id",
        "artist_id2": "e2.artist_id",
        "entity_id": "e.artist_id",
    },
}


def build_all_stats(conn):
    """Populate all stats tables. Call after all chart data is loaded."""
    logger.info("Building song stats...")
    build_song_stats(conn)
    logger.info("Building album stats...")
    build_album_stats(conn)
    logger.info("Building artist stats...")
    build_artist_stats(conn)
    # Additive: the generalized per-chart rollup runs AFTER the v1.0 builds and
    # does not touch artist_stats. Safe to run even when chart_entries is empty
    # (it simply writes no rows for charts with no entries).
    logger.info("Building artist_chart_stats rollup...")
    build_artist_chart_stats(conn)
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


def build_artist_chart_stats(conn):
    """Populate the generalized per-chart artist rollup ``artist_chart_stats``.

    Writes ONE row per (artist_id, chart_id) -- adding a chart adds ROWS, never
    columns -- by looping over the ``charts`` registry and, for each chart,
    aggregating ``chart_entries`` under the SINGLE parametric phantom-week CTE
    (``valid_weeks_cte``). The entity-to-artist resolution branches on the chart's
    ``entity_kind``: song charts join ``song_artists``, album charts join
    ``album_artists``, and artist-entity charts read ``artist_id`` directly off the
    entry (so Artist 100 drops in for free in Phase 11).

    Writes exactly the authoritative Plan-01 ``artist_chart_stats`` columns:
    ``total_entries``, ``total_weeks``, ``number_ones``, ``best_peak``,
    ``max_simultaneous``, ``first_date``, ``last_date``. Deterministic; this is a
    DELETE + rebuild, so re-running yields identical rows.

    Additive and independent of the v1.0 ``build_artist_stats`` path, which is left
    untouched (compatibility; Phase 15 retires it).
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM artist_chart_stats;")

        cur.execute("SELECT id, entity_kind FROM charts;")
        charts = cur.fetchall()

        for chart_id, entity_kind in charts:
            rollup = _ENTITY_ROLLUP.get(entity_kind)
            if rollup is None:
                logger.warning(
                    "Skipping chart %s: unknown entity_kind %r", chart_id, entity_kind
                )
                continue

            join_clause = rollup["join"]
            join2_clause = rollup["join2"]
            artist_id_expr = rollup["artist_id"]
            artist_id2_expr = rollup["artist_id2"]
            entity_id_expr = rollup["entity_id"]

            # One parametric INSERT per chart, bound to a single chart_id param.
            # The phantom filter is the shared valid_weeks_cte; the per-(artist,
            # week) entry counts feed max_simultaneous.
            cur.execute(
                f"""
                WITH {valid_weeks_cte('valid_weeks')}
                INSERT INTO artist_chart_stats (
                    artist_id, chart_id, total_entries, total_weeks,
                    number_ones, best_peak, max_simultaneous,
                    first_date, last_date
                )
                SELECT
                    agg.artist_id,
                    (SELECT chart_id FROM bound_valid_weeks),
                    agg.total_entries,
                    agg.total_weeks,
                    agg.number_ones,
                    agg.best_peak,
                    agg.max_simultaneous,
                    agg.first_date,
                    agg.last_date
                FROM (
                    SELECT
                        {artist_id_expr} AS artist_id,
                        COUNT(DISTINCT {entity_id_expr}) AS total_entries,
                        COUNT(*) AS total_weeks,
                        COUNT(DISTINCT {entity_id_expr})
                            FILTER (WHERE e.rank = 1) AS number_ones,
                        MIN(e.rank) AS best_peak,
                        MIN(cw.chart_date) AS first_date,
                        MAX(cw.chart_date) AS last_date,
                        COALESCE(MAX(sim.week_count), 0) AS max_simultaneous
                    FROM chart_entries e
                    JOIN chart_weeks cw ON e.chart_week_id = cw.id
                    {join_clause}
                    LEFT JOIN (
                        SELECT
                            {artist_id2_expr} AS artist_id,
                            e2.chart_week_id,
                            COUNT(*) AS week_count
                        FROM chart_entries e2
                        {join2_clause}
                        WHERE e2.chart_id = (SELECT chart_id FROM bound_valid_weeks)
                          AND e2.chart_week_id IN (SELECT id FROM valid_weeks)
                        GROUP BY {artist_id2_expr}, e2.chart_week_id
                    ) sim ON sim.artist_id = {artist_id_expr}
                         AND sim.chart_week_id = e.chart_week_id
                    WHERE e.chart_id = (SELECT chart_id FROM bound_valid_weeks)
                      AND e.chart_week_id IN (SELECT id FROM valid_weeks)
                    GROUP BY {artist_id_expr}
                ) agg;
                """,
                (chart_id,),
            )

    conn.commit()
