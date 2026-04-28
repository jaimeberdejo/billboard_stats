import Link from "next/link";

interface DetailHeaderProps {
  backHref: string;
  title: string;
  subtitle: string;
  quoteTitle?: boolean;
}

export function DetailHeader({
  backHref,
  title,
  subtitle,
  quoteTitle = false,
}: DetailHeaderProps) {
  return (
    <header className="border-b border-black/10 pb-4">
      <Link
        href={backHref}
        className="inline-flex text-[12px] font-[600] leading-[1.45] text-[#888888] transition-colors hover:text-[#C8102E]"
      >
        ← Back
      </Link>
      <div className="mt-3">
        <h1 className="text-[16px] font-[600] leading-[1.2] text-[#0A0A0A] sm:text-[22px]">
          {quoteTitle ? `"${title}"` : title}
        </h1>
        <p className="mt-1 text-[12px] leading-[1.45] text-[#888888]">{subtitle}</p>
      </div>
    </header>
  );
}
