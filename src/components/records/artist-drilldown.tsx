"use client";

import { useRouter } from "next/navigation";

import type { DrilldownPayload } from "@/lib/records";

interface ArtistDrilldownProps {
  payload: DrilldownPayload | null;
}

export function ArtistDrilldown({ payload }: ArtistDrilldownProps) {
  const router = useRouter();

  if (!payload) {
    return null;
  }

  if (payload.unsupportedMessage) {
    return (
      <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-4 text-[12px] leading-[1.45] text-[#888888]">
        {payload.unsupportedMessage}
      </div>
    );
  }

  if (payload.rows.length === 0) {
    return (
      <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-4 text-[12px] leading-[1.45] text-[#888888]">
        No items found.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded border border-black/10 bg-white">
      <div className="divide-y divide-black/10">
        {payload.rows.map((row) => {
          const href = row.song_id ? `/song/${row.song_id}` : `/album/${row.album_id}`;

          return (
            <button
              key={`${href}-${row.rank}`}
              type="button"
              onClick={() => router.push(href)}
              className="flex w-full items-center gap-3 px-3 py-3 text-left transition-colors hover:bg-[#F5F5F5]"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12px] font-[600] leading-[1.3] text-[#0A0A0A]">
                  {row.title}
                </div>
                <div className="mt-0.5 truncate text-[12px] leading-[1.45] text-[#888888]">
                  {row.artist_credit}
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div className="text-[14px] font-[700] leading-[1.1] text-[#0A0A0A]">
                  {row.value}
                </div>
                <div className="mt-0.5 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
                  {payload.valueLabel}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
