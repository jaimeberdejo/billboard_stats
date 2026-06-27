/**
 * Chart-week date-part SQL helpers — the SINGLE home of the chart-week rule.
 *
 * Billboard charts are dated to their Saturday issue date, so a `chart_date`
 * that belongs to a real chart week is always a Saturday (Postgres day-of-week
 * 6, where Sunday = 0). Before this module, that rule lived as a lone inline
 * `EXTRACT(DOW FROM chart_date) = 6` literal in data-status.ts. Centralizing it
 * here means data-status and the Phase 14 analytics queries share ONE definition
 * of "is a chart week" rather than each re-deriving the DOW literal.
 *
 * Two predicates live here:
 *   - `saturdayPredicate(col)` — the Saturday (chart-day) predicate text.
 *   - `isoWeekExpr(col)`       — the ISO week-of-year expression, used by the
 *     this-week-in-history same-week-across-years match (14-02).
 *
 * SECURITY: every returned string is a CODE CONSTANT. The only variability is
 * the `col` argument, which is a code-controlled SQL identifier (default
 * `"chart_date"`), NEVER user input. Callers must only ever pass a literal,
 * trusted column name — exactly as valid-weeks.ts documents for its constant
 * CTE text. There is nothing bound or interpolated from a request here.
 */

/**
 * Postgres predicate text asserting that `col` is a Saturday — Billboard's
 * chart issue day (day-of-week 6, Sunday = 0).
 *
 * Returns a code-constant predicate fragment (no leading `AND`/`WHERE`); compose
 * it into a query with `... AND ${saturdayPredicate("chart_date")}`.
 *
 * @param col Trusted, code-controlled column identifier (default `chart_date`).
 */
export function saturdayPredicate(col = "chart_date"): string {
  return `EXTRACT(DOW FROM ${col}) = 6`;
}

/**
 * Postgres expression for the ISO 8601 week-of-year of a date column.
 *
 * Returns a code-constant scalar expression; use it in a SELECT/WHERE to match
 * the same week across different years (the this-week-in-history query in
 * 14-02), e.g. `... WHERE ${isoWeekExpr("chart_date")} = ${isoWeekExpr("CURRENT_DATE")}`.
 *
 * @param col Trusted, code-controlled column identifier (default `chart_date`).
 */
export function isoWeekExpr(col = "chart_date"): string {
  return `EXTRACT(WEEK FROM ${col})`;
}
