---
status: complete
completed_at: "2026-04-30T00:00:00Z"
---

# Quick Task Summary

## Outcome

Confirmed that the current ETL artist parser does **not** safely distinguish band names containing `&` from multi-artist collaborations.

The parser in `billboard_stats/etl/artist_parser.py` splits on `&` whenever it appears with spaces around it:

- `_GROUP_SPLIT = re.compile(r"\s*,\s*|\s+&\s+|\s+[Xx]\s+|\s+[Aa]nd\s+")`

Direct parser checks showed these false splits:

- `Earth, Wind & Fire` -> `Earth`, `Wind`, `Fire`
- `Hall & Oates` -> `Hall`, `Oates`
- `Simon & Garfunkel` -> `Simon`, `Garfunkel`

Dataset scan showed this is not a rare edge case. There are 2,424 unique raw credits containing ` & ` in the stored chart JSON, including:

- `Peter, Paul & Mary`
- `Brooks & Dunn`
- `Bob Seger & The Silver Bullet Band`
- `Kool & The Gang`
- `Earth, Wind & Fire`
- `Huey Lewis & The News`
- `Blood, Sweat & Tears`

So the current logic handles collaboration credits like `Future & Drake`, but it also misclassifies many valid band or act names that use `&`.

## Verification

- Inspected `billboard_stats/etl/artist_parser.py`
- Ran sample parser checks with representative credits
- Scanned stored JSON chart data for raw ` & ` credits

## Recommendation

The safest next fix is not a generic regex tweak alone. It should be:

1. Add an exception / canonical-name allowlist for known band names with `&`
2. Only split `&` when the full raw credit is not in that allowlist
3. Optionally review historically common false splits already loaded into `artists`, `song_artists`, and `album_artists`
