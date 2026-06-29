"""Registry-driven incremental chart update and data gap repair.

This is the WEEKLY path (Plan 10-03, DATA-06 success criterion #4). It runs ONE
registry-driven incremental update: it loops the chart registry
(:func:`billboard_stats.etl.chart_registry.iter_charts`) and, per chart, derives
the new date window from that chart's ``last_loaded_date``, fetches just the
delta, and calls :func:`billboard_stats.etl.loader.load_chart` (which writes
the single ``chart_entries`` store for every chart — the legacy
``hot100_entries`` / ``b200_entries`` dual-write was retired in Phase 15) —
replacing the hardcoded hot-100 / billboard-200 branches and the old
``_load_hot100`` / ``_load_b200`` calls. After loading, when any chart got new
weeks, it rebuilds BOTH the ``artist_stats`` and the new
``artist_chart_stats`` via :func:`build_all_stats`.

INCREMENTAL-ONLY: the weekly path NEVER triggers the multi-decade backfill. Each
chart's fetch window starts the day AFTER its ``last_loaded_date`` and ends at
the latest publishable chart week; a chart that has never been loaded
(``last_loaded_date is None``) is SKIPPED here (the full first load is
:func:`run_etl`'s / Phase 11's job, not the weekly updater). A chart whose
on-disk folder is absent/partial is logged and skipped, never a crash.

psycopg2 is NEVER a top-level import (mirrors chart_registry.py /
migrate_multichart.py): ``get_conn`` / ``put_conn`` and ``load_chart`` are
imported lazily inside the functions that need them, so this module imports
cleanly in the psycopg2-free test environment and the tests inject a fake
registry + stub ``load_chart`` / the fetcher (no real DB, no network).

Usage:
    python -m billboard_stats.etl.updater          # run update + gap repair
    python -m billboard_stats.etl.updater --repair  # gap repair only
    python -m billboard_stats.etl.updater --update  # incremental update only

Suggested crontab (Monday 6 AM):
    0 6 * * 1 cd /path/to/billboard_stats && python -m billboard_stats.etl.updater
"""

from __future__ import annotations

import datetime
import logging
import os
from pathlib import Path

from billboard_stats.etl.chart_registry import iter_charts
from billboard_stats.etl.fetcher import (
    DATA_DIR,
    download_b200,
    download_chart,
    download_hot100,
    find_failed_downloads,
    get_latest_publishable_chart_week,
)
from billboard_stats.etl.stats_builder import build_all_stats

logger = logging.getLogger(__name__)

# psycopg2-free hygiene: the loader imports psycopg2/execute_values at top level
# (it is operator-run), so updater.py does NOT import it eagerly. ``load_chart``
# is resolved lazily on first use via :func:`_get_load_chart` and cached here, so
# tests can also inject a stub by assigning ``updater.load_chart`` directly.
load_chart = None


def _get_load_chart():
    """Return the loader's ``load_chart``, importing it lazily on first use.

    Lazy so this module imports cleanly without psycopg2 (the fake-DB tests
    inject a stub by setting ``updater.load_chart`` before calling
    :func:`update_charts`); only the real operator-run path triggers the import.
    """
    global load_chart
    if load_chart is None:
        from billboard_stats.etl.loader import load_chart as _lc

        load_chart = _lc
    return load_chart


def _fetch_chart_delta(chart, start_date: str, end_date: str, data_dir: str):
    """Fetch one chart's incremental delta with the chart-appropriate downloader.

    The two LEGACY charts keep their existing fetch behavior (their on-disk
    folders are ``hot100`` / ``b200``, NOT the slug), so they use
    :func:`download_hot100` / :func:`download_b200`. Every other chart's folder
    IS its slug, so it uses the generic slug downloader
    :func:`download_chart`. INCREMENTAL-ONLY: the window is always
    ``[start_date, end_date]`` bounded by ``last_loaded_date`` — never a
    multi-decade backfill.
    """
    if chart.slug == "hot-100":
        download_hot100(start_date, end_date, data_dir)
    elif chart.slug == "billboard-200":
        download_b200(data_dir=data_dir, start_date=start_date, end_date=end_date)
    else:
        download_chart(chart.slug, start_date, end_date, data_dir)


