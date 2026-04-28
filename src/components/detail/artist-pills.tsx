import Link from "next/link";

interface ArtistPillLink {
  id: number;
  name: string;
}

interface ArtistPillsProps {
  artists: ArtistPillLink[];
}

export function ArtistPills({ artists }: ArtistPillsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {artists.map((artist) => (
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
