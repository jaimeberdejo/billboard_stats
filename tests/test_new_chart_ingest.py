"""Fixture/mock-DB ingest tests for the 9 new charts (Plan 11-01).

These tests run entirely against the in-memory fake DB layer reused verbatim from
tests/test_loader_registry.py. They make NO real database connection and NO
network calls (the real Neon prod load is a deferred operator step — see
docs/ETL-REGISTRY.md). They prove the four ROADMAP Phase 11 success criteria:

* artist-100 loads as an artist entity — a collaborative credit resolves to ONE
  chart_entries.artist_id with NO collaboration-splitting (CHARTS-03);
* an empty-title artist row is kept via the REAL parse_chart_file gate (Task 1);
* the same (title, artist) across two song / two album charts collapses to ONE
  songs / albums row (CHARTS-01 / CHARTS-02 cross-chart dedup);
* a thin/old week with None numerics loads without error;
* register_new_charts seeds the 9 CURATED_CHARTS into the charts table
  idempotently (9 inserted, then 0 on re-run) via real ON CONFLICT semantics.
"""

import re
import tempfile
import unittest
from datetime import date

from billboard_stats.etl import loader
from billboard_stats.etl.chart_registry import ChartRecord
from billboard_stats.etl.charts import CURATED_CHARTS
from billboard_stats.etl.json_parser import parse_chart_file

from tests.test_loader_registry import (
    FakeConn,
    FakeCursor,
    FakeDB,
    _fake_execute_values,
    _load,
)


# ============================================================================
# FakeCursor extension: model INSERT INTO charts ... ON CONFLICT (slug) DO NOTHING
# ============================================================================
class RegisteringFakeCursor(FakeCursor):
    """FakeCursor that also models the register_new_charts INSERT (Plan 11-01).

    The shared FakeCursor raises on any unhandled SQL; it has no handler for the
    ``INSERT INTO charts (...) VALUES (...) ON CONFLICT (slug) DO NOTHING``
    statement register_new_charts emits. This subclass adds that handler with
    REAL conflict semantics (slug-membership check), so the "9 then 0"
    idempotency assertion passes because the second call hits a genuine slug
    conflict — not because the INSERT silently no-ops on an unhandled path.
    """

    def execute(self, sql, params=None):
        norm = re.sub(r"\s+", " ", sql).strip().lower()
        # New handler (Plan 11-01): INSERT INTO charts ... ON CONFLICT (slug)
        # DO NOTHING — insert only if the slug is not already present.
        if norm.startswith("insert into charts"):
            slug, title, entity_kind, category = tuple(params)
            self._db.register_chart(slug, title, entity_kind, category)
            self._result = None
            return
        return super().execute(sql, params)


class RegisteringFakeConn(FakeConn):
    def cursor(self):
        return RegisteringFakeCursor(self._db)


class RegisteringFakeDB(FakeDB):
    """FakeDB that can model ON CONFLICT (slug) DO NOTHING for the charts table."""

    def register_chart(self, slug, title, entity_kind, category):
        # ON CONFLICT (slug) DO NOTHING: skip if the slug already exists.
        if any(c["slug"] == slug for c in self.charts):
            return
        next_id = max((c["id"] for c in self.charts), default=0) + 1
        self.charts.append(
            {
                "id": next_id,
                "slug": slug,
                "title": title,
                "entity_kind": entity_kind,
                "category": category,
            }
        )


