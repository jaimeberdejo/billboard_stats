"use client";

/**
 * ComparisonView — the ANALYTICS-01 entity-vs-entity comparison (Phase 14).
 *
 * Clones the records-view client scaffold (useState/useEffect/useTransition +
 * URL sync via useRouter/usePathname/useSearchParams + the cache:"no-store"
 * fetch/error idiom). Renders two SAME-KIND entity pickers and a 2-up metric
 * card showing the five era-labeled metric families consumed from
 * ComparisonPayload (/api/analytics/compare), plus the presence-by-year trend
 * overlay beneath (Entity A red, Entity B ink).
 *
 * Honesty contract (Pitfall 1 / threat T-14-03-I): each entity carries its own
 * derived era label and a methodology eyebrow so cross-era totals are presented
 * truthfully, never silently equated.
 */

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import {
  PresenceChart,
  type PresenceSeriesPoint,
} from "@/components/analytics/presence-chart";
import type {
  ComparisonPayload,
  EntityKind,
  PresencePayload,
} from "@/lib/analytics";

const ENTITY_KINDS: Array<{ label: string; value: EntityKind }> = [
  { label: "Artist", value: "artist" },
  { label: "Song", value: "song" },
  { label: "Album", value: "album" },
];

function parseEntityKind(value: string | null): EntityKind {
  return value === "song" || value === "album" || value === "artist"
    ? value
    : "artist";
}

/** Trimmed positive-integer id from the URL/input, or "" when blank/invalid. */
function parseId(value: string | null): string {
  if (!value) {
    return "";
  }
  const trimmed = value.trim();
  return /^\d+$/.test(trimmed) ? trimmed : "";
}

async function fetchComparison(
  entityKind: EntityKind,
  aId: string,
  bId: string,
): Promise<ComparisonPayload> {
  const params = new URLSearchParams({ entityKind, aId, bId });
  const response = await fetch(`/api/analytics/compare?${params.toString()}`, {
    method: "GET",
    cache: "no-store",
  });

  const payload = (await response.json()) as ComparisonPayload | { error?: string };
  if (!response.ok || !("left" in payload)) {
    throw new Error(
      "error" in payload && payload.error
        ? payload.error
        : "Could not load analytics. Please try again later.",
    );
  }
  return payload;
}

/**
 * Presence-by-year for one entity on one chart. Returns an empty series when the
 * entity has no chart slug (no-throw) so the overlay simply omits that line.
 */
async function fetchPresence(
  chartSlug: string | undefined,
  entityKind: EntityKind,
  id: string,
): Promise<PresenceSeriesPoint[]> {
  if (!chartSlug || !id) {
    return [];
  }
  const params = new URLSearchParams({ chart: chartSlug, entityKind, id });
  const response = await fetch(`/api/analytics/presence?${params.toString()}`, {
    method: "GET",
    cache: "no-store",
  });
  const payload = (await response.json()) as PresencePayload | { error?: string };
  if (!response.ok || !("series" in payload)) {
    return [];
  }
  return payload.series.map((point) => ({ year: point.year, weeks: point.weeks }));
}

/** "#N" / "—" peak formatting; red only when #1 (accent reserved for emphasis). */
function PeakValue({ peak }: { peak: number | null }) {
  if (peak === null) {
    return <span className="text-[14px] font-[700] text-[#888888]">—</span>;
  }
  const isTop = peak === 1;
  return (
    <span
      className={[
        "text-[14px] font-[700]",
        isTop ? "text-[#C8102E]" : "text-[#0A0A0A]",
      ].join(" ")}
    >
      #{peak}
    </span>
  );
}

function NumberValue({ value }: { value: number }) {
  return <span className="text-[14px] font-[700] text-[#0A0A0A]">{value}</span>;
}

