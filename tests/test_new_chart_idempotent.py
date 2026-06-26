"""Idempotent re-run tests for the 9 new charts (Plan 11-01).

Re-loading the SAME new-chart week (song / album / artist, all
``legacy_table=None``) must add ZERO new chart_weeks and ZERO new chart_entries.
This mirrors tests/test_loader_registry.py:497-547 and extends the idempotency
proof across all three new-chart entity kinds.

The idempotency rests on:
* ``_upsert_chart_week``'s new-chart branch keying on the partial unique index
  ``uq_chart_weeks_chart_id_date (chart_id, chart_date) WHERE chart_id IS NOT
  NULL`` — so the second load conflict-resolves to the existing week id;
* ``chart_entries`` ON CONFLICT (chart_week_id, rank) DO NOTHING — so the
  duplicate entry rows are skipped.

Using the SAME ``chart_date_offset`` on both passes targets the SAME week. NO
real DB connection and NO network (the FakeDB harness is reused verbatim).
"""

import unittest

from billboard_stats.etl.chart_registry import ChartRecord

from tests.test_loader_registry import FakeDB, _load


def _song_record():
    return ChartRecord(
        slug="country-songs", entity_kind="song", folder="/fake/country-songs",
        last_loaded_date=None, legacy_table=None,
    )


def _album_record():
    return ChartRecord(
        slug="country-albums", entity_kind="album", folder="/fake/country-albums",
        last_loaded_date=None, legacy_table=None,
    )


def _artist_record():
    return ChartRecord(
        slug="artist-100", entity_kind="artist", folder="/fake/artist-100",
        last_loaded_date=None, legacy_table=None,
    )


_SONG_ENTRIES = [
    {"rank": 1, "title": "Country Song A", "artist": "Artist Four", "peak_pos": 1,
     "last_pos": None, "weeks": 1, "is_new": True, "image": None},
    {"rank": 2, "title": "Country Song B", "artist": "Artist Five", "peak_pos": 2,
     "last_pos": 2, "weeks": 4, "is_new": False, "image": None},
]

_ALBUM_ENTRIES = [
    {"rank": 1, "title": "Country Album A", "artist": "Artist Four",
     "peak_pos": 1, "last_pos": None, "weeks": 1, "is_new": True, "image": None},
]

_ARTIST_ENTRIES = [
    {"rank": 1, "title": "", "artist": "Artist Solo", "peak_pos": 1,
     "last_pos": None, "weeks": 1, "is_new": True, "image": None},
]


class NewChartIdempotentReloadTests(unittest.TestCase):
    def test_song_chart_reload_adds_zero_weeks_and_entries(self):
        db = FakeDB(
            charts=[{"id": 3, "slug": "country-songs", "entity_kind": "song"}]
        )
        chart = _song_record()
        _load(db, chart, _SONG_ENTRIES, chart_date_offset=0)
        _load(db, chart, _SONG_ENTRIES, chart_date_offset=0)  # re-run, same week

        weeks = [w for w in db.chart_weeks if w["chart_id"] == 3]
        self.assertEqual(len(weeks), 1)               # no duplicate week
        self.assertIsNone(weeks[0]["chart_type"])     # new chart -> no chart_type
        ce = [e for e in db.chart_entries if e["chart_id"] == 3]
        self.assertEqual(len(ce), len(_SONG_ENTRIES))  # zero new entries
        # New charts never write legacy tables.
        self.assertEqual(db.hot100_entries, [])
        self.assertEqual(db.b200_entries, [])

    def test_album_chart_reload_adds_zero_weeks_and_entries(self):
        db = FakeDB(
            charts=[{"id": 5, "slug": "country-albums", "entity_kind": "album"}]
        )
        chart = _album_record()
        _load(db, chart, _ALBUM_ENTRIES, chart_date_offset=0)
        _load(db, chart, _ALBUM_ENTRIES, chart_date_offset=0)

        weeks = [w for w in db.chart_weeks if w["chart_id"] == 5]
        self.assertEqual(len(weeks), 1)
        self.assertIsNone(weeks[0]["chart_type"])
        ce = [e for e in db.chart_entries if e["chart_id"] == 5]
        self.assertEqual(len(ce), len(_ALBUM_ENTRIES))
        self.assertEqual(db.hot100_entries, [])
        self.assertEqual(db.b200_entries, [])

    def test_artist_chart_reload_adds_zero_weeks_and_entries(self):
        db = FakeDB(
            charts=[{"id": 7, "slug": "artist-100", "entity_kind": "artist"}]
        )
        chart = _artist_record()
        _load(db, chart, _ARTIST_ENTRIES, chart_date_offset=0)
        _load(db, chart, _ARTIST_ENTRIES, chart_date_offset=0)

        weeks = [w for w in db.chart_weeks if w["chart_id"] == 7]
        self.assertEqual(len(weeks), 1)
        self.assertIsNone(weeks[0]["chart_type"])
        ce = [e for e in db.chart_entries if e["chart_id"] == 7]
        self.assertEqual(len(ce), len(_ARTIST_ENTRIES))
        for e in ce:
            self.assertIsNotNone(e["artist_id"])
            self.assertIsNone(e["song_id"])
            self.assertIsNone(e["album_id"])
        # Zero legacy rows for the artist chart.
        self.assertEqual(db.hot100_entries, [])
        self.assertEqual(db.b200_entries, [])


if __name__ == "__main__":
    unittest.main()
