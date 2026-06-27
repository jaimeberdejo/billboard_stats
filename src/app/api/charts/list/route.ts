/**
 * GET /api/charts/list
 *
 * Returns the active chart registry rows for the selector and two-level nav,
 * each tagged with its derived genre family.
 *
 * Response shape:
 *   200: { charts: ChartRegistryRow[] }
 *   500: { error: string }
 *
 * Threat-model mitigations:
 *   - T-13-03: errors returned as concise JSON; raw SQL / stack traces are never
 *     surfaced.
 *   - T-13-04: read-only public endpoint over a tiny static registry table;
 *     long s-maxage cache caps origin load.
 */

import { listActiveCharts } from "@/lib/charts";

export async function GET(): Promise<Response> {
  try {
    const charts = await listActiveCharts();
    return Response.json(
      { charts },
      {
        headers: {
          "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
        },
      },
    );
  } catch {
    return Response.json(
      { error: "Failed to load chart list." },
      { status: 500 },
    );
  }
}
