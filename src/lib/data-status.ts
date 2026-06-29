/**
 * Data status and freshness helpers.
 *
 * Mirrors the Python `data_status_service.py` behavior:
 * - `get_table_counts()` -> `getTableCounts()`
 * - `get_latest_chart_dates()` -> `getLatestChartDates()`
 * - `get_data_summary()` -> `getDataSummary()`
 */

import { getSql } from "@/lib/db";
import { saturdayPredicate } from "@/lib/chart-week";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Row counts for all major tracked tables. */
export interface TableCounts {
  chart_weeks: number;
  chart_entries: number;
  songs: number;
  albums: number;
  artists: number;
  song_stats: number;
  album_stats: number;
  artist_stats: number;
}

/** Latest chart_date per chart (keyed by chart slug). */
export type LatestDates = Record<string, string>;

/** Combined summary returned by `getDataSummary()`. */
export interface DataSummary {
  counts: TableCounts;
  latestDates: LatestDates;
  chart_weeks: number;
  songs: number;
  albums: number;
  artists: number;
  chart_entries: number;
}

// ---------------------------------------------------------------------------
// Allowed table list (mirrors Python _ALLOWED_TABLES allowlist)
// ---------------------------------------------------------------------------

const ALLOWED_TABLES = [
  "chart_weeks",
  "chart_entries",
  "songs",
  "albums",
  "artists",
  "song_stats",
  "album_stats",
  "artist_stats",
] as const;

type AllowedTable = (typeof ALLOWED_TABLES)[number];

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

/**
 * Row counts for all major tables.
 * Table names come exclusively from the hardcoded allowlist — safe to inline.
 */
export async function getTableCounts(): Promise<TableCounts> {
  const sql = getSql();

  // Build a single query using UNION ALL to avoid N round trips.
  const unionQuery = ALLOWED_TABLES.map(
    (table) => `SELECT '${table}' AS tbl, COUNT(*) AS cnt FROM ${table}`,
  ).join("\nUNION ALL\n");

  const rows = await sql.query(unionQuery);

  const counts: Partial<TableCounts> = {};
  for (const row of rows) {
    const tbl = row.tbl as AllowedTable;
    counts[tbl] = parseInt(row.cnt as string, 10);
  }

  return {
    chart_weeks: counts.chart_weeks ?? 0,
    chart_entries: counts.chart_entries ?? 0,
    songs: counts.songs ?? 0,
    albums: counts.albums ?? 0,
    artists: counts.artists ?? 0,
    song_stats: counts.song_stats ?? 0,
    album_stats: counts.album_stats ?? 0,
    artist_stats: counts.artist_stats ?? 0,
  };
}

/**
 * Latest chart_date per chart, grouped (keyed by chart slug).
 *
 * Reads the chart identity from the `charts` registry via `chart_weeks.chart_id`
 * (the dropped chart-type discriminator column is gone). The returned keys are
 * chart slugs (`'hot-100'` / `'billboard-200'` / ...), unchanged from before —
 * downstream consumers that index by slug are unaffected.
 */
export async function getLatestChartDates(): Promise<LatestDates> {
  const sql = getSql();

  // The Saturday (chart-day) predicate is a code constant sourced from the
  // single-source-of-truth chart-week module — no bound params here, so this
  // uses the sql.query(text) form (matching how records.ts composes constant
  // predicate text) rather than the tagged-template form.
  const rows = await sql.query(
    `SELECT c.slug,
           MAX(cw.chart_date)::text AS latest_date
    FROM chart_weeks cw
    JOIN charts c ON cw.chart_id = c.id
    WHERE cw.chart_date <= CURRENT_DATE
      AND ${saturdayPredicate("cw.chart_date")}
    GROUP BY c.slug`,
  );

  const result: LatestDates = {};
  for (const row of rows) {
    result[row.slug as string] = row.latest_date as string;
  }
  return result;
}

/**
 * Combined summary: counts, latest dates, and top-level numeric shortcuts.
 * Mirrors Python `get_data_summary()`.
 */
export async function getDataSummary(): Promise<DataSummary> {
  const [counts, latestDates] = await Promise.all([
    getTableCounts(),
    getLatestChartDates(),
  ]);

  return {
    counts,
    latestDates,
    chart_weeks: counts.chart_weeks,
    songs: counts.songs,
    albums: counts.albums,
    artists: counts.artists,
    chart_entries: counts.chart_entries,
  };
}
