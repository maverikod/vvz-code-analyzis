# Step B.3 — Backoff and DB availability

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Pattern

Same as vectorization worker:

- If DB is unavailable, log and retry with backoff (e.g. 1–60 s).
- When DB is available again, run the cycle.
- On each cycle, reconnect or reuse existing `DatabaseClient` as in vectorization.
