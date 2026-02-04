# Step B.4 — Logging and PID file

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Logging

- Use a dedicated log file (e.g. `indexing_worker.log`).
- Use rotating file handler (same pattern as vectorization).

## PID file

- Path: e.g. `indexing_worker.pid`.
- Remove on exit **only** if the PID in the file is the current process.
