"""Unit tests for the curated-chart slug list and verify_slugs.

billboard.ChartData is mocked throughout so the suite makes NO network calls.
"""

import json
import unittest
from unittest import mock

import billboard

from billboard_stats.etl import charts
from billboard_stats.etl.charts import (
    CURATED_CHARTS,
    SlugVerificationError,
    get_chart,
    verify_slug,
    verify_slugs,
)


def _fake_entry():
    return mock.Mock()


class _FakeChart:
    """A ChartData-like stand-in that is re-iterable (like the real object)."""

    def __init__(self, date="2024-08-10", previous_date="2024-08-03", n_entries=10):
        self.date = date
        self.previousDate = previous_date
        self.entries = [_fake_entry() for _ in range(n_entries)]

    def __iter__(self):
        return iter(self.entries)

    def __len__(self):
        return len(self.entries)


def _fake_chart(date="2024-08-10", previous_date="2024-08-03", n_entries=10):
    """Build a fresh re-iterable fake ChartData object."""
    return _FakeChart(date=date, previous_date=previous_date, n_entries=n_entries)


class CuratedChartsShapeTests(unittest.TestCase):
    def test_curated_set_has_expected_counts(self):
        kinds = [c["entity_kind"] for c in CURATED_CHARTS]
        self.assertEqual(len(CURATED_CHARTS), 9)
        self.assertEqual(kinds.count("song"), 4)
        self.assertEqual(kinds.count("album"), 4)
        self.assertEqual(kinds.count("artist"), 1)

    def test_includes_artist_100(self):
        slugs = [c["slug"] for c in CURATED_CHARTS]
        self.assertIn("artist-100", slugs)

    def test_get_chart_lookup(self):
        self.assertEqual(get_chart("artist-100")["title"], "Artist 100")
        self.assertIsNone(get_chart("does-not-exist"))


class VerifySlugSuccessTests(unittest.TestCase):
    def test_slug_with_entries_is_verified_with_first_date(self):
        with mock.patch.object(
            billboard, "ChartData", return_value=_fake_chart()
        ) as mocked:
            result = verify_slug("country-songs")

        # verify_slug bounds verification latency with an explicit timeout
        # (mirrors download_chart), so it must not fall back to the library
        # default of 25s x retries.
        mocked.assert_called_once_with("country-songs", timeout=20)
        self.assertEqual(result["slug"], "country-songs")
        self.assertTrue(result["verified"])
        self.assertIsNotNone(result["first_date"])
        self.assertEqual(result["entry_count"], 10)

    def test_first_date_prefers_previous_date_then_date(self):
        # previousDate is older than date, so first_date should be previousDate
        with mock.patch.object(
            billboard,
            "ChartData",
            return_value=_fake_chart(date="2024-08-10", previous_date="2024-08-03"),
        ):
            result = verify_slug("country-songs")
        self.assertEqual(result["first_date"], "2024-08-03")

    def test_first_date_null_is_flagged_not_today(self):
        # Neither date nor previousDate available -> null first_date, flagged.
        chart = _fake_chart(date=None, previous_date=None, n_entries=5)
        with mock.patch.object(billboard, "ChartData", return_value=chart):
            result = verify_slug("country-songs")
        self.assertTrue(result["verified"])
        self.assertIsNone(result["first_date"])
        self.assertTrue(result["first_date_unknown"])


class VerifySlugFailureTests(unittest.TestCase):
    def test_library_not_found_error_fails_loudly(self):
        err = billboard.BillboardNotFoundException("not found")
        with mock.patch.object(billboard, "ChartData", side_effect=err):
            with self.assertRaises(SlugVerificationError) as ctx:
                verify_slug("bogus-slug")
        # The error must name the offending slug.
        self.assertIn("bogus-slug", str(ctx.exception))

    def test_http_error_fails_loudly(self):
        import requests

        with mock.patch.object(
            billboard, "ChartData", side_effect=requests.exceptions.HTTPError("403")
        ):
            with self.assertRaises(SlugVerificationError) as ctx:
                verify_slug("country-songs")
        self.assertIn("country-songs", str(ctx.exception))

    def test_zero_entries_fails_loudly(self):
        empty = _fake_chart(n_entries=0)
        with mock.patch.object(billboard, "ChartData", return_value=empty):
            with self.assertRaises(SlugVerificationError) as ctx:
                verify_slug("renamed-empty-slug")
        self.assertIn("renamed-empty-slug", str(ctx.exception))
        self.assertIn("zero", str(ctx.exception).lower())


class VerifySlugsSetTests(unittest.TestCase):
    def test_verify_all_succeeds_and_writes_sidecar(self):
        tmp = self.id().replace(".", "_") + ".json"
        try:
            with mock.patch.object(
                billboard, "ChartData", return_value=_fake_chart()
            ):
                results = verify_slugs(
                    CURATED_CHARTS, sidecar_path=tmp, raise_on_failure=True, delay=0
                )
            self.assertEqual(len(results), len(CURATED_CHARTS))
            self.assertTrue(all(r["verified"] for r in results))
            with open(tmp, encoding="utf-8") as f:
                sidecar = json.load(f)
            self.assertEqual(len(sidecar), len(CURATED_CHARTS))
            self.assertIn("first_date", sidecar[0])
        finally:
            import os

            if os.path.exists(tmp):
                os.remove(tmp)

    def test_verify_all_raises_on_any_failure_and_names_slug(self):
        # First slug fails -> the whole set fails loudly, no sidecar written.
        tmp = self.id().replace(".", "_") + ".json"

        def fake_chartdata(slug):
            if slug == CURATED_CHARTS[0]["slug"]:
                raise billboard.BillboardNotFoundException("nope")
            return _fake_chart()

        try:
            with mock.patch.object(billboard, "ChartData", side_effect=fake_chartdata):
                with self.assertRaises(SlugVerificationError) as ctx:
                    verify_slugs(
                        CURATED_CHARTS, sidecar_path=tmp, raise_on_failure=True, delay=0
                    )
            self.assertIn(CURATED_CHARTS[0]["slug"], str(ctx.exception))
            import os

            self.assertFalse(os.path.exists(tmp))
        finally:
            import os

            if os.path.exists(tmp):
                os.remove(tmp)


if __name__ == "__main__":
    unittest.main()
