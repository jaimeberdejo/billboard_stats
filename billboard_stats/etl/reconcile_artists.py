"""Idempotent artist-identity reconciliation migration (DATA-05).

The historical over-eager parser shattered multi-part acts into standalone
fragment rows — for example the act "Earth, Wind & Fire" was stored as three
separate artists "Earth", "Wind", and "Fire", each carrying its own
song_artists / album_artists links. Plan 01 fixed the parser so NEW loads stay
whole, but the already-stored fragments still pollute the join tables. This
script heals them.

Design / safety contract (D-07, D-07a, D-07b, D-07c):

* **Reconciliation is DRIVEN BY RE-PARSING THE RAW CREDITS**, not by re-splitting
  canonical artist names. The source of truth is the stored ``artist_credit``
  strings on ``songs`` and ``albums`` — the very same inputs the loader fed to
  the parser. For each distinct credit we run the NEW ``parse_artist_credit`` to
  get the canonical (name, role) list the credit SHOULD map to today, then
  reconcile the DB's join rows to match that target.

  This is fundamentally safer than the old approach, which derived "fragments"
  by splitting each canonical act NAME on the group-split regex and then
  merged+deleted matching artist rows. That was unsound: members of real acts
  are themselves real standalone artists (solo "Diana Ross", solo "Tina Turner",
  "Tyler"), so the old logic would delete them. Here, an artist is deleted ONLY
  when, after re-deriving every link from the credits, it has ZERO remaining
  links — i.e. no credit's new-parse produces it. Solo Diana Ross is produced by
  her own standalone credits, so she always keeps links and is never deleted. A
  pure shatter like "Wind" (only ever created by the old split, with no
  standalone "Wind" credit) ends up with zero links → deleted.

* DB access goes through an INJECTABLE connection so tests can pass an in-memory
  fake. The SQL is written to run unchanged against a real PostgreSQL when the
  OPERATOR applies it via docs/RECONCILIATION.md.
* --dry-run reports every link add/remove and artist delete it WOULD make,
  writing nothing, and exits 0.
* A non-dry run performs everything in a SINGLE transaction on ONE connection:
  re-derive every song/album's target artist set from its credit, add missing
  canonical links (creating the canonical artist row if absent, mirroring the
  loader's get-or-create), remove links the new parse no longer supports, then
  delete any artist (and its artist_stats) left with zero links. Each link's
  ``role`` is taken DETERMINISTICALLY from the new parse (fixing CR-02 — no
  reliance on ON CONFLICT's arbitrary surviving row). It commits only if every
  before/after invariant holds; on any violated invariant it rolls back.
* Invariants (WR-01): distinct song/album ID SETS unchanged (not just counts);
  no song/album left with zero artists; total link rows only DECREASE; and every
  artist still present is produced by at least one credit's new-parse while every
  deleted artist is produced by NONE — so a wrong-target merge is caught.
* Idempotent: detection is data-driven, so once links match the credits a re-run
  is a clean no-op. There is no "already ran" flag.
* This module NEVER connects to production during automated execution and NEVER
  rebuilds artist_stats — those are operator steps in the runbook.
"""

from __future__ import annotations

import argparse
import logging
from typing import Dict, Iterable, List, Optional, Set, Tuple

from billboard_stats.etl.artist_aliases import canonicalize
from billboard_stats.etl.artist_parser import _normalize_key, parse_artist_credit

logger = logging.getLogger(__name__)


class ReconciliationInvariantError(RuntimeError):
    """Raised when a before/after safety invariant is violated; triggers rollback."""


# ----------------------------------------------------------------------------
# Target derivation: re-parse the raw credits
# ----------------------------------------------------------------------------
def _db_known_acts(artists_by_name: Dict[str, str]) -> List[str]:
    """Derive the parser's known-acts set from the artists already in the DB.

    Any stored artist name containing an internal separator (``,`` or `` & ``) is
    a multi-part act the parser must keep whole when re-parsing credits. This is
    the same DB-derived source the loader's parser would have seen, so re-parsing
    reproduces the loader's intended (post-fix) output.
    """
    return [
        name
        for name in artists_by_name.values()
        if ("," in name or " & " in name)
    ]


