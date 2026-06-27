import Link from "next/link";

import { ArtistCatalogTable } from "@/components/artist/artist-catalog-table";
import { DetailHeader } from "@/components/detail/detail-header";
import { StatsBar } from "@/components/detail/stats-bar";
import {
  getArtistDetail,
  type ArtistCatalogAlbumRow,
  type ArtistCatalogSongRow,
  type ArtistCreditScope,
  type ArtistDetailPayload,
} from "@/lib/artists";

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

/**
 * Career first/last dates are aggregated across ALL the artist's charts, so no
 * single chart slug applies — render them as plain muted text (no chart link).
 * Per-chart date links live in the per-chart catalog tables instead.
 */
function formatDateRange(start: string | null, end: string | null): string {
  if (!start && !end) {
    return "Career aggregate detail";
  }

  return `${formatDate(start)} – ${formatDate(end)}`;
}

async function loadArtistDetail(
  artistId: number | null,
  creditScope: ArtistCreditScope,
): Promise<{ detail: ArtistDetailPayload | null; error: string | null }> {
  if (!artistId) {
    return { detail: null, error: null };
  }

  try {
    const detail = await getArtistDetail(artistId, creditScope);
    return { detail, error: null };
  } catch {
    return {
      detail: null,
      error: "Could not load detail data. Refresh the page or return to Latest Charts and try again.",
    };
  }
}

function parseCreditScope(value: string | string[] | undefined): ArtistCreditScope {
  if (value === "lead") {
    return "lead";
  }

  return "all";
}

export default async function ArtistDetailPage(props: PageProps<"/artist/[id]">) {
  const { id } = await props.params;
  const searchParams = await props.searchParams;
  const artistId = parseId(id);
  const creditScope = parseCreditScope(searchParams?.credits);
  const { detail, error } = await loadArtistDetail(artistId, creditScope);

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

  const totals = detail.careerTotals;
  const statsItems = [
    { label: "Charts", value: String(totals?.chart_count ?? 0) },
    { label: "Entries", value: String(totals?.total_entries ?? 0) },
    {
      label: "#1s",
      value: String(totals?.number_ones ?? 0),
      accent: (totals?.number_ones ?? 0) > 0,
    },
    { label: "Total Weeks", value: String(totals?.total_weeks ?? 0) },
    {
      label: "Best Peak",
      value: formatPeak(totals?.best_peak ?? null),
      accent: totals?.best_peak === 1,
    },
    { label: "Max Simultaneous", value: String(totals?.max_simultaneous ?? 0) },
  ];

  // Group catalog rows by their originating chart slug so each per-chart section
  // passes its own real slug to ArtistCatalogTable (correct date links).
  const songsBySlug = new Map<string, ArtistCatalogSongRow[]>();
  for (const song of detail.songs) {
    const list = songsBySlug.get(song.chart_slug) ?? [];
    list.push(song);
    songsBySlug.set(song.chart_slug, list);
  }
  const albumsBySlug = new Map<string, ArtistCatalogAlbumRow[]>();
  for (const album of detail.albums) {
    const list = albumsBySlug.get(album.chart_slug) ?? [];
    list.push(album);
    albumsBySlug.set(album.chart_slug, list);
  }

  // Render catalog sections in the rollup (sort_order) sequence; only charts
  // with catalog rows produce a section.
  const catalogSections = detail.chartRollups
    .map((rollup) => ({
      rollup,
      songs: songsBySlug.get(rollup.chart_slug) ?? [],
      albums: albumsBySlug.get(rollup.chart_slug) ?? [],
    }))
    .filter((section) => section.songs.length > 0 || section.albums.length > 0);

  const hasCatalogData = catalogSections.length > 0;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-3 py-3 sm:px-6 sm:py-4">
      <DetailHeader
        backHref="/"
        title={detail.artist.name}
        subtitle={formatDateRange(
          totals?.first_date ?? null,
          totals?.last_date ?? null,
        )}
      />

      <div className="mt-6 w-fit inline-flex self-start overflow-hidden rounded border border-black/10 bg-[#F5F5F5]">
        {([
          { value: "all", label: "All Credits" },
          { value: "lead", label: "As Lead Artist" },
        ] as const).map((option) => {
          const href =
            option.value === "all"
              ? `/artist/${detail.artist.id}`
              : `/artist/${detail.artist.id}?credits=lead`;

          return (
            <Link
              key={option.value}
              href={href}
              className={[
                "border-r border-black/10 px-4 py-2 text-center text-[11px] font-[600] uppercase tracking-[0.08em] last:border-r-0",
                creditScope === option.value
                  ? "bg-[#C8102E] !text-white visited:!text-white focus:!text-white"
                  : "bg-white text-[#0A0A0A] hover:bg-[#F5F5F5]",
              ].join(" ")}
            >
              {option.label}
            </Link>
          );
        })}
      </div>

      <div className="mt-6">
        <StatsBar items={statsItems} />
      </div>

      {detail.chartRollups.length > 0 ? (
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {detail.chartRollups.map((rollup) => (
            <div
              key={rollup.chart_slug}
              className="rounded border border-black/10 bg-white px-3 py-3"
            >
              <div className="text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
                {rollup.chart_title}
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] leading-[1.45] text-[#0A0A0A]">
                <span>
                  <span className="text-[#888888]">Entries</span> {rollup.total_entries}
                </span>
                <span>
                  <span className="text-[#888888]">Weeks</span> {rollup.total_weeks}
                </span>
                <span
                  className={rollup.number_ones > 0 ? "font-[700] text-[#C8102E]" : ""}
                >
                  <span className="text-[#888888]">#1s</span> {rollup.number_ones}
                </span>
                <span
                  className={rollup.best_peak === 1 ? "font-[700] text-[#C8102E]" : ""}
                >
                  <span className="text-[#888888]">Peak</span> {formatPeak(rollup.best_peak)}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {hasCatalogData ? (
        <div className="mt-6 flex flex-col gap-6">
          {catalogSections.map((section) => (
            <div key={section.rollup.chart_slug} className="flex flex-col gap-6">
              {section.songs.length > 0 ? (
                <ArtistCatalogTable
                  title={section.rollup.chart_title}
                  chartSlug={section.rollup.chart_slug}
                  rows={section.songs.map((song) => ({
                    id: song.id,
                    title: song.title,
                    peak_position: song.peak_position,
                    total_weeks: song.total_weeks,
                    weeks_at_peak: song.weeks_at_peak,
                    debut_date: song.debut_date,
                    last_date: song.last_date,
                    href: `/song/${song.id}`,
                  }))}
                />
              ) : null}

              {section.albums.length > 0 ? (
                <ArtistCatalogTable
                  title={section.rollup.chart_title}
                  chartSlug={section.rollup.chart_slug}
                  rows={section.albums.map((album) => ({
                    id: album.id,
                    title: album.title,
                    peak_position: album.peak_position,
                    total_weeks: album.total_weeks,
                    weeks_at_peak: album.weeks_at_peak,
                    debut_date: album.debut_date,
                    last_date: album.last_date,
                    href: `/album/${album.id}`,
                  }))}
                />
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-6 rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
          This page does not have chart history to display yet. Try another song, album, or artist, or confirm the database stats tables are populated.
        </div>
      )}
    </div>
  );
}
