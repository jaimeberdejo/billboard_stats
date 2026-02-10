# Billboard Stats

A data platform for exploring Billboard Hot 100 and Billboard 200 chart history, built with Python, PostgreSQL, and Streamlit.

## Features

- **Latest Charts** — Browse any weekly chart with position, peak, movement, and weeks on chart
- **Search** — Find artists, songs, or albums by name
- **Artist Detail** — Career stats, full discography with chart performance, navigable song/album lists
- **Song / Album Detail** — Peak position, total weeks, chart run history table and interactive visualization
- **Records** — Leaderboards including:
  - Most weeks at #1, longest chart runs, biggest debuts, fastest to #1
  - Most #1 songs/albums by artist (with inline drill-down showing the actual items)
  - Most entries by artist, most simultaneous entries
  - Custom query builder with artist filter, peak/debut position range sliders, and min-weeks filter
- **Data Status** — Database stats and one-click incremental updates

## Architecture

```
billboard_stats/
├── app.py                  # Streamlit frontend (all pages)
├── db/
│   ├── connection.py       # psycopg2 connection pool
│   └── schema.sql          # DDL (CREATE TABLE IF NOT EXISTS)
├── models/
│   └── schemas.py          # Pydantic data models
├── etl/
│   ├── fetcher.py          # Downloads chart JSON via billboard.py
│   ├── json_parser.py      # Parses stored JSON files
│   ├── artist_parser.py    # Splits compound artist credits
│   ├── loader.py           # Full ETL: JSON → PostgreSQL
│   ├── stats_builder.py    # Builds song_stats, album_stats, artist_stats
│   └── updater.py          # Incremental update + gap repair CLI
└── services/
    ├── artist_service.py
    ├── song_service.py
    ├── album_service.py
    ├── chart_service.py
    ├── records_service.py
    └── data_status_service.py
```

## Prerequisites

- Python 3.9+
- PostgreSQL 12+ (with `pg_trgm` extension)

## Setup

1. **Create the database:**

```bash
createdb billboard
psql billboard -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
psql billboard -f billboard_stats/db/schema.sql
```

2. **Install dependencies:**

```bash
pip install -r requirements.txt
```

3. **Configure database connection** (optional — defaults to `localhost:5432/billboard`):

```bash
export PGHOST=localhost
export PGPORT=5432
export PGDATABASE=billboard
export PGUSER=postgres
export PGPASSWORD=yourpassword
```

4. **Load chart data:**

```python
from billboard_stats.etl.loader import load_all
load_all()  # Fetches and loads all available chart history
```

5. **Build stats tables:**

```bash
python3 rebuild_stats.py
```

## Running

```bash
streamlit run billboard_stats/app.py
```

## Updating data

Use the **Data Status** page in the app, or run from the command line:

```bash
python3 -m billboard_stats.etl.updater
```

This fetches new weeks since the last loaded date and repairs any gaps.
