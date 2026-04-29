"use client";

import { useState, useTransition } from "react";
import { ChartControls } from "@/components/charts/chart-controls";
import { ChartTable } from "@/components/charts/chart-table";
import type { ChartSnapshot, ChartType } from "@/lib/charts";

interface LatestChartsViewProps {
  initialSnapshot: ChartSnapshot | null;
  initialError: string | null;
}

const EMPTY_SNAPSHOT: ChartSnapshot = {
  chartType: "hot-100",
  selectedDate: "",
  latestDate: "",
  availableDates: [],
  entries: [],
};

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
}: LatestChartsViewProps) {
  const [snapshot, setSnapshot] = useState<ChartSnapshot>(initialSnapshot ?? EMPTY_SNAPSHOT);
  const [error, setError] = useState<string | null>(initialError);
  const [isPending, startTransition] = useTransition();

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

  return (
    <section className="flex flex-1 flex-col gap-4">
      <ChartControls
        availableDates={snapshot.availableDates}
        chartType={snapshot.chartType}
        entryCount={snapshot.entries.length}
        isPending={isPending}
        selectedDate={snapshot.selectedDate}
        onChartTypeChange={(chartType) => runFetch(chartType)}
        onDateChange={(date) => runFetch(snapshot.chartType, date)}
      />

      {error ? (
        <div className="rounded border border-[#C8102E]/20 bg-[#FCEDEE] px-3 py-3 text-[12px] leading-[1.45] text-[#0A0A0A]">
          {error}
        </div>
      ) : null}

      {snapshot.entries.length > 0 ? (
        <ChartTable chartType={snapshot.chartType} entries={snapshot.entries} />
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
