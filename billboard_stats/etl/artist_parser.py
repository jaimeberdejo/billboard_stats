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

import re
from typing import List, Tuple

# Separators that denote featured/with artists (checked in priority order)
_FEAT_PATTERNS = [
    (re.compile(r"\s+[Ff]eaturing\s+", re.IGNORECASE), "featured"),
    (re.compile(r"\s+[Ff]eat\.?\s+", re.IGNORECASE), "featured"),
    (re.compile(r"\s+[Ff]t\.?\s+", re.IGNORECASE), "featured"),
    (re.compile(r"\s+[Ww]ith\s+", re.IGNORECASE), "with"),
]

# Separators within a group of artists (e.g. "Drake, Lil Wayne & Rick Ross")
_GROUP_SPLIT = re.compile(r"\s*,\s*|\s+&\s+|\s+[Xx]\s+|\s+[Aa]nd\s+")


def _split_group(text: str) -> List[str]:
    """Split a group of artists by commas, ampersands, 'X', or 'and'."""
    parts = _GROUP_SPLIT.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def parse_artist_credit(credit: str) -> List[Tuple[str, str]]:
    """Parse a Billboard artist credit string into (name, role) tuples.

    Returns a list of (artist_name, role) where role is one of:
    'primary', 'featured', or 'with'.
    """
    if not credit or not credit.strip():
        return []

    credit = credit.strip()

    # Try to split on featuring/with keywords (first match wins)
    for pattern, role in _FEAT_PATTERNS:
        match = pattern.search(credit)
        if match:
            primary_part = credit[: match.start()].strip()
            secondary_part = credit[match.end() :].strip()

            results = []
            for name in _split_group(primary_part):
                results.append((name, "primary"))
            for name in _split_group(secondary_part):
                results.append((name, role))
            return results

    # No featuring keyword — all are primary, split on separators
    names = _split_group(credit)
    return [(name, "primary") for name in names]
