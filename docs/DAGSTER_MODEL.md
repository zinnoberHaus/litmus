# The Dagster Model: OSS/Cloud Split Applied to Litmus

Reference notes on how Dagster (by Dagster Labs, formerly Elementl) splits its Apache-licensed open source project from its hosted commercial product, Dagster+. Collected April 2026 from Dagster's pricing page, docs, GitHub repo, blog, and community threads. Used as a design reference for Litmus's own OSS-to-SaaS path.

## 1. License

Dagster is licensed under **Apache License 2.0** — the actual `LICENSE` file in `dagster-io/dagster` is the standard Apache 2.0 text, copyright Dagster Labs, Inc. No additional Commons Clause, BSL, SSPL, or Elastic-style restriction. This is a genuinely permissive OSS license.

What that permits, concretely:
- Anyone (including AWS, Databricks, Snowflake) can fork Dagster and run it commercially as a hosted service.
- Users can self-host for internal production use with no royalty, disclosure, or contribution obligation.
- Derivative works can be closed-source; only the NOTICE and attribution requirements bind.
- There is no "you can't use this to build a competing service" clause. Dagster Labs is deliberately betting on execution velocity and network effects, not licensing as a moat.

Contrast with MongoDB (SSPL), CockroachDB (BSL), Elastic (SSPL/Elastic License) — all of which changed their license specifically to stop hyperscaler re-hosting. Dagster has not. This is a strategic choice that informs everything below.

## 2. Feature Split

