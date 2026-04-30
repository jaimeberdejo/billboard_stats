"use client";

import { useRouter } from "next/navigation";

import { ArtistDrilldown } from "@/components/records/artist-drilldown";
import type { DrilldownPayload, RecordLeaderboardRow } from "@/lib/records";

interface LeaderboardListProps {
  rows: RecordLeaderboardRow[];
  valueLabel: string;
  expandedRowKey: string | null;
  drilldownPayload?: DrilldownPayload | null;
  onRowClick: (row: RecordLeaderboardRow) => void;
}

export function LeaderboardList({
  rows,
  valueLabel,
  expandedRowKey,
  drilldownPayload,
  onRowClick,
}: LeaderboardListProps) {
  const router = useRouter();

  return (
    <div className="overflow-hidden rounded border border-black/10 bg-white">
      <div className="divide-y divide-black/10">
        {rows.map((row) => {
          const rowKey = `${row.artist_id ?? "row"}:${row.chart_date ?? "none"}`;
          const isExpanded = expandedRowKey === rowKey;
          const key = `${row.rank}-${row.title}-${row.artist_id ?? row.song_id ?? row.album_id ?? "row"}`;

          return (
            <div key={key}>
              <button
                type="button"
                onClick={() => {
                  if (row.artist_id) {
                    onRowClick(row);
                    return;
                  }
                  if (row.song_id) {
                    router.push(`/song/${row.song_id}`);
                    return;
                  }
                  if (row.album_id) {
                    router.push(`/album/${row.album_id}`);
                  }
                }}
                className="flex w-full items-center gap-3 px-3 py-3 text-left transition-colors hover:bg-[#F5F5F5]"
              >
                <div className="w-8 shrink-0 text-[12px] font-[700] leading-[1.1] text-[#888888]">
                  {row.rank}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12px] font-[600] leading-[1.3] text-[#0A0A0A]">
                    {row.title}
                    {row.artist_id ? (
                      <span className="ml-2 text-[10px] font-[600] text-[#BBBBBB]">
                        {isExpanded ? "▲" : "▼"}
                      </span>
                    ) : null}
                  </div>
                  {row.artist_credit ? (
                    <div className="mt-0.5 truncate text-[12px] leading-[1.45] text-[#888888]">
                      {row.artist_credit}
                    </div>
                  ) : null}
                  {row.chart_date ? (
                    <div className="mt-0.5 text-[11px] leading-[1.45] text-[#888888]">
                      {row.chart_date}
                    </div>
                  ) : null}
                </div>
                <div className="shrink-0 text-right">
                  <div className="text-[14px] font-[700] leading-[1.1] text-[#0A0A0A]">
                    {row.value}
                  </div>
                  <div className="mt-0.5 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
                    {valueLabel}
                  </div>
                </div>
              </button>

              {isExpanded ? <ArtistDrilldown payload={drilldownPayload ?? null} /> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
