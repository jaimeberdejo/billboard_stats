"""Idempotent artist-identity reconciliation migration (DATA-05).

The historical over-eager parser shattered multi-part acts into standalone
fragment rows — for example the act "Earth, Wind & Fire" was stored as three
separate artists "Earth", "Wind", and "Fire", each carrying its own
song_artists / album_artists links. Plan 01 fixed the parser so NEW loads stay
whole, but the already-stored fragments still pollute the join tables. This
script heals them: it finds each fragment cluster, repoints its links onto the
canonical artist (deduping collisions), and deletes the now-orphaned fragment
rows.

Design / safety contract (D-07, D-07a, D-07b, D-07c):

* DB access goes through an INJECTABLE connection so tests can pass an in-memory
  fake. The SQL is written to run unchanged against a real PostgreSQL when the
  OPERATOR applies it via docs/RECONCILIATION.md.
* --dry-run reports every fragment -> canonical merge and the link repoints it
  WOULD make, writing nothing, and exits 0.
* A non-dry run performs everything in a SINGLE transaction: repoint
  song_artists / album_artists onto the canonical id with ON CONFLICT DO NOTHING
  semantics (insert canonical link, then delete the fragment link), then delete
  orphaned fragment artist_stats and artists rows. It commits only if every
  before/after invariant holds; on any violated invariant it rolls back and
  raises.
* Invariants: distinct song count and distinct album count are unchanged; no
  song or album is left with zero artists; total (song_artists + album_artists)
  link rows only DECREASE, via dedupe.
* Idempotent: detection is data-driven, so once the fragments are gone a re-run
  finds nothing and is a clean no-op. There is no "already ran" flag.
* This module NEVER connects to production during automated execution and NEVER
  rebuilds artist_stats — those are operator steps in the runbook.
"""

from __future__ import annotations

import argparse
import logging
from typing import Dict, Iterable, List, Optional, Tuple

from billboard_stats.etl.artist_aliases import is_genuine_alias
from billboard_stats.etl.artist_parser import (
    _PROTECTED_AMPERSAND_ACTS,
    _GROUP_SPLIT,
    _normalize_key,
)

logger = logging.getLogger(__name__)


class ReconciliationInvariantError(RuntimeError):
    """Raised when a before/after safety invariant is violated; triggers rollback."""


# ----------------------------------------------------------------------------
# Fragment detection
# ----------------------------------------------------------------------------
def _build_known_multipart_acts(known_acts: Optional[Iterable[str]]) -> List[str]:
    """Return canonical multi-part act names (curated allowlist UNION DB-derived).

    Mirrors the parser's known-acts source (D-02): the curated
    ``_PROTECTED_AMPERSAND_ACTS`` allowlist plus any caller-supplied canonical
    names (the reconcile layer passes DB-derived ``artists.name`` values that
    contain a comma or " & "). Only names that actually contain an internal
    separator are multi-part acts worth healing.
    """
    seen: Dict[str, str] = {}
    for name in _PROTECTED_AMPERSAND_ACTS:
        seen[_normalize_key(name)] = name
    if known_acts:
        for name in known_acts:
            if name and name.strip():
                seen[_normalize_key(name)] = name.strip()

    multipart: List[str] = []
    for name in seen.values():
        if "," in name or " & " in name:
            multipart.append(name)
    return multipart


def _fragment_names_for(act_name: str) -> List[str]:
    """Split a canonical multi-part act name into its component fragment names.

    Reuses the parser's group-split regex so fragment derivation stays consistent
    with how the old parser would have shattered the act in the first place.
    """
    parts = _GROUP_SPLIT.split(act_name)
    fragments = []
    for part in parts:
        piece = part.strip()
        if piece and _normalize_key(piece) != _normalize_key(act_name):
            fragments.append(piece)
    return fragments


