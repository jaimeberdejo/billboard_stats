"use client";

import { useMemo, useState } from "react";
import Link from "next/link";

interface ArtistCatalogTableRow {
  id: number;
  title: string;
  peak_position: number | null;
  total_weeks: number;
  weeks_at_peak: number;
  debut_date: string | null;
  last_date: string | null;
  href: string;
}

interface ArtistCatalogTableProps {
  title: string;
  rows: ArtistCatalogTableRow[];
}

type SortKey = "title" | "peak_position" | "total_weeks" | "weeks_at_peak" | "debut_date" | "last_date";
type SortDirection = "asc" | "desc";

function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function ArtistCatalogTable({ title, rows }: ArtistCatalogTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("debut_date");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const sortedRows = useMemo(() => {
    const direction = sortDirection === "asc" ? 1 : -1;
    return [...rows].sort((left, right) => {
      if (sortKey === "title") {
        return left.title.localeCompare(right.title) * direction;
      }

      if (sortKey === "debut_date" || sortKey === "last_date") {
        const leftValue = left[sortKey] ?? "";
        const rightValue = right[sortKey] ?? "";
        return leftValue.localeCompare(rightValue) * direction;
      }

      const leftValue = left[sortKey] ?? Number.POSITIVE_INFINITY;
      const rightValue = right[sortKey] ?? Number.POSITIVE_INFINITY;
      if (leftValue === rightValue) {
        return left.title.localeCompare(right.title);
      }
      return (leftValue - rightValue) * direction;
    });
  }, [rows, sortDirection, sortKey]);

  const columns: Array<{ key: SortKey; label: string }> = [
    { key: "title", label: "TITLE" },
    { key: "peak_position", label: "PK" },
    { key: "total_weeks", label: "WKS" },
    { key: "weeks_at_peak", label: "WKS@PK" },
    { key: "debut_date", label: "DEBUT" },
    { key: "last_date", label: "LAST" },
  ];

  const handleSort = (nextKey: SortKey) => {
    if (sortKey === nextKey) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }

    setSortKey(nextKey);
    setSortDirection(nextKey === "title" ? "asc" : "desc");
  };

  return (
    <section>
      <div className="mb-3 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
        {title}
      </div>
      <div className="overflow-hidden rounded border border-black/10 bg-white">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-black/10 bg-white">
                {columns.map((column) => (
                  <th
                    key={column.key}
                    className="px-3 py-2 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]"
                  >
                    <button
                      type="button"
                      onClick={() => handleSort(column.key)}
                      className="inline-flex items-center gap-1 transition-colors hover:text-[#0A0A0A]"
                    >
                      <span>{column.label}</span>
                      <span className="text-[9px] text-[#BBBBBB]">
                        {sortKey === column.key ? (sortDirection === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row) => (
                <tr
                  key={`${row.href}-${row.id}`}
                  className="border-b border-black/10 bg-white last:border-b-0 hover:bg-[#F5F5F5]"
                >
                  <td className="px-3 py-2">
                    <Link
                      href={row.href}
                      className="block text-[12px] font-[600] leading-[1.3] text-[#0A0A0A] transition-colors hover:text-[#C8102E]"
                    >
                      {row.title}
                    </Link>
                  </td>
                  <td
                    className={[
                      "px-3 py-2 text-[12px] text-[#0A0A0A]",
                      row.peak_position === 1 ? "font-[700] text-[#C8102E]" : "",
                    ].join(" ")}
                  >
                    {row.peak_position ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-[12px] text-[#0A0A0A]">{row.total_weeks}</td>
                  <td className="px-3 py-2 text-[12px] text-[#0A0A0A]">{row.weeks_at_peak}</td>
                  <td className="px-3 py-2 text-[12px] text-[#888888]">
                    {formatDate(row.debut_date)}
                  </td>
                  <td className="px-3 py-2 text-[12px] text-[#888888]">
                    {formatDate(row.last_date)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
