"""Fixture/mock-DB tests for the artist reconciliation migration (Plan 08-02).

These tests run entirely against an in-memory fake DB layer mirroring the repo's
unittest + unittest.mock pattern (see tests/test_charts.py,
tests/test_backfill_guardrail.py). They make NO real database connection and NO
network calls. The real-DB validation (dry-run -> pg_dump snapshot -> apply ->
rebuild stats -> verify) is carried by docs/RECONCILIATION.md as operator steps.

Reconciliation is now DRIVEN BY RE-PARSING THE STORED CREDITS, so the fake DB
models ``songs`` and ``albums`` (each with an ``artist_credit``) alongside the
join tables. The reconcile path re-parses each credit with the NEW parser and
reconciles links to that target, deleting an artist only when it ends up with
ZERO links. This is what protects solo members of real acts (Diana Ross, Tina
Turner, Tyler) while still healing pure shatter fragments (Earth/Wind/Fire).

Fidelity gaps the fake DB does NOT model (covered by the operator runbook, not
here): real PostgreSQL ``role`` arbitration on ON CONFLICT (the reconcile now
sets role deterministically from the parse, so this is moot, but the runbook
still asserts post-merge roles); FK ordering between link deletes and artist
deletes; and dangling-link detection after apply. See WR-02/WR-04 in 08-REVIEW.

The alias-module cases live under names matching ``-k alias`` so Task 1's verify
(`pytest -k alias`) selects them.
"""

import copy
import re
import unittest

