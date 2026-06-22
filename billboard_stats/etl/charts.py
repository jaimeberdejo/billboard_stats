"""Curated Billboard chart slug list + live slug verification.

This module is the *source of truth* for the curated set of charts Phase 7
acquires (genre song charts, mirrored genre album charts, and Artist 100). It is
deliberately a small in-code list (NOT a database table — the chart registry
table is a later phase) plus a live verification spike that resolves each
candidate slug against ``billboard.ChartData(slug)`` and records its
``first_date``.

The downloader (``fetcher.download_chart``) and the operator backfill runner read
verified slugs + first_dates from the ``verified_charts.json`` sidecar written by
``verify_slugs`` so they never have to re-hit the network to know which slugs are
safe.

NOTHING here touches Postgres.
"""

import json
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Curated chart set (CHARTS-04)
# ---------------------------------------------------------------------------
#
# These slugs are *best-guess candidates* derived from billboard.com URL paths
# (see .planning/research/STACK.md). Slug confidence is MEDIUM — every slug is
# UNVERIFIED until ``verify_slugs`` resolves it live. If a candidate fails the
# live check, correct it here to the real Billboard slug and re-verify.
#
# Scope: 4 genre SONG charts, the 4 mirrored genre ALBUM charts, and Artist 100.
# Hot 100 / Billboard 200 are intentionally EXCLUDED (already on disk via the
# existing path). Component charts (Streaming/Radio/Sales) are deferred.

CURATED_CHARTS = [
    # --- Genre song charts (4) ---
    {
        "slug": "country-songs",
        "title": "Hot Country Songs",
        "entity_kind": "song",
        "category": "country",
        "candidate": True,
    },
    {
        "slug": "r-b-hip-hop-songs",
        "title": "Hot R&B/Hip-Hop Songs",
        "entity_kind": "song",
        "category": "r-b-hip-hop",
        "candidate": True,
    },
    {
        "slug": "rock-songs",
        "title": "Hot Rock & Alternative Songs",
        "entity_kind": "song",
        "category": "rock",
        "candidate": True,
    },
    {
        "slug": "latin-songs",
        "title": "Hot Latin Songs",
        "entity_kind": "song",
        "category": "latin",
        "candidate": True,
    },
    # --- Genre album charts (4, mirroring the same genres) ---
    {
        "slug": "country-albums",
        "title": "Top Country Albums",
        "entity_kind": "album",
        "category": "country",
        "candidate": True,
    },
    {
        "slug": "r-b-hip-hop-albums",
        "title": "Top R&B/Hip-Hop Albums",
        "entity_kind": "album",
        "category": "r-b-hip-hop",
        "candidate": True,
    },
    {
        "slug": "rock-albums",
        "title": "Top Rock & Alternative Albums",
        "entity_kind": "album",
        "category": "rock",
        "candidate": True,
    },
    {
        "slug": "latin-albums",
        "title": "Top Latin Albums",
        "entity_kind": "album",
        "category": "latin",
        "candidate": True,
    },
    # --- Artist chart (1) ---
    {
        "slug": "artist-100",
        "title": "Artist 100",
        "entity_kind": "artist",
        "category": "overall",
        "candidate": True,
    },
]


def get_chart(slug):
    """Look up a curated chart record by its slug.

    Args:
        slug: The chart slug (e.g. ``"country-songs"``).

    Returns:
        The matching chart record dict, or ``None`` if no curated chart has
        that slug.
    """
    for chart in CURATED_CHARTS:
        if chart["slug"] == slug:
            return chart
    return None


# Sidecar of verified (slug, first_date) results, written by ``verify_slugs``.
VERIFIED_CHARTS_PATH = str(Path(__file__).resolve().parent / "verified_charts.json")


# ---------------------------------------------------------------------------
# Live slug verification (CHARTS-04, success criterion #1)
# ---------------------------------------------------------------------------


class SlugVerificationError(Exception):
    """A curated slug failed live verification.

    Raised when ``billboard.ChartData(slug)`` errors (renamed/removed slug,
    HTTP error) OR resolves but returns zero entries. Always names the
    offending slug so failures are loud, never silent zero-row successes.
    """


def _earliest_known_date(chart):
    """Best-effort earliest available date for a fetched chart.

    billboard.py exposes ``date`` (this chart's date) and ``previousDate`` (the
    prior week's chart date). For the verification spike, capturing the latest
    chart's ``previousDate`` (falling back to ``date``) records a real recent
    date and confirms ``previousDate`` traversal works. The full walk-to-earliest
    is the operator's ``--full`` concern.

    Returns ``(first_date, unknown)`` where ``first_date`` is a date string or
    ``None`` and ``unknown`` is True when neither field was available (so the
    operator's FULL backfill does not silently scrape an empty range). We never
    silently substitute today's date.
    """
    previous = getattr(chart, "previousDate", None)
    current = getattr(chart, "date", None)
    # Prefer the older of the two real dates we can see.
    for candidate in (previous, current):
        if candidate:
            return candidate, False
    return None, True


