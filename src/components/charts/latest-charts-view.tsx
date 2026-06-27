"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { ChartControls } from "@/components/charts/chart-controls";
import { ChartTable } from "@/components/charts/chart-table";
import type { ChartRegistryRow, ChartSnapshot, ChartType } from "@/lib/charts";

interface LatestChartsViewProps {
  initialSnapshot: ChartSnapshot | null;
  initialError: string | null;
  /**
   * Optional SSR-passed registry list. When provided, the selector renders
   * fully on first paint (no client loading flash); otherwise the list is
   * fetched from /api/charts/list on mount.
   */
  initialCharts?: ChartRegistryRow[];
}

const EMPTY_SNAPSHOT: ChartSnapshot = {
  chartType: "hot-100",
  chartSlug: "hot-100",
  chartTitle: null,
  chartFamily: null,
  entityKind: null,
  selectedDate: "",
  latestDate: "",
  availableDates: [],
  previousDate: null,
  nextDate: null,
  entries: [],
};

function resolveChartDateInput(input: string, availableDates: string[]): string | null {
  const normalized = input.trim();
  if (!normalized || availableDates.length === 0) {
    return null;
  }

  if (/^\d{4}$/.test(normalized)) {
    return availableDates.find((date) => date.startsWith(`${normalized}-`)) ?? null;
  }

  if (!/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
    return null;
  }

  if (availableDates.includes(normalized)) {
    return normalized;
  }

  for (const date of availableDates) {
    if (date <= normalized) {
      return date;
    }
  }

  return availableDates[availableDates.length - 1] ?? null;
}

async function fetchSnapshot(chartType: ChartType, date?: string): Promise<ChartSnapshot> {
  const params = new URLSearchParams({ chart: chartType });
  if (date) {
    params.set("date", date);
  }

  const response = await fetch(`/api/charts?${params.toString()}`, {
    method: "GET",
    cache: "no-store",
  });

  const payload = (await response.json()) as ChartSnapshot | { error?: string };
  if (!response.ok || !("entries" in payload)) {
    throw new Error(
      "error" in payload && payload.error
        ? payload.error
        : "Could not load chart data. Refresh the page or try a different week.",
    );
  }

  return payload;
}

export function LatestChartsView({
  initialSnapshot,
  initialError,
  initialCharts,
}: LatestChartsViewProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [snapshot, setSnapshot] = useState<ChartSnapshot>(initialSnapshot ?? EMPTY_SNAPSHOT);
  const [error, setError] = useState<string | null>(initialError);
  const [charts, setCharts] = useState<ChartRegistryRow[]>(initialCharts ?? []);
  const [isPending, startTransition] = useTransition();

  // Load the active chart registry list for the two-level selector. Skipped
  // when the list was SSR-passed (no client flash). Unknown/failed loads leave
  // `charts` empty — the selector then degrades to a disabled shell.
  useEffect(() => {
    if (initialCharts && initialCharts.length > 0) {
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const response = await fetch("/api/charts/list", { cache: "no-store" });
        const payload = (await response.json()) as
          | { charts: ChartRegistryRow[] }
          | { error?: string };
        if (!cancelled && response.ok && "charts" in payload) {
          setCharts(payload.charts);
        }
      } catch {
        // Non-fatal: selector renders disabled until the list is available.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [initialCharts]);

  const runFetch = (chartType: ChartType, date?: string) => {
    startTransition(async () => {
      try {
        const nextSnapshot = await fetchSnapshot(chartType, date);
        setSnapshot(nextSnapshot);
        setError(null);
      } catch (fetchError) {
        setError(
          fetchError instanceof Error
            ? fetchError.message
            : "Could not load chart data. Refresh the page or try a different week.",
        );
      }
    });
  };

  // Fall back to the first available chart if the active slug is not present in
  // the loaded registry list (invalid/removed chart), per UI-SPEC States.
  useEffect(() => {
    if (charts.length === 0 || !snapshot.chartType) {
      return;
    }
    if (!charts.some((row) => row.slug === snapshot.chartType)) {
      const fallback = charts[0]?.slug;
      if (fallback) {
        runFetch(fallback);
      }
    }
    // runFetch is stable for our purposes; deliberately excluded to avoid loops.
  }, [charts, snapshot.chartType]);

  useEffect(() => {
    if (!snapshot.chartType || !snapshot.selectedDate) {
      return;
    }

    const params = new URLSearchParams();
    params.set("chart", snapshot.chartType);
    params.set("date", snapshot.selectedDate);
    const nextUrl = `${pathname}?${params.toString()}`;

    if (`${pathname}?${searchParams.toString()}` !== nextUrl) {
      router.replace(nextUrl, { scroll: false });
    }
  }, [pathname, router, searchParams, snapshot.chartType, snapshot.selectedDate]);

  // Resolve the active chart title for attribution: prefer the snapshot's title,
  // fall back to the registry list row for the current slug.
  const chartTitle =
    snapshot.chartTitle ??
    charts.find((row) => row.slug === snapshot.chartType)?.title ??
    "this chart";

  return (
    <section className="flex flex-1 flex-col gap-4">
      <ChartControls
        availableDates={snapshot.availableDates}
        charts={charts}
        chartType={snapshot.chartType}
        chartTitle={chartTitle}
        entryCount={snapshot.entries.length}
        isPending={isPending}
        latestDate={snapshot.latestDate}
        nextDate={snapshot.nextDate}
        previousDate={snapshot.previousDate}
        selectedDate={snapshot.selectedDate}
        onChartTypeChange={(chartType) => runFetch(chartType)}
        onDateChange={(date) => runFetch(snapshot.chartType, date)}
        onDateSearch={(value) => {
          const resolvedDate = resolveChartDateInput(value, snapshot.availableDates);
          if (!resolvedDate) {
            setError("Enter a year like 1990 or a chart date like 1990-05-12.");
            return;
          }

          runFetch(snapshot.chartType, resolvedDate);
        }}
      />

      {error ? (
        <div className="rounded border border-[#C8102E]/20 bg-[#FCEDEE] px-3 py-3 text-[12px] leading-[1.45] text-[#0A0A0A]">
          {error}
        </div>
      ) : null}

      {snapshot.entries.length > 0 ? (
        <ChartTable
          chartType={snapshot.chartType}
          entries={snapshot.entries}
        />
      ) : (
        <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-8 text-center">
          <p className="text-[12px] font-[600] uppercase tracking-[0.08em] text-[#0A0A0A]">
            No chart data available
          </p>
          <p className="mt-2 text-[12px] leading-[1.45] text-[#888888]">
            Try another chart week or confirm the database has Billboard data loaded.
          </p>
        </div>
      )}
    </section>
  );
}
