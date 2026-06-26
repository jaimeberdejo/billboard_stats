"""Fixture/mock-DB tests for the artist-gender migration (Plan 12-01).

These tests run entirely offline — NO real database connection and NO network
calls. The real-DB apply (dry-run -> snapshot -> apply -> verify -> rebuild) is
the operator runbook (Plan 12-02), not here.

This module starts with the W-3 byte-consistency (lockstep) gate; the
single-transaction runner-behavior tests (fake DB) are added alongside the
runner itself.

W-3 byte-consistency — the three gender ALTER/ADD COLUMN statements AND the
DO-block CHECK guard must be TEXTUALLY IDENTICAL, after whitespace
normalization, across all THREE sources of the DDL:
  * billboard_stats/db/migrations/002_gender.sql
  * the Phase-12 additive block in billboard_stats/db/schema.sql
  * billboard_stats.etl.migrate_gender._DDL_STATEMENTS
This enforces the 001<->schema.sql lockstep convention by TEST (it replaces a
bare grep, which counts presence but not byte-for-byte agreement).
"""

import copy
import os
import re
import unittest

from billboard_stats.etl import migrate_gender
from billboard_stats.etl.migrate_gender import (
    GenderMigrationError,
    migrate,
)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MIGRATION_SQL = os.path.join(
    _REPO_ROOT, "billboard_stats", "db", "migrations", "002_gender.sql"
)
_SCHEMA_SQL = os.path.join(_REPO_ROOT, "billboard_stats", "db", "schema.sql")


# ============================================================================
# W-3: byte-consistency (lockstep) across the three DDL sources
# ============================================================================
def _normalize(stmt: str) -> str:
    """Collapse all runs of whitespace (incl. newlines) to a single space and
    strip leading/trailing whitespace — the whitespace-normalizer applied to
    every source so the comparison is byte-for-byte on content, not layout."""
    return re.sub(r"\s+", " ", stmt).strip()


# A statement is part of the gender DDL iff its normalized text mentions one of
# the gender columns or the gender CHECK guard. This lets the same extractor run
# over the migration file (gender-only) AND schema.sql (full schema, many other
# statements) AND the _DDL_STATEMENTS list.
_GENDER_MARKERS = ("gender", "artists_gender_check")


def _is_gender_ddl(norm_stmt: str) -> bool:
    low = norm_stmt.lower()
    return any(marker in low for marker in _GENDER_MARKERS)


def _split_sql_statements(sql_text: str):
    """Split a .sql file into statements, treating a DO $$ ... $$ block as one
    statement. Strips full-line `--` comments first so comment prose mentioning
    'gender' is not mistaken for a DDL statement."""
    # Drop full-line comments (a line whose first non-space chars are `--`).
    lines = [
        ln for ln in sql_text.splitlines() if not ln.lstrip().startswith("--")
    ]
    body = "\n".join(lines)

    statements = []
    i = 0
    n = len(body)
    buf = []
    while i < n:
        # Detect a dollar-quoted block opening: $$ ... $$
        if body[i : i + 2] == "$$":
            # Consume up to and including the closing $$.
            buf.append("$$")
            i += 2
            close = body.find("$$", i)
            if close == -1:
                buf.append(body[i:])
                i = n
            else:
                buf.append(body[i:close])
                buf.append("$$")
                i = close + 2
            continue
        ch = body[i]
        buf.append(ch)
        if ch == ";":
            statements.append("".join(buf))
            buf = []
        i += 1
    if "".join(buf).strip():
        statements.append("".join(buf))
    return statements


