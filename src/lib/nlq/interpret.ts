import {
  CHART_ALIASES,
  ENTITY_ALIASES,
  METRIC_ALIASES,
  PRESET_ALIASES,
  UNSUPPORTED_CUE_WORDS,
} from "./catalog.ts";
import {
  buildInterpretationAmbiguityReasons,
  buildInterpretationExplanation,
  buildInterpretationWarnings,
} from "./explain.ts";
import {
  type InterpretationIntent,
  type InterpretationStatus,
  type InterpretedQuery,
  type RecordsCustomInterpretation,
  type RecordsPresetInterpretation,
  type SearchInterpretation,
  interpretedQuerySchema,
} from "./schema.ts";
import {
  extractPositiveIntegers,
  normalizeQuestion,
  splitArtistNames,
  tokenizeQuestion,
} from "./normalize.ts";

type ChartType = RecordsCustomInterpretation["chart"];

interface InterpretationDraft {
  status: InterpretationStatus;
  intent: InterpretationIntent;
  search: SearchInterpretation | null;
  recordsPreset: RecordsPresetInterpretation | null;
  recordsCustom: RecordsCustomInterpretation | null;
  ambiguityHints?: string[];
  warningHints?: string[];
}

const SEARCH_COMMAND_PREFIXES = [
  "search",
  "find",
  "lookup",
  "show me",
  "show",
];