def verify_slug(slug):
    """Live-verify a single slug against ``billboard.ChartData(slug)``.

    Makes one network call. Confirms the chart resolves with >= 1 entry and
    captures its ``first_date``.

    Returns:
        dict with ``slug``, ``verified``, ``first_date``, ``first_date_unknown``,
        and ``entry_count`` on success.

    Raises:
        SlugVerificationError: if the library raises (not-found / HTTP error)
            or the slug resolves to zero entries. The message names the slug.
    """
    import billboard

    try:
        chart = billboard.ChartData(slug)
    except Exception as exc:  # noqa: BLE001 - re-raise as a loud, named error
        raise SlugVerificationError(
            f"slug '{slug}' failed verification: {type(exc).__name__}: {exc}"
        ) from exc

    entry_count = len(list(chart))
    if entry_count == 0:
        raise SlugVerificationError(
            f"slug '{slug}' resolved but returned zero entries "
            "(renamed/removed chart must fail loudly, not silently)"
        )

    first_date, unknown = _earliest_known_date(chart)
    return {
        "slug": slug,
        "verified": True,
        "first_date": first_date,
        "first_date_unknown": unknown,
        "entry_count": entry_count,
    }


def verify_slugs(charts=None, sidecar_path=None, raise_on_failure=True, delay=1.5):
    """Verify a set of curated charts live, recording (slug, first_date).

    Args:
        charts: Iterable of chart records (defaults to ``CURATED_CHARTS``).
        sidecar_path: Where to write the verified-charts JSON sidecar. Defaults
            to ``VERIFIED_CHARTS_PATH``. Only written when ALL slugs pass.
        raise_on_failure: If True (default), re-raise on the first failing slug
            after recording results so the CLI exits non-zero. The sidecar is
            NOT written on any failure.
        delay: Polite seconds to wait between live requests.

    Returns:
        List of per-chart result dicts (each with ``slug``, ``verified``,
        ``first_date``, ``first_date_unknown``, ``entry_count``, and on failure
        ``error``).

    Raises:
        SlugVerificationError: when ``raise_on_failure`` and any slug failed.
    """
    if charts is None:
        charts = CURATED_CHARTS
    if sidecar_path is None:
        sidecar_path = VERIFIED_CHARTS_PATH

    charts = list(charts)
    results = []
    first_error = None

    for i, chart in enumerate(charts):
        slug = chart["slug"] if isinstance(chart, dict) else chart.slug
        try:
            res = verify_slug(slug)
            results.append(res)
        except SlugVerificationError as exc:
            results.append(
                {
                    "slug": slug,
                    "verified": False,
                    "first_date": None,
                    "first_date_unknown": True,
                    "entry_count": 0,
                    "error": str(exc),
                }
            )
            if first_error is None:
                first_error = exc
        if delay and i < len(charts) - 1:
            time.sleep(delay)

    if first_error is not None:
        if raise_on_failure:
            raise first_error
        return results

    # All passed -> persist the sidecar bridge for the downloader / runner.
    sidecar = [
        {
            "slug": r["slug"],
            "first_date": r["first_date"],
            "first_date_unknown": r["first_date_unknown"],
        }
        for r in results
    ]
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=2)

    return results


def _cli_verify(sidecar_path=None):
    """Run verification across CURATED_CHARTS, print a PASS/FAIL table.

    Returns a process exit code: 0 if all slugs passed, 1 if any failed.
    """
    if sidecar_path is None:
        sidecar_path = VERIFIED_CHARTS_PATH

    try:
        results = verify_slugs(sidecar_path=sidecar_path, raise_on_failure=False)
    except SlugVerificationError as exc:  # defensive; raise_on_failure=False above
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    any_failed = False
    print(f"{'SLUG':<22} {'STATUS':<6} {'FIRST_DATE':<12} ENTRIES")
    print("-" * 56)
    for r in results:
        status = "PASS" if r["verified"] else "FAIL"
        if not r["verified"]:
            any_failed = True
        first_date = r["first_date"] or ("?" if r["first_date_unknown"] else "")
        print(
            f"{r['slug']:<22} {status:<6} {str(first_date):<12} {r['entry_count']}"
        )
        if not r["verified"]:
            print(f"    -> {r.get('error', 'unknown error')}", file=sys.stderr)

    if any_failed:
        print("\nFAILED: one or more slugs did not verify.", file=sys.stderr)
        return 1

    print(f"\nOK: {len(results)} slugs verified; sidecar written to {sidecar_path}")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Curated Billboard chart slugs")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("verify", help="Live-verify every curated slug + first_date")

    args = parser.parse_args()
    if args.command == "verify":
        sys.exit(_cli_verify())
    parser.print_help()
