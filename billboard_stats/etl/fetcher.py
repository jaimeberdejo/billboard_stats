"""Billboard chart data fetcher — downloads Hot 100 and Billboard 200 JSON files.

Consolidates the original download_charts.py, album_downloader.py,
retry_failed_albums.py, and check_data_gaps.py into a single module.
"""

import datetime
import json
import os
import sys
import time
from pathlib import Path

import urllib3

urllib3.disable_warnings()

# Default data directory (billboard_stats/data/)
DATA_DIR = str(Path(__file__).resolve().parent.parent / "data")

MIN_FILE_SIZE = 100  # bytes — files smaller than this are considered failed


def get_saturdays_between(start_date: str, end_date: str) -> list[str]:
    """Get all Saturday date strings between two dates (inclusive)."""
    start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()

    d = start
    d += datetime.timedelta(days=(5 - d.weekday() + 7) % 7)

    dates = []
    while d <= end:
        dates.append(d.strftime("%Y-%m-%d"))
        d += datetime.timedelta(days=7)
    return dates


def get_saturdays_for_year(year: int) -> list[str]:
    """Get all Saturday date strings for a given year."""
    d = datetime.date(year, 1, 1)
    d += datetime.timedelta(days=(5 - d.weekday() + 7) % 7)
    dates = []
    while d.year == year:
        dates.append(d.strftime("%Y-%m-%d"))
        d += datetime.timedelta(days=7)
    return dates


def download_hot100(start_date: str, end_date: str, data_dir: str = None,
                    overwrite: bool = False, delay: float = 1.5):
    """Download Hot 100 chart data for all Saturdays in the date range.

    Args:
        start_date: Start date as 'YYYY-MM-DD'.
        end_date: End date as 'YYYY-MM-DD'.
        data_dir: Root data directory. Defaults to project root.
        overwrite: If True, overwrite existing files.
        delay: Seconds to wait between requests.
    """
    import billboard

    if data_dir is None:
        data_dir = DATA_DIR

    folder = os.path.join(data_dir, "hot100")
    os.makedirs(folder, exist_ok=True)

    dates = get_saturdays_between(start_date, end_date)
    print(f"Downloading Hot 100: {len(dates)} weeks ({start_date} to {end_date})")

    success, failed = 0, 0
    for date_str in dates:
        filepath = os.path.join(folder, f"{date_str}.json")
        if not overwrite and os.path.exists(filepath) and os.path.getsize(filepath) >= MIN_FILE_SIZE:
            continue

        sys.stdout.write(f"\r  Downloading {date_str}...")
        sys.stdout.flush()

        try:
            chart = billboard.ChartData("hot-100", date=date_str, timeout=20)
            data = [
                {
                    "rank": entry.rank,
                    "title": entry.title,
                    "artist": entry.artist,
                    "peakPos": entry.peakPos,
                    "lastPos": entry.lastPos,
                    "weeks": entry.weeks,
                    "isNew": entry.isNew,
                    "image": entry.image,
                }
                for entry in chart
            ]
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f)
            success += 1
            time.sleep(delay)
        except Exception as e:
            sys.stdout.write(f" FAILED ({e})\n")
            failed += 1
            time.sleep(delay * 1.5)

    print(f"\nHot 100 done: {success} downloaded, {failed} failed.")


def download_b200(start_year: int, end_year: int, data_dir: str = None,
                  overwrite: bool = False, delay: float = 1.5):
    """Download Billboard 200 chart data for all Saturdays in the year range.

    Args:
        start_year: Start year (e.g. 1958).
        end_year: End year (e.g. 2026).
        data_dir: Root data directory. Defaults to project root.
        overwrite: If True, overwrite existing files.
        delay: Seconds to wait between requests.
    """
    import billboard

    if data_dir is None:
        data_dir = DATA_DIR

    folder = os.path.join(data_dir, "b200")
    os.makedirs(folder, exist_ok=True)

    print(f"Downloading Billboard 200: {start_year} to {end_year}")

    success, failed = 0, 0
    for year in range(start_year, end_year + 1):
        dates = get_saturdays_for_year(year)
        for date_str in dates:
            filepath = os.path.join(folder, f"{date_str}.json")
            if not overwrite and os.path.exists(filepath) and os.path.getsize(filepath) >= MIN_FILE_SIZE:
                continue

            sys.stdout.write(f"\r  Downloading {date_str}...")
            sys.stdout.flush()

            try:
                chart = billboard.ChartData("billboard-200", date=date_str, timeout=20)
                data = [
                    {
                        "rank": entry.rank,
                        "album": entry.title,
                        "artist": entry.artist,
                        "peakPos": entry.peakPos,
                        "lastPos": entry.lastPos,
                        "weeks": entry.weeks,
                        "isNew": entry.isNew,
                        "image": entry.image,
                    }
                    for entry in chart
                ]
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                success += 1
                time.sleep(delay)
            except Exception as e:
                sys.stdout.write(f" FAILED ({e})\n")
                failed += 1
                time.sleep(delay * 1.5)

        print(f"\n  Year {year} complete.")

    print(f"Billboard 200 done: {success} downloaded, {failed} failed.")


