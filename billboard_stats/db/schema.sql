-- Billboard Music Statistics Platform — Database Schema
-- Requires PostgreSQL 12+ with pg_trgm extension

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- Core Tables
-- ============================================================

-- Individual artists (normalized, deduplicated)
CREATE TABLE artists (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL UNIQUE,
    image_url   TEXT
);

-- ============================================================
-- Phase 12: Artist gender enrichment (additive)
-- ============================================================
-- Adds three first-class gender columns to the artists table above. They are
-- STRICTLY ADDITIVE: the v1.0 artists shape (id, name, image_url) and the GIN
-- trigram index on name are kept verbatim. The fresh CREATE TABLE artists above
-- does NOT list these columns; the ALTER ... ADD COLUMN IF NOT EXISTS form below
-- is what reconciles a fresh install with an existing one (mirror how Phase 9
-- kept schema.sql and 001_multichart.sql in lockstep). This block is
-- byte-for-byte consistent (after whitespace normalization) with
-- db/migrations/002_gender.sql and migrate_gender._DDL_STATEMENTS; a test
-- enforces that lockstep (W-3). 'unknown' is a FIRST-CLASS default value, not a
-- missing sentinel; population of real values is the Phase 12 enricher's job,
-- not this schema.

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

-- Unique songs (identified by title + raw credit)
CREATE TABLE songs (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(500) NOT NULL,
    artist_credit   VARCHAR(500) NOT NULL,
    image_url       TEXT,
    UNIQUE(title, artist_credit)
);

-- Unique albums
CREATE TABLE albums (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(500) NOT NULL,
    artist_credit   VARCHAR(500) NOT NULL,
    image_url       TEXT,
    UNIQUE(title, artist_credit)
);

-- Many-to-many: songs <-> normalized artists
CREATE TABLE song_artists (
    song_id     INT REFERENCES songs(id),
    artist_id   INT REFERENCES artists(id),
    role        VARCHAR(20) NOT NULL DEFAULT 'primary',
    PRIMARY KEY (song_id, artist_id)
);

-- Many-to-many: albums <-> normalized artists
CREATE TABLE album_artists (
    album_id    INT REFERENCES albums(id),
    artist_id   INT REFERENCES artists(id),
    role        VARCHAR(20) NOT NULL DEFAULT 'primary',
    PRIMARY KEY (album_id, artist_id)
);

-- Each weekly chart publication. As of Phase 15 the v1.0 per-publication type
-- column + its CHECK and the bifurcated date/type UNIQUE are RETIRED; a week's
-- chart identity is carried solely by the chart_id FK (NOT NULL since Phase 15)
-- and deduped on the full UNIQUE(chart_id, chart_date). The chart_id FK is added
-- by the Phase 9 block below (and promoted to NOT NULL + given the full UNIQUE
-- by the Phase 15 block at the end of this file), so a FRESH install and a
-- migrated install converge to the same final shape.
CREATE TABLE chart_weeks (
    id          SERIAL PRIMARY KEY,
    chart_date  DATE NOT NULL
);

-- ============================================================
-- Multi-Chart Generalization (Phase 9, additive)
-- ============================================================
-- These objects generalize the (now-retired) bifurcated per-chart entry model
-- into a chart registry + a single polymorphic chart_entries table + a per-chart
-- artist rollup. chart_entries is now the SOLE entry store.
-- The v1.0 stats tables (artist_stats, song_stats, album_stats) are kept. All
-- new statements use IF NOT EXISTS so a fresh install and an existing install
-- converge to the same shape and re-application is a no-op. Seeding of the
-- charts registry and backfill of chart_entries / artist_chart_stats happen
-- in the Phase 9 migration (Plan 02), not here. The chart_weeks.chart_id FK is
-- added here and promoted to NOT NULL + given the full UNIQUE(chart_id,
-- chart_date) by the Phase 15 block at the end of this file.

