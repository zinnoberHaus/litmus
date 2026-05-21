-- mart_revenue_by_market: revenue + customer count per market.
-- Source: raw_transactions JOIN raw_markets. Refresh: daily. Idempotent.

CREATE OR REPLACE TABLE mart_revenue_by_market AS
SELECT
    m.market_id,
    m.name AS market_name,
    m.region,
    m.tier,
    COUNT(DISTINCT t.customer_id) AS unique_customers,
    COUNT(t.transaction_id) AS transaction_count,
    SUM(CASE WHEN t.status = 'paid' THEN t.amount ELSE 0 END) AS revenue,
    SUM(CASE WHEN t.status = 'refunded' THEN t.amount ELSE 0 END) AS refunds,
    CURRENT_TIMESTAMP AS updated_at
FROM raw_markets m
LEFT JOIN raw_transactions t USING (market_id)
GROUP BY m.market_id, m.name, m.region, m.tier
ORDER BY revenue DESC;
