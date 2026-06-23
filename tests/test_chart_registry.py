"""Fixture/fake-DB tests for the registry-driven ETL helper (Plan 10-01).

These tests run entirely against an in-memory fake DB layer mirroring
tests/test_migrate_multichart.py. They make NO real database connection and NO
network calls. The real-DB read is lazy / operator-time; here a fake connection
is injected.

The registry is the SOURCE-OF-TRUTH adapter the loader (Plan 02) and updater
(Plan 03) build against: it reads the DB ``charts`` table (seeded by Phase 9 with
hot-100=song, billboard-200=album) and yields one ChartRecord per chart carrying
``(slug, entity_kind, folder, last_loaded_date, legacy_table)``. ``folder`` maps
each legacy chart to its REAL on-disk folder (hot-100 -> data/hot100,
billboard-200 -> data/b200) and every other chart to data/{slug};
``legacy_table`` is the dual-write target table+entity-column for the two legacy
charts (None for new charts); ``last_loaded_date`` is the max already-loaded
chart_date (None when no weeks are loaded -- the incremental start signal).
"""

import copy
import re
import unittest
from datetime import date

from billboard_stats.etl import chart_registry
from billboard_stats.etl.chart_registry import ChartRecord, iter_charts, list_charts


# ============================================================================
# In-memory fake DB layer
# ============================================================================
class FakeCursor:
    """A psycopg2-cursor-like stand-in interpreting the single SQL read
    iter_charts() emits: charts LEFT JOIN chart_weeks for a per-chart
    MAX(chart_date), grouped by chart."""

    def __init__(self, db):
        self._db = db
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        norm = re.sub(r"\s+", " ", sql).strip().lower()
        params = params or ()

        # The registry's one read: per-chart row with MAX(chart_date).
        if norm.startswith("select") and "from charts" in norm:
            rows = []
            for c in self._db.charts:
                if "is_active" in norm and "where" in norm and "c.is_active" in norm:
                    # active_only path filters in SQL; the fake honors it below
                    # via a flag passed through the WHERE marker.
                    pass
                last = self._db.max_chart_date(c["id"])
                rows.append(
                    (c["slug"], c["entity_kind"], c.get("is_active", True), last)
                )
            # Honor active_only filtering when the query restricts to is_active.
            if "where c.is_active" in norm:
                rows = [r for r in rows if r[2]]
            self._result = rows
            return

        raise AssertionError(f"FakeCursor: unhandled SQL: {norm!r}")

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None


class FakeConn:
    """A connection-like stand-in yielding FakeCursor."""

    def __init__(self, db):
        self._db = db

    def cursor(self):
        return FakeCursor(self._db)


class FakeDB:
    """In-memory model of charts + chart_weeks for the registry read."""

    def __init__(self, charts=None, chart_weeks=None):
        # charts: {"id", "slug", "entity_kind", "is_active"}
        self.charts = [dict(c) for c in (charts or [])]
        # chart_weeks: {"id", "chart_id", "chart_date"}
        self.chart_weeks = [dict(w) for w in (chart_weeks or [])]

    def max_chart_date(self, chart_id):
        dates = [
            w["chart_date"]
            for w in self.chart_weeks
            if w.get("chart_id") == chart_id and w.get("chart_date") is not None
        ]
        return max(dates) if dates else None

    def snapshot(self):
        return copy.deepcopy({"charts": self.charts, "chart_weeks": self.chart_weeks})


def _fixture():
    """hot-100 (song) + billboard-200 (album) + a new country-songs (song) chart,
    plus a couple loaded weeks for hot-100 and none for country-songs."""
    charts = [
        {"id": 1, "slug": "hot-100", "entity_kind": "song", "is_active": True},
        {"id": 2, "slug": "billboard-200", "entity_kind": "album", "is_active": True},
        {"id": 3, "slug": "country-songs", "entity_kind": "song", "is_active": True},
    ]
    chart_weeks = [
        {"id": 1, "chart_id": 1, "chart_date": date(2024, 1, 6)},
        {"id": 2, "chart_id": 1, "chart_date": date(2024, 1, 13)},
        {"id": 3, "chart_id": 2, "chart_date": date(2023, 12, 30)},
        # country-songs has no loaded weeks yet.
    ]
    return FakeDB(charts, chart_weeks)


def _record_by_slug(records, slug):
    return next(r for r in records if r.slug == slug)


# ----------------------------------------------------------------------------
# Folder + legacy_table mapping
# ----------------------------------------------------------------------------
class RegistryMappingTests(unittest.TestCase):
    def test_hot100_folder_and_legacy_table(self):
        db = _fixture()
        records = list_charts(FakeConn(db), data_dir="/data")
        hot100 = _record_by_slug(records, "hot-100")
        self.assertTrue(hot100.folder.endswith("/hot100"), hot100.folder)
        self.assertEqual(hot100.legacy_table, ("hot100_entries", "song_id"))
        self.assertEqual(hot100.entity_kind, "song")

    def test_b200_folder_and_legacy_table(self):
        db = _fixture()
        records = list_charts(FakeConn(db), data_dir="/data")
        b200 = _record_by_slug(records, "billboard-200")
        self.assertTrue(b200.folder.endswith("/b200"), b200.folder)
        self.assertEqual(b200.legacy_table, ("b200_entries", "album_id"))
        self.assertEqual(b200.entity_kind, "album")

    def test_new_chart_folder_is_slug_and_no_legacy_table(self):
        db = _fixture()
        records = list_charts(FakeConn(db), data_dir="/data")
        country = _record_by_slug(records, "country-songs")
        self.assertTrue(country.folder.endswith("/country-songs"), country.folder)
        self.assertIsNone(country.legacy_table)

    def test_folder_is_joined_under_data_dir(self):
        db = _fixture()
        records = list_charts(FakeConn(db), data_dir="/srv/data")
        hot100 = _record_by_slug(records, "hot-100")
        self.assertEqual(hot100.folder, "/srv/data/hot100")


