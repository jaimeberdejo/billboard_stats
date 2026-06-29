-- Migration 003 — Retire v1.0 Legacy Tables (Phase 15, Plan 04)
-- =============================================================================
-- Operator-applied, DESTRUCTIVE, IDEMPOTENT migration that retires the v1.0
-- bifurcated storage now that every live read (Wave A), every write (Wave B),
-- and the TypeScript data layer (Wave C) have been re-pointed onto the
-- polymorphic `chart_entries` table keyed by `chart_id`. It:
--   * promotes `chart_weeks.chart_id` to NOT NULL and gives it a FULL
--     UNIQUE(chart_id, chart_date) week-dedup key (the new sole conflict
--     target the collapsed loader upsert already relies on);
--   * drops the now-dead `chart_weeks.chart_type` column (auto-dropping its
--     CHECK and the old UNIQUE(chart_date, chart_type));
--   * drops the bifurcated `hot100_entries` / `b200_entries` tables and every
--     index that fed them, plus the now-redundant partial
--     `uq_chart_weeks_chart_id_date` index (superseded by the full UNIQUE).
--
-- It is applied by billboard_stats/etl/migrate_retire_legacy.py, which wraps the
-- whole thing in a SINGLE transaction and asserts post-migration invariants
-- (the two legacy tables are gone, `chart_type` is gone, no chart_weeks row has
-- a NULL chart_id, the chart_entries row count is UNCHANGED, and the
-- UNIQUE(chart_id, chart_date) constraint exists), rolling back on any mismatch.
-- The Python runner — NOT this file — owns those assertions so a violation can
-- roll back.
--
-- =============================================================================
-- DEPLOY ORDERING (M-02) — APPLY THIS MIGRATION BEFORE THE NEXT LIVE LOAD
-- =============================================================================
-- The Phase-15 loader (billboard_stats/etl/loader._upsert_chart_week) now upserts
-- weeks with `ON CONFLICT (chart_id, chart_date)`, whose arbiter is the FULL
-- `chart_weeks_chart_id_date_key` UNIQUE this migration adds in step 2. The old
-- partial `uq_chart_weeks_chart_id_date` index is NOT a valid arbiter for that
-- unqualified ON CONFLICT. Therefore on a LIVE/migrated DB this migration MUST be
-- applied BEFORE the first post-Phase-15 `run_etl` / loader run — otherwise every
-- week's upsert aborts with "no unique or exclusion constraint matching the
-- ON CONFLICT specification". A fresh `schema.sql` install already carries the
-- full constraint, so this ordering constraint is specific to live/migrated DBs.
--
-- =============================================================================
-- REVERSIBILITY / SAFETY CONTRACT (success criterion 3) — READ BEFORE APPLYING
-- =============================================================================
-- This migration is IRREVERSIBLE at the data level: DROP TABLE destroys the
-- v1.0 per-chart entry rows. Those rows are already redundant (chart_entries
-- holds the same data, proven row-for-row by tests/test_etl_equivalence.py and
-- tests/test_stats_equivalence.py), but the OPERATOR MUST take a backup FIRST so
-- the apply is reversible:
--
--   -- (operator pre-drop backup, run on a throwaway Neon branch first)
--   pg_dump --no-owner --no-privileges \
--           -t hot100_entries -t b200_entries -t chart_weeks \
--           "$DATABASE_URL" > backups/pre_003_retire_legacy.sql
--   -- (or, in-database, snapshot the entry tables before the drop:)
--   -- CREATE TABLE hot100_entries_backup AS SELECT * FROM hot100_entries;
--   -- CREATE TABLE b200_entries_backup  AS SELECT * FROM b200_entries;
--
-- Recovery, if ever needed, restores from that dump. The runner's invariant
-- asserts (chart_entries count unchanged, no NULL chart_id) are the in-band
-- guard that the drop is safe; the backup is the out-of-band guard.
--
-- Safety contract (mirrors db/migrations/002_gender.sql house style):
--   * Every statement is IDEMPOTENT: ALTER ... IF EXISTS, DROP ... IF EXISTS, a
--     DO-block-guarded ADD CONSTRAINT (Postgres has no ADD CONSTRAINT IF NOT
--     EXISTS), so a fresh install and an existing install converge to the same
--     shape and re-application is a clean no-op.
--   * DDL ORDER is non-negotiable: the new NOT NULL + full UNIQUE are added
--     BEFORE the column/table drops, so `chart_weeks` is NEVER left without a
--     week-dedup key mid-migration.
--   * This block is byte-for-byte consistent (after whitespace normalization)
--     with the final post-drop shape in db/schema.sql AND with
--     migrate_retire_legacy._DDL_STATEMENTS; a test enforces that lockstep (W-3).

-- -----------------------------------------------------------------------------
-- 1. Promote chart_id to NOT NULL (every week now carries a chart identity).
-- -----------------------------------------------------------------------------
ALTER TABLE chart_weeks ALTER COLUMN chart_id SET NOT NULL;

-- -----------------------------------------------------------------------------
-- 2. Add the FULL UNIQUE(chart_id, chart_date) week-dedup key idempotently. This
--    is the sole ON CONFLICT target the collapsed loader upsert (Wave B) relies
--    on. Guard on pg_constraint by the deterministic name because Postgres has
--    no ADD CONSTRAINT IF NOT EXISTS.
-- -----------------------------------------------------------------------------
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chart_weeks_chart_id_date_key') THEN ALTER TABLE chart_weeks ADD CONSTRAINT chart_weeks_chart_id_date_key UNIQUE (chart_id, chart_date); END IF; END $$;

-- -----------------------------------------------------------------------------
-- 3. Drop the dead chart_type column. This AUTO-DROPS its CHECK constraint and
--    the old UNIQUE(chart_date, chart_type) that depended on it.
-- -----------------------------------------------------------------------------
ALTER TABLE chart_weeks DROP COLUMN IF EXISTS chart_type;

-- -----------------------------------------------------------------------------
-- 4. Drop the legacy indexes: the chart_type composite index, the now-redundant
--    partial (chart_id, chart_date) index (superseded by the full UNIQUE added
--    in step 2), and the four per-entry indexes on the bifurcated tables.
-- -----------------------------------------------------------------------------
DROP INDEX IF EXISTS idx_chart_weeks_type_date;
DROP INDEX IF EXISTS uq_chart_weeks_chart_id_date;
DROP INDEX IF EXISTS idx_hot100_song_id;
DROP INDEX IF EXISTS idx_hot100_chart_week;
DROP INDEX IF EXISTS idx_b200_album_id;
DROP INDEX IF EXISTS idx_b200_chart_week;

-- -----------------------------------------------------------------------------
-- 5. Drop the bifurcated v1.0 entry tables (data lives in chart_entries now).
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS hot100_entries;
DROP TABLE IF EXISTS b200_entries;
