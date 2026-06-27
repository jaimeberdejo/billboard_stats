"use client";

import type { GenderFilter, GenderLeaderboardPayload } from "@/lib/records";

/**
 * Opt-in gender filter for the records leaderboard (GENDER-03).
 *
 * Renders the segmented toggle (All default · Women · Men · Unknown, plus
 * Group/Mixed only when those buckets are present in the payload), the
 * coverage % + methodology note when a non-"All" filter is active, and the
 * CALM dashed "no gender data yet" panel for the 0%-coverage / all-Unknown
 * state — never the red error band (UI-SPEC §5). The Unknown option carries its
 * count as part of the accessible name; the coverage line lives in an
 * aria-live="polite" region so toggling announces the new coverage.
 *
 * Reuses the chart-controls segmented idiom verbatim (role="group",
 * aria-pressed, active = bg-[#C8102E] text-white).
 */

interface GenderOption {
  value: GenderFilter;
  label: string;
}

/** The always-present options in display order; group/mixed are appended only
 *  when their buckets actually appear in the payload (UI-SPEC). */
const BASE_OPTIONS: GenderOption[] = [
  { value: "all", label: "All" },
  { value: "female", label: "Women" },
  { value: "male", label: "Men" },
];

const OPTIONAL_OPTIONS: GenderOption[] = [
  { value: "group", label: "Group" },
  { value: "mixed", label: "Mixed" },
];

function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

function formatPct(coveragePct: number): number {
  // coveragePct is a fraction in [0,1]; render as a whole-number percent.
  return Math.round(coveragePct * 100);
}

interface GenderFilterProps {
  value: GenderFilter;
  coverage: GenderLeaderboardPayload | null;
  onChange: (next: GenderFilter) => void;
  disabled?: boolean;
}

export function GenderFilter({
  value,
  coverage,
  onChange,
  disabled = false,
}: GenderFilterProps) {
  const unknownCount = coverage?.unknownArtists ?? 0;
  const totalArtists = coverage?.totalArtists ?? 0;
  const matchedArtists = coverage?.matchedArtists ?? 0;
  const coveragePct = formatPct(coverage?.coveragePct ?? 0);

  // Surface Group/Mixed only if the payload reports rows in those buckets OR the
  // filter is currently set to one of them (so a deep-linked filter stays
  // visible). Until enrichment runs these stay hidden — calm by default.
  const optionalVisible = OPTIONAL_OPTIONS.filter(
    (option) =>
      value === option.value ||
      coverage?.rows.some((row) => row.gender === option.value),
  );

  const options: GenderOption[] = [
    ...BASE_OPTIONS,
    ...optionalVisible,
    { value: "unknown", label: `Unknown (${formatCount(unknownCount)})` },
  ];

  const isFilterActive = value !== "all";
  // 0%-coverage / all-Unknown is the truthful current state. The gendered
  // filters (Women/Men/Group/Mixed) return zero matched rows then — render the
  // calm dashed panel rather than an empty-looking leaderboard or a red error.
  const isZeroCoverageGenderedFilter =
    isFilterActive &&
    value !== "unknown" &&
    coverage !== null &&
    coverage.rows.length === 0;

  const coverageLine =
    coveragePct === 0
      ? `Coverage: 0% (0 of ${formatCount(totalArtists)} artists gendered). Gender enrichment pending; all artists are Unknown.`
      : `Coverage: ${coveragePct}% (${formatCount(matchedArtists)} of ${formatCount(
          totalArtists,
        )} artists gendered). Gender is best-effort; ${formatCount(
          unknownCount,
        )} artists are Unknown and excluded from this filtered view.`;

  return (
    <div className="flex flex-col gap-2">
      <div
        role="group"
        aria-label="Gender filter"
        className="inline-flex w-fit max-w-full flex-wrap overflow-hidden rounded border border-black/10 bg-[#F5F5F5]"
      >
        {options.map((option) => {
          const active = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              disabled={disabled}
              aria-pressed={active}
              onClick={() => onChange(option.value)}
              className={[
                "border-r border-black/10 px-3 py-2.5 text-[11px] font-[600] tracking-[0.08em] transition-colors last:border-r-0 sm:py-1.5",
                "disabled:cursor-not-allowed disabled:opacity-40",
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

      {/* Coverage / methodology — announced on filter change (aria-live). The 0%
          state is calm grey, never the red error band. */}
      <div aria-live="polite" className="flex flex-col gap-1">
        {isZeroCoverageGenderedFilter ? (
          <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
            <p className="text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
              No gender data yet.
            </p>
            <p className="mt-2 text-[12px] text-[#888888]">
              Gender enrichment hasn&apos;t been run, so every artist is currently
              Unknown (coverage 0%). This filter will populate once artists are
              gendered.
            </p>
          </div>
        ) : null}

        {isFilterActive && coverage !== null ? (
          <p
            className={[
              "text-[10px] font-[600] uppercase tracking-[0.08em]",
              coveragePct === 0 ? "text-[#888888]" : "text-[#C8102E]",
            ].join(" ")}
          >
            {coverageLine}
          </p>
        ) : null}
      </div>
    </div>
  );
}
