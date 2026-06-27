"use client";

/**
 * PresenceChart — the ANALYTICS-02 presence-by-year trend (Phase 14).
 *
 * A "use client" Recharts LineChart styled to match the existing flat SVG
 * `chart-run-visualization` aesthetic EXACTLY (UI-SPEC "Recharts Styling
 * Contract"): no gradients/3D/drop-shadows, solid 1px rgba(0,0,0,0.08) grid,
 * #888888 10px ticks, the single red #C8102E series (+ optional ink #0A0A0A
 * second series for the comparison overlay), an ink custom tooltip, and
 * `accessibilityLayer` ON for keyboard navigation.
 *
 * Pitfall 4: Recharts uses browser APIs and throws if imported into a server
 * component — hence the "use client" directive on line 1. If recharts was
 * deferred in 14-01 (not installed), the dynamic import below falls back to the
 * muted "Trend chart unavailable in this build." note so the rest of the app
 * still builds and renders. In this build recharts IS installed (^3.9.0), so the
 * Recharts path ships.
 */

import { useEffect, useState } from "react";

// ---------------------------------------------------------------------------
// Centralized flat-aesthetic color constants — single source of truth shared
// with the rest of the app's chart chrome (UI-SPEC: "Colors as constants").
// ---------------------------------------------------------------------------
const ACCENT = "#C8102E"; // Entity A / single active series (Billboard red)
const INK = "#0A0A0A"; // Entity B (comparison overlay) + tooltip background
const GRID = "rgba(0,0,0,0.08)"; // solid 1px grid + axis lines (no dash)
const MUTED = "#888888"; // axis ticks + muted note text

const CHART_HEIGHT = 260; // matches chart-run-visualization L112
const CHART_MARGIN = { top: 20, right: 24, bottom: 28, left: 40 } as const;

/** One {year, weeks} point in a presence series. Mirrors PresencePoint. */
export interface PresenceSeriesPoint {
  year: number;
  weeks: number;
}

interface PresenceChartProps {
  /** Entity A series (rendered as the red active line). */
  data: PresenceSeriesPoint[];
  /** Optional Entity B series for the comparison overlay (ink line). */
  secondSeries?: PresenceSeriesPoint[];
  /** Accessible name describing the chart, e.g. "Presence by year for X on hot-100". */
  accessibleName: string;
  /** Display label for series A in the legend (comparison context). */
  labelA?: string;
  /** Display label for series B in the legend (comparison context). */
  labelB?: string;
}

/**
 * The shape Recharts needs: one row per year carrying both series' values keyed
 * by `a`/`b` so a single <LineChart data> drives the overlay. Years present in
 * either series are unioned so neither line is silently truncated.
 */
interface MergedRow {
  year: number;
  a: number | null;
  b: number | null;
}

function mergeSeries(
  a: PresenceSeriesPoint[],
  b: PresenceSeriesPoint[] | undefined,
): MergedRow[] {
  const byYear = new Map<number, MergedRow>();
  for (const point of a) {
    byYear.set(point.year, { year: point.year, a: point.weeks, b: null });
  }
  for (const point of b ?? []) {
    const existing = byYear.get(point.year);
    if (existing) {
      existing.b = point.weeks;
    } else {
      byYear.set(point.year, { year: point.year, a: null, b: point.weeks });
    }
  }
  return [...byYear.values()].sort((l, r) => l.year - r.year);
}

/** Bordered surface wrapper shared by the chart + every fallback state. */
function ChartSurface({
  accessibleName,
  children,
}: {
  accessibleName: string;
  children: React.ReactNode;
}) {
  return (
    <div className="relative overflow-hidden rounded border border-black/10 bg-white px-3 py-4">
      <div className="mb-3 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
        Presence by Year
      </div>
      <div role="img" aria-label={accessibleName}>
        {children}
      </div>
    </div>
  );
}

/** Muted no-data line (UI-SPEC States: empty series). */
function muteNote(text: string) {
  return <p className="text-[11px] leading-[1.45] text-[#888888]">{text}</p>;
}

