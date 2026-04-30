# Quick Task Plan

Investigate whether artist-credit parsing correctly handles band names that contain `&` as part of the actual name rather than as a collaboration separator.

Steps:

1. Inspect the current parser logic in the ETL.
2. Run representative examples through the parser.
3. Scan the stored chart data for real credits containing ` & `.
4. Summarize whether this was handled and identify concrete false splits.
