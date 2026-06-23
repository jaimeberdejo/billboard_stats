"""Fixture/stub tests for the registry-driven incremental updater (Plan 10-03).

These tests run entirely against an in-memory fake DB + stubbed registry,
loader, and fetcher. They make NO real database connection and NO network
calls. The real-DB full-2-chart run parity + the weekly-green validation are the
operator runbook in docs/ETL-REGISTRY.md, not here.

What these tests pin down (DATA-06 success criteria #1, #4):

* ``update_charts(conn, data_dir=...)`` runs ONE registry-driven incremental
  path: it loops ``iter_charts`` and, per chart, derives the new date window from
  the chart's ``last_loaded_date``, computes which on-disk dates are new, and
  calls ``load_chart`` (which DUAL-WRITES) once per chart that has new weeks --
  replacing the hardcoded hot-100 / billboard-200 branches and the
  ``_load_hot100`` / ``_load_b200`` calls.
* A chart already current through the latest publishable week loads nothing.
* A chart whose on-disk folder is absent/partial is skipped without raising.
* ``build_all_stats`` (BOTH v1.0 ``artist_stats`` AND ``artist_chart_stats``) is
  rebuilt exactly when at least one chart loaded new weeks.
* The path stays INCREMENTAL-ONLY -- it never triggers the multi-decade backfill
  (only per-chart delta downloads bounded by ``last_loaded_date``).
* Module hygiene: ``updater.py`` has no top-level psycopg2 import.

The fetcher (download) + load_chart are stubbed so NO network and NO real DB are
touched; ``iter_charts`` is replaced with an injected fake registry, mirroring
the dependency-injection style of tests/test_migrate_multichart.py.
"""

import datetime
import inspect
import os
import tempfile
import unittest

from billboard_stats.etl import updater
from billboard_stats.etl.chart_registry import ChartRecord


# ============================================================================
# Stub harness: inject a fake registry + stub load_chart / fetcher / stats
# ============================================================================
class _Recorder:
    """Captures load_chart / download / build_all_stats calls (no real work)."""

    def __init__(self):
        self.load_chart_calls = []     # (slug, sorted(only_dates))
        self.downloads = []            # (kind, args) -- proves incremental-only
        self.build_all_stats_calls = 0


class UpdaterRegistryHarness(unittest.TestCase):
    """Patches updater.iter_charts / load_chart / the fetcher downloaders /
    build_all_stats / get_latest_publishable_chart_week so update_charts runs
    over an injected fake registry with NO network and NO real DB."""

    LATEST_WEEK = datetime.date(2026, 6, 20)  # a Saturday

    def setUp(self):
        self.rec = _Recorder()
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = self._tmp.name

        self._saved = {
            "iter_charts": updater.iter_charts,
            "load_chart": updater.load_chart,
            "download_hot100": updater.download_hot100,
            "download_b200": updater.download_b200,
            "download_chart": getattr(updater, "download_chart", None),
            "build_all_stats": updater.build_all_stats,
            "latest_week": updater.get_latest_publishable_chart_week,
        }

        # Default: empty registry; individual tests set self._charts.
        self._charts = []
        updater.iter_charts = lambda conn, data_dir=None, **kw: iter(self._charts)

        def _fake_load_chart(conn, chart, only_dates=None, data_dir=None):
            self.rec.load_chart_calls.append(
                (chart.slug, sorted(only_dates) if only_dates else [])
            )

        updater.load_chart = _fake_load_chart

        def _fake_dl_hot100(*a, **k):
            self.rec.downloads.append(("hot100", a, k))

        def _fake_dl_b200(*a, **k):
            self.rec.downloads.append(("b200", a, k))

        def _fake_dl_chart(*a, **k):
            self.rec.downloads.append(("chart", a, k))

        updater.download_hot100 = _fake_dl_hot100
        updater.download_b200 = _fake_dl_b200
        if hasattr(updater, "download_chart"):
            updater.download_chart = _fake_dl_chart

        def _fake_build_all_stats(conn):
            self.rec.build_all_stats_calls += 1

        updater.build_all_stats = _fake_build_all_stats
        updater.get_latest_publishable_chart_week = lambda *a, **k: self.LATEST_WEEK

    def tearDown(self):
        updater.iter_charts = self._saved["iter_charts"]
        updater.load_chart = self._saved["load_chart"]
        updater.download_hot100 = self._saved["download_hot100"]
        updater.download_b200 = self._saved["download_b200"]
        if self._saved["download_chart"] is not None:
            updater.download_chart = self._saved["download_chart"]
        updater.build_all_stats = self._saved["build_all_stats"]
        updater.get_latest_publishable_chart_week = self._saved["latest_week"]
        self._tmp.cleanup()

    # --- helpers --------------------------------------------------------------
    def _make_folder(self, folder_name, dates):
        """Create data_dir/folder_name/{date}.json for each date string."""
        folder = os.path.join(self.data_dir, folder_name)
        os.makedirs(folder, exist_ok=True)
        for d in dates:
            with open(os.path.join(folder, f"{d}.json"), "w") as f:
                f.write('[{"rank": 1}]')
        return folder

    def _chart(self, slug, folder_name, entity_kind, last_loaded_date,
               legacy_table):
        return ChartRecord(
            slug=slug,
            entity_kind=entity_kind,
            folder=os.path.join(self.data_dir, folder_name),
            last_loaded_date=last_loaded_date,
            legacy_table=legacy_table,
        )


