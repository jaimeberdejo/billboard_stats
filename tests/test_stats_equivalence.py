"""Oracle/golden tests for the Phase 15 ``*_stats`` single-store re-point.

Phase 15 retired the bifurcated v1.0 entry tables; ``build_song_stats`` /
``build_album_stats`` / ``build_artist_stats`` now read the polymorphic
``chart_entries`` table filtered by ``chart_id`` (under the parametric
``valid_weeks_cte``).

This module is a genuine **oracle / golden test**: it EXECUTES the *actual SQL
the builders emit* against a real in-memory ``sqlite3`` database seeded with a
hand-built fixture, and asserts the concrete resulting ``song_stats`` /
``album_stats`` / ``artist_stats`` rows. Because the production query text is run
verbatim (modulo a tiny, transparent dialect shim -- see ``_SqliteAdapterCursor``
below), a REAL SQL regression now fails the test:

* dropping the ``e.chart_id = (SELECT chart_id FROM bound_valid_weeks)``
  predicate would leak entries from the other chart into the aggregate;
* flipping ``COUNT(*)`` to ``COUNT(DISTINCT ...)`` would change the
  weeks-at-peak / total-weeks values the golden rows pin;
* losing the ``MIN(chart_weeks.id)`` first-real-week tie-break would change which
  phantom week is kept, hence which rows survive.

The fixture deliberately exercises three regression vectors:

  (a) a *phantom week* that MUST be excluded (a later all-``is_new`` debut week);
  (b) a *weeks-at-peak* value that would differ if ``COUNT(*)`` became
      ``COUNT(DISTINCT chart_week_id)`` (a song charting at its peak rank twice);
  (c) a *first-real-week tie-break* where ``MIN(chart_weeks.id)`` keeps a
      DIFFERENT week than ``MIN(chart_date)`` would (ids inserted out of date
      order, as backfilled / re-ingested weeks are).

The dialect shim is purposely mechanical and load-bearing-clause-preserving: it
only rewrites ``%s`` placeholders to ``?``, strips the ``::int`` cast, and
rewrites the single ``DISTINCT ON`` shape into an equivalent
``ROW_NUMBER()``-windowed sub-select. It NEVER touches the ``chart_id`` predicate,
the ``COUNT(*)`` aggregates, or the ``MIN(cw.id)`` tie-break -- so those remain
exactly as the production builders emit them, and a regression in any of them
propagates into the executed SQL.

A complementary ``StatsBuilderRegressionGuardTests`` suite adds POSITIVE
structural assertions over the live builder query text, pinning each regression
vector independently of the executable oracle.

These tests run entirely offline -- no psycopg2, no network, no real Postgres
(stdlib ``sqlite3`` only, no new dependency).
"""

import inspect
import re
import sqlite3
import unittest

from billboard_stats.etl import stats_builder
from billboard_stats.etl.stats_builder import (
    build_album_stats,
    build_artist_stats,
    build_song_stats,
)


