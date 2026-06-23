"""Fixture/mock-DB tests for the artist reconciliation migration (Plan 08-02).

These tests run entirely against an in-memory fake DB layer mirroring the repo's
unittest + unittest.mock pattern (see tests/test_charts.py,
tests/test_backfill_guardrail.py). They make NO real database connection and NO
network calls. The real-DB validation (dry-run -> pg_dump snapshot -> apply ->
rebuild stats -> verify) is carried by docs/RECONCILIATION.md as operator steps.

The alias-module cases live under names matching ``-k alias`` so Task 1's verify
(`pytest -k alias`) selects them.
"""

import copy
import re
import unittest

from billboard_stats.etl import artist_aliases
from billboard_stats.etl import reconcile_artists
from billboard_stats.etl.reconcile_artists import (
    ReconciliationInvariantError,
    reconcile,
)


# ============================================================================
# In-memory fake DB layer
# ============================================================================
class FakeCursor:
    """A psycopg2-cursor-like stand-in that interprets the SQL reconcile emits.

    It models four tables as plain Python structures and executes the exact
    statement shapes reconcile_artists.py uses (a SELECT of artists, four COUNT
    queries, and per-table INSERT...SELECT...ON CONFLICT DO NOTHING / DELETE...
    ANY(...) pairs). No real database is involved.
    """

    def __init__(self, db):
        self._db = db
        self._result = None

    # Context-manager protocol (mirrors `with conn.cursor() as cur:`).
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        norm = re.sub(r"\s+", " ", sql).strip().lower()
        params = params or ()

        if norm.startswith("select id, name from artists"):
            self._result = [(a["id"], a["name"]) for a in self._db.artists]
            return

        if norm.startswith("select count(distinct song_id) from song_artists"):
            self._result = [(len({l["song_id"] for l in self._db.song_artists}),)]
            return

        if norm.startswith("select count(distinct album_id) from album_artists"):
            self._result = [(len({l["album_id"] for l in self._db.album_artists}),)]
            return

        if norm.startswith("select count(*) from song_artists"):
            self._result = [(len(self._db.song_artists),)]
            return

        if norm.startswith("select count(*) from album_artists"):
            self._result = [(len(self._db.album_artists),)]
            return

        if norm.startswith("insert into song_artists"):
            canonical_id, fragment_ids = params
            self._db.insert_links(
                "song_artists", "song_id", canonical_id, set(fragment_ids)
            )
            return

        if norm.startswith("delete from song_artists where artist_id = any"):
            (fragment_ids,) = params
            self._db.delete_links("song_artists", set(fragment_ids))
            return

        if norm.startswith("insert into album_artists"):
            canonical_id, fragment_ids = params
            self._db.insert_links(
                "album_artists", "album_id", canonical_id, set(fragment_ids)
            )
            return

        if norm.startswith("delete from album_artists where artist_id = any"):
            (fragment_ids,) = params
            self._db.delete_links("album_artists", set(fragment_ids))
            return

        if norm.startswith("delete from artist_stats where artist_id = any"):
            (fragment_ids,) = params
            self._db.artist_stats = [
                s for s in self._db.artist_stats if s not in set(fragment_ids)
            ]
            return

        if norm.startswith("delete from artists where id = any"):
            (fragment_ids,) = params
            self._db.artists = [
                a for a in self._db.artists if a["id"] not in set(fragment_ids)
            ]
            return

        raise AssertionError(f"FakeCursor: unhandled SQL: {norm!r}")

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0]


