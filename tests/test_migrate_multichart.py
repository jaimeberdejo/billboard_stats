"""Fixture/mock-DB tests for the multi-chart migration (Plan 09-02).

These tests run entirely against an in-memory fake DB layer mirroring
tests/test_reconcile_artists.py. They make NO real database connection and NO
network calls. The real-DB apply (dry-run -> snapshot -> apply -> verify parity
-> verify v1.0 pages) is the operator runbook in Plan 03, not here.

The migration is STRICTLY ADDITIVE and IDEMPOTENT: it applies the additive DDL
(IF NOT EXISTS), seeds the charts registry (hot-100 -> entity_kind=song,
billboard-200 -> entity_kind=album), backfills chart_weeks.chart_id from
chart_type, and backfills chart_entries from hot100_entries (song_id) and
b200_entries (album_id) -- exactly one entity FK per row so the
num_nonnulls(...) = 1 CHECK holds. It runs in a single transaction and asserts
row-count parity (per-chart equality + total), rolling back on any mismatch.

Fidelity gaps the fake DB does NOT model (covered by the operator runbook, not
here): real PostgreSQL num_nonnulls CHECK enforcement, real
ON CONFLICT (chart_week_id, rank) arbitration across charts, and FK validation.
The runner sets exactly one entity FK per backfilled row, which the tests assert
directly.
"""

import copy
import re
import unittest

from billboard_stats.etl import migrate_multichart
from billboard_stats.etl.migrate_multichart import (
    MigrationParityError,
    migrate,
)


class SimulatedUndefinedTable(Exception):
    """Stand-in for ``psycopg2.errors.UndefinedTable``.

    Raised by the pristine FakeCursor when a read touches a ``charts`` /
    ``chart_entries`` table that does NOT yet exist (prod's real pre-migration
    state). Subclasses Exception so the runner's broad
    ``except Exception: conn.rollback(); raise`` propagates it unchanged — the
    same way the real psycopg2 error surfaces on a pristine v1.0 DB.
    """


