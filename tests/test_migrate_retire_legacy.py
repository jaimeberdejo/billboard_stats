"""Fixture/mock-DB tests for the legacy-table retirement migration (Plan 15-04).

These tests run entirely offline — NO real database connection and NO network
calls. The real-DB apply (backup -> dry-run -> apply -> verify) is the operator
runbook, NOT here. The destructive DROP is a DEFERRED operator step.

This module starts with the W-3 byte-consistency (lockstep) gate, then the
single-transaction runner-behavior tests over an injectable fake DB (apply +
commit, dry-run-writes-nothing, invariant-mismatch rollback + raise, and the
no-top-level-psycopg2 hygiene check).

W-3 byte-consistency — the migration's INVARIANT-adding DDL (the ALTER ... SET
NOT NULL and the DO-block UNIQUE guard, added BEFORE the drops) must be
TEXTUALLY IDENTICAL, after whitespace normalization, across all THREE sources:
  * billboard_stats/db/migrations/003_retire_legacy.sql
  * the Phase-15 final-shape block in billboard_stats/db/schema.sql
  * billboard_stats.etl.migrate_retire_legacy._DDL_STATEMENTS
A fresh install (schema.sql) reaches the same chart_weeks shape a migrated
install reaches, so schema.sql carries those invariant statements but NOT the
DROP statements (the legacy objects are never created in a fresh install). A
second assertion pins that the migration .sql and ``_DDL_STATEMENTS`` agree on
the FULL statement set, drops included.
"""

import copy
import os
import re
import unittest

