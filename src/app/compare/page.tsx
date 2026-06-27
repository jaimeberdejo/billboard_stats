import { Suspense } from "react";

import { ComparisonView } from "@/components/analytics/comparison-view";

export const metadata = {
  title: "Compare — Billboard Stats",
};

export default function ComparePage() {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6">
      <div className="border-b border-black/10 pb-3">
        <p className="text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          Compare
        </p>
        <h1 className="mt-1 text-[16px] font-[700] leading-[1.2] text-[#0A0A0A]">
          Entity Comparison
        </h1>
      </div>
      <Suspense fallback={null}>
        <ComparisonView />
      </Suspense>
    </div>
  );
}
