import { type ChartType } from "@/lib/charts";
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

const VALID_B200_WEEKS_CTE = `
    phantom_b200 AS (
        SELECT e.chart_week_id
        FROM b200_entries e
        GROUP BY e.chart_week_id
        HAVING COUNT(*) FILTER (WHERE e.is_new = true AND e.weeks_on_chart = 1)
               >= COUNT(*) * 95 / 100
    ),
    first_real_b200 AS (
        SELECT MIN(cw.id) AS id
        FROM phantom_b200 ph
        JOIN chart_weeks cw ON ph.chart_week_id = cw.id
        WHERE cw.chart_type = 'billboard-200'
    ),
    valid_b200_weeks AS (
        SELECT cw.id
        FROM chart_weeks cw
        WHERE cw.chart_type = 'billboard-200'
          AND (cw.id NOT IN (SELECT chart_week_id FROM phantom_b200)
               OR cw.id = (SELECT id FROM first_real_b200))
    )
`;

export type RecordPreset =
  | "most-weeks-at-number-one"
  | "longest-chart-runs"
  | "most-top-10-weeks"
  | "most-number-one-songs-by-artist"
  | "most-number-one-albums-by-artist"
  | "most-entries-by-artist"
  | "most-total-chart-weeks-by-artist"
  | "most-simultaneous-entries";

export type CustomRankBy =
  | "weeks-at-number-one"
  | "total-weeks"
  | "weeks-at-position"
  | "weeks-in-top-n"
  | "most-entries"
  | "number-one-entries";

export type CustomEntity = "songs" | "albums" | "artists";

export interface RecordLeaderboardRow {
  rank: number;
  title: string;
  artist_credit: string;
  value: number;
  song_id: number | null;
  album_id: number | null;
  artist_id: number | null;
  chart_date: string | null;
}

export interface RecordDrilldownRow {
  rank: number;
  title: string;
  artist_credit: string;
  value: number;
  song_id: number | null;
  album_id: number | null;
}

export interface SimultaneousDrilldownWeek {
  chart_date: string;
  value: number;
  rows: RecordDrilldownRow[];
}

export interface PresetRecordsPayload {
  mode: "preset";
  record: RecordPreset;
  chart: ChartType;
  valueLabel: string;
  supportsDrilldown: boolean;
  unsupportedMessage: string | null;
  rows: RecordLeaderboardRow[];
}

export interface CustomRecordsInput {
  entity: CustomEntity;
  chart: ChartType;
  rankBy: CustomRankBy;
  rankByParam: number;
  sortDir?: "asc" | "desc";
  limit?: number;
  peakMin?: number | null;
  peakMax?: number | null;
  weeksMin?: number | null;
  debutPosMin?: number | null;
  debutPosMax?: number | null;
  artistNames?: string[] | null;
}

export interface CustomRecordsPayload {
  mode: "custom";
  entity: CustomEntity;
  chart: ChartType;
  valueLabel: string;
  rows: RecordLeaderboardRow[];
}

export interface DrilldownPayload {
  mode: "drilldown";
  record: RecordPreset;
  chart: ChartType;
  artistId: number;
  artistName: string | null;
  chartDate?: string | null;
  valueLabel: string;
  unsupportedMessage: string | null;
  rows: RecordDrilldownRow[];
  weeks?: SimultaneousDrilldownWeek[];
}

const PRESET_VALUE_LABELS: Record<RecordPreset, string> = {
  "most-weeks-at-number-one": "Wks #1",
  "longest-chart-runs": "Total Wks",
  "most-top-10-weeks": "Top 10 Wks",
  "most-number-one-songs-by-artist": "#1 Songs",
  "most-number-one-albums-by-artist": "#1 Albums",
  "most-entries-by-artist": "Entries",
  "most-total-chart-weeks-by-artist": "Total Wks",
  "most-simultaneous-entries": "Simult.",
};

const DRILLDOWN_VALUE_LABELS: Partial<Record<RecordPreset, string>> = {
  "most-number-one-songs-by-artist": "Wks #1",
  "most-number-one-albums-by-artist": "Wks #1",
  "most-entries-by-artist": "Total Wks",
  "most-total-chart-weeks-by-artist": "Total Wks",
  "most-simultaneous-entries": "Position",
};

function toIsoDate(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }
  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }
  return null;
}