from billboard_stats.etl import migrate_retire_legacy
from billboard_stats.etl.migrate_retire_legacy import (
    RetireLegacyMigrationError,
    migrate,
)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MIGRATION_SQL = os.path.join(
    _REPO_ROOT, "billboard_stats", "db", "migrations", "003_retire_legacy.sql"
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


# An INVARIANT statement promotes chart_weeks to its final shape: the chart_id
# SET NOT NULL or the full-UNIQUE DO-block guard. These are the statements that
# MUST appear identically in all three sources (the fresh schema reaches the same
# shape). A retire statement (the broader set) is any of those OR a drop.
_INVARIANT_MARKERS = ("set not null", "chart_weeks_chart_id_date_key")
_DROP_MARKERS = ("drop table", "drop index", "drop column")


def _is_invariant_ddl(norm_stmt: str) -> bool:
    low = norm_stmt.lower()
    return any(marker in low for marker in _INVARIANT_MARKERS)


def _is_retire_ddl(norm_stmt: str) -> bool:
    low = norm_stmt.lower()
    return _is_invariant_ddl(norm_stmt) or any(
        marker in low for marker in _DROP_MARKERS
    )


def _split_sql_statements(sql_text: str):
    """Split a .sql file into statements, treating a DO $$ ... $$ block as one
    statement. Strips full-line `--` comments first so comment prose is not
    mistaken for a DDL statement."""
    lines = [
        ln for ln in sql_text.splitlines() if not ln.lstrip().startswith("--")
    ]
    body = "\n".join(lines)

    statements = []
    i = 0
    n = len(body)
    buf = []
    while i < n:
        if body[i : i + 2] == "$$":
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


def _ddl_from_sql_file(path: str, predicate):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    out = set()
    for stmt in _split_sql_statements(text):
        norm = _normalize(stmt)
        if norm and predicate(norm):
            out.add(norm)
    return out


def _ddl_from_list(statements, predicate):
    return {_normalize(s) for s in statements if predicate(_normalize(s))}


class RetireDdlByteConsistencyTests(unittest.TestCase):
    """W-3: the retire DDL must be identical across the relevant sources."""

    def test_three_sources_have_byte_consistent_retire_ddl(self):
        # The INVARIANT-adding statements (NOT NULL + full UNIQUE) appear in all
        # three sources and must be byte-identical (the fresh schema reaches the
        # same chart_weeks shape a migrated install reaches).
        inv_migration = _ddl_from_sql_file(_MIGRATION_SQL, _is_invariant_ddl)
        inv_schema = _ddl_from_sql_file(_SCHEMA_SQL, _is_invariant_ddl)
        inv_runner = _ddl_from_list(
            migrate_retire_legacy._DDL_STATEMENTS, _is_invariant_ddl
        )

        # Exactly the 2 invariant statements per source.
        self.assertEqual(
            len(inv_migration), 2,
            f"003_retire_legacy.sql invariant DDL: expected 2, got "
            f"{len(inv_migration)}: {sorted(inv_migration)}",
        )
        self.assertEqual(
            len(inv_schema), 2,
            f"schema.sql Phase-15 block: expected 2 invariant statements, got "
            f"{len(inv_schema)}: {sorted(inv_schema)}",
        )
        self.assertEqual(
            len(inv_runner), 2,
            f"_DDL_STATEMENTS invariant DDL: expected 2, got "
            f"{len(inv_runner)}: {sorted(inv_runner)}",
        )

        # The whitespace-normalized SETS must be equal across all three sources.
        self.assertEqual(
            inv_migration, inv_schema,
            "003_retire_legacy.sql and schema.sql invariant DDL differ after "
            "whitespace normalization (lockstep broken)",
        )
        self.assertEqual(
            inv_migration, inv_runner,
            "003_retire_legacy.sql and migrate_retire_legacy._DDL_STATEMENTS "
            "invariant DDL differ after whitespace normalization (lockstep broken)",
        )

    def test_migration_and_runner_agree_on_full_retire_ddl(self):
        # The migration file and the runner must agree on the FULL retire DDL
        # set — invariants AND drops — so the runner applies exactly what the
        # operator-facing .sql documents.
        full_migration = _ddl_from_sql_file(_MIGRATION_SQL, _is_retire_ddl)
        full_runner = _ddl_from_list(
            migrate_retire_legacy._DDL_STATEMENTS, _is_retire_ddl
        )
        # 2 invariants + 1 drop column + 6 drop index + 2 drop table = 11.
        self.assertEqual(
            len(full_migration), 11,
            f"003_retire_legacy.sql retire DDL: expected 11, got "
            f"{len(full_migration)}: {sorted(full_migration)}",
        )
        self.assertEqual(full_migration, full_runner)

    def test_invariants_precede_drops_in_the_runner(self):
        # DDL ORDER is non-negotiable: the NOT NULL + UNIQUE must be applied
        # BEFORE any drop so chart_weeks is never left without a week-dedup key.
        stmts = migrate_retire_legacy._DDL_STATEMENTS
        first_drop = next(
            i for i, s in enumerate(stmts)
            if any(m in _normalize(s).lower() for m in _DROP_MARKERS)
        )
        last_invariant = max(
            i for i, s in enumerate(stmts) if _is_invariant_ddl(_normalize(s))
        )
        self.assertLess(
            last_invariant, first_drop,
            "every invariant statement must precede the first drop",
        )

    def test_migration_documents_a_pre_drop_backup(self):
        # Reversibility (success criterion 3): the migration header must document
        # an operator pre-drop backup step.
        with open(_MIGRATION_SQL, "r", encoding="utf-8") as fh:
            body = fh.read().lower()
        self.assertIn("pg_dump", body)
        self.assertIn("backup", body)


# ============================================================================
# In-memory fake DB layer (mirrors test_migrate_gender.py)
# ============================================================================
class FakeCursor:
    """A psycopg2-cursor-like stand-in interpreting the SQL migrate() emits.

    Models chart_weeks / chart_entries plus the catalog views the runner reads
    (information_schema.tables / .columns, pg_constraint). DDL DROP/ALTER are
    interpreted to actually mutate the modeled catalog so the destructive
    behavior is ASSERTED, not assumed. Any unhandled statement raises
    AssertionError so drift is caught.
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
        params = tuple(params) if params else ()

        # --- DDL: invariants -------------------------------------------------
        if norm.startswith("alter table chart_weeks alter column chart_id set not null"):
            self._db.set_chart_id_not_null()
            return
        if norm.startswith("do $$") or norm.startswith("do$$"):
            # The DO-block adds the full UNIQUE(chart_id, chart_date) constraint.
            self._db.add_unique_constraint()
            return

        # --- DDL: drops ------------------------------------------------------
        if norm.startswith("alter table chart_weeks drop column if exists chart_type"):
            self._db.drop_chart_type()
            return
        if norm.startswith("drop index if exists"):
            return  # indexes are not modeled; the drop is a no-op
        if norm.startswith("drop table if exists hot100_entries"):
            self._db.drop_table("hot100_entries")
            return
        if norm.startswith("drop table if exists b200_entries"):
            self._db.drop_table("b200_entries")
            return

        # --- catalog reads: information_schema.tables ------------------------
        if norm.startswith("select table_name from information_schema.tables"):
            (wanted,) = params
            present = [t for t in wanted if t in self._db.tables]
            self._result = [(t,) for t in present]
            return

        # --- catalog reads: information_schema.columns -----------------------
        # The runner hardcodes table_name = 'chart_weeks' and binds only the
        # column name, so exactly ONE param arrives here.
        if norm.startswith("select column_name from information_schema.columns"):
            (column,) = params
            present = column in self._db.columns.get("chart_weeks", set())
            self._result = [(column,)] if present else []
            return

        # --- catalog reads: pg_constraint ------------------------------------
        if norm.startswith("select 1 from pg_constraint where conname ="):
            (conname,) = params
            self._result = [(1,)] if conname in self._db.constraints else []
            return

        # --- row counts ------------------------------------------------------
        if norm.startswith("select count(*) from chart_weeks where chart_id is null"):
            self._result = [(self._db.count_null_chart_id(),)]
            return
        if norm.startswith("select count(*) from chart_entries"):
            self._result = [(len(self._db.chart_entries),)]
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
    """In-memory model of the pre-retirement schema catalog + data."""

    def __init__(self, chart_weeks=None, chart_entries=None,
                 tables=None, columns=None, constraints=None):
        # chart_weeks rows: {"id", "chart_date", "chart_id"}
        self.chart_weeks = [dict(w) for w in (chart_weeks or [])]
        self.chart_entries = [dict(e) for e in (chart_entries or [])]
        # modeled catalog
        self.tables = set(
            tables if tables is not None
            else {"chart_weeks", "chart_entries", "hot100_entries", "b200_entries"}
        )
        self.columns = {
            t: set(cols)
            for t, cols in (
                columns if columns is not None
                else {"chart_weeks": {"id", "chart_date", "chart_id", "chart_type"}}
            ).items()
        }
        self.constraints = set(constraints or [])
        self.chart_id_not_null = False

    # --- DDL mutations ---------------------------------------------------------
    def set_chart_id_not_null(self):
        self.chart_id_not_null = True

    def add_unique_constraint(self):
        self.constraints.add("chart_weeks_chart_id_date_key")

    def drop_chart_type(self):
        self.columns.get("chart_weeks", set()).discard("chart_type")
        for w in self.chart_weeks:
            w.pop("chart_type", None)

    def drop_table(self, table):
        self.tables.discard(table)

    # --- reads -----------------------------------------------------------------
    def count_null_chart_id(self):
        return sum(1 for w in self.chart_weeks if w.get("chart_id") is None)

    # --- snapshot / restore ----------------------------------------------------
    def snapshot(self):
        return copy.deepcopy({
            "chart_weeks": self.chart_weeks,
            "chart_entries": self.chart_entries,
            "tables": self.tables,
            "columns": self.columns,
            "constraints": self.constraints,
            "chart_id_not_null": self.chart_id_not_null,
        })

    def restore(self, snap):
        snap = copy.deepcopy(snap)
        self.chart_weeks = snap["chart_weeks"]
        self.chart_entries = snap["chart_entries"]
        self.tables = snap["tables"]
        self.columns = snap["columns"]
        self.constraints = snap["constraints"]
        self.chart_id_not_null = snap["chart_id_not_null"]


def _fixture():
    """A pre-retirement DB: 2 weeks (both chart_id-bearing), 3 chart_entries,
    legacy tables + chart_type column still present."""
    return FakeDB(
        chart_weeks=[
            {"id": 1, "chart_date": "2020-01-04", "chart_id": 1, "chart_type": "hot-100"},
            {"id": 2, "chart_date": "2020-01-04", "chart_id": 2, "chart_type": "billboard-200"},
        ],
        chart_entries=[
            {"id": 1, "chart_id": 1, "chart_week_id": 1, "rank": 1},
            {"id": 2, "chart_id": 1, "chart_week_id": 1, "rank": 2},
            {"id": 3, "chart_id": 2, "chart_week_id": 2, "rank": 1},
        ],
    )


# ----------------------------------------------------------------------------
# Apply: drops the legacy tables/column, promotes chart_id, commits
# ----------------------------------------------------------------------------
class RetireApplyTests(unittest.TestCase):
    def test_apply_drops_tables_and_commits(self):
        db = _fixture()
        before_entries = len(db.chart_entries)
        conn = FakeConn(db)

        report = migrate(conn, dry_run=False)

        # Legacy tables gone, chart_type column gone, UNIQUE present, NOT NULL set.
        self.assertNotIn("hot100_entries", db.tables)
        self.assertNotIn("b200_entries", db.tables)
        self.assertNotIn("chart_type", db.columns["chart_weeks"])
        self.assertIn("chart_weeks_chart_id_date_key", db.constraints)
        self.assertTrue(db.chart_id_not_null)
        # chart_entries row count unchanged (live polymorphic data untouched).
        self.assertEqual(len(db.chart_entries), before_entries)
        self.assertEqual(report["before"]["chart_entries"], before_entries)
        self.assertEqual(report["after"]["chart_entries"], before_entries)
        self.assertEqual(
            sorted(report["dropped_tables"]),
            ["b200_entries", "hot100_entries"],
        )
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)
        self.assertFalse(report["dry_run"])

    def test_second_run_is_idempotent_noop_and_still_commits(self):
        db = _fixture()
        migrate(FakeConn(db), dry_run=False)
        snapshot_after_first = db.snapshot()

        second = FakeConn(db)
        report = migrate(second, dry_run=False)

        # Nothing left to drop; state byte-for-byte identical; still commits.
        self.assertEqual(report["dropped_tables"], [])
        self.assertEqual(db.snapshot(), snapshot_after_first)
        self.assertTrue(second.committed)
        self.assertFalse(second.rolled_back)


# ----------------------------------------------------------------------------
# Dry run: reports planned drops, writes nothing
# ----------------------------------------------------------------------------
class RetireDryRunTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        db = _fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        report = migrate(conn, dry_run=True)

        self.assertTrue(report["dry_run"])
        self.assertEqual(
            sorted(report["dropped_tables"]),
            ["b200_entries", "hot100_entries"],
        )
        # Nothing written, nothing committed.
        self.assertEqual(db.snapshot(), before)
        self.assertIn("hot100_entries", db.tables)
        self.assertIn("b200_entries", db.tables)
        self.assertIn("chart_type", db.columns["chart_weeks"])
        self.assertFalse(conn.committed)


# ----------------------------------------------------------------------------
# Assertion failure -> rollback + raise
# ----------------------------------------------------------------------------
class RetireRollbackTests(unittest.TestCase):
    def test_chart_entries_count_change_rolls_back_and_raises(self):
        # Force the count-unchanged invariant to trip by mutating chart_entries
        # while dropping a table. The runner must roll back + raise.
        db = _fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        original = FakeDB.drop_table

        def row_dropping_drop(self_db, table):
            original(self_db, table)
            if table == "hot100_entries":
                self_db.chart_entries.pop()  # simulate non-additive data loss

        FakeDB.drop_table = row_dropping_drop
        try:
            with self.assertRaises(RetireLegacyMigrationError) as ctx:
                migrate(conn, dry_run=False)
        finally:
            FakeDB.drop_table = original

        self.assertIn("row-count changed", str(ctx.exception))
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)
        self.assertEqual(db.snapshot(), before)

    def test_remaining_null_chart_id_rolls_back_and_raises(self):
        # If a chart_weeks row still has a NULL chart_id after the (no-op in the
        # fake) NOT NULL promotion, the invariant must trip -> rollback + raise.
        db = _fixture()
        db.chart_weeks.append(
            {"id": 3, "chart_date": "2020-01-11", "chart_id": None,
             "chart_type": "hot-100"}
        )
        before = db.snapshot()
        conn = FakeConn(db)

        with self.assertRaises(RetireLegacyMigrationError) as ctx:
            migrate(conn, dry_run=False)

        self.assertIn("NULL chart_id", str(ctx.exception))
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)
        self.assertEqual(db.snapshot(), before)

    def test_missing_unique_constraint_rolls_back_and_raises(self):
        # If the UNIQUE(chart_id, chart_date) guard fails to add the constraint,
        # the invariant must trip -> rollback + raise.
        db = _fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        original = FakeDB.add_unique_constraint
        FakeDB.add_unique_constraint = lambda self_db: None  # guard adds nothing
        try:
            with self.assertRaises(RetireLegacyMigrationError) as ctx:
                migrate(conn, dry_run=False)
        finally:
            FakeDB.add_unique_constraint = original

        self.assertIn("UNIQUE", str(ctx.exception))
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)
        self.assertEqual(db.snapshot(), before)

    def test_table_still_present_rolls_back_and_raises(self):
        # If a legacy table somehow survives the drop, the invariant trips.
        db = _fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        original = FakeDB.drop_table

        def noop_drop(self_db, table):
            if table == "b200_entries":
                return  # b200 survives -> assertion must trip
            original(self_db, table)

        FakeDB.drop_table = noop_drop
        try:
            with self.assertRaises(RetireLegacyMigrationError) as ctx:
                migrate(conn, dry_run=False)
        finally:
            FakeDB.drop_table = original

        self.assertIn("still present", str(ctx.exception))
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)
        self.assertEqual(db.snapshot(), before)


# ----------------------------------------------------------------------------
# Module hygiene: no top-level psycopg2 import + exports
# ----------------------------------------------------------------------------
class RetirePostgresFreeTests(unittest.TestCase):
    def test_module_has_no_top_level_psycopg_import(self):
        import inspect

        source = inspect.getsource(migrate_retire_legacy)
        top_level = [
            l for l in source.splitlines()
            if l.startswith("import ") or l.startswith("from ")
        ]
        self.assertFalse(
            any("psycopg" in l for l in top_level),
            "psycopg2 must not be a top-level import",
        )

    def test_exports_migrate_main_and_error(self):
        self.assertTrue(hasattr(migrate_retire_legacy, "migrate"))
        self.assertTrue(hasattr(migrate_retire_legacy, "main"))
        self.assertTrue(hasattr(migrate_retire_legacy, "RetireLegacyMigrationError"))
        self.assertTrue(issubclass(RetireLegacyMigrationError, RuntimeError))


if __name__ == "__main__":
    unittest.main()
