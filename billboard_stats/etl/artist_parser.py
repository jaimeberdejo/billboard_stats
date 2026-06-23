"""Parse raw Billboard artist credit strings into individual artists with roles.

Examples:
    "Drake"                                  -> [("Drake", "primary")]
    "Drake Featuring Rihanna"                -> [("Drake", "primary"), ("Rihanna", "featured")]
    "Future & Drake"                         -> [("Future", "primary"), ("Drake", "primary")]
    "DJ Khaled Featuring Drake, Lil Wayne & Rick Ross"
        -> [("DJ Khaled", "primary"), ("Drake", "featured"),
            ("Lil Wayne", "featured"), ("Rick Ross", "featured")]
    "Post Malone With Doja Cat"              -> [("Post Malone", "primary"), ("Doja Cat", "with")]
    "Beyonce X Shakira"                      -> [("Beyonce", "primary"), ("Shakira", "primary")]
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, List, Tuple

logger = logging.getLogger(__name__)

# Separators that denote featured/with artists (checked in priority order)
_FEAT_PATTERNS = [
    (re.compile(r"\s+[Ff]eaturing\s+", re.IGNORECASE), "featured"),
    (re.compile(r"\s+[Ff]eat\.?\s+", re.IGNORECASE), "featured"),
    (re.compile(r"\s+[Ff]t\.?\s+", re.IGNORECASE), "featured"),
    (re.compile(r"\s+[Ww]ith\s+", re.IGNORECASE), "with"),
]

# Separators within a group of artists (e.g. "Drake, Lil Wayne & Rick Ross")
_GROUP_SPLIT = re.compile(r"\s*,\s*|\s+&\s+|\s+[Xx]\s+|\s+[Aa]nd\s+")

# Known act names where `&` is part of the act identity and should not be
# treated as a collaboration separator. This is intentionally curated and can
# be extended as additional false splits are discovered in the historical data.
_PROTECTED_AMPERSAND_ACTS = (
    "Aly & AJ",
    "Archie Bell & The Drells",
    "Ashford & Simpson",
    "BeBe & CeCe Winans",
    "Big & Rich",
    "Blood, Sweat & Tears",
    "Bob Seger & The Silver Bullet Band",
    "Booker T. & The MG's",
    "Brooks & Dunn",
    "Bruce Hornsby & The Range",
    "Captain & Tennille",
    "Chad & Jeremy",
    "Cheech & Chong",
    "Commander Cody & His Lost Planet Airmen",
    "Country Joe & The Fish",
    "Crosby, Stills & Nash",
    "Crosby, Stills, Nash & Young",
    "D.J. Jazzy Jeff & The Fresh Prince",
    "Derek & The Dominos",
    "Diana Ross & The Supremes",
    "Dion & The Belmonts",
    "Earth, Wind & Fire",
    "Edie Brickell & New Bohemians",
    "Emerson, Lake & Palmer",
    "England Dan & John Ford Coley",
    "Ferrante & Teicher",
    "George Thorogood & The Destroyers",
    "Gloria Estefan & Miami Sound Machine",
    "Hall & Oates",
    "Hamilton, Joe Frank & Reynolds",
    "Heavy D & The Boyz",
    "Herb Alpert & The Tijuana Brass",
    "Hootie & The Blowfish",
    "Huey Lewis & The News",
    "Ike & Tina Turner",
    "Jan & Dean",
    "Jay & The Americans",
    "Joan Jett & The Blackhearts",
    "John Cafferty & The Beaver Brown Band",
    "Jr. Walker & The All Stars",
    "K-Ci & JoJo",
    "Kool & The Gang",
    "Lil Jon & The East Side Boyz",
    "Loggins & Messina",
    "Macklemore & Ryan Lewis",
    "Marky Mark & The Funky Bunch",
    "Marilyn McCoo & Billy Davis Jr.",
    "Marvin Gaye & Tammi Terrell",
    "Martha & The Vandellas",
    "Mumford & Sons",
    "Paul Revere & The Raiders",
    "Peaches & Herb",
    "Peter, Paul & Mary",
    "R. Kelly & Public Announcement",
    "Ray Parker Jr. & Raydio",
    "Rene & Angela",
    "Sam & Dave",
    "Seals & Crofts",
    "Selena Gomez & The Scene",
    "Simon & Garfunkel",
    "Sly & The Family Stone",
    "Smokey Robinson & The Miracles",
    "Sonny & Cher",
    "Southside Johnny & The Asbury Jukes",
    "The Mamas & The Papas",
    "Tony Orlando & Dawn",
    "Tyler, The Creator",
    "Wisin & Yandel",
)


def _protect_known_ampersand_acts(text: str) -> tuple[str, dict[str, str]]:
    """Temporarily replace protected act names with opaque tokens."""
    protected: dict[str, str] = {}
    masked = text

    for index, act_name in enumerate(
        sorted(_PROTECTED_AMPERSAND_ACTS, key=len, reverse=True)
    ):
        token = f"__PROTECTED_ARTIST_{index}__"
        pattern = re.compile(re.escape(act_name), re.IGNORECASE)
        if pattern.search(masked):
            masked = pattern.sub(token, masked)
            protected[token] = act_name

    return masked, protected


def _normalize_key(text: str) -> str:
    """Normalize a credit/name to a casefolded, single-spaced lookup key."""
    return re.sub(r"\s+", " ", text.strip()).casefold()


def _build_known_acts_index(
    known_acts: Iterable[str] | None,
) -> dict[str, str]:
    """Build a normalized-key -> canonical-name index of known single acts.

    Seeds with the curated allowlist and unions in any caller-supplied names
    (the DB-derived layer passes canonical `artists.name` values here). This
    module never touches the database; the set is injected so the parser stays
    pure and deterministic.
    """
    index: dict[str, str] = {}
    for name in _PROTECTED_AMPERSAND_ACTS:
        index[_normalize_key(name)] = name
    if known_acts:
        for name in known_acts:
            if name and name.strip():
                # Caller-supplied names take precedence over the curated seed.
                index[_normalize_key(name)] = name.strip()
    return index


def _split_group(text: str) -> List[str]:
    """Split a group of artists by commas, ampersands, 'X', or 'and'."""
    masked, protected = _protect_known_ampersand_acts(text.strip())
    parts = _GROUP_SPLIT.split(masked)
    return [protected.get(p.strip(), p.strip()) for p in parts if p.strip()]


def _resolve_segment(
    segment: str, role: str, known_index: dict[str, str]
) -> List[Tuple[str, str]]:
    """Resolve one credit segment to (name, role) tuples.

    Lookup-first: if the whole segment matches a known single act, emit it as a
    single artist without splitting. Otherwise fall back to separator splitting,
    and surface any comma-containing split for later review.
    """
    segment = segment.strip()
    if not segment:
        return []

    match = known_index.get(_normalize_key(segment))
    if match is not None:
        return [(match, role)]

    names = _split_group(segment)
    if len(names) > 1 and "," in segment:
        # A comma-bearing credit was split into multiple artists; record it so
        # an unlisted comma-act can be reviewed and promoted to the known set.
        logger.info(
            "Comma-containing credit split into multiple artists: %r -> %r",
            segment,
            names,
        )
    return [(name, role) for name in names]


def parse_artist_credit(
    credit: str,
    known_acts: Iterable[str] | None = None,
) -> List[Tuple[str, str]]:
    """Parse a Billboard artist credit string into (name, role) tuples.

    Lookup-first / split-second: the whole credit (and each Featuring/With
    segment) is matched against the known single-acts set BEFORE any separator
    split, so comma/ampersand act names resolve to one artist. Genuine
    collaborations with no whole-credit match still split.

    `known_acts` is an optional, injected set of canonical act names (e.g.
    DB-derived `artists.name` values). It is unioned with the curated allowlist.
    The parser never queries the database.

    Returns a list of (artist_name, role) where role is one of:
    'primary', 'featured', or 'with'.
    """
    if not credit or not credit.strip():
        return []

    credit = credit.strip()
    known_index = _build_known_acts_index(known_acts)

    # Lookup-first on the full raw credit (covers standalone comma/& acts).
    whole_match = known_index.get(_normalize_key(credit))
    if whole_match is not None:
        return [(whole_match, "primary")]

    # Try to split on featuring/with keywords (first match wins). Each side gets
    # the whole-segment lookup before falling back to the group splitter.
    for pattern, role in _FEAT_PATTERNS:
        match = pattern.search(credit)
        if match:
            primary_part = credit[: match.start()].strip()
            secondary_part = credit[match.end() :].strip()

            results: List[Tuple[str, str]] = []
            results.extend(_resolve_segment(primary_part, "primary", known_index))
            results.extend(_resolve_segment(secondary_part, role, known_index))
            return results

    # No featuring keyword — resolve the whole credit as a primary segment.
    return _resolve_segment(credit, "primary", known_index)
