"""Main ETL orchestrator — loads Billboard JSON data into PostgreSQL.

This is the registry-driven load path (Plan 10-02, DATA-06). The two hardcoded
``_load_hot100`` / ``_load_b200`` loaders are collapsed into ONE entity_kind-
dispatched :func:`load_chart`, and :func:`run_etl` drives it over the chart
registry (:func:`billboard_stats.etl.chart_registry.iter_charts`) instead of two
hardcoded calls.

Dual-write transition contract (CONTEXT decision): :func:`load_chart` ALWAYS
writes the new polymorphic ``chart_entries`` (and sets ``chart_weeks.chart_id``)
for every chart, AND for the two LEGACY charts ALSO writes the old
``hot100_entries`` / ``b200_entries`` tables via the registry's per-chart
``legacy_table`` mapping. This keeps the live v1.0 frontend fed until the Phase
13 cutover; NEW charts (``legacy_table=None``) write ``chart_entries`` only. The
legacy writes are strictly additive (same INSERT shape + ON CONFLICT
(chart_week_id, rank) DO NOTHING as v1.0) and are retired in Phase 15.

The psycopg2-dependent imports (``execute_values`` and the connection-pool
helpers ``get_conn`` / ``put_conn``) are GUARDED behind ``try/except ImportError``
so this module imports cleanly in the psycopg2-free test/CI environment, while
staying module-level names so the fixture tests can monkeypatch
``loader.execute_values`` (and ``parse_chart_file`` / ``list_chart_files``) over a
fake connection -- no real DB or network is touched. When psycopg2 IS installed
(the operator-run path) the names bind to the real implementations and behavior
is identical to the v1.0 loader. (Mirrors updater.py's psycopg2-free hygiene.)
"""

from __future__ import annotations

import logging
from pathlib import Path

try:
    from psycopg2.extras import execute_values
except ImportError:  # test/CI env without psycopg2
    execute_values = None

try:
    from billboard_stats.db.connection import get_conn, put_conn
except ImportError:  # test/CI env without psycopg2 (connection pool needs it)
    get_conn = put_conn = None

from billboard_stats.etl.artist_parser import parse_artist_credit
from billboard_stats.etl.chart_registry import iter_charts
from billboard_stats.etl.json_parser import list_chart_files, parse_chart_file
from billboard_stats.etl.stats_builder import build_all_stats

logger = logging.getLogger(__name__)

# Batch size for bulk inserts
BATCH_SIZE = 1000

# entity_kind -> the entity table, its link table, the FK column on the link
# table pointing at the entity, and the chart_entries FK column for that entity.
# Drives the single parametric load path: song -> songs/song_artists,
# album -> albums/album_artists, artist -> artists directly (no link table; the
# artist branch is structurally present so Phase 11's Artist 100 needs no loader
# change, but it is NOT exercised in this phase).
_ENTITY_DISPATCH = {
    "song": {
        "entity_table": "songs",
        "link_table": "song_artists",
        "link_fk": "song_id",
        "ce_fk": "song_id",
    },
    "album": {
        "entity_table": "albums",
        "link_table": "album_artists",
        "link_fk": "album_id",
        "ce_fk": "album_id",
    },
    "artist": {
        # Artist-entity charts carry artist_id directly on the chart_entries row;
        # there is no intermediary entity/link table.
        "entity_table": "artists",
        "link_table": None,
        "link_fk": None,
        "ce_fk": "artist_id",
    },
}


def run_etl(data_dir: str = None):
    """Run the full registry-driven ETL pipeline.

    Creates the schema, then loops the chart registry
    (:func:`iter_charts`) calling :func:`load_chart` per chart (replacing the two
    hardcoded ``_load_hot100`` / ``_load_b200`` calls), then builds BOTH the v1.0
    ``artist_stats`` and the new ``artist_chart_stats`` via :func:`build_all_stats`.

    A chart whose on-disk folder is absent or partial (the Phase 7 backfill may
    not have downloaded it yet) is skipped with a log line, never a crash.

    Args:
        data_dir: Root directory containing the per-chart subdirectories.
                  Defaults to the project ``data`` directory.
    """
    if data_dir is None:
        data_dir = str(Path(__file__).resolve().parent.parent / "data")

    conn = get_conn()
    try:
        logger.info("Creating database schema...")
        _create_schema(conn)

        logger.info("Loading charts from registry...")
        for chart in iter_charts(conn, data_dir=data_dir):
            if not Path(chart.folder).is_dir():
                logger.warning(
                    "Skipping chart %s: folder not found: %s",
                    chart.slug,
                    chart.folder,
                )
                continue
            logger.info("Loading chart %s (%s)...", chart.slug, chart.entity_kind)
            load_chart(conn, chart, data_dir=data_dir)

        logger.info("Building pre-computed stats...")
        build_all_stats(conn)

        logger.info("ETL complete.")
    finally:
        put_conn(conn)


