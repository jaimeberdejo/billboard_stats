"""Destructive, idempotent legacy-table retirement migration runner (Phase 15).

Retires the v1.0 bifurcated storage now that every live read (Wave A), write
(Wave B), and the TypeScript layer (Wave C) read/write the polymorphic
``chart_entries`` table keyed by ``chart_id``. It:

  * promotes ``chart_weeks.chart_id`` to NOT NULL;
  * adds a FULL ``UNIQUE(chart_id, chart_date)`` week-dedup key (the sole
    ON CONFLICT target the collapsed loader upsert relies on);
  * drops the dead ``chart_type`` column on ``chart_weeks`` (+ its CHECK + the old
    ``UNIQUE(chart_date, chart_type)``);
  * drops the ``hot100_entries`` / ``b200_entries`` tables, every index that fed
    them, and the now-redundant partial ``uq_chart_weeks_chart_id_date`` index.

The migration is operator-applied via the CLI (``main``) per the runbook;
``migrate`` takes an INJECTABLE connection so tests can pass an in-memory fake
DB. The destructive DROP is a DEFERRED OPERATOR STEP — this module NEVER connects
to a real database during automated execution.

Design / safety contract (mirrors billboard_stats/etl/migrate_gender.py):

* DB access goes through an INJECTABLE connection (``cursor()`` context manager,
  ``commit()``, ``rollback()``). The SQL runs unchanged against real PostgreSQL.
* DDL ORDER is non-negotiable: the new NOT NULL + full UNIQUE are added BEFORE
  the column/table drops, so ``chart_weeks`` is never left without a week-dedup
  key mid-migration. ``_DDL_STATEMENTS`` is byte-for-byte consistent (after
  whitespace normalization) with db/migrations/003_retire_legacy.sql AND the
  final post-drop shape in db/schema.sql; a test enforces that lockstep (W-3).
* Every statement is IDEMPOTENT (ALTER ... IF EXISTS, DROP ... IF EXISTS, a
  DO-block-guarded ADD CONSTRAINT) so a fresh install and an existing install
  converge and a re-apply is a clean no-op.
* Everything runs in a SINGLE transaction on ONE connection. After the DDL it
  asserts post-migration invariants:
    - ``hot100_entries`` / ``b200_entries`` are GONE (information_schema.tables);
    - the ``chart_type`` column on ``chart_weeks`` is GONE (information_schema.columns);
    - NO ``chart_weeks`` row has a NULL ``chart_id``;
    - the ``chart_entries`` row count is UNCHANGED vs before the migration (the
      drop removes redundant copies, never the live polymorphic data);
    - the ``UNIQUE(chart_id, chart_date)`` constraint EXISTS (pg_constraint).
  On any mismatch it calls ``rollback()`` and raises
  ``RetireLegacyMigrationError``; it commits only if every assertion holds.
* ``--dry-run`` reports the planned drops (which legacy objects still exist) and
  writes nothing, exiting 0.
* psycopg2 is imported LAZILY inside ``main()`` so the module imports cleanly in
  the psycopg2-free test environment.
* This module NEVER connects to a real database during automated execution; the
  real prod apply is the DEFERRED operator runbook step (Plan 15-04).
"""

from __future__ import annotations

import argparse
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# The two bifurcated v1.0 entry tables this migration retires.
_LEGACY_TABLES: List[str] = ["hot100_entries", "b200_entries"]

# The dead chart_weeks column this migration drops.
_LEGACY_COLUMN: str = "chart_type"

# The full week-dedup constraint this migration guarantees on chart_weeks.
_UNIQUE_CONSTRAINT: str = "chart_weeks_chart_id_date_key"


class RetireLegacyMigrationError(RuntimeError):
    """Raised when a post-migration assertion fails; triggers rollback."""


# ----------------------------------------------------------------------------
# DDL: the executable statements from db/migrations/003_retire_legacy.sql, in
# the SAME order (invariants BEFORE drops). Kept byte-consistent (after
# whitespace normalization) with db/schema.sql's final post-drop shape AND the
# .sql file — db/migrations/003_retire_legacy.sql is the source of truth and a
# test (W-3) asserts all three agree.
# ----------------------------------------------------------------------------
_DDL_STATEMENTS: List[str] = [
    "ALTER TABLE chart_weeks ALTER COLUMN chart_id SET NOT NULL;",
    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chart_weeks_chart_id_date_key') THEN ALTER TABLE chart_weeks ADD CONSTRAINT chart_weeks_chart_id_date_key UNIQUE (chart_id, chart_date); END IF; END $$;",
    "ALTER TABLE chart_weeks DROP COLUMN IF EXISTS chart_type;",
    "DROP INDEX IF EXISTS idx_chart_weeks_type_date;",
    "DROP INDEX IF EXISTS uq_chart_weeks_chart_id_date;",
    "DROP INDEX IF EXISTS idx_hot100_song_id;",
    "DROP INDEX IF EXISTS idx_hot100_chart_week;",
    "DROP INDEX IF EXISTS idx_b200_album_id;",
    "DROP INDEX IF EXISTS idx_b200_chart_week;",
    "DROP TABLE IF EXISTS hot100_entries;",
    "DROP TABLE IF EXISTS b200_entries;",
]


def _count(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    return cur.fetchone()[0]


def _existing_legacy_entry_tables(cur) -> List[str]:
    """Return which of the two legacy entry tables still exist.

    Uses the information_schema catalog so the check works against real
    PostgreSQL and the fake DB alike.
    """
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name = ANY(%s);",
        (_LEGACY_TABLES,),
    )
    return [row[0] for row in cur.fetchall()]


