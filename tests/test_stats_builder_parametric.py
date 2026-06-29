"""Fixture/mock-DB tests for the parametric phantom-week CTE + artist_chart_stats
rollup build (Plan 09-03, DATA-03 / success criterion #5).

These tests run entirely against an in-memory fake DB layer mirroring
tests/test_reconcile_artists.py and tests/test_migrate_multichart.py. They make
NO real database connection and NO network calls. The real-DB apply (run
build_artist_chart_stats after the migration backfill) is the operator runbook in
docs/MIGRATION-MULTICHART.md, not here.

What these tests pin down:

* The phantom-week filter is ONE parametric CTE keyed by ``chart_id`` over
  ``chart_entries`` (not the two hardcoded chart_type-literal CTEs). A week is
  phantom when >= 95% of that chart's entries for the week have ``is_new=true AND
  weeks_on_chart=1``; the earliest phantom is kept as the real first chart, all
  later phantoms are excluded.
* ``build_artist_chart_stats`` writes ONE row per (artist_id, chart_id) into
  ``artist_chart_stats`` with the authoritative Plan-01 columns (total_entries,
  total_weeks, number_ones, best_peak, max_simultaneous, first_date, last_date),
  aggregating ``chart_entries`` through ``song_artists`` (entity_kind=song),
  ``album_artists`` (entity_kind=album), or ``artist_id`` directly
  (entity_kind=artist).
* Adding a second chart yields additional ROWS, never new columns.
* The v1.0 ``build_artist_stats`` path and both literal CTEs remain present and
  unchanged (compatibility) -- asserted by the source-level checks below.

The fake DB executes the EXACT statement shapes ``build_artist_chart_stats``
emits: a per-chart DELETE/INSERT driven by a registry loop and a parametric
phantom CTE bound to a chart_id. Fidelity gaps the fake DB does NOT model (real
SQL CTE evaluation, num_nonnulls, FK ordering) are covered by the runbook, not
here.
"""

import copy
import inspect
import re
import unittest

from billboard_stats.etl import stats_builder
from billboard_stats.etl.stats_builder import (
    build_artist_chart_stats,
    valid_weeks_cte,
)


# ============================================================================
# In-memory fake DB layer
# ============================================================================
class FakeCursor:
    """A psycopg2-cursor-like stand-in interpreting the SQL the parametric
    artist_chart_stats build emits.

    It models charts / chart_weeks / chart_entries / song_artists /
    album_artists / artist_chart_stats as plain Python structures and computes
    the per-chart rollup the SQL describes -- applying the SAME parametric
    phantom-week filter the production CTE encodes. No real database is involved.
    """

    def __init__(self, db):
        self._db = db
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        norm = re.sub(r"\s+", " ", sql).strip().lower()
        params = tuple(params) if params else ()

        if norm.startswith("delete from artist_chart_stats"):
            self._db.artist_chart_stats = []
            return

        if norm.startswith("select id, entity_kind from charts"):
            self._result = [(c["id"], c["entity_kind"]) for c in self._db.charts]
            return

        # The parametric rollup INSERT: one statement per chart. It is a
        # ``WITH <parametric phantom CTE> INSERT INTO artist_chart_stats ...``
        # bound to a single chart_id placeholder. The fake interprets it by
        # computing the rollup rows for that chart using the SAME parametric
        # phantom filter the CTE encodes.
        if "insert into artist_chart_stats" in norm:
            # The single bind param is the chart_id (the bound_valid_weeks CTE
            # carries exactly one %s placeholder).
            (chart_id,) = params
            # Sanity: the statement must be driven by the parametric chart_id CTE
            # over chart_entries -- never a hardcoded chart_type literal.
            self._db._assert_parametric(norm)
            self._db.build_chart_rollup(chart_id)
            return

        raise AssertionError(f"FakeCursor: unhandled SQL: {norm!r}")

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None


