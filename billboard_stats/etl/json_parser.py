"""Read and validate Billboard chart JSON files."""

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Expected date pattern in filenames
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\.json$")


def list_chart_files(directory: str) -> List[Tuple[date, str]]:
    """List all chart JSON files in a directory, sorted by date.

    Returns list of (chart_date, file_path) tuples.
    """
    results = []
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    for filename in os.listdir(directory):
        match = _DATE_RE.search(filename)
        if match:
            chart_date = date.fromisoformat(match.group(1))
            results.append((chart_date, str(dir_path / filename)))

    results.sort(key=lambda x: x[0])
    return results


def parse_chart_file(
    file_path: str, entity_kind: Optional[str] = None
) -> Optional[List[Dict]]:
    """Parse ANY Billboard chart JSON file into the normalized entry shape.

    This is the single parametric parser that collapses ``parse_hot100_file`` and
    ``parse_b200_file`` into one path. Each on-disk JSON shape differs only in the
    entity-name key:

    * legacy hot100 files use ``title``;
    * legacy billboard-200 files use ``album``;
    * Phase-7 new-chart files use ``title``;

    so the title field is read as ``item.get("title") or item.get("album")`` and
    all three shapes parse to the IDENTICAL normalized shape:
    ``rank, title, artist, peak_pos, last_pos, weeks, is_new, image``.

    Field rules: ``rank`` via :func:`_safe_int` (WR-06: tolerant, a non-numeric
    rank drops that one row via the ``rank > 0`` gate instead of crashing the
    whole file), ``peak_pos``/``last_pos``/``weeks`` via :func:`_safe_int`,
    ``is_new`` via ``bool(...)``, ``image`` via :func:`_clean_image_url`.

    Validity gate (Phase 11 / CHARTS-03): the kept-entry rule is entity-kind
    aware. The on-disk JSON does NOT encode ``entity_kind``, so the caller
    (``load_chart``) supplies it from the chart registry:

    * ``entity_kind == "artist"``: the ranked entity IS the artist, so an entry
      is kept when ``rank > 0`` AND ``artist`` (the title may be empty — ~4.3% of
      real artist-100 rows carry an empty title and must NOT be dropped).
    * every other kind, INCLUDING the default ``None``: keep the existing
      ``rank > 0`` AND ``title`` AND ``artist`` gate, byte-for-byte unchanged.

    Returns None if the file is invalid, malformed, missing, non-list, or empty
    (exactly as the v1.0 parsers did).
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(data, list) or len(data) == 0:
        return None

    entries = []
    for item in data:
        entry = {
            # WR-06: parse rank with the tolerant _safe_int (like every other
            # numeric field) instead of a bare int(...). A single malformed entry
            # (e.g. "rank": "N/A" or JSON null) would otherwise raise inside this
            # loop, uncaught (the try/except above wraps only the file open/load),
            # crashing the whole week's parse and — since load_chart does not wrap
            # parse_chart_file — the whole chart load. _safe_int returns None on a
            # bad rank; `None or 0` -> 0, which the `rank > 0` validity gate below
            # drops, so one bad row is skipped instead of aborting the file.
            "rank": _safe_int(item.get("rank")) or 0,
            # title-or-album fallback: legacy hot100 + Phase-7 new charts use the
            # "title" key; legacy b200 uses "album". This is the ONLY shape
            # difference across the three on-disk sources.
            "title": str(item.get("title") or item.get("album") or "").strip(),
            "artist": str(item.get("artist", "")).strip(),
            "peak_pos": _safe_int(item.get("peakPos")),
            "last_pos": _safe_int(item.get("lastPos")),
            "weeks": _safe_int(item.get("weeks")),
            "is_new": bool(item.get("isNew", False)),
            "image": _clean_image_url(item.get("image")),
        }
        # Entity-kind-aware validity gate (CHARTS-03): for an artist chart the
        # ranked entity IS the artist, so an empty title is valid; every other
        # kind (and the default None) keeps the title-AND-artist requirement.
        if entity_kind == "artist":
            valid = entry["rank"] > 0 and entry["artist"]
        else:
            valid = entry["rank"] > 0 and entry["title"] and entry["artist"]
        if valid:
            entries.append(entry)

    return entries if entries else None


def parse_hot100_file(file_path: str) -> Optional[List[Dict]]:
    """Compat shim: delegate to :func:`parse_chart_file`.

    Kept importable so callers that still reference the v1.0 parser name keep
    working until loader.py / updater.py are migrated to the registry path
    (Plans 10-02 / 10-03). Hot 100 files use the ``title`` key, which
    ``parse_chart_file`` reads first.
    """
    return parse_chart_file(file_path)


def parse_b200_file(file_path: str) -> Optional[List[Dict]]:
    """Compat shim: delegate to :func:`parse_chart_file`.

    Kept importable for the same transition reason as :func:`parse_hot100_file`.
    Billboard 200 files use the ``album`` key, which ``parse_chart_file`` reads
    via the ``title or album`` fallback -- producing output identical to the
    original ``parse_b200_file``.
    """
    return parse_chart_file(file_path)


def _safe_int(value) -> Optional[int]:
    """Convert a value to int, returning None if not possible."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _clean_image_url(url) -> Optional[str]:
    """Return a cleaned image URL or None for placeholder/lazy-load URLs."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url or "lazy-load" in url.lower() or url.startswith("data:"):
        return None
    return url
