# Phase 7: Natural-Language Query Interpretation - Pattern Map

**Mapped:** 2026-04-29
**Files analyzed:** 6
**Analogs found:** 5 / 6

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/app/api/query/route.ts` | route | request-response | `src/app/api/records/route.ts` | exact |
| `src/lib/nlq/schema.ts` | model | transform | `src/lib/records.ts` | role-match |
| `src/lib/nlq/normalize.ts` | utility | transform | `src/lib/search.ts` | partial |
| `src/lib/nlq/catalog.ts` | config | transform | `src/lib/charts.ts` | role-match |
| `src/lib/nlq/interpret.ts` | service | transform | `src/app/api/records/route.ts` | partial |
| `src/lib/nlq/explain.ts` | utility | transform | `src/components/records/custom-query-builder.tsx` | partial |
| `src/lib/nlq/fixtures.ts` | test | transform | — | none |

## Pattern Assignments

### `src/app/api/query/route.ts` (route, request-response)

**Analog:** `src/app/api/records/route.ts`

**Why this match:** Phase 7 needs the same server-owned boundary as the records endpoint: trim request params, validate against allowlists, return concise `400` errors for invalid input, and keep `500` responses generic.

**Imports pattern** ([src/app/api/records/route.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/app/api/records/route.ts:1)):
```typescript
import { type NextRequest } from "next/server";

