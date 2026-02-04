# Step C.5 — Optional: config

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Where

If there is a `config.json` (or similar) section for workers.

## Add

An `indexing_worker` section with:

- `poll_interval`
- `batch_size`
- `log_path` (or derive from `logs` dir)

Use defaults (e.g. 30, 5) if missing.
