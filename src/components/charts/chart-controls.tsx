"use client";

import { useMemo, useRef } from "react";

import type { ChartRegistryRow, ChartType } from "@/lib/charts";
import { FAMILY_ORDER, type ChartFamily } from "@/lib/chart-families";

interface ChartControlsProps {
  availableDates: string[];
  charts: ChartRegistryRow[];
  chartType: ChartType;
  /** Resolved active-chart title for the Latest Charts attribution line. */
  chartTitle: string;
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

/** Human-facing label for each family row tab. */
const FAMILY_LABEL: Record<ChartFamily, string> = {
  Core: "Hot 100 / Billboard 200",
  Artist: "Artist 100",
  Country: "Country",
  Latin: "Latin",
  "R&B/Hip-Hop": "R&B/Hip-Hop",
  Rock: "Rock",
};

/**
 * Abbreviated, space-constrained chart labels for the Row-2 segmented control.
 * The full registry title is always supplied as the button's accessible name, so
 * the abbreviation never costs AT users the real chart name.
 */
const CHART_ABBREV: Record<string, string> = {
  "hot-100": "HOT 100",
  "billboard-200": "B200",
};

function chartLabel(row: ChartRegistryRow): string {
  return CHART_ABBREV[row.slug] ?? (row.title ?? row.slug);
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
  charts,
  chartType,
  chartTitle,
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

  // Group the registry list into families in the shared FAMILY_ORDER so the
  // family row and the chart row render in a stable, predictable sequence.
  const familyGroups = useMemo(() => {
    const byFamily = new Map<ChartFamily, ChartRegistryRow[]>();
    for (const row of charts) {
      const bucket = byFamily.get(row.family);
      if (bucket) {
        bucket.push(row);
      } else {
        byFamily.set(row.family, [row]);
      }
    }
    for (const bucket of byFamily.values()) {
      bucket.sort((a, b) => a.sort_order - b.sort_order);
    }
    return FAMILY_ORDER.filter((family) => byFamily.has(family)).map((family) => ({
      family,
      label: FAMILY_LABEL[family],
      charts: byFamily.get(family) ?? [],
    }));
  }, [charts]);

  // Determine the active family from the currently-selected chart slug.
  const activeFamily = useMemo<ChartFamily | null>(() => {
    const match = charts.find((row) => row.slug === chartType);
    return match?.family ?? familyGroups[0]?.family ?? null;
  }, [charts, chartType, familyGroups]);

  // Row 2 only renders when the active family has more than one chart.
  const activeFamilyCharts = useMemo<ChartRegistryRow[]>(() => {
    const group = familyGroups.find((g) => g.family === activeFamily);
    return group?.charts ?? [];
  }, [familyGroups, activeFamily]);

  const handleFamilySelect = (family: ChartFamily) => {
    if (family === activeFamily) {
      return;
    }
    const group = familyGroups.find((g) => g.family === family);
    const firstChart = group?.charts[0];
    if (firstChart) {
      onChartTypeChange(firstChart.slug);
    }
  };

  return (
    <div className="flex flex-col gap-3 border-b border-black/10 pb-3">
      <div className="flex flex-wrap items-center gap-2">
        {/* Row 1 — genre-family tabs */}
        <div
          role="group"
          aria-label="Chart family"
          className="inline-flex max-w-full overflow-x-auto overflow-y-hidden rounded border border-black/10 bg-[#F5F5F5]"
        >
          {familyGroups.map((group) => {
            const active = group.family === activeFamily;

            return (
              <button
                key={group.family}
                type="button"
                onClick={() => handleFamilySelect(group.family)}
                aria-pressed={active}
                aria-label={group.label}
                className={[
                  "whitespace-nowrap border-r border-black/10 px-3 py-1.5 text-[11px] font-[600] tracking-[0.08em] transition-colors last:border-r-0",
                  active
                    ? "bg-[#C8102E] text-white"
                    : "bg-transparent text-[#0A0A0A] hover:bg-white",
                ].join(" ")}
              >
                {group.label}
              </button>
            );
          })}
        </div>

        <div className="ml-auto text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          {isPending ? "Loading..." : `${entryCount} entries`}
        </div>
      </div>

      {/* Row 2 — specific-chart selector (only when the active family has >1 chart) */}
      {activeFamilyCharts.length > 1 ? (
        <div
          role="group"
          aria-label="Chart"
          className="inline-flex w-fit max-w-full flex-wrap overflow-hidden rounded border border-black/10 bg-[#F5F5F5]"
        >
          {activeFamilyCharts.map((row) => {
            const active = row.slug === chartType;

            return (
              <button
                key={row.slug}
                type="button"
                onClick={() => onChartTypeChange(row.slug)}
                aria-pressed={active}
                aria-label={row.title ?? row.slug}
                className={[
                  "min-w-[72px] border-r border-black/10 px-3 py-1.5 text-[11px] font-[600] tracking-[0.08em] transition-colors last:border-r-0",
                  active
                    ? "bg-[#C8102E] text-white"
                    : "bg-transparent text-[#0A0A0A] hover:bg-white",
                ].join(" ")}
              >
                {chartLabel(row)}
              </button>
            );
          })}
        </div>
      ) : null}

      <div className="flex flex-wrap items-end gap-2">
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

        <label className="flex min-w-[220px] flex-1 flex-col gap-1" htmlFor="chart-week-input">
          <span className="sr-only">Jump to chart week</span>
          <input
            key={selectedDate}
            id="chart-week-input"
            list="chart-week-suggestions"
            defaultValue={selectedDate}
            ref={dateInputRef}
            placeholder="Type a date: YYYY-MM-DD or year"
            disabled={isPending || availableDates.length === 0}
            className="w-full rounded border border-black/10 bg-white px-2 py-1.5 text-[11px] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
          />
        </label>
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
        Viewing {chartTitle} · {formatChartDate(selectedDate)}. Type an exact chart date or a year,
        then press Go. Latest available week: {formatChartDate(latestDate)}.
      </div>

    </div>
  );
}