# ============================================================================
# Task 2: register_new_charts
# ============================================================================
class RegisterNewChartsTests(unittest.TestCase):
    def test_registers_nine_charts_on_empty_table(self):
        db = RegisteringFakeDB(charts=[])
        conn = RegisteringFakeConn(db)
        loader.register_new_charts(conn)

        self.assertEqual(len(db.charts), 9)
        slugs = {c["slug"] for c in db.charts}
        expected = {c["slug"] for c in CURATED_CHARTS}
        self.assertEqual(slugs, expected)

    def test_artist_and_genre_entity_kinds_from_curated(self):
        db = RegisteringFakeDB(charts=[])
        conn = RegisteringFakeConn(db)
        loader.register_new_charts(conn)

        by_slug = {c["slug"]: c for c in db.charts}
        self.assertEqual(by_slug["artist-100"]["entity_kind"], "artist")
        self.assertEqual(by_slug["country-songs"]["entity_kind"], "song")
        self.assertEqual(by_slug["country-albums"]["entity_kind"], "album")

    def test_second_call_inserts_zero_rows_idempotent(self):
        db = RegisteringFakeDB(charts=[])
        conn = RegisteringFakeConn(db)
        loader.register_new_charts(conn)
        self.assertEqual(len(db.charts), 9)
        # Re-run: ON CONFLICT (slug) DO NOTHING -> zero new rows.
        loader.register_new_charts(conn)
        self.assertEqual(len(db.charts), 9)

    def test_legacy_charts_untouched_total_eleven(self):
        db = RegisteringFakeDB(
            charts=[
                {"id": 1, "slug": "hot-100", "title": "Hot 100",
                 "entity_kind": "song", "category": "overall"},
                {"id": 2, "slug": "billboard-200", "title": "Billboard 200",
                 "entity_kind": "album", "category": "overall"},
            ]
        )
        conn = RegisteringFakeConn(db)
        loader.register_new_charts(conn)
        # 2 legacy + 9 new = 11; legacy rows untouched.
        self.assertEqual(len(db.charts), 11)
        legacy = {c["slug"]: c for c in db.charts
                  if c["slug"] in ("hot-100", "billboard-200")}
        self.assertEqual(legacy["hot-100"]["id"], 1)
        self.assertEqual(legacy["billboard-200"]["id"], 2)

    def test_register_precedes_iter_charts_in_run_etl(self):
        import inspect

        src = inspect.getsource(loader.run_etl)
        self.assertLess(
            src.index("register_new_charts"),
            src.index("iter_charts"),
            "register_new_charts must precede the iter_charts loop in run_etl",
        )


# ============================================================================
# Task 3 fixtures: ChartRecords with legacy_table=None for the new charts
# ============================================================================
def _artist100_record():
    return ChartRecord(
        slug="artist-100", entity_kind="artist", folder="/fake/artist-100",
        last_loaded_date=None, legacy_table=None,
    )


def _country_songs_record():
    return ChartRecord(
        slug="country-songs", entity_kind="song", folder="/fake/country-songs",
        last_loaded_date=None, legacy_table=None,
    )


def _rock_songs_record():
    return ChartRecord(
        slug="rock-songs", entity_kind="song", folder="/fake/rock-songs",
        last_loaded_date=None, legacy_table=None,
    )


def _country_albums_record():
    return ChartRecord(
        slug="country-albums", entity_kind="album", folder="/fake/country-albums",
        last_loaded_date=None, legacy_table=None,
    )


def _rock_albums_record():
    return ChartRecord(
        slug="rock-albums", entity_kind="album", folder="/fake/rock-albums",
        last_loaded_date=None, legacy_table=None,
    )


# ============================================================================
# Task 3: artist-100 direct link + NO collaboration-splitting (CHARTS-03)
# ============================================================================
class ArtistChartIngestTests(unittest.TestCase):
    def test_collaborative_credit_resolves_to_one_artist_id_no_split(self):
        db = FakeDB(
            charts=[{"id": 7, "slug": "artist-100", "entity_kind": "artist"}]
        )
        entries = [
            {"rank": 1, "title": "", "artist": "Artist Two Featuring Artist One",
             "peak_pos": 1, "last_pos": None, "weeks": 1, "is_new": True,
             "image": None},
        ]
        _load(db, _artist100_record(), entries, chart_date_offset=0)

        artist_ce = [e for e in db.chart_entries if e["chart_id"] == 7]
        self.assertEqual(len(artist_ce), 1)
        e = artist_ce[0]
        self.assertIsNotNone(e["artist_id"])
        self.assertIsNone(e["song_id"])
        self.assertIsNone(e["album_id"])
        # No collaboration-splitting: the whole credit is ONE artist row, and the
        # artist path never touches the song_artists link table.
        self.assertEqual(len(db.song_artists), 0)
        self.assertEqual(len(db.album_artists), 0)
        self.assertEqual(len(db.artists), 1)
        self.assertEqual(db.artists[0]["name"],
                         "Artist Two Featuring Artist One")

    def test_empty_title_artist_row_kept_via_real_parser_gate(self):
        # Exercise the REAL parse_chart_file gate (Task 1), not a stubbed parser:
        # write a temp JSON file with one rank>0 / empty-title / non-empty-artist
        # row and assert the artist-kind gate keeps it.
        import json
        import os

        rows = [
            {"rank": 1, "title": "", "artist": "Taylor Swift", "peakPos": 1,
             "lastPos": 1, "weeks": 50, "isNew": False, "image": None},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2024-01-06.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rows, f)
            parsed = parse_chart_file(path, entity_kind="artist")

        self.assertIsNotNone(parsed)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["title"], "")
        self.assertEqual(parsed[0]["artist"], "Taylor Swift")

    def test_empty_title_artist_row_loads_to_artist_id(self):
        # End-to-end: an empty-title artist entry produces a chart_entries row
        # with artist_id set (proving the gate + the artist dispatch together).
        db = FakeDB(
            charts=[{"id": 7, "slug": "artist-100", "entity_kind": "artist"}]
        )
        entries = [
            {"rank": 1, "title": "", "artist": "Taylor Swift", "peak_pos": 1,
             "last_pos": 1, "weeks": 50, "is_new": False, "image": None},
        ]
        _load(db, _artist100_record(), entries, chart_date_offset=0)
        artist_ce = [e for e in db.chart_entries if e["chart_id"] == 7]
        self.assertEqual(len(artist_ce), 1)
        self.assertIsNotNone(artist_ce[0]["artist_id"])


