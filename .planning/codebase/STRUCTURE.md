---
last_mapped_date: 2026-04-27
---
# Codebase Structure

The codebase layout follows a functional separation of concerns:

- `app.py`
  - The main Streamlit entry point. Contains UI components, routing (`st.session_state["page"]`), sidebars, and rendering logic.
- `rebuild_stats.py`
  - A small top-level CLI utility script to trigger reconstruction of the materialized statistics tables.
- `db/`
  - `connection.py`: Manages PostgreSQL connection lifecycle and exports `execute_query`.
  - `schema.sql`: Contains schema DDL components.
- `etl/`
  - Encapsulates the entire ingestion pipeline: extracting JSON via the `billboard` Python API wrapper, processing entries, and loading them into SQL (`loader.py`). Handles gap repairs (`updater.py`).
- `models/`
  - `schemas.py`: Contains strictly typed **Pydantic** domain models (e.g., `Artist`, `Song`, `SongWithStats`).
- `services/`
  - Domain-specific logic grouped by entities (`artist_service.py`, `song_service.py`, `album_service.py`, `chart_service.py`, `records_service.py`).
- `bot/`
  - Encapsulates Telegram bot integration, built over `python-telegram-bot`.
