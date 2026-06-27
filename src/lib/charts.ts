/**
 * Weekly chart snapshot helpers — registry-backed, parametric path.
 *
 * Reads the polymorphic `chart_entries` / `charts` model through the SINGLE
 * shared phantom-week CTE (`validWeeksCte` in @/lib/valid-weeks). Every chart —
 * including Hot 100 and Billboard 200 — resolves its `chart_id` from the
 * registry and flows through the identical query; there is NO slug-specific read
 * branch and NO reference to the legacy `hot100_entries` / `b200_entries` tables.
 *
 * Phantom-week filtering: the billboard.py library returns the first real chart
 * for any query date before the chart actually started. These phantom weeks are
 * detected (95%+ of entries have is_new=true AND weeks_on_chart=1) and excluded,
 * keeping only the earliest such week per chart. The rule lives once in
 * @/lib/valid-weeks (CR-01: in lockstep with stats_builder.py).
 */

import { getSql } from "@/lib/db";
import { validWeeksCte, resolveChart, type ChartRow } from "@/lib/valid-weeks";
import { genreFamily, type ChartFamily } from "@/lib/chart-families";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * A chart identifier. Widened from the closed two-value union to the open
 * registry slug set; validated at the boundary via parseChartType /
 * resolveChart rather than by the type system.
 */
export type ChartType = string;

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
  /** Populated for song-entity charts; null otherwise. */
  song_id: number | null;
  /** Populated for album-entity charts; null otherwise. */
  album_id: number | null;
}

/** Active chart registry row, tagged with its derived genre family. */
export interface ChartRegistryRow {
  slug: string;
  title: string | null;
  entity_kind: "song" | "album" | "artist";
  category: string | null;
  family: ChartFamily;
  sort_order: number;
}

/** Full payload returned by `getChartSnapshot()`. */
export interface ChartSnapshot {
  /** Back-compat alias of the chart slug. */
  chartType: ChartType;
  /** Resolved chart slug (e.g. "hot-100", "country-songs"). */
  chartSlug: string;
  /** Human-facing chart title from the registry. */
  chartTitle: string | null;
  /** Derived display family (Core / Artist / Country / ...). */
  chartFamily: ChartFamily | null;
  /** Ranked entity type for this chart. */
  entityKind: "song" | "album" | "artist" | null;
  selectedDate: string;
  latestDate: string;
  availableDates: string[];
  previousDate: string | null;
  nextDate: string | null;
  entries: ChartEntry[];
}

// ---------------------------------------------------------------------------
// Entity-shape lookup (mirrors stats_builder.py _ENTITY_ROLLUP)
//
// Branches ONLY the entity JOIN/SELECT on entity_kind. All strings here are code
// constants — never derived from user input. The only bound values in the
// queries below are chart_id ($1) and chartDate ($2).
// ---------------------------------------------------------------------------

interface EntityQueryShape {
  /** Title column expression. */
  titleExpr: string;
  /** Artist-credit column expression. */
  artistCreditExpr: string;
  /** Image-url column expression. */
  imageUrlExpr: string;
  /** The entity-id column selected from chart_entries (e.song_id / e.album_id / e.artist_id). */
  entityIdExpr: string;
  /** JOIN(s) bringing the entity row + a primary-artist id into scope. */
  joins: string;
  /** Expression yielding the primary artist_id for detail-page linking. */
  artistIdExpr: string;
  /** Which ChartEntry field the entity id maps to. */
  entityIdField: "song_id" | "album_id";
}

