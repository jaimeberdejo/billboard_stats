# Quick Task Plan

Fix ETL artist parsing so known act names containing `&` are not split into separate artists.

Steps:

1. Add a protected-name layer ahead of the generic `&` split logic.
2. Keep normal collaboration parsing working for credits like `Future & Drake`.
3. Add targeted unit tests for both protected act names and real collaborations.
4. Document the operational follow-up needed for already-loaded database rows.