function mapRows(rows: Record<string, unknown>[]): RecordLeaderboardRow[] {
  return rows.map((row, index) => ({
    rank: index + 1,
    title: row.title as string,
    artist_credit: row.artist_credit as string,
    value: Number(row.value ?? 0),
    song_id: (row.song_id as number | null) ?? null,
    album_id: (row.album_id as number | null) ?? null,
    artist_id: (row.artist_id as number | null) ?? null,
    chart_date: toIsoDate(row.chart_date),
  }));
}

function mapDrilldownRows(rows: Record<string, unknown>[]): RecordDrilldownRow[] {
  return rows.map((row, index) => ({
    rank: index + 1,
    title: row.title as string,
    artist_credit: row.artist_credit as string,
    value: Number(row.value ?? 0),
    song_id: (row.song_id as number | null) ?? null,
    album_id: (row.album_id as number | null) ?? null,
  }));
}

function mapSimultaneousWeeks(
  rows: Record<string, unknown>[],
): SimultaneousDrilldownWeek[] {
  const grouped = new Map<
    string,
    {
      chart_date: string;
      value: number;
      rows: RecordDrilldownRow[];
    }
  >();

  for (const row of rows) {
    const chartDate = toIsoDate(row.chart_date);
    if (!chartDate) {
      continue;
    }

    const existing = grouped.get(chartDate);
    const nextEntry: RecordDrilldownRow = {
      rank: Number(row.entry_rank ?? 0),
      title: row.title as string,
      artist_credit: row.artist_credit as string,
      value: Number(row.entry_rank ?? 0),
      song_id: (row.song_id as number | null) ?? null,
      album_id: (row.album_id as number | null) ?? null,
    };

    if (!existing) {
      grouped.set(chartDate, {
        chart_date: chartDate,
        value: Number(row.week_value ?? 0),
        rows: [nextEntry],
      });
      continue;
    }

    existing.rows.push(nextEntry);
  }

  return [...grouped.values()].map((week) => ({
    chart_date: week.chart_date,
    value: week.value,
    rows: week.rows
      .sort((left, right) => left.rank - right.rank)
      .map((row, index) => ({ ...row, rank: index + 1 })),
  }));
}

function getUnsupportedMessage(
  record: RecordPreset,
  chart: ChartType,
): string | null {
  if (record === "most-simultaneous-entries" && chart === "billboard-200") {
    return "This record is only tracked for the Hot 100.";
  }
  if (record === "most-number-one-songs-by-artist" && chart === "billboard-200") {
    return "This record is only available for the Hot 100.";
  }
  if (record === "most-number-one-albums-by-artist" && chart === "hot-100") {
    return "This record is only available for the Billboard 200.";
  }
  return null;
}

async function getArtistName(artistId: number): Promise<string | null> {
  const sql = getSql();
  const rows = await sql.query(
    `SELECT name
     FROM artists
     WHERE id = $1`,
    [artistId],
  );
  const row = rows[0];
  return row ? (row.name as string) : null;
}

