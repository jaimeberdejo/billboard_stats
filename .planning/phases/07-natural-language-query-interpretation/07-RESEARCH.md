# Phase 7: Natural-Language Query Interpretation - Research

**Researched:** 2026-04-29
**Domain:** Constrained natural-language interpretation for Billboard search and records queries
**Confidence:** HIGH

## User Constraints

- No Phase 7 `CONTEXT.md` exists, so there are no locked user decisions to copy verbatim for this phase. [VERIFIED: `gsd-sdk query init.phase-op "7"`]
- Recommendations must stay grounded in the existing Phase 4 search/records implementation and roadmap boundaries rather than inventing a new chatbot surface. [VERIFIED: `.planning/ROADMAP.md`; `.planning/phases/04-search-records/04-CONTEXT.md`; user prompt]
- Phase 7 is interpretation only; safe execution belongs to Phase 8 and user-facing assistant UI belongs to Phase 9. [VERIFIED: `.planning/ROADMAP.md`; user prompt]
- The natural-language layer must not permit arbitrary SQL or generic assistant scope. [VERIFIED: user prompt]

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEARCH-01 | Fuzzy search across songs, albums, and artists (min 2 chars) | Map NL inputs to the existing `searchAll(query)` contract and preserve the current 2-character minimum and 50-row grouped response. [VERIFIED: `.planning/REQUIREMENTS.md`; `src/lib/search.ts`; `src/app/api/search/route.ts`] |
| RECORDS-02 | Custom Query Builder filtering by metric, sort, artist, peak, debut, and min-weeks | Map NL inputs to the existing `CustomRecordsInput` shape and current route allowlists for entity, `rankBy`, chart, ranges, and artist filters. [VERIFIED: `.planning/REQUIREMENTS.md`; `src/lib/records.ts`; `src/app/api/records/route.ts`; `src/components/records/custom-query-builder.tsx`] |
</phase_requirements>

## Summary

Phase 7 should introduce a typed intermediate representation for natural-language chart questions, not a direct NL-to-SQL path. The current app already has narrow execution contracts for grouped search results and allowlisted records modes, plus hard bounds for chart type, ranking dimensions, and numeric ranges. [VERIFIED: `src/lib/search.ts`; `src/app/api/search/route.ts`; `src/lib/records.ts`; `src/app/api/records/route.ts`] The safest planning move is to make Phase 7 interpret user text into that same bounded vocabulary and explicitly return `ok`, `needs_clarification`, or `unsupported` instead of trying to execute anything. [VERIFIED: `src/app/api/records/route.ts`; user prompt]

The repo does not currently contain any AI SDK, OpenAI SDK, or existing NLQ layer, while the current records/search behavior is already highly structured and domain-limited. [VERIFIED: `package.json`; repo grep; `src/lib/records.ts`; `src/lib/search.ts`] That makes a deterministic, schema-first interpreter the best default for planning: it minimizes new infrastructure, keeps execution safety aligned with Phase 8, and remains easy to regression-test with golden queries before a UI arrives in Phase 9. [VERIFIED: `package.json`; `.planning/ROADMAP.md`; `src/components/search/search-view.tsx`; `src/components/records/records-view.tsx`]

