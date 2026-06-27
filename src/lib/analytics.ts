/**
 * Server-side analytics query layer (Phase 14).
 *
 * Three correctness-critical query shapes live here, each COMPOSING the already-
 * shipped primitives rather than reinventing them:
 *
 *   - getEntityComparison  (ANALYTICS-01) — five era-labeled metric families per
 *     entity, computed over the entity's full multi-chart career via
 *     `validWeeksForCharts` (per-chart MIN(cw.id) first-real-week tie-break
 *     preserved — NEVER a single global MIN across charts).
 *   - getPresenceByYear    (ANALYTICS-02) — {year, weeks}[] where `weeks` is the
 *     COUNT of valid-week rows GROUP BY year. The per-row Billboard counter is
 *     deliberately NOT summed (Pitfall 2 / the documented methodology invariant).
 *   - getThisWeekInHistory (ANALYTICS-03) — the same ISO week across prior years
 *     (Saturday-aligned via @/lib/chart-week), with explicit charted:false
 *     markers for years that had no chart that week (no-throw degradation).
 *
 * METHODOLOGY INVARIANT (grep-gated): every count is `COUNT(*)` over valid-week
 * rows selected through `validWeeksCte` / `validWeeksForCharts`. There is no
 * arithmetic over the per-row `weeks_on_chart` counter anywhere in this module —
 * that counter is Billboard's own, is not phantom-filtered, and over-counts.
 *
 * SECURITY: all SQL text is a CODE CONSTANT. The only values that flow from a
 * request are bound as `$N` query parameters (chart ids, entity ids, dates,
 * topN); the route layer validates slug/entityKind/id/date against the registry
 * and allowlists BEFORE calling any function here. Nothing user-supplied is ever
 * interpolated into the SQL string.
 */

import { getSql } from "@/lib/db";
import { validWeeksCte, validWeeksForCharts } from "@/lib/valid-weeks";

// ---------------------------------------------------------------------------
// Shared entity-kind shape
// ---------------------------------------------------------------------------

/** The three comparable entity kinds. */
export type EntityKind = "artist" | "song" | "album";

/**
 * The `chart_entries` id column that carries each entity kind. All three are
 * code constants keyed by a validated `EntityKind` — never derived from raw
 * request text — so they are safe to splice into the constant SQL.
 */
const ENTITY_ID_COLUMN: Record<EntityKind, string> = {
  artist: "artist_id",
  song: "song_id",
  album: "album_id",
};

/** Defensive ISO-date coercion (mirrors the records.ts `toIsoDate` idiom). */
function toIsoDate(value: unknown): string | null {
  if (typeof value === "string") {
    return value.length >= 10 ? value.slice(0, 10) : value;
  }
  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }
  return null;
}

/** Year extracted from an ISO date string, or null. */
function yearOf(isoDate: string | null): number | null {
  if (!isoDate) {
    return null;
  }
  const year = Number(isoDate.slice(0, 4));
  return Number.isInteger(year) ? year : null;
}

// ---------------------------------------------------------------------------
// ANALYTICS-01: entity comparison
// ---------------------------------------------------------------------------

/** The five comparable metric families for one entity. */
export interface ComparisonMetrics {
  /** Best (lowest) rank ever achieved — MIN(rank). Null if no chart history. */
  peak: number | null;
  /** COUNT of valid chart-week rows (NOT the per-row counter). */
  weeksOnChart: number;
  /** COUNT FILTER (rank = 1) — weeks spent at #1. */
  weeksAtNumberOne: number;
  /** COUNT FILTER (rank <= 10) — weeks spent in the top 10. */
  topTenWeeks: number;
  /** MIN(chart_date) across the entity's valid weeks. */
  firstDate: string | null;
  /** MAX(chart_date) across the entity's valid weeks. */
  lastDate: string | null;
  /** Human-facing active era, e.g. "1991–2004" (empty if no history). */
  activeEra: string;
}

