"""Fixture/mock-DB + mocked-HTTP tests for the gender enricher (Plan 12-02).

These tests run entirely against an in-memory fake DB layer and a fake HTTP
client returning recorded JSON fixtures. They make NO real database connection
and NO network calls. The real-DB / live-network validation (the operator's
MusicBrainz/Wikidata run + the prod 002_gender apply + the coverage SPIKE
measurement) is carried by docs/GENDER-ENRICHMENT.md as DEFERRED operator steps.

The fake DB models the ``artists`` table with the Phase 12 gender columns
(``gender``, ``gender_source``, ``gender_source_id``) and interprets the exact
statements ``enrich()`` emits (the two SELECTs, the optional id-scoped SELECT,
and the parameterized UPDATE). ``FakeHttpClient`` maps (url, params) to recorded
JSON, so the MusicBrainz two-step (search -> lookup) and the Wikidata fallback
(wbsearchentities -> wbgetentities) are exercised without a socket.

Mirrors the repo's unittest + unittest.mock idiom (see
tests/test_reconcile_artists.py, tests/test_charts.py): no pytest fixtures, no
``responses`` lib, the rate-limit sleep monkeypatched to a no-op.
"""

import copy
import re
import unittest

from billboard_stats.etl import gender_enricher
from billboard_stats.etl.gender_enricher import (
    HttpClient,
    _map_gender,
    _map_wikidata,
    enrich,
)


# ============================================================================
# In-memory fake DB layer (artists with gender columns)
# ============================================================================
class FakeCursor:
    """A psycopg2-cursor-like stand-in interpreting the SQL enrich() emits."""

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

        # Default selection gate: only gender='unknown' rows. Must be checked
        # BEFORE the bare "select id, name from artists" prefix.
        if norm.startswith("select id, name from artists where gender = 'unknown'"):
            rows = [a for a in self._db.artists if a["gender"] == "unknown"]
            # Optional id scoping (only_artist_ids -> WHERE ... AND id = ANY(%s)).
            if "id = any" in norm:
                (ids,) = params
                idset = set(ids)
                rows = [a for a in rows if a["id"] in idset]
            self._result = [(a["id"], a["name"]) for a in rows]
            return

        # --refresh selection: ALL rows (optionally id-scoped).
        if norm.startswith("select id, name from artists"):
            rows = list(self._db.artists)
            if "id = any" in norm:
                (ids,) = params
                idset = set(ids)
                rows = [a for a in rows if a["id"] in idset]
            self._result = [(a["id"], a["name"]) for a in rows]
            return

        # Pre/post-load id snapshot used by the ETL delta path.
        if norm.startswith("select id from artists"):
            self._result = [(a["id"],) for a in self._db.artists]
            return

        if norm.startswith("update artists set gender"):
            gender, source, source_id, artist_id = params
            self._db.update_gender(artist_id, gender, source, source_id)
            return

        # --- coverage_report() read-only aggregation queries (test_gender_coverage
        #     uses its own harness; tolerated here only if reused). ---
        raise AssertionError(f"FakeCursor: unhandled SQL: {norm!r}")

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0]


class FakeConn:
    """A connection-like stand-in tracking commit/rollback and snapshotting."""

    def __init__(self, db):
        self._db = db
        self.committed = False
        self.commit_count = 0
        self.rolled_back = False
        self.rollback_count = 0
        self._snapshot = db.snapshot()

    def cursor(self):
        return FakeCursor(self._db)

    def commit(self):
        self.committed = True
        self.commit_count += 1

    def rollback(self):
        self.rolled_back = True
        self.rollback_count += 1
        self._db.restore(self._snapshot)


