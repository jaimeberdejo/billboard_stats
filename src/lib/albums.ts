import { getSql } from "@/lib/db";
import { validWeeksForCharts } from "@/lib/valid-weeks";
import { chartDepth, genreFamily } from "@/lib/chart-families";
import type {
  ChartRunGroup,
  DetailArtistLink,
  DetailChartRunPoint,
} from "@/lib/songs";

export type { ChartRunGroup, DetailArtistLink, DetailChartRunPoint };

export interface AlbumDetailPayload {
  album: {
    id: number;
    title: string;
    artist_credit: string;
    image_url: string | null;
  };
  stats: {
    album_id: number;
    total_weeks: number;
    peak_position: number | null;
    weeks_at_peak: number;
    weeks_at_number_one: number;
    debut_date: string | null;
    last_date: string | null;
    debut_position: number | null;
  } | null;
  artists: DetailArtistLink[];
  runsByChart: ChartRunGroup[];
}

function isPositiveInteger(value: number): boolean {
  return Number.isInteger(value) && value > 0;
}

function toIsoDate(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }
  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }
  return null;
}

/**
 * Group a flat ordered run-row result (sorted by sort_order, chart_date) into
 * per-chart ChartRunGroup[] — symmetric to songs.ts groupRunsByChart. `depth` =
 * max rank seen on the chart (per-chart y-axis bound from real data).
 */
function groupRunsByChart(rows: Record<string, unknown>[]): ChartRunGroup[] {
  const grouped = new Map<number, ChartRunGroup>();

  for (const row of rows) {
    const chartId = row.chart_id as number;
    const point: DetailChartRunPoint = {
      chart_date: toIsoDate(row.chart_date) ?? "",
      rank: row.rank as number,
      last_pos: (row.last_pos as number | null) ?? null,
      is_new: row.is_new as boolean,
      peak_pos: (row.peak_pos as number | null) ?? null,
      weeks_on_chart: (row.weeks_on_chart as number | null) ?? null,
    };

    const existing = grouped.get(chartId);
    if (!existing) {
      const slug = row.chart_slug as string;
      grouped.set(chartId, {
        chartSlug: slug,
        chartTitle: (row.chart_title as string | null) ?? slug,
        family: genreFamily(slug, (row.chart_category as string | null) ?? null),
        depth: chartDepth(slug),
        points: [point],
      });
      continue;
    }

    existing.points.push(point);
  }

  return [...grouped.values()];
}

export async function getAlbumDetail(
  albumId: number,
): Promise<AlbumDetailPayload | null> {
  if (!isPositiveInteger(albumId)) {
    return null;
  }

  const sql = getSql();

  // Charts this album touches (small N), then a per-chart valid-weeks union so
  // EACH chart keeps its own MIN(cw.id) first-real-week (CR-01 / Pitfall 2).
  const chartIdRows = await sql.query(
    `SELECT DISTINCT cw.chart_id
     FROM chart_entries e
     JOIN chart_weeks cw ON e.chart_week_id = cw.id
     WHERE e.album_id = $1
       AND cw.chart_id IS NOT NULL`,
    [albumId],
  );
  const chartIds = chartIdRows
    .map((r) => r.chart_id as number)
    .filter((id): id is number => typeof id === "number");

  const [albumRows, statsRows, artistRows, chartRunRows] = await Promise.all([
    sql.query(
      `SELECT id, title, artist_credit, image_url
       FROM albums
       WHERE id = $1`,
      [albumId],
    ),
    sql.query(
      `SELECT album_id,
              total_weeks,
              peak_position,
              weeks_at_peak,
              weeks_at_number_one,
              debut_date::text AS debut_date,
              last_date::text AS last_date,
              debut_position
       FROM album_stats
       WHERE album_id = $1`,
      [albumId],
    ),
    sql.query(
      `SELECT a.id, a.name, a.image_url
       FROM album_artists aa
       JOIN artists a ON aa.artist_id = a.id
       WHERE aa.album_id = $1
       ORDER BY aa.role, a.name`,
      [albumId],
    ),
    (async () => {
      if (chartIds.length === 0) {
        return [] as Record<string, unknown>[];
      }
      const vw = validWeeksForCharts(chartIds, 1);
      const albumParamIndex = chartIds.length + 1;
      return sql.query(
        `WITH ${vw.cte}
         SELECT c.sort_order AS sort_order,
                c.id AS chart_id,
                c.slug AS chart_slug,
                c.title AS chart_title,
                c.category AS chart_category,
                cw.chart_date::text AS chart_date,
                e.rank,
                e.last_pos,
                e.is_new,
                e.peak_pos,
                e.weeks_on_chart
         FROM chart_entries e
         JOIN chart_weeks cw ON e.chart_week_id = cw.id
         JOIN charts c ON cw.chart_id = c.id
         WHERE e.album_id = $${albumParamIndex}
           AND e.chart_week_id IN (SELECT id FROM ${vw.finalRelation})
         ORDER BY c.sort_order ASC, cw.chart_date ASC`,
        [...chartIds, albumId],
      );
    })(),
  ]);

  const albumRow = albumRows[0];
  if (!albumRow) {
    return null;
  }

  const statsRow = statsRows[0];

  return {
    album: {
      id: albumRow.id as number,
      title: albumRow.title as string,
      artist_credit: albumRow.artist_credit as string,
      image_url: (albumRow.image_url as string | null) ?? null,
    },
    stats: statsRow
      ? {
          album_id: statsRow.album_id as number,
          total_weeks: (statsRow.total_weeks as number) ?? 0,
          peak_position: (statsRow.peak_position as number | null) ?? null,
          weeks_at_peak: (statsRow.weeks_at_peak as number) ?? 0,
          weeks_at_number_one: (statsRow.weeks_at_number_one as number) ?? 0,
          debut_date: toIsoDate(statsRow.debut_date),
          last_date: toIsoDate(statsRow.last_date),
          debut_position: (statsRow.debut_position as number | null) ?? null,
        }
      : null,
    artists: artistRows.map((row) => ({
      id: row.id as number,
      name: row.name as string,
      image_url: (row.image_url as string | null) ?? null,
    })),
    runsByChart: groupRunsByChart(chartRunRows),
  };
}
