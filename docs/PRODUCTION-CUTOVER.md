# Production Cutover Runbook — v2.0 + v2.1

The full chain below was **validated end-to-end on a throwaway Neon branch** (Phase 16,
`.planning/phases/16-real-db-migration-hardening/16-BRANCH-VALIDATION.md`). Prod is still pure v1.0 —
none of this is applied yet. Run from repo root with `.venv/bin/python` (Python 3.11). `psql` isn't
installed locally; the ad-hoc checks below use Python, or install `psql` if you prefer.

> **Golden rule:** all migrations are operator-applied, one transaction each, with invariant asserts +
> rollback. Take the `pg_dump` before the destructive step. Point `PG*` at a **Neon branch first** for a
> final rehearsal, then repeat against `main`.

## 0. Point PG* at the target

```bash
# Get a connection string and export PG* (branch first, then main):
neonctl connection-string <branch-or-main> --project-id patient-mud-67801214 \
  --database-name neondb --role-name neondb_owner
# parse into PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD/PGSSLMODE (db/connection.py reads these)
```

## Phase A — additive (the live v1.0 app keeps working; legacy tables untouched)

```bash
# 1. Multichart schema + backfill (Phase 9). REQUIRES the Phase-16 fix (now in main).
.venv/bin/python -m billboard_stats.etl.migrate_multichart --dry-run   # sanity: planned counts == source counts
.venv/bin/python -m billboard_stats.etl.migrate_multichart             # apply (parity-asserted)

# 2. Rebuild ALL stats from chart_entries (prod artist_stats is STALE ~52wk — do NOT skip).
.venv/bin/python -c "from billboard_stats.db.connection import get_conn,put_conn; from billboard_stats.etl.stats_builder import build_all_stats; c=get_conn(); build_all_stats(c); put_conn(c)"

# 3. Gender columns (Phase 12).
.venv/bin/python -m billboard_stats.etl.migrate_gender --dry-run
.venv/bin/python -m billboard_stats.etl.migrate_gender

# 4. Gender enrichment — MULTI-HOUR (1 req/s × up to 4 req/artist). Run in tmux/nohup.
.venv/bin/python -m billboard_stats.etl.gender_enricher --contact "https://github.com/jaimeberdejo/billboard_stats"
```

At this point chart_entries + *_stats + artist_chart_stats + gender are all populated, and the
**legacy tables still exist** — so the currently-deployed v1.0 app is unaffected.

## Phase B — deploy the new frontend (zero-downtime; do this BEFORE dropping legacy)

The v2.0 Next.js code reads `chart_entries`/`*_stats` and never touches the legacy tables, so it runs
correctly on the Phase-A (additive) schema while legacy tables still exist. Deploying here means the
destructive drop in Phase C is invisible to the live app.

```bash
git push origin main            # ~200 commits ahead; triggers the Vercel production deploy
git push origin v2.0            # the milestone tag (local-only today)
# verify the deployed app renders (Latest Charts, a detail page, Records, /compare)
```

## Phase C — retire legacy + load the new charts

```bash
# 5. BACKUP before the destructive step.
pg_dump --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$PGDATABASE" \
        --format=custom --file="pre-003-backup-$(date +%Y%m%d-%H%M%S).dump"

# 6. Retire legacy tables (Phase 15). MUST precede the first run_etl (loader's ON CONFLICT needs the
#    UNIQUE this adds). Safe now that the new app is deployed and no longer reads the legacy tables.
.venv/bin/python -m billboard_stats.etl.migrate_retire_legacy --dry-run
.venv/bin/python -m billboard_stats.etl.migrate_retire_legacy

# 7. Load the 9 new charts from the backfilled JSON on disk (Phase 11). This run also triggers the
#    gender enrichment of newly-inserted artists — MULTI-HOUR; run in tmux/nohup.
.venv/bin/python -m billboard_stats.etl.loader        # run_etl(): register + load + enrich + build_all_stats
```

After Phase C the new charts (Artist 100 + genre song/album) appear in the selector with data, and
the model is a single source of truth.

## Verify (per docs/MIGRATION-MULTICHART.md §6)
- `num_nonnulls(song_id,album_id,artist_id)=1` for all chart_entries (0 bad rows).
- `artist_chart_stats` vs `artist_stats` zero-discrepancy for hot-100 + billboard-200 (after the rebuild).
- The deployed app: Latest Charts, detail pages, Records, /compare, gender filter, the new-chart selector.

## Rollback
- Phase A is additive → drop the new objects, or `pg_restore` the snapshot.
- Phase C → `pg_restore` the §5 `pre-003` dump.

## Optional reconciliation (Phase 8) — heal split artist fragments
Run BEFORE Phase A step 1 if you want the comma+ampersand merges (Earth/Wind/Fire, Tyler/The Creator):
```bash
.venv/bin/python -m billboard_stats.etl.reconcile_artists --dry-run   # review the merges/deletes
.venv/bin/python -m billboard_stats.etl.reconcile_artists
```