from billboard_stats.etl import artist_aliases
from billboard_stats.etl import artist_parser
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

    It models artists / songs / albums / song_artists / album_artists /
    artist_stats as plain Python structures and executes the exact statement
    shapes reconcile_artists.py uses. No real database is involved.
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

        if norm.startswith("select song_id, artist_id from song_artists"):
            self._result = [
                (l["song_id"], l["artist_id"]) for l in self._db.song_artists
            ]
            return

        if norm.startswith("select album_id, artist_id from album_artists"):
            self._result = [
                (l["album_id"], l["artist_id"]) for l in self._db.album_artists
            ]
            return

        if norm.startswith("select id, artist_credit from songs"):
            self._result = [(s["id"], s["artist_credit"]) for s in self._db.songs]
            return

        if norm.startswith("select id, artist_credit from albums"):
            self._result = [(a["id"], a["artist_credit"]) for a in self._db.albums]
            return

        if norm.startswith("select distinct song_id from song_artists"):
            self._result = [
                (sid,) for sid in {l["song_id"] for l in self._db.song_artists}
            ]
            return

        if norm.startswith("select distinct album_id from album_artists"):
            self._result = [
                (aid,) for aid in {l["album_id"] for l in self._db.album_artists}
            ]
            return

        if norm.startswith("select count(*) from song_artists"):
            self._result = [(len(self._db.song_artists),)]
            return

        if norm.startswith("select count(*) from album_artists"):
            self._result = [(len(self._db.album_artists),)]
            return

        if norm.startswith("insert into artists"):
            (name,) = params
            self._result = [(self._db.get_or_create_artist(name),)]
            return

        if norm.startswith("insert into song_artists"):
            song_id, artist_id, role = params
            self._db.insert_link("song_artists", "song_id", song_id, artist_id, role)
            return

        if norm.startswith("delete from song_artists where song_id"):
            song_id, artist_id = params
            self._db.delete_link("song_artists", "song_id", song_id, artist_id)
            return

        if norm.startswith("insert into album_artists"):
            album_id, artist_id, role = params
            self._db.insert_link(
                "album_artists", "album_id", album_id, artist_id, role
            )
            return

        if norm.startswith("delete from album_artists where album_id"):
            album_id, artist_id = params
            self._db.delete_link("album_artists", "album_id", album_id, artist_id)
            return

        if norm.startswith("delete from artist_stats where artist_id = any"):
            (artist_ids,) = params
            self._db.artist_stats = [
                s for s in self._db.artist_stats if s not in set(artist_ids)
            ]
            return

        if norm.startswith("delete from artists where id = any"):
            (artist_ids,) = params
            self._db.artists = [
                a for a in self._db.artists if a["id"] not in set(artist_ids)
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
    """In-memory model of artists / songs / albums / *_artists / artist_stats."""

    def __init__(
        self,
        artists,
        songs=None,
        albums=None,
        song_artists=None,
        album_artists=None,
        artist_stats=None,
    ):
        # artists: list of {"id": int, "name": str}
        self.artists = [dict(a) for a in artists]
        # songs/albums: list of {"id": int, "artist_credit": str}
        self.songs = [dict(s) for s in (songs or [])]
        self.albums = [dict(a) for a in (albums or [])]
        # *_artists: list of {"song_id"/"album_id": int, "artist_id": int, "role": str}
        self.song_artists = [dict(l) for l in (song_artists or [])]
        self.album_artists = [dict(l) for l in (album_artists or [])]
        # artist_stats: list of artist_id ints (one row per artist)
        self.artist_stats = list(artist_stats or [])
        self._next_id = (max((a["id"] for a in self.artists), default=0)) + 1

    def get_or_create_artist(self, name):
        for a in self.artists:
            if a["name"] == name:
                return a["id"]
        new_id = self._next_id
        self._next_id += 1
        self.artists.append({"id": new_id, "name": name})
        return new_id

    def insert_link(self, table, key, entity_id, artist_id, role):
        """INSERT ... ON CONFLICT (entity, artist) DO NOTHING."""
        links = getattr(self, table)
        for l in links:
            if l[key] == entity_id and l["artist_id"] == artist_id:
                return  # conflict -> do nothing
        links.append({key: entity_id, "artist_id": artist_id, "role": role})

    def delete_link(self, table, key, entity_id, artist_id):
        links = getattr(self, table)
        setattr(
            self,
            table,
            [
                l
                for l in links
                if not (l[key] == entity_id and l["artist_id"] == artist_id)
            ],
        )

    def snapshot(self):
        return copy.deepcopy(
            {
                "artists": self.artists,
                "songs": self.songs,
                "albums": self.albums,
                "song_artists": self.song_artists,
                "album_artists": self.album_artists,
                "artist_stats": self.artist_stats,
            }
        )

    def restore(self, snap):
        snap = copy.deepcopy(snap)
        self.artists = snap["artists"]
        self.songs = snap["songs"]
        self.albums = snap["albums"]
        self.song_artists = snap["song_artists"]
        self.album_artists = snap["album_artists"]
        self.artist_stats = snap["artist_stats"]

    def artist_id(self, name):
        for a in self.artists:
            if a["name"] == name:
                return a["id"]
        return None

    def song_artist_ids(self, song_id):
        return [l["artist_id"] for l in self.song_artists if l["song_id"] == song_id]

    def album_artist_ids(self, album_id):
        return [l["artist_id"] for l in self.album_artists if l["album_id"] == album_id]


def _ewf_fixture():
    """Earth, Wind & Fire fixture: canonical act + three pure shatter fragments.

    The stored credits all say "Earth, Wind & Fire"; the OLD parser shattered
    them into "Earth"/"Wind"/"Fire" links. Re-parsing the credits with the new
    parser produces only the canonical act, so the three fragments end up with
    zero links and are deleted. There is NO standalone "Earth"/"Wind"/"Fire"
    credit, so they are pure fragments.

    - artist 1 = "Earth, Wind & Fire" (canonical), 2="Earth", 3="Wind", 4="Fire"
    - song 100 (credit EWF) links all three fragments (the classic shatter)
    - song 101 (credit EWF) links only "Earth"
    - album 200 (credit EWF) links "Wind"
    - Drake (song 102 / album 201) is an unrelated control.
    """
    artists = [
        {"id": 1, "name": "Earth, Wind & Fire"},
        {"id": 2, "name": "Earth"},
        {"id": 3, "name": "Wind"},
        {"id": 4, "name": "Fire"},
        {"id": 5, "name": "Drake"},
    ]
    songs = [
        {"id": 100, "artist_credit": "Earth, Wind & Fire"},
        {"id": 101, "artist_credit": "Earth, Wind & Fire"},
        {"id": 102, "artist_credit": "Drake"},
    ]
    albums = [
        {"id": 200, "artist_credit": "Earth, Wind & Fire"},
        {"id": 201, "artist_credit": "Drake"},
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
    return FakeDB(artists, songs, albums, song_artists, album_artists, artist_stats)


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

        # The three pure-shatter fragment rows are deleted; canonical + Drake stay.
        names = {a["name"] for a in db.artists}
        self.assertEqual(names, {"Earth, Wind & Fire", "Drake"})
        self.assertIsNone(db.artist_id("Earth"))
        self.assertIsNone(db.artist_id("Wind"))
        self.assertIsNone(db.artist_id("Fire"))

        # song 100 now links the canonical artist exactly once.
        self.assertEqual(db.song_artist_ids(100), [1])
        # song 101 (was "Earth") is repointed to the canonical artist.
        self.assertEqual(db.song_artist_ids(101), [1])
        # album 200 (was "Wind") is repointed to the canonical artist.
        self.assertEqual(db.album_artist_ids(200), [1])

        self.assertEqual(len(report["deleted_artists"]), 3)
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)

    def test_dedupe_yields_one_link(self):
        # song 100 had three fragment links; collapsing onto one canonical id
        # must leave exactly ONE link.
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

    def test_repoint_role_is_deterministic_primary(self):
        # CR-02: the role on the repointed canonical link comes from the parse,
        # not from arbitrary ON CONFLICT arbitration. EWF parses as primary.
        db = _ewf_fixture()
        reconcile(FakeConn(db), dry_run=False)
        for l in db.song_artists:
            if l["song_id"] in (100, 101) and l["artist_id"] == 1:
                self.assertEqual(l["role"], "primary")


class ReconcileInvariantTests(unittest.TestCase):
    def test_distinct_song_and_album_counts_unchanged(self):
        db = _ewf_fixture()
        before_songs = {l["song_id"] for l in db.song_artists}
        before_albums = {l["album_id"] for l in db.album_artists}
        conn = FakeConn(db)

        reconcile(conn, dry_run=False)

        after_songs = {l["song_id"] for l in db.song_artists}
        after_albums = {l["album_id"] for l in db.album_artists}
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

        self.assertEqual(len(report["deleted_artists"]), 0)
        self.assertEqual(report["added_song_links"], 0)
        self.assertEqual(report["removed_song_links"], 0)
        # State is byte-for-byte identical after the second run.
        self.assertEqual(db.snapshot(), snapshot_after_first)


class ReconcileDryRunTests(unittest.TestCase):
    def test_dry_run_reports_but_writes_nothing(self):
        db = _ewf_fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        report = reconcile(conn, dry_run=True)

        self.assertTrue(report["dry_run"])
        self.assertEqual(len(report["deleted_artists"]), 3)
        deleted_names = {d["name"] for d in report["deleted_artists"]}
        self.assertEqual(deleted_names, {"Earth", "Wind", "Fire"})
        # Nothing was written and nothing was committed.
        self.assertEqual(db.snapshot(), before)
        self.assertFalse(conn.committed)


class ReconcileGenuineAliasTests(unittest.TestCase):
    def test_genuine_alias_row_not_deleted_as_fragment(self):
        # "Janet" is a genuine alias of "Janet Jackson", and "Ke$ha" of "Kesha".
        # A credit "Janet" re-parses + canonicalizes to "Janet Jackson", so the
        # link repoints onto Janet Jackson; the bare "Janet" row, if it has no
        # other links, would be deleted (it is now just an alias spelling). Model
        # the canonical rows existing and assert they survive.
        artists = [
            {"id": 1, "name": "Earth, Wind & Fire"},
            {"id": 2, "name": "Earth"},
            {"id": 3, "name": "Wind"},
            {"id": 4, "name": "Fire"},
            {"id": 5, "name": "Janet Jackson"},
            {"id": 6, "name": "Kesha"},
        ]
        songs = [
            {"id": 100, "artist_credit": "Earth, Wind & Fire"},
            {"id": 101, "artist_credit": "Janet Jackson"},
            {"id": 102, "artist_credit": "Kesha"},
        ]
        song_artists = [
            {"song_id": 100, "artist_id": 2, "role": "primary"},
            {"song_id": 100, "artist_id": 3, "role": "primary"},
            {"song_id": 100, "artist_id": 4, "role": "primary"},
            {"song_id": 101, "artist_id": 5, "role": "primary"},
            {"song_id": 102, "artist_id": 6, "role": "primary"},
        ]
        db = FakeDB(artists, songs, [], song_artists, [], [1, 2, 3, 4, 5, 6])
        reconcile(FakeConn(db), dry_run=False)

        # Canonical alias-targets survive (they keep their links).
        self.assertIsNotNone(db.artist_id("Janet Jackson"))
        self.assertIsNotNone(db.artist_id("Kesha"))
        # The EWF fragments were still healed.
        self.assertIsNone(db.artist_id("Earth"))


# ----------------------------------------------------------------------------
# CR-01 regression: real standalone members of acts are NEVER deleted
# ----------------------------------------------------------------------------
class ReconcileMemberArtistSafetyTests(unittest.TestCase):
    def test_diana_ross_solo_survives_alongside_supremes_act(self):
        # "Diana Ross & The Supremes" is a curated act; "Diana Ross" is also a
        # hugely-charting SOLO artist with her own credits. The OLD code split
        # the act name and deleted solo Diana Ross. The new code re-parses
        # credits: the solo "Diana Ross" credit produces the "Diana Ross" artist,
        # so she ALWAYS retains links and is never deleted.
        artists = [
            {"id": 1, "name": "Diana Ross & The Supremes"},
            {"id": 2, "name": "Diana Ross"},
            {"id": 3, "name": "The Supremes"},
        ]
        songs = [
            {"id": 100, "artist_credit": "Diana Ross & The Supremes"},
            {"id": 101, "artist_credit": "Diana Ross"},  # her solo catalog
            {"id": 102, "artist_credit": "Diana Ross"},
        ]
        song_artists = [
            {"song_id": 100, "artist_id": 1, "role": "primary"},
            {"song_id": 101, "artist_id": 2, "role": "primary"},
            {"song_id": 102, "artist_id": 2, "role": "primary"},
        ]
        db = FakeDB(artists, songs, [], song_artists, [], [1, 2, 3])
        reconcile(FakeConn(db), dry_run=False)

        # Solo Diana Ross SURVIVES with her full solo catalog.
        diana = db.artist_id("Diana Ross")
        self.assertIsNotNone(diana)
        self.assertEqual(sorted(db.song_artist_ids(101)), [diana])
        self.assertEqual(sorted(db.song_artist_ids(102)), [diana])
        # The act itself also survives on its own credit.
        self.assertIsNotNone(db.artist_id("Diana Ross & The Supremes"))

    def test_tina_turner_solo_survives_alongside_ike_and_tina(self):
        # "Ike & Tina Turner" is a curated duo; solo "Tina Turner" is a real
        # standalone artist. Re-parsing her solo credit keeps her links, so she
        # is never deleted.
        artists = [
            {"id": 1, "name": "Ike & Tina Turner"},
            {"id": 2, "name": "Tina Turner"},
            {"id": 3, "name": "Ike"},
        ]
        songs = [
            {"id": 100, "artist_credit": "Ike & Tina Turner"},
            {"id": 101, "artist_credit": "Tina Turner"},  # solo career
        ]
        song_artists = [
            {"song_id": 100, "artist_id": 1, "role": "primary"},
            {"song_id": 101, "artist_id": 2, "role": "primary"},
        ]
        db = FakeDB(artists, songs, [], song_artists, [], [1, 2, 3])
        reconcile(FakeConn(db), dry_run=False)

        tina = db.artist_id("Tina Turner")
        self.assertIsNotNone(tina)
        self.assertEqual(db.song_artist_ids(101), [tina])
        self.assertIsNotNone(db.artist_id("Ike & Tina Turner"))

    def test_tyler_standalone_survives_alongside_tyler_the_creator(self):
        # "Tyler, The Creator" is a curated comma-act; a standalone artist named
        # "Tyler" with his own credit must NOT be merged+deleted into the act.
        artists = [
            {"id": 1, "name": "Tyler, The Creator"},
            {"id": 2, "name": "Tyler"},
        ]
        songs = [
            {"id": 100, "artist_credit": "Tyler, The Creator"},
            {"id": 101, "artist_credit": "Tyler"},  # a different, standalone Tyler
        ]
        song_artists = [
            {"song_id": 100, "artist_id": 1, "role": "primary"},
            {"song_id": 101, "artist_id": 2, "role": "primary"},
        ]
        db = FakeDB(artists, songs, [], song_artists, [], [1, 2])
        reconcile(FakeConn(db), dry_run=False)

        tyler = db.artist_id("Tyler")
        self.assertIsNotNone(tyler)
        self.assertEqual(db.song_artist_ids(101), [tyler])
        # The act keeps its own credit and is parsed whole (lookup-first).
        self.assertEqual(db.song_artist_ids(100), [db.artist_id("Tyler, The Creator")])

    def test_pure_fragment_deleted_but_member_with_own_credit_kept(self):
        # Mixed case in ONE db: "Earth"/"Wind"/"Fire" are pure fragments (only
        # EWF credits) and get deleted, while "Diana Ross" (own solo credit)
        # is kept — proving the deletion gate is link-driven, not name-driven.
        artists = [
            {"id": 1, "name": "Earth, Wind & Fire"},
            {"id": 2, "name": "Earth"},
            {"id": 3, "name": "Wind"},
            {"id": 4, "name": "Fire"},
            {"id": 5, "name": "Diana Ross & The Supremes"},
            {"id": 6, "name": "Diana Ross"},
        ]
        songs = [
            {"id": 100, "artist_credit": "Earth, Wind & Fire"},
            {"id": 101, "artist_credit": "Diana Ross & The Supremes"},
            {"id": 102, "artist_credit": "Diana Ross"},
        ]
        song_artists = [
            {"song_id": 100, "artist_id": 2, "role": "primary"},
            {"song_id": 100, "artist_id": 3, "role": "primary"},
            {"song_id": 100, "artist_id": 4, "role": "primary"},
            {"song_id": 101, "artist_id": 5, "role": "primary"},
            {"song_id": 102, "artist_id": 6, "role": "primary"},
        ]
        db = FakeDB(artists, songs, [], song_artists, [], [1, 2, 3, 4, 5, 6])
        reconcile(FakeConn(db), dry_run=False)

        # Pure fragments deleted.
        self.assertIsNone(db.artist_id("Earth"))
        self.assertIsNone(db.artist_id("Wind"))
        self.assertIsNone(db.artist_id("Fire"))
        # Real member with her own credit kept.
        self.assertIsNotNone(db.artist_id("Diana Ross"))
        self.assertIsNotNone(db.artist_id("Diana Ross & The Supremes"))


class ShatterFragmentHealingTests(unittest.TestCase):
    """Regression for the production incident: 64 orphan fragment-artists left by
    the OLD parser splitting real act names on ``&`` / ``,`` / `` X `` / ``and``.

    Each case seeds the shattered fragment links exactly as the old parser left
    them, then proves reconcile RE-PARSES the stored credit with the current
    parser and heals the links onto the SINGLE canonical act, deleting the now
    zero-link fragments — while never over-merging a real solo member that has
    its own primary credit.
    """

    def test_blood_sweat_and_tears_shatter_heals_to_canonical_act(self):
        # "Blood, Sweat & Tears" is a curated protected act (it lives in the
        # parser's _PROTECTED_AMPERSAND_ACTS allowlist). The old parser split it
        # on "," and " & " into standalone rows Blood / Sweat / Tears, each
        # carrying the song's link. Re-parsing the stored credit yields ONLY the
        # canonical act, so the fragments end zero-link and are deleted.
        self.assertIn(
            "Blood, Sweat & Tears", artist_parser._PROTECTED_AMPERSAND_ACTS
        )
        artists = [
            {"id": 1, "name": "Blood, Sweat & Tears"},  # canonical act
            {"id": 2, "name": "Blood"},  # pure shatter fragment
            {"id": 3, "name": "Sweat"},  # pure shatter fragment
            {"id": 4, "name": "Tears"},  # pure shatter fragment
        ]
        songs = [{"id": 100, "artist_credit": "Blood, Sweat & Tears"}]
        song_artists = [
            {"song_id": 100, "artist_id": 2, "role": "primary"},
            {"song_id": 100, "artist_id": 3, "role": "primary"},
            {"song_id": 100, "artist_id": 4, "role": "primary"},
        ]
        db = FakeDB(artists, songs, [], song_artists, [], [1, 2, 3, 4])
        conn = FakeConn(db)

        report = reconcile(conn, dry_run=False)

        # The link resolves to the SINGLE canonical act, exactly once.
        canonical = db.artist_id("Blood, Sweat & Tears")
        self.assertEqual(db.song_artist_ids(100), [canonical])
        # The three zero-link fragments are deleted.
        self.assertIsNone(db.artist_id("Blood"))
        self.assertIsNone(db.artist_id("Sweat"))
        self.assertIsNone(db.artist_id("Tears"))
        self.assertEqual(
            {d["name"] for d in report["deleted_artists"]},
            {"Blood", "Sweat", "Tears"},
        )
        # Fragment artist_stats rows are cleaned up; canonical stays.
        self.assertEqual(sorted(db.artist_stats), [canonical])
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)

    def test_x_act_from_known_acts_heals_shatter(self):
        # A `` X `` act — "TOMORROW X TOGETHER" — shattered into TOMORROW /
        # TOGETHER. Note: reconcile's DB-derived known-acts set only auto-covers
        # names containing "," or " & " (see _db_known_acts), so an `` X `` act
        # must be supplied through reconcile()'s ``known_acts`` parameter (the
        # documented hook for exactly this). With it supplied, the credit
        # re-parses whole and the fragments heal onto the single canonical act.
        artists = [
            {"id": 1, "name": "TOMORROW X TOGETHER"},  # canonical act
            {"id": 2, "name": "TOMORROW"},  # pure shatter fragment
            {"id": 3, "name": "TOGETHER"},  # pure shatter fragment
        ]
        songs = [{"id": 100, "artist_credit": "TOMORROW X TOGETHER"}]
        song_artists = [
            {"song_id": 100, "artist_id": 2, "role": "primary"},
            {"song_id": 100, "artist_id": 3, "role": "primary"},
        ]
        db = FakeDB(artists, songs, [], song_artists, [], [1, 2, 3])
        conn = FakeConn(db)

        report = reconcile(
            conn, dry_run=False, known_acts=["TOMORROW X TOGETHER"]
        )

        canonical = db.artist_id("TOMORROW X TOGETHER")
        self.assertEqual(db.song_artist_ids(100), [canonical])
        self.assertIsNone(db.artist_id("TOMORROW"))
        self.assertIsNone(db.artist_id("TOGETHER"))
        self.assertEqual(
            {d["name"] for d in report["deleted_artists"]},
            {"TOMORROW", "TOGETHER"},
        )
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)

    def test_solo_member_with_own_primary_credit_survives_healing(self):
        # Protection assertion (mirrors ReconcileMemberArtistSafetyTests): the
        # curated act "Sonny & Cher" shatters into Sonny / Cher, but "Cher" is a
        # genuine solo artist with her OWN primary credit. Healing must delete the
        # pure fragment "Sonny" while KEEPING solo Cher (link-driven, not
        # name-driven) — proving healing does not over-merge a real member.
        artists = [
            {"id": 1, "name": "Sonny & Cher"},  # curated act
            {"id": 2, "name": "Sonny"},  # pure shatter fragment
            {"id": 3, "name": "Cher"},  # genuine solo member
        ]
        songs = [
            {"id": 100, "artist_credit": "Sonny & Cher"},  # shattered onto 2,3
            {"id": 101, "artist_credit": "Cher"},  # her solo catalog
        ]
        song_artists = [
            {"song_id": 100, "artist_id": 2, "role": "primary"},
            {"song_id": 100, "artist_id": 3, "role": "primary"},
            {"song_id": 101, "artist_id": 3, "role": "primary"},
        ]
        db = FakeDB(artists, songs, [], song_artists, [], [1, 2, 3])
        conn = FakeConn(db)

        reconcile(conn, dry_run=False)

        # Solo Cher SURVIVES with her own solo credit intact.
        cher = db.artist_id("Cher")
        self.assertIsNotNone(cher)
        self.assertEqual(db.song_artist_ids(101), [cher])
        # The act itself is healed whole onto song 100.
        self.assertEqual(db.song_artist_ids(100), [db.artist_id("Sonny & Cher")])
        # The pure fragment with no standalone credit is deleted.
        self.assertIsNone(db.artist_id("Sonny"))
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)