class FakeDB:
    """In-memory model of the artists table with the Phase 12 gender columns."""

    def __init__(self, artists):
        # artists: list of dicts with id, name, gender, gender_source,
        # gender_source_id (last three optional; default unknown/None/None).
        self.artists = []
        for a in artists:
            self.artists.append(
                {
                    "id": a["id"],
                    "name": a["name"],
                    "gender": a.get("gender", "unknown"),
                    "gender_source": a.get("gender_source"),
                    "gender_source_id": a.get("gender_source_id"),
                }
            )

    def update_gender(self, artist_id, gender, source, source_id):
        for a in self.artists:
            if a["id"] == artist_id:
                a["gender"] = gender
                a["gender_source"] = source
                a["gender_source_id"] = source_id
                return
        raise AssertionError(f"update of unknown artist id {artist_id}")

    def by_id(self, artist_id):
        for a in self.artists:
            if a["id"] == artist_id:
                return a
        return None

    def snapshot(self):
        return copy.deepcopy({"artists": self.artists})

    def restore(self, snap):
        self.artists = copy.deepcopy(snap)["artists"]


# ============================================================================
# Mocked HTTP client + recorded JSON fixtures
# ============================================================================
MB_SEARCH = "https://musicbrainz.org/ws/2/artist"

# MusicBrainz search response — a multi-candidate result for a Person (Female).
MB_SEARCH_BEYONCE = {
    "count": 2,
    "artists": [
        {
            "id": "859d0860-d480-4efd-970c-c05d5f1776b8",
            "name": "Beyoncé",
            "type": "Person",
            "score": 100,
        },
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "Beyonce tribute",
            "type": "Person",
            "score": 55,
        },
    ],
}
# MB Person lookup — gender Female.
MB_LOOKUP_BEYONCE = {
    "id": "859d0860-d480-4efd-970c-c05d5f1776b8",
    "name": "Beyoncé",
    "type": "Person",
    "gender": "Female",
}

# A male Person.
MB_SEARCH_DRAKE = {
    "count": 1,
    "artists": [
        {
            "id": "b49b81cc-d5b7-4bdd-aadb-385df8de69a6",
            "name": "Drake",
            "type": "Person",
            "score": 99,
        }
    ],
}
MB_LOOKUP_DRAKE = {
    "id": "b49b81cc-d5b7-4bdd-aadb-385df8de69a6",
    "name": "Drake",
    "type": "Person",
    "gender": "Male",
}

# A Group (no gender key in the lookup).
MB_SEARCH_QUEEN = {
    "count": 1,
    "artists": [
        {
            "id": "0383dadf-2a4e-4d10-a46a-e9e041da8eb3",
            "name": "Queen",
            "type": "Group",
            "score": 100,
        }
    ],
}
MB_LOOKUP_QUEEN = {
    "id": "0383dadf-2a4e-4d10-a46a-e9e041da8eb3",
    "name": "Queen",
    "type": "Group",
    # NOTE: no "gender" key — groups carry no gender in MusicBrainz.
}

# A Non-binary Person -> maps to 'unknown'.
MB_SEARCH_NB = {
    "count": 1,
    "artists": [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Sam Smith",
            "type": "Person",
            "score": 97,
        }
    ],
}
MB_LOOKUP_NB = {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "Sam Smith",
    "type": "Person",
    "gender": "Non-binary",
}

# A low-score search (best < threshold) -> no confident MB match.
MB_SEARCH_LOWSCORE = {
    "count": 1,
    "artists": [
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "Obscure",
            "type": "Person",
            "score": 40,
        }
    ],
}

# An empty MB search -> no MB match (forces Wikidata fallback in tests).
MB_SEARCH_EMPTY = {"count": 0, "artists": []}

WD_API = "https://www.wikidata.org/w/api.php"
# Wikidata search -> a single QID.
WD_SEARCH_FEMALE = {"search": [{"id": "Q1234"}]}
# Wikidata entity claims: human (Q5) + female P21 (Q6581072).
WD_ENTITY_FEMALE = {
    "entities": {
        "Q1234": {
            "claims": {
                "P31": [
                    {
                        "mainsnak": {
                            "datavalue": {"value": {"id": "Q5"}}
                        }
                    }
                ],
                "P21": [
                    {
                        "mainsnak": {
                            "datavalue": {"value": {"id": "Q6581072"}}
                        }
                    }
                ],
            }
        }
    }
}


