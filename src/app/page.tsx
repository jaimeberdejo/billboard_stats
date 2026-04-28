import { LatestChartsView } from "@/components/charts/latest-charts-view";
import { getChartSnapshot, type ChartSnapshot } from "@/lib/charts";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Latest Charts — Billboard Stats",
};

async function loadInitialSnapshot(): Promise<{
  snapshot: ChartSnapshot | null;
  error: string | null;
}> {
  try {
    const snapshot = await getChartSnapshot("hot-100");
    return { snapshot, error: null };
  } catch {
    return {
      snapshot: null,
      error: "Could not load chart data. Refresh the page or try a different week.",
    };
  }
}

export default async function Home() {
  const { snapshot, error } = await loadInitialSnapshot();

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-3 py-3 sm:px-6 sm:py-4">
      <LatestChartsView initialSnapshot={snapshot} initialError={error} />
    </div>
  );
}
