# Assignments for 5 models: test fixes (parallel)

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Reference:** [TEST_FIX_PARALLEL_GROUPS.md](TEST_FIX_PARALLEL_GROUPS.md) — groups and path lists.

Each model gets **one group**. No model may edit files from another group. Shared files (e.g. `tests/conftest.py`) may be touched only if the change is necessary for that group and does not break others; prefer group-local fixes.

---

## Role (all 5 models)

- **Executor:** Fix failing tests and collection issues **only** in the assigned group. Do not refactor production code unless the task explicitly requires it. Follow project rules (black, flake8, mypy, file size, docstrings).

---

## Model 1 — Group 1: Database, driver, SQLite, RPC, schema

**Scope:** All test files listed in **Group 1** in [TEST_FIX_PARALLEL_GROUPS.md](TEST_FIX_PARALLEL_GROUPS.md).

**Task:**

1. Run the Group 1 path list:  
   `pytest tests/test_database_transactions.py tests/test_database_transaction_context.py tests/test_database_client.py tests/test_database_client_integration_real_data.py tests/test_database_client_integration_real_server.py tests/test_database_driver_process.py tests/test_database_ast_cst_chunks_verification.py tests/test_database_files_update.py tests/test_database_files_update_real.py tests/test_driver_sqlite.py tests/test_driver_sqlite_batch.py tests/test_driver_sqlite_edge_cases.py tests/test_driver_concurrent.py tests/test_driver_rpc_server.py tests/test_driver_runner.py tests/test_driver_factory.py tests/test_driver_config_file_validation.py tests/test_driver_config_validation.py tests/test_driver_config_validation_errors.py tests/test_driver_integration_real_data.py tests/test_driver_integration_real_server.py tests/test_sqlite_batch.py tests/test_sqlite_driver_transactions.py tests/test_sqlite_proxy_transactions.py tests/test_sqlite_transactions_edge_cases.py tests/test_sqlite_operations_coverage.py tests/test_sqlite_query_journal.py tests/test_sqlite_schema_edge_cases.py tests/test_rpc_client.py tests/test_rpc_server.py tests/test_rpc_server_edge_cases.py tests/test_rpc_server_coverage.py tests/test_rpc_protocol.py tests/test_rpc_request.py tests/test_rpc_result.py tests/test_rpc_handlers.py tests/test_rpc_serialization.py tests/test_request_queue.py tests/test_request_queue_coverage.py tests/test_schema_sync.py tests/test_schema_sync_integration.py tests/test_transient.py tests/test_config_driver_helpers.py tests/test_get_driver_config.py tests/integration/test_database_driver.py -q`
2. Fix every collection error and every test failure in this set. Do not change test files outside Group 1.
3. After fixes: run the same command again; the run must finish with **zero failures** and **zero errors** (green).
4. Run `black`, `flake8`, `mypy` on every modified file.

**Completion:** Group 1 pytest run is green and lint/format checks pass.

**Blackstop:** If a failure can be fixed only by changing production code outside `tests/`, stop and report the file and reason; do not change that production code unless the orchestrator approves.

---

## Model 2 — Group 2: CST, tree, file write, query_cst

**Scope:** All test files listed in **Group 2** in [TEST_FIX_PARALLEL_GROUPS.md](TEST_FIX_PARALLEL_GROUPS.md).

**Task:**

1. Run the Group 2 path list:  
   `pytest tests/test_cst_load_file_command.py tests/test_cst_save_tree_command.py tests/test_cst_modify_tree_command.py tests/test_cst_tree_saver.py tests/test_cst_tree_targeted_access.py tests/test_cst_validation.py tests/test_cst_query_integration.py tests/test_cst_query_parser.py tests/test_cst_query_executor.py tests/test_cst_query_special_chars.py tests/test_cst_compose_atomic_integration.py tests/test_compose_cst_module_ops.py tests/test_tree_modifier.py tests/test_tree_action.py tests/test_update_file_data_atomic.py tests/test_file_write_integrations.py tests/test_file_write_integrations_real.py tests/test_file_tree_snapshot_fidelity.py tests/test_query_cst/ -q`
2. Fix every collection error and every test failure in this set. Do not change test files outside Group 2.
3. After fixes: run the same command again; the run must finish with **zero failures** and **zero errors** (green).
4. Run `black`, `flake8`, `mypy` on every modified file.

**Completion:** Group 2 pytest run is green and lint/format checks pass.

**Blackstop:** If a failure can be fixed only by changing production code outside `tests/`, stop and report the file and reason; do not change that production code unless the orchestrator approves.

---

## Model 3 — Group 3: Commands, project, pipeline

