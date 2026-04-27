---
last_mapped_date: 2026-04-27
---
# Tech Stack

**Language:** Python 3.9+  
**Frontend Framework:** Streamlit (>= 1.30)  
**Database:** PostgreSQL 12+ (requires `pg_trgm` extension for pattern matching and search)  

## Dependencies
- `psycopg2-binary` (>= 2.9): Database adapter for PostgreSQL
- `pydantic` (>= 2.0): Data validation and settings management (used in `models/schemas.py`)
- `billboard.py` (>= 7.0): Unofficial API wrapper for retrieving Billboard charts
- `altair` (>= 5.0): Declarative statistical visualizations for interactive charts in Streamlit
- `python-telegram-bot[job-queue]` (>= 20.0): Telegram bot framework
- `pytz` (>= 2024.1): World timezone definitions

## Environment & Configuration
Database connection is configured using standard PostgreSQL environment variables:
- `PGHOST` (default: localhost)
- `PGPORT` (default: 5432)
- `PGDATABASE` (default: billboard)
- `PGUSER` (default: postgres)
- `PGPASSWORD` (default: yourpassword)
