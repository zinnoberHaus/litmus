import type { TrustStatus } from "@/lib/fixtures";

interface TrustBadgeProps {
  status: TrustStatus;
  score?: number;
  size?: "sm" | "md";
  label?: string;
}

const STATUS_COPY: Record<TrustStatus, string> = {
  pass: "Trusted",
  warn: "Review",
  fail: "Broken",
};

const STATUS_CLASSES: Record<TrustStatus, string> = {
  pass: "bg-green-50 text-trust-pass ring-green-200",
  warn: "bg-yellow-50 text-trust-warn ring-yellow-200",
  fail: "bg-red-50 text-trust-fail ring-red-200",
};

const DOT_CLASSES: Record<TrustStatus, string> = {
  pass: "bg-trust-pass",
  warn: "bg-trust-warn",
  fail: "bg-trust-fail",
};

export function TrustBadge({
  status,
  score,
  size = "md",
  label,
}: TrustBadgeProps) {
  const dims =
    size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full ring-1 ${STATUS_CLASSES[status]} ${dims} font-medium`}
    >
      <span
        aria-hidden
        className={`inline-block h-2 w-2 rounded-full ${DOT_CLASSES[status]}`}
      />
      <span>{label ?? STATUS_COPY[status]}</span>
      {typeof score === "number" && (
        <span className="font-mono text-[0.7em] opacity-80">
          {(score * 100).toFixed(0)}
        </span>
      )}
    </span>
  );
}
