"""Background-style jobs callable from API routes (or a future scheduler).

Nothing here runs on a timer — the ``litmus_api`` process exposes these as
plain functions. Production deployments wire their own scheduler (Airflow,
cron, Dagster, …) that hits the corresponding endpoint on a cadence.
"""