# ============================================================================
# In-memory fake DB layer
# ============================================================================
class FakeCursor:
    """A psycopg2-cursor-like stand-in interpreting the SQL migrate() emits.

    It models charts / chart_weeks (chart_type + nullable chart_id) /
    hot100_entries / b200_entries / chart_entries as plain Python structures and
    executes the exact statement shapes migrate_multichart.py uses. No real
    database is involved. DDL statements (CREATE TABLE IF NOT EXISTS, ALTER
    TABLE, CREATE INDEX) are accepted as no-ops because the fake DB already
    models the target shape.
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

        # --- PRISTINE-DB guard: reads of a not-yet-created object raise --------
        # Models prod's real pre-migration state where `charts` / `chart_entries`
        # do NOT exist yet. Any read (or to_regclass existence check that is NOT
        # the guard short-circuit) touching an ABSENT table raises a simulated
        # UndefinedTable -- exactly what real PostgreSQL does -- UNTIL the
        # CREATE TABLE IF NOT EXISTS DDL below flips the table present. The
        # `to_regclass('public.<table>')` existence probe is handled by its own
        # branch (it must NOT raise -- that is the whole point of the guard).
        if not norm.startswith("select to_regclass("):
            for table in ("chart_entries", "charts"):
                if not self._db.is_present(table) and (
                    f"from {table}" in norm or f"{table} ce" in norm
                ):
                    raise SimulatedUndefinedTable(
                        f'relation "{table}" does not exist'
                    )

        # --- to_regclass existence probe (the runner's pristine-DB guard) -----
        # `SELECT to_regclass('public.<table>') IS NOT NULL` -- returns the
        # boolean presence of the table WITHOUT raising even when absent.
        if norm.startswith("select to_regclass("):
            m = re.search(r"to_regclass\('public\.(\w+)'\)", norm)
            table = m.group(1) if m else None
            self._result = [(bool(self._db.is_present(table)),)]
            return

        # --- DDL: accepted as no-ops (the fake DB models the target shape) ----
        if (
            norm.startswith("create table")
            or norm.startswith("alter table")
            or norm.startswith("create index")
        ):
            # CREATE TABLE IF NOT EXISTS flips an absent table present-and-empty
            # (prod-faithful: the read now succeeds and returns 0 rows). Other
            # DDL (ALTER, CREATE INDEX, CREATE TABLE for an already-present
            # table) stays a pure no-op.
            if norm.startswith("create table if not exists charts"):
                self._db.mark_present("charts")
            elif norm.startswith("create table if not exists chart_entries"):
                self._db.mark_present("chart_entries")
            self._result = None
            return

        # --- Seed: INSERT INTO charts ... ON CONFLICT (slug) DO NOTHING -------
        if norm.startswith("insert into charts"):
            slug, title, entity_kind, category, sort_order = params
            self._db.seed_chart(slug, title, entity_kind, category, sort_order)
            return

        # --- chart_weeks.chart_id backfill ------------------------------------
        if norm.startswith("update chart_weeks set chart_id"):
            self._db.backfill_chart_weeks_chart_id()
            return

        # --- chart_entries backfill from hot100_entries -----------------------
        if (
            norm.startswith("insert into chart_entries")
            and "from hot100_entries" in norm
        ):
            self._db.backfill_chart_entries("hot-100", "song")
            return

        # --- chart_entries backfill from b200_entries -------------------------
        if (
            norm.startswith("insert into chart_entries")
            and "from b200_entries" in norm
        ):
            self._db.backfill_chart_entries("billboard-200", "album")
            return

        # --- WR-04 dry-run conflict-aware planned counts ----------------------
        # Source rows whose (chart_week_id, rank) is NOT already in
        # chart_entries -- the same conflict semantics the real backfill uses.
        if (
            norm.startswith("select count(*) from hot100_entries h")
            and "where not exists" in norm
        ):
            self._result = [(self._db.count_source_not_yet_inserted("hot-100"),)]
            return
        if (
            norm.startswith("select count(*) from b200_entries b")
            and "where not exists" in norm
        ):
            self._result = [
                (self._db.count_source_not_yet_inserted("billboard-200"),)
            ]
            return

        # --- COUNT(*) parity queries ------------------------------------------
        # Bare source counts only (the WR-03 reverse anti-joins also start with
        # "select count(*) from hot100_entries h LEFT JOIN ..." -- exclude those
        # so they fall through to the dedicated handlers below).
        if (
            norm.startswith("select count(*) from hot100_entries")
            and "left join" not in norm
            and "where not exists" not in norm
        ):
            self._result = [(len(self._db.hot100_entries),)]
            return

        if (
            norm.startswith("select count(*) from b200_entries")
            and "left join" not in norm
            and "where not exists" not in norm
        ):
            self._result = [(len(self._db.b200_entries),)]
            return

        if norm.startswith("select count(*) from chart_entries where chart_id ="):
            (chart_id,) = params
            self._result = [
                (len([e for e in self._db.chart_entries if e["chart_id"] == chart_id]),)
            ]
            return

        # --- WR-03 content-parity checks (anti-joins + polymorphism) ----------
        if norm.startswith(
            "select count(*) from chart_entries "
            "where num_nonnulls(song_id, album_id, artist_id) <> 1"
        ):
            self._result = [(self._db.count_bad_polymorphism(),)]
            return

        # hot-100 / billboard-200 anti-joins: chart_entries with no source row.
        if (
            norm.startswith("select count(*) from chart_entries ce")
            and "join charts c" in norm
            and "left join hot100_entries" in norm
        ):
            self._result = [(self._db.count_ce_orphans("hot-100"),)]
            return
        if (
            norm.startswith("select count(*) from chart_entries ce")
            and "join charts c" in norm
            and "left join b200_entries" in norm
        ):
            self._result = [(self._db.count_ce_orphans("billboard-200"),)]
            return

        # source rows that were not backfilled (reverse anti-join).
        if (
            norm.startswith("select count(*) from hot100_entries h")
            and "left join chart_entries ce" in norm
        ):
            self._result = [(self._db.count_source_missing("hot-100"),)]
            return
        if (
            norm.startswith("select count(*) from b200_entries b")
            and "left join chart_entries ce" in norm
        ):
            self._result = [(self._db.count_source_missing("billboard-200"),)]
            return

        if norm.startswith("select count(*) from chart_entries"):
            self._result = [(len(self._db.chart_entries),)]
            return

        # --- chart id lookup by slug ------------------------------------------
        if norm.startswith("select id from charts where slug ="):
            (slug,) = params
            self._result = [(self._db.chart_id(slug),)] if self._db.chart_id(slug) else []
            return

        if norm.startswith("select id, slug from charts"):
            self._result = [(c["id"], c["slug"]) for c in self._db.charts]
            return

        # --- chart_weeks.chart_id NULL check ----------------------------------
        if norm.startswith("select count(*) from chart_weeks where chart_id is null"):
            self._result = [
                (len([w for w in self._db.chart_weeks if w["chart_id"] is None]),)
            ]
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
    """In-memory model of charts / chart_weeks / hot100_entries / b200_entries /
    chart_entries for the migration."""

    # The tables whose presence the pristine-DB model tracks. Every other table
    # (chart_weeks, hot100_entries, b200_entries, ...) is a v1.0 table that
    # ALWAYS exists, so it is never gated.
    _GATED_TABLES = ("charts", "chart_entries")

    def __init__(
        self,
        chart_weeks=None,
        hot100_entries=None,
        b200_entries=None,
        charts=None,
        chart_entries=None,
        present_tables=None,
    ):
        # chart_weeks: {"id": int, "chart_type": str, "chart_id": int|None}
        self.chart_weeks = [dict(w) for w in (chart_weeks or [])]
        # hot100_entries / b200_entries: full v1.0 entry rows
        self.hot100_entries = [dict(e) for e in (hot100_entries or [])]
        self.b200_entries = [dict(e) for e in (b200_entries or [])]
        # charts: {"id", "slug", "title", "entity_kind", "category", "sort_order"}
        self.charts = [dict(c) for c in (charts or [])]
        # chart_entries: polymorphic rows
        self.chart_entries = [dict(e) for e in (chart_entries or [])]
        self._next_chart_id = (max((c["id"] for c in self.charts), default=0)) + 1
        self._next_ce_id = (max((e["id"] for e in self.chart_entries), default=0)) + 1
        # Which gated tables currently EXIST. Defaults to all-present so every
        # existing fixture behaves exactly as before; the pristine factory passes
        # an empty set so charts/chart_entries start ABSENT until DDL creates them.
        self.present_tables = (
            set(self._GATED_TABLES) if present_tables is None else set(present_tables)
        )

    # --- pristine-DB presence tracking ----------------------------------------
    def is_present(self, table):
        """Whether a gated table currently exists. Non-gated (v1.0) tables are
        always present."""
        if table not in self._GATED_TABLES:
            return True
        return table in self.present_tables

    def mark_present(self, table):
        """Flip a gated table from absent to present (CREATE TABLE IF NOT EXISTS)."""
        self.present_tables.add(table)

    # --- seed ------------------------------------------------------------------
    def seed_chart(self, slug, title, entity_kind, category, sort_order):
        """INSERT ... ON CONFLICT (slug) DO NOTHING."""
        for c in self.charts:
            if c["slug"] == slug:
                return  # conflict -> do nothing
        new_id = self._next_chart_id
        self._next_chart_id += 1
        self.charts.append(
            {
                "id": new_id,
                "slug": slug,
                "title": title,
                "entity_kind": entity_kind,
                "category": category,
                "sort_order": sort_order,
            }
        )

    def chart_id(self, slug):
        for c in self.charts:
            if c["slug"] == slug:
                return c["id"]
        return None

    # --- backfills -------------------------------------------------------------
    def backfill_chart_weeks_chart_id(self):
        """UPDATE chart_weeks SET chart_id = (chart by slug) WHERE chart_id IS NULL."""
        for w in self.chart_weeks:
            if w["chart_id"] is None:
                w["chart_id"] = self.chart_id(w["chart_type"])

    def _week_chart_type(self, chart_week_id):
        for w in self.chart_weeks:
            if w["id"] == chart_week_id:
                return w["chart_type"]
        return None

    def backfill_chart_entries(self, slug, entity_kind):
        """INSERT INTO chart_entries ... ON CONFLICT (chart_week_id, rank) DO NOTHING.

        Mirrors the migration: exactly one entity FK per row (song_id for
        hot-100, album_id for billboard-200), conflict-skipping on
        (chart_week_id, rank), and JOINed to chart_weeks ON cw.chart_type = slug
        so a source row whose week is the WRONG chart_type is NOT backfilled
        (WR-02 -- guarantees chart_entries.chart_id agrees with the week).
        """
        chart_id = self.chart_id(slug)
        source = self.hot100_entries if entity_kind == "song" else self.b200_entries
        entity_col = "song_id" if entity_kind == "song" else "album_id"
        existing = {(e["chart_week_id"], e["rank"]) for e in self.chart_entries}
        for src in source:
            # WR-02: JOIN chart_weeks ON cw.chart_type = slug -- skip rows whose
            # source week is not actually this chart's type.
            if self._week_chart_type(src["chart_week_id"]) != slug:
                continue
            key = (src["chart_week_id"], src["rank"])
            if key in existing:
                continue  # ON CONFLICT (chart_week_id, rank) DO NOTHING
            existing.add(key)
            row = {
                "id": self._next_ce_id,
                "chart_id": chart_id,
                "chart_week_id": src["chart_week_id"],
                "song_id": None,
                "album_id": None,
                "artist_id": None,
                "rank": src["rank"],
                "peak_pos": src.get("peak_pos"),
                "last_pos": src.get("last_pos"),
                "weeks_on_chart": src.get("weeks_on_chart"),
                "is_new": src.get("is_new", False),
            }
            row[entity_col] = src[entity_col]
            self._next_ce_id += 1
            self.chart_entries.append(row)

    # --- WR-04 dry-run conflict-aware planned-count modeling ------------------
    def count_source_not_yet_inserted(self, slug):
        """Source rows whose (chart_week_id, rank) is NOT already present in
        chart_entries -- mirrors ON CONFLICT (chart_week_id, rank) DO NOTHING,
        regardless of chart_id (the real conflict key is week+rank)."""
        source = self.hot100_entries if slug == "hot-100" else self.b200_entries
        present = {(e["chart_week_id"], e["rank"]) for e in self.chart_entries}
        return sum(
            1 for s in source if (s["chart_week_id"], s["rank"]) not in present
        )

    # --- WR-03 content-parity modeling ----------------------------------------
    def count_bad_polymorphism(self):
        """Rows that don't set EXACTLY one of song_id/album_id/artist_id."""
        bad = 0
        for e in self.chart_entries:
            nonnull = sum(
                1 for k in ("song_id", "album_id", "artist_id") if e.get(k) is not None
            )
            if nonnull != 1:
                bad += 1
        return bad

    def count_ce_orphans(self, slug):
        """chart_entries rows for ``slug`` with no matching source row on
        (chart_week_id, rank, entity_id) -- the forward anti-join."""
        chart_id = self.chart_id(slug)
        if slug == "hot-100":
            source = {
                (s["chart_week_id"], s["rank"], s["song_id"])
                for s in self.hot100_entries
            }
            col = "song_id"
        else:
            source = {
                (s["chart_week_id"], s["rank"], s["album_id"])
                for s in self.b200_entries
            }
            col = "album_id"
        orphans = 0
        for e in self.chart_entries:
            if e["chart_id"] != chart_id:
                continue
            if (e["chart_week_id"], e["rank"], e[col]) not in source:
                orphans += 1
        return orphans

    def count_source_missing(self, slug):
        """Source rows that were NOT backfilled into chart_entries for ``slug``
        on (chart_week_id, rank, entity_id) -- the reverse anti-join."""
        chart_id = self.chart_id(slug)
        if slug == "hot-100":
            source = self.hot100_entries
            col = "song_id"
        else:
            source = self.b200_entries
            col = "album_id"
        present = {
            (e["chart_week_id"], e["rank"], e[col])
            for e in self.chart_entries
            if e["chart_id"] == chart_id
        }
        missing = 0
        for s in source:
            if (s["chart_week_id"], s["rank"], s[col]) not in present:
                missing += 1
        return missing

    # --- snapshot --------------------------------------------------------------
    def snapshot(self):
        return copy.deepcopy(
            {
                "chart_weeks": self.chart_weeks,
                "hot100_entries": self.hot100_entries,
                "b200_entries": self.b200_entries,
                "charts": self.charts,
                "chart_entries": self.chart_entries,
                "present_tables": sorted(self.present_tables),
            }
        )

    def restore(self, snap):
        snap = copy.deepcopy(snap)
        self.chart_weeks = snap["chart_weeks"]
        self.hot100_entries = snap["hot100_entries"]
        self.b200_entries = snap["b200_entries"]
        self.charts = snap["charts"]
        self.chart_entries = snap["chart_entries"]
        self.present_tables = set(snap.get("present_tables", self._GATED_TABLES))