-- Registry of every chart we ingest (DATA-01). Generalizes the retired v1.0
-- per-publication type CHECK into an open, self-describing table.
CREATE TABLE IF NOT EXISTS charts (
    id          SERIAL PRIMARY KEY,
    slug        VARCHAR(64) NOT NULL UNIQUE,    -- billboard.py slug, e.g. 'hot-100'
    title       VARCHAR(128),                   -- human label, e.g. 'Billboard Hot 100'
    entity_kind VARCHAR(16) NOT NULL CHECK (entity_kind IN ('song', 'album', 'artist')),  -- ranked entity type
    category    VARCHAR(32),                    -- UI grouping, e.g. 'core' | 'genre' | 'artist'
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,  -- include in weekly fetch?
    first_date  DATE,                           -- earliest real chart (post-phantom)
    sort_order  SMALLINT NOT NULL DEFAULT 100
);

-- Wire chart_weeks to the registry. The FK is added here; the Phase 15 block at
-- the end of this file promotes it to NOT NULL and adds the full
-- UNIQUE(chart_id, chart_date) week-dedup key (every week now carries a chart
-- identity; chart_entries is the sole entry store).
ALTER TABLE chart_weeks ADD COLUMN IF NOT EXISTS chart_id INT REFERENCES charts(id);

-- Unified, polymorphic weekly entries (DATA-02). One table for all charts;
-- exactly one of song_id / album_id / artist_id is set per row, enforced by the
-- num_nonnulls CHECK. artist_id is a first-class polymorphic target so Artist
-- 100 (entity_kind='artist') drops in for free in Phase 11 with no schema
-- change. Mirrors the v1.0 per-entry columns (rank, peak_pos, last_pos,
-- weeks_on_chart, is_new) and the UNIQUE(chart_week_id, rank) idempotency
-- constraint carried over from the retired v1.0 per-chart entry tables.
CREATE TABLE IF NOT EXISTS chart_entries (
    chart_id        INT NOT NULL REFERENCES charts(id),
    chart_week_id   INT NOT NULL REFERENCES chart_weeks(id),
    song_id         INT REFERENCES songs(id),    -- exactly one of the three is non-null
    album_id        INT REFERENCES albums(id),
    artist_id       INT REFERENCES artists(id),
    rank            SMALLINT NOT NULL,
    peak_pos        SMALLINT,
    last_pos        SMALLINT,
    weeks_on_chart  SMALLINT,
    is_new          BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (chart_week_id, rank),  -- natural key; the v1.0 surrogate id was dropped (migration 004)
    CHECK (num_nonnulls(song_id, album_id, artist_id) = 1)  -- one-of-three polymorphism guard
);

-- Per-chart artist rollup (DATA-03). One ROW per (artist, chart) — adding a
-- chart adds rows, never columns. Generalizes the per-chart facts that the v1.0
-- artist_stats table hardcodes as hot100_/b200_ columns. Career totals derive
-- by aggregation (SUM/MIN/MAX GROUP BY artist_id) over these rows. The column
-- names declared here are authoritative — Plan 03's INSERT writes exactly these.
-- Coexists with artist_stats (compat); artist_stats is NOT altered or dropped.
CREATE TABLE IF NOT EXISTS artist_chart_stats (
    artist_id        INT  NOT NULL REFERENCES artists(id),
    chart_id         INT  NOT NULL REFERENCES charts(id),
    total_entries    INT  NOT NULL DEFAULT 0,   -- songs OR albums OR direct artist entries on this chart
    total_weeks      INT  NOT NULL DEFAULT 0,   -- summed entity-weeks of presence (NOT distinct weeks): COUNT(*) of valid entries rolled up to this artist; one entity charting per week = +1, two entities same week = +2. Matches v1.0 total_hot100_weeks/total_b200_weeks. (WR-01)
    number_ones      INT  NOT NULL DEFAULT 0,   -- count of #1 placements on this chart
    best_peak        SMALLINT,                  -- best (lowest) rank achieved on this chart
    max_simultaneous INT  NOT NULL DEFAULT 0,   -- max concurrent entries in a single week
    first_date       DATE,                      -- earliest chart_week date on this chart
    last_date        DATE,                      -- latest chart_week date on this chart
    PRIMARY KEY (artist_id, chart_id)
);

-- ============================================================
-- Pre-computed Stats Tables
-- ============================================================

-- Aggregated stats per song
CREATE TABLE song_stats (
    song_id             INT PRIMARY KEY REFERENCES songs(id),
    total_weeks         INT NOT NULL DEFAULT 0,
    peak_position       SMALLINT,
    weeks_at_peak       INT NOT NULL DEFAULT 0,
    weeks_at_number_one INT NOT NULL DEFAULT 0,
    debut_date          DATE,
    last_date           DATE,
    debut_position      SMALLINT
);

