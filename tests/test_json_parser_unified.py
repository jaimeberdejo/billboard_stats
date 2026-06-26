"""Equivalence tests for the unified parse_chart_file (Plan 10-01).

These tests build tiny temp-dir JSON fixtures (no real DB, no network, mirroring
tests/test_integrity_check.py) and prove that the single ``parse_chart_file``
collapses the two v1.0 parsers into one title-or-album path:

* on a hot100-shaped file (``title`` key) it is byte-equal to ``parse_hot100_file``;
* on a b200-shaped file (``album`` key) it is byte-equal to ``parse_b200_file``;
* on a Phase-7 new-chart file (``title`` key) it parses to the normalized shape;
* an invalid/empty file returns ``None`` exactly as the v1.0 parsers do.

``parse_hot100_file`` / ``parse_b200_file`` remain importable as thin compat
shims (loader/updater are migrated in Plans 02/03), so this also asserts the
shims still produce the same normalized output.
"""

import json
import os
import tempfile
import unittest

from billboard_stats.etl.json_parser import (
    parse_b200_file,
    parse_chart_file,
    parse_hot100_file,
)


# A hot100 entry uses the ``title`` key; b200 uses ``album``; Phase-7 new charts
# use ``title``. Every other field is identical across all three shapes.
_HOT100_ROWS = [
    {
        "rank": 1,
        "title": "Flowers",
        "artist": "Miley Cyrus",
        "peakPos": 1,
        "lastPos": 2,
        "weeks": 5,
        "isNew": False,
        "image": "https://example.com/flowers.jpg",
    },
    {
        "rank": 2,
        "title": "Kill Bill",
        "artist": "SZA",
        "peakPos": 1,
        "lastPos": 1,
        "weeks": 10,
        "isNew": False,
        "image": "https://charts-static.billboard.com/lazy-load.gif",  # cleaned -> None
    },
]

_B200_ROWS = [
    {
        "rank": 1,
        "album": "Midnights",
        "artist": "Taylor Swift",
        "peakPos": 1,
        "lastPos": 1,
        "weeks": 12,
        "isNew": False,
        "image": "https://example.com/midnights.jpg",
    },
    {
        "rank": 2,
        "album": "SOS",
        "artist": "SZA",
        "peakPos": 1,
        "lastPos": 3,
        "weeks": 8,
        "isNew": True,
        "image": None,
    },
]

# A new Phase-7 chart (e.g. country-songs) uses the ``title`` key like hot100.
_NEW_CHART_ROWS = [
    {
        "rank": 1,
        "title": "Last Night",
        "artist": "Morgan Wallen",
        "peakPos": 1,
        "lastPos": 1,
        "weeks": 20,
        "isNew": False,
        "image": "https://example.com/lastnight.jpg",
    },
]


def _write(tmpdir, name, rows):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    return path


class ParseChartFileEquivalenceTests(unittest.TestCase):
    def test_equals_hot100_parser_on_title_key_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", _HOT100_ROWS)
            self.assertEqual(
                parse_chart_file(path), parse_hot100_file(path)
            )

    def test_equals_b200_parser_on_album_key_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", _B200_ROWS)
            self.assertEqual(
                parse_chart_file(path), parse_b200_file(path)
            )

    def test_parses_new_chart_title_key_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", _NEW_CHART_ROWS)
            result = parse_chart_file(path)
            self.assertIsNotNone(result)
            self.assertEqual(len(result), 1)
            entry = result[0]
            self.assertEqual(entry["rank"], 1)
            self.assertEqual(entry["title"], "Last Night")  # taken from title key
            self.assertEqual(entry["artist"], "Morgan Wallen")
            self.assertEqual(entry["peak_pos"], 1)
            self.assertEqual(entry["weeks"], 20)
            self.assertFalse(entry["is_new"])

    def test_title_taken_from_album_when_title_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", _B200_ROWS)
            result = parse_chart_file(path)
            titles = [e["title"] for e in result]
            self.assertIn("Midnights", titles)
            self.assertIn("SOS", titles)


class ParseChartFileNormalizedShapeTests(unittest.TestCase):
    def test_normalized_keys_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", _HOT100_ROWS)
            entry = parse_chart_file(path)[0]
            self.assertEqual(
                set(entry.keys()),
                {
                    "rank",
                    "title",
                    "artist",
                    "peak_pos",
                    "last_pos",
                    "weeks",
                    "is_new",
                    "image",
                },
            )

    def test_lazy_load_image_cleaned_to_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", _HOT100_ROWS)
            killbill = next(
                e for e in parse_chart_file(path) if e["title"] == "Kill Bill"
            )
            self.assertIsNone(killbill["image"])

    def test_invalid_rows_dropped(self):
        # rank<=0 OR missing title/artist must be dropped (validity gate).
        rows = [
            {"rank": 0, "title": "Zero", "artist": "Nobody"},  # rank <= 0
            {"rank": 1, "title": "", "artist": "Somebody"},  # empty title/album
            {"rank": 2, "title": "Good", "artist": ""},  # empty artist
            {"rank": 3, "title": "Keep", "artist": "Me"},  # valid
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", rows)
            result = parse_chart_file(path)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["title"], "Keep")


