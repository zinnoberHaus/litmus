"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Segmented-control nav for the install flow. dbt is the primary path per
 * blueprint — it is visually emphasised and always first.
 */

const TABS = [
  { href: "/install/dbt", label: "dbt package", hint: "primary" },
  { href: "/install/cli", label: "Standalone CLI" },
  { href: "/install/hosted", label: "Self-hosted" },
  { href: "/install/slack", label: "Slack" },
];

export function InstallTabs() {
  const pathname = usePathname();
  return (
    <div className="flex flex-wrap gap-2 rounded-xl border border-neutral-200 bg-white p-1 shadow-sm">
      {TABS.map((t) => {
        const active =
          pathname === t.href ||
          (t.href !== "/install" && pathname?.startsWith(t.href));
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              active
                ? "bg-neutral-900 text-white shadow-sm"
                : "text-neutral-600 hover:bg-neutral-50 hover:text-neutral-900"
            }`}
          >
            {t.label}
            {t.hint && (
              <span
                className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                  active
                    ? "bg-white/20 text-white"
                    : "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200"
                }`}
              >
                {t.hint}
              </span>
            )}
          </Link>
        );
      })}
    </div>
  );
}