class FakeConn:
    """A connection-like stand-in tracking commit/rollback and snapshotting state."""

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
    """In-memory model of artists / song_artists / album_artists / artist_stats."""

    def __init__(self, artists, song_artists=None, album_artists=None, artist_stats=None):
        # artists: list of {"id": int, "name": str}
        self.artists = [dict(a) for a in artists]
        # *_artists: list of {"song_id"/"album_id": int, "artist_id": int, "role": str}
        self.song_artists = [dict(l) for l in (song_artists or [])]
        self.album_artists = [dict(l) for l in (album_artists or [])]
        # artist_stats: list of artist_id ints (one row per artist)
        self.artist_stats = list(artist_stats or [])

    def insert_links(self, table, key, canonical_id, fragment_ids):
        """INSERT...SELECT...ON CONFLICT DO NOTHING: add canonical link per entity."""
        links = getattr(self, table)
        existing = {(l[key], l["artist_id"]) for l in links}
        # The entities touched by any fragment.
        for link in list(links):
            if link["artist_id"] in fragment_ids:
                entity = link[key]
                if (entity, canonical_id) not in existing:
                    links.append({key: entity, "artist_id": canonical_id, "role": link["role"]})
                    existing.add((entity, canonical_id))

    def delete_links(self, table, fragment_ids):
        links = getattr(self, table)
        setattr(
            self,
            table,
            [l for l in links if l["artist_id"] not in fragment_ids],
        )

    def snapshot(self):
        return copy.deepcopy(
            {
                "artists": self.artists,
                "song_artists": self.song_artists,
                "album_artists": self.album_artists,
                "artist_stats": self.artist_stats,
            }
        )

    def restore(self, snap):
        snap = copy.deepcopy(snap)
        self.artists = snap["artists"]
        self.song_artists = snap["song_artists"]
        self.album_artists = snap["album_artists"]
        self.artist_stats = snap["artist_stats"]

    def artist_id(self, name):
        for a in self.artists:
            if a["name"] == name:
                return a["id"]
        return None


def _ewf_fixture():
    """Earth, Wind & Fire fixture: canonical + three fragments with links.

    - artist 1 = "Earth, Wind & Fire" (canonical), 2="Earth", 3="Wind", 4="Fire"
    - song 100 links all three fragments (the classic shatter)
    - song 101 links only "Earth"
    - album 200 links "Wind"
    - a couple of unrelated artists/links to prove invariants stay put
    """
    artists = [
        {"id": 1, "name": "Earth, Wind & Fire"},
        {"id": 2, "name": "Earth"},
        {"id": 3, "name": "Wind"},
        {"id": 4, "name": "Fire"},
        {"id": 5, "name": "Drake"},
    ]
    song_artists = [
        {"song_id": 100, "artist_id": 2, "role": "primary"},
        {"song_id": 100, "artist_id": 3, "role": "primary"},
        {"song_id": 100, "artist_id": 4, "role": "primary"},
        {"song_id": 101, "artist_id": 2, "role": "primary"},
        {"song_id": 102, "artist_id": 5, "role": "primary"},
    ]
    album_artists = [
        {"album_id": 200, "artist_id": 3, "role": "primary"},
        {"album_id": 201, "artist_id": 5, "role": "primary"},
    ]
    artist_stats = [1, 2, 3, 4, 5]
    return FakeDB(artists, song_artists, album_artists, artist_stats)


# ----------------------------------------------------------------------------
# Task 1: ETL genuine-alias map (moved from src/lib/artist-identity.ts)
# ----------------------------------------------------------------------------
class AliasModuleTests(unittest.TestCase):
    def test_alias_janet_resolves_to_canonical(self):
        self.assertEqual(artist_aliases.canonicalize("Janet"), "Janet Jackson")

    def test_alias_kesha_dollar_resolves_to_canonical(self):
        self.assertEqual(artist_aliases.canonicalize("Ke$ha"), "Kesha")

    def test_alias_unknown_name_unchanged(self):
        self.assertEqual(artist_aliases.canonicalize("Drake"), "Drake")

    def test_alias_lookup_is_case_insensitive(self):
        self.assertEqual(artist_aliases.canonicalize("janet"), "Janet Jackson")
        self.assertEqual(artist_aliases.canonicalize("KE$HA"), "Kesha")

    def test_alias_lookup_is_whitespace_normalized(self):
        self.assertEqual(artist_aliases.canonicalize("  Janet  "), "Janet Jackson")

    def test_alias_is_deterministic(self):
        first = artist_aliases.canonicalize("Janet")
        second = artist_aliases.canonicalize("Janet")
        self.assertEqual(first, second)

    def test_canonical_name_itself_is_stable(self):
        # Passing the canonical name returns the same canonical name.
        self.assertEqual(artist_aliases.canonicalize("Janet Jackson"), "Janet Jackson")
        self.assertEqual(artist_aliases.canonicalize("Kesha"), "Kesha")

    def test_genuine_alias_set_contains_aliases_not_fragments(self):
        genuine = artist_aliases.genuine_alias_names()
        # Genuine alternate spellings survive reconciliation.
        self.assertIn("janet", genuine)
        self.assertIn("ke$ha", genuine)
        # Split fragments are NOT genuine aliases — they are healed by
        # reconciliation, so they must never appear in the genuine-alias set.
        self.assertNotIn("earth", genuine)
        self.assertNotIn("wind", genuine)
        self.assertNotIn("fire", genuine)

    def test_earth_wind_fire_pieces_are_not_genuine_aliases(self):
        # canonicalize must NOT collapse a split fragment to the group name —
        # that healing is reconciliation's job, not the alias map's.
        self.assertEqual(artist_aliases.canonicalize("Earth"), "Earth")
        self.assertEqual(artist_aliases.canonicalize("Wind"), "Wind")
        self.assertEqual(artist_aliases.canonicalize("Fire"), "Fire")

    def test_is_genuine_alias_helper(self):
        self.assertTrue(artist_aliases.is_genuine_alias("Janet"))
        self.assertTrue(artist_aliases.is_genuine_alias("janet jackson"))
        self.assertFalse(artist_aliases.is_genuine_alias("Earth"))
        self.assertFalse(artist_aliases.is_genuine_alias("Drake"))


