# Semantic layer

The files in this directory tell Litmus what your tables *mean*.

A `.yaml` file per entity (`customer`, `market`, `transaction`, …) declares:

- `entity` — short noun (customer, order, channel)
- `kind` — `dimension` (slow-changing reference) or `fact` (event/transaction stream)
- `table` — the raw/mart table that backs it
- `primary_key` — the unique-ID column
- `dimensions` — columns you slice / group by
- `measures` — columns you aggregate (with the right aggregation pre-declared)
- `joins` — how this entity connects to other entities
- `description` — one line per entity / dim / measure, used by the agents

When the agents answer a question like "what's our top market by revenue,"
they read these files first — so "revenue" always means the same thing
(sum of paid transaction amounts) and the join paths are correct.

Add a file here for each new mart table you ship. `pipeline-builder` does
this automatically; you can also write them by hand.
