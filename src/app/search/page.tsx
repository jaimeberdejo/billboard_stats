import { SearchView } from "@/components/search/search-view";

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
      <SearchView />
    </div>
  );
}
