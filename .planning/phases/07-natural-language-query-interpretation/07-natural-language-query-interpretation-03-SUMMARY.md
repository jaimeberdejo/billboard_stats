# Plan 07-03 Summary

## Outcome

Locked the Phase 7 interpretation behavior with executable fixtures:

- Added `src/lib/nlq/fixtures.ts` with nine golden cases covering search, preset records, custom records, clarification, unsupported, and invalid contract combinations
- Added `scripts/verify-nlq-fixtures.ts` as a hermetic fixture verifier that runs the interpreter directly, checks branch fields, and detects explanation drift against `buildInterpretationExplanation()`
- Updated the NLQ module imports and TypeScript config so the fixture verifier can run under `node --experimental-strip-types` while the app still passes `next build`

## Verification

- `rg -n 'GOLDEN_QUERY_FIXTURES|needs_clarification|records_preset|records_custom|unsupported|expectedExplanationIncludes|entity/chart|preset/chart' src/lib/nlq/fixtures.ts` — PASS
- `rg -n 'interpretQuery|process.exitCode = 1|GOLDEN_QUERY_FIXTURES' scripts/verify-nlq-fixtures.ts` — PASS
- `! rg -n 'getSql|fetch\\(' scripts/verify-nlq-fixtures.ts` — PASS
- `npm run lint -- src/lib/nlq/fixtures.ts scripts/verify-nlq-fixtures.ts src/lib/nlq/catalog.ts src/lib/nlq/interpret.ts src/lib/nlq/explain.ts` — PASS
- `node --experimental-strip-types scripts/verify-nlq-fixtures.ts` — PASS (`Verified 9 NLQ fixtures.`)
- `npm run build` — PASS

## Commits

| Commit | Description |
|--------|-------------|
| `60956a44` | `test(07-03): add nlq golden fixtures` |
| `733229c0` | `test(07-03): add nlq fixture verifier` |

## Deviations from Plan

**[Rule 1 - Behavior Bug] Preset detection was too broad** — Found during: Task 2 | Issue: the first fixture run treated `billboard 200 songs with most weeks at #1` as a preset leaderboard instead of a constrained custom query that should fail semantic validation | Fix: tightened preset detection so presets only trigger for standalone leaderboard asks, not any query containing a metric substring | Files modified: `src/lib/nlq/interpret.ts` | Verification: `node --experimental-strip-types scripts/verify-nlq-fixtures.ts`, `npm run build` | Commit hash: `733229c0`

**[Rule 1 - Tooling Compatibility] Fixture runner needed TS extension import support** — Found during: Task 2 | Issue: the standalone Node verifier required explicit `.ts` specifiers, but the repo typecheck initially rejected them | Fix: switched NLQ internal runtime imports to explicit `.ts` specifiers where needed for the verifier and enabled `allowImportingTsExtensions` in `tsconfig.json` so the build and script could use the same module graph | Files modified: `scripts/verify-nlq-fixtures.ts`, `src/lib/nlq/catalog.ts`, `src/lib/nlq/explain.ts`, `src/lib/nlq/interpret.ts`, `tsconfig.json` | Verification: `npm run lint -- src/lib/nlq/fixtures.ts scripts/verify-nlq-fixtures.ts src/lib/nlq/catalog.ts src/lib/nlq/interpret.ts src/lib/nlq/explain.ts`, `node --experimental-strip-types scripts/verify-nlq-fixtures.ts`, `npm run build` | Commit hash: `733229c0`

**Total deviations:** 2 auto-fixed. **Impact:** positive; the verifier is now executable in the exact planned mode and catches semantic interpretation regressions.

## Self-Check: PASSED
