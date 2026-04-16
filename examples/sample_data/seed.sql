-- =============================================================================
-- Litmus Demo Seed Data
-- Target: DuckDB
-- Creates: orders, subscriptions, subscription_events, invoices
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. ORDERS — e-commerce and one-time purchases
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    order_id        VARCHAR PRIMARY KEY,
    customer_id     VARCHAR NOT NULL,
    order_date      TIMESTAMP NOT NULL,
    status          VARCHAR NOT NULL,       -- completed, pending, refunded, canceled
    subtotal        DECIMAL(12,2) NOT NULL,
    discount        DECIMAL(12,2) DEFAULT 0,
    tax             DECIMAL(12,2) DEFAULT 0,
    net_amount      DECIMAL(12,2) NOT NULL,
    currency        VARCHAR(3) DEFAULT 'USD',
    channel         VARCHAR DEFAULT 'web',  -- web, mobile, api, pos
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO orders (order_id, customer_id, order_date, status, subtotal, discount, tax, net_amount, currency, channel) VALUES
-- 2025-01 orders
('ord_001', 'cust_001', '2025-01-03 10:15:00', 'completed',  149.99,  0.00, 12.00, 161.99, 'USD', 'web'),
('ord_002', 'cust_002', '2025-01-05 14:30:00', 'completed',  299.00, 29.90, 21.53, 290.63, 'USD', 'web'),
('ord_003', 'cust_003', '2025-01-08 09:45:00', 'completed',   49.99,  5.00,  3.60,  48.59, 'USD', 'mobile'),
('ord_004', 'cust_004', '2025-01-10 16:20:00', 'completed',  799.00,  0.00, 63.92, 862.92, 'USD', 'web'),
('ord_005', 'cust_005', '2025-01-12 11:00:00', 'refunded',   199.00, 19.90, 14.33, 193.43, 'USD', 'web'),
('ord_006', 'cust_006', '2025-01-15 08:30:00', 'completed',  599.00, 59.90, 43.13, 582.23, 'USD', 'api'),
('ord_007', 'cust_007', '2025-01-18 13:45:00', 'completed',   89.99,  0.00,  7.20,  97.19, 'USD', 'mobile'),
('ord_008', 'cust_008', '2025-01-20 15:10:00', 'completed', 1249.00,124.90, 89.93,1214.03, 'USD', 'web'),
('ord_009', 'cust_009', '2025-01-22 10:00:00', 'completed',  349.99, 35.00, 25.20, 340.19, 'USD', 'web'),
('ord_010', 'cust_010', '2025-01-25 17:30:00', 'completed',  179.00,  0.00, 14.32, 193.32, 'USD', 'pos'),
-- 2025-02 orders
('ord_011', 'cust_001', '2025-02-01 09:00:00', 'completed',  249.99, 25.00, 18.00, 242.99, 'USD', 'web'),
('ord_012', 'cust_011', '2025-02-03 12:15:00', 'completed',  499.00,  0.00, 39.92, 538.92, 'USD', 'web'),
('ord_013', 'cust_012', '2025-02-05 14:30:00', 'completed',   79.99,  8.00,  5.76,  77.75, 'USD', 'mobile'),
('ord_014', 'cust_013', '2025-02-08 16:00:00', 'refunded',   399.00, 39.90, 28.73, 387.83, 'USD', 'web'),
('ord_015', 'cust_014', '2025-02-10 11:45:00', 'completed',  159.00, 15.90, 11.45, 154.55, 'USD', 'api'),
('ord_016', 'cust_003', '2025-02-12 10:30:00', 'completed',  699.00, 69.90, 50.33, 679.43, 'USD', 'web'),
('ord_017', 'cust_015', '2025-02-15 13:00:00', 'completed',  119.99, 12.00,  8.64, 116.63, 'USD', 'mobile'),
('ord_018', 'cust_016', '2025-02-18 09:20:00', 'completed',  899.00,  0.00, 71.92, 970.92, 'USD', 'web'),
('ord_019', 'cust_017', '2025-02-20 15:50:00', 'completed',   59.99,  0.00,  4.80,  64.79, 'USD', 'pos'),
('ord_020', 'cust_018', '2025-02-22 08:10:00', 'completed',  449.00, 44.90, 32.33, 436.43, 'USD', 'web'),
-- 2025-03 orders
('ord_021', 'cust_002', '2025-03-01 10:00:00', 'completed',  329.99, 33.00, 23.76, 320.75, 'USD', 'web'),
('ord_022', 'cust_019', '2025-03-03 11:30:00', 'completed', 1499.00,149.90,107.93,1457.03, 'USD', 'web'),
('ord_023', 'cust_020', '2025-03-05 14:00:00', 'completed',   99.99,  0.00,  8.00, 107.99, 'USD', 'mobile'),
('ord_024', 'cust_004', '2025-03-08 09:15:00', 'completed',  549.00, 54.90, 39.53, 533.63, 'USD', 'api'),
('ord_025', 'cust_021', '2025-03-10 16:45:00', 'refunded',   279.00, 27.90, 20.09, 271.19, 'USD', 'web'),
('ord_026', 'cust_022', '2025-03-12 12:00:00', 'completed',  189.99,  0.00, 15.20, 205.19, 'USD', 'web'),
('ord_027', 'cust_023', '2025-03-15 08:45:00', 'completed',  749.00, 74.90, 53.93, 728.03, 'USD', 'web'),
('ord_028', 'cust_006', '2025-03-18 13:20:00', 'completed',  429.00, 42.90, 30.89, 416.99, 'USD', 'pos'),
('ord_029', 'cust_024', '2025-03-20 10:50:00', 'completed',   69.99,  7.00,  5.04,  68.03, 'USD', 'mobile'),
('ord_030', 'cust_025', '2025-03-22 15:30:00', 'completed',  999.00, 99.90, 71.93, 971.03, 'USD', 'web');

