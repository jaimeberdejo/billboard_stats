"""Idempotent, additive multi-chart migration runner (DATA-01 / DATA-02).

Takes an EXISTING v1.0 production database from the bifurcated
hot100_entries/b200_entries shape to the generalized multi-chart shape WITHOUT
mutating anything the unchanged v1.0 frontend reads. The migration is
operator-applied via the CLI (``main``) per the runbook; ``migrate`` takes an
INJECTABLE connection so tests can pass an in-memory fake DB.

Design / safety contract (mirrors billboard_stats/etl/reconcile_artists.py):

* DB access goes through an INJECTABLE connection (``cursor()`` context manager,
  ``commit()``, ``rollback()``). The SQL runs unchanged against real PostgreSQL.
* The migration is STRICTLY ADDITIVE and IDEMPOTENT:
    1. applies the additive DDL from db/migrations/001_multichart.sql, guarded by
       IF NOT EXISTS (so fresh + existing installs converge, re-apply is a no-op);
    2. seeds the ``charts`` registry — hot-100 -> entity_kind=song,
       billboard-200 -> entity_kind=album — with ON CONFLICT (slug) DO NOTHING;
    3. backfills ``chart_weeks.chart_id`` from the existing ``chart_type``
       (NULL-only; KEEPS chart_type populated);
    4. backfills ``chart_entries`` from ``hot100_entries`` (song_id set) and
       ``b200_entries`` (album_id set) — exactly ONE entity FK per row so the
       num_nonnulls(...) = 1 CHECK holds — skipping already-migrated rows via
       ON CONFLICT (chart_week_id, rank) DO NOTHING.
* Everything runs in a SINGLE transaction on ONE connection. After the backfill
  it asserts row-count PARITY on TOTAL post-backfill counts:
    count(chart_entries WHERE chart_id = hot-100)     == count(hot100_entries)
    count(chart_entries WHERE chart_id = billboard-200) == count(b200_entries)
    count(chart_entries)                              == hot100_entries + b200_entries
  and that no known chart_type week is left with a NULL chart_id. Comparing
  TOTAL counts (not "rows inserted this run") means an idempotent re-run with
  zero inserts still passes parity. It ALSO asserts CONTENT parity (WR-03): an
  anti-join in both directions proves every backfilled chart_entries row
  round-trips its v1.0 source on (chart_week_id, rank, entity_id) and that the
  one-of-three entity-FK invariant holds -- so a wrong-but-equal-count backfill
  (right number of rows, wrong song_id/album_id/rank/week) is caught and rolled
  back. On any mismatch it calls ``rollback()`` and raises
  ``MigrationParityError``; it commits only if every assertion holds.
* ``--dry-run`` reports the planned seed/backfill counts and writes nothing,
  exiting 0.
* psycopg2 is imported LAZILY inside ``main()`` so the module imports cleanly in
  the psycopg2-free test environment.
* This module NEVER connects to a real database during automated execution and
  NEVER builds stats — the real-DB apply is the operator runbook (Plan 03).
"""

from __future__ import annotations

import argparse
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# The two core charts this migration seeds. (slug, title, entity_kind, category,
# sort_order). entity_kind is the load-bearing field.
_SEED_CHARTS: List[Tuple[str, str, str, str, int]] = [
    ("hot-100", "Billboard Hot 100", "song", "core", 1),
    ("billboard-200", "Billboard 200", "album", "core", 2),
]

# Maps each seeded chart slug to the v1.0 source entry table + entity column the
# chart_entries backfill copies from.
_BACKFILL_SOURCES: List[Tuple[str, str, str]] = [
    ("hot-100", "hot100_entries", "song_id"),
    ("billboard-200", "b200_entries", "album_id"),
]


class MigrationParityError(RuntimeError):
    """Raised when a row-count parity assertion fails; triggers rollback."""