Dagster does not publish an official feature matrix — community members have been asking for one since October 2024 (GitHub Discussion #25313) and June 2025 with no response. What follows is reconstructed from the docs, the "When to move from OSS to Dagster+" blog, the "Open Core Business Model" blog, and the Dagster+ marketing pages.

| Feature | OSS | Dagster+ |
|---|---|---|
| Orchestration engine (asset graph, ops, jobs) | Yes | Yes (same code) |
| Asset graph UI / Webserver (formerly Dagit) | Yes, self-hosted | Yes, hosted |
| Scheduler (cron) | Yes (via daemon) | Yes |
| Sensors (event-driven triggers) | Yes | Yes |
| Partitioned assets | Yes | Yes |
| Backfills | Yes | Yes |
| Run history storage (Postgres/SQLite) | Yes, user-operated | Managed |
| Basic asset lineage | Yes | Yes |
| GraphQL API | Yes | Yes |
| Python APIs & integrations | Yes | Yes |
| Branch Deployments (ephemeral PR envs) | No | Cloud-only |
| Insights (cost/runtime trends dashboard) | No | Cloud-only |
| Column-level lineage in UI | No | Cloud-only |
| Asset Catalog (search-first experience) | No | Cloud-only |
| Granular alerts (Slack/Teams/PagerDuty, freshness SLAs) | No | Cloud-only |
| Serverless execution | No | Cloud-only |
| Hybrid deployment (managed control plane, user compute) | No | Cloud-only |
| Multi-tenant / multi-deployment control plane | No | Cloud-only |
| SSO (Okta, Azure AD, Ping) | No | Cloud-only |
| SAML integration | No | Enterprise tier only |
| SCIM user provisioning | No | Cloud-only |
| RBAC (Viewer/Editor/Admin) | No | Starter tier and up |
| Audit log | No | Enterprise tier only |
| Teams feature (team-scoped permissions) | No | Enterprise tier only |
| Code location management (multi-repo) | Manual via workspace.yaml | Managed, click-to-add |
| 99.9% uptime SLA | N/A | Cloud-only |
| EU data residency | N/A | Cloud-only |

Note: the core **orchestration engine and the web UI are fully in OSS**. This is the most important line. Dagster did not pull the UI behind the paywall the way some open-core vendors have.

## 3. Cloud Pricing (as of April 2026, with May 1, 2026 changes flagged)

Source: https://dagster.io/pricing.

**Current (until May 1, 2026):**
- **Solo**: $10/mo + $0.040/credit. 1 user, 1 code location, 1 deployment. 30-day free trial.
- **Starter**: $100/mo + $0.035/credit. Up to 3 users, 5 code locations, 1 deployment. Adds Catalog Search, RBAC.
- **Pro**: Contact sales. Unlimited code locations and deployments. Adds Insights, column-level lineage, priority support, uptime SLA.

**New structure (effective May 1, 2026):**
- **Solo**: $120/mo, includes 7,500 credits. Overage on top.
- **Starter**: $1,200/mo, includes 30,000 credits.
- **Enterprise**: Contact sales. Adds Teams, Audit Logs, SAML.

**Serverless compute**: flat $0.01 per compute-minute across all tiers, on top of the plan cost. This is where Dagster monetizes runtime.

"Credits" roughly map to orchestration events (per-op/per-step accounting). This is the controversial part — a simple job with 8 ops running every 5 minutes consumes ~2,304 credits/day, which a Medium writeup translated to ~$1,173/mo on Starter. High-frequency or highly-decomposed jobs get expensive fast.

## 4. Monetization Mechanics

**Free tier:** OSS is the free tier. There is no free Dagster+ tier — the cheapest paid plan is the $10/mo Solo (rising to $120/mo in May 2026). The 30-day Dagster+ trial is the only free taste of Cloud.

**Conversion wedge:** operational pain. The OSS install requires running the webserver, daemon, Postgres, code servers, and their orchestration yourself. Teams hit the wall when they need (a) Branch Deployments for CI/CD of data pipelines, (b) a shared instance for the team without each dev running their own, (c) alerts and SLAs, or (d) SSO because their security team won't let a new tool in without it.

**Model: hybrid — seat-capped plans + consumption.** Unlike Snowflake (pure consumption) or Linear (pure seat), Dagster bundles:
1. A base monthly fee with seat and code-location caps that force plan upgrades as the team grows.
2. Credits (orchestration events) that scale with workload — the "you use it more, you pay more" axis.
3. Serverless compute-minutes as a separate line, metered.

**Are they selling enterprise features or real product capabilities?** Both, and this is where Dagster is aggressive:
- *Classic enterprise gates* (SSO, SAML, SCIM, RBAC, audit log) — all Cloud-only, following the standard open-core playbook.
- *Product capabilities that most would consider core orchestration* are also Cloud-only: Branch Deployments, Insights, the Asset Catalog, granular alerts, column-level lineage. These are the ones that draw community complaints. A self-hoster does not get PR-based environment testing or a freshness-SLA alerting system — they would build those themselves.

## 5. OSS Adoption Trajectory

- **GitHub**: ~15,300 stars as of April 2026 (grew from single-digit thousands in 2020 to ~15k over six years — steady, not viral).
- **PyPI**: the `dagster` package has ~5.2M downloads/month and ~77M all-time. `dagster-webserver` shows ~161k weekly. Active release cadence (1.13.0 shipped April 9, 2026).
- **Funding**: Dagster Labs (née Elementl) raised a $33M Series B in May 2023 led by Georgian, with Sequoia, Index, Amplify, 8VC, Human Capital. Total raised ~$47M across three rounds. ARR not disclosed.
- **Named production users**: DoorDash, Flexport, Aritzia.

**How they bootstrapped OSS → Cloud:** Dagster spent 2018–2021 building the OSS engine and API surface (asset-centric orchestration, pitched as a correction of Airflow's task-centric model). Cloud launched in 2022. They did not gate the UI, the scheduler, or the sensors — these are standard OSS. Cloud was sold as "the managed control plane you'd otherwise build yourself" plus team/enterprise features. Growth came from analytics engineers evaluating Dagster as a dbt partner, then pulling it into their stack; Cloud adoption followed once teams outgrew single-dev local deployments.

## 6. What They Kept Proprietary That's Surprising

The critical observation for Litmus: **Dagster kept the UI open**. The full webserver, GraphQL API, asset graph visualization, run viewer, and job launcher are in OSS. You can self-host a production Dagster deployment and never pay a cent.

This is the less-common open-core path. The alternative, taken by GitLab (Ultimate tier), Sentry (business features), and previously by Grafana (Enterprise UI), is to keep a community UI but gate UI features behind a Cloud/Enterprise build. Dagster did not do this for the core UI.

What they *did* keep proprietary is narrower and more strategic:
1. **The multi-tenant control plane itself.** Dagster+ is not the UI — it's the hosted service that runs many users' webservers, metadata stores, and daemons. That operational system is closed.
2. **Branch Deployments.** Arguably the most-requested "bring to OSS" feature. They keep it closed because it's the single highest-value CI/CD capability, and it requires the multi-tenant control plane to work cleanly anyway.
3. **Insights.** The cost/runtime analytics dashboard. Closed because it requires a long-running time-series store that OSS self-hosters wouldn't run.
4. **Catalog + column-level lineage.** The search-first catalog UI and column lineage visualization are Cloud-only, even though the lineage *data* is emitted by OSS.
5. **Alerting.** Freshness-policy alerts, Slack/PagerDuty routing — Cloud-only.

The pattern: **OSS gets the engine and the single-instance UI; Cloud gets the things that require a long-running service (multi-tenant state, time-series analytics, alerting) or are inherently enterprise-shaped (SSO, audit, RBAC, SAML).**

They explicitly frame this as the "three-complexity" split in their Open Core Business Model post: *Application complexity* (OSS, forever), *Operational complexity* (Cloud), *Enterprise complexity* (Cloud). Founder Nick Schrock is quoted: "This in-process framework, its core abstractions, the APIs to interact with it will forever and always be open source."

## 7. Community Friction Points

Three concrete, cited complaints:

1. **No public OSS-vs-Cloud feature matrix.** GitHub Discussion [#25313](https://github.com/dagster-io/dagster/discussions/25313) opened October 2024 explicitly asks for a comparison page like Prefect's. It sat unanswered for 8+ months. Users repeatedly note they cannot evaluate whether to adopt without knowing what they're giving up.

2. **Credit pricing makes high-frequency workloads unaffordable.** GitHub Discussion [#26622](https://github.com/dagster-io/dagster/discussions/26622) ("Evaluating Dagster Open Source for Enterprise-Scale Near Real-Time Workloads") details a 600-table Data Vault refreshing every 5 minutes and calls Dagster+ "financially unfeasible" at that cadence. The Medium post ["The Problem with Dagster"](https://medium.com/@woody1193/the-problem-with-dagster-5683ea50cd9d) works the math: an 8-op job every 5 minutes = ~2,304 credits/day = ~$1,173-$2,464/mo, and notes the perverse incentive to collapse ops to save cost, which destroys the asset-graph visualization that was the reason to adopt Dagster.

3. **"OSS might be a gateway, not a destination."** The same #26622 thread and multiple Reddit/HN threads voice the fear that Cloud-only features will keep expanding while OSS stagnates. Specific worry: new features will ship Cloud-first, and when equivalent OSS capabilities are deprecated or never built, teams get squeezed. Dagster has not publicly committed to feature parity for any non-enterprise capability, which fuels this.

## 8. Litmus-Applicable Lessons

Litmus is smaller in scope: a metric-definition DSL + data-trust check runner, not a full orchestrator. Still, the Dagster playbook is substantially transferable. Mapping:

**What translates:**
- **Apache 2.0, no fork-blocker clause.** Litmus is already pitched as a PLG wedge for analytics engineers; licensing permissiveness is the point. Don't reach for BSL/SSPL — the risk of a hyperscaler re-hosting a narrow metric tool is low, and the cost in community trust is high.
- **Keep the CLI, parser, `MetricSpec`, check runner, and all reporters (console/JSON/HTML/Markdown) in OSS forever.** These are Litmus's "application complexity" layer — equivalent to Dagster's engine + single-instance UI. If Litmus ever gates the shareable HTML dashboard (`litmus share`), it should match Dagster's mistake profile, not its wins.
- **Monetize the long-running service, not the library.** Dagster's clearest-earned money is multi-tenant control plane + time-series (Insights) + alerting. For Litmus the analog is: a hosted service that stores check history across runs and teams, exposes trend dashboards, routes alerts, and holds the SQLite-or-equivalent `HistoryStore` centrally. The current `~/.litmus/history.db` sqlite file is the exact thing that naturally becomes a hosted product.
- **Gate enterprise features the boring way.** SSO, SAML, SCIM, audit log, RBAC — all safe to gate behind Cloud/Enterprise. Nobody complains about this split; it's priced into expectations.
- **Consumption + seats hybrid.** A pure seat model undervalues high-volume check runs; pure consumption scares small teams. Dagster's "base fee with included credits + overage + separate compute meter" is a reasonable template. For Litmus, "check runs" or "metrics monitored" are the natural meter.

**What does NOT translate:**
- **Branch Deployments.** Dagster's flagship Cloud feature depends on orchestrating infrastructure per PR. Litmus doesn't have infrastructure to spin up — running checks against a branch's `.metric` files in CI is already free in OSS via the GitHub Action. Don't try to gate a PR-preview experience; it's already solved.
- **Column-level lineage UI.** Dagster gates this because it requires a catalog backend. Litmus deliberately does not do lineage — stay out.
- **Credits-per-op pricing.** Dagster's credit model is the single loudest complaint. For Litmus, "per check run" is cleaner and maps to real value (one run = one trust verdict). Avoid micro-metering internal steps.
- **Hiding the UI behind Cloud.** Litmus's HTML reporter and `litmus share` dashboard should stay OSS. The moment the business-owner audience can't see results without a login, the adoption wedge collapses. The wedge requires engineers being able to point stakeholders at a URL with zero friction.

**Non-obvious lesson — publish the matrix early.** Dagster's single biggest self-inflicted wound is refusing to publish OSS vs Cloud comparison. Litmus should ship a public feature matrix on day one of launching a hosted offering. Transparency is a wedge advantage against Dagster.

**Non-obvious lesson — the "three-complexity" frame is a useful internal discipline.** Before gating any feature, ask: does this live in the library (OSS), the service (Cloud), or the enterprise contract (Cloud)? If it's library-level, it stays open. That single rule would have prevented most of Dagster's friction points.

## Sources

- Dagster pricing: https://dagster.io/pricing
- Dagster+ May 2026 pricing update: https://support.dagster.io/articles/3171123463-dagster-solo-and-starter-pricing-updates-may-2026
- Open Core Business Model blog: https://dagster.io/blog/open-core-business-model-dagster
- When to Move from OSS to Dagster+: https://dagster.io/blog/when-to-move-from-dagster-oss-to-dagster
- OSS vs Dagster+ GitHub discussion: https://github.com/dagster-io/dagster/discussions/25313
- Near-real-time pricing complaint: https://github.com/dagster-io/dagster/discussions/26622
- "The Problem with Dagster" (Ryan Wood): https://medium.com/@woody1193/the-problem-with-dagster-5683ea50cd9d
- Dagster LICENSE: https://github.com/dagster-io/dagster/blob/master/LICENSE
- Dagster+ docs: https://docs.dagster.io/deployment/dagster-plus
- PyPI stats: https://clickpy.clickhouse.com/dashboard/dagster
- Series B funding: https://techcrunch.com/2023/05/24/elementl-raises-33m-series-b-for-its-data-orchestration-platform-based-on-dagster/
