"use client";

/**
 * ThisWeekView — the ANALYTICS-03 "this week in history" timeline (Phase 14).
 *
 * Consumes ThisWeekPayload from /api/analytics/this-week (the records-view
 * fetch/error scaffold). Renders year groups newest → oldest, each with a real
 * heading element ("{year} · {Saturday chart date}") and the group's top-N
 * entries in the leaderboard-row idiom (rank · title · artist credit), clickable
 * through to the entity detail page.
 *
 * The honesty contract (UI-SPEC §3 / CONTEXT): a year with charted===false is
 * NEVER silently skipped — it renders the year header followed by the explicit
 * muted line "No chart published this week." so the absence is visible and true.
 */

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import type { ChartRegistryRow } from "@/lib/charts";
import type { ThisWeekGroup, ThisWeekPayload } from "@/lib/analytics";

/** Saturday chart-date formatter (UTC, mirrors chart-run-visualization). */
const DATE_FORMAT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "long",
  day: "numeric",
  timeZone: "UTC",
});

function formatChartDate(isoDate: string | null): string {
  if (!isoDate) {
    return "";
  }
  const parsed = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return isoDate;
  }
  return DATE_FORMAT.format(parsed).toUpperCase();
}

async function fetchThisWeek(
  chart: string,
  date: string,
  topN: number,
): Promise<ThisWeekPayload> {
  const params = new URLSearchParams({ chart, topN: String(topN) });
  if (date.trim()) {
    params.set("date", date.trim());
  }
  const response = await fetch(`/api/analytics/this-week?${params.toString()}`, {
    method: "GET",
    cache: "no-store",
  });

  const payload = (await response.json()) as ThisWeekPayload | { error?: string };
  if (!response.ok || !("groups" in payload)) {
    throw new Error(
      "error" in payload && payload.error
        ? payload.error
        : "Could not load analytics. Please try again later.",
    );
  }
  return payload;
}

/** A single year group: header + entries OR the explicit no-chart-week line. */
function YearGroup({
  group,
  entityKind,
  onEntityClick,
}: {
  group: ThisWeekGroup;
  entityKind: ChartRegistryRow["entity_kind"] | null;
  onEntityClick: (entityKind: ChartRegistryRow["entity_kind"] | null) => void;
}) {
  const formattedDate = formatChartDate(group.chartDate);
  const headerText = formattedDate
    ? `${group.year} · ${formattedDate}`
    : `${group.year}`;

  return (
    <div className="px-3 py-3">
      {/* Real heading element so groups are AT-navigable (UI-SPEC a11y). */}
      <h3 className="text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
        {headerText}
      </h3>

      {group.charted && group.rows.length > 0 ? (
        <div className="mt-2 divide-y divide-black/10">
          {group.rows.map((row, index) => (
            <button
              key={`${row.rank}-${row.title}-${index}`}
              type="button"
              onClick={() => onEntityClick(entityKind)}
              className="flex w-full items-center gap-3 py-2 text-left transition-colors hover:bg-[#F5F5F5]"
            >
              <div className="w-8 shrink-0 text-[12px] font-[700] leading-[1.1] text-[#888888]">
                {row.rank}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12px] font-[600] leading-[1.3] text-[#0A0A0A]">
                  {row.title}
                </div>
                {row.artist_credit ? (
                  <div className="mt-0.5 truncate text-[12px] leading-[1.45] text-[#888888]">
                    {row.artist_credit}
                  </div>
                ) : null}
              </div>
            </button>
          ))}
        </div>
      ) : (
        // Explicit no-chart-that-week marker — never a silent skip.
        <p className="mt-2 text-[11px] leading-[1.45] text-[#888888]">
          No chart published this week.
        </p>
      )}
    </div>
  );
}

interface ThisWeekViewProps {
  /** Default chart slug; falls back to hot-100. */
  defaultChart?: string;
}

export function ThisWeekView({ defaultChart = "hot-100" }: ThisWeekViewProps) {
  const router = useRouter();
  const [chart, setChart] = useState<string>(defaultChart);
  const [date, setDate] = useState<string>("");
  const [topN] = useState<number>(10);
  const [registryCharts, setRegistryCharts] = useState<ChartRegistryRow[]>([]);
  const [payload, setPayload] = useState<ThisWeekPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  // Load the active chart registry so the selector is registry-driven.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch("/api/charts/list", { method: "GET" });
        const data = (await response.json()) as
          | { charts: ChartRegistryRow[] }
          | { error?: string };
        if (!cancelled && response.ok && "charts" in data) {
          setRegistryCharts(data.charts);
        }
      } catch {
        // Selector degrades to the default chart if the registry can't load.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    startTransition(async () => {
      try {
        const next = await fetchThisWeek(chart, date, topN);
        if (!cancelled) {
          setPayload(next);
          setError(null);
        }
      } catch (fetchError) {
        if (!cancelled) {
          setPayload(null);
          setError(
            fetchError instanceof Error
              ? fetchError.message
              : "Could not load analytics. Please try again later.",
          );
        }
      }
    });
    return () => {
      cancelled = true;
    };
  }, [chart, date, topN]);

  const activeEntityKind =
    registryCharts.find((row) => row.slug === chart)?.entity_kind ?? null;

  const navigateToScope = (entityKind: ChartRegistryRow["entity_kind"] | null) => {
    // Group rows do not carry entity ids (this-week is aggregate); route to the
    // chart's latest view as the safe drill-in (entity ids land in a later mount).
    if (entityKind) {
      router.push(`/?chart=${encodeURIComponent(chart)}`);
    }
  };

  const groups = payload?.groups ?? [];

  return (
    <section className="mt-6 flex flex-col gap-4">
      <div className="border-b border-black/10 pb-3">
        <p className="text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          This Week in History
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-black/10 pb-3">
        <label className="flex items-center gap-2">
          <span className="text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
            Chart
          </span>
          <select
            value={chart}
            onChange={(event) => setChart(event.target.value)}
            aria-label="Chart"
            className="rounded border border-black/10 bg-white px-2 py-1.5 text-[11px] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
          >
            {(registryCharts.length > 0
              ? registryCharts
              : [
                  {
                    slug: "hot-100",
                    title: "Hot 100",
                    entity_kind: "song",
                    category: "core",
                    family: "Core",
                    sort_order: 0,
                  } as ChartRegistryRow,
                ]
            ).map((row) => (
              <option key={row.slug} value={row.slug}>
                {row.title ?? row.slug}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-2">
          <span className="text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
            Date
          </span>
          <input
            type="date"
            value={date}
            onChange={(event) => setDate(event.target.value)}
            aria-label="Target date"
            className="rounded border border-black/10 bg-white px-2 py-1.5 text-[11px] font-[600] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
          />
        </label>

        <span className="ml-auto text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          {isPending ? "Loading…" : null}
        </span>
      </div>

      {error ? (
        <div className="rounded border border-[#C8102E]/15 bg-[#FCEDEE] px-4 py-4 text-[12px] leading-[1.45] text-[#C8102E]">
          {error}
        </div>
      ) : null}

      {!error && payload && groups.length > 0 ? (
        <div className="overflow-hidden rounded border border-black/10 bg-white divide-y divide-black/10">
          {groups.map((group) => (
            <YearGroup
              key={group.year}
              group={group}
              entityKind={activeEntityKind}
              onEntityClick={navigateToScope}
            />
          ))}
        </div>
      ) : null}

      {!error && payload && groups.length === 0 ? (
        <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
          No records found.
        </div>
      ) : null}
    </section>
  );
}