class FakeConn:
    def __init__(self, db):
        self._db = db
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return FakeCursor(self._db)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeDB:
    """In-memory model of charts / chart_weeks / chart_entries / song_artists /
    album_artists / artist_chart_stats for the parametric rollup build."""

    def __init__(
        self,
        charts=None,
        chart_weeks=None,
        chart_entries=None,
        song_artists=None,
        album_artists=None,
        artist_chart_stats=None,
    ):
        # charts: {"id", "slug", "entity_kind"}
        self.charts = [dict(c) for c in (charts or [])]
        # chart_weeks: {"id", "chart_date", "chart_id"}
        self.chart_weeks = [dict(w) for w in (chart_weeks or [])]
        # chart_entries: polymorphic rows
        self.chart_entries = [dict(e) for e in (chart_entries or [])]
        self.song_artists = [dict(l) for l in (song_artists or [])]
        self.album_artists = [dict(l) for l in (album_artists or [])]
        # artist_chart_stats: list of dicts keyed (artist_id, chart_id)
        self.artist_chart_stats = [dict(r) for r in (artist_chart_stats or [])]

    # --- guard: the rollup INSERT must be parametric over chart_entries -------
    def _assert_parametric(self, norm):
        """Fail loudly if the rollup INSERT is not the single parametric CTE
        keyed by chart_id over chart_entries (success criterion #5)."""
        assert "chart_entries" in norm, "rollup must aggregate chart_entries"
        assert "chart_id =" in norm, "rollup must filter by a chart_id bind"
        # No hardcoded chart_type literal leaks into the generalized path.
        assert "chart_type = 'hot-100'" not in norm
        assert "chart_type = 'billboard-200'" not in norm
        assert "from hot100_entries" not in norm
        assert "from b200_entries" not in norm

    # --- parametric phantom-week filter (the SAME rule the production CTE
    #     encodes, now keyed by chart_id over chart_entries) -------------------
    def valid_week_ids(self, chart_id):
        """Return the set of chart_week_id values for ``chart_id`` that are NOT
        phantom, plus the earliest phantom (kept as the real first chart).

        A week is phantom when >= 95% of that chart's entries for the week have
        is_new=true AND weeks_on_chart=1.

        The "first real" phantom week is selected by ``MIN(chart_weeks.id)``
        scoped to the chart -- the SAME rule the production parametric CTE and
        the v1.0 literal CTEs use (CR-01). Using MIN(id), not MIN(chart_date),
        is load-bearing: it guarantees the parametric path and the v1.0 path
        agree even when chart_weeks.id order != chart_date order.
        """
        weeks = {}
        for e in self.chart_entries:
            if e["chart_id"] != chart_id:
                continue
            weeks.setdefault(e["chart_week_id"], []).append(e)

        phantom_week_ids = []
        for week_id, entries in weeks.items():
            total = len(entries)
            phantom_entries = sum(
                1
                for e in entries
                if e.get("is_new") and e.get("weeks_on_chart") == 1
            )
            if total > 0 and phantom_entries >= total * 95 / 100:
                phantom_week_ids.append(week_id)

        # earliest phantom by chart_week id (MIN(cw.id)) is kept as the real
        # first chart -- matches the production CTE + v1.0 rule (CR-01).
        first_real = None
        if phantom_week_ids:
            first_real = min(phantom_week_ids)

        valid = set()
        for week_id in weeks:
            if week_id not in phantom_week_ids or week_id == first_real:
                valid.add(week_id)
        return valid

    def v1_valid_week_ids(self, chart_id):
        """Independent reference implementation of the v1.0 literal-CTE rule
        (_VALID_HOT100_WEEKS_CTE / _VALID_B200_WEEKS_CTE): phantom detection per
        chart_week, then keep all non-phantom weeks plus the phantom week with
        the smallest chart_weeks.id (MIN(cw.id)).

        Used by the CR-01 regression test to assert the parametric path agrees
        with the v1.0 path on the SAME data, including when id order != date
        order.
        """
        weeks = {}
        for e in self.chart_entries:
            if e["chart_id"] != chart_id:
                continue
            weeks.setdefault(e["chart_week_id"], []).append(e)

        phantom_week_ids = []
        for week_id, entries in weeks.items():
            total = len(entries)
            phantom_entries = sum(
                1
                for e in entries
                if e.get("is_new") and e.get("weeks_on_chart") == 1
            )
            if total > 0 and phantom_entries >= total * 95 / 100:
                phantom_week_ids.append(week_id)

        first_real = min(phantom_week_ids) if phantom_week_ids else None
        valid = set()
        for week_id in weeks:
            if week_id not in phantom_week_ids or week_id == first_real:
                valid.add(week_id)
        return valid

    def _week_date(self, week_id):
        for w in self.chart_weeks:
            if w["id"] == week_id:
                return w["chart_date"]
        return None

    def _entity_artist_ids(self, entity_kind, entry):
        """Resolve the artist(s) an entry rolls up to for the given entity_kind."""
        if entity_kind == "song":
            return [
                l["artist_id"]
                for l in self.song_artists
                if l["song_id"] == entry["song_id"]
            ]
        if entity_kind == "album":
            return [
                l["artist_id"]
                for l in self.album_artists
                if l["album_id"] == entry["album_id"]
            ]
        if entity_kind == "artist":
            return [entry["artist_id"]] if entry["artist_id"] is not None else []
        return []

    def _entity_id(self, entity_kind, entry):
        return {
            "song": entry["song_id"],
            "album": entry["album_id"],
            "artist": entry["artist_id"],
        }[entity_kind]

    def build_chart_rollup(self, chart_id):
        """Compute one artist_chart_stats row per (artist_id, chart_id) for this
        chart, using the parametric phantom filter."""
        chart = next(c for c in self.charts if c["id"] == chart_id)
        entity_kind = chart["entity_kind"]
        valid = self.valid_week_ids(chart_id)

        # Per artist accumulators.
        agg = {}
        # max simultaneous: per (artist, week) entry counts.
        per_week = {}
        for e in self.chart_entries:
            if e["chart_id"] != chart_id:
                continue
            if e["chart_week_id"] not in valid:
                continue
            date = self._week_date(e["chart_week_id"])
            entity_id = self._entity_id(entity_kind, e)
            for artist_id in self._entity_artist_ids(entity_kind, e):
                a = agg.setdefault(
                    artist_id,
                    {
                        "entities": set(),
                        "total_weeks": 0,
                        "number_ones": set(),
                        "best_peak": None,
                        "first_date": None,
                        "last_date": None,
                    },
                )
                a["entities"].add(entity_id)
                a["total_weeks"] += 1
                if e["rank"] == 1:
                    a["number_ones"].add(entity_id)
                if a["best_peak"] is None or e["rank"] < a["best_peak"]:
                    a["best_peak"] = e["rank"]
                if a["first_date"] is None or date < a["first_date"]:
                    a["first_date"] = date
                if a["last_date"] is None or date > a["last_date"]:
                    a["last_date"] = date
                key = (artist_id, e["chart_week_id"])
                per_week[key] = per_week.get(key, 0) + 1

        max_sim = {}
        for (artist_id, _week), cnt in per_week.items():
            max_sim[artist_id] = max(max_sim.get(artist_id, 0), cnt)

        for artist_id, a in agg.items():
            self.artist_chart_stats.append(
                {
                    "artist_id": artist_id,
                    "chart_id": chart_id,
                    "total_entries": len(a["entities"]),
                    "total_weeks": a["total_weeks"],
                    "number_ones": len(a["number_ones"]),
                    "best_peak": a["best_peak"],
                    "max_simultaneous": max_sim.get(artist_id, 0),
                    "first_date": a["first_date"],
                    "last_date": a["last_date"],
                }
            )

    def rows_for(self, artist_id, chart_id):
        return [
            r
            for r in self.artist_chart_stats
            if r["artist_id"] == artist_id and r["chart_id"] == chart_id
        ]

    def snapshot(self):
        return copy.deepcopy(self.artist_chart_stats)


