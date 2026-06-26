"""Offline, idempotent artist-gender enricher (GENDER-02).

Populates the Phase 12 gender columns on ``artists`` (``gender``,
``gender_source``, ``gender_source_id``) from authoritative CC0 sources:
**MusicBrainz** primary, **Wikidata** fallback. The match is keyed by the
artist's stable ID (MusicBrainz MBID / Wikidata QID) — NOT the raw, ambiguous
name string — and the chosen ID is persisted into ``gender_source_id`` so the
batch is idempotent and re-runnable.

Design / safety contract (mirrors reconcile_artists.py + the Phase 8/10/11
operator-script pattern):

* DB access goes through an INJECTABLE connection so tests pass an in-memory
  fake. HTTP access goes through an INJECTABLE client (``http``) so tests pass a
  fake returning recorded JSON fixtures — NO real network is touched in tests.
* The module imports cleanly in the psycopg2-free, network-free test/CI env:
  there is NO top-level ``psycopg2`` import and NO top-level ``requests`` import.
  ``requests`` is imported lazily INSIDE :meth:`HttpClient.get_json` (the only
  place it is referenced); ``get_conn`` / ``put_conn`` are imported lazily inside
  :func:`main`.
* The selection query IS the idempotency gate (data-driven, no "already ran"
  flag): a default run fills ONLY ``gender = 'unknown'`` rows; ``--refresh``
  re-fetches ALL rows. ``only_artist_ids`` (the ETL delta path) further scopes
  the selection to a given id set.
* TRANSACTION OWNERSHIP (W-1): :func:`enrich` OWNS its own transaction. It does
  ALL work inside one ``with conn.cursor() as cur:`` block, ``conn.commit()``s
  its successful work at the end, and on a fatal error ``conn.rollback()``s its
  OWN failed unit then re-raises. Callers (including the ETL hook) MUST NOT
  commit or rollback on its behalf.
* Per-artist resilience: an HTTP/parse error for ONE artist is caught, leaves
  that row ``'unknown'``, and the batch continues — one bad lookup never aborts
  the run. A failure OUTSIDE the per-artist guard (e.g. a DB write error) is
  fatal: rollback + re-raise.
* Defensive parsing (T-12-04): MusicBrainz/Wikidata responses are UNTRUSTED
  JSON. Every field access uses ``dict.get`` with defaults, guards missing /
  None / wrong-typed values, never indexes blindly, and never evals.
* Politeness (T-12-06): a ``delay``-second sleep between resolves (default
  ~1.1s, MusicBrainz's documented ~1 req/sec). ``delay`` is injectable so tests
  pass ``0`` (and ``time.sleep`` is monkeypatched to a no-op). A descriptive
  ``User-Agent`` with an operator-supplied ``--contact`` is sent on every call.

The LIVE network run, the real prod ``002_gender`` apply, and the coverage SPIKE
measurement are DEFERRED operator steps documented in docs/GENDER-ENRICHMENT.md.
"""

from __future__ import annotations

import argparse
import logging
import time
from typing import Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Endpoints + identity
# ----------------------------------------------------------------------------
MB_BASE = "https://musicbrainz.org/ws/2"
MB_ARTIST = f"{MB_BASE}/artist"
WD_API = "https://www.wikidata.org/w/api.php"

# Default MusicBrainz confidence threshold (score 0-100). Below this the top
# candidate is treated as no-match (do not guess; Pitfall 4 / T-12-09).
DEFAULT_MIN_SCORE = 90

# Wikidata Q-ids used by the mapping (VERIFIED against Property:P21 / class ids).
WD_HUMAN = "Q5"
WD_MALE = "Q6581097"
WD_FEMALE = "Q6581072"
# A small set of "musical group" classes treated as group/band.
WD_GROUP_CLASSES = {
    "Q215380",  # musical group
    "Q105756498",  # musical duo
    "Q281643",  # vocal group
    "Q9212979",  # musical ensemble
}

# MusicBrainz artist types that are ensembles (no per-person gender).
MB_GROUP_TYPES = {"group", "choir", "orchestra"}
# MusicBrainz artist types that carry a personal gender.
MB_PERSON_TYPES = {"person", "character"}


def _user_agent(contact: Optional[str]) -> str:
    """Build the descriptive User-Agent MusicBrainz + Wikidata require (T-12-06).

    The contact is an operator-supplied URL/email embedded per MusicBrainz's
    documented ``Application/Version ( contact )`` format. The contact is
    intentionally public (no secret).
    """
    contact = (contact or "https://github.com/jaimeberdejo/billboard_stats").strip()
    return f"billboard_stats-gender-enricher/1.0 ( {contact} )"