class ParseChartFileMalformedRankTests(unittest.TestCase):
    """WR-06: a single non-numeric/null rank must drop THAT row, not crash the
    whole file. _safe_int tolerates it; the rank>0 gate then drops it."""

    def test_non_numeric_rank_drops_row_without_crashing(self):
        rows = [
            {"rank": "N/A", "title": "Bad String Rank", "artist": "X"},  # dropped
            {"rank": None, "title": "Null Rank", "artist": "Y"},          # dropped
            {"rank": 1, "title": "Keep Me", "artist": "Z"},               # valid
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", rows)
            result = parse_chart_file(path)  # must not raise
            self.assertIsNotNone(result)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["title"], "Keep Me")
            self.assertEqual(result[0]["rank"], 1)

    def test_all_ranks_malformed_returns_none(self):
        rows = [
            {"rank": "N/A", "title": "A", "artist": "X"},
            {"rank": None, "title": "B", "artist": "Y"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", rows)
            self.assertIsNone(parse_chart_file(path))


class ParseChartFileInvalidFileTests(unittest.TestCase):
    def test_empty_list_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", [])
            self.assertIsNone(parse_chart_file(path))

    def test_malformed_json_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2024-01-06.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{not valid json")
            self.assertIsNone(parse_chart_file(path))

    def test_missing_file_returns_none(self):
        self.assertIsNone(parse_chart_file("/no/such/file/2024-01-06.json"))

    def test_non_list_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2024-01-06.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"not": "a list"}, f)
            self.assertIsNone(parse_chart_file(path))


class CompatShimTests(unittest.TestCase):
    """parse_hot100_file / parse_b200_file remain importable shims that delegate
    to parse_chart_file and return identical normalized output."""

    def test_hot100_shim_matches_unified(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", _HOT100_ROWS)
            self.assertEqual(parse_hot100_file(path), parse_chart_file(path))

    def test_b200_shim_matches_unified(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", _B200_ROWS)
            self.assertEqual(parse_b200_file(path), parse_chart_file(path))


class ParseChartFileEntityKindGateTests(unittest.TestCase):
    """Phase 11 / CHARTS-03: the validity gate is entity-kind-aware.

    For ``entity_kind="artist"`` the ranked entity IS the artist, so a row with
    ``rank > 0`` and a non-empty ``artist`` is KEPT even when its ``title`` is
    empty (~4.3% of real artist-100 rows carry an empty title). For every other
    kind (and the no-arg default) the existing ``rank > 0 AND title AND artist``
    gate is preserved byte-for-byte.
    """

    # An artist-chart file mirroring the real artist-100 shape: rank present,
    # artist non-empty, title EMPTY. The on-disk JSON does not encode entity_kind
    # (it is supplied by the caller).
    _ARTIST_ROWS = [
        {
            "rank": 1,
            "title": "",  # empty title — the artist is the entity
            "artist": "Taylor Swift",
            "peakPos": 1,
            "lastPos": 1,
            "weeks": 50,
            "isNew": False,
            "image": None,
        },
        {
            "rank": 2,
            "title": "",
            "artist": "",  # no artist -> dropped even on an artist chart
            "peakPos": 2,
            "lastPos": 3,
            "weeks": 10,
            "isNew": False,
            "image": None,
        },
    ]

    def test_artist_kind_keeps_empty_title_row_with_artist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", self._ARTIST_ROWS)
            result = parse_chart_file(path, entity_kind="artist")
        self.assertIsNotNone(result)
        # Only the rank-1 row survives: empty title is fine for an artist chart,
        # but the rank-2 row has an empty artist and must still be dropped.
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["rank"], 1)
        self.assertEqual(result[0]["title"], "")
        self.assertEqual(result[0]["artist"], "Taylor Swift")

    def test_artist_kind_drops_empty_artist_row(self):
        rows = [
            {"rank": 1, "title": "anything", "artist": "", "peakPos": None,
             "lastPos": None, "weeks": None, "isNew": False, "image": None},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", rows)
            result = parse_chart_file(path, entity_kind="artist")
        # Empty artist -> nothing valid -> None (artist is the required field).
        self.assertIsNone(result)

    def test_song_kind_still_drops_empty_title_row(self):
        # Same empty-title rows, but as a SONG chart: title IS required, so the
        # empty-title row is dropped exactly as before.
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", self._ARTIST_ROWS)
            result = parse_chart_file(path, entity_kind="song")
        self.assertIsNone(result)

    def test_default_no_arg_unchanged_drops_empty_title(self):
        # No entity_kind argument -> behaves exactly like today (title required).
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", self._ARTIST_ROWS)
            result = parse_chart_file(path)
        self.assertIsNone(result)

    def test_song_kind_byte_equal_to_default_on_normal_file(self):
        # entity_kind="song" must be byte-for-byte equal to the no-arg default on
        # a normal song file (no behavior change for song/album/None).
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", _HOT100_ROWS)
            self.assertEqual(
                parse_chart_file(path, entity_kind="song"),
                parse_chart_file(path),
            )

    def test_album_kind_drops_missing_album_row(self):
        # Album charts use the "album" key; a row missing it (empty title) drops.
        rows = [
            {"rank": 1, "album": "Real Album", "artist": "Some Artist",
             "peakPos": 1, "lastPos": 1, "weeks": 2, "isNew": False,
             "image": None},
            {"rank": 2, "artist": "Other Artist", "peakPos": 2, "lastPos": 2,
             "weeks": 1, "isNew": False, "image": None},  # no album key
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "2024-01-06.json", rows)
            result = parse_chart_file(path, entity_kind="album")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Real Album")


if __name__ == "__main__":
    unittest.main()