class ReconcileCreditJustifiedAddTests(unittest.TestCase):
    """RR-WR-01: a credit's new-parse may legitimately ADD a link the entity is
    missing. The invariant must validate the add per-entity (target-correctness)
    and COMMIT — not reject it via the old ``after_links <= before_links`` proxy.
    """

    def test_feature_add_commits_not_rolls_back(self):
        # Song credited "Drake Featuring Rihanna" linked only to Drake. The new
        # parse produces Drake (primary) + Rihanna (featured); reconciliation
        # must ADD the Rihanna link and COMMIT (old invariant rolled this back
        # with "total link rows increased").
        artists = [
            {"id": 1, "name": "Drake"},
            {"id": 2, "name": "Rihanna"},
        ]
        songs = [{"id": 100, "artist_credit": "Drake Featuring Rihanna"}]
        song_artists = [{"song_id": 100, "artist_id": 1, "role": "primary"}]
        db = FakeDB(artists, songs, [], song_artists, [], [1, 2])
        conn = FakeConn(db)

        report = reconcile(conn, dry_run=False)

        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)
        self.assertEqual(report["added_song_links"], 1)
        # Song 100 now links BOTH the primary and the featured artist.
        self.assertEqual(sorted(db.song_artist_ids(100)), [1, 2])
        # The featured link carries the role the parse assigned.
        rihanna_link = next(
            l for l in db.song_artists
            if l["song_id"] == 100 and l["artist_id"] == 2
        )
        self.assertEqual(rihanna_link["role"], "featured")

    def test_zero_link_song_gets_its_correct_links_added(self):
        # A song with ZERO current links (interrupted/partial load or pruned
        # links) must have its correct link ADDED and COMMIT. Its distinct id set
        # GROWS — that is allowed (only SHRINKING is a violation), and the old
        # "a song lost all its artists" message must not fire for a gained song.
        artists = [{"id": 1, "name": "Drake"}]
        songs = [{"id": 101, "artist_credit": "Drake"}]
        db = FakeDB(artists, songs, [], [], [], [1])
        conn = FakeConn(db)

        report = reconcile(conn, dry_run=False)

        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)
        self.assertEqual(report["added_song_links"], 1)
        self.assertEqual(db.song_artist_ids(101), [1])

    def test_dry_run_add_then_apply_agree(self):
        # The dry-run vs apply feasibility disagreement (RR-WR-01 secondary
        # smell): a plan that dry-run advertises as an add must now actually
        # apply+commit when re-run with dry_run=False.
        artists = [
            {"id": 1, "name": "Drake"},
            {"id": 2, "name": "Rihanna"},
        ]
        songs = [{"id": 100, "artist_credit": "Drake Featuring Rihanna"}]
        song_artists = [{"song_id": 100, "artist_id": 1, "role": "primary"}]

        db_dry = FakeDB(artists, songs, [], song_artists, [], [1, 2])
        dry_conn = FakeConn(db_dry)
        dry_report = reconcile(dry_conn, dry_run=True)
        self.assertEqual(dry_report["added_song_links"], 1)
        self.assertFalse(dry_conn.committed)
        # Same plan applied for real commits (feasibility now agrees).
        db_apply = FakeDB(artists, songs, [], song_artists, [], [1, 2])
        apply_conn = FakeConn(db_apply)
        apply_report = reconcile(apply_conn, dry_run=False)
        self.assertEqual(apply_report["added_song_links"], 1)
        self.assertTrue(apply_conn.committed)
        self.assertFalse(apply_conn.rolled_back)

    def test_add_and_heal_in_one_run(self):
        # Mixed run: EWF shatter is healed (net-remove + delete) AND a separate
        # feature credit adds a link, all in one transaction that COMMITS.
        artists = [
            {"id": 1, "name": "Earth, Wind & Fire"},
            {"id": 2, "name": "Earth"},
            {"id": 3, "name": "Wind"},
            {"id": 4, "name": "Fire"},
            {"id": 5, "name": "Drake"},
            {"id": 6, "name": "Rihanna"},
        ]
        songs = [
            {"id": 100, "artist_credit": "Earth, Wind & Fire"},
            {"id": 101, "artist_credit": "Drake Featuring Rihanna"},
        ]
        song_artists = [
            {"song_id": 100, "artist_id": 2, "role": "primary"},
            {"song_id": 100, "artist_id": 3, "role": "primary"},
            {"song_id": 100, "artist_id": 4, "role": "primary"},
            {"song_id": 101, "artist_id": 5, "role": "primary"},
        ]
        db = FakeDB(artists, songs, [], song_artists, [], [1, 2, 3, 4, 5, 6])
        conn = FakeConn(db)

        reconcile(conn, dry_run=False)

        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)
        # EWF healed onto canonical; fragments deleted.
        self.assertEqual(db.song_artist_ids(100), [1])
        self.assertIsNone(db.artist_id("Earth"))
        # Feature add applied.
        self.assertEqual(sorted(db.song_artist_ids(101)), [5, 6])


