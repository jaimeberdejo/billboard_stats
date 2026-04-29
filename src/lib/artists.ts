import { getArtistIdentityGroup, getCanonicalArtistName } from "@/lib/artist-identity";
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
  last_date: string | null;
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
  last_date: string | null;
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
): Promise<ArtistDetailPayload | null> {
  if (!isPositiveInteger(artistId)) {
    return null;
  }

  const sql = getSql();
  const artistGroup = await resolveArtistGroup(artistId);
  if (!artistGroup) {
    return null;
  }

  const [artistRows, statsRows, songRows, albumRows] = await Promise.all([
    Promise.resolve([
      {
        id: artistGroup.canonical.id,
        name: artistGroup.canonical.name,
        image_url: artistGroup.canonical.image_url,
      },
    ]),
    sql.query(
      `SELECT COUNT(*)::int AS stats_count,
              COALESCE(SUM(total_hot100_songs), 0)::int AS total_hot100_songs,
              COALESCE(SUM(total_b200_albums), 0)::int AS total_b200_albums,
              COALESCE(SUM(total_hot100_weeks), 0)::int AS total_hot100_weeks,
              COALESCE(SUM(total_b200_weeks), 0)::int AS total_b200_weeks,
              COALESCE(SUM(hot100_number_ones), 0)::int AS hot100_number_ones,
              COALESCE(SUM(b200_number_ones), 0)::int AS b200_number_ones,
              MIN(best_hot100_peak) AS best_hot100_peak,
              MIN(best_b200_peak) AS best_b200_peak,
              MIN(first_chart_date)::text AS first_chart_date,
              MAX(latest_chart_date)::text AS latest_chart_date,
              COALESCE(MAX(max_simultaneous_hot100), 0)::int AS max_simultaneous_hot100
       FROM artist_stats
       WHERE artist_id = ANY($1::int[])`,
      [artistGroup.artistIds],
    ),
    sql.query(
      `SELECT *
       FROM (
         SELECT DISTINCT ON (s.id)
                s.id,
                s.title,
                s.artist_credit,
                ss.peak_position,
                ss.total_weeks,
                ss.weeks_at_peak,
                ss.weeks_at_number_one,
                ss.debut_date::text AS debut_date,
                ss.last_date::text AS last_date,
                ss.debut_position
         FROM song_artists sa
         JOIN songs s ON sa.song_id = s.id
         LEFT JOIN song_stats ss ON s.id = ss.song_id
         WHERE sa.artist_id = ANY($1::int[])
         ORDER BY s.id, CASE WHEN sa.role = 'primary' THEN 0 ELSE 1 END, sa.artist_id
       ) songs_for_artist
       ORDER BY debut_date ASC NULLS LAST, title ASC`,
      [artistGroup.artistIds],
    ),
    sql.query(
      `SELECT *
       FROM (
         SELECT DISTINCT ON (a.id)
                a.id,
                a.title,
                a.artist_credit,
                als.peak_position,
                als.total_weeks,
                als.weeks_at_peak,
                als.weeks_at_number_one,
                als.debut_date::text AS debut_date,
                als.last_date::text AS last_date,
                als.debut_position
         FROM album_artists aa
         JOIN albums a ON aa.album_id = a.id
         LEFT JOIN album_stats als ON a.id = als.album_id
         WHERE aa.artist_id = ANY($1::int[])
         ORDER BY a.id, CASE WHEN aa.role = 'primary' THEN 0 ELSE 1 END, aa.artist_id
       ) albums_for_artist
       ORDER BY debut_date ASC NULLS LAST, title ASC`,
      [artistGroup.artistIds],
    ),
  ]);

  const artistRow = artistRows[0];
  if (!artistRow) {
    return null;
  }

  const statsRow = statsRows[0];
  const statsCount = (statsRow?.stats_count as number | undefined) ?? 0;

  return {
    artist: {
      id: artistRow.id as number,
      name: artistRow.name as string,
      image_url: (artistRow.image_url as string | null) ?? null,
    },
    stats: statsCount > 0
      ? {
          artist_id: artistGroup.canonical.id,
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
      last_date: toIsoDate(row.last_date),
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
      last_date: toIsoDate(row.last_date),
      debut_position: (row.debut_position as number | null) ?? null,
    })),
  };
}
