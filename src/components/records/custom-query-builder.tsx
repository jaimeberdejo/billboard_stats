"use client";

type CustomRankBy =
  | "weeks-at-number-one"
  | "total-weeks"
  | "weeks-at-position"
  | "weeks-in-top-n";

export interface CustomQueryState {
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
  chart: "hot-100" | "billboard-200";
  state: CustomQueryState;
  onChange: (nextState: CustomQueryState) => void;
}

export function CustomQueryBuilder({
  chart,
  state,
  onChange,
}: CustomQueryBuilderProps) {
  const chartMax = chart === "hot-100" ? 100 : 200;
  const showRankParam =
    state.rankBy === "weeks-at-position" || state.rankBy === "weeks-in-top-n";
  const entityLabel = chart === "hot-100" ? "songs" : "albums";

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
        <div className="flex flex-wrap items-center gap-x-2 gap-y-3 text-[14px] leading-[1.8] text-[#333333]">
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
          <span>at</span>
          <select
            value={state.rankBy}
            onChange={(event) =>
              update("rankBy", event.target.value as CustomRankBy)
            }
            className="rounded border border-black/10 bg-white px-2 py-1 text-[12px] font-[600] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
          >
            <option value="weeks-at-number-one">#1 rank</option>
            <option value="weeks-at-position">specific position</option>
            <option value="weeks-in-top-n">top range</option>
            <option value="total-weeks">total weeks on chart</option>
          </select>
          {showRankParam ? (
            <>
              <span>{state.rankBy === "weeks-at-position" ? "position #" : "top"}</span>
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
            </>
          ) : null}
        </div>
      </div>

      <div className="grid gap-4 rounded border border-black/10 bg-white px-4 py-4 sm:grid-cols-2">
        <label className="flex flex-col gap-2 text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          Artists
          <input
            value={state.artistNames}
            onChange={(event) => update("artistNames", event.target.value)}
            placeholder="e.g. Drake, Taylor Swift"
            className="rounded border border-black/10 bg-white px-3 py-2 text-[12px] normal-case tracking-normal text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
          />
        </label>

        <label className="flex flex-col gap-2 text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          Min. chart weeks
          <input
            type="number"
            min={1}
            value={state.weeksMin}
            onChange={(event) => update("weeksMin", event.target.value)}
            placeholder="any"
            className="rounded border border-black/10 bg-white px-3 py-2 text-[12px] normal-case tracking-normal text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
          />
        </label>

        <div className="flex flex-col gap-2 text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          <span>Peak range</span>
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <input
              type="number"
              min={1}
              max={chartMax}
              value={state.peakMin}
              onChange={(event) =>
                update("peakMin", Math.min(clamp(Number(event.target.value) || 1), state.peakMax))
              }
              className="rounded border border-black/10 bg-white px-3 py-2 text-[12px] normal-case tracking-normal text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
            />
            <input
              type="number"
              min={1}
              max={chartMax}
              value={state.peakMax}
              onChange={(event) =>
                update("peakMax", Math.max(clamp(Number(event.target.value) || chartMax), state.peakMin))
              }
              className="rounded border border-black/10 bg-white px-3 py-2 text-[12px] normal-case tracking-normal text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
            />
          </div>
        </div>

        <div className="flex flex-col gap-2 text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          <span>Debut range</span>
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <input
              type="number"
              min={1}
              max={chartMax}
              value={state.debutPosMin}
              onChange={(event) =>
                update(
                  "debutPosMin",
                  Math.min(clamp(Number(event.target.value) || 1), state.debutPosMax),
                )
              }
              className="rounded border border-black/10 bg-white px-3 py-2 text-[12px] normal-case tracking-normal text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
            />
            <input
              type="number"
              min={1}
              max={chartMax}
              value={state.debutPosMax}
              onChange={(event) =>
                update(
                  "debutPosMax",
                  Math.max(clamp(Number(event.target.value) || chartMax), state.debutPosMin),
                )
              }
              className="rounded border border-black/10 bg-white px-3 py-2 text-[12px] normal-case tracking-normal text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
