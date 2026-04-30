---
status: complete
completed_at: "2026-04-30T00:00:00Z"
---

# Quick Task Summary

## Outcome

Implemented an allowlist-based fix in `billboard_stats/etl/artist_parser.py` so known act names containing `&` are protected before the generic group-splitting regex runs.

This now preserves examples like:

- `Earth, Wind & Fire`
- `Simon & Garfunkel`
- `Macklemore & Ryan Lewis`
- `Bob Seger & The Silver Bullet Band`

while still splitting true collaboration credits such as:

- `Future & Drake`

Added targeted Python unit tests in `tests/test_artist_parser.py` covering:

- standard featured credits
- true `&` collaborations
- protected `&` band/duo names
- protected names inside `Featuring` / `With` patterns

## Verification

- `python -m unittest tests.test_artist_parser` — PASS

## Notes

- This fixes future ETL parsing and future reloads.
- Existing normalized rows already loaded into `artists`, `song_artists`, and `album_artists` will still reflect the old split behavior until the data is repaired or reloaded through the ETL.
