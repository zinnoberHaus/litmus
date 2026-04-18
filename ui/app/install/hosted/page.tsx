import Link from "next/link";
import { CodeBlock } from "@/components/CodeBlock";

const DOCKER_COMPOSE = `# docker-compose.yml
version: "3.9"
services:
  litmus-api:
    image: ghcr.io/zinnoberhaus/litmus:0.3
    ports: ["8080:8080"]
    environment:
      LITMUS_AUTO_MIGRATE: "true"
      LITMUS_PUBLIC_URL: "http://localhost:8080"
  litmus-ui:
    image: ghcr.io/zinnoberhaus/litmus-ui:0.3
    ports: ["3000:3000"]
    environment:
      NEXT_PUBLIC_LITMUS_API: "http://localhost:8080"
    depends_on: [litmus-api]
`;

const DOCKER_UP = `docker-compose up`;

const PUSH_CMD = `litmus check metrics/ --push http://localhost:8080`;

export default function InstallHostedPage() {
  return (
    <article className="space-y-8">
      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          1. Spin it up
        </h2>
        <CodeBlock caption="docker-compose.yml" code={DOCKER_COMPOSE} />
        <CodeBlock caption="your shell" code={DOCKER_UP} />
        <p className="mt-2 text-sm text-neutral-600">
          Visit <code>http://localhost:3000</code> for the catalog UI and{" "}
          <code>http://localhost:8080/docs</code> for the OpenAPI explorer.
        </p>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          2. Push runs from CI
        </h2>
        <CodeBlock caption="your shell" code={PUSH_CMD} />
        <p className="mt-2 text-sm text-neutral-600">
          The <code>--push</code> flag upserts each metric and writes a run
          row. Private repos need an API key (<code>--api-key</code>).
        </p>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          3. Embed badges
        </h2>
        <p className="text-sm text-neutral-600">
          Every metric gets an embed token. Drop the SVG into any Notion,
          Slack, Confluence, or README surface —{" "}
          <Link
            href="/badge"
            className="underline underline-offset-2"
          >
            full guide in the badge gallery
          </Link>
          .
        </p>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          4. (Optional) AI explanations &amp; /ask
        </h2>
        <p className="text-sm text-neutral-600">
          Set <code>LITMUS_ANTHROPIC_API_KEY</code> to unlock{" "}
          <Link href="/ask" className="underline underline-offset-2">
            /ask
          </Link>{" "}
          and the &ldquo;Why did this fail?&rdquo; panel. Feature is opt-in
          per install — no key, no AI calls.
        </p>
      </section>

      <aside className="rounded-xl border border-neutral-200 bg-neutral-50 p-4 text-sm text-neutral-700">
        <div className="font-semibold">Single-tenant by default</div>
        <p className="mt-1 text-neutral-600">
          OSS ships single-org, no SSO. Multi-tenancy, orgs, SSO, and billing
          land in v0.5 (Cloud). The OSS UI hides the org switcher by design.
        </p>
      </aside>

      <div className="flex flex-wrap items-center gap-3 pt-4">
        <Link
          href="/install/slack"
          className="text-sm text-neutral-600 hover:text-neutral-900"
        >
          Next: plug into Slack &rarr;
        </Link>
      </div>
    </article>
  );
}
