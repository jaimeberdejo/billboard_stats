import { type NextRequest } from "next/server";

import { parseChartType, type ChartType } from "@/lib/charts";
import { chartDepth } from "@/lib/chart-families";
import {
  type CustomCreditScope,
  type CustomEntity,
  type GenderFilter,
  getArtistRecordDrilldown,
  getCustomRecords,
  getGenderLeaderboard,
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

const CUSTOM_CREDIT_SCOPE_ALLOWLIST = new Set<CustomCreditScope>(["all", "lead"]);

/**
 * The gender filter vocabulary (GENDER-03). The five real values mirror the
 * artists_gender_check vocabulary in schema.sql plus the opt-in "all" default.
 * The query param is validated against this Set BEFORE it is bound as $N — it is
 * never interpolated into SQL (T-14-04-V).
 */
const GENDER_ALLOWLIST = new Set<GenderFilter>([
  "all",
  "female",
  "male",
  "group",
  "mixed",
  "unknown",
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

function parseCustomCreditScope(value: string | null): CustomCreditScope {
  return value !== null && CUSTOM_CREDIT_SCOPE_ALLOWLIST.has(value as CustomCreditScope)
    ? (value as CustomCreditScope)
    : "all";
}

/**
 * Parse the gender filter against the allowlist, defaulting to "all" when the
 * param is absent or invalid. Gender is opt-in, so a missing/unknown value is
 * NOT a 400 — it simply means the unfiltered ("All") view (GENDER-03).
 */
function parseGender(value: string | null): GenderFilter {
  return value !== null && GENDER_ALLOWLIST.has(value as GenderFilter)
    ? (value as GenderFilter)
    : "all";
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
  // Registry-derived chart depth (e.g. 100 / 200 / 50), replacing the hardcoded
  // hot-100 ? 100 : 200 so position-range validation works for any chart.
  return chartDepth(chart);
}

export async function GET(request: NextRequest): Promise<Response> {
  const { searchParams } = request.nextUrl;
  const mode = searchParams.get("mode");
  // Validate the chart slug against the registry (parseChartType resolves it via
  // the active charts set). Any active chart slug is accepted — the records
  // subsystem reads the polymorphic chart_entries path keyed by chart_id.
  const chart = await parseChartType(searchParams.get("chart"));

  if (!chart) {
    return Response.json(
      { error: 'Invalid or missing "chart" parameter. Must be an active chart slug.' },
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

    const limit = parsePositiveInteger(searchParams.get("limit"), 1, 1000) ?? 50;
    const creditScope = parseCustomCreditScope(searchParams.get("creditScope"));

    try {
      const payload = await getPresetRecords(record, chart, limit, creditScope);
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
    const startYear = parsePositiveInteger(searchParams.get("startYear"), 1950, 2100);
    const endYear = parsePositiveInteger(searchParams.get("endYear"), 1950, 2100);
    const limit = parsePositiveInteger(searchParams.get("limit"), 1, 1000) ?? 50;

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
    if (startYear && endYear && startYear > endYear) {
      return Response.json(
        { error: 'Custom mode received an invalid year range: start year exceeds end year.' },
        { status: 400 },
      );
    }

    try {
      const payload = await getCustomRecords({
        entity,
        chart,
        creditScope: parseCustomCreditScope(searchParams.get("creditScope")),
        rankBy,
        rankByParam,
        sortDir,
        peakMin,
        peakMax,
        weeksMin,
        debutPosMin,
        debutPosMax,
        startYear,
        endYear,
        limit,
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

  if (mode === "gender") {
    // Gender is opt-in: a missing/invalid value defaults to "all" (never a 400).
    // The value is allowlist-validated before binding (T-14-04-V); limit reuses
    // the existing 1..1000 clamp (T-14-04-D).
    const gender = parseGender(searchParams.get("gender"));
    const limit = parsePositiveInteger(searchParams.get("limit"), 1, 1000) ?? 50;

    try {
      const payload = await getGenderLeaderboard(chart, gender, limit);
      return Response.json(payload, {
        headers: { "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400" },
      });
    } catch {
      return Response.json(
        { error: "Failed to load gender leaderboard. Please try again later." },
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
    const creditScope = parseCustomCreditScope(searchParams.get("creditScope"));

    try {
      const payload = await getArtistRecordDrilldown(
        record,
        chart,
        artistId,
        chartDate,
        creditScope,
      );
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
    { error: 'Invalid or missing "mode" parameter. Expected "preset", "custom", "gender", or "drilldown".' },
    { status: 400 },
  );
}
