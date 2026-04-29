const HASH_AND_WORD_REPLACEMENTS: Array<[RegExp, string]> = [
  [/#1/g, " number one "],
  [/no\.?\s*1/g, " number one "],
];

export function normalizeQuestion(question: string): string {
  let normalized = question.trim().toLowerCase();

  for (const [pattern, replacement] of HASH_AND_WORD_REPLACEMENTS) {
    normalized = normalized.replace(pattern, replacement);
  }

  return normalized.replace(/\s+/g, " ").trim();
}

export function tokenizeQuestion(question: string): string[] {
  return normalizeQuestion(question)
    .replace(/[^a-z0-9#\s-]+/g, " ")
    .split(/\s+/)
    .filter(Boolean);
}

export function extractPositiveIntegers(question: string): number[] {
  return Array.from(normalizeQuestion(question).matchAll(/\b([1-9]\d*)\b/g), (match) =>
    Number(match[1]),
  );
}

export function splitArtistNames(value: string): string[] {
  return value
    .split(/,| and /)
    .map((part) => part.trim())
    .filter(Boolean);
}