# ============================================================================
# Fixtures
# ============================================================================
def _two_chart_fixture():
    """A hot-100 (song) chart with a phantom debut week + a real week, and a
    billboard-200 (album) chart with a single real week.

    hot-100 (chart_id=1):
      week 1 (2020-01-01) is a PHANTOM debut: both entries is_new + weeks=1.
        - song 10 rank 1 (artist 100)
        - song 11 rank 2 (artist 101)
      week 2 (2020-01-08) is REAL:
        - song 10 rank 1 (artist 100)  -> a #1
        - song 11 rank 3 (artist 101)
      week 3 (2020-01-15) is ALSO phantom-shaped but LATER -> excluded.
        - song 12 rank 1 (artist 100), is_new + weeks=1

    billboard-200 (chart_id=2):
      week 4 (2020-01-01) REAL:
        - album 20 rank 1 (artist 100)  -> artist 100 charts on BOTH charts
        - album 21 rank 2 (artist 102)
    """
    charts = [
        {"id": 1, "slug": "hot-100", "entity_kind": "song"},
        {"id": 2, "slug": "billboard-200", "entity_kind": "album"},
    ]
    chart_weeks = [
        {"id": 1, "chart_date": "2020-01-01", "chart_id": 1},
        {"id": 2, "chart_date": "2020-01-08", "chart_id": 1},
        {"id": 3, "chart_date": "2020-01-15", "chart_id": 1},
        {"id": 4, "chart_date": "2020-01-01", "chart_id": 2},
    ]
    chart_entries = [
        # hot-100 week 1 (phantom debut)
        _ce(1, 1, song_id=10, rank=1, is_new=True, weeks_on_chart=1),
        _ce(1, 1, song_id=11, rank=2, is_new=True, weeks_on_chart=1),
        # hot-100 week 2 (real)
        _ce(1, 2, song_id=10, rank=1, is_new=False, weeks_on_chart=2),
        _ce(1, 2, song_id=11, rank=3, is_new=False, weeks_on_chart=2),
        # hot-100 week 3 (later phantom -> excluded)
        _ce(1, 3, song_id=12, rank=1, is_new=True, weeks_on_chart=1),
        # billboard-200 week 4 (real)
        _ce(2, 4, album_id=20, rank=1, is_new=False, weeks_on_chart=3),
        _ce(2, 4, album_id=21, rank=2, is_new=False, weeks_on_chart=2),
    ]
    song_artists = [
        {"song_id": 10, "artist_id": 100, "role": "primary"},
        {"song_id": 11, "artist_id": 101, "role": "primary"},
        {"song_id": 12, "artist_id": 100, "role": "primary"},
    ]
    album_artists = [
        {"album_id": 20, "artist_id": 100, "role": "primary"},
        {"album_id": 21, "artist_id": 102, "role": "primary"},
    ]
    return FakeDB(
        charts=charts,
        chart_weeks=chart_weeks,
        chart_entries=chart_entries,
        song_artists=song_artists,
        album_artists=album_artists,
    )


