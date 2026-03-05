# Database query journal

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Purpose

The database driver can write every executed SQL statement to a **query journal** file. This allows:

- **Inspection**: see all queries (and parameters) in chronological order.
- **Recovery**: replay successful write statements from the journal into another database (e.g. after restore from backup).

## Configuration

- **Default**: when the database driver is started by the server, the journal path is set to  
  `{config_dir}/logs/database_queries.jsonl`.
- **Override**: in `code_analysis.database.driver.config` set `query_log_path` to an absolute or relative path to a `.jsonl` file.  
  Example: `"query_log_path": "/var/log/code_analysis/db_queries.jsonl"`.
- **Disable**: do not set `query_log_path` in the driver config and ensure the startup code does not add it (or set it to empty string and handle in driver if needed). Currently the main startup always adds a default path; to disable, you would need to set `query_log_path` to `null` or remove it from the resolved config if the driver supports that.
- **Rotation**: journal rotates when the file reaches **100 MB** (config: `query_log_max_bytes`, default 104857600). Rotated files are `database_queries.jsonl.1`, `.2`, … (default 5 kept via `query_log_backup_count`).

## Format (JSON Lines)

One JSON object per line. Fields:

| Field            | Type    | Description |
|-----------------|---------|-------------|
| `ts`            | string  | ISO 8601 UTC timestamp |
| `sql`           | string  | SQL statement |
| `params`        | array or object | Bound parameters (positional or named) |
| `success`       | boolean | Whether execution succeeded |
| `transaction_id`| string  | Optional; present when the query ran inside a transaction |
| `error`         | string  | Optional; present when `success` is false |

Example line:

```json
{"ts": "2026-02-08T12:00:00.000000+00:00", "sql": "UPDATE files SET needs_chunking = ? WHERE id = ?", "params": [0, 42], "success": true}
```

## Replay (recovery)

Use the helper from the same module:

```python
from code_analysis.core.database_driver_pkg.sqlite_query_journal import replay_journal

def my_execute(sql: str, params):
    # Your DB execute (e.g. driver.execute(sql, params))
    ...

result = replay_journal(
    "logs/database_queries.jsonl",
    my_execute,
    only_success=True,  # replay only successful writes
    limit=1000,         # optional: max entries
)
# result: {"replayed": 1000, "failed": 0, "errors": []}
```

- **only_success=True**: only entries with `"success": true` are replayed (recommended for recovery).
- **only_success=False**: all entries are replayed; failed ones may raise in `my_execute`.

## Log location

By default the file is created under the server config directory, in the `logs` subdirectory:

- `logs/database_queries.jsonl` (relative to config dir)

The file is appended to and rotated automatically when it reaches 100 MB (see Configuration).

## Testing

Unit and recovery tests live in `tests/test_sqlite_query_journal.py`:

- **SQLiteQueryJournal**: write entries (success/failure), dict/positional params, write after close (no-op), path property.
- **replay_journal**: missing file, `only_success`, `limit`, invalid JSON, missing `sql`, execute_fn that raises.
- **Recovery**:
  - Record INSERT/UPDATE in a journal, replay into an empty DB with same schema, assert data matches.
  - Replay with `only_success=True` skips failed entries; only successful writes are applied.
  - Integration: start driver with `query_log_path`, run CREATE/INSERT/UPDATE, disconnect; replay journal into a new DB and verify restored rows.

Run: `pytest tests/test_sqlite_query_journal.py -v`
