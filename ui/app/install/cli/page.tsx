import Link from "next/link";
import { CodeBlock } from "@/components/CodeBlock";

const PIP_INSTALL = `pip install litmus-data`;

const INIT_CMD = `litmus init demo-metrics --warehouse duckdb
cd demo-metrics`;

const CHECK_CMD = `litmus check metrics/`;

const CI_SNIPPET = `# .github/workflows/metrics.yml
name: Litmus
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: litmus-data/litmus@v0
        with:
          path: metrics/
          fail-on-warning: false`;

const WAREHOUSE_ENV = `# Credentials are read from env vars only — never commit them to litmus.yml.
export LITMUS_WAREHOUSE_USER=...
export LITMUS_WAREHOUSE_PASSWORD=...`;

export default function InstallCliPage() {
  return (
    <article className="space-y-8">
      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          1. Install
        </h2>
        <CodeBlock caption="your shell" code={PIP_INSTALL} />
        <p className="mt-2 text-sm text-neutral-600">
          Python 3.10+. DuckDB ships zero-config; extras for{" "}
          <code>postgres</code>, <code>snowflake</code>, <code>bigquery</code>.
        </p>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          2. Scaffold a project
        </h2>
        <CodeBlock caption="your shell" code={INIT_CMD} />
        <p className="mt-2 text-sm text-neutral-600">
          Generates a <code>litmus.yml</code>, a DuckDB file with seed data,
          and example <code>.metric</code> / YAML files you can edit.
        </p>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          3. Run trust checks
        </h2>
        <CodeBlock caption="your shell" code={CHECK_CMD} />
        <p className="mt-2 text-sm text-neutral-600">
          Exits non-zero if any rule fails. History is written to{" "}
          <code>~/.litmus/history.db</code> (SQLite) by default — change via{" "}
          <code>--backend warehouse</code> or <code>LITMUS_HISTORY_DB</code>.
        </p>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          4. Wire into CI
        </h2>
        <CodeBlock caption=".github/workflows/metrics.yml" code={CI_SNIPPET} />
        <p className="mt-2 text-sm text-neutral-600">
          The action pins on <code>@v0</code> — inputs/outputs are promised
          stable across v0.3 and beyond.
        </p>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          5. Point at your warehouse
        </h2>
        <CodeBlock caption="your shell" code={WAREHOUSE_ENV} />
        <p className="mt-2 text-sm text-neutral-600">
          Credentials live only in env vars. See{" "}
          <a
            href="https://github.com/zinnoberHaus/litmus/tree/main/docs/getting-started.md"
            target="_blank"
            rel="noreferrer"
            className="underline underline-offset-2"
          >
            docs/getting-started.md
          </a>{" "}
          for per-adapter setup.
        </p>
      </section>

      <div className="flex flex-wrap items-center gap-3 pt-4">
        <Link
          href="/install/dbt"
          className="text-sm text-neutral-600 hover:text-neutral-900"
        >
          &larr; Rather run inside dbt?
        </Link>
        <Link
          href="/install/hosted"
          className="text-sm text-neutral-600 hover:text-neutral-900"
        >
          Next: self-host the UI &rarr;
        </Link>
      </div>
    </article>
  );
}
