import { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "danger" | "secondary";

const variants: Record<Variant, string> = {
  primary:
    "bg-blue-600 hover:bg-blue-700 text-white",
  danger:
    "bg-red-600 hover:bg-red-700 text-white",
  secondary:
    "bg-zinc-700 hover:bg-zinc-600 text-zinc-200",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({
  variant = "primary",
  className = "",
  disabled,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`rounded px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
      disabled={disabled}
      {...rest}
    >
      {children}
    </button>
  );
}
