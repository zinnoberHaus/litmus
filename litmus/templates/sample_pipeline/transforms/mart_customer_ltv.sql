-- mart_customer_ltv: lifetime revenue per customer + primary market.
-- Source: raw_customers + raw_transactions + raw_markets. Refresh: daily. Idempotent.

CREATE OR REPLACE TABLE mart_customer_ltv AS
SELECT
    c.customer_id,
    c.name,
    c.country,
    m.name AS primary_market,
    m.region,
    COUNT(t.transaction_id) AS lifetime_transactions,
    COALESCE(SUM(CASE WHEN t.status = 'paid' THEN t.amount ELSE 0 END), 0) AS lifetime_revenue,
    MAX(t.transacted_at) AS last_transaction_at,
    CURRENT_TIMESTAMP AS updated_at
FROM raw_customers c
LEFT JOIN raw_markets m ON m.market_id = c.primary_market_id
LEFT JOIN raw_transactions t ON t.customer_id = c.customer_id
GROUP BY c.customer_id, c.name, c.country, m.name, m.region
ORDER BY lifetime_revenue DESC;