# ----------------------------------------------------------------------------
# Injectable HTTP client (the ONLY place requests is referenced)
# ----------------------------------------------------------------------------
class HttpClient:
    """Minimal injectable HTTP boundary; tests pass a fake returning fixtures.

    ``requests`` is imported lazily inside :meth:`get_json` so the module (and
    this class's constructor) import cleanly with no ``requests`` installed.
    """

    def get_json(
        self, url: str, params=None, headers=None, timeout: int = 20
    ) -> Tuple[int, object]:
        import requests  # lazy: module imports cleanly without requests in CI

        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.status_code, resp.json()


# ----------------------------------------------------------------------------
# Pure mapping helpers (no I/O — unit-testable directly)
# ----------------------------------------------------------------------------
def _map_gender(mb_type: Optional[str], mb_gender: Optional[str]) -> str:
    """Map a MusicBrainz (type, gender) pair to the 5-value vocabulary.

    Person/Character + Female -> 'female'; Person/Character + Male -> 'male';
    Person/Character + Non-binary / absent / other -> 'unknown';
    Group/Choir/Orchestra -> 'group' (gender is NEVER read for ensembles);
    Other / absent type / unmappable -> 'unknown'.

    NEVER returns 'mixed' (reserved for the manual path). Pure function.
    """
    t = (mb_type or "").strip().lower()
    # Branch on TYPE first — groups never read gender (Pitfall 5).
    if t in MB_GROUP_TYPES:
        return "group"
    if t in MB_PERSON_TYPES:
        g = (mb_gender or "").strip().lower()
        if g == "female":
            return "female"
        if g == "male":
            return "male"
        # Non-binary / absent / anything else -> unknown (no misattribution).
        return "unknown"
    # Other / absent / unmappable type.
    return "unknown"


def _map_wikidata(p31: Set[str], p21: Optional[str]) -> str:
    """Map Wikidata (P31 instance-of set, P21 sex-or-gender) to the vocabulary.

    P31 includes a group/band class -> 'group'. P31 includes human (Q5) ->
    read P21 (male -> 'male', female -> 'female', else -> 'unknown'). Otherwise
    'unknown'. NEVER returns 'mixed'. Pure function.
    """
    p31 = p31 or set()
    # A group/band class wins (a band is a group regardless of any stray P21).
    if p31 & WD_GROUP_CLASSES:
        return "group"
    if WD_HUMAN in p31:
        if p21 == WD_MALE:
            return "male"
        if p21 == WD_FEMALE:
            return "female"
        return "unknown"
    return "unknown"


# ----------------------------------------------------------------------------
# Resolution: MusicBrainz primary, Wikidata fallback (defensive parsing)
# ----------------------------------------------------------------------------
def mb_resolve(
    http, name: str, *, contact: Optional[str] = None,
    min_score: int = DEFAULT_MIN_SCORE, limit: int = 5,
) -> Optional[Tuple[str, str]]:
    """Resolve a name via MusicBrainz search -> lookup.

    Returns ``(gender, mbid)`` on a confident match, else ``None``. The Lucene
    name is passed via ``params`` (urllib-encoded by the client), never
    string-concatenated into the query; ``fmt=json`` is always set. Defensive
    parsing throughout — the response body is untrusted JSON.
    """
    headers = {"User-Agent": _user_agent(contact)}
    _, body = http.get_json(
        MB_ARTIST,
        params={"query": f'artist:"{name}"', "fmt": "json", "limit": limit},
        headers=headers,
    )
    cands = body.get("artists") if isinstance(body, dict) else None
    if not isinstance(cands, list) or not cands:
        return None
    cands = [c for c in cands if isinstance(c, dict)]
    if not cands:
        return None
    best = max(cands, key=lambda a: _as_int(a.get("score")))
    if _as_int(best.get("score")) < min_score:
        return None  # low confidence -> stay unknown
    mbid = best.get("id")
    if not isinstance(mbid, str) or not mbid:
        return None
    _, art = http.get_json(
        f"{MB_ARTIST}/{mbid}", params={"fmt": "json"}, headers=headers,
    )
    if not isinstance(art, dict):
        return None
    gender = _map_gender(art.get("type"), art.get("gender"))
    if gender == "unknown":
        # A confident MB id but an unmappable gender (e.g. Non-binary) — leave
        # the row unknown WITHOUT falling through to Wikidata (we DID get a
        # confident match; the gender simply has no 5-value bucket).
        return None
    return gender, mbid


