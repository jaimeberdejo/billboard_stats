import Link from "next/link";

import { getCanonicalArtistName } from "@/lib/artist-identity";

interface ArtistPillLink {
  id: number;
  name: string;
}

interface ArtistPillsProps {
  artists: ArtistPillLink[];
}

export function ArtistPills({ artists }: ArtistPillsProps) {
  const canonicalArtists = new Map<string, ArtistPillLink>();

  for (const artist of artists) {
    const canonicalName = getCanonicalArtistName(artist.name);
    if (!canonicalArtists.has(canonicalName) || artist.name === canonicalName) {
      canonicalArtists.set(canonicalName, { id: artist.id, name: canonicalName });
    }
  }

  return (
    <div className="flex flex-wrap gap-2">
      {[...canonicalArtists.values()].map((artist) => (
        <Link
          key={artist.id}
          href={`/artist/${artist.id}`}
          className="rounded-full border border-black/10 px-3 py-1.5 text-[12px] font-[600] leading-[1.45] text-[#0A0A0A] transition-colors hover:border-[#C8102E] hover:text-[#C8102E]"
        >
          {artist.name}
        </Link>
      ))}
    </div>
  );
}
