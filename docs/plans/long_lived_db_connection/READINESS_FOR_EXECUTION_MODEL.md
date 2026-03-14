# Readiness for handoff to execution model (Llama-level)

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Purpose:** Checklist and gaps so the plan is unambiguous for an executor model. Fix all "Must fix" items before handoff.

---

## 1. What is ready

- **TZ.md:** Goal, scope, current-code analysis, requirements, constraints, forbidden alternatives, validation, decision rules, and executor handoff (section 10) are clear. References point to real paths.
- **PLAN.md:** Step list, target files, order (01→02→03→04, then 05–09 parallel), validation policy, blackstops.
- **PARALLEL_CHAINS.md:** Dependencies and parallelization are clear.
- **Step files 01, 03, 04, 05–09:** Each has Executor role, Read first, Expected file change, Atomic operations, Forbidden alternatives, Blackstops, Mandatory validation. Scope is one target file per step.
- **Step 02:** Same structure; references integrity/connect/probe and shutdown order.

---

## 2. Must fix before handoff

### 2.1 (Critical) Startup race: shared DB must be set before server accepts requests

**Issue:** In `main_app_events.py`, `_start_workers_bg()` runs in a **daemon background thread**. The startup handler returns right after `thread.start()`, so Hypercorn can accept HTTP (and MCP) requests before the thread has run. If "open DB and set_shared_database" is added only inside that thread, the first command may call `get_shared_database()` before it is set → `SharedDatabaseNotInitializedError`.

**Required change:** In **Step 02** and **TZ section 3.6**:

1. **TZ.md (3.6 Startup):** Add: "The long-lived connection MUST be set (set_shared_database) **before** the server process starts accepting requests. If the DB open runs in a background thread, the startup handler MUST wait for that thread to complete (or for a readiness signal) before returning; do not return from startup while shared_database is still unset."

2. **step_02_startup_shutdown_connection.md:** In "Expected file change" and "Atomic operations", add explicitly:
   - Option A: Run "open DB + set_shared_database" in the **main** startup flow (e.g. before starting the worker thread), so startup blocks until the shared connection is set; then start the worker thread as today.
   - Option B: Run it in the existing background thread but have the startup handler **wait** for completion (e.g. thread.join() with a timeout, or a threading.Event set by the thread when set_shared_database is done). Only then return from startup.
   - Add a Blackstop: "Stop if the server can accept requests before set_shared_database() has been called."

This removes ambiguity for the executor.

### 2.2 Step 03: Tests that run without full server

**Issue:** After Step 03, `_open_database_from_config()` returns `get_shared_database()`, which raises if not set. Tests that invoke commands without starting the real server will fail unless they set up the shared DB.

**Required change:** In **step_03_base_mcp_command_use_shared.md**, in "Mandatory validation" or "Decision rules", add explicitly:

- "If pytest fails because get_shared_database() is not set (e.g. SharedDatabaseNotInitializedError), add or adjust a fixture (e.g. in conftest.py or the failing test module) that: in setup, calls set_shared_database(open_database_from_config_impl(...)) using the same resolve_config_path and get_socket_path as the server; in teardown, calls close_shared_database(). Do not add a fallback inside production code; only test setup may set the shared database for isolated tests."

This tells the executor exactly how to fix failing tests.

### 2.3 Step 01: core/__init__.py

**Issue:** Step 01 says "The project has no top-level code_analysis/core/__init__.py; do not create one." If the project later adds one, or the executor finds an existing one, the rule is clear. Minor: add one line in "Read first" or "Decision rules": "Verify that code_analysis/core/__init__.py does not exist (or do not add the new module to it in this step)." Optional.

---

## 3. Recommended (optional) clarifications

- **Step 02 / Step 04 order:** Step 02 says "if Step 04 is not yet implemented... call existing open_database_from_config_impl()". PLAN order is 01→02→03→04, so Step 02 runs before Step 04. That is correct: Step 02 can call open_database_from_config_impl() and set_shared_database(client_or_proxy); Step 04 later extracts "open once" into a dedicated function. No change needed; executor can follow as-is.
- **Proxy interface (Step 01):** "Forward all attribute/method access except disconnect()" is enough; executor can use __getattr__ delegation. No change needed.
- **Steps 05–09:** Each step is self-contained; "Replace DatabaseClient + connect with _open_database_from_config(); keep database.disconnect() in finally" is clear. No change needed.

---

## 4. Summary

| Item                         | Severity   | Action                                      |
|-----------------------------|------------|---------------------------------------------|
| Startup race (2.1)          | **Critical** | Add to TZ 3.6 and Step 02 (wait/block rule) |
| Test fixtures (2.2)         | **Must fix** | Add to Step 03 (how to fix failing tests)   |
| core/__init__.py (2.3)      | Optional   | Optional one-line note in Step 01           |

**Status:** Items 2.1 and 2.2 have been applied (TZ 3.6, Step 02 Expected file change + Atomic op 5 + Blackstop, Step 03 Decision rules). The plan is ready for handoff to an execution model (Llama-level): order is clear, steps are bounded, validation and blackstops are defined, and the two main ambiguities (startup ordering, test setup) are removed.