# ----------------------------------------------------------------------------
# Invariant snapshot
# ----------------------------------------------------------------------------
def _capture_snapshot(cur) -> Dict[str, object]:
    """Capture invariant snapshot (id SETS, not just counts) from the DB."""
    snap: Dict[str, object] = {}

    cur.execute("SELECT DISTINCT song_id FROM song_artists;")
    snap["song_ids"] = {row[0] for row in cur.fetchall()}

    cur.execute("SELECT DISTINCT album_id FROM album_artists;")
    snap["album_ids"] = {row[0] for row in cur.fetchall()}

    cur.execute("SELECT COUNT(*) FROM song_artists;")
    snap["song_links"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM album_artists;")
    snap["album_links"] = cur.fetchone()[0]

    return snap


def _assert_invariants(
    before: Dict[str, object],
    after: Dict[str, object],
    deleted_artist_keys: Set[str],
    produced_keys: Set[str],
) -> None:
    """Assert the reconciliation safety invariants, raising on any violation.

    WR-01: compare the actual distinct ID SETS (not just counts) so a song/album
    silently swapping which entities have artists is caught, and assert that no
    artist produced by some credit's new-parse was deleted — which is what
    catches a wrong-target merge that the old count-only checks missed.
    """
    if after["song_ids"] != before["song_ids"]:
        lost = before["song_ids"] - after["song_ids"]
        raise ReconciliationInvariantError(
            f"distinct song id set changed (lost {sorted(lost)[:10]}...) "
            "— a song lost all its artists"
        )
    if after["album_ids"] != before["album_ids"]:
        lost = before["album_ids"] - after["album_ids"]
        raise ReconciliationInvariantError(
            f"distinct album id set changed (lost {sorted(lost)[:10]}...) "
            "— an album lost all its artists"
        )
    before_links = before["song_links"] + before["album_links"]
    after_links = after["song_links"] + after["album_links"]
    if after_links > before_links:
        raise ReconciliationInvariantError(
            f"total link rows increased: {before_links} -> {after_links} "
            "(reconciliation must only dedupe/repoint, never net-add)"
        )
    # No artist that some credit's new-parse PRODUCES may be deleted. This is the
    # invariant that would catch a wrong-but-nonempty merge (CR-01 regression):
    # solo Diana Ross is produced by her own credits, so deleting her trips this.
    wrongly_deleted = deleted_artist_keys & produced_keys
    if wrongly_deleted:
        raise ReconciliationInvariantError(
            "deleted artist(s) still produced by a credit's new-parse: "
            f"{sorted(wrongly_deleted)[:10]} — refusing to destroy a real artist"
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
    """Reconcile artist links to match the NEW parse of every stored credit.

    Args:
        conn: An injectable DB connection exposing ``cursor()`` (context
            manager), ``commit()``, and ``rollback()``.
        dry_run: When True, compute and report the planned changes and exit
            without writing.
        known_acts: Optional extra canonical act names unioned with the
            DB-derived multi-part names for parser lookup. Normally ``None`` —
            the known-acts set is derived from the artists table in the SAME
            transaction (WR-02).

    Returns:
        A report dict describing the planned/applied changes.
    """
    report: Dict[str, object] = {
        "dry_run": dry_run,
        "added_song_links": 0,
        "added_album_links": 0,
        "removed_song_links": 0,
        "removed_album_links": 0,
        "deleted_artists": [],
        "created_artists": [],
        "before": None,
        "after": None,
    }

    try:
        with conn.cursor() as cur:
            # --- Load DB snapshot (single transaction; WR-02) ----------------
            cur.execute("SELECT id, name FROM artists;")
            id_to_name: Dict[int, str] = {}
            artists_by_name: Dict[str, str] = {}
            name_to_id: Dict[str, int] = {}
            for row in cur.fetchall():
                artist_id, name = row[0], row[1]
                id_to_name[artist_id] = name
                key = _normalize_key(name)
                artists_by_name[key] = name
                name_to_id[key] = artist_id

            # Known-acts set derived from the artists table, in THIS transaction.
            derived_acts = _db_known_acts(artists_by_name)
            if known_acts:
                derived_acts = list(derived_acts) + [
                    n for n in known_acts if n and n.strip()
                ]

            # Current links per entity.
            cur.execute("SELECT song_id, artist_id FROM song_artists;")
            song_links: Dict[int, Set[int]] = {}
            for song_id, artist_id in cur.fetchall():
                song_links.setdefault(song_id, set()).add(artist_id)

            cur.execute("SELECT album_id, artist_id FROM album_artists;")
            album_links: Dict[int, Set[int]] = {}
            for album_id, artist_id in cur.fetchall():
                album_links.setdefault(album_id, set()).add(artist_id)

            # Every stored credit (the source of truth we re-parse).
            cur.execute("SELECT id, artist_credit FROM songs;")
            song_credits = [(row[0], row[1]) for row in cur.fetchall()]
            cur.execute("SELECT id, artist_credit FROM albums;")
            album_credits = [(row[0], row[1]) for row in cur.fetchall()]

            # --- Compute the add/remove plan from the re-parsed credits ------
            (
                song_add,
                song_remove,
                song_produced,
            ) = _plan_for_kind(
                name_to_id, song_credits, song_links, derived_acts
            )
            (
                album_add,
                album_remove,
                album_produced,
            ) = _plan_for_kind(
                name_to_id, album_credits, album_links, derived_acts
            )
            produced_keys = song_produced | album_produced

            # Artists that, after applying the plan, retain at least one link.
            surviving_ids = _surviving_artist_ids(
                song_links, song_add, song_remove,
                album_links, album_add, album_remove,
                name_to_id,
            )
            orphan_ids = [
                aid for aid in id_to_name if aid not in surviving_ids
            ]
            # An artist is a TRUE orphan (safe to delete) only if no credit's
            # new-parse produces it. This protects solo members of real acts.
            deletable_ids = [
                aid
                for aid in orphan_ids
                if _normalize_key(id_to_name[aid]) not in produced_keys
            ]
            deleted_artist_keys = {
                _normalize_key(id_to_name[aid]) for aid in deletable_ids
            }

            report["added_song_links"] = len(song_add)
            report["added_album_links"] = len(album_add)
            report["removed_song_links"] = len(song_remove)
            report["removed_album_links"] = len(album_remove)
            report["deleted_artists"] = [
                {"id": aid, "name": id_to_name[aid]} for aid in deletable_ids
            ]

            has_work = (
                song_add or song_remove or album_add or album_remove or deletable_ids
            )
            if not has_work:
                logger.info("Nothing to reconcile — links already match credits.")
                return report

            for d in report["deleted_artists"]:
                logger.info("Will delete orphan artist: %s(#%s)", d["name"], d["id"])

            if dry_run:
                logger.info(
                    "Dry run: +%d/-%d song links, +%d/-%d album links, "
                    "%d orphan artists; writing nothing.",
                    len(song_add), len(song_remove),
                    len(album_add), len(album_remove),
                    len(deletable_ids),
                )
                return report

            before = _capture_snapshot(cur)
            report["before"] = {
                "song_links": before["song_links"],
                "album_links": before["album_links"],
            }

            # --- Apply: get-or-create canonical artists, then add/remove -----
            created = _apply_plan(
                cur,
                "song_artists", "song_id",
                song_add, song_remove,
                name_to_id, id_to_name,
            )
            created |= _apply_plan(
                cur,
                "album_artists", "album_id",
                album_add, album_remove,
                name_to_id, id_to_name,
            )
            report["created_artists"] = sorted(created)

            # Delete true-orphan stats and artist rows (after links are gone).
            if deletable_ids:
                cur.execute(
                    "DELETE FROM artist_stats WHERE artist_id = ANY(%s);",
                    (deletable_ids,),
                )
                cur.execute(
                    "DELETE FROM artists WHERE id = ANY(%s);",
                    (deletable_ids,),
                )

            after = _capture_snapshot(cur)
            report["after"] = {
                "song_links": after["song_links"],
                "album_links": after["album_links"],
            }

            _assert_invariants(before, after, deleted_artist_keys, produced_keys)

        conn.commit()
        logger.info(
            "Reconciliation committed: +%d/-%d song links, +%d/-%d album links, "
            "%d orphan artists deleted.",
            len(song_add), len(song_remove),
            len(album_add), len(album_remove),
            len(deletable_ids),
        )
        return report
    except Exception:
        conn.rollback()
        raise


def _plan_for_kind(
    name_to_id: Dict[str, int],
    credits: List[Tuple[int, str]],
    current_links: Dict[int, Set[int]],
    known_acts: List[str],
) -> Tuple[
    List[Tuple[int, str, str]],
    List[Tuple[int, int]],
    Set[str],
]:
    """Diff current links for one entity kind against the re-parsed credits.

    Returns (links_to_add, links_to_remove, produced_keys) where each add is
    ``(entity_id, canonical_name, role)`` and each remove is
    ``(entity_id, artist_id)``. Roles are taken deterministically from the parse
    (first occurrence of a canonical name wins), fixing CR-02.
    """
    id_to_key = {aid: key for key, aid in name_to_id.items()}
    links_to_add: List[Tuple[int, str, str]] = []
    links_to_remove: List[Tuple[int, int]] = []
    produced_keys: Set[str] = set()

    for entity_id, credit in credits:
        target_role: Dict[str, str] = {}
        target_name: Dict[str, str] = {}
        for raw_name, role in parse_artist_credit(credit, known_acts=known_acts):
            canonical = canonicalize(raw_name)
            key = _normalize_key(canonical)
            produced_keys.add(key)
            if key not in target_role:
                target_role[key] = role
                target_name[key] = canonical

        current = current_links.get(entity_id, set())
        current_keys = {
            id_to_key[aid] for aid in current if aid in id_to_key
        }

        # Add any target artist not currently linked.
        for key, canonical in target_name.items():
            artist_id = name_to_id.get(key)
            if artist_id is None or artist_id not in current:
                links_to_add.append((entity_id, canonical, target_role[key]))

        # Remove any current link whose canonical name is not in the target.
        for artist_id in current:
            key = id_to_key.get(artist_id)
            if key is None or key not in target_name:
                links_to_remove.append((entity_id, artist_id))

    return links_to_add, links_to_remove, produced_keys


def _surviving_artist_ids(
    song_links, song_add, song_remove,
    album_links, album_add, album_remove,
    name_to_id,
) -> Set[int]:
    """Compute the set of artist ids that retain >=1 link after the plan applies.

    Adds reference canonical NAMES (some may be created this run); we resolve
    them via ``name_to_id`` and ignore not-yet-existing ids (a created artist
    trivially survives because the very link that created it is its evidence).
    """
    surviving: Set[int] = set()
    _apply_links_for_survival(
        song_links, song_add, song_remove, name_to_id, surviving
    )
    _apply_links_for_survival(
        album_links, album_add, album_remove, name_to_id, surviving
    )
    return surviving


def _apply_links_for_survival(
    current_links, adds, removes, name_to_id, surviving
) -> None:
    remove_set = set(removes)
    for entity_id, artist_ids in current_links.items():
        for artist_id in artist_ids:
            if (entity_id, artist_id) not in remove_set:
                surviving.add(artist_id)
    for entity_id, canonical, _role in adds:
        artist_id = name_to_id.get(_normalize_key(canonical))
        if artist_id is not None:
            surviving.add(artist_id)


def _apply_plan(
    cur,
    table: str,
    key_col: str,
    adds: List[Tuple[int, str, str]],
    removes: List[Tuple[int, int]],
    name_to_id: Dict[str, int],
    id_to_name: Dict[int, str],
) -> Set[str]:
    """Apply the add/remove link plan for one join table.

    Returns the set of artist names CREATED during application (get-or-create,
    mirroring the loader). Each insert sets ``role`` explicitly from the plan, so
    there is no reliance on ON CONFLICT's arbitrary surviving row (CR-02).
    """
    created: Set[str] = set()

    for entity_id, canonical, role in adds:
        key = _normalize_key(canonical)
        artist_id = name_to_id.get(key)
        if artist_id is None:
            # get-or-create the canonical artist, mirroring loader.py.
            cur.execute(
                "INSERT INTO artists (name) VALUES (%s) "
                "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
                "RETURNING id;",
                (canonical,),
            )
            artist_id = cur.fetchone()[0]
            name_to_id[key] = artist_id
            id_to_name[artist_id] = canonical
            created.add(canonical)

        cur.execute(
            f"INSERT INTO {table} ({key_col}, artist_id, role) "
            f"VALUES (%s, %s, %s) "
            f"ON CONFLICT ({key_col}, artist_id) DO NOTHING;",
            (entity_id, artist_id, role),
        )

    for entity_id, artist_id in removes:
        cur.execute(
            f"DELETE FROM {table} WHERE {key_col} = %s AND artist_id = %s;",
            (entity_id, artist_id),
        )

    return created


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint. The OPERATOR runs this against the real DB per the runbook."""
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile artist links to the new parse of every stored credit "
            "(operator-applied; see docs/RECONCILIATION.md)."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the planned changes without writing anything.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Lazy DB import so the module imports cleanly in environments without
    # psycopg2 (e.g. the mock-based test environment). A SINGLE connection is
    # used end-to-end so detection and execution share one transaction (WR-02).
    from billboard_stats.db.connection import get_conn, put_conn

    conn = get_conn()
    try:
        report = reconcile(conn, dry_run=args.dry_run)
    finally:
        put_conn(conn)

    print(
        f"{'DRY RUN — ' if report['dry_run'] else ''}"
        f"song links +{report['added_song_links']}/-{report['removed_song_links']}, "
        f"album links +{report['added_album_links']}/-{report['removed_album_links']}, "
        f"{len(report['deleted_artists'])} orphan artist(s) deleted."
    )
    for d in report["deleted_artists"]:
        print(f"  delete orphan: {d['name']} (#{d['id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
