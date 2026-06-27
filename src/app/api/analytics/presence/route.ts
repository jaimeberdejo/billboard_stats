import { type NextRequest } from "next/server";

import { parseChartType } from "@/lib/charts";
import { resolveChart } from "@/lib/valid-weeks";
import { getPresenceByYear, type EntityKind } from "@/lib/analytics";

const CACHE_CONTROL = "public, s-maxage=3600, stale-while-revalidate=86400";

const ENTITY_KIND_ALLOWLIST = new Set<EntityKind>(["artist", "song", "album"]);

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

function isValidEntityKind(value: string | null): value is EntityKind {
  return value !== null && ENTITY_KIND_ALLOWLIST.has(value as EntityKind);
}

/**
 * GET /api/analytics/presence?chart=hot-100&entityKind=song&id=1
 *
 * Presence-by-year for one entity on one chart. The slug is validated against
 * the registry (parseChartType) and resolved to its chart_id BEFORE any query;
 * entityKind via allowlist; id as a bounded positive int. All values bind as $N.
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

  const entityKind = searchParams.get("entityKind");
  if (!isValidEntityKind(entityKind)) {
    return Response.json(
      { error: 'Invalid or missing "entityKind" parameter. Must be artist, song, or album.' },
      { status: 400 },
    );
  }

  const id = parsePositiveInteger(searchParams.get("id"));
  if (!id) {
    return Response.json(
      { error: 'Invalid or missing "id" parameter. Must be a positive integer.' },
      { status: 400 },
    );
  }

  try {
    const chart = await resolveChart(chartSlug);
    if (!chart) {
      return Response.json(
        { error: 'Invalid or missing "chart" parameter. Must be an active chart slug.' },
        { status: 400 },
      );
    }
    const payload = await getPresenceByYear(chart.id, chart.slug, entityKind, id);
    return Response.json(payload, { headers: { "Cache-Control": CACHE_CONTROL } });
  } catch {
    return Response.json(
      { error: "Could not load analytics. Please try again later." },
      { status: 500 },
    );
  }
}
