"""Fixture/mock-DB tests for the registry-driven loader (Plan 10-02, DATA-06).

These tests run entirely against an in-memory fake DB layer mirroring
tests/test_migrate_multichart.py and tests/test_stats_builder_parametric.py.
They make NO real database connection and NO network calls. The real-DB full
2-chart run parity is the operator runbook in Plan 03, not here.

What these tests pin down (success criteria #1, #2):

* ``load_chart(conn, chart, ...)`` is ONE entity_kind-dispatched loader that
  replaces ``_load_hot100`` / ``_load_b200``. song -> songs/song_artists +
  chart_entries.song_id; album -> albums/album_artists + chart_entries.album_id.
* DUAL-WRITE: for the two LEGACY charts it writes the new ``chart_entries`` row
  AND the mapped legacy table (hot100_entries/song or b200_entries/album), same
  count and same ``(chart_week_id, rank)``. A NEW chart (``legacy_table=None``)
  writes ``chart_entries`` ONLY -- zero legacy rows.
* ``chart_weeks`` carries BOTH ``chart_type`` (legacy upsert key) AND
  ``chart_id`` (the registry id), so the old and new phantom CTEs both resolve.
* Every ``chart_entries`` row sets EXACTLY ONE of song_id/album_id/artist_id.

The loader is driven over a parsed-entry fixture by stubbing ``parse_chart_file``
and ``list_chart_files`` so the loader exercises the REAL per-entry path (entity
upsert, artist links, dual-write) with no on-disk JSON.
"""

import re
import unittest

from billboard_stats.etl import loader
from billboard_stats.etl.chart_registry import ChartRecord


