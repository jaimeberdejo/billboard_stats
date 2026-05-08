---
phase: quick-260508-mbw
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/lib/records.ts
autonomous: false
requirements:
  - QUICK-260508-MBW
must_haves:
  truths:
    - "Custom-query Songs+Hot100 with Artist=\"Katy, Taylor\" returns rows containing both artist matches (no 500)."
    - "Custom-query Albums with multiple comma-separated artists returns rows (no 500)."
    - "Custom-query Artists + year filter (e.g. startYear=2010) with multiple artists returns rows (no 500)."
    - "Custom-query Artists with NO year filter and multiple artists still returns correct rows (existing branch unchanged)."
    - "Single-artist queries continue to work for Songs, Albums, and Artists across all year-filter branches."
  artifacts:
    - path: "src/lib/records.ts"
      provides: "Per-iteration $N placeholders for artist ILIKE clauses across all SQL builders."
      contains: "artistValues.map((_, index) =>"
  key_links:
    - from: "src/lib/records.ts buildFilters() (~line 550)"
      to: "Postgres parameter array"
      via: "each ILIKE clause references its OWN $N (placeholderOffset + params.length + index + 1)"
      pattern: "artistValues\\.map\\(\\(_,\\s*index\\)\\s*=>"
    - from: "src/lib/records.ts artists+yearFilter branch (~line 658)"
      to: "Postgres parameter array"
      via: "each ILIKE clause references its OWN $N"
      pattern: "artistValues\\.map\\(\\(_,\\s*index\\)\\s*=>"
    - from: "src/lib/records.ts artists no-year branch (~line 589)"
      to: "Postgres parameter array"
      via: "Already correct: $${index + 2}; verify NOT regressed"
      pattern: "a\\.name ILIKE \\$\\$\\{index \\+ 2\\}"
---

<objective>
Fix the comma-separated artist input failure in custom queries.

Root cause: in `src/lib/records.ts`, two SQL builders generate the artist ILIKE clause with `artistValues.map(() => ... placeholder())`, where `placeholder()` reads `params.length` lazily. Because the map callback runs BEFORE `params.push(...artistValues)`, every iteration returns the SAME `$N`. Two artists -> SQL like `(... ILIKE $N OR ... ILIKE $N)` while 2 distinct values get pushed -> Postgres parameter count mismatch -> generic 500 surfaced as "Failed to load custom records. Please try again later." in the records-view UI.

Purpose: Restore "Songs/Albums/Artists with multiple comma-separated artists" custom queries.
Output: Bug fix in `src/lib/records.ts`. No API or UI changes; no schema changes.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@src/lib/records.ts
@src/app/api/records/route.ts

<interfaces>
<!-- Three artist-clause sites in src/lib/records.ts. The first two are buggy; the third is correct and must not regress. -->

Site A — buildFilters() inner helper, songs/albums (~line 539-579):
```ts
const buildFilters = (
  placeholderOffset = 0,
  artistExpr = "i.artist_credit",
  statsExpr = "st",
) => {
  const params: Array<string | number> = [];
  const filters: string[] = [];
  const placeholder = () => `$${placeholderOffset + params.length + 1}`;

  if (artistNames && artistNames.length > 0) {
    const artistValues = artistNames.map((name) => `%${name}%`);
    // BUG: placeholder() returns the SAME $N for every iteration because
    // params.length has not been incremented yet (push happens after the map).
    const artistClause = artistValues.map(() => `${artistExpr} ILIKE ${placeholder()}`);
    filters.push(`(${artistClause.join(" OR ")})`);
    params.push(...artistValues);
  }
  // ...subsequent placeholder() calls (peakMin, peakMax, weeksMin, debutPosMin/Max)
  //    must STILL resolve to the correct next index after the artistValues are pushed.
};
```

Site B — Artists branch WITH year filter (~line 649-665):
```ts
} else if (entity === "artists" && hasYearFilter) {
  const yearFilter = buildYearFilter();
  const params: Array<string | number> = [...yearFilter.params];
  const filters: string[] = [];
  const placeholder = () => `$${params.length + 1}`;

  if (artistNames && artistNames.length > 0) {
    const artistValues = artistNames.map((name) => `%${name}%`);
    // BUG: same shape as Site A.
    const artistClause = artistValues.map(() => `a.name ILIKE ${placeholder()}`);
    filters.push(`(${artistClause.join(" OR ")})`);
    params.push(...artistValues);
  }
  // ...weeksMin placeholder() must still be correct after.
}
```

Site C — Artists branch WITHOUT year filter (~line 581-595) [ALREADY CORRECT]:
```ts
if (entity === "artists" && !hasYearFilter) {
  // ...
  const params: Array<string | number> = [];
  const placeholder = () => `$${params.length + 2}`;  // +2 because $1 is reserved for `chart`.

  if (artistNames && artistNames.length > 0) {
    const artistValues = artistNames.map((name) => `%${name}%`);
    // CORRECT: hardcoded offset (chart=$1, so artists start at $2).
    const artistClause = artistValues.map((_, index) => `a.name ILIKE $${index + 2}`);
    filters.push(`(${artistClause.join(" OR ")})`);
    params.push(...artistValues);
  }
  // The next placeholder() call (weeksMin) reads params.length AFTER push, so it returns the right $N.
}
```

