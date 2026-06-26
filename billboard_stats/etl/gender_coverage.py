"""Read-only artist-gender coverage report (Phase 12 SPIKE harness).

Computes the gender-enrichment match rate over the ``artists`` table: total,
matched (``gender <> 'unknown'``), overall and per-source match rate, and the
full 5-value distribution. Optionally a chart-presence-weighted coverage (each
artist weighted by ``SUM(total_weeks)`` from ``artist_chart_stats``) so coverage
reflects the artists users actually see on leaderboards.

This is the SPIKE *harness* — the script is BUILT here; the actual MEASUREMENT
against the real loaded artist table + live-enriched data is a DEFERRED operator
step (see docs/GENDER-ENRICHMENT.md). It is strictly READ-ONLY: no writes, no
commit.

Design (mirrors the operator-script pattern):
* Injectable DB connection so tests pass an in-memory fake (no real DB).
* No top-level ``psycopg2`` import; ``get_conn`` / ``put_conn`` are imported
  lazily inside :func:`main`.
* Divide-by-zero safe (an empty artists table reports a 0.0 match rate).

Why a sub-~70% match rate matters: below ~70% (raw or weighted) coverage, a
gender filter that silently drops ``unknown`` artists hides a large, non-random
slice of the catalog — so Phase 14 must surface ``unknown`` as a first-class
filter facet rather than an all/female/male toggle. The deferred measurement
decides which framing Phase 14 ships.
"""

from __future__ import annotations

import argparse
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# The 5-value vocabulary, in a stable reporting order.
VOCAB = ("female", "male", "group", "mixed", "unknown")


def _rate(numerator: int, denominator: int) -> float:
    """Divide-by-zero-safe ratio (returns 0.0 when the denominator is 0)."""
    if not denominator:
        return 0.0
    return numerator / denominator


def coverage_report(conn, *, weighted: bool = False) -> Dict[str, object]:
    """Compute the gender-coverage report over ``artists``. Read-only.

    Args:
        conn: Injectable DB connection exposing ``cursor()`` (context manager).
        weighted: When True, also compute chart-presence-weighted coverage
            (artists weighted by ``SUM(total_weeks)`` from ``artist_chart_stats``).
            Guarded — absence of the table degrades gracefully to ``None``.

    Returns:
        A report dict with total / matched / match_rate, the per-source
        breakdown, the 5-value distribution (counts + pct), and (optionally) the
        weighted coverage block.
    """
    report: Dict[str, object] = {
        "total": 0,
        "matched": 0,
        "match_rate": 0.0,
        "by_source": {},
        "distribution": {},
        "weighted": None,
    }

    with conn.cursor() as cur:
        # Total artists (denominator).
        cur.execute("SELECT COUNT(*) FROM artists;")
        total = int(cur.fetchone()[0] or 0)
        report["total"] = total

        # 5-value distribution (counts), then derive matched + percentages.
        cur.execute("SELECT gender, COUNT(*) FROM artists GROUP BY gender;")
        counts = {gender: int(n or 0) for gender, n in cur.fetchall()}
        distribution = {
            value: {
                "count": counts.get(value, 0),
                "pct": _rate(counts.get(value, 0), total),
            }
            for value in VOCAB
        }
        # Include any unexpected gender value not in VOCAB (defensive).
        for gender, n in counts.items():
            if gender not in distribution:
                distribution[gender] = {"count": int(n or 0), "pct": _rate(n, total)}
        report["distribution"] = distribution

        matched = total - counts.get("unknown", 0)
        report["matched"] = matched
        report["match_rate"] = _rate(matched, total)

        # Per-source breakdown (musicbrainz | wikidata | manual | NULL).
        cur.execute(
            "SELECT gender_source, COUNT(*) FROM artists GROUP BY gender_source;"
        )
        by_source = {}
        for source, n in cur.fetchall():
            key = source if source is not None else "none"
            by_source[key] = {"count": int(n or 0), "rate": _rate(n, total)}
        report["by_source"] = by_source

        if weighted:
            report["weighted"] = _weighted_coverage(cur)

    return report


def _weighted_coverage(cur) -> Optional[Dict[str, object]]:
    """Chart-presence-weighted coverage; returns None if the table is absent.

    Weights each artist by SUM(total_weeks) from artist_chart_stats. A weighted
    match rate reflects the catalog users actually see on leaderboards.
    """
    try:
        cur.execute(
            "SELECT COALESCE(SUM(acs.total_weeks), 0) "
            "FROM artist_chart_stats acs;"
        )
        total_weight = int(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COALESCE(SUM(acs.total_weeks), 0) "
            "FROM artist_chart_stats acs "
            "JOIN artists a ON a.id = acs.artist_id "
            "WHERE a.gender <> 'unknown';"
        )
        matched_weight = int(cur.fetchone()[0] or 0)
    except Exception:
        # The table may not exist in some installs; degrade gracefully.
        logger.warning(
            "Weighted coverage unavailable (artist_chart_stats missing?)."
        )
        return None
    return {
        "total_weight": total_weight,
        "matched_weight": matched_weight,
        "match_rate": _rate(matched_weight, total_weight),
    }


def main(argv=None) -> int:
    """CLI entrypoint. The OPERATOR runs this against the real DB (DEFERRED).

    See docs/GENDER-ENRICHMENT.md — the coverage MEASUREMENT is a deferred
    operator step (needs the real loaded + enriched artist table).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Report artist-gender enrichment coverage (read-only; "
            "operator-run — see docs/GENDER-ENRICHMENT.md)."
        )
    )
    parser.add_argument(
        "--weighted", action="store_true",
        help="Also report chart-presence-weighted coverage (SUM(total_weeks)).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Lazy DB import so the module imports cleanly without psycopg2 (test env).
    from billboard_stats.db.connection import get_conn, put_conn

    conn = get_conn()
    try:
        report = coverage_report(conn, weighted=args.weighted)
    finally:
        put_conn(conn)

    total = report["total"]
    print(
        f"Gender coverage: {report['matched']}/{total} matched "
        f"({report['match_rate'] * 100:.1f}%)."
    )
    print("By source:")
    for source, info in sorted(report["by_source"].items()):
        print(f"  {source}: {info['count']} ({info['rate'] * 100:.1f}%)")
    print("Distribution:")
    for value in VOCAB:
        info = report["distribution"].get(value, {"count": 0, "pct": 0.0})
        print(f"  {value}: {info['count']} ({info['pct'] * 100:.1f}%)")
    if report["weighted"] is not None:
        w = report["weighted"]
        print(
            f"Weighted coverage: {w['matched_weight']}/{w['total_weight']} "
            f"({w['match_rate'] * 100:.1f}%)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