# ============================================================================
# In-memory fake DB layer
# ============================================================================
class FakeCursor:
    """A psycopg2-cursor-like stand-in interpreting the SQL load_chart emits.

    Models charts / chart_weeks / songs / albums / artists / song_artists /
    album_artists / chart_entries / hot100_entries / b200_entries as plain
    Python structures and executes the exact statement shapes load_chart uses,
    including the execute_values batch INSERTs (driven through the module-level
    ``execute_values`` shim in this test).
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

        # --- pre-load artist cache: SELECT id, name FROM artists ---------------
        if norm.startswith("select id, name from artists"):
            self._result = [(a["id"], a["name"]) for a in self._db.artists]
            return

        # --- chart_id resolution: SELECT id FROM charts WHERE slug = %s --------
        if norm.startswith("select id from charts where slug ="):
            (slug,) = params
            cid = self._db.chart_id(slug)
            self._result = [(cid,)] if cid is not None else []
            return

        # --- chart_weeks upsert (legacy: chart_type + chart_id) ----------------
        if norm.startswith("insert into chart_weeks"):
            self._result = [(self._db.upsert_chart_week(norm, params),)]
            return

        # --- songs upsert ------------------------------------------------------
        if norm.startswith("insert into songs"):
            title, artist_credit, image = params
            self._result = [(self._db.upsert_song(title, artist_credit, image),)]
            return

        # --- albums upsert -----------------------------------------------------
        if norm.startswith("insert into albums"):
            title, artist_credit, image = params
            self._result = [(self._db.upsert_album(title, artist_credit, image),)]
            return

        # --- artists upsert ----------------------------------------------------
        if norm.startswith("insert into artists"):
            (name,) = params
            self._result = [(self._db.upsert_artist(name),)]
            return

        # --- song_artists link -------------------------------------------------
        if norm.startswith("insert into song_artists"):
            song_id, artist_id, role = params
            self._db.link_song_artist(song_id, artist_id, role)
            return

        # --- album_artists link ------------------------------------------------
        if norm.startswith("insert into album_artists"):
            album_id, artist_id, role = params
            self._db.link_album_artist(album_id, artist_id, role)
            return

        raise AssertionError(f"FakeCursor: unhandled SQL: {norm!r}")

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None


class FakeConn:
    def __init__(self, db):
        self._db = db
        self.commits = 0

    def cursor(self):
        return FakeCursor(self._db)

    def commit(self):
        self.commits += 1


def _fake_execute_values(cur, sql, rows, page_size=None):
    """Stand-in for psycopg2.extras.execute_values.

    Interprets the two batch INSERT shapes load_chart emits -- INTO chart_entries
    and INTO the mapped legacy table -- and applies them to the fake DB with
    ON CONFLICT (chart_week_id, rank) DO NOTHING semantics.
    """
    db = cur._db
    norm = re.sub(r"\s+", " ", sql).strip().lower()

    if norm.startswith("insert into chart_entries"):
        db.insert_chart_entries(rows)
        return
    if norm.startswith("insert into hot100_entries"):
        db.insert_legacy("hot100_entries", "song_id", rows)
        return
    if norm.startswith("insert into b200_entries"):
        db.insert_legacy("b200_entries", "album_id", rows)
        return
    raise AssertionError(f"_fake_execute_values: unhandled SQL: {norm!r}")


class FakeDB:
    """In-memory model of every table load_chart touches."""

    def __init__(self, charts=None, artists=None):
        # charts: {"id", "slug", "entity_kind"}
        self.charts = [dict(c) for c in (charts or [])]
        self.artists = [dict(a) for a in (artists or [])]
        self.songs = []
        self.albums = []
        self.song_artists = []
        self.album_artists = []
        self.chart_weeks = []
        self.chart_entries = []
        self.hot100_entries = []
        self.b200_entries = []
        self._next = {
            "artist": (max((a["id"] for a in self.artists), default=0)) + 1,
            "song": 1,
            "album": 1,
            "week": 1,
            "ce": 1,
            "legacy": 1,
        }

    def _take(self, kind):
        v = self._next[kind]
        self._next[kind] += 1
        return v

    # --- lookups ---------------------------------------------------------------
    def chart_id(self, slug):
        for c in self.charts:
            if c["slug"] == slug:
                return c["id"]
        return None

    # --- upserts ---------------------------------------------------------------
    def upsert_chart_week(self, norm, params):
        """Upsert chart_weeks and return the week id, modeling the REAL Postgres
        conflict keys (CR-01) -- NOT a chart_id-aware match that masks duplicates.

        Handles BOTH week-insert shapes load_chart emits, each with its OWN
        conflict arbiter exactly as real Postgres applies it:

        * LEGACY charts: ``(chart_date, chart_type, chart_id)`` -- ON CONFLICT on
          the existing ``UNIQUE(chart_date, chart_type)``. The dedup key is
          (chart_date, chart_type) ONLY; chart_id is NOT part of the key. On a
          conflict the row's chart_id is refreshed (``SET chart_id =
          EXCLUDED.chart_id``).
        * NEW charts: ``(chart_date, chart_id)`` -- ON CONFLICT on the partial
          unique index ``uq_chart_weeks_chart_id_date (chart_id, chart_date)
          WHERE chart_id IS NOT NULL``. The dedup key is (chart_id, chart_date)
          ONLY (no chart_type). This makes a new-chart re-load idempotent instead
          of inserting a duplicate week.

        Matching the real keys here is what lets the new-chart idempotency test
        actually exercise the dedup: an earlier chart_id-aware match key agreed
        with real Postgres only by luck (chart_id is constant per chart in tests)
        and silently masked the duplicate-week bug.
        """
        if len(params) == 3:
            # Legacy: dedup on (chart_date, chart_type) ONLY.
            chart_date, chart_type, chart_id = params
            for w in self.chart_weeks:
                if (
                    w["chart_date"] == chart_date
                    and w["chart_type"] == chart_type
                ):
                    w["chart_id"] = chart_id  # SET chart_id = EXCLUDED.chart_id
                    return w["id"]
        else:
            # New chart: dedup on (chart_id, chart_date) ONLY (chart_type NULL).
            chart_date, chart_id = params
            chart_type = None
            for w in self.chart_weeks:
                if (
                    w["chart_id"] == chart_id
                    and w["chart_date"] == chart_date
                ):
                    w["chart_id"] = chart_id  # SET chart_id = EXCLUDED.chart_id
                    return w["id"]

        wid = self._take("week")
        self.chart_weeks.append(
            {
                "id": wid,
                "chart_date": chart_date,
                "chart_type": chart_type,
                "chart_id": chart_id,
            }
        )
        return wid

    def upsert_song(self, title, artist_credit, image):
        for s in self.songs:
            if s["title"] == title and s["artist_credit"] == artist_credit:
                return s["id"]
        sid = self._take("song")
        self.songs.append(
            {"id": sid, "title": title, "artist_credit": artist_credit,
             "image_url": image}
        )
        return sid

    def upsert_album(self, title, artist_credit, image):
        for a in self.albums:
            if a["title"] == title and a["artist_credit"] == artist_credit:
                return a["id"]
        aid = self._take("album")
        self.albums.append(
            {"id": aid, "title": title, "artist_credit": artist_credit,
             "image_url": image}
        )
        return aid

    def upsert_artist(self, name):
        for a in self.artists:
            if a["name"] == name:
                return a["id"]
        aid = self._take("artist")
        self.artists.append({"id": aid, "name": name})
        return aid

    def link_song_artist(self, song_id, artist_id, role):
        key = (song_id, artist_id)
        if any((l["song_id"], l["artist_id"]) == key for l in self.song_artists):
            return  # ON CONFLICT DO NOTHING
        self.song_artists.append(
            {"song_id": song_id, "artist_id": artist_id, "role": role}
        )

    def link_album_artist(self, album_id, artist_id, role):
        key = (album_id, artist_id)
        if any((l["album_id"], l["artist_id"]) == key for l in self.album_artists):
            return
        self.album_artists.append(
            {"album_id": album_id, "artist_id": artist_id, "role": role}
        )

    # --- batch inserts ---------------------------------------------------------
    def insert_chart_entries(self, rows):
        """Each row: (chart_id, chart_week_id, song_id, album_id, artist_id,
        rank, peak_pos, last_pos, weeks_on_chart, is_new). ON CONFLICT
        (chart_week_id, rank) DO NOTHING."""
        present = {(e["chart_week_id"], e["rank"]) for e in self.chart_entries}
        for r in rows:
            (chart_id, chart_week_id, song_id, album_id, artist_id, rank,
             peak_pos, last_pos, weeks_on_chart, is_new) = r
            if (chart_week_id, rank) in present:
                continue
            present.add((chart_week_id, rank))
            self.chart_entries.append(
                {
                    "id": self._take("ce"),
                    "chart_id": chart_id,
                    "chart_week_id": chart_week_id,
                    "song_id": song_id,
                    "album_id": album_id,
                    "artist_id": artist_id,
                    "rank": rank,
                    "peak_pos": peak_pos,
                    "last_pos": last_pos,
                    "weeks_on_chart": weeks_on_chart,
                    "is_new": is_new,
                }
            )

    def insert_legacy(self, table, entity_col, rows):
        """Each row: (chart_week_id, entity_id, rank, peak_pos, last_pos,
        weeks_on_chart, is_new). ON CONFLICT (chart_week_id, rank) DO NOTHING."""
        target = getattr(self, table)
        present = {(e["chart_week_id"], e["rank"]) for e in target}
        for r in rows:
            (chart_week_id, entity_id, rank, peak_pos, last_pos,
             weeks_on_chart, is_new) = r
            if (chart_week_id, rank) in present:
                continue
            present.add((chart_week_id, rank))
            target.append(
                {
                    "id": self._take("legacy"),
                    "chart_week_id": chart_week_id,
                    entity_col: entity_id,
                    "rank": rank,
                    "peak_pos": peak_pos,
                    "last_pos": last_pos,
                    "weeks_on_chart": weeks_on_chart,
                    "is_new": is_new,
                }
            )


# ============================================================================
# Fixtures
# ============================================================================
from datetime import date


_HOT100_ENTRIES = [
    {"rank": 1, "title": "Song A", "artist": "Artist One", "peak_pos": 1,
     "last_pos": 2, "weeks": 5, "is_new": False, "image": None},
    {"rank": 2, "title": "Song B", "artist": "Artist Two Featuring Artist One",
     "peak_pos": 2, "last_pos": 1, "weeks": 3, "is_new": False, "image": None},
]

_B200_ENTRIES = [
    {"rank": 1, "title": "Album A", "artist": "Artist One", "peak_pos": 1,
     "last_pos": None, "weeks": 1, "is_new": True, "image": None},
    {"rank": 2, "title": "Album B", "artist": "Artist Three", "peak_pos": 2,
     "last_pos": 2, "weeks": 4, "is_new": False, "image": None},
]

_NEW_CHART_ENTRIES = [
    {"rank": 1, "title": "Country Song A", "artist": "Artist Four", "peak_pos": 1,
     "last_pos": None, "weeks": 1, "is_new": True, "image": None},
]


def _hot100_record():
    return ChartRecord(
        slug="hot-100", entity_kind="song", folder="/fake/hot100",
        last_loaded_date=None, legacy_table=("hot100_entries", "song_id"),
    )


def _b200_record():
    return ChartRecord(
        slug="billboard-200", entity_kind="album", folder="/fake/b200",
        last_loaded_date=None, legacy_table=("b200_entries", "album_id"),
    )


def _new_chart_record():
    return ChartRecord(
        slug="country-songs", entity_kind="song", folder="/fake/country-songs",
        last_loaded_date=None, legacy_table=None,
    )


class _LoaderHarness:
    """Patch the loader's parse_chart_file/list_chart_files/execute_values so
    load_chart runs over an in-memory parsed-entry fixture.

    ``chart_date_offset`` shifts the single stubbed week file's date so multiple
    ``_load`` passes for the SAME chart produce DISTINCT chart_weeks (they would
    otherwise collide on the (chart_date, chart_type) upsert key).
    """

    def __init__(self, entries, chart_date_offset=0):
        self._entries = entries
        self._offset = chart_date_offset
        self._saved = {}

    def __enter__(self):
        from datetime import timedelta

        d = date(2020, 1, 1) + timedelta(days=self._offset)
        self._saved["parse"] = loader.parse_chart_file
        self._saved["list"] = loader.list_chart_files
        self._saved["ev"] = loader.execute_values
        loader.parse_chart_file = lambda path: list(self._entries)
        loader.list_chart_files = lambda directory: [
            (d, f"/fake/{d.isoformat()}.json")
        ]
        loader.execute_values = _fake_execute_values
        return self

    def __exit__(self, *exc):
        loader.parse_chart_file = self._saved["parse"]
        loader.list_chart_files = self._saved["list"]
        loader.execute_values = self._saved["ev"]
        return False


def _load(db, chart, entries, chart_date_offset=0):
    conn = FakeConn(db)
    with _LoaderHarness(entries, chart_date_offset=chart_date_offset):
        loader.load_chart(conn, chart)
    return conn


# ============================================================================
# Tests
# ============================================================================
class LoadChartDualWriteTests(unittest.TestCase):
    def _base_db(self):
        return FakeDB(
            charts=[
                {"id": 1, "slug": "hot-100", "entity_kind": "song"},
                {"id": 2, "slug": "billboard-200", "entity_kind": "album"},
                {"id": 3, "slug": "country-songs", "entity_kind": "song"},
            ]
        )

    def test_hot100_dual_writes_chart_entries_and_hot100_entries(self):
        db = self._base_db()
        _load(db, _hot100_record(), _HOT100_ENTRIES)

        hot_ce = [e for e in db.chart_entries if e["chart_id"] == 1]
        # chart_entries written with chart_id=hot-100 and song_id set.
        self.assertEqual(len(hot_ce), len(_HOT100_ENTRIES))
        for e in hot_ce:
            self.assertIsNotNone(e["song_id"])
        # legacy hot100_entries dual-written: same count + same (week, rank).
        self.assertEqual(len(db.hot100_entries), len(hot_ce))
        ce_keys = {(e["chart_week_id"], e["rank"]) for e in hot_ce}
        legacy_keys = {(e["chart_week_id"], e["rank"]) for e in db.hot100_entries}
        self.assertEqual(ce_keys, legacy_keys)
        # same song_id per (week, rank)
        ce_song = {(e["chart_week_id"], e["rank"]): e["song_id"] for e in hot_ce}
        legacy_song = {
            (e["chart_week_id"], e["rank"]): e["song_id"]
            for e in db.hot100_entries
        }
        self.assertEqual(ce_song, legacy_song)
        # no b200 rows
        self.assertEqual(db.b200_entries, [])

    def test_billboard200_dual_writes_chart_entries_and_b200_entries(self):
        db = self._base_db()
        _load(db, _b200_record(), _B200_ENTRIES)

        b200_ce = [e for e in db.chart_entries if e["chart_id"] == 2]
        self.assertEqual(len(b200_ce), len(_B200_ENTRIES))
        for e in b200_ce:
            self.assertIsNotNone(e["album_id"])
        self.assertEqual(len(db.b200_entries), len(b200_ce))
        ce_keys = {(e["chart_week_id"], e["rank"], e["album_id"]) for e in b200_ce}
        legacy_keys = {
            (e["chart_week_id"], e["rank"], e["album_id"])
            for e in db.b200_entries
        }
        self.assertEqual(ce_keys, legacy_keys)
        self.assertEqual(db.hot100_entries, [])

    def test_new_chart_writes_chart_entries_only_no_legacy(self):
        db = self._base_db()
        _load(db, _new_chart_record(), _NEW_CHART_ENTRIES)

        new_ce = [e for e in db.chart_entries if e["chart_id"] == 3]
        self.assertEqual(len(new_ce), len(_NEW_CHART_ENTRIES))
        for e in new_ce:
            self.assertIsNotNone(e["song_id"])
        # ZERO legacy rows for a new chart.
        self.assertEqual(db.hot100_entries, [])
        self.assertEqual(db.b200_entries, [])

    def test_new_chart_reload_is_idempotent_no_duplicate_weeks_or_entries(self):
        # CR-01: re-loading the SAME new-chart (legacy_table=None) week must NOT
        # duplicate chart_weeks or chart_entries. The new-chart week insert keys
        # on (chart_id, chart_date) via the partial unique index, so the second
        # load conflict-resolves to the existing week id and the chart_entries
        # ON CONFLICT (chart_week_id, rank) then skips the duplicate rows. Using
        # the SAME chart_date_offset on both passes targets the SAME week.
        db = self._base_db()
        chart = _new_chart_record()  # entity_kind="song", legacy_table=None
        _load(db, chart, _NEW_CHART_ENTRIES, chart_date_offset=0)
        _load(db, chart, _NEW_CHART_ENTRIES, chart_date_offset=0)

        # Exactly ONE chart_weeks row for the new chart (no duplicate week).
        new_weeks = [w for w in db.chart_weeks if w["chart_id"] == 3]
        self.assertEqual(len(new_weeks), 1)
        self.assertIsNone(new_weeks[0]["chart_type"])  # new chart -> no chart_type

        # chart_entries not duplicated: still exactly one row per fixture entry.
        new_ce = [e for e in db.chart_entries if e["chart_id"] == 3]
        self.assertEqual(len(new_ce), len(_NEW_CHART_ENTRIES))
        # And still zero legacy rows.
        self.assertEqual(db.hot100_entries, [])
        self.assertEqual(db.b200_entries, [])

    def test_new_artist_chart_reload_is_idempotent(self):
        # CR-01, artist-entity path: exercise the genuinely new-chart (artist)
        # branch (entity_kind="artist", legacy_table=None) and prove re-loading
        # the same week stays idempotent end-to-end through the artist resolve +
        # chart_entries.artist_id path.
        db = FakeDB(
            charts=[{"id": 7, "slug": "artist-100", "entity_kind": "artist"}]
        )
        chart = ChartRecord(
            slug="artist-100", entity_kind="artist", folder="/fake/artist-100",
            last_loaded_date=None, legacy_table=None,
        )
        entries = [
            {"rank": 1, "title": "", "artist": "Artist Solo", "peak_pos": 1,
             "last_pos": None, "weeks": 1, "is_new": True, "image": None},
        ]
        _load(db, chart, entries, chart_date_offset=0)
        _load(db, chart, entries, chart_date_offset=0)

        weeks = [w for w in db.chart_weeks if w["chart_id"] == 7]
        self.assertEqual(len(weeks), 1)
        artist_ce = [e for e in db.chart_entries if e["chart_id"] == 7]
        self.assertEqual(len(artist_ce), len(entries))
        for e in artist_ce:
            self.assertIsNotNone(e["artist_id"])
            self.assertIsNone(e["song_id"])
            self.assertIsNone(e["album_id"])

    def test_chart_weeks_chart_id_set_on_load(self):
        db = self._base_db()
        _load(db, _hot100_record(), _HOT100_ENTRIES)
        self.assertTrue(db.chart_weeks)
        for w in db.chart_weeks:
            self.assertEqual(w["chart_id"], 1)        # hot-100 registry id
            self.assertEqual(w["chart_type"], "hot-100")  # legacy key preserved

    def test_every_chart_entry_sets_exactly_one_entity_fk(self):
        db = self._base_db()
        _load(db, _hot100_record(), _HOT100_ENTRIES)
        _load(db, _b200_record(), _B200_ENTRIES)
        _load(db, _new_chart_record(), _NEW_CHART_ENTRIES)
        for e in db.chart_entries:
            nonnull = sum(
                1 for k in ("song_id", "album_id", "artist_id")
                if e[k] is not None
            )
            self.assertEqual(nonnull, 1, f"row {e} must set exactly one entity FK")

    def test_entity_kind_dispatch_links_artists(self):
        db = self._base_db()
        _load(db, _hot100_record(), _HOT100_ENTRIES)
        # Song B credits "Artist Two Featuring Artist One" -> two song_artists
        # links (primary + featured). Artist One already linked via Song A.
        names = {a["name"] for a in db.artists}
        self.assertIn("Artist One", names)
        self.assertIn("Artist Two", names)
        # song_artists has links for both songs.
        self.assertTrue(db.song_artists)


class RunEtlRegistryTests(unittest.TestCase):
    def test_run_etl_loops_registry_and_builds_both_stats(self):
        """run_etl must iterate iter_charts and call load_chart per chart, then
        build_all_stats -- never the hardcoded _load_hot100/_load_b200 dispatch.
        Verified at the source level (no real DB)."""
        import inspect

        src = inspect.getsource(loader.run_etl)
        self.assertIn("iter_charts", src)
        self.assertIn("load_chart", src)
        self.assertIn("build_all_stats", src)
        # The two hardcoded dispatch calls are gone from run_etl.
        self.assertNotIn("_load_hot100(", src)
        self.assertNotIn("_load_b200(", src)


if __name__ == "__main__":
    unittest.main()