def _gender_ddl_from_sql_file(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    out = set()
    for stmt in _split_sql_statements(text):
        norm = _normalize(stmt)
        if norm and _is_gender_ddl(norm):
            out.add(norm)
    return out


def _gender_ddl_from_list(statements):
    return {
        _normalize(s) for s in statements if _is_gender_ddl(_normalize(s))
    }


class GenderDdlByteConsistencyTests(unittest.TestCase):
    """W-3: the gender DDL must be identical across the three sources."""

    def test_three_sources_have_byte_consistent_gender_ddl(self):
        from_migration = _gender_ddl_from_sql_file(_MIGRATION_SQL)
        from_schema = _gender_ddl_from_sql_file(_SCHEMA_SQL)
        from_runner = _gender_ddl_from_list(migrate_gender._DDL_STATEMENTS)

        # Each source must contribute exactly the 4 gender DDL fragments
        # (3 ADD COLUMN + 1 DO-block CHECK guard).
        self.assertEqual(
            len(from_migration), 4,
            f"002_gender.sql gender DDL: expected 4 statements, got "
            f"{len(from_migration)}: {sorted(from_migration)}",
        )
        self.assertEqual(
            len(from_schema), 4,
            f"schema.sql Phase-12 block: expected 4 gender statements, got "
            f"{len(from_schema)}: {sorted(from_schema)}",
        )
        self.assertEqual(
            len(from_runner), 4,
            f"_DDL_STATEMENTS: expected 4 gender statements, got "
            f"{len(from_runner)}: {sorted(from_runner)}",
        )

        # The whitespace-normalized SETS must be equal across all three sources.
        self.assertEqual(
            from_migration, from_schema,
            "002_gender.sql and schema.sql gender DDL differ after "
            "whitespace normalization (lockstep broken)",
        )
        self.assertEqual(
            from_migration, from_runner,
            "002_gender.sql and migrate_gender._DDL_STATEMENTS differ after "
            "whitespace normalization (lockstep broken)",
        )

    def test_each_source_has_the_three_add_column_and_the_check_guard(self):
        # Spot-assert the load-bearing fragments are present in every source.
        for label, ddl in (
            ("002_gender.sql", _gender_ddl_from_sql_file(_MIGRATION_SQL)),
            ("schema.sql", _gender_ddl_from_sql_file(_SCHEMA_SQL)),
            ("_DDL_STATEMENTS", _gender_ddl_from_list(migrate_gender._DDL_STATEMENTS)),
        ):
            joined = " || ".join(sorted(ddl)).lower()
            self.assertIn(
                "add column if not exists gender varchar(8) not null default 'unknown'",
                joined, f"{label} missing the gender ADD COLUMN",
            )
            self.assertIn(
                "add column if not exists gender_source varchar(16)",
                joined, f"{label} missing the gender_source ADD COLUMN",
            )
            self.assertIn(
                "add column if not exists gender_source_id varchar(64)",
                joined, f"{label} missing the gender_source_id ADD COLUMN",
            )
            self.assertIn(
                "artists_gender_check", joined,
                f"{label} missing the CHECK guard",
            )

    def test_migration_drops_renames_or_narrows_nothing(self):
        # The migration file must not DROP/RENAME/ALTER ... TYPE any object.
        with open(_MIGRATION_SQL, "r", encoding="utf-8") as fh:
            body = "\n".join(
                ln for ln in fh.read().splitlines()
                if not ln.lstrip().startswith("--")
            ).lower()
        self.assertNotIn("drop ", body)
        self.assertNotIn("rename ", body)
        self.assertNotIn("alter column", body)
        self.assertNotIn(" type ", body)


# ============================================================================
# In-memory fake DB layer (mirrors test_migrate_multichart.py)
# ============================================================================
class FakeCursor:
    """A psycopg2-cursor-like stand-in interpreting the SQL migrate() emits.

    Models the artists table (id, name, plus the gender columns once added) and
    executes the exact statement shapes migrate_gender.py uses. DDL ALTERs are
    interpreted to actually add the modeled columns (defaulting gender to
    'unknown') so the additive default behavior is ASSERTED, not assumed. Any
    unhandled statement raises AssertionError so drift is caught.
    """

    def __init__(self, db):
        self._db = db
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        norm = re.sub(r"\s+", " ", sql).strip().lower()
        params = params or ()

        # --- DDL: ADD COLUMN ALTERs actually add the modeled column ----------
        if norm.startswith("alter table artists add column if not exists gender_source_id"):
            self._db.add_gender_column("gender_source_id")
            return
        if norm.startswith("alter table artists add column if not exists gender_source"):
            self._db.add_gender_column("gender_source")
            return
        if norm.startswith("alter table artists add column if not exists gender"):
            self._db.add_gender_column("gender")  # backfills 'unknown'
            return

        # --- DO-block CHECK guard: no-op in the fake DB ----------------------
        if norm.startswith("do $$") or norm.startswith("do$$"):
            self._result = None
            return

        # --- existence check against the catalog -----------------------------
        if norm.startswith(
            "select column_name from information_schema.columns"
        ):
            (wanted,) = params
            present = [c for c in wanted if c in self._db.gender_columns]
            self._result = [(c,) for c in present]
            return

        # --- artist row count ------------------------------------------------
        if norm.startswith("select count(*) from artists where gender is null"):
            self._result = [(self._db.count_null_gender(),)]
            return

        if norm.startswith("select count(*) from artists"):
            self._result = [(len(self._db.artists),)]
            return

        raise AssertionError(f"FakeCursor: unhandled SQL: {norm!r}")

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None


class FakeConn:
    """A connection-like stand-in tracking commit/rollback and snapshotting."""

    def __init__(self, db):
        self._db = db
        self.committed = False
        self.rolled_back = False
        self._snapshot = db.snapshot()

    def cursor(self):
        return FakeCursor(self._db)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True
        self._db.restore(self._snapshot)


class FakeDB:
    """In-memory model of the artists table for the gender migration."""

    def __init__(self, artists, gender_columns=None):
        # artists: list of {"id": int, "name": str, ...gender fields once added}
        self.artists = [dict(a) for a in artists]
        # which gender columns currently exist (start empty = pre-migration)
        self.gender_columns = list(gender_columns or [])

    def add_gender_column(self, col):
        """ADD COLUMN IF NOT EXISTS: idempotent; gender backfills 'unknown'."""
        if col in self.gender_columns:
            return  # IF NOT EXISTS -> no-op
        self.gender_columns.append(col)
        default = "unknown" if col == "gender" else None
        for a in self.artists:
            a[col] = default

    def count_null_gender(self):
        if "gender" not in self.gender_columns:
            return 0
        return sum(1 for a in self.artists if a.get("gender") is None)

    def snapshot(self):
        return copy.deepcopy(
            {"artists": self.artists, "gender_columns": self.gender_columns}
        )

    def restore(self, snap):
        snap = copy.deepcopy(snap)
        self.artists = snap["artists"]
        self.gender_columns = snap["gender_columns"]


def _fixture():
    """A small pre-migration v1.0 artists table: 3 rows, no gender columns."""
    return FakeDB(
        artists=[
            {"id": 1, "name": "Beyoncé", "image_url": None},
            {"id": 2, "name": "Queen", "image_url": None},
            {"id": 3, "name": "Drake", "image_url": None},
        ],
        gender_columns=[],
    )


# ----------------------------------------------------------------------------
# Additive apply: columns added with 'unknown' default + row-count parity
# ----------------------------------------------------------------------------
class GenderMigrateApplyTests(unittest.TestCase):
    def test_apply_adds_three_columns_with_unknown_default_and_commits(self):
        db = _fixture()
        before_rows = len(db.artists)
        conn = FakeConn(db)

        report = migrate(conn, dry_run=False)

        # All three columns now exist.
        self.assertIn("gender", db.gender_columns)
        self.assertIn("gender_source", db.gender_columns)
        self.assertIn("gender_source_id", db.gender_columns)
        # Every pre-existing row survives with gender backfilled to 'unknown'.
        self.assertEqual(len(db.artists), before_rows)
        for a in db.artists:
            self.assertEqual(a["gender"], "unknown")
            self.assertIsNone(a["gender_source"])
            self.assertIsNone(a["gender_source_id"])
        # Report reflects the three added columns + row-count parity.
        self.assertEqual(
            sorted(report["added_columns"]),
            ["gender", "gender_source", "gender_source_id"],
        )
        self.assertEqual(report["before"]["artists"], before_rows)
        self.assertEqual(report["after"]["artists"], before_rows)
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)
        self.assertFalse(report["dry_run"])


