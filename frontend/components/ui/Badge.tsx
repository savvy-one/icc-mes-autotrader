export type BadgeColor = "green" | "red" | "yellow" | "blue" | "zinc" | "emerald" | "purple" | "amber" | "cyan";

const colors: Record<BadgeColor, string> = {
  green: "bg-green-900/50 text-green-400 border-green-700",
  red: "bg-red-900/50 text-red-400 border-red-700",
  yellow: "bg-yellow-900/50 text-yellow-400 border-yellow-700",
  blue: "bg-blue-900/50 text-blue-400 border-blue-700",
  zinc: "bg-zinc-800 text-zinc-400 border-zinc-600",
  emerald: "bg-emerald-900/50 text-emerald-400 border-emerald-700",
  purple: "bg-purple-900/50 text-purple-400 border-purple-700",
  amber: "bg-amber-900/50 text-amber-400 border-amber-700",
  cyan: "bg-cyan-900/50 text-cyan-400 border-cyan-700",
};

interface BadgeProps {
  color?: BadgeColor;
  children: React.ReactNode;
}

export function Badge({ color = "zinc", children }: BadgeProps) {
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${colors[color]}`}
    >
      {children}
    </span>
  );
}
