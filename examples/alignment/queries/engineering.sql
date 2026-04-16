-- Engineering team's "Monthly Revenue" query.
--
-- How they explain it in Slack:
--   "Any order that isn't cancelled. Gross amount (before refunds).
--    Calendar month."
--
-- What this silently includes:
--   - Pending orders (not yet completed)
--   - Non-USD orders at their local amount (no conversion)
--   - Refunded amounts still counted in the total
--
-- Expected result against the seed data: $4,400,000

SELECT
    SUM(
        CASE
            WHEN amount IS NOT NULL THEN amount
            ELSE amount_local
        END
    ) AS monthly_revenue
FROM orders
WHERE status != 'cancelled'
  AND order_date >= DATE '2026-03-01'
  AND order_date <  DATE '2026-04-01';