# ----------------------------------------------------------------------------
# Task 2/3: reconciliation behavior against the fixture DB
# ----------------------------------------------------------------------------
class ReconcileMergeTests(unittest.TestCase):
    def test_fragments_merge_into_canonical(self):
        db = _ewf_fixture()
        conn = FakeConn(db)

        report = reconcile(conn, dry_run=False)

        # The three fragment artist rows are deleted; canonical + Drake remain.
        names = {a["name"] for a in db.artists}
        self.assertEqual(names, {"Earth, Wind & Fire", "Drake"})
        self.assertIsNone(db.artist_id("Earth"))
        self.assertIsNone(db.artist_id("Wind"))
        self.assertIsNone(db.artist_id("Fire"))

        # song 100 now links the canonical artist exactly once.
        s100 = [l for l in db.song_artists if l["song_id"] == 100]
        self.assertEqual(len(s100), 1)
        self.assertEqual(s100[0]["artist_id"], 1)

        # song 101 (only "Earth") is repointed to the canonical artist.
        s101 = [l for l in db.song_artists if l["song_id"] == 101]
        self.assertEqual([l["artist_id"] for l in s101], [1])

        # album 200 ("Wind") is repointed to the canonical artist.
        a200 = [l for l in db.album_artists if l["album_id"] == 200]
        self.assertEqual([l["artist_id"] for l in a200], [1])

        self.assertEqual(report["merged_fragments"], 3)
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)

    def test_dedupe_yields_one_link_via_on_conflict(self):
        # song 100 had three fragment links; collapsing onto one canonical id
        # must leave exactly ONE link (proving ON CONFLICT DO NOTHING dedupe).
        db = _ewf_fixture()
        before_links = len(db.song_artists) + len(db.album_artists)
        conn = FakeConn(db)

        reconcile(conn, dry_run=False)

        after_links = len(db.song_artists) + len(db.album_artists)
        # 3 EWF song links on song 100 collapse to 1 (net -2); the standalone
        # "Earth" on 101 and "Wind" on 200 repoint with no change in count.
        self.assertEqual(after_links, before_links - 2)

    def test_fragment_stats_rows_deleted(self):
        db = _ewf_fixture()
        conn = FakeConn(db)
        reconcile(conn, dry_run=False)
        # Fragment artist_stats rows (2,3,4) are gone; canonical (1) and 5 stay.
        self.assertEqual(sorted(db.artist_stats), [1, 5])

    def test_no_song_or_album_loses_all_artists(self):
        db = _ewf_fixture()
        conn = FakeConn(db)
        reconcile(conn, dry_run=False)
        songs = {l["song_id"] for l in db.song_artists}
        albums = {l["album_id"] for l in db.album_artists}
        self.assertEqual(songs, {100, 101, 102})
        self.assertEqual(albums, {200, 201})


class ReconcileInvariantTests(unittest.TestCase):
    def test_distinct_song_and_album_counts_unchanged(self):
        db = _ewf_fixture()
        before_songs = len({l["song_id"] for l in db.song_artists})
        before_albums = len({l["album_id"] for l in db.album_artists})
        conn = FakeConn(db)

        reconcile(conn, dry_run=False)

        after_songs = len({l["song_id"] for l in db.song_artists})
        after_albums = len({l["album_id"] for l in db.album_artists})
        self.assertEqual(after_songs, before_songs)
        self.assertEqual(after_albums, before_albums)

    def test_total_links_only_decrease(self):
        db = _ewf_fixture()
        before = len(db.song_artists) + len(db.album_artists)
        conn = FakeConn(db)
        reconcile(conn, dry_run=False)
        after = len(db.song_artists) + len(db.album_artists)
        self.assertLessEqual(after, before)


