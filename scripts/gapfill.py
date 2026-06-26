#!/usr/bin/env python3
"""Targeted gap-fill for curated chart slugs.

The backward history walk (``download_chart_history``) stops at the first run of
``empty_tolerance`` consecutive empty/not-found weeks. billboard.com serves the
deep end INCONSISTENTLY (a week that returns empty on one request returns data
on a later one), so the walk can stop short and orphan real older data below a
transient empty run. This leaves interior HOLES in an otherwise contiguous span.

This operator tool closes those holes WITHOUT debut logic: it computes the
missing Saturdays inside each chart's [earliest, latest] on-disk span and
re-fetches ONLY those weeks via the empty-tolerant ``download_chart`` primitive,
repeating for several rounds (billboard inconsistency means a week missing this
round may succeed next). Weeks that stay missing after all rounds are genuinely
empty on billboard (or that machine had no network) — reported, not fatal.

Usage:
    python scripts/gapfill.py country-songs country-albums rock-songs \
        --rounds 4 --delay 1.5

Resumable and safe to re-run: on-disk weeks are skipped (no network call).
Hard-stops on HTTP 403/429 (propagated from download_chart) — do NOT tight-retry.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys

from billboard_stats.etl.fetcher import (
    DATA_DIR,
    MIN_FILE_SIZE,
    HardStopError,
    download_chart,
)


def _ondisk_saturdays(folder: str) -> list[datetime.date]:
    """Valid (>= MIN_FILE_SIZE) chart dates currently on disk, sorted."""
    dates = []
    if not os.path.isdir(folder):
        return dates
    for fn in os.listdir(folder):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(folder, fn)
        if os.path.getsize(path) < MIN_FILE_SIZE:
            continue
        try:
            dates.append(datetime.date.fromisoformat(fn[:-5]))
        except ValueError:
            pass
    return sorted(dates)


def _missing_saturdays(folder: str) -> tuple[list[datetime.date], datetime.date, datetime.date]:
    """Saturdays absent inside the [earliest, latest] on-disk span."""
    present = _ondisk_saturdays(folder)
    if not present:
        return [], None, None
    earliest, latest = present[0], present[-1]
    present_set = set(present)
    missing = []
    d = earliest
    while d <= latest:
        if d not in present_set:
            missing.append(d)
        d += datetime.timedelta(days=7)
    return missing, earliest, latest


def gapfill_slug(slug: str, data_dir: str, rounds: int, delay: float) -> dict:
    """Re-fetch interior holes for one slug over up to ``rounds`` passes."""
    folder = os.path.join(data_dir, slug)
    missing, earliest, latest = _missing_saturdays(folder)
    if earliest is None:
        print(f"[{slug}] no on-disk data — skipping.")
        return {"slug": slug, "filled": 0, "remaining": 0}

    print(f"[{slug}] span {earliest} -> {latest}: {len(missing)} holes to fill.")
    if not missing:
        return {"slug": slug, "filled": 0, "remaining": 0}

    initial = len(missing)
    for rnd in range(1, rounds + 1):
        if not missing:
            break
        print(f"[{slug}] round {rnd}/{rounds}: attempting {len(missing)} weeks...")
        for d in missing:
            ds = d.isoformat()
            # start==end fetches exactly that week; empty/failure is tolerated.
            download_chart(slug, ds, ds, data_dir=data_dir, delay=delay)
        missing, _, _ = _missing_saturdays(folder)
        print(f"[{slug}] round {rnd} done: {len(missing)} still missing.")

    filled = initial - len(missing)
    print(f"[{slug}] DONE: filled {filled}/{initial}; {len(missing)} genuinely "
          f"empty/unreachable.")
    return {"slug": slug, "filled": filled, "remaining": len(missing)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Targeted gap-fill for chart slugs.")
    p.add_argument("slugs", nargs="+", help="Chart slugs to gap-fill.")
    p.add_argument("--rounds", type=int, default=4,
                   help="Max re-fetch rounds per slug (default 4).")
    p.add_argument("--delay", type=float, default=1.5,
                   help="Polite seconds between requests (default 1.5).")
    p.add_argument("--data-dir", default=None, help="Data directory override.")
    args = p.parse_args(argv)

    data_dir = args.data_dir or DATA_DIR
    summary = []
    try:
        for slug in args.slugs:
            summary.append(gapfill_slug(slug, data_dir, args.rounds, args.delay))
    except HardStopError as exc:
        print(f"HARD STOP (403/429): {exc}", file=sys.stderr)
        return 3

    print("\n=== gap-fill summary ===")
    for r in summary:
        print(f"  {r['slug']}: filled {r['filled']}, remaining {r['remaining']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