def wd_resolve(
    http, name: str, *, contact: Optional[str] = None,
) -> Optional[Tuple[str, str]]:
    """Resolve a name via the Wikidata Action API (search -> getentities).

    Returns ``(gender, qid)`` on a confident match, else ``None``. Defensive
    parsing throughout. Called ONLY when MusicBrainz returns no confident match.
    """
    headers = {"User-Agent": _user_agent(contact)}
    _, s = http.get_json(
        WD_API,
        params={
            "action": "wbsearchentities", "search": name,
            "language": "en", "type": "item", "format": "json", "limit": 5,
        },
        headers=headers,
    )
    hits = s.get("search") if isinstance(s, dict) else None
    if not isinstance(hits, list) or not hits:
        return None
    first = hits[0] if isinstance(hits[0], dict) else {}
    qid = first.get("id")
    if not isinstance(qid, str) or not qid:
        return None
    _, e = http.get_json(
        WD_API,
        params={
            "action": "wbgetentities", "ids": qid,
            "props": "claims", "format": "json",
        },
        headers=headers,
    )
    entities = e.get("entities") if isinstance(e, dict) else None
    entity = entities.get(qid) if isinstance(entities, dict) else None
    claims = entity.get("claims") if isinstance(entity, dict) else None
    if not isinstance(claims, dict):
        return None
    p31 = _claim_ids(claims, "P31")
    p21 = next(iter(_claim_ids(claims, "P21")), None)
    gender = _map_wikidata(p31, p21)
    if gender == "unknown":
        return None
    return gender, qid


def _claim_ids(claims: Dict[str, object], prop: str) -> Set[str]:
    """Defensively extract the set of entity-id values for a Wikidata property."""
    out: Set[str] = set()
    statements = claims.get(prop)
    if not isinstance(statements, list):
        return out
    for c in statements:
        if not isinstance(c, dict):
            continue
        snak = c.get("mainsnak")
        dv = snak.get("datavalue") if isinstance(snak, dict) else None
        value = dv.get("value") if isinstance(dv, dict) else None
        if isinstance(value, dict):
            vid = value.get("id")
            if isinstance(vid, str) and vid:
                out.add(vid)
    return out


