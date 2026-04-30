---
phase: 07-natural-language-query-interpretation
reviewed: 2026-04-29T17:19:25Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - src/lib/nlq/schema.ts
  - src/lib/nlq/catalog.ts
  - src/lib/nlq/normalize.ts
  - src/lib/nlq/interpret.ts
  - src/lib/nlq/explain.ts
  - src/lib/nlq/fixtures.ts
  - src/app/api/query/route.ts
  - scripts/verify-nlq-fixtures.ts
  - tsconfig.json
findings:
  critical: 0
  warning: 2
  info: 0
  total: 2
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-04-29T17:19:25Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Re-reviewed the Phase 07 NLQ interpreter source after the post-review fixes. The core schema, catalog, normalization, explanation, fixture verification script, and API route are in better shape, and the targeted checks passed:

- `./node_modules/.bin/tsc -p tsconfig.json --noEmit`
- `node --experimental-strip-types scripts/verify-nlq-fixtures.ts`

No critical issues remain, but two actionable correctness bugs are still present: one in POST input validation and one in numeric metric extraction for records queries.

## Warnings

### WR-01: POST route can throw on non-string `question` payloads

**File:** `src/app/api/query/route.ts:5-7,42-45`
**Issue:** `parseQuestion()` assumes the input has a `.trim()` method. In `POST`, the payload is only checked for object shape, then cast to `{ question?: string | null }`. A request such as `{ "question": 123 }` reaches `value?.trim()`, throws a `TypeError`, and bypasses the intended 400 response path.
**Fix:**
```ts
function parseQuestion(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}
```

### WR-02: Metric parsing uses the first number in the whole question, not the matched metric number

**File:** `src/lib/nlq/interpret.ts:128-146,478-486`
**Issue:** `inferMetric()` extracts `firstInteger` from the entire question and reuses it for `top N` and `position N` metrics. Queries with an unrelated earlier number are misread. Example: `songs from 1990 with most weeks in the top 10` is interpreted as `top 1990`, which then fails with `The Hot 100 does not support that position range.` instead of using `10` as the metric parameter.
**Fix:**
```ts
const topMatch = normalizedQuestion.match(/\btop\s+(\d+)\b/);
if (topMatch) {
  return {
    rankBy: "weeks-in-top-n",
    rankByParam: Number(topMatch[1]),
  };
}

const positionMatch = normalizedQuestion.match(/\bposition\s+#?(\d+)\b/);
if (positionMatch) {
  return {
    rankBy: "weeks-at-position",
    rankByParam: Number(positionMatch[1]),
  };
}
```

---

_Reviewed: 2026-04-29T17:19:25Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
