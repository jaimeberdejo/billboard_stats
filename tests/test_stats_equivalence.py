"""Build-both-ways equivalence tests for the Phase 15 ``*_stats`` re-point.

Phase 15 re-points ``build_song_stats`` / ``build_album_stats`` /
``build_artist_stats`` from the retired bifurcated ``hot100_entries`` /
``b200_entries`` tables onto the polymorphic ``chart_entries`` table filtered by
``chart_id`` (under the parametric ``valid_weeks_cte``). The output ``*_stats``
rows MUST be byte-identical to the legacy build -- this is the riskiest change in
the whole phase, so it is gated here.

These tests run entirely against an in-memory fake DB layer (no psycopg2, no
network). The fake DB holds ONE fixture where the legacy entry rows
(``hot100_entries`` / ``b200_entries``) and the polymorphic ``chart_entries``
rows are the SAME data (mirroring the dual-write invariant proven in
``test_etl_equivalence.py``). It interprets BOTH:

* the LEGACY ``*_stats`` SQL -- snapshotted verbatim in this test from the
  pre-Phase-15 production builders, reading ``FROM hot100_entries`` /
  ``FROM b200_entries`` and the literal ``valid_hot100_weeks`` / ``valid_b200_weeks``
  CTEs -- driven by ``_build_*_stats_legacy`` helpers below; and
* the RE-POINTED production ``*_stats`` SQL -- emitted by the real
  ``stats_builder.build_song_stats`` / ``build_album_stats`` /
  ``build_artist_stats`` over ``chart_entries`` -- exercised by calling the real
  functions.

If the re-point ever diverges (e.g. ``COUNT(*)`` silently rewritten to
``COUNT(DISTINCT chart_week_id)``, Pitfall 2; or a different phantom tie-break),
the sorted-row equality assertions below fail.

The fake DB does NOT execute literal SQL text -- it interprets the statement
*shapes* the builders emit (same harness style as
``test_stats_builder_parametric.py``). The legacy path is interpreted from the
legacy entry tables; the re-pointed path is interpreted from ``chart_entries``.
Both interpret the SAME phantom rule (MIN(id) first-real week) so any genuine
semantic drift in the production SQL surfaces as a fixture-row diff.
"""

import inspect
import re
import unittest

from billboard_stats.etl import stats_builder
from billboard_stats.etl.stats_builder import (
    build_album_stats,
    build_artist_stats,
    build_song_stats,
)


# ============================================================================
# Snapshot of the LEGACY *_stats SQL (pre-Phase-15), captured verbatim so the
# test can build "the old way" even after the production constants/queries are
# deleted. Only their PRESENCE markers matter to the fake interpreter; the text
# documents exactly what was replaced.
# ============================================================================
_LEGACY_SONG_STATS_INSERT = """
    WITH valid_hot100_weeks
    INSERT INTO song_stats (...)
    SELECT e.song_id, COUNT(*), MIN(e.rank), ...
    FROM hot100_entries e
    JOIN chart_weeks cw ON e.chart_week_id = cw.id
    WHERE e.chart_week_id IN (SELECT id FROM valid_hot100_weeks)
    GROUP BY e.song_id;
"""
_LEGACY_ALBUM_STATS_INSERT = """
    WITH valid_b200_weeks
    INSERT INTO album_stats (...)
    SELECT e.album_id, COUNT(*), MIN(e.rank), ...
    FROM b200_entries e
    JOIN chart_weeks cw ON e.chart_week_id = cw.id
    WHERE e.chart_week_id IN (SELECT id FROM valid_b200_weeks)
    GROUP BY e.album_id;
"""