**Primary recommendation:** Use a server-side deterministic interpreter with shared Zod schemas, explicit intent/status enums, and zero direct SQL generation from natural-language input. [VERIFIED: `src/lib/records.ts`; `src/app/api/records/route.ts`; `https://zod.dev/basics?curius=1296&id=handling-errors`; `https://zod.dev/json-schema?id=configuration`]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Normalize raw user question | API / Backend | Browser / Client | Interpretation should stay server-side so the same contract can feed Phase 8 execution and Phase 9 UI without duplicating parsing logic in the browser. [VERIFIED: `src/app/api/search/route.ts`; `src/app/api/records/route.ts`; `https://nextjs.org/docs/app/api-reference/file-conventions/route`] |
| Classify intent (`search`, `records_preset`, `records_custom`, `clarify`, `unsupported`) | API / Backend | — | Intent selection determines which existing backend contract can be called later, so it belongs alongside the current allowlists and validation logic. [VERIFIED: `src/lib/search.ts`; `src/lib/records.ts`; `src/app/api/records/route.ts`] |
| Extract entity/chart/filter parameters | API / Backend | — | The current records route already owns valid enums, bounds, and range semantics for chart positions and filters. [VERIFIED: `src/app/api/records/route.ts`; `src/components/records/custom-query-builder.tsx`] |
| Produce user-visible interpretation/explanation | API / Backend | Browser / Client | The explanation text should be generated from the typed interpretation object server-side, while Phase 9 can render it client-side without redefining business rules. [VERIFIED: `.planning/ROADMAP.md`; user prompt] |
| Execute search/records query | API / Backend | Database / Storage | Actual execution is already implemented in server libs and remains Phase 8 work. [VERIFIED: `.planning/ROADMAP.md`; `src/lib/search.ts`; `src/lib/records.ts`] |

## Project Constraints (from CLAUDE.md)

