export default function Home() {
  const featuredCharts = [
    {
      label: "Hot 100",
      focus: "Track weekly song peaks, total chart runs, and rebound climbs.",
      stat: "66 years",
    },
    {
      label: "Billboard 200",
      focus: "Compare album longevity, debuts, and catalog returns at a glance.",
      stat: "10,000+ weeks",
    },
    {
      label: "Search Ready",
      focus: "Surface songs, albums, and artists through one compact interface.",
      stat: "1 endpoint live",
    },
  ];

  const checkpoints = [
    "Next.js App Router with TypeScript and Tailwind is wired up.",
    "Space Grotesk is bundled locally, so builds do not rely on Google Fonts access.",
    "The Neon health route is available at /api/health and reports missing config clearly.",
  ];

  return (
    <main className="flex flex-1 bg-[linear-gradient(180deg,#f5f0e8_0%,#ffffff_38%,#f7f7f5_100%)] text-slate-950">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-10 px-5 py-6 sm:px-8 lg:px-10">
        <header className="flex flex-col gap-6 border-b border-black/10 pb-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl space-y-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-billboard">
              Phase 1 Infrastructure
            </p>
            <div className="space-y-3">
              <h1 className="max-w-4xl text-4xl font-semibold tracking-[-0.04em] sm:text-5xl">
                Billboard chart history with a frontend shell that is ready for live data.
              </h1>
              <p className="max-w-2xl text-sm leading-6 text-slate-700 sm:text-base">
                This project now boots on Next.js, uses a bundled Space Grotesk
                variable font, and exposes a health endpoint for the Neon
                connection that the later chart views will depend on.
              </p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-black/10 bg-black/10 text-[11px] uppercase tracking-[0.18em] sm:grid-cols-4">
            <div className="bg-white px-4 py-3">
              <div className="text-slate-500">Framework</div>
              <div className="mt-2 text-base tracking-normal text-slate-950">
                Next 16
              </div>
            </div>
            <div className="bg-white px-4 py-3">
              <div className="text-slate-500">Type</div>
              <div className="mt-2 text-base tracking-normal text-slate-950">
                App Router
              </div>
            </div>
            <div className="bg-white px-4 py-3">
              <div className="text-slate-500">Database</div>
              <div className="mt-2 text-base tracking-normal text-slate-950">
                Neon
              </div>
            </div>
            <div className="bg-white px-4 py-3">
              <div className="text-slate-500">Font</div>
              <div className="mt-2 text-base tracking-normal text-slate-950">
                Space Grotesk
              </div>
            </div>
          </div>
        </header>

        <section className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.7fr)]">
          <div className="rounded-[28px] bg-slate-950 p-6 text-stone-50 shadow-[0_24px_80px_rgba(15,23,42,0.18)] sm:p-8">
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <div>
                <p className="text-[11px] uppercase tracking-[0.3em] text-white/55">
                  Live Readiness
                </p>
                <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">
                  Initial shell in place
                </h2>
              </div>
              <div className="rounded-full border border-white/15 px-3 py-1 text-[11px] uppercase tracking-[0.22em] text-white/70">
                Core-01 to Core-05
              </div>
            </div>
            <div className="mt-6 grid gap-px overflow-hidden rounded-2xl bg-white/10 sm:grid-cols-3">
              {featuredCharts.map((item) => (
                <article key={item.label} className="bg-white/[0.04] p-4">
                  <p className="text-[11px] uppercase tracking-[0.24em] text-white/55">
                    {item.label}
                  </p>
                  <p className="mt-6 text-3xl font-semibold tracking-[-0.04em]">
                    {item.stat}
                  </p>
                  <p className="mt-3 text-sm leading-6 text-white/72">
                    {item.focus}
                  </p>
                </article>
              ))}
            </div>
          </div>

          <aside className="rounded-[28px] border border-black/10 bg-white p-6 shadow-[0_20px_60px_rgba(15,23,42,0.08)] sm:p-8">
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-billboard">
              Verification
            </p>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.03em]">
              What is ready now
            </h2>
            <ul className="mt-6 space-y-4 text-sm leading-6 text-slate-700">
              {checkpoints.map((checkpoint) => (
                <li
                  key={checkpoint}
                  className="rounded-2xl border border-black/8 bg-stone-50 px-4 py-3"
                >
                  {checkpoint}
                </li>
              ))}
            </ul>
            <div className="mt-6 rounded-2xl bg-billboard px-4 py-4 text-white">
              <p className="text-[11px] uppercase tracking-[0.24em] text-white/75">
                Health Check
              </p>
              <p className="mt-2 text-sm leading-6">
                Configure <code className="font-semibold">DATABASE_URL</code> in{" "}
                <code className="font-semibold">.env.local</code>, then request{" "}
                <code className="font-semibold">/api/health</code>.
              </p>
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}