def _fixture():
    """A small fixture DB: 2 hot-100 weeks + 1 b200 week, no charts/chart_entries
    yet (a pristine pre-migration v1.0 DB)."""
    chart_weeks = [
        {"id": 1, "chart_type": "hot-100", "chart_id": None},
        {"id": 2, "chart_type": "hot-100", "chart_id": None},
        {"id": 3, "chart_type": "billboard-200", "chart_id": None},
    ]
    hot100_entries = [
        {"id": 1, "chart_week_id": 1, "song_id": 10, "rank": 1,
         "peak_pos": 1, "last_pos": 2, "weeks_on_chart": 5, "is_new": False},
        {"id": 2, "chart_week_id": 1, "song_id": 11, "rank": 2,
         "peak_pos": 2, "last_pos": 1, "weeks_on_chart": 3, "is_new": False},
        {"id": 3, "chart_week_id": 2, "song_id": 10, "rank": 1,
         "peak_pos": 1, "last_pos": 1, "weeks_on_chart": 6, "is_new": False},
    ]
    b200_entries = [
        {"id": 1, "chart_week_id": 3, "album_id": 20, "rank": 1,
         "peak_pos": 1, "last_pos": None, "weeks_on_chart": 1, "is_new": True},
        {"id": 2, "chart_week_id": 3, "album_id": 21, "rank": 2,
         "peak_pos": 2, "last_pos": 2, "weeks_on_chart": 4, "is_new": False},
    ]
    return FakeDB(chart_weeks, hot100_entries, b200_entries)