def _chart_type_present(cur) -> bool:
    """Return whether the chart_type column on chart_weeks still exists."""
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'chart_weeks' AND column_name = %s;",
        (_LEGACY_COLUMN,),
    )
    return cur.fetchone() is not None


def _unique_constraint_present(cur) -> bool:
    """Return whether the full UNIQUE(chart_id, chart_date) constraint exists."""
    cur.execute(
        "SELECT 1 FROM pg_constraint WHERE conname = %s;",
        (_UNIQUE_CONSTRAINT,),
    )
    return cur.fetchone() is not None


def migrate(conn, *, dry_run: bool = False) -> Dict[str, object]:
    """Apply the destructive legacy-retirement migration on the injected conn.

    Args:
        conn: An injectable DB connection exposing ``cursor()`` (context
            manager), ``commit()``, and ``rollback()``.
        dry_run: When True, report which legacy objects still exist (the planned
            drops) and return WITHOUT writing or committing.

    Returns:
        A report dict: ``dry_run`` flag, ``dropped_tables`` (legacy tables this
        run dropped — the planned drops under dry_run), and ``before`` /
        ``after`` chart_entries row counts.

    Raises:
        RetireLegacyMigrationError: if any post-migration assertion fails (the
            connection is rolled back first).
    """
    report: Dict[str, object] = {
        "dry_run": dry_run,
        "dropped_tables": [],
        "before": None,
        "after": None,
    }

    try:
        with conn.cursor() as cur:
            # --- Pre-existing state (single transaction) ---------------------
            before_entries = _count(cur, "SELECT COUNT(*) FROM chart_entries;")
            report["before"] = {"chart_entries": before_entries}
            existing_before = _existing_legacy_entry_tables(cur)

            # --- DRY RUN: report the planned drops, change nothing -----------
            if dry_run:
                report["dropped_tables"] = list(existing_before)
                logger.info(
                    "Dry run: %d legacy table(s) to drop (%s); writing nothing.",
                    len(existing_before),
                    ", ".join(existing_before) or "none",
                )
                return report

            # --- 1. DDL (invariants BEFORE drops; idempotent) ----------------
            for stmt in _DDL_STATEMENTS:
                cur.execute(stmt)
            report["dropped_tables"] = list(existing_before)

            # --- 2. Post-migration assertions --------------------------------
            # (a) the two legacy entry tables are GONE.
            still_present = _existing_legacy_entry_tables(cur)
            if still_present:
                raise RetireLegacyMigrationError(
                    f"legacy table(s) still present after migration: "
                    f"{', '.join(still_present)}"
                )

            # (b) the chart_type column on chart_weeks is GONE.
            if _chart_type_present(cur):
                raise RetireLegacyMigrationError(
                    "chart_type column on chart_weeks still present after migration"
                )

            # (c) no chart_weeks row has a NULL chart_id (NOT NULL promoted).
            null_chart_id = _count(
                cur, "SELECT COUNT(*) FROM chart_weeks WHERE chart_id IS NULL;"
            )
            if null_chart_id:
                raise RetireLegacyMigrationError(
                    f"{null_chart_id} chart_weeks row(s) have a NULL chart_id "
                    "after migration (chart_id must be NOT NULL)"
                )

            # (d) chart_entries row count UNCHANGED: the drop removes redundant
            #     copies, never the live polymorphic data.
            after_entries = _count(cur, "SELECT COUNT(*) FROM chart_entries;")
            if after_entries != before_entries:
                raise RetireLegacyMigrationError(
                    f"chart_entries row-count changed during migration: "
                    f"{before_entries} -> {after_entries} (the drop must not "
                    "touch the live polymorphic data)"
                )

            # (e) the full UNIQUE(chart_id, chart_date) constraint EXISTS.
            if not _unique_constraint_present(cur):
                raise RetireLegacyMigrationError(
                    f"UNIQUE constraint {_UNIQUE_CONSTRAINT!r} missing after "
                    "migration (the week-dedup key must be present)"
                )

            report["after"] = {"chart_entries": after_entries}

        conn.commit()
        logger.info(
            "Migration committed: dropped %d legacy table(s) (%s); "
            "%d chart_entries row(s) unchanged, chart_id NOT NULL, "
            "UNIQUE(chart_id, chart_date) present.",
            len(report["dropped_tables"]),
            ", ".join(report["dropped_tables"]) or "none (already applied)",
            after_entries,
        )
        return report
    except Exception:
        conn.rollback()
        raise


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint. The OPERATOR runs this against the real DB per the runbook.

    DESTRUCTIVE: take the documented pre-drop backup FIRST (see the header of
    db/migrations/003_retire_legacy.sql). Run ``--dry-run`` first on a throwaway
    Neon branch to confirm the planned drops.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Apply the destructive, idempotent legacy-table retirement migration "
            "(operator-applied; take the documented pre-drop backup FIRST)."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which legacy objects would be dropped without writing anything.",
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

    dropped = report["dropped_tables"]
    print(
        f"{'DRY RUN — ' if report['dry_run'] else ''}"
        f"{'would drop' if report['dry_run'] else 'dropped'} "
        f"{len(dropped)} legacy table(s)"
        f"{(': ' + ', '.join(dropped)) if dropped else ' (already retired)'}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
