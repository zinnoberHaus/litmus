import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Litmus — Metric Catalog",
  description:
    "Trust-first metric catalog. Every number has a definition, a lineage, and a passing trust check.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-neutral-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <Link href="/" className="flex items-center gap-2">
              <span
                aria-hidden
                className="inline-block h-3 w-3 rounded-full bg-trust-pass"
              />
              <span className="text-lg font-semibold tracking-tight">
                Litmus
              </span>
              <span className="text-sm text-neutral-500">metric catalog</span>
            </Link>
            <nav className="flex items-center gap-4 text-sm text-neutral-600">
              <Link
                href="/"
                className="hover:text-neutral-900"
              >
                Catalog
              </Link>
              <a
                href="https://github.com/"
                target="_blank"
                rel="noreferrer"
                className="hover:text-neutral-900"
              >
                GitHub
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
        <footer className="mx-auto max-w-6xl px-6 py-10 text-xs text-neutral-500">
          Litmus UI scaffold — dummy data. Wire to the Python API when ready.
        </footer>
      </body>
    </html>
  );
}