def _detect_fragment_clusters(
    artists_by_name: Dict[str, int],
    known_acts: Optional[Iterable[str]],
) -> List[Tuple[str, int, List[Tuple[str, int]]]]:
    """Find fragment clusters present in the artists table.

    ``artists_by_name`` maps normalized artist name -> artist_id (built from a
    single SELECT of the artists table). For each canonical multi-part act that
    exists in the table, collect the fragment artist rows that ALSO exist and are
    neither a genuine alias nor a legitimate standalone act (i.e. not itself a
    canonical multi-part act and not equal to the canonical name).

    Returns a list of (canonical_name, canonical_id, [(fragment_name,
    fragment_id), ...]) for clusters that have at least one fragment to merge.
    """
    canonical_keys = {
        _normalize_key(a) for a in _build_known_multipart_acts(known_acts)
    }
    clusters = []
    for act_name in _build_known_multipart_acts(known_acts):
        canonical_key = _normalize_key(act_name)
        canonical_id = artists_by_name.get(canonical_key)
        if canonical_id is None:
            # The canonical act itself is not in the DB — nothing to merge onto.
            continue

        fragments: List[Tuple[str, int]] = []
        for frag_name in _fragment_names_for(act_name):
            frag_key = _normalize_key(frag_name)
            if frag_key == canonical_key:
                continue
            # A genuine alias is never treated as a fragment.
            if is_genuine_alias(frag_name):
                continue
            # A fragment that is itself a known multi-part canonical act is a
            # legitimate standalone act, not a shard to merge.
            if frag_key in canonical_keys:
                continue
            frag_id = artists_by_name.get(frag_key)
            if frag_id is None:
                continue
            if frag_id == canonical_id:
                continue
            fragments.append((frag_name, frag_id))

        if fragments:
            clusters.append((act_name, canonical_id, fragments))
    return clusters


