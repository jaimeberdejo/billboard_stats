"""Main ETL orchestrator — loads Billboard JSON data into PostgreSQL."""

import logging
import os
from pathlib import Path

from psycopg2.extras import execute_values

from billboard_stats.db.connection import get_conn, put_conn, execute_script
from billboard_stats.etl.artist_parser import parse_artist_credit
from billboard_stats.etl.json_parser import list_chart_files, parse_hot100_file, parse_b200_file
from billboard_stats.etl.stats_builder import build_all_stats

logger = logging.getLogger(__name__)

# Batch size for bulk inserts
BATCH_SIZE = 1000


def run_etl(data_dir: str = None):
    """Run the full ETL pipeline.

    Args:
        data_dir: Root directory containing hot100/ and b200/ subdirectories.
                  Defaults to the project root.
    """
    if data_dir is None:
        data_dir = str(Path(__file__).resolve().parent.parent / "data")

    hot100_dir = os.path.join(data_dir, "hot100")
    b200_dir = os.path.join(data_dir, "b200")

    conn = get_conn()
    try:
        # Step 1: Create schema
        logger.info("Creating database schema...")
        _create_schema(conn)

        # Step 2: Load Hot 100
        logger.info("Loading Hot 100 data...")
        _load_hot100(conn, hot100_dir)

        # Step 3: Load Billboard 200
        logger.info("Loading Billboard 200 data...")
        _load_b200(conn, b200_dir)

        # Step 4: Build pre-computed stats
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


def _load_hot100(conn, directory: str, only_dates=None):
    """Load Hot 100 JSON files.

    Args:
        conn: Database connection.
        directory: Path to hot100/ directory.
        only_dates: Optional set of date strings (e.g. {'2026-02-01'}).
                    If provided, only files matching these dates are loaded.
    """
    files = list_chart_files(directory)
    if only_dates is not None:
        only_dates_set = set(only_dates)
        files = [(d, p) for d, p in files if d.isoformat() in only_dates_set]
    logger.info(f"Found {len(files)} Hot 100 chart files to load.")

    # Caches to avoid repeated lookups
    song_cache = {}     # (title, artist_credit) -> song_id
    artist_cache = {}   # name -> artist_id

    for i, (chart_date, file_path) in enumerate(files):
        entries = parse_hot100_file(file_path)
        if entries is None:
            logger.warning(f"Skipping invalid file: {file_path}")
            continue

        with conn.cursor() as cur:
            # Insert chart_week
            cur.execute(
                "INSERT INTO chart_weeks (chart_date, chart_type) "
                "VALUES (%s, 'hot-100') "
                "ON CONFLICT (chart_date, chart_type) DO UPDATE SET chart_date = EXCLUDED.chart_date "
                "RETURNING id;",
                (chart_date,),
            )
            chart_week_id = cur.fetchone()[0]

            # Prepare batch entries
            entry_rows = []
            for entry in entries:
                title = entry["title"]
                artist_credit = entry["artist"]
                cache_key = (title, artist_credit)

                # Upsert song
                if cache_key not in song_cache:
                    cur.execute(
                        "INSERT INTO songs (title, artist_credit, image_url) "
                        "VALUES (%s, %s, %s) "
                        "ON CONFLICT (title, artist_credit) DO UPDATE SET "
                        "image_url = COALESCE(NULLIF(EXCLUDED.image_url, songs.image_url), songs.image_url) "
                        "RETURNING id;",
                        (title, artist_credit, entry["image"]),
                    )
                    song_id = cur.fetchone()[0]
                    song_cache[cache_key] = song_id

                    # Parse and insert artist links
                    parsed = parse_artist_credit(artist_credit)
                    for artist_name, role in parsed:
                        if artist_name not in artist_cache:
                            cur.execute(
                                "INSERT INTO artists (name) VALUES (%s) "
                                "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
                                "RETURNING id;",
                                (artist_name,),
                            )
                            artist_cache[artist_name] = cur.fetchone()[0]

                        cur.execute(
                            "INSERT INTO song_artists (song_id, artist_id, role) "
                            "VALUES (%s, %s, %s) "
                            "ON CONFLICT DO NOTHING;",
                            (song_id, artist_cache[artist_name], role),
                        )
                else:
                    song_id = song_cache[cache_key]

                entry_rows.append((
                    chart_week_id, song_id, entry["rank"],
                    entry["peak_pos"], entry["last_pos"],
                    entry["weeks"], entry["is_new"],
                ))

            # Batch insert entries
            if entry_rows:
                execute_values(
                    cur,
                    "INSERT INTO hot100_entries "
                    "(chart_week_id, song_id, rank, peak_pos, last_pos, weeks_on_chart, is_new) "
                    "VALUES %s "
                    "ON CONFLICT (chart_week_id, rank) DO NOTHING;",
                    entry_rows,
                    page_size=BATCH_SIZE,
                )

        conn.commit()

        if (i + 1) % 500 == 0:
            logger.info(f"  Loaded {i + 1}/{len(files)} Hot 100 weeks...")

    logger.info(f"Hot 100 loading complete: {len(files)} weeks.")