# ----------------------------------------------------------------------------
# Idempotent re-run: a second apply is a byte-equal no-op
# ----------------------------------------------------------------------------
class GenderMigrateIdempotencyTests(unittest.TestCase):
    def test_second_run_is_byte_equal_noop_and_still_commits(self):
        db = _fixture()
        migrate(FakeConn(db), dry_run=False)
        snapshot_after_first = db.snapshot()

        second = FakeConn(db)
        report = migrate(second, dry_run=False)

        # Zero columns added on the second run; state byte-for-byte identical.
        self.assertEqual(report["added_columns"], [])
        self.assertEqual(db.snapshot(), snapshot_after_first)
        # Still commits (additive assertions hold even with zero adds this run).
        self.assertTrue(second.committed)
        self.assertFalse(second.rolled_back)


# ----------------------------------------------------------------------------
# Dry run: reports planned adds, writes nothing
# ----------------------------------------------------------------------------
class GenderMigrateDryRunTests(unittest.TestCase):
    def test_dry_run_reports_planned_adds_but_writes_nothing(self):
        db = _fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        report = migrate(conn, dry_run=True)

        self.assertTrue(report["dry_run"])
        self.assertEqual(
            sorted(report["added_columns"]),
            ["gender", "gender_source", "gender_source_id"],
        )
        # Nothing written, nothing committed.
        self.assertEqual(db.snapshot(), before)
        self.assertEqual(db.gender_columns, [])
        self.assertFalse(conn.committed)

    def test_dry_run_on_already_migrated_db_reports_zero_adds(self):
        db = _fixture()
        migrate(FakeConn(db), dry_run=False)  # apply first
        before = db.snapshot()
        conn = FakeConn(db)

        report = migrate(conn, dry_run=True)

        self.assertTrue(report["dry_run"])
        self.assertEqual(report["added_columns"], [])
        self.assertEqual(db.snapshot(), before)
        self.assertFalse(conn.committed)


