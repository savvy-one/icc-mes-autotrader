interface PanelProps {
  title: string;
  children: React.ReactNode;
  className?: string;
}

export function Panel({ title, children, className = "" }: PanelProps) {
  return (
    <div
      className={`rounded-lg border border-zinc-700 bg-zinc-900 p-4 ${className}`}
    >
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">
        {title}
      </h3>
      {children}
    </div>
  );
}
