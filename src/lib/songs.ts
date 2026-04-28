import { getSql } from "@/lib/db";

const VALID_HOT100_WEEKS_CTE = `
    phantom_hot100 AS (
        SELECT e.chart_week_id
        FROM hot100_entries e
        GROUP BY e.chart_week_id
        HAVING COUNT(*) FILTER (WHERE e.is_new = true AND e.weeks_on_chart = 1)
               >= COUNT(*) * 95 / 100
    ),
    first_real_hot100 AS (
        SELECT MIN(cw.id) AS id
        FROM phantom_hot100 ph
        JOIN chart_weeks cw ON ph.chart_week_id = cw.id
        WHERE cw.chart_type = 'hot-100'
    ),
    valid_hot100_weeks AS (
        SELECT cw.id
        FROM chart_weeks cw
        WHERE cw.chart_type = 'hot-100'
          AND (cw.id NOT IN (SELECT chart_week_id FROM phantom_hot100)
               OR cw.id = (SELECT id FROM first_real_hot100))
    )
`;

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
  chartRun: DetailChartRunPoint[];
  chartType: "hot-100";
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

export async function getSongDetail(songId: number): Promise<SongDetailPayload | null> {
  if (!isPositiveInteger(songId)) {
    return null;
  }

  const sql = getSql();

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
    sql.query(
      `WITH ${VALID_HOT100_WEEKS_CTE}
       SELECT cw.chart_date::text AS chart_date,
              e.rank,
              e.last_pos,
              e.is_new,
              e.peak_pos,
              e.weeks_on_chart
       FROM hot100_entries e
       JOIN chart_weeks cw ON e.chart_week_id = cw.id
       WHERE e.song_id = $1
         AND cw.id IN (SELECT id FROM valid_hot100_weeks)
       ORDER BY cw.chart_date ASC`,
      [songId],
    ),
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
    chartRun: chartRunRows.map((row) => ({
      chart_date: toIsoDate(row.chart_date) ?? "",
      rank: row.rank as number,
      last_pos: (row.last_pos as number | null) ?? null,
      is_new: row.is_new as boolean,
      peak_pos: (row.peak_pos as number | null) ?? null,
      weeks_on_chart: (row.weeks_on_chart as number | null) ?? null,
    })),
    chartType: "hot-100",
  };
}