-- Aggregated stats per album
CREATE TABLE album_stats (
    album_id            INT PRIMARY KEY REFERENCES albums(id),
    total_weeks         INT NOT NULL DEFAULT 0,
    peak_position       SMALLINT,
    weeks_at_peak       INT NOT NULL DEFAULT 0,
    weeks_at_number_one INT NOT NULL DEFAULT 0,
    debut_date          DATE,
    last_date           DATE,
    debut_position      SMALLINT
);

-- Aggregated career stats per artist (cross-chart)
CREATE TABLE artist_stats (
    artist_id               INT PRIMARY KEY REFERENCES artists(id),
    total_hot100_songs      INT NOT NULL DEFAULT 0,
    total_b200_albums       INT NOT NULL DEFAULT 0,
    total_hot100_weeks      INT NOT NULL DEFAULT 0,
    total_b200_weeks        INT NOT NULL DEFAULT 0,
    hot100_number_ones      INT NOT NULL DEFAULT 0,
    b200_number_ones        INT NOT NULL DEFAULT 0,
    best_hot100_peak        SMALLINT,
    best_b200_peak          SMALLINT,
    first_chart_date        DATE,
    latest_chart_date       DATE,
    max_simultaneous_hot100 INT NOT NULL DEFAULT 0
);

-- ============================================================
-- Indexes
-- ============================================================

-- Multi-chart entry indexes (Phase 9): mirror the per-entry indexes above for
-- the polymorphic chart_entries table — by week, by chart, and a partial index
-- per entity FK so each lookup matches the v1.0 access pattern.
CREATE INDEX IF NOT EXISTS idx_ce_chart ON chart_entries(chart_id);
-- (no idx_ce_week: redundant with the (chart_week_id, rank) PRIMARY KEY's leading column — migration 004)
CREATE INDEX IF NOT EXISTS idx_ce_song ON chart_entries(song_id) WHERE song_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ce_album ON chart_entries(album_id) WHERE album_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ce_artist ON chart_entries(artist_id) WHERE artist_id IS NOT NULL;

-- Per-chart artist rollup index (mirrors ARCHITECTURE.md idx_acs_chart).
CREATE INDEX IF NOT EXISTS idx_acs_chart ON artist_chart_stats(chart_id);

-- Fast lookups by date
CREATE INDEX idx_chart_weeks_date ON chart_weeks(chart_date);

-- Fast lookups by artist_id on join tables
CREATE INDEX IF NOT EXISTS idx_song_artists_artist ON song_artists(artist_id);
CREATE INDEX IF NOT EXISTS idx_album_artists_artist ON album_artists(artist_id);

-- Artist name search (trigram)
CREATE INDEX idx_artists_name_trgm ON artists USING gin (name gin_trgm_ops);

-- Song/album title search (trigram)
CREATE INDEX idx_songs_title_trgm ON songs USING gin (title gin_trgm_ops);
CREATE INDEX idx_albums_title_trgm ON albums USING gin (title gin_trgm_ops);

-- ============================================================
-- Phase 15: Retire v1.0 legacy tables — final chart_weeks shape
-- ============================================================
-- These two ADDITIVE statements bring chart_weeks to its final post-retirement
-- shape so a FRESH install converges to the same shape a migrated install
-- reaches: chart_id is promoted to NOT NULL and given the full
-- UNIQUE(chart_id, chart_date) week-dedup key (the sole entry-week conflict
-- target now that chart_entries is the sole entry store). These are the
-- INVARIANT-adding statements db/migrations/003_retire_legacy.sql applies BEFORE
-- its drops; they are byte-for-byte consistent (after whitespace normalization)
-- with that file AND migrate_retire_legacy._DDL_STATEMENTS, and a test enforces
-- that lockstep (W-3). The migration's DROP COLUMN/INDEX/TABLE statements are
-- NOT replayed here: on a fresh install the legacy objects were never created
-- above, so this file simply omits them and converges to the same end state.
ALTER TABLE chart_weeks ALTER COLUMN chart_id SET NOT NULL;
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chart_weeks_chart_id_date_key') THEN ALTER TABLE chart_weeks ADD CONSTRAINT chart_weeks_chart_id_date_key UNIQUE (chart_id, chart_date); END IF; END $$;