class ReconcileIdempotencyTests(unittest.TestCase):
    def test_second_run_is_noop(self):
        db = _ewf_fixture()
        reconcile(FakeConn(db), dry_run=False)
        snapshot_after_first = db.snapshot()

        second = FakeConn(db)
        report = reconcile(second, dry_run=False)

        self.assertEqual(report["merged_fragments"], 0)
        self.assertEqual(report["clusters"], [])
        # State is byte-for-byte identical after the second run.
        self.assertEqual(db.snapshot(), snapshot_after_first)


class ReconcileDryRunTests(unittest.TestCase):
    def test_dry_run_reports_but_writes_nothing(self):
        db = _ewf_fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        report = reconcile(conn, dry_run=True)

        self.assertTrue(report["dry_run"])
        self.assertEqual(report["merged_fragments"], 3)
        self.assertEqual(len(report["clusters"]), 1)
        self.assertEqual(report["clusters"][0]["canonical_name"], "Earth, Wind & Fire")
        # Nothing was written and nothing was committed.
        self.assertEqual(db.snapshot(), before)
        self.assertFalse(conn.committed)


class ReconcileGenuineAliasTests(unittest.TestCase):
    def test_genuine_alias_row_not_deleted_as_fragment(self):
        # "Janet" is a genuine alias of "Janet Jackson", and "Ke$ha" of "Kesha".
        # Even alongside an EWF merge, neither genuine-alias row is deleted.
        artists = [
            {"id": 1, "name": "Earth, Wind & Fire"},
            {"id": 2, "name": "Earth"},
            {"id": 3, "name": "Wind"},
            {"id": 4, "name": "Fire"},
            {"id": 5, "name": "Janet"},
            {"id": 6, "name": "Ke$ha"},
        ]
        song_artists = [
            {"song_id": 100, "artist_id": 2, "role": "primary"},
            {"song_id": 100, "artist_id": 3, "role": "primary"},
            {"song_id": 100, "artist_id": 4, "role": "primary"},
            {"song_id": 101, "artist_id": 5, "role": "primary"},
            {"song_id": 102, "artist_id": 6, "role": "primary"},
        ]
        db = FakeDB(artists, song_artists, [], [1, 2, 3, 4, 5, 6])
        reconcile(FakeConn(db), dry_run=False)

        # Genuine-alias rows survive.
        self.assertIsNotNone(db.artist_id("Janet"))
        self.assertIsNotNone(db.artist_id("Ke$ha"))
        # The EWF fragments were still healed.
        self.assertIsNone(db.artist_id("Earth"))


class ReconcileRollbackTests(unittest.TestCase):
    def test_invariant_violation_rolls_back_and_raises(self):
        # Force an invariant breach by making _capture_counts report a dropped
        # distinct-song count after the merge, simulating a song losing all
        # artists. The run must roll back (restore state) and raise.
        db = _ewf_fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        original = reconcile_artists._capture_counts
        calls = {"n": 0}

        def fake_counts(cur):
            counts = original(cur)
            calls["n"] += 1
            if calls["n"] == 2:  # the AFTER snapshot
                counts["distinct_songs"] -= 1
            return counts

        reconcile_artists._capture_counts = fake_counts
        try:
            with self.assertRaises(ReconciliationInvariantError):
                reconcile(conn, dry_run=False)
        finally:
            reconcile_artists._capture_counts = original

        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)
        # State restored to its pre-run snapshot.
        self.assertEqual(db.snapshot(), before)


class ReconcilePostgresFreeTests(unittest.TestCase):
    def test_module_has_no_top_level_psycopg_import(self):
        import inspect

        src = inspect.getsource(reconcile_artists)
        # psycopg2 must only be imported lazily inside the operator CLI path,
        # never at module top level, so the module imports in the mock env.
        lines = src.splitlines()
        top_level = [
            l for l in lines if l.startswith("import ") or l.startswith("from ")
        ]
        self.assertFalse(
            any("psycopg" in l for l in top_level),
            "psycopg2 must not be a top-level import",
        )


if __name__ == "__main__":
    unittest.main()
