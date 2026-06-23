"""ETL-side genuine artist alias map (the single source of truth for identity).

Ported from ``src/lib/artist-identity.ts`` (``CANONICAL_ARTIST_ALIASES``) so that
artist identity is fixed at the SOURCE during loading rather than patched at read
time in the frontend.

A GENUINE alias is an alternate name/spelling for the SAME act — for example the
mononym "Janet" for "Janet Jackson", or the stylized "Ke$ha" for "Kesha". These
must survive: ``canonicalize`` collapses them to the canonical name, and the
reconciliation migration must never delete a genuine-alias artist row as if it
were a leftover fragment.

This is deliberately DISTINCT from a SPLIT FRAGMENT. The historical over-eager
parser shattered acts like "Earth, Wind & Fire" into the standalone rows "Earth",
"Wind", and "Fire". Those pieces are NOT alternate names for the act — they are
artifacts of a bad split, and they are healed by the reconciliation migration
(see reconcile_artists.py), NOT by this alias map. Accordingly the
"Earth, Wind & Fire" grouping is intentionally absent here.

The module is pure: no database access and no network, so it imports cleanly in
the mock-based test environment.
"""

from __future__ import annotations

import re
from typing import Dict, List, Set


# Canonical act name -> list of GENUINE alternate names (same act, different
# spelling/mononym). Only entries that must survive reconciliation belong here.
#
# Note on the historically shattered group act: its individual pieces are
# deliberately NOT modeled here as alternate names, because they are repaired by
# the reconciliation migration rather than treated as aliases.
CANONICAL_ARTIST_ALIASES: Dict[str, List[str]] = {
    "Janet Jackson": ["Janet"],
    "Kesha": ["Ke$ha"],
}


def _normalize_key(name: str) -> str:
    """Normalize a name to a casefolded, single-spaced lookup key."""
    return re.sub(r"\s+", " ", name.strip()).casefold()


def _build_alias_index() -> Dict[str, str]:
    """Build a normalized-key -> canonical-name index of genuine aliases.

    Both each canonical name and each of its alternate names map to the
    canonical name, so a lookup of either resolves consistently.
    """
    index: Dict[str, str] = {}
    for canonical_name, alternates in CANONICAL_ARTIST_ALIASES.items():
        index[_normalize_key(canonical_name)] = canonical_name
        for alt in alternates:
            index[_normalize_key(alt)] = canonical_name
    return index


_ALIAS_INDEX: Dict[str, str] = _build_alias_index()


def canonicalize(name: str) -> str:
    """Return the canonical name for a genuine alias, else the input unchanged.

    Case-insensitive, whitespace-normalized, and deterministic: the same input
    always yields the same output. A name that is not a genuine alias (including
    a split fragment such as a piece of a group act) is returned verbatim.
    """
    if name is None:
        return name
    canonical = _ALIAS_INDEX.get(_normalize_key(name))
    if canonical is not None:
        return canonical
    return name


def genuine_alias_names() -> Set[str]:
    """Return the set of normalized keys that are genuine aliases.

    Reconciliation consults this to avoid deleting a genuine-alias artist row as
    if it were a leftover fragment. Includes both each canonical name and each of
    its alternate names, all as normalized keys.
    """
    return set(_ALIAS_INDEX.keys())


def is_genuine_alias(name: str) -> bool:
    """Return True if ``name`` is a known canonical name or a genuine alias."""
    if name is None:
        return False
    return _normalize_key(name) in _ALIAS_INDEX
