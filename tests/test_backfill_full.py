"""Unit tests for the backward-walking FULL backfill (history depth discovery).

These exercise ``fetcher.download_chart_history`` directly with
``billboard.ChartData`` mocked, so the suite makes NO network calls. They prove
the FULL backfill discovers each chart's true history by walking BACKWARD from
the latest week to the chart's debut, instead of trusting the (misleading)
``first_date`` recorded in ``verified_charts.json`` (which is the current week).

Behavior contract under test:
  - walks backward one Saturday (7 days) at a time from the latest week
  - saves each non-empty week's JSON
  - SKIPS weeks already on disk (resumable cache skip)
  - STOPS at the first before-debut EMPTY / NOT-FOUND week (the debut boundary),
    treating it as natural end-of-history, NOT a loud error
  - a 403/429 raises HardStopError and is NEVER treated as the debut boundary
  - an optional stop_floor bounds a pathological never-empty chart
"""

import datetime
import json
import os
import tempfile
import unittest
from unittest import mock

import requests

import billboard

from billboard_stats.etl import fetcher
from billboard_stats.etl.fetcher import HardStopError, download_chart_history


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
    """A chart with n entries (n == 0 means a before-debut empty week)."""

    def __init__(self, n=3):
        self.entries = [_fake_entry(i + 1) for i in range(n)]

    def __iter__(self):
        return iter(self.entries)


def _http_error(status):
    resp = mock.Mock()
    resp.status_code = status
    return requests.exceptions.HTTPError(f"{status} error", response=resp)


# A fixed "today" so the latest publishable week is deterministic.
# 2024-08-10 is itself a Saturday, so it is the latest week.
_AS_OF = datetime.date(2024, 8, 10)
_LATEST = datetime.date(2024, 8, 10)


