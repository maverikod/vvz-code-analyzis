# Step 01: query_cst — return UUID in matches[].node_id (file-based path)

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Context:** [../ROOT_CAUSE_AND_TASKS.md](../ROOT_CAUSE_AND_TASKS.md) (section 1)

---

## Executor role

Implementer: ensure that file-based `query_cst` (when running the selector on source without range-only mode) returns `matches[].node_id` as **UUID** (same as tree-based commands), not the legacy synthetic id (`kind:qualname:NodeType:line:col-line:col`).

---

## Execution directive

- Execute only this step. Do not change step 02 or other files except as required by this step.
- Read every file listed in "Read first" before writing code.
- All commands (black, flake8, mypy, tests) from **project root**.
- Mandatory validation: run black, flake8, mypy on modified files; run any existing tests for query_cst or cst_query.

---

## Step scope

- **Target:** `code_analysis/commands/query_cst_command.py` (and optionally a small helper in `code_analysis/core/cst_tree/` if you prefer not to store the tree in the global cache).
- **Change:** When computing `matches` for the **query-only path** (not range_only), build a CST tree from the same `source`, obtain `node_ids_by_exact_key` from its `metadata_map`, and pass it into `query_source(..., node_ids_by_exact_key=node_ids_by_exact_key)` so that `Match.node_id` is set from the tree’s UUIDs.
- **Do not** change the selector logic, the shape of the response, or the range_only / compose_cst_module paths; only ensure that in the path where `query_source(source, selector_for_query, include_code=include_code)` is called, the third conceptual argument `node_ids_by_exact_key` is supplied.

---

## Dependency contract

- **Prerequisites:** None.
- **Unlocks:** Step 02 is independent.
- **Forbidden scope:** Do not change `cst_query/executor.py` contract of `query_source` (signature is already correct); do not change tree-based commands (cst_load_file, cst_find_node, cst_get_node_info).

---

## Read first

- `docs/plans/cst_paradigm_fixes/ROOT_CAUSE_AND_TASKS.md` (section 1)
- `code_analysis/commands/query_cst_command.py` (around the call `query_source(source, selector_for_query, include_code=include_code)`, and how `source` and `file_path` are obtained)
- `code_analysis/cst_query/executor.py` (`query_source` signature and use of `node_ids_by_exact_key`; `Match.node_id = info.node_id or _legacy_node_id(info)`)
- `code_analysis/core/cst_tree/tree_builder.py` (`create_tree_from_code(file_path, source_code, ...)` — returns tree with `metadata_map`; note: it registers tree in `_trees`; if that is undesirable, use a throwaway path or a helper that only builds the metadata map)
- `code_analysis/core/cst_tree/node_id_markers.py` (`build_exact_key_to_id_from_metadata(metadata_map)` → exact_key → node_id dict)
- `code_analysis/core/cst_tree/tree_finder.py` (how `_find_nodes_xpath` calls `query_source` with `node_ids_by_exact_key` for reference)

---

## Expected behavior

- **Before:** `query_cst(project_id, file_path, selector="function[name='main']")` returns `matches[].node_id` like `function:main:FunctionDef:145:0-161:62`.
- **After:** Same call returns `matches[].node_id` as UUID (e.g. `a1b2c3d4-e5f6-7890-abcd-ef1234567890`), consistent with `cst_find_node` + `cst_get_node_info` for the same node.

---

## Implementation notes

1. In the branch where `matches = query_source(source, selector_for_query, include_code=include_code)` is called, you have `source` and (from context) a logical `file_path` or a stable string key for the tree (e.g. resolved path). Use `create_tree_from_code(file_path, source)` (or equivalent) to get a `CSTTree` with `metadata_map`. If the tree must not be stored in the global `_trees`, either call a helper that builds only the metadata map and exact_key map, or build the tree and do not register it (if the API allows), or register and then remove after reading `metadata_map`.
2. Compute `node_ids_by_exact_key = build_exact_key_to_id_from_metadata(tree.metadata_map)`.
3. Call `query_source(source, selector_for_query, include_code=include_code, node_ids_by_exact_key=node_ids_by_exact_key)`.
4. No change to `query_source` itself; it already accepts and uses `node_ids_by_exact_key`.
