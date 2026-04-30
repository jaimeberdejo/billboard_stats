"use client";

import { useRef } from "react";

import type { ChartType } from "@/lib/charts";

interface ChartControlsProps {
  availableDates: string[];
  chartType: ChartType;
  entryCount: number;
  isPending: boolean;
  latestDate: string;
  nextDate: string | null;
  previousDate: string | null;
  selectedDate: string;
  onChartTypeChange: (chartType: ChartType) => void;
  onDateChange: (date: string) => void;
  onDateSearch: (value: string) => void;
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
  latestDate,
  nextDate,
  previousDate,
  selectedDate,
  onChartTypeChange,
  onDateChange,
  onDateSearch,
}: ChartControlsProps) {
  const dateInputRef = useRef<HTMLInputElement | null>(null);

  return (
    <div className="flex flex-col gap-3 border-b border-black/10 pb-3">
      <div className="flex flex-wrap items-center gap-2">
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

        <div className="ml-auto text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          {isPending ? "Loading..." : `${entryCount} entries`}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => previousDate && onDateChange(previousDate)}
          disabled={isPending || !previousDate}
          className="rounded border border-black/10 bg-white px-3 py-1.5 text-[11px] font-[600] uppercase tracking-[0.08em] text-[#0A0A0A] transition hover:border-[#C8102E] hover:text-[#C8102E] disabled:cursor-not-allowed disabled:opacity-40"
        >
          Prev Week
        </button>

        <button
          type="button"
          onClick={() => nextDate && onDateChange(nextDate)}
          disabled={isPending || !nextDate}
          className="rounded border border-black/10 bg-white px-3 py-1.5 text-[11px] font-[600] uppercase tracking-[0.08em] text-[#0A0A0A] transition hover:border-[#C8102E] hover:text-[#C8102E] disabled:cursor-not-allowed disabled:opacity-40"
        >
          Next Week
        </button>

        <label className="sr-only" htmlFor="chart-week-input">
          Jump to chart week
        </label>
        <input
          key={selectedDate}
          id="chart-week-input"
          list="chart-week-suggestions"
          defaultValue={selectedDate}
          ref={dateInputRef}
          placeholder="1990 or 1990-05-12"
          disabled={isPending || availableDates.length === 0}
          className="min-w-[190px] flex-1 rounded border border-black/10 bg-white px-2 py-1.5 text-[11px] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
        />
        <datalist id="chart-week-suggestions">
          {availableDates.map((date) => (
            <option key={date} value={date}>
              {formatChartDate(date)}
            </option>
          ))}
        </datalist>

        <button
          type="button"
          onClick={() => onDateSearch(dateInputRef.current?.value ?? selectedDate)}
          disabled={isPending || availableDates.length === 0}
          className="rounded bg-[#C8102E] px-3 py-1.5 text-[11px] font-[600] uppercase tracking-[0.08em] text-white transition hover:bg-[#A50E26] disabled:cursor-not-allowed disabled:opacity-40"
        >
          Go
        </button>
      </div>

      <div className="text-[11px] leading-[1.45] text-[#888888]">
        Viewing {formatChartDate(selectedDate)}. Jump by year or exact date. Latest available week:{" "}
        {formatChartDate(latestDate)}.
      </div>

    </div>
  );
}
