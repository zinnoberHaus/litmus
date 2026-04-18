-- Demo orders model — a toy fact table we can point Litmus trust rules at.
-- No seed files required; everything materialises in memory from literals.

select 1 as order_id, 101 as customer_id, 'completed' as status, 120.00 as amount, cast('2026-04-10' as date) as order_date, current_timestamp as updated_at
union all select 2, 102, 'completed',   450.50, cast('2026-04-11' as date), current_timestamp
union all select 3, 103, 'pending',      80.00, cast('2026-04-11' as date), current_timestamp
union all select 4, 104, 'completed', 1200.00, cast('2026-04-12' as date), current_timestamp
union all select 5, 105, 'completed',   320.25, cast('2026-04-13' as date), current_timestamp
union all select 6, 106, 'completed',    75.99, cast('2026-04-14' as date), current_timestamp
union all select 7, 107, 'completed',   890.00, cast('2026-04-15' as date), current_timestamp
union all select 8, 108, 'completed',    44.50, cast('2026-04-16' as date), current_timestamp
