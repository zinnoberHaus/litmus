import { CopyButton } from "./CopyButton";

interface CodeBlockProps {
  code: string;
  language?: string;
  /** Optional small caption above the block (e.g. filename, shell label). */
  caption?: string;
  /** Hide the copy affordance (rarely useful — defaults to visible). */
  hideCopy?: boolean;
}

/**
 * Server-rendered code block with a floating copy button. No syntax
 * highlighting dependency — the goal is zero new runtime deps. Captions are
 * used to disambiguate "your shell" vs "packages.yml" vs "README.md" snippets
 * on the install flow.
 */
export function CodeBlock({ code, language, caption, hideCopy }: CodeBlockProps) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-neutral-200 bg-neutral-950">
      {caption ? (
        <div className="flex items-center justify-between border-b border-neutral-800 bg-neutral-900 px-4 py-2 text-xs text-neutral-400">
          <span className="font-mono">{caption}</span>
          {language ? (
            <span className="text-[10px] uppercase tracking-wide text-neutral-500">
              {language}
            </span>
          ) : null}
        </div>
      ) : null}
      <pre className="overflow-x-auto px-4 py-3 font-mono text-xs text-neutral-100">
        <code>{code}</code>
      </pre>
      {!hideCopy ? <CopyButton text={code} floating /> : null}
    </div>
  );
}
