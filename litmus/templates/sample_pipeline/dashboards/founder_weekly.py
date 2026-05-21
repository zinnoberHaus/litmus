"""Founder weekly dashboard — what the CEO checks on Monday morning.

Reads only from mart_* tables. Caches every query. Surfaces Litmus trust
status in the header so stale data is impossible to miss.

Backed by the customers -> markets -> transactions ontology that ships
with Litmus's sample pipeline.
"""

from __future__ import annotations

import os

import duckdb
import streamlit as st

from litmus.dashboards import freshness_header, trust_banner

WAREHOUSE = os.environ.get(
    "LITMUS_WAREHOUSE_URL", "duckdb:///./data/warehouse.duckdb"
).replace("duckdb:///", "").replace("duckdb://", "")

MART_TABLES = ["mart_daily_revenue", "mart_customer_ltv", "mart_revenue_by_market"]

st.set_page_config(page_title="Founder Weekly", layout="wide")
st.title("Founder Weekly")
freshness_header(MART_TABLES)
trust_banner(MART_TABLES)


@st.cache_data(ttl=900)
def daily_revenue():
    con = duckdb.connect(WAREHOUSE, read_only=True)
    return con.execute(
        "SELECT day, revenue, transaction_count FROM mart_daily_revenue ORDER BY day"
    ).df()


@st.cache_data(ttl=900)
def revenue_by_market():
    con = duckdb.connect(WAREHOUSE, read_only=True)
    return con.execute(
        "SELECT market_name, region, tier, unique_customers, transaction_count, "
        "revenue FROM mart_revenue_by_market ORDER BY revenue DESC"
    ).df()


@st.cache_data(ttl=900)
def top_customers(limit: int = 10):
    con = duckdb.connect(WAREHOUSE, read_only=True)
    return con.execute(
        "SELECT name, country, primary_market, lifetime_revenue, lifetime_transactions "
        "FROM mart_customer_ltv ORDER BY lifetime_revenue DESC LIMIT ?",
        [limit],
    ).df()


revenue_df = daily_revenue()
markets_df = revenue_by_market()
customers_df = top_customers()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total revenue", f"${revenue_df['revenue'].sum():,.0f}")
col2.metric("Total transactions", f"{revenue_df['transaction_count'].sum():,}")
col3.metric("Active markets", f"{len(markets_df[markets_df['revenue'] > 0])}")
col4.metric(
    "Avg daily revenue",
    f"${revenue_df['revenue'].mean():,.0f}" if len(revenue_df) else "$0",
)

st.subheader("Revenue trend")
if len(revenue_df):
    st.line_chart(revenue_df.set_index("day")["revenue"])
else:
    st.info("No revenue rows yet — run `litmus demo` to load sample data.")

left, right = st.columns(2)

with left:
    st.subheader("Revenue by market")
    if len(markets_df):
        st.bar_chart(markets_df.set_index("market_name")["revenue"])
        st.dataframe(
            markets_df[["market_name", "tier", "unique_customers", "revenue"]],
            hide_index=True,
            use_container_width=True,
        )

with right:
    st.subheader("Top customers")
    st.dataframe(customers_df, hide_index=True, use_container_width=True)
