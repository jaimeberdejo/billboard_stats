"""Equivalence fixture/diff tests for the registry load path (Plan 10-02).

DATA-06 success criterion #3, expressed as a fixture diff with NO production DB
and NO network. These tests drive the registry-driven ``load_chart`` over a
FIXED fixture corpus of hot-100 + billboard-200 weeks and prove the new
polymorphic ``chart_entries`` rows are row-count AND content identical to the
dual-written legacy ``hot100_entries`` / ``b200_entries`` rows -- i.e. the new
path and the legacy path it feeds agree row-for-row, so the dual-write can never
silently diverge (threat T-10-04).

The assertions mirror migrate_multichart's WR-03 parity: a two-way anti-join on
``(chart_week_id, rank, entity_id)`` for each legacy chart, the one-FK-per-row
polymorphism guard (T-10-05), song_artists / album_artists link parity (W1 --
the unified artist_cache must produce the same links the v1.0 path did), and a
guard that a NEW chart (legacy_table=None) writes ZERO legacy rows (T-10-06: the
legacy tables are touched ONLY for the two legacy charts).

The loader is driven over the parsed-entry fixture by reusing the fake DB and
harness from tests/test_loader_registry.py, so the loader exercises the REAL
per-entry path (entity upsert, artist links, dual-write).
"""

import unittest

from billboard_stats.etl.chart_registry import ChartRecord

from tests.test_loader_registry import (
    FakeDB,
    _load,
)


# ============================================================================
# Fixed equivalence corpus (2 hot-100 weeks + 1 b200 week, shared artist)
# ============================================================================
# A couple of hot-100 weeks and a billboard-200 week, mirroring
# test_migrate_multichart._fixture. Artist "Alpha" charts on BOTH charts so the
# W1 link parity is exercised across two loads sharing one artist_cache.
_HOT100_WEEK_1 = [
    {"rank": 1, "title": "Song Alpha", "artist": "Alpha", "peak_pos": 1,
     "last_pos": 2, "weeks": 5, "is_new": False, "image": None},
    {"rank": 2, "title": "Song Beta", "artist": "Beta Featuring Alpha",
     "peak_pos": 2, "last_pos": 1, "weeks": 3, "is_new": False, "image": None},
]
_HOT100_WEEK_2 = [
    {"rank": 1, "title": "Song Alpha", "artist": "Alpha", "peak_pos": 1,
     "last_pos": 1, "weeks": 6, "is_new": False, "image": None},
    {"rank": 2, "title": "Song Gamma", "artist": "Gamma", "peak_pos": 2,
     "last_pos": 3, "weeks": 2, "is_new": False, "image": None},
]
_B200_WEEK = [
    {"rank": 1, "title": "Album Alpha", "artist": "Alpha", "peak_pos": 1,
     "last_pos": None, "weeks": 1, "is_new": True, "image": None},
    {"rank": 2, "title": "Album Delta", "artist": "Delta & Alpha", "peak_pos": 2,
     "last_pos": 2, "weeks": 4, "is_new": False, "image": None},
]


def _hot100_record():
    return ChartRecord(
        slug="hot-100", entity_kind="song", folder="/fake/hot100",
        last_loaded_date=None, legacy_table=("hot100_entries", "song_id"),
    )


def _b200_record():
    return ChartRecord(
        slug="billboard-200", entity_kind="album", folder="/fake/b200",
        last_loaded_date=None, legacy_table=("b200_entries", "album_id"),
    )


def _new_chart_record():
    return ChartRecord(
        slug="country-songs", entity_kind="song", folder="/fake/country-songs",
        last_loaded_date=None, legacy_table=None,
    )


def _corpus_db():
    return FakeDB(
        charts=[
            {"id": 1, "slug": "hot-100", "entity_kind": "song"},
            {"id": 2, "slug": "billboard-200", "entity_kind": "album"},
            {"id": 3, "slug": "country-songs", "entity_kind": "song"},
        ]
    )


def _load_legacy_corpus():
    """Load the hot-100 (two weeks) + billboard-200 (one week) corpus through the
    registry path, dual-writing. Returns the fake DB after the load.

    Two distinct hot-100 weeks are produced by feeding two different parsed-entry
    fixtures via the harness's per-file stub; each ``_load`` call drives one
    week file.
    """
    db = _corpus_db()
    # hot-100 week 1 and week 2 (two separate load passes, distinct date stub).
    _load(db, _hot100_record(), _HOT100_WEEK_1)
    _load(db, _hot100_record(), _HOT100_WEEK_2, chart_date_offset=1)
    # billboard-200 week.
    _load(db, _b200_record(), _B200_WEEK)
    return db


class HotEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.db = _load_legacy_corpus()

    # --- count parity ----------------------------------------------------------
    def test_hot100_count_parity(self):
        hot_ce = [e for e in self.db.chart_entries if e["chart_id"] == 1]
        self.assertEqual(len(hot_ce), len(self.db.hot100_entries))
        # corpus has 2 hot-100 weeks x 2 entries = 4 rows.
        self.assertEqual(len(hot_ce), 4)

    def test_b200_count_parity(self):
        b200_ce = [e for e in self.db.chart_entries if e["chart_id"] == 2]
        self.assertEqual(len(b200_ce), len(self.db.b200_entries))
        self.assertEqual(len(b200_ce), len(_B200_WEEK))

    # --- content parity: two-way anti-join on (week, rank, entity_id) ----------
    def test_hot100_content_parity_both_directions(self):
        hot_ce = [e for e in self.db.chart_entries if e["chart_id"] == 1]
        ce_set = {(e["chart_week_id"], e["rank"], e["song_id"]) for e in hot_ce}
        legacy_set = {
            (e["chart_week_id"], e["rank"], e["song_id"])
            for e in self.db.hot100_entries
        }
        # forward: no chart_entries row without a matching legacy row.
        self.assertEqual(ce_set - legacy_set, set())
        # reverse: no legacy row without a matching chart_entries row.
        self.assertEqual(legacy_set - ce_set, set())
        self.assertEqual(ce_set, legacy_set)

    def test_b200_content_parity_both_directions(self):
        b200_ce = [e for e in self.db.chart_entries if e["chart_id"] == 2]
        ce_set = {(e["chart_week_id"], e["rank"], e["album_id"]) for e in b200_ce}
        legacy_set = {
            (e["chart_week_id"], e["rank"], e["album_id"])
            for e in self.db.b200_entries
        }
        self.assertEqual(ce_set - legacy_set, set())
        self.assertEqual(legacy_set - ce_set, set())
        self.assertEqual(ce_set, legacy_set)

    # --- per-row field parity (peak/last/weeks/is_new) -------------------------
    def test_hot100_full_field_parity(self):
        hot_ce = {
            (e["chart_week_id"], e["rank"]): e
            for e in self.db.chart_entries
            if e["chart_id"] == 1
        }
        for le in self.db.hot100_entries:
            ce = hot_ce[(le["chart_week_id"], le["rank"])]
            self.assertEqual(ce["song_id"], le["song_id"])
            self.assertEqual(ce["peak_pos"], le["peak_pos"])
            self.assertEqual(ce["last_pos"], le["last_pos"])
            self.assertEqual(ce["weeks_on_chart"], le["weeks_on_chart"])
            self.assertEqual(ce["is_new"], le["is_new"])

    # --- polymorphism guard (T-10-05) ------------------------------------------
    def test_every_chart_entry_sets_exactly_one_entity_fk(self):
        for e in self.db.chart_entries:
            nonnull = sum(
                1 for k in ("song_id", "album_id", "artist_id")
                if e[k] is not None
            )
            self.assertEqual(nonnull, 1, f"row {e} must set exactly one entity FK")

    # --- W1 link parity --------------------------------------------------------
    def test_song_artists_links_match_v1_path(self):
        # The unified artist_cache must produce the SAME song_artists links the
        # v1.0 _load_hot100 produced. Independently recompute the expected links
        # from the corpus via parse_artist_credit and compare.
        from billboard_stats.etl.artist_parser import parse_artist_credit

        expected = set()
        title_to_song = {s["title"]: s["id"] for s in self.db.songs}
        name_to_artist = {a["name"]: a["id"] for a in self.db.artists}
        for entry in _HOT100_WEEK_1 + _HOT100_WEEK_2:
            song_id = title_to_song[entry["title"]]
            for name, role in parse_artist_credit(entry["artist"]):
                expected.add((song_id, name_to_artist[name], role))
        actual = {
            (l["song_id"], l["artist_id"], l["role"]) for l in self.db.song_artists
        }
        self.assertEqual(actual, expected)

    def test_album_artists_links_match_v1_path(self):
        from billboard_stats.etl.artist_parser import parse_artist_credit

        expected = set()
        title_to_album = {a["title"]: a["id"] for a in self.db.albums}
        name_to_artist = {a["name"]: a["id"] for a in self.db.artists}
        for entry in _B200_WEEK:
            album_id = title_to_album[entry["title"]]
            for name, role in parse_artist_credit(entry["artist"]):
                expected.add((album_id, name_to_artist[name], role))
        actual = {
            (l["album_id"], l["artist_id"], l["role"])
            for l in self.db.album_artists
        }
        self.assertEqual(actual, expected)

    def test_shared_artist_resolves_to_one_id_across_charts(self):
        # W1: "Alpha" charts on hot-100 (songs) AND billboard-200 (albums). The
        # pre-loaded artist_cache must resolve Alpha to a SINGLE artist id across
        # both loads -- never two duplicate artist rows.
        alphas = [a for a in self.db.artists if a["name"] == "Alpha"]
        self.assertEqual(len(alphas), 1)


