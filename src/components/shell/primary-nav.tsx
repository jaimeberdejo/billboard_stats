"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { label: "Latest Charts", href: "/" },
  { label: "Search", href: "/search" },
  { label: "Records", href: "/records" },
  { label: "Data Status", href: "/status" },
] as const;

export function PrimaryNav() {
  const pathname = usePathname();

  return (
    <nav className="flex items-center gap-1">
      {NAV_ITEMS.map(({ label, href }) => {
        const isActive =
          href === "/"
            ? pathname === "/"
            : pathname === href || pathname.startsWith(href + "/");
        return (
          <Link
            key={href}
            href={href}
            style={
              isActive
                ? {
                    backgroundColor: "#0A0A0A",
                    color: "#FFFFFF",
                  }
                : undefined
            }
            className={[
              "rounded px-3 py-1.5 text-[12px] font-[500] tracking-tight transition-colors",
              isActive
                ? ""
                : "text-[#888888] hover:bg-[#F5F5F5] hover:text-[#0A0A0A]",
            ].join(" ")}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
