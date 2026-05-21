"""Founder weekly dashboard — what the CEO checks on Monday morning.

Reads only from mart_* tables (per the analyst conventions in
.claude/agents/analyst.md). Caches every query. Surfaces Litmus trust
status in the header so stale data is impossible to miss.
"""

from __future__ import annotations

import os

import duckdb
import streamlit as st

from litmus.dashboards import freshness_header, trust_banner

WAREHOUSE = os.environ.get(
    "LITMUS_WAREHOUSE_URL", "duckdb:///./data/warehouse.duckdb"
).replace("duckdb:///", "").replace("duckdb://", "")

MART_TABLES = ["mart_daily_revenue", "mart_customer_ltv"]

st.set_page_config(page_title="Founder Weekly", layout="wide")
st.title("Founder Weekly")
freshness_header(MART_TABLES)
trust_banner(MART_TABLES)


@st.cache_data(ttl=900)
def daily_revenue():
    con = duckdb.connect(WAREHOUSE, read_only=True)
    return con.execute(
        "SELECT day, revenue, order_count FROM mart_daily_revenue ORDER BY day"
    ).df()


@st.cache_data(ttl=900)
def top_customers(limit: int = 10):
    con = duckdb.connect(WAREHOUSE, read_only=True)
    return con.execute(
        "SELECT name, country, lifetime_revenue, lifetime_orders "
        "FROM mart_customer_ltv ORDER BY lifetime_revenue DESC LIMIT ?",
        [limit],
    ).df()


revenue_df = daily_revenue()
customers_df = top_customers()

col1, col2, col3 = st.columns(3)
col1.metric("Total revenue", f"${revenue_df['revenue'].sum():,.0f}")
col2.metric("Total orders", f"{revenue_df['order_count'].sum():,}")
col3.metric(
    "Avg daily revenue",
    f"${revenue_df['revenue'].mean():,.0f}" if len(revenue_df) else "$0",
)

st.subheader("Revenue trend")
if len(revenue_df):
    st.line_chart(revenue_df.set_index("day")["revenue"])
else:
    st.info("No revenue rows yet — run `litmus demo` to load sample data.")

st.subheader("Top 10 customers by lifetime revenue")
st.dataframe(customers_df, hide_index=True, use_container_width=True)