const ENTITY_QUERY_SHAPE: Record<"song" | "album" | "artist", EntityQueryShape> = {
  song: {
    titleExpr: "s.title",
    artistCreditExpr: "s.artist_credit",
    imageUrlExpr: "s.image_url",
    entityIdExpr: "e.song_id",
    joins: `JOIN songs s ON e.song_id = s.id
       LEFT JOIN LATERAL (
         SELECT sa.artist_id
         FROM song_artists sa
         WHERE sa.song_id = s.id
         ORDER BY CASE WHEN sa.role = 'primary' THEN 0 ELSE 1 END, sa.artist_id
         LIMIT 1
       ) pa ON true`,
    artistIdExpr: "pa.artist_id",
    entityIdField: "song_id",
  },
  album: {
    titleExpr: "a.title",
    artistCreditExpr: "a.artist_credit",
    imageUrlExpr: "a.image_url",
    entityIdExpr: "e.album_id",
    joins: `JOIN albums a ON e.album_id = a.id
       LEFT JOIN LATERAL (
         SELECT aa.artist_id
         FROM album_artists aa
         WHERE aa.album_id = a.id
         ORDER BY CASE WHEN aa.role = 'primary' THEN 0 ELSE 1 END, aa.artist_id
         LIMIT 1
       ) pa ON true`,
    artistIdExpr: "pa.artist_id",
    entityIdField: "album_id",
  },
  // Artist-entity charts (e.g. Artist 100) carry artist_id directly on the
  // chart_entries row — no join table needed. The artist's name doubles as both
  // the title and the artist credit; there is no album_id / song_id.
  artist: {
    titleExpr: "ar.name",
    artistCreditExpr: "ar.name",
    imageUrlExpr: "ar.image_url",
    entityIdExpr: "e.artist_id",
    joins: `JOIN artists ar ON e.artist_id = ar.id`,
    artistIdExpr: "e.artist_id",
    entityIdField: "song_id", // unused for artist rows (both song_id/album_id null)
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Narrow an arbitrary string to a valid chart slug, or return null.
 *
 * Registry-driven (replaces the closed two-value allowlist): resolves the slug
 * against the active charts set. Returns the slug if it is an active chart, else
 * null. T-13-01: validation happens BEFORE any chart query keys on it.
 */
export async function parseChartType(
  value: string | null | undefined,
): Promise<ChartType | null> {
  if (!value) {
    return null;
  }
  const chart = await resolveChart(value);
  return chart ? chart.slug : null;
}

/** ISO date string validation (YYYY-MM-DD). */
export function isValidISODate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

/**
 * All active charts in the registry, tagged with their derived genre family.
 * Ordered by sort_order then title for stable nav/selector rendering.
 */
export async function listActiveCharts(): Promise<ChartRegistryRow[]> {
  const sql = getSql();
  const rows = await sql.query(
    `SELECT slug, title, entity_kind, category, sort_order
     FROM charts
     WHERE is_active = true
     ORDER BY sort_order, title`,
  );
  return rows.map((r) => {
    const slug = r.slug as string;
    const category = (r.category as string | null) ?? null;
    return {
      slug,
      title: (r.title as string | null) ?? null,
      entity_kind: r.entity_kind as "song" | "album" | "artist",
      category,
      family: genreFamily(slug, category),
      sort_order: r.sort_order as number,
    };
  });
}

/**
 * All available chart dates for a given chart slug, newest first.
 * Excludes phantom weeks (duplicate data from before the chart started).
 *
 * Single parametric path keyed by chart_id — no slug-specific branch. Unknown /
 * inactive slugs resolve to no chart and return an empty list.
 */
export async function getAvailableDates(chartSlug: ChartType): Promise<string[]> {
  const chart = await resolveChart(chartSlug);
  if (!chart) {
    return [];
  }
  const sql = getSql();
  const rows = await sql.query(
    `WITH ${validWeeksCte("valid_weeks", "$1")}
     SELECT cw.chart_date::text AS chart_date
     FROM chart_weeks cw
     WHERE cw.chart_id = $1
       AND cw.id IN (SELECT id FROM valid_weeks)
     ORDER BY cw.chart_date DESC`,
    [chart.id],
  );
  return rows.map((r) => r.chart_date as string);
}

/**
 * Full chart entries for a specific week of the given chart.
 *
 * Resolves chart_id + entity_kind from the registry, runs the parametric CTE
 * over `chart_entries` filtered by chart_id ($1) and chart_date ($2), and
 * branches ONLY the entity JOIN/SELECT on entity_kind (mirrors _ENTITY_ROLLUP).
 *
 * @param chart      resolved registry row (chart_id + entity_kind known)
 * @param chartDate  ISO date string (YYYY-MM-DD), already validated by caller
 */
async function getWeeklyChart(
  chart: ChartRow,
  chartDate: string,
): Promise<ChartEntry[]> {
  const sql = getSql();
  const shape = ENTITY_QUERY_SHAPE[chart.entity_kind];

  const rows = await sql.query(
    `WITH ${validWeeksCte("valid_weeks", "$1")}
     SELECT e.rank,
            ${shape.titleExpr} AS title,
            ${shape.artistCreditExpr} AS artist_credit,
            ${shape.artistIdExpr} AS artist_id,
            ${shape.imageUrlExpr} AS image_url,
            e.peak_pos,
            e.last_pos,
            e.weeks_on_chart,
            e.is_new,
            ${shape.entityIdExpr} AS entity_id
     FROM chart_entries e
     JOIN chart_weeks cw ON e.chart_week_id = cw.id
     ${shape.joins}
     WHERE cw.chart_id = $1
       AND cw.chart_date = $2::date
       AND cw.id IN (SELECT id FROM valid_weeks)
     ORDER BY e.rank`,
    [chart.id, chartDate],
  );

  return rows.map((r) => {
    const entityId = (r.entity_id as number | null) ?? null;
    return {
      rank: r.rank as number,
      title: r.title as string,
      artist_credit: r.artist_credit as string,
      artist_id: (r.artist_id as number | null) ?? null,
      image_url: (r.image_url as string | null) ?? null,
      peak_pos: (r.peak_pos as number | null) ?? null,
      last_pos: (r.last_pos as number | null) ?? null,
      weeks_on_chart: (r.weeks_on_chart as number | null) ?? null,
      is_new: r.is_new as boolean,
      song_id: chart.entity_kind === "song" ? entityId : null,
      album_id: chart.entity_kind === "album" ? entityId : null,
    };
  });
}

/**
 * Unified chart snapshot: entries + available dates for the requested chart slug
 * and optional date.
 *
 * If `requestedDate` is not provided, the newest available date is used. An
 * unknown / inactive slug behaves as the "no data" case (empty snapshot) rather
 * than throwing, so a newly-removed chart degrades gracefully.
 */
export async function getChartSnapshot(
  chartSlug: ChartType,
  requestedDate?: string,
): Promise<ChartSnapshot> {
  const chart = await resolveChart(chartSlug);

  if (!chart) {
    return {
      chartType: chartSlug,
      chartSlug,
      chartTitle: null,
      chartFamily: null,
      entityKind: null,
      selectedDate: "",
      latestDate: "",
      availableDates: [],
      previousDate: null,
      nextDate: null,
      entries: [],
    };
  }

  const chartFamily = genreFamily(chart.slug, chart.category);
  const availableDates = await getAvailableDates(chart.slug);

  const latestDate = availableDates[0] ?? null;
  if (!latestDate) {
    return {
      chartType: chart.slug,
      chartSlug: chart.slug,
      chartTitle: chart.title,
      chartFamily,
      entityKind: chart.entity_kind,
      selectedDate: "",
      latestDate: "",
      availableDates: [],
      previousDate: null,
      nextDate: null,
      entries: [],
    };
  }

  // Use requested date if available; fall back to latest.
  const selectedDate =
    requestedDate && availableDates.includes(requestedDate)
      ? requestedDate
      : latestDate;
  const selectedIndex = availableDates.indexOf(selectedDate);

  const entries = await getWeeklyChart(chart, selectedDate);

  return {
    chartType: chart.slug,
    chartSlug: chart.slug,
    chartTitle: chart.title,
    chartFamily,
    entityKind: chart.entity_kind,
    selectedDate,
    latestDate,
    availableDates,
    previousDate:
      selectedIndex >= 0 && selectedIndex < availableDates.length - 1
        ? availableDates[selectedIndex + 1]
        : null,
    nextDate: selectedIndex > 0 ? availableDates[selectedIndex - 1] : null,
    entries,
  };
}
