"use client";

import { useDeferredValue, useEffect, useState, useTransition } from "react";

import { SearchResultsTable } from "@/components/search/search-results-table";
import type { SearchResultsPayload } from "@/lib/search";

type SearchTab = "Songs" | "Albums" | "Artists";

const EMPTY_RESULTS: SearchResultsPayload = {
  query: "",
  songs: [],
  albums: [],
  artists: [],
};

async function fetchSearchResults(query: string): Promise<SearchResultsPayload> {
  const params = new URLSearchParams({ q: query });
  const response = await fetch(`/api/search?${params.toString()}`, {
    method: "GET",
    cache: "no-store",
  });

  const payload = (await response.json()) as SearchResultsPayload | { error?: string };
  if (!response.ok || !("songs" in payload)) {
    throw new Error(
      "error" in payload && payload.error
        ? payload.error
        : "Could not load search results. Please try again later.",
    );
  }

  return payload;
}

export function SearchView() {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query.trim());
  const [activeTab, setActiveTab] = useState<SearchTab>("Songs");
  const [results, setResults] = useState<SearchResultsPayload>(EMPTY_RESULTS);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    if (deferredQuery.length < 2) {
      return;
    }

    let cancelled = false;

    startTransition(async () => {
      try {
        const payload = await fetchSearchResults(deferredQuery);
        if (!cancelled) {
          setResults(payload);
          setError(null);
        }
      } catch (fetchError) {
        if (!cancelled) {
          setResults(EMPTY_RESULTS);
          setError(
            fetchError instanceof Error
              ? fetchError.message
              : "Could not load search results. Please try again later.",
          );
        }
      }
    });

    return () => {
      cancelled = true;
    };
  }, [deferredQuery]);

  const counts = {
    Songs: results.songs.length,
    Albums: results.albums.length,
    Artists: results.artists.length,
  };

  const currentRows =
    activeTab === "Songs"
      ? results.songs
      : activeTab === "Albums"
        ? results.albums
        : results.artists;

  const emptyLabel =
    activeTab === "Songs"
      ? "No songs found"
      : activeTab === "Albums"
        ? "No albums found"
        : "No artists found";

  return (
    <section className="mt-6 flex flex-col gap-4">
      <input
        value={query}
        onChange={(event) => {
          const nextQuery = event.target.value;
          setQuery(nextQuery);
          if (nextQuery.trim().length < 2) {
            setError(null);
          }
        }}
        placeholder="Search artists, songs, albums…"
        className="w-full rounded border border-black/10 bg-white px-3 py-3 text-[12px] leading-[1.45] text-[#0A0A0A] outline-none transition focus:border-[#C8102E]"
        autoFocus
      />

      <div className="flex flex-wrap gap-2 border-b border-black/10 pb-3">
        {(["Songs", "Albums", "Artists"] as const).map((tab) => {
          const active = tab === activeTab;
          const showCount = deferredQuery.length >= 2;

          return (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={[
                "rounded border px-3 py-1.5 text-[11px] font-[600] tracking-[0.08em] transition-colors",
                active
                  ? "border-[#C8102E] bg-[#C8102E] text-white"
                  : "border-black/10 bg-[#F5F5F5] text-[#0A0A0A] hover:bg-white",
              ].join(" ")}
            >
              {tab}
              {showCount ? (
                <span className={active ? "text-white/80" : "text-[#888888]"}>
                  {" "}
                  ({counts[tab]})
                </span>
              ) : null}
            </button>
          );
        })}

        <span className="ml-auto self-center text-[11px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          {isPending ? "Loading..." : deferredQuery.length >= 2 ? `${currentRows.length} results` : ""}
        </span>
      </div>

      {deferredQuery.length < 2 ? (
        <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
          Type at least 2 characters to search.
        </div>
      ) : null}

      {error ? (
        <div className="rounded border border-[#C8102E]/15 bg-[#FCEDEE] px-4 py-4 text-[12px] leading-[1.45] text-[#C8102E]">
          {error}
        </div>
      ) : null}

      {deferredQuery.length >= 2 && !error ? (
        currentRows.length > 0 ? (
          <SearchResultsTable tab={activeTab} rows={currentRows} />
        ) : (
          <div className="rounded border border-dashed border-black/10 bg-[#F5F5F5] px-4 py-6 text-[12px] leading-[1.45] text-[#888888]">
            {emptyLabel}
          </div>
        )
      ) : null}
    </section>
  );
}