export async function getPresetRecords(
  record: RecordPreset,
  chart: ChartType,
  limit = 50,
): Promise<PresetRecordsPayload> {
  const unsupportedMessage = getUnsupportedMessage(record, chart);
  if (unsupportedMessage) {
    return {
      mode: "preset",
      record,
      chart,
      valueLabel: PRESET_VALUE_LABELS[record],
      supportsDrilldown: record in DRILLDOWN_VALUE_LABELS,
      unsupportedMessage,
      rows: [],
    };
  }

  const sql = getSql();
  let rows: Record<string, unknown>[] = [];

  switch (record) {
    case "most-weeks-at-number-one":
      if (chart === "hot-100") {
        rows = await sql.query(
          `SELECT s.title, s.artist_credit, ss.weeks_at_number_one AS value, s.id AS song_id
           FROM song_stats ss
           JOIN songs s ON ss.song_id = s.id
           WHERE ss.weeks_at_number_one > 0
           ORDER BY ss.weeks_at_number_one DESC, s.title
           LIMIT $1`,
          [limit],
        );
      } else {
        rows = await sql.query(
          `SELECT a.title, a.artist_credit, als.weeks_at_number_one AS value, a.id AS album_id
           FROM album_stats als
           JOIN albums a ON als.album_id = a.id
           WHERE als.weeks_at_number_one > 0
           ORDER BY als.weeks_at_number_one DESC, a.title
           LIMIT $1`,
          [limit],
        );
      }
      break;
    case "longest-chart-runs":
      if (chart === "hot-100") {
        rows = await sql.query(
          `SELECT s.title, s.artist_credit, ss.total_weeks AS value, s.id AS song_id
           FROM song_stats ss
           JOIN songs s ON ss.song_id = s.id
           ORDER BY ss.total_weeks DESC, s.title
           LIMIT $1`,
          [limit],
        );
      } else {
        rows = await sql.query(
          `SELECT a.title, a.artist_credit, als.total_weeks AS value, a.id AS album_id
           FROM album_stats als
           JOIN albums a ON als.album_id = a.id
           ORDER BY als.total_weeks DESC, a.title
           LIMIT $1`,
          [limit],
        );
      }
      break;
    case "most-top-10-weeks":
      if (chart === "hot-100") {
        rows = await sql.query(
          `WITH ${VALID_HOT100_WEEKS_CTE}
           SELECT s.title, s.artist_credit, COUNT(*) AS value, s.id AS song_id
           FROM hot100_entries e
           JOIN songs s ON e.song_id = s.id
           WHERE e.chart_week_id IN (SELECT id FROM valid_hot100_weeks)
             AND e.rank <= 10
           GROUP BY s.id, s.title, s.artist_credit
           ORDER BY value DESC, s.title
           LIMIT $1`,
          [limit],
        );
      } else {
        rows = await sql.query(
          `WITH ${VALID_B200_WEEKS_CTE}
           SELECT a.title, a.artist_credit, COUNT(*) AS value, a.id AS album_id
           FROM b200_entries e
           JOIN albums a ON e.album_id = a.id
           WHERE e.chart_week_id IN (SELECT id FROM valid_b200_weeks)
             AND e.rank <= 10
           GROUP BY a.id, a.title, a.artist_credit
           ORDER BY value DESC, a.title
           LIMIT $1`,
          [limit],
        );
      }
      break;
    case "most-number-one-songs-by-artist":
      rows = await sql.query(
        `SELECT a.name AS title, a.name AS artist_credit,
                COUNT(DISTINCT ss.song_id) AS value, a.id AS artist_id
         FROM song_stats ss
         JOIN song_artists sa ON ss.song_id = sa.song_id
         JOIN artists a ON sa.artist_id = a.id
         WHERE ss.weeks_at_number_one > 0
         GROUP BY a.id, a.name
         ORDER BY value DESC, a.name
         LIMIT $1`,
        [limit],
      );
      break;
    case "most-number-one-albums-by-artist":
      rows = await sql.query(
        `SELECT a.name AS title, a.name AS artist_credit,
                COUNT(DISTINCT als.album_id) AS value, a.id AS artist_id
         FROM album_stats als
         JOIN album_artists aa ON als.album_id = aa.album_id
         JOIN artists a ON aa.artist_id = a.id
         WHERE als.weeks_at_number_one > 0
         GROUP BY a.id, a.name
         ORDER BY value DESC, a.name
         LIMIT $1`,
        [limit],
      );
      break;
    case "most-entries-by-artist":
      if (chart === "hot-100") {
        rows = await sql.query(
          `SELECT a.name AS title, a.name AS artist_credit,
                  ast.total_hot100_songs AS value, a.id AS artist_id
           FROM artist_stats ast
           JOIN artists a ON ast.artist_id = a.id
           WHERE ast.total_hot100_songs > 0
           ORDER BY ast.total_hot100_songs DESC, a.name
           LIMIT $1`,
          [limit],
        );
      } else {
        rows = await sql.query(
          `SELECT a.name AS title, a.name AS artist_credit,
                  ast.total_b200_albums AS value, a.id AS artist_id
           FROM artist_stats ast
           JOIN artists a ON ast.artist_id = a.id
           WHERE ast.total_b200_albums > 0
           ORDER BY ast.total_b200_albums DESC, a.name
           LIMIT $1`,
          [limit],
        );
      }
      break;
    case "most-total-chart-weeks-by-artist":
      if (chart === "hot-100") {
        rows = await sql.query(
          `SELECT a.name AS title, a.name AS artist_credit,
                  ast.total_hot100_weeks AS value, a.id AS artist_id
           FROM artist_stats ast
           JOIN artists a ON ast.artist_id = a.id
           WHERE ast.total_hot100_weeks > 0
           ORDER BY ast.total_hot100_weeks DESC, a.name
           LIMIT $1`,
          [limit],
        );
      } else {
        rows = await sql.query(
          `SELECT a.name AS title, a.name AS artist_credit,
                  ast.total_b200_weeks AS value, a.id AS artist_id
           FROM artist_stats ast
           JOIN artists a ON ast.artist_id = a.id
           WHERE ast.total_b200_weeks > 0
           ORDER BY ast.total_b200_weeks DESC, a.name
           LIMIT $1`,
          [limit],
        );
      }
      break;
    case "most-simultaneous-entries":
      rows = await sql.query(
        `WITH ${VALID_HOT100_WEEKS_CTE},
         artist_week_counts AS (
           SELECT sa.artist_id, e.chart_week_id, COUNT(*) AS cnt
           FROM hot100_entries e
           JOIN song_artists sa ON e.song_id = sa.song_id
           WHERE e.chart_week_id IN (SELECT id FROM valid_hot100_weeks)
           GROUP BY sa.artist_id, e.chart_week_id
         )
         SELECT a.name AS title, a.name AS artist_credit,
                awc.cnt AS value, a.id AS artist_id, cw.chart_date::text AS chart_date
         FROM artist_week_counts awc
         JOIN artists a ON awc.artist_id = a.id
         JOIN chart_weeks cw ON awc.chart_week_id = cw.id
         ORDER BY awc.cnt DESC, cw.chart_date DESC, a.name
         LIMIT $1`,
        [limit],
      );
      break;
  }

  return {
    mode: "preset",
    record,
    chart,
    valueLabel: PRESET_VALUE_LABELS[record],
    supportsDrilldown: record in DRILLDOWN_VALUE_LABELS,
    unsupportedMessage: null,
    rows: mapRows(rows),
  };
}