def _pristine_fixture():
    """Prod's ACTUAL pre-migration shape: chart_weeks + hot100_entries +
    b200_entries populated, but `charts` and `chart_entries` ABSENT (the tables
    don't exist yet -- not merely empty). Any read of `charts` / `chart_entries`
    raises a simulated UndefinedTable until the migration's
    CREATE TABLE IF NOT EXISTS DDL flips them present.

    This is the fixture the FakeDB-seeded `_fixture()` could NOT model (it
    pre-defines `chart_entries=[]`), which is exactly why the pristine-DB
    UndefinedTable defect slipped past the offline suite.
    """
    db = _fixture()
    db.present_tables = set()  # charts + chart_entries do NOT exist yet
    return db


# ----------------------------------------------------------------------------
# Pristine v1.0 DB: charts / chart_entries absent until the DDL creates them
# (MIG-01 regression — the CONFIRMED DEFECT: pre-DDL reads of those tables
# raise UndefinedTable on the real prod DB in BOTH dry-run and apply).
# ----------------------------------------------------------------------------
class MigratePristineDbTests(unittest.TestCase):
    def test_dry_run_on_pristine_db_succeeds(self):
        db = _pristine_fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        report = migrate(conn, dry_run=True)

        self.assertTrue(report["dry_run"])
        # A missing `charts` table => no chart seeded yet => both planned.
        self.assertEqual(report["seeded_charts"], 2)
        # A missing `chart_entries` table => every source row is a planned insert.
        self.assertEqual(report["backfill"]["hot-100"], len(db.hot100_entries))
        self.assertEqual(
            report["backfill"]["billboard-200"], len(db.b200_entries)
        )
        # Dry-run still writes nothing and commits nothing.
        self.assertEqual(db.snapshot(), before)
        self.assertFalse(conn.committed)

    def test_apply_on_pristine_db_succeeds(self):
        db = _pristine_fixture()
        conn = FakeConn(db)

        report = migrate(conn, dry_run=False)

        self.assertFalse(report["dry_run"])
        # Seeded both charts and backfilled the full source counts.
        self.assertEqual(report["seeded_charts"], 2)
        self.assertEqual(report["backfill"]["hot-100"], len(db.hot100_entries))
        self.assertEqual(
            report["backfill"]["billboard-200"], len(db.b200_entries)
        )
        # Parity + content checks held -> committed (no rollback).
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)
        # The DDL flipped both tables present.
        self.assertTrue(db.is_present("charts"))
        self.assertTrue(db.is_present("chart_entries"))
        # Per-chart parity holds on the now-created chart_entries.
        hot100_id = db.chart_id("hot-100")
        b200_id = db.chart_id("billboard-200")
        self.assertEqual(
            len([e for e in db.chart_entries if e["chart_id"] == hot100_id]),
            len(db.hot100_entries),
        )
        self.assertEqual(
            len([e for e in db.chart_entries if e["chart_id"] == b200_id]),
            len(db.b200_entries),
        )