class FakeHttpClient:
    """Maps (url, params) -> (status, recorded_json). Records every call."""

    def __init__(self, routes):
        # routes: list of (predicate(url, params) -> bool, (status, json) | Exception)
        self._routes = routes
        self.calls = []

    def get_json(self, url, params=None, headers=None, timeout=20):
        params = params or {}
        self.calls.append((url, dict(params)))
        for predicate, result in self._routes:
            if predicate(url, params):
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"FakeHttpClient: unrouted call url={url} params={params}")

    def touched_wikidata(self):
        return any(url == WD_API for url, _ in self.calls)


def _is_mb_search(url, params):
    return url == MB_SEARCH and "query" in params


def _is_mb_lookup(url, params, mbid):
    return url == f"{MB_SEARCH}/{mbid}"


def _wd_action(action):
    def pred(url, params):
        return url == WD_API and params.get("action") == action

    return pred


def _route_search_returns(name_query_substr, response):
    def pred(url, params):
        return (
            url == MB_SEARCH
            and "query" in params
            and name_query_substr.lower() in params["query"].lower()
        )

    return (pred, response)


def _route_lookup(mbid, response):
    return (lambda url, params: url == f"{MB_SEARCH}/{mbid}", response)


# ============================================================================
# Pure mapping tests (_map_gender / _map_wikidata) — no DB, no HTTP
# ============================================================================
class MapGenderTests(unittest.TestCase):
    def test_mapping_person_female(self):
        self.assertEqual(_map_gender("Person", "Female"), "female")

    def test_mapping_person_male(self):
        self.assertEqual(_map_gender("Person", "Male"), "male")

    def test_mapping_character_female(self):
        self.assertEqual(_map_gender("Character", "Female"), "female")

    def test_mapping_person_nonbinary_is_unknown(self):
        self.assertEqual(_map_gender("Person", "Non-binary"), "unknown")

    def test_mapping_person_absent_gender_is_unknown(self):
        self.assertEqual(_map_gender("Person", None), "unknown")

    def test_mapping_group_is_group(self):
        self.assertEqual(_map_gender("Group", None), "group")

    def test_mapping_choir_is_group(self):
        self.assertEqual(_map_gender("Choir", None), "group")

    def test_mapping_orchestra_is_group(self):
        self.assertEqual(_map_gender("Orchestra", None), "group")

    def test_mapping_group_never_emits_mixed(self):
        # Even if a group somehow had a gender value, the automated path never
        # emits 'mixed' (reserved for manual).
        self.assertNotEqual(_map_gender("Group", "Female"), "mixed")
        self.assertEqual(_map_gender("Group", "Female"), "group")

    def test_mapping_other_type_is_unknown(self):
        self.assertEqual(_map_gender("Other", None), "unknown")

    def test_mapping_absent_type_is_unknown(self):
        self.assertEqual(_map_gender(None, "Female"), "unknown")

    def test_mapping_never_returns_mixed(self):
        for t in ("Person", "Character", "Group", "Choir", "Orchestra", "Other", None):
            for g in ("Female", "Male", "Non-binary", None, "Other"):
                self.assertNotEqual(_map_gender(t, g), "mixed")


class MapWikidataTests(unittest.TestCase):
    def test_human_male(self):
        self.assertEqual(_map_wikidata({"Q5"}, "Q6581097"), "male")

    def test_human_female(self):
        self.assertEqual(_map_wikidata({"Q5"}, "Q6581072"), "female")

    def test_human_nonbinary_is_unknown(self):
        self.assertEqual(_map_wikidata({"Q5"}, "Q48270"), "unknown")

    def test_human_absent_p21_is_unknown(self):
        self.assertEqual(_map_wikidata({"Q5"}, None), "unknown")

    def test_band_is_group(self):
        self.assertEqual(_map_wikidata({"Q215380"}, None), "group")

    def test_unknown_class_is_unknown(self):
        self.assertEqual(_map_wikidata({"Q99999999"}, None), "unknown")

    def test_never_returns_mixed(self):
        self.assertNotEqual(_map_wikidata({"Q215380"}, "Q6581072"), "mixed")


