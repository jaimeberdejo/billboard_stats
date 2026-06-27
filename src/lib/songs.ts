import { getSql } from "@/lib/db";
import { validWeeksForCharts } from "@/lib/valid-weeks";
import { genreFamily, type ChartFamily } from "@/lib/chart-families";

export interface DetailArtistLink {
  id: number;
  name: string;
  image_url: string | null;
}

export interface DetailChartRunPoint {
  chart_date: string;
  rank: number;
  last_pos: number | null;
  is_new: boolean;
  peak_pos: number | null;
  weeks_on_chart: number | null;
}

/**
 * One chart's worth of an entity's run, grouped from the polymorphic
 * chart_entries read. A song/album that charts on multiple charts yields one
 * group per chart, in the stable family/sort order. Single-chart entities yield
 * exactly one group (renders identically to the v1.0 single flat run).
 */
export interface ChartRunGroup {
  chartSlug: string;
  chartTitle: string;
  family: ChartFamily;
  /** Chart depth (rank count) used to parameterize the run-visualization y-axis. */
  depth: number;
  points: DetailChartRunPoint[];
}

export interface SongDetailPayload {
  song: {
    id: number;
    title: string;
    artist_credit: string;
    image_url: string | null;
  };
  stats: {
    song_id: number;
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
 * Group a flat ordered run-row result (already sorted by sort_order, chart_date)
 * into per-chart ChartRunGroup[]. Mirrors the Map-keyed grouping idiom in
 * records.ts (mapSimultaneousWeeks). Preserves first-seen chart order so the
 * incoming charts.sort_order ASC ordering carries through to the rendered
 * sequence. `depth` = max rank seen on the chart (a safe per-chart y-axis bound
 * derived from real data, never a hardcoded 100/200).
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
        chartTitle:
          (row.chart_title as string | null) ?? slug,
        family: genreFamily(slug, (row.chart_category as string | null) ?? null),
        depth: point.rank,
        points: [point],
      });
      continue;
    }

    existing.points.push(point);
    if (point.rank > existing.depth) {
      existing.depth = point.rank;
    }
  }

  return [...grouped.values()];
}

export async function getSongDetail(songId: number): Promise<SongDetailPayload | null> {
  if (!isPositiveInteger(songId)) {
    return null;
  }

  const sql = getSql();

  // Discover the charts this song touches (small N), then build a per-chart
  // valid-weeks union so EACH chart keeps its own MIN(cw.id) first-real-week
  // (CR-01 / Pitfall 2 — never a single cross-chart MIN).
  const chartIdRows = await sql.query(
    `SELECT DISTINCT cw.chart_id
     FROM chart_entries e
     JOIN chart_weeks cw ON e.chart_week_id = cw.id
     WHERE e.song_id = $1
       AND cw.chart_id IS NOT NULL`,
    [songId],
  );
  const chartIds = chartIdRows
    .map((r) => r.chart_id as number)
    .filter((id): id is number => typeof id === "number");

  const [songRows, statsRows, artistRows, chartRunRows] = await Promise.all([
    sql.query(
      `SELECT id, title, artist_credit, image_url
       FROM songs
       WHERE id = $1`,
      [songId],
    ),
    sql.query(
      `SELECT song_id,
              total_weeks,
              peak_position,
              weeks_at_peak,
              weeks_at_number_one,
              debut_date::text AS debut_date,
              last_date::text AS last_date,
              debut_position
       FROM song_stats
       WHERE song_id = $1`,
      [songId],
    ),
    sql.query(
      `SELECT a.id, a.name, a.image_url
       FROM song_artists sa
       JOIN artists a ON sa.artist_id = a.id
       WHERE sa.song_id = $1
       ORDER BY sa.role, a.name`,
      [songId],
    ),
    (async () => {
      if (chartIds.length === 0) {
        return [] as Record<string, unknown>[];
      }
      // chartIds occupy $1..$N (bound params); the song id is the last param.
      const vw = validWeeksForCharts(chartIds, 1);
      const songParamIndex = chartIds.length + 1;
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
         WHERE e.song_id = $${songParamIndex}
           AND e.chart_week_id IN (SELECT id FROM ${vw.finalRelation})
         ORDER BY c.sort_order ASC, cw.chart_date ASC`,
        [...chartIds, songId],
      );
    })(),
  ]);

  const songRow = songRows[0];
  if (!songRow) {
    return null;
  }

  const statsRow = statsRows[0];

  return {
    song: {
      id: songRow.id as number,
      title: songRow.title as string,
      artist_credit: songRow.artist_credit as string,
      image_url: (songRow.image_url as string | null) ?? null,
    },
    stats: statsRow
      ? {
          song_id: statsRow.song_id as number,
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
