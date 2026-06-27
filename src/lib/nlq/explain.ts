import { chartEntityKind, chartTitle } from "../chart-families.ts";
import type {
  InterpretedQuery,
  RecordsCustomInterpretation,
  RecordsPresetInterpretation,
  SearchInterpretation,
} from "./schema.ts";

type ExplanationSubject = Pick<
  InterpretedQuery,
  "status" | "intent" | "search" | "recordsPreset" | "recordsCustom"
>;

function chartLabel(chart: string): string {
  // Registry-seeded human title, replacing the closed hot-100/billboard-200
  // ternary so any ingested chart renders its real name.
  return chartTitle(chart);
}

function recordLabel(record: RecordsPresetInterpretation["record"]): string {
  return record.replaceAll("-", " ");
}

function rankLabel(query: RecordsCustomInterpretation): string {
  switch (query.rankBy) {
    case "weeks-at-number-one":
      return "weeks at #1";
    case "total-weeks":
      return "total weeks on chart";
    case "weeks-at-position":
      return `weeks at position #${query.rankByParam}`;
    case "weeks-in-top-n":
      return `weeks in the top ${query.rankByParam}`;
    case "most-entries":
      return "most chart entries";
    case "number-one-entries":
      // Entity_kind-derived label (registry), not the hot-100/billboard-200
      // literal: song charts rank #1 songs, album charts rank #1 albums.
      return chartEntityKind(query.chart) === "song"
        ? "most #1 songs"
        : "most #1 albums";
  }
}

function searchExplanation(search: SearchInterpretation): string {
  if (search.entity === "mixed") {
    return `Interpret as a grouped search for matches to "${search.query}".`;
  }

  return `Interpret as a ${search.entity} search for "${search.query}".`;
}

function presetExplanation(recordsPreset: RecordsPresetInterpretation): string {
  return `Interpret as the ${recordLabel(recordsPreset.record)} leaderboard for the ${chartLabel(recordsPreset.chart)}.`;
}

function customExplanation(recordsCustom: RecordsCustomInterpretation): string {
  return `Interpret as a ${chartLabel(recordsCustom.chart)} ${recordsCustom.entity} records query ranked by ${rankLabel(recordsCustom)}.`;
}

export function buildInterpretationExplanation(
  query: ExplanationSubject,
  ambiguityReasons: string[] = [],
): string {
  if (query.status === "unsupported") {
    return "This question is outside the supported Billboard search and records vocabulary for Phase 7.";
  }

  if (query.status === "needs_clarification") {
    if (ambiguityReasons.length > 0) {
      return ambiguityReasons[0];
    }

    return "This question needs clarification before it can be mapped to a supported search or records contract.";
  }

  if (query.intent === "search" && query.search) {
    return searchExplanation(query.search);
  }

  if (query.intent === "records_preset" && query.recordsPreset) {
    return presetExplanation(query.recordsPreset);
  }

  if (query.intent === "records_custom" && query.recordsCustom) {
    return customExplanation(query.recordsCustom);
  }

  return "This question was interpreted successfully.";
}

export function buildInterpretationWarnings(
  query: ExplanationSubject,
  warnings: string[] = [],
): string[] {
  const nextWarnings = [...warnings];

  if (query.intent === "search" && query.search?.entity === "mixed") {
    nextWarnings.push("Search results may include songs, albums, and artists.");
  }

  return nextWarnings;
}

export function buildInterpretationAmbiguityReasons(
  _query: ExplanationSubject,
  ambiguityReasons: string[] = [],
): string[] {
  return [...ambiguityReasons];
}
