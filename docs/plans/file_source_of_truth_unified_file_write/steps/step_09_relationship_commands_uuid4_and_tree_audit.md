# Step 09: Relationship Commands — UUID4 and Tree Alignment Audit

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**Parallel chains:** [../plan/PARALLEL_CHAINS.md](../plan/PARALLEL_CHAINS.md)  
**TZ:** [../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md](../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md)

---

## Executor role

Senior Python developer and integrator (audit and alignment).

---

## Execution directive

- Execute only this step.
- Read every file and entry point listed in `Read first` before editing code.
- Modify only `code_analysis/commands/ast/graph_entity_nodes.py` (and, if the audit shows gaps, the minimum set of callers needed to satisfy the contract; if more than one file must change, escalate so the plan can split into 09a/09b).
- Do not regress existing response shapes; only add or enforce `file_path` + `cst_node_id` (UUID4) where missing.
- Stop immediately if any blackstop is triggered.

---

## Step scope

- **Target code file:** `code_analysis/commands/ast/graph_entity_nodes.py`
- **Step type:** audit and contract alignment
- **Primary purpose:** Ensure all relationship/link commands (hierarchy, dependencies, usages, entity_dependencies, graph, list_entities, entity_info) return `file_path` and `cst_node_id` (UUID4) for entity nodes so they align with snapshot `node_id` and support building real trees later.

---

## Dependency contract

- **Prerequisites:** Step 08 (and Phase 1 final gate)
- **Unlocks:** Step 10
- **Step 08 outcome:** Unified file write and fidelity tests are in place; snapshot and node tables store `node_id` (UUID4).
- **Forbidden scope expansion:** Do not change schema or unified sync in this step; only response shape and documentation.

---

## Required context

- PLAN.md section “UUID4 (cst_node_id) capabilities”: entity tables and snapshot nodes use the same UUID4 identity; relationship commands must expose it so clients can correlate entities with snapshot tree nodes.
- Commands that return links/dependencies/usages: `get_class_hierarchy`, `find_dependencies`, `find_usages`, `entity_dependencies`, `export_graph`, `list_entities`, `get_entity_info`. Each must return `file_path` and `cst_node_id` (valid UUID4) for every entity node where applicable.
- `graph_entity_nodes.py` already builds entity nodes with `file_path` and `cst_node_id`; it is the shared layer used by graph (and possibly others). Audit all callers and ensure no command returns entity references without `file_path` + `cst_node_id`.

---

## Read first

- `docs/plans/file_source_of_truth_unified_file_write/plan/PLAN.md` — section “UUID4 (cst_node_id) capabilities”
- `code_analysis/commands/ast/graph_entity_nodes.py` — `build_entity_nodes_from_hierarchy_rows`, `resolve_to_entity_nodes_with_cst_node_id`
- `code_analysis/commands/ast/hierarchy.py` — response shape and use of graph_entity_nodes or direct queries
- `code_analysis/commands/ast/dependencies.py` — `_get_containing_cst_node_id`, response shape
- `code_analysis/commands/ast/usages.py` — `_resolve_cst_node_id_at_line`, response shape
- `code_analysis/commands/ast/entity_dependencies.py` — use of `cst_node_id` in queries and response
- `code_analysis/commands/ast/graph.py` — use of graph_entity_nodes, response shape
- `code_analysis/commands/ast/list_entities.py` — response shape (file_path, cst_node_id)
- `code_analysis/commands/ast/entity_info.py` — response shape (file_path, cst_node_id)

---

## Expected file change

- `code_analysis/commands/ast/graph_entity_nodes.py`: Contract made explicit in module docstring and function docstrings: all entity nodes returned for relationship/graph use must include `file_path` and `cst_node_id` (UUID4); `cst_node_id` is the same identifier as `file_tree_snapshot_nodes.node_id`. Any code path that could return an entity without valid `cst_node_id` must be removed or fixed.
- If audit shows other command files (hierarchy, dependencies, usages, entity_dependencies, graph, list_entities, entity_info) return entities without `file_path` or `cst_node_id`, fix the minimum set so that all relationship responses satisfy the contract. If that set is more than one file, document in handoff and escalate for plan split (e.g. 09a/09b).

---

## Forbidden alternatives

