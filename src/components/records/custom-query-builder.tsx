"use client";

import { useState } from "react";

import type { CustomEntity, CustomRankBy } from "@/lib/records";

export interface CustomQueryState {
  entity: CustomEntity;
  chartContext: "hot-100" | "billboard-200";
  sortDir: "asc" | "desc";
  rankBy: CustomRankBy;
  rankByParam: number;
  artistNames: string;
  peakMin: number;
  peakMax: number;
  weeksMin: string;
  debutPosMin: number;
  debutPosMax: number;
}

interface CustomQueryBuilderProps {
  state: CustomQueryState;
  onChange: (nextState: CustomQueryState) => void;
}

const TOP_RANGE_OPTIONS = [3, 5, 10, 40] as const;
const MIN_WEEKS_OPTIONS = [
  { label: "any", value: "" },
  { label: "10+", value: "10" },
  { label: "20+", value: "20" },
  { label: "40+", value: "40" },
  { label: "52+", value: "52" },
] as const;

export function CustomQueryBuilder({
  state,
  onChange,
}: CustomQueryBuilderProps) {
  const [filtersOpen, setFiltersOpen] = useState(false);
  const entityChart =
    state.entity === "songs"
      ? "hot-100"
      : state.entity === "albums"
        ? "billboard-200"
        : state.chartContext;
  const chartMax = entityChart === "hot-100" ? 100 : 200;
  const showRankParam =
    state.rankBy === "weeks-at-position" || state.rankBy === "weeks-in-top-n";
  const showPositionFilters = state.entity !== "artists";
  const entityLabel = state.entity;

  const entityOptions: Array<{ label: string; value: CustomEntity }> = [
    { label: "Songs", value: "songs" },
    { label: "Albums", value: "albums" },
    { label: "Artists", value: "artists" },
  ];

  const rankOptions: Array<{ label: string; value: CustomRankBy }> =
    state.entity === "artists"
      ? [
          { label: "total chart weeks", value: "total-weeks" },
          { label: "most entries", value: "most-entries" },
          {
            label: entityChart === "hot-100" ? "most #1 songs" : "most #1 albums",
            value: "number-one-entries",
          },
        ]
      : [
          { label: "#1 rank", value: "weeks-at-number-one" },
          { label: "specific position", value: "weeks-at-position" },
          { label: "top range", value: "weeks-in-top-n" },
          { label: "total weeks on chart", value: "total-weeks" },
        ];

  const update = <Key extends keyof CustomQueryState>(
    key: Key,
    value: CustomQueryState[Key],
  ) => {
    onChange({
      ...state,
      [key]: value,
    });
  };

  const clamp = (value: number) => Math.max(1, Math.min(chartMax, value));

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded border border-black/10 bg-[#FAFAFA] px-4 py-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="min-w-[220px]">
            <span className="mb-1 block text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
              Mode
            </span>
            <div className="inline-flex overflow-hidden rounded border border-black/10 bg-white">
              {entityOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() =>
                    onChange((() => {
                      const nextChartMax = option.value === "albums" ? 200 : 100;
                      return {
                        ...state,
                        entity: option.value,
                        rankBy:
                          option.value === "artists"
                            ? "total-weeks"
                            : "weeks-at-number-one",
                        rankByParam:
                          option.value === "artists"
                            ? 10
                            : Math.min(state.rankByParam, nextChartMax),
                        peakMin: Math.min(state.peakMin, nextChartMax),
                        peakMax: Math.min(state.peakMax, nextChartMax),
                        debutPosMin: Math.min(state.debutPosMin, nextChartMax),
                        debutPosMax: Math.min(state.debutPosMax, nextChartMax),
                      };
                    })())
                  }
                  className={[
                    "min-w-[72px] border-r border-black/10 px-3 py-2 text-[11px] font-[600] tracking-[0.08em] last:border-r-0",
                    state.entity === option.value
                      ? "bg-[#C8102E] text-white"
                      : "bg-transparent text-[#0A0A0A] hover:bg-[#F5F5F5]",
                  ].join(" ")}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {state.entity === "artists" ? (
            <div className="min-w-[180px]">
              <span className="mb-1 block text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
                Chart
              </span>
              <div className="inline-flex overflow-hidden rounded border border-black/10 bg-white">
                {([
                  { value: "hot-100", label: "HOT 100" },
                  { value: "billboard-200", label: "B200" },
                ] as const).map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => update("chartContext", option.value)}
                    className={[
                      "min-w-[78px] border-r border-black/10 px-3 py-2 text-[11px] font-[600] tracking-[0.08em] last:border-r-0",
                      state.chartContext === option.value
                        ? "bg-[#C8102E] text-white"
                        : "bg-transparent text-[#0A0A0A] hover:bg-[#F5F5F5]",
                    ].join(" ")}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <label className="min-w-[160px] flex-1">
            <span className="mb-1 block text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
              {state.entity === "artists" ? "Artist name" : "Artist"}
            </span>
            <input
              value={state.artistNames}
              onChange={(event) => update("artistNames", event.target.value)}
              placeholder="e.g. Drake, Taylor Swift"
              className="w-full rounded border border-black/10 bg-white px-3 py-2 text-[12px] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
            />
          </label>

          <label className="min-w-[100px]">
            <span className="mb-1 block text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
              Min. chart weeks
            </span>
            <select
              value={state.weeksMin}
              onChange={(event) => update("weeksMin", event.target.value)}
              className="w-[92px] rounded border border-black/10 bg-white px-3 py-2 text-[12px] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
            >
              {MIN_WEEKS_OPTIONS.map((option) => (
                <option key={option.label} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          {showPositionFilters ? (
            <div>
              <span className="mb-1 block text-[11px] font-[600] uppercase tracking-[0.08em] text-transparent">
                Filters
              </span>
              <button
                type="button"
                onClick={() => setFiltersOpen((current) => !current)}
                className="rounded border border-black/10 bg-white px-3 py-2 text-[11px] font-[600] text-[#555555] transition hover:border-[#C8102E] hover:text-[#0A0A0A]"
              >
                {filtersOpen ? "▲ Fewer filters" : "▼ More filters"}
              </button>
            </div>
          ) : null}
        </div>

        {filtersOpen && showPositionFilters ? (
          <div className="mt-4 flex flex-wrap gap-6 border-t border-black/10 pt-4">
            <div className="min-w-[240px] flex-1">
              <div className="mb-2 text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
                Best peak — between #{state.peakMin} and #{state.peakMax}
              </div>
              <div className="flex items-center gap-2">
                <span className="min-w-[12px] text-[10px] text-[#AAAAAA]">1</span>
                <input
                  type="range"
                  min={1}
                  max={chartMax}
                  value={state.peakMin}
                  onChange={(event) =>
                    update("peakMin", Math.min(clamp(Number(event.target.value) || 1), state.peakMax))
                  }
                  className="flex-1 accent-[#C8102E]"
                />
                <input
                  type="range"
                  min={1}
                  max={chartMax}
                  value={state.peakMax}
                  onChange={(event) =>
                    update("peakMax", Math.max(clamp(Number(event.target.value) || chartMax), state.peakMin))
                  }
                  className="flex-1 accent-[#C8102E]"
                />
                <span className="min-w-[20px] text-[10px] text-[#AAAAAA]">{chartMax}</span>
              </div>
            </div>

            <div className="min-w-[240px] flex-1">
              <div className="mb-2 text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
                Debut position — between #{state.debutPosMin} and #{state.debutPosMax}
              </div>
              <div className="flex items-center gap-2">
                <span className="min-w-[12px] text-[10px] text-[#AAAAAA]">1</span>
                <input
                  type="range"
                  min={1}
                  max={chartMax}
                  value={state.debutPosMin}
                  onChange={(event) =>
                    update(
                      "debutPosMin",
                      Math.min(clamp(Number(event.target.value) || 1), state.debutPosMax),
                    )
                  }
                  className="flex-1 accent-[#C8102E]"
                />
                <input
                  type="range"
                  min={1}
                  max={chartMax}
                  value={state.debutPosMax}
                  onChange={(event) =>
                    update(
                      "debutPosMax",
                      Math.max(clamp(Number(event.target.value) || chartMax), state.debutPosMin),
                    )
                  }
                  className="flex-1 accent-[#C8102E]"
                />
                <span className="min-w-[20px] text-[10px] text-[#AAAAAA]">{chartMax}</span>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      <div className="rounded-r-[6px] rounded-l-none border border-[#E0E0E0] border-l-[3px] border-l-[#C8102E] bg-white px-4 py-3">
        <div className="flex flex-wrap items-center gap-x-1 gap-y-2 text-[14px] leading-[2] text-[#333333]">
          <span>Show me</span>
          <strong>{entityLabel}</strong>
          <span>with the</span>
          <select
            value={state.sortDir}
            onChange={(event) => update("sortDir", event.target.value as "asc" | "desc")}
            className="rounded border border-black/10 bg-white px-2 py-1 text-[12px] font-[600] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
          >
            <option value="desc">most weeks</option>
            <option value="asc">least weeks</option>
          </select>
          <span>weeks at:</span>
          <select
            value={state.rankBy}
            onChange={(event) => update("rankBy", event.target.value as CustomRankBy)}
            className="rounded border border-black/10 bg-white px-2 py-1 text-[12px] font-[600] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
          >
            {rankOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {showRankParam && state.entity !== "artists" ? (
            <>
              <span className="text-[#888888]">
                {state.rankBy === "weeks-at-position" ? "position #" : "top"}
              </span>
              {state.rankBy === "weeks-in-top-n" ? (
                <select
                  value={String(state.rankByParam)}
                  onChange={(event) =>
                    update("rankByParam", clamp(Number(event.target.value) || 10))
                  }
                  className="rounded border border-[#C8102E] bg-[#FFF0F0] px-2 py-1 text-[12px] font-[700] text-[#C8102E] outline-none"
                >
                  {TOP_RANGE_OPTIONS.filter((option) => option <= chartMax).map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="number"
                  min={1}
                  max={chartMax}
                  value={state.rankByParam}
                  onChange={(event) =>
                    update("rankByParam", clamp(Number(event.target.value) || 1))
                  }
                  className="w-16 rounded border border-[#C8102E] bg-[#FFF0F0] px-2 py-1 text-center text-[12px] font-[700] text-[#C8102E] outline-none"
                />
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
