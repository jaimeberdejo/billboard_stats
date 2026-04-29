---
status: diagnosed
phase: 07-natural-language-query-interpretation
source: 07-natural-language-query-interpretation-01-SUMMARY.md, 07-natural-language-query-interpretation-02-SUMMARY.md, 07-natural-language-query-interpretation-03-SUMMARY.md
started: 2026-04-29T00:00:00.000Z
updated: 2026-04-29T19:45:00.000Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running dev server. Start the app fresh with `npm run dev`. The server boots without errors and `GET /api/query?q=test` returns a JSON response (any valid JSON body — not a 404 or 500).
result: pass

### 2. Golden Fixture Verifier
expected: Running `node --experimental-strip-types scripts/verify-nlq-fixtures.ts` in the terminal prints exactly `Verified 9 NLQ fixtures.` with exit code 0 and no errors.
result: issue
reported: "Verified 10 NLQ fixtures (not 9 as documented). Node.js [MODULE_TYPELESS_PACKAGE_JSON] warning: module type not specified in package.json, reparsing as ES module incurs performance overhead."
severity: minor

### 3. Search Interpretation
expected: `GET /api/query?q=songs+by+taylor+swift` returns JSON with `"status": "search"` (or `"search_entity"`) and an explanation string describing the search intent.
result: issue
reported: "Returns status: needs_clarification, intent: clarify. Explanation: 'This records-style question needs a supported ranking metric before it can be interpreted.' search is null."
severity: major

### 4. Preset Records Interpretation
expected: `GET /api/query?q=most+weeks+at+%231+on+hot+100` returns JSON with `"status": "records_preset"` indicating a leaderboard preset was matched.
result: pass

### 5. Needs Clarification Response
expected: Sending a bare or ambiguous query — e.g. `GET /api/query?q=billboard` — returns JSON with `"status": "needs_clarification"` and a clarification message explaining what information is missing.
result: issue
reported: "Returns status: ok, intent: search. Treats 'billboard' as a mixed grouped search rather than triggering clarification. No clarification message returned."
severity: minor

### 6. Unsupported Query Rejection
expected: Sending a date-filter query like `GET /api/query?q=songs+from+last+week` (or similar unsupported intent) returns JSON with `"status": "unsupported"` and an explanation of why it isn't supported.
result: issue
reported: "Returns status: needs_clarification, intent: clarify. Same explanation as test 3: 'This records-style question needs a supported ranking metric before it can be interpreted.' Does not return unsupported."
severity: major

### 7. App Build Passes
expected: `npm run build` completes without TypeScript errors, lint errors, or build failures. The output ends with a successful build summary.
result: pass

## Summary

total: 7
passed: 3
issues: 4
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "Fixture verifier prints 'Verified 9 NLQ fixtures.' with no warnings"
  status: failed
  reason: "User reported: Verified 10 NLQ fixtures (not 9 as documented). Node.js [MODULE_TYPELESS_PACKAGE_JSON] warning: module type not specified in package.json, reparsing as ES module incurs performance overhead."
  severity: minor
  test: 2
  root_cause: "A 10th fixture was added in post-summary fix commits (ec439c9b, 09ebaa4d); the SUMMARY.md count of 9 is stale. Missing 'type': 'module' in package.json causes Node.js to reparse the ES module script on every run."
  artifacts:
    - path: "package.json"
      issue: "Missing \"type\": \"module\" field"
    - path: "src/lib/nlq/fixtures.ts"
      issue: "Contains 10 fixtures; SUMMARY.md documents 9"
  missing:
    - "Add \"type\": \"module\" to package.json to suppress the Node.js module-type warning"
  debug_session: ""

- truth: "Query 'songs by taylor swift' is interpreted as a search with status: search"
  status: failed
  reason: "User reported: Returns status: needs_clarification, intent: clarify. Explanation: 'This records-style question needs a supported ranking metric before it can be interpreted.' search is null."
  severity: major
  test: 3
  root_cause: "In buildCustomInterpretation (interpret.ts:340-347), ARTIST_FILTER_RE (/\\bby\\s+.../i) matches 'by taylor swift', making artistNames non-null and setting recordsCuePresent=true. With no metric present, the function returns needs_clarification. The 'by [artist]' pattern is too broad — it captures plain search queries like 'songs by [artist]' that have no records intent."
  artifacts:
    - path: "src/lib/nlq/interpret.ts"
      issue: "ARTIST_FILTER_RE at line 48 pulls 'by [artist]' into records path even when no chart/metric cues are present"
    - path: "src/lib/nlq/interpret.ts"
      issue: "buildCustomInterpretation recordsCuePresent check (line 340) triggers on artistNames alone"
  missing:
    - "Guard ARTIST_FILTER_RE so artist-name detection only contributes to recordsCuePresent when at least one other records cue (chart, metric, weeksMin, peakRange, debutRange, or records keyword) is also present"
  debug_session: ""

- truth: "Bare ambiguous query 'billboard' triggers needs_clarification with explanation"
  status: failed
  reason: "User reported: Returns status: ok, intent: search. Treats 'billboard' as a mixed grouped search rather than triggering clarification. No clarification message returned."
  severity: minor
  test: 5
  root_cause: "'billboard' is not in CHART_ALIASES (only 'hot 100', 'hot100', 'billboard 200', 'b200', 'billboard200' are defined). No records cues are detected, so it falls through to buildSearchInterpretation as a generic mixed search. This is arguably acceptable behaviour — treating 'billboard' as a search term is reasonable. The test expectation of needs_clarification was too strict."
  artifacts:
    - path: "src/lib/nlq/catalog.ts"
      issue: "CHART_ALIASES does not include bare 'billboard' as a chart cue"
  missing:
    - "Optionally: add 'billboard' to CHART_ALIASES mapped to a clarification path, or accept current search fallback as intended behaviour"
  debug_session: ""

- truth: "Date-filter query 'songs from last week' returns status: unsupported"
  status: failed
  reason: "User reported: Returns status: needs_clarification, intent: clarify. Same explanation as test 3: 'This records-style question needs a supported ranking metric before it can be interpreted.' Does not return unsupported."
  severity: major
  test: 6
  root_cause: "detectUnsupportedCue (interpret.ts:64-73) only matches 4-digit years via YEAR_FILTER_RE (/\\b(from|in)\\s+(\\d{4})\\b/i) and a narrow UNSUPPORTED_CUE_WORDS list that does not include relative date terms ('last', 'week', 'month', 'recent', 'today', 'yesterday'). 'songs from last week' passes the unsupported check, then 'songs' is detected as an entity making recordsCuePresent=true with no metric, falling into needs_clarification. The fix(07-03) commit only covered year-based date filters."
  artifacts:
    - path: "src/lib/nlq/interpret.ts"
      issue: "YEAR_FILTER_RE (line 52) only matches 4-digit years; relative date phrases like 'last week' are not caught"
    - path: "src/lib/nlq/catalog.ts"
      issue: "UNSUPPORTED_CUE_WORDS missing relative date terms: 'last week', 'this week', 'last month', 'recent', 'today', 'yesterday'"
  missing:
    - "Add a RELATIVE_DATE_RE pattern to detectUnsupportedCue covering 'last week', 'this week', 'last month', 'this year', 'today', 'yesterday', 'recent'"
    - "Or extend UNSUPPORTED_CUE_WORDS with 'last week', 'this week', 'last month', 'recent', 'today', 'yesterday'"
  debug_session: ""
