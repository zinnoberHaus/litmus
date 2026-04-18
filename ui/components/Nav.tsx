import Link from "next/link";

interface NavProps {
  /** Dim the top nav to a subtler fill on marketing pages. */
  variant?: "app" | "marketing";
}

/**
 * Global top nav. Per blueprint (§2.5) the OSS build hides the org switcher
 * and renders a "Powered by Litmus" attribution on the right; Cloud will
 * re-introduce the switcher in a later release.
 *
 * The Docs link is an external anchor to the GitHub docs folder — this
 * matches the blueprint decision to not ship a hosted docs site in v0.3.
 */
export function Nav({ variant = "app" }: NavProps) {
  const wrap =
    variant === "marketing"
      ? "border-b border-neutral-200 bg-white/80 backdrop-blur"
      : "border-b border-neutral-200 bg-white";
  return (
    <header className={wrap}>
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/" className="flex items-center gap-2">
          <span
            aria-hidden
            className="inline-block h-3 w-3 rounded-full bg-trust-pass"
          />
          <span className="text-lg font-semibold tracking-tight text-neutral-900">
            Litmus
          </span>
        </Link>
        <nav className="flex items-center gap-1 text-sm text-neutral-600 md:gap-4">
          <NavLink href="/metrics">Catalog</NavLink>
          <NavLink href="/install">Install</NavLink>
          <NavLink href="/ask">Ask</NavLink>
          <NavLink href="/badge">Badges</NavLink>
          <a
            href="https://github.com/zinnoberHaus/litmus/tree/main/docs"
            target="_blank"
            rel="noreferrer"
            className="rounded-md px-2 py-1 hover:bg-neutral-100 hover:text-neutral-900"
          >
            Docs
          </a>
          <a
            href="https://github.com/zinnoberHaus/litmus"
            target="_blank"
            rel="noreferrer"
            className="ml-2 inline-flex items-center gap-1.5 rounded-md border border-neutral-200 px-2.5 py-1 text-xs font-medium text-neutral-700 hover:border-neutral-300 hover:bg-neutral-50"
            aria-label="Litmus on GitHub"
          >
            <GitHubGlyph />
            GitHub
          </a>
        </nav>
      </div>
    </header>
  );
}

function NavLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="rounded-md px-2 py-1 hover:bg-neutral-100 hover:text-neutral-900"
    >
      {children}
    </Link>
  );
}

function GitHubGlyph() {
  return (
    <svg
      viewBox="0 0 16 16"
      width="14"
      height="14"
      aria-hidden
      className="fill-current"
    >
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}
