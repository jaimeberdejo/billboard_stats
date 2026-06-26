-- Migration 002 — Artist Gender Enrichment (Phase 12, Plan 01)
-- =============================================================================
-- Operator-applied, STRICTLY ADDITIVE, IDEMPOTENT migration that adds three
-- first-class gender columns to the v1.0 `artists` table WITHOUT mutating
-- anything the existing frontend reads. It gives every artist a `gender`
-- attribute (default 'unknown' — a first-class value, NOT a sentinel for
-- "missing"), a `gender_source` provenance column, and a `gender_source_id`
-- holding the stable MBID/QID used for the match (GENDER-01).
--
-- It is applied by billboard_stats/etl/migrate_gender.py, which wraps the whole
-- thing in a SINGLE transaction and asserts post-migration invariants (the 3
-- columns exist, artist row count is unchanged, every row's gender is
-- non-NULL), rolling back on any mismatch. The Python runner — NOT this file —
-- owns those assertions so a violation can roll back.
--
-- Safety contract (mirrors db/schema.sql's additive Phase 12 block):
--   * DDL is guarded with ADD COLUMN IF NOT EXISTS so a fresh install and an
--     existing install converge to the same shape and re-application is a no-op.
--     The DDL here is byte-for-byte consistent (after whitespace normalization)
--     with the Phase 12 block appended to db/schema.sql by this plan AND with
--     migrate_gender._DDL_STATEMENTS; a test enforces that lockstep (W-3).
--   * `gender` is NOT NULL DEFAULT 'unknown', so every pre-existing artist row
--     backfills to 'unknown' automatically (PG 12+ makes a constant default a
--     metadata-only change — no table rewrite).
--   * The 5-value vocabulary CHECK (female|male|group|mixed|unknown) is added
--     idempotently inside a DO block that first tests pg_constraint for the
--     constraint name — Postgres has no ADD CONSTRAINT IF NOT EXISTS, so the
--     DO-block guard is what keeps a re-run a clean no-op.
--   * It DROPS, RENAMES, or NARROWS no existing object. The v1.0 artists
--     columns (id, name, image_url) and the GIN trigram index on name are
--     untouched; these are pure additions.

-- -----------------------------------------------------------------------------
-- 1. DDL (additive; IF NOT EXISTS) — identical to db/schema.sql's Phase 12
--    block and migrate_gender._DDL_STATEMENTS (W-3 lockstep).
-- -----------------------------------------------------------------------------

-- gender: the first-class act-type/gender attribute. 'unknown' is a real value
-- (the default), not a missing sentinel. Existing rows backfill to 'unknown'.
ALTER TABLE artists ADD COLUMN IF NOT EXISTS gender VARCHAR(8) NOT NULL DEFAULT 'unknown';

-- gender_source: provenance of the match (musicbrainz|wikidata|manual or NULL).
ALTER TABLE artists ADD COLUMN IF NOT EXISTS gender_source VARCHAR(16);

-- gender_source_id: the stable ID used for the match — an MBID (36 chars) or a
-- Wikidata QID. Persisting the ID (not the raw name) is what makes the enricher
-- idempotent and re-runnable.
ALTER TABLE artists ADD COLUMN IF NOT EXISTS gender_source_id VARCHAR(64);

-- Constrain gender to the 5-value vocabulary, added idempotently. Postgres has
-- no ADD CONSTRAINT IF NOT EXISTS, so guard on pg_constraint by the
-- deterministic name artists_gender_check before adding it.
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'artists_gender_check') THEN ALTER TABLE artists ADD CONSTRAINT artists_gender_check CHECK (gender IN ('female', 'male', 'group', 'mixed', 'unknown')); END IF; END $$;
