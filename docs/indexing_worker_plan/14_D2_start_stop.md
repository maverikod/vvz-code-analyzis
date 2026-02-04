# Step D.2 — start_worker / stop_worker

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Where

`worker_management_mcp_commands.py` (or equivalent).

## Change

- Add `"indexing"` to the allowed `worker_type` enum for start/stop.
- **Start**: When starting, call `worker_manager.start_indexing_worker(...)` with params from request (or config).
- **Stop**: When stopping, call `stop_worker_type("indexing")`.
