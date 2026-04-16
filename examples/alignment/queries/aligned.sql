-- The aligned "Monthly Revenue" query — derived directly from
-- metrics/monthly_revenue.metric and approved by all three teams.
--
-- Every filter in this query traces back to a line in the Given block.
-- If you want to change the definition, edit the .metric file first,
-- get sign-off, then update this SQL to match. Not the other way around.
--
-- Expected result against the seed data: $3,250,000

WITH period_orders AS (
    SELECT
        order_id,
        amount
    FROM orders
    WHERE status = 'completed'                             -- "status is 'completed'"
      AND amount IS NOT NULL                                -- "amount is not null"
      AND order_date >= DATE '2026-03-01'                   -- "current calendar month"
      AND order_date <  DATE '2026-04-01'
),
period_refunds AS (
    SELECT r.refund_amount AS amt
    FROM refunds r
    JOIN period_orders p USING (order_id)
)
SELECT
    ROUND(
        (SELECT SUM(amount) FROM period_orders)
        - COALESCE((SELECT SUM(amt) FROM period_refunds), 0),
        2
    ) AS monthly_revenue;
