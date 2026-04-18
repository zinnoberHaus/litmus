import Link from "next/link";

/**
 * App-router 404. Explicit not-found.tsx avoids Next.js 15's default 404
 * prerender path which tries to import <Html> from `pages/_document` and
 * fails in App-Router-only projects.
 */
export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-xl flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-full bg-neutral-100 text-neutral-500">
        <svg
          viewBox="0 0 24 24"
          width="24"
          height="24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        </svg>
      </div>
      <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">
        Page not found
      </h1>
      <p className="mt-2 text-sm text-neutral-600">
        That URL doesn&rsquo;t match anything in the Litmus catalog.
      </p>
      <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
        <Link
          href="/"
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800"
        >
          Back home
        </Link>
        <Link
          href="/metrics"
          className="rounded-md border border-neutral-200 bg-white px-4 py-2 text-sm font-medium text-neutral-800 hover:border-neutral-300 hover:bg-neutral-50"
        >
          Browse catalog
        </Link>
      </div>
    </div>
  );
}