def _as_int(value) -> int:
    """Best-effort int coercion for an untrusted score field (default 0)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _resolve_gender(
    http, name: str, *, contact: Optional[str] = None,
    min_score: int = DEFAULT_MIN_SCORE,
) -> Optional[Tuple[str, str, str]]:
    """MB primary, Wikidata fallback. Returns (gender, source, source_id) | None.

    ``None`` means no confident match -> the caller leaves the row 'unknown'.
    Wikidata is queried ONLY when MusicBrainz returns no confident match.
    """
    mb = mb_resolve(http, name, contact=contact, min_score=min_score)
    if mb is not None:
        gender, mbid = mb
        return gender, "musicbrainz", mbid
    wd = wd_resolve(http, name, contact=contact)
    if wd is not None:
        gender, qid = wd
        return gender, "wikidata", qid
    return None


# ----------------------------------------------------------------------------
# Entrypoint — single transaction, idempotent, injectable conn + http
# ----------------------------------------------------------------------------
def enrich(
    conn,
    *,
    http=None,
    dry_run: bool = False,
    refresh: bool = False,
    limit: Optional[int] = None,
    only_artist_ids: Optional[Iterable[int]] = None,
    contact: Optional[str] = None,
    min_score: int = DEFAULT_MIN_SCORE,
    delay: float = 1.1,
) -> Dict[str, object]:
    """Fill artist gender from MusicBrainz (primary) + Wikidata (fallback).

    Args:
        conn: Injectable DB connection exposing ``cursor()`` (context manager),
            ``commit()``, and ``rollback()``.
        http: Injectable HTTP client with ``get_json(url, params, headers,
            timeout)``. Defaults to a real :class:`HttpClient` (lazy requests).
        dry_run: Report planned updates and write nothing (no commit).
        refresh: Re-fetch ALL rows instead of only ``gender = 'unknown'``.
        limit: Cap the number of artists processed (operator batch cap).
        only_artist_ids: Restrict selection to these ids (the ETL delta path).
        contact: Operator contact embedded in the User-Agent.
        min_score: MusicBrainz confidence threshold (default 90).
        delay: Seconds to sleep between resolves (polite ~1 req/sec). Injectable
            so tests pass 0.

    Returns:
        A report dict (matched / unmatched / updated / dry_run / ...).

    Transaction ownership (W-1): commits its own successful work; on a fatal
    error rolls back its own unit and re-raises. Callers MUST NOT commit/rollback.
    """
    if http is None:
        http = HttpClient()

    only_ids: Optional[Set[int]] = (
        set(only_artist_ids) if only_artist_ids is not None else None
    )

    report: Dict[str, object] = {
        "dry_run": dry_run,
        "refresh": refresh,
        "selected": 0,
        "matched": 0,
        "unmatched": 0,
        "errors": 0,
        "updated": [],
    }

    try:
        with conn.cursor() as cur:
            # --- Selection IS the idempotency gate (no "already ran" flag) ----
            if refresh:
                base = "SELECT id, name FROM artists"
            else:
                base = "SELECT id, name FROM artists WHERE gender = 'unknown'"

            if only_ids is not None:
                connector = " AND" if "where" in base.lower() else " WHERE"
                cur.execute(
                    f"{base}{connector} id = ANY(%s);", (list(only_ids),)
                )
            else:
                cur.execute(f"{base};")
            rows = cur.fetchall()

            if limit is not None:
                rows = rows[:limit]
            report["selected"] = len(rows)

            for artist_id, name in rows:
                # Per-artist resilience: one bad lookup never aborts the batch.
                try:
                    resolved = _resolve_gender(
                        http, name, contact=contact, min_score=min_score
                    )
                except Exception:
                    logger.exception(
                        "Gender resolution failed for artist %s(#%s); "
                        "leaving 'unknown' and continuing.",
                        name, artist_id,
                    )
                    report["errors"] += 1
                    resolved = None

                if delay:
                    time.sleep(delay)

                if resolved is None:
                    report["unmatched"] += 1
                    continue

                gender, source, source_id = resolved
                report["matched"] += 1
                report["updated"].append(
                    {
                        "id": artist_id,
                        "name": name,
                        "gender": gender,
                        "source": source,
                        "source_id": source_id,
                    }
                )
                if dry_run:
                    continue

                cur.execute(
                    "UPDATE artists SET gender = %s, gender_source = %s, "
                    "gender_source_id = %s WHERE id = %s;",
                    (gender, source, source_id, artist_id),
                )

        if dry_run:
            logger.info(
                "Dry run: %d selected, %d would match, %d unmatched, %d errors; "
                "writing nothing.",
                report["selected"], report["matched"],
                report["unmatched"], report["errors"],
            )
            return report

        conn.commit()
        logger.info(
            "Gender enrichment committed: %d selected, %d matched, %d unmatched, "
            "%d errors.",
            report["selected"], report["matched"],
            report["unmatched"], report["errors"],
        )
        return report
    except Exception:
        conn.rollback()
        raise


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint. The OPERATOR runs this against the real DB + network.

    See docs/GENDER-ENRICHMENT.md — this is a DEFERRED operator step.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Enrich artist gender from MusicBrainz (primary) + Wikidata "
            "(fallback) (operator-applied; see docs/GENDER-ENRICHMENT.md)."
        )
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report the planned updates without writing anything.",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Re-fetch ALL rows, not only gender='unknown'.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap the number of artists processed this run.",
    )
    parser.add_argument(
        "--contact", default=None,
        help="A real contact URL/email embedded in the required User-Agent.",
    )
    parser.add_argument(
        "--min-score", type=int, default=DEFAULT_MIN_SCORE,
        help="MusicBrainz confidence threshold (0-100; default 90).",
    )
    parser.add_argument(
        "--delay", type=float, default=1.1,
        help="Seconds between resolves (polite ~1 req/sec; default 1.1).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Lazy DB import so the module imports cleanly without psycopg2 (the
    # mock-based test env). Construct the real HTTP client lazily too.
    from billboard_stats.db.connection import get_conn, put_conn

    client = HttpClient()
    conn = get_conn()
    try:
        report = enrich(
            conn,
            http=client,
            dry_run=args.dry_run,
            refresh=args.refresh,
            limit=args.limit,
            contact=args.contact,
            min_score=args.min_score,
            delay=args.delay,
        )
    finally:
        put_conn(conn)

    print(
        f"{'DRY RUN — ' if report['dry_run'] else ''}"
        f"{report['selected']} selected, {report['matched']} matched, "
        f"{report['unmatched']} unmatched, {report['errors']} error(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
