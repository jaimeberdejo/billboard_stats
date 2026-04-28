import { ArtistPills } from "@/components/detail/artist-pills";
import { ChartHistoryTable } from "@/components/detail/chart-history-table";
import { DetailHeader } from "@/components/detail/detail-header";
import { StatsBar } from "@/components/detail/stats-bar";
import { getSongDetail, type SongDetailPayload } from "@/lib/songs";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Song Detail — Billboard Stats",
};

function parseId(value: string): number | null {
  if (!/^\d+$/.test(value)) {
    return null;
  }

  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function formatPeak(value: number | null): string {
  return value ? `#${value}` : "—";
}

async function loadSongDetail(
  songId: number | null,
): Promise<{ detail: SongDetailPayload | null; error: string | null }> {
  if (!songId) {
    return { detail: null, error: null };
  }

  try {
    const detail = await getSongDetail(songId);
    return { detail, error: null };
  } catch {
    return {
      detail: null,
      error: "Could not load detail data. Refresh the page or return to Latest Charts and try again.",
    };
  }
}

export default async function SongDetailPage(props: PageProps<"/song/[id]">) {
  const { id } = await props.params;
  const songId = parseId(id);
  const { detail, error } = await loadSongDetail(songId);

  if (error) {
    return (
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-3 py-3 sm:px-6 sm:py-4">
        <DetailHeader backHref="/" title="Song Detail" subtitle="Database-backed detail route" />
        <div className="mt-6 rounded border border-[#C8102E]/15 bg-[#FCEDEE] px-4 py-4 text-[12px] leading-[1.45] text-[#C8102E]">
          {error}
        </div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-3 py-3 sm:px-6 sm:py-4">
        <DetailHeader backHref="/" title="Song Detail" subtitle="Database-backed detail route" />
        <div className="mt-6 rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
          Song not found
        </div>
      </div>
    );
  }

  const stats = detail.stats;
  const statsItems = [
    { label: "Peak", value: formatPeak(stats?.peak_position ?? null), accent: stats?.peak_position === 1 },
    { label: "Weeks on Chart", value: String(stats?.total_weeks ?? 0) },
    {
      label: "Weeks at #1",
      value: String(stats?.weeks_at_number_one ?? 0),
      accent: (stats?.weeks_at_number_one ?? 0) > 0,
    },
    { label: "Weeks at Peak", value: String(stats?.weeks_at_peak ?? 0) },
    { label: "Debut Position", value: formatPeak(stats?.debut_position ?? null) },
    { label: "Debut Date", value: formatDate(stats?.debut_date ?? null) },
  ];

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-3 py-3 sm:px-6 sm:py-4">
      <DetailHeader
        backHref="/"
        title={detail.song.title}
        subtitle={detail.song.artist_credit}
        quoteTitle
      />

      <div className="mt-6">
        <StatsBar items={statsItems} />
      </div>

      <section className="mt-6">
        <div className="mb-3 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          Chart History
        </div>
        {detail.chartRun.length > 0 ? (
          <ChartHistoryTable chartRun={detail.chartRun} />
        ) : (
          <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
            No chart history available
          </div>
        )}
      </section>

      <section className="mt-6">
        <div className="mb-3 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          Artists
        </div>
        <ArtistPills artists={detail.artists.map((artist) => ({ id: artist.id, name: artist.name }))} />
      </section>
    </div>
  );
}
