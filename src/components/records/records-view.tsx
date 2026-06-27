"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import {
  CustomQueryBuilder,
  type CustomQueryState,
} from "@/components/records/custom-query-builder";
import { GenderFilter } from "@/components/records/gender-filter";
import { LeaderboardList } from "@/components/records/leaderboard-list";
import { chartDepth } from "@/lib/chart-families";
import type { ChartRegistryRow, ChartType } from "@/lib/charts";
import {
  type CustomRecordsPayload,
  type DrilldownPayload,
  type GenderFilter as GenderFilterValue,
  type GenderLeaderboardPayload,
  type PresetRecordsPayload,
  type RecordLeaderboardRow,
  type RecordPreset,
} from "@/lib/records";

/** Compact toggle labels for the common core/artist charts; falls back to title. */
const CHART_TOGGLE_ABBREV: Record<string, string> = {
  "hot-100": "HOT 100",
  "billboard-200": "B200",
  "artist-100": "ARTIST 100",
};

function chartToggleLabel(row: ChartRegistryRow): string {
  return CHART_TOGGLE_ABBREV[row.slug] ?? (row.title ?? row.slug);
}

const RECORD_OPTIONS: Array<{ label: string; value: "custom-query" | RecordPreset }> = [
  { label: "Custom Query", value: "custom-query" },
  { label: "Most Weeks at #1", value: "most-weeks-at-number-one" },
  { label: "Longest Chart Runs", value: "longest-chart-runs" },
  { label: "Most Top 10 Weeks", value: "most-top-10-weeks" },
  { label: "Most #1 Songs (by Artist)", value: "most-number-one-songs-by-artist" },
  { label: "Most #1 Albums (by Artist)", value: "most-number-one-albums-by-artist" },
  { label: "Most Entries by Artist", value: "most-entries-by-artist" },
  { label: "Most Total Chart Weeks by Artist", value: "most-total-chart-weeks-by-artist" },
  { label: "Most Simultaneous Entries", value: "most-simultaneous-entries" },
];

function parseRecordType(value: string | null): "custom-query" | RecordPreset {
  if (value === "custom-query") {
    return value;
  }

  return RECORD_OPTIONS.some((option) => option.value === value)
    ? (value as RecordPreset)
    : "most-weeks-at-number-one";
}

function parseChart(value: string | null): ChartType {
  // Registry slugs are validated server-side by the records API; default to the
  // Hot 100 core chart when absent/blank. Any non-empty slug is admitted.
  return value && value.trim() ? value : "hot-100";
}

const GENDER_VALUES: GenderFilterValue[] = [
  "all",
  "female",
  "male",
  "group",
  "mixed",
  "unknown",
];

function parseGender(value: string | null): GenderFilterValue {
  // Gender is opt-in; default to "all" when absent or unrecognized.
  return value && GENDER_VALUES.includes(value as GenderFilterValue)
    ? (value as GenderFilterValue)
    : "all";
}