-- ---------------------------------------------------------------------------
-- 2. SUBSCRIPTIONS — SaaS recurring billing
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id   VARCHAR PRIMARY KEY,
    customer_id       VARCHAR NOT NULL,
    plan_name         VARCHAR NOT NULL,         -- starter, professional, enterprise, trial
    plan_amount       DECIMAL(10,2) NOT NULL,   -- monthly charge (annual plans stored as monthly equiv)
    billing_interval  VARCHAR NOT NULL,         -- monthly, annual
    status            VARCHAR NOT NULL,         -- active, canceled, past_due, trialing, expired
    started_at        TIMESTAMP NOT NULL,
    canceled_at       TIMESTAMP,
    current_period_start TIMESTAMP,
    current_period_end   TIMESTAMP,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO subscriptions (subscription_id, customer_id, plan_name, plan_amount, billing_interval, status, started_at, canceled_at, current_period_start, current_period_end) VALUES
-- Active monthly subscriptions
('sub_001', 'cust_001', 'professional',  79.00, 'monthly', 'active',   '2024-06-15 00:00:00', NULL,                    '2025-03-15 00:00:00', '2025-04-15 00:00:00'),
('sub_002', 'cust_002', 'starter',       29.00, 'monthly', 'active',   '2024-08-01 00:00:00', NULL,                    '2025-03-01 00:00:00', '2025-04-01 00:00:00'),
('sub_003', 'cust_003', 'enterprise',   299.00, 'monthly', 'active',   '2024-03-10 00:00:00', NULL,                    '2025-03-10 00:00:00', '2025-04-10 00:00:00'),
('sub_004', 'cust_004', 'professional',  79.00, 'monthly', 'active',   '2024-09-20 00:00:00', NULL,                    '2025-03-20 00:00:00', '2025-04-20 00:00:00'),
('sub_005', 'cust_006', 'starter',       29.00, 'monthly', 'active',   '2024-11-05 00:00:00', NULL,                    '2025-03-05 00:00:00', '2025-04-05 00:00:00'),
('sub_006', 'cust_007', 'professional',  79.00, 'monthly', 'active',   '2025-01-10 00:00:00', NULL,                    '2025-03-10 00:00:00', '2025-04-10 00:00:00'),
('sub_007', 'cust_008', 'enterprise',   299.00, 'monthly', 'active',   '2024-07-22 00:00:00', NULL,                    '2025-03-22 00:00:00', '2025-04-22 00:00:00'),
('sub_008', 'cust_011', 'starter',       29.00, 'monthly', 'active',   '2025-02-01 00:00:00', NULL,                    '2025-03-01 00:00:00', '2025-04-01 00:00:00'),
('sub_009', 'cust_012', 'professional',  79.00, 'monthly', 'active',   '2024-12-15 00:00:00', NULL,                    '2025-03-15 00:00:00', '2025-04-15 00:00:00'),
('sub_010', 'cust_015', 'enterprise',   299.00, 'monthly', 'active',   '2024-10-01 00:00:00', NULL,                    '2025-03-01 00:00:00', '2025-04-01 00:00:00'),
-- Active annual subscriptions (plan_amount = annual price / 12)
('sub_011', 'cust_016', 'professional',  66.58, 'annual',  'active',   '2024-04-01 00:00:00', NULL,                    '2025-04-01 00:00:00', '2026-04-01 00:00:00'),
('sub_012', 'cust_018', 'enterprise',   249.17, 'annual',  'active',   '2024-05-15 00:00:00', NULL,                    '2025-05-15 00:00:00', '2026-05-15 00:00:00'),
('sub_013', 'cust_019', 'starter',       24.17, 'annual',  'active',   '2024-09-01 00:00:00', NULL,                    '2025-09-01 00:00:00', '2026-09-01 00:00:00'),
-- Past due
('sub_014', 'cust_020', 'professional',  79.00, 'monthly', 'past_due', '2024-08-10 00:00:00', NULL,                    '2025-02-10 00:00:00', '2025-03-10 00:00:00'),
('sub_015', 'cust_022', 'starter',       29.00, 'monthly', 'past_due', '2024-11-20 00:00:00', NULL,                    '2025-02-20 00:00:00', '2025-03-20 00:00:00'),
-- Canceled during March 2025
('sub_016', 'cust_005', 'starter',       29.00, 'monthly', 'canceled', '2024-07-01 00:00:00', '2025-03-05 00:00:00',   '2025-03-01 00:00:00', '2025-04-01 00:00:00'),
('sub_017', 'cust_009', 'professional',  79.00, 'monthly', 'canceled', '2024-10-15 00:00:00', '2025-03-18 00:00:00',   '2025-03-15 00:00:00', '2025-04-15 00:00:00'),
('sub_018', 'cust_010', 'enterprise',   299.00, 'monthly', 'canceled', '2024-06-01 00:00:00', '2025-03-25 00:00:00',   '2025-03-01 00:00:00', '2025-04-01 00:00:00'),
-- Canceled during February 2025
('sub_019', 'cust_013', 'starter',       29.00, 'monthly', 'canceled', '2024-09-10 00:00:00', '2025-02-12 00:00:00',   '2025-02-10 00:00:00', '2025-03-10 00:00:00'),
('sub_020', 'cust_014', 'professional',  79.00, 'monthly', 'canceled', '2024-04-20 00:00:00', '2025-02-28 00:00:00',   '2025-02-20 00:00:00', '2025-03-20 00:00:00'),
-- Trialing (not counted in churn)
('sub_021', 'cust_023', 'trial',          0.00, 'monthly', 'trialing', '2025-03-20 00:00:00', NULL,                    '2025-03-20 00:00:00', '2025-04-20 00:00:00'),
('sub_022', 'cust_024', 'trial',          0.00, 'monthly', 'trialing', '2025-03-22 00:00:00', NULL,                    '2025-03-22 00:00:00', '2025-04-22 00:00:00'),
-- Expired (natural end, no renewal)
('sub_023', 'cust_025', 'starter',       29.00, 'monthly', 'expired',  '2024-05-01 00:00:00', NULL,                    '2025-02-01 00:00:00', '2025-03-01 00:00:00'),
('sub_024', 'cust_017', 'professional',  79.00, 'monthly', 'expired',  '2024-08-15 00:00:00', NULL,                    '2025-01-15 00:00:00', '2025-02-15 00:00:00');

