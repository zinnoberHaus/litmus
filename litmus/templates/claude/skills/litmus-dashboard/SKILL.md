---
name: litmus-dashboard
description: Scaffold a new Streamlit dashboard for a specific stakeholder. Wires it to existing mart tables and surfaces the data-test status in the header. Use after litmus-transform has produced a mart table the dashboard will read from.
---

# /litmus-dashboard

Build a Streamlit dashboard.

## How to invoke

```
/litmus-dashboard <name>
/litmus-dashboard founder_weekly
/litmus-dashboard sales_pipeline --from mart_deals,mart_pipeline_velocity
```

## Workflow you execute

1. **Confirm the audience.** Who reads this, how often, what decision does it inform? If the user can't answer, ask. Dashboards nobody opens are worse than no dashboard.
2. **Confirm the mart tables exist.** If the user asks for "founder weekly" and the only relevant data is `raw_*`, escalate to `data-architect` + `pipeline-builder` — **do not build a dashboard on raw tables.**
3. **Scaffold the file** at `dashboards/<name>.py`:
   ```python
   from __future__ import annotations

   import streamlit as st
   import duckdb
   from litmus.dashboards import freshness_header, data_test_banner

   st.set_page_config(page_title="<Name>", layout="wide")
   st.title("<Name>")
   freshness_header(["mart_daily_revenue", "mart_customer_ltv"])
   data_test_banner(["mart_daily_revenue", "mart_customer_ltv"])

   @st.cache_data(ttl=900)
   def load_revenue():
       con = duckdb.connect("./data/warehouse.duckdb", read_only=True)
       return con.execute("SELECT day, revenue FROM mart_daily_revenue ORDER BY day").df()

   df = load_revenue()
   st.line_chart(df.set_index("day")["revenue"])
   ```
4. **Run it** — `streamlit run dashboards/<name>.py`. Confirm it loads.
5. **Hand off to `code-reviewer`.** They gate on: `mart_*` only, `@st.cache_data` present, freshness header present, data-test status surfaced, file named for the audience.
6. **Tell `ops-pilot`** — "new dashboard at `dashboards/<name>.py`, served at <url>. Add it to the Notion project page."

## Conventions

- File is named for the audience (`founder_weekly.py`, `sales_pipeline.py`), not generic (`dashboard.py`, `main.py`).
- Reads only from `mart_*` tables. Raw-table reads are a `code-reviewer` blocker.
- Every query function has `@st.cache_data(ttl=900)`. The warehouse is not a transactional DB; re-running aggregations on every page reload is a perf-disaster.
- Header always shows freshness ("data through <timestamp>") and any failing data test as a banner.
- One question per chart. If you need three, make three charts. Don't pack four lines on one axis.
- Default to text + tables. Charts are for trends over time; everything else is better as a number or a table.

## Failure modes

- **Underlying mart table missing** — escalate to `data-architect`.
- **Query too slow even with cache** — escalate to `data-architect`; the mart table is probably not pre-aggregated enough.
- **User wants a chart for a one-off question** — gently push back: "want me to answer this once with a SQL query, or build a recurring dashboard?" Don't build dashboards for one-time questions.