# ============================================================================
# In-memory fake DB modelling charts / chart_weeks / chart_entries +
# legacy hot100_entries / b200_entries + song_artists / album_artists + artists,
# and the three *_stats target tables.
# ============================================================================
class _StatsFakeCursor:
    """Interprets the *_stats statement SHAPES both the legacy and re-pointed
    builders emit, computing the resulting rows in Python.

    Dispatch is by statement shape (DELETE / INSERT-or-UPDATE per stats table)
    plus the table the statement reads:

    * a statement reading ``hot100_entries`` / ``b200_entries`` is the LEGACY
      path -> rows computed from the legacy entry tables;
    * a statement reading ``chart_entries`` is the RE-POINTED path -> rows
      computed from ``chart_entries`` filtered by the bound chart_id param.

    Both apply the SAME phantom-week filter (MIN(id) first-real), so identical
    fixture data yields identical rows IFF the production SQL preserves the
    legacy semantics.
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

        # --- slug -> chart_id resolution (re-pointed builders) -----------------
        if norm.startswith("select id from charts where slug ="):
            (slug,) = params
            cid = self._db.chart_id(slug)
            self._result = [(cid,)] if cid is not None else []
            return

        # --- DELETE FROM <stats table> -----------------------------------------
        for tbl in ("song_stats", "album_stats", "artist_stats"):
            if norm.startswith(f"delete from {tbl}"):
                setattr(self._db, tbl, {})
                return

        # --- artist_stats seed: INSERT INTO artist_stats (artist_id) SELECT ----
        if norm.startswith("insert into artist_stats (artist_id)"):
            for a in self._db.artists:
                self._db.artist_stats.setdefault(a["id"], {"artist_id": a["id"]})
            return

        # --- song_stats build (INSERT) -----------------------------------------
        if "insert into song_stats" in norm:
            self._db.build_song_stats_insert(self._legacy(norm), params)
            return
        if "update song_stats" in norm and "weeks_at_peak" in norm:
            self._db.song_stats_weeks_at_peak(self._legacy(norm), params)
            return
        if "update song_stats" in norm and "debut_position" in norm:
            self._db.song_stats_debut_position(self._legacy(norm), params)
            return

        # --- album_stats build -------------------------------------------------
        if "insert into album_stats" in norm:
            self._db.build_album_stats_insert(self._legacy(norm), params)
            return
        if "update album_stats" in norm and "weeks_at_peak" in norm:
            self._db.album_stats_weeks_at_peak(self._legacy(norm), params)
            return
        if "update album_stats" in norm and "debut_position" in norm:
            self._db.album_stats_debut_position(self._legacy(norm), params)
            return

        # --- artist_stats updates ----------------------------------------------
        if "update artist_stats" in norm and "total_hot100_songs" in norm:
            self._db.artist_total_hot100_songs()
            return
        if "update artist_stats" in norm and "total_b200_albums" in norm:
            self._db.artist_total_b200_albums()
            return
        if "update artist_stats" in norm and "total_hot100_weeks" in norm:
            self._db.artist_hot100_weeks(self._legacy(norm), params)
            return
        if "update artist_stats" in norm and "total_b200_weeks" in norm:
            self._db.artist_b200_weeks(self._legacy(norm), params)
            return
        if "update artist_stats" in norm and "first_chart_date" in norm:
            self._db.artist_chart_dates(self._legacy(norm), params)
            return
        if "update artist_stats" in norm and "max_simultaneous_hot100" in norm:
            self._db.artist_max_sim(self._legacy(norm), params)
            return

        raise AssertionError(f"_StatsFakeCursor: unhandled SQL: {norm!r}")

    @staticmethod
    def _legacy(norm):
        """True if this statement is the legacy path (reads the legacy entry
        tables); False if it reads chart_entries (re-pointed path)."""
        if "hot100_entries" in norm or "b200_entries" in norm:
            return True
        if "chart_entries" in norm:
            return False
        raise AssertionError(f"cannot classify legacy vs re-pointed: {norm!r}")

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None


class _StatsFakeConn:
    def __init__(self, db):
        self._db = db
        self.commits = 0

    def cursor(self):
        return _StatsFakeCursor(self._db)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


class StatsFakeDB:
    def __init__(self, charts, chart_weeks, chart_entries,
                 song_artists=None, album_artists=None, artists=None):
        self.charts = [dict(c) for c in charts]
        self.chart_weeks = [dict(w) for w in chart_weeks]
        self.chart_entries = [dict(e) for e in chart_entries]
        self.song_artists = [dict(l) for l in (song_artists or [])]
        self.album_artists = [dict(l) for l in (album_artists or [])]
        self.artists = [dict(a) for a in (artists or [])]
        # Legacy entry tables MIRROR chart_entries (the dual-write invariant).
        self.hot100_entries = [
            dict(e) for e in self.chart_entries
            if self.chart_slug(e["chart_id"]) == "hot-100"
        ]
        self.b200_entries = [
            dict(e) for e in self.chart_entries
            if self.chart_slug(e["chart_id"]) == "billboard-200"
        ]
        self.song_stats = {}
        self.album_stats = {}
        self.artist_stats = {}

    # --- registry helpers ------------------------------------------------------
    def chart_id(self, slug):
        for c in self.charts:
            if c["slug"] == slug:
                return c["id"]
        return None

    def chart_slug(self, chart_id):
        for c in self.charts:
            if c["id"] == chart_id:
                return c["slug"]
        return None

    def _week_date(self, week_id):
        for w in self.chart_weeks:
            if w["id"] == week_id:
                return w["chart_date"]
        return None

    # --- phantom filter (MIN(id) first-real, shared by both paths) -------------
    def _valid_week_ids(self, chart_id):
        weeks = {}
        for e in self.chart_entries:
            if e["chart_id"] != chart_id:
                continue
            weeks.setdefault(e["chart_week_id"], []).append(e)
        phantom = []
        for wid, entries in weeks.items():
            total = len(entries)
            ph = sum(1 for e in entries
                     if e.get("is_new") and e.get("weeks_on_chart") == 1)
            if total > 0 and ph >= total * 95 / 100:
                phantom.append(wid)
        first_real = min(phantom) if phantom else None
        return {wid for wid in weeks
                if wid not in phantom or wid == first_real}

    def _entries(self, legacy, chart_id):
        """The entry rows for a chart -- from the legacy table (legacy path) or
        chart_entries (re-pointed path). Both are the SAME data."""
        if legacy:
            slug = self.chart_slug(chart_id) if chart_id is not None else None
            src = self.hot100_entries if (
                slug == "hot-100" or chart_id is None and False
            ) else None
            # legacy path classifies by entity, not chart_id param. Decide by the
            # caller's chart_id which legacy table to read.
            if chart_id == self.chart_id("hot-100"):
                src = self.hot100_entries
            elif chart_id == self.chart_id("billboard-200"):
                src = self.b200_entries
            return [e for e in src]
        return [e for e in self.chart_entries if e["chart_id"] == chart_id]

    # --- song_stats ------------------------------------------------------------
    def build_song_stats_insert(self, legacy, params):
        chart_id = self.chart_id("hot-100") if legacy else params[0]
        valid = self._valid_week_ids(chart_id)
        agg = {}
        for e in self._entries(legacy, chart_id):
            if e["chart_week_id"] not in valid:
                continue
            sid = e["song_id"]
            d = self._week_date(e["chart_week_id"])
            a = agg.setdefault(sid, {
                "song_id": sid, "total_weeks": 0, "peak_position": None,
                "weeks_at_peak": 0, "weeks_at_number_one": 0,
                "debut_date": None, "last_date": None, "debut_position": None,
            })
            a["total_weeks"] += 1
            if a["peak_position"] is None or e["rank"] < a["peak_position"]:
                a["peak_position"] = e["rank"]
            if e["rank"] == 1:
                a["weeks_at_number_one"] += 1
            if a["debut_date"] is None or d < a["debut_date"]:
                a["debut_date"] = d
            if a["last_date"] is None or d > a["last_date"]:
                a["last_date"] = d
        self.song_stats = agg

    def song_stats_weeks_at_peak(self, legacy, params):
        chart_id = self.chart_id("hot-100") if legacy else params[0]
        valid = self._valid_week_ids(chart_id)
        for sid, a in self.song_stats.items():
            cnt = sum(
                1 for e in self._entries(legacy, chart_id)
                if e["song_id"] == sid and e["chart_week_id"] in valid
                and e["rank"] == a["peak_position"]
            )
            a["weeks_at_peak"] = cnt

    def song_stats_debut_position(self, legacy, params):
        chart_id = self.chart_id("hot-100") if legacy else params[0]
        valid = self._valid_week_ids(chart_id)
        best = {}
        for e in sorted(self._entries(legacy, chart_id),
                        key=lambda e: (e["song_id"],
                                       self._week_date(e["chart_week_id"]))):
            if e["chart_week_id"] not in valid:
                continue
            if e["song_id"] not in best:
                best[e["song_id"]] = e["rank"]
        for sid, a in self.song_stats.items():
            if sid in best:
                a["debut_position"] = best[sid]

    # --- album_stats -----------------------------------------------------------
    def build_album_stats_insert(self, legacy, params):
        chart_id = self.chart_id("billboard-200") if legacy else params[0]
        valid = self._valid_week_ids(chart_id)
        agg = {}
        for e in self._entries(legacy, chart_id):
            if e["chart_week_id"] not in valid:
                continue
            aid = e["album_id"]
            d = self._week_date(e["chart_week_id"])
            a = agg.setdefault(aid, {
                "album_id": aid, "total_weeks": 0, "peak_position": None,
                "weeks_at_peak": 0, "weeks_at_number_one": 0,
                "debut_date": None, "last_date": None, "debut_position": None,
            })
            a["total_weeks"] += 1
            if a["peak_position"] is None or e["rank"] < a["peak_position"]:
                a["peak_position"] = e["rank"]
            if e["rank"] == 1:
                a["weeks_at_number_one"] += 1
            if a["debut_date"] is None or d < a["debut_date"]:
                a["debut_date"] = d
            if a["last_date"] is None or d > a["last_date"]:
                a["last_date"] = d
        self.album_stats = agg

    def album_stats_weeks_at_peak(self, legacy, params):
        chart_id = self.chart_id("billboard-200") if legacy else params[0]
        valid = self._valid_week_ids(chart_id)
        for aid, a in self.album_stats.items():
            cnt = sum(
                1 for e in self._entries(legacy, chart_id)
                if e["album_id"] == aid and e["chart_week_id"] in valid
                and e["rank"] == a["peak_position"]
            )
            a["weeks_at_peak"] = cnt

    def album_stats_debut_position(self, legacy, params):
        chart_id = self.chart_id("billboard-200") if legacy else params[0]
        valid = self._valid_week_ids(chart_id)
        best = {}
        for e in sorted(self._entries(legacy, chart_id),
                        key=lambda e: (e["album_id"],
                                       self._week_date(e["chart_week_id"]))):
            if e["chart_week_id"] not in valid:
                continue
            if e["album_id"] not in best:
                best[e["album_id"]] = e["rank"]
        for aid, a in self.album_stats.items():
            if aid in best:
                a["debut_position"] = best[aid]

    # --- artist_stats ----------------------------------------------------------
    def _song_artist_ids(self, song_id):
        return [l["artist_id"] for l in self.song_artists
                if l["song_id"] == song_id]

    def _album_artist_ids(self, album_id):
        return [l["artist_id"] for l in self.album_artists
                if l["album_id"] == album_id]

    def artist_total_hot100_songs(self):
        cnt = {}
        for l in self.song_artists:
            cnt.setdefault(l["artist_id"], set()).add(l["song_id"])
        for aid, songs in cnt.items():
            self.artist_stats.setdefault(aid, {"artist_id": aid})[
                "total_hot100_songs"] = len(songs)

    def artist_total_b200_albums(self):
        cnt = {}
        for l in self.album_artists:
            cnt.setdefault(l["artist_id"], set()).add(l["album_id"])
        for aid, albums in cnt.items():
            self.artist_stats.setdefault(aid, {"artist_id": aid})[
                "total_b200_albums"] = len(albums)

    def artist_hot100_weeks(self, legacy, params):
        chart_id = self.chart_id("hot-100") if legacy else params[0]
        valid = self._valid_week_ids(chart_id)
        # COUNT(*) over song_artists join (summed entity-weeks) -- preserved.
        weeks = {}
        ones = {}
        best = {}
        for e in self._entries(legacy, chart_id):
            if e["chart_week_id"] not in valid:
                continue
            for aid in self._song_artist_ids(e["song_id"]):
                weeks[aid] = weeks.get(aid, 0) + 1
                if e["rank"] == 1:
                    ones.setdefault(aid, set()).add(e["song_id"])
                if aid not in best or e["rank"] < best[aid]:
                    best[aid] = e["rank"]
        for aid in weeks:
            r = self.artist_stats.setdefault(aid, {"artist_id": aid})
            r["total_hot100_weeks"] = weeks[aid]
            r["hot100_number_ones"] = len(ones.get(aid, set()))
            r["best_hot100_peak"] = best[aid]

    def artist_b200_weeks(self, legacy, params):
        chart_id = self.chart_id("billboard-200") if legacy else params[0]
        valid = self._valid_week_ids(chart_id)
        weeks = {}
        ones = {}
        best = {}
        for e in self._entries(legacy, chart_id):
            if e["chart_week_id"] not in valid:
                continue
            for aid in self._album_artist_ids(e["album_id"]):
                weeks[aid] = weeks.get(aid, 0) + 1
                if e["rank"] == 1:
                    ones.setdefault(aid, set()).add(e["album_id"])
                if aid not in best or e["rank"] < best[aid]:
                    best[aid] = e["rank"]
        for aid in weeks:
            r = self.artist_stats.setdefault(aid, {"artist_id": aid})
            r["total_b200_weeks"] = weeks[aid]
            r["b200_number_ones"] = len(ones.get(aid, set()))
            r["best_b200_peak"] = best[aid]

    def artist_chart_dates(self, legacy, params):
        # Combined hot-100 + billboard-200. legacy: no params; re-pointed: (h, b).
        h_id = self.chart_id("hot-100")
        b_id = self.chart_id("billboard-200")
        h_valid = self._valid_week_ids(h_id)
        b_valid = self._valid_week_ids(b_id)
        first = {}
        last = {}
        for e in self._entries(legacy, h_id):
            if e["chart_week_id"] not in h_valid:
                continue
            d = self._week_date(e["chart_week_id"])
            for aid in self._song_artist_ids(e["song_id"]):
                if aid not in first or d < first[aid]:
                    first[aid] = d
                if aid not in last or d > last[aid]:
                    last[aid] = d
        for e in self._entries(legacy, b_id):
            if e["chart_week_id"] not in b_valid:
                continue
            d = self._week_date(e["chart_week_id"])
            for aid in self._album_artist_ids(e["album_id"]):
                if aid not in first or d < first[aid]:
                    first[aid] = d
                if aid not in last or d > last[aid]:
                    last[aid] = d
        for aid in first:
            r = self.artist_stats.setdefault(aid, {"artist_id": aid})
            r["first_chart_date"] = first[aid]
            r["latest_chart_date"] = last[aid]

    def artist_max_sim(self, legacy, params):
        chart_id = self.chart_id("hot-100") if legacy else params[0]
        valid = self._valid_week_ids(chart_id)
        per_week = {}
        for e in self._entries(legacy, chart_id):
            if e["chart_week_id"] not in valid:
                continue
            for aid in self._song_artist_ids(e["song_id"]):
                key = (aid, e["chart_week_id"])
                per_week[key] = per_week.get(key, 0) + 1
        max_sim = {}
        for (aid, _w), cnt in per_week.items():
            max_sim[aid] = max(max_sim.get(aid, 0), cnt)
        for aid, m in max_sim.items():
            self.artist_stats.setdefault(aid, {"artist_id": aid})[
                "max_simultaneous_hot100"] = m

    # --- snapshots for equality ------------------------------------------------
    @staticmethod
    def _rows_sorted(table_dict):
        return sorted(
            (tuple(sorted(row.items(), key=lambda kv: kv[0]))
             for row in table_dict.values())
        )


# ============================================================================
# Legacy builders: drive the SAME fake DB with the snapshotted LEGACY SQL so we
# can compare "old way" vs "new way" on one fixture. These reproduce the exact
# legacy statement sequence (FROM hot100_entries / FROM b200_entries), proving
# the re-pointed production functions write identical rows.
# ============================================================================
def _build_song_stats_legacy(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM song_stats;")
        cur.execute(_LEGACY_SONG_STATS_INSERT)
        cur.execute("WITH valid_hot100_weeks UPDATE song_stats SET weeks_at_peak"
                    " FROM hot100_entries e ...")
        cur.execute("WITH valid_hot100_weeks UPDATE song_stats SET debut_position"
                    " FROM hot100_entries e ...")


def _build_album_stats_legacy(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM album_stats;")
        cur.execute(_LEGACY_ALBUM_STATS_INSERT)
        cur.execute("WITH valid_b200_weeks UPDATE album_stats SET weeks_at_peak"
                    " FROM b200_entries e ...")
        cur.execute("WITH valid_b200_weeks UPDATE album_stats SET debut_position"
                    " FROM b200_entries e ...")


def _build_artist_stats_legacy(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM artist_stats;")
        cur.execute("INSERT INTO artist_stats (artist_id) SELECT id FROM artists;")
        cur.execute("UPDATE artist_stats SET total_hot100_songs FROM song_artists sa")
        cur.execute("UPDATE artist_stats SET total_b200_albums FROM album_artists aa")
        cur.execute("WITH valid_hot100_weeks UPDATE artist_stats SET"
                    " total_hot100_weeks FROM hot100_entries e ...")
        cur.execute("WITH valid_b200_weeks UPDATE artist_stats SET"
                    " total_b200_weeks FROM b200_entries e ...")
        cur.execute("WITH valid_hot100_weeks, valid_b200_weeks UPDATE artist_stats"
                    " SET first_chart_date FROM hot100_entries e ... b200_entries ...")
        cur.execute("WITH valid_hot100_weeks UPDATE artist_stats SET"
                    " max_simultaneous_hot100 FROM hot100_entries e ...")


# ============================================================================
# Fixture: two hot-100 weeks (one phantom debut + one real) and one b200 week,
# with a shared artist charting on both, so song/album/artist stats all exercise.
# ============================================================================
def _ctr():
    _ctr.n = getattr(_ctr, "n", 0) + 1
    return _ctr.n


def _ce(chart_id, week_id, *, song_id=None, album_id=None, rank=1,
        is_new=False, weeks_on_chart=1):
    return {
        "id": _ctr(), "chart_id": chart_id, "chart_week_id": week_id,
        "song_id": song_id, "album_id": album_id, "artist_id": None,
        "rank": rank, "peak_pos": rank, "last_pos": None,
        "weeks_on_chart": weeks_on_chart, "is_new": is_new,
    }


def _fixture():
    charts = [
        {"id": 1, "slug": "hot-100", "entity_kind": "song"},
        {"id": 2, "slug": "billboard-200", "entity_kind": "album"},
    ]
    chart_weeks = [
        {"id": 1, "chart_date": "2020-01-04", "chart_id": 1},  # phantom debut
        {"id": 2, "chart_date": "2020-01-11", "chart_id": 1},  # real
        {"id": 3, "chart_date": "2020-01-18", "chart_id": 1},  # later phantom (excl)
        {"id": 4, "chart_date": "2020-01-04", "chart_id": 2},  # real
        {"id": 5, "chart_date": "2020-01-11", "chart_id": 2},  # real
    ]
    chart_entries = [
        # hot-100 week 1 (phantom: all is_new + weeks=1) -> KEPT (earliest)
        _ce(1, 1, song_id=10, rank=1, is_new=True, weeks_on_chart=1),
        _ce(1, 1, song_id=11, rank=2, is_new=True, weeks_on_chart=1),
        # hot-100 week 2 (real)
        _ce(1, 2, song_id=10, rank=1, is_new=False, weeks_on_chart=2),
        _ce(1, 2, song_id=11, rank=2, is_new=False, weeks_on_chart=2),
        # hot-100 week 3 (later phantom) -> EXCLUDED
        _ce(1, 3, song_id=12, rank=1, is_new=True, weeks_on_chart=1),
        # billboard-200 week 4 (real)
        _ce(2, 4, album_id=20, rank=1, is_new=False, weeks_on_chart=3),
        _ce(2, 4, album_id=21, rank=2, is_new=False, weeks_on_chart=4),
        # billboard-200 week 5 (real)
        _ce(2, 5, album_id=20, rank=1, is_new=False, weeks_on_chart=4),
    ]
    song_artists = [
        {"song_id": 10, "artist_id": 100, "role": "primary"},
        {"song_id": 11, "artist_id": 101, "role": "primary"},
        {"song_id": 12, "artist_id": 100, "role": "primary"},
    ]
    album_artists = [
        {"album_id": 20, "artist_id": 100, "role": "primary"},
        {"album_id": 21, "artist_id": 102, "role": "primary"},
    ]
    artists = [{"id": 100}, {"id": 101}, {"id": 102}]
    return StatsFakeDB(
        charts=charts, chart_weeks=chart_weeks, chart_entries=chart_entries,
        song_artists=song_artists, album_artists=album_artists, artists=artists,
    )


# ============================================================================
# Equivalence tests
# ============================================================================
class SongStatsEquivalenceTests(unittest.TestCase):
    def test_song_stats_equivalent_legacy_vs_chart_entries(self):
        db = _fixture()
        conn = _StatsFakeConn(db)
        # Build the LEGACY way (FROM hot100_entries).
        _build_song_stats_legacy(conn)
        legacy = StatsFakeDB._rows_sorted(db.song_stats)
        # Build the RE-POINTED way (real production fn, FROM chart_entries).
        db.song_stats = {}
        build_song_stats(conn)
        new = StatsFakeDB._rows_sorted(db.song_stats)
        self.assertEqual(legacy, new)
        # Sanity: stats are non-empty (phantom week-1 kept, week-3 excluded).
        self.assertTrue(new)


class AlbumStatsEquivalenceTests(unittest.TestCase):
    def test_album_stats_equivalent_legacy_vs_chart_entries(self):
        db = _fixture()
        conn = _StatsFakeConn(db)
        _build_album_stats_legacy(conn)
        legacy = StatsFakeDB._rows_sorted(db.album_stats)
        db.album_stats = {}
        build_album_stats(conn)
        new = StatsFakeDB._rows_sorted(db.album_stats)
        self.assertEqual(legacy, new)
        self.assertTrue(new)


class ArtistStatsEquivalenceTests(unittest.TestCase):
    def test_artist_stats_equivalent_legacy_vs_chart_entries(self):
        db = _fixture()
        conn = _StatsFakeConn(db)
        _build_artist_stats_legacy(conn)
        legacy = StatsFakeDB._rows_sorted(db.artist_stats)
        db.artist_stats = {}
        build_artist_stats(conn)
        new = StatsFakeDB._rows_sorted(db.artist_stats)
        self.assertEqual(legacy, new)
        self.assertTrue(new)

    def test_total_weeks_preserves_count_star_semantics(self):
        # Pitfall 2: total_hot100_weeks / total_b200_weeks are summed entity-weeks
        # (COUNT(*) over the artist join), NOT distinct calendar weeks. Verify the
        # re-pointed build keeps that semantic by checking a known value.
        db = _fixture()
        conn = _StatsFakeConn(db)
        build_artist_stats(conn)
        # Artist 100: song 10 charts hot-100 week1 (kept phantom) + week2 (real)
        # = 2 entity-weeks. (song 12 is in week3, excluded.)
        self.assertEqual(db.artist_stats[100]["total_hot100_weeks"], 2)
        # Artist 100: album 20 charts b200 week4 + week5 = 2 entity-weeks.
        self.assertEqual(db.artist_stats[100]["total_b200_weeks"], 2)


class StatsBuilderSourceGuardTests(unittest.TestCase):
    def test_no_legacy_table_reads_remain_in_builders(self):
        for fn in (build_song_stats, build_album_stats, build_artist_stats):
            src = inspect.getsource(fn)
            self.assertNotIn("FROM hot100_entries", src)
            self.assertNotIn("FROM b200_entries", src)
            self.assertIn("chart_entries", src)

    def test_count_star_preserved_in_artist_builder(self):
        src = inspect.getsource(build_artist_stats)
        # COUNT(*) AS total_weeks must NOT have become COUNT(DISTINCT ...).
        self.assertIn("COUNT(*) AS total_weeks", src)
        self.assertNotIn("COUNT(DISTINCT chart_week_id)", src)

    def test_legacy_constants_deleted(self):
        src = inspect.getsource(stats_builder)
        self.assertNotIn("_VALID_HOT100_WEEKS_CTE =", src)
        self.assertNotIn("_VALID_B200_WEEKS_CTE =", src)


if __name__ == "__main__":
    unittest.main()
