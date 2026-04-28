export const metadata = {
  title: "Data Status — Billboard Stats",
};

export default function StatusPage() {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6">
      <div className="border-b border-black/10 pb-3">
        <p className="text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
          Data Status
        </p>
        <h1 className="mt-1 text-[16px] font-[700] leading-[1.2] text-[#0A0A0A]">
          Data Status
        </h1>
      </div>

      {/* Stats bar skeleton — Plan 03 will replace with live counts */}
      <div className="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded border border-black/10 bg-black/10 sm:grid-cols-4">
        {["Hot 100 Weeks", "B200 Weeks", "Songs", "Artists"].map((label) => (
          <div key={label} className="bg-white px-3 py-3">
            <p className="text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
              {label}
            </p>
            <p className="mt-2 text-[15px] font-[700] leading-[1.1] text-[#0A0A0A]">
              —
            </p>
          </div>
        ))}
      </div>

      {/* Status table skeleton — Plan 03 will replace with live data */}
      <div className="mt-4 overflow-hidden rounded border border-black/10">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-black/10 bg-white">
              <th className="px-3 py-2 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
                Chart
              </th>
              <th className="px-3 py-2 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
                Latest Date
              </th>
              <th className="px-3 py-2 text-[10px] font-[600] uppercase tracking-[0.08em] text-[#888888]">
                Weeks Loaded
              </th>
            </tr>
          </thead>
          <tbody>
            {["Hot 100", "Billboard 200"].map((chart) => (
              <tr key={chart} className="border-b border-black/10 bg-white last:border-0">
                <td className="px-3 py-2 text-[12px] text-[#0A0A0A]">{chart}</td>
                <td className="px-3 py-2 text-[12px] text-[#888888]">—</td>
                <td className="px-3 py-2 text-[12px] text-[#888888]">—</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-[11px] text-[#AAAAAA]">
        Live data will be available after Plan 03 wires the database connection.
      </p>
    </div>
  );
}
