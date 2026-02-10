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

-- Each weekly chart publication
CREATE TABLE chart_weeks (
    id          SERIAL PRIMARY KEY,
    chart_date  DATE NOT NULL,
    chart_type  VARCHAR(20) NOT NULL CHECK (chart_type IN ('hot-100', 'billboard-200')),
    UNIQUE(chart_date, chart_type)
);

-- Weekly Hot 100 position entries
CREATE TABLE hot100_entries (
    id              SERIAL PRIMARY KEY,
    chart_week_id   INT NOT NULL REFERENCES chart_weeks(id),
    song_id         INT NOT NULL REFERENCES songs(id),
    rank            SMALLINT NOT NULL,
    peak_pos        SMALLINT,
    last_pos        SMALLINT,
    weeks_on_chart  SMALLINT,
    is_new          BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(chart_week_id, rank)
);

-- Weekly Billboard 200 position entries
CREATE TABLE b200_entries (
    id              SERIAL PRIMARY KEY,
    chart_week_id   INT NOT NULL REFERENCES chart_weeks(id),
    album_id        INT NOT NULL REFERENCES albums(id),
    rank            SMALLINT NOT NULL,
    peak_pos        SMALLINT,
    last_pos        SMALLINT,
    weeks_on_chart  SMALLINT,
    is_new          BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(chart_week_id, rank)
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

-- Fast lookups for chart runs
CREATE INDEX idx_hot100_song_id ON hot100_entries(song_id);
CREATE INDEX idx_hot100_chart_week ON hot100_entries(chart_week_id);
CREATE INDEX idx_b200_album_id ON b200_entries(album_id);
CREATE INDEX idx_b200_chart_week ON b200_entries(chart_week_id);

-- Fast lookups by date
CREATE INDEX idx_chart_weeks_date ON chart_weeks(chart_date);
CREATE INDEX idx_chart_weeks_type_date ON chart_weeks(chart_type, chart_date);

-- Artist name search (trigram)
CREATE INDEX idx_artists_name_trgm ON artists USING gin (name gin_trgm_ops);

-- Song/album title search (trigram)
CREATE INDEX idx_songs_title_trgm ON songs USING gin (title gin_trgm_ops);
CREATE INDEX idx_albums_title_trgm ON albums USING gin (title gin_trgm_ops);
