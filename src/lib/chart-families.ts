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
