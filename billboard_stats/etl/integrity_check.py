"""Audit chart JSON data for missing weeks and invalid payloads.

Usage:
    python -m billboard_stats.etl.integrity_check
    python -m billboard_stats.etl.integrity_check --chart hot-100
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from pathlib import Path
from typing import Callable

from billboard_stats.etl.fetcher import (
    DATA_DIR,
    MIN_FILE_SIZE,
    download_b200,
    download_hot100,
    get_latest_publishable_chart_week,
)
from billboard_stats.etl.json_parser import parse_b200_file, parse_hot100_file

ChartParser = Callable[[str], list[dict] | None]
logger = logging.getLogger(__name__)

CHART_CONFIG = {
    "hot-100": {
        "folder": "hot100",
        "label": "Hot 100",
        "parser": parse_hot100_file,
    },
    "billboard-200": {
        "folder": "b200",
        "label": "Billboard 200",
        "parser": parse_b200_file,
    },
}


def _get_expected_saturdays(start: dt.date, end: dt.date) -> list[dt.date]:
    current = start + dt.timedelta(days=(5 - start.weekday()) % 7)
    dates: list[dt.date] = []
    while current <= end:
        dates.append(current)
        current += dt.timedelta(days=7)
    return dates


def audit_chart_data(
    chart_type: str,
    data_dir: str | None = None,
    latest_week: dt.date | None = None,
) -> dict:
    """Return integrity results for one chart dataset."""
    if chart_type not in CHART_CONFIG:
        raise ValueError(f"Unsupported chart type: {chart_type}")

    data_root = Path(data_dir or DATA_DIR)
    config = CHART_CONFIG[chart_type]
    folder = data_root / config["folder"]
    parser: ChartParser = config["parser"]
    latest_expected_week = latest_week or get_latest_publishable_chart_week()

    if not folder.is_dir():
        raise FileNotFoundError(f"Chart directory not found: {folder}")

    valid_dates: list[dt.date] = []
    invalid_filenames: list[str] = []
    files_by_date: dict[dt.date, Path] = {}
    empty_files: list[str] = []
    invalid_json_files: list[str] = []
    invalid_payload_files: list[str] = []
    future_files: list[str] = []

    for path in sorted(folder.glob("*.json")):
        try:
            chart_date = dt.date.fromisoformat(path.stem)
        except ValueError:
            invalid_filenames.append(path.name)
            continue

        if chart_date > latest_expected_week:
            future_files.append(path.name)
            continue

        valid_dates.append(chart_date)
        files_by_date[chart_date] = path

        if path.stat().st_size < MIN_FILE_SIZE:
            empty_files.append(path.name)
            continue

        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            invalid_json_files.append(path.name)
            continue

        if not isinstance(data, list) or len(data) == 0:
            invalid_payload_files.append(path.name)
            continue

        if parser(str(path)) is None:
            invalid_payload_files.append(path.name)

    latest_present_week = max(valid_dates) if valid_dates else None
    range_end = min(latest_expected_week, latest_present_week) if latest_present_week else latest_expected_week

    missing_dates: list[str] = []
    if valid_dates:
        expected_dates = _get_expected_saturdays(min(valid_dates), range_end)
        missing_dates = [
            date.isoformat()
            for date in expected_dates
            if date not in files_by_date
        ]

    return {
        "chart_type": chart_type,
        "label": config["label"],
        "directory": str(folder),
        "start": min(valid_dates).isoformat() if valid_dates else None,
        "end": latest_present_week.isoformat() if latest_present_week else None,
        "latest_expected_week": latest_expected_week.isoformat(),
        "missing_dates": missing_dates,
        "empty_files": empty_files,
        "invalid_json_files": invalid_json_files,
        "invalid_payload_files": invalid_payload_files,
        "invalid_filenames": invalid_filenames,
        "future_files": future_files,
        "file_count": len(valid_dates),
        "ok": not any([
            missing_dates,
            empty_files,
            invalid_json_files,
            invalid_payload_files,
            invalid_filenames,
        ]),
    }


def audit_all_chart_data(data_dir: str | None = None, latest_week: dt.date | None = None) -> dict:
    """Return integrity results for every supported chart dataset."""
    results = {
        chart_type: audit_chart_data(chart_type, data_dir=data_dir, latest_week=latest_week)
        for chart_type in CHART_CONFIG
    }
    results["ok"] = all(result["ok"] for result in results.values())
    return results


def _print_report(results: dict) -> None:
    chart_items = [(key, value) for key, value in results.items() if key != "ok"]
    for _, result in chart_items:
        print(f"\n{result['label']}")
        print(f"  Directory: {result['directory']}")
        print(f"  Range: {result['start']} -> {result['end']}")
        print(f"  Latest expected week: {result['latest_expected_week']}")
        print(f"  Files: {result['file_count']}")
        print(f"  Missing weeks: {len(result['missing_dates'])}")
        print(f"  Empty files: {len(result['empty_files'])}")
        print(f"  Invalid JSON: {len(result['invalid_json_files'])}")
        print(f"  Invalid payloads: {len(result['invalid_payload_files'])}")
        print(f"  Bad filenames: {len(result['invalid_filenames'])}")
        print(f"  Future files ignored: {len(result['future_files'])}")

        for label, items in [
            ("Missing weeks", result["missing_dates"]),
            ("Empty files", result["empty_files"]),
            ("Invalid JSON", result["invalid_json_files"]),
            ("Invalid payloads", result["invalid_payload_files"]),
            ("Bad filenames", result["invalid_filenames"]),
            ("Future files ignored", result["future_files"]),
        ]:
            if items:
                print(f"  {label}:")
                for item in items:
                    print(f"    - {item}")

    print("\nIntegrity check passed." if results["ok"] else "\nIntegrity check found issues.")


def _parse_date_stem(filename: str) -> str | None:
    stem = Path(filename).stem
    try:
        dt.date.fromisoformat(stem)
    except ValueError:
        return None
    return stem


def _group_consecutive_saturdays(date_strings: list[str]) -> list[tuple[str, str]]:
    if not date_strings:
        return []

    dates = sorted(dt.date.fromisoformat(date_string) for date_string in set(date_strings))
    groups: list[tuple[str, str]] = []
    start = dates[0]
    previous = dates[0]

    for current in dates[1:]:
        if current - previous == dt.timedelta(days=7):
            previous = current
            continue
        groups.append((start.isoformat(), previous.isoformat()))
        start = previous = current

    groups.append((start.isoformat(), previous.isoformat()))
    return groups


def _collect_repair_dates(result: dict) -> tuple[list[str], list[str]]:
    date_strings = list(result["missing_dates"])
    skipped_files: list[str] = []

    for filename in (
        result["empty_files"]
        + result["invalid_json_files"]
        + result["invalid_payload_files"]
    ):
        date_string = _parse_date_stem(filename)
        if date_string is None:
            skipped_files.append(filename)
            continue
        date_strings.append(date_string)

    for filename in result["invalid_filenames"]:
        skipped_files.append(filename)

    return sorted(set(date_strings)), skipped_files


def _download_ranges(chart_type: str, date_ranges: list[tuple[str, str]], data_dir: str) -> None:
    for start_date, end_date in date_ranges:
        logger.info("%s: downloading %s -> %s", chart_type, start_date, end_date)
        if chart_type == "hot-100":
            download_hot100(start_date, end_date, data_dir=data_dir, overwrite=True)
        else:
            download_b200(data_dir=data_dir, start_date=start_date, end_date=end_date, overwrite=True)


def repair_chart_data(
    chart_type: str,
    data_dir: str | None = None,
    latest_week: dt.date | None = None,
    reload_db: bool = False,
) -> dict:
    """Repair missing or invalid local chart JSON and optionally reload the DB."""
    data_root = str(Path(data_dir or DATA_DIR))
    before = audit_chart_data(chart_type, data_dir=data_root, latest_week=latest_week)
    repair_dates, skipped_files = _collect_repair_dates(before)

    if repair_dates:
        _download_ranges(chart_type, _group_consecutive_saturdays(repair_dates), data_root)

    after = audit_chart_data(chart_type, data_dir=data_root, latest_week=latest_week)
    repaired_dates = sorted(set(repair_dates) - set(after["missing_dates"]))

    reload_summary = {
        "attempted": False,
        "loaded_dates": [],
        "stats_rebuilt": False,
    }
    if reload_db and repaired_dates:
        from billboard_stats.db.connection import get_conn, put_conn
        from billboard_stats.etl.loader import _load_b200, _load_hot100
        from billboard_stats.etl.stats_builder import build_all_stats

        conn = get_conn()
        try:
            chart_dir = str(Path(data_root) / CHART_CONFIG[chart_type]["folder"])
            if chart_type == "hot-100":
                _load_hot100(conn, chart_dir, only_dates=set(repaired_dates))
            else:
                _load_b200(conn, chart_dir, only_dates=set(repaired_dates))
            build_all_stats(conn)
            reload_summary = {
                "attempted": True,
                "loaded_dates": repaired_dates,
                "stats_rebuilt": True,
            }
        finally:
            put_conn(conn)

    return {
        "chart_type": chart_type,
        "attempted_dates": repair_dates,
        "skipped_files": skipped_files,
        "repaired_dates": repaired_dates,
        "before": before,
        "after": after,
        "reload_db": reload_summary,
        "ok": after["ok"],
    }


def repair_all_chart_data(
    data_dir: str | None = None,
    latest_week: dt.date | None = None,
    reload_db: bool = False,
) -> dict:
    """Repair all supported chart datasets and optionally reload the DB."""
    results = {
        chart_type: repair_chart_data(
            chart_type,
            data_dir=data_dir,
            latest_week=latest_week,
            reload_db=reload_db,
        )
        for chart_type in CHART_CONFIG
    }
    results["ok"] = all(result["ok"] for result in results.values())
    return results


def _print_repair_report(results: dict) -> None:
    chart_items = [(key, value) for key, value in results.items() if key != "ok"]
    for _, result in chart_items:
        print(f"\n{CHART_CONFIG[result['chart_type']]['label']} Repair")
        print(f"  Attempted dates: {len(result['attempted_dates'])}")
        print(f"  Repaired dates: {len(result['repaired_dates'])}")
        print(f"  Remaining issues: {'none' if result['after']['ok'] else 'present'}")
        if result["attempted_dates"]:
            print("  Attempted:")
            for item in result["attempted_dates"]:
                print(f"    - {item}")
        if result["skipped_files"]:
            print("  Skipped files:")
            for item in result["skipped_files"]:
                print(f"    - {item}")
        if result["reload_db"]["attempted"]:
            print(f"  DB reloaded: {len(result['reload_db']['loaded_dates'])} dates")

    print("\nRepair completed cleanly." if results["ok"] else "\nRepair completed with remaining issues.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Billboard chart JSON integrity")
    parser.add_argument(
        "--chart",
        choices=["hot-100", "billboard-200", "all"],
        default="all",
        help="Chart dataset to audit",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Override the root data directory containing hot100/ and b200/",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Re-download missing/empty/invalid local files before reporting",
    )
    parser.add_argument(
        "--reload-db",
        action="store_true",
        help="After repair, reload repaired weeks into PostgreSQL and rebuild stats",
    )
    args = parser.parse_args()

    if args.reload_db and not args.repair:
        parser.error("--reload-db requires --repair")

    if args.repair:
        if args.chart == "all":
            results = repair_all_chart_data(data_dir=args.data_dir, reload_db=args.reload_db)
        else:
            chart_result = repair_chart_data(args.chart, data_dir=args.data_dir, reload_db=args.reload_db)
            results = {"ok": chart_result["ok"], args.chart: chart_result}
        _print_repair_report(results)
    elif args.chart == "all":
        results = audit_all_chart_data(data_dir=args.data_dir)
    else:
        chart_result = audit_chart_data(args.chart, data_dir=args.data_dir)
        results = {"ok": chart_result["ok"], args.chart: chart_result}

    if not args.repair:
        _print_report(results)
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
