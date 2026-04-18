import type { Metadata } from "next";
import Link from "next/link";
import { Nav } from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Litmus — Canonical metric contracts",
  description:
    "Canonical metric contracts for engineers, AI-answered questions for PMs, embeddable trust badges for everyone.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <Nav />
        <main>{children}</main>
        <footer className="border-t border-neutral-200 bg-white">
          <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-8 text-xs text-neutral-500 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-2">
              <span
                aria-hidden
                className="inline-block h-2 w-2 rounded-full bg-trust-pass"
              />
              <span className="font-medium text-neutral-700">Litmus</span>
              <span>— canonical metric contracts.</span>
            </div>
            <div className="flex flex-wrap items-center gap-4">
              <Link href="/metrics" className="hover:text-neutral-800">
                Catalog
              </Link>
              <Link href="/install" className="hover:text-neutral-800">
                Install
              </Link>
              <Link href="/ask" className="hover:text-neutral-800">
                Ask
              </Link>
              <Link href="/badge" className="hover:text-neutral-800">
                Badges
              </Link>
              <a
                href="https://github.com/zinnoberHaus/litmus"
                target="_blank"
                rel="noreferrer"
                className="hover:text-neutral-800"
              >
                GitHub
              </a>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