def _load_b200(conn, directory: str, only_dates=None):
    """Load Billboard 200 JSON files.

    Args:
        conn: Database connection.
        directory: Path to b200/ directory.
        only_dates: Optional set of date strings (e.g. {'2026-02-01'}).
                    If provided, only files matching these dates are loaded.
    """
    files = list_chart_files(directory)
    if only_dates is not None:
        only_dates_set = set(only_dates)
        files = [(d, p) for d, p in files if d.isoformat() in only_dates_set]
    logger.info(f"Found {len(files)} Billboard 200 chart files to load.")

    album_cache = {}    # (title, artist_credit) -> album_id
    artist_cache = {}   # name -> artist_id

    # Pre-load existing artists
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM artists;")
        for row in cur.fetchall():
            artist_cache[row[1]] = row[0]

    for i, (chart_date, file_path) in enumerate(files):
        entries = parse_b200_file(file_path)
        if entries is None:
            logger.warning(f"Skipping invalid file: {file_path}")
            continue

        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chart_weeks (chart_date, chart_type) "
                "VALUES (%s, 'billboard-200') "
                "ON CONFLICT (chart_date, chart_type) DO UPDATE SET chart_date = EXCLUDED.chart_date "
                "RETURNING id;",
                (chart_date,),
            )
            chart_week_id = cur.fetchone()[0]

            entry_rows = []
            for entry in entries:
                title = entry["title"]
                artist_credit = entry["artist"]
                cache_key = (title, artist_credit)

                if cache_key not in album_cache:
                    cur.execute(
                        "INSERT INTO albums (title, artist_credit, image_url) "
                        "VALUES (%s, %s, %s) "
                        "ON CONFLICT (title, artist_credit) DO UPDATE SET "
                        "image_url = COALESCE(NULLIF(EXCLUDED.image_url, albums.image_url), albums.image_url) "
                        "RETURNING id;",
                        (title, artist_credit, entry["image"]),
                    )
                    album_id = cur.fetchone()[0]
                    album_cache[cache_key] = album_id

                    parsed = parse_artist_credit(artist_credit)
                    for artist_name, role in parsed:
                        if artist_name not in artist_cache:
                            cur.execute(
                                "INSERT INTO artists (name) VALUES (%s) "
                                "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
                                "RETURNING id;",
                                (artist_name,),
                            )
                            artist_cache[artist_name] = cur.fetchone()[0]

                        cur.execute(
                            "INSERT INTO album_artists (album_id, artist_id, role) "
                            "VALUES (%s, %s, %s) "
                            "ON CONFLICT DO NOTHING;",
                            (album_id, artist_cache[artist_name], role),
                        )
                else:
                    album_id = album_cache[cache_key]

                entry_rows.append((
                    chart_week_id, album_id, entry["rank"],
                    entry["peak_pos"], entry["last_pos"],
                    entry["weeks"], entry["is_new"],
                ))

            if entry_rows:
                execute_values(
                    cur,
                    "INSERT INTO b200_entries "
                    "(chart_week_id, album_id, rank, peak_pos, last_pos, weeks_on_chart, is_new) "
                    "VALUES %s "
                    "ON CONFLICT (chart_week_id, rank) DO NOTHING;",
                    entry_rows,
                    page_size=BATCH_SIZE,
                )

        conn.commit()

        if (i + 1) % 500 == 0:
            logger.info(f"  Loaded {i + 1}/{len(files)} Billboard 200 weeks...")

    logger.info(f"Billboard 200 loading complete: {len(files)} weeks.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_etl()
