# Operator Runbook: Multi-Chart Schema Migration

This runbook is for the **operator** applying the one-time multi-chart
generalization migration (Phase 9, DATA-01 / DATA-02 / DATA-03) to the
production database.

> **Scope.** The migration is **built and unit-tested in this repo**
> (`billboard_stats/etl/migrate_multichart.py` +
> `billboard_stats/db/migrations/001_multichart.sql`, with fixture-DB tests in
> `tests/test_migrate_multichart.py` and `tests/test_stats_builder_parametric.py`),
> but it is **applied to the database by a human operator** — exactly like the
> Phase-7 backfill and the Phase-8 reconciliation. It is **NOT** a
> phase-completion gate. Phase 9 is accepted when the additive schema + migration
> runner + the parametric `artist_chart_stats` rollup ship and their fixture-DB
> tests pass, and this documented operator sequence exists. The actual apply
> against production Neon happens afterward, on the operator's schedule.
>
> ⚠️ **This runbook carries the ONLY real-database step in Phase 9.** The repo's
> automated test suite runs entirely against an in-memory **fixture (mock) DB**
> and **never** connects to a real database or builds stats against one. **Never**
> run this migration (or the stats rebuild) in CI or any automated execution —
> the real-DB validation described below is the operator's responsibility and
> lives here, not in CI.

## What it does — strictly additive

The migration takes an **existing v1.0 production database** from the bifurcated
`hot100_entries` / `b200_entries` shape to the generalized multi-chart shape
**without mutating anything the unchanged v1.0 frontend reads**. It:

1. Adds the **`charts`** registry, the polymorphic **`chart_entries`** table, the
   per-chart **`artist_chart_stats`** rollup, and a **NULLABLE `chart_weeks.chart_id`**
   FK (all DDL guarded with `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`).
2. **Seeds** the registry with the two core charts — `hot-100`
   (`entity_kind=song`) and `billboard-200` (`entity_kind=album`) — via
   `ON CONFLICT (slug) DO NOTHING`.
3. **Backfills** `chart_weeks.chart_id` from the existing `chart_type`
   (NULL-only; it **keeps** `chart_type` populated — Phase 15 retires it, not
   this migration).
4. **Backfills** `chart_entries` from `hot100_entries` (sets `song_id`) and
   `b200_entries` (sets `album_id`) — exactly one entity FK per row so the
   `num_nonnulls(song_id, album_id, artist_id) = 1` CHECK holds — skipping
   already-migrated rows via `ON CONFLICT (chart_week_id, rank) DO NOTHING`.

Then, as a **separate operator step**, you run `build_artist_chart_stats` to
populate the rollup from the freshly backfilled `chart_entries`.

**It DROPS, RENAMES, or NARROWS no v1.0 object.** `hot100_entries`,
`b200_entries`, `chart_weeks.chart_type` + its CHECK, and the `*_stats` tables
are untouched. Because the frontend is unchanged and still reads the old tables,
**"v1.0 pages still render" holds by construction** — §6 confirms it post-apply.

The runner is **idempotent**: the DDL is `IF NOT EXISTS`, the seed is
`ON CONFLICT DO NOTHING`, the `chart_id` backfill fills only NULLs, and the
`chart_entries` backfill conflict-skips already-migrated rows. A second apply is a
clean **no-op** that still passes parity (parity is asserted on **total**
post-backfill counts, not "rows inserted this run").

---

## 0. Prerequisites

- Python venv with `requirements.txt` installed (includes `psycopg2-binary`).
  Use `.venv/bin/python` for all commands below.
- Run everything from the repo root:
  `/Users/jaimeberdejosanchez/projects/billboard_stats`.
- `pg_dump` and `psql` available on PATH (PostgreSQL client tools).

---

## 1. Point PG* env at the target — validate on a BRANCH FIRST, never the primary

