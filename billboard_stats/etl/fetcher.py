"""Billboard chart data fetcher — downloads Hot 100 and Billboard 200 JSON files.

Consolidates the original download_charts.py, album_downloader.py,
retry_failed_albums.py, and check_data_gaps.py into a single module.
"""

from __future__ import annotations

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


def get_latest_publishable_chart_week(as_of: datetime.date | None = None) -> datetime.date:
    """Return the most recent Saturday that is valid for chart maintenance."""
    current_date = as_of or datetime.date.today()
    return current_date - datetime.timedelta(days=(current_date.weekday() - 5) % 7)


def get_saturdays_between(start_date: str, end_date: str) -> list[str]:
    """Get all Saturday date strings between two dates (inclusive)."""
    start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    if end < start:
        return []

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


def download_b200(start_year: int = None, end_year: int = None, data_dir: str = None,
                  overwrite: bool = False, delay: float = 1.5,
                  start_date: str = None, end_date: str = None):
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

    if start_date is not None or end_date is not None:
        if not start_date or not end_date:
            raise ValueError("download_b200 requires both start_date and end_date when date-bounded")
        dates = get_saturdays_between(start_date, end_date)
        print(f"Downloading Billboard 200: {len(dates)} weeks ({start_date} to {end_date})")
    else:
        if start_year is None or end_year is None:
            raise ValueError("download_b200 requires start_year/end_year or start_date/end_date")
        print(f"Downloading Billboard 200: {start_year} to {end_year}")
        dates = []
        for year in range(start_year, end_year + 1):
            dates.extend(get_saturdays_for_year(year))

    success, failed = 0, 0
    current_year = None
    for date_str in dates:
        filepath = os.path.join(folder, f"{date_str}.json")
        if not overwrite and os.path.exists(filepath) and os.path.getsize(filepath) >= MIN_FILE_SIZE:
            continue

        year = int(date_str[:4])
        if start_date is None and current_year != year:
            current_year = year
            print(f"\n  Year {year}")

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

    print(f"Billboard 200 done: {success} downloaded, {failed} failed.")


class HardStopError(Exception):
    """An HTTP 403/429 was received — abort the whole run immediately.

    Per Pitfall 4, a 403/429 from billboard.com signals rate-limiting / IP block
    and must HARD-STOP the run rather than tight-retrying the offending week.
    """


def _http_status(exc) -> int | None:
    """Return the HTTP status code carried by an exception, if any."""
    response = getattr(exc, "response", None)
    if response is not None:
        return getattr(response, "status_code", None)
    return None


# Safety floor for the backward history walk. No Billboard chart predates the
# Hot 100's 1958 debut, so a chart that never returns an empty/not-found week
# (a pathological parse loop) is bounded by this cutoff instead of walking back
# forever. Callers may override via download_chart_history(stop_floor=...).
HISTORY_STOP_FLOOR = datetime.date(1958, 1, 1)


# Sentinel results for the per-week fetch helper.
_WEEK_SKIPPED = "skipped"      # file already on disk (cache skip)
_WEEK_HAS_DATA = "has_data"    # fetched + saved with >= 1 entry
_WEEK_EMPTY = "empty"          # resolved but zero entries (treat as before-debut)
_WEEK_NOT_FOUND = "not_found"  # 404 / BillboardNotFoundException (before debut)
_WEEK_FAILED = "failed"        # other transient error (tolerated, not a boundary)


