"""Fixture-DB tests for the read-only gender coverage report (Plan 12-02).

Runs entirely against an in-memory fake DB (no real DB, no network), mirroring
the repo's unittest idiom. The actual MEASUREMENT against the real loaded +
enriched artist table is a DEFERRED operator step (docs/GENDER-ENRICHMENT.md).
"""

import re
import unittest

from billboard_stats.etl import gender_coverage
from billboard_stats.etl.gender_coverage import coverage_report


class FakeCursor:
    """Interprets the read-only aggregation SQL coverage_report() emits."""

    def __init__(self, db):
        self._db = db
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        norm = re.sub(r"\s+", " ", sql).strip().lower()

        if norm.startswith("select count(*) from artists"):
            self._result = [(len(self._db["artists"]),)]
            return

        if norm.startswith("select gender, count(*) from artists group by gender"):
            counts = {}
            for a in self._db["artists"]:
                counts[a["gender"]] = counts.get(a["gender"], 0) + 1
            self._result = list(counts.items())
            return

        if norm.startswith(
            "select gender_source, count(*) from artists group by gender_source"
        ):
            counts = {}
            for a in self._db["artists"]:
                src = a.get("gender_source")
                counts[src] = counts.get(src, 0) + 1
            self._result = list(counts.items())
            return

        # Weighted coverage queries (optional).
        if "from artist_chart_stats" in norm and "join artists" not in norm:
            if "artist_chart_stats" not in self._db:
                raise RuntimeError("relation artist_chart_stats does not exist")
            total = sum(r["total_weeks"] for r in self._db["artist_chart_stats"])
            self._result = [(total,)]
            return

        if "from artist_chart_stats" in norm and "join artists" in norm:
            if "artist_chart_stats" not in self._db:
                raise RuntimeError("relation artist_chart_stats does not exist")
            gender_by_id = {a["id"]: a["gender"] for a in self._db["artists"]}
            total = sum(
                r["total_weeks"]
                for r in self._db["artist_chart_stats"]
                if gender_by_id.get(r["artist_id"], "unknown") != "unknown"
            )
            self._result = [(total,)]
            return

        raise AssertionError(f"FakeCursor: unhandled SQL: {norm!r}")

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0]


class FakeConn:
    def __init__(self, db):
        self._db = db

    def cursor(self):
        return FakeCursor(self._db)


def _artist(aid, gender, source=None):
    return {"id": aid, "gender": gender, "gender_source": source}


class CoverageReportTests(unittest.TestCase):
    def test_basic_match_rate_and_distribution(self):
        db = {
            "artists": [
                _artist(1, "female", "musicbrainz"),
                _artist(2, "male", "musicbrainz"),
                _artist(3, "group", "wikidata"),
                _artist(4, "unknown", None),
                _artist(5, "unknown", None),
            ]
        }
        report = coverage_report(FakeConn(db))

        self.assertEqual(report["total"], 5)
        self.assertEqual(report["matched"], 3)  # 5 total - 2 unknown
        self.assertAlmostEqual(report["match_rate"], 3 / 5)

        dist = report["distribution"]
        self.assertEqual(dist["female"]["count"], 1)
        self.assertEqual(dist["male"]["count"], 1)
        self.assertEqual(dist["group"]["count"], 1)
        self.assertEqual(dist["mixed"]["count"], 0)
        self.assertEqual(dist["unknown"]["count"], 2)
        self.assertAlmostEqual(dist["unknown"]["pct"], 2 / 5)

    def test_by_source_breakdown(self):
        db = {
            "artists": [
                _artist(1, "female", "musicbrainz"),
                _artist(2, "male", "musicbrainz"),
                _artist(3, "group", "wikidata"),
                _artist(4, "mixed", "manual"),
                _artist(5, "unknown", None),
            ]
        }
        report = coverage_report(FakeConn(db))
        by_source = report["by_source"]
        self.assertEqual(by_source["musicbrainz"]["count"], 2)
        self.assertEqual(by_source["wikidata"]["count"], 1)
        self.assertEqual(by_source["manual"]["count"], 1)
        self.assertEqual(by_source["none"]["count"], 1)

    def test_empty_table_is_divide_by_zero_safe(self):
        report = coverage_report(FakeConn({"artists": []}))
        self.assertEqual(report["total"], 0)
        self.assertEqual(report["matched"], 0)
        self.assertEqual(report["match_rate"], 0.0)
        # Distribution still reports all 5 vocab buckets at 0.
        for value in ("female", "male", "group", "mixed", "unknown"):
            self.assertEqual(report["distribution"][value]["count"], 0)
            self.assertEqual(report["distribution"][value]["pct"], 0.0)

    def test_all_unknown_zero_match_rate(self):
        db = {"artists": [_artist(1, "unknown"), _artist(2, "unknown")]}
        report = coverage_report(FakeConn(db))
        self.assertEqual(report["match_rate"], 0.0)
        self.assertEqual(report["matched"], 0)

    def test_weighted_coverage(self):
        db = {
            "artists": [
                _artist(1, "female", "musicbrainz"),
                _artist(2, "unknown", None),
            ],
            "artist_chart_stats": [
                {"artist_id": 1, "total_weeks": 30},
                {"artist_id": 2, "total_weeks": 10},
            ],
        }
        report = coverage_report(FakeConn(db), weighted=True)
        w = report["weighted"]
        self.assertEqual(w["total_weight"], 40)
        self.assertEqual(w["matched_weight"], 30)
        self.assertAlmostEqual(w["match_rate"], 30 / 40)

    def test_weighted_coverage_graceful_when_table_absent(self):
        db = {"artists": [_artist(1, "female", "musicbrainz")]}  # no artist_chart_stats
        report = coverage_report(FakeConn(db), weighted=True)
        self.assertIsNone(report["weighted"])


class CoveragePostgresFreeTests(unittest.TestCase):
    def test_module_has_no_top_level_psycopg_import(self):
        import inspect

        src = inspect.getsource(gender_coverage)
        lines = src.splitlines()
        top_level = [
            l for l in lines if l.startswith("import ") or l.startswith("from ")
        ]
        self.assertFalse(
            any("psycopg" in l for l in top_level),
            "psycopg2 must not be a top-level import",
        )


if __name__ == "__main__":
    unittest.main()