The runner reads the same `PG*` environment variables as the rest of the ETL
(`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, and optional
`PGSSLMODE`) via `billboard_stats/db/connection.py`. The whole migration uses a
**single connection / single transaction**, so detection and execution always see
a consistent snapshot — run it with **no concurrent writers**.

> Use **PG\*** env placeholders only — never paste secrets into this file, a
> shell history you will share, or a commit.

**Validate against a Neon BRANCH first** — never the production primary during
testing. Create a Neon branch of `neondb`, point the `PG*` vars at the branch,
run the full **dry-run → snapshot → apply → rebuild stats → verify** sequence
there, and only after it checks out repeat the apply against the production
primary.

> Reminder: the repo's automated tests use a **fixture DB** with no real
> credentials. This runbook carries the only real-database validation. Do not
> shortcut it.

---

## 2. DRY-RUN — see what WOULD change (writes nothing)

```bash
.venv/bin/python -m billboard_stats.etl.migrate_multichart --dry-run
```

- The `--dry-run` path computes the planned seed + backfill counts and **writes
  nothing**, exiting 0.
- Read the report. On a pristine pre-migration v1.0 DB it reports the two charts
  to seed and the full source counts to backfill, e.g.

  ```
  DRY RUN — seeded 2 chart(s); backfilled +<N_hot100> hot-100 / +<N_b200> billboard-200 chart_entries.
  ```

- **Sanity-check the planned counts.** The planned `hot-100` backfill should equal
  `COUNT(*)` of `hot100_entries`, and the planned `billboard-200` backfill should
  equal `COUNT(*)` of `b200_entries` (confirm with the §6 parity query).
- If the report shows **0 charts to seed and +0/+0 backfill**, the migration is
  already applied (idempotent no-op) — you are done with the apply; you may still
  re-run the §4 stats rebuild if catalog data changed.

---

## 3. SNAPSHOT — take a `pg_dump` backup BEFORE applying

The migration is additive, but **snapshot anyway** so you can roll back the new
objects (and have a restore point for the whole DB). Replace the `PG*`
placeholders with your target's values (do not inline secrets):

```bash
pg_dump \
  --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$PGDATABASE" \
  --format=custom \
  --file="multichart-backup-$(date +%Y%m%d-%H%M%S).dump"
```

Keep this `.dump` file until you have verified the apply (see §6) — it is your
rollback source.

---

## 4. APPLY — run for real (single transaction, row-count parity assertions)

```bash
.venv/bin/python -m billboard_stats.etl.migrate_multichart
```

- All work happens in a **single transaction** on **one connection**: apply the
  additive DDL (`IF NOT EXISTS`), seed the `charts` registry
  (`ON CONFLICT (slug) DO NOTHING`), backfill `chart_weeks.chart_id` from
  `chart_type` (NULL-only), then backfill `chart_entries` from the two v1.0 entry
  tables (`ON CONFLICT (chart_week_id, rank) DO NOTHING`).
- After the backfill it asserts **row-count PARITY on TOTAL post-backfill
  counts** and **rolls back and raises `MigrationParityError`** on any mismatch
  (it never leaves a half-migrated DB):

  ```
  count(chart_entries WHERE chart_id = hot-100)       == count(hot100_entries)
  count(chart_entries WHERE chart_id = billboard-200) == count(b200_entries)
  count(chart_entries)                                == hot100_entries + b200_entries
  ```

  plus: **no known `chart_type` week is left with a NULL `chart_id`**.
- It **commits only if every assertion holds**. Comparing TOTAL counts (not "rows
  inserted this run") means an idempotent re-run with zero inserts still passes
  parity and commits.

---

## 5. REBUILD STATS — populate `artist_chart_stats` after the backfill

The rollup is a **separate operator step** (like RECONCILIATION.md §5) — the
migration runner deliberately never builds stats. After the backfill populates
`chart_entries`, run the new parametric rollup `build_artist_chart_stats`, which
DELETEs and rebuilds `artist_chart_stats` (one row per artist × chart) using the
**single parametric phantom-week CTE keyed by `chart_id`** over `chart_entries`:

```bash
.venv/bin/python -c "from billboard_stats.db.connection import get_conn, put_conn; from billboard_stats.etl.stats_builder import build_artist_chart_stats; c = get_conn(); build_artist_chart_stats(c); put_conn(c)"
```

> This is **additive** and does **not** touch the v1.0 `artist_stats` table.
> `build_artist_chart_stats` is a DELETE+rebuild, so it is safe to re-run; the
> existing `build_artist_stats` (v1.0) rebuild is unchanged and independent.

---

## 6. VERIFY — row-count parity, the chart_id backfill, and v1.0 pages

**a. Row-count parity** — confirm `chart_entries` per chart equals the v1.0
source counts (this is the same invariant the runner asserts; verify it
independently with `psql`):

```bash
psql "host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER" -c \
  "SELECT
     (SELECT COUNT(*) FROM hot100_entries) AS src_hot100,
     (SELECT COUNT(*) FROM chart_entries ce JOIN charts c ON c.id = ce.chart_id
        WHERE c.slug = 'hot-100') AS ce_hot100,
     (SELECT COUNT(*) FROM b200_entries) AS src_b200,
     (SELECT COUNT(*) FROM chart_entries ce JOIN charts c ON c.id = ce.chart_id
        WHERE c.slug = 'billboard-200') AS ce_b200,
     (SELECT COUNT(*) FROM chart_entries) AS ce_total;"
```

Expect `src_hot100 == ce_hot100`, `src_b200 == ce_b200`, and
`ce_total == src_hot100 + src_b200`.

**b. `chart_weeks.chart_id` backfilled, `chart_type` preserved** — every known
chart-type week has a non-NULL `chart_id`, and `chart_type` is still populated:

```bash
psql "host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER" -c \
  "SELECT
     (SELECT COUNT(*) FROM chart_weeks
        WHERE chart_id IS NULL
          AND chart_type IN ('hot-100','billboard-200')) AS unbackfilled_weeks,
     (SELECT COUNT(*) FROM chart_weeks WHERE chart_type IS NOT NULL) AS chart_type_kept;"
```

Expect `unbackfilled_weeks = 0` and `chart_type_kept` unchanged from before the
apply.

**c. One-of-three polymorphism holds** — every `chart_entries` row sets exactly
one entity FK:

```bash
psql "host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER" -c \
  "SELECT COUNT(*) AS bad_rows FROM chart_entries
     WHERE num_nonnulls(song_id, album_id, artist_id) <> 1;"
```

Expect `bad_rows = 0`.

**d. `artist_chart_stats` populated** — the rollup wrote rows (one per artist ×
chart):

```bash
psql "host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER" -c \
  "SELECT c.slug, COUNT(*) AS rollup_rows
     FROM artist_chart_stats acs JOIN charts c ON c.id = acs.chart_id
     GROUP BY c.slug ORDER BY c.slug;"
```

**e. Stat-path agreement — `artist_chart_stats` must match `artist_stats`.**
The repo's automated suite runs against a fixture DB and **cannot** prove the
generalized parametric rollup (`build_artist_chart_stats` →
`artist_chart_stats`) agrees with the v1.0 path (`build_artist_stats` →
`artist_stats`) on **real** data — the two paths share the phantom-week and
first-real-week rules (both now use `MIN(chart_weeks.id)` after CR-01), but only
a real-Postgres diff confirms they agree. On the **Neon branch**, before
applying to the production primary, diff a sample of the new per-chart rollup
against the v1.0 career stats for both core charts and confirm zero
discrepancies — e.g. hot-100 total weeks / number-ones / first-and-last dates:

```bash
psql "host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER" -c \
  "SELECT acs.artist_id,
          acs.total_weeks, ast.total_hot100_weeks,
          acs.number_ones, ast.hot100_number_ones,
          acs.best_peak,   ast.best_hot100_peak,
          acs.first_date,  ast.first_chart_date
     FROM artist_chart_stats acs
     JOIN charts c     ON c.id = acs.chart_id AND c.slug = 'hot-100'
     JOIN artist_stats ast ON ast.artist_id = acs.artist_id
    WHERE acs.total_weeks    IS DISTINCT FROM ast.total_hot100_weeks
       OR acs.number_ones    IS DISTINCT FROM ast.hot100_number_ones
       OR acs.best_peak      IS DISTINCT FROM ast.best_hot100_peak
    LIMIT 50;"
```

Expect **zero rows** (and repeat for `billboard-200` against the `*_b200_*`
columns). Any discrepancy means the two stat paths disagree on production data —
treat it as a failure, do **not** apply to the primary, and investigate before
proceeding (this is the exact silent-divergence class CR-01 guards against).

**f. Manual UI check — every v1.0 page still renders.** The additive invariant
means the unchanged frontend reads the **untouched old tables**, so this is a
confirmation, not a migration of the read path. Manually confirm:

- The **Latest Charts** toggle (Hot 100 ↔ Billboard 200) loads both charts.
- A **song detail**, an **album detail**, and an **artist detail** page render
  with their chart runs and stats intact.
- The **Records** page renders.

If any v1.0 page regresses, treat it as a failure and roll back (§7) — the
migration must never disturb v1.0 reads.

---

## 7. ROLLBACK — restore / drop the additive objects if any check fails

If verification fails, you have two options. Because the migration is additive,
the **new objects can simply be dropped** (the v1.0 tables were never touched):

```bash
psql "host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER" -c \
  "BEGIN;
     DROP TABLE IF EXISTS artist_chart_stats;
     DROP TABLE IF EXISTS chart_entries;
     ALTER TABLE chart_weeks DROP COLUMN IF EXISTS chart_id;
     DROP TABLE IF EXISTS charts;
   COMMIT;"
```

Or restore the whole database from the §3 snapshot:

```bash
pg_restore \
  --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$PGDATABASE" \
  --clean --if-exists \
  "multichart-backup-YYYYMMDD-HHMMSS.dump"
```

Investigate before retrying. Since the v1.0 tables are untouched, v1.0 pages keep
rendering throughout.

---

## 8. Re-run note — the migration is idempotent

A second `apply` after a completed run finds the **DDL already present** (guarded
by `IF NOT EXISTS`), the **seed conflicting** (`ON CONFLICT (slug) DO NOTHING`),
and the **backfill already done** (`chart_id` NULLs filled, `chart_entries` rows
conflict-skipped on `(chart_week_id, rank)`). It inserts **zero** new rows, the
parity assertions still hold on the **total** counts, and it **commits a clean
no-op**. Re-running the §5 stats rebuild is likewise safe — it is a DELETE+rebuild
and always reproduces the same rollup rows from the current `chart_entries`. It is
therefore always safe to re-run the dry-run, the apply, or the stats rebuild to
confirm a clean state.
