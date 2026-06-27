import { getArtistIdentityGroup, getCanonicalArtistName } from "@/lib/artist-identity";
import { getSql } from "@/lib/db";
import { genreFamily, type ChartFamily } from "@/lib/chart-families";

export interface ArtistCatalogSongRow {
  id: number;
  title: string;
  artist_credit: string;
  peak_position: number | null;
  total_weeks: number;
  weeks_at_peak: number;
  weeks_at_number_one: number;
  debut_date: string | null;
  last_date: string | null;
  debut_position: number | null;
  /** Originating chart slug for correct per-chart date links. */
  chart_slug: string;
}

export interface ArtistCatalogAlbumRow {
  id: number;
  title: string;
  artist_credit: string;
  peak_position: number | null;
  total_weeks: number;
  weeks_at_peak: number;
  weeks_at_number_one: number;
  debut_date: string | null;
  last_date: string | null;
  debut_position: number | null;
  /** Originating chart slug for correct per-chart date links. */
  chart_slug: string;
}

/**
 * Per-chart rollup for one artist on one chart, read from artist_chart_stats
 * (DATA-03) and tagged with the chart's title + derived family. Adding a chart
 * adds rollups, never columns.
 */
export interface ArtistChartRollup {
  chart_slug: string;
  chart_title: string;
  family: ChartFamily;
  entity_kind: "song" | "album" | "artist";
  total_entries: number;
  total_weeks: number;
  number_ones: number;
  best_peak: number | null;
  max_simultaneous: number;
  first_date: string | null;
  last_date: string | null;
}

/**
 * Career totals derived by aggregating artist_chart_stats GROUP BY artist_id
 * across ALL charts (Pitfall 4: aggregate this single source — never also sum
 * artist_stats, which would double-count). Matches the Python rollup semantics
 * (total_weeks = entity-weeks; best_peak = lowest rank; first/last = MIN/MAX).
 */
export interface ArtistCareerTotals {
  total_entries: number;
  total_weeks: number;
  number_ones: number;
  best_peak: number | null;
  max_simultaneous: number;
  first_date: string | null;
  last_date: string | null;
  chart_count: number;
}

export interface ArtistDetailPayload {
  artist: {
    id: number;
    name: string;
    image_url: string | null;
  };
  careerTotals: ArtistCareerTotals | null;
  chartRollups: ArtistChartRollup[];
  songs: ArtistCatalogSongRow[];
  albums: ArtistCatalogAlbumRow[];
}

export type ArtistCreditScope = "all" | "lead";

