import Link from "next/link";
import { CodeBlock } from "@/components/CodeBlock";

// NOTE(litmus-ui, task #53): The exact `dbt_project.yml` keys, macro names,
// and warehouse table schema here match blueprint §2.2 Decision 2. The dbt
// package itself is being built in parallel by `litmus-connector` (task #51);
// if their shipped snippet differs from what's below, update this page to
// match *their* README, since the package is the source of truth for install.

// TODO(litmus-ui): swap placeholder Hub URL once the dbt-hub PR lands
// (tracked in blueprint §4.1). Until then, this link is labelled "(coming
// soon)" so users aren't sent to a 404.
const DBT_HUB_URL = "https://hub.getdbt.com/litmus-data/litmus/latest/";

const PACKAGES_YML = `# packages.yml
packages:
  - package: litmus-data/litmus
    version: [">=0.3.0", "<0.4.0"]
`;

const DBT_DEPS = `dbt deps`;

const DBT_PROJECT_YML = `# dbt_project.yml
# Add the on-run-end hook so every dbt run materialises trust results.
on-run-end:
  - "{{ litmus.litmus_run_trust_checks() }}"

vars:
  litmus:
    metrics_path: "metrics/"   # where your .metric / .yml files live`;

const DBT_RUN = `dbt deps
dbt run --select litmus`;

const SAMPLE_META = `# models/finance/fct_mrr.yml — attach trust rules via \`meta:\`
models:
  - name: fct_mrr
    description: "Monthly recurring revenue."
    meta:
      litmus:
        metric: monthly_revenue
        trust:
          freshness_max_hours: 4
          volume_drop_max_pct: 5
          value_change_max_pct: 20`;

export default function InstallDbtPage() {
  return (
    <article className="prose prose-neutral max-w-none space-y-8">
      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          1. Add the package
        </h2>
        <p className="text-neutral-600">
          Drop the entry into your project&rsquo;s <code>packages.yml</code>.
        </p>
        <CodeBlock caption="packages.yml" code={PACKAGES_YML} />
        <CodeBlock caption="your shell" code={DBT_DEPS} />
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          2. Wire the on-run-end hook
        </h2>
        <p className="text-neutral-600">
          The hook fires after every <code>dbt run</code> and materialises
          results into <code>litmus_runs</code> and{" "}
          <code>litmus_check_results</code> tables.
        </p>
        <CodeBlock caption="dbt_project.yml" code={DBT_PROJECT_YML} />
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          3. Declare trust rules
        </h2>
        <p className="text-neutral-600">
          Two paths — drop <code>.metric</code> / YAML files into{" "}
          <code>metrics/</code>, or attach rules directly to a dbt model via{" "}
          <code>meta:</code>.
        </p>
        <CodeBlock caption="models/finance/fct_mrr.yml" code={SAMPLE_META} />
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          4. Run it
        </h2>
        <CodeBlock caption="your shell" code={DBT_RUN} />
        <p className="mt-3 text-neutral-600">
          A fresh <code>litmus_runs</code> table appears in your warehouse
          after the first run. Point the Litmus UI at it and the catalog
          populates automatically.
        </p>
      </section>

      <aside className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 text-sm text-amber-900">
        <div className="font-semibold">dbt Hub listing — coming soon</div>
        <p className="mt-1 text-amber-800">
          Submission to{" "}
          <a
            href={DBT_HUB_URL}
            target="_blank"
            rel="noreferrer"
            className="underline"
          >
            hub.getdbt.com
          </a>{" "}
          is in flight (task #51). The GitHub-release install above already
          works today on every dbt adapter we ship for.
        </p>
      </aside>

      <div className="flex flex-wrap items-center gap-3 pt-4">
        <Link
          href="/install/cli"
          className="text-sm text-neutral-600 hover:text-neutral-900"
        >
          &larr; Prefer the standalone CLI?
        </Link>
        <Link
          href="/install/slack"
          className="text-sm text-neutral-600 hover:text-neutral-900"
        >
          Next: Slack sign-off &rarr;
        </Link>
      </div>
    </article>
  );
}
