import type { ReactNode } from "react";

interface SectionProps {
  id?: string;
  /** Small uppercase "for engineers" eyebrow. */
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  /** Anchor link/CTA shown on the right of the heading row. */
  action?: ReactNode;
  /** Tone tints the eyebrow + section divider. Mirrors the audience colors. */
  tone?: "engineers" | "pm" | "viewers" | "neutral";
  children: ReactNode;
  /** Add extra vertical padding, used for the landing sections. */
  spacious?: boolean;
  className?: string;
}

const TONE_ACCENT: Record<NonNullable<SectionProps["tone"]>, string> = {
  engineers: "text-indigo-700 bg-indigo-50 ring-indigo-200",
  pm: "text-violet-700 bg-violet-50 ring-violet-200",
  viewers: "text-emerald-700 bg-emerald-50 ring-emerald-200",
  neutral: "text-neutral-600 bg-neutral-100 ring-neutral-200",
};

/**
 * Landing-style section wrapper used on `/`, `/install`, `/ask`, `/badge`.
 * Keeps heading/eyebrow/CTA rhythm consistent across the marketing pages
 * without pulling in a new component library.
 */
export function Section({
  id,
  eyebrow,
  title,
  description,
  action,
  tone = "neutral",
  spacious = false,
  children,
  className = "",
}: SectionProps) {
  return (
    <section
      id={id}
      className={`${spacious ? "py-16" : "py-10"} ${className}`.trim()}
    >
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          {eyebrow ? (
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ring-1 ${TONE_ACCENT[tone]}`}
            >
              {eyebrow}
            </span>
          ) : null}
          <h2 className="mt-3 text-2xl font-semibold tracking-tight text-neutral-900 md:text-3xl">
            {title}
          </h2>
          {description ? (
            <div className="mt-2 max-w-3xl text-neutral-600">{description}</div>
          ) : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      {children}
    </section>
  );
}