# ----------------------------------------------------------------------------
# Registry-loop + per-chart delta from last_loaded_date
# ----------------------------------------------------------------------------
class UpdateChartsRegistryLoopTests(UpdaterRegistryHarness):
    def test_loops_registry_and_loads_only_new_dates_per_chart(self):
        # hot-100 already loaded through 2026-06-06; on disk there are two newer
        # Saturdays (06-13, 06-20) -> those are the only_dates passed to
        # load_chart. b200 loaded through 2026-06-13; one newer week on disk.
        self._make_folder(
            "hot100", ["2026-06-06", "2026-06-13", "2026-06-20"]
        )
        self._make_folder("b200", ["2026-06-13", "2026-06-20"])
        self._charts = [
            self._chart("hot-100", "hot100", "song",
                        datetime.date(2026, 6, 6),
                        ("hot100_entries", "song_id")),
            self._chart("billboard-200", "b200", "album",
                        datetime.date(2026, 6, 13),
                        ("b200_entries", "album_id")),
        ]

        updater.update_charts(conn=object(), data_dir=self.data_dir)

        by_slug = dict(self.rec.load_chart_calls)
        # load_chart called once per chart that has new dates.
        self.assertEqual(len(self.rec.load_chart_calls), 2)
        self.assertEqual(by_slug["hot-100"], ["2026-06-13", "2026-06-20"])
        self.assertEqual(by_slug["billboard-200"], ["2026-06-20"])

    def test_chart_already_current_loads_nothing(self):
        # hot-100 already loaded through the latest publishable week -> no new
        # dates -> load_chart is NOT called for it.
        self._make_folder("hot100", ["2026-06-13", "2026-06-20"])
        self._charts = [
            self._chart("hot-100", "hot100", "song",
                        self.LATEST_WEEK,  # already current
                        ("hot100_entries", "song_id")),
        ]

        updater.update_charts(conn=object(), data_dir=self.data_dir)

        self.assertEqual(self.rec.load_chart_calls, [])
        # No load happened -> stats are NOT rebuilt.
        self.assertEqual(self.rec.build_all_stats_calls, 0)

    def test_dates_after_latest_publishable_week_are_excluded(self):
        # A file dated AFTER the latest publishable week must NOT be loaded
        # (guards against pre-fetched future weeks).
        self._make_folder(
            "hot100", ["2026-06-13", "2026-06-20", "2026-06-27"]
        )
        self._charts = [
            self._chart("hot-100", "hot100", "song",
                        datetime.date(2026, 6, 6),
                        ("hot100_entries", "song_id")),
        ]

        updater.update_charts(conn=object(), data_dir=self.data_dir)

        by_slug = dict(self.rec.load_chart_calls)
        self.assertEqual(by_slug["hot-100"], ["2026-06-13", "2026-06-20"])


