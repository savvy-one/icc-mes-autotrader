"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4 text-center">
      <h2 className="text-lg font-bold text-red-400">Something went wrong</h2>
      <p className="text-sm text-zinc-400">{error.message}</p>
      <button
        onClick={reset}
        className="rounded bg-zinc-700 px-4 py-2 text-sm text-white hover:bg-zinc-600"
      >
        Try again
      </button>
    </div>
  );
}
