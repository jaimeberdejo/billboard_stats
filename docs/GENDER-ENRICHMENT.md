# Operator Runbook: Artist Gender Enrichment

This runbook is for the **operator** populating the Phase 12 artist `gender`
attribute against the **production** database and the **live** MusicBrainz /
Wikidata APIs (GENDER-01 / GENDER-02).

> **Scope.** Phase 12 is **built and unit-tested in this repo** — the migration
> (`billboard_stats/db/migrations/002_gender.sql` +
> `billboard_stats/etl/migrate_gender.py`), the enricher
> (`billboard_stats/etl/gender_enricher.py`), the read-only coverage report
> (`billboard_stats/etl/gender_coverage.py`), and the never-blocking ETL stage in
> `run_etl` — with fixture-DB + mocked-HTTP tests in
> `tests/test_migrate_gender.py`, `tests/test_gender_enricher.py`, and
> `tests/test_gender_coverage.py`. The **three steps below are applied by a human
> operator** against real data + network, exactly like the Phase-7 backfill, the
> Phase-8 reconciliation, and the Phase-9 multi-chart migration. They are **NOT**
> phase-completion gates.
>
> ⚠️ **The repo's automated test suite runs entirely against an in-memory fixture
> (mock) DB and a mocked HTTP client — it NEVER connects to a real database and
> NEVER makes a real network call.** Do **not** run any step in this runbook in CI
> or any automated execution. The real-DB + live-network work is the operator's
> responsibility and lives here, not in CI.

---

## Politeness & identity policy (read before any live run)

Both MusicBrainz and Wikidata require a **descriptive `User-Agent` with a real
contact** and enforce rate limits. The enricher honors all of this; the operator
only supplies the contact and respects the defaults.

- **User-Agent.** The enricher sends
  `billboard_stats-gender-enricher/1.0 ( <contact> )`, MusicBrainz's documented
  `Application/Version ( contact )` format. Supply a **real** contact URL/email
  you own via `--contact` (or set `GENDER_ENRICHER_CONTACT` and pass it through).
  A missing/abusive User-Agent gets you blocked (403).
- **Rate limit.** MusicBrainz allows **at most ~1 request/second per client.**
  The enricher sleeps `--delay` seconds between artist resolves (default `1.1`).
  **Do not lower `--delay` below 1.0** — bursts get `503`s and sustained abuse can
  get your IP blocked. Wikidata's Action API has the same ~1 req/sec courtesy.
- **No API keys / secrets.** Both services are public **CC0**; there is nothing to
  store. The contact in the User-Agent is intentionally public.
- **Confidence threshold.** The enricher takes the top MusicBrainz search
  candidate only when its `score >= --min-score` (default `90`); below that the
  row stays `unknown` (it does not guess). Tune via `--min-score` against the
  coverage measurement (step 3).
- **License.** MusicBrainz core data (artist `gender`/`type`) and Wikidata are
  both **CC0** (public domain), so the derived `gender` value is fully
  redistributable. Attribution to MusicBrainz / Wikidata is **courteous but not
  legally required** — credit them anyway.

---

## Step 1 — Apply the `002_gender` migration to production (DEFERRED)

The strictly-additive, idempotent migration adds three columns to `artists`
(`gender NOT NULL DEFAULT 'unknown'`, `gender_source`, `gender_source_id`) and a
5-value `CHECK`. It DROPs/RENAMEs nothing and is safe to re-run.

**Dry-run first** (reports the planned column adds, writes nothing):

```bash
python -m billboard_stats.etl.migrate_gender --dry-run
```

**Apply** (one transaction; the runner asserts the 3 columns exist, the artist
row count is unchanged, and every row's `gender` is non-NULL, rolling back on any
mismatch):

```bash
python -m billboard_stats.etl.migrate_gender
```

Re-running is a clean no-op (the `ADD COLUMN IF NOT EXISTS` / `DO`-block guards).

---

## Step 2 — Live gender enrichment run (DEFERRED)

Populates `gender` from **MusicBrainz** (primary) with a **Wikidata** fallback,
keyed by the stable MBID/QID (persisted into `gender_source_id`).

**Dry-run** (reports the planned updates + the candidate matches, writes nothing):

```bash
python -m billboard_stats.etl.gender_enricher \
  --contact "https://github.com/<you>/billboard_stats" \
  --dry-run --limit 50
```

**Apply incrementally** (start with a small `--limit` to spot-check, then widen):

```bash
python -m billboard_stats.etl.gender_enricher \
  --contact "https://github.com/<you>/billboard_stats" \
  --limit 500
```

A default run fills **only** `gender = 'unknown'` rows, so you can run it in
batches and re-run safely — it picks up where it left off. To **re-fetch every
row** (e.g. after raising `--min-score`, or to refresh stale matches), add
`--refresh`:

```bash
python -m billboard_stats.etl.gender_enricher \
  --contact "https://github.com/<you>/billboard_stats" --refresh
```

Useful flags: `--min-score N` (MusicBrainz confidence cutoff, default 90),
`--delay S` (seconds between requests, default 1.1 — **keep >= 1.0**),
`--limit N` (batch cap).

**Notes.**
- The **weekly ETL already enriches newly-inserted artists automatically** (the
  never-blocking delta-only stage in `run_etl`). This manual run is for the
  **initial backfill** of the existing catalog and for `--refresh` passes.
- The automated path **never emits `'mixed'`** (groups map to `'group'`); `'mixed'`
  is reserved for manual curation via `gender_source = 'manual'`.
- MusicBrainz `Non-binary` (and Wikidata non-binary/intersex/trans `P21` values)
  map to `'unknown'` — there is no 5-value bucket for them; the enricher does not
  force them into male/female.

---

## Step 3 — Coverage SPIKE measurement (DEFERRED) + how to record it

After step 2, measure how much of the catalog got matched. This is the **SPIKE
measurement** — the script is built and tested in the repo; **running it against
the real enriched table is the deferred operator step.** It is **read-only**.

```bash
python -m billboard_stats.etl.gender_coverage            # raw coverage
python -m billboard_stats.etl.gender_coverage --weighted # + chart-presence-weighted
```

It reports:
- **Total / matched / match rate** (matched = `gender <> 'unknown'`), overall and
  **by source** (`musicbrainz` vs `wikidata` vs `manual`).
- The full **5-value distribution** (`female | male | group | mixed | unknown`,
  counts + %).
- With `--weighted`, a **chart-presence-weighted** coverage (artists weighted by
  `SUM(total_weeks)` from `artist_chart_stats`) — the coverage of the artists
  users actually see on leaderboards, not the long tail of one-week wonders.

**Record the result** (raw %, weighted %, and the by-source split) in this file or
a session note. **It drives Phase 14's filter framing:**

> **If the match rate is below ~70% (raw or weighted), Phase 14 must surface
> `unknown` as a first-class filter facet** (e.g. an explicit
> "Unknown/Unclassified" bucket plus a visible coverage caveat) rather than a
> simple all/female/male toggle — otherwise the filter would silently hide a
> large, non-random slice of the catalog. **At or above ~70%**, the toggle UX is
> defensible with a small footnote.

If raw coverage is low but **weighted** coverage is high (the popular artists are
well-matched, only the long tail is `unknown`), a toggle with a footnote may still
be acceptable — note both numbers so Phase 14 can decide.

---

## Recorded measurement

| Date | Raw match rate | Weighted match rate | By source (mb / wd / manual) | Notes |
|------|----------------|---------------------|------------------------------|-------|
| _(deferred — fill in after the live run)_ | | | | |
