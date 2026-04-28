import type { ChartEntry } from "@/lib/charts";

interface ChartTableProps {
  chartType: "hot-100" | "billboard-200";
  entries: ChartEntry[];
}

function getMovement(entry: ChartEntry): {
  label: string;
  tone: string;
} {
  if (entry.is_new) {
    return {
      label: "NEW",
      tone: "bg-[#C8102E] text-white",
    };
  }

  if (!entry.last_pos || entry.last_pos <= 0) {
    return {
      label: "RE",
      tone: "border border-[#C8102E]/20 bg-[#FCEDEE] text-[#C8102E]",
    };
  }

  const delta = entry.last_pos - entry.rank;
  if (delta > 0) {
    return {
      label: `▲${delta}`,
      tone: "text-[#16A34A]",
    };
  }

  if (delta < 0) {
    return {
      label: `▼${Math.abs(delta)}`,
      tone: "text-[#DC2626]",
    };
  }

  return {
    label: "•",
    tone: "text-[#AAAAAA]",
  };
}

function lastWeekLabel(entry: ChartEntry): string {
  if (entry.is_new || !entry.last_pos || entry.last_pos <= 0) {
    return "—";
  }

  return String(entry.last_pos);
}

export function ChartTable({ chartType, entries }: ChartTableProps) {
  return (
    <div className="overflow-hidden rounded border border-black/10 bg-white">
      <div className="max-h-[calc(100vh-14rem)] overflow-auto">
        <table className="min-w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-black/10 bg-white">
              {["POS", "MV", "TITLE / ARTIST", "LW", "PK", "WKS"].map((heading, index) => (
                <th
                  key={heading}
                  className={[
                    "sticky top-0 z-10 bg-white px-3 py-2 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888] sm:top-11",
                    index > 2 ? "text-right" : "",
                  ].join(" ")}
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => {
              const movement = getMovement(entry);
              const key = `${chartType}-${entry.rank}-${entry.song_id ?? entry.album_id ?? entry.title}`;

              return (
                <tr
                  key={key}
                  className="cursor-default border-b border-black/10 bg-white transition-colors hover:bg-[#F5F5F5] last:border-b-0"
                >
                  <td className="px-3 py-2 align-top">
                    <span
                      className={[
                        "text-[15px] font-[700] leading-[1.1] text-[#0A0A0A]",
                        entry.rank === 1 ? "text-[#C8102E]" : "",
                      ].join(" ")}
                    >
                      {entry.rank}
                    </span>
                  </td>
                  <td className="px-3 py-2 align-top">
                    <span
                      className={[
                        "inline-flex min-h-6 min-w-10 items-center justify-center rounded px-1.5 text-[10px] font-[700] uppercase tracking-[0.08em]",
                        movement.tone,
                      ].join(" ")}
                    >
                      {movement.label}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="text-[12px] font-[600] leading-[1.3] text-[#0A0A0A]">
                      {entry.title}
                    </div>
                    <div className="mt-0.5 text-[12px] leading-[1.45] text-[#888888]">
                      {entry.artist_credit}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right text-[12px] text-[#0A0A0A]">
                    {lastWeekLabel(entry)}
                  </td>
                  <td
                    className={[
                      "px-3 py-2 text-right text-[12px] text-[#0A0A0A]",
                      entry.peak_pos === 1 ? "font-[700] text-[#C8102E]" : "",
                    ].join(" ")}
                  >
                    {entry.peak_pos ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right text-[12px] text-[#0A0A0A]">
                    {entry.weeks_on_chart ?? "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