export async function getCustomRecords(
  input: CustomRecordsInput,
): Promise<CustomRecordsPayload> {
  const {
    entity,
    chart,
    rankBy,
    rankByParam,
    sortDir = "desc",
    limit = 50,
    peakMin,
    peakMax,
    weeksMin,
    debutPosMin,
    debutPosMax,
    artistNames,
  } = input;

  const sql = getSql();
  const isHot100 = chart === "hot-100";
  const entryTable = isHot100 ? "hot100_entries" : "b200_entries";
  const itemTable = isHot100 ? "songs" : "albums";
  const statsTable = isHot100 ? "song_stats" : "album_stats";
  const idCol = isHot100 ? "song_id" : "album_id";
  const validWeeksCte = isHot100 ? VALID_HOT100_WEEKS_CTE : VALID_B200_WEEKS_CTE;
  const validWeeksTable = isHot100 ? "valid_hot100_weeks" : "valid_b200_weeks";
  const orderDir = sortDir === "asc" ? "ASC" : "DESC";

  let rows: Record<string, unknown>[] = [];
  let valueLabel = "Value";

  const buildFilters = (placeholderOffset = 0) => {
    const params: Array<string | number> = [];
    const filters: string[] = [];
    const placeholder = () => `$${placeholderOffset + params.length + 1}`;

    if (artistNames && artistNames.length > 0) {
      const artistValues = artistNames.map((name) => `%${name}%`);
      const artistClause = artistValues.map(() => `i.artist_credit ILIKE ${placeholder()}`);
      filters.push(`(${artistClause.join(" OR ")})`);
      params.push(...artistValues);
    }
    if (peakMin != null) {
      filters.push(`st.peak_position >= ${placeholder()}`);
      params.push(peakMin);
    }
    if (peakMax != null) {
      filters.push(`st.peak_position <= ${placeholder()}`);
      params.push(peakMax);
    }
    if (weeksMin != null) {
      filters.push(`st.total_weeks >= ${placeholder()}`);
      params.push(weeksMin);
    }
    if (debutPosMin != null) {
      filters.push(`st.debut_position >= ${placeholder()}`);
      params.push(debutPosMin);
    }
    if (debutPosMax != null) {
      filters.push(`st.debut_position <= ${placeholder()}`);
      params.push(debutPosMax);
    }

    return {
      params,
      filterSql: filters.length > 0 ? ` AND ${filters.join(" AND ")}` : "",
    };
  };

  if (entity === "artists") {
    const params: Array<string | number> = [];
    const filters: string[] = [];

    if (artistNames && artistNames.length > 0) {
      const artistValues = artistNames.map((name) => `%${name}%`);
      const artistClause = artistValues.map((_, index) => `a.name ILIKE $${index + 1}`);
      filters.push(`(${artistClause.join(" OR ")})`);
      params.push(...artistValues);
    }
    if (weeksMin != null) {
      filters.push(
        `${isHot100 ? "ast.total_hot100_weeks" : "ast.total_b200_weeks"} >= $${params.length + 1}`,
      );
      params.push(weeksMin);
    }

    let valueSql = "";
    if (rankBy === "total-weeks") {
      valueLabel = "Total Wks";
      valueSql = isHot100 ? "ast.total_hot100_weeks" : "ast.total_b200_weeks";
      filters.push(`${valueSql} > 0`);
    } else if (rankBy === "most-entries") {
      valueLabel = "Entries";
      valueSql = isHot100 ? "ast.total_hot100_songs" : "ast.total_b200_albums";
      filters.push(`${valueSql} > 0`);
    } else {
      valueLabel = isHot100 ? "#1 Songs" : "#1 Albums";
      valueSql = isHot100 ? "ast.hot100_number_ones" : "ast.b200_number_ones";
      filters.push(`${valueSql} > 0`);
    }

    const filterSql = filters.length > 0 ? `WHERE ${filters.join(" AND ")}` : "";
    params.push(limit);
    rows = await sql.query(
      `SELECT a.name AS title,
              a.name AS artist_credit,
              ${valueSql} AS value,
              a.id AS artist_id
       FROM artist_stats ast
       JOIN artists a ON ast.artist_id = a.id
       ${filterSql}
       ORDER BY ${valueSql} ${orderDir}, a.name
       LIMIT $${params.length}`,
      params,
    );
  } else if (rankBy === "total-weeks" || rankBy === "weeks-at-number-one") {
    const { params, filterSql } = buildFilters();
    const valueCol = rankBy === "total-weeks" ? "total_weeks" : "weeks_at_number_one";
    valueLabel = rankBy === "total-weeks" ? "Total Wks" : "Wks #1";
    const valueFilter =
      rankBy === "weeks-at-number-one" ? ` AND st.${valueCol} > 0` : "";
    params.push(limit);
    rows = await sql.query(
      `SELECT i.title,
              i.artist_credit,
              st.${valueCol} AS value,
              i.id AS ${idCol}
       FROM ${statsTable} st
       JOIN ${itemTable} i ON st.${idCol} = i.id
       WHERE 1=1${valueFilter}${filterSql}
       ORDER BY st.${valueCol} ${orderDir}, i.title
       LIMIT $${params.length}`,
      params,
    );
  } else {
    const { params, filterSql } = buildFilters(1);
    const rankFilter =
      rankBy === "weeks-at-position" ? "e.rank = $1" : "e.rank <= $1";
    valueLabel =
      rankBy === "weeks-at-position" ? `Wks @#${rankByParam}` : `Wks Top ${rankByParam}`;

    rows = await sql.query(
      `WITH ${validWeeksCte}
       SELECT i.title,
              i.artist_credit,
              COUNT(*) AS value,
              i.id AS ${idCol}
       FROM ${entryTable} e
       JOIN ${itemTable} i ON e.${idCol} = i.id
       JOIN ${statsTable} st ON st.${idCol} = i.id
       WHERE e.chart_week_id IN (SELECT id FROM ${validWeeksTable})
         AND ${rankFilter}${filterSql}
       GROUP BY i.id, i.title, i.artist_credit
       ORDER BY value ${orderDir}, i.title
       LIMIT $${params.length + 2}`,
      [rankByParam, ...params, limit],
    );
  }

  return {
    mode: "custom",
    entity,
    chart,
    valueLabel,
    rows: mapRows(rows),
  };
}

