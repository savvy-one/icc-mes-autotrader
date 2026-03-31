"use client";

import dynamic from "next/dynamic";
import { SessionControls } from "@/components/dashboard/SessionControls";
import { FSMStatePanel } from "@/components/dashboard/FSMStatePanel";
import { PnLPanel } from "@/components/dashboard/PnLPanel";
import { PositionPanel } from "@/components/dashboard/PositionPanel";
import { OptionContractPanel } from "@/components/dashboard/OptionContractPanel";
import { TickerStatesPanel } from "@/components/dashboard/TickerStatesPanel";
import { EventLog } from "@/components/dashboard/EventLog";

const CandleChart = dynamic(
  () => import("@/components/dashboard/CandleChart").then((m) => m.CandleChart),
  { ssr: false },
);

export default function DashboardPage() {
  return (
    <div className="space-y-4">
      <SessionControls />

      {/* Multi-ticker ORB panel (only visible when multi-ticker active) */}
      <TickerStatesPanel />

      {/* Status panels */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <FSMStatePanel />
        <PnLPanel />
        <PositionPanel />
        <OptionContractPanel />
      </div>

      {/* Chart */}
      <CandleChart />

      {/* Event log */}
      <EventLog />
    </div>
  );
}
