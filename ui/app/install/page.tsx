import Link from "next/link";

const OPTIONS = [
  {
    href: "/install/dbt",
    title: "dbt package",
    tag: "recommended",
    tagTone: "indigo",
    blurb:
      "Ship as an on-run-end hook alongside your existing dbt models. Zero new infra; results land in a warehouse table.",
  },
  {
    href: "/install/cli",
    title: "Standalone CLI",
    tag: "no dbt",
    tagTone: "neutral",
    blurb:
      "Pip install, connect a warehouse, commit your `.metric` files, and run `litmus check` locally or in CI.",
  },
  {
    href: "/install/hosted",
    title: "Self-hosted catalog + badges",
    tag: "Docker",
    tagTone: "neutral",
    blurb:
      "Run the FastAPI catalog and Next.js UI in your own infra. Lets you publish embed badges and expose /ask to PMs.",
  },
  {
    href: "/install/slack",
    title: "Slack sign-off + /ask",
    tag: "new",
    tagTone: "violet",
    blurb:
      "Post sign-off prompts to a Slack channel and handle approvals via block-kit buttons. Webhook-only for v0.3 — full Slack App in v0.4.",
  },
] as const;

export default function InstallHubPage() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {OPTIONS.map((o) => (
        <Link
          key={o.href}
          href={o.href}
          className="group rounded-xl border border-neutral-200 bg-white p-5 shadow-sm transition hover:border-neutral-300 hover:shadow"
        >
          <div className="flex items-start justify-between gap-3">
            <h2 className="text-base font-semibold tracking-tight group-hover:underline">
              {o.title}
            </h2>
            <Tag tone={o.tagTone}>{o.tag}</Tag>
          </div>
          <p className="mt-2 text-sm text-neutral-600">{o.blurb}</p>
          <div className="mt-3 text-xs font-medium text-neutral-500 group-hover:text-neutral-800">
            Open walkthrough &rarr;
          </div>
        </Link>
      ))}
    </div>
  );
}

function Tag({
  tone,
  children,
}: {
  tone: "indigo" | "neutral" | "violet";
  children: React.ReactNode;
}) {
  const map = {
    indigo: "bg-indigo-50 text-indigo-700 ring-indigo-200",
    violet: "bg-violet-50 text-violet-700 ring-violet-200",
    neutral: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ${map[tone]}`}
    >
      {children}
    </span>
  );
}
