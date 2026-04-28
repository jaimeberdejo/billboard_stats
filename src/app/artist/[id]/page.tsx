import { ArtistCatalogTable } from "@/components/artist/artist-catalog-table";
import { DetailHeader } from "@/components/detail/detail-header";
import { StatsBar } from "@/components/detail/stats-bar";
import { getArtistDetail, type ArtistDetailPayload } from "@/lib/artists";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Artist Detail — Billboard Stats",
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

function formatRange(start: string | null, end: string | null): string {
  if (!start && !end) {
    return "Career aggregate detail";
  }

  return `${formatDate(start)} – ${formatDate(end)}`;
}

async function loadArtistDetail(
  artistId: number | null,
): Promise<{ detail: ArtistDetailPayload | null; error: string | null }> {
  if (!artistId) {
    return { detail: null, error: null };
  }

  try {
    const detail = await getArtistDetail(artistId);
    return { detail, error: null };
  } catch {
    return {
      detail: null,
      error: "Could not load detail data. Refresh the page or return to Latest Charts and try again.",
    };
  }
}

export default async function ArtistDetailPage(props: PageProps<"/artist/[id]">) {
  const { id } = await props.params;
  const artistId = parseId(id);
  const { detail, error } = await loadArtistDetail(artistId);

  if (error) {
    return (
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-3 py-3 sm:px-6 sm:py-4">
        <DetailHeader backHref="/" title="Artist Detail" subtitle="Database-backed detail route" />
        <div className="mt-6 rounded border border-[#C8102E]/15 bg-[#FCEDEE] px-4 py-4 text-[12px] leading-[1.45] text-[#C8102E]">
          {error}
        </div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-3 py-3 sm:px-6 sm:py-4">
        <DetailHeader backHref="/" title="Artist Detail" subtitle="Database-backed detail route" />
        <div className="mt-6 rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
          Artist not found
        </div>
      </div>
    );
  }

  const stats = detail.stats;
  const statsItems = [
    { label: "Hot 100 Songs", value: String(stats?.total_hot100_songs ?? 0) },
    { label: "B200 Albums", value: String(stats?.total_b200_albums ?? 0) },
    {
      label: "#1 Songs",
      value: String(stats?.hot100_number_ones ?? 0),
      accent: (stats?.hot100_number_ones ?? 0) > 0,
    },
    {
      label: "#1 Albums",
      value: String(stats?.b200_number_ones ?? 0),
      accent: (stats?.b200_number_ones ?? 0) > 0,
    },
    { label: "Hot 100 Weeks", value: String(stats?.total_hot100_weeks ?? 0) },
    { label: "B200 Weeks", value: String(stats?.total_b200_weeks ?? 0) },
    {
      label: "Best Hot 100",
      value: formatPeak(stats?.best_hot100_peak ?? null),
      accent: stats?.best_hot100_peak === 1,
    },
    { label: "Max Simultaneous", value: String(stats?.max_simultaneous_hot100 ?? 0) },
  ];

  const hasCatalogData = detail.songs.length > 0 || detail.albums.length > 0;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-3 py-3 sm:px-6 sm:py-4">
      <DetailHeader
        backHref="/"
        title={detail.artist.name}
        subtitle={formatRange(stats?.first_chart_date ?? null, stats?.latest_chart_date ?? null)}
      />

      <div className="mt-6">
        <StatsBar items={statsItems} />
      </div>

      {hasCatalogData ? (
        <div className="mt-6 flex flex-col gap-6">
          {detail.songs.length > 0 ? (
            <ArtistCatalogTable
              title="Hot 100 Songs"
              rows={detail.songs.map((song) => ({
                id: song.id,
                title: song.title,
                peak_position: song.peak_position,
                total_weeks: song.total_weeks,
                weeks_at_peak: song.weeks_at_peak,
                debut_date: song.debut_date,
                href: `/song/${song.id}`,
              }))}
            />
          ) : null}

          {detail.albums.length > 0 ? (
            <ArtistCatalogTable
              title="Billboard 200 Albums"
              rows={detail.albums.map((album) => ({
                id: album.id,
                title: album.title,
                peak_position: album.peak_position,
                total_weeks: album.total_weeks,
                weeks_at_peak: album.weeks_at_peak,
                debut_date: album.debut_date,
                href: `/album/${album.id}`,
              }))}
            />
          ) : null}
        </div>
      ) : (
        <div className="mt-6 rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
          This page does not have chart history to display yet. Try another song, album, or artist, or confirm the database stats tables are populated.
        </div>
      )}
    </div>
  );
}
