"""Unit tests for the generalized download_chart primitive.

billboard.ChartData is mocked so the suite makes NO network calls.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

import requests

import billboard

from billboard_stats.etl import fetcher
from billboard_stats.etl.fetcher import HardStopError, download_chart


def _fake_entry(rank):
    e = mock.Mock()
    e.rank = rank
    e.title = f"Song {rank}"
    e.artist = f"Artist {rank}"
    e.peakPos = rank
    e.lastPos = rank
    e.weeks = 1
    e.isNew = False
    e.image = None
    return e


class _FakeChart:
    def __init__(self, n=3):
        self.entries = [_fake_entry(i + 1) for i in range(n)]

    def __iter__(self):
        return iter(self.entries)


class DownloadChartPathTests(unittest.TestCase):
    def test_writes_per_slug_directory_and_generic_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(billboard, "ChartData", return_value=_FakeChart()):
                download_chart(
                    "country-songs",
                    "2024-08-03",
                    "2024-08-10",
                    data_dir=tmp,
                    delay=0,
                )
            slug_dir = os.path.join(tmp, "country-songs")
            self.assertTrue(os.path.isdir(slug_dir))
            files = sorted(os.listdir(slug_dir))
            self.assertEqual(files, ["2024-08-03.json", "2024-08-10.json"])

            with open(os.path.join(slug_dir, "2024-08-03.json")) as f:
                data = json.load(f)
            self.assertEqual(
                set(data[0].keys()),
                {"rank", "title", "artist", "peakPos", "lastPos", "weeks", "isNew", "image"},
            )


class DownloadChartCacheSkipTests(unittest.TestCase):
    def test_existing_large_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            slug_dir = os.path.join(tmp, "country-songs")
            os.makedirs(slug_dir)
            existing = os.path.join(slug_dir, "2024-08-03.json")
            with open(existing, "w") as f:
                # Comfortably above MIN_FILE_SIZE.
                f.write("[" + ("0" * fetcher.MIN_FILE_SIZE) + "]")

            with mock.patch.object(
                billboard, "ChartData", return_value=_FakeChart()
            ) as mocked:
                download_chart(
                    "country-songs",
                    "2024-08-03",
                    "2024-08-03",
                    data_dir=tmp,
                    delay=0,
                )
            # The only week in range already exists -> no ChartData call.
            mocked.assert_not_called()


def _http_error(status):
    resp = mock.Mock()
    resp.status_code = status
    return requests.exceptions.HTTPError(f"{status} error", response=resp)


class DownloadChartHardStopTests(unittest.TestCase):
    def test_403_aborts_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                billboard, "ChartData", side_effect=_http_error(403)
            ):
                with self.assertRaises(HardStopError):
                    download_chart(
                        "country-songs",
                        "2024-08-03",
                        "2024-08-31",  # multiple weeks; must abort on first
                        data_dir=tmp,
                        delay=0,
                    )

    def test_429_aborts_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                billboard, "ChartData", side_effect=_http_error(429)
            ):
                with self.assertRaises(HardStopError):
                    download_chart(
                        "country-songs",
                        "2024-08-03",
                        "2024-08-31",
                        data_dir=tmp,
                        delay=0,
                    )

    def test_403_does_not_continue_to_next_week(self):
        # Only one ChartData call should happen before the hard stop aborts.
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                billboard, "ChartData", side_effect=_http_error(403)
            ) as mocked:
                with self.assertRaises(HardStopError):
                    download_chart(
                        "country-songs",
                        "2024-08-03",
                        "2024-08-31",
                        data_dir=tmp,
                        delay=0,
                    )
            self.assertEqual(mocked.call_count, 1)


class DownloadChartTolerantErrorTests(unittest.TestCase):
    def test_non_http_error_continues(self):
        # A transient/missing-week error (not 403/429) must not abort the run.
        call = {"n": 0}

        def side_effect(*args, **kwargs):
            call["n"] += 1
            if call["n"] == 1:
                raise ValueError("transient parse glitch")
            return _FakeChart()

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(billboard, "ChartData", side_effect=side_effect):
                # Should NOT raise; first week fails, second succeeds.
                download_chart(
                    "country-songs",
                    "2024-08-03",
                    "2024-08-10",
                    data_dir=tmp,
                    delay=0,
                )
            slug_dir = os.path.join(tmp, "country-songs")
            files = os.listdir(slug_dir)
            # Only the second (successful) week was written.
            self.assertEqual(files, ["2024-08-10.json"])

    def test_404_not_found_continues(self):
        # Pre-launch weeks raise BillboardNotFoundException -> tolerated.
        call = {"n": 0}

        def side_effect(*args, **kwargs):
            call["n"] += 1
            if call["n"] == 1:
                raise billboard.BillboardNotFoundException("no chart that week")
            return _FakeChart()

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(billboard, "ChartData", side_effect=side_effect):
                download_chart(
                    "country-songs",
                    "2024-08-03",
                    "2024-08-10",
                    data_dir=tmp,
                    delay=0,
                )
            slug_dir = os.path.join(tmp, "country-songs")
            self.assertEqual(os.listdir(slug_dir), ["2024-08-10.json"])


if __name__ == "__main__":
    unittest.main()
