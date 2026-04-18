import Link from "next/link";
import { AskPanel } from "@/components/AskPanel";

export const metadata = {
  title: "Ask Litmus — AI-answered metric questions",
  description:
    "Ask plain-English questions about your business metrics. Every answer is stamped with a trust status and a link to the canonical definition.",
};

export default function AskPage() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <div className="mb-8">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-violet-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-violet-700 ring-1 ring-violet-200">
          For PMs · AI Q&amp;A
        </span>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">
          Ask Litmus
        </h1>
        <p className="mt-2 max-w-2xl text-neutral-600">
          Plain-English questions in, warehouse-backed answers out. Every
          response is stamped with the trust status and a link to the
          canonical metric definition — no SQL, no YAML, no git.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <AskPanel mode="standalone" />
        <aside className="space-y-4">
          <div className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-700">
              How it works
            </h3>
            <ol className="mt-3 space-y-2 text-xs text-neutral-600">
              <li>
                <strong className="text-neutral-900">1.</strong> Your question
                is resolved to a catalog metric by Claude with forced
                tool-use.
              </li>
              <li>
                <strong className="text-neutral-900">2.</strong> SQL is
                generated from the metric spec (never from the model output).
              </li>
              <li>
                <strong className="text-neutral-900">3.</strong> The query
                runs against your warehouse on a read-only connection.
              </li>
              <li>
                <strong className="text-neutral-900">4.</strong> The answer
                ships with the latest trust status from Litmus checks.
              </li>
            </ol>
          </div>
          <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 text-xs text-amber-900">
            <div className="font-semibold">Privacy</div>
            <p className="mt-1 text-amber-800">
              Claude sees your metric names, descriptions, and trust rules —
              never raw warehouse rows or SQL. Full disclosure in{" "}
              <a
                href="https://github.com/zinnoberHaus/litmus/tree/main/docs/ai-ask.md"
                target="_blank"
                rel="noreferrer"
                className="underline"
              >
                docs/ai-ask.md
              </a>
              .
            </p>
          </div>
          <Link
            href="/install/slack"
            className="block rounded-xl border border-neutral-200 bg-white p-4 shadow-sm transition hover:border-neutral-300 hover:shadow"
          >
            <div className="text-sm font-semibold text-neutral-900">
              Prefer Slack?
            </div>
            <p className="mt-1 text-xs text-neutral-600">
              Add <code>/ask</code> to your workspace and answer questions
              without leaving the channel. Setup takes ~5 min.
            </p>
            <div className="mt-2 text-xs font-medium text-neutral-500">
              Slack setup &rarr;
            </div>
          </Link>
        </aside>
      </div>
    </div>
  );
}
