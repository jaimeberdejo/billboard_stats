"""Build pre-computed statistics tables from raw chart entries.

Handles phantom chart weeks: the billboard.py library returns the first
real chart for any query date before the chart actually started. These
phantom weeks are detected (ALL entries have is_new=true AND weeks_on_chart=1)
and excluded from stats, keeping only the earliest such week per chart type.

Phantom-week filtering is expressed by ONE parametric source (Phase 9, made the
sole path in Phase 15):

* ``valid_weeks_cte`` expresses the phantom rule as ONE parametric CTE keyed by
  ``chart_id`` over the polymorphic ``chart_entries`` table. Every builder
  (``build_song_stats`` / ``build_album_stats`` / ``build_artist_stats`` and the
  generalized ``build_artist_chart_stats``) resolves its chart slug to a
  ``chart_id`` and binds that one int into this CTE -- so the v1.0-named stats
  tables (``song_stats`` / ``album_stats`` / ``artist_stats``) and the
  ``artist_chart_stats`` rollup share the SAME phantom rule over the SAME storage.
  Adding a chart adds rows, never columns.

Phase 15 retired the legacy bifurcated storage: the two hardcoded per-chart-type
phantom CTE constants and every read of the legacy hot-100 / billboard-200 entry
tables here were re-pointed onto ``chart_entries`` filtered by ``chart_id``. The
re-pointed builds produce byte-identical ``*_stats`` rows (gated by
``tests/test_stats_equivalence.py``), because ``chart_entries`` was backfilled
from and dual-written alongside the legacy tables, and ``valid_weeks_cte`` picks
the SAME ``MIN(chart_weeks.id)`` first-real week the legacy CTEs picked.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _resolve_chart_id(conn, slug: str) -> int:
    """Resolve a chart slug to its registry ``chart_id`` (an int).

    Mirrors :func:`billboard_stats.etl.loader._resolve_chart_id`. The parametric
    ``valid_weeks_cte`` binds a ``%s::int`` chart_id, NOT a slug -- so each
    re-pointed builder resolves its slug once and binds the int (Pitfall 1).
    Raises ``ValueError`` if the slug is unknown (a missing registry row would
    otherwise silently produce empty stats).
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM charts WHERE slug = %s;", (slug,))
        row = cur.fetchone()
    if not row or row[0] is None:
        raise ValueError(f"No chart registered for slug {slug!r}")
    return row[0]


