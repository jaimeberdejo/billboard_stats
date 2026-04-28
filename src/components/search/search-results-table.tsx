"use client";

import { useRouter } from "next/navigation";

import type {
  SearchAlbumRow,
  SearchArtistRow,
  SearchSongRow,
} from "@/lib/search";

type SearchTab = "Songs" | "Albums" | "Artists";

interface SearchResultsTableProps {
  tab: SearchTab;
  rows: SearchSongRow[] | SearchAlbumRow[] | SearchArtistRow[];
}

export function SearchResultsTable({ tab, rows }: SearchResultsTableProps) {
  const router = useRouter();

  if (tab === "Artists") {
    const artistRows = rows as SearchArtistRow[];

    return (
      <div className="overflow-hidden rounded border border-black/10 bg-white">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-black/10 bg-white">
                {["NAME", "SONGS", "ALBUMS", "#1 SNG", "#1 ALB"].map((heading) => (
                  <th
                    key={heading}
                    className="px-3 py-2 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]"
                  >
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {artistRows.map((artist) => (
                <tr
                  key={artist.id}
                  className="cursor-pointer border-b border-black/10 bg-white last:border-b-0 hover:bg-[#F5F5F5]"
                  onClick={() => router.push(`/artist/${artist.id}`)}
                >
                  <td className="px-3 py-2 text-[12px] font-[600] leading-[1.3] text-[#0A0A0A]">
                    {artist.name}
                  </td>
                  <td className="px-3 py-2 text-[12px] text-[#0A0A0A]">
                    {artist.total_hot100_songs}
                  </td>
                  <td className="px-3 py-2 text-[12px] text-[#0A0A0A]">
                    {artist.total_b200_albums}
                  </td>
                  <td
                    className={[
                      "px-3 py-2 text-[12px] text-[#0A0A0A]",
                      artist.hot100_number_ones > 0 ? "font-[700] text-[#C8102E]" : "",
                    ].join(" ")}
                  >
                    {artist.hot100_number_ones}
                  </td>
                  <td
                    className={[
                      "px-3 py-2 text-[12px] text-[#0A0A0A]",
                      artist.b200_number_ones > 0 ? "font-[700] text-[#C8102E]" : "",
                    ].join(" ")}
                  >
                    {artist.b200_number_ones}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  const detailRows = rows as Array<SearchSongRow | SearchAlbumRow>;
  const routeBase = tab === "Songs" ? "/song" : "/album";

  return (
    <div className="overflow-hidden rounded border border-black/10 bg-white">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-black/10 bg-white">
              {["TITLE", "ARTIST", "PK", "WKS", "WKS@PK"].map((heading) => (
                <th
                  key={heading}
                  className="px-3 py-2 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]"
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {detailRows.map((row) => (
              <tr
                key={row.id}
                className="cursor-pointer border-b border-black/10 bg-white last:border-b-0 hover:bg-[#F5F5F5]"
                onClick={() => router.push(`${routeBase}/${row.id}`)}
              >
                <td className="px-3 py-2 text-[12px] font-[600] leading-[1.3] text-[#0A0A0A]">
                  {row.title}
                </td>
                <td className="px-3 py-2 text-[12px] leading-[1.45] text-[#888888]">
                  {row.artist_credit}
                </td>
                <td
                  className={[
                    "px-3 py-2 text-[12px] text-[#0A0A0A]",
                    row.peak_position === 1 ? "font-[700] text-[#C8102E]" : "",
                  ].join(" ")}
                >
                  {row.peak_position ?? "—"}
                </td>
                <td className="px-3 py-2 text-[12px] text-[#0A0A0A]">{row.total_weeks}</td>
                <td className="px-3 py-2 text-[12px] text-[#0A0A0A]">{row.weeks_at_peak}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
