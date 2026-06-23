// This map holds GENUINE artist aliases only — real alternate names the database
// does not collapse on its own (e.g. a stage-name variant for the same act).
// Split-fragment identity (an act mistakenly broken into separate pieces) is now
// fixed at the source in the ETL (artist_aliases.py / reconcile_artists.py), so it
// is no longer merged here at read time.
const CANONICAL_ARTIST_ALIASES = {
  "Janet Jackson": ["Janet"],
  Kesha: ["Ke$ha"],
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
