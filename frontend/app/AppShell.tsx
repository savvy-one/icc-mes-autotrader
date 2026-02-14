"use client";

import { Header } from "@/components/layout/Header";
import { useWebSocket } from "@/hooks/useWebSocket";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { readyState } = useWebSocket();

  return (
    <div className="flex min-h-screen flex-col">
      <Header wsState={readyState} />
      <main className="flex-1 p-4">{children}</main>
    </div>
  );
}
