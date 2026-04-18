# Slack integration — sign-off workflow

> **Status:** v0.3 MVP. Webhook-only posting, signature-verified inbound
> routes, approve/reject buttons on metric revisions. Full Slack App
> (OAuth + Marketplace) is deferred to v0.4 — see `REFACTOR_BLUEPRINT.md`
> §2.3 for the reasoning.

Litmus can post a sign-off prompt to Slack every time a `MetricRevision` is
written. A PM clicks **Approve** or **Reject**; the revision row in the
catalog records who acted and when, and the UI renders a
`<SignoffChip>` next to the revision.

The integration ships without any new Python dependencies — outbound posts
use `urllib.request`, inbound requests are HMAC-verified the same way we
verify GitHub webhooks.

---

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `LITMUS_SLACK_SIGNING_SECRET` | Yes (for inbound) | HMAC key Slack signs every slash command / interaction / event with. An unset secret fails closed with 401 — never silently accepts. |
| `LITMUS_SLACK_WEBHOOK_URL` | Yes (for outbound) | Incoming webhook URL Litmus POSTs sign-off prompts to. If unset, the server logs `"Slack webhook URL not configured"` and the feature is silently disabled. |
| `LITMUS_SLACK_DEFAULT_CHANNEL` | Optional | Fallback channel id (e.g. `C0123…`) passed in the payload when the webhook URL is one that supports channel overrides. |
| `LITMUS_SLACK_BOT_TOKEN` | Optional | Required **only** if you want the "update the original message after a button press" UX (`chat.update`). Without it, the button click is still recorded but the original Slack message keeps its buttons. |
| `LITMUS_SLACK_SIGNOFF_ALL` | Optional | `true` → every upsert triggers a sign-off prompt. Default (`false`) requires a per-upsert opt-in via `MetricUpsertIn.signoff_required`. |
| `LITMUS_SLACK_BOT_USER_AGENT` | Optional | Custom `User-Agent` header on outbound POSTs. Defaults to `litmus-slack/0.3`. |

All three are read lazily inside the Slack routes — no secret access at
import time. Rotating a secret is a `kubectl set env` and a restart, no
code change needed.

---

## Endpoints

All mounted under `/api/v1/slack/`.

| Method + path | Purpose |
|---|---|
| `POST /api/v1/slack/events` | Slack Events API callback. Handles `url_verification` handshakes. `app_mention` / `message` events are stubbed (200 OK, logged) — task #54 fills them in with the `/ask` logic. |
| `POST /api/v1/slack/commands` | Slash command handler. Dispatches `/litmus-signoff pending` and `/litmus-signoff metric <slug>`. |
| `POST /api/v1/slack/interactions` | Block Kit button clicks. Handles `litmus_signoff_approve` and `litmus_signoff_reject` action ids. |
| `POST /api/v1/slack/signoff/request` | Internal — posts a sign-off prompt for an existing revision id. Used by the UI "request sign-off" affordance. Authenticated via the normal `current_org` dependency. |

Every inbound endpoint verifies Slack's `X-Slack-Signature` (HMAC-SHA256 of
`v0:{timestamp}:{body}`) and rejects timestamps more than 5 minutes old.

---

## Slack app setup (workspace admin)

The integration needs *one* Slack app in *your* workspace. No Slack
Marketplace involvement in v0.3.

1. **Create an app** at <https://api.slack.com/apps> → **From scratch**.
2. **Incoming webhook** — in *Features* → *Incoming Webhooks* → turn on
   and click **Add New Webhook to Workspace**. Pick the channel the
   sign-off prompts should land in. Copy the URL and set it as
   `LITMUS_SLACK_WEBHOOK_URL` on the Litmus server.
3. **Signing secret** — in *Basic Information* → *App Credentials*, copy
   the **Signing Secret** and set it as `LITMUS_SLACK_SIGNING_SECRET`.
4. **Slash command** — in *Features* → *Slash Commands* → **Create New
   Command**:
   - Command: `/litmus-signoff`
   - Request URL: `https://<your-litmus-host>/api/v1/slack/commands`
   - Short description: `List pending metric sign-offs, or request one`
   - Usage hint: `pending | metric <slug>`
5. **Interactivity** — in *Features* → *Interactivity & Shortcuts* → turn on
   and set the Request URL to
   `https://<your-litmus-host>/api/v1/slack/interactions`.
