# Billboard Stats

Billboard Stats is a read-only music chart explorer built on Next.js and Neon PostgreSQL. It surfaces Billboard Hot 100 and Billboard 200 data with latest-chart browsing, search, records, and detail pages for songs, albums, and artists.

The repository also contains the legacy Python ETL and support code used to fetch chart JSON, load it into PostgreSQL, and rebuild aggregate stats.

## What’s in the repo

- `src/` — the production Next.js app
- `src/app/` — App Router pages and API routes
- `src/lib/` — database-backed query helpers for charts, search, records, details, and data status
- `billboard_stats/` — Python ETL, database schema, legacy Streamlit app, and Telegram bot code
- `.planning/` — GSD planning and execution artifacts

## App features

- Latest charts for Hot 100 and Billboard 200
- Detail pages for songs, albums, and artists
- Search across songs, albums, and artists
- Records / leaderboards views
- Data status view showing row counts and latest chart dates

## Web routes

- `/` — latest charts
- `/search` — search
- `/records` — records and leaderboards
- `/status` — data status
- `/song/[id]` — song detail
- `/album/[id]` — album detail
- `/artist/[id]` — artist detail

## API routes

- `/api/charts`
- `/api/search`
- `/api/records`
- `/api/data-status`
- `/api/health`

## Tech stack

- Next.js 16
- React 19
- TypeScript
- Tailwind CSS 4
- Neon PostgreSQL via `@neondatabase/serverless`
- Python ETL with `psycopg2`, `billboard.py`, `pydantic`, `streamlit`

## Requirements

- Node.js 20+
- npm
- Python 3.11+ recommended
- A Neon PostgreSQL database

## Environment variables

The repo already documents the expected env vars in [.env.example](./.env.example).

### Next.js app

The web app requires:

```bash
DATABASE_URL=postgresql://user:password@ep-pooler-name-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require
```

This should be a pooled Neon connection string.

### Python ETL

The ETL uses direct PostgreSQL connection settings:

```bash
PGHOST=ep-<id>.us-east-1.aws.neon.tech
PGPORT=5432
PGDATABASE=neondb
PGUSER=<neon-user>
PGPASSWORD=<neon-password>
PGSSLMODE=require
```

The repo currently expects these to be available through `billboard_stats/.env` or exported in the shell.

## Local development

Install JavaScript dependencies:

```bash
npm install
```

Start the Next.js dev server:

```bash
npm run dev
```

Build for production:

```bash
npm run build
```

Run lint:

```bash
npm run lint
```

## Python setup

Install Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## ETL and data refresh

The canonical updater entrypoint is:

```bash
python -m billboard_stats.etl.updater
```

Other supported modes:

```bash
python -m billboard_stats.etl.updater --repair
python -m billboard_stats.etl.updater --update
```

What it does:

- repairs missing recent chart files
- downloads newer chart data
- loads new rows into PostgreSQL
- rebuilds aggregate stats tables

## Phase 6 ETL operations

Use the committed shell wrapper for manual backfills and weekly maintenance:

```bash
chmod +x scripts/run_weekly_etl.sh
./scripts/run_weekly_etl.sh
```

Useful modes:

```bash
./scripts/run_weekly_etl.sh --repair
./scripts/run_weekly_etl.sh --update
```

The script:

- loads ETL credentials from `billboard_stats/.env` when present
- falls back to already-exported `PG*` variables for CI or shell-driven runs
- runs the same `python -m billboard_stats.etl.updater` entrypoint used for weekly automation

### Post-run verification

After a backfill or weekly update, verify the public app freshness:

```bash
curl -s https://billboard-stats.vercel.app/api/data-status
curl -s "https://billboard-stats.vercel.app/api/charts?chart=hot-100" | head -c 200
curl -s "https://billboard-stats.vercel.app/api/charts?chart=billboard-200" | head -c 200
```

Expected:

- `/api/data-status` reports non-future latest dates
- Hot 100 latest date advances beyond stale checkpoints when new data exists
- both chart endpoints return real JSON payloads

The ETL and data-status layers now treat only non-future Saturday chart dates as valid latest weeks, so invalid future rows/files should no longer masquerade as current data.

## Database notes

- Database access for the web app is centralized in `src/lib/db.ts`
- SQL schema lives in `billboard_stats/db/schema.sql`
- The dataset includes normalized artist join tables for songs and albums
- The app is read-only; write-side data maintenance currently happens through the Python ETL

## Deployment

The app is designed for:

- Neon PostgreSQL for data storage
- Vercel for web deployment

The current deployment flow expects:

- `DATABASE_URL` set in Vercel
- GitHub connected to Vercel
- production deploys from the main branch

## Project status

The core web app is live and usable. Current planning artifacts in `.planning/` also cover:

- deployment and Neon cutover
- chart data freshness backfill
- weekly ETL automation planning

## Legacy code

The `billboard_stats/` package still contains:

- the original Streamlit app
- ETL loaders and fetchers
- Telegram bot code

Those pieces are still relevant operationally for data loading, even though the primary user-facing app is now the Next.js frontend in `src/`.
