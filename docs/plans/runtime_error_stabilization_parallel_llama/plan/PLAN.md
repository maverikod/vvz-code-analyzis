# Plan: Runtime Error Stabilization (Parallel LLAMA Execution)

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**TZ:** [../TZ_RUNTIME_ERROR_STABILIZATION_PARALLEL_LLAMA.md](../TZ_RUNTIME_ERROR_STABILIZATION_PARALLEL_LLAMA.md)  
**Parallel chains:** [PARALLEL_CHAINS.md](PARALLEL_CHAINS.md)

---

## Executor role

Strict executor (LLAMA-level handoff). Implement exactly as written in step files.

---

## Mandatory gates per step

1. `black <touched_file(s)>`
2. `flake8 <touched_file(s)>`
3. `mypy <touched_file(s)>`
4. Step-specific checks from step file.

Step is not done until all gates pass.

---

## Ordered steps

| Step | Description file |
|---|---|
| 01 | [../steps/step_01_add_import_path_regression_test.md](../steps/step_01_add_import_path_regression_test.md) |
| 02 | [../steps/step_02_fix_permanently_delete_from_trash_imports.md](../steps/step_02_fix_permanently_delete_from_trash_imports.md) |
| 03 | [../steps/step_03_fix_restore_project_from_trash_imports.md](../steps/step_03_fix_restore_project_from_trash_imports.md) |
| 04 | [../steps/step_04_fix_list_trashed_projects_imports.md](../steps/step_04_fix_list_trashed_projects_imports.md) |
| 05 | [../steps/step_05_fix_delete_project_imports.md](../steps/step_05_fix_delete_project_imports.md) |
| 06 | [../steps/step_06_fix_delete_unwatched_projects_imports.md](../steps/step_06_fix_delete_unwatched_projects_imports.md) |
| 07 | [../steps/step_07_fix_change_project_id_imports.md](../steps/step_07_fix_change_project_id_imports.md) |
| 08 | [../steps/step_08_fix_list_projects_imports.md](../steps/step_08_fix_list_projects_imports.md) |
| 09 | [../steps/step_09_fix_vectorization_unpack_in_processing.md](../steps/step_09_fix_vectorization_unpack_in_processing.md) |
| 10 | [../steps/step_10_harden_db_connect_return_contract.md](../steps/step_10_harden_db_connect_return_contract.md) |
| 11 | [../steps/step_11_add_fk_race_guard_in_update_file_data.md](../steps/step_11_add_fk_race_guard_in_update_file_data.md) |
| 12 | [../steps/step_12_add_fk_race_guard_in_index_file_rpc.md](../steps/step_12_add_fk_race_guard_in_index_file_rpc.md) |
| 13 | [../steps/step_13_add_fk_race_regression_test.md](../steps/step_13_add_fk_race_regression_test.md) |

---

## Completion condition

Plan is complete only when:

1. All steps complete with their gates.
2. Full test suite is green.
3. Proxy/server smoke run shows no recurring import-path failures for covered modules.