class NewChartNoLegacyTests(unittest.TestCase):
    def test_new_chart_writes_zero_legacy_rows(self):
        db = _corpus_db()
        _load(db, _new_chart_record(),
              [{"rank": 1, "title": "Country One", "artist": "Cole",
                "peak_pos": 1, "last_pos": None, "weeks": 1, "is_new": True,
                "image": None}])
        new_ce = [e for e in db.chart_entries if e["chart_id"] == 3]
        self.assertTrue(new_ce)
        # ZERO legacy rows for a new chart (T-10-06).
        self.assertEqual(db.hot100_entries, [])
        self.assertEqual(db.b200_entries, [])


class StatsRegistryLoopTests(unittest.TestCase):
    def test_build_all_stats_runs_both_v1_and_registry_paths(self):
        # build_all_stats must call BOTH the v1.0 build_artist_stats (literal
        # path, for the live frontend) AND the registry-loop build_artist_chart_stats.
        import inspect

        from billboard_stats.etl import stats_builder

        src = inspect.getsource(stats_builder.build_all_stats)
        self.assertIn("build_artist_stats", src)
        self.assertIn("build_artist_chart_stats", src)

    def test_build_artist_chart_stats_loops_the_registry(self):
        # The generalized rollup loops `SELECT id, entity_kind FROM charts` (the
        # registry) -- one parametric INSERT per chart.
        import inspect

        from billboard_stats.etl import stats_builder

        src = inspect.getsource(stats_builder.build_artist_chart_stats)
        self.assertIn("SELECT id, entity_kind FROM charts", src)

    def test_v1_build_artist_stats_preserved(self):
        # The v1.0 literal path is KEPT unchanged (compat).
        import inspect

        from billboard_stats.etl import stats_builder

        self.assertEqual(
            inspect.getsource(stats_builder).count("def build_artist_stats"), 1
        )


# ============================================================================
# CR-02: build_all_stats is a SINGLE transaction (one commit; rollback on error)
# ============================================================================
class _CountingCursor:
    """Accepts any SQL (DELETE/INSERT/UPDATE/SELECT) as a no-op. Returns an empty
    result for the registry SELECT so build_artist_chart_stats loops zero charts."""

    def __init__(self, fail_on=None):
        self._fail_on = fail_on
        self._result = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        norm = " ".join(sql.split()).lower()
        if self._fail_on and self._fail_on in norm:
            raise RuntimeError("boom")
        # SELECT id, entity_kind FROM charts -> no charts (rollup loops nothing).
        self._result = []

    def fetchall(self):
        return self._result

    def fetchone(self):
        return None


class _CountingConn:
    def __init__(self, fail_on=None):
        self.commits = 0
        self.rollbacks = 0
        self._fail_on = fail_on

    def cursor(self):
        return _CountingCursor(fail_on=self._fail_on)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class BuildAllStatsTransactionTests(unittest.TestCase):
    def test_build_all_stats_commits_exactly_once(self):
        from billboard_stats.etl.stats_builder import build_all_stats

        conn = _CountingConn()
        build_all_stats(conn)
        # The four DELETE+INSERT builders run with commit=False; build_all_stats
        # commits ONCE at the end so the live site flips atomically (CR-02).
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 0)

    def test_build_all_stats_rolls_back_on_failure(self):
        from billboard_stats.etl.stats_builder import build_all_stats

        # Fail inside the album_stats DELETE -> no partial commit, full rollback,
        # so the previous stats stay intact instead of an empty table.
        conn = _CountingConn(fail_on="delete from album_stats")
        with self.assertRaises(RuntimeError):
            build_all_stats(conn)
        self.assertEqual(conn.commits, 0)
        self.assertEqual(conn.rollbacks, 1)


if __name__ == "__main__":
    unittest.main()
