/**
 * GET /api/data-status
 *
 * Returns aggregate row counts and latest chart dates for the data-status
 * indicator panel on the UI.
 *
 * Response shape:
 *   200: { counts, latestDates, chart_weeks, songs, albums, artists,
 *           hot100_entries, b200_entries }
 *   500: { error: string }
 *
 * Threat-model mitigation (TM-02-04):
 *   - Database errors are caught and returned as concise JSON; raw SQL and
 *     stack traces are never surfaced to the caller.
 */

import { getDataSummary } from "@/lib/data-status";

export async function GET(): Promise<Response> {
  try {
    const summary = await getDataSummary();

    return Response.json({
      counts: summary.counts,
      latestDates: summary.latestDates,
      chart_weeks: summary.chart_weeks,
      songs: summary.songs,
      albums: summary.albums,
      artists: summary.artists,
      hot100_entries: summary.hot100_entries,
      b200_entries: summary.b200_entries,
    });
  } catch {
    return Response.json(
      { error: "Failed to load data status. Please try again later." },
      { status: 500 },
    );
  }
}