Caller surface (route.ts line 75, unchanged):
```ts
function parseArtistNames(value: string | null): string[] | null {
  if (!value) return null;
  const parts = value.split(",").map((p) => p.trim()).filter(Boolean);
  return parts.length > 0 ? parts : null;
}
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix per-iteration placeholders for artist ILIKE clauses (Sites A and B)</name>
  <files>src/lib/records.ts</files>
  <action>
In `src/lib/records.ts`, fix the two buggy artist-clause sites so each ILIKE gets its OWN parameter placeholder. Do NOT touch Site C (the `entity === "artists" && !hasYearFilter` branch, ~line 589 with `$${index + 2}`) — it is already correct and verified.

**Site A — `buildFilters()` (~line 539-579):**

Replace the buggy three lines:
```ts
const artistValues = artistNames.map((name) => `%${name}%`);
const artistClause = artistValues.map(() => `${artistExpr} ILIKE ${placeholder()}`);
filters.push(`(${artistClause.join(" OR ")})`);
params.push(...artistValues);
```
With:
```ts
const artistValues = artistNames.map((name) => `%${name}%`);
// Capture the base offset BEFORE the map so each iteration gets its own $N.
const artistBase = placeholderOffset + params.length;
const artistClause = artistValues.map(
  (_, index) => `${artistExpr} ILIKE $${artistBase + index + 1}`,
);
filters.push(`(${artistClause.join(" OR ")})`);
params.push(...artistValues);
```

This preserves `placeholder()`'s contract for the subsequent peakMin / peakMax / weeksMin / debutPosMin / debutPosMax pushes — after `params.push(...artistValues)`, `params.length` is incremented by `artistValues.length`, so the next `placeholder()` call returns the correct next `$N`.

**Site B — Artists + year-filter branch (~line 649-665):**

Replace:
```ts
const artistValues = artistNames.map((name) => `%${name}%`);
const artistClause = artistValues.map(() => `a.name ILIKE ${placeholder()}`);
filters.push(`(${artistClause.join(" OR ")})`);
params.push(...artistValues);
```
With:
```ts
const artistValues = artistNames.map((name) => `%${name}%`);
const artistBase = params.length; // local placeholder() is `$${params.length + 1}`, no extra offset.
const artistClause = artistValues.map(
  (_, index) => `a.name ILIKE $${artistBase + index + 1}`,
);
filters.push(`(${artistClause.join(" OR ")})`);
params.push(...artistValues);
```

Again, after the push, the subsequent `weeksMin` `placeholder()` call resolves to the correct next `$N`.

**Site C (do NOT change):** Leave the no-year-filter Artists branch (`artistValues.map((_, index) => \`a.name ILIKE $${index + 2}\`)`, ~line 589) untouched. Verify that the diff shows zero changes inside the `if (entity === "artists" && !hasYearFilter) { ... }` block.

**Constraints:**
- No SQL refactor beyond these two artist-clause replacements.
- No changes to `route.ts`, `records-view.tsx`, or any types.
- No new dependencies.
- `placeholder()` keeps its existing definition at both sites — only the artist-clause `.map()` callback changes.
  </action>
  <verify>
    <automated>npx tsc --noEmit && npx eslint src/lib/records.ts</automated>
  </verify>
  <done>
    Both buggy sites use per-iteration `$N` placeholders captured from a base offset taken BEFORE the map. Site C is byte-identical to before. `tsc --noEmit` passes. `eslint src/lib/records.ts` passes. A grep `grep -n "artistValues.map" src/lib/records.ts` shows three matches, none of which is the bare `() => ... placeholder()` form.
  </done>
</task>

<task type="auto">
  <name>Task 2: Programmatic SQL-shape trace for the three artist branches</name>
  <files>scripts/verify-artist-placeholders.mjs</files>
  <action>
Create a small standalone Node script that imports nothing from the app (no DB connection). Its job is to mechanically prove that for `artistNames = ["Katy", "Taylor"]` the SQL fragment produced by each fixed builder uses TWO DISTINCT placeholders and that the next non-artist filter placeholder is also correct.

The simplest, most robust approach is **NOT** to import `records.ts` (which runs Next.js module-resolution and hits `getSql()`); instead, copy the relevant builder logic into the script as a self-contained mirror, then assert against the post-fix shape. This keeps the verification independent of the production module and free of side effects.

Concretely, the script should:

