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

import os
import re
import unittest

from billboard_stats.etl import migrate_gender

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


if __name__ == "__main__":
    unittest.main()