const ARTIST_FILTER_RE = /\bby\s+([a-z0-9,&.'\-\s]+)$/i;
const MIN_WEEKS_RE = /\b(?:at least|min(?:imum)?|over)\s+(\d+)\s+weeks?\b/i;
const DEBUT_RANGE_RE = /\bdebut(?:ed)?\s+(?:between\s+)?#?(\d+)(?:\s+(?:and|to|-)\s+#?(\d+))?/i;
const PEAK_RANGE_RE = /\bpeak(?:ed)?\s+(?:between\s+)?#?(\d+)(?:\s+(?:and|to|-)\s+#?(\d+))?/i;

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function hasAlias(normalizedQuestion: string, alias: string): boolean {
  return new RegExp(`(^|\\s)${escapeRegExp(alias)}(\\s|$)`).test(
    normalizedQuestion,
  );
}

function detectUnsupportedCue(normalizedQuestion: string): string | null {
  return (
    UNSUPPORTED_CUE_WORDS.find((cue) => hasAlias(normalizedQuestion, cue)) ?? null
  );
}

function findLongestAlias<T extends string>(
  normalizedQuestion: string,
  aliases: Record<string, T>,
): T | null {
  const matched = Object.entries(aliases)
    .filter(([alias]) => hasAlias(normalizedQuestion, alias))
    .sort((left, right) => right[0].length - left[0].length)[0];

  return matched?.[1] ?? null;
}

function findLongestAliasEntry<T extends string>(
  normalizedQuestion: string,
  aliases: Record<string, T>,
): [string, T] | null {
  const matched = Object.entries(aliases)
    .filter(([alias]) => hasAlias(normalizedQuestion, alias))
    .sort((left, right) => right[0].length - left[0].length)[0];

  return matched ?? null;
}

function inferChart(normalizedQuestion: string): ChartType | null {
  return findLongestAlias(normalizedQuestion, CHART_ALIASES);
}

function inferEntity(normalizedQuestion: string): "songs" | "albums" | "artists" | "mixed" | null {
  return findLongestAlias(normalizedQuestion, ENTITY_ALIASES);
}

function stripChartPhrases(normalizedQuestion: string): string {
  let stripped = normalizedQuestion;

  for (const alias of Object.keys(CHART_ALIASES).sort((left, right) => right.length - left.length)) {
    stripped = stripped.replace(new RegExp(`(^|\\s)${escapeRegExp(alias)}(\\s|$)`, "g"), " ");
  }

  return stripped.replace(/\b(on|for)\b/g, " ").replace(/\s+/g, " ").trim();
}

function isStandalonePresetQuestion(
  normalizedQuestion: string,
  presetAlias: string,
): boolean {
  let cleaned = stripChartPhrases(normalizedQuestion);

  for (const prefix of SEARCH_COMMAND_PREFIXES) {
    if (cleaned.startsWith(`${prefix} `)) {
      cleaned = cleaned.slice(prefix.length).trim();
      break;
    }
  }

  cleaned = cleaned.replace(/^the\s+/, "").trim();

  return cleaned === presetAlias;
}

function inferMetric(normalizedQuestion: string): {
  rankBy: RecordsCustomInterpretation["rankBy"];
  rankByParam?: number;
} | null {
  const [firstInteger] = extractPositiveIntegers(normalizedQuestion);
  const topMatch = normalizedQuestion.match(/\btop\s+(\d+)\b/);
  if (topMatch && firstInteger) {
    return {
      rankBy: "weeks-in-top-n",
      rankByParam: firstInteger,
    };
  }

  const positionMatch = normalizedQuestion.match(/\bposition\s+#?(\d+)\b/);
  if (positionMatch && firstInteger) {
    return {
      rankBy: "weeks-at-position",
      rankByParam: firstInteger,
    };
  }

  const matchedEntry = Object.entries(METRIC_ALIASES)
    .filter(([alias]) => hasAlias(normalizedQuestion, alias))
    .sort((left, right) => right[0].length - left[0].length)[0];
  if (matchedEntry) {
    return matchedEntry[1];
  }

  return null;
}

function inferSearchQuery(normalizedQuestion: string): string {
  let query = normalizedQuestion;

  for (const prefix of SEARCH_COMMAND_PREFIXES) {
    if (query.startsWith(`${prefix} `)) {
      query = query.slice(prefix.length).trim();
      break;
    }
  }

  for (const [alias] of Object.entries(ENTITY_ALIASES)) {
    if (query.startsWith(`${alias} `)) {
      query = query.slice(alias.length).trim();
      break;
    }
  }

  return query.trim();
}

function buildSearchInterpretation(normalizedQuestion: string): InterpretationDraft {
  const entity = inferEntity(normalizedQuestion) ?? "mixed";
  const query = inferSearchQuery(normalizedQuestion);

  if (query.length < 2) {
    return {
      status: "needs_clarification",
      intent: "clarify",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        "Search queries need at least 2 characters after removing command words.",
      ],
    };
  }

  return {
    status: "ok",
    intent: "search",
    search: {
      entity,
      query,
    },
    recordsPreset: null,
    recordsCustom: null,
  };
}

function validatePresetChart(
  preset: RecordsPresetInterpretation["record"],
  chart: ChartType,
): string | null {
  if (preset === "most-simultaneous-entries" && chart === "billboard-200") {
    return "Most simultaneous entries is only available for the Hot 100.";
  }
  if (preset === "most-number-one-songs-by-artist" && chart === "billboard-200") {
    return "Most #1 songs by artist is only available for the Hot 100.";
  }
  if (preset === "most-number-one-albums-by-artist" && chart === "hot-100") {
    return "Most #1 albums by artist is only available for the Billboard 200.";
  }

  return null;
}

function buildPresetInterpretation(normalizedQuestion: string): InterpretationDraft | null {
  const presetEntry = findLongestAliasEntry(normalizedQuestion, PRESET_ALIASES);
  if (!presetEntry) {
    return null;
  }
  const [presetAlias, record] = presetEntry;

  if (!isStandalonePresetQuestion(normalizedQuestion, presetAlias)) {
    return null;
  }

  const explicitChart = inferChart(normalizedQuestion);
  let chart = explicitChart;

  if (!chart) {
    if (record === "most-number-one-songs-by-artist" || record === "most-simultaneous-entries") {
      chart = "hot-100";
    } else if (record === "most-number-one-albums-by-artist") {
      chart = "billboard-200";
    }
  }

  if (!chart) {
    return {
      status: "needs_clarification",
      intent: "clarify",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        "This records leaderboard needs a chart type before it can be interpreted.",
      ],
    };
  }

  const incompatibility = validatePresetChart(record, chart);
  if (incompatibility) {
    return {
      status: "unsupported",
      intent: "unsupported",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [incompatibility],
    };
  }

  return {
    status: "ok",
    intent: "records_preset",
    search: null,
    recordsPreset: {
      chart,
      record,
    },
    recordsCustom: null,
  };
}

function inferArtistNames(normalizedQuestion: string): string[] | null {
  const byMatch = normalizedQuestion.match(ARTIST_FILTER_RE);
  if (!byMatch) {
    return null;
  }

  const names = splitArtistNames(byMatch[1]);
  return names.length > 0 ? names : null;
}

function inferWeeksMin(normalizedQuestion: string): number | null {
  const explicit = normalizedQuestion.match(MIN_WEEKS_RE);
  if (explicit) {
    return Number(explicit[1]);
  }

  const plusMatch = normalizedQuestion.match(/\b(\d+)\+\s+weeks?\b/i);
  if (plusMatch) {
    return Number(plusMatch[1]);
  }

  return null;
}

function inferRange(
  normalizedQuestion: string,
  pattern: RegExp,
): { min: number | null; max: number | null } {
  const match = normalizedQuestion.match(pattern);
  if (!match) {
    return { min: null, max: null };
  }

  const min = Number(match[1]);
  const max = match[2] ? Number(match[2]) : min;

  return { min, max };
}

function chartMax(chart: ChartType): number {
  return chart === "hot-100" ? 100 : 200;
}

function buildCustomInterpretation(normalizedQuestion: string): InterpretationDraft | null {
  const metric = inferMetric(normalizedQuestion);
  const explicitChart = inferChart(normalizedQuestion);
  const entity = inferEntity(normalizedQuestion);
  const artistEntity = entity === "mixed" ? null : entity;
  const artistNames = inferArtistNames(normalizedQuestion);
  const weeksMin = inferWeeksMin(normalizedQuestion);
  const peakRange = inferRange(normalizedQuestion, PEAK_RANGE_RE);
  const debutRange = inferRange(normalizedQuestion, DEBUT_RANGE_RE);
  const recordsCuePresent =
    explicitChart !== null ||
    artistEntity !== null ||
    artistNames !== null ||
    weeksMin !== null ||
    peakRange.min !== null ||
    debutRange.min !== null ||
    /\b(entries|weeks|peak|debut|position|top\s+\d+)\b/.test(normalizedQuestion);

  if (!metric) {
    if (!recordsCuePresent) {
      return null;
    }

    return {
      status: "needs_clarification",
      intent: "clarify",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        "This records-style question needs a supported ranking metric before it can be interpreted.",
      ],
    };
  }

  let resolvedEntity = artistEntity;
  if (!resolvedEntity) {
    if (metric.rankBy === "most-entries" || metric.rankBy === "number-one-entries") {
      resolvedEntity = "artists";
    } else if (explicitChart === "hot-100") {
      resolvedEntity = "songs";
    } else if (explicitChart === "billboard-200") {
      resolvedEntity = "albums";
    }
  }

  if (!resolvedEntity) {
    return {
      status: "needs_clarification",
      intent: "clarify",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        "This records query needs a target entity such as songs, albums, or artists.",
      ],
    };
  }

  let resolvedChart = explicitChart;
  if (!resolvedChart) {
    if (resolvedEntity === "songs") {
      resolvedChart = "hot-100";
    } else if (resolvedEntity === "albums") {
      resolvedChart = "billboard-200";
    }
  }

  if (!resolvedChart) {
    return {
      status: "needs_clarification",
      intent: "clarify",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        "Artist records queries need a chart type such as Hot 100 or Billboard 200.",
      ],
    };
  }

  if (resolvedEntity === "songs" && resolvedChart !== "hot-100") {
    return {
      status: "needs_clarification",
      intent: "clarify",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        "Song records can only be interpreted against the Hot 100 contract.",
      ],
    };
  }

  if (resolvedEntity === "albums" && resolvedChart !== "billboard-200") {
    return {
      status: "needs_clarification",
      intent: "clarify",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        "Album records can only be interpreted against the Billboard 200 contract.",
      ],
    };
  }

  const songAlbumRankBys: Array<RecordsCustomInterpretation["rankBy"]> = [
    "weeks-at-number-one",
    "total-weeks",
    "weeks-at-position",
    "weeks-in-top-n",
  ];
  const artistRankBys: Array<RecordsCustomInterpretation["rankBy"]> = [
    "total-weeks",
    "most-entries",
    "number-one-entries",
  ];

  if (
    resolvedEntity === "artists" &&
    !artistRankBys.includes(metric.rankBy)
  ) {
    return {
      status: "needs_clarification",
      intent: "clarify",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        "Artist records queries only support total weeks, most entries, or chart-specific number one entries.",
      ],
    };
  }

  if (
    (resolvedEntity === "songs" || resolvedEntity === "albums") &&
    !songAlbumRankBys.includes(metric.rankBy)
  ) {
    return {
      status: "needs_clarification",
      intent: "clarify",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        "Song and album records queries only support #1 weeks, total weeks, specific positions, or top-N runs.",
      ],
    };
  }

  const resolvedRankByParam =
    metric.rankByParam ??
    (metric.rankBy === "weeks-at-position" ? 1 : metric.rankBy === "weeks-in-top-n" ? 10 : 1);
  const maxPosition = chartMax(resolvedChart);

  if (
    (metric.rankBy === "weeks-at-position" || metric.rankBy === "weeks-in-top-n") &&
    resolvedRankByParam > maxPosition
  ) {
    return {
      status: "needs_clarification",
      intent: "clarify",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        `The ${resolvedChart === "hot-100" ? "Hot 100" : "Billboard 200"} does not support that position range.`,
      ],
    };
  }

  if (
    peakRange.min !== null &&
    peakRange.max !== null &&
    peakRange.min > peakRange.max
  ) {
    return {
      status: "needs_clarification",
      intent: "clarify",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        "Peak range filters need a minimum that does not exceed the maximum.",
      ],
    };
  }

  if (
    debutRange.min !== null &&
    debutRange.max !== null &&
    debutRange.min > debutRange.max
  ) {
    return {
      status: "needs_clarification",
      intent: "clarify",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        "Debut range filters need a minimum that does not exceed the maximum.",
      ],
    };
  }

  const recordsCustom: RecordsCustomInterpretation = {
    entity: resolvedEntity,
    chart: resolvedChart,
    rankBy: metric.rankBy,
    rankByParam: resolvedRankByParam,
    sortDir: normalizeQuestion(normalizedQuestion).includes("least weeks")
      ? "asc"
      : "desc",
    peakMin: peakRange.min,
    peakMax: peakRange.max,
    weeksMin,
    debutPosMin: debutRange.min,
    debutPosMax: debutRange.max,
    artistNames,
  };

  return {
    status: "ok",
    intent: "records_custom",
    search: null,
    recordsPreset: null,
    recordsCustom,
  };
}

