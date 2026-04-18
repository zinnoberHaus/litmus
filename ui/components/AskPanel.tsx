"use client";

/**
 * AskPanel — reusable AI Q&A chat component.
 *
 * Two modes:
 * - ``mode="sidebar"`` (on `/metrics/[slug]`): narrower, pre-seeded with the
 *   current metric's slug so the first turn is scoped to that metric.
 * - ``mode="standalone"`` (on `/ask`): full-width, no pre-seeded metric.
 *
 * The component posts to ``POST /api/v1/ask`` (see ``lib/ask.ts``) which is
 * built in parallel per blueprint task #54. Until that endpoint ships, the
 * helper returns a mocked response; the UI is forward-compatible with the
 * real API because it only consumes the agreed `AskResponse` shape.
 *
 * Empty-state seed questions are pulled from a small list the server will
 * eventually provide per-metric. For now they're static copy so users can
 * try the chat flow without typing.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { postAsk, type AskResponse, type AskError } from "@/lib/ask";

interface AskPanelProps {
  mode?: "sidebar" | "standalone";
  /** When set, seeds `metric_slug` on the request so the answer is scoped. */
  metricSlug?: string;
  /** Optional metric name used in the empty-state copy. */
  metricName?: string;
  /** Optional seed prompts; falls back to a generic set. */
  suggestions?: string[];
}

type ChatTurn =
  | { role: "user"; text: string; id: string }
  | { role: "assistant"; response: AskResponse; id: string }
  | { role: "error"; error: AskError; id: string };

const DEFAULT_SUGGESTIONS = [
  "what was revenue last month?",
  "are active users trending up?",
  "is churn still failing trust checks?",
];

const STATUS_DOT: Record<AskResponse["trust_status"], string> = {
  passed: "bg-trust-pass",
  warning: "bg-trust-warn",
  failed: "bg-trust-fail",
  error: "bg-trust-fail",
  unknown: "bg-neutral-400",
};

const STATUS_LABEL: Record<AskResponse["trust_status"], string> = {
  passed: "Trusted",
  warning: "Review",
  failed: "Broken",
  error: "Error",
  unknown: "Unknown",
};

export function AskPanel({
  mode = "standalone",
  metricSlug,
  metricName,
  suggestions,
}: AskPanelProps) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const turnIdRef = useRef(0);
  const endRef = useRef<HTMLDivElement>(null);

  const seeds =
    suggestions ??
    (metricName
      ? [
          `what's the value of ${metricName.toLowerCase()} right now?`,
          `has ${metricName.toLowerCase()} changed in the last 7 days?`,
          `why is ${metricName.toLowerCase()} in warning?`,
        ]
      : DEFAULT_SUGGESTIONS);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy]);

  async function send(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    const userId = `t${turnIdRef.current++}`;
    setTurns((prev) => [...prev, { role: "user", text: trimmed, id: userId }]);
    setInput("");
    setBusy(true);
    try {
      const response = await postAsk({
        question: trimmed,
        metric_slug: metricSlug,
        context: { source: mode === "sidebar" ? "metric_detail" : "ask_page" },
      });
      const asstId = `t${turnIdRef.current++}`;
      setTurns((prev) => [
        ...prev,
        { role: "assistant", response, id: asstId },
      ]);
    } catch (err) {
      const asstId = `t${turnIdRef.current++}`;
      const error =
        err && typeof err === "object" && "code" in err
          ? (err as AskError)
          : ({
              code: "transport",
              message: err instanceof Error ? err.message : String(err),
            } satisfies AskError);
      setTurns((prev) => [...prev, { role: "error", error, id: asstId }]);
    } finally {
      setBusy(false);
    }
  }

  const isSidebar = mode === "sidebar";
  const outer = isSidebar
    ? "flex h-full flex-col rounded-xl border border-neutral-200 bg-white"
    : "flex min-h-[520px] flex-col rounded-xl border border-neutral-200 bg-white shadow-sm";

  return (
    <div className={outer}>
      {!isSidebar ? (
        <div className="flex items-center gap-2 border-b border-neutral-200 px-5 py-3 text-sm font-medium text-neutral-700">
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-full bg-violet-500"
          />
          Ask Litmus
          <span className="ml-2 rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-700 ring-1 ring-violet-200">
            beta
          </span>
        </div>
      ) : (
        <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-700">
            <span
              aria-hidden
              className="inline-block h-2 w-2 rounded-full bg-violet-500"
            />
            Ask about this metric
          </div>
          <Link
            href="/ask"
            className="text-xs text-neutral-500 hover:text-neutral-800"
          >
            Open full chat &rarr;
          </Link>
        </div>
      )}

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {turns.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-neutral-600">
              Ask a plain-English question. Answers come with a trust status
              and a link to the metric definition — no SQL required.
            </p>
            <div className="flex flex-wrap gap-2">
              {seeds.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => send(s)}
                  className="rounded-full border border-neutral-200 bg-neutral-50 px-3 py-1 text-xs text-neutral-700 hover:border-neutral-300 hover:bg-white"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t) => (
          <TurnView key={t.id} turn={t} />
        ))}

        {busy && (
          <div className="flex items-center gap-2 text-xs text-neutral-500">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-violet-500" />
            Thinking…
          </div>
        )}

        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
        className="flex items-center gap-2 border-t border-neutral-200 px-4 py-3"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            isSidebar ? "Ask about this metric…" : "Ask any metric question…"
          }
          className="flex-1 rounded-md border border-neutral-200 bg-white px-3 py-2 text-sm placeholder:text-neutral-400 focus:border-violet-300 focus:outline-none focus:ring-2 focus:ring-violet-200"
          disabled={busy}
        />
        <button
          type="submit"
          disabled={busy || input.trim().length === 0}
          className="rounded-md bg-violet-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-neutral-300"
        >
          Ask
        </button>
      </form>
    </div>
  );
}