export function ComparisonView() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const [entityKind, setEntityKind] = useState<EntityKind>(() =>
    parseEntityKind(searchParams.get("entityKind")),
  );
  const [aId, setAId] = useState<string>(() => parseId(searchParams.get("aId")));
  const [bId, setBId] = useState<string>(() => parseId(searchParams.get("bId")));

  const [payload, setPayload] = useState<ComparisonPayload | null>(null);
  const [seriesA, setSeriesA] = useState<PresenceSeriesPoint[]>([]);
  const [seriesB, setSeriesB] = useState<PresenceSeriesPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const aReady = parseId(aId) !== "";
  const bReady = parseId(bId) !== "";
  const bothReady = aReady && bReady;

  // URL sync — mirrors records-view (replace, no scroll). entityKind drives BOTH
  // sides so the comparison is always same-kind (UI-SPEC: enforce same kind).
  useEffect(() => {
    const params = new URLSearchParams();
    params.set("entityKind", entityKind);
    if (aId.trim()) {
      params.set("aId", aId.trim());
    }
    if (bId.trim()) {
      params.set("bId", bId.trim());
    }
    const nextUrl = `${pathname}?${params.toString()}`;
    if (`${pathname}?${searchParams.toString()}` !== nextUrl) {
      router.replace(nextUrl, { scroll: false });
    }
  }, [aId, bId, entityKind, pathname, router, searchParams]);

  // Fetch the comparison payload + each entity's presence series when both ids
  // are present. The presence fetches are best-effort — a failure there must not
  // trip the red error band reserved for the primary comparison fetch.
  useEffect(() => {
    let cancelled = false;
    startTransition(async () => {
      if (!bothReady) {
        if (!cancelled) {
          setPayload(null);
          setSeriesA([]);
          setSeriesB([]);
          setError(null);
        }
        return;
      }

      try {
        const nextPayload = await fetchComparison(entityKind, aId.trim(), bId.trim());
        if (cancelled) {
          return;
        }
        setPayload(nextPayload);
        setError(null);

        const [presenceA, presenceB] = await Promise.all([
          fetchPresence(nextPayload.left.charts[0], entityKind, aId.trim()),
          fetchPresence(nextPayload.right.charts[0], entityKind, bId.trim()),
        ]);
        if (!cancelled) {
          setSeriesA(presenceA);
          setSeriesB(presenceB);
        }
      } catch (fetchError) {
        if (!cancelled) {
          setPayload(null);
          setSeriesA([]);
          setSeriesB([]);
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
  }, [aId, bId, bothReady, entityKind]);

  const left = payload?.left ?? null;
  const right = payload?.right ?? null;
  const hasHistory =
    left !== null &&
    right !== null &&
    (left.metrics.weeksOnChart > 0 || right.metrics.weeksOnChart > 0);

  const inputClass =
    "w-[120px] rounded border border-black/10 bg-white px-2 py-1.5 text-[11px] font-[600] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]";
  const selectClass =
    "rounded border border-black/10 bg-white px-2 py-1.5 text-[11px] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]";
  const eraEyebrow =
    "text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]";

  return (
    <section className="mt-6 flex flex-col gap-4">
      {/* Control bar: one entity-kind select drives both sides (same-kind), plus
          an id input for A and B. */}
      <div className="flex flex-wrap items-center gap-2 border-b border-black/10 pb-3">
        <label className="flex items-center gap-2">
          <span className={eraEyebrow}>Type</span>
          <select
            value={entityKind}
            onChange={(event) =>
              setEntityKind(event.target.value as EntityKind)
            }
            aria-label="Entity type (applies to both sides)"
            className={selectClass}
          >
            {ENTITY_KINDS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-2">
          <span className={eraEyebrow}>A id</span>
          <input
            type="number"
            min={1}
            step={1}
            inputMode="numeric"
            value={aId}
            onChange={(event) => setAId(event.target.value)}
            aria-label="Entity A id"
            className={inputClass}
          />
        </label>

        <label className="flex items-center gap-2">
          <span className={eraEyebrow}>B id</span>
          <input
            type="number"
            min={1}
            step={1}
            inputMode="numeric"
            value={bId}
            onChange={(event) => setBId(event.target.value)}
            aria-label="Entity B id"
            className={inputClass}
          />
        </label>

        <span className={`ml-auto ${eraEyebrow}`}>
          {isPending ? "Loading…" : null}
        </span>
      </div>

      {error ? (
        <div className="rounded border border-[#C8102E]/15 bg-[#FCEDEE] px-4 py-4 text-[12px] leading-[1.45] text-[#C8102E]">
          {error}
        </div>
      ) : null}

      {!bothReady ? (
        <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
          Pick two entities of the same type to compare.
        </div>
      ) : null}

      {bothReady && !error && left && right && !hasHistory ? (
        <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
          This entity has no chart history to compare yet.
        </div>
      ) : null}

      {bothReady && !error && left && right && hasHistory ? (
        <>
          {/* 2-up metric grid as a real table (UI-SPEC Accessibility): entity
              names as column headers, metric labels as row headers. */}
          <div className="overflow-hidden rounded border border-black/10 bg-white">
            <table className="w-full table-fixed border-collapse">
              <caption className="sr-only">
                Comparison of {left.label || `Entity ${left.id}`} and{" "}
                {right.label || `Entity ${right.id}`}
              </caption>
              <thead>
                <tr className="divide-x divide-black/10 border-b border-black/10">
                  <th scope="col" className="w-1/3 px-3 py-2 text-left">
                    <span className={eraEyebrow}>Metric</span>
                  </th>
                  <th scope="col" className="px-3 py-2 text-left align-top">
                    <span className="block truncate text-[12px] font-[600] text-[#0A0A0A]">
                      {left.label || `Entity ${left.id}`}
                    </span>
                    {left.metrics.activeEra ? (
                      <span className={`mt-0.5 block ${eraEyebrow}`}>
                        {left.metrics.activeEra}
                      </span>
                    ) : null}
                  </th>
                  <th scope="col" className="px-3 py-2 text-left align-top">
                    <span className="block truncate text-[12px] font-[600] text-[#0A0A0A]">
                      {right.label || `Entity ${right.id}`}
                    </span>
                    {right.metrics.activeEra ? (
                      <span className={`mt-0.5 block ${eraEyebrow}`}>
                        {right.metrics.activeEra}
                      </span>
                    ) : null}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/10">
                <tr className="divide-x divide-black/10">
                  <th scope="row" className="px-3 py-2 text-left">
                    <span className={eraEyebrow}>Peak</span>
                  </th>
                  <td className="px-3 py-2 tabular-nums">
                    <PeakValue peak={left.metrics.peak} />
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    <PeakValue peak={right.metrics.peak} />
                  </td>
                </tr>
                <tr className="divide-x divide-black/10">
                  <th scope="row" className="px-3 py-2 text-left">
                    <span className={eraEyebrow}>Weeks on Chart</span>
                  </th>
                  <td className="px-3 py-2 tabular-nums">
                    <NumberValue value={left.metrics.weeksOnChart} />
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    <NumberValue value={right.metrics.weeksOnChart} />
                  </td>
                </tr>
                <tr className="divide-x divide-black/10">
                  <th scope="row" className="px-3 py-2 text-left">
                    <span className={eraEyebrow}>#1s</span>
                  </th>
                  <td className="px-3 py-2 tabular-nums">
                    <NumberValue value={left.metrics.weeksAtNumberOne} />
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    <NumberValue value={right.metrics.weeksAtNumberOne} />
                  </td>
                </tr>
                <tr className="divide-x divide-black/10">
                  <th scope="row" className="px-3 py-2 text-left">
                    <span className={eraEyebrow}>Top 10s</span>
                  </th>
                  <td className="px-3 py-2 tabular-nums">
                    <NumberValue value={left.metrics.topTenWeeks} />
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    <NumberValue value={right.metrics.topTenWeeks} />
                  </td>
                </tr>
                <tr className="divide-x divide-black/10">
                  <th scope="row" className="px-3 py-2 text-left">
                    <span className={eraEyebrow}>Career Span</span>
                  </th>
                  <td className="px-3 py-2 text-[12px] text-[#0A0A0A] tabular-nums">
                    {left.metrics.activeEra || "—"}
                  </td>
                  <td className="px-3 py-2 text-[12px] text-[#0A0A0A] tabular-nums">
                    {right.metrics.activeEra || "—"}
                  </td>
                </tr>
              </tbody>
            </table>

            {/* Methodology eyebrow — the honesty caveat for cross-era totals. */}
            <p className="border-t border-black/10 px-3 py-2 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
              Weeks counted from valid chart weeks; eras differ — compare with care.
            </p>
          </div>

          {/* Trend overlay: A red, B ink. The trend is fetched per-entity for a
              SINGLE chart (charts[0]) while the metric table above spans ALL of
              each entity's charts. For multi-chart entities those scopes differ,
              so the eyebrow names the chart each line represents to keep the
              scope mismatch visible (honesty contract / WR-02). */}
          {left.charts[0] || right.charts[0] ? (
            <p className={eraEyebrow}>
              Trend scoped to one chart per entity —
              {left.charts[0]
                ? ` ${left.label || `Entity ${left.id}`}: ${left.charts[0]}`
                : ""}
              {left.charts[0] && right.charts[0] ? ";" : ""}
              {right.charts[0]
                ? ` ${right.label || `Entity ${right.id}`}: ${right.charts[0]}`
                : ""}
              . Totals above span all charts.
            </p>
          ) : null}
          <PresenceChart
            data={seriesA}
            secondSeries={seriesB}
            labelA={left.label || `Entity ${left.id}`}
            labelB={right.label || `Entity ${right.id}`}
            accessibleName={`Presence by year for ${
              left.label || `Entity ${left.id}`
            } and ${right.label || `Entity ${right.id}`}`}
          />
        </>
      ) : null}
    </section>
  );
}