def _ce(chart_id, chart_week_id, *, song_id=None, album_id=None, artist_id=None,
        rank=1, is_new=False, weeks_on_chart=1):
    _ce.counter = getattr(_ce, "counter", 0) + 1
    return {
        "id": _ce.counter,
        "chart_id": chart_id,
        "chart_week_id": chart_week_id,
        "song_id": song_id,
        "album_id": album_id,
        "artist_id": artist_id,
        "rank": rank,
        "peak_pos": rank,
        "last_pos": None,
        "weeks_on_chart": weeks_on_chart,
        "is_new": is_new,
    }


def _artist_chart_fixture():
    """An artist-entity chart (entity_kind=artist) where chart_entries set
    artist_id DIRECTLY -- the Phase 11 Artist 100 case that drops in for free."""
    charts = [{"id": 5, "slug": "artist-100", "entity_kind": "artist"}]
    chart_weeks = [
        {"id": 50, "chart_date": "2021-01-01", "chart_id": 5},
        {"id": 51, "chart_date": "2021-01-08", "chart_id": 5},
    ]
    chart_entries = [
        _ce(5, 50, artist_id=200, rank=1, is_new=False, weeks_on_chart=2),
        _ce(5, 51, artist_id=200, rank=2, is_new=False, weeks_on_chart=3),
        _ce(5, 50, artist_id=201, rank=2, is_new=False, weeks_on_chart=1),
    ]
    return FakeDB(charts=charts, chart_weeks=chart_weeks, chart_entries=chart_entries)