def _fetch_and_save_week(slug: str, date_str: str, folder: str,
                         overwrite: bool, delay: float) -> str:
    """Fetch + save ONE week of a chart, returning an outcome sentinel.

    This is the single per-week fetch/save primitive shared by both
    :func:`download_chart` (forward range) and :func:`download_chart_history`
    (backward walk) so the fetch/parse/write/skip/hard-stop logic lives in one
    place.

    Returns one of the ``_WEEK_*`` sentinels:
        - ``_WEEK_SKIPPED``: the file already exists (>= ``MIN_FILE_SIZE``).
        - ``_WEEK_HAS_DATA``: fetched and wrote a file with >= 1 entry.
        - ``_WEEK_EMPTY``: the chart resolved but had zero entries.
        - ``_WEEK_NOT_FOUND``: a 404 / ``BillboardNotFoundException``.
        - ``_WEEK_FAILED``: any other (transient) error.

    Raises:
        HardStopError: on an HTTP 403/429 (rate-limit / IP-block).
    """
    import billboard

    filepath = os.path.join(folder, f"{date_str}.json")
    if not overwrite and os.path.exists(filepath) and os.path.getsize(filepath) >= MIN_FILE_SIZE:
        return _WEEK_SKIPPED

    sys.stdout.write(f"\r  Downloading {date_str}...")
    sys.stdout.flush()

    try:
        chart = billboard.ChartData(slug, date=date_str, timeout=20)
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
    except billboard.BillboardNotFoundException:
        # No chart published that week — for the backward walk this is the
        # natural before-debut boundary, not a loud error.
        sys.stdout.write(f" not found ({date_str})\n")
        time.sleep(delay)
        return _WEEK_NOT_FOUND
    except Exception as e:
        status = _http_status(e)
        if status in (403, 429):
            # Hard stop: an IP-block / rate-limit signal aborts the run.
            sys.stdout.write(f" HARD STOP (HTTP {status})\n")
            raise HardStopError(
                f"HTTP {status} fetching {slug} {date_str} — aborting run "
                "(rate-limited / IP-blocked; not retrying)"
            ) from e
        # Tolerate transient errors; caller decides whether to keep going.
        sys.stdout.write(f" FAILED ({e})\n")
        time.sleep(delay * 1.5)
        return _WEEK_FAILED

    if not data:
        # Resolved but empty: a chart that existed structurally but listed no
        # entries for this week. For the backward walk this means we've gone
        # before the chart's debut. Do NOT write an empty file.
        sys.stdout.write(f" empty ({date_str})\n")
        time.sleep(delay)
        return _WEEK_EMPTY

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f)
    time.sleep(delay)
    return _WEEK_HAS_DATA


def download_chart(slug: str, start_date: str, end_date: str, data_dir: str = None,
                   overwrite: bool = False, delay: float = 1.5):
    """Download an arbitrary chart by slug for all Saturdays in a date range.

    Generalizes ``download_hot100`` into a slug-parameterized, resumable
    primitive. Writes one JSON file per chart per week under
    ``data/{slug}/{YYYY-MM-DD}.json`` with the generic per-entry shape.

    Behavior:
        - A week whose file already exists and is >= ``MIN_FILE_SIZE`` is SKIPPED
          (no ChartData call) — on-disk cache skip makes a resumed run never
          re-scrape an existing file.
        - An HTTP 403 or 429 raises :class:`HardStopError` and aborts the whole
          run immediately — NOT a tight per-week retry loop.
        - Any other per-week error is counted as a failure and the run continues
          (so genuinely-missing pre-launch weeks don't kill the run).

    Args:
        slug: The verified chart slug (e.g. ``"country-songs"``).
        start_date: Start date as 'YYYY-MM-DD'.
        end_date: End date as 'YYYY-MM-DD'.
        data_dir: Root data directory. Defaults to project ``data/``.
        overwrite: If True, overwrite existing files.
        delay: Seconds to wait between requests (politeness).

    Raises:
        HardStopError: on an HTTP 403/429 response.
    """
    import billboard

    if data_dir is None:
        data_dir = DATA_DIR

    folder = os.path.join(data_dir, slug)
    os.makedirs(folder, exist_ok=True)

    dates = get_saturdays_between(start_date, end_date)
    print(f"Downloading {slug}: {len(dates)} weeks ({start_date} to {end_date})")

    success, failed = 0, 0
    for date_str in dates:
        # HardStopError (403/429) propagates out of the helper.
        outcome = _fetch_and_save_week(slug, date_str, folder, overwrite, delay)
        if outcome == _WEEK_HAS_DATA:
            success += 1
        elif outcome in (_WEEK_EMPTY, _WEEK_NOT_FOUND, _WEEK_FAILED):
            # A genuinely-missing / pre-launch / transient week does not kill a
            # forward range download; keep going (count non-skips as failures).
            failed += 1

    print(f"\n{slug} done: {success} downloaded, {failed} failed.")


