#!/usr/bin/env node
/**
 * verify-artist-placeholders.mjs
 *
 * Deterministic, dependency-free regression check for the comma-separated
 * artist-input bug fix in src/lib/records.ts (quick task 260508-mbw).
 *
 * Why a mirror, not an import?
 * - src/lib/records.ts is wired to Next.js + getSql(); importing it would
 *   pull in a runtime DB client. We don't need a DB roundtrip to prove the
 *   SQL-shape contract — we just need to assert that for N artists the
 *   builder emits N distinct `$N` placeholders, that the next non-artist
 *   filter placeholder is correct, and that `params` has the right length.
 *
 * The mirrors below copy the post-fix logic for Site A (`buildFilters()`)
 * and Site B (artists + year-filter branch). They MUST stay structurally
 * aligned with the production code; cross-check by eye after any edit to
 * either site.
 */

import assert from "node:assert/strict";

/**
 * Mirror of post-fix Site A in src/lib/records.ts (`buildFilters()`).
 * Returns { filterSql, params } describing the artist ILIKE + optional peakMin
 * portion of the WHERE clause.
 */
function buildFiltersMirror({
  artistNames = null,
  peakMin = null,
  placeholderOffset = 0,
  artistExpr = "i.artist_credit",
  statsExpr = "st",
} = {}) {
  const params = [];
  const filters = [];
  const placeholder = () => `$${placeholderOffset + params.length + 1}`;

  if (artistNames && artistNames.length > 0) {
    const artistValues = artistNames.map((name) => `%${name}%`);
    // Capture the base offset BEFORE the map so each iteration gets its own $N.
    const artistBase = placeholderOffset + params.length;
    const artistClause = artistValues.map(
      (_, index) => `${artistExpr} ILIKE $${artistBase + index + 1}`,
    );
    filters.push(`(${artistClause.join(" OR ")})`);
    params.push(...artistValues);
  }
  if (peakMin != null) {
    filters.push(`${statsExpr}.peak_position >= ${placeholder()}`);
    params.push(peakMin);
  }

  return {
    params,
    filterSql: filters.length > 0 ? ` AND ${filters.join(" AND ")}` : "",
  };
}

/**
 * Mirror of post-fix Site B in src/lib/records.ts (artists + year-filter branch).
 * `yearFilterParamCount` simulates the `[...yearFilter.params]` prefix that the
 * real builder seeds into params before the artist clause runs.
 */
function buildArtistsYearMirror({
  artistNames = null,
  weeksMin = null,
  yearFilterParamCount = 0,
} = {}) {
  // Seed params with placeholders for the year-filter values that already exist.
  const params = [];
  for (let i = 0; i < yearFilterParamCount; i += 1) {
    params.push(`__year_${i}`);
  }
  const filters = [];
  const placeholder = () => `$${params.length + 1}`;

  if (artistNames && artistNames.length > 0) {
    const artistValues = artistNames.map((name) => `%${name}%`);
    const artistBase = params.length;
    const artistClause = artistValues.map(
      (_, index) => `a.name ILIKE $${artistBase + index + 1}`,
    );
    filters.push(`(${artistClause.join(" OR ")})`);
    params.push(...artistValues);
  }
  if (weeksMin != null) {
    filters.push(`aggregated.total_weeks >= ${placeholder()}`);
    params.push(weeksMin);
  }

  return {
    params,
    filterSql: filters.length > 0 ? ` AND ${filters.join(" AND ")}` : "",
  };
}

// ---------- Assertions ----------

// 1. Site A: two artists, no peakMin, offset 0.
{
  const { params, filterSql } = buildFiltersMirror({
    artistNames: ["Katy", "Taylor"],
    peakMin: null,
    placeholderOffset: 0,
  });
  assert.match(filterSql, /\$1/, "Scenario 1: $1 must appear");
  assert.match(filterSql, /\$2/, "Scenario 1: $2 must appear");
  // Distinct placeholders: count occurrences of "$1" and "$2".
  const dollar1 = (filterSql.match(/\$1\b/g) || []).length;
  const dollar2 = (filterSql.match(/\$2\b/g) || []).length;
  assert.equal(dollar1, 1, "Scenario 1: $1 used exactly once");
  assert.equal(dollar2, 1, "Scenario 1: $2 used exactly once");
  assert.equal(params.length, 2, "Scenario 1: params.length === 2");
  assert.deepEqual(params, ["%Katy%", "%Taylor%"]);
}

// 2. Site A: two artists + peakMin=10 must produce $1, $2, $3.
{
  const { params, filterSql } = buildFiltersMirror({
    artistNames: ["Katy", "Taylor"],
    peakMin: 10,
    placeholderOffset: 0,
  });
  assert.match(filterSql, /ILIKE \$1/, "Scenario 2: artist 1 -> $1");
  assert.match(filterSql, /ILIKE \$2/, "Scenario 2: artist 2 -> $2");
  assert.match(filterSql, /peak_position >= \$3/, "Scenario 2: peakMin -> $3");
  assert.deepEqual(params, ["%Katy%", "%Taylor%", 10]);
}

// 3. Site A with placeholderOffset=1 (rankByParam=$1 case): artists -> $2,$3, peak -> $4.
{
  const { params, filterSql } = buildFiltersMirror({
    artistNames: ["Katy", "Taylor"],
    peakMin: 10,
    placeholderOffset: 1,
  });
  assert.match(filterSql, /ILIKE \$2/, "Scenario 3: artist 1 -> $2");
  assert.match(filterSql, /ILIKE \$3/, "Scenario 3: artist 2 -> $3");
  assert.match(filterSql, /peak_position >= \$4/, "Scenario 3: peakMin -> $4");
  // Critically: $1 must NOT appear (it's reserved by the caller).
  assert.doesNotMatch(filterSql, /\$1\b/, "Scenario 3: $1 reserved by caller");
  assert.deepEqual(params, ["%Katy%", "%Taylor%", 10]);
}

// 4. Site A: single artist -> single placeholder $1.
{
  const { params, filterSql } = buildFiltersMirror({
    artistNames: ["Solo"],
    peakMin: null,
    placeholderOffset: 0,
  });
  assert.match(filterSql, /ILIKE \$1/, "Scenario 4: solo artist -> $1");
  assert.doesNotMatch(filterSql, /\$2/, "Scenario 4: no $2 for single artist");
  assert.equal(params.length, 1, "Scenario 4: params.length === 1");
  assert.deepEqual(params, ["%Solo%"]);
}

// 5. Site B: yearFilterParamCount=2, two artists, weeksMin=5 -> artists $3,$4 + weeks $5.
{
  const { params, filterSql } = buildArtistsYearMirror({
    artistNames: ["Katy", "Taylor"],
    weeksMin: 5,
    yearFilterParamCount: 2,
  });
  assert.match(filterSql, /a\.name ILIKE \$3/, "Scenario 5: artist 1 -> $3");
  assert.match(filterSql, /a\.name ILIKE \$4/, "Scenario 5: artist 2 -> $4");
  assert.match(filterSql, /total_weeks >= \$5/, "Scenario 5: weeksMin -> $5");
  // params: 2 year-filter values + 2 artist values + 1 weeksMin = 5.
  assert.equal(params.length, 5, "Scenario 5: params.length === 5");
  assert.equal(params[2], "%Katy%");
  assert.equal(params[3], "%Taylor%");
  assert.equal(params[4], 5);
}

console.log("OK: artist placeholder shape verified");