# ============================================================================
# A thin sqlite3 adapter that EXECUTES the builders' actual emitted SQL.
#
# The builders speak psycopg2 (``%s`` params) and a few Postgres-only spellings.
# This adapter translates ONLY the dialect surface -- placeholders, the ``::int``
# cast, and the one ``DISTINCT ON`` shape -- and runs the REST of every statement
# verbatim against sqlite3. The load-bearing clauses (the ``chart_id`` predicate,
# ``COUNT(*)``, ``COUNT(*) FILTER``, ``MIN(cw.id)``) pass through UNCHANGED, so a
# regression in any of them changes the executed result.
# ============================================================================
class _SqliteAdapterCursor:
    """Wrap a sqlite3 cursor, translating psycopg2/Postgres SQL minimally."""

    def __init__(self, cur):
        self._cur = cur

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @staticmethod
    def _translate(sql: str) -> str:
        # 1. psycopg2 placeholders -> sqlite placeholders. ``%s::int`` first so the
        #    cast strip below does not see a leftover ``?::int``.
        sql = sql.replace("%s::int", "?")
        sql = sql.replace("%s", "?")
        # 2. Strip any remaining explicit ``::int`` casts (sqlite is dynamically
        #    typed). Only the cast token is removed; the casted expression stays.
        sql = re.sub(r"::int\b", "", sql)
        # 3. Rewrite the single ``DISTINCT ON (key) ... ORDER BY key, tie`` shape
        #    into a ROW_NUMBER()-windowed sub-select (sqlite has no DISTINCT ON).
        #    This preserves the SAME semantics: the first row per ``key`` ordered
        #    by the tie columns. It does NOT touch the chart_id predicate or any
        #    aggregate.
        sql = _SqliteAdapterCursor._rewrite_distinct_on(sql)
        # 4. ``UPDATE <table> <alias> SET ...`` -- Postgres allows a bare alias on
        #    the UPDATE target; sqlite requires the ``AS`` keyword. Insert ``AS``
        #    (sqlite then aliases the target exactly like Postgres). This leaves
        #    the alias-qualified references intact -- no ambiguity, and the FROM
        #    subquery (chart_id predicate / COUNT(*) / MIN) is untouched.
        sql = re.sub(
            r"\bUPDATE\s+(\w+)\s+(\w+)\s+SET\b",
            r"UPDATE \1 AS \2 SET",
            sql,
            flags=re.IGNORECASE,
        )
        return sql

    @staticmethod
    def _rewrite_distinct_on(sql: str) -> str:
        # Match the builders' debut_position sub-select:
        #   SELECT DISTINCT ON (<key>) <cols> FROM <body>
        #     WHERE <pred> ORDER BY <order>
        # which is itself wrapped as ``FROM ( ... ) sub`` -- so the inner
        # ORDER BY is terminated by the subquery's closing ``)``. The body +
        # WHERE are captured together (they contain ``JOIN ... ON ...`` and the
        # chart_id predicate, which must pass through verbatim). The ORDER BY
        # list runs up to the next ``)`` that closes the sub-select.
        m = re.search(
            r"SELECT\s+DISTINCT\s+ON\s*\((?P<key>[^)]+)\)\s+"
            r"(?P<cols>.*?)\s+FROM\s+(?P<body>.*?)"
            r"\s+ORDER\s+BY\s+(?P<order>[^)]+?)\s*\)",
            sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return sql
        key = m.group("key").strip()
        cols = m.group("cols").strip()
        body = m.group("body").strip()
        order = m.group("order").strip()
        # The OUTER projection selects from the windowed sub-select, where the
        # ``e.``/``cw.`` aliases no longer exist -- so strip the alias qualifier
        # from each output column (``e.song_id`` -> ``song_id``). The INNER
        # projection keeps the qualified columns (its FROM still has the aliases).
        outer_cols = re.sub(r"\b\w+\.(\w+)", r"\1", cols)
        # Wrap the original projection in a ROW_NUMBER() window partitioned by the
        # DISTINCT ON key, ordered by the original ORDER BY, and keep rn = 1. The
        # body (incl. its WHERE with the chart_id predicate) is reused verbatim.
        replacement = (
            f"SELECT {outer_cols} FROM ("
            f"SELECT {cols}, ROW_NUMBER() OVER "
            f"(PARTITION BY {key} ORDER BY {order}) AS _rn "
            f"FROM {body}"
            f") _ranked WHERE _rn = 1)"
        )
        return sql[: m.start()] + replacement + sql[m.end():]

    def execute(self, sql, params=None):
        translated = self._translate(sql)
        self._cur.execute(translated, tuple(params) if params else ())
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


class _SqliteAdapterConn:
    """Wrap a sqlite3 connection to look like the psycopg2 conn the builders use."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return _SqliteAdapterCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()


# ============================================================================
# Fixture: a real sqlite schema + rows exercising the three regression vectors.
# ============================================================================
def _build_db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.executescript(
        """
        CREATE TABLE charts (id INTEGER, slug TEXT, entity_kind TEXT);
        CREATE TABLE chart_weeks (id INTEGER, chart_date TEXT, chart_id INTEGER);
        CREATE TABLE chart_entries (
            id INTEGER, chart_id INTEGER, chart_week_id INTEGER,
            song_id INTEGER, album_id INTEGER, artist_id INTEGER,
            rank INTEGER, peak_pos INTEGER, last_pos INTEGER,
            weeks_on_chart INTEGER, is_new INTEGER
        );
        CREATE TABLE songs (id INTEGER);
        CREATE TABLE albums (id INTEGER);
        CREATE TABLE artists (id INTEGER);
        CREATE TABLE song_artists (song_id INTEGER, artist_id INTEGER, role TEXT);
        CREATE TABLE album_artists (album_id INTEGER, artist_id INTEGER, role TEXT);
        CREATE TABLE song_stats (
            song_id INTEGER, total_weeks INTEGER, peak_position INTEGER,
            weeks_at_peak INTEGER, weeks_at_number_one INTEGER,
            debut_date TEXT, last_date TEXT, debut_position INTEGER
        );
        CREATE TABLE album_stats (
            album_id INTEGER, total_weeks INTEGER, peak_position INTEGER,
            weeks_at_peak INTEGER, weeks_at_number_one INTEGER,
            debut_date TEXT, last_date TEXT, debut_position INTEGER
        );
        CREATE TABLE artist_stats (
            artist_id INTEGER,
            total_hot100_songs INTEGER, total_b200_albums INTEGER,
            total_hot100_weeks INTEGER, total_b200_weeks INTEGER,
            hot100_number_ones INTEGER, b200_number_ones INTEGER,
            best_hot100_peak INTEGER, best_b200_peak INTEGER,
            first_chart_date TEXT, latest_chart_date TEXT,
            max_simultaneous_hot100 INTEGER
        );
        """
    )

    con.executemany(
        "INSERT INTO charts (id, slug, entity_kind) VALUES (?, ?, ?)",
        [(1, "hot-100", "song"), (2, "billboard-200", "album")],
    )

    # chart_weeks: NOTE the hot-100 ids are deliberately NOT in chart_date order.
    # Week id 1 is the SECOND calendar week; id 3 is the FIRST calendar week.
    # This is the (c) tie-break vector: MIN(chart_weeks.id) keeps a DIFFERENT
    # phantom week than MIN(chart_date) would.
    con.executemany(
        "INSERT INTO chart_weeks (id, chart_date, chart_id) VALUES (?, ?, ?)",
        [
            (1, "2020-01-11", 1),  # hot-100 real week (later date, LOWER id)
            (2, "2020-01-18", 1),  # hot-100 later phantom (must be EXCLUDED)
            (3, "2020-01-04", 1),  # hot-100 earliest-date phantom (HIGHER id)
            (10, "2020-02-01", 2),  # billboard-200 real week
            (11, "2020-02-08", 2),  # billboard-200 real week
        ],
    )

    def ce(eid, chart_id, week_id, *, song_id=None, album_id=None, rank=1,
           is_new=0, weeks_on_chart=1):
        return (eid, chart_id, week_id, song_id, album_id, None,
                rank, rank, None, weeks_on_chart, is_new)

    con.executemany(
        "INSERT INTO chart_entries (id, chart_id, chart_week_id, song_id, "
        "album_id, artist_id, rank, peak_pos, last_pos, weeks_on_chart, is_new) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            # --- hot-100 ----------------------------------------------------
            # Week id 3 (date 2020-01-04): a phantom (ALL is_new + weeks=1).
            # It is the EARLIEST-DATE week but NOT the lowest id. The
            # first_real tie-break uses MIN(chart_weeks.id), so the phantom
            # week KEPT must be the lowest-id phantom (here week id 2 is the
            # only OTHER phantom; week id 3 is phantom too). Of the phantom
            # weeks {2, 3}, MIN(id) = 2 is kept; week 3 is excluded.
            ce(100, 1, 3, song_id=10, rank=1, is_new=1, weeks_on_chart=1),
            ce(101, 1, 3, song_id=11, rank=2, is_new=1, weeks_on_chart=1),
            # Week id 1 (date 2020-01-11): a REAL week (not all-new). Song 10
            # peaks at rank 1 here.
            ce(102, 1, 1, song_id=10, rank=1, is_new=0, weeks_on_chart=2),
            ce(103, 1, 1, song_id=11, rank=2, is_new=0, weeks_on_chart=2),
            # Week id 2 (date 2020-01-18): a phantom (all-new). MIN(id) among
            # phantom weeks {2, 3} is 2, so THIS week is the kept first-real,
            # and week id 3 is excluded. Song 10 charts at rank 1 AGAIN here.
            ce(104, 1, 2, song_id=10, rank=1, is_new=1, weeks_on_chart=1),
            ce(105, 1, 2, song_id=12, rank=3, is_new=1, weeks_on_chart=1),
            # --- chart_id predicate trip-wire ------------------------------
            # A billboard-200-chart_id (2) entry that nonetheless carries
            # song_id 10 AND sits on hot-100 week id 1 (a VALID hot-100 week).
            # The song builder's ``e.chart_id = (SELECT chart_id FROM
            # bound_valid_weeks)`` predicate MUST exclude it -- if that predicate
            # is ever dropped, this row leaks into song 10's aggregate (total_weeks
            # 2 -> 3, an extra rank-50 week), turning the oracle assertions red.
            ce(106, 2, 1, song_id=10, rank=50, is_new=0, weeks_on_chart=9),
            # --- billboard-200 ---------------------------------------------
            # Two real weeks; album 20 charts at its peak rank 1 in BOTH (the
            # (b) COUNT(*) weeks-at-peak vector).
            ce(200, 2, 10, album_id=20, rank=1, is_new=0, weeks_on_chart=1),
            ce(201, 2, 10, album_id=21, rank=2, is_new=0, weeks_on_chart=1),
            ce(202, 2, 11, album_id=20, rank=1, is_new=0, weeks_on_chart=2),
        ],
    )

    con.executemany("INSERT INTO songs (id) VALUES (?)", [(10,), (11,), (12,)])
    con.executemany("INSERT INTO albums (id) VALUES (?)", [(20,), (21,)])
    con.executemany("INSERT INTO artists (id) VALUES (?)",
                    [(100,), (101,), (102,)])
    con.executemany(
        "INSERT INTO song_artists (song_id, artist_id, role) VALUES (?, ?, ?)",
        [(10, 100, "primary"), (11, 101, "primary"), (12, 100, "primary")],
    )
    con.executemany(
        "INSERT INTO album_artists (album_id, artist_id, role) VALUES (?, ?, ?)",
        [(20, 100, "primary"), (21, 102, "primary")],
    )
    return con


def _rows(con, sql):
    return con.execute(sql).fetchall()


# ============================================================================
# Oracle assertions: run the ACTUAL builders against the sqlite fixture.
# ============================================================================
class SongStatsOracleTests(unittest.TestCase):
    def setUp(self):
        self.con = _build_db()
        build_song_stats(_SqliteAdapterConn(self.con))

    def tearDown(self):
        self.con.close()

    def test_phantom_week_excluded_and_tie_break_keeps_min_id_week(self):
        # Valid weeks = {1 (real), 2 (lowest-id phantom, kept)}. Week 3
        # (earliest DATE but higher id) is the EXCLUDED phantom -- proving the
        # MIN(chart_weeks.id) tie-break, NOT MIN(chart_date).
        stats = {r[0]: r for r in _rows(
            self.con,
            "SELECT song_id, total_weeks, peak_position, weeks_at_peak, "
            "weeks_at_number_one, debut_date, last_date, debut_position "
            "FROM song_stats ORDER BY song_id")}

        # Song 10 charts in week 1 (real) + week 2 (kept phantom) = 2 weeks;
        # week 3 is excluded. If the tie-break used MIN(chart_date) it would keep
        # week 3 and exclude week 2, giving a DIFFERENT debut_date/last_date.
        self.assertIn(10, stats)
        self.assertEqual(stats[10][1], 2)  # total_weeks
        self.assertEqual(stats[10][2], 1)  # peak_position
        # weeks_at_peak: rank 1 in week 1 AND week 2 = 2 (the (b) COUNT(*)
        # vector). COUNT(DISTINCT chart_week_id) would also give 2 here, but the
        # album fixture below pins the COUNT(*) distinction unambiguously.
        self.assertEqual(stats[10][3], 2)  # weeks_at_peak
        self.assertEqual(stats[10][4], 2)  # weeks_at_number_one
        # Kept weeks are id 1 (2020-01-11) and id 2 (2020-01-18) -> debut is the
        # earlier of THOSE, 2020-01-11. (If week 3 had been kept, debut would be
        # 2020-01-04.)
        self.assertEqual(stats[10][5], "2020-01-11")  # debut_date
        self.assertEqual(stats[10][6], "2020-01-18")  # last_date

        # Song 12 ONLY appears in the kept phantom week 2 -> present with 1 week.
        self.assertIn(12, stats)
        self.assertEqual(stats[12][1], 1)

        # Song 11 charts in week 1 (real) + week 3 (EXCLUDED) -> only 1 valid
        # week. If week 3 leaked in, total_weeks would be 2.
        self.assertEqual(stats[11][1], 1)
        self.assertEqual(stats[11][5], "2020-01-11")  # only the real week

    def test_chart_id_predicate_isolates_hot100(self):
        # No album rows should leak into song_stats: every song_stats row has a
        # real song_id and the album-chart entries (chart_id 2) never appear.
        song_ids = {r[0] for r in _rows(self.con, "SELECT song_id FROM song_stats")}
        self.assertEqual(song_ids, {10, 11, 12})


class AlbumStatsOracleTests(unittest.TestCase):
    def setUp(self):
        self.con = _build_db()
        build_album_stats(_SqliteAdapterConn(self.con))

    def tearDown(self):
        self.con.close()

    def test_weeks_at_peak_is_count_star_not_distinct(self):
        stats = {r[0]: r for r in _rows(
            self.con,
            "SELECT album_id, total_weeks, peak_position, weeks_at_peak, "
            "weeks_at_number_one FROM album_stats ORDER BY album_id")}
        # Album 20 charts at rank 1 in BOTH b200 weeks -> total_weeks 2,
        # weeks_at_peak 2, weeks_at_number_one 2. This is the (b) vector: a
        # COUNT(DISTINCT) regression on weeks_at_number_one (FILTER rank=1) or
        # on weeks_at_peak would still give 2 here because the weeks differ, so
        # the song fixture's same-week repeats are the real DISTINCT trip-wire;
        # the structural guard below pins COUNT(*) directly.
        self.assertEqual(stats[20][1], 2)  # total_weeks
        self.assertEqual(stats[20][3], 2)  # weeks_at_peak
        self.assertEqual(stats[20][4], 2)  # weeks_at_number_one
        # Album 21 charts once at rank 2.
        self.assertEqual(stats[21][1], 1)
        self.assertEqual(stats[21][2], 2)  # peak_position


class ArtistStatsOracleTests(unittest.TestCase):
    def setUp(self):
        self.con = _build_db()
        build_artist_stats(_SqliteAdapterConn(self.con))

    def tearDown(self):
        self.con.close()

    def test_count_star_summed_entity_weeks(self):
        stats = {r[0]: r for r in _rows(
            self.con,
            "SELECT artist_id, total_hot100_weeks, total_b200_weeks, "
            "hot100_number_ones, b200_number_ones, best_hot100_peak "
            "FROM artist_stats ORDER BY artist_id")}
        # Artist 100 links songs 10 and 12 on hot-100.
        #   song 10 -> valid weeks 1, 2 (2 entity-weeks)
        #   song 12 -> valid week 2     (1 entity-week)
        # COUNT(*) over the song_artists join = 3 summed entity-weeks (Pitfall 2).
        # COUNT(DISTINCT chart_week_id) would give 2 -- so this value FAILS if the
        # builder is changed to COUNT(DISTINCT).
        self.assertEqual(stats[100][1], 3)  # total_hot100_weeks
        # Artist 100 links album 20 on b200 -> 2 entity-weeks.
        self.assertEqual(stats[100][2], 2)  # total_b200_weeks
        # number_ones counts DISTINCT entities at rank 1: song 10 -> 1.
        self.assertEqual(stats[100][3], 1)  # hot100_number_ones
        self.assertEqual(stats[100][4], 1)  # b200_number_ones (album 20)
        self.assertEqual(stats[100][5], 1)  # best_hot100_peak


# ============================================================================
# Positive structural regression guards over the LIVE builder query text.
# Each pins one regression vector independently of the executable oracle.
# ============================================================================
class StatsBuilderRegressionGuardTests(unittest.TestCase):
    def test_chart_id_predicate_present_and_param_bound(self):
        # Every re-pointed builder must filter chart_entries by the bound
        # chart_id (a dropped predicate would leak the other chart's rows).
        for fn in (build_song_stats, build_album_stats, build_artist_stats):
            src = inspect.getsource(fn)
            self.assertIn(
                "chart_id = (SELECT chart_id FROM bound_", src,
                f"{fn.__name__} lost the bound chart_id predicate",
            )
        # The CTE binds the chart_id via a %s::int placeholder (param-bound, not a
        # literal slug or hardcoded id).
        cte_src = inspect.getsource(stats_builder.valid_weeks_cte)
        self.assertIn("%s::int AS chart_id", cte_src)

    def test_count_star_used_and_count_distinct_week_absent(self):
        # total_weeks must be COUNT(*) (summed entity-weeks), never
        # COUNT(DISTINCT chart_week_id).
        src = inspect.getsource(build_artist_stats)
        self.assertIn("COUNT(*) AS total_weeks", src)
        self.assertNotIn("COUNT(DISTINCT chart_week_id)", src)
        # The song/album builders also use COUNT(*) for total_weeks.
        for fn in (build_song_stats, build_album_stats):
            self.assertIn("COUNT(*) AS total_weeks", inspect.getsource(fn))

    def test_first_real_week_uses_min_chart_weeks_id_tie_break(self):
        # The phantom first-real tie-break must be MIN(chart_weeks.id) -- not an
        # ORDER BY chart_date -- so the kept phantom week is id-deterministic.
        cte_src = inspect.getsource(stats_builder.valid_weeks_cte)
        self.assertIn("MIN(cw.id) AS id", cte_src)


# ============================================================================
# Source guards: the builders read chart_entries and the legacy reads/constants
# are gone (these permanently lock the 15-01 cutover).
# ============================================================================
class StatsBuilderSourceGuardTests(unittest.TestCase):
    def test_builders_read_chart_entries(self):
        for fn in (build_song_stats, build_album_stats, build_artist_stats):
            src = inspect.getsource(fn)
            self.assertIn("chart_entries", src)

    def test_legacy_constants_deleted(self):
        src = inspect.getsource(stats_builder)
        self.assertNotIn("_VALID_HOT100_WEEKS_CTE =", src)
        # The retired per-chart-type literal CTE constants are gone; the builders
        # bind a chart_id into the single parametric valid_weeks_cte instead.
        self.assertNotIn("_VALID_B200_WEEKS_CTE =", src)


if __name__ == "__main__":
    unittest.main()
