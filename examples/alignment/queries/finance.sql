-- Finance team's "Monthly Revenue" query.
--
-- How they explain it in email:
--   "Only invoiced and paid orders count as revenue. We only report in
--    USD — if a conversion isn't recorded, we exclude the row.
--    Net of refunds. Current calendar month."
--
-- What diverges from engineering/analytics:
--   - Requires both invoiced_at AND paid_at to be non-null.
--   - Requires amount_usd to be non-null (no "fallback to local").
--   - Calendar month strict.
--
-- Expected result against the seed data: $2,750,000

WITH period_orders AS (
    SELECT
        order_id,
        amount
    FROM orders
    WHERE status = 'completed'
      AND invoiced_at IS NOT NULL
      AND paid_at     IS NOT NULL
      AND amount      IS NOT NULL
      AND order_date >= DATE '2026-03-01'
      AND order_date <  DATE '2026-04-01'
),
period_refunds AS (
    SELECT
        r.order_id,
        r.refund_amount AS amt
    FROM refunds r
    JOIN period_orders p USING (order_id)
)
SELECT
    (SELECT SUM(amount) FROM period_orders) -
    COALESCE((SELECT SUM(amt) FROM period_refunds), 0) AS monthly_revenue;
