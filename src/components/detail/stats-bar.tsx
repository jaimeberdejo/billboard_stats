interface StatsBarItem {
  label: string;
  value: string;
  accent?: boolean;
}

interface StatsBarProps {
  items: StatsBarItem[];
}

export function StatsBar({ items }: StatsBarProps) {
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded border border-black/10 bg-black/10 sm:grid-cols-3 lg:grid-cols-6">
      {items.map((item) => (
        <div key={item.label} className="bg-white px-3 py-3">
          <p className="text-[10px] font-[600] uppercase tracking-[0.07em] text-[#888888]">
            {item.label}
          </p>
          <p
            className={[
              "mt-2 text-[16px] font-[600] leading-[1.1] text-[#0A0A0A]",
              item.value.length > 12 ? "text-[12px] font-[400] leading-[1.45]" : "",
              item.accent ? "text-[#C8102E]" : "",
            ].join(" ")}
          >
            {item.value}
          </p>
        </div>
      ))}
    </div>
  );
}
