# Badge examples

Visual-QA assets for the Litmus embed badge. Open `index.html` in a browser
to see every size × status × style combination rendered inline — the same
SVG output your Litmus server ships from `GET /embed/<token>/badge.svg`.

## Files

- `index.html` — visual grid of every badge variant. Self-contained, no
  server required. Use it when you're tweaking `litmus_api/embed_svg.py`
  to eyeball the changes before running the Next.js UI.
- `snippets.md` — copy-paste snippets for each platform (GitHub README,
  Notion, Slack, Confluence, email). Keep this in sync with
  [`docs/badges.md`](../../docs/badges.md).

## Regenerating the grid

The grid is hand-rendered in HTML so we don't need to run the FastAPI server
to preview it — but the SVGs mirror what the server actually emits. If you
change the server renderer, re-run the visual check:

```bash
# Start the API locally
pip install 'litmus-data[server]'
uvicorn litmus_api.main:app

# Pull a badge in each variant and diff against the checked-in fixtures
for size in small medium large; do
  curl -s "http://localhost:8000/embed/lme_demo/badge.svg?size=$size" \
    > "fixtures/${size}.svg"
done
```

The server-rendered output should match the HTML grid byte-for-byte when
`LITMUS_PUBLIC_URL` is unset.
