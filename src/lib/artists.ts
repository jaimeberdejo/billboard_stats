import { getSql } from "@/lib/db";

export interface ArtistCatalogSongRow {
  id: number;
  title: string;
  artist_credit: string;
  peak_position: number | null;
  total_weeks: number;
  weeks_at_peak: number;
  weeks_at_number_one: number;
  debut_date: string | null;
  debut_position: number | null;
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
  debut_position: number | null;
}

export interface ArtistDetailPayload {
  artist: {
    id: number;
    name: string;
    image_url: string | null;
  };
  stats: {
    artist_id: number;
    total_hot100_songs: number;
    total_b200_albums: number;
    total_hot100_weeks: number;
    total_b200_weeks: number;
    hot100_number_ones: number;
    b200_number_ones: number;
    best_hot100_peak: number | null;
    best_b200_peak: number | null;
    first_chart_date: string | null;
    latest_chart_date: string | null;
    max_simultaneous_hot100: number;
  } | null;
  songs: ArtistCatalogSongRow[];
  albums: ArtistCatalogAlbumRow[];
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

export async function getArtistDetail(
  artistId: number,
): Promise<ArtistDetailPayload | null> {
  if (!isPositiveInteger(artistId)) {
    return null;
  }

  const sql = getSql();

  const [artistRows, statsRows, songRows, albumRows] = await Promise.all([
    sql.query(
      `SELECT id, name, image_url
       FROM artists
       WHERE id = $1`,
      [artistId],
    ),
    sql.query(
      `SELECT artist_id,
              total_hot100_songs,
              total_b200_albums,
              total_hot100_weeks,
              total_b200_weeks,
              hot100_number_ones,
              b200_number_ones,
              best_hot100_peak,
              best_b200_peak,
              first_chart_date::text AS first_chart_date,
              latest_chart_date::text AS latest_chart_date,
              max_simultaneous_hot100
       FROM artist_stats
       WHERE artist_id = $1`,
      [artistId],
    ),
    sql.query(
      `SELECT s.id,
              s.title,
              s.artist_credit,
              ss.peak_position,
              ss.total_weeks,
              ss.weeks_at_peak,
              ss.weeks_at_number_one,
              ss.debut_date::text AS debut_date,
              ss.debut_position
       FROM song_artists sa
       JOIN songs s ON sa.song_id = s.id
       LEFT JOIN song_stats ss ON s.id = ss.song_id
       WHERE sa.artist_id = $1
       ORDER BY ss.debut_date ASC NULLS LAST, s.title ASC`,
      [artistId],
    ),
    sql.query(
      `SELECT a.id,
              a.title,
              a.artist_credit,
              als.peak_position,
              als.total_weeks,
              als.weeks_at_peak,
              als.weeks_at_number_one,
              als.debut_date::text AS debut_date,
              als.debut_position
       FROM album_artists aa
       JOIN albums a ON aa.album_id = a.id
       LEFT JOIN album_stats als ON a.id = als.album_id
       WHERE aa.artist_id = $1
       ORDER BY als.debut_date ASC NULLS LAST, a.title ASC`,
      [artistId],
    ),
  ]);

  const artistRow = artistRows[0];
  if (!artistRow) {
    return null;
  }

  const statsRow = statsRows[0];

  return {
    artist: {
      id: artistRow.id as number,
      name: artistRow.name as string,
      image_url: (artistRow.image_url as string | null) ?? null,
    },
    stats: statsRow
      ? {
          artist_id: statsRow.artist_id as number,
          total_hot100_songs: (statsRow.total_hot100_songs as number) ?? 0,
          total_b200_albums: (statsRow.total_b200_albums as number) ?? 0,
          total_hot100_weeks: (statsRow.total_hot100_weeks as number) ?? 0,
          total_b200_weeks: (statsRow.total_b200_weeks as number) ?? 0,
          hot100_number_ones: (statsRow.hot100_number_ones as number) ?? 0,
          b200_number_ones: (statsRow.b200_number_ones as number) ?? 0,
          best_hot100_peak: (statsRow.best_hot100_peak as number | null) ?? null,
          best_b200_peak: (statsRow.best_b200_peak as number | null) ?? null,
          first_chart_date: toIsoDate(statsRow.first_chart_date),
          latest_chart_date: toIsoDate(statsRow.latest_chart_date),
          max_simultaneous_hot100:
            (statsRow.max_simultaneous_hot100 as number) ?? 0,
        }
      : null,
    songs: songRows.map((row) => ({
      id: row.id as number,
      title: row.title as string,
      artist_credit: row.artist_credit as string,
      peak_position: (row.peak_position as number | null) ?? null,
      total_weeks: (row.total_weeks as number) ?? 0,
      weeks_at_peak: (row.weeks_at_peak as number) ?? 0,
      weeks_at_number_one: (row.weeks_at_number_one as number) ?? 0,
      debut_date: toIsoDate(row.debut_date),
      debut_position: (row.debut_position as number | null) ?? null,
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
      debut_position: (row.debut_position as number | null) ?? null,
    })),
  };
}
