# Operator Runbook: Artist-Identity Reconciliation

This runbook is for the **operator** applying the one-time artist-identity
reconciliation migration (Phase 8, DATA-05) to the production database.

> **Scope.** The reconciliation script is **built and unit-tested in this repo**,
> but it is **applied to the database by a human operator** — exactly like the
> Phase-7 backfill. It is **NOT** a phase-completion gate. Phase 8 is accepted
> when the parser fix ships, the reconciliation script + its fixture-DB tests
> pass, and this documented operator sequence exists. The actual apply against
> production Neon happens afterward, on the operator's schedule.
>
> ⚠️ **This migration MUTATES production data** (it repoints join rows and
> deletes fragment artist rows). **Never** run it in CI or any automated
> execution. The repo's automated test suite runs entirely against a fixture
> (mock) DB and **never** connects to a real database — the real-DB validation
> described below is the operator's responsibility and lives here, not in CI.

## What it heals

The historical over-eager parser shattered multi-part acts into standalone
fragment artist rows. The canonical example: **"Earth, Wind & Fire"** was stored
as three separate artists — **"Earth"**, **"Wind"**, and **"Fire"** — each with
its own `song_artists` / `album_artists` links. The Plan-01 parser fix keeps NEW
loads whole, but the already-stored fragments still pollute the join tables. This
migration repoints each fragment's links onto the canonical artist (deduping
collisions with `ON CONFLICT DO NOTHING`) and deletes the orphaned fragment rows.

Genuine aliases (e.g. "Janet" for "Janet Jackson", "Ke$ha" for "Kesha") are
modeled in `billboard_stats/etl/artist_aliases.py` and are **NOT** treated as
fragments — the migration never deletes a genuine-alias row.

The script is **idempotent**: once the fragments are merged, a second run finds
nothing and is a clean no-op (data-driven, not a flag).

---

## 0. Prerequisites

- Python venv with `requirements.txt` installed (includes `psycopg2-binary`).
  Use `.venv/bin/python` for all commands below.
- Run everything from the repo root:
  `/Users/jaimeberdejosanchez/projects/billboard_stats`.
- `pg_dump` and `psql` available on PATH (PostgreSQL client tools).

---

## 1. Point PG* env at the target — validate on a branch FIRST, never the primary

The script reads the same `PG*` environment variables as the rest of the ETL
(`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, and optional
`PGSSLMODE`) via `billboard_stats/db/connection.py`.

> Use **PG\*** env placeholders only — never paste secrets into this file, a
> shell history you will share, or a commit.

**Validate against an ephemeral Postgres or a Neon BRANCH first** — never the
production primary during testing. Create a Neon branch of `neondb`, point the
`PG*` vars at the branch, run the full dry-run → snapshot → apply → rebuild →
verify sequence there, and only after it checks out repeat the apply against the
production primary.

> Reminder: the repo's automated tests use a **fixture DB** with no real
> credentials. This runbook carries the only real-database validation. Do not
> shortcut it.

---

## 2. DRY-RUN — see what WOULD change (writes nothing)

```bash
.venv/bin/python -m billboard_stats.etl.reconcile_artists --dry-run
```

- The `--dry-run` path computes the planned merges and **writes nothing**,
  exiting 0.
- Read the report: each line shows a canonical act and the fragment artists that
  would be merged into it, e.g.

  ```
  DRY RUN — 1 cluster(s), 3 fragment row(s).
    Earth, Wind & Fire <- Earth, Wind, Fire
  ```

- If the report lists **zero clusters**, there is nothing to reconcile (either
  already applied, or no fragments present) — you are done.

---

## 3. SNAPSHOT — take a `pg_dump` backup BEFORE applying

Back up the four tables the migration touches so you can roll back. Replace the
`PG*` placeholders with your target's values (do not inline secrets):

```bash
pg_dump \
  --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$PGDATABASE" \
  --table=artists --table=song_artists --table=album_artists --table=artist_stats \
  --format=custom \
  --file="reconcile-backup-$(date +%Y%m%d-%H%M%S).dump"
```

Keep this `.dump` file until you have verified the apply (see §6) — it is your
rollback source.

---

## 4. APPLY — run for real (single transaction)

```bash
.venv/bin/python -m billboard_stats.etl.reconcile_artists
```

- All work happens in a **single transaction**: repoint `song_artists` /
  `album_artists` onto each canonical artist with `ON CONFLICT DO NOTHING`, then
  delete the orphaned fragment `artist_stats` and `artists` rows.
- The script captures **before/after invariant counts** and **rolls back and
  raises** if any invariant is violated, so it never leaves a half-merged DB.

---

## 5. REBUILD STATS — refresh `artist_stats` after a real apply

The merge changes which `artist_id` owns each catalog row, so career stats must
be recomputed. Run the existing `build_artist_stats` rebuild (a DELETE+rebuild):

```bash
.venv/bin/python -c "from billboard_stats.db.connection import get_conn, put_conn; from billboard_stats.etl.stats_builder import build_artist_stats; c = get_conn(); build_artist_stats(c); put_conn(c)"
```

> Do **not** run the rebuild during the reconciliation itself — `reconcile_artists`
> deliberately never calls `build_artist_stats`. The rebuild is this separate
> operator step.

---

## 6. VERIFY — invariants + a previously-fragmented artist

Confirm the safety invariants held and the heal is visible:

- **Distinct song count unchanged** and **distinct album count unchanged** (no
  song/album lost all its artists).
- **No song or album left with zero artists.**
- **Total link rows only decreased** (via dedupe) — never increased.

  Quick check with `psql` (run before/after, compare):

  ```bash
  psql "host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER" -c \
    "SELECT
       (SELECT COUNT(DISTINCT song_id)  FROM song_artists)  AS songs,
       (SELECT COUNT(DISTINCT album_id) FROM album_artists) AS albums,
       (SELECT COUNT(*) FROM song_artists) + (SELECT COUNT(*) FROM album_artists) AS links;"
  ```

- **Manual UI check:** open a previously-fragmented artist's detail page (e.g.
  **Earth, Wind & Fire**) and confirm it now shows the **merged catalog** (the
  songs/albums that were split across "Earth"/"Wind"/"Fire" all appear under the
  single act) and a **correct first-chart date** (the earliest date across the
  merged catalog, not a fragment's partial history). Confirm the standalone
  "Earth", "Wind", "Fire" artist rows/pages no longer exist.

---

## 7. ROLLBACK — restore from the snapshot if any check fails

If verification fails, restore the four tables from the §3 snapshot:

```bash
pg_restore \
  --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$PGDATABASE" \
  --clean --if-exists \
  --table=artists --table=song_artists --table=album_artists --table=artist_stats \
  "reconcile-backup-YYYYMMDD-HHMMSS.dump"
```

Then re-run `build_artist_stats` (§5) to restore the pre-merge stats, and
investigate before retrying.

---

## 8. Re-run note — the script is idempotent

A second `apply` after a completed run finds **no fragments left to merge** and
is a **no-op** (it reports zero clusters and writes nothing). This is data-driven,
not gated by an "already ran" flag, so it is always safe to re-run the dry-run or
apply to confirm a clean state.