interface ArtistRow {
  id: number;
  name: string;
  image_url: string | null;
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

async function resolveArtistGroup(
  artistId: number,
): Promise<{ canonical: ArtistRow; artistIds: number[] } | null> {
  const sql = getSql();
  const artistRows = await sql.query(
    `SELECT id, name, image_url
     FROM artists
     WHERE id = $1`,
    [artistId],
  );

  const currentArtist = artistRows[0];
  if (!currentArtist) {
    return null;
  }

  const currentName = currentArtist.name as string;
  const candidateNames = getArtistIdentityGroup(currentName);
  const groupedRows = await sql.query(
    `SELECT id, name, image_url
     FROM artists
     WHERE lower(name) = ANY($1::text[])`,
    [candidateNames.map((name) => name.toLowerCase())],
  );

  const artists = groupedRows.length > 0 ? groupedRows : artistRows;
  const canonicalName = getCanonicalArtistName(currentName);
  const canonicalArtistRow =
    artists.find((row) => (row.name as string) === canonicalName) ?? artists[0];

  return {
    canonical: {
      id: canonicalArtistRow.id as number,
      name: canonicalName,
      image_url: (canonicalArtistRow.image_url as string | null) ?? null,
    },
    artistIds: artists.map((row) => row.id as number),
  };
}

export async function getArtistDetail(
  artistId: number,
  creditScope: ArtistCreditScope = "all",
): Promise<ArtistDetailPayload | null> {
  if (!isPositiveInteger(artistId)) {
    return null;
  }

  const sql = getSql();
  const artistGroup = await resolveArtistGroup(artistId);
  if (!artistGroup) {
    return null;
  }

  const songRoleFilter =
    creditScope === "lead" ? "AND sa.role = 'primary'" : "";
  const albumRoleFilter =
    creditScope === "lead" ? "AND aa.role = 'primary'" : "";

  const [artistRows, rollupRows, songRows, albumRows] = await Promise.all([
    Promise.resolve([
      {
        id: artistGroup.canonical.id,
        name: artistGroup.canonical.name,
        image_url: artistGroup.canonical.image_url,
      },
    ]),
    // Per-chart rollups: one row per (artist, chart) from artist_chart_stats,
    // summed across the identity group's artist ids and joined to the registry.
    // Covers ALL charts (not just hot-100/b200) — no legacy entry tables.
    sql.query(
      `SELECT c.slug AS chart_slug,
              c.title AS chart_title,
              c.category AS chart_category,
              c.entity_kind AS entity_kind,
              c.sort_order AS sort_order,
              SUM(acs.total_entries)::int AS total_entries,
              SUM(acs.total_weeks)::int AS total_weeks,
              SUM(acs.number_ones)::int AS number_ones,
              MIN(acs.best_peak) AS best_peak,
              MAX(acs.max_simultaneous)::int AS max_simultaneous,
              MIN(acs.first_date)::text AS first_date,
              MAX(acs.last_date)::text AS last_date
       FROM artist_chart_stats acs
       JOIN charts c ON acs.chart_id = c.id
       WHERE acs.artist_id = ANY($1::int[])
       GROUP BY c.id, c.slug, c.title, c.category, c.entity_kind, c.sort_order
       ORDER BY c.sort_order ASC, c.title ASC`,
      [artistGroup.artistIds],
    ),
    // Catalog songs, threaded with the originating chart slug so per-chart
    // sections + date links resolve to the right chart. A song on multiple
    // charts yields one catalog row per chart it appears on.
    sql.query(
      `SELECT DISTINCT ON (s.id, c.id)
              s.id,
              s.title,
              s.artist_credit,
              ss.peak_position,
              ss.total_weeks,
              ss.weeks_at_peak,
              ss.weeks_at_number_one,
              ss.debut_date::text AS debut_date,
              ss.last_date::text AS last_date,
              ss.debut_position,
              c.slug AS chart_slug,
              c.sort_order AS sort_order
       FROM song_artists sa
       JOIN songs s ON sa.song_id = s.id
       LEFT JOIN song_stats ss ON s.id = ss.song_id
       JOIN chart_entries e ON e.song_id = s.id
       JOIN chart_weeks cw ON e.chart_week_id = cw.id
       JOIN charts c ON cw.chart_id = c.id
       WHERE sa.artist_id = ANY($1::int[])
       ${songRoleFilter}
       ORDER BY s.id, c.id, CASE WHEN sa.role = 'primary' THEN 0 ELSE 1 END, sa.artist_id`,
      [artistGroup.artistIds],
    ),
    sql.query(
      `SELECT DISTINCT ON (a.id, c.id)
              a.id,
              a.title,
              a.artist_credit,
              als.peak_position,
              als.total_weeks,
              als.weeks_at_peak,
              als.weeks_at_number_one,
              als.debut_date::text AS debut_date,
              als.last_date::text AS last_date,
              als.debut_position,
              c.slug AS chart_slug,
              c.sort_order AS sort_order
       FROM album_artists aa
       JOIN albums a ON aa.album_id = a.id
       LEFT JOIN album_stats als ON a.id = als.album_id
       JOIN chart_entries e ON e.album_id = a.id
       JOIN chart_weeks cw ON e.chart_week_id = cw.id
       JOIN charts c ON cw.chart_id = c.id
       WHERE aa.artist_id = ANY($1::int[])
       ${albumRoleFilter}
       ORDER BY a.id, c.id, CASE WHEN aa.role = 'primary' THEN 0 ELSE 1 END, aa.artist_id`,
      [artistGroup.artistIds],
    ),
  ]);

  const artistRow = artistRows[0];
  if (!artistRow) {
    return null;
  }

  const chartRollups: ArtistChartRollup[] = rollupRows.map((row) => {
    const slug = row.chart_slug as string;
    return {
      chart_slug: slug,
      chart_title: (row.chart_title as string | null) ?? slug,
      family: genreFamily(slug, (row.chart_category as string | null) ?? null),
      entity_kind: row.entity_kind as "song" | "album" | "artist",
      total_entries: (row.total_entries as number) ?? 0,
      total_weeks: (row.total_weeks as number) ?? 0,
      number_ones: (row.number_ones as number) ?? 0,
      best_peak: (row.best_peak as number | null) ?? null,
      max_simultaneous: (row.max_simultaneous as number) ?? 0,
      first_date: toIsoDate(row.first_date),
      last_date: toIsoDate(row.last_date),
    };
  });

  // Career totals = aggregate across the per-chart rollups (single source).
  // total_weeks/number_ones/total_entries SUM; best_peak MIN; max_simultaneous
  // MAX; first/last MIN/MAX. Never also sum artist_stats (Pitfall 4).
  const careerTotals: ArtistCareerTotals | null =
    chartRollups.length > 0
      ? chartRollups.reduce<ArtistCareerTotals>(
          (acc, r) => ({
            total_entries: acc.total_entries + r.total_entries,
            total_weeks: acc.total_weeks + r.total_weeks,
            number_ones: acc.number_ones + r.number_ones,
            best_peak:
              r.best_peak === null
                ? acc.best_peak
                : acc.best_peak === null
                  ? r.best_peak
                  : Math.min(acc.best_peak, r.best_peak),
            max_simultaneous: Math.max(acc.max_simultaneous, r.max_simultaneous),
            first_date:
              r.first_date === null
                ? acc.first_date
                : acc.first_date === null
                  ? r.first_date
                  : r.first_date < acc.first_date
                    ? r.first_date
                    : acc.first_date,
            last_date:
              r.last_date === null
                ? acc.last_date
                : acc.last_date === null
                  ? r.last_date
                  : r.last_date > acc.last_date
                    ? r.last_date
                    : acc.last_date,
            chart_count: acc.chart_count + 1,
          }),
          {
            total_entries: 0,
            total_weeks: 0,
            number_ones: 0,
            best_peak: null,
            max_simultaneous: 0,
            first_date: null,
            last_date: null,
            chart_count: 0,
          },
        )
      : null;

  return {
    artist: {
      id: artistRow.id as number,
      name: artistRow.name as string,
      image_url: (artistRow.image_url as string | null) ?? null,
    },
    careerTotals,
    chartRollups,
    songs: songRows.map((row) => ({
      id: row.id as number,
      title: row.title as string,
      artist_credit: row.artist_credit as string,
      peak_position: (row.peak_position as number | null) ?? null,
      total_weeks: (row.total_weeks as number) ?? 0,
      weeks_at_peak: (row.weeks_at_peak as number) ?? 0,
      weeks_at_number_one: (row.weeks_at_number_one as number) ?? 0,
      debut_date: toIsoDate(row.debut_date),
      last_date: toIsoDate(row.last_date),
      debut_position: (row.debut_position as number | null) ?? null,
      chart_slug: row.chart_slug as string,
    })),
    albums: albumRows.map((row) => ({
      id: row.id as number,
      title: row.title as string,
      artist_credit: row.artist_credit as string,
      peak_position: (row.peak_position as number | null) ?? null,
      total_weeks: (row.total_weeks as number) ?? 0,
      weeks_at_peak: (row.weeks_at_peak as number) ?? 0,
      weeks_at_number_one: (row.weeks_at_number_one as number) ?? 0,
      debut_date: toIsoDate(row.debut_date),
      last_date: toIsoDate(row.last_date),
      debut_position: (row.debut_position as number | null) ?? null,
      chart_slug: row.chart_slug as string,
    })),
  };
}
