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

So the RPC driver process never runs the `temp_files` migration. Recovery (temp_files → files) uses a **single implementation** in `core/db_integrity.recover_files_table_if_needed(db_path)` and is used in two places so indexing works without manual steps.

## Recovery (temp_files → files)

- **On driver connect:** Before opening the DB connection, the RPC driver calls `recover_files_table_if_needed(db_path)`. If the DB has `temp_files` and no `files`, it renames `temp_files` to `files`. So after an aborted migration, the next driver start (e.g. server restart) fixes the schema and index_file works.
- **Explicit repair:** **repair_sqlite_database** with **force=false** also calls `recover_files_table_if_needed(db_path)` and returns `mode: "files_table_recovered"` when it performed the rename. Use when you want to fix the DB without restarting the server.

## Recommendations

1. **Run full schema sync (config_cli schema) when the server and database driver process are stopped**, or at least when no indexing or other DB-heavy work is in progress, to avoid lock contention and partial state visible across processes.
2. **Do not assume the RPC driver process ever runs the temp_files migration.** Only `db_driver/sqlite.py` (used by `config_cli schema` with the direct driver) does. If you see "no such table: main.temp_files" in indexing_errors, run **repair_sqlite_database** (force=false) to recover the files table; or run force=true to recreate the DB from scratch.
3. **If the DB is in a bad state** (e.g. after an aborted schema change), use **repair_sqlite_database** (force=false) first; it will recover temp_files → files and fix entity_cross_ref stale FKs when applicable. For manual repair: `ALTER TABLE temp_files RENAME TO files`; then recreate entity_cross_ref if it still references temp_files/temp_methods.

4. **Stale FKs in entity_cross_ref:** When migration renames `files`→`temp_files` and `methods`→`temp_methods`, SQLite updates FKs in `entity_cross_ref` to point at those names. After the migration drops `temp_*`, those FKs are broken (e.g. "no such table: main.temp_files" on DELETE FROM entity_cross_ref). The driver on connect and repair_sqlite_database (force=false) call `fix_entity_cross_ref_stale_fks(db_path)` to recreate the table with correct REFERENCES files(id), methods(id). The db_driver migration also calls it after a successful sync that recreated files or methods, so all temp_table statements stay in one connection and the schema is consistent.

## Related code

| Component | File | Role |
|-----------|------|------|
| Full migration (temp_files) | `core/db_driver/sqlite.py` | `sync_schema()` with SchemaComparator; single transaction for all statements |
| Migration SQL generation | `core/database/schema_sync.py` | `SchemaComparator.generate_migration_sql()`; RENAME to temp_*, INSERT FROM temp_*, DROP temp_* |
| Recovery (temp_files → files) | `core/db_integrity.py` | `recover_files_table_if_needed(db_path)`; single implementation |
| Driver on connect | `core/database_driver_pkg/drivers/sqlite.py` | Calls recover_files_table_if_needed(db_path) before opening connection |
| repair_sqlite_database command | `commands/database_integrity_mcp_commands.py` | Calls recover_files_table_if_needed when force=false before CONFIRM_REQUIRED |
| Simplified sync (no temp_files) | `core/database_driver_pkg/drivers/sqlite_schema.py` | `SQLiteSchemaManager.sync_schema()`; only creates missing tables |
