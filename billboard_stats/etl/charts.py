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

import os
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
