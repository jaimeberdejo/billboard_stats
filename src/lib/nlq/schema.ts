import { z } from "zod";

export const interpretationStatusSchema = z.enum([
  "ok",
  "needs_clarification",
  "unsupported",
]);

export const interpretationIntentSchema = z.enum([
  "search",
  "records_preset",
  "records_custom",
  "clarify",
  "unsupported",
]);

export const searchEntitySchema = z.enum([
  "songs",
  "albums",
  "artists",
  "mixed",
]);

export const chartTypeSchema = z.enum(["hot-100", "billboard-200"]);

export const recordPresetSchema = z.enum([
  "most-weeks-at-number-one",
  "longest-chart-runs",
  "most-top-10-weeks",
  "most-number-one-songs-by-artist",
  "most-number-one-albums-by-artist",
  "most-entries-by-artist",
  "most-total-chart-weeks-by-artist",
  "most-simultaneous-entries",
]);

export const customRankBySchema = z.enum([
  "weeks-at-number-one",
  "total-weeks",
  "weeks-at-position",
  "weeks-in-top-n",
  "most-entries",
  "number-one-entries",
]);

export const customEntitySchema = z.enum(["songs", "albums", "artists"]);

export const searchInterpretationSchema = z.object({
  entity: searchEntitySchema,
  query: z.string().min(2),
});

export const recordsPresetInterpretationSchema = z.object({
  chart: chartTypeSchema,
  record: recordPresetSchema,
});

export const recordsCustomInterpretationSchema = z.object({
  entity: customEntitySchema,
  chart: chartTypeSchema,
  rankBy: customRankBySchema,
  rankByParam: z.number().int().positive(),
  sortDir: z.enum(["asc", "desc"]).default("desc"),
  peakMin: z.number().int().positive().nullable(),
  peakMax: z.number().int().positive().nullable(),
  weeksMin: z.number().int().positive().nullable(),
  debutPosMin: z.number().int().positive().nullable(),
  debutPosMax: z.number().int().positive().nullable(),
  artistNames: z.array(z.string().min(1)).nullable(),
});

export const interpretedQuerySchema = z.object({
  originalQuestion: z.string(),
  normalizedQuestion: z.string(),
  status: interpretationStatusSchema,
  intent: interpretationIntentSchema,
  explanation: z.string(),
  warnings: z.array(z.string()),
  ambiguityReasons: z.array(z.string()),
  search: searchInterpretationSchema.nullable(),
  recordsPreset: recordsPresetInterpretationSchema.nullable(),
  recordsCustom: recordsCustomInterpretationSchema.nullable(),
});

export type InterpretationStatus = z.infer<typeof interpretationStatusSchema>;
export type InterpretationIntent = z.infer<typeof interpretationIntentSchema>;
export type SearchEntity = z.infer<typeof searchEntitySchema>;
export type SearchInterpretation = z.infer<typeof searchInterpretationSchema>;
export type RecordsPresetInterpretation = z.infer<
  typeof recordsPresetInterpretationSchema
>;
export type RecordsCustomInterpretation = z.infer<
  typeof recordsCustomInterpretationSchema
>;
export type InterpretedQuery = z.infer<typeof interpretedQuerySchema>;
