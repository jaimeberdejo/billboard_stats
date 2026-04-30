import { LatestChartsView } from "@/components/charts/latest-charts-view";
import { getChartSnapshot, type ChartSnapshot } from "@/lib/charts";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Latest Charts — Billboard Stats",
};

function parseChartType(
  value: string | string[] | undefined,
): "hot-100" | "billboard-200" | undefined {
  return value === "billboard-200" ? "billboard-200" : value === "hot-100" ? "hot-100" : undefined;
}

function parseRequestedDate(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : undefined;
}

async function loadRequestedSnapshot(
  chartType: "hot-100" | "billboard-200",
  requestedDate?: string,
): Promise<{
  snapshot: ChartSnapshot | null;
  error: string | null;
}> {
  try {
    const snapshot = await getChartSnapshot(chartType, requestedDate);
    return { snapshot, error: null };
  } catch {
    return {
      snapshot: null,
      error: "Could not load chart data. Refresh the page or try a different week.",
    };
  }
}

export default async function Home(props: PageProps<"/">) {
  const searchParams = await props.searchParams;
  const chartType = parseChartType(searchParams?.chart) ?? "hot-100";
  const requestedDate = parseRequestedDate(searchParams?.date);
  const { snapshot, error } = await loadRequestedSnapshot(chartType, requestedDate);

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-3 py-3 sm:px-6 sm:py-4">
      <LatestChartsView initialSnapshot={snapshot} initialError={error} />
    </div>
  );
}
