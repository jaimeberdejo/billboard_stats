"""Idempotent, additive artist-gender migration runner (GENDER-01).

Adds three first-class gender columns to the v1.0 ``artists`` table WITHOUT
mutating anything the existing frontend reads:

  * ``gender``           VARCHAR(8) NOT NULL DEFAULT 'unknown' (5-value CHECK)
  * ``gender_source``    VARCHAR(16)  -- musicbrainz|wikidata|manual|NULL
  * ``gender_source_id`` VARCHAR(64)  -- the MBID/QID used for the match

The migration is operator-applied via the CLI (``main``) per the runbook;
``migrate`` takes an INJECTABLE connection so tests can pass an in-memory fake
DB. ``unknown`` is a FIRST-CLASS default value (every pre-existing row backfills
to it), not a missing sentinel. Population of real values is the Phase 12
enricher's job (Plan 12-02), not this runner.

Design / safety contract (mirrors billboard_stats/etl/migrate_multichart.py):

* DB access goes through an INJECTABLE connection (``cursor()`` context manager,
  ``commit()``, ``rollback()``). The SQL runs unchanged against real PostgreSQL.
* The migration is STRICTLY ADDITIVE and IDEMPOTENT:
    1. applies the additive DDL from db/migrations/002_gender.sql, guarded by
       ADD COLUMN IF NOT EXISTS (so fresh + existing installs converge and a
       re-apply is a clean no-op);
    2. adds the 5-value CHECK idempotently via a DO block that guards on
       pg_constraint (Postgres has no ADD CONSTRAINT IF NOT EXISTS).
  ``_DDL_STATEMENTS`` is byte-for-byte consistent (after whitespace
  normalization) with 002_gender.sql AND db/schema.sql's Phase 12 block; a test
  enforces that lockstep (W-3).
* Everything runs in a SINGLE transaction on ONE connection. After the DDL it
  asserts ADDITIVE-ONLY invariants:
    - the artist row count is UNCHANGED vs before the migration;
    - all three gender columns now exist on artists;
    - no artist row has a NULL gender (the default backfilled every row).
  On any mismatch it calls ``rollback()`` and raises ``GenderMigrationError``;
  it commits only if every assertion holds.
* ``--dry-run`` reports which of the three columns are missing (the planned
  adds) and writes nothing, exiting 0.
* psycopg2 is imported LAZILY inside ``main()`` so the module imports cleanly in
  the psycopg2-free test environment.
* This module NEVER connects to a real database during automated execution; the
  real prod apply is the DEFERRED operator runbook step (Plan 12-02).
"""

from __future__ import annotations

import argparse
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# The three additive gender columns this migration guarantees on ``artists``.
_GENDER_COLUMNS: List[str] = ["gender", "gender_source", "gender_source_id"]


class GenderMigrationError(RuntimeError):
    """Raised when a post-migration assertion fails; triggers rollback."""


# ----------------------------------------------------------------------------
# DDL: the additive statements from db/migrations/002_gender.sql, guarded by
# ADD COLUMN IF NOT EXISTS + a DO-block CHECK guard. Kept byte-consistent (after
# whitespace normalization) with db/schema.sql's Phase 12 block AND the .sql
# file — db/migrations/002_gender.sql is the source of truth and a test (W-3)
# asserts all three agree.
# ----------------------------------------------------------------------------
_DDL_STATEMENTS: List[str] = [
    "ALTER TABLE artists ADD COLUMN IF NOT EXISTS gender VARCHAR(8) NOT NULL DEFAULT 'unknown';",
    "ALTER TABLE artists ADD COLUMN IF NOT EXISTS gender_source VARCHAR(16);",
    "ALTER TABLE artists ADD COLUMN IF NOT EXISTS gender_source_id VARCHAR(64);",
    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'artists_gender_check') THEN ALTER TABLE artists ADD CONSTRAINT artists_gender_check CHECK (gender IN ('female', 'male', 'group', 'mixed', 'unknown')); END IF; END $$;",
]