# ----------------------------------------------------------------------------
# Invariant snapshot
# ----------------------------------------------------------------------------
def _capture_counts(cur) -> Dict[str, int]:
    """Capture invariant counts from the current DB state."""
    counts: Dict[str, int] = {}

    cur.execute("SELECT COUNT(DISTINCT song_id) FROM song_artists;")
    counts["distinct_songs"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT album_id) FROM album_artists;")
    counts["distinct_albums"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM song_artists;")
    counts["song_links"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM album_artists;")
    counts["album_links"] = cur.fetchone()[0]

    return counts


def _assert_invariants(before: Dict[str, int], after: Dict[str, int]) -> None:
    """Assert the reconciliation safety invariants, raising on any violation."""
    if after["distinct_songs"] != before["distinct_songs"]:
        raise ReconciliationInvariantError(
            "distinct song count changed: "
            f"{before['distinct_songs']} -> {after['distinct_songs']} "
            "(a song lost all its artists)"
        )
    if after["distinct_albums"] != before["distinct_albums"]:
        raise ReconciliationInvariantError(
            "distinct album count changed: "
            f"{before['distinct_albums']} -> {after['distinct_albums']} "
            "(an album lost all its artists)"
        )
    before_links = before["song_links"] + before["album_links"]
    after_links = after["song_links"] + after["album_links"]
    if after_links > before_links:
        raise ReconciliationInvariantError(
            f"total link rows increased: {before_links} -> {after_links} "
            "(repoint must only dedupe, never add)"
        )


# ----------------------------------------------------------------------------
# Repoint + orphan delete
# ----------------------------------------------------------------------------
def _repoint_and_delete(cur, canonical_id: int, fragment_ids: List[int]) -> None:
    """Repoint a fragment cluster's links onto the canonical id, then delete orphans.

    For each join table, insert the canonical link for every song/album the
    fragments touch (ON CONFLICT DO NOTHING dedupes against an existing canonical
    link), then delete the fragment link rows. Finally delete the fragment
    artist_stats and artists rows. Total link rows can only decrease.
    """
    # song_artists: insert canonical links, then drop fragment links.
    cur.execute(
        """
        INSERT INTO song_artists (song_id, artist_id, role)
        SELECT sa.song_id, %s, sa.role
        FROM song_artists sa
        WHERE sa.artist_id = ANY(%s)
        ON CONFLICT (song_id, artist_id) DO NOTHING;
        """,
        (canonical_id, fragment_ids),
    )
    cur.execute(
        "DELETE FROM song_artists WHERE artist_id = ANY(%s);",
        (fragment_ids,),
    )

    # album_artists: insert canonical links, then drop fragment links.
    cur.execute(
        """
        INSERT INTO album_artists (album_id, artist_id, role)
        SELECT aa.album_id, %s, aa.role
        FROM album_artists aa
        WHERE aa.artist_id = ANY(%s)
        ON CONFLICT (album_id, artist_id) DO NOTHING;
        """,
        (canonical_id, fragment_ids),
    )
    cur.execute(
        "DELETE FROM album_artists WHERE artist_id = ANY(%s);",
        (fragment_ids,),
    )

    # Delete the now-orphaned fragment stats and artist rows.
    cur.execute(
        "DELETE FROM artist_stats WHERE artist_id = ANY(%s);",
        (fragment_ids,),
    )
    cur.execute(
        "DELETE FROM artists WHERE id = ANY(%s);",
        (fragment_ids,),
    )


# ----------------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------------
def reconcile(
    conn,
    *,
    dry_run: bool = False,
    known_acts: Optional[Iterable[str]] = None,
) -> Dict[str, object]:
    """Reconcile fragment artists into their canonical artist.

    Args:
        conn: An injectable DB connection exposing ``cursor()`` (context
            manager), ``commit()``, and ``rollback()``.
        dry_run: When True, compute and report the planned merges and exit
            without writing.
        known_acts: Optional canonical act names (DB-derived ``artists.name``
            values) unioned with the curated allowlist for detection.

    Returns:
        A report dict: ``{"dry_run": bool, "clusters": [...], "merged_fragments":
        int, "before": {...}, "after": {...} or None}``.
    """
    report: Dict[str, object] = {
        "dry_run": dry_run,
        "clusters": [],
        "merged_fragments": 0,
        "before": None,
        "after": None,
    }

    try:
        with conn.cursor() as cur:
            # Load the full artists table once to detect fragment clusters.
            cur.execute("SELECT id, name FROM artists;")
            artists_by_name: Dict[str, int] = {}
            for row in cur.fetchall():
                artist_id, name = row[0], row[1]
                artists_by_name[_normalize_key(name)] = artist_id

            clusters = _detect_fragment_clusters(artists_by_name, known_acts)

            planned = []
            for canonical_name, canonical_id, fragments in clusters:
                planned.append(
                    {
                        "canonical_name": canonical_name,
                        "canonical_id": canonical_id,
                        "fragments": [
                            {"name": fn, "id": fid} for fn, fid in fragments
                        ],
                    }
                )
            report["clusters"] = planned
            report["merged_fragments"] = sum(
                len(c["fragments"]) for c in planned
            )

            if not clusters:
                logger.info("No fragment clusters found — nothing to reconcile.")
                return report

            for canonical_name, canonical_id, fragments in clusters:
                frag_desc = ", ".join(f"{fn}(#{fid})" for fn, fid in fragments)
                logger.info(
                    "Merge plan: %s(#%s) <- %s",
                    canonical_name,
                    canonical_id,
                    frag_desc,
                )

            if dry_run:
                logger.info(
                    "Dry run: %d fragment rows across %d clusters would be "
                    "merged; writing nothing.",
                    report["merged_fragments"],
                    len(clusters),
                )
                return report

            before = _capture_counts(cur)
            report["before"] = before

            for _, canonical_id, fragments in clusters:
                fragment_ids = [fid for _, fid in fragments]
                _repoint_and_delete(cur, canonical_id, fragment_ids)

            after = _capture_counts(cur)
            report["after"] = after

            # Roll back if any safety invariant is violated.
            _assert_invariants(before, after)

        conn.commit()
        logger.info(
            "Reconciliation committed: merged %d fragment rows across %d clusters.",
            report["merged_fragments"],
            len(clusters),
        )
        return report
    except Exception:
        conn.rollback()
        raise


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint. The OPERATOR runs this against the real DB per the runbook."""
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile fragment artists into their canonical artist "
            "(operator-applied; see docs/RECONCILIATION.md)."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the planned merges without writing anything.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Lazy DB import so the module imports cleanly in environments without
    # psycopg2 (e.g. the mock-based test environment).
    from billboard_stats.db.connection import get_conn, put_conn

    known_acts = _load_db_known_acts(get_conn, put_conn)

    conn = get_conn()
    try:
        report = reconcile(conn, dry_run=args.dry_run, known_acts=known_acts)
    finally:
        put_conn(conn)

    print(
        f"{'DRY RUN — ' if report['dry_run'] else ''}"
        f"{len(report['clusters'])} cluster(s), "
        f"{report['merged_fragments']} fragment row(s)."
    )
    for cluster in report["clusters"]:
        names = ", ".join(f["name"] for f in cluster["fragments"])
        print(f"  {cluster['canonical_name']} <- {names}")
    return 0


def _load_db_known_acts(get_conn, put_conn) -> List[str]:
    """Read DB-derived canonical multi-part act names (operator/real-DB path)."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name FROM artists "
                "WHERE name LIKE '%,%' OR name LIKE '% & %';"
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        put_conn(conn)


if __name__ == "__main__":
    raise SystemExit(main())