def valid_weeks_cte(name: str = "valid_weeks") -> str:
    """Return the SQL body of a parametric valid-weeks CTE keyed by ``chart_id``.

    This is the SINGLE parametric source every stats build uses (success
    criterion #5). It encodes the SAME phantom-week rule the retired v1.0
    per-chart-type literal CTEs encoded
    -- a week is phantom when >= 95% of THAT CHART's ``chart_entries`` rows for the
    week have ``is_new = true AND weeks_on_chart = 1`` -- but keyed by a
    ``chart_id`` bind parameter over the polymorphic ``chart_entries`` table
    instead of a hardcoded ``chart_type`` literal. The earliest phantom week --
    selected by ``MIN(chart_weeks.id)`` scoped to the bound chart, identical to
    the v1.0 literal CTEs' ``MIN(cw.id)`` rule (CR-01) -- is kept as the real
    first chart; all later phantoms are excluded.

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
        -- Pick the SAME "first real" week the retired v1.0 literal per-chart-type
        -- CTEs picked, which use
        -- MIN(cw.id) scoped to the chart. Using MIN(id) -- NOT
        -- ORDER BY chart_date -- guarantees the parametric path and the v1.0
        -- path select the identical first-real week even when chart_weeks.id
        -- order != chart_date order (e.g. backfilled / re-ingested weeks
        -- inserted out of date order, as in this migration and the Phase 7
        -- offline-raw-JSON backfill). The bound chart_id scope makes the two
        -- paths provably identical on the same data (CR-01). If a date-ordered
        -- tie-break is ever wanted, change BOTH paths together -- never ship
        -- two paths that silently disagree on production data.
        SELECT MIN(cw.id) AS id
        FROM phantom_{name} ph
        JOIN chart_weeks cw ON ph.chart_week_id = cw.id
        WHERE cw.chart_id = (SELECT chart_id FROM bound_{name})
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
    """Populate all stats tables in a SINGLE transaction. Call after all chart
    data is loaded.

    Runs BOTH stats paths during the transition (Plan 10-02):

    * The v1.0 literal path (``build_song_stats`` / ``build_album_stats`` /
      ``build_artist_stats``) over the bifurcated hot100_entries/b200_entries
      tables -- KEPT byte-unchanged so the unchanged v1.0 frontend keeps reading
      ``artist_stats``. Phase 15 retires it.
    * The generalized registry-loop rollup (``build_artist_chart_stats``), which
      is the canonical multi-chart stats run: it loops the ``charts`` registry
      and, per chart, aggregates the polymorphic ``chart_entries`` under the
      single parametric phantom CTE -- adding a chart adds ROWS, never columns.

    The rollup runs AFTER the v1.0 builds and does not touch ``artist_stats``;
    it is safe to run even when ``chart_entries`` is empty (it simply writes no
    rows for charts with no entries).

    CR-02: every builder is a ``DELETE FROM <stats_table>`` + repopulate. They run
    here with ``commit=False`` so the whole rebuild is ONE transaction committed
    exactly once at the end. This protects the LIVE v1.0 site during the dual-write
    transition: a concurrent reader sees the OLD stats until the final commit
    atomically flips to the NEW set, never an empty/half-rebuilt ``artist_stats``
    (or any other stats table) mid-rebuild. On any failure we roll back, leaving
    the previous stats intact rather than freezing the site on an empty table.
    """
    try:
        logger.info("Building song stats...")
        build_song_stats(conn, commit=False)
        logger.info("Building album stats...")
        build_album_stats(conn, commit=False)
        logger.info("Building artist stats...")
        build_artist_stats(conn, commit=False)
        # Canonical multi-chart stats run: the generalized per-chart rollup loops
        # the registry and is additive over the v1.0 builds above.
        logger.info("Building artist_chart_stats rollup...")
        build_artist_chart_stats(conn, commit=False)
        # Single atomic flip: readers go straight from the old stats to the new.
        conn.commit()
        logger.info("Stats build complete.")
    except Exception:
        # Leave the previous stats intact rather than exposing an empty table.
        conn.rollback()
        logger.exception("Stats rebuild failed; rolled back (previous stats kept).")
        raise


def build_song_stats(conn, commit=True):
    """Populate song_stats from the hot-100 ``chart_entries``, excluding phantoms.

    Re-pointed in Phase 15: aggregates ``chart_entries`` filtered by the hot-100
    ``chart_id`` (resolved once from the ``'hot-100'`` slug) under the parametric
    ``valid_weeks_cte``, instead of the retired ``hot100_entries`` table. The rows
    written are byte-identical to the legacy build (``tests/test_stats_equivalence``).

    ``commit=False`` defers the commit so :func:`build_all_stats` can wrap the
    whole multi-table rebuild in one transaction (CR-02); direct callers keep the
    default per-build commit.
    """
    hot100_chart_id = _resolve_chart_id(conn, "hot-100")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM song_stats;")
        cur.execute(f"""
            WITH {valid_weeks_cte('valid_weeks')}
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
            FROM chart_entries e
            JOIN chart_weeks cw ON e.chart_week_id = cw.id
            WHERE e.chart_id = (SELECT chart_id FROM bound_valid_weeks)
              AND e.chart_week_id IN (SELECT id FROM valid_weeks)
            GROUP BY e.song_id;
        """, (hot100_chart_id,))

        # Update weeks_at_peak
        cur.execute(f"""
            WITH {valid_weeks_cte('valid_weeks')}
            UPDATE song_stats ss
            SET weeks_at_peak = sub.cnt
            FROM (
                SELECT e.song_id, COUNT(*) AS cnt
                FROM chart_entries e
                JOIN song_stats s ON e.song_id = s.song_id AND e.rank = s.peak_position
                WHERE e.chart_id = (SELECT chart_id FROM bound_valid_weeks)
                  AND e.chart_week_id IN (SELECT id FROM valid_weeks)
                GROUP BY e.song_id
            ) sub
            WHERE ss.song_id = sub.song_id;
        """, (hot100_chart_id,))

        # Update debut_position
        cur.execute(f"""
            WITH {valid_weeks_cte('valid_weeks')}
            UPDATE song_stats ss
            SET debut_position = sub.rank
            FROM (
                SELECT DISTINCT ON (e.song_id) e.song_id, e.rank
                FROM chart_entries e
                JOIN chart_weeks cw ON e.chart_week_id = cw.id
                WHERE e.chart_id = (SELECT chart_id FROM bound_valid_weeks)
                  AND e.chart_week_id IN (SELECT id FROM valid_weeks)
                ORDER BY e.song_id, cw.chart_date
            ) sub
            WHERE ss.song_id = sub.song_id;
        """, (hot100_chart_id,))

    if commit:
        conn.commit()


def build_album_stats(conn, commit=True):
    """Populate album_stats from the billboard-200 ``chart_entries``, excluding phantoms.

    Re-pointed in Phase 15: aggregates ``chart_entries`` filtered by the
    billboard-200 ``chart_id`` (resolved once from the ``'billboard-200'`` slug)
    under the parametric ``valid_weeks_cte``, instead of the retired
    ``b200_entries`` table. Rows are byte-identical to the legacy build.

    ``commit=False`` defers the commit for :func:`build_all_stats`'s single-
    transaction rebuild (CR-02).
    """
    b200_chart_id = _resolve_chart_id(conn, "billboard-200")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM album_stats;")
        cur.execute(f"""
            WITH {valid_weeks_cte('valid_weeks')}
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
            FROM chart_entries e
            JOIN chart_weeks cw ON e.chart_week_id = cw.id
            WHERE e.chart_id = (SELECT chart_id FROM bound_valid_weeks)
              AND e.chart_week_id IN (SELECT id FROM valid_weeks)
            GROUP BY e.album_id;
        """, (b200_chart_id,))

        cur.execute(f"""
            WITH {valid_weeks_cte('valid_weeks')}
            UPDATE album_stats ss
            SET weeks_at_peak = sub.cnt
            FROM (
                SELECT e.album_id, COUNT(*) AS cnt
                FROM chart_entries e
                JOIN album_stats s ON e.album_id = s.album_id AND e.rank = s.peak_position
                WHERE e.chart_id = (SELECT chart_id FROM bound_valid_weeks)
                  AND e.chart_week_id IN (SELECT id FROM valid_weeks)
                GROUP BY e.album_id
            ) sub
            WHERE ss.album_id = sub.album_id;
        """, (b200_chart_id,))

        cur.execute(f"""
            WITH {valid_weeks_cte('valid_weeks')}
            UPDATE album_stats ss
            SET debut_position = sub.rank
            FROM (
                SELECT DISTINCT ON (e.album_id) e.album_id, e.rank
                FROM chart_entries e
                JOIN chart_weeks cw ON e.chart_week_id = cw.id
                WHERE e.chart_id = (SELECT chart_id FROM bound_valid_weeks)
                  AND e.chart_week_id IN (SELECT id FROM valid_weeks)
                ORDER BY e.album_id, cw.chart_date
            ) sub
            WHERE ss.album_id = sub.album_id;
        """, (b200_chart_id,))

    if commit:
        conn.commit()


def build_artist_stats(conn, commit=True):
    """Populate artist_stats with cross-chart career statistics, excluding phantom weeks.

    Re-pointed in Phase 15: the per-chart weeks/number-ones/peak/date blocks
    aggregate ``chart_entries`` filtered by the resolved hot-100 / billboard-200
    ``chart_id`` under the parametric ``valid_weeks_cte`` (one CTE namespace per
    chart so the combined two-chart UPDATE binds both), instead of the retired
    ``hot100_entries`` / ``b200_entries`` tables. ``COUNT(*)`` over the
    ``song_artists`` / ``album_artists`` join is PRESERVED exactly (summed
    entity-weeks, NOT distinct calendar weeks -- WR-01 / Pitfall 2); the
    ``total_*_songs`` / ``total_*_albums`` counts already read the link tables and
    are untouched. Rows are byte-identical to the legacy build.

    ``commit=False`` defers the commit for :func:`build_all_stats`'s single-
    transaction rebuild (CR-02), so the live frontend never reads an empty
    ``artist_stats`` mid-rebuild.
    """
    hot100_chart_id = _resolve_chart_id(conn, "hot-100")
    b200_chart_id = _resolve_chart_id(conn, "billboard-200")
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
        # COUNT(*) over song_artists is PRESERVED (summed entity-weeks, WR-01).
        cur.execute(f"""
            WITH {valid_weeks_cte('valid_hot100')}
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
                JOIN chart_entries e ON sa.song_id = e.song_id
                WHERE e.chart_id = (SELECT chart_id FROM bound_valid_hot100)
                  AND e.chart_week_id IN (SELECT id FROM valid_hot100)
                GROUP BY sa.artist_id
            ) sub
            WHERE ast.artist_id = sub.artist_id;
        """, (hot100_chart_id,))

        # Billboard 200 total weeks & number ones & best peak (filtered)
        # COUNT(*) over album_artists is PRESERVED (summed entity-weeks, WR-01).
        cur.execute(f"""
            WITH {valid_weeks_cte('valid_b200')}
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
                JOIN chart_entries e ON aa.album_id = e.album_id
                WHERE e.chart_id = (SELECT chart_id FROM bound_valid_b200)
                  AND e.chart_week_id IN (SELECT id FROM valid_b200)
                GROUP BY aa.artist_id
            ) sub
            WHERE ast.artist_id = sub.artist_id;
        """, (b200_chart_id,))

        # First and latest chart dates (filtered, union of both charts)
        # Two CTE namespaces (valid_hot100 / valid_b200), each bound to its own
        # chart_id, so the combined UPDATE binds both ids (hot-100 first, b200 next).
        cur.execute(f"""
            WITH {valid_weeks_cte('valid_hot100')},
            {valid_weeks_cte('valid_b200')}
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
                    JOIN chart_entries e ON sa.song_id = e.song_id
                    JOIN chart_weeks cw ON e.chart_week_id = cw.id
                    WHERE e.chart_id = (SELECT chart_id FROM bound_valid_hot100)
                      AND e.chart_week_id IN (SELECT id FROM valid_hot100)
                    UNION ALL
                    SELECT aa.artist_id, cw.chart_date
                    FROM album_artists aa
                    JOIN chart_entries e ON aa.album_id = e.album_id
                    JOIN chart_weeks cw ON e.chart_week_id = cw.id
                    WHERE e.chart_id = (SELECT chart_id FROM bound_valid_b200)
                      AND e.chart_week_id IN (SELECT id FROM valid_b200)
                ) combined
                GROUP BY artist_id
            ) sub
            WHERE ast.artist_id = sub.artist_id;
        """, (hot100_chart_id, b200_chart_id))

        # Max simultaneous Hot 100 entries (filtered)
        cur.execute(f"""
            WITH {valid_weeks_cte('valid_hot100')}
            UPDATE artist_stats ast
            SET max_simultaneous_hot100 = sub.max_sim
            FROM (
                SELECT
                    sa.artist_id,
                    MAX(week_count) AS max_sim
                FROM (
                    SELECT sa2.artist_id, e.chart_week_id, COUNT(*) AS week_count
                    FROM song_artists sa2
                    JOIN chart_entries e ON sa2.song_id = e.song_id
                    WHERE e.chart_id = (SELECT chart_id FROM bound_valid_hot100)
                      AND e.chart_week_id IN (SELECT id FROM valid_hot100)
                    GROUP BY sa2.artist_id, e.chart_week_id
                ) sa
                GROUP BY sa.artist_id
            ) sub
            WHERE ast.artist_id = sub.artist_id;
        """, (hot100_chart_id,))

    if commit:
        conn.commit()


def build_artist_chart_stats(conn, commit=True):
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

    ``commit=False`` defers the commit for :func:`build_all_stats`'s single-
    transaction rebuild (CR-02).
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
                        -- total_weeks is "summed entity-weeks of presence",
                        -- NOT distinct calendar weeks: one entry contributes 1
                        -- per linked artist, so an artist with two entities
                        -- charting in the SAME week counts +2. This matches the
                        -- v1.0 build_artist_stats COUNT(*) over the same join
                        -- (total_hot100_weeks / total_b200_weeks) exactly, so
                        -- the two paths stay consistent (WR-01). Use
                        -- COUNT(DISTINCT e.chart_week_id) only if the semantic
                        -- is deliberately changed in BOTH paths.
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

    if commit:
        conn.commit()
