# Schema sync and temp_files table

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Purpose

This document clarifies who runs full schema synchronization (with `SchemaComparator` and the `temp_files` migration), and how to avoid inconsistent DB state (e.g. "no such table: main.temp_files") when indexing or running the RPC driver.

## Who runs sync_schema with SchemaComparator (and temp_files)

**Only the direct SQLite driver in `code_analysis.core.db_driver.sqlite`** runs the full migration that uses `temp_files`:

- **Entry point:** `config_cli schema` (or any code that creates `CodeDatabase` with the **db_driver** and then calls `sync_schema()`).
- **Requirements:** The process must set `CODE_ANALYSIS_DB_DRIVER=1` or `CODE_ANALYSIS_DB_WORKER=1` so that `db_driver.create_driver("sqlite", config)` is allowed (see `code_analysis/core/db_driver/__init__.py`).
- **Flow:** `db_driver/sqlite.py` `sync_schema()` uses `SchemaComparator(self, schema_definition)` and `comparator.generate_migration_sql(diff)`. For table `files` with type changes, the generated SQL includes:
  1. `ALTER TABLE files RENAME TO temp_files`
  2. `CREATE TABLE files (...)` (new schema)
  3. `INSERT INTO files (...) SELECT ... FROM temp_files`
  4. `DROP TABLE temp_files`
- **Transaction:** All migration statements run in a **single transaction** (`begin_transaction()` before the loop, `commit()` only after the loop). There is no per-statement commit, so `temp_files` is visible to the `INSERT` in the same connection.

## Who does not run SchemaComparator (no temp_files)

**The RPC database driver** (`code_analysis.core.database_driver_pkg.drivers.sqlite`) does **not** use `SchemaComparator`:

- **Used by:** The database driver process (started by the server) that handles RPCs such as `index_file`, `execute`, `sync_schema` (RPC), etc.
- **sync_schema:** Implemented by `SQLiteSchemaManager` in `database_driver_pkg/drivers/sqlite_schema.py`. It only creates **missing** tables by name; it does not run `SchemaComparator` or `generate_migration_sql`, and never creates or references `temp_files`.

So the RPC driver process never runs the `temp_files` migration. It only runs recovery (see below) when it opens the DB.

## Recovery on connect (database_driver_pkg)

When the **RPC driver** opens the database, it runs `_recover_files_table_if_needed()` on **every** `connect()`:

- If table `files` is missing and table `temp_files` exists (e.g. left over from an aborted migration in another process), it runs `ALTER TABLE temp_files RENAME TO files` and commits.
- This ensures that after a crashed or interrupted `config_cli schema` run, the next time the driver process connects, the `files` table is restored and `index_file` and other operations can succeed.

See `code_analysis/core/database_driver_pkg/drivers/sqlite.py`: `connect()` calls `_recover_files_table_if_needed()` before other migrations and table setup.

## Recommendations

1. **Run full schema sync (config_cli schema) when the server and database driver process are stopped**, or at least when no indexing or other DB-heavy work is in progress, to avoid lock contention and partial state visible across processes.
2. **Do not assume the RPC driver process ever runs the temp_files migration.** Only `db_driver/sqlite.py` (used by `config_cli schema` with the direct driver) does. If you see "no such table: main.temp_files" in indexing_errors, the failure is either from a sync_schema run (e.g. config_cli schema) that did not complete in one transaction, or from a different code path that should not reference `temp_files`; check logs for `[indexing_errors] Stored temp_files-related` and `[index_file] temp_files-related failure` to identify the caller.
3. **After an aborted schema sync**, restart the database driver process (or the whole server) so that `connect()` runs again and `_recover_files_table_if_needed()` can rename `temp_files` back to `files` if needed.

## Related code

| Component | File | Role |
|-----------|------|------|
| Full migration (temp_files) | `core/db_driver/sqlite.py` | `sync_schema()` with SchemaComparator; single transaction for all statements |
| Migration SQL generation | `core/database/schema_sync.py` | `SchemaComparator.generate_migration_sql()`; RENAME to temp_*, INSERT FROM temp_*, DROP temp_* |
| Recovery | `core/database_driver_pkg/drivers/sqlite.py` | `_recover_files_table_if_needed()` on connect(); renames temp_files → files |
| Simplified sync (no temp_files) | `core/database_driver_pkg/drivers/sqlite_schema.py` | `SQLiteSchemaManager.sync_schema()`; only creates missing tables |