# ----------------------------------------------------------------------------
# Assertion failure -> rollback
# ----------------------------------------------------------------------------
class GenderMigrateRollbackTests(unittest.TestCase):
    def test_row_count_change_rolls_back_and_raises(self):
        # Force the additive-only assertion to trip by mutating the artist row
        # count between the before/after reads (a column-add that also added a
        # row would be non-additive). The migration must roll back + raise.
        db = _fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        original = FakeDB.add_gender_column

        def row_adding_add(self_db, col):
            original(self_db, col)
            if col == "gender":
                # Simulate a non-additive DDL that inserted a stray row.
                self_db.artists.append(
                    {"id": 999, "name": "STRAY", "image_url": None,
                     "gender": "unknown", "gender_source": None,
                     "gender_source_id": None}
                )

        FakeDB.add_gender_column = row_adding_add
        try:
            with self.assertRaises(GenderMigrationError) as ctx:
                migrate(conn, dry_run=False)
        finally:
            FakeDB.add_gender_column = original

        self.assertIn("row-count changed", str(ctx.exception))
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)
        # State restored to its pre-run snapshot.
        self.assertEqual(db.snapshot(), before)

    def test_null_gender_after_migration_rolls_back_and_raises(self):
        # If a row somehow ends up with a NULL gender (the default failed to
        # backfill), the assertion must trip -> rollback + raise.
        db = _fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        original = FakeDB.add_gender_column

        def null_gender_add(self_db, col):
            original(self_db, col)
            if col == "gender" and self_db.artists:
                self_db.artists[0]["gender"] = None  # break the default backfill

        FakeDB.add_gender_column = null_gender_add
        try:
            with self.assertRaises(GenderMigrationError) as ctx:
                migrate(conn, dry_run=False)
        finally:
            FakeDB.add_gender_column = original

        self.assertIn("NULL gender", str(ctx.exception))
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)
        self.assertEqual(db.snapshot(), before)


# ----------------------------------------------------------------------------
# Module hygiene: no top-level psycopg2 import + exports
# ----------------------------------------------------------------------------
class GenderMigratePostgresFreeTests(unittest.TestCase):
    def test_module_has_no_top_level_psycopg_import(self):
        import inspect

        source = inspect.getsource(migrate_gender)
        top_level = [
            l for l in source.splitlines()
            if l.startswith("import ") or l.startswith("from ")
        ]
        self.assertFalse(
            any("psycopg" in l for l in top_level),
            "psycopg2 must not be a top-level import",
        )

    def test_exports_migrate_main_and_error(self):
        self.assertTrue(hasattr(migrate_gender, "migrate"))
        self.assertTrue(hasattr(migrate_gender, "main"))
        self.assertTrue(hasattr(migrate_gender, "GenderMigrationError"))
        self.assertTrue(issubclass(GenderMigrationError, RuntimeError))


if __name__ == "__main__":
    unittest.main()
