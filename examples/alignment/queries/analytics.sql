-- Analytics team's "Monthly Revenue" query.
--
-- How they explain it in Slack:
--   "Completed orders, net of refunds. Rolling 30 days
--    (that's what our dashboard shows)."
--
-- What diverges from finance/engineering:
--   - "Rolling 30 days" picks up early April — finance and engineering
--     use calendar month and exclude those.
--   - Non-USD orders are counted at local amount if USD conversion is
--     missing — analytics' dashboard is "good enough" tolerant.
--   - Refunds are subtracted (net revenue).
--
-- Expected result against the seed data: $3,550,000

WITH period_orders AS (
    SELECT
        order_id,
        COALESCE(amount, amount_local) AS amt
    FROM orders
    WHERE status = 'completed'
      AND order_date >= CURRENT_DATE - INTERVAL 30 DAY
),
period_refunds AS (
    SELECT
        r.order_id,
        r.refund_amount AS amt
    FROM refunds r
    JOIN period_orders p USING (order_id)
)
SELECT
    (SELECT SUM(amt) FROM period_orders) -
    COALESCE((SELECT SUM(amt) FROM period_refunds), 0) AS monthly_revenue;
