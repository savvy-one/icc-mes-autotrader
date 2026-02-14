"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { WSStatus } from "./WSStatus";
import { useAuthStore } from "@/stores/authStore";
import type { WSReadyState } from "@/hooks/useWebSocket";

const navLinks = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/trades", label: "Trades" },
  { href: "/config", label: "Config" },
];

export function Header({ wsState }: { wsState: WSReadyState }) {
  const pathname = usePathname();
  const logout = useAuthStore((s) => s.logout);

  return (
    <header className="flex items-center justify-between border-b border-zinc-700 bg-zinc-900 px-4 py-3">
      <div className="flex items-center gap-6">
        <span className="text-sm font-bold tracking-wide text-white">
          ICC AutoTrader
        </span>
        <nav className="flex gap-4">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`text-sm transition-colors ${
                pathname === link.href
                  ? "text-blue-400"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
      <div className="flex items-center gap-4">
        <WSStatus state={wsState} />
        <button
          onClick={logout}
          className="text-xs text-zinc-500 transition-colors hover:text-zinc-200"
        >
          Logout
        </button>
      </div>
    </header>
  );
}
