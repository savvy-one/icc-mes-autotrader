"use client";

import { SessionControls } from "@/components/dashboard/SessionControls";
import { FSMStatePanel } from "@/components/dashboard/FSMStatePanel";
import { PnLPanel } from "@/components/dashboard/PnLPanel";
import { PositionPanel } from "@/components/dashboard/PositionPanel";
import { CandleChart } from "@/components/dashboard/CandleChart";
import { EventLog } from "@/components/dashboard/EventLog";

export default function DashboardPage() {
  return (
    <div className="space-y-4">
      <SessionControls />

      {/* Status panels */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <FSMStatePanel />
        <PnLPanel />
        <PositionPanel />
      </div>

      {/* Chart */}
      <CandleChart />

      {/* Event log */}
      <EventLog />
    </div>
  );
}