6. **Events API** (optional for v0.3, prerequisite for #54 AI Q&A) —
   *Features* → *Event Subscriptions* → turn on, Request URL
   `https://<your-litmus-host>/api/v1/slack/events`. Slack will POST a
   `url_verification` challenge which Litmus echoes back automatically.
   Subscribe to `app_mention` and `message.channels` bot events once #54
   ships; for v0.3 you can skip this section entirely.
7. **Install the app** to the workspace (*Install App*). Grab the bot
   token (starts with `xoxb-`) and — only if you want "button click updates
   the original message" — set it as `LITMUS_SLACK_BOT_TOKEN`.

---

## Opting a revision into sign-off

Three ways:

1. **Per-upsert flag.** POST `/api/v1/metrics` with
   `{"signoff_required": true, "spec_text": "..."}`. The UI uses this when
   an owner manually flips the toggle on a metric.
2. **Ops kill-switch.** Set `LITMUS_SLACK_SIGNOFF_ALL=true` on the server.
   Every upsert fires a prompt. Useful for pilot deployments before your
   team has audited which metrics genuinely need PM approval.
3. **Slash command.** `/litmus-signoff metric monthly_revenue` from Slack
   marks the latest revision as `pending` and posts a fresh prompt.

Once Architect adds `signoff_required` to `MetricSpec` (see
`REFACTOR_BLUEPRINT.md` §2.3), a fourth path lights up: declaring
`signoff_required: true` in the `.metric` / YAML header. The code hook is
already in place — `_signoff_required_for` in `litmus_api/routes/metrics.py`
is the single function to extend.

---

## UX flow

```
1. Engineer pushes a .metric change.
2. GitHub webhook → _perform_upsert writes a new MetricRevision.
3. Litmus POSTs to LITMUS_SLACK_WEBHOOK_URL with a Block Kit message:
     ┌─────────────────────────────────────────┐
     │ Sign-off requested: Monthly Revenue     │
     │ Revision 4a2f… of `monthly_revenue`     │
     │ [ Approve ]  [ Reject ]                 │
     └─────────────────────────────────────────┘
4. PM clicks Approve.
5. Slack POSTs the interaction to /api/v1/slack/interactions.
6. Litmus verifies signature, flips signoff_status=approved,
   records signoff_by + signoff_at, and (if bot token configured)
   edits the original message to read "✅ Approved by @alice".
7. The metric detail page shows the green <SignoffChip>.
```

---

## Manual end-to-end verification

> This section exists because our test suite mocks the outbound HTTP calls.
> Before cutting v0.3, a human must exercise the full round-trip at least
> once.

### Pre-flight

- Slack app created per "Slack app setup" above, webhook URL points at a
  test channel (e.g. `#litmus-qa`).
- Litmus server running locally with:

  ```bash
  export LITMUS_SLACK_SIGNING_SECRET=<from-slack-basic-info>
  export LITMUS_SLACK_WEBHOOK_URL=<incoming-webhook-url>
  export LITMUS_SLACK_BOT_TOKEN=<optional>
  uvicorn litmus_api.main:app
  ```

- `ngrok http 8000` (or equivalent) so Slack can reach your local server.
- Update the Request URLs in the Slack app to the `ngrok` domain.

### Steps

1. **Trigger a sign-off prompt.**

   ```bash
   curl -X POST http://localhost:8000/api/v1/metrics \
     -H 'Content-Type: application/json' \
     -d '{
       "spec_text": "Metric: QA Revenue\nSource: orders\n...",
       "slug": "qa_revenue",
       "signoff_required": true
     }'
   ```

   Expected: a Block Kit card appears in `#litmus-qa` with Approve / Reject
   buttons.

2. **Click Approve.** Expected:
   - Button click lands on `/api/v1/slack/interactions`.
   - HTTP 200.
   - `/api/v1/metrics/qa_revenue/revisions` shows the latest revision with
     `signoff_status=approved`, `signoff_by=<your-username>`,
     `signoff_at=<~now>`.
   - If `LITMUS_SLACK_BOT_TOKEN` is set, the original Slack message now
     reads `✅ Approved by @<you>` and the buttons are gone.

3. **Test the slash command.** In Slack:

   ```
   /litmus-signoff pending
   ```

   Expected: ephemeral reply "No pending sign-offs." (since we just
   approved).

   Then:

   ```
   /litmus-signoff metric qa_revenue
   ```

   Expected: in-channel reply "Sign-off requested for `qa_revenue`." and a
   fresh prompt in the configured channel.

4. **Test signature rejection.** From your laptop:

   ```bash
   curl -X POST https://<ngrok>/api/v1/slack/commands \
     -H 'Content-Type: application/x-www-form-urlencoded' \
     -H 'X-Slack-Signature: v0=bogus' \
     -H 'X-Slack-Request-Timestamp: 1' \
     -d 'command=/litmus-signoff'
   ```

   Expected: HTTP 401, no state change.

5. **Test the url_verification handshake.** In the Slack app's *Event
   Subscriptions* page, set the URL and click *Save*. Slack auto-POSTs a
   challenge. Expected: Slack shows "Verified" ✅.

---

## What's mocked in tests vs manually verified

| Scenario | Automated (`tests/test_api/test_slack.py`) | Manual |
|---|---|---|
| Signature HMAC math | ✅ | — |
| 5-minute timestamp window | ✅ | — |
| 401 on bad signature / missing secret | ✅ | ✅ (step 4) |
| `url_verification` challenge | ✅ | ✅ (step 5) |
| Slash command routing | ✅ | ✅ (step 3) |
| Button click → DB update | ✅ | ✅ (step 2) |
| `_fire_signoff_hook` on upsert | ✅ (mocked urlopen) | ✅ (step 1) |
| Slack outage doesn't break upsert | ✅ | — |
| Block Kit message actually renders in Slack | — | ✅ (step 1) |
| `chat.update` edits the original message | — | ✅ (step 2 with bot token) |

Everything in the left column runs on every PR. Everything in the right
column is a pre-release checklist item owned by whoever tags v0.3.

---

## Security notes

- HMAC comparison uses `hmac.compare_digest` — constant-time, immune to
  timing side channels.
- The signing secret lives in the env only; never logged, never persisted
  to disk, never sent to Claude (for the future `/ask` flow).
- We do NOT accept slash commands or interactions from anonymous Slack
  workspaces — `current_org` still runs on these routes so the standard
  tenant model applies.
- Slack button `value` fields carry the `MetricRevision.id` (a UUID). We
  still filter the revision lookup by `current_org.id` so a spoofed
  payload from a different workspace can't flip a revision that doesn't
  belong to the acting org.

---

## See also

- [`REFACTOR_BLUEPRINT.md`](../REFACTOR_BLUEPRINT.md) §2.3 — strategic
  choice of webhook-only vs full Slack App.
- [`docs/github-webhook.md`](github-webhook.md) — sibling pattern for the
  GitHub push ingestor (same HMAC shape, different header names).
- [`docs/ai-explanations.md`](ai-explanations.md) — the same "talk to
  Claude sparingly" philosophy that `/ask` will inherit in task #54.
