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
                {["TITLE", "PK", "WKS", "WKS@PK", "DEBUT", "LAST"].map((heading) => (
                  <th
                    key={heading}
                    className="px-3 py-2 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]"
                  >
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
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