# ----------------------------------------------------------------------------
# last_loaded_date (incremental signal)
# ----------------------------------------------------------------------------
class RegistryLastLoadedDateTests(unittest.TestCase):
    def test_last_loaded_date_is_max_chart_date(self):
        db = _fixture()
        records = list_charts(FakeConn(db), data_dir="/data")
        hot100 = _record_by_slug(records, "hot-100")
        self.assertEqual(hot100.last_loaded_date, date(2024, 1, 13))

    def test_last_loaded_date_none_when_no_weeks(self):
        db = _fixture()
        records = list_charts(FakeConn(db), data_dir="/data")
        country = _record_by_slug(records, "country-songs")
        self.assertIsNone(country.last_loaded_date)


# ----------------------------------------------------------------------------
# active_only filtering
# ----------------------------------------------------------------------------
class RegistryActiveOnlyTests(unittest.TestCase):
    def test_active_only_excludes_inactive_charts(self):
        charts = [
            {"id": 1, "slug": "hot-100", "entity_kind": "song", "is_active": True},
            {"id": 2, "slug": "retired-chart", "entity_kind": "song", "is_active": False},
        ]
        db = FakeDB(charts, [])
        active = list_charts(FakeConn(db), data_dir="/data", active_only=True)
        slugs = {r.slug for r in active}
        self.assertIn("hot-100", slugs)
        self.assertNotIn("retired-chart", slugs)

    def test_active_only_false_includes_inactive(self):
        charts = [
            {"id": 1, "slug": "hot-100", "entity_kind": "song", "is_active": True},
            {"id": 2, "slug": "retired-chart", "entity_kind": "song", "is_active": False},
        ]
        db = FakeDB(charts, [])
        allrecs = list_charts(FakeConn(db), data_dir="/data", active_only=False)
        slugs = {r.slug for r in allrecs}
        self.assertIn("retired-chart", slugs)


# ----------------------------------------------------------------------------
# Partial / absent on-disk folder tolerance
# ----------------------------------------------------------------------------
class RegistryPartialFolderTests(unittest.TestCase):
    def test_absent_folder_does_not_raise_and_record_is_yielded(self):
        # data_dir points at a directory whose chart subfolders do NOT exist on
        # disk. iter_charts must NOT stat/raise -- it yields the record anyway;
        # callers decide whether to load.
        db = _fixture()
        records = list_charts(
            FakeConn(db), data_dir="/nonexistent/path/that/does/not/exist"
        )
        self.assertEqual(len(records), 3)
        country = _record_by_slug(records, "country-songs")
        self.assertTrue(
            country.folder.endswith("/country-songs"), country.folder
        )


# ----------------------------------------------------------------------------
# ChartRecord shape + iter_charts is a generator
# ----------------------------------------------------------------------------
class RegistryRecordShapeTests(unittest.TestCase):
    def test_chartrecord_has_expected_fields(self):
        rec = ChartRecord(
            slug="x",
            entity_kind="song",
            folder="/data/x",
            last_loaded_date=None,
            legacy_table=None,
        )
        self.assertEqual(rec.slug, "x")
        self.assertEqual(rec.entity_kind, "song")
        self.assertEqual(rec.folder, "/data/x")
        self.assertIsNone(rec.last_loaded_date)
        self.assertIsNone(rec.legacy_table)

    def test_iter_charts_yields_chartrecords(self):
        db = _fixture()
        recs = list(iter_charts(FakeConn(db), data_dir="/data"))
        self.assertTrue(all(isinstance(r, ChartRecord) for r in recs))
        self.assertEqual(len(recs), 3)


# ----------------------------------------------------------------------------
# Module hygiene: no top-level psycopg2 import
# ----------------------------------------------------------------------------
class RegistryPostgresFreeTests(unittest.TestCase):
    def test_module_has_no_top_level_psycopg_import(self):
        import inspect

        source = inspect.getsource(chart_registry)
        lines = source.splitlines()
        top_level = [
            l for l in lines if l.startswith("import ") or l.startswith("from ")
        ]
        self.assertFalse(
            any("psycopg" in l for l in top_level),
            "psycopg2 must not be a top-level import",
        )

    def test_exports_iter_and_list_and_record(self):
        self.assertTrue(hasattr(chart_registry, "iter_charts"))
        self.assertTrue(hasattr(chart_registry, "list_charts"))
        self.assertTrue(hasattr(chart_registry, "ChartRecord"))


if __name__ == "__main__":
    unittest.main()
