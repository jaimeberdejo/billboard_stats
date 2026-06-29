"""Stats-builder tests for the Phase 15 ``*_stats`` single-store re-point.

Phase 15 retired the bifurcated v1.0 entry tables; ``build_song_stats`` /
``build_album_stats`` / ``build_artist_stats`` now read the polymorphic
``chart_entries`` table filtered by ``chart_id`` (under the parametric
``valid_weeks_cte``). These tests pin the resulting ``*_stats`` rows against a
fixed fixture and guard the load-bearing semantics that the original cutover
(15-01) proved equivalent to the legacy build:

* the COUNT(*) summed-entity-weeks semantics for the artist rollup (Pitfall 2);
* the phantom-week filter (MIN(id) first-real week);
* a SOURCE guard that the builders read ``chart_entries`` and the legacy
  constants are gone.

The earlier build-both-ways equivalence (legacy SQL vs re-pointed SQL on one
fixture) served its one-time cutover purpose in 15-01 and is now permanently
locked by the source-guard suite below; with the legacy tables dropped there is
nothing left to compare against, so this module asserts the re-pointed build
directly over ``chart_entries``.

These tests run entirely against an in-memory fake DB layer (no psycopg2, no
network). The fake DB does NOT execute literal SQL text -- it interprets the
statement *shapes* the builders emit (same harness style as
``test_stats_builder_parametric.py``), computing the resulting rows in Python.
"""

import inspect
import unittest

from billboard_stats.etl import stats_builder
from billboard_stats.etl.stats_builder import (
    build_album_stats,
    build_artist_stats,
    build_song_stats,
)


