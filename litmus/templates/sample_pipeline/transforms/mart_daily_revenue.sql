-- mart_daily_revenue: total paid revenue + transaction count per day.
-- Source: raw_transactions. Refresh: daily. Idempotent.

CREATE OR REPLACE TABLE mart_daily_revenue AS
SELECT
    CAST(DATE_TRUNC('day', transacted_at) AS DATE) AS day,
    COUNT(*) AS transaction_count,
    SUM(amount) AS revenue,
    CURRENT_TIMESTAMP AS updated_at
FROM raw_transactions
WHERE status = 'paid'
GROUP BY 1
ORDER BY 1;