/** One side of a comparison. */
export interface ComparisonEntity {
  kind: EntityKind;
  id: number;
  label: string;
  /** The chart slugs this entity appears on (transparency for cross-era spans). */
  charts: string[];
  metrics: ComparisonMetrics;
}

/** Full 2-up comparison payload. */
export interface ComparisonPayload {
  left: ComparisonEntity;
  right: ComparisonEntity;
  /** Methodology notes — labels each metric so cross-era totals are honest. */
  metricDefinitions: Record<keyof ComparisonMetrics, string>;
}

const COMPARISON_METRIC_DEFINITIONS: Record<keyof ComparisonMetrics, string> = {
  peak: "best (lowest) rank ever achieved",
  weeksOnChart: "valid chart weeks (count of chart-week rows)",
  weeksAtNumberOne: "weeks at #1 (rank = 1 valid-week rows)",
  topTenWeeks: "weeks in the top 10 (rank ≤ 10 valid-week rows)",
  firstDate: "earliest valid chart date",
  lastDate: "latest valid chart date",
  activeEra: "first–last charting year",
};

/** Zeroed metrics for an entity with no chart history (no-throw degradation). */
function emptyMetrics(): ComparisonMetrics {
  return {
    peak: null,
    weeksOnChart: 0,
    weeksAtNumberOne: 0,
    topTenWeeks: 0,
    firstDate: null,
    lastDate: null,
    activeEra: "",
  };
}

/** Build the "1991–2004" era label from first/last dates. */
function deriveActiveEra(firstDate: string | null, lastDate: string | null): string {
  const startYear = yearOf(firstDate);
  const endYear = yearOf(lastDate);
  if (startYear === null && endYear === null) {
    return "";
  }
  if (startYear !== null && endYear !== null) {
    return startYear === endYear ? `${startYear}` : `${startYear}–${endYear}`;
  }
  return `${startYear ?? endYear}`;
}

/**
 * Resolve a human display label from the entity's own table. The id column /
 * table are code constants keyed by the validated `kind`; the id binds as `$1`.
 * Returns `""` when the entity row is missing (no-throw degradation).
 */
async function resolveEntityLabel(kind: EntityKind, entityId: number): Promise<string> {
  const sql = getSql();
  let rows: Record<string, unknown>[] = [];
  if (kind === "artist") {
    rows = await sql.query(`SELECT name AS label FROM artists WHERE id = $1`, [entityId]);
  } else if (kind === "song") {
    rows = await sql.query(`SELECT title AS label FROM songs WHERE id = $1`, [entityId]);
  } else {
    rows = await sql.query(`SELECT title AS label FROM albums WHERE id = $1`, [entityId]);
  }
  return (rows[0]?.label as string | null) ?? "";
}

/**
 * Compute the five metric families for a single entity across ALL charts it
 * appears on, via `validWeeksForCharts` (which composes the canonical per-chart
 * `validWeeksCte` once per chart_id and UNIONs — preserving each chart's own
 * MIN(cw.id) first-real-week tie-break; NO single global MIN across charts).
 */
