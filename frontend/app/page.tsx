import Link from "next/link";

const features = [
  {
    title: "FSM Strategy Engine",
    desc: "ICC methodology — Indication, Correction, Continuation — driven by a deterministic finite state machine with 11 states.",
  },
  {
    title: "Risk Controls",
    desc: "20% daily kill switch, max 2 trades/session, cooldown timers, and position-level stop/target enforcement.",
  },
  {
    title: "Real-Time Dashboard",
    desc: "Live candlestick charts, FSM state visualization, P&L tracking, and event log via WebSocket.",
  },
  {
    title: "Paper & Cash Trading",
    desc: "Seamless switching between simulated backtests, paper trading, and live execution via Interactive Brokers.",
  },
];

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6 py-20">
      <div className="mx-auto max-w-3xl text-center">
        <h1 className="mb-3 text-3xl font-bold tracking-tight text-white sm:text-4xl">
          ICC MES AutoTrader
        </h1>
        <p className="mb-10 text-lg text-zinc-400">
          Automated MES futures trading powered by the ICC methodology with strict risk controls for small accounts.
        </p>

        <div className="mb-12 grid grid-cols-1 gap-4 text-left sm:grid-cols-2">
          {features.map((f) => (
            <div
              key={f.title}
              className="rounded-lg border border-zinc-800 bg-zinc-900 p-5"
            >
              <h3 className="mb-1 text-sm font-semibold text-blue-400">
                {f.title}
              </h3>
              <p className="text-xs leading-relaxed text-zinc-400">{f.desc}</p>
            </div>
          ))}
        </div>

        <Link
          href="/login"
          className="inline-block rounded-md bg-blue-600 px-8 py-3 text-sm font-medium text-white transition-colors hover:bg-blue-500"
        >
          Login
        </Link>
      </div>
    </div>
  );
}