def _create_schema(conn):
    """Execute the schema DDL."""
    schema_path = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
    with open(schema_path, "r") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def load_chart(conn, chart, only_dates=None, data_dir=None):
    """Load one registered chart's JSON into the DB, dual-writing the transition.

    ONE entity_kind-dispatched loader replacing ``_load_hot100`` /
    ``_load_b200``. For each week file under ``chart.folder`` it:

    1. Upserts the ``chart_weeks`` row keyed by the existing
       ``UNIQUE(chart_date, chart_type)`` for the LEGACY charts, ALSO setting
       ``chart_weeks.chart_id`` to the registry id (``SET chart_id =
       EXCLUDED.chart_id``) so BOTH the v1.0 chart_type-literal phantom CTE and
       the new chart_id-keyed parametric CTE resolve the week. (The new-chart
       week path, keyed by chart_id only, is structurally present but NOT
       exercised in this phase -- only the two legacy charts run.)
    2. Dispatches on ``chart.entity_kind``: song -> upsert ``songs`` +
       ``song_artists`` (via :func:`parse_artist_credit`); album -> upsert
       ``albums`` + ``album_artists``; artist -> upsert/lookup ``artists`` and
       set ``chart_entries.artist_id`` directly.
    3. DUAL-WRITE: ALWAYS batch-inserts ``chart_entries`` (chart_id, chart_week_id,
       the ONE entity FK, rank, peak_pos, last_pos, weeks_on_chart, is_new) with
       ``ON CONFLICT (chart_week_id, rank) DO NOTHING``. THEN, when
       ``chart.legacy_table`` is not None, ALSO batch-inserts the mapped legacy
       table (``hot100_entries``/song_id or ``b200_entries``/album_id) from the
       SAME entry rows with the SAME conflict clause -- exactly as the v1.0
       loaders did. NEW charts (``legacy_table=None``) write ``chart_entries``
       only.

    Args:
        conn: DB connection (real psycopg2 at operator-time, fake in tests).
        chart: A :class:`~billboard_stats.etl.chart_registry.ChartRecord`.
        only_dates: Optional set/iterable of ISO date strings; when provided,
            only week files matching these dates are loaded.
        data_dir: Unused here (the folder already lives on ``chart.folder``);
            accepted for a uniform call signature with the updater path.
    """
    dispatch = _ENTITY_DISPATCH.get(chart.entity_kind)
    if dispatch is None:
        logger.warning(
            "Skipping chart %s: unknown entity_kind %r",
            chart.slug,
            chart.entity_kind,
        )
        return

    files = list_chart_files(chart.folder)
    if only_dates is not None:
        only_dates_set = set(only_dates)
        files = [(d, p) for d, p in files if d.isoformat() in only_dates_set]
    logger.info("Found %d %s chart files to load.", len(files), chart.slug)

    chart_id = _resolve_chart_id(conn, chart.slug)

    # W1 (artist_cache strategy): the v1.0 _load_b200 pre-loaded the artist_cache
    # from the DB while _load_hot100 started empty. The unified load_chart uses
    # ONE consistent strategy -- ALWAYS pre-load the cache from artists -- so a
    # second chart's load reuses artist ids resolved by an earlier chart instead
    # of issuing redundant ON CONFLICT upserts. This is purely an optimization
    # (the artist INSERT still uses ON CONFLICT (name) DO UPDATE ... RETURNING
    # id), so it changes NO rows vs. either v1.0 path -- the equivalence tests
    # assert song_artists / album_artists parity to prove it.
    artist_cache = {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM artists;")
        for row in cur.fetchall() or []:
            artist_cache[row[1]] = row[0]

    entity_cache = {}  # (title, artist_credit) -> entity_id (song/album)

    for i, (chart_date, file_path) in enumerate(files):
        entries = parse_chart_file(file_path)
        if entries is None:
            logger.warning("Skipping invalid file: %s", file_path)
            continue

        with conn.cursor() as cur:
            chart_week_id = _upsert_chart_week(
                cur, chart_date, chart.legacy_table, chart_id
            )

            ce_rows = []      # chart_entries batch
            legacy_rows = []  # legacy table batch (only when legacy_table set)

            for entry in entries:
                entity_id = _resolve_entity(
                    cur, chart, dispatch, entry, entity_cache, artist_cache
                )

                # chart_entries row: exactly ONE entity FK is non-null.
                song_id = entity_id if dispatch["ce_fk"] == "song_id" else None
                album_id = entity_id if dispatch["ce_fk"] == "album_id" else None
                artist_id = entity_id if dispatch["ce_fk"] == "artist_id" else None
                ce_rows.append((
                    chart_id, chart_week_id, song_id, album_id, artist_id,
                    entry["rank"], entry["peak_pos"], entry["last_pos"],
                    entry["weeks"], entry["is_new"],
                ))

                if chart.legacy_table is not None:
                    # Same entry shape the v1.0 loaders wrote: (chart_week_id,
                    # entity_id, rank, peak_pos, last_pos, weeks_on_chart, is_new).
                    legacy_rows.append((
                        chart_week_id, entity_id, entry["rank"],
                        entry["peak_pos"], entry["last_pos"],
                        entry["weeks"], entry["is_new"],
                    ))

            # ALWAYS write chart_entries.
            if ce_rows:
                execute_values(
                    cur,
                    "INSERT INTO chart_entries "
                    "(chart_id, chart_week_id, song_id, album_id, artist_id, "
                    "rank, peak_pos, last_pos, weeks_on_chart, is_new) "
                    "VALUES %s "
                    "ON CONFLICT (chart_week_id, rank) DO NOTHING;",
                    ce_rows,
                    page_size=BATCH_SIZE,
                )

            # DUAL-WRITE: for legacy charts ONLY, also write the mapped legacy
            # table with the SAME entry rows + same conflict clause.
            if chart.legacy_table is not None and legacy_rows:
                legacy_table, legacy_fk = chart.legacy_table
                execute_values(
                    cur,
                    f"INSERT INTO {legacy_table} "
                    f"(chart_week_id, {legacy_fk}, rank, peak_pos, last_pos, "
                    f"weeks_on_chart, is_new) "
                    f"VALUES %s "
                    f"ON CONFLICT (chart_week_id, rank) DO NOTHING;",
                    legacy_rows,
                    page_size=BATCH_SIZE,
                )

        conn.commit()

        if (i + 1) % 500 == 0:
            logger.info("  Loaded %d/%d %s weeks...", i + 1, len(files), chart.slug)

    logger.info("%s loading complete: %d weeks.", chart.slug, len(files))


def _resolve_chart_id(conn, slug):
    """Look up the registry id for a chart slug (chart_weeks.chart_id target)."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM charts WHERE slug = %s;", (slug,))
        row = cur.fetchone()
    return row[0] if row else None


def _upsert_chart_week(cur, chart_date, legacy_table, chart_id):
    """Upsert the chart_weeks row and return its id.

    For LEGACY charts the upsert keys on the existing UNIQUE(chart_date,
    chart_type) -- supplying chart_type (derived from the legacy table mapping)
    AND setting chart_id = EXCLUDED.chart_id so both phantom CTEs resolve. Do NOT
    attempt a chart_id-keyed week upsert here: there is no UNIQUE on chart_id.

    The new-chart branch (no chart_type) is structurally present for Phase 11 but
    NOT exercised this phase (only the two legacy charts run).
    """
    if legacy_table is not None:
        chart_type = _legacy_chart_type(legacy_table)
        cur.execute(
            "INSERT INTO chart_weeks (chart_date, chart_type, chart_id) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (chart_date, chart_type) DO UPDATE SET "
            "chart_id = EXCLUDED.chart_id "
            "RETURNING id;",
            (chart_date, chart_type, chart_id),
        )
        return cur.fetchone()[0]

    # New-chart path (NOT exercised in Phase 10): the week is identified by
    # chart_id + chart_date. There is no UNIQUE(chart_id, chart_date) yet, so
    # this branch is reserved for the Phase 11 ingest (which adds the constraint
    # / dedicated path). Kept structurally present per the plan.
    cur.execute(
        "INSERT INTO chart_weeks (chart_date, chart_id) "
        "VALUES (%s, %s) "
        "RETURNING id;",
        (chart_date, chart_id),
    )
    return cur.fetchone()[0]


def _legacy_chart_type(legacy_table):
    """Map a legacy (table, fk) tuple back to its chart_type literal."""
    table_name = legacy_table[0]
    if table_name == "hot100_entries":
        return "hot-100"
    if table_name == "b200_entries":
        return "billboard-200"
    raise ValueError(f"Unknown legacy table: {table_name!r}")


def _resolve_entity(cur, chart, dispatch, entry, entity_cache, artist_cache):
    """Upsert the entity (song|album|artist) for an entry and return its id.

    For song/album charts this upserts the entity row and its artist links
    (via :func:`parse_artist_credit`), caching by (title, artist_credit). For
    artist charts it upserts/looks up the artist directly (no link table).
    """
    title = entry["title"]
    artist_credit = entry["artist"]

    if chart.entity_kind == "artist":
        # Artist-entity charts: the ranked entity IS the artist. Upsert/lookup
        # the artist by the credit (treated as the artist name) and return its id
        # directly -- no song/album indirection. NOT exercised in Phase 10.
        return _upsert_artist(cur, artist_credit, artist_cache)

    cache_key = (title, artist_credit)
    if cache_key in entity_cache:
        return entity_cache[cache_key]

    entity_table = dispatch["entity_table"]
    cur.execute(
        f"INSERT INTO {entity_table} (title, artist_credit, image_url) "
        f"VALUES (%s, %s, %s) "
        f"ON CONFLICT (title, artist_credit) DO UPDATE SET "
        f"image_url = COALESCE(NULLIF(EXCLUDED.image_url, "
        f"{entity_table}.image_url), {entity_table}.image_url) "
        f"RETURNING id;",
        (title, artist_credit, entry["image"]),
    )
    entity_id = cur.fetchone()[0]
    entity_cache[cache_key] = entity_id

    # Link artists.
    link_table = dispatch["link_table"]
    link_fk = dispatch["link_fk"]
    for artist_name, role in parse_artist_credit(artist_credit):
        artist_id = _upsert_artist(cur, artist_name, artist_cache)
        cur.execute(
            f"INSERT INTO {link_table} ({link_fk}, artist_id, role) "
            f"VALUES (%s, %s, %s) "
            f"ON CONFLICT DO NOTHING;",
            (entity_id, artist_id, role),
        )

    return entity_id


def _upsert_artist(cur, name, artist_cache):
    """Upsert an artist by name, caching the id. ON CONFLICT (name) DO UPDATE."""
    if name in artist_cache:
        return artist_cache[name]
    cur.execute(
        "INSERT INTO artists (name) VALUES (%s) "
        "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
        "RETURNING id;",
        (name,),
    )
    artist_id = cur.fetchone()[0]
    artist_cache[name] = artist_id
    return artist_id


# ---------------------------------------------------------------------------
# Compatibility shims (kept importable until Plan 03 migrates updater.py).
# These delegate to load_chart for the corresponding legacy ChartRecord so any
# caller still referencing the v1.0 loader names keeps working during the
# transition. run_etl itself NO LONGER calls these -- it loops the registry.
# ---------------------------------------------------------------------------
def _load_hot100(conn, directory: str, only_dates=None):
    """Compat shim: load the hot-100 legacy chart via :func:`load_chart`."""
    from billboard_stats.etl.chart_registry import ChartRecord

    chart = ChartRecord(
        slug="hot-100",
        entity_kind="song",
        folder=directory,
        last_loaded_date=None,
        legacy_table=("hot100_entries", "song_id"),
    )
    load_chart(conn, chart, only_dates=only_dates)


def _load_b200(conn, directory: str, only_dates=None):
    """Compat shim: load the billboard-200 legacy chart via :func:`load_chart`."""
    from billboard_stats.etl.chart_registry import ChartRecord

    chart = ChartRecord(
        slug="billboard-200",
        entity_kind="album",
        folder=directory,
        last_loaded_date=None,
        legacy_table=("b200_entries", "album_id"),
    )
    load_chart(conn, chart, only_dates=only_dates)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_etl()
