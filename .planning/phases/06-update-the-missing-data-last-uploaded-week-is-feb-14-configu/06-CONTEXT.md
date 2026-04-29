# Phase 06: Data Freshness Backfill & Weekly ETL Automation - Context

**Gathered:** 2026-04-29
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers a reliable weekly Billboard data maintenance path for the production Neon database. It covers three linked outcomes: correcting the current freshness gap where Hot 100 data stops at 2026-02-14, preventing the ETL and freshness surfaces from trusting impossible future chart weeks, and wiring a real unattended weekly automation path for the existing Python ETL.

This phase is operational and data-pipeline focused. It does not introduce new product UI beyond any minimal freshness safeguards required to keep existing status surfaces truthful.

</domain>

<decisions>
## Implementation Decisions

### ETL Architecture
- **D-01:** Reuse the existing Python ETL (`billboard_stats/etl/*`) rather than rewriting the pipeline in TypeScript.
- **D-02:** The current incremental updater (`python -m billboard_stats.etl.updater`) remains the canonical entrypoint for weekly maintenance.
- **D-03:** Weekly automation must target the Neon production database used by the live app, not a separate local-only database.

### Freshness / Data Integrity
- **D-04:** The app and ETL must stop treating future-dated chart files or rows as valid “latest” data.
- **D-05:** The current known real freshness gap is Hot 100 data stopping at 2026-02-14; the phase must explicitly backfill from there through the latest available publishable week.
- **D-06:** Billboard 200 local archive data already contains future-dated JSON files for late 2026. The phase must account for this as a data-validity bug, not as evidence that the database is current.

### Automation Strategy
- **D-07:** The old Telegram bot scheduler is not the production automation mechanism for this repo. Weekly ETL must run from a standalone operational path that does not require the bot process to be alive.
- **D-08:** GitHub Actions is the preferred automation target because the repo already lives on GitHub and the ETL can run headlessly against Neon with secrets.
- **D-09:** Automation must support both scheduled execution and manual re-runs for repair / verification.

### Operational Safety
- **D-10:** Secrets stay in env vars / GitHub Actions secrets; no credentials are committed.
- **D-11:** The phase must leave behind a human-readable runbook so the weekly ETL can be operated without reverse-engineering the codebase.

### the agent's Discretion
- Exact weekly cron timing, as long as it aligns with Billboard’s weekly publishing cadence.
- Whether the freshness safeguards live entirely in ETL code, entirely in read/query code, or in both layers.
- Whether the runbook lives in `README.md` or a dedicated ops document, as long as it is committed and discoverable.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing ETL
- `billboard_stats/etl/updater.py` — current incremental update and gap-repair entrypoint
- `billboard_stats/etl/fetcher.py` — current date iteration and remote download logic
- `billboard_stats/etl/loader.py` — current JSON-to-Postgres loading path
- `billboard_stats/etl/json_parser.py` — file enumeration / parsing behavior
- `billboard_stats/db/connection.py` — Neon env-var contract used by the ETL

### Existing Freshness Surfaces
- `src/lib/data-status.ts` — Next.js freshness query helpers
- `src/components/status/data-status-panel.tsx` — production status/freshness UI
- `billboard_stats/services/data_status_service.py` — legacy Python freshness query behavior

### Existing Automation Clue
- `billboard_stats/bot/scheduler.py` — prior async weekly job pattern; useful as a messaging/reference pattern, but not the production scheduler

### Production Cutover Context
- `.planning/phases/05-i-want-to-configure-neon-and-deploy-the-app-in-vercel/05-CONTEXT.md`
- `.planning/phases/05-i-want-to-configure-neon-and-deploy-the-app-in-vercel/05-RESEARCH.md`
- `.planning/phases/05-i-want-to-configure-neon-and-deploy-the-app-in-vercel/05-02-SUMMARY.md`
- `.planning/phases/05-i-want-to-configure-neon-and-deploy-the-app-in-vercel/05-03-SUMMARY.md`

</canonical_refs>

<specifics>
## Specific Ideas

- The current local archive shows `hot100` ending at `2026-02-14`, while `b200` contains late-2026 JSON files. That mismatch should be treated as a concrete bug and planning anchor.
- The live app already exposes enough read-side surface to verify freshness after backfill: `/api/data-status`, `/api/charts?chart=hot-100`, and the `/status` page.
- A good automation target is a GitHub Actions workflow with `schedule` + `workflow_dispatch`, Python setup, dependency install, exported Neon env vars, and `python -m billboard_stats.etl.updater`.

</specifics>

<deferred>
## Deferred Ideas

- User-facing “Update Now” buttons in the web app
- Telegram bot notifications as the primary automation/reporting path
- Full observability stack (alerts, dashboards, error aggregation)
- Multi-environment ETL branching or preview-database automation

</deferred>

---

*Phase: 06-update-the-missing-data-last-uploaded-week-is-feb-14-configu*
*Context gathered: 2026-04-29*
