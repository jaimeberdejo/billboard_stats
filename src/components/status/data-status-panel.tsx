import type { DataSummary } from "@/lib/data-status";

interface DataStatusPanelProps {
  summary: DataSummary | null;
  error: string | null;
}

const COUNT_ROWS: Array<keyof DataSummary["counts"]> = [
  "chart_weeks",
  "hot100_entries",
  "b200_entries",
  "songs",
  "albums",
  "artists",
  "song_stats",
  "album_stats",
  "artist_stats",
];

function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatDate(value: string | undefined): string {
  if (!value) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function DataStatusPanel({ summary, error }: DataStatusPanelProps) {
  const latestDates = summary?.latestDates ?? {};
  const counts = summary?.counts;

  const stats = [
    { label: "Hot 100 Latest", value: formatDate(latestDates["hot-100"]) },
    { label: "B200 Latest", value: formatDate(latestDates["billboard-200"]) },
    {
      label: "Coverage",
      value:
        latestDates["hot-100"] || latestDates["billboard-200"]
          ? `1958–${new Date(
              `${latestDates["hot-100"] ?? latestDates["billboard-200"]}T00:00:00Z`,
            ).getUTCFullYear()}`
          : "—",
    },
    { label: "Weeks Loaded", value: counts ? formatCount(counts.chart_weeks) : "—" },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded border border-black/10 bg-black/10 sm:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="bg-white px-3 py-3">
            <p className="text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
              {stat.label}
            </p>
            <p className="mt-2 text-[14px] font-[700] leading-[1.1] text-[#0A0A0A]">
              {stat.value}
            </p>
          </div>
        ))}
      </div>

      <div className="overflow-hidden rounded border border-black/10 bg-white">
        <table className="min-w-full border-collapse">
          <tbody>
            {COUNT_ROWS.map((key) => (
              <tr key={key} className="border-b border-black/10 last:border-b-0">
                <td className="px-3 py-2 text-[12px] leading-[1.45] text-[#0A0A0A]">
                  {key}
                </td>
                <td className="px-3 py-2 text-right text-[12px] leading-[1.45] text-[#0A0A0A]">
                  {counts ? formatCount(counts[key]) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {error ? (
        <p className="text-[12px] leading-[1.45] text-[#C8102E]">{error}</p>
      ) : null}
    </div>
  );
}