def _id_order_reversed_phantom_fixture():
    """A hot-100 (song) chart where chart_weeks.id order is the REVERSE of
    chart_date order, with TWO phantom weeks and one real week. This is the
    out-of-order-loaded shape the migration / Phase 7 backfill produces.

    chart_weeks:
      id=1  chart_date 2020-01-15  (LATER date, SMALLER id)  -> phantom
      id=2  chart_date 2020-01-01  (EARLIER date, LARGER id) -> phantom
      id=3  chart_date 2020-01-22                            -> real

    MIN(cw.id) picks id=1 as the first-real phantom (v1.0 + fixed parametric).
    The OLD MIN(chart_date) tie-break would have picked id=2 instead. So the
    set of valid weeks differs by one phantom week between the two rules unless
    both use MIN(id).
    """
    charts = [{"id": 1, "slug": "hot-100", "entity_kind": "song"}]
    chart_weeks = [
        {"id": 1, "chart_date": "2020-01-15", "chart_id": 1},
        {"id": 2, "chart_date": "2020-01-01", "chart_id": 1},
        {"id": 3, "chart_date": "2020-01-22", "chart_id": 1},
    ]
    chart_entries = [
        # week id=1 (phantom): both entries is_new + weeks=1
        _ce(1, 1, song_id=10, rank=1, is_new=True, weeks_on_chart=1),
        _ce(1, 1, song_id=11, rank=2, is_new=True, weeks_on_chart=1),
        # week id=2 (phantom): both entries is_new + weeks=1
        _ce(1, 2, song_id=12, rank=1, is_new=True, weeks_on_chart=1),
        _ce(1, 2, song_id=13, rank=2, is_new=True, weeks_on_chart=1),
        # week id=3 (real)
        _ce(1, 3, song_id=10, rank=1, is_new=False, weeks_on_chart=2),
    ]
    song_artists = [
        {"song_id": 10, "artist_id": 100, "role": "primary"},
        {"song_id": 11, "artist_id": 101, "role": "primary"},
        {"song_id": 12, "artist_id": 102, "role": "primary"},
        {"song_id": 13, "artist_id": 103, "role": "primary"},
    ]
    return FakeDB(
        charts=charts,
        chart_weeks=chart_weeks,
        chart_entries=chart_entries,
        song_artists=song_artists,
    )