# ----------------------------------------------------------------------------
# Absent / partial folder tolerance
# ----------------------------------------------------------------------------
class UpdateChartsFolderToleranceTests(UpdaterRegistryHarness):
    def test_absent_folder_is_skipped_without_raising(self):
        # The chart's folder does not exist on disk (Phase 7 may not have it /
        # a new chart not ingested until Phase 11). The loop must tolerate it.
        self._charts = [
            self._chart("country-songs", "country-songs", "song",
                        datetime.date(2026, 6, 6), None),
        ]

        # Must not raise.
        updater.update_charts(conn=object(), data_dir=self.data_dir)

        self.assertEqual(self.rec.load_chart_calls, [])
        self.assertEqual(self.rec.build_all_stats_calls, 0)

    def test_chart_with_no_last_loaded_date_is_skipped(self):
        # A chart never loaded yet (last_loaded_date=None) has no incremental
        # start signal -- the weekly INCREMENTAL path must NOT backfill it; it is
        # skipped (full load is run_etl's / Phase 11's job, not the updater).
        self._make_folder(
            "country-songs", ["2026-06-13", "2026-06-20"]
        )
        self._charts = [
            self._chart("country-songs", "country-songs", "song",
                        None, None),
        ]

        updater.update_charts(conn=object(), data_dir=self.data_dir)

        self.assertEqual(self.rec.load_chart_calls, [])
        # No backfill download was triggered for the never-loaded chart.
        self.assertEqual(self.rec.downloads, [])


# ----------------------------------------------------------------------------
# Stats rebuild on change
# ----------------------------------------------------------------------------
class UpdateChartsStatsRebuildTests(UpdaterRegistryHarness):
    def test_build_all_stats_called_once_when_any_chart_loaded(self):
        self._make_folder("hot100", ["2026-06-13", "2026-06-20"])
        self._make_folder("b200", ["2026-06-20"])
        self._charts = [
            self._chart("hot-100", "hot100", "song",
                        datetime.date(2026, 6, 6),
                        ("hot100_entries", "song_id")),
            self._chart("billboard-200", "b200", "album",
                        datetime.date(2026, 6, 13),
                        ("b200_entries", "album_id")),
        ]

        updater.update_charts(conn=object(), data_dir=self.data_dir)

        # Both stats sets rebuilt via a SINGLE build_all_stats call.
        self.assertEqual(self.rec.build_all_stats_calls, 1)

    def test_build_all_stats_not_called_when_nothing_loaded(self):
        # Charts all current -> no load -> no stats rebuild.
        self._make_folder("hot100", ["2026-06-20"])
        self._charts = [
            self._chart("hot-100", "hot100", "song",
                        self.LATEST_WEEK,
                        ("hot100_entries", "song_id")),
        ]

        updater.update_charts(conn=object(), data_dir=self.data_dir)

        self.assertEqual(self.rec.build_all_stats_calls, 0)


# ----------------------------------------------------------------------------
# Incremental-only: download window is bounded by last_loaded_date
# ----------------------------------------------------------------------------
class UpdateChartsIncrementalOnlyTests(UpdaterRegistryHarness):
    def test_download_window_starts_after_last_loaded_date(self):
        # The delta fetch starts the day AFTER last_loaded_date and ends at the
        # latest publishable week -- never a multi-decade backfill.
        self._make_folder("hot100", ["2026-06-13"])
        self._charts = [
            self._chart("hot-100", "hot100", "song",
                        datetime.date(2026, 6, 6),
                        ("hot100_entries", "song_id")),
        ]

        updater.update_charts(conn=object(), data_dir=self.data_dir)

        # Exactly one hot100 download with a start strictly after 2026-06-06.
        hot_dls = [d for d in self.rec.downloads if d[0] == "hot100"]
        self.assertEqual(len(hot_dls), 1)
        _, args, kwargs = hot_dls[0]
        start = (args[0] if args else kwargs.get("start_date"))
        self.assertEqual(start, "2026-06-07")
        # The window never reaches back before the chart's debut (1958).
        self.assertNotIn("1958", str(args) + str(kwargs))


# ----------------------------------------------------------------------------
# Module hygiene: no top-level psycopg2 import
# ----------------------------------------------------------------------------
class UpdaterPostgresFreeTests(unittest.TestCase):
    def test_module_has_no_top_level_psycopg_import(self):
        source = inspect.getsource(updater)
        top_level = [
            l for l in source.splitlines()
            if l.startswith("import ") or l.startswith("from ")
        ]
        self.assertFalse(
            any("psycopg" in l for l in top_level),
            "psycopg2 must not be a top-level import in updater.py",
        )

    def test_update_charts_is_registry_driven(self):
        # The single incremental path loops the registry and calls load_chart.
        src = inspect.getsource(updater.update_charts)
        self.assertIn("iter_charts", src)
        self.assertIn("load_chart", src)
        # The hardcoded legacy loader calls are gone.
        self.assertNotIn("_load_hot100", src)
        self.assertNotIn("_load_b200", src)


