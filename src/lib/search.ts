import { getSql } from "@/lib/db";

export interface SearchSongRow {
  id: number;
  title: string;
  artist_credit: string;
  peak_position: number | null;
  total_weeks: number;
  weeks_at_peak: number;
}

export interface SearchAlbumRow {
  id: number;
  title: string;
  artist_credit: string;
  peak_position: number | null;
  total_weeks: number;
  weeks_at_peak: number;
}

export interface SearchArtistRow {
  id: number;
  name: string;
  total_hot100_songs: number;
  total_b200_albums: number;
  hot100_number_ones: number;
  b200_number_ones: number;
}

export interface SearchResultsPayload {
  query: string;
  songs: SearchSongRow[];
  albums: SearchAlbumRow[];
  artists: SearchArtistRow[];
}

const SEARCH_LIMIT = 50;

function normalizeQuery(query: string): string {
  return query.trim();
}

export async function searchAll(query: string): Promise<SearchResultsPayload> {
  const normalized = normalizeQuery(query);
  if (normalized.length < 2) {
    return {
      query: normalized,
      songs: [],
      albums: [],
      artists: [],
    };
  }

  const sql = getSql();
  const [songRows, albumRows, artistRows] = await Promise.all([
    sql.query(
      `SELECT s.id,
              s.title,
              s.artist_credit,
              ss.peak_position,
              ss.total_weeks,
              ss.weeks_at_peak,
              similarity(s.title, $1) AS sim
       FROM songs s
       LEFT JOIN song_stats ss ON s.id = ss.song_id
       WHERE s.title % $1
       ORDER BY sim DESC, s.title ASC
       LIMIT $2`,
      [normalized, SEARCH_LIMIT],
    ),
    sql.query(
      `SELECT a.id,
              a.title,
              a.artist_credit,
              als.peak_position,
              als.total_weeks,
              als.weeks_at_peak,
              similarity(a.title, $1) AS sim
       FROM albums a
       LEFT JOIN album_stats als ON a.id = als.album_id
       WHERE a.title % $1
       ORDER BY sim DESC, a.title ASC
       LIMIT $2`,
      [normalized, SEARCH_LIMIT],
    ),
    sql.query(
      `SELECT a.id,
              a.name,
              ast.total_hot100_songs,
              ast.total_b200_albums,
              ast.hot100_number_ones,
              ast.b200_number_ones,
              similarity(a.name, $1) AS sim
       FROM artists a
       LEFT JOIN artist_stats ast ON a.id = ast.artist_id
       WHERE a.name % $1
       ORDER BY sim DESC, a.name ASC
       LIMIT $2`,
      [normalized, SEARCH_LIMIT],
    ),
  ]);

  return {
    query: normalized,
    songs: songRows.map((row) => ({
      id: row.id as number,
      title: row.title as string,
      artist_credit: row.artist_credit as string,
      peak_position: (row.peak_position as number | null) ?? null,
      total_weeks: (row.total_weeks as number) ?? 0,
      weeks_at_peak: (row.weeks_at_peak as number) ?? 0,
    })),
    albums: albumRows.map((row) => ({
      id: row.id as number,
      title: row.title as string,
      artist_credit: row.artist_credit as string,
      peak_position: (row.peak_position as number | null) ?? null,
      total_weeks: (row.total_weeks as number) ?? 0,
      weeks_at_peak: (row.weeks_at_peak as number) ?? 0,
    })),
    artists: artistRows.map((row) => ({
      id: row.id as number,
      name: row.name as string,
      total_hot100_songs: (row.total_hot100_songs as number) ?? 0,
      total_b200_albums: (row.total_b200_albums as number) ?? 0,
      hot100_number_ones: (row.hot100_number_ones as number) ?? 0,
      b200_number_ones: (row.b200_number_ones as number) ?? 0,
    })),
  };
}
