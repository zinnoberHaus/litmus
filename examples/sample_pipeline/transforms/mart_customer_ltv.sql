-- mart_customer_ltv: lifetime revenue per customer, with order count and country.
-- Source: raw_orders + raw_customers. Refresh: daily. Idempotent.

CREATE OR REPLACE TABLE mart_customer_ltv AS
SELECT
    c.customer_id,
    c.name,
    c.country,
    COUNT(o.order_id) AS lifetime_orders,
    COALESCE(SUM(CASE WHEN o.status = 'paid' THEN o.amount ELSE 0 END), 0) AS lifetime_revenue,
    MAX(o.order_at) AS last_order_at,
    CURRENT_TIMESTAMP AS updated_at
FROM raw_customers c
LEFT JOIN raw_orders o USING (customer_id)
GROUP BY c.customer_id, c.name, c.country
ORDER BY lifetime_revenue DESC;
