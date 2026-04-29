import {
  GOLDEN_QUERY_FIXTURES,
  type GoldenQueryFixture,
} from "../src/lib/nlq/fixtures.ts";
import { buildInterpretationExplanation } from "../src/lib/nlq/explain.ts";
import { interpretQuery } from "../src/lib/nlq/interpret.ts";

function assertPartialMatch(
  fixtureName: string,
  branchName: string,
  actual: Record<string, unknown> | null,
  expected: Record<string, unknown> | null | undefined,
): string[] {
  if (expected === undefined) {
    return [];
  }

  if (expected === null) {
    return actual === null
      ? []
      : [`${fixtureName}: expected ${branchName} to be null`];
  }

  if (actual === null) {
    return [`${fixtureName}: expected ${branchName} to be populated`];
  }

  const failures: string[] = [];

  for (const [key, value] of Object.entries(expected)) {
    const actualValue = actual[key];
    if (Array.isArray(value)) {
      if (JSON.stringify(actualValue) !== JSON.stringify(value)) {
        failures.push(
          `${fixtureName}: ${branchName}.${key} mismatch (expected ${JSON.stringify(value)}, got ${JSON.stringify(actualValue)})`,
        );
      }
      continue;
    }

    if (actualValue !== value) {
      failures.push(
        `${fixtureName}: ${branchName}.${key} mismatch (expected ${JSON.stringify(value)}, got ${JSON.stringify(actualValue)})`,
      );
    }
  }

  return failures;
}

function assertIncludes(
  fixtureName: string,
  fieldName: string,
  haystack: string | string[],
  snippets: string[] | undefined,
): string[] {
  if (!snippets || snippets.length === 0) {
    return [];
  }

  const text = Array.isArray(haystack) ? haystack.join(" | ") : haystack;
  return snippets
    .filter((snippet) => !text.includes(snippet))
    .map(
      (snippet) =>
        `${fixtureName}: expected ${fieldName} to include ${JSON.stringify(snippet)} (got ${JSON.stringify(text)})`,
    );
}

function verifyFixture(fixture: GoldenQueryFixture): string[] {
  const result = interpretQuery(fixture.question);
  const failures: string[] = [];

  if (result.status !== fixture.expectedStatus) {
    failures.push(
      `${fixture.name}: status mismatch (expected ${fixture.expectedStatus}, got ${result.status})`,
    );
  }

  if (result.intent !== fixture.expectedIntent) {
    failures.push(
      `${fixture.name}: intent mismatch (expected ${fixture.expectedIntent}, got ${result.intent})`,
    );
  }

  failures.push(
    ...assertPartialMatch(
      fixture.name,
      "search",
      result.search as Record<string, unknown> | null,
      fixture.expectedSearch as Record<string, unknown> | null | undefined,
    ),
  );
  failures.push(
    ...assertPartialMatch(
      fixture.name,
      "recordsPreset",
      result.recordsPreset as Record<string, unknown> | null,
      fixture.expectedRecordsPreset as Record<string, unknown> | null | undefined,
    ),
  );
  failures.push(
    ...assertPartialMatch(
      fixture.name,
      "recordsCustom",
      result.recordsCustom as Record<string, unknown> | null,
      fixture.expectedRecordsCustom as Record<string, unknown> | null | undefined,
    ),
  );

  const regeneratedExplanation = buildInterpretationExplanation(result, result.ambiguityReasons);
  if (regeneratedExplanation !== result.explanation) {
    failures.push(
      `${fixture.name}: explanation drift detected (expected route output to match explain.ts helper)`,
    );
  }

  failures.push(
    ...assertIncludes(
      fixture.name,
      "explanation",
      result.explanation,
      fixture.expectedExplanationIncludes,
    ),
  );
  failures.push(
    ...assertIncludes(
      fixture.name,
      "warnings",
      result.warnings,
      fixture.expectedWarningsIncludes,
    ),
  );
  failures.push(
    ...assertIncludes(
      fixture.name,
      "ambiguityReasons",
      result.ambiguityReasons,
      fixture.expectedAmbiguityIncludes,
    ),
  );

  return failures;
}

const failures = GOLDEN_QUERY_FIXTURES.flatMap(verifyFixture);

if (failures.length > 0) {
  process.exitCode = 1;
  for (const failure of failures) {
    console.error(failure);
  }
} else {
  console.log(`Verified ${GOLDEN_QUERY_FIXTURES.length} NLQ fixtures.`);
}
