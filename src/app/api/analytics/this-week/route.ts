import { type NextRequest } from "next/server";

import { parseChartType, isValidISODate } from "@/lib/charts";
import { chartDepth } from "@/lib/chart-families";
import { resolveChart } from "@/lib/valid-weeks";
import { getThisWeekInHistory } from "@/lib/analytics";

const CACHE_CONTROL = "public, s-maxage=3600, stale-while-revalidate=86400";

function parsePositiveInteger(
  value: string | null,
  minimum = 1,
  maximum = Number.MAX_SAFE_INTEGER,
): number | null {
  if (!value || !/^\d+$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    return null;
  }
  return parsed;
}

/** Today's date as an ISO YYYY-MM-DD string (server-side default). */
function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * GET /api/analytics/this-week?chart=hot-100&date=2024-06-22&topN=10
 *
 * This-week-in-history for a chart. The slug is validated against the registry
 * and resolved BEFORE any query; the date (if supplied) must be a valid ISO
 * date, otherwise 400; topN is clamped to the chart depth (DoS bound). When
 * `date` is omitted, the server defaults to today. All values bind as $N.
 */
export async function GET(request: NextRequest): Promise<Response> {
  const { searchParams } = request.nextUrl;

  const chartSlug = await parseChartType(searchParams.get("chart"));
  if (!chartSlug) {
    return Response.json(
      { error: 'Invalid or missing "chart" parameter. Must be an active chart slug.' },
      { status: 400 },
    );
  }

  // Date: if supplied it MUST be a valid ISO date; if absent, default to today.
  const rawDate = searchParams.get("date");
  if (rawDate !== null && !isValidISODate(rawDate)) {
    return Response.json(
      { error: 'Invalid "date" parameter. Must be an ISO date (YYYY-MM-DD).' },
      { status: 400 },
    );
  }
  const date = rawDate ?? todayIso();

  // Clamp topN to the chart depth so an unbounded request cannot blow up the
  // result set (DoS bound); default to 10.
  const maxPosition = chartDepth(chartSlug);
  const topN = parsePositiveInteger(searchParams.get("topN"), 1, maxPosition) ?? 10;

  try {
    const chart = await resolveChart(chartSlug);
    if (!chart) {
      return Response.json(
        { error: 'Invalid or missing "chart" parameter. Must be an active chart slug.' },
        { status: 400 },
      );
    }
    const payload = await getThisWeekInHistory(
      chart.id,
      chart.slug,
      chart.entity_kind,
      date,
      topN,
    );
    return Response.json(payload, { headers: { "Cache-Control": CACHE_CONTROL } });
  } catch {
    return Response.json(
      { error: "Could not load analytics. Please try again later." },
      { status: 500 },
    );
  }
}