/**
 * Custom ink tooltip — matches chart-run-visualization L276 (no default Recharts
 * white chrome). Declared at module scope (not during render) so it keeps stable
 * identity. Typed loosely because the recharts payload shape is internal; we
 * only read the year label + per-series values.
 */
function InkTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value?: number | null; name?: string; color?: string }>;
  label?: string | number;
}) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }
  return (
    <div className="rounded bg-[#0A0A0A] px-2 py-1 text-[10px] leading-[1.35] text-white shadow-lg">
      <div className="font-[600]">{label}</div>
      {payload.map((item, index) => (
        <div key={index} style={{ color: item.color ?? "#FFFFFF" }}>
          {item.value ?? 0} wks
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// recharts module loader (deferral-safe). recharts IS installed in this build;
// the dynamic guard exists ONLY so a missing module degrades to the unavailable
// note instead of breaking the route (UI-SPEC States: "Recharts unavailable").
// ---------------------------------------------------------------------------
type RechartsModule = typeof import("recharts");

export function PresenceChart({
  data,
  secondSeries,
  accessibleName,
  labelA,
  labelB,
}: PresenceChartProps) {
  const [recharts, setRecharts] = useState<RechartsModule | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    import("recharts")
      .then((mod) => {
        if (!cancelled) {
          setRecharts(mod);
        }
      })
      .catch(() => {
        // recharts deferred / failed to load — degrade gracefully.
        if (!cancelled) {
          setUnavailable(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const merged = mergeSeries(data, secondSeries);
  const hasOverlay = (secondSeries?.length ?? 0) > 0;

  if (merged.length === 0) {
    return (
      <ChartSurface accessibleName={accessibleName}>
        {muteNote("No charted weeks.")}
      </ChartSurface>
    );
  }

  if (unavailable) {
    return (
      <ChartSurface accessibleName={accessibleName}>
        {muteNote("Trend chart unavailable in this build.")}
      </ChartSurface>
    );
  }

  if (!recharts) {
    // Brief client-side load window before the chunk resolves.
    return (
      <ChartSurface accessibleName={accessibleName}>
        {muteNote("Loading…")}
      </ChartSurface>
    );
  }

  const {
    ResponsiveContainer,
    LineChart,
    Line,
    CartesianGrid,
    XAxis,
    YAxis,
    Tooltip,
    Legend,
  } = recharts;

  return (
    <ChartSurface accessibleName={accessibleName}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <LineChart
          data={merged}
          margin={CHART_MARGIN}
          accessibilityLayer
        >
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis
            dataKey="year"
            tickLine={false}
            axisLine={{ stroke: GRID }}
            tick={{ fontSize: 10, fill: MUTED }}
          />
          <YAxis
            allowDecimals={false}
            axisLine={false}
            tickLine={false}
            width={40}
            tick={{ fontSize: 10, fill: MUTED }}
          />
          <Tooltip content={<InkTooltip />} cursor={{ stroke: "rgba(0,0,0,0.15)" }} />
          {hasOverlay ? (
            <Legend
              wrapperStyle={{
                fontSize: 10,
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                color: MUTED,
              }}
            />
          ) : null}
          <Line
            type="monotone"
            dataKey="a"
            name={labelA ?? "Entity A"}
            stroke={ACCENT}
            strokeWidth={2.5}
            strokeLinejoin="round"
            strokeLinecap="round"
            dot={false}
            activeDot={{ r: 4, fill: ACCENT }}
            connectNulls
            isAnimationActive={false}
          />
          {hasOverlay ? (
            <Line
              type="monotone"
              dataKey="b"
              name={labelB ?? "Entity B"}
              stroke={INK}
              strokeWidth={2.5}
              strokeLinejoin="round"
              strokeLinecap="round"
              dot={false}
              activeDot={{ r: 4, fill: INK }}
              connectNulls
              isAnimationActive={false}
            />
          ) : null}
        </LineChart>
      </ResponsiveContainer>
    </ChartSurface>
  );
}
