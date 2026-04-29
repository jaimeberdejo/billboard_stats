import { type NextRequest } from "next/server";

import { parseChartType, type ChartType } from "@/lib/charts";
import {
  type CustomEntity,
  getArtistRecordDrilldown,
  getCustomRecords,
  getPresetRecords,
  type CustomRankBy,
  type RecordPreset,
} from "@/lib/records";

const PRESET_ALLOWLIST = new Set<RecordPreset>([
  "most-weeks-at-number-one",
  "longest-chart-runs",
  "most-top-10-weeks",
  "most-number-one-songs-by-artist",
  "most-number-one-albums-by-artist",
  "most-entries-by-artist",
  "most-total-chart-weeks-by-artist",
  "most-simultaneous-entries",
]);

const CUSTOM_RANK_BY_ALLOWLIST = new Set<CustomRankBy>([
  "weeks-at-number-one",
  "total-weeks",
  "weeks-at-position",
  "weeks-in-top-n",
  "most-entries",
  "number-one-entries",
]);

const CUSTOM_ENTITY_ALLOWLIST = new Set<CustomEntity>([
  "songs",
  "albums",
  "artists",
]);

function parsePositiveInteger(
  value: string | null,
  minimum = 1,
  maximum = Number.MAX_SAFE_INTEGER,
): number | null {
  if (!value || !/^\d+$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    return null;
  }
  return parsed;
}

function isValidRecordPreset(value: string | null): value is RecordPreset {
  return value !== null && PRESET_ALLOWLIST.has(value as RecordPreset);
}

function isValidCustomRankBy(value: string | null): value is CustomRankBy {
  return value !== null && CUSTOM_RANK_BY_ALLOWLIST.has(value as CustomRankBy);
}

function isValidCustomEntity(value: string | null): value is CustomEntity {
  return value !== null && CUSTOM_ENTITY_ALLOWLIST.has(value as CustomEntity);
}

function parseArtistNames(value: string | null): string[] | null {
  if (!value) {
    return null;
  }
  const parts = value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.length > 0 ? parts : null;
}

function maxPositionForChart(chart: ChartType): number {
  return chart === "hot-100" ? 100 : 200;
}

export async function GET(request: NextRequest): Promise<Response> {
  const { searchParams } = request.nextUrl;
  const mode = searchParams.get("mode");
  const chart = parseChartType(searchParams.get("chart"));

  if (!chart) {
    return Response.json(
      { error: 'Invalid or missing "chart" parameter. Must be "hot-100" or "billboard-200".' },
      { status: 400 },
    );
  }

  if (mode === "preset") {
    const record = searchParams.get("record");
    if (!isValidRecordPreset(record)) {
      return Response.json(
        { error: 'Invalid or missing "record" parameter for preset mode.' },
        { status: 400 },
      );
    }

    try {
      const payload = await getPresetRecords(record, chart);
      return Response.json(payload, {
        headers: { "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400" },
      });
    } catch {
      return Response.json(
        { error: "Failed to load preset records. Please try again later." },
        { status: 500 },
      );
    }
  }

  if (mode === "custom") {
    const entity = searchParams.get("entity");
    if (!isValidCustomEntity(entity)) {
      return Response.json(
        { error: 'Invalid or missing "entity" parameter for custom mode.' },
        { status: 400 },
      );
    }

    const rankBy = searchParams.get("rankBy");
    if (!isValidCustomRankBy(rankBy)) {
      return Response.json(
        { error: 'Invalid or missing "rankBy" parameter for custom mode.' },
        { status: 400 },
      );
    }

    const maxPosition = maxPositionForChart(chart);
    const defaultRankByParam = rankBy === "weeks-at-position" ? 1 : 10;
    const rankByParam =
      parsePositiveInteger(searchParams.get("rankByParam"), 1, maxPosition) ??
      defaultRankByParam;
    const sortDir =
      searchParams.get("sortDir") === "asc" ? "asc" : "desc";
    const peakMin = parsePositiveInteger(searchParams.get("peakMin"), 1, maxPosition);
    const peakMax = parsePositiveInteger(searchParams.get("peakMax"), 1, maxPosition);
    const weeksMin = parsePositiveInteger(searchParams.get("weeksMin"), 1, 10000);
    const debutPosMin = parsePositiveInteger(searchParams.get("debutPosMin"), 1, maxPosition);
    const debutPosMax = parsePositiveInteger(searchParams.get("debutPosMax"), 1, maxPosition);

    if (peakMin && peakMax && peakMin > peakMax) {
      return Response.json(
        { error: 'Custom mode received an invalid peak range: minimum exceeds maximum.' },
        { status: 400 },
      );
    }
    if (debutPosMin && debutPosMax && debutPosMin > debutPosMax) {
      return Response.json(
        { error: 'Custom mode received an invalid debut range: minimum exceeds maximum.' },
        { status: 400 },
      );
    }

    try {
      const payload = await getCustomRecords({
        entity,
        chart,
        rankBy,
        rankByParam,
        sortDir,
        peakMin,
        peakMax,
        weeksMin,
        debutPosMin,
        debutPosMax,
        artistNames: parseArtistNames(searchParams.get("artistNames")),
      });
      return Response.json(payload, {
        headers: { "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400" },
      });
    } catch {
      return Response.json(
        { error: "Failed to load custom records. Please try again later." },
        { status: 500 },
      );
    }
  }

  if (mode === "drilldown") {
    const record = searchParams.get("record");
    if (!isValidRecordPreset(record)) {
      return Response.json(
        { error: 'Invalid or missing "record" parameter for drilldown mode.' },
        { status: 400 },
      );
    }

    const artistId = parsePositiveInteger(searchParams.get("artistId"));
    if (!artistId) {
      return Response.json(
        { error: 'Invalid or missing "artistId" parameter for drilldown mode.' },
        { status: 400 },
      );
    }

    const chartDate = searchParams.get("chartDate")?.trim() ?? undefined;

    try {
      const payload = await getArtistRecordDrilldown(record, chart, artistId, chartDate);
      return Response.json(payload, {
        headers: { "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400" },
      });
    } catch {
      return Response.json(
        { error: "Failed to load record drilldown data. Please try again later." },
        { status: 500 },
      );
    }
  }

  return Response.json(
    { error: 'Invalid or missing "mode" parameter. Expected "preset", "custom", or "drilldown".' },
    { status: 400 },
  );
}