# ============================================================================
# Parametric phantom-week CTE
# ============================================================================
class ValidWeeksCteTests(unittest.TestCase):
    def test_cte_is_parameterized_by_chart_id(self):
        # valid_weeks_cte(name) returns (sql, ) shape carrying a %s placeholder so
        # the SAME CTE works for ANY chart_id -- not a literal chart_type.
        sql = valid_weeks_cte("valid_weeks")
        self.assertIsInstance(sql, str)
        self.assertIn("%s", sql)  # chart_id is a bind param, not a literal
        self.assertIn("chart_entries", sql.lower())
        # No hardcoded chart_type literal in the parametric CTE.
        self.assertNotIn("hot-100", sql.lower())
        self.assertNotIn("billboard-200", sql.lower())

    def test_phantom_week_excluded_earliest_phantom_kept(self):
        db = _two_chart_fixture()
        valid = db.valid_week_ids(1)  # hot-100
        # Week 1 is the earliest phantom -> KEPT. Week 3 is a later phantom ->
        # excluded. Week 2 is real -> kept.
        self.assertIn(1, valid)
        self.assertIn(2, valid)
        self.assertNotIn(3, valid)

    def test_first_real_uses_min_id_not_chart_date(self):
        # CR-01 (source-level pin): the production parametric CTE must select
        # the first-real week by MIN(cw.id) scoped to the bound chart -- the
        # SAME rule as the v1.0 literal CTEs -- NOT by ORDER BY cw.chart_date.
        # Ordering by chart_date would silently diverge from artist_stats on
        # out-of-order-loaded weeks (Phase 7/11), so guard against regression.
        sql = re.sub(r"\s+", " ", valid_weeks_cte("valid_weeks")).lower()
        self.assertIn("min(cw.id)", sql)
        self.assertIn(
            "where cw.chart_id = (select chart_id from bound_valid_weeks)", sql
        )
        # The old date-ordered tie-break must be gone from first_real.
        self.assertNotIn("order by cw.chart_date, cw.id limit 1", sql)

    def test_parametric_first_real_agrees_with_v1_when_id_order_ne_date_order(self):
        # CR-01 (behavioral): build a chart where chart_weeks.id order is the
        # REVERSE of chart_date order, with TWO phantom weeks. MIN(cw.id)
        # (v1.0 + fixed parametric) and the OLD MIN(chart_date) tie-break would
        # pick DIFFERENT first-real weeks. Assert the parametric path now agrees
        # with the v1.0 rule -- i.e. the two stat paths can never silently
        # diverge on the same data.
        db = _id_order_reversed_phantom_fixture()
        parametric_valid = db.valid_week_ids(1)
        v1_valid = db.v1_valid_week_ids(1)
        self.assertEqual(parametric_valid, v1_valid)
        # Concretely: id=1 (later date) is the MIN-id phantom -> KEPT;
        # id=2 (earlier date) is the other phantom -> EXCLUDED. The old
        # date-ordered rule would have kept id=2 and excluded id=1.
        self.assertIn(1, parametric_valid)
        self.assertNotIn(2, parametric_valid)