export async function getArtistRecordDrilldown(
  record: RecordPreset,
  chart: ChartType,
  artistId: number,
  chartDate?: string,
): Promise<DrilldownPayload> {
  const unsupportedMessage = getUnsupportedMessage(record, chart);
  const artistName = await getArtistName(artistId);
  if (unsupportedMessage) {
    return {
      mode: "drilldown",
      record,
      chart,
      artistId,
      artistName,
      chartDate: chartDate ?? null,
      valueLabel: DRILLDOWN_VALUE_LABELS[record] ?? "Value",
      unsupportedMessage,
      rows: [],
      weeks: [],
    };
  }

  const sql = getSql();
  let rows: Record<string, unknown>[] = [];

  switch (record) {
    case "most-number-one-songs-by-artist":
      rows = await sql.query(
        `SELECT s.title, s.artist_credit, ss.weeks_at_number_one AS value, s.id AS song_id
         FROM song_stats ss
         JOIN songs s ON ss.song_id = s.id
         JOIN song_artists sa ON s.id = sa.song_id
         WHERE sa.artist_id = $1 AND ss.weeks_at_number_one > 0
         ORDER BY ss.weeks_at_number_one DESC, s.title`,
        [artistId],
      );
      break;
    case "most-number-one-albums-by-artist":
      rows = await sql.query(
        `SELECT a.title, a.artist_credit, als.weeks_at_number_one AS value, a.id AS album_id
         FROM album_stats als
         JOIN albums a ON als.album_id = a.id
         JOIN album_artists aa ON a.id = aa.album_id
         WHERE aa.artist_id = $1 AND als.weeks_at_number_one > 0
         ORDER BY als.weeks_at_number_one DESC, a.title`,
        [artistId],
      );
      break;
    case "most-entries-by-artist":
      if (chart === "hot-100") {
        rows = await sql.query(
          `SELECT s.title, s.artist_credit, ss.total_weeks AS value, s.id AS song_id
           FROM song_stats ss
           JOIN songs s ON ss.song_id = s.id
           JOIN song_artists sa ON s.id = sa.song_id
           WHERE sa.artist_id = $1
           ORDER BY ss.total_weeks DESC, s.title`,
          [artistId],
        );
      } else {
        rows = await sql.query(
          `SELECT a.title, a.artist_credit, als.total_weeks AS value, a.id AS album_id
           FROM album_stats als
           JOIN albums a ON als.album_id = a.id
           JOIN album_artists aa ON a.id = aa.album_id
           WHERE aa.artist_id = $1
           ORDER BY als.total_weeks DESC, a.title`,
          [artistId],
        );
      }
      break;
    case "most-total-chart-weeks-by-artist":
      if (chart === "hot-100") {
        rows = await sql.query(
          `SELECT s.title, s.artist_credit, ss.total_weeks AS value, s.id AS song_id
           FROM song_stats ss
           JOIN songs s ON ss.song_id = s.id
           JOIN song_artists sa ON s.id = sa.song_id
           WHERE sa.artist_id = $1
           ORDER BY ss.total_weeks DESC, s.title`,
          [artistId],
        );
      } else {
        rows = await sql.query(
          `SELECT a.title, a.artist_credit, als.total_weeks AS value, a.id AS album_id
           FROM album_stats als
           JOIN albums a ON als.album_id = a.id
           JOIN album_artists aa ON a.id = aa.album_id
           WHERE aa.artist_id = $1
           ORDER BY als.total_weeks DESC, a.title`,
          [artistId],
        );
      }
      break;
    case "most-simultaneous-entries":
      rows = await sql.query(
        `WITH ${VALID_HOT100_WEEKS_CTE},
         week_counts AS (
           SELECT e.chart_week_id, COUNT(*) AS cnt
           FROM hot100_entries e
           JOIN song_artists sa ON e.song_id = sa.song_id
           WHERE sa.artist_id = $1
             AND e.chart_week_id IN (SELECT id FROM valid_hot100_weeks)
           GROUP BY e.chart_week_id
         )
         SELECT cw.chart_date::text AS chart_date,
                week_counts.cnt AS week_value,
                s.title,
                s.artist_credit,
                e.rank AS entry_rank,
                s.id AS song_id
         FROM week_counts
         JOIN chart_weeks cw ON week_counts.chart_week_id = cw.id
         JOIN hot100_entries e ON e.chart_week_id = week_counts.chart_week_id
         JOIN songs s ON e.song_id = s.id
         JOIN song_artists sa ON s.id = sa.song_id
         WHERE sa.artist_id = $1
           AND ($2::date IS NULL OR cw.chart_date = $2::date)
         ORDER BY week_counts.cnt DESC, cw.chart_date DESC, e.rank ASC`,
        [artistId, chartDate ?? null],
      );
      break;
    default:
      rows = [];
      break;
  }

  return {
    mode: "drilldown",
    record,
    chart,
    artistId,
    artistName,
    chartDate: chartDate ?? null,
    valueLabel: DRILLDOWN_VALUE_LABELS[record] ?? "Value",
    unsupportedMessage: null,
    rows:
      record === "most-simultaneous-entries" ? [] : mapDrilldownRows(rows),
    weeks:
      record === "most-simultaneous-entries" ? mapSimultaneousWeeks(rows) : [],
  };
}