function finalizeInterpretation(
  originalQuestion: string,
  normalizedQuestion: string,
  draft: InterpretationDraft,
): InterpretedQuery {
  const partial: Omit<
    InterpretedQuery,
    "originalQuestion" | "normalizedQuestion" | "explanation" | "warnings" | "ambiguityReasons"
  > = {
    status: draft.status,
    intent: draft.intent,
    search: draft.search,
    recordsPreset: draft.recordsPreset,
    recordsCustom: draft.recordsCustom,
  };

  const explanationSubject = {
    ...partial,
  };
  const ambiguityReasons = buildInterpretationAmbiguityReasons(
    explanationSubject,
    draft.ambiguityHints ?? [],
  );
  const warnings = buildInterpretationWarnings(
    explanationSubject,
    draft.warningHints ?? [],
  );
  const explanation = buildInterpretationExplanation(
    explanationSubject,
    ambiguityReasons,
  );

  return interpretedQuerySchema.parse({
    originalQuestion,
    normalizedQuestion,
    ...partial,
    explanation,
    warnings,
    ambiguityReasons,
  });
}

export function interpretQuery(question: string): InterpretedQuery {
  const normalizedQuestion = normalizeQuestion(question);
  const unsupportedCue = detectUnsupportedCue(normalizedQuestion);

  if (unsupportedCue) {
    return finalizeInterpretation(question, normalizedQuestion, {
      status: "unsupported",
      intent: "unsupported",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        `Questions about "${unsupportedCue}" are outside the supported search and records vocabulary.`,
      ],
    });
  }

  const preset = buildPresetInterpretation(normalizedQuestion);
  if (preset) {
    return finalizeInterpretation(question, normalizedQuestion, preset);
  }

  const custom = buildCustomInterpretation(normalizedQuestion);
  if (custom) {
    return finalizeInterpretation(question, normalizedQuestion, custom);
  }

  if (tokenizeQuestion(normalizedQuestion).length === 0) {
    return finalizeInterpretation(question, normalizedQuestion, {
      status: "needs_clarification",
      intent: "clarify",
      search: null,
      recordsPreset: null,
      recordsCustom: null,
      ambiguityHints: [
        "A question is required before the interpreter can map it to search or records.",
      ],
    });
  }

  return finalizeInterpretation(
    question,
    normalizedQuestion,
    buildSearchInterpretation(normalizedQuestion),
  );
}