function TurnView({ turn }: { turn: ChatTurn }) {
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-violet-600 px-3 py-2 text-sm text-white shadow-sm">
          {turn.text}
        </div>
      </div>
    );
  }
  if (turn.role === "error") {
    return (
      <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
        <div className="font-medium">Could not answer that.</div>
        <p className="mt-1 text-xs font-mono text-rose-700">
          {turn.error.message}
        </p>
        {turn.error.suggestions && turn.error.suggestions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {turn.error.suggestions.map((s) => (
              <span
                key={s}
                className="rounded-full bg-white px-2 py-0.5 text-[11px] ring-1 ring-rose-200"
              >
                {s}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }
  const r = turn.response;
  return (
    <div className="max-w-[92%] rounded-2xl rounded-tl-sm border border-neutral-200 bg-neutral-50 px-3 py-3 shadow-sm">
      <div className="flex items-center gap-2 text-xs text-neutral-500">
        <span
          aria-hidden
          className={`inline-block h-2 w-2 rounded-full ${STATUS_DOT[r.trust_status]}`}
        />
        <span className="font-medium text-neutral-700">
          {STATUS_LABEL[r.trust_status]}
        </span>
        {r.metric_name && (
          <span className="text-neutral-500">· {r.metric_name}</span>
        )}
        {r.time_window && (
          <span className="ml-auto rounded-full bg-white px-2 py-0.5 text-[10px] uppercase tracking-wide ring-1 ring-neutral-200">
            {r.time_window.replaceAll("_", " ")}
          </span>
        )}
      </div>
      <p className="mt-2 text-sm leading-snug text-neutral-900">{r.answer}</p>
      {r.explanation && (
        <p className="mt-2 border-l-2 border-neutral-300 pl-3 text-xs italic text-neutral-600">
          {r.explanation}
        </p>
      )}
      <div className="mt-2 flex items-center justify-between text-[11px] text-neutral-500">
        <Link
          href={r.metric_url ?? r.definition_url}
          className="text-neutral-600 underline decoration-dotted underline-offset-2 hover:text-neutral-900"
        >
          View metric definition &rarr;
        </Link>
        {r.model_id && (
          <span className="font-mono text-neutral-400">{r.model_id}</span>
        )}
      </div>
    </div>
  );
}
