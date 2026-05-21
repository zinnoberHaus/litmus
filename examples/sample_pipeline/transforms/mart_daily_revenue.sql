-- mart_daily_revenue: total paid revenue + order count per day.
-- Source: raw_orders. Refresh: daily. Idempotent (CREATE OR REPLACE).

CREATE OR REPLACE TABLE mart_daily_revenue AS
SELECT
    CAST(DATE_TRUNC('day', order_at) AS DATE) AS day,
    COUNT(*) AS order_count,
    SUM(amount) AS revenue,
    CURRENT_TIMESTAMP AS updated_at
FROM raw_orders
WHERE status = 'paid'
GROUP BY 1
ORDER BY 1;
