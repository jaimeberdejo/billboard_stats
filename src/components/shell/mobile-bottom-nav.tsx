"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { label: "Charts", href: "/" },
  { label: "Search", href: "/search" },
  { label: "Records", href: "/records" },
  { label: "Status", href: "/status" },
] as const;

export function MobileBottomNav() {
  const pathname = usePathname();

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 flex h-14 items-stretch border-t border-black/10 bg-white sm:hidden"
      aria-label="Mobile navigation"
    >
      {NAV_ITEMS.map(({ label, href }) => {
        const isActive =
          href === "/"
            ? pathname === "/"
            : pathname === href || pathname.startsWith(href + "/");
        return (
          <Link
            key={href}
            href={href}
            className={[
              "flex flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-[600] tracking-tight transition-colors",
              isActive
                ? "bg-[#0A0A0A] text-white"
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