function parsePositiveNumber(value: string | null, fallback: number): number {
  if (!value || !/^\d+$/.test(value)) {
    return fallback;
  }

  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function buildInitialCustomState(searchParams: URLSearchParams): CustomQueryState {
  const entity = (() => {
    const raw = searchParams.get("entity");
    return raw === "albums" || raw === "artists" ? raw : "songs";
  })();
  const chartContext = parseChart(searchParams.get("chartContext"));
  // Registry-derived chart depth: albums default to the Billboard 200 depth,
  // songs to the Hot 100 depth, artists to their selected chart's depth.
  const chartMax =
    entity === "albums"
      ? chartDepth("billboard-200")
      : entity === "artists"
        ? chartDepth(chartContext)
        : chartDepth("hot-100");

  return {
    entity,
    chartContext,
    creditScope: searchParams.get("creditScope") === "lead" ? "lead" : "all",
    sortDir: searchParams.get("sortDir") === "asc" ? "asc" : "desc",
    rankBy: (() => {
      const raw = searchParams.get("rankBy");
      return raw === "total-weeks" ||
        raw === "weeks-at-position" ||
        raw === "weeks-in-top-n" ||
        raw === "most-entries" ||
        raw === "number-one-entries"
        ? raw
        : "weeks-at-number-one";
    })(),
    rankByParam: Math.min(parsePositiveNumber(searchParams.get("rankByParam"), 10), chartMax),
    artistNames: searchParams.get("artistNames") ?? "",
    peakMin: Math.min(parsePositiveNumber(searchParams.get("peakMin"), 1), chartMax),
    peakMax: Math.min(parsePositiveNumber(searchParams.get("peakMax"), chartMax), chartMax),
    weeksMin: searchParams.get("weeksMin") ?? "",
    debutPosMin: Math.min(parsePositiveNumber(searchParams.get("debutPosMin"), 1), chartMax),
    debutPosMax: Math.min(parsePositiveNumber(searchParams.get("debutPosMax"), chartMax), chartMax),
    startYear: searchParams.get("startYear") ?? "",
    endYear: searchParams.get("endYear") ?? "",
  };
}

async function fetchPreset(
  chart: ChartType,
  record: RecordPreset,
  limit: number,
): Promise<PresetRecordsPayload> {
  const params = new URLSearchParams({
    mode: "preset",
    chart,
    record,
    limit: String(limit),
  });

  const response = await fetch(`/api/records?${params.toString()}`, {
    method: "GET",
    cache: "no-store",
  });

  const payload = (await response.json()) as PresetRecordsPayload | { error?: string };
  if (!response.ok || !("rows" in payload)) {
    throw new Error(
      "error" in payload && payload.error
        ? payload.error
        : "Could not load records. Please try again later.",
    );
  }

  return payload;
}

async function fetchGenderLeaderboard(
  chart: ChartType,
  gender: GenderFilterValue,
  limit: number,
): Promise<GenderLeaderboardPayload> {
  const params = new URLSearchParams({
    mode: "gender",
    chart,
    gender,
    limit: String(limit),
  });

  const response = await fetch(`/api/records?${params.toString()}`, {
    method: "GET",
    cache: "no-store",
  });

  const payload = (await response.json()) as
    | GenderLeaderboardPayload
    | { error?: string };
  if (!response.ok || !("rows" in payload)) {
    throw new Error(
      "error" in payload && payload.error
        ? payload.error
        : "Could not load gender leaderboard. Please try again later.",
    );
  }

  return payload;
}

async function fetchDrilldown(
  chart: ChartType,
  record: RecordPreset,
  row: RecordLeaderboardRow,
): Promise<DrilldownPayload> {
  const params = new URLSearchParams({
    mode: "drilldown",
    chart,
    record,
    artistId: String(row.artist_id),
  });

  if (row.chart_date) {
    params.set("chartDate", row.chart_date);
  }

  const response = await fetch(`/api/records?${params.toString()}`, {
    method: "GET",
    cache: "no-store",
  });

  const payload = (await response.json()) as DrilldownPayload | { error?: string };
  if (!response.ok || !("rows" in payload)) {
    throw new Error(
      "error" in payload && payload.error
        ? payload.error
        : "Could not load record drilldown data. Please try again later.",
    );
  }

  return payload;
}

async function fetchCustomRecords(
  state: CustomQueryState,
  limit: number,
): Promise<CustomRecordsPayload> {
  // Drive the chart from the builder's chartContext for every entity (WR-01),
  // not a hardcoded hot-100/billboard-200 per entity. The slug is validated
  // server-side, and getCustomRecords scopes the legacy-stats arms to the core
  // charts, so an unsupported entity/chart combination returns an empty result
  // rather than mislabeled data.
  const chart: ChartType = state.chartContext;
  const params = new URLSearchParams({
    mode: "custom",
    entity: state.entity,
    chart,
    creditScope: state.creditScope,
    rankBy: state.rankBy,
    rankByParam: String(state.rankByParam),
    sortDir: state.sortDir,
    limit: String(limit),
  });

  if (state.artistNames.trim()) {
    params.set("artistNames", state.artistNames.trim());
  }
  if (state.weeksMin.trim()) {
    params.set("weeksMin", state.weeksMin.trim());
  }
  if (state.startYear.trim()) {
    params.set("startYear", state.startYear.trim());
  }
  if (state.endYear.trim()) {
    params.set("endYear", state.endYear.trim());
  }
  params.set("peakMin", String(state.peakMin));
  params.set("peakMax", String(state.peakMax));
  params.set("debutPosMin", String(state.debutPosMin));
  params.set("debutPosMax", String(state.debutPosMax));

  const response = await fetch(`/api/records?${params.toString()}`, {
    method: "GET",
    cache: "no-store",
  });

  const payload = (await response.json()) as CustomRecordsPayload | { error?: string };
  if (!response.ok || !("rows" in payload)) {
    throw new Error(
      "error" in payload && payload.error
        ? payload.error
        : "Could not load custom records. Please try again later.",
    );
  }

  return payload;
}

export function RecordsView() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [recordType, setRecordType] = useState<"custom-query" | RecordPreset>(() =>
    parseRecordType(searchParams.get("recordType")),
  );
  const [chart, setChart] = useState<ChartType>(() =>
    parseChart(searchParams.get("chart")),
  );
  const [gender, setGender] = useState<GenderFilterValue>(() =>
    parseGender(searchParams.get("gender")),
  );
  const [genderPayload, setGenderPayload] =
    useState<GenderLeaderboardPayload | null>(null);
  const [registryCharts, setRegistryCharts] = useState<ChartRegistryRow[]>([]);
  const [payload, setPayload] = useState<PresetRecordsPayload | null>(null);
  const [customPayload, setCustomPayload] = useState<CustomRecordsPayload | null>(null);
  const [drilldown, setDrilldown] = useState<DrilldownPayload | null>(null);
  const [expandedRowKey, setExpandedRowKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [requestedLimit, setRequestedLimit] = useState(() => searchParams.get("limit") ?? "50");
  const [customState, setCustomState] = useState<CustomQueryState>(() =>
    buildInitialCustomState(searchParams),
  );

  const resetExpandedState = () => {
    setExpandedRowKey(null);
    setDrilldown(null);
  };

  // Load the active chart registry so the chart selector + attribution are
  // registry-driven (any ingested chart), not the hardcoded hot-100/b200 pair.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch("/api/charts/list", { method: "GET" });
        const payload = (await response.json()) as
          | { charts: ChartRegistryRow[] }
          | { error?: string };
        if (!cancelled && response.ok && "charts" in payload) {
          setRegistryCharts(payload.charts);
        }
      } catch {
        // Selector degrades to the default chart if the registry can't load.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Human-facing title of the active chart for result attribution (CHARTS-06).
  const activeChartTitle =
    registryCharts.find((row) => row.slug === chart)?.title ?? chart;

  const getRowKey = (row: RecordLeaderboardRow) =>
    `${row.artist_id ?? "row"}:${row.chart_date ?? "none"}`;

  const resolvedLimit = (() => {
    const parsed = Number(requestedLimit);
    if (!Number.isInteger(parsed) || parsed < 1) {
      return 1;
    }
    return Math.min(parsed, 1000);
  })();

  useEffect(() => {
    const params = new URLSearchParams();
    params.set("recordType", recordType);
    params.set("chart", chart);
    params.set("limit", requestedLimit);
    params.set("gender", gender);

    if (recordType === "custom-query") {
      params.set("entity", customState.entity);
      params.set("chartContext", customState.chartContext);
      params.set("creditScope", customState.creditScope);
      params.set("sortDir", customState.sortDir);
      params.set("rankBy", customState.rankBy);
      params.set("rankByParam", String(customState.rankByParam));
      params.set("peakMin", String(customState.peakMin));
      params.set("peakMax", String(customState.peakMax));
      params.set("debutPosMin", String(customState.debutPosMin));
      params.set("debutPosMax", String(customState.debutPosMax));

      if (customState.artistNames.trim()) {
        params.set("artistNames", customState.artistNames.trim());
      }
      if (customState.weeksMin.trim()) {
        params.set("weeksMin", customState.weeksMin.trim());
      }
      if (customState.startYear.trim()) {
        params.set("startYear", customState.startYear.trim());
      }
      if (customState.endYear.trim()) {
        params.set("endYear", customState.endYear.trim());
      }
    }

    const nextUrl = `${pathname}?${params.toString()}`;
    if (`${pathname}?${searchParams.toString()}` !== nextUrl) {
      router.replace(nextUrl, { scroll: false });
    }
  }, [chart, customState, gender, pathname, recordType, requestedLimit, router, searchParams]);

  const handleRecordTypeChange = (nextRecordType: "custom-query" | RecordPreset) => {
    setRecordType(nextRecordType);
    resetExpandedState();
    if (nextRecordType === "custom-query") {
      setPayload(null);
      setCustomPayload(null);
      setGenderPayload(null);
      setError(null);
    }
  };

  const handleGenderChange = (nextGender: GenderFilterValue) => {
    setGender(nextGender);
    resetExpandedState();
  };

  const handleChartChange = (nextChart: ChartType) => {
    setChart(nextChart);
    setGenderPayload(null);
    resetExpandedState();
    const nextDepth = chartDepth(nextChart);
    setCustomState((current) => ({
      ...current,
      chartContext: nextChart,
      peakMin: 1,
      peakMax: nextDepth,
      debutPosMin: 1,
      debutPosMax: nextDepth,
      rankByParam: Math.min(current.rankByParam, nextDepth),
    }));
  };

  useEffect(() => {
    if (recordType === "custom-query") {
      return;
    }

    let cancelled = false;
    startTransition(async () => {
      try {
        const nextPayload = await fetchPreset(chart, recordType, resolvedLimit);
        if (!cancelled) {
          setPayload(nextPayload);
          setError(null);
        }
      } catch (fetchError) {
        if (!cancelled) {
          setPayload(null);
          setError(
            fetchError instanceof Error
              ? fetchError.message
              : "Could not load records. Please try again later.",
          );
        }
      }
    });

    return () => {
      cancelled = true;
    };
  }, [chart, recordType, resolvedLimit]);

  // Gender coverage/leaderboard fetch. Runs for the preset (leaderboard) surface
  // only — custom-query is gender-agnostic. Fetched on every chart/gender change
  // so the Unknown count + coverage are always current, even in the "All" view.
  useEffect(() => {
    if (recordType === "custom-query") {
      return;
    }

    let cancelled = false;
    startTransition(async () => {
      try {
        const nextGenderPayload = await fetchGenderLeaderboard(
          chart,
          gender,
          resolvedLimit,
        );
        if (!cancelled) {
          setGenderPayload(nextGenderPayload);
        }
      } catch {
        // Coverage is supplementary; a failure here must not blank the page or
        // trip the red error band reserved for the primary fetch.
        if (!cancelled) {
          setGenderPayload(null);
        }
      }
    });

    return () => {
      cancelled = true;
    };
  }, [chart, gender, recordType, resolvedLimit]);

  useEffect(() => {
    if (recordType !== "custom-query") {
      return;
    }

    let cancelled = false;
    startTransition(async () => {
      try {
        const nextPayload = await fetchCustomRecords(customState, resolvedLimit);
        if (!cancelled) {
          setCustomPayload(nextPayload);
          setError(null);
        }
      } catch (fetchError) {
        if (!cancelled) {
          setCustomPayload(null);
          setError(
            fetchError instanceof Error
              ? fetchError.message
              : "Could not load custom records. Please try again later.",
          );
        }
      }
    });

    return () => {
      cancelled = true;
    };
  }, [customState, recordType, resolvedLimit]);

  const onRowClick = (row: RecordLeaderboardRow) => {
    if (!payload?.supportsDrilldown || !row.artist_id) {
      return;
    }

    const rowKey = getRowKey(row);
    if (expandedRowKey === rowKey) {
      setExpandedRowKey(null);
      setDrilldown(null);
      return;
    }

    setExpandedRowKey(rowKey);
    startTransition(async () => {
      try {
        const nextDrilldown = await fetchDrilldown(chart, payload.record, row);
        setDrilldown(nextDrilldown);
        setError(null);
      } catch (fetchError) {
        setDrilldown(null);
        setError(
          fetchError instanceof Error
            ? fetchError.message
            : "Could not load record drilldown data. Please try again later.",
        );
      }
    });
  };

  // When a non-"All" gender filter is active on the preset surface, the gender
  // leaderboard replaces the preset rows. The Unknown/coverage chrome is always
  // owned by GenderFilter (the calm 0% panel renders there, never as a red band).
  const genderActive = recordType !== "custom-query" && gender !== "all";
  const genderRows: RecordLeaderboardRow[] = (genderPayload?.rows ?? []).map(
    (row) => ({
      rank: row.rank,
      title: row.name,
      artist_credit: row.name,
      value: row.value,
      song_id: null,
      album_id: null,
      artist_id: row.artist_id,
      chart_date: null,
    }),
  );

  const resultCount =
    recordType === "custom-query"
      ? (customPayload?.rows.length ?? 0)
      : genderActive
        ? genderRows.length
        : (payload?.rows.length ?? 0);

  return (
    <section className="mt-6 flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 border-b border-black/10 pb-3">
        <select
          value={recordType}
          onChange={(event) =>
            handleRecordTypeChange(event.target.value as "custom-query" | RecordPreset)
          }
          className="min-w-[240px] rounded border border-black/10 bg-white px-2 py-1.5 text-[11px] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
        >
          {RECORD_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        {recordType !== "custom-query" ? (
          <div className="inline-flex overflow-hidden rounded border border-black/10 bg-[#F5F5F5]">
            {(registryCharts.length > 0
              ? registryCharts.filter((row) => row.entity_kind !== "artist")
              : [
                  {
                    slug: "hot-100",
                    title: "Hot 100",
                    entity_kind: "song",
                    category: "core",
                    family: "Core",
                    sort_order: 0,
                  } as ChartRegistryRow,
                  {
                    slug: "billboard-200",
                    title: "Billboard 200",
                    entity_kind: "album",
                    category: "core",
                    family: "Core",
                    sort_order: 1,
                  } as ChartRegistryRow,
                ]
            ).map((row) => (
              <button
                key={row.slug}
                type="button"
                onClick={() => handleChartChange(row.slug)}
                aria-label={row.title ?? row.slug}
                className={[
                  "min-w-[78px] border-r border-black/10 px-3 py-1.5 text-[11px] font-[600] tracking-[0.08em] transition-colors last:border-r-0",
                  chart === row.slug
                    ? "bg-[#C8102E] text-white"
                    : "bg-transparent text-[#0A0A0A] hover:bg-white",
                ].join(" ")}
              >
                {chartToggleLabel(row)}
              </button>
            ))}
          </div>
        ) : null}

        {recordType !== "custom-query" ? (
          <GenderFilter
            value={gender}
            coverage={genderPayload}
            onChange={handleGenderChange}
            disabled={isPending}
          />
        ) : null}

        <label className="ml-auto flex items-center gap-2">
          <span className="text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
            Results
          </span>
          <input
            type="number"
            min={1}
            max={1000}
            step={1}
            value={requestedLimit}
            onChange={(event) => setRequestedLimit(event.target.value)}
            inputMode="numeric"
            className="w-[92px] rounded border border-black/10 bg-white px-2 py-1.5 text-right text-[11px] font-[600] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
          />
          <span className="text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
            {isPending ? "Loading..." : `${resultCount} shown`}
          </span>
        </label>
      </div>

      {recordType !== "custom-query" ? (
        <p className="text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          Chart: <span className="text-[#0A0A0A]">{activeChartTitle}</span>
        </p>
      ) : null}

      {recordType === "custom-query" ? (
        <CustomQueryBuilder
          state={customState}
          onChange={setCustomState}
          charts={registryCharts}
        />
      ) : null}

      {error ? (
        <div className="rounded border border-[#C8102E]/15 bg-[#FCEDEE] px-4 py-4 text-[12px] leading-[1.45] text-[#C8102E]">
          {error}
        </div>
      ) : null}

      {recordType !== "custom-query" && !genderActive && payload?.unsupportedMessage ? (
        <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
          {payload.unsupportedMessage}
        </div>
      ) : null}

      {recordType !== "custom-query" && genderActive ? (
        genderPayload?.unsupportedMessage ? (
          <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
            {genderPayload.unsupportedMessage}
          </div>
        ) : genderRows.length > 0 ? (
          <LeaderboardList
            rows={genderRows}
            valueLabel={genderPayload?.valueLabel ?? "Wks"}
            expandedRowKey={null}
            onRowClick={(row) => {
              if (row.artist_id) {
                router.push(`/artist/${row.artist_id}`);
              }
            }}
          />
        ) : // Empty gendered result: GenderFilter renders the calm 0%/all-Unknown
        // dashed panel inline (never a red band), so no extra empty panel here.
        null
      ) : null}

      {recordType !== "custom-query" &&
      !genderActive &&
      payload &&
      !payload.unsupportedMessage ? (
        payload.rows.length > 0 ? (
          <>
            <LeaderboardList
              rows={payload.rows}
              valueLabel={payload.valueLabel}
              expandedRowKey={expandedRowKey}
              drilldownPayload={drilldown}
              onRowClick={onRowClick}
            />
          </>
        ) : (
          <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
            No records found.
          </div>
        )
      ) : null}

      {recordType === "custom-query" && customPayload ? (
        customPayload.rows.length > 0 ? (
          <LeaderboardList
            rows={customPayload.rows}
            valueLabel={customPayload.valueLabel}
            expandedRowKey={null}
            onRowClick={(row) => {
              if (customPayload.entity === "artists" && row.artist_id) {
                router.push(`/artist/${row.artist_id}`);
              }
            }}
          />
        ) : (
          <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
            No records found.
          </div>
        )
      ) : null}
    </section>
  );
}