def _new_on_disk_dates(folder: str, last_loaded, latest_valid_week) -> list:
    """Return the ISO date strings on disk that are NEW for this chart.

    A date is new when ``last_loaded < d <= latest_valid_week``. Tolerant of an
    absent folder (returns ``[]``). The window upper bound excludes any
    pre-fetched future week beyond the latest publishable chart week.
    """
    if not os.path.isdir(folder):
        return []
    new_dates = []
    for fname in sorted(os.listdir(folder)):
        if not fname.endswith(".json"):
            continue
        date_str = fname[: -len(".json")]
        try:
            d = datetime.date.fromisoformat(date_str)
        except ValueError:
            continue
        if last_loaded < d <= latest_valid_week:
            new_dates.append(date_str)
    return new_dates


def update_charts(conn, data_dir: str = None, rebuild_stats: bool = True) -> dict:
    """Registry-driven incremental update over EVERY registered chart.

    ONE incremental path (replacing the hardcoded hot-100 / billboard-200
    branches): loop :func:`iter_charts`, and for each chart derive its delta
    window from ``last_loaded_date`` (the day after, through
    :func:`get_latest_publishable_chart_week`), fetch the delta with the
    chart-appropriate downloader, compute which on-disk dates are new, and call
    :func:`load_chart` (single-write to ``chart_entries`` — the legacy dual-write
    was retired in Phase 15) with those ``only_dates``. After the
    loop, when any chart loaded new weeks, rebuild BOTH stats sets via
    :func:`build_all_stats`.

    INCREMENTAL-ONLY: never triggers the multi-decade backfill. A chart with
    ``last_loaded_date is None`` (never loaded) is SKIPPED — the weekly path does
    not first-load a chart (that is :func:`run_etl` / Phase 11). A chart whose
    on-disk folder is absent/partial is logged and skipped, never a crash.

    repair_gaps (below) keeps its legacy-folder logic for the two core charts
    only; new charts are not gap-repaired until Phase 11 — intentionally not
    over-scoped here.

    Args:
        conn: Database connection (real psycopg2 at operator-time, a fake in
            tests). ``load_chart`` is imported lazily so this module stays
            psycopg2-free at import time.
        data_dir: Root data directory containing the per-chart subdirectories.
        rebuild_stats: When True (default, the standalone path) rebuild stats
            here after loading. The combined weekly path (:func:`run_update`)
            passes False so stats are rebuilt EXACTLY ONCE at the end across both
            repair + update, instead of twice (CR-02).

    Returns:
        ``{chart_slug: n_weeks_loaded}`` for every chart that loaded new weeks.
    """
    # Resolve load_chart lazily (psycopg2-free import hygiene). Tests inject a
    # stub by setting updater.load_chart before calling this; that wins.
    _load_chart = load_chart if load_chart is not None else _get_load_chart()

    if data_dir is None:
        data_dir = DATA_DIR

    latest_valid_week = get_latest_publishable_chart_week()
    loaded = {}  # slug -> count of new weeks loaded

    for chart in iter_charts(conn, data_dir=data_dir):
        last_loaded = chart.last_loaded_date

        # Never-loaded charts are NOT first-loaded by the weekly incremental
        # path (no incremental start signal). Their full first load is run_etl /
        # Phase 11, not this updater. Skip without backfilling.
        if last_loaded is None:
            logger.warning(
                "Skipping %s: no existing data (last_loaded_date is None). "
                "Run the full ETL first; the weekly path is incremental-only.",
                chart.slug,
            )
            continue

        # Tolerate an absent/partial on-disk folder (Phase 7 may not have it).
        if not os.path.isdir(chart.folder):
            logger.warning(
                "Skipping %s: data folder not found: %s",
                chart.slug,
                chart.folder,
            )
            continue

        # Fetch only the delta since last_loaded_date (incremental-only).
        if last_loaded < latest_valid_week:
            start = (last_loaded + datetime.timedelta(days=1)).isoformat()
            end = latest_valid_week.isoformat()
            logger.info("%s: fetching delta %s..%s", chart.slug, start, end)
            _fetch_chart_delta(chart, start, end, data_dir)
        else:
            logger.info(
                "%s: already current through the latest valid chart week.",
                chart.slug,
            )

        new_dates = _new_on_disk_dates(chart.folder, last_loaded, latest_valid_week)
        if not new_dates:
            logger.info("%s: no new weeks to load.", chart.slug)
            continue

        logger.info("Loading %d new %s week(s)...", len(new_dates), chart.slug)
        _load_chart(conn, chart, only_dates=set(new_dates), data_dir=data_dir)
        loaded[chart.slug] = len(new_dates)

    # Rebuild BOTH v1.0 artist_stats AND artist_chart_stats when anything loaded.
    # When rebuild_stats is False the caller (run_update) owns a single rebuild
    # after repair + update both finish, so we never rebuild twice (CR-02).
    if loaded and rebuild_stats:
        logger.info("Rebuilding stats (artist_stats + artist_chart_stats)...")
        build_all_stats(conn)
        logger.info("Stats rebuild complete.")
    elif loaded:
        logger.info("Loaded new data; stats rebuild deferred to caller.")
    else:
        logger.info("No new data loaded; skipping stats rebuild.")

    return loaded


