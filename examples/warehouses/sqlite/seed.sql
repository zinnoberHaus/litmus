-- SQLite seed script — same semantics as a production app DB.
-- Run with: sqlite3 app.sqlite < seed.sql

DROP TABLE IF EXISTS orders;

CREATE TABLE orders (
    order_id     INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL,
    status       TEXT NOT NULL,
    amount       REAL,
    order_date   TEXT NOT NULL,
    updated_at   TEXT DEFAULT (datetime('now'))
);

INSERT INTO orders (order_id, customer_id, status, amount, order_date) VALUES
  (1, 201, 'completed', 89.00,   '2026-04-10'),
  (2, 202, 'completed', 450.50,  '2026-04-11'),
  (3, 203, 'pending',   120.00,  '2026-04-11'),
  (4, 204, 'completed', 1200.00, '2026-04-12'),
  (5, 205, 'cancelled', 55.00,   '2026-04-12'),
  (6, 206, 'completed', 310.25,  '2026-04-13'),
  (7, 207, 'completed', 78.99,   '2026-04-14'),
  (8, 208, 'completed', 2100.00, '2026-04-14'),
  (9, 209, 'completed', 44.50,   '2026-04-15'),
  (10,210, 'completed', 890.00,  '2026-04-15'),
  (11,211, 'completed', 115.75,  '2026-04-16'),
  (12,212, 'completed', 640.00,  '2026-04-16');