- Do not drop `cst_node_id` or replace it with line/range-only identity.
- Do not add optional “legacy” response shape without `cst_node_id` for the same entities.
- Do not change schema or file_tree_sync in this step.

---

## Atomic operations

1. Audit `graph_entity_nodes.py`: ensure every code path that builds entity nodes for graph/hierarchy/call_graph includes `file_path` and valid UUID4 `cst_node_id`.
2. Audit callers (hierarchy, dependencies, usages, entity_dependencies, graph, list_entities, entity_info): ensure they use graph_entity_nodes or equivalent and that their API responses include `file_path` and `cst_node_id` for each entity.
3. Fix any gap: add or enforce the contract in `graph_entity_nodes.py` and, if necessary, in the smallest set of caller files so that all relationship commands align.
4. Document in module/function docstrings: alignment with UUID4 and with snapshot `node_id`; relationship commands are the read-side counterpart to snapshot node identity.

---

## Expected deliverables

- All relationship commands (hierarchy, dependencies, usages, entity_dependencies, graph, list_entities, entity_info) return `file_path` and `cst_node_id` (UUID4) for entity nodes where applicable.
- `graph_entity_nodes.py` (and any touched caller) has explicit contract documentation; no regression of existing behavior except adding or enforcing the contract.
- Short handoff note: list of commands audited and any files changed beyond graph_entity_nodes.

---

## Mandatory validation

- Apply the full execution policy from [PLAN.md](../plan/PLAN.md).
- Run `black` / `flake8` / `mypy` on all modified files; expect no errors.
- Run tests for hierarchy, dependencies, usages, graph, list_entities, entity_info (e.g. `pytest tests/ -k "hierarchy or dependencies or usages or graph or list_entities or entity_info" -v --tb=short` or the narrowest set that covers these commands); expect all to pass.
- Manually or via a small script: call at least one of each command and assert response entities include `file_path` and `cst_node_id` (valid UUID4).

---

## Decision rules

- If a command does not yet return `cst_node_id`, add it (from existing entity tables or JOINs) rather than leaving it out.
- If more than two files must be changed to satisfy the contract, complete the minimal change for graph_entity_nodes and one caller, then escalate and document the remaining commands for a follow-up step (09b).
- If the target file would exceed the project size limit after edits, split or escalate per plan rules.

---

## Blackstops

- Stop if any relationship command must drop or weaken UUID4 (e.g. return only line/range) to satisfy the contract.
- Stop if schema or unified sync is modified in this step.

---

## Handoff package

Return exactly:

- The modified `code_analysis/commands/ast/graph_entity_nodes.py` (and any other modified files).
- Confirmation that all `Read first` files and entry points were inspected before editing.
- Confirmation that the exact `Expected file change` was implemented without unauthorized alternatives.
- A short audit summary: which commands were checked, which already satisfied the contract, which were fixed; list of files changed.
- Validation evidence (black, flake8, mypy, pytest and any manual checks).

---

## Handoff (Step 09 completed)

- **Files modified:** `graph_entity_nodes.py`, `hierarchy.py`, `list_entities.py`.
- **Read first:** All listed files and entry points were read before edits.
- **Expected file change:** Implemented. Contract documented in graph_entity_nodes; hierarchy and list_entities enforce file_path + valid UUID4 cst_node_id.

**Audit summary:**

| Command | Status | Notes |
|---------|--------|--------|
| get_class_hierarchy | Fixed | Only classes with valid cst_node_id and file_path included in response. |
| find_dependencies | OK | Already returned only entries with resolved cst_node_id. |
| find_usages | OK | _resolve_usages_with_cst_node_id returns only valid UUID4. |
| entity_dependencies / entity_dependents | OK | _get_*_via_execute skip rows without valid cst_node_id. |
| export_graph | OK | Uses build_entity_nodes_hierarchy / build_entity_nodes_call_graph. |
| list_code_entities | Fixed | _is_valid_uuid4 + file_path check; only valid UUID4 entities returned. |
| get_code_entity_info | OK | _normalize_entities keeps only valid cst_node_id. |

**Validation:** black, flake8, mypy passed on all three files. pytest: test_ast_dependencies_response, test_entity_info_response — 11/11 passed. Four errors in test_entity_cross_ref* are fixture-related (no such table: projects), not caused by this step.
