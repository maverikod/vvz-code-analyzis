# Step 01: Add shared database holder module

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../PLAN.md](../PLAN.md)  
**Parallel chains:** [../PARALLEL_CHAINS.md](../PARALLEL_CHAINS.md)  
**TZ:** [../TZ.md](../TZ.md)

---

## Executor role

Implementer: add exactly one new module that provides a thread-safe holder for the long-lived database client and a getter that raises if not set. Optionally provide a proxy that forwards all methods to the real client but makes `disconnect()` a no-op so existing command code can keep calling `database.disconnect()` without closing the shared connection.

---

## Execution directive

- Execute only this step.
- Read every file listed in "Read first" before writing code.
- Create only the new file declared in "Target code file"; do not modify other modules.
- Do not invent alternative implementations (e.g. no connection pool, no per-request connection).
- Stop immediately if any blackstop is triggered.

---

## Step scope

- **Target code file:** `code_analysis/core/shared_database.py` (new file)
- **Step type:** New module
- **Primary purpose:** Provide set_shared_database(client), get_shared_database(), close_shared_database(); get_shared_database() returns a proxy that no-ops disconnect() so commands can keep calling disconnect() safely.

---

## Dependency contract

- **Prerequisites:** None (first step).
- **Unlocks:** Step 02 (startup/shutdown will set and close the shared client).
- **Forbidden scope expansion:** Do not touch base_mcp_command.py, main_app_events.py, or any command file in this step.

---

## Required context

- TZ requires one long-lived connection; commands must get it via a shared accessor; disconnect() on the shared client must be a no-op when used from commands.
- No fallback: if shared is not set, get_shared_database() must raise (no "open new connection" fallback).

---

## Read first

- `docs/plans/long_lived_db_connection/TZ.md` (sections 3.4, 4, 5, 6)
- `code_analysis/core/database_client/client.py` (DatabaseClient interface: connect, disconnect, and methods used by commands)
- `code_analysis/commands/base_mcp_command_open_db.py` (to see what type is returned: DatabaseClient)

---

## Expected file change

- New file `code_analysis/core/shared_database.py` with:
  - A thread-safe holder (e.g. a lock and a variable holding the real DatabaseClient or None).
  - `set_shared_database(client: DatabaseClient) -> None`: store the client (or a proxy wrapping it). If already set, either overwrite or raise; TZ does not require “set once only” but implementation must be thread-safe.
  - `get_shared_database() -> DatabaseClient`: return a proxy that forwards all attribute/method access to the stored client except `disconnect()`, which is a no-op. If no client is set, raise a clear exception (e.g. SharedDatabaseNotInitializedError).
  - `close_shared_database() -> None`: call disconnect() on the real stored client, then clear the holder. Idempotent if already closed/cleared.
  - The proxy MUST implement the same public interface as DatabaseClient (connect, disconnect, select, insert, update, delete, execute, list_projects, get_project, etc.) by delegation; disconnect() on the proxy MUST be a no-op.
- File docstring and author/email per project rules. No TODO, no pass, no placeholder logic.

---

## Forbidden alternatives

- Do not add a connection pool or multiple clients.
- Do not make get_shared_database() open a new connection if the holder is empty; it must raise.
- Do not skip the proxy; commands must be able to call disconnect() without closing the real connection.

---

## Atomic operations

1. Create `code_analysis/core/shared_database.py` with a custom exception (e.g. SharedDatabaseNotInitializedError).
2. Implement thread-safe holder (lock + optional reference to real client).
3. Implement proxy class that wraps DatabaseClient and no-ops disconnect(); forward all other method/attribute calls to the wrapped client.
4. Implement set_shared_database(client), get_shared_database(), close_shared_database().
5. Export the exception and the three functions (and proxy if needed for tests). The module is importable as `code_analysis.core.shared_database`; do not add to a top-level `code_analysis/core/__init__.py` if it does not exist.

---

## Expected deliverables

- New module exists and is importable; get_shared_database() raises when not set; after set_shared_database(db), get_shared_database() returns a proxy; proxy.disconnect() is a no-op; close_shared_database() disconnects the real client and clears the holder.

---

## Mandatory validation

- Run `black code_analysis/core/shared_database.py` and expect success with no remaining formatting changes.
- Run `flake8 code_analysis/core/shared_database.py` and expect zero violations.
- Run `mypy code_analysis/core/shared_database.py` and expect zero type errors.
- Run the full test suite (`pytest`); all tests must pass. Step is not complete until the test suite is green.

---

## Decision rules

- The project has no top-level `code_analysis/core/__init__.py`; do not create one for this step. The new module is imported as `from code_analysis.core.shared_database import get_shared_database`, etc.
- If the target file would exceed 350–400 lines, split into two files (e.g. shared_database.py + shared_database_proxy.py) in the same step.

---

## Blackstops

- Stop if you must change any command file or base_mcp_command.py in this step.
- Stop if get_shared_database() could return a non-proxy that would allow disconnect() to close the real connection.

---

## Handoff package

Return: the new file path; confirmation that "Read first" files were read; confirmation that the expected API (set/get/close + proxy with no-op disconnect) is implemented; validation evidence (black, flake8, mypy, pytest); any blockers or risks.
