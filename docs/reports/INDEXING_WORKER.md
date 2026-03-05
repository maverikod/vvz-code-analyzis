# Indexing Worker

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Purpose

The **indexing worker** keeps fulltext search (and AST/CST/entities data) up to date when files change on disk. It runs in a **separate process** (like the vectorization worker), so it does not block the server. Manual **update_indexes** remains available for full project refresh or recovery.

## How it discovers work

- The worker queries the database for projects that have at least one file with **needs_chunking = 1** (the same flag used by the file watcher and vectorization worker).
- Per project, it takes a **batch** of files with `needs_chunking = 1` (default batch size 5, configurable), ordered by `updated_at ASC`.
- For each file it calls the driver RPC **index_file(file_path, project_id)**. The driver performs the same logic as **update_file_data** (AST, CST, entities, code_content → fulltext) and clears `needs_chunking` for that file after success.
- There is **no** `root_dir` parameter: project root comes from the database (`projects.root_path`).

## Process and lifecycle

- Runs in a **separate process** (same pattern as the vectorization worker).
- Started automatically on server startup **before** the vectorization worker (so the indexer clears `needs_chunking` first; vectorization still picks up files via “no code_chunks” or chunk updates).
- Uses **DatabaseClient** (RPC) only; the driver process reads files from disk when handling the index_file RPC.
- Backoff (1–60 s) when the database is unavailable; resets when the DB is available again.
- Writes cycle statistics to **indexing_worker_stats** (start/update/end of each cycle).

## Config

Config section: **code_analysis.indexing_worker** (e.g. in `config.json`).

| Key            | Description                    | Default |
|----------------|--------------------------------|--------|
| **enabled**    | If false, worker is not started on startup | true  |
| **poll_interval** | Seconds between cycles       | 30     |
| **batch_size** | Max files per project per cycle | 5    |
| **log_path**   | Path to worker log file        | derived from config logs dir / indexing_worker.log |

Example:

```json
{
  "code_analysis": {
    "indexing_worker": {
      "enabled": true,
      "poll_interval": 30,
      "batch_size": 5,
      "log_path": "/path/to/logs/indexing_worker.log"
    }
  }
}
```

## Start / stop via MCP

- **get_worker_status** (worker_type = `"indexing"`): reports PID, log path, running/not running, and last cycle stats from **indexing_worker_stats** (files indexed, failed, timing).
- **start_worker** (worker_type = `"indexing"`): starts the indexing worker with params from request or config.
- **stop_worker** (worker_type = `"indexing"`): stops the indexing worker (same pattern as file_watcher and vectorization).

See [COMMANDS_GUIDE.md](COMMANDS_GUIDE.md) and command help for parameter details.

## Related docs

- [SEARCH_AND_VECTORIZATION_DATA_FLOW.md](SEARCH_AND_VECTORIZATION_DATA_FLOW.md) — data flow for fulltext and semantic search, and role of the indexing worker.
- [indexing_worker_plan/](indexing_worker_plan/) — implementation plan and step files.
