/**
 * Shared parametric phantom-week helper (the keystone of the multi-chart cutover).
 *
 * SOURCE OF TRUTH — keep in lockstep with:
 *   billboard_stats/etl/stats_builder.py:79-144 (`valid_weeks_cte`)
 *
 * This module is the SINGLE place the frontend expresses the phantom-week rule.
 * It is a line-for-line translation of the Python `valid_weeks_cte` body. The
 * 15-01 cutover proved this parametric path selects the IDENTICAL weeks the
 * now-RETIRED v1.0 per-chart-type literal CTEs (`_VALID_HOT100_WEEKS_CTE` /
 * `_VALID_B200_WEEKS_CTE`, deleted in Phase 15) selected on the same data
 * (CR-01). The load-bearing invariants preserved here:
 *
 *   - Phantom rule: a week is phantom when >= 95% of THAT chart's `chart_entries`
 *     rows for the week have `is_new = true AND weeks_on_chart = 1`. Expressed in
 *     SQL as `COUNT(*) FILTER (...) >= COUNT(*) * 95 / 100` (integer division,
 *     matching the Python literal).
 *   - First-real-week tie-break: the earliest phantom week is kept as the real
 *     first chart, selected by the MINIMUM `chart_weeks.id` scoped to the bound
 *     chart — NOT by `ORDER BY chart_date`. Using the min id (rather than a
 *     date-ordered pick) guarantees the parametric path and the v1.0 path agree
 *     even when `chart_weeks.id` order != `chart_date` order (backfilled /
 *     re-ingested weeks inserted out of date order). CR-01: if a date-ordered
 *     tie-break is ever wanted, change BOTH the Python and this TS path together
 *     — never let two paths silently disagree on production data.
 *   - Keyed by `chart_id` (a bound parameter) over the polymorphic
 *     `chart_entries` table — NOT by a hardcoded `chart_type` literal. There is
 *     exactly ONE such CTE for ALL charts; Hot 100 and Billboard 200 are just two
 *     ordinary `chart_id` values.
 *
 * SECURITY: the returned text is a CODE CONSTANT, never derived from user input.
 * The ONLY bound value is the chart_id (a `$N` placeholder). Callers MUST bind
 * chart_id as a query parameter — never interpolate untrusted input into the SQL.
 */

import { getSql } from "@/lib/db";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChartRow {
  id: number;
  slug: string;
  title: string | null;
  entity_kind: "song" | "album" | "artist";
  category: string | null;
}

// ---------------------------------------------------------------------------
// Parametric CTE builder
// ---------------------------------------------------------------------------

/**
 * Return the SQL *body* of a parametric valid-weeks CTE keyed by `chart_id`.
 *
 * Line-for-line translation of `valid_weeks_cte` in stats_builder.py:108-144.
 * Produces a relation `<name>` with a single `id` column = the valid
 * `chart_week_id` values for the bound chart. The chart_id is bound ONCE via a
 * leading `bound_<name>` sub-CTE and referenced everywhere as
 * `(SELECT chart_id FROM bound_<name>)`, so the whole CTE takes EXACTLY ONE bind
 * parameter.
 *
 * The returned text is a CTE body (no leading `WITH`); compose it as
 * `WITH ${validWeeksCte()} SELECT ...` or chain after other CTEs with a leading
 * comma.
 *
 * @param name           CTE relation name to emit (default `valid_weeks`).
 * @param idPlaceholder  SQL placeholder for the bound chart_id (default `$1`).
 *                       The Python `%s` becomes this caller-supplied `$N` token.
 */
export function validWeeksCte(
  name = "valid_weeks",
  idPlaceholder = "$1",
): string {
  return `
    bound_${name} AS (
        SELECT ${idPlaceholder}::int AS chart_id
    ),
    phantom_${name} AS (
        SELECT e.chart_week_id
        FROM chart_entries e
        WHERE e.chart_id = (SELECT chart_id FROM bound_${name})
        GROUP BY e.chart_week_id
        HAVING COUNT(*) FILTER (WHERE e.is_new = true AND e.weeks_on_chart = 1)
               >= COUNT(*) * 95 / 100
    ),
    first_real_${name} AS (
        -- Pick the SAME "first real" week the v1.0 literal CTEs pick: MIN(cw.id)
        -- scoped to the bound chart. MIN(cw.id) — NOT ORDER BY chart_date —
        -- keeps the parametric and v1.0 paths byte-identical on the same data
        -- even when chart_weeks.id order != chart_date order (CR-01).
        SELECT MIN(cw.id) AS id
        FROM phantom_${name} ph
        JOIN chart_weeks cw ON ph.chart_week_id = cw.id
        WHERE cw.chart_id = (SELECT chart_id FROM bound_${name})
    ),
    ${name} AS (
        SELECT DISTINCT e.chart_week_id AS id
        FROM chart_entries e
        WHERE e.chart_id = (SELECT chart_id FROM bound_${name})
          AND (e.chart_week_id NOT IN (SELECT chart_week_id FROM phantom_${name})
               OR e.chart_week_id = (SELECT id FROM first_real_${name}))
    )
`;
}