# ============================================================================
# In-memory fake DB interpreting the RE-POINTED *_stats statement SHAPES over
# chart_entries (the sole entry store) + song_artists / album_artists + artists,
# and the three *_stats target tables.
# ============================================================================
class _StatsFakeCursor:
    """Interprets the *_stats statement SHAPES the re-pointed builders emit,
    computing the resulting rows in Python.

    Dispatch is by statement shape (slug->chart_id resolution, DELETE, the
    artist seed, and an INSERT/UPDATE per stats table). Every entry read comes
    from ``chart_entries`` filtered by the bound chart_id param.
    """

    def __init__(self, db):
        self._db = db
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        norm = " ".join(sql.split()).strip().lower()
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
            self._db.build_song_stats_insert(params)
            return
        if "update song_stats" in norm and "weeks_at_peak" in norm:
            self._db.song_stats_weeks_at_peak(params)
            return
        if "update song_stats" in norm and "debut_position" in norm:
            self._db.song_stats_debut_position(params)
            return

        # --- album_stats build -------------------------------------------------
        if "insert into album_stats" in norm:
            self._db.build_album_stats_insert(params)
            return
        if "update album_stats" in norm and "weeks_at_peak" in norm:
            self._db.album_stats_weeks_at_peak(params)
            return
        if "update album_stats" in norm and "debut_position" in norm:
            self._db.album_stats_debut_position(params)
            return

        # --- artist_stats updates ----------------------------------------------
        if "update artist_stats" in norm and "total_hot100_songs" in norm:
            self._db.artist_total_hot100_songs()
            return
        if "update artist_stats" in norm and "total_b200_albums" in norm:
            self._db.artist_total_b200_albums()
            return
        if "update artist_stats" in norm and "total_hot100_weeks" in norm:
            self._db.artist_hot100_weeks(params)
            return
        if "update artist_stats" in norm and "total_b200_weeks" in norm:
            self._db.artist_b200_weeks(params)
            return
        if "update artist_stats" in norm and "first_chart_date" in norm:
            self._db.artist_chart_dates(params)
            return
        if "update artist_stats" in norm and "max_simultaneous_hot100" in norm:
            self._db.artist_max_sim(params)
            return

        raise AssertionError(f"_StatsFakeCursor: unhandled SQL: {norm!r}")

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
        self.song_stats = {}
        self.album_stats = {}
        self.artist_stats = {}

    # --- registry helpers ------------------------------------------------------
    def chart_id(self, slug):
        for c in self.charts:
            if c["slug"] == slug:
                return c["id"]
        return None

    def _week_date(self, week_id):
        for w in self.chart_weeks:
            if w["id"] == week_id:
                return w["chart_date"]
        return None

    # --- phantom filter (MIN(id) first-real) -----------------------------------
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

    def _entries(self, chart_id):
        """The chart_entries rows for a chart (the sole entry store)."""
        return [e for e in self.chart_entries if e["chart_id"] == chart_id]

    # --- song_stats ------------------------------------------------------------
    def build_song_stats_insert(self, params):
        chart_id = params[0]
        valid = self._valid_week_ids(chart_id)
        agg = {}
        for e in self._entries(chart_id):
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

    def song_stats_weeks_at_peak(self, params):
        chart_id = params[0]
        valid = self._valid_week_ids(chart_id)
        for sid, a in self.song_stats.items():
            cnt = sum(
                1 for e in self._entries(chart_id)
                if e["song_id"] == sid and e["chart_week_id"] in valid
                and e["rank"] == a["peak_position"]
            )
            a["weeks_at_peak"] = cnt

    def song_stats_debut_position(self, params):
        chart_id = params[0]
        valid = self._valid_week_ids(chart_id)
        best = {}
        for e in sorted(self._entries(chart_id),
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
    def build_album_stats_insert(self, params):
        chart_id = params[0]
        valid = self._valid_week_ids(chart_id)
        agg = {}
        for e in self._entries(chart_id):
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

    def album_stats_weeks_at_peak(self, params):
        chart_id = params[0]
        valid = self._valid_week_ids(chart_id)
        for aid, a in self.album_stats.items():
            cnt = sum(
                1 for e in self._entries(chart_id)
                if e["album_id"] == aid and e["chart_week_id"] in valid
                and e["rank"] == a["peak_position"]
            )
            a["weeks_at_peak"] = cnt

    def album_stats_debut_position(self, params):
        chart_id = params[0]
        valid = self._valid_week_ids(chart_id)
        best = {}
        for e in sorted(self._entries(chart_id),
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

    def artist_hot100_weeks(self, params):
        chart_id = params[0]
        valid = self._valid_week_ids(chart_id)
        # COUNT(*) over song_artists join (summed entity-weeks) -- preserved.
        weeks = {}
        ones = {}
        best = {}
        for e in self._entries(chart_id):
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

    def artist_b200_weeks(self, params):
        chart_id = params[0]
        valid = self._valid_week_ids(chart_id)
        weeks = {}
        ones = {}
        best = {}
        for e in self._entries(chart_id):
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

    def artist_chart_dates(self, params):
        # Combined hot-100 + billboard-200; re-pointed params: (hot_id, b200_id).
        h_id = self.chart_id("hot-100")
        b_id = self.chart_id("billboard-200")
        h_valid = self._valid_week_ids(h_id)
        b_valid = self._valid_week_ids(b_id)
        first = {}
        last = {}
        for e in self._entries(h_id):
            if e["chart_week_id"] not in h_valid:
                continue
            d = self._week_date(e["chart_week_id"])
            for aid in self._song_artist_ids(e["song_id"]):
                if aid not in first or d < first[aid]:
                    first[aid] = d
                if aid not in last or d > last[aid]:
                    last[aid] = d
        for e in self._entries(b_id):
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

    def artist_max_sim(self, params):
        chart_id = params[0]
        valid = self._valid_week_ids(chart_id)
        per_week = {}
        for e in self._entries(chart_id):
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
# Re-pointed build assertions (chart_entries is the sole store)
# ============================================================================
class SongStatsBuildTests(unittest.TestCase):
    def test_song_stats_built_over_chart_entries(self):
        db = _fixture()
        conn = _StatsFakeConn(db)
        build_song_stats(conn)
        # Phantom week-1 kept, week-3 excluded -> stats are non-empty.
        self.assertTrue(db.song_stats)
        # Song 10 charts in week1 (kept phantom) + week2 (real) = 2 weeks.
        self.assertEqual(db.song_stats[10]["total_weeks"], 2)
        # Song 12 only appears in the EXCLUDED later-phantom week -> not present.
        self.assertNotIn(12, db.song_stats)


class AlbumStatsBuildTests(unittest.TestCase):
    def test_album_stats_built_over_chart_entries(self):
        db = _fixture()
        conn = _StatsFakeConn(db)
        build_album_stats(conn)
        self.assertTrue(db.album_stats)
        # Album 20 charts in b200 week4 + week5 = 2 weeks.
        self.assertEqual(db.album_stats[20]["total_weeks"], 2)


class ArtistStatsBuildTests(unittest.TestCase):
    def test_artist_stats_built_over_chart_entries(self):
        db = _fixture()
        conn = _StatsFakeConn(db)
        build_artist_stats(conn)
        self.assertTrue(db.artist_stats)

    def test_total_weeks_preserves_count_star_semantics(self):
        # Pitfall 2: total_hot100_weeks / total_b200_weeks are summed entity-weeks
        # (COUNT(*) over the artist join), NOT distinct calendar weeks.
        db = _fixture()
        conn = _StatsFakeConn(db)
        build_artist_stats(conn)
        # Artist 100: song 10 charts hot-100 week1 (kept phantom) + week2 (real)
        # = 2 entity-weeks. (song 12 is in week3, excluded.)
        self.assertEqual(db.artist_stats[100]["total_hot100_weeks"], 2)
        # Artist 100: album 20 charts b200 week4 + week5 = 2 entity-weeks.
        self.assertEqual(db.artist_stats[100]["total_b200_weeks"], 2)


# ============================================================================
# Source guards: the builders read chart_entries and the legacy reads/constants
# are gone (these permanently lock the 15-01 cutover).
# ============================================================================
class StatsBuilderSourceGuardTests(unittest.TestCase):
    def test_builders_read_chart_entries(self):
        for fn in (build_song_stats, build_album_stats, build_artist_stats):
            src = inspect.getsource(fn)
            self.assertIn("chart_entries", src)

    def test_count_star_preserved_in_artist_builder(self):
        src = inspect.getsource(build_artist_stats)
        # COUNT(*) AS total_weeks must NOT have become COUNT(DISTINCT ...).
        self.assertIn("COUNT(*) AS total_weeks", src)
        self.assertNotIn("COUNT(DISTINCT chart_week_id)", src)

    def test_legacy_constants_deleted(self):
        src = inspect.getsource(stats_builder)
        self.assertNotIn("_VALID_HOT100_WEEKS_CTE =", src)


if __name__ == "__main__":
    unittest.main()