**Scope:** All test files listed in **Group 3** in [TEST_FIX_PARALLEL_GROUPS.md](TEST_FIX_PARALLEL_GROUPS.md).

**Task:**

1. Run the Group 3 path list:  
   `pytest tests/test_project_manager.py tests/test_project_id_validation.py tests/test_project_root_detection.py tests/test_project_discovery.py tests/test_analysis_commands_integration.py tests/test_search_commands.py tests/test_trash_commands.py tests/test_trash_utils.py tests/integration/test_commands.py -q` (pipeline: python scripts/run_pipeline.py)
2. Fix every collection error and every test failure in this set. Do not change test files outside Group 3.
3. Tests that require a running server/DB (e.g. pipeline MCP) may be skipped when the service is unavailable; if you skip them, add a clear skip reason and ensure the rest of the group is green.
4. After fixes: run the same command again; the run must finish with **zero failures** and **zero errors** for the tests that run (skipped are allowed).
5. Run `black`, `flake8`, `mypy` on every modified file.

**Completion:** Group 3 pytest run is green (with documented skips if any) and lint/format checks pass.

**Blackstop:** If a failure can be fixed only by changing production code outside `tests/`, stop and report the file and reason; do not change that production code unless the orchestrator approves.

---

## Model 4 — Group 4: Workers, vectorization, indexing, file watcher

**Scope:** All test files listed in **Group 4** in [TEST_FIX_PARALLEL_GROUPS.md](TEST_FIX_PARALLEL_GROUPS.md).

**Task:**

1. Run the Group 4 path list:  
   `pytest tests/test_indexing_worker.py tests/test_vectorization_integration.py tests/test_worker_manager_database_driver.py tests/test_main_process_integration.py tests/test_file_watcher_integration.py tests/integration/test_workers.py -q`
2. Fix every collection error and every test failure in this set. Do not change test files outside Group 4.
3. Tests that require external services (embedding, chunker, DB driver process) may be skipped when unavailable; if you skip them, add a clear skip reason and ensure the rest of the group is green.
4. After fixes: run the same command again; the run must finish with **zero failures** and **zero errors** for the tests that run (skipped are allowed).
5. Run `black`, `flake8`, `mypy` on every modified file.

**Completion:** Group 4 pytest run is green (with documented skips if any) and lint/format checks pass.

**Blackstop:** If a failure can be fixed only by changing production code outside `tests/`, stop and report the file and reason; do not change that production code unless the orchestrator approves.

---

## Model 5 — Group 5: Entities, object models, regression, misc, performance

**Scope:** All test files listed in **Group 5** in [TEST_FIX_PARALLEL_GROUPS.md](TEST_FIX_PARALLEL_GROUPS.md).

**Task:**

1. Run the Group 5 path list (use the full list from TEST_FIX_PARALLEL_GROUPS.md Group 5; abbreviated here):  
   `pytest tests/test_entity_cross_ref.py tests/test_entity_cross_ref_builder.py tests/test_entity_cross_ref_integration.py tests/test_entity_info_response.py tests/test_ast_dependencies_response.py tests/test_object_models/ tests/test_object_models_integration.py tests/regression/ tests/test_regression.py tests/test_exceptions.py tests/test_constants.py tests/test_settings_manager.py tests/test_path_normalization.py tests/test_fixture_content.py tests/test_edge_cases.py tests/test_mutable_cst_layer.py tests/test_libcst_comment_behavior.py tests/test_client_api.py tests/test_client_api_code_structure_analysis.py tests/test_client_result.py tests/test_docstring_chunker_batch_persist.py tests/test_scanner_with_discovery.py tests/test_comprehensive_analysis_mtime_gate.py tests/test_file_batch_packing.py tests/test_file_data_batch_integration.py tests/test_read_only_batch_command.py tests/test_read_only_batch_whitelist.py tests/test_xpath_filter.py tests/test_ast_cst_operations.py tests/test_ast_cst_operations_integration.py tests/test_migration.py tests/performance/ tests/test_performance.py -q`
2. Fix every collection error and every test failure in this set. Do not change test files outside Group 5.
3. After fixes: run the same command again; the run must finish with **zero failures** and **zero errors** (green).
4. Run `black`, `flake8`, `mypy` on every modified file.

**Completion:** Group 5 pytest run is green and lint/format checks pass.

**Blackstop:** If a failure can be fixed only by changing production code outside `tests/`, stop and report the file and reason; do not change that production code unless the orchestrator approves.

---

## After all 5 complete

Run the full suite from repo root:

```bash
pytest tests/ -q
```

The plan is complete only when this command is green (no collection errors, no test failures). If the full run fails after all groups are green in isolation, the failures are at the boundaries (e.g. shared conftest or imports); the orchestrator will assign a follow-up to fix those.