/**
 * Compose a multi-chart valid-weeks CTE for the (few) charts an entity touches.
 *
 * CR-01 (Pitfall 2): this MUST NOT collapse into a single cross-chart phantom
 * subquery that takes one global `MIN(cw.id)` across all charts — that would
 * select the wrong first-real week per chart. Instead it COMPOSES the canonical
 * single-chart `validWeeksCte` once per chart_id and UNIONs the per-chart
 * relations, so each chart keeps its own per-chart `MIN(cw.id)` first-real-week
 * tie-break. The emitted SQL therefore provably inherits the same `MIN(cw.id)`
 * rule as the single-chart path (one bound param per chart).
 *
 * Returns `{ cte, finalRelation, placeholders }`:
 *   - `cte`            : the full CTE body (no leading `WITH`).
 *   - `finalRelation`  : the name of the unioned relation with a single `id`
 *                        column = valid chart_week_ids across all charts.
 *   - `placeholders`   : the ordered `$N` bind tokens (one chart_id per chart).
 *
 * Bind the chartIds (in order) as query params; the CTE text is a code constant.
 *
 * @param chartIds  Small set of chart_id values (already resolved + validated).
 * @param startIndex 1-based index of the first `$N` placeholder (default 1).
 */
export function validWeeksForCharts(
  chartIds: number[],
  startIndex = 1,
): { cte: string; finalRelation: string; placeholders: string[] } {
  if (chartIds.length === 0) {
    // Empty union still yields an id column so callers can `IN (SELECT id ...)`.
    return {
      cte: `
    valid_weeks_all AS (
        SELECT NULL::int AS id WHERE false
    )
`,
      finalRelation: "valid_weeks_all",
      placeholders: [],
    };
  }

  const placeholders: string[] = [];
  const perChartBodies: string[] = [];
  const unionSelects: string[] = [];

  chartIds.forEach((_chartId, i) => {
    const placeholder = `$${startIndex + i}`;
    placeholders.push(placeholder);
    const relName = `valid_weeks_${i}`;
    // COMPOSE the canonical single-chart rule per chart_id — this is what keeps
    // the per-chart MIN(cw.id) first-real-week tie-break in the emitted SQL.
    perChartBodies.push(validWeeksCte(relName, placeholder).trim());
    unionSelects.push(`        SELECT id FROM ${relName}`);
  });

  const cte = `
    ${perChartBodies.join(",\n    ")},
    valid_weeks_all AS (
${unionSelects.join("\n        UNION\n")}
    )
`;

  return { cte, finalRelation: "valid_weeks_all", placeholders };
}

// ---------------------------------------------------------------------------
// Registry resolution (slug -> chart_id)
// ---------------------------------------------------------------------------

/**
 * Resolve a chart slug to its registry row, or null if no such chart.
 *
 * SECURITY (T-13-01): the slug is bound as `$1` (never interpolated). Callers
 * should still validate the slug against the active registry before use, but
 * this parameterized lookup is itself injection-safe.
 */
export async function resolveChart(slug: string): Promise<ChartRow | null> {
  const sql = getSql();
  const rows = await sql.query(
    `SELECT id, slug, title, entity_kind, category
     FROM charts
     WHERE slug = $1`,
    [slug],
  );
  if (rows.length === 0) {
    return null;
  }
  const r = rows[0];
  return {
    id: r.id as number,
    slug: r.slug as string,
    title: (r.title as string | null) ?? null,
    entity_kind: r.entity_kind as "song" | "album" | "artist",
    category: (r.category as string | null) ?? null,
  };
}

/** Resolve a chart slug to just its chart_id, or null. */
export async function resolveChartId(slug: string): Promise<number | null> {
  const chart = await resolveChart(slug);
  return chart ? chart.id : null;
}