# ----------------------------------------------------------------------------
# CR-02: the combined weekly invocation rebuilds stats AT MOST ONCE
# ----------------------------------------------------------------------------
class _FakeConnectionModule:
    """Stand-in for billboard_stats.db.connection so run_update's lazy import
    resolves without psycopg2. Hands back a sentinel conn and records returns."""

    def __init__(self):
        self.conn = object()
        self.returned = []

    def get_conn(self):
        return self.conn

    def put_conn(self, conn):
        self.returned.append(conn)


class RunUpdateSingleRebuildTests(unittest.TestCase):
    """run_update must rebuild stats EXACTLY ONCE across repair + update, and
    pass rebuild_stats=False into each phase so neither rebuilds on its own."""

    def setUp(self):
        import sys

        self._saved = {
            "repair_gaps": updater.repair_gaps,
            "update_charts": updater.update_charts,
            "build_all_stats": updater.build_all_stats,
            "conn_mod": sys.modules.get("billboard_stats.db.connection"),
        }
        self._sys = sys
        self.fake_conn_mod = _FakeConnectionModule()
        sys.modules["billboard_stats.db.connection"] = self.fake_conn_mod

        self.repair_calls = []
        self.update_calls = []
        self.build_all_stats_calls = 0

        def _fake_repair(conn, data_dir=None, rebuild_stats=True):
            self.repair_calls.append({"rebuild_stats": rebuild_stats})
            return {"hot-100": 1, "billboard-200": 0}  # repaired some

        def _fake_update(conn, data_dir=None, rebuild_stats=True):
            self.update_calls.append({"rebuild_stats": rebuild_stats})
            return {"hot-100": 2}  # loaded some

        def _fake_build_all_stats(conn):
            self.build_all_stats_calls += 1

        updater.repair_gaps = _fake_repair
        updater.update_charts = _fake_update
        updater.build_all_stats = _fake_build_all_stats

    def tearDown(self):
        updater.repair_gaps = self._saved["repair_gaps"]
        updater.update_charts = self._saved["update_charts"]
        updater.build_all_stats = self._saved["build_all_stats"]
        if self._saved["conn_mod"] is not None:
            self._sys.modules["billboard_stats.db.connection"] = self._saved["conn_mod"]
        else:
            self._sys.modules.pop("billboard_stats.db.connection", None)

    def test_both_phases_rebuild_stats_once_not_twice(self):
        updater.run_update(repair=True, update=True)
        # Each phase ran with rebuild_stats=False (deferred to run_update).
        self.assertEqual(self.repair_calls, [{"rebuild_stats": False}])
        self.assertEqual(self.update_calls, [{"rebuild_stats": False}])
        # And the single combined rebuild ran EXACTLY ONCE.
        self.assertEqual(self.build_all_stats_calls, 1)

    def test_no_rebuild_when_nothing_loaded(self):
        updater.repair_gaps = lambda conn, data_dir=None, rebuild_stats=True: {
            "hot-100": 0, "billboard-200": 0
        }
        updater.update_charts = lambda conn, data_dir=None, rebuild_stats=True: {}
        updater.run_update(repair=True, update=True)
        self.assertEqual(self.build_all_stats_calls, 0)

    def test_update_only_path_rebuilds_once(self):
        updater.run_update(repair=False, update=True)
        self.assertEqual(self.repair_calls, [])
        self.assertEqual(self.update_calls, [{"rebuild_stats": False}])
        self.assertEqual(self.build_all_stats_calls, 1)


class WeeklyEntrypointIncrementalOnlyTests(unittest.TestCase):
    """CR-02: the weekly script (the cron path, no args) runs the INCREMENTAL
    update only -- it must NOT default to repair + update."""

    def test_run_weekly_etl_defaults_to_update_only(self):
        import os

        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(here, "scripts", "run_weekly_etl.sh")
        with open(script) as f:
            body = f.read()
        # With no args the script forces --update (incremental-only), never the
        # historical gap scan / double stats rebuild.
        self.assertIn('set -- --update', body)
        self.assertIn('"$#" -eq 0', body)


if __name__ == "__main__":
    unittest.main()
