# Phase 06: Data Freshness Backfill & Weekly ETL Automation — Research

**Researched:** 2026-04-29
**Domain:** Python ETL / Neon operations / GitHub Actions scheduling
**Confidence:** HIGH

---

<summary>
## Summary

The repo already contains almost everything needed for a weekly ETL system, but it is split across legacy local tooling and one bot-only scheduler hook. The phase should not invent a new pipeline. It should harden the existing updater, prove freshness against Neon, and then run that same updater on a weekly GitHub Actions schedule.

Three concrete findings drive the plan:

1. `billboard_stats/etl/updater.py` already performs incremental updates plus gap repair and is the correct canonical command.
2. The current local archive is internally inconsistent: `hot100` ends at `2026-02-14`, while `b200` contains future-dated late-2026 JSON files. Freshness logic cannot blindly trust `MAX(chart_date)`.
3. The repo has no `.github/workflows/` automation today. The only scheduling code lives in `billboard_stats/bot/scheduler.py`, which is tied to the Telegram bot runtime and is not suitable as the production scheduler for the deployed app.

</summary>

<findings>
## Findings

### 1. Existing ETL entrypoint is already correct in shape

`billboard_stats/etl/updater.py` already exposes:

- `update_charts(conn, data_dir=None)` — incremental “download new + load + rebuild stats”
- `repair_gaps(conn, data_dir=None, since_year=2025)` — repair missing recent data
- `run_update(data_dir=None, repair=True, update=True)` — combined operational entrypoint

This is the right place to anchor both manual backfills and scheduled automation.

### 2. Current freshness logic is vulnerable to bad dates

The read-side freshness helpers in both:

- `src/lib/data-status.ts`
- `billboard_stats/services/data_status_service.py`

use `MAX(chart_date)` grouped by chart type. That means any future-dated row in `chart_weeks` will be reported as the newest data, even if it is impossible.

The local archive confirms this risk is real:

- `billboard_stats/data/hot100` latest file: `2026-02-14`
- `billboard_stats/data/b200` latest files: late `2026-12-*`

So Phase 6 must include a validity guard either before data reaches the DB, at the DB/query layer, or both.

### 3. Fetcher year logic explains the future-data risk

`billboard_stats/etl/fetcher.py` contains:

- `get_saturdays_for_year(year)` — returns every Saturday in the year
- `download_b200(start_year, end_year, ...)` — iterates every Saturday in each year

This is acceptable for historical backfills, but it is too permissive for “latest data” maintenance if the caller uses the current year as an upper bound. The updater should be bounded by the latest publishable chart week, not by “all Saturdays in the current year”.

### 4. The Telegram bot scheduler is a pattern, not the final automation

`billboard_stats/bot/scheduler.py` already demonstrates an async wrapper around `run_update()`, but:

- it only runs if the Telegram bot process is alive
- it is not connected to the deployed Next.js/Vercel stack
- it has no independent infrastructure-level scheduling or secret management

This is useful as a reference for messaging/result formatting, but not as the production scheduler.

### 5. GitHub Actions is the cleanest weekly automation target

The repo currently has no `.github/workflows/` directory. A weekly workflow can:

- check out the repo
- install Python dependencies from `requirements.txt`
- provide Neon credentials via GitHub secrets
- run `python -m billboard_stats.etl.updater`
- support both `schedule` and `workflow_dispatch`

This aligns with the existing hosting/deployment model without depending on Vercel background jobs.

### 6. Verification already has natural endpoints

The live app already exposes what this phase needs for acceptance:

- `/api/data-status`
- `/api/charts?chart=hot-100`
- `/api/charts?chart=billboard-200`
- `/status`

The plan should use those for post-backfill and post-automation verification rather than inventing new read APIs.

</findings>

<recommended_breakdown>
## Recommended Plan Breakdown

### Plan 06-01 — Harden chronology and freshness rules

Make the ETL and freshness queries reject or ignore future weeks, and add a clear operational/audit path for determining the true latest valid chart week.

### Plan 06-02 — Backfill the missing production data and write the operator runbook

Use the hardened updater against Neon, fill the gap from `2026-02-14` forward, verify the app surfaces real fresh data, and document the manual maintenance procedure.

### Plan 06-03 — Automate weekly ETL in GitHub Actions

Add the scheduled/manual workflow, define the required secrets, and verify that a headless CI run can execute the same updater safely every week.

</recommended_breakdown>

<risks>
## Risks / Planning Notes

- If future-dated `billboard-200` rows are already in Neon, query-side freshness guards alone are not enough; the plan should include a cleanup or at least a verification/audit step.
- Networked ETL execution against Neon is not fully autonomous in this environment; manual checkpoints are appropriate for the backfill and workflow-secret setup.
- `billboard_stats/.env` currently points at Neon already, so documentation and automation should avoid reintroducing localhost assumptions.

</risks>

---

*Phase: 06-update-the-missing-data-last-uploaded-week-is-feb-14-configu*
*Research generated: 2026-04-29*
