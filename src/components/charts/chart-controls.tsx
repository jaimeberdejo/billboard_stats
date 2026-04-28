"use client";

import type { ChartType } from "@/lib/charts";

interface ChartControlsProps {
  availableDates: string[];
  chartType: ChartType;
  entryCount: number;
  isPending: boolean;
  selectedDate: string;
  onChartTypeChange: (chartType: ChartType) => void;
  onDateChange: (date: string) => void;
}

function formatChartDate(value: string): string {
  if (!value) {
    return "No dates";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function ChartControls({
  availableDates,
  chartType,
  entryCount,
  isPending,
  selectedDate,
  onChartTypeChange,
  onDateChange,
}: ChartControlsProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-black/10 pb-3">
      <div className="inline-flex overflow-hidden rounded border border-black/10 bg-[#F5F5F5]">
        {([
          { value: "hot-100", label: "HOT 100" },
          { value: "billboard-200", label: "B200" },
        ] as const).map((option) => {
          const active = option.value === chartType;

          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onChartTypeChange(option.value)}
              aria-pressed={active}
              className={[
                "min-w-[78px] border-r border-black/10 px-3 py-1.5 text-[11px] font-[600] tracking-[0.08em] transition-colors last:border-r-0",
                active
                  ? "bg-[#C8102E] text-white"
                  : "bg-transparent text-[#0A0A0A] hover:bg-white",
              ].join(" ")}
            >
              {option.label}
            </button>
          );
        })}
      </div>

      <label className="sr-only" htmlFor="chart-week-select">
        Chart week
      </label>
      <select
        id="chart-week-select"
        value={selectedDate}
        onChange={(event) => onDateChange(event.target.value)}
        disabled={isPending || availableDates.length === 0}
        className="min-w-[154px] rounded border border-black/10 bg-white px-2 py-1.5 text-[11px] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
      >
        {availableDates.map((date) => (
          <option key={date} value={date}>
            {formatChartDate(date)}
          </option>
        ))}
      </select>

      <span className="ml-auto text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
        {isPending ? "Loading..." : `${entryCount} entries`}
      </span>
    </div>
  );
}
