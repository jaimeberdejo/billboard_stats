import { type ChartType } from "@/lib/charts";
import { getSql } from "@/lib/db";
import { validWeeksCte, resolveChart, type ChartRow } from "@/lib/valid-weeks";

/**
 * Registry-driven entity-shape lookup for the records SQL builder.
 *
 * The records subsystem reads the polymorphic `chart_entries` table filtered by
 * `chart_id` (bound `$N`) through the SHARED parametric `validWeeksCte` — there
 * is NO `hot100_entries` / `b200_entries` table reference and NO
 * `isHot100 = chart === "hot-100"` 2-way switch. The entity table / stats table /
 * id column / artist-link table are derived from the chart's `entity_kind`
 * (resolved from the registry), NOT from a hardcoded two-chart literal. All
 * strings here are CODE CONSTANTS keyed by entity_kind — never user input. The
 * only bound values remain `$N` params (chart_id, dates, filter values, limit).
 *
 * NOTE: the v1.0 pre-computed stats tables (song_stats / album_stats /
 * artist_stats) are entity-keyed (song_stats by song_id, album_stats by
 * album_id), so the song-entity charts share song_stats and the album-entity
 * charts share album_stats. artist_stats keeps its v1.0 hot100_/b200_ columns
 * (Phase 15 generalizes the artist rollup onto artist_chart_stats); the
 * artist-rollup presets pick the song- vs album-side column by entity_kind.
 */
interface RecordsEntityShape {
  /** Entity row table joined to chart_entries (songs / albums). */
  itemTable: string;
  /** Pre-computed per-entity stats table (song_stats / album_stats). */
  statsTable: string;
  /** chart_entries entity-id column for this entity_kind (song_id / album_id). */
  idCol: "song_id" | "album_id";
  /** Artist link table (song_artists / album_artists). */
  artistLinkTable: string;
  /** Artist link table entity-id column. */
  artistLinkIdCol: "song_id" | "album_id";
}

/**
 * Resolve the records entity shape from a chart's entity_kind. Artist-entity
 * charts (Artist 100) have no song/album-keyed stats rollup in the v1.0 records
 * subsystem, so they map onto the song shape defensively (the api/records layer
 * gates which charts reach here); the entity-kind switch never hardcodes a
 * chart slug.
 */
function recordsEntityShape(entityKind: ChartRow["entity_kind"]): RecordsEntityShape {
  if (entityKind === "album") {
    return {
      itemTable: "albums",
      statsTable: "album_stats",
      idCol: "album_id",
      artistLinkTable: "album_artists",
      artistLinkIdCol: "album_id",
    };
  }
  // song (and defensive default for artist) entity charts.
  return {
    itemTable: "songs",
    statsTable: "song_stats",
    idCol: "song_id",
    artistLinkTable: "song_artists",
    artistLinkIdCol: "song_id",
  };
}

/**
 * Resolve a chart slug to its registry row for the records builders. Throws on
 * an unknown slug — callers (the api/records route) validate the slug via
 * parseChartType before reaching here, so this is a defensive invariant.
 */