def download_chart_history(slug: str, data_dir: str = None, overwrite: bool = False,
                           delay: float = 1.5, as_of: datetime.date = None,
                           stop_floor: datetime.date = None,
                           empty_tolerance: int = 1) -> dict:
    """Download a chart's FULL history by walking BACKWARD to its debut.

    Unlike :func:`download_chart` (which needs a known start date), this
    discovers each chart's true history depth at runtime. It starts at the
    latest publishable chart week and walks backward one Saturday (7 days) at a
    time, saving each week via the shared per-week primitive. It STOPS when it
    reaches the chart's debut — signalled by a before-debut week that resolves
    EMPTY or NOT-FOUND — rather than trusting a (misleading) recorded
    ``first_date``.

    This is resumable for free: weeks already on disk are skipped (no network
    call), so a re-run continues where a crashed/cancelled run left off.

    Args:
        slug: The verified chart slug (e.g. ``"artist-100"``).
        data_dir: Root data directory. Defaults to project ``data/``.
        overwrite: If True, re-fetch even weeks already on disk.
        delay: Polite seconds between requests.
        as_of: Treat this date as "today" when computing the latest week
            (injectable for deterministic tests). Defaults to today.
        stop_floor: Earliest date the walk may reach before giving up
            unconditionally (bounds a pathological never-empty chart). Defaults
            to :data:`HISTORY_STOP_FLOOR` (1958-01-01).
        empty_tolerance: Number of CONSECUTIVE empty/not-found weeks that marks
            the debut boundary. Default 1 — a single empty at the deep end is the
            expected debut. Raise to 2 to tolerate one legitimately-missing
            mid-history week before stopping.

    Returns:
        A summary dict: ``{"slug", "saved", "skipped", "failed", "earliest",
        "stopped_at", "reason"}`` where ``reason`` is ``"debut"`` (hit the empty
        boundary) or ``"floor"`` (hit ``stop_floor``).

    Raises:
        HardStopError: propagated from the per-week primitive on an HTTP 403/429.
            A 403/429 is NEVER treated as the debut boundary.
    """
    if data_dir is None:
        data_dir = DATA_DIR
    if stop_floor is None:
        stop_floor = HISTORY_STOP_FLOOR

    folder = os.path.join(data_dir, slug)
    os.makedirs(folder, exist_ok=True)

    week = get_latest_publishable_chart_week(as_of=as_of)
    print(f"Walking {slug} history backward from {week.isoformat()} "
          f"(floor {stop_floor.isoformat()})")

    saved = skipped = failed = 0
    consecutive_empty = 0
    earliest = None
    reason = "floor"

    while week >= stop_floor:
        date_str = week.isoformat()
        # HardStopError (403/429) propagates — NOT a debut boundary.
        outcome = _fetch_and_save_week(slug, date_str, folder, overwrite, delay)

        if outcome in (_WEEK_EMPTY, _WEEK_NOT_FOUND):
            consecutive_empty += 1
            if consecutive_empty >= empty_tolerance:
                # Reached the chart's debut: the deep end is empty. Stop cleanly.
                reason = "debut"
                break
        else:
            # Any data/skip/transient-failure week resets the empty run so a
            # single missing mid-history week doesn't falsely end the walk.
            consecutive_empty = 0
            if outcome == _WEEK_HAS_DATA:
                saved += 1
                earliest = date_str
            elif outcome == _WEEK_SKIPPED:
                skipped += 1
                earliest = date_str
            elif outcome == _WEEK_FAILED:
                failed += 1

        week -= datetime.timedelta(days=7)

    print(f"\n{slug} history done ({reason}): {saved} saved, {skipped} skipped, "
          f"{failed} failed; earliest kept = {earliest}.")
    return {
        "slug": slug,
        "saved": saved,
        "skipped": skipped,
        "failed": failed,
        "earliest": earliest,
        "stopped_at": week.isoformat(),
        "reason": reason,
    }


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

    dl_chart = sub.add_parser("download-chart", help="Download any chart by slug")
    dl_chart.add_argument("--slug", required=True)
    dl_chart.add_argument("--start", required=True, help="YYYY-MM-DD")
    dl_chart.add_argument("--end", required=True, help="YYYY-MM-DD")
    dl_chart.add_argument("--overwrite", action="store_true")

    retry = sub.add_parser("retry", help="Retry failed downloads")
    retry.add_argument("--chart", default="hot-100", choices=["hot-100", "billboard-200"])

    gaps = sub.add_parser("check-gaps", help="Check for data gaps")

    args = parser.parse_args()

    if args.command == "download-hot100":
        download_hot100(args.start, args.end, overwrite=args.overwrite)
    elif args.command == "download-b200":
        download_b200(args.start_year, args.end_year, overwrite=args.overwrite)
    elif args.command == "download-chart":
        download_chart(args.slug, args.start, args.end, overwrite=args.overwrite)
    elif args.command == "retry":
        retry_failed(args.chart)
    elif args.command == "check-gaps":
        check_data_gaps()
    else:
        parser.print_help()
