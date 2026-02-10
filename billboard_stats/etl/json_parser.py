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


def parse_hot100_file(file_path: str) -> Optional[List[Dict]]:
    """Parse a Hot 100 JSON file.

    Each entry has: rank, title, artist, peakPos, lastPos, weeks, isNew, image.
    Returns None if the file is invalid or empty.
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
            "rank": int(item.get("rank", 0)),
            "title": str(item.get("title", "")).strip(),
            "artist": str(item.get("artist", "")).strip(),
            "peak_pos": _safe_int(item.get("peakPos")),
            "last_pos": _safe_int(item.get("lastPos")),
            "weeks": _safe_int(item.get("weeks")),
            "is_new": bool(item.get("isNew", False)),
            "image": _clean_image_url(item.get("image")),
        }
        if entry["rank"] > 0 and entry["title"] and entry["artist"]:
            entries.append(entry)

    return entries if entries else None


def parse_b200_file(file_path: str) -> Optional[List[Dict]]:
    """Parse a Billboard 200 JSON file.

    Each entry has: rank, album, artist, peakPos, lastPos, weeks, isNew, image.
    Returns None if the file is invalid or empty.
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
            "rank": int(item.get("rank", 0)),
            "title": str(item.get("album", "")).strip(),
            "artist": str(item.get("artist", "")).strip(),
            "peak_pos": _safe_int(item.get("peakPos")),
            "last_pos": _safe_int(item.get("lastPos")),
            "weeks": _safe_int(item.get("weeks")),
            "is_new": bool(item.get("isNew", False)),
            "image": _clean_image_url(item.get("image")),
        }
        if entry["rank"] > 0 and entry["title"] and entry["artist"]:
            entries.append(entry)

    return entries if entries else None


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