import { parseChartType, type ChartType } from "@/lib/charts";
import {
  type CustomEntity,
  getArtistRecordDrilldown,
  getCustomRecords,
  getPresetRecords,
  type CustomRankBy,
  type RecordPreset,
} from "@/lib/records";
```

**Validation branch pattern** ([src/app/api/records/route.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/app/api/records/route.ts:81)):
```typescript
export async function GET(request: NextRequest): Promise<Response> {
  const { searchParams } = request.nextUrl;
  const mode = searchParams.get("mode");
  const chart = parseChartType(searchParams.get("chart"));

  if (!chart) {
    return Response.json(
      { error: 'Invalid or missing "chart" parameter. Must be "hot-100" or "billboard-200".' },
      { status: 400 },
    );
  }
```

**Range/error guard pattern** ([src/app/api/records/route.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/app/api/records/route.ts:130)):
```typescript
const maxPosition = maxPositionForChart(chart);
const defaultRankByParam = rankBy === "weeks-at-position" ? 1 : 10;
const rankByParam =
  parsePositiveInteger(searchParams.get("rankByParam"), 1, maxPosition) ??
  defaultRankByParam;

if (peakMin && peakMax && peakMin > peakMax) {
  return Response.json(
    { error: 'Custom mode received an invalid peak range: minimum exceeds maximum.' },
    { status: 400 },
  );
}
```

**Failure handling pattern** ([src/app/api/records/route.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/app/api/records/route.ts:156)):
```typescript
try {
  const payload = await getCustomRecords({
    entity,
    chart,
    rankBy,
    rankByParam,
    sortDir,
    peakMin,
    peakMax,
    weeksMin,
    debutPosMin,
    debutPosMax,
    artistNames: parseArtistNames(searchParams.get("artistNames")),
  });
  return Response.json(payload);
} catch {
  return Response.json(
    { error: "Failed to load custom records. Please try again later." },
    { status: 500 },
  );
}
```

**Planning note:** Keep `route.ts` interpretation-only. It should call `interpret` and `explain`, and it should not import `searchAll`, `getPresetRecords`, or `getCustomRecords` in Phase 7.

---

### `src/lib/nlq/schema.ts` (model, transform)

**Analog:** `src/lib/records.ts`

**Why this match:** `records.ts` is the repo’s main example of a typed contract module: union types first, payload/input interfaces next, then narrow helper constants.

**Type union pattern** ([src/lib/records.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/lib/records.ts:50)):
```typescript
export type RecordPreset =
  | "most-weeks-at-number-one"
  | "longest-chart-runs"
  | "most-top-10-weeks"
  | "most-number-one-songs-by-artist"
  | "most-number-one-albums-by-artist"
  | "most-entries-by-artist"
  | "most-total-chart-weeks-by-artist"
  | "most-simultaneous-entries";

export type CustomRankBy =
  | "weeks-at-number-one"
  | "total-weeks"
  | "weeks-at-position"
  | "weeks-in-top-n"
  | "most-entries"
  | "number-one-entries";

export type CustomEntity = "songs" | "albums" | "artists";
```

**Input object pattern** ([src/lib/records.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/lib/records.ts:100)):
```typescript
export interface CustomRecordsInput {
  entity: CustomEntity;
  chart: ChartType;
  rankBy: CustomRankBy;
  rankByParam: number;
  sortDir?: "asc" | "desc";
  limit?: number;
  peakMin?: number | null;
  peakMax?: number | null;
  weeksMin?: number | null;
  debutPosMin?: number | null;
  debutPosMax?: number | null;
  artistNames?: string[] | null;
}
```

**Payload object pattern** ([src/lib/search.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/lib/search.ts:30)):
```typescript
export interface SearchResultsPayload {
  query: string;
  songs: SearchSongRow[];
  albums: SearchAlbumRow[];
  artists: SearchArtistRow[];
}
```

**Planning note:** `schema.ts` should export both Zod schemas and inferred TS types for the bounded IR from research: `status`, `intent`, `search`, `recordsPreset`, and `recordsCustom`.

---

### `src/lib/nlq/normalize.ts` (utility, transform)

**Analog:** `src/lib/search.ts`

**Why this match:** The current search path keeps normalization narrow and deterministic. Phase 7 normalization should do the same: trim, collapse obvious noise, but avoid semantic guessing.

**Minimal normalization pattern** ([src/lib/search.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/lib/search.ts:37)):
```typescript
const SEARCH_LIMIT = 50;

function normalizeQuery(query: string): string {
  return query.trim();
}

export async function searchAll(query: string): Promise<SearchResultsPayload> {
  const normalized = normalizeQuery(query);
  if (normalized.length < 2) {
    return {
      query: normalized,
      songs: [],
      albums: [],
      artists: [],
    };
  }
```

**CSV splitting pattern for names/tokens** ([src/app/api/records/route.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/app/api/records/route.ts:66)):
```typescript
function parseArtistNames(value: string | null): string[] | null {
  if (!value) {
    return null;
  }
  const parts = value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.length > 0 ? parts : null;
}
```

**Planning note:** Normalize text into a canonical lowercased/tokenized form, but preserve the original question separately for explanation output and future execution handoff.

---

### `src/lib/nlq/catalog.ts` (config, transform)

**Analog:** `src/lib/charts.ts`

**Why this match:** `charts.ts` shows the current allowlist style: central constant set first, small parser helper second. `catalog.ts` should be the alias/keyword equivalent for intent, chart, entity, and metric vocab.

**Allowlist constant pattern** ([src/lib/charts.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/lib/charts.ts:106)):
```typescript
const ALLOWED_CHART_TYPES: ReadonlySet<string> = new Set(["hot-100", "billboard-200"]);

export function parseChartType(value: string | null | undefined): ChartType | null {
  if (value && ALLOWED_CHART_TYPES.has(value)) {
    return value as ChartType;
  }
  return null;
}
```

**Value-label catalog pattern** ([src/lib/records.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/lib/records.ts:134)):
```typescript
const PRESET_VALUE_LABELS: Record<RecordPreset, string> = {
  "most-weeks-at-number-one": "Wks #1",
  "longest-chart-runs": "Total Wks",
  "most-top-10-weeks": "Top 10 Wks",
  "most-number-one-songs-by-artist": "#1 Songs",
  "most-number-one-albums-by-artist": "#1 Albums",
  "most-entries-by-artist": "Entries",
  "most-total-chart-weeks-by-artist": "Total Wks",
  "most-simultaneous-entries": "Simult.",
};
```

**UI vocabulary source** ([src/components/records/custom-query-builder.tsx](/Users/jaimeberdejosanchez/projects/billboard_stats/src/components/records/custom-query-builder.tsx:52)):
```typescript
const entityOptions: Array<{ label: string; value: CustomEntity }> = [
  { label: "Songs", value: "songs" },
  { label: "Albums", value: "albums" },
  { label: "Artists", value: "artists" },
];

const rankOptions: Array<{ label: string; value: CustomRankBy }> =
  state.entity === "artists"
    ? [
        { label: "total chart weeks", value: "total-weeks" },
        { label: "most entries", value: "most-entries" },
```

**Planning note:** Build `catalog.ts` from the backend’s real enums, not from freeform prompt phrasing. The alias maps should collapse into existing record/chart/entity values only.

---

### `src/lib/nlq/interpret.ts` (service, transform)

**Analog:** `src/app/api/records/route.ts`

**Why this match:** The core task is deterministic branching from raw input into a narrow contract. `records/route.ts` already models that style with mode-first branching, per-branch validation, defaults, and explicit invalid states.

**Branch-by-mode pattern** ([src/app/api/records/route.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/app/api/records/route.ts:93)):
```typescript
if (mode === "preset") {
  const record = searchParams.get("record");
  if (!isValidRecordPreset(record)) {
    return Response.json(
      { error: 'Invalid or missing "record" parameter for preset mode.' },
      { status: 400 },
    );
  }
```

**Defaults derived from validated intent** ([src/app/api/records/route.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/app/api/records/route.ts:130)):
```typescript
const maxPosition = maxPositionForChart(chart);
const defaultRankByParam = rankBy === "weeks-at-position" ? 1 : 10;
const rankByParam =
  parsePositiveInteger(searchParams.get("rankByParam"), 1, maxPosition) ??
  defaultRankByParam;
const sortDir =
  searchParams.get("sortDir") === "asc" ? "asc" : "desc";
```

**Deterministic bounded return pattern** ([src/lib/search.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/lib/search.ts:43)):
```typescript
export async function searchAll(query: string): Promise<SearchResultsPayload> {
  const normalized = normalizeQuery(query);
  if (normalized.length < 2) {
    return {
      query: normalized,
      songs: [],
      albums: [],
      artists: [],
    };
  }
```

**Planning note:** Structure `interpret.ts` as `normalize -> detect intent -> extract params -> validate against schema -> return status`. It should return `needs_clarification` and `unsupported` objects instead of throwing for domain ambiguity.

---

### `src/lib/nlq/explain.ts` (utility, transform)

**Analog:** `src/components/records/custom-query-builder.tsx`

**Why this match:** The query builder already turns structured filter state into short human-readable phrases. `explain.ts` should do the server-side equivalent from the interpretation object.

**Readable phrase composition pattern** ([src/components/records/custom-query-builder.tsx](/Users/jaimeberdejosanchez/projects/billboard_stats/src/components/records/custom-query-builder.tsx:87)):
```tsx
return (
  <div className="flex flex-col gap-4">
    <div className="rounded-r-[6px] rounded-l-none border border-[#E0E0E0] border-l-[3px] border-l-[#C8102E] bg-white px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-1 gap-y-2 text-[14px] leading-[2] text-[#333333]">
        <span>Show me</span>
        <strong>{entityLabel}</strong>
```

**Domain label pattern** ([src/lib/records.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/lib/records.ts:134)):
```typescript
const PRESET_VALUE_LABELS: Record<RecordPreset, string> = {
  "most-weeks-at-number-one": "Wks #1",
  "longest-chart-runs": "Total Wks",
  "most-top-10-weeks": "Top 10 Wks",
```

**Planning note:** Generate explanation text from normalized enum values, not from the raw query. That keeps explanations stable when synonyms like `b200`, `billboard 200`, and `albums chart` normalize to the same chart.

---

### `src/lib/nlq/fixtures.ts` (test, transform)

**Analog:** none

**Why no close analog:** The repo does not currently have an in-repo test/fixture pattern for app code, and research explicitly introduces golden NL queries as a new evaluation asset rather than matching an existing test harness.

**Use research shape instead** ([07-RESEARCH.md](/Users/jaimeberdejosanchez/projects/billboard_stats/.planning/phases/07-natural-language-query-interpretation/07-RESEARCH.md:125)):
```text
│       └── fixtures.ts           # golden query cases for planning/evals
```

**Supporting rationale** ([07-RESEARCH.md](/Users/jaimeberdejosanchez/projects/billboard_stats/.planning/phases/07-natural-language-query-interpretation/07-RESEARCH.md:27)):
```text
That makes a deterministic, schema-first interpreter the best default for planning:
it minimizes new infrastructure, keeps execution safety aligned with Phase 8,
and remains easy to regression-test with golden queries before a UI arrives in Phase 9.
```

**Planning note:** Store fixture objects as plain typed cases, for example `{ query, expectedStatus, expectedIntent, expectedSubset }`, and keep them independent from any runner-specific API.

## Shared Patterns

### Typed bounded contracts
**Source:** [src/lib/records.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/lib/records.ts:50), [src/lib/search.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/lib/search.ts:30)
**Apply to:** `schema.ts`, `interpret.ts`, `route.ts`
```typescript
export type CustomEntity = "songs" | "albums" | "artists";

export interface CustomRecordsInput {
  entity: CustomEntity;
  chart: ChartType;
  rankBy: CustomRankBy;
  rankByParam: number;
  sortDir?: "asc" | "desc";
  peakMin?: number | null;
  peakMax?: number | null;
  weeksMin?: number | null;
  debutPosMin?: number | null;
  debutPosMax?: number | null;
  artistNames?: string[] | null;
}
```

### Chart allowlists and parser helpers
**Source:** [src/lib/charts.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/lib/charts.ts:106)
**Apply to:** `catalog.ts`, `interpret.ts`, `route.ts`
```typescript
const ALLOWED_CHART_TYPES: ReadonlySet<string> = new Set(["hot-100", "billboard-200"]);

export function parseChartType(value: string | null | undefined): ChartType | null {
  if (value && ALLOWED_CHART_TYPES.has(value)) {
    return value as ChartType;
  }
  return null;
}
```

### Numeric/range parsing
**Source:** [src/app/api/records/route.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/app/api/records/route.ts:39)
**Apply to:** `normalize.ts`, `interpret.ts`
```typescript
function parsePositiveInteger(
  value: string | null,
  minimum = 1,
  maximum = Number.MAX_SAFE_INTEGER,
): number | null {
  if (!value || !/^\d+$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    return null;
  }
  return parsed;
}
```

### Concise route error responses
**Source:** [src/app/api/search/route.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/app/api/search/route.ts:5), [src/app/api/charts/route.ts](/Users/jaimeberdejosanchez/projects/billboard_stats/src/app/api/charts/route.ts:24)
**Apply to:** `src/app/api/query/route.ts`
```typescript
if (query.length < 2) {
  return Response.json(
    { error: 'Search query cannot be shorter than 2 characters.' },
    { status: 400 },
  );
}

try {
  const payload = await searchAll(query);
  return Response.json(payload);
} catch {
  return Response.json(
    { error: "Failed to load search results. Please try again later." },
    { status: 500 },
  );
}
```

### UI vocabulary as canonical phrasing source
**Source:** [src/components/records/custom-query-builder.tsx](/Users/jaimeberdejosanchez/projects/billboard_stats/src/components/records/custom-query-builder.tsx:58)
**Apply to:** `catalog.ts`, `explain.ts`, `fixtures.ts`
```typescript
const rankOptions: Array<{ label: string; value: CustomRankBy }> =
  state.entity === "artists"
    ? [
        { label: "total chart weeks", value: "total-weeks" },
        { label: "most entries", value: "most-entries" },
        {
          label: entityChart === "hot-100" ? "most #1 songs" : "most #1 albums",
          value: "number-one-entries",
        },
      ]
    : [
        { label: "#1 rank", value: "weeks-at-number-one" },
        { label: "specific position", value: "weeks-at-position" },
        { label: "top range", value: "weeks-in-top-n" },
        { label: "total weeks on chart", value: "total-weeks" },
      ];
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/lib/nlq/fixtures.ts` | test | transform | No existing app-code test fixtures or golden-query corpus in `src/`; planner should use Phase 7 research guidance instead. |

## Metadata

**Analog search scope:** `src/app/api`, `src/lib`, `src/components/records`, `src/components/search`, `.planning/phases/07-natural-language-query-interpretation`
**Files scanned:** 11
**Pattern extraction date:** 2026-04-29
