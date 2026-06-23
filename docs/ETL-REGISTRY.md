# Operator Runbook: Registry-Driven ETL & Weekly Updater

This runbook is for the **operator** validating the registry-driven ETL — the
full 2-chart run and the weekly incremental updater — on a Neon branch **before**
production is pointed at it (Phase 10, DATA-06 success criteria **#3** and **#4**).

> **Scope.** The registry-driven path is **built and unit-tested in this repo**
> (`billboard_stats/etl/loader.py` `run_etl` / `load_chart` and
> `billboard_stats/etl/updater.py` `update_charts`, with fixture-DB tests in
> `tests/test_loader_registry.py`, `tests/test_etl_equivalence.py`, and
> `tests/test_updater_registry.py`), but the **"full 2-chart run is at parity
> with v1.0"** check and the **"weekly job runs green on the two charts"** check
> are **validated by a human operator on a Neon branch** — exactly like the
> Phase-9 migration (`docs/MIGRATION-MULTICHART.md`). They are **NOT** a
> phase-completion gate or a CI step. Phase 10 is accepted when the
> registry-driven load + updater + their fixture-DB tests ship and pass, and this
> documented operator sequence exists. The actual Neon-branch validation and the
> production cutover happen afterward, on the operator's schedule.
>
> ⚠️ **This runbook carries the ONLY real-database / real-network steps for the
> registry-driven ETL.** The repo's automated suite runs entirely against an
> in-memory **fixture (mock) DB** with a **stubbed fetcher** and **never**
> connects to a real database or scrapes billboard.com. **Never** run the
> full ETL, the weekly updater, or the parity checks in CI or any automated
> execution — the real-DB / real-fetch validation below is the **operator's**
> responsibility and lives here, not in CI.
>
> 🚦 **Do NOT silently switch production.** Production behavior is **not** changed
> by shipping this code. The operator **validates first** on a Neon branch (§3–§5
> below), and **only then** points the production weekly job at the
> registry-driven path. A silent cutover that broke the live v1.0 site is exactly
> the failure this gate prevents.

## What the registry-driven ETL does

The two hardcoded `_load_hot100` / `_load_b200` loaders are collapsed into ONE
`entity_kind`-dispatched `load_chart`, and both the full run (`run_etl`) and the
weekly incremental run (`update_charts`) **loop the chart registry**
(`billboard_stats.etl.chart_registry.iter_charts` — the DB `charts` table) instead
of two hardcoded calls.

- **Single load path, dual-write.** `load_chart` ALWAYS writes the new
  polymorphic `chart_entries` row (and sets `chart_weeks.chart_id`) for every
  chart, AND for the two **legacy** charts ALSO writes the old `hot100_entries` /
  `b200_entries` tables (same INSERT shape + `ON CONFLICT (chart_week_id, rank)
  DO NOTHING` as v1.0). NEW charts (`legacy_table = None`) write `chart_entries`
  only. The dual-write keeps the **live v1.0 frontend fed** (it still reads the
  old tables until the Phase 13 read-path cutover); the legacy writes are retired
  in **Phase 15**.
- **Both stats sets.** After loading, `build_all_stats` rebuilds BOTH the v1.0
  `artist_stats` AND the new per-chart `artist_chart_stats`.
- **Weekly = registry-driven + INCREMENTAL-ONLY.** `update_charts` loops the
  registry and, per chart, derives the delta window from that chart's
  `last_loaded_date` (the day after, through the latest publishable chart week),
  fetches just the delta with the chart-appropriate downloader, and calls
  `load_chart` (dual-write) for the new weeks. It **never** triggers the
  multi-decade backfill; a chart that has never been loaded
  (`last_loaded_date IS NULL`) is **skipped** by the weekly path (its first full
  load is `run_etl`'s / Phase 11's job), and an absent/partial on-disk folder is
  logged and skipped, never a crash.

**It DROPS, RENAMES, or NARROWS no v1.0 object.** Because the frontend is
unchanged and still reads the old tables, **"v1.0 pages still render" holds by
construction** while the dual-write continues — §5e confirms it post-validation.

---

## 0. Prerequisites

- Python venv with `requirements.txt` installed (includes `psycopg2-binary` and
  the `billboard` client). Use `.venv/bin/python` for all commands below.
- Run everything from the repo root:
  `/Users/jaimeberdejosanchez/projects/billboard_stats`.
- `pg_dump` and `psql` available on PATH (PostgreSQL client tools).
- The Phase-9 multi-chart migration (`docs/MIGRATION-MULTICHART.md`) has already
  been applied on the target (the `charts` registry + `chart_entries` exist and
  the two core charts are seeded). The registry-driven load reads `charts`.

---

## 1. Point PG* env at a Neon BRANCH first — never the production primary

The full ETL and the weekly updater read the same `PG*` environment variables as
the rest of the ETL (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`,
and optional `PGSSLMODE`) via `billboard_stats/db/connection.py` — the same
secrets the `weekly-etl` GitHub Actions workflow uses.

> Use **PG\*** env placeholders only — never paste secrets into this file, a
> shell history you will share, or a commit.

**Create a Neon branch of `neondb`, point the `PG*` vars at the branch**, and run
the full validation sequence (§3 → §5) there. Only after every check is clean do
you point the **production** weekly job at the registry-driven path (§6).

> Reminder: the repo's automated tests use a **fixture DB** + **stubbed fetcher**
> with no real credentials and no network. This runbook carries the only
> real-database / real-fetch validation. Do not shortcut it.

---

## 2. SNAPSHOT — take a `pg_dump` backup of the Neon branch before validating

Even on a branch, snapshot so you have a clean restore point for re-runs.
Replace the `PG*` placeholders with your branch's values (do not inline secrets):

```bash
pg_dump \
  --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$PGDATABASE" \
  --format=custom \
  --file="etl-registry-branch-$(date +%Y%m%d-%H%M%S).dump"
```

---

## 3. FULL 2-CHART REGISTRY RUN — `run_etl` over hot-100 + billboard-200

Run the full registry-driven ETL. It loops the registry, calls `load_chart`
(dual-write) per chart, then rebuilds both stats sets:

```bash
.venv/bin/python -m billboard_stats.etl.loader
```

- For each registered, on-disk chart it loads `chart_entries` AND (for the two
  legacy charts) the legacy `hot100_entries` / `b200_entries` tables.
- A chart whose on-disk folder is absent/partial is logged and skipped, never a
  crash.

---

## 4. PARITY CHECK (criterion #3) — registry-driven rows == v1.0 rows

Confirm the registry-driven full run produced the **same** legacy rows and stats
as the v1.0 path. Run each query against the Neon branch with `psql`.

**a. `chart_entries` per chart == the legacy source counts** (dual-write parity):

```bash
psql "host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER" -c \
  "SELECT
     (SELECT COUNT(*) FROM hot100_entries) AS src_hot100,
     (SELECT COUNT(*) FROM chart_entries ce JOIN charts c ON c.id = ce.chart_id
        WHERE c.slug = 'hot-100') AS ce_hot100,
     (SELECT COUNT(*) FROM b200_entries) AS src_b200,
     (SELECT COUNT(*) FROM chart_entries ce JOIN charts c ON c.id = ce.chart_id
        WHERE c.slug = 'billboard-200') AS ce_b200;"
```

Expect `src_hot100 == ce_hot100` and `src_b200 == ce_b200`.

**b. One-of-three polymorphism holds** — every `chart_entries` row sets exactly
one entity FK:

```bash
psql "host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER" -c \
  "SELECT COUNT(*) AS bad_rows FROM chart_entries
     WHERE num_nonnulls(song_id, album_id, artist_id) <> 1;"
```

Expect `bad_rows = 0`.

**c. `artist_chart_stats` agrees with v1.0 `artist_stats`** — the generalized
per-chart rollup must match the v1.0 career stats for both core charts (same
diff as `docs/MIGRATION-MULTICHART.md` §6e):

```bash
psql "host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER" -c \
  "SELECT acs.artist_id,
          acs.total_weeks, ast.total_hot100_weeks,
          acs.number_ones, ast.hot100_number_ones,
          acs.best_peak,   ast.best_hot100_peak
     FROM artist_chart_stats acs
     JOIN charts c     ON c.id = acs.chart_id AND c.slug = 'hot-100'
     JOIN artist_stats ast ON ast.artist_id = acs.artist_id
    WHERE acs.total_weeks IS DISTINCT FROM ast.total_hot100_weeks
       OR acs.number_ones IS DISTINCT FROM ast.hot100_number_ones
       OR acs.best_peak   IS DISTINCT FROM ast.best_hot100_peak
    LIMIT 50;"
```

Expect **zero rows** (repeat for `billboard-200` against the `*_b200_*` columns).
Any discrepancy means the two stat paths disagree on real data — treat it as a
failure, **do NOT proceed to the production cutover**, and investigate.

---

## 5. WEEKLY GREEN RUN (criterion #4) — run the updater on the two charts

With the branch at parity, validate the **weekly incremental path** end-to-end —
the same script the cron runs. This proves the weekly job "runs green on the two
charts via the registry-driven incremental path."

**Option A — exercise the GitHub Actions workflow against the branch** (preferred
fidelity): set the `weekly-etl` repo/environment secrets to the **Neon branch**
connection and trigger a **manual** run:

```bash
gh workflow run weekly-etl.yml
gh run watch
```

**Option B — run the entrypoint locally** (with `PG*` pointed at the branch):

```bash
bash scripts/run_weekly_etl.sh --update
```

Then confirm it was a clean incremental run:

**a. It loaded only the delta, dual-wrote, and rebuilt stats** — re-run the §4a
parity query and confirm counts still match (the incremental load conflict-skips
already-present `(chart_week_id, rank)` rows, so a re-run is a clean no-op).

**b. INCREMENTAL-ONLY sanity** — confirm the run did NOT walk back the full
history. The per-chart fetch window starts the day after `last_loaded_date`; a
green run touches at most a handful of recent weeks, never decades. Spot-check the
run log: each chart logs `fetching delta <start>..<end>` with a `<start>`
immediately after its last loaded Saturday (or `already current`), never a
1958-era start.

If the manual run is green and the parity checks still hold, criterion #4 is
validated on the branch.

**c. v1.0 pages still render against the branch.** Because the dual-write keeps
the old tables fed, point a local frontend at the branch and confirm the **Latest
Charts** toggle, a **song / album / artist detail** page, and the **Records** page
all render. If any v1.0 page regresses, treat it as a failure and stop.

---

## 6. CUT OVER PRODUCTION — only after §3–§5 are clean

Only now point the **production** weekly job at the registry-driven path:

1. The code already ships the registry-driven `update_charts`; the production
   `weekly-etl` workflow already runs `bash scripts/run_weekly_etl.sh` (which now
   invokes the registry-driven updater). **No production behavior changes until
   you confirm the branch validation above passed.**
2. Restore the production `weekly-etl` secrets (point `PG*` back at the
   production primary if you changed them for §5 Option A).
3. Trigger one **manual** `workflow_dispatch` production run and confirm it is
   green and incremental (the §5 checks against production), then let the Monday
   cron resume.

Do **not** skip directly to a scheduled production run without the manual
confirmation — the manual dispatch is your last gate before the cron relies on it.

---

## 7. ROLLBACK — if any production check regresses

The registry-driven updater is **additive** (dual-write; the v1.0 tables are
still written and read). If a production run regresses:

- The dual-write means the v1.0 tables stay populated, so v1.0 pages keep
  rendering; you have time to investigate without a live outage.
- Re-point the weekly job at the previous behavior by reverting the Plan 10-03
  commits (or pinning the workflow to the prior `updater.py`) and re-running the
  manual dispatch.
- Restore the branch / DB from a §2 snapshot if needed.

Investigate before retrying. Because the v1.0 tables are untouched and the load
is conflict-skipping + idempotent, re-running the dry validation on a fresh Neon
branch is always safe.

---

## 8. Re-run note — the registry-driven path is idempotent

The full run and the weekly updater both conflict-skip already-present
`chart_entries` / legacy rows on `(chart_week_id, rank)` and rebuild stats with a
DELETE+rebuild, so a second run inserts **zero** new rows and reproduces the same
stats. It is always safe to re-run §3 (full), §5 (weekly), and the §4 parity
checks to confirm a clean state on a branch before the production cutover.
