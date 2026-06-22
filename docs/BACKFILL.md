# Operator Runbook: Offline Chart Backfill

This runbook is for the **operator** running the multi-decade raw-JSON backfill
of the curated Billboard charts (Phase 7, CHARTS-04).

> **Scope.** This phase ACQUIRES raw chart JSON only. It does **not** load
> anything into Postgres (that is a later phase) — the backfill is entirely
> Postgres-free.
>
> **The full multi-decade scrape is the operator's job. It is NOT a Phase-7
> completion gate.** Phase 7 is accepted when: the tooling is proven, the slugs
> are verified, the smoke-test download is on disk, and this documented operator
> command exists. The long scrape runs afterward, on the operator's schedule.

---

## 0. Prerequisites

- Python venv with `billboard.py>=7.1` and `requirements.txt` installed.
  Use `.venv/bin/python` for all commands below.
- Run everything from the repo root: `/Users/jaimeberdejosanchez/projects/billboard_stats`.

---

## 1. Verify the curated slugs (Plan 01)

The backfill only ever scrapes slugs that have been **live-verified**. Run the
slug-verification spike, which resolves each curated slug against
`billboard.ChartData(slug)`, captures its `first_date`, and writes the sidecar:

```bash
.venv/bin/python -m billboard_stats.etl.charts verify
```

- On success it prints a PASS/FAIL table and writes
  **`billboard_stats/data/verified_charts.json`** — the verified-slug sidecar
  the backfill reads.
- The sidecar's `first_date` is a **"verified-as-of" marker** — the week
  verification ran — **NOT** each chart's earliest/debut week. The FULL backfill
  deliberately does **not** use it as a start date (see §3); it discovers true
  history depth by walking backward to the debut.
- A renamed/removed slug **fails loudly** (non-zero exit). Fix the slug in
  `billboard_stats/etl/charts.py` (`CURATED_CHARTS`) and re-run.
- If `verified_charts.json` is missing, the backfill aborts with a clear error
  telling you to run this step first.

---

## 2. Smoke-test (proof-of-path)

The smoke-test downloads only a **few recent weeks per verified chart** — it
proves the verify→download path end to end **without** a multi-decade scrape.
This is the Phase-7 acceptance artifact.

**Locally:**

```bash
.venv/bin/python -m billboard_stats.etl.backfill --smoke --allow
# or, via the operator runner (loads .env, sets the guardrail marker):
scripts/run_backfill.sh --smoke --allow
```

**Via the manual GitHub workflow:** open the **`backfill`** workflow in the
GitHub Actions tab → **Run workflow** → set `mode = smoke` (leave `slug` blank).
The workflow is `workflow_dispatch`-only and sets `BACKFILL_ALLOW=1` for you.

After the smoke-test, a few `billboard_stats/data/{slug}/{YYYY-MM-DD}.json` files
exist for each verified chart. Re-running the same command downloads `0` new
files (everything is skipped) — proving **resumability**.

---

## 3. Full multi-decade backfill (the operator's long job)

The full backfill **discovers each chart's true history depth by walking
BACKWARD to its debut**. For each verified chart it starts at the latest
publishable week and steps back one Saturday (7 days) at a time, saving every
week's JSON, until it reaches a **before-debut boundary** — a week that resolves
**empty** or **not-found (404)**. That boundary is treated as the natural
end-of-history (the chart's debut), and the walk stops cleanly there.

This replaces the earlier (broken) approach of starting from the sidecar's
`first_date`: that field records the *verified-as-of* week (the current week at
verification time), so using it as a start would download only ~1 week per chart
instead of the full multi-decade history. The backward walk needs no knowledge
of each chart's launch date (Artist 100 since 2014, Hot 100 since 1958, genre
charts vary) — it finds the debut empirically.

This is **long-running** (N charts × thousands of Saturdays × a polite ~1.5s
delay = hours to days).

> **Boundary semantics.** A `403`/`429` is **never** treated as the debut
> boundary — it is a rate-limit / IP-block and hard-stops the run (see §4). Only
> an empty / not-found week marks the debut. A configurable **safety floor**
> (default `1958-01-01`) bounds the walk so a chart that never returns empty
> cannot loop forever. A small **consecutive-empty tolerance** (default 1) means
> a single legitimately-missing mid-history week does not falsely end the walk.

**Locally (recommended for the full history):**

```bash
scripts/run_backfill.sh --full --allow
# or one chart at a time:
scripts/run_backfill.sh --full --slug artist-100 --allow
.venv/bin/python -m billboard_stats.etl.backfill --full --slug country-songs --allow
```

**Via the manual GitHub workflow:** run the **`backfill`** workflow with
`mode = full` (optionally a single `slug`).

> ⚠️ **GitHub Actions has a 6-hour single-job cap.** A complete multi-decade
> `full` run can exceed it. The job is resumable (see below), so a timeout is
> recoverable, but for the true full history prefer a **local or long-lived
> machine**, and consider running **per-slug** to bound each run.

### Resumability / crash recovery

Resumability is automatic via the **on-disk cache**: any week whose JSON file
already exists (and is ≥ `MIN_FILE_SIZE`) is **skipped** — no network call.

- If the run crashes, is cancelled, or hits the Actions timeout: **just re-run
  the same command.** Finished weeks are skipped; the run resumes where it left
  off.
- There is no separate checkpoint/state file to manage — the JSON corpus on disk
  *is* the state.

---

## 4. HTTP 403 / 429 — HARD STOP behavior

`billboard.py` is an unofficial scraper against a live site. A `403` or `429`
response signals **rate-limiting / IP-block**.

- The downloader **hard-stops** the whole run on the first `403`/`429` — it
  raises and aborts rather than tight-retrying the offending week. The backfill
  orchestrator does **not** swallow this; the run exits non-zero.
- **What to do if it triggers:** STOP. Do **not** tight-retry or loop. Wait
  (minutes to hours — back off generously), then re-run later. Resumability means
  the re-run skips everything already downloaded and only fetches the remainder.
- Keep scrape volume **polite**: the default ~1.5s delay is intentional; do not
  lower it to "go faster."

---

## 5. Guardrails — the weekly cron is incremental-only

The multi-decade backfill must **never** run on a schedule. Two layers enforce
this:

1. **Workflow level:** the `backfill` workflow is `workflow_dispatch`-only — it
   has **no `schedule:` trigger**, so GitHub can only start it manually.
2. **Code level:** `run_backfill` aborts (raises `BackfillGuardrailError`) when
   `GITHUB_EVENT_NAME == "schedule"`, or when the marker env var
   `BACKFILL_ALLOW` is not `1`. The `--allow` flag and the manual workflow set
   `BACKFILL_ALLOW=1`; nothing else does.

The existing **`weekly-etl`** cron (`weekly-etl.yml`, Monday 06:00 UTC) runs
**only** the incremental updater (`billboard_stats.etl.updater`) and never
invokes the backfill — verified by an automated check that the weekly workflow
references neither the backfill module nor its operator runner.

---

## 6. Operator responsibilities (ToS / redistribution)

Confirming **billboard.com's Terms of Use and redistribution posture** before
scaling scrape volume is the **operator's responsibility** — it is the milestone's
biggest non-technical risk. Verify the legal posture before launching the full
multi-decade × multi-chart backfill, and keep request volume polite.
