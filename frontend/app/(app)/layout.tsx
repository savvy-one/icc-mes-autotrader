"use client";

import { useEffect } from "react";
import { AppShell } from "../AppShell";
import { useAuthStore } from "@/stores/authStore";
import { verifyToken } from "@/lib/api";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { hydrate, logout, isAuthenticated } = useAuthStore();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (!isAuthenticated) return;
    verifyToken().catch(() => {
      // Don't logout on verify failure — may be a transient network issue
      // (e.g. ngrok tunnel not reachable). The token is still valid locally.
    });
  }, [isAuthenticated]);

  return <AppShell>{children}</AppShell>;
}
