/**
 * Genre-family derivation for the chart selector and two-level nav.
 *
 * Read-side ONLY: this derives a coarse display family from a chart's slug +
 * category. NO database column is added — the curated genre lives in
 * billboard_stats/etl/charts.py (CURATED_CHARTS[].genre) and the registry only
 * stores `category` ('core' | 'genre' | 'artist'). This module maps the 11
 * curated charts onto a stable, UI-facing family grouping.
 *
 * Seed source of truth: billboard_stats/etl/charts.py CURATED_CHARTS (genre slugs
 * country | r-b-hip-hop | rock | latin) plus the two legacy core charts (hot-100,
 * billboard-200) and artist-100.
 */

/** Coarse display family for nav + detail-page grouping. */
export type ChartFamily =
  | "Core"
  | "Artist"
  | "Country"
  | "Latin"
  | "R&B/Hip-Hop"
  | "Rock";

/**
 * Stable display order shared by the nav and the detail-page grouping so both
 * render families in the same sequence. Matches the UI-SPEC families ordering:
 * core → artist → country → latin → r-b-hip-hop → rock.
 */
export const FAMILY_ORDER: readonly ChartFamily[] = [
  "Core",
  "Artist",
  "Country",
  "Latin",
  "R&B/Hip-Hop",
  "Rock",
] as const;

/**
 * Map a genre-slug prefix to its display family. Seeded from the CURATED_CHARTS
 * `genre` values. Both the `-songs` and `-albums` variants of a genre share the
 * same family (the prefix match below covers both).
 */
const GENRE_PREFIX_FAMILY: Record<string, ChartFamily> = {
  "country-": "Country",
  "r-b-hip-hop-": "R&B/Hip-Hop",
  "rock-": "Rock",
  "latin-": "Latin",
};

/**
 * Derive the display family for a chart from its slug + registry category.
 *
 *   - hot-100 / billboard-200, or category 'core'  -> "Core"
 *   - artist-100, or category 'artist'             -> "Artist"
 *   - otherwise match the genre slug prefix (country- / r-b-hip-hop- / rock- /
 *     latin-)                                        -> the matched genre family
 *   - any unknown future chart                      -> "Core" (so a newly
 *     ingested chart still appears in nav rather than throwing)
 */
export function genreFamily(slug: string, category: string | null): ChartFamily {
  if (slug === "hot-100" || slug === "billboard-200" || category === "core") {
    return "Core";
  }
  if (slug === "artist-100" || category === "artist") {
    return "Artist";
  }
  for (const prefix of Object.keys(GENRE_PREFIX_FAMILY)) {
    if (slug.startsWith(prefix)) {
      return GENRE_PREFIX_FAMILY[prefix];
    }
  }
  // Unknown/future chart: keep it visible in nav rather than throwing.
  return "Core";
}

// ---------------------------------------------------------------------------
// Synchronous chart metadata (depth + entity_kind), seeded from the registry.
//
// SOURCE OF TRUTH — keep in lockstep with:
//   billboard_stats/etl/charts.py CURATED_CHARTS + the legacy core seed.
//
// The async read paths (records.ts, /api/records, charts.ts) resolve depth +
// entity_kind from the `charts` registry row directly. But the NLQ interpreter
// (src/lib/nlq/interpret.ts) MUST stay PURE / SYNCHRONOUS / offline-testable —
// it cannot do a DB round-trip. This static map is the registry-derived,
// no-DB source the interpreter uses to generalize its chart-depth + entity_kind
// guards off the closed two-chart universe (it replaces the hardcoded
// `chart === "hot-100" ? 100 : 200` and `chart === "billboard-200"` branches).
//
// Depth = the chart's rank count (max position): Hot 100 = 100, Billboard 200
// = 200, Artist 100 = 100, and the curated genre song/album charts publish a
// top-50. The `-songs`/`-albums` genre charts are matched by slug prefix so a
// new `<genre>-songs` / `<genre>-albums` chart inherits the right entity_kind +
// depth without a code change. Unknown future charts fall back to a safe
// song-entity / depth-100 default rather than throwing.
// ---------------------------------------------------------------------------

export type ChartEntityKind = "song" | "album" | "artist";

interface ChartMeta {
  entityKind: ChartEntityKind;
  depth: number;
}

/** Exact-slug metadata for the non-genre-prefixed charts. */
const CHART_META_BY_SLUG: Record<string, ChartMeta> = {
  "hot-100": { entityKind: "song", depth: 100 },
  "billboard-200": { entityKind: "album", depth: 200 },
  "artist-100": { entityKind: "artist", depth: 100 },
};

/**
 * Genre-prefix metadata. The curated genre charts are deliberately named
 * `<genre>-songs` / `<genre>-albums` (country / r-b-hip-hop / rock / latin), all
 * top-50, so a prefix rule covers each genre's song+album pair with one entry.
 */
const GENRE_SUFFIX_META: Array<{ suffix: string; meta: ChartMeta }> = [
  { suffix: "-songs", meta: { entityKind: "song", depth: 50 } },
  { suffix: "-albums", meta: { entityKind: "album", depth: 50 } },
];

const DEFAULT_CHART_META: ChartMeta = { entityKind: "song", depth: 100 };

function lookupChartMeta(slug: string): ChartMeta {
  const exact = CHART_META_BY_SLUG[slug];
  if (exact) {
    return exact;
  }
  for (const { suffix, meta } of GENRE_SUFFIX_META) {
    if (slug.endsWith(suffix)) {
      return meta;
    }
  }
  return DEFAULT_CHART_META;
}

/**
 * The chart's rank count (max position) — the registry-derived replacement for
 * the hardcoded `chart === "hot-100" ? 100 : 200`. Used for position-range
 * validation bounds in the records API and the NLQ interpreter.
 */
export function chartDepth(slug: string): number {
  return lookupChartMeta(slug).depth;
}

/**
 * The ranked entity type for a chart, derived synchronously from its slug —
 * the registry-derived replacement for the `chart === "hot-100"` /
 * `chart === "billboard-200"` entity guards in the NLQ interpreter.
 */
export function chartEntityKind(slug: string): ChartEntityKind {
  return lookupChartMeta(slug).entityKind;
}
