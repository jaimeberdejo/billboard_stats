import Link from "next/link";

export const metadata = {
  title: "Search — Billboard Stats",
};

export default function SearchPage() {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6">
      <div className="border-b border-black/10 pb-3">
        <p className="text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          Search
        </p>
        <h1 className="mt-1 text-[16px] font-[700] leading-[1.2] text-[#0A0A0A]">
          Artist, Song &amp; Album Search
        </h1>
      </div>

      <div className="mt-6 rounded border border-black/10 bg-[#F5F5F5] px-4 py-5">
        <p className="text-[12px] font-[600] text-[#0A0A0A]">
          Available in Phase 4
        </p>
        <p className="mt-2 text-[12px] text-[#888888]">
          Fuzzy search across songs, albums, and artists is planned for Phase 4.
          In the meantime, browse current chart rankings on{" "}
          <Link href="/" className="text-[#C8102E] hover:underline">
            Latest Charts
          </Link>
          .
        </p>
      </div>
    </div>
  );
}
