import type { DetailChartRunPoint } from "@/lib/songs";

interface ChartHistoryTableProps {
  chartRun: DetailChartRunPoint[];
}

function getMovement(point: DetailChartRunPoint): { label: string; tone: string } {
  if (point.is_new) {
    return {
      label: "NEW",
      tone: "bg-[#C8102E] text-white",
    };
  }

  if (!point.last_pos || point.last_pos <= 0) {
    return {
      label: "RE",
      tone: "border border-[#C8102E]/20 bg-[#FCEDEE] text-[#C8102E]",
    };
  }

  const delta = point.last_pos - point.rank;
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

function formatWeek(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function formatLastWeek(point: DetailChartRunPoint): string {
  if (point.is_new || !point.last_pos || point.last_pos <= 0) {
    return "—";
  }

  return String(point.last_pos);
}

export function ChartHistoryTable({ chartRun }: ChartHistoryTableProps) {
  const rows = [...chartRun].reverse();

  return (
    <div className="overflow-hidden rounded border border-black/10 bg-white">
      <div className="max-h-[32rem] overflow-auto">
        <table className="min-w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-black/10 bg-white">
              {["Week", "Pos", "Mv", "Lw", "Pk", "Wks"].map((heading) => (
                <th
                  key={heading}
                  className="sticky top-0 z-10 bg-white px-3 py-2 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]"
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((point) => {
              const movement = getMovement(point);

              return (
                <tr
                  key={`${point.chart_date}-${point.rank}`}
                  className="border-b border-black/10 bg-white last:border-b-0 hover:bg-[#F5F5F5]"
                >
                  <td className="px-3 py-2 text-[12px] leading-[1.45] text-[#888888]">
                    {formatWeek(point.chart_date)}
                  </td>
                  <td
                    className={[
                      "px-3 py-2 text-[12px] text-[#0A0A0A]",
                      point.rank === 1 ? "font-[700] text-[#C8102E]" : "",
                    ].join(" ")}
                  >
                    {point.rank}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={[
                        "inline-flex min-h-6 min-w-10 items-center justify-center rounded px-1.5 text-[10px] font-[700] uppercase tracking-[0.08em]",
                        movement.tone,
                      ].join(" ")}
                    >
                      {movement.label}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-[12px] text-[#0A0A0A]">
                    {formatLastWeek(point)}
                  </td>
                  <td
                    className={[
                      "px-3 py-2 text-[12px] text-[#0A0A0A]",
                      point.peak_pos === 1 ? "font-[700] text-[#C8102E]" : "",
                    ].join(" ")}
                  >
                    {point.peak_pos ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-[12px] text-[#0A0A0A]">
                    {point.weeks_on_chart ?? "—"}
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
