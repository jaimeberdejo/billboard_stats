"""Registry-driven ETL helper: yield one record per registered chart.

This is the foundational adapter the loader (Plan 10-02) and updater
(Plan 10-03) build against. It reads the DB ``charts`` table -- the runtime
SOURCE OF TRUTH for which charts the ETL loads (seeded by the Phase 9 migration
with hot-100=song, billboard-200=album) -- and yields one :class:`ChartRecord`
per chart carrying everything a loader needs to drive a parametric load:

    (slug, entity_kind, folder, last_loaded_date, legacy_table)

Distinct from ``charts.py`` CURATED_CHARTS, which is the Phase 7 ACQUISITION
curation (what to *download*); this registry is the LOAD list (what is in the DB
and therefore loaded into chart_entries).

Design constraints (per the Phase 10 CONTEXT decisions):

* ``folder`` maps each LEGACY chart to its REAL on-disk folder name
  (hot-100 -> ``data/hot100``, billboard-200 -> ``data/b200``) and every other
  chart to ``data/{slug}``. Returned as a path under ``data_dir``
  (default :data:`fetcher.DATA_DIR`). The folder is NOT stat-ed: a record is
  yielded even when the on-disk folder does not exist yet (the Phase 7 backfill
  may not have downloaded a chart), so callers decide whether to load.
* ``legacy_table`` is the dual-write target during the transition: hot-100 ->
  ``("hot100_entries", "song_id")``, billboard-200 -> ``("b200_entries",
  "album_id")``, every other chart -> ``None``. New charts never touch a legacy
  table.
* ``last_loaded_date`` is ``MAX(chart_weeks.chart_date)`` for the chart (``None``
  when no weeks are loaded yet -- the incremental start signal).
* psycopg2 is NEVER a top-level import (mirrors migrate_multichart.py): the
  module imports cleanly in the psycopg2-free test environment and tests inject a
  fake connection. A :class:`ChartRecord` is a plain NamedTuple usable with no DB.

This module makes NO real database connection and NO network calls during
automated execution; the real ``charts`` read is lazy / operator-time.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Iterator, List, NamedTuple, Optional, Tuple

# Legacy charts -> their REAL on-disk folder name (NOT the slug). New charts use
# the slug itself as the folder name.
_LEGACY_FOLDER: dict = {
    "hot-100": "hot100",
    "billboard-200": "b200",
}

# Legacy charts -> (dual-write v1.0 entry table, entity FK column). Every other
# chart writes only chart_entries (no legacy table).
_LEGACY_TABLE: dict = {
    "hot-100": ("hot100_entries", "song_id"),
    "billboard-200": ("b200_entries", "album_id"),
}


class ChartRecord(NamedTuple):
    """One registered chart, as the loader/updater consume it.

    Attributes:
        slug: The chart slug (e.g. ``"hot-100"``, ``"country-songs"``).
        entity_kind: ``"song"`` | ``"album"`` | ``"artist"`` -- drives which
            entity table the loader writes.
        folder: Absolute path to the chart's on-disk JSON folder under the
            supplied ``data_dir`` (legacy charts map to their real folder name;
            others to ``data/{slug}``). May not exist on disk yet.
        last_loaded_date: ``MAX(chart_weeks.chart_date)`` already loaded for this
            chart, or ``None`` when nothing is loaded (incremental start signal).
        legacy_table: ``(table_name, entity_fk_column)`` to dual-write for the
            two legacy charts, else ``None``.
    """

    slug: str
    entity_kind: str
    folder: str
    last_loaded_date: Optional[date]
    legacy_table: Optional[Tuple[str, str]]


def _resolve_folder(slug: str, data_dir: str) -> str:
    """Map a chart slug to its on-disk folder path under ``data_dir``.

    Legacy charts map to their real folder name (hot-100 -> hot100,
    billboard-200 -> b200); every other chart to ``data_dir/{slug}``. The path
    is NOT stat-ed -- an absent folder is fine (Phase 7 partial-folder
    tolerance).
    """
    folder_name = _LEGACY_FOLDER.get(slug, slug)
    return os.path.join(data_dir, folder_name)


def _resolve_legacy_table(slug: str) -> Optional[Tuple[str, str]]:
    """Map a chart slug to its dual-write ``(table, entity_fk)`` or ``None``."""
    return _LEGACY_TABLE.get(slug)


def iter_charts(
    conn,
    data_dir: Optional[str] = None,
    active_only: bool = True,
) -> Iterator[ChartRecord]:
    """Yield one :class:`ChartRecord` per registered chart from the DB.

    Issues a SINGLE read joining ``charts`` to a per-chart
    ``MAX(chart_weeks.chart_date)`` and yields a record per row. psycopg2 is not
    imported here; ``conn`` is any object exposing a psycopg2-style cursor (the
    tests inject a fake connection).

    Args:
        conn: A DB connection (real psycopg2 at operator-time, or a fake in
            tests) exposing ``conn.cursor()`` with ``execute`` / ``fetchall``.
        data_dir: Root data directory the chart folders live under. Defaults to
            :data:`fetcher.DATA_DIR` (imported lazily so importing this module
            never requires the data package side effects).
        active_only: When True (default) only charts with ``is_active = TRUE``
            are yielded (the weekly path only iterates active charts).

    Yields:
        :class:`ChartRecord` for each chart, in the order the DB returns them.

    Notes:
        Tolerant of a missing/partial on-disk folder: the folder path is built
        but never stat-ed, so a chart whose JSON folder does not exist yet is
        still yielded. Tolerant of an empty ``charts`` table (yields nothing,
        never raises).
    """
    if data_dir is None:
        # Lazy import so this module imports cleanly without the fetcher side
        # effects (and keeps a single canonical DATA_DIR default).
        from billboard_stats.etl.fetcher import DATA_DIR

        data_dir = DATA_DIR

    # One read: every chart + its max already-loaded chart_date. LEFT JOIN so a
    # chart with no loaded weeks still appears (last_loaded_date = NULL).
    if active_only:
        sql = (
            "SELECT c.slug, c.entity_kind, c.is_active, MAX(cw.chart_date) "
            "FROM charts c "
            "LEFT JOIN chart_weeks cw ON cw.chart_id = c.id "
            "WHERE c.is_active "
            "GROUP BY c.id, c.slug, c.entity_kind, c.is_active "
            "ORDER BY c.sort_order, c.id"
        )
    else:
        sql = (
            "SELECT c.slug, c.entity_kind, c.is_active, MAX(cw.chart_date) "
            "FROM charts c "
            "LEFT JOIN chart_weeks cw ON cw.chart_id = c.id "
            "GROUP BY c.id, c.slug, c.entity_kind, c.is_active "
            "ORDER BY c.sort_order, c.id"
        )

    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall() or []

    for row in rows:
        slug, entity_kind, _is_active, last_loaded_date = row
        yield ChartRecord(
            slug=slug,
            entity_kind=entity_kind,
            folder=_resolve_folder(slug, data_dir),
            last_loaded_date=last_loaded_date,
            legacy_table=_resolve_legacy_table(slug),
        )


def list_charts(
    conn,
    data_dir: Optional[str] = None,
    active_only: bool = True,
) -> List[ChartRecord]:
    """Eager :func:`iter_charts` -> a list, for callers that want to index/len."""
    return list(iter_charts(conn, data_dir=data_dir, active_only=active_only))
