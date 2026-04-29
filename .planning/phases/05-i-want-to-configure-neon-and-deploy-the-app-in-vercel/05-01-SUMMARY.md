---
plan: 05-01
phase: 05-i-want-to-configure-neon-and-deploy-the-app-in-vercel
status: complete
completed: 2026-04-29
---

# Plan 05-01: Neon Database Setup — Summary

## What was built

A Neon PostgreSQL project was created in `aws-eu-central-1` (Frankfurt) and the full 193 MB local Billboard dataset was migrated into it. All 11 tables are present with row counts matching expected values.

## Neon Project

- **Project name:** billboard-stats
- **Project ID:** patient-mud-67801214
- **Region:** aws-eu-central-1 (Frankfurt)
- **Database:** neondb
- **User:** neondb_owner

## Connection Strings

**Unpooled** (for pg_restore / psql / Python ETL):
```
postgresql://neondb_owner:****@ep-crimson-waterfall-al2uil2s.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require
```

**Pooled** (for Vercel / Next.js DATABASE_URL):
```
postgresql://neondb_owner:****@ep-crimson-waterfall-al2uil2s-pooler.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require
```

## Row Count Verification

All 11 tables verified against expected values (within 1%):

| Table | Expected rows | Status |
|---|---|---|
| b200_entries | 686,580 | ✓ |
| hot100_entries | 351,668 | ✓ |
| album_artists | 42,170 | ✓ |
| song_artists | 40,056 | ✓ |
| album_stats | 39,440 | ✓ |
| albums | 39,440 | ✓ |
| song_stats | 32,120 | ✓ |
| songs | 32,120 | ✓ |
| artist_stats | 14,628 | ✓ |
| artists | 14,628 | ✓ |
| chart_weeks | 7,073 | ✓ |

## Non-fatal errors during pg_restore

Extension ownership warnings for `pg_trgm` / `plpgsql` — expected and non-fatal. No data table errors.

## Cleanup

`billboard.dump` deleted from project root after successful verification.

## Self-Check: PASSED
