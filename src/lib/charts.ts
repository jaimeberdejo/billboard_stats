/**
 * Weekly chart snapshot helpers.
 *
 * Mirrors the Python `chart_service.py` behavior:
 * - `get_weekly_chart()` -> `getWeeklyChart()`
 * - `get_available_dates()` -> `getAvailableDates()`
 *
 * Phantom-week filtering: the billboard.py library returns the first real
 * chart for any query date before the chart actually started. These phantom
 * weeks are detected (95%+ of entries have is_new=true AND weeks_on_chart=1)
 * and excluded from stats, keeping only the earliest such week per chart type.
 */

import { getSql } from "@/lib/db";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ChartType = "hot-100" | "billboard-200";

/** A single chart row returned for any chart type. */
export interface ChartEntry {
  rank: number;
  title: string;
  artist_credit: string;
  /** Populated with the first primary normalized artist for detail-page linking when available. */
  artist_id: number | null;
  image_url: string | null;
  peak_pos: number | null;
  last_pos: number | null;
  weeks_on_chart: number | null;
  is_new: boolean;
  /** Populated for hot-100 entries; null for billboard-200. */
  song_id: number | null;
  /** Populated for billboard-200 entries; null for hot-100. */
  album_id: number | null;
}

/** Full payload returned by `getChartSnapshot()`. */
export interface ChartSnapshot {
  chartType: ChartType;
  selectedDate: string;
  latestDate: string;
  availableDates: string[];
  entries: ChartEntry[];
}

// ---------------------------------------------------------------------------
// CTE fragments (translated from Python stats_builder.py)
//
// These strings are code constants — never derived from user input.
// Safe to compose inline into SQL queries.
// ---------------------------------------------------------------------------

const VALID_HOT100_WEEKS_CTE = `
    phantom_hot100 AS (
        SELECT e.chart_week_id
        FROM hot100_entries e
        GROUP BY e.chart_week_id
        HAVING COUNT(*) FILTER (WHERE e.is_new = true AND e.weeks_on_chart = 1)
               >= COUNT(*) * 95 / 100
    ),
    first_real_hot100 AS (
        SELECT MIN(cw.id) AS id
        FROM phantom_hot100 ph
        JOIN chart_weeks cw ON ph.chart_week_id = cw.id
        WHERE cw.chart_type = 'hot-100'
    ),
    valid_hot100_weeks AS (
        SELECT cw.id
        FROM chart_weeks cw
        WHERE cw.chart_type = 'hot-100'
          AND (cw.id NOT IN (SELECT chart_week_id FROM phantom_hot100)
               OR cw.id = (SELECT id FROM first_real_hot100))
    )
`;

const VALID_B200_WEEKS_CTE = `
    phantom_b200 AS (
        SELECT e.chart_week_id
        FROM b200_entries e
        GROUP BY e.chart_week_id
        HAVING COUNT(*) FILTER (WHERE e.is_new = true AND e.weeks_on_chart = 1)
               >= COUNT(*) * 95 / 100
    ),
    first_real_b200 AS (
        SELECT MIN(cw.id) AS id
        FROM phantom_b200 ph
        JOIN chart_weeks cw ON ph.chart_week_id = cw.id
        WHERE cw.chart_type = 'billboard-200'
    ),
    valid_b200_weeks AS (
        SELECT cw.id
        FROM chart_weeks cw
        WHERE cw.chart_type = 'billboard-200'
          AND (cw.id NOT IN (SELECT chart_week_id FROM phantom_b200)
               OR cw.id = (SELECT id FROM first_real_b200))
    )
`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ALLOWED_CHART_TYPES: ReadonlySet<string> = new Set(["hot-100", "billboard-200"]);

/** Narrow an arbitrary string to a valid ChartType, or return null. */
export function parseChartType(value: string | null | undefined): ChartType | null {
  if (value && ALLOWED_CHART_TYPES.has(value)) {
    return value as ChartType;
  }
  return null;
}

/** ISO date string validation (YYYY-MM-DD). */
export function isValidISODate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

/**
 * All available chart dates for a given chart type, newest first.
 * Excludes phantom weeks (duplicate data from before the chart started).
 */
export async function getAvailableDates(chartType: ChartType): Promise<string[]> {
  const sql = getSql();

  if (chartType === "hot-100") {
    const rows = await sql.query(
      `WITH ${VALID_HOT100_WEEKS_CTE}
       SELECT cw.chart_date::text AS chart_date
       FROM chart_weeks cw
       WHERE cw.chart_type = 'hot-100'
         AND cw.id IN (SELECT id FROM valid_hot100_weeks)
       ORDER BY cw.chart_date DESC`,
    );
    return rows.map((r) => r.chart_date as string);
  } else {
    const rows = await sql.query(
      `WITH ${VALID_B200_WEEKS_CTE}
       SELECT cw.chart_date::text AS chart_date
       FROM chart_weeks cw
       WHERE cw.chart_type = 'billboard-200'
         AND cw.id IN (SELECT id FROM valid_b200_weeks)
       ORDER BY cw.chart_date DESC`,
    );
    return rows.map((r) => r.chart_date as string);
  }
}

