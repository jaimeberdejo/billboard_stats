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
loads whole, but the already-stored fragments still pollute the join tables.

**How it heals — driven by RE-PARSING the stored credits.** The migration does
**not** guess fragments by splitting canonical artist names (that approach is
unsound: real members of acts — solo **Diana Ross**, solo **Tina Turner**,
standalone **Tyler** — are themselves real artists and would be wrongly deleted).
Instead, the source of truth is the stored `artist_credit` string on every `song`
and `album` — the exact input the loader fed to the parser. For each credit the
migration runs the NEW `parse_artist_credit` (with the DB-derived known-acts set)
to get the canonical artist list the credit SHOULD map to today, then reconciles
each song/album's join rows to that target: it adds missing canonical links
(get-or-create the artist, mirroring the loader), removes links the new parse no
longer supports, and sets each link's `role` **deterministically** from the
parse. An artist row (and its `artist_stats`) is deleted **only** when, after
re-deriving every link, it has **zero** remaining links — a true orphan no credit
produces. This inherently protects solo members of real acts (they are produced
by their own standalone credits) while still deleting pure shatter fragments like
"Wind" (which only ever had EWF-split links and no standalone credit of its own).

Genuine aliases (e.g. "Janet" for "Janet Jackson", "Ke$ha" for "Kesha") are
modeled in `billboard_stats/etl/artist_aliases.py` and are folded into the
canonical identity during the re-parse, exactly as at load time.

The script is **idempotent**: once links match the re-parsed credits, a second
run is a clean no-op (data-driven, not a flag).

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

> **Access note.** Because reconciliation re-parses the stored credits, the role
> it runs as needs **read** access to `songs` and `albums` (specifically their
> `artist_credit` column) in addition to the write access it needs on `artists`,
> `song_artists`, `album_artists`, and `artist_stats`. The whole run uses a
> **single connection / single transaction**, so detection and execution always
> see a consistent snapshot — run it with **no concurrent writers**.

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
- Read the report: it summarizes the link adds/removes and lists every orphan
  artist that would be deleted, e.g.

  ```
  DRY RUN — song links +0/-2, album links +0/-1, 3 orphan artist(s) deleted.
    delete orphan: Earth (#2)
    delete orphan: Wind (#3)
    delete orphan: Fire (#4)
  ```

- **Sanity-check the delete list.** Every name here must be a pure shatter
  fragment (a piece of an act with no standalone credit of its own). If you see a
  real standalone artist (e.g. "Diana Ross", "Tina Turner", "Tyler"), STOP — that
  would mean the artist has no surviving credit, which should never happen; do not
  apply.
- If the report shows **0 link changes and 0 orphans**, there is nothing to
  reconcile (already applied, or no fragments present) — you are done.

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

- All work happens in a **single transaction** on **one connection**: re-derive
  every song/album's target artist set from its credit, add missing canonical
  links (get-or-create the artist, role set deterministically from the parse),
  remove links the new parse no longer supports, then delete any artist left with
  zero links (and its `artist_stats`).
- The script captures **before/after invariants** — distinct song/album id SETS
  unchanged, no song/album left with zero artists, link totals only decrease, and
  **no artist produced by some credit's new-parse is deleted** — and **rolls back
  and raises** on any violation, so it never leaves a half-merged DB.

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

- **No dangling join rows** referencing a deleted artist (the fixture tests
  cannot exercise real FK ordering — WR-04). After apply, this must return zero:

  ```bash
  psql "host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER" -c \
    "SELECT
       (SELECT COUNT(*) FROM song_artists  sa LEFT JOIN artists a ON a.id = sa.artist_id WHERE a.id IS NULL) AS dangling_song_links,
       (SELECT COUNT(*) FROM album_artists aa LEFT JOIN artists a ON a.id = aa.artist_id WHERE a.id IS NULL) AS dangling_album_links;"
  ```

- **Role spot-check** (the fixture DB does not model PostgreSQL `role`
  arbitration — CR-02). The reconcile sets each link's `role` deterministically
  from the new parse, so a previously-shattered act's primary link should read
  `primary`:

  ```bash
  psql "host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER" -c \
    "SELECT sa.role, COUNT(*) FROM song_artists sa
       JOIN artists a ON a.id = sa.artist_id
      WHERE a.name = 'Earth, Wind & Fire' GROUP BY sa.role;"
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
