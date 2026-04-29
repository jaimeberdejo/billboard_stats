const CANONICAL_ARTIST_ALIASES = {
  "Janet Jackson": ["Janet"],
} as const;

const aliasToCanonicalName = new Map<string, string>();
const canonicalToGroupNames = new Map<string, string[]>();

for (const [canonicalName, aliases] of Object.entries(CANONICAL_ARTIST_ALIASES)) {
  const groupNames = [canonicalName, ...aliases];
  canonicalToGroupNames.set(canonicalName.toLowerCase(), groupNames);
  aliasToCanonicalName.set(canonicalName.toLowerCase(), canonicalName);

  for (const aliasName of aliases) {
    aliasToCanonicalName.set(aliasName.toLowerCase(), canonicalName);
  }
}

export function getCanonicalArtistName(name: string): string {
  return aliasToCanonicalName.get(name.trim().toLowerCase()) ?? name;
}

export function getArtistIdentityGroup(name: string): string[] {
  const canonicalName = getCanonicalArtistName(name);
  return canonicalToGroupNames.get(canonicalName.toLowerCase()) ?? [canonicalName];
}