# ============================================================================
# Task 3: cross-chart dedup (CHARTS-01 songs / CHARTS-02 albums)
# ============================================================================
class CrossChartDedupTests(unittest.TestCase):
    def test_same_song_across_two_song_charts_collapses_to_one_row(self):
        db = FakeDB(
            charts=[
                {"id": 3, "slug": "country-songs", "entity_kind": "song"},
                {"id": 4, "slug": "rock-songs", "entity_kind": "song"},
            ]
        )
        entry = [
            {"rank": 1, "title": "Crossover Hit", "artist": "Genre Bender",
             "peak_pos": 1, "last_pos": 1, "weeks": 3, "is_new": False,
             "image": None},
        ]
        _load(db, _country_songs_record(), entry, chart_date_offset=0)
        _load(db, _rock_songs_record(), entry, chart_date_offset=0)

        # Exactly ONE songs row despite charting on two song charts.
        self.assertEqual(len(db.songs), 1)
        song_id = db.songs[0]["id"]
        ce = [e for e in db.chart_entries if e["chart_id"] in (3, 4)]
        self.assertEqual(len(ce), 2)
        for e in ce:
            self.assertEqual(e["song_id"], song_id)

    def test_same_album_across_two_album_charts_collapses_to_one_row(self):
        db = FakeDB(
            charts=[
                {"id": 5, "slug": "country-albums", "entity_kind": "album"},
                {"id": 6, "slug": "rock-albums", "entity_kind": "album"},
            ]
        )
        entry = [
            {"rank": 1, "title": "Crossover Album", "artist": "Genre Bender",
             "peak_pos": 1, "last_pos": 1, "weeks": 3, "is_new": False,
             "image": None},
        ]
        _load(db, _country_albums_record(), entry, chart_date_offset=0)
        _load(db, _rock_albums_record(), entry, chart_date_offset=0)

        self.assertEqual(len(db.albums), 1)
        album_id = db.albums[0]["id"]
        ce = [e for e in db.chart_entries if e["chart_id"] in (5, 6)]
        self.assertEqual(len(ce), 2)
        for e in ce:
            self.assertEqual(e["album_id"], album_id)


# ============================================================================
# Task 3: thin/old + None tolerance
# ============================================================================
class ThinWeekToleranceTests(unittest.TestCase):
    def test_none_numeric_week_loads_without_error(self):
        db = FakeDB(
            charts=[{"id": 3, "slug": "country-songs", "entity_kind": "song"}]
        )
        # Mirrors _B200_ENTRIES[0]: None peak/last/weeks on a thin/old week.
        entries = [
            {"rank": 1, "title": "Old Song", "artist": "Old Artist",
             "peak_pos": None, "last_pos": None, "weeks": None, "is_new": False,
             "image": None},
        ]
        _load(db, _country_songs_record(), entries, chart_date_offset=0)

        ce = [e for e in db.chart_entries if e["chart_id"] == 3]
        self.assertEqual(len(ce), 1)
        self.assertIsNone(ce[0]["peak_pos"])
        self.assertIsNone(ce[0]["last_pos"])
        self.assertIsNone(ce[0]["weeks_on_chart"])


if __name__ == "__main__":
    unittest.main()
