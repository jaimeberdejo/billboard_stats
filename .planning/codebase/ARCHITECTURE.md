---
last_mapped_date: 2026-04-27
---
# Architecture

## Design Patterns and Layers
The application follows a pragmatic tiered architecture tailored for a data-centric Streamlit application:
1. **Presentation Layer (Frontend):** 
   - Uses **Streamlit** (primarily in `app.py`) for a fast, responsive user interface. 
   - A secondary surface exists as a Telegram Bot (in `bot/`).
2. **Service Layer:** 
   - Modules in `services/` (e.g., `song_service.py`, `artist_service.py`) encapsulate the core business logic. They fetch data via SQL queries and return typed data models.
3. **Data Model Layer:** 
   - **Pydantic** is used in `models/schemas.py` to enforce rigid data validation and typing for entities coming out of the database (e.g., `Song`, `ChartRunEntry`, `SongStats`).
4. **Data Access & Storage Layer:** 
   - Logic in `db/connection.py` handles the psycopg2 connection pooling and provides fundamental SQL execution functions (`execute_query`).
   - The system utilizes **PostgreSQL**, leveraging the `pg_trgm` extension for performant fuzzy searching.
5. **Data Pipeline (ETL):** 
   - Located in the `etl/` directory, this pipeline handles ingestion, fetching raw charts from Billboard, parsing JSON records, and executing bulk inserts to Postgres.
   - `stats_builder.py` reconstructs optimized read-heavy materialized statistic tables like `song_stats`.

## Data Flow
`Streamlit Event (app.py) -> Service Function (services/) -> Raw SQL Query (db/connection.py) -> PostgreSQL -> Pydantic Model (models/) -> Streamlit UI`