def repair_gaps(
    conn, data_dir: str = None, since_year: int = 2025, rebuild_stats: bool = True
) -> dict:
    """Find and re-download genuinely missing historical data.

    LEGACY-ONLY scope: gap repair runs against the two core charts' legacy
    folders (hot100 / b200) via the legacy downloaders + the loader's
    compatibility shims. New (registry-only) charts are NOT gap-repaired until
    Phase 11 — intentionally not over-scoped here; the weekly registry-driven
    incremental path lives in :func:`update_charts`.

    Args:
        conn: Database connection.
        data_dir: Root data directory.
        since_year: Only look for gaps from this year onward.
        rebuild_stats: When True (default, the standalone repair path) rebuild
            stats here after repair. The combined weekly path
            (:func:`run_update`) passes False so stats are rebuilt EXACTLY ONCE
            at the end across both repair + update (CR-02).
    """
    # Lazy import: the legacy-folder compat shims live in loader (which imports
    # psycopg2 at top level); keep this module psycopg2-free at import time.
    from billboard_stats.etl.loader import _load_b200, _load_hot100

    if data_dir is None:
        data_dir = DATA_DIR

    latest_valid_week = get_latest_publishable_chart_week()
    repaired = {"hot-100": 0, "billboard-200": 0}

    for chart_type in ["hot-100", "billboard-200"]:
        missing = find_failed_downloads(
            chart_type,
            since_year,
            latest_valid_week.year,
            data_dir,
        )
        missing = [d for d in missing if d <= latest_valid_week.isoformat()]

        if not missing:
            logger.info(f"{chart_type}: no gaps found since {since_year}.")
            continue

        logger.info(f"{chart_type}: {len(missing)} missing dates found. Re-downloading...")

        if chart_type == "hot-100":
            download_hot100(missing[0], missing[-1], data_dir, overwrite=True)
            # Load repaired data
            hot100_dir = os.path.join(data_dir, "hot100")
            loaded = [d for d in missing
                      if os.path.exists(os.path.join(hot100_dir, f"{d}.json"))
                      and os.path.getsize(os.path.join(hot100_dir, f"{d}.json")) >= 100]
            if loaded:
                _load_hot100(conn, hot100_dir, only_dates=set(loaded))
                repaired["hot-100"] = len(loaded)
        else:
            download_b200(
                data_dir=data_dir,
                overwrite=True,
                start_date=missing[0],
                end_date=missing[-1],
            )
            b200_dir = os.path.join(data_dir, "b200")
            loaded = [d for d in missing
                      if os.path.exists(os.path.join(b200_dir, f"{d}.json"))
                      and os.path.getsize(os.path.join(b200_dir, f"{d}.json")) >= 100]
            if loaded:
                _load_b200(conn, b200_dir, only_dates=set(loaded))
                repaired["billboard-200"] = len(loaded)

    # Rebuild stats if anything was repaired. When rebuild_stats is False the
    # caller (run_update) owns a single rebuild after repair + update both
    # finish, so we never rebuild twice in one weekly invocation (CR-02).
    if any(v > 0 for v in repaired.values()) and rebuild_stats:
        logger.info("Rebuilding stats after gap repair...")
        build_all_stats(conn)
    elif any(v > 0 for v in repaired.values()):
        logger.info("Repaired data; stats rebuild deferred to caller.")

    return repaired