# ----------------------------------------------------------------------------
# Parity / backfill success
# ----------------------------------------------------------------------------
class MigrateParityTests(unittest.TestCase):
    def test_seed_and_backfill_parity_commits(self):
        db = _fixture()
        conn = FakeConn(db)

        report = migrate(conn, dry_run=False)

        # Registry seeded with the two charts (correct entity_kind).
        hot100 = next(c for c in db.charts if c["slug"] == "hot-100")
        b200 = next(c for c in db.charts if c["slug"] == "billboard-200")
        self.assertEqual(hot100["entity_kind"], "song")
        self.assertEqual(b200["entity_kind"], "album")

        # Per-chart count parity: chart_entries(hot-100) == hot100_entries, etc.
        hot100_ce = [e for e in db.chart_entries if e["chart_id"] == hot100["id"]]
        b200_ce = [e for e in db.chart_entries if e["chart_id"] == b200["id"]]
        self.assertEqual(len(hot100_ce), len(db.hot100_entries))
        self.assertEqual(len(b200_ce), len(db.b200_entries))
        # Total parity.
        self.assertEqual(
            len(db.chart_entries),
            len(db.hot100_entries) + len(db.b200_entries),
        )

        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)
        self.assertFalse(report["dry_run"])

    def test_each_chart_entry_has_exactly_one_entity_id(self):
        db = _fixture()
        migrate(FakeConn(db), dry_run=False)
        for e in db.chart_entries:
            nonnull = sum(
                1 for k in ("song_id", "album_id", "artist_id") if e[k] is not None
            )
            self.assertEqual(nonnull, 1, f"row {e} must set exactly one entity FK")

    def test_hot100_rows_set_song_id_b200_rows_set_album_id(self):
        db = _fixture()
        migrate(FakeConn(db), dry_run=False)
        hot100_id = db.chart_id("hot-100")
        b200_id = db.chart_id("billboard-200")
        for e in db.chart_entries:
            if e["chart_id"] == hot100_id:
                self.assertIsNotNone(e["song_id"])
                self.assertIsNone(e["album_id"])
                self.assertIsNone(e["artist_id"])
            elif e["chart_id"] == b200_id:
                self.assertIsNotNone(e["album_id"])
                self.assertIsNone(e["song_id"])
                self.assertIsNone(e["artist_id"])

    def test_chart_weeks_chart_id_backfilled_chart_type_preserved(self):
        db = _fixture()
        migrate(FakeConn(db), dry_run=False)
        for w in db.chart_weeks:
            # chart_id is backfilled from chart_type for every week.
            self.assertIsNotNone(w["chart_id"])
            self.assertEqual(w["chart_id"], db.chart_id(w["chart_type"]))
            # chart_type stays populated (Phase 15 retires it, not this migration).
            self.assertIn(w["chart_type"], ("hot-100", "billboard-200"))


