-- Migration 004: chart_entries storage cleanup (dead surrogate key + redundant index)
--
-- WHAT & WHY
--   chart_entries carried a BIGSERIAL surrogate `id` PRIMARY KEY that had ZERO
--   index scans in production and no foreign-key or application-code dependency:
--   the row's real identity is the natural key (chart_week_id, rank), which was
--   already enforced by a UNIQUE constraint. The single-column index
--   idx_ce_week(chart_week_id) was fully redundant -- the (chart_week_id, rank)
--   index already serves every lookup on chart_week_id via its leading column.
--
--   This migration removes the dead surrogate key and the redundant index and
--   promotes the natural key to PRIMARY KEY. On the 2-chart production dataset
--   (~1.05M rows) this reclaims ~33 MB of index space immediately (the 22 MB id
--   PK index + the 11 MB idx_ce_week); the dropped `id` column's heap space is
--   reclaimed lazily on the next table rewrite. The saving scales with row count
--   as additional charts are loaded, and fewer indexes means a smaller WAL spike
--   during bulk loads.
--
-- SAFETY
--   * Transactional DDL -- the whole thing commits or rolls back atomically.
--   * No FK references chart_entries; the app/ETL never read or wrote `id`.
--   * Fully reversible (see the rollback block at the foot of this file).
--   * Run VACUUM ANALYZE afterwards (separately -- it cannot run in a txn block)
--     to refresh planner stats and reclaim the small dead-tuple backlog.

BEGIN;

-- 1. Drop the redundant single-column index (covered by chart_entries'
--    (chart_week_id, rank) unique index leading column).
DROP INDEX IF EXISTS idx_ce_week;

-- 2. Drop the unused surrogate primary key, then the natural-key UNIQUE
--    constraint (its index is rebuilt as the PRIMARY KEY in step 4).
ALTER TABLE chart_entries DROP CONSTRAINT chart_entries_pkey;
ALTER TABLE chart_entries DROP CONSTRAINT chart_entries_chart_week_id_rank_key;

-- 3. Drop the now-orphan surrogate column (cascades to chart_entries_id_seq).
ALTER TABLE chart_entries DROP COLUMN id;

-- 4. Promote the natural key to PRIMARY KEY (chart_week_id & rank are already
--    NOT NULL, so no row rewrite/scan failure is possible).
ALTER TABLE chart_entries
    ADD CONSTRAINT chart_entries_pkey PRIMARY KEY (chart_week_id, rank);

COMMIT;

-- Post-migration (run OUTSIDE a transaction block):
--   VACUUM ANALYZE chart_entries;
--   VACUUM ANALYZE songs; VACUUM ANALYZE albums; VACUUM ANALYZE artists;

-- ---------------------------------------------------------------------------
-- ROLLBACK (restore the v1.0 surrogate-key shape):
--   BEGIN;
--   ALTER TABLE chart_entries DROP CONSTRAINT chart_entries_pkey;
--   ALTER TABLE chart_entries
--       ADD CONSTRAINT chart_entries_chart_week_id_rank_key UNIQUE (chart_week_id, rank);
--   ALTER TABLE chart_entries ADD COLUMN id BIGSERIAL PRIMARY KEY;
--   CREATE INDEX idx_ce_week ON chart_entries(chart_week_id);
--   COMMIT;
-- ---------------------------------------------------------------------------
