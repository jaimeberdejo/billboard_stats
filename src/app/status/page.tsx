import { DataStatusPanel } from "@/components/status/data-status-panel";
import { getDataSummary, type DataSummary } from "@/lib/data-status";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Data Status — Billboard Stats",
};

async function loadSummary(): Promise<{
  summary: DataSummary | null;
  error: string | null;
}> {
  try {
    const summary = await getDataSummary();
    return { summary, error: null };
  } catch {
    return {
      summary: null,
      error: "Could not load data status. Refresh the page and verify DATABASE_URL is configured.",
    };
  }
}

export default async function StatusPage() {
  const { summary, error } = await loadSummary();

  return (
    <div className="mx-auto w-full max-w-7xl px-3 py-3 sm:px-6 sm:py-4">
      <div className="border-b border-black/10 pb-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
              Data Status
            </p>
            <h1 className="mt-1 text-[16px] font-[700] leading-[1.2] text-[#0A0A0A]">
              Data Status
            </h1>
          </div>
          <p className="text-[11px] text-[#888888]">
            Aggregate read-only database coverage and freshness.
          </p>
        </div>
      </div>

      <div className="mt-4">
        <DataStatusPanel summary={summary} error={error} />
      </div>
    </div>
  );
}
