"use client";

import { useEffect, useState } from "react";
import { getConfig } from "@/lib/api";
import { Panel } from "@/components/ui/Panel";

export default function ConfigPage() {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getConfig()
      .then(setConfig)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="p-4 text-zinc-500">Loading...</p>;
  if (!config) return <p className="p-4 text-zinc-500">Failed to load config.</p>;

  const sections = ["strategy", "risk", "ib"] as const;

  return (
    <div>
      <h1 className="mb-4 text-lg font-bold">Configuration</h1>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Top-level scalars */}
        <Panel title="General">
          <ConfigTable
            data={{
              env: config.env,
              db_url: config.db_url,
              log_level: config.log_level,
            }}
          />
        </Panel>

        {sections.map((key) => {
          const section = config[key];
          if (!section || typeof section !== "object") return null;
          return (
            <Panel key={key} title={key.toUpperCase()}>
              <ConfigTable data={section as Record<string, unknown>} />
            </Panel>
          );
        })}
      </div>
    </div>
  );
}

function ConfigTable({ data }: { data: Record<string, unknown> }) {
  return (
    <table className="w-full text-xs">
      <tbody>
        {Object.entries(data).map(([k, v]) => (
          <tr key={k} className="border-b border-zinc-800">
            <td className="py-1 pr-3 text-zinc-400">{k}</td>
            <td className="py-1 text-zinc-200">{String(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
