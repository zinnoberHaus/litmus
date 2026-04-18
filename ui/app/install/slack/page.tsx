import Link from "next/link";
import { CodeBlock } from "@/components/CodeBlock";

// NOTE(litmus-ui, task #53): The Slack surface is being built in parallel
// by `litmus-inspector` (task #52). Webhook-only for v0.3; full Slack App
// lands in v0.4. Commands/endpoints here reflect blueprint §2.3 Decision 3.

const ENV_VARS = `export LITMUS_SLACK_WEBHOOK_URL="https://hooks.slack.com/..."
export LITMUS_SLACK_SIGNING_SECRET="your-signing-secret"`;

const SLASH_CONFIG = `# In your Slack app > Slash Commands, add three commands:
#   /ask            →  POST https://<your-litmus-host>/api/v1/slack/commands
#   /litmus         →  POST https://<your-litmus-host>/api/v1/slack/commands
#   /litmus-approve →  POST https://<your-litmus-host>/api/v1/slack/commands`;

const YAML_SIGNOFF = `# metrics/monthly_revenue.yml
name: Monthly Recurring Revenue
signoff_required: true   # YAML-only header; DSL users can ignore
owner: finance-analytics
...`;

export default function InstallSlackPage() {
  return (
    <article className="space-y-8">
      <aside className="rounded-xl border border-violet-200 bg-violet-50/60 p-4 text-sm text-violet-900">
        <div className="font-semibold">v0.3 — webhook-only</div>
        <p className="mt-1 text-violet-800">
          The full Slack App with OAuth and Marketplace distribution lands in
          v0.4. For now, the setup below uses a webhook URL + slash-command
          config in <em>your</em> Slack workspace — ~1 day of work, works
          forever, no Marketplace gate.
        </p>
      </aside>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          1. Set the environment variables
        </h2>
        <CodeBlock caption="server env" code={ENV_VARS} />
        <p className="mt-2 text-sm text-neutral-600">
          If <code>LITMUS_SLACK_WEBHOOK_URL</code> is unset, sign-off is
          silently disabled — the server never crashes on missing Slack
          config.
        </p>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          2. Create the Slack app
        </h2>
        <ol className="list-inside list-decimal space-y-2 text-sm text-neutral-700">
          <li>
            Go to{" "}
            <a
              href="https://api.slack.com/apps"
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-2"
            >
              api.slack.com/apps
            </a>{" "}
            and create a new app <em>from scratch</em>.
          </li>
          <li>
            Enable <strong>Incoming Webhooks</strong>. Copy the webhook URL
            into <code>LITMUS_SLACK_WEBHOOK_URL</code>.
          </li>
          <li>
            Enable <strong>Interactivity &amp; Shortcuts</strong>. Point the
            request URL at{" "}
            <code>https://&lt;your-host&gt;/api/v1/slack/interactions</code>.
          </li>
          <li>
            Add the slash commands shown below. Copy the signing secret into{" "}
            <code>LITMUS_SLACK_SIGNING_SECRET</code>.
          </li>
        </ol>
        <CodeBlock caption="Slack slash-command config" code={SLASH_CONFIG} />
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          3. Turn sign-off on per metric
        </h2>
        <CodeBlock
          caption="metrics/monthly_revenue.yml"
          code={YAML_SIGNOFF}
        />
        <p className="mt-2 text-sm text-neutral-600">
          Every time that metric&rsquo;s spec changes, the engineer pushing
          the change gets a Slack block-kit message with approve / reject
          buttons. The revision stays marked <em>pending</em> until a PM
          signs off.
        </p>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">
          4. Use /ask in Slack
        </h2>
        <p className="text-sm text-neutral-600">
          Once <code>LITMUS_ANTHROPIC_API_KEY</code> is set, members of the
          workspace can type <code>/ask what was revenue last month?</code>{" "}
          in any channel. The answer posts with the trust status inline —
          same UX as the{" "}
          <Link href="/ask" className="underline underline-offset-2">
            web chat
          </Link>
          .
        </p>
      </section>

      <div className="flex flex-wrap items-center gap-3 pt-4">
        <Link
          href="/install/hosted"
          className="text-sm text-neutral-600 hover:text-neutral-900"
        >
          &larr; Self-host the server first
        </Link>
        <Link
          href="/badge"
          className="text-sm text-neutral-600 hover:text-neutral-900"
        >
          Next: embed badges &rarr;
        </Link>
      </div>
    </article>
  );
}
