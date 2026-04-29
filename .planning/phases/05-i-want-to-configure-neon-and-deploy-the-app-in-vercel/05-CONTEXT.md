# Phase 05: Configure Neon & Deploy to Vercel - Context

**Gathered:** 2026-04-29
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers a live, production deployment of the Billboard Stats Next.js app. It covers: creating a Neon PostgreSQL project, migrating the full Billboard dataset from localhost into Neon, wiring `DATABASE_URL` into both the Next.js app and the Python ETL pipeline, and deploying the app to Vercel via GitHub integration. The app code is complete — this is purely infrastructure and configuration work.

</domain>

<decisions>
## Implementation Decisions

### Neon Database Setup
- **D-01:** No Neon project exists yet — one must be created from scratch.
- **D-02:** Existing data lives in local PostgreSQL (localhost). Migration path: `pg_dump` from localhost, restore into Neon via `pg_restore` or `psql`.
- **D-03:** The `@neondatabase/serverless` client is already installed and wired in `src/lib/db.ts` — no code changes needed, only `DATABASE_URL` must be set.

### ETL Pipeline Cutover
- **D-04:** Updating the Python ETL pipeline to write to Neon is in scope for this phase — both the app and the ETL should point at the same Neon database.
- **D-05:** ETL connection string location is unknown — the plan should include a step to locate it in the Python codebase before updating it. Move it to an env var if it's hardcoded.

### Vercel Deployment
- **D-06:** Set up both GitHub integration (push to `main` → auto-deploy) AND Vercel CLI for ad-hoc deploys.
- **D-07:** `DATABASE_URL` must be set as a Vercel environment variable (Production + Preview + Development scopes, all pointing at the same Neon project for now).

### Preview Environments
- **D-08:** Production only for now — all Vercel environments (production, preview, development) share the same Neon database. No Neon branching needed.

### Claude's Discretion
- Exact Neon project name and database name are at the agent's discretion.
- Whether to use `pg_dump --format=custom` or plain SQL for the migration dump is at the agent's discretion based on data size.
- Vercel project name is at the agent's discretion (suggest `billboard-stats`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Database Client
- `src/lib/db.ts` — existing Neon serverless client; only `DATABASE_URL` env var is needed to activate it
- `.env.example` — shows expected `DATABASE_URL` format: `postgresql://user:password@host.neon.tech/neondb`

### App Config
- `next.config.ts` — minimal config, no changes needed for Vercel deployment
- `package.json` — confirms `@neondatabase/serverless@^1.1.0` is already installed

### Project Context
- `.planning/PROJECT.md` — confirms Neon + Vercel is the locked hosting choice; ETL stays Python and runs independently
- `.planning/REQUIREMENTS.md` — CORE-03 (Deploy to Vercel) and CORE-02 (Connect Neon + typed API routes) are the requirements this phase closes

### External
- No external specs — requirements fully captured in decisions above

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/lib/db.ts`: `getSql()` function — already reads `DATABASE_URL` from `process.env` and returns a Neon SQL client. Zero changes needed once env var is set.
- All `src/lib/*.ts` helpers (charts, songs, albums, artists, search, records, data-status) already use `getSql()` — they'll work against Neon automatically.

### Established Patterns
- The app uses `@neondatabase/serverless` exclusively — no `pg` or other client to swap out.
- No server-side secrets beyond `DATABASE_URL` — env var surface is minimal.

### Integration Points
- Vercel `DATABASE_URL` env var → `src/lib/db.ts` → all API routes and server components
- Python ETL `DATABASE_URL` (or equivalent) → must point at same Neon project so ETL-written data is immediately visible in the app
- GitHub remote `github.com/jaimeberdejo/billboard_stats` → Vercel GitHub integration auto-deploy

</code_context>

<specifics>
## Specific Ideas

- Migration order matters: create Neon project → dump local DB → restore into Neon → verify row counts → then set Vercel env var and deploy. Don't deploy until data is confirmed in Neon.
- Vercel CLI should be installed globally (`npm i -g vercel`) so the user can run `vercel --prod` for one-off deploys without relying on CI.
- After deployment, do a smoke-test pass: load /charts, /search, /records, /artist/[id] and confirm data returns.

</specifics>

<deferred>
## Deferred Ideas

- Neon branching for preview deployments — decided against for now; can add in a future phase if preview isolation becomes needed.
- Custom domain — not in scope; Vercel-provided `.vercel.app` URL is sufficient for v1.0.

</deferred>

---

*Phase: 05-i-want-to-configure-neon-and-deploy-the-app-in-vercel*
*Context gathered: 2026-04-29*
