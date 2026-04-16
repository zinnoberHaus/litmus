# SQLite example

Point Litmus at a SQLite database (an app DB, a Datasette file, a local analytics cache).

## Run it

```bash
./setup.sh                    # creates app.sqlite, bridges into bridge.duckdb
litmus check orders.metric
```

## How it works

Litmus's native SQLite connector reads the `.sqlite` file directly — no bridge, no extension, no extras. `setup.sh` just seeds the DB from `seed.sql`, and `litmus.yml` has `type: sqlite` with `database: app.sqlite`.

## Adapting it

1. Replace `app.sqlite` with your file (symlink, copy, or edit the path in `setup.sh`).
2. Edit `orders.metric` to match your table + columns.
3. Re-run.