-- ---------------------------------------------------------------------------
-- 3. SUBSCRIPTION_EVENTS — lifecycle audit log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subscription_events (
    event_id          VARCHAR PRIMARY KEY,
    subscription_id   VARCHAR NOT NULL,
    event_type        VARCHAR NOT NULL,         -- created, renewed, canceled, upgraded, downgraded, payment_failed, expired
    previous_plan     VARCHAR,
    new_plan          VARCHAR,
    previous_amount   DECIMAL(10,2),
    new_amount        DECIMAL(10,2),
    occurred_at       TIMESTAMP NOT NULL,
    metadata          VARCHAR                   -- JSON-like notes
);

INSERT INTO subscription_events (event_id, subscription_id, event_type, previous_plan, new_plan, previous_amount, new_amount, occurred_at, metadata) VALUES
-- Creation events
('evt_001', 'sub_001', 'created',        NULL,           'professional', NULL,    79.00, '2024-06-15 00:00:00', NULL),
('evt_002', 'sub_002', 'created',        NULL,           'starter',      NULL,    29.00, '2024-08-01 00:00:00', NULL),
('evt_003', 'sub_003', 'created',        NULL,           'enterprise',   NULL,   299.00, '2024-03-10 00:00:00', NULL),
('evt_004', 'sub_004', 'created',        NULL,           'professional', NULL,    79.00, '2024-09-20 00:00:00', NULL),
('evt_005', 'sub_005', 'created',        NULL,           'starter',      NULL,    29.00, '2024-11-05 00:00:00', NULL),
('evt_006', 'sub_006', 'created',        NULL,           'professional', NULL,    79.00, '2025-01-10 00:00:00', NULL),
('evt_007', 'sub_007', 'created',        NULL,           'enterprise',   NULL,   299.00, '2024-07-22 00:00:00', NULL),
('evt_008', 'sub_008', 'created',        NULL,           'starter',      NULL,    29.00, '2025-02-01 00:00:00', NULL),
('evt_009', 'sub_009', 'created',        NULL,           'professional', NULL,    79.00, '2024-12-15 00:00:00', NULL),
('evt_010', 'sub_010', 'created',        NULL,           'enterprise',   NULL,   299.00, '2024-10-01 00:00:00', NULL),
('evt_011', 'sub_011', 'created',        NULL,           'professional', NULL,    66.58, '2024-04-01 00:00:00', NULL),
('evt_012', 'sub_012', 'created',        NULL,           'enterprise',   NULL,   249.17, '2024-05-15 00:00:00', NULL),
('evt_013', 'sub_013', 'created',        NULL,           'starter',      NULL,    24.17, '2024-09-01 00:00:00', NULL),
('evt_014', 'sub_016', 'created',        NULL,           'starter',      NULL,    29.00, '2024-07-01 00:00:00', NULL),
('evt_015', 'sub_017', 'created',        NULL,           'professional', NULL,    79.00, '2024-10-15 00:00:00', NULL),
('evt_016', 'sub_018', 'created',        NULL,           'enterprise',   NULL,   299.00, '2024-06-01 00:00:00', NULL),
-- Renewal events (monthly renewals for active subs)
('evt_017', 'sub_001', 'renewed',        'professional', 'professional',  79.00,  79.00, '2025-02-15 00:00:00', NULL),
('evt_018', 'sub_001', 'renewed',        'professional', 'professional',  79.00,  79.00, '2025-03-15 00:00:00', NULL),
('evt_019', 'sub_002', 'renewed',        'starter',      'starter',       29.00,  29.00, '2025-03-01 00:00:00', NULL),
('evt_020', 'sub_003', 'renewed',        'enterprise',   'enterprise',   299.00, 299.00, '2025-03-10 00:00:00', NULL),
('evt_021', 'sub_004', 'renewed',        'professional', 'professional',  79.00,  79.00, '2025-03-20 00:00:00', NULL),
('evt_022', 'sub_005', 'renewed',        'starter',      'starter',       29.00,  29.00, '2025-03-05 00:00:00', NULL),
('evt_023', 'sub_007', 'renewed',        'enterprise',   'enterprise',   299.00, 299.00, '2025-03-22 00:00:00', NULL),
('evt_024', 'sub_008', 'renewed',        'starter',      'starter',       29.00,  29.00, '2025-03-01 00:00:00', NULL),
('evt_025', 'sub_009', 'renewed',        'professional', 'professional',  79.00,  79.00, '2025-03-15 00:00:00', NULL),
('evt_026', 'sub_010', 'renewed',        'enterprise',   'enterprise',   299.00, 299.00, '2025-03-01 00:00:00', NULL),
-- Upgrade events
('evt_027', 'sub_002', 'upgraded',       'starter',      'professional',  29.00,  79.00, '2025-01-15 00:00:00', '{"reason": "team growth"}'),
('evt_028', 'sub_002', 'downgraded',     'professional', 'starter',       79.00,  29.00, '2025-02-15 00:00:00', '{"reason": "cost reduction"}'),
('evt_029', 'sub_005', 'upgraded',       'starter',      'professional',  29.00,  79.00, '2025-02-10 00:00:00', '{"reason": "feature needs"}'),
('evt_030', 'sub_005', 'downgraded',     'professional', 'starter',       79.00,  29.00, '2025-03-01 00:00:00', '{"reason": "budget cut"}'),
-- Cancellation events
('evt_031', 'sub_016', 'canceled',       'starter',      NULL,            29.00,   0.00, '2025-03-05 00:00:00', '{"reason": "switched to competitor"}'),
('evt_032', 'sub_017', 'canceled',       'professional', NULL,            79.00,   0.00, '2025-03-18 00:00:00', '{"reason": "no longer needed"}'),
('evt_033', 'sub_018', 'canceled',       'enterprise',   NULL,           299.00,   0.00, '2025-03-25 00:00:00', '{"reason": "company downsized"}'),
('evt_034', 'sub_019', 'canceled',       'starter',      NULL,            29.00,   0.00, '2025-02-12 00:00:00', '{"reason": "poor onboarding"}'),
('evt_035', 'sub_020', 'canceled',       'professional', NULL,            79.00,   0.00, '2025-02-28 00:00:00', '{"reason": "migrating systems"}'),
-- Payment failures
('evt_036', 'sub_014', 'payment_failed', 'professional', 'professional',  79.00,  79.00, '2025-03-10 00:00:00', '{"retry": 1}'),
('evt_037', 'sub_014', 'payment_failed', 'professional', 'professional',  79.00,  79.00, '2025-03-13 00:00:00', '{"retry": 2}'),
('evt_038', 'sub_015', 'payment_failed', 'starter',      'starter',       29.00,  29.00, '2025-03-20 00:00:00', '{"retry": 1}'),
-- Expiration events
('evt_039', 'sub_023', 'expired',        'starter',      NULL,            29.00,   0.00, '2025-03-01 00:00:00', NULL),
('evt_040', 'sub_024', 'expired',        'professional', NULL,            79.00,   0.00, '2025-02-15 00:00:00', NULL);