def _count(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    return cur.fetchone()[0]


def _existing_gender_columns(cur) -> List[str]:
    """Return which of the three gender columns already exist on artists.

    Uses the information_schema catalog so the check works against real
    PostgreSQL and the fake DB alike.
    """
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'artists' AND column_name = ANY(%s);",
        (_GENDER_COLUMNS,),
    )
    return [row[0] for row in cur.fetchall()]


def migrate(conn, *, dry_run: bool = False) -> Dict[str, object]:
    """Apply the additive gender migration on the injected connection.

    Args:
        conn: An injectable DB connection exposing ``cursor()`` (context
            manager), ``commit()``, and ``rollback()``.
        dry_run: When True, report which of the three columns are missing
            (the planned adds) and return WITHOUT writing or committing.

    Returns:
        A report dict: ``dry_run`` flag, ``added_columns`` (columns this run
        added — the planned adds under dry_run), and ``before`` / ``after``
        artist row counts.

    Raises:
        GenderMigrationError: if any post-migration assertion fails (the
            connection is rolled back first).
    """
    report: Dict[str, object] = {
        "dry_run": dry_run,
        "added_columns": [],
        "before": None,
        "after": None,
    }

    try:
        with conn.cursor() as cur:
            # --- Pre-existing state (single transaction) ---------------------
            before_artists = _count(cur, "SELECT COUNT(*) FROM artists;")
            report["before"] = {"artists": before_artists}
            existing_before = _existing_gender_columns(cur)
            missing = [c for c in _GENDER_COLUMNS if c not in existing_before]

            # --- DRY RUN: report the planned column adds, change nothing ------
            if dry_run:
                report["added_columns"] = list(missing)
                logger.info(
                    "Dry run: %d column(s) to add (%s); writing nothing.",
                    len(missing),
                    ", ".join(missing) or "none",
                )
                return report

            # --- 1. DDL (additive; IF NOT EXISTS) ----------------------------
            for stmt in _DDL_STATEMENTS:
                cur.execute(stmt)
            report["added_columns"] = list(missing)

            # --- 2. ADDITIVE-ONLY post-migration assertions ------------------
            # Row count unchanged: the migration adds columns, never rows.
            after_artists = _count(cur, "SELECT COUNT(*) FROM artists;")
            if after_artists != before_artists:
                raise GenderMigrationError(
                    f"artist row-count changed during migration: "
                    f"{before_artists} -> {after_artists} (must be additive)"
                )

            # All three gender columns now exist.
            existing_after = _existing_gender_columns(cur)
            still_missing = [c for c in _GENDER_COLUMNS if c not in existing_after]
            if still_missing:
                raise GenderMigrationError(
                    f"gender column(s) missing after migration: "
                    f"{', '.join(still_missing)}"
                )

            # The NOT NULL DEFAULT 'unknown' backfilled every pre-existing row;
            # no artist may have a NULL gender.
            null_gender = _count(
                cur, "SELECT COUNT(*) FROM artists WHERE gender IS NULL;"
            )
            if null_gender:
                raise GenderMigrationError(
                    f"{null_gender} artist row(s) have a NULL gender after "
                    "migration (the 'unknown' default should backfill all rows)"
                )

            report["after"] = {"artists": after_artists}

        conn.commit()
        logger.info(
            "Migration committed: added %d gender column(s) (%s); %d artist "
            "row(s) unchanged, all gender values non-NULL.",
            len(report["added_columns"]),
            ", ".join(report["added_columns"]) or "none (already applied)",
            after_artists,
        )
        return report
    except Exception:
        conn.rollback()
        raise


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint. The OPERATOR runs this against the real DB per the runbook."""
    parser = argparse.ArgumentParser(
        description=(
            "Apply the additive, idempotent artist-gender migration "
            "(operator-applied; see docs/GENDER-ENRICHMENT.md)."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which gender columns would be added without writing anything.",
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

    added = report["added_columns"]
    print(
        f"{'DRY RUN — ' if report['dry_run'] else ''}"
        f"{'would add' if report['dry_run'] else 'added'} "
        f"{len(added)} gender column(s)"
        f"{(': ' + ', '.join(added)) if added else ' (already applied)'}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
