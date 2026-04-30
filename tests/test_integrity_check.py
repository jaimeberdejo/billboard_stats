import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from billboard_stats.etl.integrity_check import (
    _collect_repair_dates,
    _group_consecutive_saturdays,
    audit_chart_data,
)


class IntegrityCheckTests(unittest.TestCase):
    def test_flags_missing_weeks_and_empty_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hot100 = root / "hot100"
            hot100.mkdir()

            valid_entry = {
                "rank": 1,
                "title": "Song A",
                "artist": "Artist A",
                "peakPos": 1,
                "lastPos": 0,
                "weeks": 1,
                "isNew": True,
                "image": "https://example.com/song-a-artwork.jpg",
            }
            (hot100 / "2022-08-06.json").write_text(
                json.dumps([valid_entry]),
                encoding="utf-8",
            )
            (hot100 / "2022-08-20.json").write_text("[]", encoding="utf-8")

            result = audit_chart_data(
                "hot-100",
                data_dir=str(root),
                latest_week=dt.date(2022, 8, 20),
            )

            self.assertEqual(result["missing_dates"], ["2022-08-13"])
            self.assertEqual(result["empty_files"], ["2022-08-20.json"])
            self.assertFalse(result["ok"])

    def test_flags_invalid_json_and_bad_filenames(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            b200 = root / "b200"
            b200.mkdir()

            (b200 / "2022-08-06.json").write_text("{" + ("invalid" * 30), encoding="utf-8")
            (b200 / "bad-name.json").write_text("[]", encoding="utf-8")

            result = audit_chart_data(
                "billboard-200",
                data_dir=str(root),
                latest_week=dt.date(2022, 8, 6),
            )

            self.assertEqual(result["invalid_json_files"], ["2022-08-06.json"])
            self.assertEqual(result["invalid_filenames"], ["bad-name.json"])
            self.assertFalse(result["ok"])

    def test_ignores_future_dated_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            b200 = root / "b200"
            b200.mkdir()

            valid_entry = {
                "rank": 1,
                "album": "Album A",
                "artist": "Artist A",
                "peakPos": 1,
                "lastPos": 0,
                "weeks": 1,
                "isNew": True,
                "image": "https://example.com/album-a-artwork.jpg",
            }
            (b200 / "2022-08-06.json").write_text(json.dumps([valid_entry]), encoding="utf-8")
            (b200 / "2022-08-13.json").write_text("[]", encoding="utf-8")

            result = audit_chart_data(
                "billboard-200",
                data_dir=str(root),
                latest_week=dt.date(2022, 8, 6),
            )

            self.assertEqual(result["future_files"], ["2022-08-13.json"])
            self.assertEqual(result["empty_files"], [])
            self.assertTrue(result["ok"])

    def test_collects_repair_dates_from_missing_and_invalid_files(self):
        result = {
            "missing_dates": ["2022-08-13"],
            "empty_files": ["2022-08-20.json"],
            "invalid_json_files": ["2022-08-27.json"],
            "invalid_payload_files": ["2022-09-03.json"],
            "invalid_filenames": ["bad-name.json"],
        }

        repair_dates, skipped = _collect_repair_dates(result)

        self.assertEqual(
            repair_dates,
            ["2022-08-13", "2022-08-20", "2022-08-27", "2022-09-03"],
        )
        self.assertEqual(skipped, ["bad-name.json"])

    def test_groups_consecutive_saturdays_into_ranges(self):
        self.assertEqual(
            _group_consecutive_saturdays(
                ["2022-08-13", "2022-08-20", "2022-09-03", "2022-09-10"]
            ),
            [("2022-08-13", "2022-08-20"), ("2022-09-03", "2022-09-10")],
        )


if __name__ == "__main__":
    unittest.main()