class ReconcileRollbackTests(unittest.TestCase):
    def test_invariant_violation_rolls_back_and_raises(self):
        # Force an invariant breach by making _capture_snapshot report a dropped
        # distinct-song id set after the merge, simulating a song losing all
        # artists. The run must roll back (restore state) and raise.
        db = _ewf_fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        original = reconcile_artists._capture_snapshot
        calls = {"n": 0}

        def fake_snapshot(cur):
            snap = original(cur)
            calls["n"] += 1
            if calls["n"] == 2:  # the AFTER snapshot
                # Drop an arbitrary song id to simulate a vanished song.
                snap["song_ids"] = set(snap["song_ids"])
                snap["song_ids"].discard(next(iter(snap["song_ids"])))
            return snap

        reconcile_artists._capture_snapshot = fake_snapshot
        try:
            with self.assertRaises(ReconciliationInvariantError):
                reconcile(conn, dry_run=False)
        finally:
            reconcile_artists._capture_snapshot = original

        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)
        # State restored to its pre-run snapshot.
        self.assertEqual(db.snapshot(), before)

    def test_target_mismatch_rolls_back_and_raises(self):
        # A genuinely artist-less / wrong RESULT (an entity ending with an
        # artist set that does NOT equal its credit's new-parse target) must
        # still roll back. We corrupt the after-keys so song 100 appears
        # artist-less, which violates the per-entity target-correctness
        # invariant — the real safety net that supersedes the old count proxy.
        db = _ewf_fixture()
        before = db.snapshot()
        conn = FakeConn(db)

        original = reconcile_artists._capture_entity_artist_keys

        def fake_keys(cur, id_to_name):
            song_keys, album_keys = original(cur, id_to_name)
            if 100 in song_keys:
                song_keys[100] = set()  # pretend song 100 lost its artist
            return song_keys, album_keys

        reconcile_artists._capture_entity_artist_keys = fake_keys
        try:
            with self.assertRaises(ReconciliationInvariantError):
                reconcile(conn, dry_run=False)
        finally:
            reconcile_artists._capture_entity_artist_keys = original

        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)
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