async function getEntityMetrics(kind: EntityKind, entityId: number): Promise<ComparisonEntity> {
  const sql = getSql();
  const idCol = ENTITY_ID_COLUMN[kind];

  // First resolve the chart set + label and the slugs (for the payload).
  const chartRows = await sql.query(
    `SELECT DISTINCT c.id AS chart_id, c.slug AS slug
     FROM chart_entries e
     JOIN charts c ON e.chart_id = c.id
     WHERE e.${idCol} = $1
     ORDER BY c.id`,
    [entityId],
  );
  const chartIds = chartRows.map((r) => r.chart_id as number);
  const slugs = chartRows.map((r) => r.slug as string);

  const label = await resolveEntityLabel(kind, entityId);

  if (chartIds.length === 0) {
    return { kind, id: entityId, label, charts: [], metrics: emptyMetrics() };
  }

  // Compose the per-chart valid-weeks UNION; bind chart ids first, then the
  // entity id at the next placeholder.
  const { cte, finalRelation, placeholders } = validWeeksForCharts(chartIds, 1);
  const entityPlaceholder = `$${placeholders.length + 1}`;

  const rows = await sql.query(
    `WITH ${cte}
     SELECT MIN(e.rank)                                AS peak,
            COUNT(*)::int                              AS weeks_on_chart,
            COUNT(*) FILTER (WHERE e.rank = 1)::int    AS weeks_at_number_one,
            COUNT(*) FILTER (WHERE e.rank <= 10)::int  AS top_ten_weeks,
            MIN(cw.chart_date)::text                   AS first_date,
            MAX(cw.chart_date)::text                   AS last_date
     FROM chart_entries e
     JOIN chart_weeks cw ON e.chart_week_id = cw.id
     WHERE e.${idCol} = ${entityPlaceholder}
       AND e.chart_week_id IN (SELECT id FROM ${finalRelation})`,
    [...chartIds, entityId],
  );

  const row = rows[0] ?? {};
  const firstDate = toIsoDate(row.first_date);
  const lastDate = toIsoDate(row.last_date);
  const peak = row.peak === null || row.peak === undefined ? null : Number(row.peak);

  const metrics: ComparisonMetrics = {
    peak,
    weeksOnChart: Number(row.weeks_on_chart ?? 0),
    weeksAtNumberOne: Number(row.weeks_at_number_one ?? 0),
    topTenWeeks: Number(row.top_ten_weeks ?? 0),
    firstDate,
    lastDate,
    activeEra: deriveActiveEra(firstDate, lastDate),
  };

  return { kind, id: entityId, label, charts: slugs, metrics };
}

/**
 * Compare two same-kind entities. The route enforces that both ids are
 * interpreted as the one `kind`. Each entity's metrics are era-labeled from its
 * OWN MIN/MAX chart_date so a cross-era comparison stays honest (Pitfall 1).
 */
export async function getEntityComparison(
  kind: EntityKind,
  leftId: number,
  rightId: number,
): Promise<ComparisonPayload> {
  const [left, right] = await Promise.all([
    getEntityMetrics(kind, leftId),
    getEntityMetrics(kind, rightId),
  ]);
  return { left, right, metricDefinitions: COMPARISON_METRIC_DEFINITIONS };
}

// ---------------------------------------------------------------------------
// ANALYTICS-02: presence by year
// ---------------------------------------------------------------------------

/** One {year, weeks} point in the presence-by-year series. */
export interface PresencePoint {
  year: number;
  /** COUNT of valid chart-week rows in that year (never the per-row counter). */
  weeks: number;
}

export interface PresencePayload {
  chart: string;
  entityKind: EntityKind;
  entityId: number;
  series: PresencePoint[];
}

/**
 * Presence-by-year for one entity on one chart: COUNT(*) of valid-week rows
 * GROUP BY year. The chart_id is bound as `$1` (also feeds the valid-weeks CTE),
 * the entity id as `$2`.
 */
export async function getPresenceByYear(
  chartId: number,
  chartSlug: string,
  entityKind: EntityKind,
  entityId: number,
): Promise<PresencePayload> {
  const sql = getSql();
  const idCol = ENTITY_ID_COLUMN[entityKind];

  const rows = await sql.query(
    `WITH ${validWeeksCte("valid_weeks", "$1")}
     SELECT EXTRACT(YEAR FROM cw.chart_date)::int AS year,
            COUNT(*)::int AS weeks
     FROM chart_entries e
     JOIN chart_weeks cw ON e.chart_week_id = cw.id
     WHERE e.chart_id = $1
       AND e.${idCol} = $2
       AND e.chart_week_id IN (SELECT id FROM valid_weeks)
     GROUP BY EXTRACT(YEAR FROM cw.chart_date)
     ORDER BY year`,
    [chartId, entityId],
  );

  const series: PresencePoint[] = rows.map((r) => ({
    year: Number(r.year ?? 0),
    weeks: Number(r.weeks ?? 0),
  }));

  return { chart: chartSlug, entityKind, entityId, series };
}
