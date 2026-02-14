type BadgeColor = "green" | "red" | "yellow" | "blue" | "zinc";

const colors: Record<BadgeColor, string> = {
  green: "bg-green-900/50 text-green-400 border-green-700",
  red: "bg-red-900/50 text-red-400 border-red-700",
  yellow: "bg-yellow-900/50 text-yellow-400 border-yellow-700",
  blue: "bg-blue-900/50 text-blue-400 border-blue-700",
  zinc: "bg-zinc-800 text-zinc-400 border-zinc-600",
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