-- ---------------------------------------------------------------------------
-- 4. INVOICES — financial records for revenue recognition
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoices (
    invoice_id        VARCHAR PRIMARY KEY,
    customer_id       VARCHAR NOT NULL,
    subscription_id   VARCHAR,                  -- NULL for one-time purchases
    order_id          VARCHAR,                  -- NULL for subscription invoices
    invoice_date      TIMESTAMP NOT NULL,
    due_date          TIMESTAMP NOT NULL,
    status            VARCHAR NOT NULL,         -- finalized, draft, void, uncollectible
    subtotal          DECIMAL(12,2) NOT NULL,
    discount          DECIMAL(12,2) DEFAULT 0,
    tax               DECIMAL(12,2) DEFAULT 0,
    net_amount        DECIMAL(12,2) NOT NULL,
    currency          VARCHAR(3) DEFAULT 'USD',
    paid_at           TIMESTAMP,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO invoices (invoice_id, customer_id, subscription_id, order_id, invoice_date, due_date, status, subtotal, discount, tax, net_amount, currency, paid_at) VALUES
-- Subscription invoices — January 2025
('inv_001', 'cust_001', 'sub_001', NULL, '2025-01-15 00:00:00', '2025-01-30 00:00:00', 'finalized',  79.00,  0.00,  6.32,  85.32, 'USD', '2025-01-15 08:00:00'),
('inv_002', 'cust_002', 'sub_002', NULL, '2025-01-01 00:00:00', '2025-01-15 00:00:00', 'finalized',  79.00,  0.00,  6.32,  85.32, 'USD', '2025-01-02 10:00:00'),
('inv_003', 'cust_003', 'sub_003', NULL, '2025-01-10 00:00:00', '2025-01-25 00:00:00', 'finalized', 299.00,  0.00, 23.92, 322.92, 'USD', '2025-01-10 09:00:00'),
('inv_004', 'cust_004', 'sub_004', NULL, '2025-01-20 00:00:00', '2025-02-04 00:00:00', 'finalized',  79.00,  0.00,  6.32,  85.32, 'USD', '2025-01-21 07:30:00'),
('inv_005', 'cust_006', 'sub_005', NULL, '2025-01-05 00:00:00', '2025-01-20 00:00:00', 'finalized',  29.00,  0.00,  2.32,  31.32, 'USD', '2025-01-05 12:00:00'),
('inv_006', 'cust_007', 'sub_006', NULL, '2025-01-10 00:00:00', '2025-01-25 00:00:00', 'finalized',  79.00,  0.00,  6.32,  85.32, 'USD', '2025-01-10 14:00:00'),
('inv_007', 'cust_008', 'sub_007', NULL, '2025-01-22 00:00:00', '2025-02-06 00:00:00', 'finalized', 299.00,  0.00, 23.92, 322.92, 'USD', '2025-01-22 11:00:00'),
-- Subscription invoices — February 2025
('inv_008', 'cust_001', 'sub_001', NULL, '2025-02-15 00:00:00', '2025-03-02 00:00:00', 'finalized',  79.00,  0.00,  6.32,  85.32, 'USD', '2025-02-15 08:15:00'),
('inv_009', 'cust_002', 'sub_002', NULL, '2025-02-01 00:00:00', '2025-02-15 00:00:00', 'finalized',  29.00,  0.00,  2.32,  31.32, 'USD', '2025-02-01 09:30:00'),
('inv_010', 'cust_003', 'sub_003', NULL, '2025-02-10 00:00:00', '2025-02-25 00:00:00', 'finalized', 299.00,  0.00, 23.92, 322.92, 'USD', '2025-02-10 10:00:00'),
('inv_011', 'cust_008', 'sub_007', NULL, '2025-02-22 00:00:00', '2025-03-09 00:00:00', 'finalized', 299.00,  0.00, 23.92, 322.92, 'USD', '2025-02-22 11:45:00'),
('inv_012', 'cust_011', 'sub_008', NULL, '2025-02-01 00:00:00', '2025-02-15 00:00:00', 'finalized',  29.00,  0.00,  2.32,  31.32, 'USD', '2025-02-01 13:00:00'),
('inv_013', 'cust_012', 'sub_009', NULL, '2025-02-15 00:00:00', '2025-03-02 00:00:00', 'finalized',  79.00,  0.00,  6.32,  85.32, 'USD', '2025-02-16 07:00:00'),
('inv_014', 'cust_015', 'sub_010', NULL, '2025-02-01 00:00:00', '2025-02-15 00:00:00', 'finalized', 299.00,  0.00, 23.92, 322.92, 'USD', '2025-02-02 09:00:00'),
-- Subscription invoices — March 2025
('inv_015', 'cust_001', 'sub_001', NULL, '2025-03-15 00:00:00', '2025-03-30 00:00:00', 'finalized',  79.00,  0.00,  6.32,  85.32, 'USD', '2025-03-15 08:00:00'),
('inv_016', 'cust_002', 'sub_002', NULL, '2025-03-01 00:00:00', '2025-03-15 00:00:00', 'finalized',  29.00,  0.00,  2.32,  31.32, 'USD', '2025-03-01 10:00:00'),
('inv_017', 'cust_003', 'sub_003', NULL, '2025-03-10 00:00:00', '2025-03-25 00:00:00', 'finalized', 299.00,  0.00, 23.92, 322.92, 'USD', '2025-03-10 09:45:00'),
('inv_018', 'cust_004', 'sub_004', NULL, '2025-03-20 00:00:00', '2025-04-04 00:00:00', 'finalized',  79.00,  0.00,  6.32,  85.32, 'USD', '2025-03-20 12:00:00'),
('inv_019', 'cust_006', 'sub_005', NULL, '2025-03-05 00:00:00', '2025-03-20 00:00:00', 'finalized',  29.00,  0.00,  2.32,  31.32, 'USD', '2025-03-05 08:30:00'),
('inv_020', 'cust_007', 'sub_006', NULL, '2025-03-10 00:00:00', '2025-03-25 00:00:00', 'finalized',  79.00,  0.00,  6.32,  85.32, 'USD', '2025-03-10 14:00:00'),
('inv_021', 'cust_008', 'sub_007', NULL, '2025-03-22 00:00:00', '2025-04-06 00:00:00', 'finalized', 299.00,  0.00, 23.92, 322.92, 'USD', '2025-03-22 10:30:00'),
('inv_022', 'cust_011', 'sub_008', NULL, '2025-03-01 00:00:00', '2025-03-15 00:00:00', 'finalized',  29.00,  0.00,  2.32,  31.32, 'USD', '2025-03-01 09:00:00'),
('inv_023', 'cust_012', 'sub_009', NULL, '2025-03-15 00:00:00', '2025-03-30 00:00:00', 'finalized',  79.00,  0.00,  6.32,  85.32, 'USD', '2025-03-15 11:00:00'),
('inv_024', 'cust_015', 'sub_010', NULL, '2025-03-01 00:00:00', '2025-03-15 00:00:00', 'finalized', 299.00,  0.00, 23.92, 322.92, 'USD', '2025-03-01 08:00:00'),
-- Past-due subscription invoices
('inv_025', 'cust_020', 'sub_014', NULL, '2025-03-10 00:00:00', '2025-03-25 00:00:00', 'finalized',  79.00,  0.00,  6.32,  85.32, 'USD', NULL),
('inv_026', 'cust_022', 'sub_015', NULL, '2025-03-20 00:00:00', '2025-04-04 00:00:00', 'finalized',  29.00,  0.00,  2.32,  31.32, 'USD', NULL),
-- Voided invoice (from canceled sub)
('inv_027', 'cust_005', 'sub_016', NULL, '2025-03-01 00:00:00', '2025-03-15 00:00:00', 'void',        29.00,  0.00,  2.32,  31.32, 'USD', NULL),
-- One-time purchase invoices (tied to orders)
('inv_028', 'cust_004', NULL, 'ord_004', '2025-01-10 16:20:00', '2025-01-25 00:00:00', 'finalized', 799.00,  0.00, 63.92, 862.92, 'USD', '2025-01-10 16:25:00'),
('inv_029', 'cust_008', NULL, 'ord_008', '2025-01-20 15:10:00', '2025-02-04 00:00:00', 'finalized',1249.00,124.90, 89.93,1214.03, 'USD', '2025-01-20 15:15:00'),
('inv_030', 'cust_019', NULL, 'ord_022', '2025-03-03 11:30:00', '2025-03-18 00:00:00', 'finalized',1499.00,149.90,107.93,1457.03, 'USD', '2025-03-03 11:35:00'),
-- Draft invoice (not yet finalized — should be excluded from revenue)
('inv_031', 'cust_023', NULL, NULL,       '2025-03-28 00:00:00', '2025-04-12 00:00:00', 'draft',       49.00,  0.00,  3.92,  52.92, 'USD', NULL);