# ============================================================================
# enrich() — fake DB + mocked HTTP
# ============================================================================
class EnrichTests(unittest.TestCase):
    def setUp(self):
        # Monkeypatch the rate-limit sleep to a no-op for all enrich() tests.
        self._orig_sleep = gender_enricher.time.sleep
        gender_enricher.time.sleep = lambda *_a, **_k: None

    def tearDown(self):
        gender_enricher.time.sleep = self._orig_sleep

    def test_persists_mbid_and_gender_female(self):
        db = FakeDB([{"id": 1, "name": "Beyoncé"}])
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Beyoncé", (200, MB_SEARCH_BEYONCE)),
                _route_lookup(MB_LOOKUP_BEYONCE["id"], (200, MB_LOOKUP_BEYONCE)),
            ]
        )
        report = enrich(conn, http=http, delay=0)

        row = db.by_id(1)
        self.assertEqual(row["gender"], "female")
        self.assertEqual(row["gender_source"], "musicbrainz")
        # Persist the MBID (a stable ID), NOT the raw name.
        self.assertEqual(row["gender_source_id"], MB_LOOKUP_BEYONCE["id"])
        self.assertTrue(conn.committed)
        self.assertEqual(report["matched"], 1)

    def test_persists_male(self):
        db = FakeDB([{"id": 1, "name": "Drake"}])
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Drake", (200, MB_SEARCH_DRAKE)),
                _route_lookup(MB_LOOKUP_DRAKE["id"], (200, MB_LOOKUP_DRAKE)),
            ]
        )
        enrich(conn, http=http, delay=0)
        self.assertEqual(db.by_id(1)["gender"], "male")

    def test_group_maps_to_group_without_reading_gender(self):
        db = FakeDB([{"id": 1, "name": "Queen"}])
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Queen", (200, MB_SEARCH_QUEEN)),
                _route_lookup(MB_LOOKUP_QUEEN["id"], (200, MB_LOOKUP_QUEEN)),
            ]
        )
        enrich(conn, http=http, delay=0)
        self.assertEqual(db.by_id(1)["gender"], "group")
        self.assertEqual(db.by_id(1)["gender_source_id"], MB_LOOKUP_QUEEN["id"])

    def test_nonbinary_person_maps_to_unknown(self):
        db = FakeDB([{"id": 1, "name": "Sam Smith"}])
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Sam Smith", (200, MB_SEARCH_NB)),
                _route_lookup(MB_LOOKUP_NB["id"], (200, MB_LOOKUP_NB)),
            ]
        )
        enrich(conn, http=http, delay=0)
        # Non-binary -> 'unknown'; row stays unknown (no misattribution).
        self.assertEqual(db.by_id(1)["gender"], "unknown")

    def test_low_score_search_leaves_unknown_and_tries_wikidata(self):
        # MB best score below threshold -> MB no-match -> Wikidata fallback.
        db = FakeDB([{"id": 1, "name": "Obscure"}])
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Obscure", (200, MB_SEARCH_LOWSCORE)),
                (_wd_action("wbsearchentities"), (200, WD_SEARCH_FEMALE)),
                (_wd_action("wbgetentities"), (200, WD_ENTITY_FEMALE)),
            ]
        )
        enrich(conn, http=http, delay=0)
        # Wikidata resolved female + persisted the QID.
        self.assertEqual(db.by_id(1)["gender"], "female")
        self.assertEqual(db.by_id(1)["gender_source"], "wikidata")
        self.assertEqual(db.by_id(1)["gender_source_id"], "Q1234")

    def test_wikidata_not_called_on_mb_hit(self):
        db = FakeDB([{"id": 1, "name": "Beyoncé"}])
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Beyoncé", (200, MB_SEARCH_BEYONCE)),
                _route_lookup(MB_LOOKUP_BEYONCE["id"], (200, MB_LOOKUP_BEYONCE)),
                # Wikidata routes present but MUST NOT be hit on an MB confident match.
                (_wd_action("wbsearchentities"), (200, WD_SEARCH_FEMALE)),
            ]
        )
        enrich(conn, http=http, delay=0)
        self.assertFalse(
            http.touched_wikidata(),
            "Wikidata must NOT be queried when MusicBrainz returns a confident match",
        )

    def test_wikidata_fallback_only_on_mb_no_match(self):
        db = FakeDB([{"id": 1, "name": "Indie Person"}])
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Indie Person", (200, MB_SEARCH_EMPTY)),
                (_wd_action("wbsearchentities"), (200, WD_SEARCH_FEMALE)),
                (_wd_action("wbgetentities"), (200, WD_ENTITY_FEMALE)),
            ]
        )
        enrich(conn, http=http, delay=0)
        self.assertTrue(http.touched_wikidata())
        self.assertEqual(db.by_id(1)["gender"], "female")
        self.assertEqual(db.by_id(1)["gender_source"], "wikidata")

    def test_http_error_leaves_row_unknown_and_continues(self):
        # Two artists: the first errors on HTTP, the second resolves cleanly.
        db = FakeDB(
            [{"id": 1, "name": "Boom"}, {"id": 2, "name": "Drake"}]
        )
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Boom", RuntimeError("boom 503")),
                _route_search_returns("Drake", (200, MB_SEARCH_DRAKE)),
                _route_lookup(MB_LOOKUP_DRAKE["id"], (200, MB_LOOKUP_DRAKE)),
            ]
        )
        report = enrich(conn, http=http, delay=0)
        # The erroring row stays unknown; the batch continues to the next row.
        self.assertEqual(db.by_id(1)["gender"], "unknown")
        self.assertEqual(db.by_id(2)["gender"], "male")
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)

    def test_fill_only_unknown_skips_already_enriched(self):
        db = FakeDB(
            [
                {
                    "id": 1,
                    "name": "Drake",
                    "gender": "male",
                    "gender_source": "musicbrainz",
                    "gender_source_id": "x",
                },
                {"id": 2, "name": "Beyoncé"},
            ]
        )
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Beyoncé", (200, MB_SEARCH_BEYONCE)),
                _route_lookup(MB_LOOKUP_BEYONCE["id"], (200, MB_LOOKUP_BEYONCE)),
                # Drake routes intentionally ABSENT: an attempt to resolve the
                # already-enriched row would raise "unrouted call".
            ]
        )
        enrich(conn, http=http, delay=0)
        self.assertEqual(db.by_id(2)["gender"], "female")
        # Drake untouched (no search call made for it).
        self.assertFalse(any("drake" in p.get("query", "").lower() for _u, p in http.calls))

    def test_refresh_refetches_all_rows(self):
        db = FakeDB(
            [
                {
                    "id": 1,
                    "name": "Drake",
                    "gender": "male",
                    "gender_source": "musicbrainz",
                    "gender_source_id": "old",
                }
            ]
        )
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Drake", (200, MB_SEARCH_DRAKE)),
                _route_lookup(MB_LOOKUP_DRAKE["id"], (200, MB_LOOKUP_DRAKE)),
            ]
        )
        enrich(conn, http=http, delay=0, refresh=True)
        # Re-fetched even though it was already non-unknown.
        self.assertEqual(db.by_id(1)["gender_source_id"], MB_LOOKUP_DRAKE["id"])

    def test_only_artist_ids_scopes_selection(self):
        db = FakeDB(
            [
                {"id": 1, "name": "Beyoncé"},
                {"id": 2, "name": "Drake"},
            ]
        )
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Beyoncé", (200, MB_SEARCH_BEYONCE)),
                _route_lookup(MB_LOOKUP_BEYONCE["id"], (200, MB_LOOKUP_BEYONCE)),
                # Drake routes absent: it must be excluded by only_artist_ids.
            ]
        )
        enrich(conn, http=http, delay=0, only_artist_ids=[1])
        self.assertEqual(db.by_id(1)["gender"], "female")
        self.assertEqual(db.by_id(2)["gender"], "unknown")

    def test_dry_run_writes_nothing(self):
        db = FakeDB([{"id": 1, "name": "Beyoncé"}])
        before = db.snapshot()
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Beyoncé", (200, MB_SEARCH_BEYONCE)),
                _route_lookup(MB_LOOKUP_BEYONCE["id"], (200, MB_LOOKUP_BEYONCE)),
            ]
        )
        report = enrich(conn, http=http, delay=0, dry_run=True)
        self.assertEqual(db.snapshot(), before)
        self.assertEqual(db.by_id(1)["gender"], "unknown")
        self.assertTrue(report["dry_run"])

    def test_limit_caps_selection(self):
        db = FakeDB(
            [
                {"id": 1, "name": "Beyoncé"},
                {"id": 2, "name": "Drake"},
            ]
        )
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Beyoncé", (200, MB_SEARCH_BEYONCE)),
                _route_lookup(MB_LOOKUP_BEYONCE["id"], (200, MB_LOOKUP_BEYONCE)),
            ]
        )
        enrich(conn, http=http, delay=0, limit=1)
        # Only the first row is processed.
        self.assertEqual(db.by_id(1)["gender"], "female")
        self.assertEqual(db.by_id(2)["gender"], "unknown")

    def test_fatal_db_error_rolls_back_and_reraises(self):
        # A failure inside the loop body that is NOT the per-artist HTTP path
        # (e.g. the UPDATE raises) must roll back the enricher's own unit + raise.
        db = FakeDB([{"id": 1, "name": "Beyoncé"}])
        conn = FakeConn(db)

        class BoomCursor(FakeCursor):
            def execute(self, sql, params=None):
                norm = re.sub(r"\s+", " ", sql).strip().lower()
                if norm.startswith("update artists set gender"):
                    raise RuntimeError("db down")
                return super().execute(sql, params)

        conn.cursor = lambda: BoomCursor(db)
        http = FakeHttpClient(
            [
                _route_search_returns("Beyoncé", (200, MB_SEARCH_BEYONCE)),
                _route_lookup(MB_LOOKUP_BEYONCE["id"], (200, MB_LOOKUP_BEYONCE)),
            ]
        )
        with self.assertRaises(RuntimeError):
            enrich(conn, http=http, delay=0)
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)


