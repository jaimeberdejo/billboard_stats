import { PrimaryNav } from "@/components/shell/primary-nav";
import { MobileBottomNav } from "@/components/shell/mobile-bottom-nav";

export function SiteShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-full flex-col">
      {/* Desktop sticky top nav — hidden below sm breakpoint */}
      <header className="sticky top-0 z-40 hidden h-11 items-center border-b border-black/10 bg-white px-4 sm:flex sm:px-6">
        <div className="flex w-full max-w-7xl items-center justify-between mx-auto">
          <span className="text-[13px] font-[700] tracking-[-0.02em] text-[#0A0A0A]">
            Chart Stats
          </span>
          <PrimaryNav />
        </div>
      </header>

      {/* Page content — bottom padding accommodates mobile nav on small screens */}
      <main className="flex flex-1 flex-col pb-14 sm:pb-0">{children}</main>

      {/* Mobile bottom nav — visible only below sm breakpoint */}
      <MobileBottomNav />
    </div>
  );
}