- Read the relevant Next.js guide in `node_modules/next/dist/docs/` before writing code because this repo uses a breaking-change-heavy Next.js version. [VERIFIED: `CLAUDE.md`; `AGENTS.md`]
- Heed deprecation notices from the shipped Next.js docs rather than relying on training-era conventions. [VERIFIED: `CLAUDE.md`; `AGENTS.md`]

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `next` | `16.2.4` | Host the interpretation route in App Router Route Handlers. [VERIFIED: npm registry; `package.json`] | Route Handlers are already the repo’s API pattern and support `GET`/`POST` handlers in `app/api/*/route.ts`. [VERIFIED: `package.json`; `https://nextjs.org/docs/app/api-reference/file-conventions/route`] |
| `zod` | `4.3.6` | Define the shared interpretation schema and validate parser output. [VERIFIED: npm registry; `https://zod.dev/basics?curius=1296&id=handling-errors`; `https://zod.dev/json-schema?id=configuration`] | Zod gives typed parsing and Zod 4 can convert schemas to JSON Schema, which keeps an optional future AI fallback aligned to the same contract. [CITED: https://zod.dev/basics?curius=1296&id=handling-errors] [CITED: https://zod.dev/json-schema?id=configuration] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `openai` | `6.35.0` | Optional structured-output fallback if deterministic coverage later proves inadequate. [VERIFIED: npm registry] | Use only after a deterministic baseline exists and only against the same strict schema; do not make it the initial Phase 7 dependency. [CITED: https://developers.openai.com/api/docs/guides/structured-outputs] |
| `ai` | `6.0.169` | Optional provider abstraction for structured object generation. [VERIFIED: npm registry] | Use only if the project later wants provider flexibility or streaming interpretation UX in Phase 9. [CITED: https://vercel.com/docs/ai-sdk] |
| `@ai-sdk/openai` | `3.0.54` | Optional OpenAI provider adapter for AI SDK. [VERIFIED: npm registry] | Only relevant if the project adopts AI SDK instead of the direct OpenAI SDK later. [VERIFIED: npm registry; CITED: https://vercel.com/docs/ai-sdk] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Deterministic parser + Zod IR | OpenAI Structured Outputs | Better long-tail phrasing coverage, but adds API keys, latency, cost, and prompt-injection evaluation work before Phase 8 can safely trust it. [CITED: https://developers.openai.com/api/docs/guides/structured-outputs] |
| Direct OpenAI SDK fallback | Vercel AI SDK `generateObject` | AI SDK gives a clean provider abstraction, but it introduces an extra layer that the repo does not currently use. [CITED: https://vercel.com/docs/ai-sdk] [VERIFIED: `package.json`] |

**Installation:**
```bash
npm install zod@4.3.6
```

**Version verification:** `next@16.2.4` is already installed in the repo, while `zod@4.3.6`, `openai@6.35.0`, `ai@6.0.169`, and `@ai-sdk/openai@3.0.54` were verified against the npm registry on 2026-04-29. [VERIFIED: npm registry; `package.json`]

## Architecture Patterns

### System Architecture Diagram

```text
Browser text input
    |
    v
/api/query (interpret only)
    |
    +--> normalize question
    |
    +--> detect intent
    |      |
    |      +--> search
    |      +--> records_preset
    |      +--> records_custom
    |      +--> needs_clarification
    |      +--> unsupported
    |
    +--> extract + validate parameters against shared Zod schema
    |
    +--> build user-visible interpretation
    |
    v
Structured interpretation object
    |
    +--> Phase 8 executor maps to existing search/records libs
    +--> Phase 9 UI renders explanation, warnings, and clarifications
```

The interpretation route should stop at the structured object boundary and never call SQL helpers in Phase 7. [VERIFIED: `.planning/ROADMAP.md`; user prompt]

### Recommended Project Structure

```text
src/
├── app/
│   └── api/
│       └── query/
│           └── route.ts          # POST/GET interpretation endpoint only
├── lib/
│   └── nlq/
│       ├── schema.ts             # shared Zod schemas + TS types
│       ├── normalize.ts          # token cleanup, synonyms, ordinal parsing
│       ├── catalog.ts            # intent keywords, chart aliases, metric aliases
│       ├── interpret.ts          # main deterministic interpreter
│       ├── explain.ts            # user-visible interpretation text
│       └── fixtures.ts           # golden query cases for planning/evals
└── components/
    └── records/
        └── custom-query-builder.tsx  # existing execution contract reference
```

This keeps the new NLP layer parallel to the existing `src/lib/search.ts` and `src/lib/records.ts` modules instead of mixing freeform parsing into execution helpers. [VERIFIED: `src/lib/search.ts`; `src/lib/records.ts`]

### Pattern 1: Shared Intermediate Representation
**What:** Define one interpretation schema that can represent only the operations the current backend already supports. [VERIFIED: `src/lib/search.ts`; `src/lib/records.ts`; `src/app/api/records/route.ts`]
**When to use:** Use for every NL query before any execution decision. [VERIFIED: user prompt; `.planning/ROADMAP.md`]
**Example:**
```typescript
// Source: synthesized from src/lib/search.ts, src/lib/records.ts, and zod.dev basics
import { z } from "zod";

export const interpretedQuerySchema = z.object({
  status: z.enum(["ok", "needs_clarification", "unsupported"]),
  intent: z.enum([
    "search",
    "records_preset",
    "records_custom",
    "clarify",
    "unsupported",
  ]),
  explanation: z.string(),
  warnings: z.array(z.string()),
  ambiguityReasons: z.array(z.string()),
  search: z
    .object({
      entity: z.enum(["songs", "albums", "artists", "mixed"]),
      query: z.string().min(2),
    })
    .nullable(),
  recordsPreset: z
    .object({
      chart: z.enum(["hot-100", "billboard-200"]),
      record: z.enum([
        "most-weeks-at-number-one",
        "longest-chart-runs",
        "most-top-10-weeks",
        "most-number-one-songs-by-artist",
        "most-number-one-albums-by-artist",
        "most-entries-by-artist",
        "most-total-chart-weeks-by-artist",
        "most-simultaneous-entries",
      ]),
    })
    .nullable(),
  recordsCustom: z
    .object({
      entity: z.enum(["songs", "albums", "artists"]),
      chart: z.enum(["hot-100", "billboard-200"]),
      rankBy: z.enum([
        "weeks-at-number-one",
        "total-weeks",
        "weeks-at-position",
        "weeks-in-top-n",
        "most-entries",
        "number-one-entries",
      ]),
      rankByParam: z.number().int().positive(),
      sortDir: z.enum(["asc", "desc"]),
      peakMin: z.number().int().positive().nullable(),
      peakMax: z.number().int().positive().nullable(),
      weeksMin: z.number().int().positive().nullable(),
      debutPosMin: z.number().int().positive().nullable(),
      debutPosMax: z.number().int().positive().nullable(),
      artistNames: z.array(z.string()).nullable(),
    })
    .nullable(),
});
```

### Pattern 2: Intent First, Then Parameter Extraction
**What:** Decide whether the query is search, preset records, custom records, clarify, or unsupported before extracting numbers and names. [VERIFIED: `src/lib/search.ts`; `src/lib/records.ts`]
**When to use:** Always, because the same phrase can contain numbers that mean different things across search and records. [VERIFIED: `src/components/records/custom-query-builder.tsx`; `src/app/api/records/route.ts`]
**Example:** `"Taylor Swift"` should resolve to `search`, while `"Taylor Swift songs with most weeks at #1"` should resolve to `records_custom`. [ASSUMED]

### Pattern 3: Alias Catalog, Not Open Vocabulary
**What:** Maintain small allowlisted synonym maps for chart names, metric phrases, ordinals, and entity nouns. [VERIFIED: `src/lib/records.ts`; `src/components/records/custom-query-builder.tsx`]
**When to use:** For all Billboard-specific wording such as `Hot 100`, `B200`, `#1`, `number one`, `top 10`, `debut`, and `entries`. [VERIFIED: `src/lib/records.ts`; `src/components/records/custom-query-builder.tsx`]
**Example:**
```typescript
// Source: synthesized from src/lib/records.ts and custom-query-builder.tsx
export const chartAliases = {
  "hot 100": "hot-100",
  hot100: "hot-100",
  "billboard 200": "billboard-200",
  b200: "billboard-200",
} as const;

export const metricAliases = {
  "#1": { rankBy: "weeks-at-number-one" },
  "number one": { rankBy: "weeks-at-number-one" },
  "top 10": { rankBy: "weeks-in-top-n", rankByParam: 10 },
  debut: { filter: "debut_position" },
  peak: { filter: "peak_position" },
} as const;
```

### Anti-Patterns to Avoid

- **NL-to-SQL generation:** The current execution layer is enum- and range-based; freeform SQL generation would bypass the exact safety boundary Phase 8 is supposed to build. [VERIFIED: `.planning/ROADMAP.md`; `src/app/api/records/route.ts`; `src/lib/records.ts`]
- **Mixing interpretation into `src/lib/records.ts`:** That file already owns execution helpers; blending parsing logic into it will make future testing and Phase 8 separation harder. [VERIFIED: `src/lib/records.ts`; `.planning/ROADMAP.md`]
- **Treating unsupported questions as search anyway:** Questions about explanations, history summaries, or unsupported date ranges should return `unsupported` or `needs_clarification`, not a guessed query. [VERIFIED: user prompt; `src/lib/search.ts`; `src/lib/records.ts`]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Query execution from NL text | Freeform SQL templates | Existing `searchAll`, `getPresetRecords`, and `getCustomRecords` allowlists | Those helpers already encode valid modes, charts, dimensions, and limits. [VERIFIED: `src/lib/search.ts`; `src/lib/records.ts`; `src/app/api/records/route.ts`] |
| Schema validation | Manual nested `if` trees | Zod `.parse()` / `.safeParse()` | Zod returns typed validated data and can share the same schema across route and tests. [CITED: https://zod.dev/basics?curius=1296&id=handling-errors] |
| Chart synonym logic in UI only | Client-only phrase parsing | Shared server alias catalog in `src/lib/nlq/*` | Interpretation must be reusable by Phase 8 execution and Phase 9 UI. [VERIFIED: `.planning/ROADMAP.md`] |
| Entity lookup heuristics | Custom substring scanners against DB tables | Existing search API/lib for post-interpretation lookup | Search already uses trigram similarity and grouped 50-row results. [VERIFIED: `src/lib/search.ts`] |

**Key insight:** Phase 7 should hand-roll only the narrow domain grammar that maps English phrasing to the app’s already-allowlisted query vocabulary; it should not hand-roll a generic assistant or a new execution engine. [VERIFIED: `src/lib/search.ts`; `src/lib/records.ts`; `.planning/ROADMAP.md`; user prompt]

## Common Pitfalls

### Pitfall 1: Letting interpretation invent unsupported filters
**What goes wrong:** The parser accepts phrases like date ranges, “since 2010,” or “female artists only,” then produces fields the executor cannot honor. [VERIFIED: `src/lib/search.ts`; `src/lib/records.ts`; `src/components/records/custom-query-builder.tsx`]
**Why it happens:** The current search and records contracts do not expose date, genre, or demographic filters. [VERIFIED: `src/lib/search.ts`; `src/lib/records.ts`; `src/components/records/custom-query-builder.tsx`]
**How to avoid:** Restrict the IR to today’s supported enums and return `unsupported` with a clear explanation when the text asks for anything outside that shape. [VERIFIED: user prompt; `src/app/api/records/route.ts`]
**Warning signs:** The proposed interpretation object contains fields that do not exist in `SearchResultsPayload`, `CustomRecordsInput`, or preset record enums. [VERIFIED: `src/lib/search.ts`; `src/lib/records.ts`]

### Pitfall 2: Mishandling chart-specific ranges
**What goes wrong:** A query like “top 150 songs” is treated as valid for Hot 100 even though the route caps positions by chart type. [VERIFIED: `src/app/api/records/route.ts`]
**Why it happens:** The current route uses `100` for `hot-100` and `200` for `billboard-200`, and defaults `rankByParam` differently by metric. [VERIFIED: `src/app/api/records/route.ts`; `src/components/records/custom-query-builder.tsx`]
**How to avoid:** Clamp and validate chart-specific numeric bounds during interpretation, not only during execution. [VERIFIED: `src/app/api/records/route.ts`; `src/components/records/custom-query-builder.tsx`]
**Warning signs:** The explanation says one thing while the executor later rewrites the value to something else. [ASSUMED]

### Pitfall 3: Confusing search intent with records intent
**What goes wrong:** Short artist or title queries are forced into a leaderboard path, or metric-heavy questions are treated as plain search. [VERIFIED: `src/lib/search.ts`; `src/lib/records.ts`]
**Why it happens:** Billboard questions often contain artist names and ranking words in the same sentence. [ASSUMED]
**How to avoid:** Use intent cues such as metric phrases (`weeks`, `entries`, `peak`, `debut`, `top N`) before deciding whether the question is search or records. [VERIFIED: `src/lib/records.ts`; `src/components/records/custom-query-builder.tsx`]
**Warning signs:** Queries with no metric language still produce `records_custom`, or queries with explicit metric language produce `search`. [ASSUMED]

### Pitfall 4: Treating ambiguity as success
**What goes wrong:** “best Drake songs” or “number one albums by Taylor” are forced into a single reading even though multiple record presets or custom metrics could apply. [ASSUMED]
**Why it happens:** Natural language compresses several missing choices: chart, entity, metric, and sort intent. [ASSUMED]
**How to avoid:** Support a `needs_clarification` status with a bounded list of ambiguity reasons and suggested interpretations. [VERIFIED: user prompt; `.planning/ROADMAP.md`]
**Warning signs:** Low-confidence phrases map to a valid-looking object with empty filters and no warnings. [ASSUMED]

## Code Examples

Verified patterns from official sources and repo contracts:

### Route Handler Shell For Interpretation
```typescript
// Source: nextjs.org route handlers + current app/api/*/route.ts pattern
import type { NextRequest } from "next/server";
import { interpretedQuerySchema } from "@/lib/nlq/schema";
import { interpretQuestion } from "@/lib/nlq/interpret";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.json();
  const question = typeof body.question === "string" ? body.question : "";

  const result = interpretedQuerySchema.parse(interpretQuestion(question));
  return Response.json(result);
}
```

### Deterministic Guardrail Example
```typescript
// Source: synthesized from src/app/api/records/route.ts and src/lib/search.ts
function classifyQuestion(question: string) {
  const q = question.trim().toLowerCase();

  if (q.length < 2) {
    return { status: "unsupported", reason: "Query too short" } as const;
  }

  if (/\b(top|weeks|entries|peak|debut|#1|number one)\b/.test(q)) {
    return { status: "records" } as const;
  }

  return { status: "search" } as const;
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ask a model for generic JSON | Use strict Structured Outputs / schema-constrained object generation | OpenAI recommends Structured Outputs over JSON mode in its current docs. [CITED: https://developers.openai.com/api/docs/guides/structured-outputs] | If the project later adopts an LLM fallback, it should share the same strict schema instead of parsing ad hoc JSON. [CITED: https://developers.openai.com/api/docs/guides/structured-outputs] |
| Schema defined once for TS only | Use Zod 4 schema plus native JSON Schema conversion | Zod 4 docs describe native JSON Schema conversion. [CITED: https://zod.dev/json-schema?id=configuration] | One contract can serve route validation, tests, and optional future AI structured-output integrations. [CITED: https://zod.dev/json-schema?id=configuration] |

**Deprecated/outdated:**
- Older “JSON mode first” guidance is outdated for modern OpenAI schema-constrained extraction flows; current docs recommend Structured Outputs when supported. [CITED: https://developers.openai.com/api/docs/guides/structured-outputs]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A deterministic parser will cover the project’s v1 Billboard query set well enough without requiring an LLM in Phase 7. | Summary; Standard Stack | If false, the planner should reserve a fallback track for structured-output AI parsing and broader evaluation. |
| A2 | Examples like “Taylor Swift” versus “Taylor Swift songs with most weeks at #1” reflect the dominant user intent split the app should support. | Architecture Patterns | If false, the parser may need a richer clarification policy earlier than planned. |
| A3 | Billboard users will frequently ask ambiguous phrases such as “best Drake songs” that need clarification instead of forced execution. | Common Pitfalls | If false, clarification handling can be simpler; if true and omitted, trust in the assistant will degrade. |

## Open Questions

1. **What is the minimum accepted v1 phrase set?**
   - What we know: The executor vocabulary is already narrow and maps cleanly to search, preset records, and custom records. [VERIFIED: `src/lib/search.ts`; `src/lib/records.ts`]
   - What's unclear: Whether Phase 7 should cover only direct paraphrases of the current query builder or also looser natural phrasing like “songs that debuted highest but lasted 20 weeks.” [VERIFIED: `src/components/records/custom-query-builder.tsx`; user prompt]
   - Recommendation: Lock a golden-query fixture list before implementation so Phase 7 scope stays finite and Phase 8 inherits predictable inputs. [ASSUMED]

2. **Should Phase 7 expose a dedicated API route immediately?**
   - What we know: The repo already uses Route Handlers for search and records and Phase 9 will need a client-callable interpretation surface. [VERIFIED: `src/app/api/search/route.ts`; `src/app/api/records/route.ts`; `.planning/ROADMAP.md`]
   - What's unclear: Whether planning should treat the route as part of Phase 7 or leave it as an internal lib only until Phase 9. [VERIFIED: `.planning/ROADMAP.md`]
   - Recommendation: Plan for the route in Phase 7 but keep it execution-free so later phases can reuse it without rewiring. [ASSUMED]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Public read-only feature; no auth scope in roadmap. [VERIFIED: `.planning/REQUIREMENTS.md`; `.planning/ROADMAP.md`] |
| V3 Session Management | no | No session state is required for interpretation. [VERIFIED: `.planning/REQUIREMENTS.md`; `.planning/ROADMAP.md`] |
| V4 Access Control | yes | Keep interpretation and later execution on the server and restrict outputs to the current allowlisted contracts. [VERIFIED: `src/app/api/search/route.ts`; `src/app/api/records/route.ts`; `.planning/ROADMAP.md`] |
| V5 Input Validation | yes | Use Zod schema validation plus existing numeric and enum bounds. [VERIFIED: `src/app/api/records/route.ts`; CITED: https://zod.dev/basics?curius=1296&id=handling-errors] |
| V6 Cryptography | no | No cryptographic operation is required for the primary deterministic design. [VERIFIED: `package.json`; `.planning/ROADMAP.md`] |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt-like input trying to force unsupported execution | Tampering | Never execute from the NL string directly; emit only typed IR fields from allowlisted enums and bounded numbers. [VERIFIED: `src/app/api/records/route.ts`; user prompt] |
| Resource abuse via oversized or pathological text | Denial of Service | Add maximum input length and early short-query rejection before deep parsing. [VERIFIED: `src/app/api/search/route.ts`; ASSUMED] |
| Confused-deputy execution in Phase 8 | Elevation of Privilege | Make Phase 7 return `needs_clarification`/`unsupported` instead of fabricating a best guess. [VERIFIED: user prompt; `.planning/ROADMAP.md`] |
| Hidden parameter injection in numbers or ranges | Tampering | Reuse the same chart max and integer validation semantics already enforced in `/api/records`. [VERIFIED: `src/app/api/records/route.ts`; `src/components/records/custom-query-builder.tsx`] |

## Sources

### Primary (HIGH confidence)

- `src/lib/search.ts` - current grouped search payload, 2-char minimum handling, trigram-based result shape. [VERIFIED: codebase]
- `src/app/api/search/route.ts` - current search route validation and error behavior. [VERIFIED: codebase]
- `src/lib/records.ts` - preset enums, custom query vocabulary, unsupported-chart handling, and top-50 result contract. [VERIFIED: codebase]
- `src/app/api/records/route.ts` - execution allowlists, numeric bounds, chart-specific max positions, and mode contract. [VERIFIED: codebase]
- `src/components/records/custom-query-builder.tsx` - currently exposed metric/filter vocabulary and UI semantics the interpreter must match. [VERIFIED: codebase]
- `https://nextjs.org/docs/app/api-reference/file-conventions/route` - current Route Handler API for Next.js App Router. [CITED: https://nextjs.org/docs/app/api-reference/file-conventions/route]
- `https://zod.dev/basics?curius=1296&id=handling-errors` - current Zod parse behavior. [CITED: https://zod.dev/basics?curius=1296&id=handling-errors]
- `https://zod.dev/json-schema?id=configuration` - Zod 4 native JSON Schema conversion. [CITED: https://zod.dev/json-schema?id=configuration]
- `https://developers.openai.com/api/docs/guides/structured-outputs` - current Structured Outputs guidance for schema-constrained extraction. [CITED: https://developers.openai.com/api/docs/guides/structured-outputs]
- `https://vercel.com/docs/ai-sdk` - current AI SDK structured object generation overview. [CITED: https://vercel.com/docs/ai-sdk]
- npm registry lookups for `next`, `zod`, `openai`, `ai`, and `@ai-sdk/openai` on 2026-04-29. [VERIFIED: npm registry]

### Secondary (MEDIUM confidence)

- `.planning/phases/04-search-records/04-CONTEXT.md` - prior UX and behavior constraints for search and records. [VERIFIED: planning docs]
- `.planning/phases/04-search-records/04-RESEARCH.md` - earlier Phase 4 research framing. [VERIFIED: planning docs]

### Tertiary (LOW confidence)

- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Versions were checked against the npm registry and the route/validation choices match both official docs and current repo patterns. [VERIFIED: npm registry; `package.json`; `https://nextjs.org/docs/app/api-reference/file-conventions/route`; `https://zod.dev/basics?curius=1296&id=handling-errors`]
- Architecture: HIGH - The recommendation is directly constrained by the existing search/records contracts and roadmap split between interpretation, execution, and UI. [VERIFIED: `.planning/ROADMAP.md`; `src/lib/search.ts`; `src/lib/records.ts`; `src/app/api/records/route.ts`]
- Pitfalls: MEDIUM - Most are grounded in current contracts, but ambiguity frequency and deterministic-coverage sufficiency remain assumptions until a fixture set is defined. [VERIFIED: `src/lib/search.ts`; `src/lib/records.ts`; ASSUMED]

**Research date:** 2026-04-29
**Valid until:** 2026-05-29
