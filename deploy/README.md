# Deploy Litmus (self-hosted, single-tenant)

## Quick start

From the repo root:

```bash
docker compose -f deploy/docker-compose.yml up
```

- UI:  http://localhost:3000
- API: http://localhost:8000 (OpenAPI docs at `/docs`)
- DB:  Postgres on port 5432, creds `litmus / litmus`

## Pushing check results

Point the CLI at the running API:

```bash
export LITMUS_ENDPOINT=http://localhost:8000
litmus check metrics/
```

The check runs against your warehouse (using your existing `litmus.yml`),
then pushes one metric upsert + one run per `.metric` file to the hosted
catalog. The metric detail page lights up within a second.

## Embedding a trust badge

Every metric gets a permanent embed URL. Find the `embed_token` in the API
response (or the metric detail page) and embed as a plain `<img>`:

```md
![Trust](http://localhost:8000/embed/lme_...yourtoken.../badge.svg)
```

Works in Notion, Slack, GitHub READMEs, Confluence, and anywhere else that
renders inline images.

## What this compose does not include

- Redis (reserved slot for worker queue; not wired up yet)
- GitHub App webhook (Cloud-only)
- AI "why did this fail" worker (bring your own Anthropic key)
- Multi-tenant control plane (orgs/billing/SSO — Cloud-only)

Self-hosters run as one org, everyone's an admin, no billing.