# ----------------------------------------------------------------------------
# WR-02: backfill is scoped to the source week's chart_type
# ----------------------------------------------------------------------------
class MigrateChartTypeScopingTests(unittest.TestCase):
    def test_backfill_skips_source_row_pointing_at_wrong_type_week(self):
        # A hot100_entries row that (corruptly) references a billboard-200 week
        # must NOT be backfilled as a hot-100 chart_entries row, because the
        # JOIN scopes the hot-100 backfill to cw.chart_type='hot-100' (WR-02).
        chart_weeks = [
            {"id": 1, "chart_type": "hot-100", "chart_id": None},
            {"id": 2, "chart_type": "billboard-200", "chart_id": None},
        ]
        hot100_entries = [
            # legitimate hot-100 row
            {"id": 1, "chart_week_id": 1, "song_id": 10, "rank": 1,
             "peak_pos": 1, "last_pos": None, "weeks_on_chart": 2, "is_new": False},
            # CORRUPT: hot100 entry whose week is a billboard-200 week
            {"id": 2, "chart_week_id": 2, "song_id": 11, "rank": 5,
             "peak_pos": 5, "last_pos": None, "weeks_on_chart": 1, "is_new": True},
        ]
        b200_entries = [
            {"id": 1, "chart_week_id": 2, "album_id": 20, "rank": 1,
             "peak_pos": 1, "last_pos": None, "weeks_on_chart": 3, "is_new": False},
        ]
        db = FakeDB(chart_weeks, hot100_entries, b200_entries)
        conn = FakeConn(db)

        # The corrupt row breaks hot-100 count parity (1 backfilled != 2 source),
        # so the migration must roll back and raise rather than silently
        # mislabel the row.
        with self.assertRaises(MigrationParityError):
            migrate(conn, dry_run=False)
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)

    def test_chart_entries_chart_id_agrees_with_week_chart_id(self):
        # On a clean DB, every backfilled chart_entries row's chart_id matches
        # its referenced week's chart_id (the invariant WR-02 protects).
        db = _fixture()
        migrate(FakeConn(db), dry_run=False)
        week_chart_id = {w["id"]: w["chart_id"] for w in db.chart_weeks}
        for e in db.chart_entries:
            self.assertEqual(e["chart_id"], week_chart_id[e["chart_week_id"]])


