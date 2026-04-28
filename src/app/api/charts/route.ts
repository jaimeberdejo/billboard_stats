/**
 * GET /api/charts
 *
 * Query parameters:
 *   chart  - "hot-100" or "billboard-200" (required)
 *   date   - ISO date YYYY-MM-DD (optional; defaults to latest available)
 *
 * Response shape:
 *   200: { chartType, selectedDate, latestDate, availableDates, entries }
 *   400: { error: string }
 *   500: { error: string }
 *
 * Threat-model mitigations (TM-02-03, TM-02-04):
 *   - chart is validated against the "hot-100"|"billboard-200" allowlist before
 *     any DB call.
 *   - date is validated as YYYY-MM-DD regex before passing to the SQL helper.
 *   - Errors returned as concise JSON; raw SQL and stack traces are never
 *     surfaced to the caller.
 */

import { type NextRequest } from "next/server";
import { getChartSnapshot, parseChartType, isValidISODate } from "@/lib/charts";

export async function GET(request: NextRequest): Promise<Response> {
  const { searchParams } = request.nextUrl;

  // --- Input validation ---

  const rawChart = searchParams.get("chart");
  const chartType = parseChartType(rawChart);

  if (!chartType) {
    return Response.json(
      { error: 'Invalid or missing "chart" parameter. Must be "hot-100" or "billboard-200".' },
      { status: 400 },
    );
  }

  const rawDate = searchParams.get("date");
  if (rawDate !== null && !isValidISODate(rawDate)) {
    return Response.json(
      { error: 'Invalid "date" parameter. Must be a date in YYYY-MM-DD format.' },
      { status: 400 },
    );
  }

  // --- Fetch data ---

  try {
    const snapshot = await getChartSnapshot(
      chartType,
      rawDate ?? undefined,
    );

    return Response.json({
      chartType: snapshot.chartType,
      selectedDate: snapshot.selectedDate,
      latestDate: snapshot.latestDate,
      availableDates: snapshot.availableDates,
      entries: snapshot.entries,
    });
  } catch {
    return Response.json(
      { error: "Failed to load chart data. Please try again later." },
      { status: 500 },
    );
  }
}
