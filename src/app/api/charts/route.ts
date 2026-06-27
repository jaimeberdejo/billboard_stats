/**
 * GET /api/charts
 *
 * Query parameters:
 *   chart  - an active chart slug from the registry (required)
 *   date   - ISO date YYYY-MM-DD (optional; defaults to latest available)
 *
 * Response shape:
 *   200: { chartType, selectedDate, latestDate, availableDates, previousDate, nextDate, entries }
 *   400: { error: string }
 *   500: { error: string }
 *
 * Threat-model mitigations (TM-02-03, TM-02-04):
 *   - chart is validated against the active charts registry (parseChartType
 *     resolves the slug via a parameterized lookup) before any chart query keys
 *     on it.
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
  const chartType = await parseChartType(rawChart);

  if (!chartType) {
    return Response.json(
      { error: "Invalid or missing chart parameter." },
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

    // Historical dates are immutable; latest chart changes weekly.
    const cacheControl = rawDate
      ? "public, s-maxage=31536000, immutable"
      : "public, s-maxage=3600, stale-while-revalidate=86400";

    return Response.json(
      {
        chartType: snapshot.chartType,
        selectedDate: snapshot.selectedDate,
        latestDate: snapshot.latestDate,
        availableDates: snapshot.availableDates,
        previousDate: snapshot.previousDate,
        nextDate: snapshot.nextDate,
        entries: snapshot.entries,
      },
      { headers: { "Cache-Control": cacheControl } },
    );
  } catch {
    return Response.json(
      { error: "Failed to load chart data. Please try again later." },
      { status: 500 },
    );
  }
}
