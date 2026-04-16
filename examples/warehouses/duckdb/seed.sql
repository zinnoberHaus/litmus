-- Seed data for the DuckDB example.
-- Run with: duckdb analytics.duckdb < seed.sql

DROP TABLE IF EXISTS events;

CREATE TABLE events (
    event_id      BIGINT PRIMARY KEY,
    user_id       BIGINT NOT NULL,
    event_type    VARCHAR NOT NULL,
    event_value   DOUBLE,
    amount        DOUBLE,
    event_date    DATE NOT NULL,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO events (event_id, user_id, event_type, event_value, amount, event_date) VALUES
  (1,  101, 'signup',       NULL, 0,      DATE '2026-04-10'),
  (2,  101, 'purchase',     1.0,  49.99,  DATE '2026-04-11'),
  (3,  102, 'signup',       NULL, 0,      DATE '2026-04-11'),
  (4,  103, 'signup',       NULL, 0,      DATE '2026-04-12'),
  (5,  103, 'purchase',     1.0,  120.00, DATE '2026-04-12'),
  (6,  104, 'signup',       NULL, 0,      DATE '2026-04-13'),
  (7,  104, 'purchase',     1.0,  15.50,  DATE '2026-04-13'),
  (8,  105, 'signup',       NULL, 0,      DATE '2026-04-14'),
  (9,  105, 'purchase',     1.0,  210.00, DATE '2026-04-14'),
  (10, 106, 'signup',       NULL, 0,      DATE '2026-04-14'),
  (11, 106, 'purchase',     1.0,  75.25,  DATE '2026-04-15'),
  (12, 107, 'signup',       NULL, 0,      DATE '2026-04-15'),
  (13, 108, 'signup',       NULL, 0,      DATE '2026-04-15'),
  (14, 108, 'purchase',     1.0,  89.00,  DATE '2026-04-16'),
  (15, 109, 'signup',       NULL, 0,      DATE '2026-04-16');

SELECT 'Loaded ' || COUNT(*) || ' events, ' || COUNT(DISTINCT user_id) || ' users' AS status FROM events;