def find_failed_downloads(chart_type: str = "hot-100", start_year: int = 1958,
                          end_year: int = 2026, data_dir: str = None) -> list[str]:
    """Find dates with missing or corrupted chart files.

    Args:
        chart_type: 'hot-100' or 'billboard-200'.
        start_year: Start year to scan.
        end_year: End year to scan.
        data_dir: Root data directory.

    Returns:
        List of date strings needing re-download.
    """
    if data_dir is None:
        data_dir = DATA_DIR

    folder_name = "hot100" if chart_type == "hot-100" else "b200"
    folder = os.path.join(data_dir, folder_name)

    if not os.path.exists(folder):
        return []

    existing = {}
    for filename in os.listdir(folder):
        if filename.endswith(".json"):
            filepath = os.path.join(folder, filename)
            existing[filename.replace(".json", "")] = os.path.getsize(filepath)

    failed = []
    for year in range(start_year, end_year + 1):
        for date_str in get_saturdays_for_year(year):
            if date_str not in existing or existing[date_str] < MIN_FILE_SIZE:
                failed.append(date_str)

    return sorted(failed)


def retry_failed(chart_type: str = "hot-100", start_year: int = 1958,
                 end_year: int = 2026, data_dir: str = None, delay: float = 1.5):
    """Find and retry all failed downloads for a chart type."""
    failed_dates = find_failed_downloads(chart_type, start_year, end_year, data_dir)
    if not failed_dates:
        print(f"No failed downloads for {chart_type}.")
        return

    print(f"Found {len(failed_dates)} failed downloads for {chart_type}.")

    if chart_type == "hot-100":
        download_hot100(failed_dates[0], failed_dates[-1], data_dir, overwrite=True, delay=delay)
    else:
        years = sorted(set(int(d[:4]) for d in failed_dates))
        download_b200(years[0], years[-1], data_dir, overwrite=True, delay=delay)


def check_data_gaps(data_dir: str = None) -> dict:
    """Analyze both chart directories for missing data.

    Returns a dict with gap analysis for each chart type.
    """
    if data_dir is None:
        data_dir = DATA_DIR

    results = {}
    for chart_type, folder_name, display_name in [
        ("hot-100", "hot100", "Hot 100"),
        ("billboard-200", "b200", "Billboard 200"),
    ]:
        folder = os.path.join(data_dir, folder_name)
        if not os.path.isdir(folder):
            print(f"  {display_name}: directory not found ({folder})")
            continue

        dates = []
        for filename in os.listdir(folder):
            if filename.endswith(".json"):
                date_str = filename.replace(".json", "")
                try:
                    dates.append(datetime.datetime.strptime(date_str, "%Y-%m-%d").date())
                except ValueError:
                    pass

        dates.sort()
        if not dates:
            print(f"  {display_name}: no files found")
            continue

        # Find missing Saturdays
        expected = set()
        d = dates[0]
        while d.weekday() != 5:
            d += datetime.timedelta(days=1)
        while d <= dates[-1]:
            expected.add(d)
            d += datetime.timedelta(days=7)

        actual = set(dates)
        missing = sorted(expected - actual)

        total = len(expected)
        completeness = (1 - len(missing) / total) * 100 if total > 0 else 0

        print(f"\n  {display_name}:")
        print(f"    Files: {len(actual)}")
        print(f"    Date range: {dates[0]} to {dates[-1]}")
        print(f"    Expected weeks: {total}")
        print(f"    Missing: {len(missing)}")
        print(f"    Completeness: {completeness:.1f}%")

        results[chart_type] = {
            "total_files": len(actual),
            "expected_weeks": total,
            "missing_count": len(missing),
            "missing_dates": [d.isoformat() for d in missing],
            "completeness": completeness,
            "start": dates[0].isoformat(),
            "end": dates[-1].isoformat(),
        }

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Billboard chart data fetcher")
    sub = parser.add_subparsers(dest="command")

    dl_hot = sub.add_parser("download-hot100", help="Download Hot 100 data")
    dl_hot.add_argument("--start", default="1958-01-01")
    dl_hot.add_argument("--end", default="2026-12-31")
    dl_hot.add_argument("--overwrite", action="store_true")

    dl_b200 = sub.add_parser("download-b200", help="Download Billboard 200 data")
    dl_b200.add_argument("--start-year", type=int, default=1958)
    dl_b200.add_argument("--end-year", type=int, default=2026)
    dl_b200.add_argument("--overwrite", action="store_true")

    retry = sub.add_parser("retry", help="Retry failed downloads")
    retry.add_argument("--chart", default="hot-100", choices=["hot-100", "billboard-200"])

    gaps = sub.add_parser("check-gaps", help="Check for data gaps")

    args = parser.parse_args()

    if args.command == "download-hot100":
        download_hot100(args.start, args.end, overwrite=args.overwrite)
    elif args.command == "download-b200":
        download_b200(args.start_year, args.end_year, overwrite=args.overwrite)
    elif args.command == "retry":
        retry_failed(args.chart)
    elif args.command == "check-gaps":
        check_data_gaps()
    else:
        parser.print_help()
