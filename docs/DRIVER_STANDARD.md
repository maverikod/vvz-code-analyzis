# Database driver standard

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document defines the standard for database drivers used by the code-analysis server. All drivers must implement the same interface and exchange formats. Batch execution is mandatory; if the DB has no native batch API, the driver emulates it (e.g. loop over `execute` in one transaction).

---

## 1. Purpose and scope

- **Drivers** provide a DB-agnostic way to run SQL and table-level operations.
- **Client** (e.g. `DatabaseClient`) talks to the driver either in-process or via RPC when the driver runs in a **separate process** (e.g. SQLite driver process with its own request queue).
- **Standard** covers: required methods, result shapes, batch contract, and (when used over RPC) the request/response format.

---

## 2. Driver interface (required methods)

The driver implements the interface defined in `BaseDatabaseDriver` (`code_analysis/core/database_driver_pkg/drivers/base.py`).

### 2.1 Lifecycle

| Method | Description |
|--------|-------------|
| `connect(config: Dict[str, Any]) -> None` | Open connection. `config` is driver-specific (e.g. SQLite: `{"path": "..."}`). |
| `disconnect() -> None` | Close connection. |

### 2.2 Table-level CRUD (optional for RPC path)

| Method | Description |
|--------|-------------|
| `create_table(schema) -> bool` | Create table from schema dict. |
| `drop_table(table_name) -> bool` | Drop table. |
| `insert(table_name, data) -> int` | Insert row; return lastrowid. |
| `update(table_name, where, data) -> int` | Update rows; return affected_rows. |
| `delete(table_name, where) -> int` | Delete rows; return affected_rows. |
| `select(table_name, where?, columns?, limit?, offset?, order_by?) -> List[Dict]` | Select rows; return list of dicts. |

### 2.3 SQL execution (mandatory)

| Method | Description |
|--------|-------------|
| `execute(sql, params?, transaction_id?) -> Dict[str, Any]` | Execute one SQL statement. See §3 for result shape. |
| `execute_batch(operations, transaction_id?) -> List[Dict[str, Any]]` | Execute multiple SQL statements in one logical batch. **Mandatory.** See §4. |

### 2.4 Transactions (mandatory)

| Method | Description |
|--------|-------------|
| `begin_transaction() -> str` | Start transaction; return transaction_id. |
| `commit_transaction(transaction_id) -> bool` | Commit. |
| `rollback_transaction(transaction_id) -> bool` | Rollback. |

### 2.5 Schema and metadata

| Method | Description |
|--------|-------------|
| `get_table_info(table_name) -> List[Dict]` | Column info (name, type, nullable, etc.). |
| `sync_schema(schema_definition, backup_dir?) -> Dict` | Synchronize DB schema with definition. |

---

## 3. Result of `execute()`

The return value must be a **dict** with at least:

| Key | Type | Meaning |
|-----|------|---------|
| `affected_rows` | int | Number of rows affected (INSERT/UPDATE/DELETE). |
| `lastrowid` | int or None | Last inserted row ID (INSERT); None if not applicable. |
| `data` | list of dicts | Present for SELECT; each dict is a row (column name → value). Omit for non-SELECT. |

- For SELECT, the driver must set `data` to the list of rows (e.g. `[dict(row) for row in cursor.fetchall()]`).
- For INSERT/UPDATE/DELETE, `data` may be omitted. Client code must not assume `data` exists for non-SELECT.

---

## 4. Batch execution: `execute_batch` (mandatory)

- **Signature:**  
  `execute_batch(operations: List[Tuple[str, Optional[tuple]]], transaction_id: Optional[str] = None) -> List[Dict[str, Any]]`

- **Input:**  
  - `operations`: list of `(sql, params)`.  
  - `params`: tuple or list of bind values (positional `?`), or `None` for no parameters.  
  - `transaction_id`: if set, all statements run in the same transaction.

- **Output:**  
  One result dict per operation, in the same order as `operations`. Each dict has the same shape as `execute()` (§3): `affected_rows`, `lastrowid`, and optionally `data` for SELECT.

- **Requirement:**  
  Every driver **must** support `execute_batch`. If the DB has no native batch API, the driver **emulates** it (e.g. loop over `execute(sql, params, transaction_id)` and return the list of results). This keeps application code simple and ensures one round-trip when the driver is used over RPC.

- **Default implementation (base class):**  
  `return [self.execute(sql, params, transaction_id) for sql, params in operations]`  
  Concrete drivers may override for native batch/executemany if available.

---

## 5. RPC transport (driver in separate process)

When the driver runs in a **separate process** (e.g. SQLite driver process), the client communicates via **RPC over a Unix socket**. Each RPC request is one method call; responses are JSON.

### 5.1 Request shape (generic)

- **JSON object:**  
  `request_id`, `method`, `params` (method-specific dict).

### 5.2 `execute` (RPC)

- **Method:** `"execute"`.
- **Params:**  
  - `sql`: string.  
  - `params`: list or tuple (or null).  
  - `transaction_id`: string or omit.
- **Response (success):**  
  `result.data` = full execute result dict (§3): `affected_rows`, `lastrowid`, `data` (if SELECT).

### 5.3 `execute_batch` (RPC)

- **Method:** `"execute_batch"`.
- **Params:**  
  - `operations`: list of `{"sql": str, "params": list | null}`.  
  - `transaction_id`: string or omit.
- **Response (success):**  
  `result.data.results` = list of result dicts (same shape as §3), one per operation, in order.

### 5.4 Errors (RPC)

- **Response:** `error` with `code` and `message`.
- **Codes:** e.g. `VALIDATION_ERROR`, `DATABASE_ERROR`, `INVALID_REQUEST`, `INTERNAL_ERROR`.

---

## 6. Process and queue (when driver runs out-of-process)

- The driver process is started by the server (e.g. `run_database_driver()` in `database_driver_pkg/runner.py`).
- It owns: **one driver instance**, a **request queue**, and an **RPC server** bound to a Unix socket.
- Each incoming RPC (including one `execute_batch` with many operations) is **one request** in the queue; when processed, the handler calls `driver.execute_batch(operations, transaction_id)` (or the appropriate method). So batching reduces round-trips: one RPC can carry many SQL operations.

---

## 7. Errors (driver layer)

- **DriverConnectionError:** connect/disconnect failures.
- **DriverOperationError:** execute/transaction/schema failures.
- Drivers must not swallow errors; they raise so the client or RPC layer can return an error response.

---

## 8. Summary checklist for driver authors

- [ ] Implement `BaseDatabaseDriver`: `connect`, `disconnect`, `execute`, `execute_batch`, transactions, table CRUD, `get_table_info`, `sync_schema` as required.
- [ ] `execute()` returns a dict with `affected_rows`, `lastrowid`, and `data` (for SELECT only when applicable).
- [ ] `execute_batch()` is implemented (native or as loop over `execute`); returns list of result dicts in order.
- [ ] If the DB has no native batch API, emulate batching (e.g. in one transaction) inside the driver.
- [ ] When used over RPC, the server serializes requests/responses as in §5; no extra fallbacks in application code for “no batch” — the driver always exposes batch.
