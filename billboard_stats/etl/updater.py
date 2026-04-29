"""Incremental chart update and data gap repair.

Usage:
    python -m billboard_stats.etl.updater          # run update + gap repair
    python -m billboard_stats.etl.updater --repair  # gap repair only
    python -m billboard_stats.etl.updater --update  # incremental update only

Suggested crontab (Monday 6 AM):
    0 6 * * 1 cd /path/to/billboard_stats && python -m billboard_stats.etl.updater
"""

import datetime
import logging
import os
from pathlib import Path

from billboard_stats.db.connection import get_conn, put_conn
from billboard_stats.etl.fetcher import (
    DATA_DIR,
    download_hot100,
    download_b200,
    find_failed_downloads,
    get_latest_publishable_chart_week,
)
from billboard_stats.etl.loader import _load_hot100, _load_b200
from billboard_stats.etl.stats_builder import build_all_stats

logger = logging.getLogger(__name__)


def _get_latest_chart_dates(conn) -> dict:
    """Query DB for the latest non-future Saturday per chart_type."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT chart_type, MAX(chart_date) FROM chart_weeks "
            "WHERE chart_date <= CURRENT_DATE "
            "AND EXTRACT(DOW FROM chart_date) = 6 "
            "GROUP BY chart_type;"
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def update_charts(conn, data_dir: str = None):
    """Incremental update: fetch new data since last DB date, load, rebuild stats.

    Args:
        conn: Database connection.
        data_dir: Root data directory containing hot100/ and b200/ subdirectories.
    """
    if data_dir is None:
        data_dir = DATA_DIR

    latest = _get_latest_chart_dates(conn)
    latest_valid_week = get_latest_publishable_chart_week()
    new_dates = {"hot-100": [], "billboard-200": []}

    # Hot 100: download dates after the latest in DB
    hot100_latest = latest.get("hot-100")
    if hot100_latest:
        start = (hot100_latest + datetime.timedelta(days=1)).isoformat()
        end = latest_valid_week.isoformat()
        if hot100_latest < latest_valid_week:
            logger.info(f"Hot 100: fetching from {start} to {end}")
            download_hot100(start, end, data_dir)
        else:
            logger.info("Hot 100: already current through the latest valid chart week.")

        # Determine which new dates to load
        hot100_dir = os.path.join(data_dir, "hot100")
        for fname in sorted(os.listdir(hot100_dir)):
            if fname.endswith(".json"):
                date_str = fname.replace(".json", "")
                try:
                    d = datetime.date.fromisoformat(date_str)
                    if hot100_latest < d <= latest_valid_week:
                        new_dates["hot-100"].append(date_str)
                except ValueError:
                    pass
    else:
        logger.warning("No existing Hot 100 data in DB. Run full ETL first.")

    # Billboard 200: download dates after the latest in DB
    b200_latest = latest.get("billboard-200")
    if b200_latest:
        start = (b200_latest + datetime.timedelta(days=1)).isoformat()
        end = latest_valid_week.isoformat()
        if b200_latest < latest_valid_week:
            logger.info(f"Billboard 200: fetching from {start} to {end}")
            download_b200(data_dir=data_dir, start_date=start, end_date=end)
        else:
            logger.info("Billboard 200: already current through the latest valid chart week.")

        b200_dir = os.path.join(data_dir, "b200")
        for fname in sorted(os.listdir(b200_dir)):
            if fname.endswith(".json"):
                date_str = fname.replace(".json", "")
                try:
                    d = datetime.date.fromisoformat(date_str)
                    if b200_latest < d <= latest_valid_week:
                        new_dates["billboard-200"].append(date_str)
                except ValueError:
                    pass
    else:
        logger.warning("No existing Billboard 200 data in DB. Run full ETL first.")

    # Load new data into DB
    hot100_new = new_dates["hot-100"]
    b200_new = new_dates["billboard-200"]

    if hot100_new:
        logger.info(f"Loading {len(hot100_new)} new Hot 100 weeks into DB...")
        _load_hot100(conn, os.path.join(data_dir, "hot100"), only_dates=set(hot100_new))
    else:
        logger.info("No new Hot 100 data to load.")

    if b200_new:
        logger.info(f"Loading {len(b200_new)} new Billboard 200 weeks into DB...")
        _load_b200(conn, os.path.join(data_dir, "b200"), only_dates=set(b200_new))
    else:
        logger.info("No new Billboard 200 data to load.")

    # Rebuild stats if anything changed
    if hot100_new or b200_new:
        logger.info("Rebuilding stats...")
        build_all_stats(conn)
        logger.info("Stats rebuild complete.")

    return {"hot100_loaded": len(hot100_new), "b200_loaded": len(b200_new)}


def repair_gaps(conn, data_dir: str = None, since_year: int = 2025):
    """Find and re-download genuinely missing historical data.

    Args:
        conn: Database connection.
        data_dir: Root data directory.
        since_year: Only look for gaps from this year onward.
    """
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

    # Rebuild stats if anything was repaired
    if any(v > 0 for v in repaired.values()):
        logger.info("Rebuilding stats after gap repair...")
        build_all_stats(conn)

    return repaired


def run_update(data_dir: str = None, repair: bool = True, update: bool = True):
    """CLI entry point: runs gap repair and/or incremental update.

    Args:
        data_dir: Root data directory.
        repair: Whether to run gap repair.
        update: Whether to run incremental update.
    """
    conn = get_conn()
    try:
        results = {}
        if repair:
            logger.info("=== Gap Repair ===")
            results["repair"] = repair_gaps(conn, data_dir)
        if update:
            logger.info("=== Incremental Update ===")
            results["update"] = update_charts(conn, data_dir)
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
