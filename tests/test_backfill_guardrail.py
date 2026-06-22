"""Unit tests for the offline backfill orchestrator + its cron guardrail.

``download_chart`` and the ``verified_charts.json`` sidecar are both mocked so
the suite makes NO network calls and never touches the real sidecar on disk.

Covers the Task-1 behavior contract:
  - smoke mode targets ONLY verified slugs with a small recent window
  - full mode uses each chart's captured ``first_date``
  - run_backfill ABORTS in a scheduled-cron context with no manual marker
  - run_backfill propagates the download_chart 403/429 hard stop
  - run_backfill never scrapes an unverified slug
"""

import json
import os
import tempfile
import unittest
from unittest import mock

from billboard_stats.etl import backfill
from billboard_stats.etl.backfill import BackfillGuardrailError, run_backfill
from billboard_stats.etl.fetcher import HardStopError


# A stable verified sidecar with two slugs and known first_dates.
_FAKE_SIDECAR = [
    {"slug": "country-songs", "first_date": "2014-01-04", "first_date_unknown": False},
    {"slug": "artist-100", "first_date": "2014-07-19", "first_date_unknown": False},
]


def _write_sidecar(path, payload=None):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload if payload is not None else _FAKE_SIDECAR, f)


# A fixed "latest publishable week" so tests are deterministic regardless of today.
_FIXED_LATEST = __import__("datetime").date(2024, 8, 10)


class _ManualEnv(dict):
    """An env mapping that simulates a legitimate manual run (BACKFILL_ALLOW=1)."""


def _manual_env():
    return {"BACKFILL_ALLOW": "1"}


def _schedule_env():
    return {"GITHUB_EVENT_NAME": "schedule"}


class GuardrailTests(unittest.TestCase):
    def test_aborts_on_scheduled_cron_without_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = os.path.join(tmp, "verified_charts.json")
            _write_sidecar(sidecar)
            with mock.patch.object(backfill, "download_chart") as dl:
                with self.assertRaises(BackfillGuardrailError):
                    run_backfill(
                        mode="smoke",
                        data_dir=tmp,
                        sidecar_path=sidecar,
                        env=_schedule_env(),
                    )
                dl.assert_not_called()

    def test_aborts_when_marker_not_set(self):
        # No GITHUB_EVENT_NAME, but BACKFILL_ALLOW absent -> still refuse.
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = os.path.join(tmp, "verified_charts.json")
            _write_sidecar(sidecar)
            with mock.patch.object(backfill, "download_chart") as dl:
                with self.assertRaises(BackfillGuardrailError):
                    run_backfill(
                        mode="smoke",
                        data_dir=tmp,
                        sidecar_path=sidecar,
                        env={},
                    )
                dl.assert_not_called()

    def test_schedule_marker_overrides_allow(self):
        # Even with BACKFILL_ALLOW=1, a scheduled-cron context must abort.
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = os.path.join(tmp, "verified_charts.json")
            _write_sidecar(sidecar)
            with mock.patch.object(backfill, "download_chart") as dl:
                with self.assertRaises(BackfillGuardrailError):
                    run_backfill(
                        mode="smoke",
                        data_dir=tmp,
                        sidecar_path=sidecar,
                        env={"GITHUB_EVENT_NAME": "schedule", "BACKFILL_ALLOW": "1"},
                    )
                dl.assert_not_called()

    def test_allow_flag_sets_marker(self):
        # allow=True should satisfy the guardrail even with an empty env.
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = os.path.join(tmp, "verified_charts.json")
            _write_sidecar(sidecar)
            with mock.patch.object(backfill, "download_chart") as dl, mock.patch.object(
                backfill, "get_latest_publishable_chart_week", return_value=_FIXED_LATEST
            ):
                run_backfill(
                    mode="smoke",
                    data_dir=tmp,
                    sidecar_path=sidecar,
                    env={},
                    allow=True,
                )
                self.assertTrue(dl.called)