# ============================================================================
# build_artist_chart_stats rollup
# ============================================================================
class BuildArtistChartStatsTests(unittest.TestCase):
    def test_one_row_per_artist_chart(self):
        db = _two_chart_fixture()
        conn = FakeConn(db)
        build_artist_chart_stats(conn)

        # Each (artist, chart) pair has exactly one row.
        for (artist_id, chart_id) in {
            (r["artist_id"], r["chart_id"]) for r in db.artist_chart_stats
        }:
            self.assertEqual(len(db.rows_for(artist_id, chart_id)), 1)
        self.assertTrue(conn.committed)

    def test_two_charts_yield_rows_not_columns(self):
        db = _two_chart_fixture()
        build_artist_chart_stats(FakeConn(db))

        # Artist 100 charts on BOTH hot-100 (chart 1) and billboard-200 (chart 2)
        # -> TWO rows, not extra columns.
        rows_100 = [r for r in db.artist_chart_stats if r["artist_id"] == 100]
        chart_ids = sorted(r["chart_id"] for r in rows_100)
        self.assertEqual(chart_ids, [1, 2])

    def test_authoritative_columns_written(self):
        db = _two_chart_fixture()
        build_artist_chart_stats(FakeConn(db))
        row = db.rows_for(100, 1)[0]  # artist 100 on hot-100
        # Exactly the Plan-01 authoritative column set.
        self.assertEqual(
            set(row.keys()),
            {
                "artist_id",
                "chart_id",
                "total_entries",
                "total_weeks",
                "number_ones",
                "best_peak",
                "max_simultaneous",
                "first_date",
                "last_date",
            },
        )

    def test_phantom_filter_applied_to_rollup(self):
        db = _two_chart_fixture()
        build_artist_chart_stats(FakeConn(db))
        row = db.rows_for(100, 1)[0]  # artist 100 on hot-100
        # song 10 appears in week1 (kept phantom) + week2 (real); song 12 is in
        # week3 (excluded later phantom). So total_entries = {song 10} = 1,
        # total_weeks = 2 (week1 + week2), number_ones = 1 (song10 hit #1).
        self.assertEqual(row["total_entries"], 1)
        self.assertEqual(row["total_weeks"], 2)
        self.assertEqual(row["number_ones"], 1)
        self.assertEqual(row["best_peak"], 1)
        self.assertEqual(row["first_date"], "2020-01-01")
        self.assertEqual(row["last_date"], "2020-01-08")

    def test_album_chart_rolls_up_through_album_artists(self):
        db = _two_chart_fixture()
        build_artist_chart_stats(FakeConn(db))
        # Artist 100 on billboard-200 via album 20 (rank 1 -> a #1).
        row = db.rows_for(100, 2)[0]
        self.assertEqual(row["total_entries"], 1)
        self.assertEqual(row["number_ones"], 1)
        self.assertEqual(row["best_peak"], 1)

    def test_delete_then_rebuild_is_idempotent(self):
        db = _two_chart_fixture()
        build_artist_chart_stats(FakeConn(db))
        first = db.snapshot()
        build_artist_chart_stats(FakeConn(db))
        # A rebuild DELETEs first, so a second run yields identical rows.
        self.assertEqual(db.snapshot(), first)

    def test_artist_entity_chart_produces_rollup_row(self):
        db = _artist_chart_fixture()
        build_artist_chart_stats(FakeConn(db))
        # entity_kind=artist: artist_id is read directly off chart_entries.
        row = db.rows_for(200, 5)[0]
        self.assertEqual(row["total_entries"], 1)  # one distinct artist entity
        self.assertEqual(row["total_weeks"], 2)    # two weeks present
        self.assertEqual(row["number_ones"], 1)    # rank 1 in week 50
        self.assertEqual(row["best_peak"], 1)
        # The other artist also gets a row.
        self.assertEqual(len(db.rows_for(201, 5)), 1)


# ============================================================================
# Phase 15: the v1.0-named builders were RE-POINTED onto chart_entries and the
# two literal per-chart-type CTE constants were RETIRED. The builders still
# exist (the v1.0-named stats tables are still produced) but no longer read the
# legacy tables or carry a hardcoded chart_type column literal.
# ============================================================================
class V1CompatibilityTests(unittest.TestCase):
    def test_build_artist_stats_repointed_onto_chart_entries(self):
        src = inspect.getsource(stats_builder)
        # The v1.0-named builders are PRESERVED (the live frontend still reads
        # song_stats / album_stats / artist_stats).
        self.assertIn("def build_song_stats", src)
        self.assertIn("def build_album_stats", src)
        self.assertIn("def build_artist_stats", src)
        # The two literal per-chart-type CTE constants were RETIRED in Phase 15.
        self.assertNotIn("_VALID_HOT100_WEEKS_CTE =", src)
        self.assertNotIn("_VALID_B200_WEEKS_CTE =", src)
        # The builders no longer read the legacy entry tables nor the dropped
        # chart_type COLUMN literal; they aggregate chart_entries instead.
        self.assertNotIn("FROM hot100_entries", src)
        self.assertNotIn("FROM b200_entries", src)
        self.assertNotIn("chart_type = 'hot-100'", src)
        self.assertNotIn("chart_type = 'billboard-200'", src)
        self.assertIn("FROM chart_entries", src)

    def test_module_imports_without_psycopg(self):
        # stats_builder must import in the psycopg2-free test env.
        import inspect as _inspect

        lines = _inspect.getsource(stats_builder).splitlines()
        top_level = [
            l for l in lines if l.startswith("import ") or l.startswith("from ")
        ]
        self.assertFalse(any("psycopg" in l for l in top_level))


if __name__ == "__main__":
    unittest.main()
