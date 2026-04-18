export type SignoffStatus = "pending" | "approved" | "rejected" | null | undefined;

interface SignoffChipProps {
  status: SignoffStatus;
  actor?: string | null;
  /** ISO timestamp — rendered as "approved 3 days ago" if present. */
  at?: string | null;
}

const LABEL: Record<"pending" | "approved" | "rejected", string> = {
  pending: "Sign-off pending",
  approved: "Approved",
  rejected: "Rejected",
};

const TONE: Record<"pending" | "approved" | "rejected", string> = {
  pending: "bg-amber-50 text-amber-800 ring-amber-200",
  approved: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  rejected: "bg-rose-50 text-rose-800 ring-rose-200",
};

/**
 * Chip that surfaces a metric revision's Slack sign-off status. Ships with
 * `null`/`undefined` support because legacy revisions (pre-Slack integration)
 * don't carry a status — in that case we render nothing rather than a
 * misleading "not required" label.
 */
export function SignoffChip({ status, actor, at }: SignoffChipProps) {
  if (!status) return null;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${TONE[status]}`}
      title={
        at
          ? `${LABEL[status]} by ${actor ?? "unknown"} on ${new Date(at).toLocaleString()}`
          : LABEL[status]
      }
    >
      <span
        aria-hidden
        className="inline-block h-1.5 w-1.5 rounded-full bg-current"
      />
      {LABEL[status]}
    </span>
  );
}
