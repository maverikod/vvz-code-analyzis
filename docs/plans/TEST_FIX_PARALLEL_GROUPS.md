# Test suite: parallel fix groups

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

Purpose: split the test suite into **5 independent groups** so that 5 models can fix failing tests in parallel without editing the same files. Each test file belongs to exactly one group.

---

## Canonical full-suite command

From repo root with `.venv` activated:

```bash
pytest tests/ -q
```

Per-group validation (run only that group):

```bash
pytest <PATH_LIST> -q
```

where `<PATH_LIST>` is the space-separated list from the group below.

---

## Group 1 — Database, driver, SQLite, RPC, schema

**Scope:** Database clients, SQLite driver, RPC server/client, request queue, schema sync, driver config helpers. No overlap with CST/commands/workers/entities.

**Pytest path list (use as-is for `pytest ...`):**

```
tests/test_database_transactions.py
tests/test_database_transaction_context.py
tests/test_database_client.py
tests/test_database_client_integration_real_data.py
tests/test_database_client_integration_real_server.py
tests/test_database_driver_process.py
tests/test_database_ast_cst_chunks_verification.py
tests/test_database_files_update.py
tests/test_database_files_update_real.py
tests/test_driver_sqlite.py
tests/test_driver_sqlite_batch.py
tests/test_driver_sqlite_edge_cases.py
tests/test_driver_concurrent.py
tests/test_driver_rpc_server.py
tests/test_driver_runner.py
tests/test_driver_factory.py
tests/test_driver_config_file_validation.py
tests/test_driver_config_validation.py
tests/test_driver_config_validation_errors.py
tests/test_driver_integration_real_data.py
tests/test_driver_integration_real_server.py
tests/test_sqlite_batch.py
tests/test_sqlite_driver_transactions.py
tests/test_sqlite_proxy_transactions.py
tests/test_sqlite_transactions_edge_cases.py
tests/test_sqlite_operations_coverage.py
tests/test_sqlite_query_journal.py
tests/test_sqlite_schema_edge_cases.py
tests/test_rpc_client.py
tests/test_rpc_server.py
tests/test_rpc_server_edge_cases.py
tests/test_rpc_server_coverage.py
tests/test_rpc_protocol.py
tests/test_rpc_request.py
tests/test_rpc_result.py
tests/test_rpc_handlers.py
tests/test_rpc_serialization.py
tests/test_request_queue.py
tests/test_request_queue_coverage.py
tests/test_schema_sync.py
tests/test_schema_sync_integration.py
tests/test_transient.py
tests/test_config_driver_helpers.py
tests/test_get_driver_config.py
tests/integration/test_database_driver.py
```

---

## Group 2 — CST, tree, file write, update_file_data, query_cst

**Scope:** CST load/save/modify commands, tree saver/targeted access, validation, query executor/parser, compose module ops, tree modifier/action, update_file_data_atomic, file write integrations, file tree snapshot, and the whole `test_query_cst` package.

**Pytest path list:**

```
tests/test_cst_load_file_command.py
tests/test_cst_save_tree_command.py
tests/test_cst_modify_tree_command.py
tests/test_cst_tree_saver.py
tests/test_cst_tree_targeted_access.py
tests/test_cst_validation.py
tests/test_cst_query_integration.py
tests/test_cst_query_parser.py
tests/test_cst_query_executor.py
tests/test_cst_query_special_chars.py
tests/test_cst_compose_atomic_integration.py
tests/test_compose_cst_module_ops.py
tests/test_tree_modifier.py
tests/test_tree_action.py
tests/test_update_file_data_atomic.py
tests/test_file_write_integrations.py
tests/test_file_write_integrations_real.py
tests/test_file_tree_snapshot_fidelity.py
tests/test_query_cst/
```

---

## Group 3 — Commands, project, pipeline

**Scope:** Project manager/discovery/root/ID validation, analysis/search/trash commands, pipeline (MCP commands, data setup, pipeline runner), integration/test_commands.

**Pytest path list:**

```
tests/test_project_manager.py
tests/test_project_id_validation.py
tests/test_project_root_detection.py
tests/test_project_discovery.py
tests/test_analysis_commands_integration.py
tests/test_search_commands.py
tests/test_trash_commands.py
tests/test_trash_utils.py
scripts/pipeline/test_mcp_commands_skeleton.py
scripts/pipeline/test_mcp_commands_db_project_file.py
scripts/pipeline/test_mcp_commands_db_other.py
scripts/pipeline/test_data_setup.py
Run pipeline: python scripts/run_pipeline.py
tests/integration/test_commands.py
```

---

## Group 4 — Workers, vectorization, indexing, file watcher

**Scope:** Indexing worker, vectorization integration, worker manager database driver, main process integration, file watcher integration, integration/test_workers.

**Pytest path list:**

```
tests/test_indexing_worker.py
tests/test_vectorization_integration.py
tests/test_worker_manager_database_driver.py
tests/test_main_process_integration.py
tests/test_file_watcher_integration.py
tests/integration/test_workers.py
```

---

## Group 5 — Entities, object models, regression, misc, performance

**Scope:** Entity cross-ref (builder, integration, response), AST dependencies response, object_models package and integration, regression tests, performance tests, and all remaining unit/misc tests (exceptions, constants, settings, path normalization, fixture content, edge cases, mutable_cst, libcst comment, client_*, docstring chunker, scanner, comprehensive_analysis_mtime_gate, file batch packing, file_data_batch_integration, read_only_batch, xpath_filter, ast_cst_operations, migration, test_performance).

**Pytest path list:**

```
tests/test_entity_cross_ref.py
tests/test_entity_cross_ref_builder.py
tests/test_entity_cross_ref_integration.py
tests/test_entity_info_response.py
tests/test_ast_dependencies_response.py
tests/test_object_models/
tests/test_object_models_integration.py
tests/regression/test_project_management_import_paths.py
tests/regression/test_index_file_fk_race_guard.py
tests/test_regression.py
tests/test_exceptions.py
tests/test_constants.py
tests/test_settings_manager.py
tests/test_path_normalization.py
tests/test_fixture_content.py
tests/test_edge_cases.py
tests/test_mutable_cst_layer.py
tests/test_libcst_comment_behavior.py
tests/test_client_api.py
tests/test_client_api_code_structure_analysis.py
tests/test_client_result.py
tests/test_docstring_chunker_batch_persist.py
tests/test_scanner_with_discovery.py
tests/test_comprehensive_analysis_mtime_gate.py
tests/test_file_batch_packing.py
tests/test_file_data_batch_integration.py
tests/test_read_only_batch_command.py
tests/test_read_only_batch_whitelist.py
tests/test_xpath_filter.py
tests/test_ast_cst_operations.py
tests/test_ast_cst_operations_integration.py
tests/test_migration.py
tests/performance/
tests/test_performance.py
```

---

## Rules

- One test file belongs to **one group only**. No overlap.
- Models must **only** change test files (and, if strictly necessary, shared fixtures in `tests/conftest.py`) for their group. Changing production code is out of scope unless the task explicitly allows it.
- After fixes, each model runs **its group** with `pytest <group path list> -q`. Full suite green is required only after all 5 groups are merged.
- If a test depends on external services (DB socket, MCP server, embedding), either skip when unavailable or document; do not leave the suite definition ambiguous.