class BackwardWalkTests(unittest.TestCase):
    def test_walks_backward_and_stops_at_debut_empty(self):
        # The chart has data for the latest 3 weeks, then an empty week (debut
        # boundary). The walk must save exactly those 3 weeks and stop.
        debut_empty = (_LATEST - datetime.timedelta(weeks=3)).isoformat()
        with_data = {
            _LATEST.isoformat(),
            (_LATEST - datetime.timedelta(weeks=1)).isoformat(),
            (_LATEST - datetime.timedelta(weeks=2)).isoformat(),
        }

        def side_effect(slug, date=None, timeout=None):
            if date in with_data:
                return _FakeChart(3)
            return _FakeChart(0)  # before debut: zero entries

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(billboard, "ChartData", side_effect=side_effect):
                result = download_chart_history(
                    "artist-100", data_dir=tmp, delay=0, as_of=_AS_OF,
                )

            slug_dir = os.path.join(tmp, "artist-100")
            saved = sorted(os.listdir(slug_dir))
            self.assertEqual(saved, sorted(f"{d}.json" for d in with_data))
            # The empty debut week is NOT written.
            self.assertNotIn(f"{debut_empty}.json", saved)

        self.assertEqual(result["saved"], 3)
        self.assertEqual(result["reason"], "debut")
        self.assertEqual(
            result["earliest"], (_LATEST - datetime.timedelta(weeks=2)).isoformat()
        )

    def test_stops_at_debut_not_found(self):
        # A BillboardNotFoundException (404) at the deep end is also a clean
        # debut boundary, not an error.
        latest_str = _LATEST.isoformat()

        def side_effect(slug, date=None, timeout=None):
            if date == latest_str:
                return _FakeChart(3)
            raise billboard.BillboardNotFoundException("no chart that week")

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(billboard, "ChartData", side_effect=side_effect):
                result = download_chart_history(
                    "artist-100", data_dir=tmp, delay=0, as_of=_AS_OF,
                )
            self.assertEqual(
                sorted(os.listdir(os.path.join(tmp, "artist-100"))),
                [f"{latest_str}.json"],
            )
        self.assertEqual(result["saved"], 1)
        self.assertEqual(result["reason"], "debut")

    def test_skips_cached_weeks(self):
        # A week already on disk is skipped (no ChartData call for it) and the
        # walk still reaches the debut boundary. Resumability.
        latest_str = _LATEST.isoformat()
        wk1 = (_LATEST - datetime.timedelta(weeks=1)).isoformat()
        with_data = {latest_str, wk1}

        with tempfile.TemporaryDirectory() as tmp:
            slug_dir = os.path.join(tmp, "artist-100")
            os.makedirs(slug_dir)
            # Pre-seed the latest week (comfortably above MIN_FILE_SIZE).
            cached = os.path.join(slug_dir, f"{latest_str}.json")
            with open(cached, "w") as f:
                f.write("[" + ("0" * fetcher.MIN_FILE_SIZE) + "]")

            calls = []

            def side_effect(slug, date=None, timeout=None):
                calls.append(date)
                if date in with_data:
                    return _FakeChart(3)
                return _FakeChart(0)

            with mock.patch.object(billboard, "ChartData", side_effect=side_effect):
                result = download_chart_history(
                    "artist-100", data_dir=tmp, delay=0, as_of=_AS_OF,
                )

            # The cached latest week was NEVER fetched.
            self.assertNotIn(latest_str, calls)
            # wk1 was fetched and saved.
            self.assertIn(f"{wk1}.json", os.listdir(slug_dir))

        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["saved"], 1)
        self.assertEqual(result["reason"], "debut")

    def test_hard_stop_403_propagates_not_debut(self):
        # A 403 must raise HardStopError and must NOT be misread as the debut
        # boundary (which would silently truncate history).
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                billboard, "ChartData", side_effect=_http_error(403)
            ):
                with self.assertRaises(HardStopError):
                    download_chart_history(
                        "artist-100", data_dir=tmp, delay=0, as_of=_AS_OF,
                    )

    def test_hard_stop_429_propagates(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                billboard, "ChartData", side_effect=_http_error(429)
            ):
                with self.assertRaises(HardStopError):
                    download_chart_history(
                        "artist-100", data_dir=tmp, delay=0, as_of=_AS_OF,
                    )

    def test_stop_floor_bounds_a_never_empty_chart(self):
        # A pathological chart that ALWAYS returns data must still terminate at
        # stop_floor instead of walking back forever.
        floor = _LATEST - datetime.timedelta(weeks=2)

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                billboard, "ChartData", return_value=_FakeChart(3)
            ):
                result = download_chart_history(
                    "artist-100", data_dir=tmp, delay=0, as_of=_AS_OF,
                    stop_floor=floor,
                )
            # latest, latest-1, latest-2 == 3 weeks down to (inclusive) the floor.
            self.assertEqual(result["saved"], 3)
            self.assertEqual(result["reason"], "floor")

    def test_empty_tolerance_allows_one_missing_midweek(self):
        # With empty_tolerance=2, a single empty mid-history week does not end
        # the walk; only TWO consecutive empties (the true debut) stops it.
        latest_str = _LATEST.isoformat()
        wk1 = (_LATEST - datetime.timedelta(weeks=1)).isoformat()  # empty (gap)
        wk2 = (_LATEST - datetime.timedelta(weeks=2)).isoformat()  # data again
        # wk3, wk4 empty -> two consecutive -> debut boundary.

        def side_effect(slug, date=None, timeout=None):
            if date in (latest_str, wk2):
                return _FakeChart(3)
            return _FakeChart(0)

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(billboard, "ChartData", side_effect=side_effect):
                result = download_chart_history(
                    "artist-100", data_dir=tmp, delay=0, as_of=_AS_OF,
                    empty_tolerance=2,
                )
            saved = sorted(os.listdir(os.path.join(tmp, "artist-100")))
            self.assertEqual(saved, sorted([f"{latest_str}.json", f"{wk2}.json"]))
            self.assertNotIn(f"{wk1}.json", saved)  # the gap week stays unwritten

        self.assertEqual(result["saved"], 2)
        self.assertEqual(result["reason"], "debut")


if __name__ == "__main__":
    unittest.main()