def run_update(data_dir: str = None, repair: bool = True, update: bool = True) -> dict:
    """CLI entry point: runs gap repair and/or the registry-driven update.

    CR-02: when BOTH phases run in one invocation they each load data that feeds
    the SAME stats tables, so this rebuilds stats EXACTLY ONCE at the end (passing
    ``rebuild_stats=False`` into each phase) instead of twice. A single rebuild
    halves the window during which the live v1.0 frontend could read a
    mid-rebuild stats table, and avoids a second DELETE+INSERT that could fail
    after the first already mutated prod. The rebuild itself is transactional
    (see :func:`billboard_stats.etl.stats_builder.build_all_stats`).

    The weekly cron points at the incremental-only ``--update`` path
    (scripts/run_weekly_etl.sh): gap repair is an operator action, not a weekly
    one. This entry point still supports running both for an operator who wants a
    repair + update in one shot.

    Args:
        data_dir: Root data directory.
        repair: Whether to run gap repair.
        update: Whether to run the registry-driven incremental update.
    """
    # Lazy import: the connection pool imports psycopg2 at top level; keep this
    # module psycopg2-free at import time (the CLI is operator-run).
    from billboard_stats.db.connection import get_conn, put_conn

    conn = get_conn()
    try:
        results = {}
        loaded_anything = False
        if repair:
            logger.info("=== Gap Repair ===")
            repaired = repair_gaps(conn, data_dir, rebuild_stats=False)
            results["repair"] = repaired
            loaded_anything = loaded_anything or any(v > 0 for v in repaired.values())
        if update:
            logger.info("=== Incremental Update (registry-driven) ===")
            updated = update_charts(conn, data_dir, rebuild_stats=False)
            results["update"] = updated
            loaded_anything = loaded_anything or bool(updated)

        # Single transactional stats rebuild after ALL loading (CR-02).
        if loaded_anything:
            logger.info("Rebuilding stats once (artist_stats + artist_chart_stats)...")
            build_all_stats(conn)
            logger.info("Stats rebuild complete.")
        else:
            logger.info("No new data loaded; skipping stats rebuild.")

        return results
    finally:
        put_conn(conn)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Billboard chart updater")
    parser.add_argument("--repair", action="store_true", help="Run gap repair only")
    parser.add_argument("--update", action="store_true", help="Run incremental update only")
    parser.add_argument("--data-dir", default=None, help="Data directory override")
    args = parser.parse_args()

    # If neither flag is set, run both
    do_repair = args.repair or (not args.repair and not args.update)
    do_update = args.update or (not args.repair and not args.update)

    results = run_update(data_dir=args.data_dir, repair=do_repair, update=do_update)
    print(f"\nResults: {results}")
    print(f"\nSuggested crontab entry (Monday 6 AM):")
    print(f"  0 6 * * 1 cd {Path.cwd()} && python -m billboard_stats.etl.updater")