/**
 * Full chart entries for a specific week.
 *
 * Mirrors Python `get_weekly_chart()`. Only `hot-100` and `billboard-200`
 * are supported.
 *
 * @param chartType - `hot-100` or `billboard-200`
 * @param chartDate - ISO date string (YYYY-MM-DD), already validated by caller
 */
async function getWeeklyChart(
  chartType: ChartType,
  chartDate: string,
): Promise<ChartEntry[]> {
  const sql = getSql();

  if (chartType === "hot-100") {
    const rows = await sql.query(
      `WITH ${VALID_HOT100_WEEKS_CTE}
       SELECT e.rank,
              s.title,
              s.artist_credit,
              pa.artist_id,
              s.image_url,
              e.peak_pos,
              e.last_pos,
              e.weeks_on_chart,
              e.is_new,
              e.song_id
       FROM hot100_entries e
       JOIN chart_weeks cw ON e.chart_week_id = cw.id
       JOIN songs s ON e.song_id = s.id
       LEFT JOIN LATERAL (
         SELECT sa.artist_id
         FROM song_artists sa
         WHERE sa.song_id = s.id
         ORDER BY CASE WHEN sa.role = 'primary' THEN 0 ELSE 1 END, sa.artist_id
         LIMIT 1
       ) pa ON true
       WHERE cw.chart_date = $1::date
         AND cw.chart_type = 'hot-100'
         AND cw.id IN (SELECT id FROM valid_hot100_weeks)
       ORDER BY e.rank`,
      [chartDate],
    );
    return rows.map((r) => ({
      rank: r.rank as number,
      title: r.title as string,
      artist_credit: r.artist_credit as string,
      artist_id: (r.artist_id as number | null) ?? null,
      image_url: (r.image_url as string | null) ?? null,
      peak_pos: (r.peak_pos as number | null) ?? null,
      last_pos: (r.last_pos as number | null) ?? null,
      weeks_on_chart: (r.weeks_on_chart as number | null) ?? null,
      is_new: r.is_new as boolean,
      song_id: r.song_id as number,
      album_id: null,
    }));
  } else {
    const rows = await sql.query(
      `WITH ${VALID_B200_WEEKS_CTE}
       SELECT e.rank,
              a.title,
              a.artist_credit,
              pa.artist_id,
              a.image_url,
              e.peak_pos,
              e.last_pos,
              e.weeks_on_chart,
              e.is_new,
              e.album_id
       FROM b200_entries e
       JOIN chart_weeks cw ON e.chart_week_id = cw.id
       JOIN albums a ON e.album_id = a.id
       LEFT JOIN LATERAL (
         SELECT aa.artist_id
         FROM album_artists aa
         WHERE aa.album_id = a.id
         ORDER BY CASE WHEN aa.role = 'primary' THEN 0 ELSE 1 END, aa.artist_id
         LIMIT 1
       ) pa ON true
       WHERE cw.chart_date = $1::date
         AND cw.chart_type = 'billboard-200'
         AND cw.id IN (SELECT id FROM valid_b200_weeks)
       ORDER BY e.rank`,
      [chartDate],
    );
    return rows.map((r) => ({
      rank: r.rank as number,
      title: r.title as string,
      artist_credit: r.artist_credit as string,
      artist_id: (r.artist_id as number | null) ?? null,
      image_url: (r.image_url as string | null) ?? null,
      peak_pos: (r.peak_pos as number | null) ?? null,
      last_pos: (r.last_pos as number | null) ?? null,
      weeks_on_chart: (r.weeks_on_chart as number | null) ?? null,
      is_new: r.is_new as boolean,
      song_id: null,
      album_id: r.album_id as number,
    }));
  }
}

/**
 * Unified chart snapshot: entries + available dates for the requested
 * chart type and optional date.
 *
 * If `requestedDate` is not provided, the newest available date is used.
 * Returns `{ chartType, selectedDate, latestDate, availableDates, entries }`.
 */
export async function getChartSnapshot(
  chartType: ChartType,
  requestedDate?: string,
): Promise<ChartSnapshot> {
  const availableDates = await getAvailableDates(chartType);

  const latestDate = availableDates[0] ?? null;
  if (!latestDate) {
    return {
      chartType,
      selectedDate: "",
      latestDate: "",
      availableDates: [],
      entries: [],
    };
  }

  // Use requested date if available; fall back to latest.
  const selectedDate =
    requestedDate && availableDates.includes(requestedDate)
      ? requestedDate
      : latestDate;

  const entries = await getWeeklyChart(chartType, selectedDate);

  return {
    chartType,
    selectedDate,
    latestDate,
    availableDates,
    entries,
  };
}
