import type {
  RecordsCustomInterpretation,
  RecordsPresetInterpretation,
} from "./schema.ts";

type ChartType = RecordsCustomInterpretation["chart"];
type CustomEntity = RecordsCustomInterpretation["entity"];
type CustomRankBy = RecordsCustomInterpretation["rankBy"];
type RecordPreset = RecordsPresetInterpretation["record"];

export const CHART_ALIASES: Record<string, ChartType> = {
  "hot 100": "hot-100",
  hot100: "hot-100",
  "billboard 200": "billboard-200",
  b200: "billboard-200",
  "billboard200": "billboard-200",
};

export const ENTITY_ALIASES: Record<string, CustomEntity | "mixed"> = {
  song: "songs",
  songs: "songs",
  track: "songs",
  tracks: "songs",
  album: "albums",
  albums: "albums",
  artist: "artists",
  artists: "artists",
  mixed: "mixed",
};

export const PRESET_ALIASES: Record<string, RecordPreset> = {
  "most weeks at #1": "most-weeks-at-number-one",
  "most weeks at number one": "most-weeks-at-number-one",
  "longest chart runs": "longest-chart-runs",
  "most top 10 weeks": "most-top-10-weeks",
  "most #1 songs by artist": "most-number-one-songs-by-artist",
  "most number one songs by artist": "most-number-one-songs-by-artist",
  "most #1 albums by artist": "most-number-one-albums-by-artist",
  "most number one albums by artist": "most-number-one-albums-by-artist",
  "most entries by artist": "most-entries-by-artist",
  "most total chart weeks by artist": "most-total-chart-weeks-by-artist",
  "most simultaneous entries": "most-simultaneous-entries",
};

export const METRIC_ALIASES: Record<
  string,
  { rankBy: CustomRankBy; rankByParam?: number }
> = {
  "#1": { rankBy: "weeks-at-number-one" },
  "number one": { rankBy: "weeks-at-number-one" },
  "weeks at #1": { rankBy: "weeks-at-number-one" },
  "weeks at number one": { rankBy: "weeks-at-number-one" },
  "most weeks": { rankBy: "total-weeks" },
  "least weeks": { rankBy: "total-weeks" },
  "most chart weeks": { rankBy: "total-weeks" },
  "least chart weeks": { rankBy: "total-weeks" },
  "total weeks": { rankBy: "total-weeks" },
  "weeks on chart": { rankBy: "total-weeks" },
  "specific position": { rankBy: "weeks-at-position" },
  "position #": { rankBy: "weeks-at-position" },
  "top 3": { rankBy: "weeks-in-top-n", rankByParam: 3 },
  "top 5": { rankBy: "weeks-in-top-n", rankByParam: 5 },
  "top 10": { rankBy: "weeks-in-top-n", rankByParam: 10 },
  "top 40": { rankBy: "weeks-in-top-n", rankByParam: 40 },
  "most entries": { rankBy: "most-entries" },
  "number one entries": { rankBy: "number-one-entries" },
  "most #1 songs": { rankBy: "number-one-entries" },
  "most #1 albums": { rankBy: "number-one-entries" },
};

export const UNSUPPORTED_CUE_WORDS = [
  "since",
  "before",
  "after",
  "year",
  "years",
  "genre",
  "female",
  "male",
  "why",
  "explain",
  "compare",
] as const;