# ----------------------------------------------------------------------------
# Parity mismatch -> rollback
# ----------------------------------------------------------------------------
class MigrateRollbackTests(unittest.TestCase):
    def test_parity_mismatch_rolls_back_and_raises(self):
        # Force a backfilled count != source count by corrupting the backfill so
        # one hot-100 row is dropped. The parity assertion must trip, rolling
        # back and raising MigrationParityError; state is restored.
        db = _fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        original = FakeDB.backfill_chart_entries

        def broken_backfill(self_db, slug, entity_kind):
            original(self_db, slug, entity_kind)
            if slug == "hot-100" and self_db.chart_entries:
                # Drop one freshly inserted hot-100 row to break parity.
                self_db.chart_entries.pop()

        FakeDB.backfill_chart_entries = broken_backfill
        try:
            with self.assertRaises(MigrationParityError):
                migrate(conn, dry_run=False)
        finally:
            FakeDB.backfill_chart_entries = original

        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)
        # State restored to its pre-run snapshot.
        self.assertEqual(db.snapshot(), before)

    def test_wrong_content_equal_count_backfill_is_caught(self):
        # WR-03: a backfill that inserts the RIGHT NUMBER of rows but with a
        # WRONG song_id must fail the content anti-join (count parity passes,
        # content parity does not) -> rollback + raise.
        db = _fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        original = FakeDB.backfill_chart_entries

        def corrupting_backfill(self_db, slug, entity_kind):
            original(self_db, slug, entity_kind)
            if slug == "hot-100":
                # Corrupt one freshly inserted hot-100 row's song_id to a value
                # that has no matching source row. Count is unchanged.
                for e in self_db.chart_entries:
                    if e["chart_id"] == self_db.chart_id("hot-100"):
                        e["song_id"] = 99999  # not in hot100_entries
                        break

        FakeDB.backfill_chart_entries = corrupting_backfill
        try:
            with self.assertRaises(MigrationParityError) as ctx:
                migrate(conn, dry_run=False)
        finally:
            FakeDB.backfill_chart_entries = original

        self.assertIn("content mismatch", str(ctx.exception))
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)
        self.assertEqual(db.snapshot(), before)