# ============================================================================
# Defensive-parsing tests (T-12-04): untrusted JSON must never crash the batch
# ============================================================================
class DefensiveParsingTests(unittest.TestCase):
    def setUp(self):
        self._orig_sleep = gender_enricher.time.sleep
        gender_enricher.time.sleep = lambda *_a, **_k: None

    def tearDown(self):
        gender_enricher.time.sleep = self._orig_sleep

    def test_malformed_mb_body_leaves_row_unknown(self):
        db = FakeDB([{"id": 1, "name": "Weird"}])
        conn = FakeConn(db)
        http = FakeHttpClient(
            [
                # Body missing "artists", wrong-typed -> must not crash.
                _route_search_returns("Weird", (200, {"unexpected": "shape"})),
                (_wd_action("wbsearchentities"), (200, {"search": []})),
            ]
        )
        report = enrich(conn, http=http, delay=0)
        self.assertEqual(db.by_id(1)["gender"], "unknown")
        self.assertTrue(conn.committed)


# ============================================================================
# ETL hook contract: never-block (W-1) + delta-scoping (W-2)
# ============================================================================
class EtlEnrichmentStageTests(unittest.TestCase):
    """Exercise loader._enrich_new_artists — the run_etl enrichment stage helper.

    The stage runs AFTER the load loop and BEFORE build_all_stats; these tests
    prove the never-block (W-1) and delta-scoping (W-2) contracts offline,
    monkeypatching the enricher (and time.sleep) so no DB/network is touched.
    """

    def setUp(self):
        from billboard_stats.etl import loader

        self.loader = loader
        self._orig_enrich = getattr(loader, "enrich", None)

    def test_w1a_successful_enrich_commits_its_own_work(self):
        # The stage delegates to enrich(), which commits its own successful work
        # (W-1a). Use the REAL enrich() against the fake conn + mocked HTTP.
        gender_enricher.time.sleep = lambda *_a, **_k: None
        try:
            db = FakeDB([{"id": 1, "name": "Beyoncé"}])
            conn = FakeConn(db)

            http = FakeHttpClient(
                [
                    _route_search_returns("Beyoncé", (200, MB_SEARCH_BEYONCE)),
                    _route_lookup(MB_LOOKUP_BEYONCE["id"], (200, MB_LOOKUP_BEYONCE)),
                ]
            )

            # Patch the lazily-imported enrich to inject our fake http while
            # keeping the REAL enrich semantics (commit on success).
            import billboard_stats.etl.gender_enricher as ge

            real_enrich = ge.enrich

            def patched_enrich(c, **kwargs):
                kwargs.setdefault("http", http)
                kwargs.setdefault("delay", 0)
                return real_enrich(c, **kwargs)

            ge.enrich = patched_enrich
            try:
                # pre_load empty -> artist 1 is "new".
                self.loader._enrich_new_artists(conn, set())
            finally:
                ge.enrich = real_enrich

            self.assertEqual(db.by_id(1)["gender"], "female")
            self.assertTrue(conn.committed)
        finally:
            pass

    def test_w1b_error_in_enrichment_preserves_load_rows_and_reaches_stats(self):
        # Simulate load rows that were committed BEFORE the stage (loader:348).
        db = FakeDB(
            [{"id": 1, "name": "Drake", "gender": "unknown"}]
        )
        conn = FakeConn(db)
        # The committed load snapshot (what per-chart commits left durable).
        committed_snapshot = db.snapshot()

        import billboard_stats.etl.gender_enricher as ge

        real_enrich = ge.enrich

        def boom_enrich(c, **kwargs):
            raise RuntimeError("enrichment exploded")

        # Track whether build_all_stats is still reached after the stage.
        calls = {"build": 0}

        def fake_build(c):
            calls["build"] += 1

        orig_build = self.loader.build_all_stats
        ge.enrich = boom_enrich
        self.loader.build_all_stats = fake_build
        try:
            # The stage must swallow the error (never raise).
            self.loader._enrich_new_artists(conn, set())
            # Then ETL proceeds to stats (we call it here to mirror run_etl flow).
            self.loader.build_all_stats(conn)
        finally:
            ge.enrich = real_enrich
            self.loader.build_all_stats = orig_build

        self.assertEqual(calls["build"], 1, "build_all_stats must still be reached")
        # The pre-committed load rows are intact (not discarded by the hook).
        self.assertEqual(db.snapshot(), committed_snapshot)

    def test_w1c_hook_does_not_issue_its_own_rollback(self):
        # An enrich that raises WITHOUT rolling back: the hook must NOT rollback.
        conn = FakeConn(FakeDB([{"id": 1, "name": "X"}]))

        import billboard_stats.etl.gender_enricher as ge

        real_enrich = ge.enrich

        def boom_no_rollback(c, **kwargs):
            raise RuntimeError("enrichment exploded before any rollback")

        ge.enrich = boom_no_rollback
        try:
            self.loader._enrich_new_artists(conn, set())
        finally:
            ge.enrich = real_enrich

        self.assertEqual(
            conn.rollback_count, 0,
            "the ETL hook must NOT call conn.rollback() — the enricher owns it",
        )

    def test_w2_delta_scopes_to_new_artists_only(self):
        # A pre-existing 'unknown' artist (id=1) and a NEW 'unknown' artist
        # (id=2) inserted by the load. The stage must pass only_artist_ids={2}
        # so the pre-existing unknown row is NOT re-enriched (delta-scoping by
        # the passed id-diff, not the unknown-gate).
        db = FakeDB(
            [
                {"id": 1, "name": "Pre Existing", "gender": "unknown"},
                {"id": 2, "name": "New Artist", "gender": "unknown"},
            ]
        )
        conn = FakeConn(db)
        pre_load = {1}  # id 1 existed before the load loop

        import billboard_stats.etl.gender_enricher as ge

        real_enrich = ge.enrich
        captured = {}

        def spy_enrich(c, **kwargs):
            captured["only_artist_ids"] = kwargs.get("only_artist_ids")
            return {"selected": 0}

        ge.enrich = spy_enrich
        try:
            self.loader._enrich_new_artists(conn, pre_load)
        finally:
            ge.enrich = real_enrich

        self.assertIsNotNone(
            captured["only_artist_ids"],
            "run_etl MUST pass a NON-None only_artist_ids delta (W-2)",
        )
        self.assertEqual(set(captured["only_artist_ids"]), {2})
        self.assertNotIn(
            1, set(captured["only_artist_ids"]),
            "pre-existing 'unknown' artist must NOT be in the delta",
        )

    def test_w2_pre_existing_unknown_not_reenriched_end_to_end(self):
        # End-to-end through the stage with the REAL enrich + mocked HTTP: the
        # pre-existing unknown row (id=1) stays unknown because it is excluded by
        # only_artist_ids, even though its gender IS still 'unknown'.
        gender_enricher.time.sleep = lambda *_a, **_k: None
        db = FakeDB(
            [
                {"id": 1, "name": "Drake", "gender": "unknown"},
                {"id": 2, "name": "Beyoncé", "gender": "unknown"},
            ]
        )
        conn = FakeConn(db)
        pre_load = {1}

        http = FakeHttpClient(
            [
                _route_search_returns("Beyoncé", (200, MB_SEARCH_BEYONCE)),
                _route_lookup(MB_LOOKUP_BEYONCE["id"], (200, MB_LOOKUP_BEYONCE)),
                # Drake routes intentionally ABSENT: any attempt to resolve the
                # pre-existing row would raise "unrouted call".
            ]
        )

        import billboard_stats.etl.gender_enricher as ge

        real_enrich = ge.enrich

        def patched_enrich(c, **kwargs):
            kwargs.setdefault("http", http)
            kwargs.setdefault("delay", 0)
            return real_enrich(c, **kwargs)

        ge.enrich = patched_enrich
        try:
            self.loader._enrich_new_artists(conn, pre_load)
        finally:
            ge.enrich = real_enrich

        self.assertEqual(db.by_id(2)["gender"], "female")  # new artist enriched
        self.assertEqual(db.by_id(1)["gender"], "unknown")  # pre-existing untouched
        # No Drake search was ever attempted (delta excluded it).
        self.assertFalse(
            any("drake" in p.get("query", "").lower() for _u, p in http.calls)
        )


# ============================================================================
# Import hygiene: no top-level psycopg2 / requests
# ============================================================================
class EnricherPostgresFreeTests(unittest.TestCase):
    def test_module_has_no_top_level_psycopg_or_requests_import(self):
        import inspect

        src = inspect.getsource(gender_enricher)
        lines = src.splitlines()
        top_level = [
            l for l in lines if l.startswith("import ") or l.startswith("from ")
        ]
        self.assertFalse(
            any("psycopg" in l for l in top_level),
            "psycopg2 must not be a top-level import",
        )
        self.assertFalse(
            any("requests" in l for l in top_level),
            "requests must not be a top-level import",
        )

    def test_default_http_client_lazy_imports_requests(self):
        # The default HttpClient is the ONLY place requests is referenced, and
        # only inside get_json(). Constructing it must not require requests.
        client = HttpClient()
        self.assertTrue(hasattr(client, "get_json"))


if __name__ == "__main__":
    unittest.main()