1. Define a local `buildFiltersMirror({ artistNames, peakMin, placeholderOffset })` function that mirrors the post-fix Site A logic (artistBase + per-iteration `$N`, then push, then placeholder() for peakMin).
2. Define a local `buildArtistsYearMirror({ artistNames, weeksMin, yearFilterParamCount })` mirror of Site B.
3. Assert (using `node:assert/strict`):
   - With `artistNames=["Katy","Taylor"]`, `placeholderOffset=0`, `peakMin=null`: the artistClause string contains `$1` and `$2` (distinct), and `params.length === 2`.
   - With `artistNames=["Katy","Taylor"]`, `placeholderOffset=0`, `peakMin=10`: the filterSql contains `$1`, `$2`, AND `$3` for the peak filter; `params` is `["%Katy%","%Taylor%",10]`.
   - With `artistNames=["Katy","Taylor"]`, `placeholderOffset=1` (the rankByParam=$1 case): artist placeholders are `$2`, `$3`; peakMin placeholder is `$4`.
   - With `artistNames=["Solo"]`: single placeholder `$1`, `params.length === 1`.
   - For Site B with `yearFilterParamCount=2` and `artistNames=["Katy","Taylor"]`, `weeksMin=5`: artist placeholders `$3`, `$4`; weeksMin placeholder `$5`.

4. On all-pass, `console.log` "OK: artist placeholder shape verified" and exit 0. On any failure, throw (non-zero exit).

After writing the script, run it with `node scripts/verify-artist-placeholders.mjs` and confirm it prints OK.

Then perform a **read-only sanity diff against the real `src/lib/records.ts`**: open the file and confirm by eye that the mirror's per-iteration shape matches the post-fix code for both Site A and Site B (this is just a manual cross-check; no automation needed).

This task delivers a deterministic regression check we can rerun any time the SQL builders change, without standing up a JS test harness.
  </action>
  <verify>
    <automated>node scripts/verify-artist-placeholders.mjs</automated>
  </verify>
  <done>
    `scripts/verify-artist-placeholders.mjs` exists, runs without error, prints "OK: artist placeholder shape verified", and contains assertions for all five scenarios above. The mirror functions structurally match the post-fix Site A and Site B in `src/lib/records.ts`.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Manual UI verification of the failing reproduction</name>
  <what-built>
    Fix applied in `src/lib/records.ts` for Sites A (Songs/Albums via `buildFilters`) and B (Artists+year). Site C (Artists no-year) untouched. Programmatic placeholder-shape script passing.
  </what-built>
  <how-to-verify>
    Start the dev server in a terminal:
    ```
    npm run dev
    ```
    Open the records page (default `http://localhost:3000/records` — adjust to actual route if different) and run the following five scenarios. Each must return rows with no error banner:

    1. **Songs (Hot 100), Artist=`Katy, Taylor`** — the original failing repro. Expect rows with titles whose `artist_credit` matches Katy OR Taylor. NO "Failed to load custom records" banner.
    2. **Albums (Billboard 200), Artist=`Drake, Future`** — analogous Site A path for albums. Expect rows.
    3. **Artists (Hot 100, no year filter), Artist=`Katy, Taylor`** — exercises the already-correct Site C; must still work (regression guard).
    4. **Artists (Hot 100), Artist=`Katy, Taylor`, startYear=2010** — exercises Site B (year filter present). Expect rows.
    5. **Songs (Hot 100), Artist=`Beyonce` (single artist)** — single-artist regression check; expect rows.

    Additionally, with the dev server still running, hit the API directly to confirm the JSON response shape:
    ```
    curl -s 'http://localhost:3000/api/records?mode=custom&chart=hot-100&entity=songs&rankBy=total-weeks&artistNames=Katy%2C%20Taylor' | head -c 500
    ```
    Expect a JSON payload with `"mode":"custom"` and a non-empty `rows` array, NOT an `"error"` field.

    Tail the dev-server log during the failing repro to confirm no Postgres parameter-count errors are thrown.
  </how-to-verify>
  <resume-signal>Type "approved" if all five scenarios return rows with no error banner and the curl returns a `rows` array. Otherwise paste the failing scenario and the dev-server log line.</resume-signal>
</task>

</tasks>

<verification>
- `npx tsc --noEmit` passes.
- `npx eslint src/lib/records.ts` passes.
- `node scripts/verify-artist-placeholders.mjs` prints OK.
- All five manual UI scenarios return rows; no 500.
- `git diff src/lib/records.ts` shows changes ONLY at Site A (~line 550) and Site B (~line 658). Site C (~line 589) is unchanged.
</verification>

<success_criteria>
- Custom-query Songs/Albums/Artists with multiple comma-separated artists returns rows (no 500, no generic error banner).
- Single-artist queries still work across Songs/Albums/Artists and across both year-filter and no-year-filter branches.
- The "already correct" no-year Artists branch (Site C) is untouched.
- A reusable verification script lives at `scripts/verify-artist-placeholders.mjs` for future regressions.
</success_criteria>

<output>
After completion, create `.planning/quick/260508-mbw-fix-comma-separated-artist-input-failure/260508-mbw-SUMMARY.md` summarizing:
- Bug root cause (lazy `placeholder()` + map callback ordering).
- Two sites fixed (line numbers from final diff).
- One site deliberately untouched and why.
- Verification: tsc/eslint, mirror-script assertions, five-scenario UI check.
</output>
