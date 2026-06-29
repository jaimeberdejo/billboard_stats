"""Fixture/mock-DB tests for the registry-driven loader (Plan 10-02, DATA-06).

These tests run entirely against an in-memory fake DB layer mirroring
tests/test_migrate_multichart.py and tests/test_stats_builder_parametric.py.
They make NO real database connection and NO network calls. The real-DB full
2-chart run parity is the operator runbook in Plan 03, not here.

What these tests pin down (success criteria #1, #2):

* ``load_chart(conn, chart, ...)`` is ONE entity_kind-dispatched loader that
  replaces ``_load_hot100`` / ``_load_b200``. song -> songs/song_artists +
  chart_entries.song_id; album -> albums/album_artists + chart_entries.album_id.
* SINGLE STORE (Phase 15): every chart — original or new — writes the polymorphic
  ``chart_entries`` row as the SOLE entry store. The v1.0 per-chart entry tables
  have been retired, so there is no dual-write.
* ``chart_weeks`` carries ``chart_id`` (the registry id) and is deduped on the
  full ``UNIQUE(chart_id, chart_date)``; the phantom CTE resolves on chart_id.
* Every ``chart_entries`` row sets EXACTLY ONE of song_id/album_id/artist_id.

The loader is driven over a parsed-entry fixture by stubbing ``parse_chart_file``
and ``list_chart_files`` so the loader exercises the REAL per-entry path (entity
upsert, artist links, single-store write) with no on-disk JSON.
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
    album_artists / chart_entries as plain Python structures and executes the
    exact statement shapes load_chart uses, including the execute_values batch
    INSERT (driven through the module-level ``execute_values`` shim in this test).
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

        # --- chart_weeks upsert (single store: chart_id only) ------------------
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

    Interprets the single batch INSERT shape load_chart emits -- INTO
    chart_entries (the SOLE entry store as of Phase 15) -- and applies it to the
    fake DB with ON CONFLICT (chart_week_id, rank) DO NOTHING semantics.
    """
    db = cur._db
    norm = re.sub(r"\s+", " ", sql).strip().lower()

    if norm.startswith("insert into chart_entries"):
        db.insert_chart_entries(rows)
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
        self._next = {
            "artist": (max((a["id"] for a in self.artists), default=0)) + 1,
            "song": 1,
            "album": 1,
            "week": 1,
            "ce": 1,
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
        conflict key (CR-01). As of Phase 15 there is ONE week-insert shape for
        every chart -- ``(chart_date, chart_id)`` ON CONFLICT on the full
        ``UNIQUE(chart_id, chart_date)`` -- so the dedup key is (chart_id,
        chart_date) and re-loading the same week conflict-resolves to the
        existing week id instead of inserting a duplicate.
        """
        chart_date, chart_id = params
        for w in self.chart_weeks:
            if w["chart_id"] == chart_id and w["chart_date"] == chart_date:
                w["chart_id"] = chart_id  # SET chart_id = EXCLUDED.chart_id
                return w["id"]

        wid = self._take("week")
        self.chart_weeks.append(
            {
                "id": wid,
                "chart_date": chart_date,
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
        last_loaded_date=None,
    )


def _b200_record():
    return ChartRecord(
        slug="billboard-200", entity_kind="album", folder="/fake/b200",
        last_loaded_date=None,
    )


def _new_chart_record():
    return ChartRecord(
        slug="country-songs", entity_kind="song", folder="/fake/country-songs",
        last_loaded_date=None,
    )


class _LoaderHarness:
    """Patch the loader's parse_chart_file/list_chart_files/execute_values so
    load_chart runs over an in-memory parsed-entry fixture.

    ``chart_date_offset`` shifts the single stubbed week file's date so multiple
    ``_load`` passes for the SAME chart produce DISTINCT chart_weeks (they would
    otherwise collide on the (chart_id, chart_date) upsert key).
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
        # Accept and ignore the entity_kind kwarg load_chart now passes
        # (parse_chart_file(file_path, entity_kind=chart.entity_kind), Plan 11-01)
        # so every stubbed _load(...) call site keeps returning the fixture list.
        loader.parse_chart_file = lambda path, entity_kind=None: list(self._entries)
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

    def test_hot100_writes_chart_entries_single_store(self):
        db = self._base_db()
        _load(db, _hot100_record(), _HOT100_ENTRIES)

        hot_ce = [e for e in db.chart_entries if e["chart_id"] == 1]
        # chart_entries written with chart_id=hot-100 and song_id set — the SOLE
        # entry store (no dual-write to a retired legacy table).
        self.assertEqual(len(hot_ce), len(_HOT100_ENTRIES))
        for e in hot_ce:
            self.assertIsNotNone(e["song_id"])
        # one chart_entries row per fixture entry, keyed on (week, rank).
        ce_keys = {(e["chart_week_id"], e["rank"]) for e in hot_ce}
        self.assertEqual(len(ce_keys), len(_HOT100_ENTRIES))

    def test_billboard200_writes_chart_entries_single_store(self):
        db = self._base_db()
        _load(db, _b200_record(), _B200_ENTRIES)

        b200_ce = [e for e in db.chart_entries if e["chart_id"] == 2]
        self.assertEqual(len(b200_ce), len(_B200_ENTRIES))
        for e in b200_ce:
            self.assertIsNotNone(e["album_id"])
        ce_keys = {(e["chart_week_id"], e["rank"], e["album_id"]) for e in b200_ce}
        self.assertEqual(len(ce_keys), len(_B200_ENTRIES))

    def test_new_chart_writes_chart_entries(self):
        db = self._base_db()
        _load(db, _new_chart_record(), _NEW_CHART_ENTRIES)

        new_ce = [e for e in db.chart_entries if e["chart_id"] == 3]
        self.assertEqual(len(new_ce), len(_NEW_CHART_ENTRIES))
        for e in new_ce:
            self.assertIsNotNone(e["song_id"])

    def test_chart_reload_is_idempotent_no_duplicate_weeks_or_entries(self):
        # CR-01: re-loading the SAME week must NOT duplicate chart_weeks or
        # chart_entries. The week insert keys on the full UNIQUE(chart_id,
        # chart_date), so the second load conflict-resolves to the existing week
        # id and the chart_entries ON CONFLICT (chart_week_id, rank) then skips
        # the duplicate rows. Using the SAME chart_date_offset on both passes
        # targets the SAME week.
        db = self._base_db()
        chart = _new_chart_record()
        _load(db, chart, _NEW_CHART_ENTRIES, chart_date_offset=0)
        _load(db, chart, _NEW_CHART_ENTRIES, chart_date_offset=0)

        # Exactly ONE chart_weeks row for the chart (no duplicate week).
        new_weeks = [w for w in db.chart_weeks if w["chart_id"] == 3]
        self.assertEqual(len(new_weeks), 1)

        # chart_entries not duplicated: still exactly one row per fixture entry.
        new_ce = [e for e in db.chart_entries if e["chart_id"] == 3]
        self.assertEqual(len(new_ce), len(_NEW_CHART_ENTRIES))

    def test_artist_chart_reload_is_idempotent(self):
        # CR-01, artist-entity path: exercise the artist-entity branch
        # (entity_kind="artist") and prove re-loading the same week stays
        # idempotent end-to-end through the artist resolve + chart_entries.
        # artist_id path.
        db = FakeDB(
            charts=[{"id": 7, "slug": "artist-100", "entity_kind": "artist"}]
        )
        chart = ChartRecord(
            slug="artist-100", entity_kind="artist", folder="/fake/artist-100",
            last_loaded_date=None,
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

    def test_unregistered_slug_fails_fast_before_writing_rows(self):
        # WR-03: a slug missing from the charts registry must raise a clear error
        # BEFORE any chart_entries are written, not a mid-batch NOT NULL/FK
        # violation. chart_entries.chart_id is NOT NULL.
        db = self._base_db()  # has hot-100 / billboard-200 / country-songs only
        ghost = ChartRecord(
            slug="not-a-real-chart", entity_kind="song",
            folder="/fake/ghost", last_loaded_date=None,
        )
        with self.assertRaises(ValueError) as ctx:
            _load(db, ghost, _HOT100_ENTRIES)
        self.assertIn("not-a-real-chart", str(ctx.exception))
        # No rows leaked before the guard fired.
        self.assertEqual(db.chart_entries, [])
        self.assertEqual(db.chart_weeks, [])

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