async function resolveRecordsChart(chart: ChartType): Promise<ChartRow> {
  const row = await resolveChart(chart);
  if (!row) {
    throw new Error(`Unknown chart slug: ${chart}`);
  }
  return row;
}

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
export type CustomCreditScope = "all" | "lead";

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
  creditScope?: CustomCreditScope;
  rankBy: CustomRankBy;
  rankByParam: number;
  sortDir?: "asc" | "desc";
  limit?: number;
  peakMin?: number | null;
  peakMax?: number | null;
  weeksMin?: number | null;
  debutPosMin?: number | null;
  debutPosMax?: number | null;
  startYear?: number | null;
  endYear?: number | null;
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
  entityKind: ChartRow["entity_kind"],
): string | null {
  // Compatibility guards expressed in entity_kind terms (not the hot-100 /
  // billboard-200 literals): the "songs" records apply to song-entity charts,
  // the "albums" record applies to album-entity charts. simultaneous-entries +
  // #1-songs are song-side records (unsupported on album charts); #1-albums is
  // an album-side record (unsupported on song charts).
  if (record === "most-simultaneous-entries" && entityKind !== "song") {
    return "This record is only tracked for song charts.";
  }
  if (record === "most-number-one-songs-by-artist" && entityKind !== "song") {
    return "This record is only available for song charts.";
  }
  if (record === "most-number-one-albums-by-artist" && entityKind !== "album") {
    return "This record is only available for album charts.";
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
  const chartRow = await resolveRecordsChart(chart);
  const entityKind = chartRow.entity_kind;
  const isSongChart = entityKind === "song";

  const unsupportedMessage = getUnsupportedMessage(record, entityKind);
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
      if (isSongChart) {
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
      if (isSongChart) {
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
      // chart_id-keyed read over the polymorphic chart_entries table through the
      // shared validWeeksCte; the entity JOIN/SELECT branch on entity_kind only.
      if (isSongChart) {
        rows = await sql.query(
          `WITH ${validWeeksCte("valid_weeks", "$2")}
           SELECT s.title, s.artist_credit, COUNT(*) AS value, s.id AS song_id
           FROM chart_entries e
           JOIN songs s ON e.song_id = s.id
           WHERE e.chart_id = $2
             AND e.chart_week_id IN (SELECT id FROM valid_weeks)
             AND e.rank <= 10
           GROUP BY s.id, s.title, s.artist_credit
           ORDER BY value DESC, s.title
           LIMIT $1`,
          [limit, chartRow.id],
        );
      } else {
        rows = await sql.query(
          `WITH ${validWeeksCte("valid_weeks", "$2")}
           SELECT a.title, a.artist_credit, COUNT(*) AS value, a.id AS album_id
           FROM chart_entries e
           JOIN albums a ON e.album_id = a.id
           WHERE e.chart_id = $2
             AND e.chart_week_id IN (SELECT id FROM valid_weeks)
             AND e.rank <= 10
           GROUP BY a.id, a.title, a.artist_credit
           ORDER BY value DESC, a.title
           LIMIT $1`,
          [limit, chartRow.id],
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
      // Legacy artist rollup (artist_stats) is keyed by the song- vs album-side
      // career column, picked by entity_kind. Phase 15 generalizes this onto
      // artist_chart_stats; until then the entity_kind branch is the contract.
      if (isSongChart) {
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
      if (isSongChart) {
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
      // Song-side record (gated above); chart_id-keyed chart_entries read.
      rows = await sql.query(
        `WITH ${validWeeksCte("valid_weeks", "$2")},
         artist_week_counts AS (
           SELECT sa.artist_id, e.chart_week_id, COUNT(*) AS cnt
           FROM chart_entries e
           JOIN song_artists sa ON e.song_id = sa.song_id
           WHERE e.chart_id = $2
             AND e.chart_week_id IN (SELECT id FROM valid_weeks)
           GROUP BY sa.artist_id, e.chart_week_id
         )
         SELECT a.name AS title, a.name AS artist_credit,
                awc.cnt AS value, a.id AS artist_id, cw.chart_date::text AS chart_date
         FROM artist_week_counts awc
         JOIN artists a ON awc.artist_id = a.id
         JOIN chart_weeks cw ON awc.chart_week_id = cw.id
         ORDER BY awc.cnt DESC, cw.chart_date DESC, a.name
         LIMIT $1`,
        [limit, chartRow.id],
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
    creditScope = "all",
    rankBy,
    rankByParam,
    sortDir = "desc",
    limit = 50,
    peakMin,
    peakMax,
    weeksMin,
    debutPosMin,
    debutPosMax,
    startYear,
    endYear,
    artistNames,
  } = input;

  const sql = getSql();
  const chartRow = await resolveRecordsChart(chart);
  const entityKind = chartRow.entity_kind;
  const isSongChart = entityKind === "song";
  const shape = recordsEntityShape(entityKind);
  // Polymorphic chart_entries read keyed by chart_id ($1), filtered through the
  // shared validWeeksCte (also bound to $1). The legacy hot100_entries /
  // b200_entries tables and the isHot100 boolean switch are gone — entity tables
  // derive from entity_kind, the chart is selected by chart_id.
  const chartId = chartRow.id;
  const itemTable = shape.itemTable;
  const statsTable = shape.statsTable;
  const idCol = shape.idCol;
  // The valid-weeks relation is bound to chart_id at $1; entry reads filter
  // chart_entries by the same chart_id ($1) AND membership in valid_weeks.
  const validWeeksCteBody = validWeeksCte("valid_weeks", "$1");
  const validWeeksTable = "valid_weeks";
  const orderDir = sortDir === "asc" ? "ASC" : "DESC";
  const hasYearFilter = startYear != null || endYear != null;
  const artistLinkTable = shape.artistLinkTable;
  const artistLinkIdCol = shape.artistLinkIdCol;

  let rows: Record<string, unknown>[] = [];
  let valueLabel = "Value";

  const buildYearFilter = (placeholderOffset = 0, dateExpr = "cw.chart_date") => {
    const params: Array<string | number> = [];
    const filters: string[] = [];
    const placeholder = () => `$${placeholderOffset + params.length + 1}`;

    if (startYear != null) {
      filters.push(`${dateExpr} >= ${placeholder()}`);
      params.push(`${startYear}-01-01`);
    }
    if (endYear != null) {
      filters.push(`${dateExpr} <= ${placeholder()}`);
      params.push(`${endYear}-12-31`);
    }

    return {
      params,
      filterSql: filters.length > 0 ? ` AND ${filters.join(" AND ")}` : "",
    };
  };

  const buildFilters = (
    placeholderOffset = 0,
    artistExpr = "i.artist_credit",
    statsExpr = "st",
  ) => {
    const params: Array<string | number> = [];
    const filters: string[] = [];
    const placeholder = () => `$${placeholderOffset + params.length + 1}`;

    if (artistNames && artistNames.length > 0) {
      const artistValues = artistNames.map((name) => `%${name}%`);
      // Capture the base offset BEFORE the map so each iteration gets its own $N.
      const artistBase = placeholderOffset + params.length;
      const artistClause = artistValues.map(
        (_, index) => `${artistExpr} ILIKE $${artistBase + index + 1}`,
      );
      filters.push(`(${artistClause.join(" OR ")})`);
      params.push(...artistValues);
    }
    if (peakMin != null) {
      filters.push(`${statsExpr}.peak_position >= ${placeholder()}`);
      params.push(peakMin);
    }
    if (peakMax != null) {
      filters.push(`${statsExpr}.peak_position <= ${placeholder()}`);
      params.push(peakMax);
    }
    if (weeksMin != null) {
      filters.push(`${statsExpr}.total_weeks >= ${placeholder()}`);
      params.push(weeksMin);
    }
    if (debutPosMin != null) {
      filters.push(`${statsExpr}.debut_position >= ${placeholder()}`);
      params.push(debutPosMin);
    }
    if (debutPosMax != null) {
      filters.push(`${statsExpr}.debut_position <= ${placeholder()}`);
      params.push(debutPosMax);
    }

    return {
      params,
      filterSql: filters.length > 0 ? ` AND ${filters.join(" AND ")}` : "",
    };
  };

  if (entity === "artists" && !hasYearFilter) {
    const roleFilter = creditScope === "lead" ? "AND link.role = 'primary'" : "";
    const params: Array<string | number> = [];
    const filters: string[] = [];
    // No chart discriminator param: the entity arm is chosen in code by
    // entity_kind, so placeholders are 1-based (was 2-based behind the removed
    // `$1 = 'hot-100'` UNION discriminator).
    const placeholder = () => `$${params.length + 1}`;

    if (artistNames && artistNames.length > 0) {
      const artistValues = artistNames.map((name) => `%${name}%`);
      const artistClause = artistValues.map((_, index) => `a.name ILIKE $${index + 1}`);
      filters.push(`(${artistClause.join(" OR ")})`);
      params.push(...artistValues);
    }
    if (weeksMin != null) {
      filters.push(`aggregated.total_weeks >= ${placeholder()}`);
      params.push(weeksMin);
    }

    let valueSql = "";
    if (rankBy === "total-weeks") {
      valueLabel = "Total Wks";
      valueSql = "aggregated.total_weeks";
      filters.push(`${valueSql} > 0`);
    } else if (rankBy === "most-entries") {
      valueLabel = "Entries";
      valueSql = "aggregated.entry_count";
      filters.push(`${valueSql} > 0`);
    } else {
      valueLabel = isSongChart ? "#1 Songs" : "#1 Albums";
      valueSql = "aggregated.number_one_count";
      filters.push(`${valueSql} > 0`);
    }

    const filterSql = filters.length > 0 ? `WHERE ${filters.join(" AND ")}` : "";
    params.push(limit);
    // Single entity-kind-keyed arm over the entity's artist-link + stats tables
    // (code constants from `shape`); replaces the 2-arm UNION discriminator.
    rows = await sql.query(
      `WITH selected_entries AS (
         SELECT link.artist_id,
                link.${artistLinkIdCol} AS item_id
         FROM ${artistLinkTable} link
         WHERE true
           ${roleFilter}
       ),
       aggregated AS (
         SELECT se.artist_id,
                COUNT(DISTINCT se.item_id)::int AS entry_count,
                COALESCE(SUM(st.total_weeks), 0)::int AS total_weeks,
                COUNT(*) FILTER (WHERE COALESCE(st.weeks_at_number_one, 0) > 0)::int AS number_one_count
         FROM selected_entries se
         JOIN ${statsTable} st ON st.${idCol} = se.item_id
         GROUP BY se.artist_id
       )
       SELECT a.name AS title,
              a.name AS artist_credit,
              ${valueSql} AS value,
              a.id AS artist_id
       FROM aggregated
       JOIN artists a ON aggregated.artist_id = a.id
       ${filterSql}
       ORDER BY ${valueSql} ${orderDir}, a.name
       LIMIT $${params.length}`,
      params,
    );
  } else if (entity === "artists" && hasYearFilter) {
    const roleFilter = creditScope === "lead" ? "WHERE link.role = 'primary'" : "";
    // $1 = chart_id (the validWeeksCte bind + the chart_entries filter). All
    // other params start at offset 1.
    const yearFilter = buildYearFilter(1);
    const params: Array<string | number> = [chartId, ...yearFilter.params];
    const filters: string[] = [];
    const placeholder = () => `$${params.length + 1}`;

    if (artistNames && artistNames.length > 0) {
      const artistValues = artistNames.map((name) => `%${name}%`);
      // Capture the base offset BEFORE the map so each iteration gets its own $N.
      // Local placeholder() resolves to `$${params.length + 1}`, so artistBase = params.length.
      const artistBase = params.length;
      const artistClause = artistValues.map(
        (_, index) => `a.name ILIKE $${artistBase + index + 1}`,
      );
      filters.push(`(${artistClause.join(" OR ")})`);
      params.push(...artistValues);
    }
    if (weeksMin != null) {
      filters.push(`aggregated.total_weeks >= ${placeholder()}`);
      params.push(weeksMin);
    }

    let valueSql = "";
    if (rankBy === "total-weeks") {
      valueLabel = "Total Wks";
      valueSql = "aggregated.total_weeks";
      filters.push(`${valueSql} > 0`);
    } else if (rankBy === "most-entries") {
      valueLabel = "Entries";
      valueSql = "aggregated.entry_count";
      filters.push(`${valueSql} > 0`);
    } else {
      valueLabel = isSongChart ? "#1 Songs" : "#1 Albums";
      valueSql = "aggregated.number_one_count";
      filters.push(`${valueSql} > 0`);
    }

    const filterSql = filters.length > 0 ? `WHERE ${filters.join(" AND ")}` : "";
    params.push(limit);

    rows = await sql.query(
      `WITH ${validWeeksCteBody},
       filtered_entries AS (
         SELECT e.${idCol} AS item_id,
                e.rank,
                cw.chart_date
         FROM chart_entries e
         JOIN chart_weeks cw ON cw.id = e.chart_week_id
         WHERE e.chart_id = $1
           AND e.chart_week_id IN (SELECT id FROM ${validWeeksTable})${yearFilter.filterSql}
       ),
       item_stats AS (
         SELECT fe.item_id,
                COUNT(*)::int AS total_weeks,
                MIN(fe.rank)::int AS peak_position,
                COUNT(*) FILTER (
                  WHERE fe.rank = (
                    SELECT MIN(fe2.rank)
                    FROM filtered_entries fe2
                    WHERE fe2.item_id = fe.item_id
                  )
                )::int AS weeks_at_peak,
                COUNT(*) FILTER (WHERE fe.rank = 1)::int AS weeks_at_number_one,
                MIN(fe.chart_date)::date AS debut_date,
                (ARRAY_AGG(fe.rank ORDER BY fe.chart_date ASC))[1]::int AS debut_position
         FROM filtered_entries fe
         GROUP BY fe.item_id
       ),
       aggregated AS (
         SELECT link.artist_id,
                COUNT(DISTINCT stats.item_id)::int AS entry_count,
                COALESCE(SUM(stats.total_weeks), 0)::int AS total_weeks,
                COUNT(*) FILTER (WHERE COALESCE(stats.weeks_at_number_one, 0) > 0)::int AS number_one_count
         FROM ${artistLinkTable} link
         JOIN item_stats stats ON stats.item_id = link.${artistLinkIdCol}
         ${roleFilter}
         GROUP BY link.artist_id
       )
       SELECT a.name AS title,
              a.name AS artist_credit,
              ${valueSql} AS value,
              a.id AS artist_id
       FROM aggregated
       JOIN artists a ON aggregated.artist_id = a.id
       ${filterSql}
       ORDER BY ${valueSql} ${orderDir}, a.name
       LIMIT $${params.length}`,
      params,
    );
  } else if (!hasYearFilter && (rankBy === "total-weeks" || rankBy === "weeks-at-number-one")) {
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
  } else if (!hasYearFilter) {
    // $1 = chart_id (validWeeksCte bind + chart_entries filter); $2 = rankByParam;
    // filters start at offset 2.
    const { params, filterSql } = buildFilters(2);
    const rankFilter =
      rankBy === "weeks-at-position" ? "e.rank = $2" : "e.rank <= $2";
    valueLabel =
      rankBy === "weeks-at-position" ? `Wks @#${rankByParam}` : `Wks Top ${rankByParam}`;

    rows = await sql.query(
      `WITH ${validWeeksCteBody}
       SELECT i.title,
              i.artist_credit,
              COUNT(*) AS value,
              i.id AS ${idCol}
       FROM chart_entries e
       JOIN ${itemTable} i ON e.${idCol} = i.id
       JOIN ${statsTable} st ON st.${idCol} = i.id
       WHERE e.chart_id = $1
         AND e.chart_week_id IN (SELECT id FROM ${validWeeksTable})
         AND ${rankFilter}${filterSql}
       GROUP BY i.id, i.title, i.artist_credit
       ORDER BY value ${orderDir}, i.title
       LIMIT $${params.length + 3}`,
      [chartId, rankByParam, ...params, limit],
    );
  } else if (rankBy === "total-weeks" || rankBy === "weeks-at-number-one") {
    // $1 = chart_id; yearFilter + filters start at offset 1.
    const yearFilter = buildYearFilter(1);
    const { params: filterParams, filterSql } = buildFilters(
      1 + yearFilter.params.length,
    );
    const valueCol = rankBy === "total-weeks" ? "total_weeks" : "weeks_at_number_one";
    valueLabel = rankBy === "total-weeks" ? "Total Wks" : "Wks #1";
    const valueFilter =
      rankBy === "weeks-at-number-one" ? ` AND st.${valueCol} > 0` : "";
    const params = [chartId, ...yearFilter.params, ...filterParams, limit];

    rows = await sql.query(
      `WITH ${validWeeksCteBody},
       filtered_entries AS (
         SELECT e.${idCol} AS item_id,
                e.rank,
                cw.chart_date
         FROM chart_entries e
         JOIN chart_weeks cw ON cw.id = e.chart_week_id
         WHERE e.chart_id = $1
           AND e.chart_week_id IN (SELECT id FROM ${validWeeksTable})${yearFilter.filterSql}
       ),
       item_stats AS (
         SELECT fe.item_id,
                COUNT(*)::int AS total_weeks,
                MIN(fe.rank)::int AS peak_position,
                COUNT(*) FILTER (
                  WHERE fe.rank = (
                    SELECT MIN(fe2.rank)
                    FROM filtered_entries fe2
                    WHERE fe2.item_id = fe.item_id
                  )
                )::int AS weeks_at_peak,
                COUNT(*) FILTER (WHERE fe.rank = 1)::int AS weeks_at_number_one,
                MIN(fe.chart_date)::date AS debut_date,
                (ARRAY_AGG(fe.rank ORDER BY fe.chart_date ASC))[1]::int AS debut_position
         FROM filtered_entries fe
         GROUP BY fe.item_id
       )
       SELECT i.title,
              i.artist_credit,
              st.${valueCol} AS value,
              i.id AS ${idCol}
       FROM item_stats st
       JOIN ${itemTable} i ON st.item_id = i.id
       WHERE 1=1${valueFilter}${filterSql}
       ORDER BY st.${valueCol} ${orderDir}, i.title
       LIMIT $${params.length}`,
      params,
    );
  } else {
    // $1 = chart_id; $2 = rankByParam; yearFilter starts at offset 2; filters
    // start after yearFilter.
    const yearFilter = buildYearFilter(2);
    const { params: filterParams, filterSql } = buildFilters(
      2 + yearFilter.params.length,
    );
    const rankFilter =
      rankBy === "weeks-at-position" ? "fe.rank = $2" : "fe.rank <= $2";
    valueLabel =
      rankBy === "weeks-at-position" ? `Wks @#${rankByParam}` : `Wks Top ${rankByParam}`;
    const params = [chartId, rankByParam, ...yearFilter.params, ...filterParams, limit];

    rows = await sql.query(
      `WITH ${validWeeksCteBody},
       filtered_entries AS (
         SELECT e.${idCol} AS item_id,
                e.rank,
                cw.chart_date
         FROM chart_entries e
         JOIN chart_weeks cw ON cw.id = e.chart_week_id
         WHERE e.chart_id = $1
           AND e.chart_week_id IN (SELECT id FROM ${validWeeksTable})${yearFilter.filterSql}
       ),
       item_stats AS (
         SELECT fe.item_id,
                COUNT(*)::int AS total_weeks,
                MIN(fe.rank)::int AS peak_position,
                COUNT(*) FILTER (
                  WHERE fe.rank = (
                    SELECT MIN(fe2.rank)
                    FROM filtered_entries fe2
                    WHERE fe2.item_id = fe.item_id
                  )
                )::int AS weeks_at_peak,
                COUNT(*) FILTER (WHERE fe.rank = 1)::int AS weeks_at_number_one,
                MIN(fe.chart_date)::date AS debut_date,
                (ARRAY_AGG(fe.rank ORDER BY fe.chart_date ASC))[1]::int AS debut_position
         FROM filtered_entries fe
         GROUP BY fe.item_id
       )
       SELECT i.title,
              i.artist_credit,
              COUNT(*) AS value,
              i.id AS ${idCol}
       FROM filtered_entries fe
       JOIN ${itemTable} i ON fe.item_id = i.id
       JOIN item_stats st ON st.item_id = i.id
       WHERE ${rankFilter}${filterSql}
       GROUP BY i.id, i.title, i.artist_credit
       ORDER BY value ${orderDir}, i.title
       LIMIT $${params.length}`,
      params,
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
  const chartRow = await resolveRecordsChart(chart);
  const entityKind = chartRow.entity_kind;
  const isSongChart = entityKind === "song";
  const unsupportedMessage = getUnsupportedMessage(record, entityKind);
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
      if (isSongChart) {
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
      if (isSongChart) {
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
      // Song-side record (gated via getUnsupportedMessage); chart_id-keyed
      // chart_entries read through the shared validWeeksCte. $1 = artistId,
      // $2 = chartDate, $3 = chart_id.
      rows = await sql.query(
        `WITH ${validWeeksCte("valid_weeks", "$3")},
         week_counts AS (
           SELECT e.chart_week_id, COUNT(*) AS cnt
           FROM chart_entries e
           JOIN song_artists sa ON e.song_id = sa.song_id
           WHERE sa.artist_id = $1
             AND e.chart_id = $3
             AND e.chart_week_id IN (SELECT id FROM valid_weeks)
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
         JOIN chart_entries e ON e.chart_week_id = week_counts.chart_week_id
              AND e.chart_id = $3
         JOIN songs s ON e.song_id = s.id
         JOIN song_artists sa ON s.id = sa.song_id
         WHERE sa.artist_id = $1
           AND ($2::date IS NULL OR cw.chart_date = $2::date)
         ORDER BY week_counts.cnt DESC, cw.chart_date DESC, e.rank ASC`,
        [artistId, chartDate ?? null, chartRow.id],
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
