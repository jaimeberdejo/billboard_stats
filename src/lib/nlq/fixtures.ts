import type {
  InterpretedQuery,
  RecordsCustomInterpretation,
  RecordsPresetInterpretation,
  SearchInterpretation,
} from "./schema.ts";

export interface GoldenQueryFixture {
  name: string;
  question: string;
  expectedStatus: InterpretedQuery["status"];
  expectedIntent: InterpretedQuery["intent"];
  expectedSearch?: Partial<SearchInterpretation> | null;
  expectedRecordsPreset?: Partial<RecordsPresetInterpretation> | null;
  expectedRecordsCustom?: Partial<RecordsCustomInterpretation> | null;
  expectedExplanationIncludes: string[];
  expectedWarningsIncludes?: string[];
  expectedAmbiguityIncludes?: string[];
}

export const GOLDEN_QUERY_FIXTURES: GoldenQueryFixture[] = [
  {
    name: "short-search-needs-clarification",
    question: "a",
    expectedStatus: "needs_clarification",
    expectedIntent: "clarify",
    expectedSearch: null,
    expectedExplanationIncludes: ["at least 2 characters"],
    expectedAmbiguityIncludes: ["at least 2 characters"],
  },
  {
    name: "mixed-search-query",
    question: "Taylor Swift",
    expectedStatus: "ok",
    expectedIntent: "search",
    expectedSearch: {
      entity: "mixed",
      query: "taylor swift",
    },
    expectedExplanationIncludes: ["grouped search", "taylor swift"],
    expectedWarningsIncludes: ["songs, albums, and artists"],
  },
  {
    name: "preset-records-query",
    question: "most simultaneous entries",
    expectedStatus: "ok",
    expectedIntent: "records_preset",
    expectedRecordsPreset: {
      chart: "hot-100",
      record: "most-simultaneous-entries",
    },
    expectedExplanationIncludes: ["most simultaneous entries", "Hot 100"],
  },
  {
    name: "custom-records-query",
    question: "show me songs with the most weeks in the top 10 by Drake",
    expectedStatus: "ok",
    expectedIntent: "records_custom",
    expectedRecordsCustom: {
      entity: "songs",
      chart: "hot-100",
      rankBy: "weeks-in-top-n",
      rankByParam: 10,
      artistNames: ["drake"],
    },
    expectedExplanationIncludes: ["Hot 100 songs records query", "top 10"],
  },
  {
    name: "unsupported-out-of-scope",
    question: "best female artists since 2010",
    expectedStatus: "unsupported",
    expectedIntent: "unsupported",
    expectedExplanationIncludes: ["outside the supported Billboard search and records vocabulary"],
    expectedAmbiguityIncludes: ['"since"'],
  },
  {
    name: "artist-records-needs-chart-clarification",
    question: "artists with most entries",
    expectedStatus: "needs_clarification",
    expectedIntent: "clarify",
    expectedRecordsCustom: null,
    expectedExplanationIncludes: ["need a chart type"],
    expectedAmbiguityIncludes: ["need a chart type"],
  },
  {
    name: "invalid-entity-chart-combination",
    question: "billboard 200 songs with most weeks at #1",
    expectedStatus: "needs_clarification",
    expectedIntent: "clarify",
    expectedExplanationIncludes: ["Song records can only be interpreted against the Hot 100 contract"],
    expectedAmbiguityIncludes: ["Song records can only be interpreted against the Hot 100 contract"],
  },
  {
    name: "invalid-entity-rankby-combination",
    question: "artists with weeks at position 5 on the hot 100",
    expectedStatus: "needs_clarification",
    expectedIntent: "clarify",
    expectedExplanationIncludes: ["Artist records queries only support total weeks, most entries, or chart-specific number one entries"],
    expectedAmbiguityIncludes: ["Artist records queries only support total weeks, most entries, or chart-specific number one entries"],
  },
  {
    name: "invalid-preset-chart-combination",
    question: "most simultaneous entries on billboard 200",
    expectedStatus: "unsupported",
    expectedIntent: "unsupported",
    expectedExplanationIncludes: ["outside the supported Billboard search and records vocabulary"],
    expectedAmbiguityIncludes: ["only available for the Hot 100"],
  },
];
