# GitHub webhook setup

Wire your repo to a running Litmus catalog server so every push that touches a `.metric` file lands in the catalog automatically — no CI job, no manual upload.

## Prerequisites

- A Litmus catalog server (the `litmus_api` package) reachable over HTTPS from GitHub.
- Your `.metric` files live in a **public** GitHub repository. Private repos need a GitHub App OAuth flow that the open-source wedge deliberately does not ship — if you need that, open an issue and tell us about your use case.

## 1. Pick a secret

Generate a long random string — this is what GitHub will use to sign every webhook payload, and what your server will use to verify that the request really came from GitHub. 32 bytes of random is plenty:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the value. You'll paste it into two places: GitHub, and your Litmus server's environment.

## 2. Configure the Litmus server

Set `LITMUS_GITHUB_WEBHOOK_SECRET` to the value from step 1, then restart the server so it picks up the env var. The webhook route refuses every request until this is set — an unset secret returns HTTP 401, not a silent accept.

```bash
export LITMUS_GITHUB_WEBHOOK_SECRET='<paste the value here>'
uvicorn litmus_api.main:app --host 0.0.0.0 --port 8000
```

For docker-compose or Kubernetes, add `LITMUS_GITHUB_WEBHOOK_SECRET` to the container env, not to `litmus.yml`.

## 3. Add the webhook on GitHub

In your repo on GitHub:

1. Go to **Settings → Webhooks → Add webhook**.
2. Fill in:

   | Field | Value |
   |-------|-------|
   | Payload URL | `https://<your-litmus-server>/webhooks/github` |
   | Content type | `application/json` |
   | Secret | the value from step 1 |
   | SSL verification | Enable (default) |
   | Which events? | **Just the push event** |
   | Active | checked |

3. Click **Add webhook**.

## 4. Test it

Make a small edit to any `.metric` file in your repo (or add a new one) and push. In the Litmus UI, the metric should show up (or its spec should update) within a few seconds.

From GitHub's side, you can inspect the delivery under **Settings → Webhooks → Recent deliveries**. A green check means the server accepted the push; red means look at the response body.

## What the server does with a push

1. Verifies the `X-Hub-Signature-256` HMAC. Missing or wrong → HTTP 401, and GitHub marks the delivery as failed.
2. Ignores non-`push` events (returns HTTP 200 with `{"status":"ignored"}`).
3. Collects every `.metric` path in the `added` and `modified` lists of every commit in the push.
4. Fetches each file from `raw.githubusercontent.com/{repo}/{head_sha}/{path}`.
5. Upserts each file through the same code path that `POST /api/v1/metrics` uses — identical re-pushes are deduped, new spec text writes a new `MetricRevision` row, and `source_repo` / `source_path` / `source_sha` / `author` all get threaded through.
6. Returns `{"upserted": [<slugs>], "ignored": [<paths that failed to parse or fetch>]}`.

## Troubleshooting

**"Invalid signature" in GitHub's delivery log**
— The secret on GitHub and the server env var don't match. Re-paste both from the same source of truth.

**"LITMUS_GITHUB_WEBHOOK_SECRET is not configured"**
— The server process didn't pick up the env var. Restart it, and make sure the secret is exported in the same shell (or baked into the container env) that starts uvicorn.

**A path I expected to land shows up in `ignored`**
— Either the file failed to parse (check the spec against `docs/spec-language.md`) or the raw fetch 404'd (make sure the repo is public and the path is right).

**Nothing happens on push**
— Double-check the event filter on the GitHub webhook is set to "Just the push event". The default of "Just the `push` event" is what you want — if it's set to "Send me everything" you'll see `ping` and other events that the server rightly ignores.

## Related

- `CLAUDE.md` → "Webhook ingestion" for the internal contract.
- `docs/getting-started.md` for the CLI-first workflow (no server required).
