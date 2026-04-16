-- Seed data for the "3 teams, 3 numbers" alignment demo.
--
-- Reporting month = March 2026. Today (for the demo) = April 2, 2026.
-- Every disagreement between the three team queries is encoded as a real
-- row here — the data isn't adversarial, it just exercises the edges
-- where each team's ad-hoc definition diverges.

DROP TABLE IF EXISTS refunds;
DROP TABLE IF EXISTS orders;

CREATE TABLE orders (
    order_id        VARCHAR PRIMARY KEY,
    customer_id     VARCHAR,
    amount_local    DECIMAL(12, 2),
    currency        VARCHAR(3),
    amount          DECIMAL(12, 2),   -- USD, converted at end-of-day rate; NULL if not yet converted
    status          VARCHAR,          -- 'completed' | 'pending' | 'cancelled'
    order_date      DATE,
    invoiced_at     TIMESTAMP,        -- NULL until finance invoices
    paid_at         TIMESTAMP,        -- NULL until customer pays
    updated_at      TIMESTAMP
);

CREATE TABLE refunds (
    refund_id       VARCHAR PRIMARY KEY,
    order_id        VARCHAR,
    refund_amount   DECIMAL(12, 2),   -- USD
    refund_date     DATE,
    updated_at      TIMESTAMP
);

-- Use CURRENT_TIMESTAMP for `updated_at` so freshness checks pass when you run
-- the demo — the seed date boundaries (March 2026) tell the alignment story,
-- but data-recency is meant to reflect "just loaded".

-- ── Core "clean" revenue: completed, invoiced, paid, USD converted ────────
-- All three teams agree on these. Total: $3,000,000.
INSERT INTO orders VALUES
  ('O-001', 'C-100', 1000000.00, 'USD', 1000000.00, 'completed', DATE '2026-03-05',
      TIMESTAMP '2026-03-06 10:00:00', TIMESTAMP '2026-03-10 14:00:00', CURRENT_TIMESTAMP),
  ('O-002', 'C-101',  800000.00, 'USD',  800000.00, 'completed', DATE '2026-03-12',
      TIMESTAMP '2026-03-13 09:00:00', TIMESTAMP '2026-03-18 16:30:00', CURRENT_TIMESTAMP),
  ('O-003', 'C-102', 1200000.00, 'USD', 1200000.00, 'completed', DATE '2026-03-20',
      TIMESTAMP '2026-03-21 11:00:00', TIMESTAMP '2026-03-25 10:15:00', CURRENT_TIMESTAMP);

-- ── Completed in March but not yet invoiced ───────────────────────────────
-- Analytics counts it (status='completed'). Finance does NOT (no invoice yet).
INSERT INTO orders VALUES
  ('O-004', 'C-103',  500000.00, 'USD',  500000.00, 'completed', DATE '2026-03-28',
      NULL, NULL, CURRENT_TIMESTAMP);

-- ── Non-USD order, not yet converted ──────────────────────────────────────
-- Analytics takes local amount as-is ($300k EUR counted as $300k).
-- Finance excludes (USD amount missing). Engineering includes gross.
-- This row also drives the null-rate trust check to flag an issue.
INSERT INTO orders VALUES
  ('O-005', 'C-104',  300000.00, 'EUR', NULL, 'completed', DATE '2026-03-15',
      TIMESTAMP '2026-03-16 12:00:00', TIMESTAMP '2026-03-22 09:45:00', CURRENT_TIMESTAMP);

-- ── Cancelled order — excluded by everyone ────────────────────────────────
INSERT INTO orders VALUES
  ('O-006', 'C-105',  400000.00, 'USD',  400000.00, 'cancelled', DATE '2026-03-18',
      NULL, NULL, CURRENT_TIMESTAMP);

-- ── Pending order (not yet completed) ─────────────────────────────────────
-- Engineering INCLUDES (status != 'cancelled'). Analytics/Finance exclude.
INSERT INTO orders VALUES
  ('O-007', 'C-106',  600000.00, 'USD',  600000.00, 'pending', DATE '2026-03-30',
      NULL, NULL, CURRENT_TIMESTAMP);

-- ── Apr 1 order — picked up by analytics' rolling 30d, excluded by others ─
INSERT INTO orders VALUES
  ('O-008', 'C-107',  250000.00, 'USD',  250000.00, 'completed', DATE '2026-04-01',
      TIMESTAMP '2026-04-01 10:00:00', TIMESTAMP '2026-04-01 14:00:00', CURRENT_TIMESTAMP);

-- ── Refund on O-002: $200k returned to customer ──────────────────────────
INSERT INTO refunds VALUES
  ('R-001', 'O-002', 200000.00, DATE '2026-03-22', CURRENT_TIMESTAMP);

-- ── Refund on O-001: $50k partial return ─────────────────────────────────
INSERT INTO refunds VALUES
  ('R-002', 'O-001', 50000.00, DATE '2026-03-28', CURRENT_TIMESTAMP);