# ----------------------------------------------------------------------------
# DDL: the additive statements from db/migrations/001_multichart.sql, guarded by
# IF NOT EXISTS. Kept byte-consistent with db/schema.sql's Phase 9 block so a
# fresh install and an existing install converge.
# ----------------------------------------------------------------------------
_DDL_STATEMENTS: List[str] = [
    """
    CREATE TABLE IF NOT EXISTS charts (
        id          SERIAL PRIMARY KEY,
        slug        VARCHAR(64) NOT NULL UNIQUE,
        title       VARCHAR(128),
        entity_kind VARCHAR(16) NOT NULL CHECK (entity_kind IN ('song', 'album', 'artist')),
        category    VARCHAR(32),
        is_active   BOOLEAN NOT NULL DEFAULT TRUE,
        first_date  DATE,
        sort_order  SMALLINT NOT NULL DEFAULT 100
    );
    """,
    "ALTER TABLE chart_weeks ADD COLUMN IF NOT EXISTS chart_id INT REFERENCES charts(id);",
    """
    CREATE TABLE IF NOT EXISTS chart_entries (
        id              BIGSERIAL PRIMARY KEY,
        chart_id        INT NOT NULL REFERENCES charts(id),
        chart_week_id   INT NOT NULL REFERENCES chart_weeks(id),
        song_id         INT REFERENCES songs(id),
        album_id        INT REFERENCES albums(id),
        artist_id       INT REFERENCES artists(id),
        rank            SMALLINT NOT NULL,
        peak_pos        SMALLINT,
        last_pos        SMALLINT,
        weeks_on_chart  SMALLINT,
        is_new          BOOLEAN NOT NULL DEFAULT FALSE,
        UNIQUE (chart_week_id, rank),
        CHECK (num_nonnulls(song_id, album_id, artist_id) = 1)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS artist_chart_stats (
        artist_id        INT  NOT NULL REFERENCES artists(id),
        chart_id         INT  NOT NULL REFERENCES charts(id),
        total_entries    INT  NOT NULL DEFAULT 0,
        total_weeks      INT  NOT NULL DEFAULT 0,
        number_ones      INT  NOT NULL DEFAULT 0,
        best_peak        SMALLINT,
        max_simultaneous INT  NOT NULL DEFAULT 0,
        first_date       DATE,
        last_date        DATE,
        PRIMARY KEY (artist_id, chart_id)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_ce_chart ON chart_entries(chart_id);",
    "CREATE INDEX IF NOT EXISTS idx_ce_week ON chart_entries(chart_week_id);",
    "CREATE INDEX IF NOT EXISTS idx_ce_song ON chart_entries(song_id) WHERE song_id IS NOT NULL;",
    "CREATE INDEX IF NOT EXISTS idx_ce_album ON chart_entries(album_id) WHERE album_id IS NOT NULL;",
    "CREATE INDEX IF NOT EXISTS idx_ce_artist ON chart_entries(artist_id) WHERE artist_id IS NOT NULL;",
    "CREATE INDEX IF NOT EXISTS idx_acs_chart ON artist_chart_stats(chart_id);",
]


def _count(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    return cur.fetchone()[0]


def _chart_id(cur, slug: str) -> Optional[int]:
    cur.execute("SELECT id FROM charts WHERE slug = %s;", (slug,))
    row = cur.fetchone()
    return row[0] if row else None


def migrate(conn, *, dry_run: bool = False) -> Dict[str, object]:
    """Apply the additive multi-chart migration on the injected connection.

    Args:
        conn: An injectable DB connection exposing ``cursor()`` (context
            manager), ``commit()``, and ``rollback()``.
        dry_run: When True, compute and report the planned seed/backfill counts
            and return WITHOUT writing or committing.

    Returns:
        A report dict: ``dry_run`` flag, ``seeded_charts`` (rows actually
        inserted this run), per-chart ``backfill`` counts (rows inserted this
        run), and ``before`` / ``after`` total counts.

    Raises:
        MigrationParityError: if any post-backfill row-count parity assertion
            fails (the connection is rolled back first).
    """
    report: Dict[str, object] = {
        "dry_run": dry_run,
        "seeded_charts": 0,
        "backfill": {slug: 0 for slug, _src, _col in _BACKFILL_SOURCES},
        "before": None,
        "after": None,
    }

    try:
        with conn.cursor() as cur:
            # --- Source + pre-existing counts (single transaction) -----------
            src_hot100 = _count(cur, "SELECT COUNT(*) FROM hot100_entries;")
            src_b200 = _count(cur, "SELECT COUNT(*) FROM b200_entries;")
            before_ce = _count(cur, "SELECT COUNT(*) FROM chart_entries;")
            report["before"] = {
                "hot100_entries": src_hot100,
                "b200_entries": src_b200,
                "chart_entries": before_ce,
            }

            # --- DRY RUN: report the planned writes, change nothing ----------
            if dry_run:
                # Planned seeds = charts not already present.
                planned_seeds = 0
                for slug, _title, _kind, _cat, _ord in _SEED_CHARTS:
                    if _chart_id(cur, slug) is None:
                        planned_seeds += 1
                report["seeded_charts"] = planned_seeds

                # Planned backfill = source rows that would actually INSERT,
                # using the SAME conflict semantics the real backfill uses
                # (ON CONFLICT (chart_week_id, rank) DO NOTHING) rather than a
                # chart_id-count subtraction (WR-04). The previous
                # `max(total - count(chart_entries WHERE chart_id=slug), 0)`
                # silently assumed every existing chart_entries row corresponds
                # to a source row that would conflict-skip; that diverges from
                # the real ON CONFLICT count whenever the table already holds
                # rows at (chart_week_id, rank) pairs not in the source (or vice
                # versa), mis-reporting the operator's go/no-go number. Counting
                # source rows whose (chart_week_id, rank) is not yet present
                # matches the real insert exactly. With a pristine DB this is the
                # full source count; a re-run reports 0.
                planned_backfill = {
                    "hot-100": _count(
                        cur,
                        "SELECT COUNT(*) FROM hot100_entries h "
                        "WHERE NOT EXISTS ("
                        "  SELECT 1 FROM chart_entries ce "
                        "  WHERE ce.chart_week_id = h.chart_week_id "
                        "    AND ce.rank = h.rank);",
                    ),
                    "billboard-200": _count(
                        cur,
                        "SELECT COUNT(*) FROM b200_entries b "
                        "WHERE NOT EXISTS ("
                        "  SELECT 1 FROM chart_entries ce "
                        "  WHERE ce.chart_week_id = b.chart_week_id "
                        "    AND ce.rank = b.rank);",
                    ),
                }
                for slug, _src, _col in _BACKFILL_SOURCES:
                    report["backfill"][slug] = planned_backfill[slug]

                logger.info(
                    "Dry run: %d chart(s) to seed, backfill +%d hot-100 / +%d "
                    "billboard-200 chart_entries; writing nothing.",
                    report["seeded_charts"],
                    report["backfill"]["hot-100"],
                    report["backfill"]["billboard-200"],
                )
                return report

            # --- 1. DDL (additive; IF NOT EXISTS) ----------------------------
            for stmt in _DDL_STATEMENTS:
                cur.execute(stmt)

            # --- 2. Seed the charts registry (ON CONFLICT (slug) DO NOTHING) -
            seeded = 0
            for slug, title, kind, cat, sort_order in _SEED_CHARTS:
                before_id = _chart_id(cur, slug)
                cur.execute(
                    "INSERT INTO charts (slug, title, entity_kind, category, sort_order) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (slug) DO NOTHING;",
                    (slug, title, kind, cat, sort_order),
                )
                if before_id is None and _chart_id(cur, slug) is not None:
                    seeded += 1
            report["seeded_charts"] = seeded

            # --- 3. Backfill chart_weeks.chart_id from chart_type ------------
            cur.execute(
                "UPDATE chart_weeks SET chart_id = "
                "(SELECT id FROM charts WHERE slug = chart_weeks.chart_type) "
                "WHERE chart_id IS NULL;"
            )

            # --- 4. Backfill chart_entries (conflict-skipping) ---------------
            hot100_id = _chart_id(cur, "hot-100")
            b200_id = _chart_id(cur, "billboard-200")

            before_hot100_ce = _count(
                cur,
                "SELECT COUNT(*) FROM chart_entries WHERE chart_id = %s;",
                (hot100_id,),
            )
            # JOIN chart_weeks ON cw.chart_type = 'hot-100' scopes the backfill
            # to rows whose source week is actually a hot-100 week (WR-02), so
            # chart_entries.chart_id can never disagree with the referenced
            # week's chart_id even if a stray entry pointed at the wrong type.
            cur.execute(
                "INSERT INTO chart_entries "
                "(chart_id, chart_week_id, song_id, rank, peak_pos, last_pos, "
                "weeks_on_chart, is_new) "
                "SELECT (SELECT id FROM charts WHERE slug = 'hot-100'), "
                "h.chart_week_id, h.song_id, h.rank, h.peak_pos, h.last_pos, "
                "h.weeks_on_chart, h.is_new "
                "FROM hot100_entries h "
                "JOIN chart_weeks cw ON cw.id = h.chart_week_id "
                "AND cw.chart_type = 'hot-100' "
                "ON CONFLICT (chart_week_id, rank) DO NOTHING;"
            )
            after_hot100_ce = _count(
                cur,
                "SELECT COUNT(*) FROM chart_entries WHERE chart_id = %s;",
                (hot100_id,),
            )
            report["backfill"]["hot-100"] = after_hot100_ce - before_hot100_ce

            before_b200_ce = _count(
                cur,
                "SELECT COUNT(*) FROM chart_entries WHERE chart_id = %s;",
                (b200_id,),
            )
            # Symmetric chart_type scoping to the hot-100 backfill above (WR-02).
            cur.execute(
                "INSERT INTO chart_entries "
                "(chart_id, chart_week_id, album_id, rank, peak_pos, last_pos, "
                "weeks_on_chart, is_new) "
                "SELECT (SELECT id FROM charts WHERE slug = 'billboard-200'), "
                "b.chart_week_id, b.album_id, b.rank, b.peak_pos, b.last_pos, "
                "b.weeks_on_chart, b.is_new "
                "FROM b200_entries b "
                "JOIN chart_weeks cw ON cw.id = b.chart_week_id "
                "AND cw.chart_type = 'billboard-200' "
                "ON CONFLICT (chart_week_id, rank) DO NOTHING;"
            )
            after_b200_ce = _count(
                cur,
                "SELECT COUNT(*) FROM chart_entries WHERE chart_id = %s;",
                (b200_id,),
            )
            report["backfill"]["billboard-200"] = after_b200_ce - before_b200_ce

            # --- 5. PARITY ASSERTIONS on TOTAL post-backfill counts ----------
            total_hot100_ce = after_hot100_ce
            total_b200_ce = after_b200_ce
            total_ce = _count(cur, "SELECT COUNT(*) FROM chart_entries;")

            if total_hot100_ce != src_hot100:
                raise MigrationParityError(
                    f"hot-100 parity mismatch: chart_entries has {total_hot100_ce} "
                    f"hot-100 rows but hot100_entries has {src_hot100}"
                )
            if total_b200_ce != src_b200:
                raise MigrationParityError(
                    f"billboard-200 parity mismatch: chart_entries has "
                    f"{total_b200_ce} billboard-200 rows but b200_entries has "
                    f"{src_b200}"
                )
            if total_ce != src_hot100 + src_b200:
                raise MigrationParityError(
                    f"total chart_entries parity mismatch: {total_ce} != "
                    f"{src_hot100} + {src_b200} (hot100_entries + b200_entries)"
                )

            # No known chart_type week may be left with a NULL chart_id.
            remaining_null = _count(
                cur,
                "SELECT COUNT(*) FROM chart_weeks WHERE chart_id IS NULL "
                "AND chart_type IN ('hot-100', 'billboard-200');",
            )
            if remaining_null:
                raise MigrationParityError(
                    f"{remaining_null} chart_weeks row(s) for known chart_types "
                    "still have a NULL chart_id after backfill"
                )

            # --- 6. CONTENT parity (WR-03) -----------------------------------
            # Count parity alone can't catch a wrong-but-equal-count backfill
            # (right number of rows, wrong song_id/album_id/rank/week). These
            # anti-join checks assert the backfilled chart_entries round-trip
            # the v1.0 source row-for-row, so a content corruption with a
            # correct count still rolls back.

            # Every chart_entries row sets exactly one entity FK (the real SQL
            # num_nonnulls CHECK; asserted here so a bad SELECT list is caught
            # even where the CHECK isn't exercised, e.g. the fake DB).
            bad_polymorphism = _count(
                cur,
                "SELECT COUNT(*) FROM chart_entries "
                "WHERE num_nonnulls(song_id, album_id, artist_id) <> 1;",
            )
            if bad_polymorphism:
                raise MigrationParityError(
                    f"{bad_polymorphism} chart_entries row(s) violate the "
                    "one-of-three entity-FK invariant"
                )

            # hot-100: every backfilled (chart_week_id, rank, song_id) must
            # exist in hot100_entries, and vice versa (round-trip both ways).
            hot100_orphans = _count(
                cur,
                "SELECT COUNT(*) FROM chart_entries ce "
                "JOIN charts c ON c.id = ce.chart_id AND c.slug = 'hot-100' "
                "LEFT JOIN hot100_entries h "
                "ON h.chart_week_id = ce.chart_week_id "
                "AND h.rank = ce.rank AND h.song_id = ce.song_id "
                "WHERE h.id IS NULL;",
            )
            hot100_missing = _count(
                cur,
                "SELECT COUNT(*) FROM hot100_entries h "
                "LEFT JOIN chart_entries ce "
                "ON ce.chart_week_id = h.chart_week_id "
                "AND ce.rank = h.rank AND ce.song_id = h.song_id "
                "AND ce.chart_id = (SELECT id FROM charts WHERE slug = 'hot-100') "
                "WHERE ce.id IS NULL;",
            )
            if hot100_orphans or hot100_missing:
                raise MigrationParityError(
                    f"hot-100 content mismatch: {hot100_orphans} chart_entries "
                    f"row(s) have no matching hot100_entries source and "
                    f"{hot100_missing} source row(s) were not backfilled "
                    "(wrong song_id/rank/week despite matching counts)"
                )

            # billboard-200: symmetric round-trip on (chart_week_id, rank,
            # album_id).
            b200_orphans = _count(
                cur,
                "SELECT COUNT(*) FROM chart_entries ce "
                "JOIN charts c ON c.id = ce.chart_id AND c.slug = 'billboard-200' "
                "LEFT JOIN b200_entries b "
                "ON b.chart_week_id = ce.chart_week_id "
                "AND b.rank = ce.rank AND b.album_id = ce.album_id "
                "WHERE b.id IS NULL;",
            )
            b200_missing = _count(
                cur,
                "SELECT COUNT(*) FROM b200_entries b "
                "LEFT JOIN chart_entries ce "
                "ON ce.chart_week_id = b.chart_week_id "
                "AND ce.rank = b.rank AND ce.album_id = b.album_id "
                "AND ce.chart_id = (SELECT id FROM charts WHERE slug = 'billboard-200') "
                "WHERE ce.id IS NULL;",
            )
            if b200_orphans or b200_missing:
                raise MigrationParityError(
                    f"billboard-200 content mismatch: {b200_orphans} "
                    f"chart_entries row(s) have no matching b200_entries source "
                    f"and {b200_missing} source row(s) were not backfilled "
                    "(wrong album_id/rank/week despite matching counts)"
                )

            report["after"] = {
                "chart_entries_hot100": total_hot100_ce,
                "chart_entries_b200": total_b200_ce,
                "chart_entries_total": total_ce,
            }

        conn.commit()
        logger.info(
            "Migration committed: seeded %d chart(s); chart_entries totals "
            "hot-100=%d, billboard-200=%d (parity holds).",
            report["seeded_charts"],
            total_hot100_ce,
            total_b200_ce,
        )
        return report
    except Exception:
        conn.rollback()
        raise


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint. The OPERATOR runs this against the real DB per the runbook."""
    parser = argparse.ArgumentParser(
        description=(
            "Apply the additive, idempotent multi-chart migration "
            "(operator-applied; see docs/MIGRATION-MULTICHART.md)."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the planned seed/backfill counts without writing anything.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Lazy DB import so the module imports cleanly in environments without
    # psycopg2 (e.g. the mock-based test environment). A SINGLE connection is
    # used end-to-end so detection and execution share one transaction.
    from billboard_stats.db.connection import get_conn, put_conn

    conn = get_conn()
    try:
        report = migrate(conn, dry_run=args.dry_run)
    finally:
        put_conn(conn)

    print(
        f"{'DRY RUN — ' if report['dry_run'] else ''}"
        f"seeded {report['seeded_charts']} chart(s); "
        f"backfilled +{report['backfill']['hot-100']} hot-100 / "
        f"+{report['backfill']['billboard-200']} billboard-200 chart_entries."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