# ----------------------------------------------------------------------------
# Dry run
# ----------------------------------------------------------------------------
class MigrateDryRunTests(unittest.TestCase):
    def test_dry_run_reports_but_writes_nothing(self):
        db = _fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        report = migrate(conn, dry_run=True)

        self.assertTrue(report["dry_run"])
        # Planned counts are reported.
        self.assertEqual(report["backfill"]["hot-100"], len(db.hot100_entries))
        self.assertEqual(report["backfill"]["billboard-200"], len(db.b200_entries))
        # Nothing was written and nothing was committed.
        self.assertEqual(db.snapshot(), before)
        self.assertFalse(conn.committed)

    def test_dry_run_planned_count_uses_conflict_semantics(self):
        # WR-04: with some rows ALREADY present at (chart_week_id, rank), the
        # dry-run planned count must report only the source rows that WOULD
        # insert (conflict-aware), not max(total - chart_id_count, 0).
        db = _fixture()
        # Pre-seed the charts + one already-migrated hot-100 row at (week 1,
        # rank 1) so it would conflict-skip.
        db.seed_chart("hot-100", "Billboard Hot 100", "song", "core", 1)
        db.seed_chart("billboard-200", "Billboard 200", "album", "core", 2)
        db.chart_entries.append(
            {
                "id": 999, "chart_id": db.chart_id("hot-100"),
                "chart_week_id": 1, "song_id": 10, "album_id": None,
                "artist_id": None, "rank": 1, "peak_pos": 1, "last_pos": None,
                "weeks_on_chart": 5, "is_new": False,
            }
        )
        before = db.snapshot()
        conn = FakeConn(db)

        report = migrate(conn, dry_run=True)

        # 3 hot-100 source rows, 1 already present at (1,1) -> 2 would insert.
        self.assertEqual(report["backfill"]["hot-100"], 2)
        # No billboard-200 rows present yet -> all source rows would insert.
        self.assertEqual(
            report["backfill"]["billboard-200"], len(db.b200_entries)
        )
        # Still writes nothing.
        self.assertEqual(db.snapshot(), before)
        self.assertFalse(conn.committed)


# ----------------------------------------------------------------------------
# Idempotent re-run
# ----------------------------------------------------------------------------
class MigrateIdempotencyTests(unittest.TestCase):
    def test_second_run_is_noop_and_parity_still_holds(self):
        db = _fixture()
        migrate(FakeConn(db), dry_run=False)
        snapshot_after_first = db.snapshot()

        second = FakeConn(db)
        report = migrate(second, dry_run=False)

        # Zero new chart_entries, zero new charts on the second run.
        self.assertEqual(report["backfill"]["hot-100"], 0)
        self.assertEqual(report["backfill"]["billboard-200"], 0)
        self.assertEqual(report["seeded_charts"], 0)
        # State byte-for-byte identical to after the first run.
        self.assertEqual(db.snapshot(), snapshot_after_first)
        # The migration still COMMITS (parity holds on TOTAL counts even with
        # zero inserts this run).
        self.assertTrue(second.committed)
        self.assertFalse(second.rolled_back)

        # Parity is asserted on TOTAL post-backfill counts, so it still holds.
        hot100_id = db.chart_id("hot-100")
        b200_id = db.chart_id("billboard-200")
        self.assertEqual(
            len([e for e in db.chart_entries if e["chart_id"] == hot100_id]),
            len(db.hot100_entries),
        )
        self.assertEqual(
            len([e for e in db.chart_entries if e["chart_id"] == b200_id]),
            len(db.b200_entries),
        )


# ----------------------------------------------------------------------------
# Module hygiene: no top-level psycopg2 import
# ----------------------------------------------------------------------------
class MigratePostgresFreeTests(unittest.TestCase):
    def test_module_has_no_top_level_psycopg_import(self):
        import inspect

        src = migrate_multichart  # module object
        source = inspect.getsource(src)
        lines = source.splitlines()
        top_level = [
            l for l in lines if l.startswith("import ") or l.startswith("from ")
        ]
        self.assertFalse(
            any("psycopg" in l for l in top_level),
            "psycopg2 must not be a top-level import",
        )

    def test_exports_migrate_main_and_error(self):
        self.assertTrue(hasattr(migrate_multichart, "migrate"))
        self.assertTrue(hasattr(migrate_multichart, "main"))
        self.assertTrue(hasattr(migrate_multichart, "MigrationParityError"))
        self.assertTrue(issubclass(MigrationParityError, RuntimeError))


if __name__ == "__main__":
    unittest.main()