class SmokeModeTests(unittest.TestCase):
    def test_smoke_targets_only_verified_slugs_small_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = os.path.join(tmp, "verified_charts.json")
            _write_sidecar(sidecar)
            with mock.patch.object(backfill, "download_chart") as dl, mock.patch.object(
                backfill, "get_latest_publishable_chart_week", return_value=_FIXED_LATEST
            ):
                run_backfill(
                    mode="smoke",
                    data_dir=tmp,
                    sidecar_path=sidecar,
                    env=_manual_env(),
                    smoke_weeks=4,
                )

            called_slugs = [c.kwargs.get("slug", c.args[0]) for c in dl.call_args_list]
            self.assertEqual(sorted(called_slugs), ["artist-100", "country-songs"])

            # Each call uses a small recent window ending at the latest week.
            for c in dl.call_args_list:
                kwargs = c.kwargs
                end = kwargs.get("end_date", c.args[2] if len(c.args) > 2 else None)
                start = kwargs.get("start_date", c.args[1] if len(c.args) > 1 else None)
                self.assertEqual(end, _FIXED_LATEST.isoformat())
                # ~4 weeks earlier (28 days), not a multi-decade start.
                self.assertEqual(start, "2024-07-13")

    def test_smoke_skips_unverified_slug(self):
        # download_chart must never be called for a slug not in the sidecar.
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = os.path.join(tmp, "verified_charts.json")
            _write_sidecar(sidecar)
            with mock.patch.object(backfill, "download_chart") as dl, mock.patch.object(
                backfill, "get_latest_publishable_chart_week", return_value=_FIXED_LATEST
            ):
                run_backfill(
                    mode="smoke",
                    data_dir=tmp,
                    sidecar_path=sidecar,
                    env=_manual_env(),
                )
            called_slugs = [c.kwargs.get("slug", c.args[0]) for c in dl.call_args_list]
            self.assertNotIn("rock-songs", called_slugs)
            self.assertNotIn("hot-100", called_slugs)


class FullModeTests(unittest.TestCase):
    def test_full_uses_each_charts_first_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = os.path.join(tmp, "verified_charts.json")
            _write_sidecar(sidecar)
            with mock.patch.object(backfill, "download_chart") as dl, mock.patch.object(
                backfill, "get_latest_publishable_chart_week", return_value=_FIXED_LATEST
            ):
                run_backfill(
                    mode="full",
                    data_dir=tmp,
                    sidecar_path=sidecar,
                    env=_manual_env(),
                )

            starts = {}
            for c in dl.call_args_list:
                slug = c.kwargs.get("slug", c.args[0])
                start = c.kwargs.get("start_date", c.args[1] if len(c.args) > 1 else None)
                end = c.kwargs.get("end_date", c.args[2] if len(c.args) > 2 else None)
                starts[slug] = start
                self.assertEqual(end, _FIXED_LATEST.isoformat())

            self.assertEqual(starts["country-songs"], "2014-01-04")
            self.assertEqual(starts["artist-100"], "2014-07-19")

    def test_full_single_slug_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = os.path.join(tmp, "verified_charts.json")
            _write_sidecar(sidecar)
            with mock.patch.object(backfill, "download_chart") as dl, mock.patch.object(
                backfill, "get_latest_publishable_chart_week", return_value=_FIXED_LATEST
            ):
                run_backfill(
                    mode="full",
                    slug="artist-100",
                    data_dir=tmp,
                    sidecar_path=sidecar,
                    env=_manual_env(),
                )
            called_slugs = [c.kwargs.get("slug", c.args[0]) for c in dl.call_args_list]
            self.assertEqual(called_slugs, ["artist-100"])

    def test_full_unverified_single_slug_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = os.path.join(tmp, "verified_charts.json")
            _write_sidecar(sidecar)
            with mock.patch.object(backfill, "download_chart"), mock.patch.object(
                backfill, "get_latest_publishable_chart_week", return_value=_FIXED_LATEST
            ):
                with self.assertRaises(ValueError):
                    run_backfill(
                        mode="full",
                        slug="not-a-verified-slug",
                        data_dir=tmp,
                        sidecar_path=sidecar,
                        env=_manual_env(),
                    )


class HardStopPropagationTests(unittest.TestCase):
    def test_hard_stop_propagates(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = os.path.join(tmp, "verified_charts.json")
            _write_sidecar(sidecar)
            with mock.patch.object(
                backfill, "download_chart", side_effect=HardStopError("HTTP 429")
            ), mock.patch.object(
                backfill, "get_latest_publishable_chart_week", return_value=_FIXED_LATEST
            ):
                with self.assertRaises(HardStopError):
                    run_backfill(
                        mode="smoke",
                        data_dir=tmp,
                        sidecar_path=sidecar,
                        env=_manual_env(),
                    )


class MissingSidecarTests(unittest.TestCase):
    def test_missing_sidecar_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "does_not_exist.json")
            with mock.patch.object(backfill, "download_chart"):
                with self.assertRaises(FileNotFoundError):
                    run_backfill(
                        mode="smoke",
                        data_dir=tmp,
                        sidecar_path=missing,
                        env=_manual_env(),
                    )


class PostgresFreeTests(unittest.TestCase):
    def test_no_psycopg_import(self):
        import inspect

        src = inspect.getsource(backfill)
        self.assertNotIn("psycopg", src)


if __name__ == "__main__":
    unittest.main()
