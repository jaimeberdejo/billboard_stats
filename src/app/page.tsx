import { LatestChartsView } from "@/components/charts/latest-charts-view";
import { getChartSnapshot, type ChartSnapshot, type ChartType } from "@/lib/charts";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Latest Charts — Billboard Stats",
};

/**
 * Resolve the requested chart slug. Threads the raw slug straight through to
 * getChartSnapshot (which resolves it against the registry and falls back to an
 * empty snapshot for unknown/inactive slugs); defaults to "hot-100" when absent.
 */
function parseChartSlug(value: string | string[] | undefined): ChartType {
  return typeof value === "string" && value ? value : "hot-100";
}

function parseRequestedDate(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : undefined;
}

async function loadRequestedSnapshot(
  chartSlug: ChartType,
  requestedDate?: string,
): Promise<{
  snapshot: ChartSnapshot | null;
  error: string | null;
}> {
  try {
    const snapshot = await getChartSnapshot(chartSlug, requestedDate);
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
  const chartSlug = parseChartSlug(searchParams?.chart);
  const requestedDate = parseRequestedDate(searchParams?.date);
  const { snapshot, error } = await loadRequestedSnapshot(chartSlug, requestedDate);

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-3 py-3 sm:px-6 sm:py-4">
      <LatestChartsView initialSnapshot={snapshot} initialError={error} />
    </div>
  );
}
